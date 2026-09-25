"""Create a verified detached copy during an explicitly approved freeze window.

This helper performs no API/model/GPU work and never writes the source run.  It
requires the launcher and workers to remain psutil ``stopped`` throughout the
copy, compares source/destination checkpoint and formal inventories, and atomically
publishes a detached directory containing the sentinel required by the CF3
exporter.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiment_baseline import cf3_local_core as core  # noqa: E402
from experiment_baseline import cf3_local_primitives as primitive  # noqa: E402
from experiment_baseline import export_cf3_detached_snapshot as exporter  # noqa: E402
from experiment_baseline import run_cf3_tiny_local as local_runner  # noqa: E402


COPY_RELATIVE_PATHS = (
    "manifest.json",
    "snapshots/actual_levels.jsonl",
    "checkpoints",
    "formal",
    "route_candidates",
    "quarantine/route_smoke",
)


class DetachedCopyError(RuntimeError):
    """Raised when a quiescent detached copy cannot be proven safe."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_state(
    launcher_pid: int, worker_pids: Sequence[int]
) -> dict[str, Any]:
    if launcher_pid in worker_pids or len(worker_pids) != len(set(worker_pids)):
        raise DetachedCopyError("launcher/worker PID roster is invalid")
    processes: dict[int, psutil.Process] = {}
    for pid in (launcher_pid, *worker_pids):
        try:
            processes[pid] = psutil.Process(pid)
        except psutil.Error as exc:
            raise DetachedCopyError(f"required frozen process is unavailable: {pid}") from exc
    statuses = {pid: process.status() for pid, process in processes.items()}
    if any(status != psutil.STATUS_STOPPED for status in statuses.values()):
        raise DetachedCopyError(f"strict-CF process is not stopped: {statuses}")
    worker_children = {
        pid: [child.pid for child in processes[pid].children(recursive=True)]
        for pid in worker_pids
    }
    if any(worker_children.values()):
        raise DetachedCopyError(
            f"a frozen strict-CF worker has children: {worker_children}"
        )
    launcher_children = {
        child.pid for child in processes[launcher_pid].children(recursive=False)
    }
    if launcher_children != set(worker_pids):
        raise DetachedCopyError(
            "launcher direct children differ from approved workers: "
            f"{sorted(launcher_children)} != {sorted(worker_pids)}"
        )
    return {
        "checked_at_utc": utc_now(),
        "launcher_pid": launcher_pid,
        "worker_pids": list(worker_pids),
        "statuses": {str(pid): statuses[pid] for pid in sorted(statuses)},
    }


def _reject_symlinks(root: Path, relative_paths: Sequence[str]) -> None:
    root = root.resolve(strict=True)
    for relative in relative_paths:
        candidate = root / Path(relative)
        if not candidate.exists():
            continue
        cursor = root
        for part in Path(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise DetachedCopyError(f"source evidence path is symlinked: {cursor}")
        if candidate.is_dir():
            for path in candidate.rglob("*"):
                if path.is_symlink():
                    raise DetachedCopyError(
                        f"source evidence tree contains symlink: {path}"
                    )


def _copy_required(source: Path, staging: Path) -> None:
    for relative in COPY_RELATIVE_PATHS:
        source_path = source / Path(relative)
        if not source_path.exists():
            if relative in {"manifest.json", "snapshots/actual_levels.jsonl"}:
                raise DetachedCopyError(f"required source artifact is missing: {relative}")
            continue
        destination = staging / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, destination, symlinks=False)
        else:
            shutil.copy2(source_path, destination, follow_symlinks=False)


def make_detached_copy(
    source_run: Path,
    destination: Path,
    *,
    launcher_pid: int,
    worker_pids: Sequence[int],
) -> dict[str, Any]:
    source = source_run.resolve(strict=True)
    if not core._inside_active_run(source):
        raise DetachedCopyError("source must be a canonical strict-CF run tree")
    destination = core.assert_outside_strict_runs(
        destination, label="detached destination"
    )
    if destination.exists():
        raise DetachedCopyError(f"detached destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlinks(source, COPY_RELATIVE_PATHS)

    process_before = _process_state(launcher_pid, worker_pids)
    manifest_path = source / "manifest.json"
    actual_path = source / "snapshots" / "actual_levels.jsonl"
    if primitive.file_sha256(manifest_path) != exporter.APPROVED["manifest_sha256"]:
        raise DetachedCopyError("source manifest differs from approved campaign")
    if (
        primitive.file_sha256(actual_path)
        != exporter.APPROVED["actual_snapshot_sha256"]
    ):
        raise DetachedCopyError("source actual snapshot differs from approved campaign")
    checkpoint_before, checkpoint_hash = exporter._checkpoint_inventory(source)
    _, formal_before, formal_hash = exporter._load_formal_bindings(source)
    formal_roots = core.formal_inventory_model_roots(formal_before)
    if formal_roots != local_runner.APPROVED_FORMAL_MODEL_ROOTS:
        raise DetachedCopyError(
            f"source formal model roots differ from approved roots: {formal_roots}"
        )
    _process_state(launcher_pid, worker_pids)

    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    try:
        staging.mkdir(exist_ok=False)
        _copy_required(source, staging)
        checkpoint_copy, checkpoint_copy_hash = exporter._checkpoint_inventory(staging)
        _, formal_copy, formal_copy_hash = exporter._load_formal_bindings(staging)
        if (
            checkpoint_copy != checkpoint_before
            or checkpoint_copy_hash != checkpoint_hash
        ):
            raise DetachedCopyError(
                "detached checkpoint inventory differs from frozen source"
            )
        if formal_copy != formal_before or formal_copy_hash != formal_hash:
            raise DetachedCopyError("detached formal inventory differs from frozen source")

        process_after = _process_state(launcher_pid, worker_pids)
        checkpoint_after, checkpoint_after_hash = exporter._checkpoint_inventory(source)
        _, formal_after, formal_after_hash = exporter._load_formal_bindings(source)
        if (
            checkpoint_after != checkpoint_before
            or checkpoint_after_hash != checkpoint_hash
        ):
            raise DetachedCopyError("source checkpoint inventory changed during copy")
        if formal_after != formal_before or formal_after_hash != formal_hash:
            raise DetachedCopyError("source formal inventory changed during copy")

        sentinel = {
            "schema": f"{core.SCHEMA}.detached_copy",
            "schema_version": core.SCHEMA_VERSION,
            "source_lineage_id": exporter.APPROVED["lineage_id"],
            "source_manifest_sha256": exporter.APPROVED["manifest_sha256"],
            "actual_snapshot_sha256": exporter.APPROVED["actual_snapshot_sha256"],
            "workers_stopped_verified_at_utc": process_before["checked_at_utc"],
            "copy_completed_at_utc": process_after["checked_at_utc"],
            "copy_method": (
                "selective byte copy while launcher/workers were psutil stopped; "
                "source and detached checkpoint/formal inventories compared"
            ),
            "checkpoint_inventory_sha256": checkpoint_hash,
            "checkpoint_file_count": len(checkpoint_before),
            "formal_inventory_sha256": formal_hash,
            "formal_file_count": len(formal_before),
            "approved_exporter_execution_sha256": (
                exporter.exporter_execution_sha256()
            ),
            "immutable": True,
        }
        core._exclusive_write(
            staging / exporter.SENTINEL_NAME,
            primitive.canonical_jsonl_row_bytes(sentinel),
        )
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return {
        "destination": str(destination),
        "copy_completed_at_utc": sentinel["copy_completed_at_utc"],
        "checkpoint_file_count": len(checkpoint_before),
        "checkpoint_inventory_sha256": checkpoint_hash,
        "formal_file_count": len(formal_before),
        "formal_inventory_sha256": formal_hash,
        "actual_snapshot_sha256": primitive.file_sha256(
            destination / "snapshots" / "actual_levels.jsonl"
        ),
        "sentinel_sha256": primitive.file_sha256(
            destination / exporter.SENTINEL_NAME
        ),
        "process_state_before": process_before,
        "process_state_after": process_after,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a detached CF3 copy during an approved stopped-worker window."
    )
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--launcher-pid", type=int, required=True)
    parser.add_argument("--worker-pid", type=int, action="append", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = make_detached_copy(
        args.source_run,
        args.destination,
        launcher_pid=args.launcher_pid,
        worker_pids=args.worker_pid,
    )
    print(primitive.canonical_json_bytes(receipt).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
