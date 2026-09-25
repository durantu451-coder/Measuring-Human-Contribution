#!/usr/bin/env python3
"""Transactional runner for the frozen actual-only sensitivity analyses."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import numpy as np

sys.dont_write_bytecode = True
import analysis_core as core

SCRIPT_PATH_UNRESOLVED = Path(os.path.abspath(__file__))
BUNDLE_DIR_UNRESOLVED = SCRIPT_PATH_UNRESOLVED.parent
BUNDLE_DIR = BUNDLE_DIR_UNRESOLVED.resolve()
PARENT_DIR_UNRESOLVED = BUNDLE_DIR_UNRESOLVED.parent
PARENT_DIR = PARENT_DIR_UNRESOLVED.resolve()
PROJECT_ROOT = BUNDLE_DIR.parents[2]
MIGRATION_ID = "phi_v2_20260822T180934_7d329704f7ab"
BUNDLE_ID = f"{MIGRATION_ID}_actual_incremental_sensitivity_20260911T172319Z_v1"
EXPECTED_STAGING_NAME = f".{BUNDLE_ID}.staging"
FINAL_DIR_UNRESOLVED = PARENT_DIR_UNRESOLVED / BUNDLE_ID
FINAL_DIR = PARENT_DIR / BUNDLE_ID
AUTHORITY_ID = f"{MIGRATION_ID}_actual_heuristic_20260911T035818Z_v1"
AUTHORITY = PARENT_DIR / AUTHORITY_ID
LEDGER = AUTHORITY / "actual_pair_features.jsonl"
CREATED_AT_UTC = "2026-09-11T17:23:19Z"
CODE_FILES = ("analysis_core.py", "run_analysis.py", "audit_analysis.py", "test_analysis.py")
PREPARED_FILES = ("run_config.json", "fold_assignments.json", "derived_features_receipt.json", "prepare_receipt.json")
TABLE_FILES = (
    "table1_ratio_vs_raw_gain.md", "table2_incremental_validity.md",
    "table3_evaluator_sensitivity.md", "table4_length_residualized.md",
    "table5_length_common_support.md",
)
PROJECTION_FILES = (
    "metrics.csv", *TABLE_FILES, "appendix_subgroups.md",
    "appendix_model_coefficients.md", "REPORT_ZH.md",
)
FORMAL_SCIENTIFIC_FILES = (
    *PREPARED_FILES, "oof_predictions.jsonl", "model_fits.jsonl",
    "checkpoint_index.json", "bootstrap_summary.json", "metrics.json",
    *PROJECTION_FILES, "execution.json",
)
ALLOWED_BUNDLE_DIRECTORIES = ("checkpoints", "checkpoints/oof", "checkpoints/bootstrap")
COMPLETION_KEYS = {
    "schema", "schema_version", "state", "bundle_id", "config_sha256",
    "authority_ledger_sha256", "checkpoint_index_sha256", "artifacts",
    "artifact_inventory_sha256", "code_snapshot", "payload_sha256_excluding_this_field",
}


def _ensure_stage(*, allow_final: bool = False) -> bool:
    parent = core.require_plain_directory(PARENT_DIR_UNRESOLVED)
    resolved_bundle = core.require_plain_directory(BUNDLE_DIR_UNRESOLVED, parent=PARENT_DIR_UNRESOLVED)
    if resolved_bundle != BUNDLE_DIR or parent != PARENT_DIR:
        raise core.AnalysisError("unresolved/canonical bundle path differs")
    if core.is_reparse_or_link(SCRIPT_PATH_UNRESOLVED) or not SCRIPT_PATH_UNRESOLVED.is_file():
        raise core.AnalysisError("runner script symlink/reparse/non-file rejected")
    destination = core.require_absent_or_plain_directory(FINAL_DIR_UNRESOLVED, parent=PARENT_DIR_UNRESOLVED)
    if destination != FINAL_DIR:
        raise core.AnalysisError("final destination canonical path differs")
    is_staging = BUNDLE_DIR_UNRESOLVED.name == EXPECTED_STAGING_NAME
    is_final = BUNDLE_DIR_UNRESOLVED.name == BUNDLE_ID
    if not is_staging and not (allow_final and is_final):
        expected = f"{EXPECTED_STAGING_NAME}" + (f" or {BUNDLE_ID}" if allow_final else "")
        raise core.AnalysisError(f"runner must execute from exact directory {expected}")
    return is_final


def _require_safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts or "\\" in value:
        raise core.AnalysisError(f"unsafe {label} path")
    return value


def _code_snapshot() -> list[dict[str, Any]]:
    records = []
    for name in CODE_FILES:
        path = BUNDLE_DIR / name
        if not path.is_file():
            raise core.AnalysisError(f"code file absent: {name}")
        records.append(core.file_record(path, BUNDLE_DIR))
    return sorted(records, key=lambda item: item["path"])


def _load_preparation() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, config_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "run_config.json")
    folds, folds_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "fold_assignments.json")
    derived, derived_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "derived_features_receipt.json")
    prepare, _, _ = core.strict_json_load_record(BUNDLE_DIR / "prepare_receipt.json")
    core.validate_frozen_run_config(config, bundle_id=BUNDLE_ID)
    core.verify_payload_hash(folds)
    core.verify_payload_hash(derived)
    core.verify_payload_hash(prepare)
    if set(folds) != {
        "schema", "schema_version", "outer_seed", "inner_master_seed", "algorithm",
        "row_order_invariant", "row_permutation_test", "cluster_row_counts",
        "cluster_row_count_sha256", "outer_assignments", "outer_assignment_sha256",
        "outer_folds", "outer_fold_cells", "coverage", "payload_sha256_excluding_this_field",
    }:
        raise core.AnalysisError("fold receipt exact schema differs")
    if set(derived) != {
        "schema", "schema_version", "state", "config_sha256", "authority_ledger_sha256",
        "pair_set_sha256", "coverage", "raw_algebra", "consensus",
        "forbidden_derived_fields_constructed", "prompt_output_text_reads",
        "recompression_operations", "payload_sha256_excluding_this_field",
    } or set(prepare) != {
        "schema", "schema_version", "state", "bundle_id", "artifacts",
        "authority_manifest_sha256", "ledger_sha256", "pair_set_sha256",
        "bootstrap_draw_sequence_sha256", "elapsed_seconds", "resources",
        "formal_statistics_started", "external_api_calls", "network_access", "gpu",
        "model_generation", "recompression", "prompt_output_text_reads",
        "payload_sha256_excluding_this_field",
    }:
        raise core.AnalysisError("prepared receipt exact schema differs")
    if (
        config.get("bundle_id") != BUNDLE_ID or prepare.get("state") != "prepared"
        or derived.get("state") != "complete"
        or derived.get("config_sha256") != config_sha
    ):
        raise core.AnalysisError("preparation state differs")
    expected = {
        "run_config.json": config_sha,
        "fold_assignments.json": folds_sha,
        "derived_features_receipt.json": derived_sha,
    }
    if prepare.get("artifacts") != expected:
        raise core.AnalysisError("prepare receipt bindings differ")
    current_code = _code_snapshot()
    if config.get("code_snapshot", {}).get("files") != current_code:
        raise core.AnalysisError("code changed after run_config freeze")
    return config, folds, derived, prepare


def _expected_derived_receipt(dataset: core.Dataset, config_sha: str) -> dict[str, Any]:
    base = {
        "schema": "actual_incremental_sensitivity.derived_features_receipt",
        "schema_version": 1, "state": "complete",
        "config_sha256": config_sha,
        "authority_ledger_sha256": dataset.ledger_sha256,
        "pair_set_sha256": dataset.pair_set_sha256,
        "coverage": {"pairs": dataset.n, "items": dataset.item_count, "source_clusters": len(dataset.cluster_keys)},
        "raw_algebra": core.raw_algebra_receipt(dataset),
        "consensus": {
            "primary_array_sha256": core.array_sha256(dataset.values["consensus_midrank_percentile"]),
            "sensitivity_array_sha256": core.array_sha256(dataset.values["consensus_global_z"]),
            "llama_global_z_array_sha256": core.array_sha256(dataset.values["phi_actual_llama_global_z"]),
            "mixtral_global_z_array_sha256": core.array_sha256(dataset.values["phi_actual_mixtral_global_z"]),
            "constructed_once_over_rows": dataset.n,
        },
        "forbidden_derived_fields_constructed": False,
        "prompt_output_text_reads": 0, "recompression_operations": 0,
    }
    return core.payload_with_hash(base)


def _validate_prepare_receipt_static(prepare: Mapping[str, Any]) -> None:
    expected_fields = {
        "schema", "schema_version", "state", "bundle_id", "artifacts",
        "authority_manifest_sha256", "ledger_sha256", "pair_set_sha256",
        "bootstrap_draw_sequence_sha256", "elapsed_seconds", "resources",
        "formal_statistics_started", "external_api_calls", "network_access", "gpu",
        "model_generation", "recompression", "prompt_output_text_reads",
        "payload_sha256_excluding_this_field",
    }
    if not isinstance(prepare, Mapping) or set(prepare) != expected_fields:
        raise core.AnalysisError("prepare receipt exact schema differs")
    core.verify_payload_hash(prepare)
    expected_artifacts = {
        name: core.sha256_file(BUNDLE_DIR / name)
        for name in ("run_config.json", "fold_assignments.json", "derived_features_receipt.json")
    }
    if prepare.get("artifacts") != expected_artifacts:
        raise core.AnalysisError("prepare receipt bindings differ")
    expected_static = {
        "schema": "actual_incremental_sensitivity.prepare_receipt", "schema_version": 1,
        "state": "prepared", "bundle_id": BUNDLE_ID,
        "authority_manifest_sha256": core.EXPECTED_AUTHORITY_MANIFEST_SHA256,
        "ledger_sha256": core.EXPECTED_LEDGER_SHA256,
        "pair_set_sha256": core.EXPECTED_PAIR_SET_SHA256,
        "bootstrap_draw_sequence_sha256": core.EXPECTED_DRAW_SHA256,
        "formal_statistics_started": False, "external_api_calls": 0,
        "network_access": False, "gpu": False, "model_generation": False,
        "recompression": False, "prompt_output_text_reads": 0,
    }
    for key, expected in expected_static.items():
        if prepare.get(key) != expected:
            raise core.AnalysisError(f"prepare receipt frozen value differs: {key}")
    elapsed = prepare.get("elapsed_seconds")
    resources = prepare.get("resources")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(float(elapsed)) or float(elapsed) < 0:
        raise core.AnalysisError("prepare elapsed_seconds must be finite and nonnegative")
    _validate_resource_receipt(resources, "prepare")


def _rebuild_and_validate_preparation(
    config: Mapping[str, Any], folds: Mapping[str, Any], derived: Mapping[str, Any], prepare_receipt: Mapping[str, Any],
) -> core.Dataset:
    authority_receipt = core.validate_authority(AUTHORITY, PROJECT_ROOT)
    dataset = core.load_ledger(LEDGER)
    rebuilt_folds = core.build_fold_plan(dataset)
    if rebuilt_folds != folds:
        raise core.AnalysisError("prepared fold plan does not exactly rebuild")
    selections = core.frozen_strongest(AUTHORITY / "metrics.json")
    expected_config = core.make_run_config(
        bundle_id=BUNDLE_ID, authority_receipt=authority_receipt,
        selections=selections, fold_plan=rebuilt_folds,
        code_files=[BUNDLE_DIR / name for name in CODE_FILES],
        created_at_utc=CREATED_AT_UTC,
    )
    if expected_config != config:
        raise core.AnalysisError("run_config differs from complete fresh semantic reconstruction")
    disk_config, config_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "run_config.json")
    if disk_config != config:
        raise core.AnalysisError("run_config changed between preparation load and semantic rebuild")
    expected_derived = _expected_derived_receipt(dataset, config_sha)
    if expected_derived != derived:
        raise core.AnalysisError("derived_features_receipt differs from complete fresh reconstruction")
    _validate_prepare_receipt_static(prepare_receipt)
    if core.bootstrap_draw_sequence_sha256() != core.EXPECTED_DRAW_SHA256:
        raise core.AnalysisError("bootstrap draw sequence SHA-256 differs")
    return dataset


def _valid_prepare_prefix_length() -> int:
    presence = [core.path_lexists(BUNDLE_DIR / name) for name in PREPARED_FILES]
    prefix_length = 0
    while prefix_length < len(presence) and presence[prefix_length]:
        # A present prefix member must be an ordinary readable file; dangling or
        # file-level reparses are never treated as an absent recovery boundary.
        core.file_fingerprint(BUNDLE_DIR / PREPARED_FILES[prefix_length])
        prefix_length += 1
    if any(presence[prefix_length:]):
        raise core.AnalysisError("preparation artifacts are not a valid ordered prefix")
    return prefix_length


def _validate_preparation_tree(prefix_length: int) -> None:
    expected = {*CODE_FILES, "RUNBOOK.md", *PREPARED_FILES[:prefix_length]}
    actual = set(core.inspect_plain_tree(BUNDLE_DIR, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES))
    if actual != expected:
        raise core.AnalysisError(
            f"preparation-stage recursive inventory differs; missing={sorted(expected-actual)}, "
            f"unknown={sorted(actual-expected)}"
        )


def prepare() -> None:
    _ensure_stage()
    if core.path_lexists(FINAL_DIR_UNRESOLVED):
        raise core.AnalysisError(f"final destination already exists: {FINAL_DIR_UNRESOLVED}")
    prefix_length = _valid_prepare_prefix_length()
    _validate_preparation_tree(prefix_length)
    if prefix_length == len(PREPARED_FILES):
        config, folds, derived, receipt = _load_preparation()
        _rebuild_and_validate_preparation(config, folds, derived, receipt)
        print("prepare: existing frozen receipts semantically rebuilt and validated; no-op", flush=True)
        return

    start = time.perf_counter()
    with core.ResourceMonitor() as monitor:
        monitor.set_phase("authority_validation")
        authority_receipt = core.validate_authority(AUTHORITY, PROJECT_ROOT)
        monitor.set_phase("ledger_scan")
        dataset = core.load_ledger(LEDGER)
        monitor.set_phase("fold_construction")
        folds = core.build_fold_plan(dataset)
        selections = core.frozen_strongest(AUTHORITY / "metrics.json")
        if core.bootstrap_draw_sequence_sha256() != core.EXPECTED_DRAW_SHA256:
            raise core.AnalysisError("bootstrap draw sequence SHA-256 differs")
        config = core.make_run_config(
            bundle_id=BUNDLE_ID, authority_receipt=authority_receipt,
            selections=selections, fold_plan=folds,
            code_files=[BUNDLE_DIR / name for name in CODE_FILES],
            created_at_utc=CREATED_AT_UTC,
        )
        # This is deliberately the first derived scientific artifact.
        core.atomic_write_json(BUNDLE_DIR / "run_config.json", config)
        core.atomic_write_json(BUNDLE_DIR / "fold_assignments.json", folds)
        derived = _expected_derived_receipt(dataset, core.sha256_file(BUNDLE_DIR / "run_config.json"))
        core.atomic_write_json(BUNDLE_DIR / "derived_features_receipt.json", derived)
    resources = monitor.receipt()
    prepare_base = {
        "schema": "actual_incremental_sensitivity.prepare_receipt",
        "schema_version": 1, "state": "prepared", "bundle_id": BUNDLE_ID,
        "artifacts": {
            name: core.sha256_file(BUNDLE_DIR / name)
            for name in ("run_config.json", "fold_assignments.json", "derived_features_receipt.json")
        },
        "authority_manifest_sha256": core.EXPECTED_AUTHORITY_MANIFEST_SHA256,
        "ledger_sha256": core.EXPECTED_LEDGER_SHA256,
        "pair_set_sha256": core.EXPECTED_PAIR_SET_SHA256,
        "bootstrap_draw_sequence_sha256": core.EXPECTED_DRAW_SHA256,
        "elapsed_seconds": time.perf_counter() - start,
        "resources": resources,
        "formal_statistics_started": False,
        "external_api_calls": 0, "network_access": False, "gpu": False,
        "model_generation": False, "recompression": False, "prompt_output_text_reads": 0,
    }
    core.atomic_write_json(BUNDLE_DIR / "prepare_receipt.json", core.payload_with_hash(prepare_base))
    print(f"prepare PASS: {dataset.n} pairs, {dataset.item_count} items, {len(dataset.cluster_keys)} clusters", flush=True)


def _prediction_key(learner: str, target: str, predictor: str) -> str:
    return f"{learner}|{target}|{predictor}"


def _analysis_predictor_matrix(
    dataset: core.Dataset, predictor: str, strongest_single: str,
) -> tuple[np.ndarray, list[str]]:
    if predictor == core.AUXILIARY_PREDICTOR_SET:
        if strongest_single not in core.HEURISTICS:
            raise core.AnalysisError("auxiliary strongest-single feature is not frozen heuristic")
        return dataset.values[strongest_single][:, None], [strongest_single]
    return core.predictor_matrix(dataset, predictor)


def _model_checkpoint_path(model_label: str, outer_fold: int) -> Path:
    token = hashlib.sha256(model_label.encode("utf-8")).hexdigest()[:24]
    return BUNDLE_DIR / "checkpoints" / "oof" / f"model_{token}_outer_{outer_fold}.npz"


def _model_checkpoint_arrays(
    model_label: str, rows: np.ndarray, prediction: np.ndarray, fit_record: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    return {
        "keys": np.asarray([model_label]),
        "rows": np.asarray(rows, dtype=np.int32),
        "values": np.asarray(prediction, dtype=np.float64),
        "fit_json": np.asarray(core.canonical_json_bytes(fit_record).decode("utf-8")),
    }


def _model_checkpoint_metadata(
    model_label: str, outer_fold: int, config_sha: str, arrays: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    keys = [model_label]
    return {
        "schema": "actual_incremental_sensitivity.model_oof_checkpoint",
        "schema_version": 1,
        "config_sha256": config_sha,
        "model_label": model_label,
        "outer_fold": int(outer_fold),
        "metric_key_sha256": core.sha256_bytes(core.canonical_json_bytes(keys)),
        "row_count": int(len(arrays["rows"])),
        "arrays": core.checkpoint_array_descriptor(arrays),
        "payload_sha256": core.checkpoint_payload_sha256(arrays),
    }


def _load_model_checkpoint(
    path: Path, *, model_label: str, outer_fold: int, config_sha: str,
    expected_rows: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    with core.open_plain_binary(path) as checkpoint_handle:
        with np.load(checkpoint_handle, allow_pickle=False) as stored:
            if set(stored.files) != {"keys", "rows", "values", "fit_json", "metadata_json"}:
                raise core.AnalysisError(f"model checkpoint array inventory differs: {path}")
            arrays = {name: np.asarray(stored[name]) for name in ("keys", "rows", "values", "fit_json")}
            metadata = core.strict_json_loads(str(stored["metadata_json"].item()), f"{path}.metadata")
    expected_metadata = _model_checkpoint_metadata(model_label, outer_fold, config_sha, arrays)
    if metadata != expected_metadata:
        raise core.AnalysisError(f"model checkpoint metadata differs: {path}")
    core.validate_deterministic_npz_file(path, arrays, metadata)
    if arrays["keys"].tolist() != [model_label]:
        raise core.AnalysisError(f"model checkpoint key differs: {path}")
    rows = np.asarray(arrays["rows"], dtype=np.int32)
    values = np.asarray(arrays["values"], dtype=np.float64)
    if (
        arrays["keys"].dtype.kind != "U" or arrays["keys"].shape != (1,)
        or arrays["rows"].dtype != np.dtype("int32")
        or arrays["values"].dtype != np.dtype("float64")
        or arrays["fit_json"].dtype.kind != "U" or arrays["fit_json"].shape != ()
        or not np.array_equal(rows, expected_rows)
        or values.shape != (len(rows),) or not np.isfinite(values).all()
    ):
        raise core.AnalysisError(f"model checkpoint row/value coverage differs: {path}")
    fit_record = core.strict_json_loads(str(arrays["fit_json"].item()), f"{path}.fit_json")
    if not isinstance(fit_record, dict) or fit_record.get("model_label") != model_label or fit_record.get("outer_fold") != outer_fold:
        raise core.AnalysisError(f"model checkpoint fit record differs: {path}")
    return values, fit_record


def _fit_ridge_resumable(
    x: np.ndarray, y: np.ndarray, dataset: core.Dataset,
    outer: Mapping[tuple[str, str, str], int], inner: Sequence[Mapping[tuple[str, str, str], int]],
    *, feature_names: Sequence[str], model_label: str, config_sha: str,
    monitor: core.ResourceMonitor,
) -> tuple[np.ndarray, list[dict[str, Any]], list[dict[str, Any]]]:
    cluster_outer = np.asarray([outer[key] for key in dataset.cluster_keys], dtype=np.int8)
    row_outer = cluster_outer[dataset.cluster_index]
    combined = np.full(dataset.n, np.nan, dtype=np.float64)
    fits: list[dict[str, Any]] = []; checkpoints: list[dict[str, Any]] = []
    for fold in range(5):
        rows = np.flatnonzero(row_outer == fold).astype(np.int32)
        path = _model_checkpoint_path(model_label, fold)
        if path.exists():
            values, fit_record = _load_model_checkpoint(
                path, model_label=model_label, outer_fold=fold,
                config_sha=config_sha, expected_rows=rows,
            )
        else:
            partial, records = core.nested_ridge_oof(
                x, y, dataset, outer, inner, feature_names=feature_names,
                model_label=model_label, outer_folds=(fold,),
            )
            if len(records) != 1:
                raise core.AnalysisError(f"{model_label}: expected one outer-fit record")
            values = partial[rows]; fit_record = records[0]
            arrays = _model_checkpoint_arrays(model_label, rows, values, fit_record)
            metadata = _model_checkpoint_metadata(model_label, fold, config_sha, arrays)
            core.write_npz_atomic(path, arrays, metadata)
        if np.isfinite(combined[rows]).any():
            raise core.AnalysisError(f"{model_label}: duplicate OOF fold coverage")
        combined[rows] = values; fits.append(fit_record)
        checkpoints.append(core.file_record(path, BUNDLE_DIR)); monitor.check()
    if not np.isfinite(combined).all():
        raise core.AnalysisError(f"{model_label}: incomplete resumed Ridge OOF")
    return combined, fits, checkpoints


def _fit_hgb_resumable(
    x: np.ndarray, y: np.ndarray, dataset: core.Dataset,
    outer: Mapping[tuple[str, str, str], int], *, model_label: str,
    config_sha: str, monitor: core.ResourceMonitor,
) -> tuple[np.ndarray | None, list[dict[str, Any]], str, list[dict[str, Any]]]:
    cluster_outer = np.asarray([outer[key] for key in dataset.cluster_keys], dtype=np.int8)
    row_outer = cluster_outer[dataset.cluster_index]
    combined = np.full(dataset.n, np.nan, dtype=np.float64)
    fits: list[dict[str, Any]] = []; checkpoints: list[dict[str, Any]] = []
    for fold in range(5):
        rows = np.flatnonzero(row_outer == fold).astype(np.int32)
        path = _model_checkpoint_path(model_label, fold)
        if path.exists():
            values, fit_record = _load_model_checkpoint(
                path, model_label=model_label, outer_fold=fold,
                config_sha=config_sha, expected_rows=rows,
            )
        else:
            partial, records, status = core.hgb_oof(
                x, y, dataset, outer, model_label=model_label, outer_folds=(fold,),
            )
            if status == "skipped_unavailable":
                if fold != 0 or checkpoints:
                    raise core.AnalysisError("HGB became unavailable after partial completion")
                return None, [{"model_label": model_label, "learner": "HistGradientBoostingRegressor", "status": status}], status, []
            if status != "complete" or partial is None or len(records) != 1:
                raise core.AnalysisError(f"{model_label}: invalid HGB fit result")
            values = partial[rows]; fit_record = records[0]
            arrays = _model_checkpoint_arrays(model_label, rows, values, fit_record)
            metadata = _model_checkpoint_metadata(model_label, fold, config_sha, arrays)
            core.write_npz_atomic(path, arrays, metadata)
        combined[rows] = values; fits.append(fit_record)
        checkpoints.append(core.file_record(path, BUNDLE_DIR)); monitor.check()
    if not np.isfinite(combined).all():
        raise core.AnalysisError(f"{model_label}: incomplete resumed HGB OOF")
    return combined, fits, "complete", checkpoints


def _fit_all(
    dataset: core.Dataset, fold_plan: Mapping[str, Any], config_sha: str,
    monitor: core.ResourceMonitor, strongest_single: str,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray], list[dict[str, Any]], list[dict[str, Any]]]:
    outer, inner = core.fold_maps(fold_plan)
    predictions: dict[str, np.ndarray] = {}
    length_predictions: dict[str, np.ndarray] = {}
    residuals: dict[str, np.ndarray] = {}
    fits: list[dict[str, Any]] = []; checkpoint_records: list[dict[str, Any]] = []
    monitor.set_phase("ridge_oof")
    for target in core.WHITEBOX_TARGETS:
        y = dataset.values[target]
        for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET):
            x, names = _analysis_predictor_matrix(dataset, predictor, strongest_single)
            label = _prediction_key("ridge", target, predictor)
            prediction, records, blocks = _fit_ridge_resumable(
                x, y, dataset, outer, inner, feature_names=names,
                model_label=label, config_sha=config_sha, monitor=monitor,
            )
            predictions[label] = prediction; fits.extend(records); checkpoint_records.extend(blocks)
            print(f"OOF {label}", flush=True)
    monitor.set_phase("hgb_oof")
    for target in core.WHITEBOX_TARGETS:
        y = dataset.values[target]
        for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET):
            x, _ = _analysis_predictor_matrix(dataset, predictor, strongest_single)
            label = _prediction_key("hgb", target, predictor)
            prediction, records, status, blocks = _fit_hgb_resumable(
                x, y, dataset, outer, model_label=label,
                config_sha=config_sha, monitor=monitor,
            )
            if status == "complete" and prediction is not None:
                predictions[label] = prediction
            fits.extend(records); checkpoint_records.extend(blocks)
            print(f"OOF {label}: {status}", flush=True)
    monitor.set_phase("length_residualization")
    for spec in core.LENGTH_SPECS:
        x, names = core.length_matrix(dataset, spec)
        for target in core.LENGTH_TARGETS:
            y = dataset.values[target]
            label = f"length_ridge|{spec}|{target}"
            prediction, records, blocks = _fit_ridge_resumable(
                x, y, dataset, outer, inner, feature_names=names,
                model_label=label, config_sha=config_sha, monitor=monitor,
            )
            length_predictions[label] = prediction
            residuals[f"{spec}|{target}"] = y - prediction
            fits.extend(records); checkpoint_records.extend(blocks)
            print(f"OOF {label}", flush=True)
    all_arrays = [*predictions.values(), *length_predictions.values(), *residuals.values()]
    if any(array.shape != (dataset.n,) or not np.isfinite(array).all() for array in all_arrays):
        raise core.AnalysisError("OOF output coverage/finite contract failed")
    return predictions, length_predictions, residuals, fits, checkpoint_records


def _commit_stream_create_or_identical(temporary: Path, destination: Path) -> None:
    core.commit_plain_file_create_or_identical(temporary, destination)
    temporary.unlink()


def _write_oof(
    dataset: core.Dataset, predictions: Mapping[str, np.ndarray],
    length_predictions: Mapping[str, np.ndarray], residuals: Mapping[str, np.ndarray],
    config_sha: str,
) -> list[dict[str, Any]]:
    all_predictions = {**predictions, **length_predictions}
    keys = sorted((*all_predictions.keys(), *(f"residual|{key}" for key in residuals)))
    key_sha = core.sha256_bytes(core.canonical_json_bytes(keys))
    outer_config = core.strict_json_load(BUNDLE_DIR / "fold_assignments.json")
    outer, _ = core.fold_maps(outer_config)
    row_outer = np.asarray([outer[dataset.cluster_keys[index]] for index in dataset.cluster_index], dtype=np.int8)
    checkpoint_records: list[dict[str, Any]] = []
    for fold in range(5):
        rows = np.flatnonzero(row_outer == fold).astype(np.int32)
        matrix = np.column_stack(
            [all_predictions[key][rows] if key in all_predictions else residuals[key.removeprefix("residual|")][rows] for key in keys]
        ).astype(np.float64, copy=False)
        arrays = {"rows": rows, "values": matrix, "keys": np.asarray(keys)}
        metadata = {
            "schema": "actual_incremental_sensitivity.oof_checkpoint", "schema_version": 1,
            "config_sha256": config_sha, "outer_fold": fold,
            "metric_key_sha256": key_sha, "row_count": int(len(rows)),
            "arrays": core.checkpoint_array_descriptor(arrays),
            "payload_sha256": core.checkpoint_payload_sha256(arrays),
        }
        path = BUNDLE_DIR / "checkpoints" / "oof" / f"outer_{fold}.npz"
        core.write_npz_atomic(path, arrays, metadata)
        checkpoint_records.append(core.file_record(path, BUNDLE_DIR))
    output = BUNDLE_DIR / "oof_predictions.jsonl"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.{os.getpid()}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            for index, pair_key in enumerate(dataset.pair_keys):
                row: dict[str, Any] = {
                    "generation_model": pair_key[0], "domain": pair_key[1],
                    "id": pair_key[2], "level": pair_key[3],
                    "outer_fold": int(row_outer[index]),
                }
                row.update({f"prediction|{key}": float(all_predictions[key][index]) for key in sorted(all_predictions)})
                row.update({f"residual|{key}": float(residuals[key][index]) for key in sorted(residuals)})
                handle.write(core.canonical_json_bytes(row, newline=True))
            handle.flush(); os.fsync(handle.fileno())
        _commit_stream_create_or_identical(temporary, output)
    finally:
        if core.path_lexists(temporary):
            if core.is_reparse_or_link(temporary): raise core.AnalysisError(f"temporary path replaced by link/reparse: {temporary}")
            temporary.unlink()
    return checkpoint_records


def _stream_validate_oof(
    dataset: core.Dataset, predictions: Mapping[str, np.ndarray],
    length_predictions: Mapping[str, np.ndarray], residuals: Mapping[str, np.ndarray],
    fold_plan: Mapping[str, Any],
) -> dict[str, Any]:
    all_predictions = {**predictions, **length_predictions}
    prediction_fields = [f"prediction|{key}" for key in sorted(all_predictions)]
    residual_fields = [f"residual|{key}" for key in sorted(residuals)]
    expected_fields = {
        "generation_model", "domain", "id", "level", "outer_fold",
        *prediction_fields, *residual_fields,
    }
    outer, _ = core.fold_maps(fold_plan)
    seen: set[tuple[str, str, str, str]] = set(); count = 0
    with core.open_plain_binary(BUNDLE_DIR / "oof_predictions.jsonl") as handle:
        for index, raw in enumerate(handle):
            if raw[-1:] != b"\n" or raw.endswith(b"\r\n"):
                raise core.AnalysisError(f"OOF line {index+1}: canonical LF required")
            row = core.strict_json_loads(raw, f"OOF line {index+1}")
            if not isinstance(row, dict) or set(row) != expected_fields:
                raise core.AnalysisError(f"OOF line {index+1}: exact schema differs")
            key = core.normalize_semantic_key(row["generation_model"], row["domain"], row["id"])
            pair_key = (*key, row["level"])
            if pair_key != dataset.pair_keys[index] or pair_key in seen:
                raise core.AnalysisError(f"OOF line {index+1}: key/order/uniqueness differs")
            expected_fold = outer[dataset.cluster_keys[int(dataset.cluster_index[index])]]
            if isinstance(row["outer_fold"], bool) or row["outer_fold"] != expected_fold:
                raise core.AnalysisError(f"OOF line {index+1}: outer fold differs")
            for label, array in all_predictions.items():
                value = core.finite_float(row[f"prediction|{label}"], f"OOF {label}")
                if value != float(array[index]):
                    raise core.AnalysisError(f"OOF line {index+1}: prediction differs for {label}")
            for label, array in residuals.items():
                value = core.finite_float(row[f"residual|{label}"], f"OOF residual {label}")
                if value != float(array[index]):
                    raise core.AnalysisError(f"OOF line {index+1}: residual differs for {label}")
            seen.add(pair_key); count += 1
    if count != dataset.n or len(seen) != dataset.n:
        raise core.AnalysisError("OOF stream row coverage differs")
    return {"rows": count, "unique_keys": len(seen), "all_rows_exact": True}


def _write_model_fits(fits: Sequence[Mapping[str, Any]]) -> None:
    output = BUNDLE_DIR / "model_fits.jsonl"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.{os.getpid()}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            for record in sorted(fits, key=lambda r: (str(r.get("model_label")), int(r.get("outer_fold", -1)))):
                handle.write(core.canonical_json_bytes(record, newline=True))
            handle.flush(); os.fsync(handle.fileno())
        _commit_stream_create_or_identical(temporary, output)
    finally:
        if core.path_lexists(temporary):
            if core.is_reparse_or_link(temporary): raise core.AnalysisError(f"temporary path replaced by link/reparse: {temporary}")
            temporary.unlink()


def _hgb_available() -> bool:
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: F401
    except ImportError:
        return False
    return True


def _expected_prediction_keys(*, include_hgb: bool) -> list[str]:
    keys = [
        _prediction_key("ridge", target, predictor)
        for target in core.WHITEBOX_TARGETS for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET)
    ]
    if include_hgb:
        keys.extend(
            _prediction_key("hgb", target, predictor)
            for target in core.WHITEBOX_TARGETS for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET)
        )
    return sorted(keys)


def _expected_length_prediction_keys() -> list[str]:
    return sorted(
        f"length_ridge|{spec}|{target}"
        for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS
    )


def _expected_checkpoint_paths(*, include_hgb: bool) -> tuple[set[str], set[str]]:
    labels = [*_expected_prediction_keys(include_hgb=include_hgb), *_expected_length_prediction_keys()]
    model_paths = {
        f"checkpoints/oof/model_{hashlib.sha256(label.encode('utf-8')).hexdigest()[:24]}_outer_{fold}.npz"
        for label in labels for fold in range(5)
    }
    aggregate_paths = {f"checkpoints/oof/outer_{fold}.npz" for fold in range(5)}
    bootstrap_paths = {
        f"checkpoints/bootstrap/block_{start:04d}_{min(core.BOOTSTRAP_REPLICATES, start + core.BOOTSTRAP_BLOCK_SIZE):04d}.npz"
        for start in range(0, core.BOOTSTRAP_REPLICATES, core.BOOTSTRAP_BLOCK_SIZE)
    }
    return model_paths | aggregate_paths, bootstrap_paths


def _load_model_fits(*, hgb_available: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    previous: tuple[str, int] | None = None
    with core.open_plain_binary(BUNDLE_DIR / "model_fits.jsonl") as handle:
        for line_number, raw in enumerate(handle, 1):
            if raw[-1:] != b"\n" or raw.endswith(b"\r\n"):
                raise core.AnalysisError(f"model_fits line {line_number}: canonical LF required")
            record = core.strict_json_loads(raw, f"model_fits line {line_number}")
            if not isinstance(record, dict):
                raise core.AnalysisError("model-fit row must be an object")
            learner = record.get("learner")
            if learner == "Ridge":
                expected_fields = {
                    "model_label", "learner", "outer_fold", "feature_names", "selected_alpha",
                    "inner_scores", "scaler_mean", "scaler_scale", "coefficients_standardized",
                    "intercept", "train_rows", "test_rows", "train_cluster_count",
                    "test_cluster_count", "train_cluster_sha256", "test_cluster_sha256",
                    "test_r2_auxiliary", "test_mae_auxiliary",
                }
            elif learner == "HistGradientBoostingRegressor" and record.get("status") == "skipped_unavailable":
                expected_fields = {"model_label", "learner", "status"}
            elif learner == "HistGradientBoostingRegressor":
                expected_fields = {
                    "model_label", "learner", "outer_fold", "parameters", "train_rows",
                    "test_rows", "train_cluster_count", "test_cluster_count",
                    "train_cluster_sha256", "test_cluster_sha256", "test_r2_auxiliary",
                    "test_mae_auxiliary",
                }
            else:
                raise core.AnalysisError("unknown model-fit learner")
            if set(record) != expected_fields:
                raise core.AnalysisError(f"model-fit exact schema differs at line {line_number}")
            order = (str(record["model_label"]), int(record.get("outer_fold", -1)))
            if previous is not None and order <= previous:
                raise core.AnalysisError("model-fit ledger order/uniqueness differs")
            previous = order; records.append(record)
    ridge_labels = sorted([
        *_expected_prediction_keys(include_hgb=False), *_expected_length_prediction_keys(),
    ])
    expected_pairs = {(label, fold) for label in ridge_labels for fold in range(5)}
    if hgb_available:
        expected_pairs |= {
            (label, fold)
            for label in _expected_prediction_keys(include_hgb=True)
            if label.startswith("hgb|") for fold in range(5)
        }
        if any(record.get("status") == "skipped_unavailable" for record in records):
            raise core.AnalysisError("HGB skip record present although import is available")
    else:
        expected_skip = {
            label for label in _expected_prediction_keys(include_hgb=True) if label.startswith("hgb|")
        }
        actual_skip = {record["model_label"] for record in records if record.get("status") == "skipped_unavailable"}
        if actual_skip != expected_skip:
            raise core.AnalysisError("HGB skip inventory differs")
    actual_pairs = {
        (record["model_label"], int(record["outer_fold"]))
        for record in records if "outer_fold" in record
    }
    if actual_pairs != expected_pairs:
        raise core.AnalysisError(
            f"model-fit inventory differs; missing={len(expected_pairs-actual_pairs)}, unknown={len(actual_pairs-expected_pairs)}"
        )
    return records


def _direct_points(dataset: core.Dataset) -> dict[str, Any]:
    references = {
        "treatment_ordinal": dataset.values["treatment_ordinal"],
        "phi_actual_llama": dataset.values["phi_actual_llama"],
        "phi_actual_mixtral": dataset.values["phi_actual_mixtral"],
        "consensus_midrank_percentile": dataset.values["consensus_midrank_percentile"],
        "consensus_global_z": dataset.values["consensus_global_z"],
    }
    output: dict[str, Any] = {}
    for candidate in core.DIRECT_CANDIDATES:
        vector = dataset.values[candidate]
        candidate_result: dict[str, Any] = {}
        for label, reference in references.items():
            candidate_result[label] = (
                core.treatment_scopes(vector, dataset)
                if label == "treatment_ordinal"
                else core.agreement_scopes(vector, reference, dataset)
            )
        candidate_result[core.JOINT_ALPHA] = core.joint_reference_scopes(
            vector, references["phi_actual_llama"], references["phi_actual_mixtral"], dataset
        )
        output[candidate] = candidate_result
    return output


def _prediction_points(dataset: core.Dataset, predictions: Mapping[str, np.ndarray]) -> dict[str, Any]:
    include_hgb = _hgb_available()
    if sorted(predictions) != _expected_prediction_keys(include_hgb=include_hgb):
        raise core.AnalysisError("predictive OOF inventory differs before point statistics")
    output: dict[str, Any] = {}
    for key, prediction in sorted(predictions.items()):
        learner, target, predictor = key.split("|", 2)
        if learner not in {"ridge", "hgb"} or target not in core.WHITEBOX_TARGETS or predictor not in {*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET}:
            raise core.AnalysisError(f"invalid predictive OOF key: {key}")
        reference = dataset.values[target]
        output[key] = {
            "agreement": core.agreement_scopes(prediction, reference, dataset),
            "auxiliary": {
                "r2": float(1.0 - np.square(reference - prediction).sum() / np.square(reference - reference.mean()).sum()),
                "mae": float(np.abs(reference - prediction).mean()),
            },
        }
    return output


def _length_points(dataset: core.Dataset, residuals: Mapping[str, np.ndarray]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for spec in core.LENGTH_SPECS:
        result: dict[str, Any] = {}
        for evaluator in core.WHITEBOX_TARGETS:
            evaluator_residual = residuals[f"{spec}|{evaluator}"]
            for candidate in ("R_actual", "G_raw_bits", "G_raw_bits_per_output_byte"):
                key = f"{candidate}_vs_{evaluator}"
                result[key] = core.agreement_scopes(
                    residuals[f"{spec}|{candidate}"], evaluator_residual, dataset
                )
        result["residual_candidate_vs_raw_treatment_ordinal"] = core.treatment_scopes(
            residuals[f"{spec}|R_actual"], dataset
        )
        output[spec] = result
    return output


def _point_metrics(dataset: core.Dataset, predictions: Mapping[str, np.ndarray], residuals: Mapping[str, np.ndarray]) -> dict[str, Any]:
    evaluator_agreement = core.agreement_scopes(
        dataset.values["phi_actual_llama"], dataset.values["phi_actual_mixtral"], dataset
    )
    return {
        "schema": "actual_incremental_sensitivity.metrics",
        "schema_version": 1, "estimand": "aggregate R_actual on real pairs only",
        "coverage": {"pairs": dataset.n, "items": dataset.item_count, "source_clusters": len(dataset.cluster_keys)},
        "metric_namespaces": {"rho": "Spearman average midranks", "alpha": core.PAIRWISE_ALPHA, "joint": core.JOINT_ALPHA},
        "direct": _direct_points(dataset),
        "incremental_validity": _prediction_points(dataset, predictions),
        "evaluator_sensitivity": {
            "llama_vs_mixtral": evaluator_agreement,
            "ordering": core.evaluator_ordering(dataset),
        },
        "length_residualized": _length_points(dataset, residuals),
        "common_support": core.common_support(dataset),
        "treatment_terminology": "investigator-specified ordinal treatment labels",
        "scientific_limits": [
            "agreement and predictive convergence do not establish criterion truth",
            "treatment levels are designed ordinal treatments, not independent human annotations",
            "cross-fitted predictive CIs are conditional on frozen OOF predictions",
            "residual_candidate_vs_raw_treatment_ordinal is one-sided nuisance residualization, not a two-sided partial correlation",
            "no counterfactual-derived quantity is analyzed",
        ],
    }


def _scope_metrics(
    x: np.ndarray, y: np.ndarray, indices: np.ndarray, levels: np.ndarray,
    x_centered: np.ndarray, y_centered: np.ndarray, scope: str,
) -> dict[str, float]:
    metrics = ("rho", core.PAIRWISE_ALPHA)
    if scope == "item_centered":
        cell = core.paired_agreement(x_centered[indices], y_centered[indices])
        return {metric: float(cell[metric]) if cell[metric] is not None else math.nan for metric in metrics}
    if scope == "macro_within_level":
        values: dict[str, list[float]] = {metric: [] for metric in metrics}
        sampled_levels = levels[indices]
        for level in core.LEVELS:
            sub = indices[sampled_levels == level]
            cell = core.paired_agreement(x[sub], y[sub])
            for metric in metrics:
                values[metric].append(float(cell[metric]) if cell[metric] is not None else math.nan)
        return {metric: float(np.mean(series)) if np.isfinite(series).all() else math.nan for metric, series in values.items()}
    if scope == "pooled":
        cell = core.paired_agreement(x[indices], y[indices])
        return {metric: float(cell[metric]) if cell[metric] is not None else math.nan for metric in metrics}
    raise core.AnalysisError(f"unknown bootstrap scope: {scope}")


def _bootstrap_specifications(
    dataset: core.Dataset, predictions: Mapping[str, np.ndarray], residuals: Mapping[str, np.ndarray],
    selections: Mapping[str, Any], support: Mapping[str, Any],
) -> tuple[
    list[str],
    Callable[[np.ndarray, np.ndarray], np.ndarray],
    Callable[[np.ndarray, np.ndarray], np.ndarray],
]:
    # Each descriptor is computed as a direct paired difference inside each draw.
    descriptors: list[tuple[str, np.ndarray, np.ndarray, np.ndarray, str, str]] = []
    references = {
        "llama": dataset.values["phi_actual_llama"],
        "mixtral": dataset.values["phi_actual_mixtral"],
        "consensus_rank": dataset.values["consensus_midrank_percentile"],
        "consensus_z": dataset.values["consensus_global_z"],
        "treatment": dataset.values["treatment_ordinal"],
    }
    baselines = (
        "G_raw_bits", "G_raw_bits_per_output_byte", "prompt_to_output_byte_ratio",
        "rouge_l_recall", selections["strongest_word_overlap"]["selected"],
        selections["strongest_char_overlap"]["selected"],
    )
    for baseline in dict.fromkeys(baselines):
        for reference_name, reference in references.items():
            scopes = (
                ("pooled", "item_centered")
                if reference_name == "treatment"
                else ("macro_within_level", "item_centered")
            )
            for scope in scopes:
                for metric in ("rho", core.PAIRWISE_ALPHA):
                    key = f"direct_delta|R_actual-minus-{baseline}|{reference_name}|{scope}|{metric}"
                    descriptors.append((key, dataset.values["R_actual"], dataset.values[baseline], reference, scope, metric))
    for learner in ("ridge", "hgb"):
        for target in core.WHITEBOX_TARGETS:
            pairs = (
                ("H+R", "H"), ("H", "L"), ("H", "O"),
                ("R-only", "G-only"), ("R-only", core.AUXILIARY_PREDICTOR_SET),
            )
            for left_set, right_set in pairs:
                left_key = _prediction_key(learner, target, left_set)
                right_key = _prediction_key(learner, target, right_set)
                if left_key not in predictions or right_key not in predictions:
                    continue
                for scope in ("macro_within_level", "item_centered"):
                    for metric in ("rho", core.PAIRWISE_ALPHA):
                        key = f"incremental_delta|{learner}|{target}|{left_set}-minus-{right_set}|{scope}|{metric}"
                        descriptors.append((key, predictions[left_key], predictions[right_key], dataset.values[target], scope, metric))
    for spec in core.LENGTH_SPECS:
        for target in core.WHITEBOX_TARGETS:
            reference = residuals[f"{spec}|{target}"]
            for baseline in ("G_raw_bits", "G_raw_bits_per_output_byte"):
                for scope in ("macro_within_level", "item_centered"):
                    for metric in ("rho", core.PAIRWISE_ALPHA):
                        key = f"length_delta|{spec}|{target}|R_actual-minus-{baseline}|{scope}|{metric}"
                        descriptors.append((key, residuals[f"{spec}|R_actual"], residuals[f"{spec}|{baseline}"], reference, scope, metric))
    keys = [entry[0] for entry in descriptors]
    centered_cache: dict[int, np.ndarray] = {}
    for _, left, right, reference, _, _ in descriptors:
        for vector in (left, right, reference):
            if id(vector) not in centered_cache:
                centered_cache[id(vector)] = core.center_within_items(vector)

    # One canonical ordered sequence drives support keys, values, and effective N.
    # Per caliper: 80 adjacent-pair summaries followed by 16 treatment agreements.
    support_descriptors: list[dict[str, Any]] = []
    output_bytes = dataset.values["output_bytes"].reshape(-1, 5)
    item_cluster = dataset.cluster_index[::5]
    method_fields = (("R", "R_actual"), ("G", "G_raw_bits"),
                     ("Llama", "phi_actual_llama"), ("Mixtral", "phi_actual_mixtral"))
    for caliper in (1.10, 1.20, 1.30):
        caliper_candidates: dict[str, list[np.ndarray]] = {label: [] for label, _ in method_fields}
        caliper_labels: list[np.ndarray] = []
        caliper_clusters: list[np.ndarray] = []
        for high, low in core.ADJACENT_LEVEL_PAIRS:
            i = core.LEVELS.index(high); j = core.LEVELS.index(low)
            mask = np.maximum(output_bytes[:, i], output_bytes[:, j]) / np.minimum(output_bytes[:, i], output_bytes[:, j]) <= caliper
            retained = np.flatnonzero(mask)
            caliper_labels.append(np.tile(
                np.asarray([core.LEVEL_VALUE[high], core.LEVEL_VALUE[low]], dtype=np.float64),
                (len(retained), 1),
            ))
            caliper_clusters.append(item_cluster[retained])
            for label, field in method_fields:
                matrix = dataset.values[field].reshape(-1, 5)
                difference = matrix[:, i] - matrix[:, j]
                caliper_candidates[label].append(matrix[retained][:, [i, j]])
                for statistic in ("mean", "median", "expected_rate", "reverse_rate", "tie_rate"):
                    support_descriptors.append({
                        "kind": "summary",
                        "key": f"support|{caliper:.2f}|{high}-{low}|{label}|{statistic}",
                        "difference": difference,
                        "mask": mask,
                        "statistic": statistic,
                    })
        labels_matrix = np.concatenate(caliper_labels, axis=0)
        cluster_vector = np.concatenate(caliper_clusters)
        for label, _ in method_fields:
            candidate_matrix = np.concatenate(caliper_candidates[label], axis=0)
            for scope in ("pooled", "adjacent_pair_centered"):
                for metric in ("rho", core.PAIRWISE_ALPHA):
                    support_descriptors.append({
                        "kind": "agreement",
                        "key": f"support_treatment|{caliper:.2f}|{label}|{scope}|{metric}",
                        "candidate_matrix": candidate_matrix,
                        "labels_matrix": labels_matrix,
                        "cluster_vector": cluster_vector,
                        "scope": scope,
                        "metric": metric,
                    })
    if (
        len(support_descriptors) != 288
        or sum(entry["kind"] == "summary" for entry in support_descriptors) != 240
        or sum(entry["kind"] == "agreement" for entry in support_descriptors) != 48
    ):
        raise core.AnalysisError("common-support bootstrap descriptor inventory differs")
    keys.extend(str(entry["key"]) for entry in support_descriptors)
    if len(set(keys)) != len(keys):
        raise core.AnalysisError("bootstrap metric keys are not unique")

    def calculate(indices: np.ndarray, cluster_multiplicity: np.ndarray) -> np.ndarray:
        result = np.full(len(keys), np.nan, dtype=np.float64)
        agreement_cache: dict[tuple[int, int, str], dict[str, float]] = {}
        def cached_score(vector: np.ndarray, reference: np.ndarray, scope: str, metric: str) -> float:
            cache_key = (id(vector), id(reference), scope)
            if cache_key not in agreement_cache:
                agreement_cache[cache_key] = _scope_metrics(
                    vector, reference, indices, dataset.levels,
                    centered_cache[id(vector)], centered_cache[id(reference)], scope,
                )
            return agreement_cache[cache_key][metric]
        for position, (_, left, right, reference, scope, metric) in enumerate(descriptors):
            result[position] = (
                cached_score(left, reference, scope, metric)
                - cached_score(right, reference, scope, metric)
            )
        offset = len(descriptors)
        item_weights = cluster_multiplicity[item_cluster]
        for local, support_descriptor in enumerate(support_descriptors):
            position = offset + local
            if support_descriptor["kind"] == "summary":
                difference = support_descriptor["difference"]
                mask = support_descriptor["mask"]
                weights = item_weights * mask.astype(np.int64)
                total = int(weights.sum())
                if total == 0:
                    continue
                statistic = support_descriptor["statistic"]
                if statistic == "mean":
                    value = float(np.dot(weights, difference) / total)
                elif statistic == "median":
                    median = core.weighted_median(difference, weights)
                    value = math.nan if median is None else median
                elif statistic == "expected_rate":
                    value = float(np.dot(weights, difference > 0) / total)
                elif statistic == "reverse_rate":
                    value = float(np.dot(weights, difference < 0) / total)
                else:
                    value = float(np.dot(weights, difference == 0) / total)
                result[position] = value
                continue
            candidate_matrix = support_descriptor["candidate_matrix"]
            labels_matrix = support_descriptor["labels_matrix"]
            cluster_vector = support_descriptor["cluster_vector"]
            weights = cluster_multiplicity[cluster_vector]
            repeated = np.repeat(np.arange(len(weights), dtype=np.int64), weights)
            if len(repeated) == 0:
                continue
            candidate = candidate_matrix[repeated]
            labels = labels_matrix[repeated]
            if support_descriptor["scope"] == "adjacent_pair_centered":
                candidate = candidate - candidate.mean(axis=1, keepdims=True)
                labels = labels - labels.mean(axis=1, keepdims=True)
            cell = core.paired_agreement(candidate.reshape(-1), labels.reshape(-1))
            value = cell[support_descriptor["metric"]]
            result[position] = math.nan if value is None else float(value)
        return result

    def effective_counts(indices: np.ndarray, cluster_multiplicity: np.ndarray) -> np.ndarray:
        result = np.zeros(len(keys), dtype=np.int32)
        for position, descriptor in enumerate(descriptors):
            scope = descriptor[4]
            result[position] = int(len(indices) // 5 if scope == "macro_within_level" else len(indices))
        offset = len(descriptors)
        item_weights = cluster_multiplicity[item_cluster]
        for local, support_descriptor in enumerate(support_descriptors):
            position = offset + local
            if support_descriptor["kind"] == "summary":
                result[position] = int(np.sum(
                    item_weights * support_descriptor["mask"].astype(np.int64)
                ))
            else:
                result[position] = int(2 * np.sum(
                    cluster_multiplicity[support_descriptor["cluster_vector"]]
                ))
        return result

    return keys, calculate, effective_counts


def _bootstrap_points(
    keys: Sequence[str], calculator: Callable[[np.ndarray, np.ndarray], np.ndarray],
    effective_calculator: Callable[[np.ndarray, np.ndarray], np.ndarray],
    dataset: core.Dataset,
) -> tuple[np.ndarray, np.ndarray]:
    identity = np.arange(len(dataset.cluster_keys), dtype=np.int32)
    indices = core.bootstrap_cluster_indices(dataset, identity)
    multiplicity = np.ones(len(dataset.cluster_keys), dtype=np.int32)
    return calculator(indices, multiplicity), effective_calculator(indices, multiplicity)


def _run_bootstrap(
    dataset: core.Dataset, predictions: Mapping[str, np.ndarray], residuals: Mapping[str, np.ndarray],
    selections: Mapping[str, Any], support: Mapping[str, Any], config_sha: str,
    monitor: core.ResourceMonitor,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    keys, calculator, effective_calculator = _bootstrap_specifications(
        dataset, predictions, residuals, selections, support
    )
    keys_sha = core.sha256_bytes(core.canonical_json_bytes(keys))
    point, point_effective = _bootstrap_points(
        keys, calculator, effective_calculator, dataset
    )
    block_records: list[dict[str, Any]] = []
    all_values: list[np.ndarray] = []
    all_effective: list[np.ndarray] = []
    draw_digest = hashlib.sha256()
    monitor.set_phase("paired_cluster_bootstrap")
    for block_start in range(0, core.BOOTSTRAP_REPLICATES, core.BOOTSTRAP_BLOCK_SIZE):
        block_end = min(core.BOOTSTRAP_REPLICATES, block_start + core.BOOTSTRAP_BLOCK_SIZE)
        path = BUNDLE_DIR / "checkpoints" / "bootstrap" / f"block_{block_start:04d}_{block_end:04d}.npz"
        block_draws: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        for replicate in range(block_start, block_end):
            draw = core.bootstrap_draw(replicate)
            draw_digest.update(draw.tobytes())
            multiplicity = np.bincount(draw, minlength=len(dataset.cluster_keys)).astype(np.int32)
            indices = core.bootstrap_cluster_indices(dataset, draw)
            block_draws.append((draw, multiplicity, indices))
        if path.exists():
            with core.open_plain_binary(path) as checkpoint_handle:
                with np.load(checkpoint_handle, allow_pickle=False) as stored:
                    if set(stored.files) != {"values", "effective", "keys", "metadata_json"}:
                        raise core.AnalysisError(f"bootstrap checkpoint inventory differs: {path}")
                    arrays = {name: np.asarray(stored[name]) for name in ("values", "effective", "keys")}
                    metadata = core.strict_json_loads(str(stored["metadata_json"].item()), f"{path}.metadata")
            values = np.asarray(arrays["values"], dtype=np.float64)
            effective = np.asarray(arrays["effective"], dtype=np.int32)
            expected_metadata = {
                "schema": "actual_incremental_sensitivity.bootstrap_checkpoint",
                "schema_version": 1, "config_sha256": config_sha,
                "metric_key_sha256": keys_sha, "replicate_start_inclusive": block_start,
                "replicate_end_exclusive": block_end,
                "arrays": core.checkpoint_array_descriptor(arrays),
                "payload_sha256": core.checkpoint_payload_sha256(arrays),
            }
            if metadata != expected_metadata or arrays["keys"].tolist() != keys:
                raise core.AnalysisError(f"bootstrap checkpoint binding differs: {path}")
            core.validate_deterministic_npz_file(path, arrays, metadata)
            if (
                arrays["values"].dtype != np.dtype("float64")
                or arrays["effective"].dtype != np.dtype("int32")
                or arrays["keys"].dtype.kind != "U"
                or values.shape != (block_end - block_start, len(keys))
                or effective.shape != values.shape
                or arrays["keys"].shape != (len(keys),)
            ):
                raise core.AnalysisError(f"bootstrap checkpoint dtype/shape differs: {path}")
        else:
            values = np.full((block_end - block_start, len(keys)), np.nan, dtype=np.float64)
            effective = np.zeros((block_end - block_start, len(keys)), dtype=np.int32)
            for local, (_, multiplicity, indices) in enumerate(block_draws):
                values[local] = calculator(indices, multiplicity)
                effective[local] = effective_calculator(indices, multiplicity)
                monitor.check()
            arrays = {"values": values, "effective": effective, "keys": np.asarray(keys)}
            metadata = {
                "schema": "actual_incremental_sensitivity.bootstrap_checkpoint",
                "schema_version": 1, "config_sha256": config_sha,
                "metric_key_sha256": keys_sha, "replicate_start_inclusive": block_start,
                "replicate_end_exclusive": block_end,
                "arrays": core.checkpoint_array_descriptor(arrays),
                "payload_sha256": core.checkpoint_payload_sha256(arrays),
            }
            core.write_npz_atomic(path, arrays, metadata)
        block_records.append(core.file_record(path, BUNDLE_DIR)); all_values.append(values); all_effective.append(effective)
        print(f"bootstrap {block_end}/{core.BOOTSTRAP_REPLICATES}", flush=True)
    if draw_digest.hexdigest() != core.EXPECTED_DRAW_SHA256:
        raise core.AnalysisError("completed bootstrap draw SHA-256 differs")
    matrix = np.concatenate(all_values, axis=0)
    effective_matrix = np.concatenate(all_effective, axis=0)
    summaries: dict[str, Any] = {}
    for index, key in enumerate(keys):
        cell = core.percentile_summary(
            matrix[:, index], float(point[index]) if np.isfinite(point[index]) else None
        )
        finite_mask = np.isfinite(matrix[:, index])
        finite_effective = effective_matrix[:, index][finite_mask]
        cell.update({
            "point_effective_n": int(point_effective[index]),
            "resample_effective_n_all_min": int(effective_matrix[:, index].min()),
            "resample_effective_n_all_max": int(effective_matrix[:, index].max()),
            "resample_effective_n_finite_min": int(finite_effective.min()) if len(finite_effective) else None,
            "resample_effective_n_finite_max": int(finite_effective.max()) if len(finite_effective) else None,
        })
        summaries[key] = cell
    summary = {
        "schema": "actual_incremental_sensitivity.bootstrap_summary",
        "schema_version": 1, "method": "paired source-cluster empirical percentile bootstrap",
        "replicates": core.BOOTSTRAP_REPLICATES, "seed": core.BOOTSTRAP_SEED,
        "cluster_count": len(dataset.cluster_keys), "block_size": core.BOOTSTRAP_BLOCK_SIZE,
        "draw_sequence_sha256": draw_digest.hexdigest(), "metric_key_sha256": keys_sha,
        "metric_keys": keys,
        "conditional_on_frozen_cross_fitted_predictions": True,
        "metrics": summaries,
    }
    return summary, block_records


def _load_oof_from_memory_guard(predictions: Mapping[str, np.ndarray], residuals: Mapping[str, np.ndarray], dataset: core.Dataset) -> None:
    expected = len(predictions) + len(residuals)
    if expected == 0:
        raise core.AnalysisError("no OOF outputs")
    if any(len(values) != dataset.n or not np.isfinite(values).all() for values in [*predictions.values(), *residuals.values()]):
        raise core.AnalysisError("OOF uniqueness/finite guard failed")


def _format_number(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.6f}"
    return str(value)


def _ci_text(cell: Mapping[str, Any]) -> str:
    ci = cell.get("ci_95_percentile", {})
    return f"[{_format_number(ci.get('lower'))}, {_format_number(ci.get('upper'))}]"


def _primary_cell(metrics: Mapping[str, Any], candidate: str, reference: str, scope: str) -> Mapping[str, Any]:
    return metrics["direct"][candidate][reference][scope]


def _render_table1(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any], selections: Mapping[str, Any]) -> str:
    candidates = [
        "R_actual", "G_raw_bits", "G_raw_bits_per_output_byte", "C_y_bits",
        "prompt_to_output_byte_ratio", "rouge_l_recall",
        selections["strongest_word_overlap"]["selected"],
        selections["strongest_char_overlap"]["selected"],
    ]
    lines = [
        "# Table 1. Normalized R_actual versus raw gain and frozen simple heuristics",
        "", "All cells pair Spearman rho with `pairwise_continuous_alpha_z`.", "",
        "| Candidate | Llama macro rho / alpha_z | Mixtral macro rho / alpha_z | Llama item-centered rho / alpha_z | Mixtral item-centered rho / alpha_z |",
        "|---|---:|---:|---:|---:|",
    ]
    for candidate in dict.fromkeys(candidates):
        cells = []
        for reference, scope in (("phi_actual_llama", "macro_within_level"), ("phi_actual_mixtral", "macro_within_level"), ("phi_actual_llama", "item_centered"), ("phi_actual_mixtral", "item_centered")):
            cell = _primary_cell(metrics, candidate, reference, scope)
            cells.append(f"{_format_number(cell['rho'])} / {_format_number(cell[core.PAIRWISE_ALPHA])}")
        lines.append(f"| {candidate} | " + " | ".join(cells) + " |")
    lines.extend(["", "## Direct paired R-minus-baseline bootstrap contrasts", "",
                  "| Contrast | Reference | Scope | Metric | Point | 95% paired cluster-bootstrap CI |",
                  "|---|---|---|---|---:|---:|"])
    for key, cell in sorted(bootstrap["metrics"].items()):
        if not key.startswith("direct_delta|"):
            continue
        _, contrast, reference, scope, metric = key.split("|")
        lines.append(f"| {contrast} | {reference} | {scope} | {metric} | {_format_number(cell['point'])} | {_ci_text(cell)} |")
    return "\n".join(lines) + "\n"


def _render_table2(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any]) -> str:
    lines = [
        "# Table 2. Cross-fitted incremental validity", "",
        "Primary rows use source-grouped nested-CV OOF predictions. All agreement cells pair rho with `pairwise_continuous_alpha_z`.", "",
        "| Learner | Target | Predictor set | Status | Macro rho / alpha_z | Item-centered rho / alpha_z | OOF R2 / MAE (auxiliary) |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for key, record in sorted(metrics["incremental_validity"].items()):
        learner, target, predictor = key.split("|", 2)
        macro = record["agreement"]["macro_within_level"]
        centered = record["agreement"]["item_centered"]
        aux = record["auxiliary"]
        status = "auxiliary frozen strongest-single" if predictor == core.AUXILIARY_PREDICTOR_SET else "primary"
        lines.append(
            f"| {learner} | {target} | {predictor} | {status} | {_format_number(macro['rho'])} / {_format_number(macro[core.PAIRWISE_ALPHA])} | "
            f"{_format_number(centered['rho'])} / {_format_number(centered[core.PAIRWISE_ALPHA])} | {_format_number(aux['r2'])} / {_format_number(aux['mae'])} |"
        )
    lines.extend(["", "## Direct paired OOF contrasts", "",
                  "| Contrast ID | Point | 95% paired cluster-bootstrap CI |",
                  "|---|---:|---:|"])
    for key, cell in sorted(bootstrap["metrics"].items()):
        if key.startswith("incremental_delta|"):
            lines.append(f"| {key} | {_format_number(cell['point'])} | {_ci_text(cell)} |")
    return "\n".join(lines) + "\n"


def _render_table3(metrics: Mapping[str, Any]) -> str:
    agreement = metrics["evaluator_sensitivity"]["llama_vs_mixtral"]
    ordering = metrics["evaluator_sensitivity"]["ordering"]
    lines = [
        "# Table 3. White-box evaluator sensitivity and consensus", "",
        "| Scope | Spearman rho | pairwise_continuous_alpha_z | N |",
        "|---|---:|---:|---:|",
    ]
    for scope in ("pooled", "macro_within_level", "item_centered"):
        cell = agreement[scope]
        lines.append(f"| {scope} | {_format_number(cell['rho'])} | {_format_number(cell[core.PAIRWISE_ALPHA])} | {_format_number(cell['n'])} |")
    for level, cell in agreement["per_level"].items():
        lines.append(f"| level:{level} | {_format_number(cell['rho'])} | {_format_number(cell[core.PAIRWISE_ALPHA])} | {_format_number(cell['n'])} |")
    for family in ("by_domain", "by_generation_model"):
        for label, cell in agreement[family].items():
            lines.append(f"| {family}:{label} | {_format_number(cell['rho'])} | {_format_number(cell[core.PAIRWISE_ALPHA])} | {_format_number(cell['n'])} |")
    lines.extend(["", "## Exact evaluator ordering", "",
                  "| Pair | Concordant | Discordant | Tied either | Inversion rate (all / non-tie) | R same-sign on concordant non-ties |",
                  "|---|---:|---:|---:|---:|---:|"])
    for family_key in ("all_ten", "adjacent_four"):
        for pair, cell in ordering[family_key].items():
            r = cell["R_on_evaluator_concordant_non_tied"]
            lines.append(f"| {family_key}:{pair} | {cell['concordant']:,} | {cell['discordant']:,} | {cell['tied_either_evaluator']:,} | {_format_number(cell['inversion_rate_all'])} / {_format_number(cell['inversion_rate_non_tie'])} | {_format_number(r['same_sign_rate'])} |")
    strict = ordering["strict_monotonicity"]
    lines.extend([
        "", "## Strict L1>L2>L3>L4>L5 monotonicity", "",
        "| Evaluator condition | Strictly monotonic items | Denominator | Rate |",
        "|---|---:|---:|---:|",
        f"| Llama | {strict['llama_items']:,} | {strict['denominator_items']:,} | {_format_number(strict['llama_items']/strict['denominator_items'])} |",
        f"| Mixtral | {strict['mixtral_items']:,} | {strict['denominator_items']:,} | {_format_number(strict['mixtral_items']/strict['denominator_items'])} |",
        f"| Both | {strict['both_items']:,} | {strict['denominator_items']:,} | {_format_number(strict['both_items']/strict['denominator_items'])} |",
    ])
    difference = ordering["absolute_global_z_difference"]
    quantiles = difference["quantiles_linear"]
    lines.extend([
        "", "## Standardized evaluator disagreement", "",
        f"Global-z absolute difference: mean={_format_number(difference['mean'])}; sample SD={_format_number(difference['sd_ddof1'])}. All subgroups reuse the one global z-standardization (`subgroups_use_global_z_not_restandardized={difference['subgroups_use_global_z_not_restandardized']}`).",
        "", "Quantiles (`method=linear`): " + ", ".join(f"q={key}: {_format_number(value)}" for key, value in quantiles.items()), "",
        "| Subgroup | Mean absolute global-z difference |", "|---|---:|",
    ])
    for level, value in difference["by_level"].items():
        lines.append(f"| level:{level} | {_format_number(value)} |")
    for domain, value in difference["by_domain"].items():
        lines.append(f"| domain:{domain} | {_format_number(value)} |")
    for model, value in difference["by_generation_model"].items():
        lines.append(f"| generation_model:{model} | {_format_number(value)} |")
    lines.extend(["", "## R_actual against the two frozen evaluator consensuses", "",
                  "| Consensus | Scope | rho | pairwise_continuous_alpha_z |",
                  "|---|---|---:|---:|"])
    for reference in ("consensus_midrank_percentile", "consensus_global_z"):
        for scope in ("macro_within_level", "item_centered"):
            cell = metrics["direct"]["R_actual"][reference][scope]
            lines.append(f"| {reference} | {scope} | {_format_number(cell['rho'])} | {_format_number(cell[core.PAIRWISE_ALPHA])} |")
    return "\n".join(lines) + "\n"


def _render_table4(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any]) -> str:
    lines = [
        "# Table 4. Cross-fitted length-residualized robustness", "",
        "Evaluator comparisons residualize candidate and evaluator independently using the same source-grouped folds. `residual_candidate_vs_raw_treatment_ordinal` instead compares residualized R to the unchanged designed ordinal labels, as frozen; it is not a two-sided partial correlation.", "",
        "| Length specification | Candidate vs evaluator | Macro rho / alpha_z | Item-centered rho / alpha_z |",
        "|---|---|---:|---:|",
    ]
    for spec, records in metrics["length_residualized"].items():
        if not spec.startswith("byte_"):
            continue
        for label, record in records.items():
            macro = record["macro_within_level"]; centered = record["item_centered"]
            lines.append(f"| {spec} | {label} | {_format_number(macro['rho'])} / {_format_number(macro[core.PAIRWISE_ALPHA])} | {_format_number(centered['rho'])} / {_format_number(centered[core.PAIRWISE_ALPHA])} |")
    lines.extend(["", "## Direct paired residual R-minus-raw-gain contrasts", "",
                  "| Contrast ID | Point | 95% paired cluster-bootstrap CI |", "|---|---:|---:|"])
    for key, cell in sorted(bootstrap["metrics"].items()):
        if key.startswith("length_delta|byte_"):
            lines.append(f"| {key} | {_format_number(cell['point'])} | {_ci_text(cell)} |")
    lines.extend(["", "## Persistence after length control", "", "| Length specification | Baseline | Classification | Relative to unadjusted |", "|---|---|---|---|"])
    for spec, baselines in metrics["outcome_neutral_classification"]["length_R_vs_baselines"].items():
        if not spec.startswith("byte_"):
            continue
        for baseline, result in baselines.items():
            lines.append(f"| {spec} | {baseline} | {result['classification']} | {result['relative_to_unadjusted']} |")
    return "\n".join(lines) + "\n"


def _render_table5(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any]) -> str:
    support = metrics["common_support"]
    lines = [
        "# Table 5. Common output-length support", "",
        "Inclusive adjacent-level output-byte calipers are nested by construction.", "",
        "| Caliper | Adjacent pair | Method | Retained item-pairs / clusters | Mean / median higher-minus-lower | Mean / median 95% CIs | Expected / reverse / tie rates | Expected / reverse / tie 95% CIs |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for caliper, pairs in support["adjacent_byte_calipers"].items():
        for pair, cell in pairs.items():
            for method, result in cell["methods"].items():
                mean_key = f"support|{caliper}|{pair}|{method}|mean"
                median_key = f"support|{caliper}|{pair}|{method}|median"
                expected_key = f"support|{caliper}|{pair}|{method}|expected_rate"
                reverse_key = f"support|{caliper}|{pair}|{method}|reverse_rate"
                tie_key = f"support|{caliper}|{pair}|{method}|tie_rate"
                lines.append(
                    f"| {caliper} | {pair} | {method} | {cell['retained_model_item_pairs']:,} / {cell['source_clusters']:,} | "
                    f"{_format_number(result['mean_higher_minus_lower'])} / {_format_number(result['median_higher_minus_lower'])} | "
                    f"{_ci_text(bootstrap['metrics'][mean_key])} / {_ci_text(bootstrap['metrics'][median_key])} | "
                    f"{_format_number(result['expected_rate'])} / {_format_number(result['reverse_rate'])} / {_format_number(result['tie_rate'])} | "
                    f"{_ci_text(bootstrap['metrics'][expected_key])} / {_ci_text(bootstrap['metrics'][reverse_key])} / {_ci_text(bootstrap['metrics'][tie_key])} |"
                )
    lines.extend(["", "## Retained adjacent-pair treatment concordance", "",
                  "| Caliper | Method | Scope | rho | pairwise_continuous_alpha_z | rho 95% CI | alpha_z 95% CI |",
                  "|---|---|---|---:|---:|---:|---:|"])
    for caliper, methods in support["adjacent_treatment_concordance"].items():
        for method, scopes in methods.items():
            for scope, cell in scopes.items():
                rho_key = f"support_treatment|{caliper}|{method}|{scope}|rho"
                alpha_key = f"support_treatment|{caliper}|{method}|{scope}|{core.PAIRWISE_ALPHA}"
                lines.append(
                    f"| {caliper} | {method} | {scope} | {_format_number(cell['rho'])} | {_format_number(cell[core.PAIRWISE_ALPHA])} | "
                    f"{_ci_text(bootstrap['metrics'][rho_key])} | {_ci_text(bootstrap['metrics'][alpha_key])} |"
                )
    all_five = support["all_five_byte_1.25"]
    lines.extend(["", f"All-five 1.25 support: {all_five['items']:,} items, {all_five['clusters']:,} clusters; policy = `{all_five['inference_policy']}`; low-support reasons = {all_five['low_support_reasons']}.", ""])
    if all_five["inference"] is not None:
        lines.extend([
            "## All-five 1.25 exploratory inference", "",
            "| Method | Scope | rho | pairwise_continuous_alpha_z | N |",
            "|---|---|---:|---:|---:|",
        ])
        for method, scopes in all_five["inference"].items():
            for scope, cell in scopes.items():
                lines.append(f"| {method} | {scope} | {_format_number(cell['rho'])} | {_format_number(cell[core.PAIRWISE_ALPHA])} | {_format_number(cell['n'])} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _flatten_metric_rows(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate, references in metrics["direct"].items():
        for reference, scopes in references.items():
            if reference == core.JOINT_ALPHA:
                for scope in ("pooled", "macro_within_level", "item_centered"):
                    cell = scopes[scope]
                    rows.append({"family": "direct_joint", "candidate": candidate, "reference": "llama+mixtral", "scope": scope, "metric": core.JOINT_ALPHA, "point": cell[core.JOINT_ALPHA], "ci_lower": None, "ci_upper": None, "n": cell["n"], "finite_resamples": None, "undefined_resamples": None, "undefined_reason": cell.get("undefined_reason")})
                for level, cell in scopes["per_level"].items():
                    rows.append({"family": "direct_joint", "candidate": candidate, "reference": "llama+mixtral", "scope": f"level:{level}", "metric": core.JOINT_ALPHA, "point": cell[core.JOINT_ALPHA], "ci_lower": None, "ci_upper": None, "n": cell["n"], "finite_resamples": None, "undefined_resamples": None, "undefined_reason": cell.get("undefined_reason")})
                for subgroup_family in ("by_domain", "by_generation_model"):
                    for subgroup, cell in scopes[subgroup_family].items():
                        rows.append({"family": "direct_joint", "candidate": candidate, "reference": "llama+mixtral", "scope": f"{subgroup_family}:{subgroup}", "metric": core.JOINT_ALPHA, "point": cell[core.JOINT_ALPHA], "ci_lower": None, "ci_upper": None, "n": cell["n"], "finite_resamples": None, "undefined_resamples": None, "undefined_reason": cell.get("undefined_reason")})
                continue
            for scope in ("pooled", "macro_within_level", "item_centered"):
                cell = scopes[scope]
                for metric_name in ("rho", core.PAIRWISE_ALPHA):
                    rows.append({"family": "direct", "candidate": candidate, "reference": reference, "scope": scope, "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
            for level, cell in scopes["per_level"].items():
                for metric_name in ("rho", core.PAIRWISE_ALPHA):
                    rows.append({"family": "direct", "candidate": candidate, "reference": reference, "scope": f"level:{level}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
            for subgroup_family in ("by_domain", "by_generation_model"):
                for subgroup, cell in scopes[subgroup_family].items():
                    for metric_name in ("rho", core.PAIRWISE_ALPHA):
                        rows.append({"family": "direct", "candidate": candidate, "reference": reference, "scope": f"{subgroup_family}:{subgroup}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
            if reference == "treatment_ordinal":
                ordinal = scopes["per_item_ordinal"]
                ordinal_metrics = (
                    "mean_per_item_spearman", "finite_spearman_items",
                    "mean_per_item_kendall_tau_b", "finite_tau_b_items",
                    "strict_monotonic_items", "strict_monotonic_rate",
                    "nonstrict_monotonic_items", "nonstrict_monotonic_rate",
                )
                for metric_name in ordinal_metrics:
                    rows.append({
                        "family": "treatment_per_item_ordinal", "candidate": candidate,
                        "reference": reference, "scope": "per_item_ordinal",
                        "metric": metric_name, "point": ordinal[metric_name],
                        "ci_lower": None, "ci_upper": None, "n": ordinal["items"],
                        "undefined_reason": None,
                    })
    for model_id, record in metrics["incremental_validity"].items():
        for scope in ("pooled", "macro_within_level", "item_centered"):
            cell = record["agreement"][scope]
            for metric_name in ("rho", core.PAIRWISE_ALPHA):
                rows.append({"family": "incremental_validity", "candidate": model_id, "reference": model_id.split("|")[1], "scope": scope, "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
        for level, cell in record["agreement"]["per_level"].items():
            for metric_name in ("rho", core.PAIRWISE_ALPHA):
                rows.append({"family": "incremental_validity", "candidate": model_id, "reference": model_id.split("|")[1], "scope": f"level:{level}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
        for subgroup_family in ("by_domain", "by_generation_model"):
            for subgroup, cell in record["agreement"][subgroup_family].items():
                for metric_name in ("rho", core.PAIRWISE_ALPHA):
                    rows.append({"family": "incremental_validity", "candidate": model_id, "reference": model_id.split("|")[1], "scope": f"{subgroup_family}:{subgroup}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
        for metric_name in ("r2", "mae"):
            rows.append({"family": "incremental_auxiliary", "candidate": model_id, "reference": model_id.split("|")[1], "scope": "pooled", "metric": metric_name, "point": record["auxiliary"][metric_name], "ci_lower": None, "ci_upper": None, "n": metrics["coverage"]["pairs"], "undefined_reason": None})
    evaluator = metrics["evaluator_sensitivity"]["llama_vs_mixtral"]
    for scope in ("pooled", "macro_within_level", "item_centered"):
        for metric_name in ("rho", core.PAIRWISE_ALPHA):
            cell = evaluator[scope]
            rows.append({"family": "evaluator_sensitivity", "candidate": "phi_actual_llama", "reference": "phi_actual_mixtral", "scope": scope, "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
    for level, cell in evaluator["per_level"].items():
        for metric_name in ("rho", core.PAIRWISE_ALPHA):
            rows.append({"family": "evaluator_sensitivity", "candidate": "phi_actual_llama", "reference": "phi_actual_mixtral", "scope": f"level:{level}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
    for subgroup_family in ("by_domain", "by_generation_model"):
        for subgroup, cell in evaluator[subgroup_family].items():
            for metric_name in ("rho", core.PAIRWISE_ALPHA):
                rows.append({"family": "evaluator_sensitivity", "candidate": "phi_actual_llama", "reference": "phi_actual_mixtral", "scope": f"{subgroup_family}:{subgroup}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
    for spec, comparisons in metrics["length_residualized"].items():
        for comparison, scopes in comparisons.items():
            for scope in ("pooled", "macro_within_level", "item_centered"):
                cell = scopes[scope]
                for metric_name in ("rho", core.PAIRWISE_ALPHA):
                    rows.append({"family": "length_residualized", "candidate": f"{spec}|{comparison}", "reference": None, "scope": scope, "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
    for caliper, methods in metrics["common_support"]["adjacent_treatment_concordance"].items():
        for method, scopes in methods.items():
            for scope, cell in scopes.items():
                for metric_name in ("rho", core.PAIRWISE_ALPHA):
                    rows.append({"family": "common_support_treatment", "candidate": method, "reference": "treatment_ordinal", "scope": f"{caliper}|{scope}", "metric": metric_name, "point": cell[metric_name], "ci_lower": None, "ci_upper": None, "n": cell["n"], "undefined_reason": cell.get("undefined_reason")})
    for key, cell in bootstrap["metrics"].items():
        ci = cell["ci_95_percentile"]
        rows.append({"family": "bootstrap_contrast", "candidate": key, "reference": None, "scope": None, "metric": "paired_difference", "point": cell["point"], "ci_lower": ci["lower"], "ci_upper": ci["upper"], "n": cell["point_effective_n"], "finite_resamples": cell["finite_resamples"], "undefined_resamples": cell["undefined_resamples"], "resample_effective_n_all_min": cell["resample_effective_n_all_min"], "resample_effective_n_all_max": cell["resample_effective_n_all_max"], "resample_effective_n_finite_min": cell["resample_effective_n_finite_min"], "resample_effective_n_finite_max": cell["resample_effective_n_finite_max"], "undefined_reason": cell.get("undefined_reason")})
    return rows


def _render_appendix_subgroups(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any]) -> str:
    lines = ["# Appendix: complete subgroup and secondary inventory", ""]
    for candidate, references in metrics["direct"].items():
        lines.extend([f"## {candidate}", ""])
        for reference, scopes in references.items():
            if reference == core.JOINT_ALPHA:
                lines.append(f"- `{core.JOINT_ALPHA}`:")
                for joint_scope in ("pooled", "macro_within_level", "item_centered"):
                    cell = scopes[joint_scope]
                    lines.append(f"  - {joint_scope}: {_format_number(cell[core.JOINT_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
                for level, cell in scopes["per_level"].items():
                    lines.append(f"  - level:{level}: {_format_number(cell[core.JOINT_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
                for family in ("by_domain", "by_generation_model"):
                    for label, cell in scopes[family].items():
                        lines.append(f"  - {family}:{label}: {_format_number(cell[core.JOINT_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
                continue
            lines.append(f"### Reference: {reference}")
            lines.append("- per_level:")
            for level, cell in scopes["per_level"].items():
                lines.append(f"  - {level}: rho={_format_number(cell['rho'])}; {core.PAIRWISE_ALPHA}={_format_number(cell[core.PAIRWISE_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
            for subgroup_family in ("by_domain", "by_generation_model"):
                lines.append(f"- {subgroup_family}:")
                for label, cell in scopes[subgroup_family].items():
                    lines.append(f"  - {label}: rho={_format_number(cell['rho'])}; {core.PAIRWISE_ALPHA}={_format_number(cell[core.PAIRWISE_ALPHA])}; n={cell['n']}")
            if reference == "treatment_ordinal":
                ordinal = scopes["per_item_ordinal"]
                lines.append(
                    f"- per-item ordinal: mean Spearman={_format_number(ordinal['mean_per_item_spearman'])}; finite Spearman items={ordinal['finite_spearman_items']}; "
                    f"mean Kendall tau-b={_format_number(ordinal['mean_per_item_kendall_tau_b'])}; finite tau-b items={ordinal['finite_tau_b_items']}; "
                    f"strict monotonic={ordinal['strict_monotonic_items']}/{ordinal['items']} ({_format_number(ordinal['strict_monotonic_rate'])}); "
                    f"nonstrict monotonic={ordinal['nonstrict_monotonic_items']}/{ordinal['items']} ({_format_number(ordinal['nonstrict_monotonic_rate'])})"
                )
            lines.append("")
    lines.extend(["## Compact word-length residualization sensitivity", ""])
    classifications = metrics["outcome_neutral_classification"]["length_R_vs_baselines"]
    for spec in ("word_L_out", "word_L_full"):
        lines.append(f"### {spec}")
        for baseline, result in classifications[spec].items():
            lines.append(f"- {baseline}: classification={result['classification']}; relative_to_unadjusted={result['relative_to_unadjusted']}")
            for metric_id in result["metric_ids"]:
                cell = bootstrap["metrics"][metric_id]
                lines.append(f"  - `{metric_id}`: point={_format_number(cell['point'])}; CI={_ci_text(cell)}")
        lines.append("")
    lines.extend(["## Common-support coverage cells", "", "```json", json.dumps(metrics["common_support"], ensure_ascii=False, sort_keys=True, indent=2), "```", ""])
    return "\n".join(lines)


def _render_coefficients(fits: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Appendix: nested-CV model fits and coefficients", "",
        "This appendix records every outer-fold fit. Ridge entries include the complete inner-alpha score grid, training-only scaler mean/scale, standardized coefficients, intercept, auxiliary test metrics, and exact train/test cluster hashes. HGB entries include the frozen parameters and fold hashes.", "",
    ]
    ordered = sorted(fits, key=lambda r: (str(r.get("model_label")), int(r.get("outer_fold", -1))))
    for record in ordered:
        label = str(record["model_label"]); fold = record.get("outer_fold", "unavailable")
        lines.extend([
            f"## {label} — outer {fold}", "",
            "```json", json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2), "```", "",
        ])
    return "\n".join(lines)


def _classification(bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    records = bootstrap["metrics"]
    output: dict[str, Any] = {}
    for learner in ("ridge", "hgb"):
        keys = [
            f"incremental_delta|{learner}|{target}|H+R-minus-H|{scope}|{metric}"
            for target in core.WHITEBOX_TARGETS
            for scope in ("macro_within_level", "item_centered")
            for metric in ("rho", core.PAIRWISE_ALPHA)
        ]
        existing = [records[key] for key in keys if key in records]
        output[f"H+R_vs_H_{learner}"] = {
            "classification": core.classify_intervals(existing) if len(existing) == 8 else "skipped_unavailable",
            "required_cells": 8, "available_cells": len(existing), "metric_ids": keys,
        }
    whitebox_keys = [
        f"direct_delta|R_actual-minus-G_raw_bits|{reference}|{scope}|{metric}"
        for reference in ("llama", "mixtral")
        for scope in ("macro_within_level", "item_centered")
        for metric in ("rho", core.PAIRWISE_ALPHA)
    ]
    treatment_keys = [
        f"direct_delta|R_actual-minus-G_raw_bits|treatment|{scope}|{metric}"
        for scope in ("pooled", "item_centered")
        for metric in ("rho", core.PAIRWISE_ALPHA)
    ]
    whitebox = core.classify_intervals([records[key] for key in whitebox_keys])
    treatment = core.classify_intervals([records[key] for key in treatment_keys])
    output["R_vs_G"] = {
        "white_box_convergence": whitebox,
        "treatment_construct": treatment,
        "overall": whitebox if whitebox == treatment and whitebox in {"stable_positive", "stable_negative"} else "mixed_or_inconclusive",
        "white_box_metric_ids": whitebox_keys,
        "treatment_metric_ids": treatment_keys,
    }
    length_results: dict[str, Any] = {}
    for spec in core.LENGTH_SPECS:
        length_results[spec] = {}
        for baseline in ("G_raw_bits", "G_raw_bits_per_output_byte"):
            keys = [
                f"length_delta|{spec}|{target}|R_actual-minus-{baseline}|{scope}|{metric}"
                for target in core.WHITEBOX_TARGETS
                for scope in ("macro_within_level", "item_centered")
                for metric in ("rho", core.PAIRWISE_ALPHA)
            ]
            category = core.classify_intervals([records[key] for key in keys])
            direct_category = whitebox if baseline == "G_raw_bits" else core.classify_intervals([
                records[f"direct_delta|R_actual-minus-{baseline}|{reference}|{scope}|{metric}"]
                for reference in ("llama", "mixtral")
                for scope in ("macro_within_level", "item_centered")
                for metric in ("rho", core.PAIRWISE_ALPHA)
            ])
            if category == direct_category and category in {"stable_positive", "stable_negative"}:
                persistence = "persists"
            elif category in {"stable_positive", "stable_negative"} and direct_category in {"stable_positive", "stable_negative"} and category != direct_category:
                persistence = "reverses"
            elif direct_category in {"stable_positive", "stable_negative"}:
                persistence = "attenuates_or_disappears"
            else:
                persistence = "inconclusive_primary_baseline"
            length_results[spec][baseline] = {
                "classification": category, "relative_to_unadjusted": persistence,
                "unadjusted_classification": direct_category, "metric_ids": keys,
            }
    output["length_R_vs_baselines"] = length_results
    return output


def _render_report(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any], classification: Mapping[str, Any]) -> str:
    agreement = metrics["evaluator_sensitivity"]["llama_vs_mixtral"]
    lines = [
        "# Actual-only 增量与敏感性分析报告", "",
        "## 冻结的主要分析", "",
        f"- Llama↔Mixtral 的五层宏平均：Spearman rho={_format_number(agreement['macro_within_level']['rho'])}，`{core.PAIRWISE_ALPHA}`={_format_number(agreement['macro_within_level'][core.PAIRWISE_ALPHA])}。",
        f"- Llama↔Mixtral 的item-centered结果：Spearman rho={_format_number(agreement['item_centered']['rho'])}，`{core.PAIRWISE_ALPHA}`={_format_number(agreement['item_centered'][core.PAIRWISE_ALPHA])}。",
        f"- Ridge中H+R相对H的冻结分类：`{classification['H+R_vs_H_ridge']['classification']}`。",
        f"- R相对raw G的总体分类：`{classification['R_vs_G']['overall']}`（white-box convergence：`{classification['R_vs_G']['white_box_convergence']}`；treatment construct：`{classification['R_vs_G']['treatment_construct']}`）。", "",
        "## 次要分析", "",
        "归一化R、raw gain、冻结heuristics、evaluator ordering、pooled结果和预声明subgroup均完整报告，不按结果筛选。",
        "strongest-single模型明确属于辅助分析，不是六个冻结primary predictor sets之一；其R-only差值也使用同一paired source-cluster bootstrap。", "",
        "## 稳健性分析", "",
        f"- 固定HGB中H+R相对H的分类：`{classification['H+R_vs_H_hgb']['classification']}`。",
        "- byte output-only长度残差化是主要稳健性规格；full-byte以及word-length规格是敏感性检查。`residual_candidate_vs_raw_treatment_ordinal`保持treatment labels不变，仅残差化R；它不是双侧partial correlation。",
        f"- byte L_out下R相对raw G：`{classification['length_R_vs_baselines']['byte_L_out']['G_raw_bits']['classification']}`，相对未调整结论为`{classification['length_R_vs_baselines']['byte_L_out']['G_raw_bits']['relative_to_unadjusted']}`。", "",
        "## 探索性分析", "",
        f"- all-five 1.25 common-support推断策略：`{metrics['common_support']['all_five_byte_1.25']['inference_policy']}`。", "",
        "## 不支持的主张", "",
        "这些结果不建立criterion truth、语义效度、因果效度、普遍优越性，也不代表相对于独立人工标注ground truth的可靠性。L1–L5是investigator-specified ordinal treatment labels。", "",
        "本分析未调用API、未联网、未使用GPU、未生成或重生成文本、未读取完整prompt/output正文、未重新压缩、未使用counterfactual字段，也未修改Word。资源约束为`sampled_process_rss_hard_limit`（50 ms采样并在退出时同步复测），不声称捕获采样间隔内所有瞬时峰值。", "",
    ]
    return "\n".join(lines)


def _write_projections(metrics: Mapping[str, Any], bootstrap: Mapping[str, Any], fits: Sequence[Mapping[str, Any]], selections: Mapping[str, Any], classification: Mapping[str, Any]) -> None:
    # Render exclusively from data reloaded from disk by the caller.
    rows = _flatten_metric_rows(metrics, bootstrap)
    csv_path = BUNDLE_DIR / "metrics.csv"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{csv_path.name}.{os.getpid()}.", suffix=".tmp", dir=csv_path.parent)
    temporary = Path(temporary_name)
    fields = ["family", "candidate", "reference", "scope", "metric", "point", "ci_lower", "ci_upper", "n", "finite_resamples", "undefined_resamples", "resample_effective_n_all_min", "resample_effective_n_all_max", "resample_effective_n_finite_min", "resample_effective_n_finite_max", "undefined_reason"]
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="", closefd=True) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader(); writer.writerows(rows); handle.flush(); os.fsync(handle.fileno())
        _commit_stream_create_or_identical(temporary, csv_path)
    finally:
        if core.path_lexists(temporary):
            if core.is_reparse_or_link(temporary): raise core.AnalysisError(f"temporary path replaced by link/reparse: {temporary}")
            temporary.unlink()
    renderers = {
        "table1_ratio_vs_raw_gain.md": _render_table1(metrics, bootstrap, selections),
        "table2_incremental_validity.md": _render_table2(metrics, bootstrap),
        "table3_evaluator_sensitivity.md": _render_table3(metrics),
        "table4_length_residualized.md": _render_table4(metrics, bootstrap),
        "table5_length_common_support.md": _render_table5(metrics, bootstrap),
        "appendix_subgroups.md": _render_appendix_subgroups(metrics, bootstrap),
        "appendix_model_coefficients.md": _render_coefficients(fits),
        "REPORT_ZH.md": _render_report(metrics, bootstrap, classification),
    }
    for name, text in renderers.items():
        core.atomic_write_text(BUNDLE_DIR / name, text)


def _validate_structured_outputs(
    metrics: Mapping[str, Any], bootstrap: Mapping[str, Any], fits: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = _flatten_metric_rows(metrics, bootstrap)
    findings = [
        *core.forbidden_identifier_findings(metrics, path="metrics"),
        *core.forbidden_identifier_findings(bootstrap, path="bootstrap"),
        *core.forbidden_identifier_findings(fits, path="model_fits"),
        *core.forbidden_identifier_findings(rows, path="metrics_csv"),
    ]
    with core.open_plain_binary(BUNDLE_DIR / "oof_predictions.jsonl") as handle:
        first = core.strict_json_loads(handle.readline(), "oof first row")
    findings.extend(core.forbidden_identifier_findings(first, path="oof_schema"))
    for name in (*TABLE_FILES, "appendix_subgroups.md", "appendix_model_coefficients.md", "REPORT_ZH.md"):
        findings.extend(core.forbidden_text_identifier_findings(
            core.read_plain_bytes(BUNDLE_DIR / name).decode("utf-8", errors="strict"), path=name,
        ))
    if findings:
        raise core.AnalysisError(f"forbidden structured identifier(s): {findings[:20]}")
    return {
        "passed": True, "forbidden_identifier_occurrences": 0,
        "structured_artifacts_scanned": [
            "metrics.json", "bootstrap_summary.json", "model_fits.jsonl",
            "oof_predictions.jsonl", "metrics.csv", *TABLE_FILES,
            "appendix_subgroups.md", "appendix_model_coefficients.md", "REPORT_ZH.md",
        ],
        "narrative_prose_excluded_by_design": True,
    }


def _validate_checkpoint_index_header(checkpoint_index: Any, config_sha: str) -> None:
    if (
        not isinstance(checkpoint_index, dict)
        or set(checkpoint_index) != {"schema", "schema_version", "config_sha256", "oof", "bootstrap", "payload_sha256_excluding_this_field"}
        or checkpoint_index.get("schema") != "actual_incremental_sensitivity.checkpoint_index"
        or checkpoint_index.get("schema_version") != 1
        or checkpoint_index.get("config_sha256") != config_sha
        or not isinstance(checkpoint_index.get("oof"), list)
        or not isinstance(checkpoint_index.get("bootstrap"), list)
    ):
        raise core.AnalysisError("checkpoint index exact schema/config differs")


def _validate_scientific_completion() -> dict[str, Any]:
    completion_path = BUNDLE_DIR / "scientific_completion.json"
    completion, completion_sha, _ = core.strict_json_load_record(completion_path)
    if not isinstance(completion, dict) or set(completion) != COMPLETION_KEYS:
        raise core.AnalysisError("scientific completion exact schema differs")
    core.verify_payload_hash(completion)
    if (
        completion.get("schema") != "actual_incremental_sensitivity.scientific_completion"
        or completion.get("schema_version") != 1
        or completion.get("state") != "complete_pending_independent_audit"
        or completion.get("bundle_id") != BUNDLE_ID
        or completion.get("authority_ledger_sha256") != core.EXPECTED_LEDGER_SHA256
    ):
        raise core.AnalysisError("scientific completion identity/state differs")
    _, config_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "run_config.json")
    if completion.get("config_sha256") != config_sha:
        raise core.AnalysisError("scientific completion config binding differs")
    checkpoint_index, checkpoint_index_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "checkpoint_index.json")
    if completion.get("checkpoint_index_sha256") != checkpoint_index_sha:
        raise core.AnalysisError("scientific completion checkpoint binding differs")
    artifacts = completion.get("artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(entry, dict) for entry in artifacts):
        raise core.AnalysisError("scientific completion artifact inventory differs")
    if [entry.get("path") for entry in artifacts] != sorted(FORMAL_SCIENTIFIC_FILES):
        raise core.AnalysisError("scientific completion artifact inventory differs")
    if completion.get("artifact_inventory_sha256") != core.sha256_bytes(core.canonical_json_bytes(artifacts)):
        raise core.AnalysisError("scientific completion artifact inventory digest differs")
    for entry in artifacts:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise core.AnalysisError("scientific completion artifact record schema differs")
        relative = _require_safe_relative(entry["path"], "scientific artifact")
        path = BUNDLE_DIR / relative
        digest, size = core.file_fingerprint(path)
        if size != entry["size"] or digest != entry["sha256"]:
            raise core.AnalysisError(f"scientific artifact drift: {entry['path']}")
    execution_record = next(entry for entry in artifacts if entry["path"] == "execution.json")
    _validate_execution_receipt(config_sha, execution_record)
    code_files = _code_snapshot()
    if completion.get("code_snapshot") != {"files": code_files, "inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(code_files))}:
        raise core.AnalysisError("scientific completion code snapshot differs")
    core.verify_payload_hash(checkpoint_index)
    _validate_checkpoint_index_header(checkpoint_index, config_sha)
    checkpoint_paths: set[str] = set()
    for family in ("oof", "bootstrap"):
        records = checkpoint_index[family]
        if records != sorted(records, key=lambda record: record["path"]):
            raise core.AnalysisError("checkpoint index order differs")
        for record in records:
            if set(record) != {"path", "sha256", "size"} or record["path"] in checkpoint_paths:
                raise core.AnalysisError("checkpoint index record differs")
            relative = _require_safe_relative(record["path"], "checkpoint")
            path = BUNDLE_DIR / relative
            digest, size = core.file_fingerprint(path)
            if size != record["size"] or digest != record["sha256"]:
                raise core.AnalysisError(f"checkpoint artifact drift: {record['path']}")
            checkpoint_paths.add(record["path"])
    expected_oof_paths, expected_bootstrap_paths = _expected_checkpoint_paths(include_hgb=_hgb_available())
    if {record["path"] for record in checkpoint_index["oof"]} != expected_oof_paths:
        raise core.AnalysisError("checkpoint index OOF logical/path inventory differs")
    if {record["path"] for record in checkpoint_index["bootstrap"]} != expected_bootstrap_paths:
        raise core.AnalysisError("checkpoint index bootstrap logical/path inventory differs")
    allowed_optional = {name for name in ("audit.json", "manifest.json") if (BUNDLE_DIR / name).exists()}
    expected_tree = {
        *CODE_FILES, "RUNBOOK.md", *FORMAL_SCIENTIFIC_FILES,
        "scientific_completion.json", *checkpoint_paths, *allowed_optional,
    }
    actual_tree = set(core.inspect_plain_tree(BUNDLE_DIR, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES))
    if actual_tree != expected_tree:
        raise core.AnalysisError(
            f"scientific completion recursive inventory differs; missing={sorted(expected_tree-actual_tree)}, "
            f"unknown={sorted(actual_tree-expected_tree)}"
        )
    return completion


def analyze() -> None:
    is_final = _ensure_stage(allow_final=True); config, folds, derived, prepare_receipt = _load_preparation()
    dataset = _rebuild_and_validate_preparation(config, folds, derived, prepare_receipt)
    if is_final:
        completion = _validate_scientific_completion(); _validate_audit_receipt(completion); _validate_existing_manifest(BUNDLE_DIR / "manifest.json")
        print("analysis: finalized bundle fully validated; no-op", flush=True)
        return
    if (BUNDLE_DIR / "scientific_completion.json").exists():
        completion = _validate_scientific_completion()
        if (BUNDLE_DIR / "audit.json").exists():
            _validate_audit_receipt(completion)
        if (BUNDLE_DIR / "manifest.json").exists():
            _validate_existing_manifest(BUNDLE_DIR / "manifest.json")
        core.validate_authority(AUTHORITY, PROJECT_ROOT)
        print("analysis: existing scientific completion and every bound artifact validated; no-op", flush=True)
        return
    stale_terminal = [name for name in ("audit.json", "manifest.json") if (BUNDLE_DIR / name).exists()]
    if stale_terminal:
        raise core.AnalysisError(f"terminal receipt exists without scientific completion: {stale_terminal}")
    start = time.perf_counter(); _, config_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "run_config.json")
    with core.ResourceMonitor() as monitor:
        monitor.set_phase("model_fitting")
        predictions, length_predictions, residuals, fits, model_blocks = _fit_all(
            dataset, folds, config_sha, monitor,
            config["frozen_strongest"]["strongest_single_heuristic"]["selected"],
        )
        _load_oof_from_memory_guard({**predictions, **length_predictions}, residuals, dataset)
        aggregate_blocks = _write_oof(
            dataset, predictions, length_predictions, residuals, config_sha,
        )
        _stream_validate_oof(dataset, predictions, length_predictions, residuals, folds)
        _write_model_fits(fits)
        reloaded_fits = _load_model_fits(hgb_available=_hgb_available())
        monitor.set_phase("point_statistics")
        points = _point_metrics(dataset, predictions, residuals)
        selections = config["frozen_strongest"]
        bootstrap, bootstrap_blocks = _run_bootstrap(
            dataset, predictions, residuals, selections, points["common_support"], config_sha, monitor,
        )
        core.atomic_write_json(BUNDLE_DIR / "bootstrap_summary.json", bootstrap)
        classification = _classification(bootstrap)
        points["bootstrap_summary_sha256"] = core.sha256_file(BUNDLE_DIR / "bootstrap_summary.json")
        points["outcome_neutral_classification"] = classification
        points["config_sha256"] = config_sha
        core.atomic_write_json(BUNDLE_DIR / "metrics.json", core.payload_with_hash(points))
        # Mandatory reload boundary: every projection derives from strict disk artifacts.
        reloaded_metrics = core.strict_json_load(BUNDLE_DIR / "metrics.json")
        reloaded_bootstrap = core.strict_json_load(BUNDLE_DIR / "bootstrap_summary.json")
        core.verify_payload_hash(reloaded_metrics)
        monitor.set_phase("projection_rendering")
        _write_projections(reloaded_metrics, reloaded_bootstrap, reloaded_fits, selections, classification)
        oof_by_path = {
            record["path"]: record for record in [*model_blocks, *aggregate_blocks]
        }
        checkpoint_index = core.payload_with_hash({
            "schema": "actual_incremental_sensitivity.checkpoint_index", "schema_version": 1,
            "config_sha256": config_sha,
            "oof": [oof_by_path[path] for path in sorted(oof_by_path)],
            "bootstrap": sorted(bootstrap_blocks, key=lambda record: record["path"]),
        })
        core.atomic_write_json(BUNDLE_DIR / "checkpoint_index.json", checkpoint_index)
        _validate_structured_outputs(reloaded_metrics, reloaded_bootstrap, reloaded_fits)
        monitor.check()
    resources = monitor.receipt()
    execution_path = BUNDLE_DIR / "execution.json"
    if execution_path.exists():
        execution = _validate_execution_receipt(config_sha)
    else:
        execution = core.payload_with_hash({
            "schema": "actual_incremental_sensitivity.execution", "schema_version": 1,
            "state": "scientific_outputs_complete", "config_sha256": config_sha,
            "elapsed_seconds": time.perf_counter() - start,
            "environment": core.environment_receipt(), "resources": resources,
            "external_api_calls": 0, "network_access": False, "gpu": False,
            "model_generation": False, "text_regeneration": False, "recompression": False,
            "prompt_output_text_reads": 0, "counterfactual_fields_used": False,
            "authority_modified": False, "word_modified": False,
        })
        core.atomic_write_json(execution_path, execution)
    records = sorted(
        [core.file_record(BUNDLE_DIR / name, BUNDLE_DIR) for name in FORMAL_SCIENTIFIC_FILES],
        key=lambda entry: entry["path"],
    )
    code_files = _code_snapshot()
    completion = core.payload_with_hash({
        "schema": "actual_incremental_sensitivity.scientific_completion", "schema_version": 1,
        "state": "complete_pending_independent_audit", "bundle_id": BUNDLE_ID,
        "config_sha256": config_sha, "authority_ledger_sha256": core.EXPECTED_LEDGER_SHA256,
        "checkpoint_index_sha256": core.sha256_file(BUNDLE_DIR / "checkpoint_index.json"),
        "artifacts": records, "artifact_inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(records)),
        "code_snapshot": {"files": code_files, "inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(code_files))},
    })
    core.atomic_write_json(BUNDLE_DIR / "scientific_completion.json", completion)
    _validate_scientific_completion()
    print(f"scientific outputs complete in {time.perf_counter() - start:.1f}s; run independent audit next", flush=True)


def _manifest_artifacts(expected_paths: set[str]) -> list[dict[str, Any]]:
    actual = set(core.inspect_plain_tree(BUNDLE_DIR, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES))
    if actual != expected_paths:
        raise core.AnalysisError(
            f"manifest source inventory differs; missing={sorted(expected_paths-actual)}, unknown={sorted(actual-expected_paths)}"
        )
    return [core.file_record(BUNDLE_DIR / name, BUNDLE_DIR) for name in sorted(expected_paths)]


def _compare_trees(left: Path, right: Path) -> bool:
    try:
        left_names = core.inspect_plain_tree(left, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES)
        right_names = core.inspect_plain_tree(right, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES)
    except core.AnalysisError:
        return False
    if left_names != right_names:
        return False
    return all(core.sha256_file(left / name) == core.sha256_file(right / name) for name in left_names)


def _validate_resource_receipt(resources: Any, label: str) -> dict[str, Any]:
    fields = {
        "rss_backend", "rss_baseline_bytes", "rss_peak_bytes", "rss_incremental_peak_bytes",
        "phase_rss_peaks_bytes", "tracemalloc_current_bytes", "tracemalloc_peak_bytes",
        "rss_target_bytes", "rss_hard_limit_bytes", "rss_limit_semantics",
        "rss_sampling_interval_milliseconds", "synchronous_exit_rss_sample",
    }
    if not isinstance(resources, dict) or set(resources) != fields:
        raise core.AnalysisError(f"{label} resource exact schema differs")
    if resources["rss_backend"] not in {"psutil", "win32_ctypes"}:
        raise core.AnalysisError(f"{label} RSS backend differs")
    numeric = fields - {"rss_backend", "phase_rss_peaks_bytes", "rss_limit_semantics", "synchronous_exit_rss_sample"}
    if any(isinstance(resources[key], bool) or not isinstance(resources[key], int) or resources[key] < 0 for key in numeric):
        raise core.AnalysisError(f"{label} resource numeric values differ")
    phases = resources["phase_rss_peaks_bytes"]
    if not isinstance(phases, dict) or not phases or any(
        not isinstance(key, str) or not key or isinstance(value, bool) or not isinstance(value, int) or value < 0
        for key, value in phases.items()
    ):
        raise core.AnalysisError(f"{label} phase RSS evidence differs")
    if (
        resources["rss_target_bytes"] != core.RSS_TARGET
        or resources["rss_hard_limit_bytes"] != core.RSS_HARD_LIMIT
        or resources["rss_limit_semantics"] != "sampled_process_rss_hard_limit"
        or resources["rss_sampling_interval_milliseconds"] != 50
        or resources["synchronous_exit_rss_sample"] is not True
        or resources["rss_peak_bytes"] < resources["rss_baseline_bytes"]
        or resources["rss_incremental_peak_bytes"] != max(0, resources["rss_peak_bytes"] - resources["rss_baseline_bytes"])
        or resources["rss_peak_bytes"] > core.RSS_HARD_LIMIT
        or max(phases.values()) > resources["rss_peak_bytes"]
        or resources["tracemalloc_current_bytes"] > resources["tracemalloc_peak_bytes"]
    ):
        raise core.AnalysisError(f"{label} resource policy/evidence differs")
    return resources


def _validate_environment_receipt(environment: Any) -> dict[str, Any]:
    expected = core.environment_receipt()
    if not isinstance(environment, dict) or set(environment) != set(expected) or environment != expected:
        raise core.AnalysisError("execution environment differs from exact runtime environment")
    return environment


def _validate_execution_receipt(config_sha: str, expected_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    execution, execution_sha, execution_size = core.strict_json_load_record(BUNDLE_DIR / "execution.json")
    if expected_record is not None and (execution_sha, execution_size) != (expected_record.get("sha256"), expected_record.get("size")):
        raise core.AnalysisError("execution parse differs from scientific artifact binding")
    expected_fields = {
        "schema", "schema_version", "state", "config_sha256", "elapsed_seconds",
        "environment", "resources", "external_api_calls", "network_access", "gpu",
        "model_generation", "text_regeneration", "recompression", "prompt_output_text_reads",
        "counterfactual_fields_used", "authority_modified", "word_modified",
        "payload_sha256_excluding_this_field",
    }
    if not isinstance(execution, dict) or set(execution) != expected_fields:
        raise core.AnalysisError("execution receipt exact schema differs")
    core.verify_payload_hash(execution)
    expected_claims = {
        "external_api_calls": 0, "network_access": False, "gpu": False,
        "model_generation": False, "text_regeneration": False, "recompression": False,
        "prompt_output_text_reads": 0, "counterfactual_fields_used": False,
        "authority_modified": False, "word_modified": False,
    }
    if (
        execution.get("schema") != "actual_incremental_sensitivity.execution"
        or execution.get("schema_version") != 1
        or execution.get("state") != "scientific_outputs_complete"
        or execution.get("config_sha256") != config_sha
        or any(execution.get(key) != value for key, value in expected_claims.items())
    ):
        raise core.AnalysisError("execution receipt frozen values differ")
    elapsed = execution.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(float(elapsed)) or float(elapsed) < 0:
        raise core.AnalysisError("execution elapsed time differs")
    _validate_environment_receipt(execution.get("environment"))
    _validate_resource_receipt(execution.get("resources"), "execution")
    return execution


def _validate_audit_receipt(completion: Mapping[str, Any]) -> dict[str, Any]:
    audit, audit_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "audit.json")
    expected_keys = {
        "schema", "schema_version", "state", "bundle_id", "config_sha256",
        "scientific_completion_sha256", "scientific_artifact_inventory_sha256",
        "authority", "coverage", "auditor_independence", "folds", "raw_algebra",
        "models", "point_statistics", "bootstrap", "checkpoints",
        "projection_byte_comparison", "structured_output_scan", "resources",
        "execution", "payload_sha256_excluding_this_field",
    }
    if not isinstance(audit, dict) or set(audit) != expected_keys:
        raise core.AnalysisError("audit receipt exact schema differs")
    core.verify_payload_hash(audit)
    if audit.get("schema") != "actual_incremental_sensitivity.independent_audit" or audit.get("state") != "pass":
        raise core.AnalysisError("audit receipt is not a pass")
    config, config_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "run_config.json")
    _, current_completion_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "scientific_completion.json")
    if audit.get("config_sha256") != config_sha:
        raise core.AnalysisError("audit is not bound to current config")
    if audit.get("scientific_completion_sha256") != current_completion_sha:
        raise core.AnalysisError("audit is not bound to current scientific completion")
    if audit.get("scientific_artifact_inventory_sha256") != completion["artifact_inventory_sha256"]:
        raise core.AnalysisError("audit is not bound to validated scientific artifact inventory")
    if audit.get("schema_version") != 1 or audit.get("bundle_id") != BUNDLE_ID or audit.get("authority") != config["authority"] or audit.get("coverage") != {"pairs": core.EXPECTED_PAIRS, "items": core.EXPECTED_ITEMS, "clusters": core.EXPECTED_CLUSTERS}:
        raise core.AnalysisError("audit identity/authority/coverage differs")
    independence = audit.get("auditor_independence")
    if not isinstance(independence, dict) or set(independence) != {"auditor_imports_production", "production_forbidden_import_scan"} or independence["auditor_imports_production"] is not False or independence["production_forbidden_import_scan"] != {"analysis_core.py": "pass", "run_analysis.py": "pass"}:
        raise core.AnalysisError("audit independence evidence differs")
    if audit.get("folds") != {"independently_rebuilt": True, "full_row_permutation_invariant": True, "zero_cluster_leakage": True, "all_cluster_counts_and_inner_outer_cells_recomputed": True} or audit.get("raw_algebra") != {"independently_rebuilt": True, "ratio_identity_exact_within_frozen_tolerance": True}:
        raise core.AnalysisError("audit fold/algebra evidence differs")
    models = audit.get("models", {})
    expected_hgb_models = 70 if _hgb_available() else 0
    expected_model_fields = {
        "ridge_outer_models_refit", "hgb_outer_models_refit", "hgb_import_available",
        "exact_model_inventory", "all_model_fit_metadata_recomputed",
        "maximum_prediction_absolute_error", "maximum_prediction_tolerance_ratio",
        "maximum_model_fit_metadata_absolute_error", "maximum_model_fit_metadata_allowed_absolute_error",
        "prediction_atol", "prediction_rtol", "fit_metadata_tolerance",
    }
    if (
        set(models) != expected_model_fields
        or models.get("ridge_outer_models_refit") != 170
        or models.get("hgb_outer_models_refit") != expected_hgb_models
        or models.get("hgb_import_available") is not _hgb_available()
        or models.get("exact_model_inventory") is not True
        or models.get("all_model_fit_metadata_recomputed") is not True
        or models.get("prediction_atol") != 1e-12
        or models.get("prediction_rtol") != 1e-10
        or models.get("fit_metadata_tolerance") != 1e-10
        or models.get("maximum_model_fit_metadata_allowed_absolute_error") != 1e-10
    ):
        raise core.AnalysisError("audit model evidence differs")
    for key in ("maximum_prediction_absolute_error", "maximum_prediction_tolerance_ratio", "maximum_model_fit_metadata_absolute_error"):
        core.finite_float(models.get(key), f"audit.models.{key}")
    if (
        any(models[key] < 0 for key in ("maximum_prediction_absolute_error", "maximum_prediction_tolerance_ratio", "maximum_model_fit_metadata_absolute_error"))
        or models["maximum_prediction_tolerance_ratio"] > 1.0
        or models["maximum_model_fit_metadata_absolute_error"] > models["maximum_model_fit_metadata_allowed_absolute_error"]
    ):
        raise core.AnalysisError("audit model errors exceed declared tolerances")
    point = audit.get("point_statistics", {})
    if set(point) != {"all_recomputed", "maximum_absolute_error", "tolerance"} or point.get("all_recomputed") is not True or point.get("tolerance") != 2e-12:
        raise core.AnalysisError("audit point-statistic evidence differs")
    point_error = core.finite_float(point.get("maximum_absolute_error"), "audit.point_statistics.maximum_absolute_error")
    if point_error < 0 or point_error > point["tolerance"]:
        raise core.AnalysisError("audit point-statistic error exceeds tolerance")
    replay = audit.get("bootstrap", {})
    expected_bootstrap_count = 552 if _hgb_available() else 512
    expected_replay_fields = {
        "replicates", "metrics", "expected_metric_inventory", "draw_sequence_sha256",
        "maximum_replay_absolute_error", "replay_absolute_tolerance",
        "maximum_percentile_absolute_error", "percentile_absolute_tolerance",
        "all_effective_matrix_elements_recomputed", "all_effective_summary_fields_recomputed",
    }
    if (
        set(replay) != expected_replay_fields or replay.get("replicates") != 2000
        or replay.get("metrics") != expected_bootstrap_count
        or replay.get("expected_metric_inventory") is not True
        or replay.get("draw_sequence_sha256") != core.EXPECTED_DRAW_SHA256
        or replay.get("replay_absolute_tolerance") != 2e-12
        or replay.get("percentile_absolute_tolerance") != 3e-12
        or replay.get("all_effective_matrix_elements_recomputed") is not True
        or replay.get("all_effective_summary_fields_recomputed") is not True
    ):
        raise core.AnalysisError("audit bootstrap evidence differs")
    replay_error = core.finite_float(replay.get("maximum_replay_absolute_error"), "audit.bootstrap.maximum_replay_absolute_error")
    percentile_error = core.finite_float(replay.get("maximum_percentile_absolute_error"), "audit.bootstrap.maximum_percentile_absolute_error")
    if replay_error < 0 or replay_error > replay["replay_absolute_tolerance"] or percentile_error < 0 or percentile_error > replay["percentile_absolute_tolerance"]:
        raise core.AnalysisError("audit bootstrap errors exceed declared tolerances")
    checkpoints = audit.get("checkpoints", {})
    expected_model_blocks = 240 if _hgb_available() else 170
    if checkpoints != {"model_outer_blocks": expected_model_blocks, "aggregate_outer_blocks": 5, "bootstrap_blocks": 80, "exact_inventory": True, "all_hashes_keys_rows_dtypes_shapes_and_payloads_valid": True, "all_oof_checkpoint_values_match_ledger": True}:
        raise core.AnalysisError("audit checkpoint evidence differs")
    if audit.get("projection_byte_comparison") != {name: True for name in sorted(PROJECTION_FILES)}:
        raise core.AnalysisError("audit projection evidence differs")
    structured = audit.get("structured_output_scan", {})
    expected_structured = {
        "passed": True, "forbidden_identifier_occurrences": 0,
        "structured_artifacts_scanned": [
            "metrics.json", "bootstrap_summary.json", "model_fits.jsonl",
            "oof_predictions.jsonl", "metrics.csv", *TABLE_FILES,
            "appendix_subgroups.md", "appendix_model_coefficients.md", "REPORT_ZH.md",
        ],
        "narrative_prose_excluded_by_design": True,
    }
    if structured != expected_structured:
        raise core.AnalysisError("audit structured-output evidence differs")
    _validate_resource_receipt(audit.get("resources"), "audit")
    execution = audit.get("execution", {})
    expected_audit_execution_fields = {
        "elapsed_seconds", "external_api_calls", "network_access", "gpu", "model_generation",
        "text_regeneration", "recompression", "prompt_output_text_reads", "counterfactual_fields_used",
        "authority_modified", "word_modified",
    }
    if set(execution) != expected_audit_execution_fields:
        raise core.AnalysisError("audit operational evidence schema differs")
    elapsed = core.finite_float(execution.get("elapsed_seconds"), "audit.execution.elapsed_seconds")
    expected_audit_claims = {
        "external_api_calls": 0, "network_access": False, "gpu": False,
        "model_generation": False, "text_regeneration": False, "recompression": False,
        "prompt_output_text_reads": 0, "counterfactual_fields_used": False,
        "authority_modified": False, "word_modified": False,
    }
    if elapsed < 0 or any(execution.get(key) != value for key, value in expected_audit_claims.items()):
        raise core.AnalysisError("audit operational evidence differs")
    return audit


def _validate_existing_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest, manifest_sha, _ = core.strict_json_load_record(manifest_path)
    expected_keys = {
        "schema", "schema_version", "state", "bundle_id", "created_at_utc",
        "authority_bundle_id", "authority_manifest_sha256", "ledger_sha256",
        "pair_set_sha256", "config_sha256", "scientific_completion_sha256",
        "audit_sha256", "artifacts", "artifact_inventory_sha256", "claims",
        "manifest_payload_sha256_excluding_this_field",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise core.AnalysisError("manifest exact schema differs")
    core.verify_payload_hash(manifest, "manifest_payload_sha256_excluding_this_field")
    if manifest.get("schema") != "actual_incremental_sensitivity.manifest" or manifest.get("schema_version") != 1 or manifest.get("state") != "complete" or manifest.get("bundle_id") != BUNDLE_ID:
        raise core.AnalysisError("manifest identity/state differs")
    expected_claims = {
        "external_api_calls": 0, "network_access": False, "gpu": False,
        "model_generation": False, "recompression": False, "prompt_output_text_reads": 0,
        "counterfactual_fields_used": False, "authority_modified": False, "word_modified": False,
    }
    _, config_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "run_config.json")
    _, completion_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "scientific_completion.json")
    _, audit_sha, _ = core.strict_json_load_record(BUNDLE_DIR / "audit.json")
    if (
        manifest.get("authority_bundle_id") != AUTHORITY_ID
        or manifest.get("created_at_utc") != CREATED_AT_UTC
        or manifest.get("authority_manifest_sha256") != core.EXPECTED_AUTHORITY_MANIFEST_SHA256
        or manifest.get("ledger_sha256") != core.EXPECTED_LEDGER_SHA256
        or manifest.get("pair_set_sha256") != core.EXPECTED_PAIR_SET_SHA256
        or manifest.get("config_sha256") != config_sha
        or manifest.get("scientific_completion_sha256") != completion_sha
        or manifest.get("audit_sha256") != audit_sha
        or manifest.get("claims") != expected_claims
    ):
        raise core.AnalysisError("manifest frozen bindings/claims differ")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or manifest.get("artifact_inventory_sha256") != core.sha256_bytes(core.canonical_json_bytes(artifacts)):
        raise core.AnalysisError("manifest artifact digest differs")
    declared = [entry["path"] for entry in artifacts]
    actual = core.inspect_plain_tree(BUNDLE_DIR, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES)
    if sorted([*declared, "manifest.json"]) != actual or len(declared) != len(set(declared)):
        raise core.AnalysisError("manifest recursive inventory differs")
    for entry in artifacts:
        if set(entry) != {"path", "sha256", "size"}:
            raise core.AnalysisError("manifest record schema differs")
        relative = _require_safe_relative(entry["path"], "manifest artifact")
        path = BUNDLE_DIR / relative
        digest, size = core.file_fingerprint(path)
        if size != entry["size"] or digest != entry["sha256"]:
            raise core.AnalysisError(f"manifest artifact differs: {entry['path']}")
    return manifest


def finalize() -> None:
    is_final = _ensure_stage(allow_final=True); config, _, _, _ = _load_preparation()
    completion = _validate_scientific_completion()
    audit = _validate_audit_receipt(completion)
    if is_final:
        _validate_existing_manifest(BUNDLE_DIR / "manifest.json")
        core.validate_authority(AUTHORITY, PROJECT_ROOT)
        print(f"finalized bundle fully validated; no-op: {BUNDLE_DIR}", flush=True)
        return
    current_code = _code_snapshot()
    if current_code != config["code_snapshot"]["files"]:
        raise core.AnalysisError("code differs from frozen config")
    core.validate_authority(AUTHORITY, PROJECT_ROOT)
    checkpoint_index = core.strict_json_load(BUNDLE_DIR / "checkpoint_index.json")
    core.verify_payload_hash(checkpoint_index)
    manifest_path = BUNDLE_DIR / "manifest.json"
    if manifest_path.exists():
        _validate_existing_manifest(manifest_path)
        if core.path_lexists(FINAL_DIR_UNRESOLVED):
            core.require_plain_directory(FINAL_DIR_UNRESOLVED, parent=PARENT_DIR_UNRESOLVED)
            if _compare_trees(BUNDLE_DIR, FINAL_DIR):
                print(f"final destination already byte-identical: {FINAL_DIR}", flush=True)
                return
            raise core.AnalysisError(f"existing final destination differs: {FINAL_DIR}")
        core.publish_directory_no_replace(BUNDLE_DIR, FINAL_DIR)
        print(f"published atomically -> {FINAL_DIR}", flush=True)
        return
    checkpoint_paths = {
        record["path"]
        for family in ("oof", "bootstrap")
        for record in checkpoint_index[family]
    }
    expected_paths = {
        *CODE_FILES, "RUNBOOK.md", *PREPARED_FILES,
        "oof_predictions.jsonl", "model_fits.jsonl", "checkpoint_index.json",
        "bootstrap_summary.json", "metrics.json", *PROJECTION_FILES,
        "execution.json", "scientific_completion.json", "audit.json",
        *checkpoint_paths,
    }
    actual_paths = set(core.inspect_plain_tree(BUNDLE_DIR, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES))
    if actual_paths != expected_paths:
        raise core.AnalysisError(
            f"pre-manifest inventory differs; missing={sorted(expected_paths-actual_paths)}, "
            f"unknown={sorted(actual_paths-expected_paths)}"
        )
    artifacts = _manifest_artifacts(expected_paths)
    base = {
        "schema": "actual_incremental_sensitivity.manifest", "schema_version": 1,
        "state": "complete", "bundle_id": BUNDLE_ID, "created_at_utc": CREATED_AT_UTC,
        "authority_bundle_id": AUTHORITY_ID,
        "authority_manifest_sha256": core.EXPECTED_AUTHORITY_MANIFEST_SHA256,
        "ledger_sha256": core.EXPECTED_LEDGER_SHA256,
        "pair_set_sha256": core.EXPECTED_PAIR_SET_SHA256,
        "config_sha256": core.sha256_file(BUNDLE_DIR / "run_config.json"),
        "scientific_completion_sha256": core.sha256_file(BUNDLE_DIR / "scientific_completion.json"),
        "audit_sha256": core.sha256_file(BUNDLE_DIR / "audit.json"),
        "artifacts": artifacts,
        "artifact_inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(artifacts)),
        "claims": {
            "external_api_calls": 0, "network_access": False, "gpu": False,
            "model_generation": False, "recompression": False, "prompt_output_text_reads": 0,
            "counterfactual_fields_used": False, "authority_modified": False, "word_modified": False,
        },
    }
    manifest = core.payload_with_hash(base, "manifest_payload_sha256_excluding_this_field")
    manifest_path = BUNDLE_DIR / "manifest.json"
    core.atomic_write_json(manifest_path, manifest)
    try:
        reloaded = _validate_existing_manifest(manifest_path)
        declared = [entry["path"] for entry in reloaded["artifacts"]]
        actual = core.inspect_plain_tree(BUNDLE_DIR, allowed_directories=ALLOWED_BUNDLE_DIRECTORIES)
        if sorted([*declared, "manifest.json"]) != actual:
            raise core.AnalysisError("final recursive inventory differs from manifest")
        for entry in reloaded["artifacts"]:
            path = BUNDLE_DIR / _require_safe_relative(entry["path"], "manifest artifact")
            digest, size = core.file_fingerprint(path)
            if size != entry["size"] or digest != entry["sha256"]:
                raise core.AnalysisError(f"final artifact differs: {entry['path']}")
        post_completion = _validate_scientific_completion()
        _validate_audit_receipt(post_completion)
        if _code_snapshot() != config["code_snapshot"]["files"]:
            raise core.AnalysisError("code drift detected after manifest write")
        if core.path_lexists(FINAL_DIR_UNRESOLVED):
            core.require_plain_directory(FINAL_DIR_UNRESOLVED, parent=PARENT_DIR_UNRESOLVED)
            if _compare_trees(BUNDLE_DIR, FINAL_DIR):
                print(f"final destination already byte-identical: {FINAL_DIR}", flush=True)
                return
            raise core.AnalysisError(f"existing final destination differs: {FINAL_DIR}")
        core.publish_directory_no_replace(BUNDLE_DIR, FINAL_DIR)
    except Exception:
        if manifest_path.exists() and BUNDLE_DIR.exists():
            manifest_path.unlink()
        raise
    print(f"published atomically -> {FINAL_DIR}", flush=True)


def validate_prepared() -> None:
    _ensure_stage(); config, folds, derived, prepare_receipt = _load_preparation()
    dataset = _rebuild_and_validate_preparation(config, folds, derived, prepare_receipt)
    print(f"prepared authority/config/folds/derived/draws PASS: {dataset.n} rows", flush=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "validate-prepared", "analyze", "finalize"))
    return parser.parse_args(argv)


def _failure_receipt_path(command: str) -> Path:
    if command not in {"prepare", "validate-prepared", "analyze", "finalize"}:
        raise core.AnalysisError(f"unknown failure-receipt command: {command}")
    return PARENT_DIR / f".{BUNDLE_ID}.{command}.FAILED.json"


def main(argv: Sequence[str] | None = None) -> None:
    command = parse_args(argv).command
    failure_path = _failure_receipt_path(command)
    try:
        {"prepare": prepare, "validate-prepared": validate_prepared, "analyze": analyze, "finalize": finalize}[command]()
    except Exception as exc:
        failure = core.payload_with_hash({
            "schema": "actual_incremental_sensitivity.failure", "schema_version": 1,
            "state": "failed", "bundle_id": BUNDLE_ID, "command": command,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "exception_type": type(exc).__name__, "message": str(exc),
            "traceback": traceback.format_exc(),
            "staging_path": str(BUNDLE_DIR), "final_published": FINAL_DIR.exists(),
        })
        core.replace_json(failure_path, failure)
        raise
    else:
        if core.path_lexists(failure_path):
            previous_failure = core.strict_json_load(failure_path)
            core.verify_payload_hash(previous_failure)
            if previous_failure.get("command") != command:
                raise core.AnalysisError("command-scoped failure receipt command differs")
            failure_path.unlink()


if __name__ == "__main__":
    main()
