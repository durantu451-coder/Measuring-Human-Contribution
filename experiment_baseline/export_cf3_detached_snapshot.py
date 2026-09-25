"""Export a CF3 wave from a verified quiescent copy of a strict-CF run.

This command must never be pointed at the canonical live run.  It performs no
API/model/GPU/SSH operation, but it imports the formal strict checkpoint
validators so it must run only after a designated process has copied a naturally
stopped run into an external detached directory and written the required sentinel.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiment_a import run_strict_cf_v1 as strict_runner  # noqa: E402
from experiment_a import strict_cf_route_bundle as route_bundle  # noqa: E402
from experiment_a import strict_cf_routes as strict_routes  # noqa: E402
from experiment_a import strict_cf_schema as strict_schema  # noqa: E402
from experiment_a import strict_cf_transport as strict_transport  # noqa: E402
from experiment_baseline import cf3_local_core as core  # noqa: E402
from experiment_baseline import cf3_local_primitives as primitive  # noqa: E402


APPROVED = {
    "lineage_id": "strict_cf_v1_1_20260905T043848Z",
    "manifest_sha256": "0597a8c885e3abed6cac5439ee8b18066d8cde90e52e02ab05fa02f8ba1855fa",
    "cohort_root_sha256": "27dc6b8d00719dc51fb23c597f30a792764d75c086c9e7a8704a8ee939397029",
    "core_inventory_sha256": "c2d8bb3a0b5c085b5b6b5d0871f9cb6312685d69cccfb5d49c924764c7e32cdf",
    "actual_snapshot_sha256": "f68aff149fc053cf8ab5c71ae96738e8962745c7d36203b22c0921247ada4a8f",
    "cohort_roster_sha256": "7d7a0999102a87330d3ef31d6a1a6ffdf895b3ada94d4361a090d1e0838c5f74",
    "expected_level_rows": 20000,
}
SENTINEL_NAME = "DETACHED_QUIESCENT_COPY.json"
SENTINEL_KEYS = {
    "schema",
    "schema_version",
    "source_lineage_id",
    "source_manifest_sha256",
    "actual_snapshot_sha256",
    "workers_stopped_verified_at_utc",
    "copy_completed_at_utc",
    "copy_method",
    "checkpoint_inventory_sha256",
    "checkpoint_file_count",
    "formal_inventory_sha256",
    "formal_file_count",
    "approved_exporter_execution_sha256",
    "immutable",
}


class CF3ExportError(RuntimeError):
    """Raised when detached evidence cannot be exported fail-closed."""


def exporter_execution_binding() -> dict[str, Any]:
    paths = (
        Path(__file__),
        Path(core.__file__),
        Path(primitive.__file__),
        Path(strict_runner.__file__),
        Path(strict_schema.__file__),
        Path(strict_routes.__file__),
        Path(route_bundle.__file__),
        Path(strict_transport.__file__),
        PROJECT_ROOT / "experiment_b" / "storage.py",
    )
    return {
        "code": [
            {
                "path": str(path.resolve()),
                "sha256": primitive.file_sha256(path),
                "size": path.stat().st_size,
            }
            for path in paths
        ],
        "runtime": {
            "python": sys.version,
            "python_implementation": sys.implementation.name,
            "sys_platform": sys.platform,
            "os_name": os.name,
        },
    }


def exporter_execution_sha256() -> str:
    return primitive.canonical_sha256(exporter_execution_binding())


def _bound_file(root: Path, relative: str | Path) -> Path:
    root = root.resolve(strict=True)
    raw = Path(relative)
    if raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
        raise CF3ExportError(f"unsafe detached relative path: {relative}")
    cursor = root
    for part in raw.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CF3ExportError(f"detached artifact path contains symlink: {cursor}")
    resolved = cursor.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CF3ExportError(f"detached artifact escapes root: {relative}") from exc
    if not resolved.is_file():
        raise CF3ExportError(f"detached artifact is not a regular file: {relative}")
    return resolved


def _safe_source_key(row: Mapping[str, Any]) -> str:
    identity = [
        str(row["generation_model"]),
        str(row["domain"]),
        str(row["id"]),
        str(row["source_text_sha256"]),
    ]
    source = primitive.canonical_json_bytes(identity)
    slug_source = str(row.get("id") or row.get("source_id") or "source")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug_source).strip(" ._") or "source"
    digest = hashlib.sha256(source).hexdigest()[:16]
    return f"{slug[:48]}-{digest}"


def checkpoint_relative_path(row: Mapping[str, Any]) -> str:
    model = str(row["generation_model"])
    domain = str(row["domain"])
    level = str(row["level"])
    for value in (model, domain, level):
        if value in {"", ".", ".."} or "/" in value or "\\" in value:
            raise CF3ExportError(f"unsafe checkpoint identity component {value!r}")
    return (
        Path("checkpoints")
        / model
        / domain
        / _safe_source_key(row)
        / f"{level}.json"
    ).as_posix()


def _checkpoint_inventory(root: Path) -> tuple[list[dict[str, Any]], str]:
    checkpoint_root = root / "checkpoints"
    if checkpoint_root.is_symlink():
        raise CF3ExportError("detached checkpoints root is a symlink")
    if not checkpoint_root.is_dir():
        return [], primitive.canonical_sha256([])
    entries = []
    for path in checkpoint_root.rglob("*"):
        if path.is_symlink():
            raise CF3ExportError(f"detached checkpoint tree contains symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not re.fullmatch(r"checkpoints/[^/]+/[^/]+/[^/]+/L[1-5]\.json", relative):
            raise CF3ExportError(f"noncanonical detached checkpoint path: {relative}")
        path = _bound_file(root, relative)
        entries.append(
            {
                "path": relative,
                "sha256": primitive.file_sha256(path),
                "size": path.stat().st_size,
            }
        )
    entries.sort(key=lambda entry: entry["path"])
    return entries, primitive.canonical_sha256(entries)


def _validate_sentinel(
    root: Path,
    *,
    inventory_sha256: str,
    inventory_count: int,
    formal_inventory_sha256: str,
    formal_file_count: int,
) -> dict[str, Any]:
    path = _bound_file(root, SENTINEL_NAME)
    value = core._strict_json(path.read_bytes(), str(path))
    if not isinstance(value, Mapping) or set(value) != SENTINEL_KEYS:
        raise CF3ExportError("detached-copy sentinel keys are not exact")
    expected = {
        "schema": f"{core.SCHEMA}.detached_copy",
        "schema_version": core.SCHEMA_VERSION,
        "source_lineage_id": APPROVED["lineage_id"],
        "source_manifest_sha256": APPROVED["manifest_sha256"],
        "actual_snapshot_sha256": APPROVED["actual_snapshot_sha256"],
        "checkpoint_inventory_sha256": inventory_sha256,
        "checkpoint_file_count": inventory_count,
        "formal_inventory_sha256": formal_inventory_sha256,
        "formal_file_count": formal_file_count,
        "approved_exporter_execution_sha256": exporter_execution_sha256(),
        "immutable": True,
    }
    for field, required in expected.items():
        if value[field] != required:
            raise CF3ExportError(f"detached-copy sentinel {field} mismatch")
    for field in (
        "workers_stopped_verified_at_utc",
        "copy_completed_at_utc",
        "copy_method",
    ):
        if not isinstance(value[field], str) or not value[field].strip():
            raise CF3ExportError(f"detached-copy sentinel {field} is blank")
    return dict(value)


def _load_manifest(root: Path) -> dict[str, Any]:
    path = _bound_file(root, "manifest.json")
    if primitive.file_sha256(path) != APPROVED["manifest_sha256"]:
        raise CF3ExportError("detached manifest does not match the approved campaign")
    manifest = core._strict_json(path.read_bytes(), str(path))
    if not isinstance(manifest, Mapping):
        raise CF3ExportError("detached manifest root is not an object")
    if (
        manifest.get("lineage_id") != APPROVED["lineage_id"]
        or manifest.get("cohort", {}).get("root_sha256")
        != APPROVED["cohort_root_sha256"]
        or manifest.get("expected_counts", {}).get("level_rows")
        != APPROVED["expected_level_rows"]
    ):
        raise CF3ExportError("detached manifest scientific identity mismatch")
    return dict(manifest)


def _load_actual_rows(root: Path) -> tuple[list[dict[str, Any]], str]:
    path = _bound_file(root, "snapshots/actual_levels.jsonl")
    if primitive.file_sha256(path) != APPROVED["actual_snapshot_sha256"]:
        raise CF3ExportError("detached actual snapshot hash mismatch")
    payload = path.read_bytes()
    if not payload.endswith(b"\n"):
        raise CF3ExportError("detached actual snapshot lacks terminal LF")
    rows = []
    seen: set[tuple[str, ...]] = set()
    roster = []
    for line_number, raw in enumerate(payload.splitlines(), 1):
        value = core._strict_json(raw, f"{path}:{line_number}")
        try:
            strict_schema.validate_actual_snapshot_row(
                value,
                seen_keys=seen,
                path=f"{path}:{line_number}",
            )
        except Exception as exc:
            raise CF3ExportError(f"invalid actual snapshot row {line_number}: {exc}") from exc
        row = dict(value)
        rows.append(row)
        roster.append(
            {
                "semantic_key": list(row["semantic_key"]),
                "source_row_sha256": primitive.canonical_row_sha256(row),
            }
        )
    if len(rows) != APPROVED["expected_level_rows"]:
        raise CF3ExportError("detached actual snapshot row count mismatch")
    roster.sort(key=lambda row: tuple(row["semantic_key"]))
    roster_payload = b"".join(
        primitive.canonical_jsonl_row_bytes(row) for row in roster
    )
    roster_hash = primitive.sha256_bytes(roster_payload)
    if roster_hash != APPROVED["cohort_roster_sha256"]:
        raise CF3ExportError("derived immutable cohort roster hash mismatch")
    return rows, roster_hash


def _formal_binding(
    root: Path, model: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    relative_pointer = f"formal/{model}.json"
    pointer_candidate = root / Path(relative_pointer)
    if not pointer_candidate.exists():
        return None, []
    pointer_path = _bound_file(root, relative_pointer)
    value = core._strict_json(pointer_path.read_bytes(), str(pointer_path))
    pointer_keys = {
        "schema",
        "schema_version",
        "campaign",
        "generation_model",
        "bundle_path",
        "bundle_sha256",
        "bundle_manifest_sha256",
        "committed_sha256",
        "transport_abi_version",
        "transport_abi_sha256",
        "protocol_sha256",
        "route_id",
        "client_id",
        "coordination",
        "smoke_report_path",
        "smoke_report_sha256",
        "promoted_at_utc",
    }
    if not isinstance(value, Mapping) or set(value) != pointer_keys:
        raise CF3ExportError(f"formal binding for {model} has non-exact keys")
    expected_campaign = {
        "lineage_id": APPROVED["lineage_id"],
        "manifest_sha256": APPROVED["manifest_sha256"],
        "cohort_root_sha256": APPROVED["cohort_root_sha256"],
        "core_inventory_sha256": APPROVED["core_inventory_sha256"],
    }
    if (
        value["schema"] != route_bundle.FORMAL_BINDING_SCHEMA
        or value["schema_version"] != route_bundle.FORMAL_SCHEMA_VERSION
        or value["campaign"] != expected_campaign
        or value["generation_model"] != model
        or value["transport_abi_version"] != strict_schema.TRANSPORT_ABI_VERSION
        or value["transport_abi_sha256"] != strict_schema.TRANSPORT_ABI_SHA256
    ):
        raise CF3ExportError(f"formal binding for {model} has invalid identity")

    bundle_sha = value["bundle_sha256"]
    if not isinstance(bundle_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", bundle_sha):
        raise CF3ExportError(f"formal binding for {model} has invalid bundle hash")
    expected_bundle_path = f"{route_bundle.CANDIDATES_REL}/{model}/{bundle_sha}"
    if value["bundle_path"] != expected_bundle_path:
        raise CF3ExportError(f"formal binding for {model} has invalid bundle path")
    bundle_manifest_path = _bound_file(root, f"{expected_bundle_path}/bundle.json")
    commit_path = _bound_file(root, f"{expected_bundle_path}/COMMITTED")
    bundle = core._strict_json(
        bundle_manifest_path.read_bytes(), str(bundle_manifest_path)
    )
    bundle_keys = {
        "schema",
        "schema_version",
        "campaign",
        "generation_model",
        "route_id",
        "client_id",
        "transport_abi_version",
        "transport_abi_sha256",
        "protocol",
        "entrypoint",
        "project_dependency_inventory",
        "project_dependency_inventory_sha256",
        "external_dependency_inventory",
        "external_dependency_inventory_sha256",
        "environment_contract",
        "runtime_fingerprint",
        "runtime_fingerprint_sha256",
        "external_runtime_fingerprint",
        "coordination",
    }
    if not isinstance(bundle, Mapping) or set(bundle) != bundle_keys:
        raise CF3ExportError(f"candidate bundle for {model} has non-exact keys")
    if (
        bundle["schema"] != route_bundle.BUNDLE_SCHEMA
        or bundle["schema_version"] != route_bundle.BUNDLE_SCHEMA_VERSION
        or bundle["campaign"] != expected_campaign
        or bundle["generation_model"] != model
        or bundle["transport_abi_version"] != strict_schema.TRANSPORT_ABI_VERSION
        or bundle["transport_abi_sha256"] != strict_schema.TRANSPORT_ABI_SHA256
        or dict(bundle["protocol"]) != route_bundle._protocol()
        or primitive.canonical_sha256(bundle) != bundle_sha
    ):
        raise CF3ExportError(f"candidate bundle for {model} identity/protocol mismatch")
    if bundle["route_id"] != value["route_id"] or bundle["client_id"] != value["client_id"]:
        raise CF3ExportError(f"formal route/client differs from bundle for {model}")
    if bundle["coordination"] != value["coordination"] or bundle["coordination"] not in (
        {"kind": "none", "version": 1},
        {"kind": "experiment_b_backend_c", "version": 1},
    ):
        raise CF3ExportError(f"formal coordination differs from bundle for {model}")
    if value["protocol_sha256"] != primitive.canonical_sha256(bundle["protocol"]):
        raise CF3ExportError(f"formal protocol hash differs from bundle for {model}")

    inventory = bundle["project_dependency_inventory"]
    if (
        not isinstance(inventory, list)
        or not inventory
        or primitive.canonical_sha256(inventory)
        != bundle["project_dependency_inventory_sha256"]
    ):
        raise CF3ExportError(f"candidate project inventory invalid for {model}")
    inventory_entries = [
        {
            "generation_model": model,
            "path": relative_pointer,
            "sha256": primitive.file_sha256(pointer_path),
            "size": pointer_path.stat().st_size,
        },
        {
            "generation_model": model,
            "path": f"{expected_bundle_path}/bundle.json",
            "sha256": primitive.file_sha256(bundle_manifest_path),
            "size": bundle_manifest_path.stat().st_size,
        },
        {
            "generation_model": model,
            "path": f"{expected_bundle_path}/COMMITTED",
            "sha256": primitive.file_sha256(commit_path),
            "size": commit_path.stat().st_size,
        },
    ]
    declared_bundle_files: set[str] = set()
    for index, entry in enumerate(inventory):
        if not isinstance(entry, Mapping) or set(entry) != {"path", "size", "sha256", "role"}:
            raise CF3ExportError(f"candidate project inventory entry {index} invalid")
        relative = str(entry["path"])
        dependency = _bound_file(root, f"{expected_bundle_path}/{relative}")
        if (
            dependency.stat().st_size != entry["size"]
            or primitive.file_sha256(dependency) != entry["sha256"]
            or relative in declared_bundle_files
        ):
            raise CF3ExportError(f"candidate dependency drift for {model}: {relative}")
        declared_bundle_files.add(relative)
        inventory_entries.append(
            {
                "generation_model": model,
                "path": f"{expected_bundle_path}/{relative}",
                "sha256": entry["sha256"],
                "size": entry["size"],
            }
        )
    if bundle["entrypoint"] not in declared_bundle_files:
        raise CF3ExportError(f"candidate entrypoint is not inventory-bound for {model}")

    external = bundle["external_dependency_inventory"]
    if (
        not isinstance(external, list)
        or primitive.canonical_sha256(external)
        != bundle["external_dependency_inventory_sha256"]
    ):
        raise CF3ExportError(f"candidate external inventory invalid for {model}")
    for index, entry in enumerate(external):
        if not isinstance(entry, Mapping) or set(entry) != {
            "role",
            "path",
            "sha256",
            "contains_credentials",
        }:
            raise CF3ExportError(f"candidate external entry {index} invalid")
        if (
            not isinstance(entry["path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"]))
            or type(entry["contains_credentials"]) is not bool
        ):
            raise CF3ExportError(f"candidate external entry {index} malformed")
    environment = bundle["environment_contract"]
    if not isinstance(environment, Mapping) or set(environment) != {
        "required_names",
        "optional_names",
        "presence",
    }:
        raise CF3ExportError(f"candidate environment contract invalid for {model}")
    names = [*environment["required_names"], *environment["optional_names"]]
    if (
        len(names) != len(set(names))
        or set(environment["presence"]) != set(names)
        or any(type(flag) is not bool for flag in environment["presence"].values())
    ):
        raise CF3ExportError(f"candidate environment contract malformed for {model}")
    if primitive.canonical_sha256(bundle["runtime_fingerprint"]) != bundle["runtime_fingerprint_sha256"]:
        raise CF3ExportError(f"candidate runtime fingerprint hash mismatch for {model}")

    commit = core._strict_json(commit_path.read_bytes(), str(commit_path))
    if not isinstance(commit, Mapping) or set(commit) != {
        "schema",
        "schema_version",
        "generation_model",
        "bundle_sha256",
        "bundle_manifest_sha256",
        "committed_at_utc",
    }:
        raise CF3ExportError(f"candidate COMMITTED record invalid for {model}")
    if (
        commit["schema"] != route_bundle.BUNDLE_COMMIT_SCHEMA
        or commit["schema_version"] != route_bundle.BUNDLE_SCHEMA_VERSION
        or commit["generation_model"] != model
        or commit["bundle_sha256"] != bundle_sha
        or commit["bundle_manifest_sha256"] != primitive.file_sha256(bundle_manifest_path)
        or value["bundle_manifest_sha256"] != primitive.file_sha256(bundle_manifest_path)
        or value["committed_sha256"] != primitive.file_sha256(commit_path)
    ):
        raise CF3ExportError(f"candidate commit/formal binding mismatch for {model}")

    smoke_path = _bound_file(root, value["smoke_report_path"])
    if primitive.file_sha256(smoke_path) != value["smoke_report_sha256"]:
        raise CF3ExportError(f"formal smoke report hash mismatch for {model}")
    smoke = core._strict_json(smoke_path.read_bytes(), str(smoke_path))
    try:
        route_bundle.validate_route_smoke_report(
            smoke,
            campaign=expected_campaign,
            model=model,
            bundle_sha256=bundle_sha,
            route_id=value["route_id"],
            client_id=value["client_id"],
        )
    except Exception as exc:
        raise CF3ExportError(f"formal smoke report invalid for {model}: {exc}") from exc
    inventory_entries.append(
        {
            "generation_model": model,
            "path": Path(value["smoke_report_path"]).as_posix(),
            "sha256": primitive.file_sha256(smoke_path),
            "size": smoke_path.stat().st_size,
        }
    )
    result = dict(value)
    result["formal_pointer_path"] = relative_pointer
    result["formal_pointer_sha256"] = primitive.file_sha256(pointer_path)
    return result, inventory_entries


def _load_formal_bindings(
    root: Path,
) -> tuple[dict[str, dict[str, Any] | None], list[dict[str, Any]], str]:
    bindings: dict[str, dict[str, Any] | None] = {}
    entries: list[dict[str, Any]] = []
    for model in primitive.MODELS:
        binding, model_entries = _formal_binding(root, model)
        bindings[model] = binding
        entries.extend(model_entries)
    entries.sort(key=lambda entry: entry["path"])
    if len({entry["path"] for entry in entries}) != len(entries):
        raise CF3ExportError("formal evidence inventory repeats a path")
    formal_payload = b"".join(
        primitive.canonical_jsonl_row_bytes(entry) for entry in entries
    )
    return bindings, entries, primitive.sha256_bytes(formal_payload)


def _campaign_bindings(manifest: Mapping[str, Any]) -> dict[str, str]:
    return {
        "manifest_sha256": APPROVED["manifest_sha256"],
        "snapshot_sha256": APPROVED["actual_snapshot_sha256"],
        "snapshot_relative_path": "snapshots/actual_levels.jsonl",
        "creation_inventory_sha256": strict_schema.canonical_sha256(
            manifest["creation_inventory"]
        ),
        "cohort_root_sha256": APPROVED["cohort_root_sha256"],
    }


def _load_previous(
    manifest_paths: Sequence[Path],
) -> tuple[set[tuple[str, ...]], str | None]:
    if not manifest_paths:
        return set(), None
    manifests, rows = core.load_snapshots(manifest_paths)
    if any(
        manifest["campaign"]
        != {
            "lineage_id": APPROVED["lineage_id"],
            "manifest_sha256": APPROVED["manifest_sha256"],
            "cohort_root_sha256": APPROVED["cohort_root_sha256"],
            "expected_level_rows": APPROVED["expected_level_rows"],
        }
        for manifest in manifests
    ):
        raise CF3ExportError("previous wave belongs to another campaign")
    if any(
        manifest["cohort_roster"]["sha256"] != APPROVED["cohort_roster_sha256"]
        for manifest in manifests
    ):
        raise CF3ExportError("previous wave uses another cohort roster")
    return (
        {tuple(row["semantic_key"]) for row in rows},
        primitive.file_sha256(manifest_paths[-1]),
    )


def _response_ids(checkpoint: Mapping[str, Any]) -> list[str]:
    result = []
    for attempt in checkpoint["attempts"]:
        if attempt.get("outcome") != "adopted":
            continue
        provenance = attempt.get("provenance")
        response_id = provenance.get("response_id") if isinstance(provenance, Mapping) else None
        if not isinstance(response_id, str) or not response_id.strip():
            raise CF3ExportError("adopted attempt lacks response ID")
        result.append(response_id.strip())
    return result


def export_snapshot(
    detached_root: Path,
    output_dir: Path,
    *,
    wave_id: str,
    previous_manifest_paths: Sequence[Path] = (),
) -> Path:
    root = core.assert_outside_strict_runs(detached_root, label="detached input").resolve(
        strict=True
    )
    core.assert_outside_strict_runs(output_dir, label="snapshot output")
    manifest = _load_manifest(root)
    actual_rows, _ = _load_actual_rows(root)
    inventory_before, inventory_hash = _checkpoint_inventory(root)
    formal, formal_inventory_before, formal_inventory_hash = _load_formal_bindings(
        root
    )
    _validate_sentinel(
        root,
        inventory_sha256=inventory_hash,
        inventory_count=len(inventory_before),
        formal_inventory_sha256=formal_inventory_hash,
        formal_file_count=len(formal_inventory_before),
    )
    inventory_by_path = {entry["path"]: entry for entry in inventory_before}
    expected_existing: set[str] = set()
    previous_keys, predecessor_hash = _load_previous(previous_manifest_paths)
    campaign_bindings = _campaign_bindings(manifest)

    checkpoints: dict[tuple[str, ...], dict[str, Any] | None] = {}
    prefixes: dict[tuple[str, ...], int] = {}
    evidence: dict[tuple[str, ...], tuple[str, str | None]] = {}
    response_ids: set[str] = set()
    for row in actual_rows:
        key = tuple(row["semantic_key"])
        relative = checkpoint_relative_path(row)
        candidate_path = root / Path(relative)
        entry = inventory_by_path.get(relative)
        if not candidate_path.exists():
            if entry is not None:
                raise CF3ExportError(f"inventory references missing checkpoint {relative}")
            checkpoints[key] = None
            prefixes[key] = 0
            evidence[key] = (relative, None)
            continue
        path = _bound_file(root, relative)
        expected_existing.add(relative)
        if entry is None:
            raise CF3ExportError(f"checkpoint absent from detached inventory {relative}")
        model = row["generation_model"]
        formal_binding = formal.get(model)
        if formal_binding is None:
            raise CF3ExportError(f"checkpoint exists without formal binding: {relative}")
        bindings = strict_runner.model_checkpoint_bindings(
            campaign_bindings, formal_binding
        )
        value = core._strict_json(path.read_bytes(), str(path))
        try:
            checkpoint = strict_runner._validate_checkpoint(
                value,
                row,
                bindings,
                formal_binding=formal_binding,
            )
        except Exception as exc:
            raise CF3ExportError(f"invalid detached checkpoint {relative}: {exc}") from exc
        for response_id in _response_ids(checkpoint):
            if response_id in response_ids:
                raise CF3ExportError(f"response ID reused across checkpoints: {response_id}")
            response_ids.add(response_id)
        checkpoint_prefix = len(checkpoint["counterfactuals"])
        if checkpoint["reconstruction"] is None:
            checkpoint_prefix = 0
        checkpoints[key] = checkpoint
        prefixes[key] = checkpoint_prefix
        evidence[key] = (relative, entry["sha256"])
    if expected_existing != set(inventory_by_path):
        extras = sorted(set(inventory_by_path) - expected_existing)
        raise CF3ExportError(f"detached inventory has unexpected checkpoints: {extras[:5]!r}")

    by_item: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in actual_rows:
        by_item[tuple(row["semantic_key"][:-1])].append(row)
    selected_rows = []
    eligibility_rows = []
    for item_key, item_rows in sorted(by_item.items()):
        ordered = sorted(item_rows, key=lambda row: primitive.LEVELS.index(row["level"]))
        if [row["level"] for row in ordered] != list(primitive.LEVELS):
            raise CF3ExportError(f"actual roster item lacks exact L1-L5: {item_key!r}")
        item_keys = {tuple(row["semantic_key"]) for row in ordered}
        previous_intersection = item_keys.intersection(previous_keys)
        if previous_intersection and previous_intersection != item_keys:
            raise CF3ExportError(f"previous wave split a five-level item: {item_key!r}")
        fully_ready = all(prefixes[tuple(row["semantic_key"])] >= 3 for row in ordered)
        for row in ordered:
            key = tuple(row["semantic_key"])
            relative, checkpoint_hash = evidence[key]
            prefix = prefixes[key]
            if key in previous_keys:
                state = "previously_emitted"
            elif fully_ready:
                state = "eligible_new_cf3"
            elif prefix >= 3:
                state = "ready_in_incomplete_item"
            else:
                state = "not_ready"
            eligibility_rows.append(
                core.build_eligibility_row(
                    semantic_key=row["semantic_key"],
                    source_row_sha256=primitive.canonical_row_sha256(row),
                    state=state,
                    evidence_relative_path=relative,
                    evidence_sha256=checkpoint_hash,
                    ready_prefix_count=prefix,
                )
            )
            if state != "eligible_new_cf3":
                continue
            checkpoint = checkpoints[key]
            assert checkpoint is not None
            selected_rows.append(
                core.build_input_row(
                    wave_id=wave_id,
                    generation_model=row["generation_model"],
                    domain=row["domain"],
                    item_id=row["id"],
                    source_id=row["source_id"],
                    source_index=row["source_index"],
                    source_text_sha256=row["source_text_sha256"],
                    level=row["level"],
                    source_row_sha256=primitive.canonical_row_sha256(row),
                    evidence_kind="checkpoint",
                    evidence_relative_path=relative,
                    evidence_sha256=checkpoint_hash,
                    actual_prompt=row["actual"]["prompt"],
                    actual_output=row["actual"]["output"],
                    counterfactuals=[
                        (entry["prompt"], entry["output"])
                        for entry in checkpoint["counterfactuals"][:3]
                    ],
                )
            )
    if not selected_rows:
        raise CF3ExportError("detached copy has no newly eligible five-level CF3 item")

    inventory_after, inventory_hash_after = _checkpoint_inventory(root)
    _, formal_inventory_after, formal_inventory_hash_after = _load_formal_bindings(
        root
    )
    if inventory_after != inventory_before or inventory_hash_after != inventory_hash:
        raise CF3ExportError("detached checkpoint inventory changed during export")
    if (
        formal_inventory_after != formal_inventory_before
        or formal_inventory_hash_after != formal_inventory_hash
    ):
        raise CF3ExportError("detached formal inventory changed during export")
    sentinel = _validate_sentinel(
        root,
        inventory_sha256=inventory_hash,
        inventory_count=len(inventory_before),
        formal_inventory_sha256=formal_inventory_hash,
        formal_file_count=len(formal_inventory_before),
    )
    return core.create_snapshot_bundle(
        output_dir,
        selected_rows,
        snapshot_id=f"{APPROVED['lineage_id']}:{wave_id}",
        wave_id=wave_id,
        evidence_state="detached_quiescent_copy",
        campaign={
            "lineage_id": APPROVED["lineage_id"],
            "manifest_sha256": APPROVED["manifest_sha256"],
            "cohort_root_sha256": APPROVED["cohort_root_sha256"],
            "expected_level_rows": APPROVED["expected_level_rows"],
        },
        freeze={
            "frozen_at_utc": sentinel["copy_completed_at_utc"],
            "actual_snapshot_sha256": APPROVED["actual_snapshot_sha256"],
            "checkpoint_inventory_sha256": inventory_hash,
            "checkpoint_file_count": len(inventory_before),
            "formal_inventory_sha256": formal_inventory_hash,
            "formal_file_count": len(formal_inventory_before),
            "exporter_execution_sha256": exporter_execution_sha256(),
            "predecessor_manifest_sha256": predecessor_hash,
            "previous_cumulative_keys_sha256": core.cumulative_keys_sha256(
                sorted(previous_keys)
            ),
        },
        formal_inventory_entries=formal_inventory_before,
        eligibility_rows=eligibility_rows,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a CF3 wave from a verified quiescent detached run copy."
    )
    parser.add_argument("--detached-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--wave-id", required=True)
    parser.add_argument(
        "--previous-manifest",
        action="append",
        type=Path,
        default=[],
        help="Prior chained CF3 snapshot manifest; repeat in chronological order",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = export_snapshot(
        args.detached_run,
        args.output_dir,
        wave_id=args.wave_id,
        previous_manifest_paths=args.previous_manifest,
    )
    print(f"Detached CF3 snapshot complete: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
