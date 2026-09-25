# -*- coding: utf-8 -*-
"""Offline, lineage-bound Experiment B actual-versus-excess analysis.

This module consumes stored canonical ratios only.  It never imports a model
adapter, starts a worker, calls an API, recompresses text, acquires an
Experiment B lock, or writes beneath ``experiment_b``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import marshal
import math
import os
import platform
import re
import shutil
import stat
import sys
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.stats import kendalltau, pearsonr, rankdata, spearmanr

try:
    from experiment_b import storage
    from experiment_b.compute_validation_metrics import (
        MODELS,
        OUTPUT_DIR,
        _expected_protocol_for_model,
        _krippendorff_interval_exact,
        _prepare_machine_payload,
        _verify_status_lineage_binding,
        load_source_index,
        load_validated_model_items,
    )
    from experiment_b.validation_schema import (
        COMPRESSORS,
        LEVELS,
        LineageManifest,
        ValidationSchemaError,
        assert_no_nonfinite_numbers,
        load_active_lineage_manifest,
        load_lineage_manifest,
        strict_json_loads,
    )
except ModuleNotFoundError:  # Direct execution from experiment_b/.
    import storage  # type: ignore[no-redef]
    from compute_validation_metrics import (  # type: ignore[no-redef]
        MODELS,
        OUTPUT_DIR,
        _expected_protocol_for_model,
        _krippendorff_interval_exact,
        _prepare_machine_payload,
        _verify_status_lineage_binding,
        load_source_index,
        load_validated_model_items,
    )
    from validation_schema import (  # type: ignore[no-redef]
        COMPRESSORS,
        LEVELS,
        LineageManifest,
        ValidationSchemaError,
        assert_no_nonfinite_numbers,
        load_active_lineage_manifest,
        load_lineage_manifest,
        strict_json_loads,
    )


SCHEMA = "experiment_b.actual_vs_excess"
SCHEMA_VERSION = 1
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "derived_outputs" / "experiment_b_actual_excess"
STATUS_NAME = "experiment_b_status.json"
LINEAGE_NAME = "lineage_manifest.json"
OLD_METRICS_NAME = "validation_metrics.json"
LEVEL_LABEL = {level: float(len(LEVELS) - index) for index, level in enumerate(LEVELS)}
EXPECTED_DATASET_COUNTS = {
    "10k_prompts": 2546,
    "wildchat": 2619,
    "oasst1": 1404,
}
EXPECTED_SOURCE_TOTAL = 6569
EXPECTED_MODEL_COUNTS = {
    "claude-sonnet-5": 2944,
    "gemini-3.6-flash": 6569,
    "claude-opus-4-8": 3987,
    "gpt-5.6-sol": 6566,
    "gpt-5.5": 4961,
}
GPT56_NONRESPONSES = ("wc_07969", "wc_01096", "wc_01102")
B_MUTATING_ENTRYPOINTS = frozenset(
    {
        "run_pipeline.py",
        "run_validation.py",
        "run_validation_parallel.py",
        "pilot_mixed_gemini_backend_b.py",
        "pilot_paired_protocol_sensitivity.py",
        "pilot_copilot_five_models.py",
        "gpt55_alias_rollout.py",
        "backend_c_route_rollout.py",
        "repair_source_quality.py",
        "repair_current_data.py",
        "cleanup_non_ok.py",
        "cleanup_zero_baseline.py",
        "re_stratify.py",
        "classify_prompts.py",
    }
)
EXPECTED_COMPLETED_COMMON = 6566
EXPECTED_FIVE_MODEL_COMMON = 2529
MIN_PUBLICATION_BOOTSTRAP_REPLICATES = 1000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
PRIMARY_METRICS = (
    "spearman_rho",
    "pearson_r",
    "kendall_tau_b",
    "krippendorff_alpha_interval",
)


class AnalysisError(RuntimeError):
    """Raised when a read, scientific, state, or publication invariant fails."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float, np.integer, np.floating))
        and math.isfinite(float(value))
    )


def _finite(value: Any, path: str) -> float:
    if not _is_finite_number(value):
        raise AnalysisError(f"{path} must be a finite non-boolean number")
    return float(value)


def _same_float(left: float, right: float, *, atol: float = 1e-12) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=atol)


def _strict_object(path: Path) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"), path=str(path))
    except (OSError, ValidationSchemaError) as exc:
        raise AnalysisError(str(exc)) from exc
    if not isinstance(value, Mapping):
        raise AnalysisError(f"{path} is not a JSON object")
    return dict(value)


def _require_ratio_triplet(row: Mapping[str, Any], path: str) -> dict[str, float]:
    actual = _finite(row.get("actual_ratio"), f"{path}.actual_ratio")
    baseline = _finite(row.get("baseline_mean"), f"{path}.baseline_mean")
    excess = _finite(row.get("excess_ratio"), f"{path}.excess_ratio")
    if not _same_float(excess, actual - baseline):
        raise AnalysisError(
            f"{path} violates excess_ratio = actual_ratio - baseline_mean: "
            f"{excess!r} != {actual - baseline!r}"
        )
    return {"actual": actual, "baseline": baseline, "excess": excess}


def validate_source_row(row: Mapping[str, Any], *, path: str) -> dict[str, float]:
    """Validate only source fields required by this derived estimand.

    Historical source ``cf_valid`` bookkeeping is deliberately not used as a
    cohort filter: 95 canonical-hash-bound rows have a documented waiver, while
    their canonical aggregate arithmetic remains valid.
    """

    if row.get("status") != "ok":
        raise AnalysisError(f"{path}.status must be 'ok'")
    try:
        assert_no_nonfinite_numbers(row, path)
    except ValidationSchemaError as exc:
        raise AnalysisError(str(exc)) from exc
    return _require_ratio_triplet(row, path)


def validate_validation_ratios(
    row: Mapping[str, Any], *, path: str
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    aggregate = _require_ratio_triplet(row, path)
    nested = row.get("per_compressor")
    if not isinstance(nested, Mapping) or set(nested) != set(COMPRESSORS):
        raise AnalysisError(f"{path}.per_compressor has the wrong keys")
    per_compressor: dict[str, dict[str, float]] = {}
    for compressor in COMPRESSORS:
        value = nested.get(compressor)
        if not isinstance(value, Mapping):
            raise AnalysisError(f"{path}.per_compressor.{compressor} is not an object")
        per_compressor[compressor] = _require_ratio_triplet(
            value, f"{path}.per_compressor.{compressor}"
        )
    return aggregate, per_compressor


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_link_or_junction(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _assert_no_link_components(path: Path) -> None:
    absolute = path.absolute()
    candidates = list(reversed(absolute.parents)) + [absolute]
    for candidate in candidates:
        if candidate.exists() and _is_link_or_junction(candidate):
            raise AnalysisError(f"derived output path contains a link/junction: {candidate}")


def validate_output_root(output_root: Path, *, experiment_root: Path = HERE) -> Path:
    _assert_no_link_components(output_root)
    resolved = output_root.resolve()
    protected = experiment_root.resolve()
    if resolved == protected or _path_is_within(resolved, protected):
        raise AnalysisError(f"derived output must remain outside Experiment B: {resolved}")
    return resolved


def _command_is_b_worker(command: Sequence[Any]) -> bool:
    normalized_parts = [
        str(part).replace("\\", "/").lower() for part in command
    ]
    basenames = {part.rsplit("/", 1)[-1] for part in normalized_parts}
    module_names = {
        f"experiment_b.{name[:-3]}"
        for name in B_MUTATING_ENTRYPOINTS
        if name.endswith(".py")
    }
    normalized = " ".join(normalized_parts)
    return bool(
        basenames & B_MUTATING_ENTRYPOINTS
        or any(module in normalized_parts for module in module_names)
        or any(
            f"experiment_b/{name}" in normalized
            for name in B_MUTATING_ENTRYPOINTS
        )
    )


def _active_b_workers() -> list[dict[str, Any]]:
    """Return B generation/mutation processes without touching them."""

    try:
        import psutil
    except ImportError as exc:  # Fail closed rather than silently skip the gate.
        raise AnalysisError("psutil is required for the no-worker preflight") from exc

    active: list[dict[str, Any]] = []
    current_pid = os.getpid()
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = int(process.info["pid"])
            if pid == current_pid:
                continue
            process_name = str(process.info.get("name") or "").lower()
            command = process.info.get("cmdline")
        except (psutil.NoSuchProcess, KeyError, TypeError, ValueError):
            continue
        except psutil.AccessDenied as exc:
            raise AnalysisError("cannot inspect a process during no-worker preflight") from exc
        if command is None:
            if "python" in process_name:
                raise AnalysisError(
                    f"cannot inspect Python process {pid} during no-worker preflight"
                )
            continue
        normalized_parts = [
            str(part).replace("\\", "/").lower() for part in command
        ]
        normalized = " ".join(normalized_parts)
        if _command_is_b_worker(command):
            active.append({"pid": pid, "command": normalized[:1000]})
    return sorted(active, key=lambda value: value["pid"])


def _lock_files(experiment_root: Path) -> list[str]:
    lock_dir = experiment_root / ".locks"
    if not lock_dir.exists():
        return []
    return sorted(str(path.resolve()) for path in lock_dir.iterdir() if path.is_file())


def preflight_state(
    *, experiment_root: Path = HERE, output_dir: Path = OUTPUT_DIR
) -> tuple[dict[str, Any], LineageManifest]:
    pause = experiment_root / "PAUSED"
    migration = experiment_root / "MIGRATION_IN_PROGRESS"
    status_path = output_dir / STATUS_NAME
    if not pause.is_file():
        raise AnalysisError(f"Experiment B is not protected by PAUSED: {pause}")
    if migration.exists():
        raise AnalysisError(f"Experiment B migration is active: {migration}")
    locks = _lock_files(experiment_root)
    if locks:
        raise AnalysisError(f"Experiment B lock directory is not empty: {locks}")
    workers = _active_b_workers()
    if workers:
        raise AnalysisError(f"Experiment B generation workers are active: {workers}")

    status = _strict_object(status_path)
    if status.get("state") != "PAUSED" or status.get("active_runs") != []:
        raise AnalysisError("Experiment B status is not a quiescent PAUSED state")
    components = status.get("components")
    if not isinstance(components, Mapping):
        raise AnalysisError("Experiment B status lacks components")
    process_state = components.get("experiment_b_processes")
    if not isinstance(process_state, Mapping) or process_state.get("active_count") != 0:
        raise AnalysisError("Experiment B status does not attest zero active processes")
    source_state = components.get("source_pipeline")
    if not isinstance(source_state, Mapping):
        raise AnalysisError("Experiment B status lacks source_pipeline")
    observed_dataset_counts = source_state.get("counts")
    if observed_dataset_counts != EXPECTED_DATASET_COUNTS:
        raise AnalysisError(
            f"source dataset counts changed: {observed_dataset_counts!r}"
        )
    if source_state.get("total") != EXPECTED_SOURCE_TOTAL:
        raise AnalysisError("source total changed")
    validation = components.get("validation")
    if not isinstance(validation, Mapping):
        raise AnalysisError("Experiment B status lacks validation")
    if validation.get("counts") != EXPECTED_MODEL_COUNTS:
        raise AnalysisError(f"validation counts changed: {validation.get('counts')!r}")
    if validation.get("total") != sum(EXPECTED_MODEL_COUNTS.values()):
        raise AnalysisError("validation total changed")
    nonresponses = validation.get("final_model_nonresponses")
    if not isinstance(nonresponses, Mapping):
        raise AnalysisError("Experiment B status lacks final model nonresponses")
    gpt56 = nonresponses.get("gpt-5.6-sol")
    if not isinstance(gpt56, Mapping) or tuple(gpt56.get("ids", ())) != GPT56_NONRESPONSES:
        raise AnalysisError("GPT-5.6 declared nonresponse roster changed")
    if gpt56.get("valid_n") != EXPECTED_MODEL_COUNTS["gpt-5.6-sol"]:
        raise AnalysisError("GPT-5.6 nonresponse disposition count changed")

    try:
        lineage = load_active_lineage_manifest(output_dir)
        _verify_status_lineage_binding(output_dir, lineage)
    except (RuntimeError, ValidationSchemaError) as exc:
        raise AnalysisError(str(exc)) from exc
    if lineage.expected_total != EXPECTED_SOURCE_TOTAL:
        raise AnalysisError("active lineage source total changed")
    if dict(lineage.expected_dataset_counts) != EXPECTED_DATASET_COUNTS:
        raise AnalysisError("active lineage source dataset counts changed")
    if tuple(lineage.models) != tuple(MODELS):
        raise AnalysisError(
            f"active lineage model roster changed: {tuple(lineage.models)!r}"
        )
    for model in MODELS:
        protocol = _expected_protocol_for_model(lineage, model)
        if not isinstance(protocol, Mapping):
            raise AnalysisError(f"active lineage lacks a protocol for {model}")
    return status, lineage


def _stream_file_record(path: Path, *, jsonl: bool) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    line_count = 0
    last = b""
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                line_count += chunk.count(b"\n")
                last = chunk[-1:]
    except OSError as exc:
        raise AnalysisError(f"cannot inventory {path}: {exc}") from exc
    if jsonl and (size == 0 or last != b"\n"):
        raise AnalysisError(f"JSONL input is empty or lacks a final LF: {path}")
    record: dict[str, Any] = {
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "size": size,
    }
    if jsonl:
        record["row_count"] = line_count
    return record


def input_inventory(
    *, output_dir: Path, experiment_root: Path, lineage: LineageManifest
) -> dict[str, dict[str, Any]]:
    if lineage.path is None:
        raise AnalysisError("production analysis requires a file-backed active lineage")
    paths: list[tuple[str, Path, bool]] = [
        ("pause_sentinel", experiment_root / "PAUSED", False),
        ("status", output_dir / STATUS_NAME, False),
        ("lineage", lineage.path, False),
        ("stale_validation_metrics", output_dir / OLD_METRICS_NAME, False),
    ]
    for dataset in EXPECTED_DATASET_COUNTS:
        paths.append(
            (f"source:{dataset}", output_dir / f"{dataset}_stratified.jsonl", True)
        )
    for model in MODELS:
        paths.append(
            (f"validation:{model}", output_dir / f"validation_{model}.jsonl", True)
        )
    return {
        name: _stream_file_record(path, jsonl=jsonl)
        for name, path, jsonl in paths
    }


def validate_source_file_lineage(
    lineage: LineageManifest,
    inventory: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    official = lineage.raw.get("official_files")
    if not isinstance(official, Mapping):
        raise AnalysisError("active lineage lacks official_files")
    if lineage.path is None:
        raise AnalysisError("source authentication requires a file-backed lineage")
    output_dir = lineage.path.resolve().parent
    result: dict[str, Any] = {}
    for dataset, expected_count in EXPECTED_DATASET_COUNTS.items():
        declaration_key = f"outputs/{dataset}_stratified.jsonl"
        declaration = official.get(declaration_key)
        if not isinstance(declaration, Mapping):
            raise AnalysisError(f"lineage lacks source declaration {declaration_key}")
        observed = inventory.get(f"source:{dataset}")
        if not isinstance(observed, Mapping):
            raise AnalysisError(f"input inventory lacks source:{dataset}")
        expected_path = (output_dir / f"{dataset}_stratified.jsonl").resolve()
        if Path(str(observed.get("path"))).resolve() != expected_path:
            raise AnalysisError(f"source inventory path differs for {dataset}")
        expected = {
            "role": f"stratified:{dataset}",
            "row_count": expected_count,
            "sha256": declaration.get("sha256"),
            "size": declaration.get("size"),
        }
        if declaration.get("role") != expected["role"]:
            raise AnalysisError(f"lineage source role differs for {dataset}")
        for field in ("row_count", "sha256", "size"):
            if observed.get(field) != expected[field]:
                raise AnalysisError(
                    f"source {dataset} {field} differs from active lineage: "
                    f"{observed.get(field)!r} != {expected[field]!r}"
                )
        result[dataset] = {
            "declaration_key": declaration_key,
            **expected,
        }
    return {
        "whole_file_verified": True,
        "files": result,
    }


def validate_source_row_lineage(
    lineage: LineageManifest,
    source_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    declared_all = lineage.raw.get("per_id_canonical_hashes")
    if not isinstance(declared_all, Mapping):
        raise AnalysisError("active lineage lacks per_id_canonical_hashes")
    result: dict[str, Any] = {}
    for dataset, expected_count in EXPECTED_DATASET_COUNTS.items():
        role = f"stratified:{dataset}"
        declared = declared_all.get(role)
        if not isinstance(declared, Mapping):
            raise AnalysisError(f"active lineage lacks per-ID hashes for {role}")
        observed_rows = {
            item_id: row
            for item_id, row in source_index.items()
            if row.get("dataset") == dataset
        }
        if len(observed_rows) != expected_count or set(observed_rows) != set(declared):
            raise AnalysisError(f"source per-ID roster differs from lineage for {dataset}")
        for item_id, row in observed_rows.items():
            observed_sha = storage.canonical_row_sha256(row)
            expected_sha = declared.get(item_id)
            if observed_sha != expected_sha:
                raise AnalysisError(
                    f"source canonical row hash differs for {dataset}/{item_id}"
                )
        result[dataset] = {
            "role": role,
            "row_count": len(observed_rows),
            "declared_mapping_sha256": storage.sha256_bytes(
                storage.canonical_json_bytes(dict(declared))
            ),
        }
    return {
        "per_id_canonical_hashes_verified": True,
        "datasets": result,
        "total_rows_verified": sum(
            value["row_count"] for value in result.values()
        ),
    }


def validate_publication_inventory(
    lineage: LineageManifest,
    inventory: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if lineage.path is None:
        raise AnalysisError("publication requires a file-backed active lineage")
    lineage_path = lineage.path.resolve()
    output_dir = lineage_path.parent
    experiment_root = output_dir.parent
    expected_paths: dict[str, tuple[Path, int | None]] = {
        "pause_sentinel": (experiment_root / "PAUSED", None),
        "status": (output_dir / STATUS_NAME, None),
        "lineage": (lineage_path, None),
        "stale_validation_metrics": (output_dir / OLD_METRICS_NAME, None),
    }
    expected_paths.update(
        {
            f"source:{dataset}": (
                output_dir / f"{dataset}_stratified.jsonl",
                count,
            )
            for dataset, count in EXPECTED_DATASET_COUNTS.items()
        }
    )
    expected_paths.update(
        {
            f"validation:{model}": (
                output_dir / f"validation_{model}.jsonl",
                count,
            )
            for model, count in EXPECTED_MODEL_COUNTS.items()
        }
    )
    if set(inventory) != set(expected_paths):
        raise AnalysisError(
            f"publication inventory role set differs: {sorted(inventory)!r}"
        )
    for role, (expected_path, expected_rows) in expected_paths.items():
        record = inventory.get(role)
        if not isinstance(record, Mapping):
            raise AnalysisError(f"publication inventory record is invalid for {role}")
        if Path(str(record.get("path"))).resolve() != expected_path.resolve():
            raise AnalysisError(f"publication inventory path differs for {role}")
        sha = record.get("sha256")
        size = record.get("size")
        if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
            raise AnalysisError(f"publication inventory SHA is invalid for {role}")
        if type(size) is not int or size < 0:
            raise AnalysisError(f"publication inventory size is invalid for {role}")
        if expected_rows is not None and record.get("row_count") != expected_rows:
            raise AnalysisError(f"publication inventory row count differs for {role}")
        observed_record = _stream_file_record(
            expected_path, jsonl=expected_rows is not None
        )
        if dict(record) != observed_record:
            raise AnalysisError(f"publication inventory bytes differ for {role}")
    lineage_record = inventory["lineage"]
    if lineage_record["sha256"] != lineage.sha256:
        raise AnalysisError("inventory lineage SHA differs from loaded lineage")
    if storage.file_sha256(lineage_path) != lineage.sha256:
        raise AnalysisError("lineage file bytes differ from loaded lineage SHA")
    try:
        reloaded = load_lineage_manifest(lineage_path)
    except ValidationSchemaError as exc:
        raise AnalysisError(f"cannot reload publication lineage: {exc}") from exc
    if (
        reloaded.sha256 != lineage.sha256
        or dict(reloaded.raw) != dict(lineage.raw)
        or tuple(reloaded.models) != tuple(lineage.models)
        or reloaded.config_fingerprint != lineage.config_fingerprint
    ):
        raise AnalysisError("publication lineage object differs from its file bytes")
    return validate_source_file_lineage(lineage, inventory)


def code_inventory() -> dict[str, dict[str, Any]]:
    paths = {
        "analyzer": Path(__file__).resolve(),
        "metrics_helpers": HERE / "compute_validation_metrics.py",
        "validation_schema": HERE / "validation_schema.py",
        "storage": HERE / "storage.py",
    }
    result = {
        name: _stream_file_record(path, jsonl=False)
        for name, path in paths.items()
    }
    loaded_functions = {
        "load_source_index": load_source_index,
        "load_validated_model_items": load_validated_model_items,
        "krippendorff_interval_exact": _krippendorff_interval_exact,
        "prepare_machine_payload": _prepare_machine_payload,
        "paired_bootstrap": paired_bootstrap,
        "build_report": build_report,
        "publish_snapshot": publish_snapshot,
    }
    for name, function in loaded_functions.items():
        result[f"loaded_code:{name}"] = {
            "kind": "loaded_python_code_object",
            "qualified_name": f"{function.__module__}.{function.__qualname__}",
            "sha256": hashlib.sha256(marshal.dumps(function.__code__)).hexdigest(),
        }
    return result


def _inventory_digest(inventory: Mapping[str, Mapping[str, Any]]) -> str:
    return storage.sha256_bytes(storage.canonical_json_bytes(inventory))


def _require_inventory_equal(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    *,
    stage: str,
) -> None:
    if dict(before) != dict(after):
        raise AnalysisError(f"protected input drift detected during {stage}")


def _id_roster_hash(ids: Sequence[str]) -> str:
    ordered = sorted(ids)
    return storage.sha256_bytes(storage.canonical_json_bytes(ordered))


def _protocol_group(row: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    protocol = row.get("generation_protocol")
    if not isinstance(protocol, Mapping):
        return (
            "legacy_hash_trusted_no_protocol",
            {
                "kind": "legacy_hash_trusted_no_protocol",
                "protocol": None,
            },
        )
    normalized = dict(protocol)
    digest = storage.sha256_bytes(storage.canonical_json_bytes(normalized))
    return (
        f"protocol_{digest[:16]}",
        {
            "kind": "stored_generation_protocol",
            "protocol_sha256": digest,
            "protocol": normalized,
        },
    )


def load_joined_rows(
    *, output_dir: Path, lineage: LineageManifest
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, int]],
]:
    try:
        source_index = load_source_index(output_dir=output_dir, lineage=lineage)
    except RuntimeError as exc:
        raise AnalysisError(str(exc)) from exc
    if len(source_index) != EXPECTED_SOURCE_TOTAL:
        raise AnalysisError("strict source loader returned an unexpected count")
    source_ratios: dict[str, dict[str, float]] = {}
    for item_id, source in source_index.items():
        source_ratios[item_id] = validate_source_row(
            source, path=f"source[{item_id!r}]"
        )

    rows_by_model: dict[str, list[dict[str, Any]]] = {}
    trust_counts: dict[str, dict[str, int]] = {}
    for model in MODELS:
        try:
            validation_rows, diagnostics = load_validated_model_items(
                model,
                output_dir=output_dir,
                lineage=lineage,
                source_index=source_index,
            )
        except RuntimeError as exc:
            raise AnalysisError(str(exc)) from exc
        expected = EXPECTED_MODEL_COUNTS[model]
        if len(validation_rows) != expected:
            raise AnalysisError(
                f"{model} current validation count changed: {len(validation_rows)} != {expected}"
            )
        joined: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in validation_rows:
            item_id = row.get("id")
            if not isinstance(item_id, str) or item_id in seen:
                raise AnalysisError(f"invalid or duplicate validation ID for {model}: {item_id!r}")
            seen.add(item_id)
            source = source_index[item_id]
            aggregate, per_compressor = validate_validation_ratios(
                row, path=f"validation[{model!r}][{item_id!r}]"
            )
            source_excess = source_ratios[item_id]["excess"]
            strat_excess = _finite(
                row.get("strat_excess_ratio"),
                f"validation[{model!r}][{item_id!r}].strat_excess_ratio",
            )
            if not _same_float(strat_excess, source_excess):
                raise AnalysisError(f"source/retest excess parity failed for {model}/{item_id}")
            protocol_group, protocol_descriptor = _protocol_group(row)
            joined.append(
                {
                    "id": item_id,
                    "dataset": source["dataset"],
                    "category": source["category"],
                    "level": source["level"],
                    "protocol_group": protocol_group,
                    "protocol_descriptor": protocol_descriptor,
                    "source_actual": source_ratios[item_id]["actual"],
                    "source_baseline": source_ratios[item_id]["baseline"],
                    "source_excess": source_excess,
                    "validation_actual": aggregate["actual"],
                    "validation_baseline": aggregate["baseline"],
                    "validation_excess": aggregate["excess"],
                    "per_compressor": per_compressor,
                }
            )
        joined.sort(key=lambda value: value["id"])
        rows_by_model[model] = joined
        legacy = int(diagnostics["legacy_unverified_count"])
        trust_counts[model] = {
            "total": len(joined),
            "legacy_hash_trusted": legacy,
            "modern_provenance_checked": len(joined) - legacy,
        }

    gpt56_ids = {row["id"] for row in rows_by_model["gpt-5.6-sol"]}
    source_ids = set(source_index)
    for item_id in GPT56_NONRESPONSES:
        if item_id not in source_ids or item_id in gpt56_ids:
            raise AnalysisError(f"GPT-5.6 nonresponse disposition drift for {item_id}")
    if source_ids - gpt56_ids != set(GPT56_NONRESPONSES):
        raise AnalysisError("GPT-5.6 missing-ID set differs from declared nonresponses")
    return source_index, rows_by_model, trust_counts


def build_cohorts(
    source_index: Mapping[str, Mapping[str, Any]],
    rows_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    source_ids = set(source_index)
    ids_by_model = {
        model: {str(row["id"]) for row in rows}
        for model, rows in rows_by_model.items()
    }
    for model, ids in ids_by_model.items():
        if len(ids) != EXPECTED_MODEL_COUNTS[model] or not ids <= source_ids:
            raise AnalysisError(f"invalid model-specific cohort for {model}")
    completed = ids_by_model["gemini-3.6-flash"] & ids_by_model["gpt-5.6-sol"]
    common = set.intersection(*(ids_by_model[model] for model in MODELS))
    if len(completed) != EXPECTED_COMPLETED_COMMON:
        raise AnalysisError(f"completed-model common cohort changed: {len(completed)}")
    if len(common) != EXPECTED_FIVE_MODEL_COMMON:
        raise AnalysisError(f"five-model common cohort changed: {len(common)}")

    def description(ids: set[str], models: Sequence[str]) -> dict[str, Any]:
        dataset_counts: dict[str, int] = defaultdict(int)
        level_counts: dict[str, int] = defaultdict(int)
        category_counts: dict[str, int] = defaultdict(int)
        for item_id in ids:
            source = source_index[item_id]
            dataset_counts[str(source["dataset"])] += 1
            level_counts[str(source["level"])] += 1
            category_counts[str(source["category"])] += 1
        return {
            "n_source_ids": len(ids),
            "models": list(models),
            "id_roster_sha256": _id_roster_hash(sorted(ids)),
            "dataset_counts": dict(sorted(dataset_counts.items())),
            "level_counts": {level: level_counts.get(level, 0) for level in LEVELS},
            "category_counts": dict(sorted(category_counts.items())),
        }

    return {
        "source_universe": {
            "ids": source_ids,
            "description": description(source_ids, ()),
        },
        "model_specific": {
            model: {
                "ids": ids,
                "description": description(ids, (model,)),
            }
            for model, ids in ids_by_model.items()
        },
        "completed_models_common": {
            "ids": completed,
            "description": description(
                completed, ("gemini-3.6-flash", "gpt-5.6-sol")
            ),
        },
        "five_model_common": {
            "ids": common,
            "description": description(common, MODELS),
        },
    }


def _summary(values: Sequence[float]) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    if not np.all(np.isfinite(array)):
        raise AnalysisError("non-finite value reached a statistical summary")
    return {
        "n": int(array.size),
        "mean": float(array.mean()),
        "sd": float(array.std(ddof=1)) if array.size > 1 else None,
        "min": float(array.min()),
        "max": float(array.max()),
    }


def _estimate_or_none(value: Any) -> float | None:
    result = float(value)
    return result if math.isfinite(result) else None


def continuous_metrics(
    left: Sequence[float],
    right: Sequence[float],
    *,
    require_defined: bool = False,
    left_label: str = "source",
    right_label: str = "validation",
) -> dict[str, Any]:
    if left_label == right_label or not left_label or not right_label:
        raise AnalysisError("continuous metric axis labels must be distinct and nonempty")
    if len(left) != len(right):
        raise AnalysisError("continuous metric vectors have different lengths")
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise AnalysisError("non-finite value reached continuous metrics")
    warning: str | None = None
    if len(x) < 2:
        warning = "fewer than two observations"
    elif np.ptp(x) == 0.0 or np.ptp(y) == 0.0:
        warning = "one or both vectors are constant"
    if warning is not None:
        if require_defined:
            raise AnalysisError(f"primary continuous metric is undefined: {warning}")
        return {
            "n": len(x),
            "spearman_rho": None,
            "spearman_p": None,
            "pearson_r": None,
            "pearson_p": None,
            "kendall_tau_b": None,
            "kendall_p": None,
            "krippendorff_alpha_interval": None,
            left_label: _summary(x.tolist()),
            right_label: _summary(y.tolist()),
            "warnings": [warning],
        }
    spearman = spearmanr(x, y)
    pearson = pearsonr(x, y)
    kendall = kendalltau(x, y)
    alpha = _krippendorff_interval_exact(np.column_stack([x, y]))
    estimates = {
        "spearman_rho": _estimate_or_none(spearman.statistic),
        "spearman_p": _estimate_or_none(spearman.pvalue),
        "pearson_r": _estimate_or_none(pearson.statistic),
        "pearson_p": _estimate_or_none(pearson.pvalue),
        "kendall_tau_b": _estimate_or_none(kendall.statistic),
        "kendall_p": _estimate_or_none(kendall.pvalue),
        "krippendorff_alpha_interval": _estimate_or_none(alpha),
    }
    if require_defined and any(estimates[key] is None for key in PRIMARY_METRICS):
        raise AnalysisError("primary continuous metric library returned non-finite output")
    warnings = [
        f"{key} is undefined" for key in PRIMARY_METRICS if estimates[key] is None
    ]
    return {
        "n": len(x),
        **estimates,
        left_label: _summary(x.tolist()),
        right_label: _summary(y.tolist()),
        "warnings": warnings,
    }


def paired_point_metrics(
    rows: Sequence[Mapping[str, Any]], *, require_defined: bool = False
) -> dict[str, Any]:
    actual = continuous_metrics(
        [float(row["source_actual"]) for row in rows],
        [float(row["validation_actual"]) for row in rows],
        require_defined=require_defined,
    )
    excess = continuous_metrics(
        [float(row["source_excess"]) for row in rows],
        [float(row["validation_excess"]) for row in rows],
        require_defined=require_defined,
    )
    delta = {
        key: (
            float(actual[key]) - float(excess[key])
            if actual[key] is not None and excess[key] is not None
            else None
        )
        for key in PRIMARY_METRICS
    }
    return {
        "n": len(rows),
        "actual": actual,
        "excess": excess,
        "delta_actual_minus_excess": delta,
    }


def _point_splits(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("dataset", "category", "protocol_group"):
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        result[f"by_{field}"] = {
            name: paired_point_metrics(group)
            for name, group in sorted(groups.items())
        }
    return result


def _bootstrap_estimates(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    if len(left) < 2 or np.ptp(left) == 0.0 or np.ptp(right) == 0.0:
        raise AnalysisError("bootstrap produced an undefined correlation vector")
    rho = np.corrcoef(rankdata(left, method="average"), rankdata(right, method="average"))[0, 1]
    pearson = np.corrcoef(left, right)[0, 1]
    tau = kendalltau(left, right).statistic
    alpha = _krippendorff_interval_exact(np.column_stack([left, right]))
    values = {
        "spearman_rho": float(rho),
        "pearson_r": float(pearson),
        "kendall_tau_b": float(tau),
        "krippendorff_alpha_interval": float(alpha),
    }
    if not all(math.isfinite(value) for value in values.values()):
        raise AnalysisError("bootstrap produced a non-finite primary statistic")
    return values


def _cohort_seed(master_seed: int, cohort_name: str) -> int:
    digest = hashlib.sha256(f"{master_seed}:{cohort_name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _percentile_interval(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "low": float(np.quantile(array, 0.025)),
        "high": float(np.quantile(array, 0.975)),
    }


def paired_bootstrap(
    rows_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    cohort_name: str,
    replicates: int,
    master_seed: int,
) -> dict[str, Any]:
    if type(replicates) is not int or replicates <= 0:
        raise AnalysisError("bootstrap replicates must be a positive integer")
    if type(master_seed) is not int or master_seed < 0:
        raise AnalysisError("bootstrap seed must be a non-negative integer")
    models = list(rows_by_model)
    if not models:
        raise AnalysisError("bootstrap requires at least one model")
    ordered: dict[str, list[Mapping[str, Any]]] = {
        model: sorted(rows, key=lambda row: str(row["id"]))
        for model, rows in rows_by_model.items()
    }
    ids = [str(row["id"]) for row in ordered[models[0]]]
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise AnalysisError("bootstrap cohort IDs are too small or duplicated")
    for model in models[1:]:
        if [str(row["id"]) for row in ordered[model]] != ids:
            raise AnalysisError("common-cohort bootstrap model ID order differs")

    strata: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(ordered[models[0]]):
        strata[(str(row["dataset"]), str(row["category"]))].append(index)
    arrays: dict[str, dict[str, np.ndarray]] = {}
    for model in models:
        rows = ordered[model]
        arrays[model] = {
            key: np.asarray([float(row[key]) for row in rows], dtype=float)
            for key in (
                "source_actual",
                "validation_actual",
                "source_excess",
                "validation_excess",
            )
        }

    seed = _cohort_seed(master_seed, cohort_name)
    rng = np.random.default_rng(seed)
    samples: dict[str, dict[str, list[float]]] = {
        model: {
            f"{estimand}.{metric}": []
            for estimand in ("actual", "excess")
            for metric in PRIMARY_METRICS
        }
        | {f"delta.{metric}": [] for metric in PRIMARY_METRICS}
        for model in models
    }
    ordered_strata = [np.asarray(strata[key], dtype=int) for key in sorted(strata)]
    undefined_replicates = 0
    for _ in range(replicates):
        sampled = np.concatenate(
            [rng.choice(indices, size=len(indices), replace=True) for indices in ordered_strata]
        )
        replicate_values: dict[str, tuple[dict[str, float], dict[str, float]]] = {}
        try:
            for model in models:
                values = arrays[model]
                actual = _bootstrap_estimates(
                    values["source_actual"][sampled],
                    values["validation_actual"][sampled],
                )
                excess = _bootstrap_estimates(
                    values["source_excess"][sampled],
                    values["validation_excess"][sampled],
                )
                replicate_values[model] = (actual, excess)
        except AnalysisError:
            undefined_replicates += 1
            continue
        for model, (actual, excess) in replicate_values.items():
            for metric in PRIMARY_METRICS:
                samples[model][f"actual.{metric}"].append(actual[metric])
                samples[model][f"excess.{metric}"].append(excess[metric])
                samples[model][f"delta.{metric}"].append(
                    actual[metric] - excess[metric]
                )
    valid_replicates = replicates - undefined_replicates
    minimum_valid = max(1, math.ceil(replicates * 0.99))
    if valid_replicates < minimum_valid:
        raise AnalysisError(
            f"bootstrap valid replicate fraction is below 0.99: "
            f"{valid_replicates}/{replicates}"
        )

    model_results: dict[str, Any] = {}
    for model in models:
        model_results[model] = {
            "actual": {
                metric: _percentile_interval(samples[model][f"actual.{metric}"])
                for metric in PRIMARY_METRICS
            },
            "excess": {
                metric: _percentile_interval(samples[model][f"excess.{metric}"])
                for metric in PRIMARY_METRICS
            },
            "delta_actual_minus_excess": {
                metric: _percentile_interval(samples[model][f"delta.{metric}"])
                for metric in PRIMARY_METRICS
            },
        }
    return {
        "method": "paired_source_id_percentile_bootstrap",
        "confidence_level": 0.95,
        "replicates_requested": replicates,
        "replicates_attempted": replicates,
        "replicates_valid": valid_replicates,
        "undefined_replicates": undefined_replicates,
        "minimum_valid_fraction": 0.99,
        "master_seed": master_seed,
        "cohort_seed": seed,
        "sampling_unit": "source_id",
        "strata": ["dataset", "category"],
        "level_excluded_from_strata": True,
        "models_share_sampled_ids": len(models) > 1,
        "models": model_results,
    }


def _label_association(rows: Sequence[Mapping[str, Any]], value_key: str) -> dict[str, Any]:
    labels = [LEVEL_LABEL[str(row["level"])] for row in rows]
    values = [float(row[value_key]) for row in rows]
    result = continuous_metrics(labels, values)
    return {
        "n": result["n"],
        "spearman_rho": result["spearman_rho"],
        "spearman_p": result["spearman_p"],
        "kendall_tau_b": result["kendall_tau_b"],
        "kendall_p": result["kendall_p"],
        "warnings": result["warnings"],
    }


def _level_descriptives(
    rows: Sequence[Mapping[str, Any]], prefixes: Sequence[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for prefix in prefixes:
        by_level: dict[str, Any] = {}
        for level in LEVELS:
            selected = [row for row in rows if row["level"] == level]
            by_level[level] = {
                estimand: _summary(
                    [float(row[f"{prefix}_{estimand}"]) for row in selected]
                )
                for estimand in ("actual", "baseline", "excess")
            }
        result[prefix] = {
            "by_level": by_level,
            "strictly_decreasing_level_means": {
                estimand: all(
                    float(by_level[LEVELS[index]][estimand]["mean"])
                    > float(by_level[LEVELS[index + 1]][estimand]["mean"])
                    for index in range(len(LEVELS) - 1)
                )
                if all(by_level[level][estimand]["mean"] is not None for level in LEVELS)
                else None
                for estimand in ("actual", "baseline", "excess")
            },
        }
    return result


def _compressor_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for estimand in ("actual", "excess"):
        matrix = np.asarray(
            [
                [float(row["per_compressor"][name][estimand]) for name in COMPRESSORS]
                for row in rows
            ],
            dtype=float,
        )
        alpha = _krippendorff_interval_exact(matrix)
        result[estimand] = {
            "n": len(rows),
            "krippendorff_alpha_interval": _estimate_or_none(alpha),
            "per_compressor": {
                name: {
                    "overall": _summary(matrix[:, index].tolist()),
                    "by_level": {
                        level: _summary(
                            [
                                float(row["per_compressor"][name][estimand])
                                for row in rows
                                if row["level"] == level
                            ]
                        )
                        for level in LEVELS
                    },
                }
                for index, name in enumerate(COMPRESSORS)
            },
        }
    return result


def _source_rows(source_index: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item_id, row in source_index.items():
        ratios = validate_source_row(row, path=f"source[{item_id!r}]")
        result.append(
            {
                "id": item_id,
                "dataset": row["dataset"],
                "category": row["category"],
                "level": row["level"],
                "source_actual": ratios["actual"],
                "source_baseline": ratios["baseline"],
                "source_excess": ratios["excess"],
            }
        )
    return sorted(result, key=lambda value: value["id"])


def _filter_ids(
    rows: Sequence[Mapping[str, Any]], ids: set[str]
) -> list[Mapping[str, Any]]:
    selected = [row for row in rows if row["id"] in ids]
    if len(selected) != len(ids):
        raise AnalysisError("cohort filter did not produce exactly one row per ID")
    return sorted(selected, key=lambda row: str(row["id"]))


def _protocol_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["protocol_group"])].append(row)
    result: dict[str, Any] = {}
    for name, selected in sorted(groups.items()):
        descriptors = {
            storage.sha256_bytes(
                storage.canonical_json_bytes(row["protocol_descriptor"])
            ): row["protocol_descriptor"]
            for row in selected
        }
        if len(descriptors) != 1:
            raise AnalysisError(f"protocol group {name} has conflicting descriptors")
        dataset_counts: dict[str, int] = defaultdict(int)
        for row in selected:
            dataset_counts[str(row["dataset"])] += 1
        result[name] = {
            "n": len(selected),
            "descriptor": next(iter(descriptors.values())),
            "dataset_counts": dict(sorted(dataset_counts.items())),
            "continuous_source_validation": paired_point_metrics(selected),
        }
    return {
        "mixed_protocol_primary_cohort": len(result) > 1,
        "group_count": len(result),
        "groups": result,
        "warning": (
            "Primary estimates describe the stored mixed-protocol corpus. "
            "Protocol-group point estimates are sensitivity diagnostics and may be "
            "confounded with dataset and collection order."
            if len(result) > 1
            else "This cohort contains one stored protocol group."
        ),
    }


def _model_report(
    rows: Sequence[Mapping[str, Any]], bootstrap_ci: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "continuous_source_validation": paired_point_metrics(
            rows, require_defined=True
        ),
        "bootstrap_ci": bootstrap_ci,
        "splits": _point_splits(rows),
        "protocol_mixture_and_sensitivity": _protocol_diagnostics(rows),
        "secondary_source_excess_quantile_label_alignment": {
            "validation_actual": _label_association(rows, "validation_actual"),
            "validation_excess": _label_association(rows, "validation_excess"),
            "warning": (
                "Within each dataset x category cell, L1-L5 were deterministically "
                "assigned from descending source-excess ranks; these are source-derived "
                "score bins, not independent human labels or criterion truth."
            ),
        },
        "level_descriptives": _level_descriptives(rows, ("source", "validation")),
        "compressor_diagnostics_validation_only": _compressor_diagnostics(rows),
    }


def build_report(
    source_index: Mapping[str, Mapping[str, Any]],
    rows_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    cohorts: Mapping[str, Any],
    *,
    lineage: LineageManifest,
    input_digest: str,
    code_inventory_digest: str,
    source_lineage_authentication: Mapping[str, Any],
    trust_counts: Mapping[str, Mapping[str, int]],
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
) -> dict[str, Any]:
    source_rows = _source_rows(source_index)
    model_specific: dict[str, Any] = {}
    for model in MODELS:
        ids = set(cohorts["model_specific"][model]["ids"])
        selected = _filter_ids(rows_by_model[model], ids)
        bootstrap = paired_bootstrap(
            {model: selected},
            cohort_name=f"model_specific:{model}",
            replicates=bootstrap_replicates,
            master_seed=seed,
        )
        model_specific[model] = {
            "cohort": cohorts["model_specific"][model]["description"],
            "trust": dict(trust_counts[model]),
            "results": _model_report(selected, bootstrap["models"][model]),
            "bootstrap_method": {
                key: value for key, value in bootstrap.items() if key != "models"
            },
        }

    sensitivity: dict[str, Any] = {}
    for cohort_key, models in (
        ("completed_models_common", ("gemini-3.6-flash", "gpt-5.6-sol")),
        ("five_model_common", tuple(MODELS)),
    ):
        ids = set(cohorts[cohort_key]["ids"])
        selected_by_model = {
            model: _filter_ids(rows_by_model[model], ids) for model in models
        }
        bootstrap = paired_bootstrap(
            selected_by_model,
            cohort_name=cohort_key,
            replicates=bootstrap_replicates,
            master_seed=seed,
        )
        sensitivity[cohort_key] = {
            "cohort": cohorts[cohort_key]["description"],
            "models": {
                model: _model_report(
                    selected_by_model[model], bootstrap["models"][model]
                )
                for model in models
            },
            "bootstrap_method": {
                key: value for key, value in bootstrap.items() if key != "models"
            },
        }

    source_level = _level_descriptives(source_rows, ("source",))["source"]
    source_summary = {
        "cohort": cohorts["source_universe"]["description"],
        "distributions": {
            estimand: _summary(
                [float(row[f"source_{estimand}"]) for row in source_rows]
            )
            for estimand in ("actual", "baseline", "excess")
        },
        "actual_excess_association": continuous_metrics(
            [float(row["source_actual"]) for row in source_rows],
            [float(row["source_excess"]) for row in source_rows],
            require_defined=True,
            left_label="actual",
            right_label="excess",
        ),
        "secondary_source_excess_quantile_label_alignment": {
            "source_actual": _label_association(source_rows, "source_actual"),
            "source_excess": _label_association(source_rows, "source_excess"),
            "warning": (
                "Within each dataset x category cell, L1-L5 were deterministically "
                "assigned from descending source-excess ranks; source label-to-excess "
                "association is partly deterministic by construction."
            ),
        },
        "level_descriptives": source_level,
    }

    limitations = [
        "Experiment B measures cross-generator reproducibility, not criterion validity.",
        "Levels were constructed within dataset x category cells from descending source-excess ranks and are secondary diagnostics.",
        "Model-specific cohorts differ in coverage; common cohorts are selection-conditioned.",
        "Primary model cohorts mix stored generation protocols; protocol-group estimates are non-randomized sensitivity diagnostics.",
        "Legacy rows are canonical-row-hash trusted but lack complete modern call provenance.",
        "Source counterfactual texts are truncated, so source per-compressor scores are not reconstructed.",
        "Stored metric reproducibility does not independently authenticate historical remote generations.",
        "Publication is a hash-recorded snapshot with repeated pre-commit checks, not a linearizable read protected by an Experiment B reader lease.",
    ]
    five_model_datasets = cohorts["five_model_common"]["description"][
        "dataset_counts"
    ]
    if five_model_datasets.get("oasst1", 0) == 0:
        limitations.append("The current five-model common cohort contains no OASST1 rows.")

    report = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "state": "DERIVED_SNAPSHOT_COMPLETE",
        "created_at_utc": created_at_utc,
        "active_lineage": {
            "path": str(lineage.path.resolve()) if lineage.path else None,
            "sha256": lineage.sha256,
            "config_fingerprint": lineage.config_fingerprint,
        },
        "input_inventory_digest": input_digest,
        "code_inventory_digest": code_inventory_digest,
        "source_lineage_authentication": dict(source_lineage_authentication),
        "analysis_contract": {
            "primary_question": (
                "On identical source IDs, compare source-to-validation reproducibility "
                "for canonical aggregate actual_ratio and excess_ratio."
            ),
            "primary_metric": "Spearman rho",
            "delta_orientation": "actual_minus_excess",
            "positive_delta_interpretation": (
                "Raw actual_ratio has stronger cross-generator reproducibility."
            ),
            "canonical_aggregate_only": True,
            "per_compressor_primary": False,
            "label_analysis_secondary": True,
            "label_definition": "source_excess_quantile_label",
            "label_circularity_warning": (
                "Within each dataset x category cell, L1-L5 were deterministically "
                "assigned from descending source-excess ranks; these are source-derived "
                "score bins, not independent human labels or criterion truth."
            ),
        },
        "bootstrap": {
            "replicates": bootstrap_replicates,
            "master_seed": seed,
            "confidence_level": 0.95,
            "minimum_valid_fraction": 0.99,
            "undefined_replicate_policy": (
                "discard the whole paired/common replicate; require at least 99% valid"
            ),
            "sampling_unit": "source_id",
            "strata": ["dataset", "category"],
            "level_used_as_stratum": False,
        },
        "coverage": {
            "source_n": len(source_index),
            "validation_total": sum(len(rows) for rows in rows_by_model.values()),
            "model_counts": {model: len(rows_by_model[model]) for model in MODELS},
            "trust_counts": {model: dict(trust_counts[model]) for model in MODELS},
            "gpt56_declared_nonresponses": list(GPT56_NONRESPONSES),
        },
        "source_universe": source_summary,
        "model_specific_primary": model_specific,
        "common_cohort_sensitivity": sensitivity,
        "limitations": limitations,
        "execution": {
            "api_calls": 0,
            "model_generation": False,
            "gpu_inference": False,
            "recompression": False,
            "experiment_b_modified": False,
        },
        "warnings": [],
    }
    return _prepare_machine_payload(report)


def _metric_csv_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    columns = (
        "cohort",
        "model",
        "scope",
        "split_type",
        "split_value",
        "metric",
        "estimate",
        "ci_low",
        "ci_high",
        "n",
        "analysis_role",
        "metric_role",
        "primary",
        "notes",
    )
    rows: list[dict[str, Any]] = []

    def add(
        *,
        cohort: str,
        model: str,
        scope: str,
        metric: str,
        estimate: Any,
        n: int,
        primary: bool,
        ci: Mapping[str, Any] | None = None,
        split_type: str = "pooled",
        split_value: str = "all",
        notes: str = "",
    ) -> None:
        analysis_role = (
            "primary" if cohort.startswith("model_specific:") else "sensitivity"
        )
        metric_role = "primary" if primary else "secondary"
        combined_primary = analysis_role == "primary" and metric_role == "primary"
        rows.append(
            dict(
                zip(
                    columns,
                    (
                        cohort,
                        model,
                        scope,
                        split_type,
                        split_value,
                        metric,
                        estimate,
                        ci.get("low") if ci else None,
                        ci.get("high") if ci else None,
                        n,
                        analysis_role,
                        metric_role,
                        combined_primary,
                        notes,
                    ),
                )
            )
        )

    reports: list[tuple[str, str, Mapping[str, Any]]] = []
    for model, entry in report["model_specific_primary"].items():
        reports.append((f"model_specific:{model}", model, entry["results"]))
    for cohort, entry in report["common_cohort_sensitivity"].items():
        for model, result in entry["models"].items():
            reports.append((cohort, model, result))

    for cohort, model, result in reports:
        point = result["continuous_source_validation"]
        bootstrap = result["bootstrap_ci"]
        for scope in ("actual", "excess"):
            for metric in PRIMARY_METRICS:
                add(
                    cohort=cohort,
                    model=model,
                    scope=scope,
                    metric=metric,
                    estimate=point[scope][metric],
                    ci=bootstrap[scope][metric],
                    n=point["n"],
                    primary=metric == "spearman_rho",
                )
        for metric in PRIMARY_METRICS:
            add(
                cohort=cohort,
                model=model,
                scope="delta_actual_minus_excess",
                metric=metric,
                estimate=point["delta_actual_minus_excess"][metric],
                ci=bootstrap["delta_actual_minus_excess"][metric],
                n=point["n"],
                primary=metric == "spearman_rho",
            )
        for split_type, groups in result["splits"].items():
            for split_value, split in groups.items():
                for scope in ("actual", "excess"):
                    add(
                        cohort=cohort,
                        model=model,
                        scope=scope,
                        metric="spearman_rho",
                        estimate=split[scope]["spearman_rho"],
                        n=split["n"],
                        primary=False,
                        split_type=split_type,
                        split_value=split_value,
                    )
                add(
                    cohort=cohort,
                    model=model,
                    scope="delta_actual_minus_excess",
                    metric="spearman_rho",
                    estimate=split["delta_actual_minus_excess"]["spearman_rho"],
                    n=split["n"],
                    primary=False,
                    split_type=split_type,
                    split_value=split_value,
                )
        label = result["secondary_source_excess_quantile_label_alignment"]
        for scope in ("validation_actual", "validation_excess"):
            add(
                cohort=cohort,
                model=model,
                scope=f"secondary_label:{scope}",
                metric="spearman_rho",
                estimate=label[scope]["spearman_rho"],
                n=label[scope]["n"],
                primary=False,
                notes=(
                    "Within each dataset x category cell, levels were assigned from "
                    "descending source-excess ranks."
                ),
            )
        compressors = result["compressor_diagnostics_validation_only"]
        for scope in ("actual", "excess"):
            add(
                cohort=cohort,
                model=model,
                scope=f"compressor_diagnostic:{scope}",
                metric="krippendorff_alpha_interval",
                estimate=compressors[scope]["krippendorff_alpha_interval"],
                n=compressors[scope]["n"],
                primary=False,
                notes="Validation-side instrument agreement only.",
            )
    return rows


def _csv_bytes(report: Mapping[str, Any]) -> bytes:
    rows = _metric_csv_rows(report)
    columns = [
        "cohort",
        "model",
        "scope",
        "split_type",
        "split_value",
        "metric",
        "estimate",
        "ci_low",
        "ci_high",
        "n",
        "analysis_role",
        "metric_role",
        "primary",
        "notes",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": storage.file_sha256(path),
        "size": path.stat().st_size,
    }


def _remove_staging(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def validate_report_for_publication(
    report: Mapping[str, Any],
    *,
    lineage: LineageManifest,
    input_digest: str,
    code_digest: str,
    source_lineage_authentication: Mapping[str, Any],
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
) -> dict[str, Any]:
    payload = _prepare_machine_payload(report)
    required = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "state": "DERIVED_SNAPSHOT_COMPLETE",
        "created_at_utc": created_at_utc,
        "input_inventory_digest": input_digest,
        "code_inventory_digest": code_digest,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise AnalysisError(
                f"report publication binding mismatch for {key}: "
                f"{payload.get(key)!r} != {expected!r}"
            )
    active = payload.get("active_lineage")
    if not isinstance(active, Mapping):
        raise AnalysisError("report lacks active_lineage binding")
    if active.get("sha256") != lineage.sha256:
        raise AnalysisError("report active lineage SHA differs from publication lineage")
    if active.get("config_fingerprint") != lineage.config_fingerprint:
        raise AnalysisError("report lineage config fingerprint differs")
    expected_lineage_path = str(lineage.path.resolve()) if lineage.path else None
    if active.get("path") != expected_lineage_path:
        raise AnalysisError("report active lineage path differs")
    authentication = payload.get("source_lineage_authentication")
    if not isinstance(authentication, Mapping):
        raise AnalysisError("report lacks source lineage authentication")
    if dict(authentication) != dict(source_lineage_authentication):
        raise AnalysisError("report source lineage authentication differs from verified context")
    if (
        authentication.get("whole_file_verified") is not True
        or authentication.get("per_id_canonical_hashes_verified") is not True
        or authentication.get("total_rows_verified") != EXPECTED_SOURCE_TOTAL
    ):
        raise AnalysisError("report source lineage authentication is incomplete")
    contract = payload.get("analysis_contract")
    expected_contract = {
        "primary_metric": "Spearman rho",
        "delta_orientation": "actual_minus_excess",
        "canonical_aggregate_only": True,
        "per_compressor_primary": False,
        "label_analysis_secondary": True,
        "label_definition": "source_excess_quantile_label",
    }
    if not isinstance(contract, Mapping) or any(
        contract.get(key) != value for key, value in expected_contract.items()
    ):
        raise AnalysisError("report analysis contract is incomplete or inconsistent")
    if not isinstance(contract.get("primary_question"), str) or not contract["primary_question"]:
        raise AnalysisError("report lacks the primary scientific question")
    limitations = payload.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(value, str) or not value for value in limitations)
    ):
        raise AnalysisError("report limitations are empty or malformed")
    bootstrap = payload.get("bootstrap")
    if not isinstance(bootstrap, Mapping):
        raise AnalysisError("report lacks bootstrap contract")
    if (
        bootstrap.get("replicates") != bootstrap_replicates
        or bootstrap.get("master_seed") != seed
        or bootstrap.get("sampling_unit") != "source_id"
        or bootstrap.get("strata") != ["dataset", "category"]
        or bootstrap.get("level_used_as_stratum") is not False
        or bootstrap.get("minimum_valid_fraction") != 0.99
        or bootstrap.get("confidence_level") != 0.95
    ):
        raise AnalysisError("report bootstrap contract differs from publication config")
    coverage = payload.get("coverage")
    if not isinstance(coverage, Mapping):
        raise AnalysisError("report lacks coverage")
    if coverage.get("source_n") != EXPECTED_SOURCE_TOTAL:
        raise AnalysisError("report source coverage differs from current contract")
    if coverage.get("validation_total") != sum(EXPECTED_MODEL_COUNTS.values()):
        raise AnalysisError("report validation coverage differs from current contract")
    if coverage.get("model_counts") != EXPECTED_MODEL_COUNTS:
        raise AnalysisError("report model coverage differs from current contract")
    if coverage.get("gpt56_declared_nonresponses") != list(GPT56_NONRESPONSES):
        raise AnalysisError("report nonresponse roster differs from current contract")
    execution = payload.get("execution")
    expected_execution = {
        "api_calls": 0,
        "model_generation": False,
        "gpu_inference": False,
        "recompression": False,
        "experiment_b_modified": False,
    }
    if not isinstance(execution, Mapping) or any(
        execution.get(key) != value for key, value in expected_execution.items()
    ):
        raise AnalysisError("report execution declaration is incomplete or inconsistent")
    for key in (
        "source_universe",
        "model_specific_primary",
        "common_cohort_sensitivity",
        "analysis_contract",
        "limitations",
    ):
        if key not in payload:
            raise AnalysisError(f"report lacks required section {key}")
    def validate_cohort_description(value: Any, expected_n: int, context: str) -> None:
        if not isinstance(value, Mapping) or value.get("n_source_ids") != expected_n:
            raise AnalysisError(f"{context} cohort count differs")
        roster_hash = value.get("id_roster_sha256")
        if not isinstance(roster_hash, str) or not _SHA256_RE.fullmatch(roster_hash):
            raise AnalysisError(f"{context} lacks a valid ID-roster hash")

    def validate_bootstrap_method(value: Any, context: str) -> None:
        if not isinstance(value, Mapping):
            raise AnalysisError(f"{context} bootstrap method is missing")
        expected = {
            "replicates_requested": bootstrap_replicates,
            "replicates_attempted": bootstrap_replicates,
            "master_seed": seed,
            "sampling_unit": "source_id",
            "strata": ["dataset", "category"],
            "level_excluded_from_strata": True,
            "minimum_valid_fraction": 0.99,
            "confidence_level": 0.95,
        }
        if any(value.get(key) != expected_value for key, expected_value in expected.items()):
            raise AnalysisError(f"{context} nested bootstrap contract differs")
        valid = value.get("replicates_valid")
        undefined = value.get("undefined_replicates")
        if (
            type(valid) is not int
            or type(undefined) is not int
            or valid + undefined != bootstrap_replicates
            or valid < math.ceil(bootstrap_replicates * 0.99)
        ):
            raise AnalysisError(f"{context} nested bootstrap replicate accounting differs")

    def validate_result(value: Any, expected_n: int, context: str) -> None:
        if not isinstance(value, Mapping):
            raise AnalysisError(f"{context} result is malformed")
        point = value.get("continuous_source_validation")
        intervals = value.get("bootstrap_ci")
        if not isinstance(point, Mapping) or point.get("n") != expected_n:
            raise AnalysisError(f"{context} continuous result N differs")
        if not isinstance(intervals, Mapping):
            raise AnalysisError(f"{context} bootstrap intervals are missing")
        for scope in ("actual", "excess", "delta_actual_minus_excess"):
            point_scope = point.get(scope)
            interval_scope = intervals.get(scope)
            if not isinstance(point_scope, Mapping) or not isinstance(interval_scope, Mapping):
                raise AnalysisError(f"{context}.{scope} is malformed")
            if scope in ("actual", "excess") and point_scope.get("n") != expected_n:
                raise AnalysisError(f"{context}.{scope} N differs")
            for metric in PRIMARY_METRICS:
                estimate = point_scope.get(metric)
                interval = interval_scope.get(metric)
                if not _is_finite_number(estimate):
                    raise AnalysisError(f"{context}.{scope}.{metric} is not finite")
                estimate_value = float(estimate)
                if metric != "krippendorff_alpha_interval":
                    bound = 2.0 if scope == "delta_actual_minus_excess" else 1.0
                    if not -bound <= estimate_value <= bound:
                        raise AnalysisError(f"{context}.{scope}.{metric} is out of range")
                elif scope != "delta_actual_minus_excess" and estimate_value > 1.0:
                    raise AnalysisError(f"{context}.{scope}.{metric} exceeds one")
                if not isinstance(interval, Mapping):
                    raise AnalysisError(f"{context}.{scope}.{metric} CI is missing")
                low = interval.get("low")
                high = interval.get("high")
                if not _is_finite_number(low) or not _is_finite_number(high):
                    raise AnalysisError(f"{context}.{scope}.{metric} CI is not finite")
                if float(low) > float(high):
                    raise AnalysisError(f"{context}.{scope}.{metric} CI is reversed")
        for metric in PRIMARY_METRICS:
            expected_delta = float(point["actual"][metric]) - float(
                point["excess"][metric]
            )
            observed_delta = float(point["delta_actual_minus_excess"][metric])
            if not _same_float(observed_delta, expected_delta, atol=1e-15):
                raise AnalysisError(f"{context}.{metric} delta arithmetic differs")
        for section in (
            "splits",
            "protocol_mixture_and_sensitivity",
            "secondary_source_excess_quantile_label_alignment",
            "level_descriptives",
            "compressor_diagnostics_validation_only",
        ):
            if not isinstance(value.get(section), Mapping):
                raise AnalysisError(f"{context} lacks required section {section}")

    source_universe = payload.get("source_universe")
    if not isinstance(source_universe, Mapping):
        raise AnalysisError("report source_universe is malformed")
    validate_cohort_description(
        source_universe.get("cohort"), EXPECTED_SOURCE_TOTAL, "source_universe"
    )
    for section in (
        "distributions",
        "actual_excess_association",
        "secondary_source_excess_quantile_label_alignment",
        "level_descriptives",
    ):
        if not isinstance(source_universe.get(section), Mapping):
            raise AnalysisError(f"source_universe lacks required section {section}")

    model_reports = payload.get("model_specific_primary")
    if not isinstance(model_reports, Mapping) or set(model_reports) != set(MODELS):
        raise AnalysisError("report model-specific section has the wrong model roster")
    for model in MODELS:
        entry = model_reports.get(model)
        if not isinstance(entry, Mapping):
            raise AnalysisError(f"report lacks model-specific entry for {model}")
        cohort = entry.get("cohort")
        results = entry.get("results")
        method = entry.get("bootstrap_method")
        validate_cohort_description(
            cohort, EXPECTED_MODEL_COUNTS[model], f"model_specific.{model}"
        )
        validate_result(
            results, EXPECTED_MODEL_COUNTS[model], f"model_specific.{model}"
        )
        validate_bootstrap_method(method, f"model_specific.{model}")
        trust = entry.get("trust")
        coverage_trust = coverage.get("trust_counts")
        if (
            not isinstance(trust, Mapping)
            or not isinstance(coverage_trust, Mapping)
            or dict(trust) != dict(coverage_trust.get(model, {}))
            or trust.get("total") != EXPECTED_MODEL_COUNTS[model]
            or trust.get("legacy_hash_trusted", 0)
            + trust.get("modern_provenance_checked", 0)
            != EXPECTED_MODEL_COUNTS[model]
        ):
            raise AnalysisError(f"report trust counts differ for {model}")
    common_reports = payload.get("common_cohort_sensitivity")
    if not isinstance(common_reports, Mapping) or set(common_reports) != {
        "completed_models_common",
        "five_model_common",
    }:
        raise AnalysisError("report common-cohort section is incomplete")
    expected_common = {
        "completed_models_common": EXPECTED_COMPLETED_COMMON,
        "five_model_common": EXPECTED_FIVE_MODEL_COMMON,
    }
    expected_common_models = {
        "completed_models_common": {"gemini-3.6-flash", "gpt-5.6-sol"},
        "five_model_common": set(MODELS),
    }
    for name, expected_n in expected_common.items():
        entry = common_reports[name]
        if not isinstance(entry, Mapping) or not isinstance(entry.get("cohort"), Mapping):
            raise AnalysisError(f"report common cohort {name} is malformed")
        validate_cohort_description(
            entry["cohort"], expected_n, f"common.{name}"
        )
        common_models = entry.get("models")
        if not isinstance(common_models, Mapping) or set(common_models) != expected_common_models[name]:
            raise AnalysisError(f"report common cohort model roster differs for {name}")
        for model, model_result in common_models.items():
            validate_result(model_result, expected_n, f"common.{name}.{model}")
        validate_bootstrap_method(entry.get("bootstrap_method"), f"common.{name}")
    return payload


def publish_snapshot(
    report: Mapping[str, Any],
    *,
    output_root: Path,
    lineage: LineageManifest,
    inventory_before: Mapping[str, Mapping[str, Any]],
    inventory_provider: Any,
    code_inventory_before: Mapping[str, Mapping[str, Any]],
    code_inventory_provider: Any,
    source_lineage_authentication: Mapping[str, Any],
    state_validator: Any,
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
) -> Path:
    if bootstrap_replicates < MIN_PUBLICATION_BOOTSTRAP_REPLICATES:
        raise AnalysisError(
            f"publication requires at least {MIN_PUBLICATION_BOOTSTRAP_REPLICATES} "
            "bootstrap replicates"
        )
    if not _SHA256_RE.fullmatch(lineage.sha256):
        raise AnalysisError("lineage SHA is not a safe lowercase SHA-256 component")
    if not _UTC_RE.fullmatch(created_at_utc):
        raise AnalysisError("publication timestamp is not strict UTC ISO-8601")
    state_validator()
    root = validate_output_root(output_root)
    input_digest = _inventory_digest(inventory_before)
    code_digest = _inventory_digest(code_inventory_before)
    current_source_file_auth = validate_publication_inventory(
        lineage, inventory_before
    )
    try:
        publication_sources, publication_rows, publication_trust = load_joined_rows(
            output_dir=lineage.path.resolve().parent,
            lineage=lineage,
        )
    except RuntimeError as exc:
        raise AnalysisError(f"cannot revalidate publication inputs: {exc}") from exc
    current_source_row_auth = validate_source_row_lineage(
        lineage, publication_sources
    )
    current_source_auth = {
        **current_source_file_auth,
        **current_source_row_auth,
    }
    if dict(source_lineage_authentication) != current_source_auth:
        raise AnalysisError("verified source authentication differs at publication")
    payload = validate_report_for_publication(
        report,
        lineage=lineage,
        input_digest=input_digest,
        code_digest=code_digest,
        source_lineage_authentication=source_lineage_authentication,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at_utc,
    )
    publication_cohorts = build_cohorts(publication_sources, publication_rows)
    recomputed_report = build_report(
        publication_sources,
        publication_rows,
        publication_cohorts,
        lineage=lineage,
        input_digest=input_digest,
        code_inventory_digest=code_digest,
        source_lineage_authentication=current_source_auth,
        trust_counts=publication_trust,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at_utc,
    )
    recomputed_payload = validate_report_for_publication(
        recomputed_report,
        lineage=lineage,
        input_digest=input_digest,
        code_digest=code_digest,
        source_lineage_authentication=current_source_auth,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at_utc,
    )
    if storage.canonical_json_bytes(payload) != storage.canonical_json_bytes(
        recomputed_payload
    ):
        raise AnalysisError(
            "publication report differs from an independent full recomputation"
        )
    inventory_after_recomputation = inventory_provider()
    _require_inventory_equal(
        inventory_before,
        inventory_after_recomputation,
        stage="publication report recomputation",
    )
    code_after_recomputation = code_inventory_provider()
    _require_inventory_equal(
        code_inventory_before,
        code_after_recomputation,
        stage="publication code recomputation",
    )
    config = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "lineage_sha256": lineage.sha256,
        "input_inventory_digest": input_digest,
        "code_inventory_digest": code_digest,
        "bootstrap_replicates": bootstrap_replicates,
        "seed": seed,
    }
    config_digest = storage.sha256_bytes(storage.canonical_json_bytes(config))
    parsed_time = datetime.fromisoformat(created_at_utc.replace("Z", "+00:00"))
    timestamp = parsed_time.strftime("%Y%m%dT%H%M%SZ")
    lineage_dir = root / lineage.sha256
    final_dir = lineage_dir / f"{timestamp}_{config_digest[:12]}"
    if final_dir.exists():
        raise AnalysisError(f"refusing to replace existing snapshot: {final_dir}")
    root.mkdir(parents=True, exist_ok=True)
    _assert_no_link_components(root)
    lineage_dir.mkdir(parents=False, exist_ok=True)
    _assert_no_link_components(lineage_dir)
    resolved_lineage_dir = lineage_dir.resolve()
    if not _path_is_within(resolved_lineage_dir, root.resolve()):
        raise AnalysisError("lineage output directory escaped the approved root")
    if _path_is_within(resolved_lineage_dir, HERE.resolve()):
        raise AnalysisError("lineage output directory entered Experiment B")
    stage = lineage_dir / f".{final_dir.name}.staging-{uuid.uuid4().hex}"
    if stage.exists():
        raise AnalysisError(f"unexpected staging collision: {stage}")
    stage.mkdir(parents=False)
    _assert_no_link_components(stage)
    if stage.resolve().parent != resolved_lineage_dir:
        _remove_staging(stage)
        raise AnalysisError("staging directory escaped the lineage output directory")
    try:
        metrics_path = stage / "metrics.json"
        csv_path = stage / "metrics.csv"
        storage.atomic_replace_json(metrics_path, payload)
        storage.atomic_replace_bytes(csv_path, _csv_bytes(payload))
        after_outputs = inventory_provider()
        _require_inventory_equal(
            inventory_before, after_outputs, stage="derived output construction"
        )
        code_after_outputs = code_inventory_provider()
        _require_inventory_equal(
            code_inventory_before,
            code_after_outputs,
            stage="derived code verification",
        )
        metrics_record = _artifact_record(metrics_path)
        csv_record = _artifact_record(csv_path)
        manifest = {
            "schema": f"{SCHEMA}.manifest",
            "schema_version": SCHEMA_VERSION,
            "state": "DERIVED_SNAPSHOT_COMPLETE",
            "created_at_utc": created_at_utc,
            "snapshot_id": final_dir.name,
            "config": config,
            "runtime": {
                "python": sys.version,
                "platform": platform.platform(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
            },
            "code_dependencies": dict(code_inventory_before),
            "code_inventory_digest_before": code_digest,
            "code_inventory_digest_after": _inventory_digest(code_after_outputs),
            "active_lineage": {
                "path": str(lineage.path.resolve()) if lineage.path else None,
                "sha256": lineage.sha256,
                "config_fingerprint": lineage.config_fingerprint,
            },
            "inputs": dict(inventory_before),
            "input_inventory_digest_before": _inventory_digest(inventory_before),
            "input_inventory_digest_after": _inventory_digest(after_outputs),
            "stale_manifest_validation_declarations_used_as_current_contract": False,
            "current_validation_counts_bound_by_status_and_derived_input_hashes": True,
            "protected_stale_validation_metrics_unchanged": True,
            "report_fully_recomputed_from_validation_inputs_at_publication": True,
            "report_recomputation_canonical_bytes_equal": True,
            "publication_semantics": (
                "hash-recorded snapshot with repeated pre-commit state/input/code checks; "
                "no Experiment B reader lease"
            ),
            "source_lineage_authentication": dict(source_lineage_authentication),
            "coverage": payload["coverage"],
            "cohorts": {
                "source_universe": payload["source_universe"]["cohort"],
                "model_specific": {
                    model: entry["cohort"]
                    for model, entry in payload["model_specific_primary"].items()
                },
                "common_sensitivity": {
                    name: entry["cohort"]
                    for name, entry in payload["common_cohort_sensitivity"].items()
                },
            },
            "protocol_group_counts": {
                model: {
                    name: group["n"]
                    for name, group in entry["results"][
                        "protocol_mixture_and_sensitivity"
                    ]["groups"].items()
                }
                for model, entry in payload["model_specific_primary"].items()
            },
            "bootstrap": payload["bootstrap"],
            "artifacts": {
                "metrics.json": metrics_record,
                "metrics.csv": csv_record,
            },
            "execution": {
                "api_calls": 0,
                "model_generation": False,
                "gpu_inference": False,
                "recompression": False,
                "experiment_b_modified": False,
            },
        }
        manifest_path = stage / "manifest.json"
        storage.atomic_replace_json(manifest_path, _prepare_machine_payload(manifest))
        after_manifest = inventory_provider()
        _require_inventory_equal(
            inventory_before, after_manifest, stage="manifest publication"
        )
        code_after_manifest = code_inventory_provider()
        _require_inventory_equal(
            code_inventory_before,
            code_after_manifest,
            stage="final code verification",
        )
        state_validator()
        _assert_no_link_components(lineage_dir)
        if lineage_dir.resolve() != resolved_lineage_dir:
            raise AnalysisError("lineage output directory changed before commit")
        if final_dir.exists():
            raise AnalysisError(f"snapshot destination appeared before commit: {final_dir}")
        os.replace(stage, final_dir)
        storage.fsync_directory(final_dir.parent)
    except BaseException:
        _remove_staging(stage)
        raise
    return final_dir


def run_analysis(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    bootstrap_replicates: int = 2000,
    seed: int = 20260910,
    experiment_root: Path = HERE,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    output_root = validate_output_root(output_root, experiment_root=experiment_root)
    if bootstrap_replicates < MIN_PUBLICATION_BOOTSTRAP_REPLICATES:
        raise AnalysisError(
            f"production publication requires at least "
            f"{MIN_PUBLICATION_BOOTSTRAP_REPLICATES} bootstrap replicates"
        )
    status, lineage = preflight_state(
        experiment_root=experiment_root, output_dir=output_dir
    )
    del status  # The exact bytes remain bound by the inventory.

    def state_validator() -> None:
        _, current_lineage = preflight_state(
            experiment_root=experiment_root, output_dir=output_dir
        )
        if current_lineage.sha256 != lineage.sha256:
            raise AnalysisError("active lineage changed during derived analysis")
        if current_lineage.path != lineage.path:
            raise AnalysisError("active lineage path changed during derived analysis")

    def inventory_provider() -> dict[str, dict[str, Any]]:
        state_validator()
        return input_inventory(
            output_dir=output_dir,
            experiment_root=experiment_root,
            lineage=lineage,
        )

    code_inventory_before = code_inventory()
    inventory_before = inventory_provider()
    source_file_authentication = validate_publication_inventory(
        lineage, inventory_before
    )
    expected_rows = {
        **{f"source:{name}": count for name, count in EXPECTED_DATASET_COUNTS.items()},
        **{f"validation:{name}": count for name, count in EXPECTED_MODEL_COUNTS.items()},
    }
    for name, expected in expected_rows.items():
        if inventory_before[name].get("row_count") != expected:
            raise AnalysisError(f"input row count changed for {name}")
    source_index, rows_by_model, trust_counts = load_joined_rows(
        output_dir=output_dir, lineage=lineage
    )
    source_row_authentication = validate_source_row_lineage(lineage, source_index)
    source_lineage_authentication = {
        **source_file_authentication,
        **source_row_authentication,
    }
    inventory_after_load = inventory_provider()
    _require_inventory_equal(
        inventory_before, inventory_after_load, stage="strict input loading"
    )
    cohorts = build_cohorts(source_index, rows_by_model)
    created_at = _utc_now()
    report = build_report(
        source_index,
        rows_by_model,
        cohorts,
        lineage=lineage,
        input_digest=_inventory_digest(inventory_before),
        code_inventory_digest=_inventory_digest(code_inventory_before),
        source_lineage_authentication=source_lineage_authentication,
        trust_counts=trust_counts,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at,
    )
    inventory_after_compute = inventory_provider()
    _require_inventory_equal(
        inventory_before, inventory_after_compute, stage="metric computation"
    )
    code_after_compute = code_inventory()
    _require_inventory_equal(
        code_inventory_before, code_after_compute, stage="metric code verification"
    )
    return publish_snapshot(
        report,
        output_root=output_root,
        lineage=lineage,
        inventory_before=inventory_before,
        inventory_provider=inventory_provider,
        code_inventory_before=code_inventory_before,
        code_inventory_provider=code_inventory,
        source_lineage_authentication=source_lineage_authentication,
        state_validator=state_validator,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260910)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = run_analysis(
        output_root=args.output_root,
        bootstrap_replicates=args.bootstrap_replicates,
        seed=args.seed,
    )
    metrics = _strict_object(snapshot / "metrics.json")
    coverage = metrics["coverage"]
    print(f"Experiment B actual-vs-excess snapshot: {snapshot}")
    print(f"active lineage: {metrics['active_lineage']['sha256']}")
    print(f"source rows: {coverage['source_n']}")
    print(f"validation rows: {coverage['validation_total']}")
    print(f"input inventory: {metrics['input_inventory_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
