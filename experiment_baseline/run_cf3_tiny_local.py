"""Run the detached, local-only matched-CF3 compression/heuristic analysis."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import importlib.metadata
import json
import lzma
import os
import sys
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiment_baseline import cf3_local_core as core  # noqa: E402
from experiment_baseline import cf3_local_primitives as primitive  # noqa: E402


DEFAULT_DOMAINS = ("arxiv", "news", "patent")
APPROVED_CAMPAIGN = {
    "lineage_id": "strict_cf_v1_1_20260905T043848Z",
    "manifest_sha256": "0597a8c885e3abed6cac5439ee8b18066d8cde90e52e02ab05fa02f8ba1855fa",
    "cohort_root_sha256": "27dc6b8d00719dc51fb23c597f30a792764d75c086c9e7a8704a8ee939397029",
    "expected_level_rows": 20000,
}
APPROVED_SNAPSHOT_ANCHORS = {
    "actual_snapshot_sha256": "f68aff149fc053cf8ab5c71ae96738e8962745c7d36203b22c0921247ada4a8f",
    "cohort_roster_sha256": "7d7a0999102a87330d3ef31d6a1a6ffdf895b3ada94d4361a090d1e0838c5f74",
    "exporter_execution_sha256": "3719a2a6b169ab7e83c28ed7f0a83dec657ad7a636d04198e73b448afdbec8d2",
}
APPROVED_FORMAL_MODEL_ROOTS = {
    "gemini-3.6-flash": "3c0580ba4134651fd3223feb995a5aeeac0050c16b624c82dbb7ee269de7ff8f",
    "gpt-5.5": "90d9121f89249928deb3bb1039718a4091e9aa85b1738626b08ac5bcb9b5e069",
    "gpt-5.6-sol": "38c1b54b9e9c5521cb594f7483c63beea141ced56bdda9f34de9307286b4bb25",
}
REQUIRED_INITIAL_FORMAL_MODELS = {
    "gemini-3.6-flash",
    "gpt-5.5",
    "gpt-5.6-sol",
}


def _atomic_json(path: Path, value: object) -> None:
    payload = primitive.canonical_jsonl_row_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _semantic_code_paths() -> tuple[Path, ...]:
    return (
        Path(primitive.__file__),
        Path(core.__file__),
        Path(__file__),
        PROJECT_ROOT / "human_contribution" / "compression.py",
        PROJECT_ROOT / "human_contribution" / "metrics.py",
        PROJECT_ROOT / "experiment_baseline" / "heuristic_overlap_pilot.py",
        PROJECT_ROOT / "experiment_a" / "strict_cf_schema.py",
        PROJECT_ROOT / "experiment_a" / "strict_cf_transport.py",
        PROJECT_ROOT / "experiment_b" / "storage.py",
    )


def _execution_binding() -> dict:
    return {
        "code": [
            {
                "path": str(path.resolve()),
                "sha256": primitive.file_sha256(path),
                "size": path.stat().st_size,
            }
            for path in _semantic_code_paths()
        ],
        "runtime": {
            "python": sys.version,
            "python_implementation": sys.implementation.name,
            "sys_platform": sys.platform,
            "os_name": os.name,
            "numpy": np.__version__,
            "scipy": importlib.metadata.version("scipy"),
            "zlib_compile_version": zlib.ZLIB_VERSION,
            "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
            "bz2_backend_module": str(Path(bz2.__file__).resolve()),
            "lzma_backend_module": str(Path(lzma.__file__).resolve()),
        },
    }


def _output_input_bindings(
    manifest_paths: Sequence[Path], manifests: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "manifest_path": str(path.resolve()),
            "manifest_sha256": primitive.file_sha256(path),
            "snapshot_id": document["snapshot_id"],
            "snapshot_root_sha256": document["snapshot_root_sha256"],
            "wave_id": document["wave_id"],
            "rows_sha256": document["rows"]["sha256"],
        }
        for path, document in zip(manifest_paths, manifests)
    ]


def _scoring_config_sha256(
    manifest_paths: Sequence[Path],
    rows: Sequence[dict],
    execution_binding: Mapping[str, Any],
) -> str:
    return primitive.canonical_sha256(
        {
            "schema": f"{core.SCHEMA}.scoring_work_config",
            "schema_version": core.SCHEMA_VERSION,
            "input_manifests": [
                {
                    "path": str(path.resolve()),
                    "sha256": primitive.file_sha256(path),
                }
                for path in manifest_paths
            ],
            "ordered_input_row_sha256": [
                primitive.canonical_row_sha256(row)
                for row in sorted(rows, key=lambda item: tuple(item["semantic_key"]))
            ],
            "cf3_protocol_sha256": core.CF3_PROTOCOL_SHA256,
            "execution_binding": dict(execution_binding),
        }
    )


def _repair_journal_tail(path: Path) -> bytes:
    if not path.exists():
        return b""
    payload = path.read_bytes()
    if not payload or payload.endswith(b"\n"):
        return payload
    boundary = payload.rfind(b"\n") + 1
    valid = payload[:boundary]
    tail = payload[boundary:]
    tail_path = path.with_name(
        f"{path.name}.malformed-tail-{primitive.sha256_bytes(tail)[:16]}.bin"
    )
    if tail_path.exists():
        if tail_path.read_bytes() != tail:
            raise core.CF3LocalError("existing malformed-tail quarantine differs")
    else:
        core._exclusive_write(tail_path, tail)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.repair.tmp")
    with temporary.open("wb") as handle:
        handle.write(valid)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return valid


def score_rows_resumable(
    input_rows: Sequence[dict],
    *,
    input_manifest_paths: Sequence[Path],
    output_dir: Path,
) -> tuple[list[dict], str, str, dict[str, Any]]:
    """Resume only the status-committed, config-bound journal prefix."""

    core.assert_outside_strict_runs(output_dir, label="analysis output")
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    journal_path = work_dir / "scored_rows.journal.jsonl"
    status_path = work_dir / "scoring_status.json"
    execution_binding = _execution_binding()
    config_sha256 = _scoring_config_sha256(
        input_manifest_paths, input_rows, execution_binding
    )
    ordered_inputs = sorted(input_rows, key=lambda row: tuple(row["semantic_key"]))
    expected = {tuple(row["semantic_key"]): row for row in ordered_inputs}
    empty_hash = primitive.sha256_bytes(b"")
    status_keys = {
        "schema",
        "schema_version",
        "state",
        "config_sha256",
        "created_at_utc",
        "completed_rows",
        "total_rows",
        "journal_size",
        "journal_sha256",
    }
    if status_path.exists():
        status = core._strict_json(status_path.read_bytes(), str(status_path))
        if not isinstance(status, dict) or set(status) != status_keys:
            raise core.CF3LocalError("scoring work status schema mismatch")
        if (
            status["schema"] != f"{core.SCHEMA}.scoring_status"
            or type(status["schema_version"]) is not int
            or status["schema_version"] != core.SCHEMA_VERSION
            or status["state"] not in {"running", "scoring_complete"}
            or status["config_sha256"] != config_sha256
            or status["total_rows"] != len(expected)
            or type(status["completed_rows"]) is not int
            or type(status["journal_size"]) is not int
            or not isinstance(status["created_at_utc"], str)
        ):
            raise core.CF3LocalError("scoring work status binding mismatch")
    elif journal_path.exists():
        raise core.CF3LocalError("scoring journal exists without its config-bound status")
    else:
        status = {
            "schema": f"{core.SCHEMA}.scoring_status",
            "schema_version": core.SCHEMA_VERSION,
            "state": "running",
            "config_sha256": config_sha256,
            "created_at_utc": core.utc_now(),
            "completed_rows": 0,
            "total_rows": len(expected),
            "journal_size": 0,
            "journal_sha256": empty_hash,
        }
        _atomic_json(status_path, status)

    payload = _repair_journal_tail(journal_path)
    committed_size = status["journal_size"]
    if committed_size < 0 or committed_size > len(payload):
        raise core.CF3LocalError("journal is shorter than its durable status prefix")
    committed = payload[:committed_size]
    if primitive.sha256_bytes(committed) != status["journal_sha256"]:
        raise core.CF3LocalError("journal committed-prefix hash mismatch")
    if len(payload) > committed_size:
        tail = payload[committed_size:]
        tail_path = journal_path.with_name(
            f"{journal_path.name}.uncommitted-tail-{primitive.sha256_bytes(tail)[:16]}.bin"
        )
        if tail_path.exists():
            if tail_path.read_bytes() != tail:
                raise core.CF3LocalError("existing uncommitted-tail quarantine differs")
        else:
            core._exclusive_write(tail_path, tail)
        temporary = journal_path.with_name(
            f".{journal_path.name}.{os.getpid()}.uncommitted.tmp"
        )
        with temporary.open("wb") as handle:
            handle.write(committed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, journal_path)
        payload = committed

    completed: dict[tuple[str, ...], dict] = {}
    for line_number, raw in enumerate(payload.splitlines(), 1):
        parsed = core._strict_json(raw, f"{journal_path}:{line_number}")
        key_value = parsed.get("semantic_key") if isinstance(parsed, dict) else None
        key = tuple(key_value) if isinstance(key_value, list) else ()
        input_row = expected.get(key)
        if input_row is None:
            raise core.CF3LocalError(f"scoring journal contains unexpected key {key!r}")
        value = core.validate_scored_against_input(
            parsed,
            input_row,
            path=f"{journal_path}:{line_number}",
        )
        if key in completed:
            raise core.CF3LocalError(f"scoring journal duplicates key {key!r}")
        completed[key] = value
    if len(completed) != status["completed_rows"]:
        raise core.CF3LocalError("journal row count differs from durable status")

    digest = hashlib.sha256(payload)
    journal_size = len(payload)
    with journal_path.open("ab") as handle:
        for row in ordered_inputs:
            key = tuple(row["semantic_key"])
            if key in completed:
                continue
            scored = core.score_input_row(row)
            row_payload = primitive.canonical_jsonl_row_bytes(scored)
            handle.write(row_payload)
            handle.flush()
            os.fsync(handle.fileno())
            digest.update(row_payload)
            journal_size += len(row_payload)
            completed[key] = scored
            status = {
                **status,
                "state": (
                    "scoring_complete"
                    if len(completed) == len(expected)
                    else "running"
                ),
                "completed_rows": len(completed),
                "journal_size": journal_size,
                "journal_sha256": digest.hexdigest(),
            }
            _atomic_json(status_path, status)
    if set(completed) != set(expected):
        raise core.CF3LocalError("scoring journal did not reach exact input coverage")
    return (
        [completed[key] for key in sorted(completed)],
        config_sha256,
        status["created_at_utc"],
        execution_binding,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze an immutable detached CF3 snapshot locally. This command has "
            "no API/model/GPU path and refuses live strict-CF run inputs."
        )
    )
    parser.add_argument(
        "--input-manifest",
        type=Path,
        required=True,
        action="append",
        help="Detached snapshot manifest; repeat for later disjoint waves",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--balanced-domains",
        default=",".join(DEFAULT_DOMAINS),
        help="Comma-separated balanced-core domains (default: arxiv,news,patent)",
    )
    parser.add_argument(
        "--balanced-per-stratum",
        type=int,
        default=0,
        help="Common-source quota per domain; 0 uses the largest feasible equal quota",
    )
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260908)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.bootstrap < 0:
        raise core.CF3LocalError("--bootstrap must be nonnegative")
    if args.balanced_per_stratum < 0:
        raise core.CF3LocalError("--balanced-per-stratum must be nonnegative")
    core.assert_outside_strict_runs(args.output_dir, label="analysis output")
    domains = tuple(
        part.strip().lower()
        for part in args.balanced_domains.split(",")
        if part.strip()
    )
    if not domains:
        raise core.CF3LocalError("--balanced-domains cannot be empty")
    analysis_request = {
        "balanced_domains": list(domains),
        "balanced_common_sources_requested": args.balanced_per_stratum,
        "bootstrap_replicates": args.bootstrap,
        "seed": args.seed,
    }

    input_manifests, input_rows = core.load_snapshots(args.input_manifest)
    if input_manifests[0]["campaign"] != APPROVED_CAMPAIGN:
        raise core.CF3LocalError(
            "input snapshot does not bind the precommitted strict_cf_v1_1 campaign"
        )
    for manifest_path, manifest in zip(args.input_manifest, input_manifests):
        observed_anchors = {
            "actual_snapshot_sha256": manifest["freeze"]["actual_snapshot_sha256"],
            "cohort_roster_sha256": manifest["cohort_roster"]["sha256"],
            "exporter_execution_sha256": manifest["freeze"]["exporter_execution_sha256"],
        }
        if observed_anchors != APPROVED_SNAPSHOT_ANCHORS:
            raise core.CF3LocalError(
                "input snapshot does not bind the approved actual roster/exporter"
            )
        formal_roots = core.formal_inventory_model_roots(
            core._load_formal_inventory(manifest_path.resolve(), manifest)
        )
        if not REQUIRED_INITIAL_FORMAL_MODELS.issubset(formal_roots):
            raise core.CF3LocalError("snapshot omits a required approved formal model")
        if any(
            APPROVED_FORMAL_MODEL_ROOTS.get(model) != root
            for model, root in formal_roots.items()
        ):
            raise core.CF3LocalError("snapshot contains an unapproved formal model root")
    if (args.output_dir / "output_manifest.json").exists():
        manifest = core.validate_completed_output(args.output_dir)
        current_execution = _execution_binding()
        expected_config = _scoring_config_sha256(
            args.input_manifest, input_rows, current_execution
        )
        if (
            manifest["inputs"]
            != _output_input_bindings(args.input_manifest, input_manifests)
            or manifest["analysis_request"] != analysis_request
            or manifest["execution_binding"] != current_execution
            or manifest["execution_config_sha256"] != expected_config
        ):
            raise core.CF3LocalError(
                "existing completed output belongs to another input/configuration"
            )
        print(
            "CF3 local analysis is already complete and hash-valid: "
            f"{args.output_dir / 'output_manifest.json'}"
        )
        return 0
    (
        scored_rows,
        execution_config_sha256,
        run_created_at_utc,
        execution_binding,
    ) = score_rows_resumable(
        input_rows,
        input_manifest_paths=args.input_manifest,
        output_dir=args.output_dir,
    )
    all_ready_summary = core.summarize_scored_rows(
        scored_rows,
        bootstrap_replicates=args.bootstrap,
        seed=args.seed,
        cohort_label="all newly eligible frozen waves (primary exploratory cohort)",
        created_at_utc=run_created_at_utc,
        bootstrap_checkpoint_path=args.output_dir / "_work" / "bootstrap_all.json",
        bootstrap_checkpoint_context={
            "execution_config_sha256": execution_config_sha256,
            "cohort": "all_newly_eligible_waves",
        },
    )
    balanced_rows, balanced_manifest = core.select_balanced_core(
        scored_rows,
        domains=domains,
        seed=args.seed,
        per_stratum=(
            args.balanced_per_stratum
            if args.balanced_per_stratum > 0
            else None
        ),
    )
    balanced_summary = core.summarize_scored_rows(
        balanced_rows,
        bootstrap_replicates=args.bootstrap,
        seed=args.seed,
        cohort_label="common-source model-and-domain balanced core (sensitivity cohort)",
        created_at_utc=run_created_at_utc,
        bootstrap_checkpoint_path=args.output_dir / "_work" / "bootstrap_balanced.json",
        bootstrap_checkpoint_context={
            "execution_config_sha256": execution_config_sha256,
            "cohort": "common_source_balanced",
            "semantic_keys_sha256": balanced_manifest["semantic_keys_sha256"],
        },
    )
    if _execution_binding() != execution_binding or _scoring_config_sha256(
        args.input_manifest, input_rows, execution_binding
    ) != execution_config_sha256:
        raise core.CF3LocalError(
            "execution code/runtime or input manifests changed before publication"
        )
    manifest_path = core.write_analysis_bundle(
        args.output_dir,
        input_manifest_paths=args.input_manifest,
        input_manifests=input_manifests,
        scored_rows=scored_rows,
        all_ready_summary=all_ready_summary,
        balanced_rows=balanced_rows,
        balanced_manifest=balanced_manifest,
        balanced_summary=balanced_summary,
        execution_config_sha256=execution_config_sha256,
        execution_binding=execution_binding,
        analysis_request=analysis_request,
        created_at_utc=run_created_at_utc,
    )
    print(
        f"CF3 local analysis complete: {len(scored_rows)} level rows; "
        f"output manifest {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
