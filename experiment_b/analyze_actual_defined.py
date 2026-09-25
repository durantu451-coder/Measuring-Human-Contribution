# -*- coding: utf-8 -*-
"""Offline, immutable Experiment B analysis with source-actual-defined levels.

This module derives labels and statistics from stored canonical ratios only.  It
never calls an API, generates text, recompresses text, uses Astra, or mutates
Experiment B.  Historical excess-defined labels remain bound as a sensitivity
comparison.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import math
import os
import platform
import shutil
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.stats import kendalltau, rankdata, spearmanr

try:
    from experiment_b import analyze_actual_vs_excess as base
    from experiment_b import storage
    from experiment_b.validation_schema import (
        COMPRESSORS,
        LEVELS,
        LineageManifest,
        ValidationSchemaError,
        assert_no_nonfinite_numbers,
        strict_json_loads,
    )
except ModuleNotFoundError:  # Direct execution from experiment_b/.
    import analyze_actual_vs_excess as base  # type: ignore[no-redef]
    import storage  # type: ignore[no-redef]
    from validation_schema import (  # type: ignore[no-redef]
        COMPRESSORS,
        LEVELS,
        LineageManifest,
        ValidationSchemaError,
        assert_no_nonfinite_numbers,
        strict_json_loads,
    )


SCHEMA = "experiment_b.actual_defined"
SCHEMA_VERSION = 1
ROSTER_SCHEMA = f"{SCHEMA}.roster"
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
OUTPUTS = HERE / "outputs"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "derived_outputs" / "experiment_b_actual_defined"
DATASETS = ("10k_prompts", "wildchat", "oasst1")
CATEGORIES = (
    "技术实现",
    "专业知识",
    "推理分析",
    "创意生成",
    "艺术设计",
    "经验情境",
)
LEVEL_NUMBER = {level: index + 1 for index, level in enumerate(LEVELS)}
LEVEL_LABEL = {level: float(len(LEVELS) - index) for index, level in enumerate(LEVELS)}
BASE_ANALYZER_SHA256 = "c22158ae71902d6f0eb96f74d469237121be67b8ebe465e9ccb2fbd5e620649d"
EXPECTED_MAPPING_SHA256 = "2acf7aa9b4b578a7c6081f0cb41ef6f6726b264479045a552e87ba4f14387b3a"
EXPECTED_ROSTER_SHA256 = "7928eb3b0e36b6cf7d9c4c9d254765ddecb3c955307288cd8b3a88a1971046e9"
EXPECTED_CHANGED = 4257
EXPECTED_LEVEL_COUNTS = {"L1": 1307, "L2": 1307, "L3": 1307, "L4": 1307, "L5": 1341}
EXPECTED_DATASET_LEVEL_COUNTS = {
    "10k_prompts": {"L1": 506, "L2": 506, "L3": 506, "L4": 506, "L5": 522},
    "wildchat": {"L1": 521, "L2": 521, "L3": 521, "L4": 521, "L5": 535},
    "oasst1": {"L1": 280, "L2": 280, "L3": 280, "L4": 280, "L5": 284},
}
BOUNDARY_TIE = {
    "dataset": "10k_prompts",
    "category": "专业知识",
    "score": 0.045062320230105514,
    "higher_id": "10k_06601",
    "higher_level": "L4",
    "lower_id": "10k_06496",
    "lower_level": "L5",
}
ROSTER_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "id",
        "dataset",
        "category",
        "pipeline_ordinal",
        "source_row_sha256",
        "source_actual_ratio",
        "cell_rank",
        "cell_size",
        "floor_level_size",
        "historical_excess_level",
        "actual_defined_level",
        "changed",
    }
)
HISTORICAL_SNAPSHOT = (
    PROJECT_ROOT
    / "derived_outputs"
    / "experiment_b_actual_excess"
    / "1920262552aaea5823bfcfbb1df9cb9cac81280591d6aef1381541578ee3613b"
    / "20260910T135636Z_308b73376289"
)
HISTORICAL_HASHES = {
    "manifest.json": "843bb301b00a7b4e099bac3a0fee2beb7161c16efc3b82196b5fde70789a7d26",
    "metrics.json": "29e8ab5784526917fcbbf2c28f7e0baac72b899fdc936e70aa928396362306bc",
    "metrics.csv": "bd8c5bed99cbff076a35b7aa5ef390d11e7cb94be48814242f9090a7e63cf703",
}
LABEL_METRICS = (
    "spearman_rho",
    "kendall_tau_b",
    "alpha_z",
    "alpha_rank",
)
MIN_PUBLICATION_REPLICATES = 1000


class ActualDefinedError(RuntimeError):
    """Raised when an input, estimand, statistic, or publication invariant fails."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite(value: Any, path: str) -> float:
    if not base._is_finite_number(value):
        raise ActualDefinedError(f"{path} must be a finite non-boolean number")
    return float(value)


def _same(left: float, right: float, *, atol: float = 1e-12) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=atol)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _strict_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ActualDefinedError(f"cannot read strict UTF-8 JSONL {path}: {exc}") from exc
    if not payload or not payload.endswith(b"\n"):
        raise ActualDefinedError(f"JSONL lacks final LF: {path}")
    physical_lines = text.split("\n")
    if physical_lines[-1] != "":
        raise ActualDefinedError(f"JSONL lacks terminal physical LF: {path}")
    for line_number, raw_line in enumerate(physical_lines[:-1], 1):
        line = raw_line + "\n"
        if not raw_line.strip():
            raise ActualDefinedError(f"invalid JSONL row at {path}:{line_number}")
        try:
            value = strict_json_loads(line, path=f"{path}:{line_number}")
            assert_no_nonfinite_numbers(value, f"{path}:{line_number}")
        except ValidationSchemaError as exc:
            raise ActualDefinedError(str(exc)) from exc
        if not isinstance(value, Mapping):
            raise ActualDefinedError(f"row is not an object at {path}:{line_number}")
        row = dict(value)
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ActualDefinedError(f"invalid ID at {path}:{line_number}")
        if item_id in seen:
            raise ActualDefinedError(f"duplicate ID {item_id!r} at {path}:{line_number}")
        seen.add(item_id)
        rows.append(row)
    record = {
        "path": str(path.resolve()),
        "sha256": storage.sha256_bytes(payload),
        "size": len(payload),
        "row_count": len(rows),
    }
    return rows, record


def _without_level(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("level", None)
    return result


def _require_base_sha() -> dict[str, Any]:
    path = Path(base.__file__).resolve()
    observed = storage.file_sha256(path)
    if observed != BASE_ANALYZER_SHA256:
        raise ActualDefinedError(
            f"completed base analyzer drift: {observed} != {BASE_ANALYZER_SHA256}"
        )
    return {"path": str(path), "sha256": observed, "size": path.stat().st_size}


def _authenticate_role(
    *,
    lineage: LineageManifest,
    role: str,
    declaration_key: str,
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    parsed_record: Mapping[str, Any],
) -> dict[str, Any]:
    official = lineage.raw.get("official_files")
    per_id_all = lineage.raw.get("per_id_canonical_hashes")
    if not isinstance(official, Mapping) or not isinstance(per_id_all, Mapping):
        raise ActualDefinedError("active lineage lacks source authentication maps")
    declaration = official.get(declaration_key)
    expected_ids = per_id_all.get(role)
    if not isinstance(declaration, Mapping) or not isinstance(expected_ids, Mapping):
        raise ActualDefinedError(f"active lineage lacks declarations for {role}")
    observed = dict(parsed_record)
    if observed.get("row_count") != len(rows):
        raise ActualDefinedError(f"parsed source record count failed for {role}")
    expected = {
        "role": role,
        "row_count": len(rows),
        "sha256": observed["sha256"],
        "size": observed["size"],
    }
    if any(declaration.get(key) != value for key, value in expected.items()):
        raise ActualDefinedError(f"whole-file lineage authentication failed for {role}")
    by_id = {str(row["id"]): row for row in rows}
    if set(by_id) != set(expected_ids):
        raise ActualDefinedError(f"per-ID lineage roster failed for {role}")
    for item_id, row in by_id.items():
        if storage.canonical_row_sha256(row) != expected_ids.get(item_id):
            raise ActualDefinedError(f"per-ID lineage hash failed for {role}/{item_id}")
    current = base._stream_file_record(path, jsonl=True)
    for key in ("path", "sha256", "size", "row_count"):
        if current.get(key) != observed.get(key):
            raise ActualDefinedError(f"source file changed after parsing for {role}")
    return {
        "role": role,
        "declaration_key": declaration_key,
        "path": str(path.resolve()),
        "sha256": observed["sha256"],
        "size": observed["size"],
        "row_count": len(rows),
        "per_id_mapping_sha256": storage.sha256_bytes(
            storage.canonical_json_bytes(dict(expected_ids))
        ),
    }


def load_source_inputs(
    lineage: LineageManifest, *, output_dir: Path = OUTPUTS
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    pipelines: dict[str, list[dict[str, Any]]] = {}
    historical: dict[str, dict[str, Any]] = {}
    authentication: dict[str, dict[str, Any]] = {}
    global_ids: set[str] = set()
    for dataset in DATASETS:
        pipeline_path = output_dir / f"{dataset}_pipeline.jsonl"
        stratified_path = output_dir / f"{dataset}_stratified.jsonl"
        pipeline_rows, pipeline_record = _strict_jsonl(pipeline_path)
        stratified_rows, stratified_record = _strict_jsonl(stratified_path)
        expected_count = base.EXPECTED_DATASET_COUNTS[dataset]
        if len(pipeline_rows) != expected_count or len(stratified_rows) != expected_count:
            raise ActualDefinedError(f"source count drift for {dataset}")
        authentication[f"pipeline:{dataset}"] = _authenticate_role(
            lineage=lineage,
            role=f"pipeline:{dataset}",
            declaration_key=f"outputs/{dataset}_pipeline.jsonl",
            path=pipeline_path,
            rows=pipeline_rows,
            parsed_record=pipeline_record,
        )
        authentication[f"stratified:{dataset}"] = _authenticate_role(
            lineage=lineage,
            role=f"stratified:{dataset}",
            declaration_key=f"outputs/{dataset}_stratified.jsonl",
            path=stratified_path,
            rows=stratified_rows,
            parsed_record=stratified_record,
        )
        pipe_index = {str(row["id"]): row for row in pipeline_rows}
        strat_index = {str(row["id"]): row for row in stratified_rows}
        if set(pipe_index) != set(strat_index):
            raise ActualDefinedError(f"pipeline/stratified ID mismatch for {dataset}")
        for ordinal, row in enumerate(pipeline_rows):
            item_id = str(row["id"])
            if item_id in global_ids:
                raise ActualDefinedError(f"duplicate source ID across datasets: {item_id}")
            global_ids.add(item_id)
            if row.get("dataset") != dataset or row.get("status") != "ok":
                raise ActualDefinedError(f"invalid pipeline identity/status for {item_id}")
            if row.get("category") not in CATEGORIES:
                raise ActualDefinedError(f"invalid category for {item_id}")
            base.validate_source_row(row, path=f"pipeline[{item_id!r}]")
            old = strat_index[item_id]
            if old.get("level") not in LEVELS:
                raise ActualDefinedError(f"invalid historical level for {item_id}")
            if storage.canonical_row_sha256(row) != storage.canonical_row_sha256(
                _without_level(old)
            ):
                raise ActualDefinedError(
                    f"stratified row differs outside level for {dataset}/{item_id}"
                )
            historical[item_id] = {
                "row": old,
                "level": str(old["level"]),
                "pipeline_ordinal": ordinal,
            }
        pipelines[dataset] = pipeline_rows
    if len(global_ids) != base.EXPECTED_SOURCE_TOTAL:
        raise ActualDefinedError("source universe count drift")
    return pipelines, historical, authentication


def stratify_actual_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    dataset: str,
    historical: Mapping[str, Mapping[str, Any]],
    categories: Sequence[str] = CATEGORIES,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for category in categories:
        pool: list[tuple[int, Mapping[str, Any], float]] = []
        for ordinal, row in enumerate(rows):
            if row.get("category") != category:
                continue
            item_id = str(row.get("id"))
            score = _finite(row.get("actual_ratio"), f"pipeline[{item_id}].actual_ratio")
            pool.append((ordinal, row, score))
        pool.sort(key=lambda value: value[2], reverse=True)
        cell_size = len(pool)
        q = cell_size // len(LEVELS)
        for rank_zero, (ordinal, row, score) in enumerate(pool):
            level_index = min(rank_zero // q, len(LEVELS) - 1) if q else len(LEVELS) - 1
            actual_level = LEVELS[level_index]
            item_id = str(row["id"])
            old = historical.get(item_id)
            if not isinstance(old, Mapping):
                raise ActualDefinedError(f"missing historical label for {item_id}")
            old_level = old.get("level")
            if old.get("pipeline_ordinal") != ordinal or old_level not in LEVELS:
                raise ActualDefinedError(f"historical source binding failed for {item_id}")
            if item_id in seen:
                raise ActualDefinedError(f"duplicate derived source ID {item_id}")
            seen.add(item_id)
            result.append(
                {
                    "schema": ROSTER_SCHEMA,
                    "schema_version": SCHEMA_VERSION,
                    "id": item_id,
                    "dataset": dataset,
                    "category": category,
                    "pipeline_ordinal": ordinal,
                    "source_row_sha256": storage.canonical_row_sha256(row),
                    "source_actual_ratio": score,
                    "cell_rank": rank_zero + 1,
                    "cell_size": cell_size,
                    "floor_level_size": q,
                    "historical_excess_level": old_level,
                    "actual_defined_level": actual_level,
                    "changed": actual_level != old_level,
                }
            )
    if len(result) != len(rows):
        raise ActualDefinedError(f"not every {dataset} row received an actual-defined level")
    return result


def build_actual_roster(
    pipelines: Mapping[str, Sequence[Mapping[str, Any]]],
    historical: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset in DATASETS:
        rows.extend(
            stratify_actual_rows(
                pipelines[dataset], dataset=dataset, historical=historical
            )
        )
    by_id = {row["id"]: row for row in rows}
    if len(rows) != base.EXPECTED_SOURCE_TOTAL or len(by_id) != len(rows):
        raise ActualDefinedError("actual-defined roster coverage differs")
    mapping = {
        item_id: by_id[item_id]["actual_defined_level"] for item_id in sorted(by_id)
    }
    mapping_sha = storage.sha256_bytes(storage.canonical_json_bytes(mapping))
    level_counts = Counter(row["actual_defined_level"] for row in rows)
    changed = sum(bool(row["changed"]) for row in rows)
    dataset_counts = {
        dataset: {
            level: sum(
                row["dataset"] == dataset and row["actual_defined_level"] == level
                for row in rows
            )
            for level in LEVELS
        }
        for dataset in DATASETS
    }
    transition = {
        old: {
            new: sum(
                row["historical_excess_level"] == old
                and row["actual_defined_level"] == new
                for row in rows
            )
            for new in LEVELS
        }
        for old in LEVELS
    }
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[(str(row["dataset"]), str(row["category"]))].append(row)
    cross_cut_ties: list[dict[str, Any]] = []
    for (dataset, category), cell in sorted(cells.items()):
        ordered = sorted(cell, key=lambda row: int(row["cell_rank"]))
        for higher, lower in zip(ordered, ordered[1:]):
            if (
                higher["actual_defined_level"] != lower["actual_defined_level"]
                and _same(
                    float(higher["source_actual_ratio"]),
                    float(lower["source_actual_ratio"]),
                    atol=0.0,
                )
            ):
                cross_cut_ties.append(
                    {
                        "dataset": dataset,
                        "category": category,
                        "score": float(higher["source_actual_ratio"]),
                        "higher_id": higher["id"],
                        "higher_level": higher["actual_defined_level"],
                        "lower_id": lower["id"],
                        "lower_level": lower["actual_defined_level"],
                    }
                )
    diagnostics = {
        "mapping_sha256": mapping_sha,
        "source_n": len(rows),
        "changed_n": changed,
        "level_counts": {level: level_counts[level] for level in LEVELS},
        "dataset_level_counts": dataset_counts,
        "historical_to_actual_transition": transition,
        "cross_cut_ties": cross_cut_ties,
    }
    return sorted(rows, key=lambda row: str(row["id"])), diagnostics


def validate_production_roster(
    roster: Sequence[Mapping[str, Any]], diagnostics: Mapping[str, Any]
) -> None:
    if diagnostics.get("mapping_sha256") != EXPECTED_MAPPING_SHA256:
        raise ActualDefinedError("production actual-level mapping SHA drift")
    if diagnostics.get("source_n") != base.EXPECTED_SOURCE_TOTAL:
        raise ActualDefinedError("production roster source count drift")
    if diagnostics.get("changed_n") != EXPECTED_CHANGED:
        raise ActualDefinedError("production changed-level count drift")
    if diagnostics.get("level_counts") != EXPECTED_LEVEL_COUNTS:
        raise ActualDefinedError("production level count drift")
    if diagnostics.get("dataset_level_counts") != EXPECTED_DATASET_LEVEL_COUNTS:
        raise ActualDefinedError("production dataset-level count drift")
    if diagnostics.get("cross_cut_ties") != [BOUNDARY_TIE]:
        raise ActualDefinedError("production cross-cut tie roster drift")
    by_id = {str(row["id"]): row for row in roster}
    high = by_id.get(BOUNDARY_TIE["higher_id"])
    low = by_id.get(BOUNDARY_TIE["lower_id"])
    if not isinstance(high, Mapping) or not isinstance(low, Mapping):
        raise ActualDefinedError("production boundary-tie IDs are missing")
    for row, expected_id, expected_level in (
        (high, BOUNDARY_TIE["higher_id"], BOUNDARY_TIE["higher_level"]),
        (low, BOUNDARY_TIE["lower_id"], BOUNDARY_TIE["lower_level"]),
    ):
        if (
            row.get("dataset") != BOUNDARY_TIE["dataset"]
            or row.get("category") != BOUNDARY_TIE["category"]
            or row.get("id") != expected_id
            or row.get("actual_defined_level") != expected_level
            or not _same(float(row["source_actual_ratio"]), float(BOUNDARY_TIE["score"]), atol=0.0)
        ):
            raise ActualDefinedError("production boundary-tie disposition drift")
    if int(high["pipeline_ordinal"]) >= int(low["pipeline_ordinal"]):
        raise ActualDefinedError("production boundary tie no longer follows pipeline order")


def roster_jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(storage.canonical_jsonl_row_bytes(row) for row in rows)


def validate_roster_bytes(
    payload: bytes, metrics_roster: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if storage.sha256_bytes(payload) != EXPECTED_ROSTER_SHA256:
        raise ActualDefinedError("serialized production roster SHA drift")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActualDefinedError("serialized roster is not UTF-8") from exc
    if not payload.endswith(b"\n"):
        raise ActualDefinedError("serialized roster lacks final LF")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    physical_lines = text.split("\n")
    if physical_lines[-1] != "":
        raise ActualDefinedError("serialized roster lacks terminal physical LF")
    for line_number, raw_line in enumerate(physical_lines[:-1], 1):
        line = raw_line + "\n"
        if not raw_line.strip():
            raise ActualDefinedError(f"invalid serialized roster row {line_number}")
        try:
            value = strict_json_loads(line, path=f"roster.jsonl:{line_number}")
            assert_no_nonfinite_numbers(value, f"roster.jsonl:{line_number}")
        except ValidationSchemaError as exc:
            raise ActualDefinedError(str(exc)) from exc
        if not isinstance(value, Mapping) or set(value) != ROSTER_FIELDS:
            raise ActualDefinedError(f"serialized roster schema differs at row {line_number}")
        row = dict(value)
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            raise ActualDefinedError(f"serialized roster ID differs at row {line_number}")
        seen.add(item_id)
        if (
            row.get("schema") != ROSTER_SCHEMA
            or row.get("schema_version") != SCHEMA_VERSION
            or row.get("dataset") not in DATASETS
            or row.get("category") not in CATEGORIES
            or row.get("historical_excess_level") not in LEVELS
            or row.get("actual_defined_level") not in LEVELS
            or type(row.get("changed")) is not bool
            or row["changed"]
            != (row["historical_excess_level"] != row["actual_defined_level"])
            or not _is_sha256(row.get("source_row_sha256"))
        ):
            raise ActualDefinedError(f"serialized roster identity differs at row {line_number}")
        for name in ("pipeline_ordinal", "cell_rank", "cell_size", "floor_level_size"):
            if type(row.get(name)) is not int or int(row[name]) < 0:
                raise ActualDefinedError(
                    f"serialized roster integer field differs at row {line_number}/{name}"
                )
        if (
            int(row["cell_rank"]) < 1
            or int(row["cell_rank"]) > int(row["cell_size"])
            or int(row["floor_level_size"]) != int(row["cell_size"]) // len(LEVELS)
        ):
            raise ActualDefinedError(f"serialized roster rank differs at row {line_number}")
        _finite(row.get("source_actual_ratio"), f"roster.jsonl:{line_number}.source_actual_ratio")
        rows.append(row)
    if len(rows) != base.EXPECTED_SOURCE_TOTAL:
        raise ActualDefinedError("serialized roster row count differs")
    if [row["id"] for row in rows] != sorted(seen):
        raise ActualDefinedError("serialized roster is not in canonical ID order")
    if roster_jsonl_bytes(rows) != payload:
        raise ActualDefinedError("serialized roster is not canonical JSONL")
    mapping = {row["id"]: row["actual_defined_level"] for row in rows}
    mapping_sha = storage.sha256_bytes(storage.canonical_json_bytes(mapping))
    level_counts = {
        level: sum(row["actual_defined_level"] == level for row in rows)
        for level in LEVELS
    }
    dataset_counts = {
        dataset: {
            level: sum(
                row["dataset"] == dataset and row["actual_defined_level"] == level
                for row in rows
            )
            for level in LEVELS
        }
        for dataset in DATASETS
    }
    if (
        mapping_sha != EXPECTED_MAPPING_SHA256
        or sum(bool(row["changed"]) for row in rows) != EXPECTED_CHANGED
        or level_counts != EXPECTED_LEVEL_COUNTS
        or dataset_counts != EXPECTED_DATASET_LEVEL_COUNTS
    ):
        raise ActualDefinedError("serialized roster production invariants differ")
    expected_metrics = {
        "mapping_sha256": mapping_sha,
        "source_n": len(rows),
        "changed_n": EXPECTED_CHANGED,
        "level_counts": level_counts,
        "dataset_level_counts": dataset_counts,
        "roster_artifact": "roster.jsonl",
    }
    if any(metrics_roster.get(key) != value for key, value in expected_metrics.items()):
        raise ActualDefinedError("serialized roster disagrees with metrics")
    by_id = {row["id"]: row for row in rows}
    high = by_id[BOUNDARY_TIE["higher_id"]]
    low = by_id[BOUNDARY_TIE["lower_id"]]
    if (
        high["actual_defined_level"] != BOUNDARY_TIE["higher_level"]
        or low["actual_defined_level"] != BOUNDARY_TIE["lower_level"]
        or not _same(
            float(high["source_actual_ratio"]), float(BOUNDARY_TIE["score"]), atol=0.0
        )
        or not _same(
            float(low["source_actual_ratio"]), float(BOUNDARY_TIE["score"]), atol=0.0
        )
    ):
        raise ActualDefinedError("serialized roster boundary tie differs")
    return rows


def _label_vectors(
    rows: Sequence[Mapping[str, Any]], label_key: str
) -> tuple[np.ndarray, np.ndarray]:
    labels = np.asarray([LEVEL_LABEL[str(row[label_key])] for row in rows], dtype=float)
    measured = np.asarray([float(row["validation_actual"]) for row in rows], dtype=float)
    if len(labels) == 0 or not np.all(np.isfinite(labels)) or not np.all(np.isfinite(measured)):
        raise ActualDefinedError("label metric vectors are empty or non-finite")
    return labels, measured


def _label_estimates(labels: np.ndarray, measured: np.ndarray) -> dict[str, float]:
    if len(labels) < 2 or np.ptp(labels) == 0.0 or np.ptp(measured) == 0.0:
        raise ActualDefinedError("label estimator is undefined")
    rho = spearmanr(labels, measured)
    tau = kendalltau(labels, measured)
    labels_z = (labels - labels.mean()) / labels.std(ddof=1)
    measured_z = (measured - measured.mean()) / measured.std(ddof=1)
    alpha_z = base._krippendorff_interval_exact(
        np.column_stack([labels_z, measured_z])
    )
    labels_rank = rankdata(labels, method="average")
    measured_rank = rankdata(measured, method="average")
    alpha_rank = base._krippendorff_interval_exact(
        np.column_stack([labels_rank, measured_rank])
    )
    result = {
        "spearman_rho": float(rho.statistic),
        "spearman_p": float(rho.pvalue),
        "kendall_tau_b": float(tau.statistic),
        "kendall_p": float(tau.pvalue),
        "alpha_z": float(alpha_z),
        "alpha_rank": float(alpha_rank),
    }
    if not all(math.isfinite(value) for value in result.values()):
        raise ActualDefinedError("label estimator returned a non-finite result")
    return result


def label_agreement(
    rows: Sequence[Mapping[str, Any]],
    label_key: str,
    *,
    require_defined: bool = True,
) -> dict[str, Any]:
    labels, measured = _label_vectors(rows, label_key)
    missing = [level for level in LEVELS if not any(row[label_key] == level for row in rows)]
    if len(labels) < 2 or np.ptp(labels) == 0.0 or np.ptp(measured) == 0.0:
        warning = (
            "label agreement undefined because n < 2 or at least one vector is constant"
        )
        if require_defined:
            raise ActualDefinedError(warning)
        return {
            "n": len(rows),
            "spearman_rho": None,
            "spearman_p": None,
            "kendall_tau_b": None,
            "kendall_p": None,
            "alpha_z": None,
            "alpha_rank": None,
            "missing_levels": missing,
            "estimator": "global_pooled_adaptation",
            "warnings": [warning],
        }
    result = _label_estimates(labels, measured)
    return {
        "n": len(rows),
        **result,
        "missing_levels": missing,
        "estimator": "global_pooled_adaptation",
        "warnings": [],
    }


def _summary(values: Sequence[float]) -> dict[str, Any]:
    return base._summary(values)


def level_gradient(
    rows: Sequence[Mapping[str, Any]], label_key: str
) -> dict[str, Any]:
    order = np.asarray([float(LEVEL_NUMBER[str(row[label_key])]) for row in rows])
    measured = np.asarray([float(row["validation_actual"]) for row in rows])
    result = base.continuous_metrics(
        order.tolist(),
        measured.tolist(),
        left_label="level_order",
        right_label="validation_actual",
    )
    by_level = {
        level: _summary(
            [float(row["validation_actual"]) for row in rows if row[label_key] == level]
        )
        for level in LEVELS
    }
    means = [by_level[level]["mean"] for level in LEVELS]
    strict = (
        all(float(means[index]) > float(means[index + 1]) for index in range(4))
        if all(value is not None for value in means)
        else None
    )
    return {
        "n": len(rows),
        "spearman_rho": result["spearman_rho"],
        "spearman_p": result["spearman_p"],
        "kendall_tau_b": result["kendall_tau_b"],
        "kendall_p": result["kendall_p"],
        "by_level": by_level,
        "strictly_decreasing_level_means": strict,
        "warnings": result["warnings"],
    }


def attach_actual_levels(
    rows_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    roster: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    labels = {str(row["id"]): str(row["actual_defined_level"]) for row in roster}
    historical = {str(row["id"]): str(row["historical_excess_level"]) for row in roster}
    result: dict[str, list[dict[str, Any]]] = {}
    for model, rows in rows_by_model.items():
        attached: list[dict[str, Any]] = []
        for row in rows:
            item_id = str(row["id"])
            if item_id not in labels or str(row["level"]) != historical[item_id]:
                raise ActualDefinedError(f"validation label crosswalk failed for {model}/{item_id}")
            value = dict(row)
            value["actual_defined_level"] = labels[item_id]
            value["historical_excess_level"] = historical[item_id]
            attached.append(value)
        result[model] = sorted(attached, key=lambda row: str(row["id"]))
    return result


def label_definition_bootstrap(
    rows_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    cohort_name: str,
    replicates: int,
    master_seed: int,
) -> dict[str, Any]:
    if type(replicates) is not int or replicates <= 0:
        raise ActualDefinedError("bootstrap replicates must be positive")
    models = list(rows_by_model)
    if not models:
        raise ActualDefinedError("bootstrap needs at least one model")
    ordered = {
        model: sorted(rows, key=lambda row: str(row["id"]))
        for model, rows in rows_by_model.items()
    }
    ids = [str(row["id"]) for row in ordered[models[0]]]
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise ActualDefinedError("bootstrap IDs are too small or duplicated")
    for model in models[1:]:
        if [str(row["id"]) for row in ordered[model]] != ids:
            raise ActualDefinedError("common bootstrap model ID rosters differ")
    strata: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(ordered[models[0]]):
        strata[(str(row["dataset"]), str(row["category"]))].append(index)
    arrays: dict[str, dict[str, np.ndarray]] = {}
    for model, rows in ordered.items():
        arrays[model] = {
            "actual_label": np.asarray(
                [LEVEL_LABEL[str(row["actual_defined_level"])] for row in rows]
            ),
            "historical_label": np.asarray(
                [LEVEL_LABEL[str(row["historical_excess_level"])] for row in rows]
            ),
            "validation_actual": np.asarray(
                [float(row["validation_actual"]) for row in rows]
            ),
        }
    rng = np.random.default_rng(base._cohort_seed(master_seed, cohort_name))
    samples = {
        model: {
            f"{definition}.{metric}": []
            for definition in ("actual_defined", "historical_excess_defined")
            for metric in LABEL_METRICS
        }
        | {f"delta.{metric}": [] for metric in LABEL_METRICS}
        for model in models
    }
    strata_arrays = [np.asarray(strata[key], dtype=int) for key in sorted(strata)]
    undefined = 0
    for _ in range(replicates):
        sampled = np.concatenate(
            [rng.choice(indices, size=len(indices), replace=True) for indices in strata_arrays]
        )
        replicate_values: dict[str, tuple[dict[str, float], dict[str, float]]] = {}
        try:
            for model in models:
                values = arrays[model]
                actual = _label_estimates(
                    values["actual_label"][sampled], values["validation_actual"][sampled]
                )
                historical = _label_estimates(
                    values["historical_label"][sampled], values["validation_actual"][sampled]
                )
                replicate_values[model] = (actual, historical)
        except ActualDefinedError:
            undefined += 1
            continue
        for model, (actual, historical) in replicate_values.items():
            for metric in LABEL_METRICS:
                samples[model][f"actual_defined.{metric}"].append(actual[metric])
                samples[model][f"historical_excess_defined.{metric}"].append(
                    historical[metric]
                )
                samples[model][f"delta.{metric}"].append(
                    actual[metric] - historical[metric]
                )
    valid = replicates - undefined
    if valid < math.ceil(replicates * 0.99):
        raise ActualDefinedError(
            f"fewer than 99% bootstrap replicates valid: {valid}/{replicates}"
        )
    return {
        "method": "paired_source_id_percentile_bootstrap",
        "confidence_level": 0.95,
        "replicates_requested": replicates,
        "replicates_attempted": replicates,
        "replicates_valid": valid,
        "undefined_replicates": undefined,
        "minimum_valid_fraction": 0.99,
        "master_seed": master_seed,
        "cohort_seed": base._cohort_seed(master_seed, cohort_name),
        "sampling_unit": "source_id",
        "strata": ["dataset", "category"],
        "level_used_as_stratum": False,
        "roster_recomputed_inside_replicate": False,
        "models_share_sampled_ids": len(models) > 1,
        "models": {
            model: {
                "actual_defined": {
                    metric: base._percentile_interval(
                        samples[model][f"actual_defined.{metric}"]
                    )
                    for metric in LABEL_METRICS
                },
                "historical_excess_defined": {
                    metric: base._percentile_interval(
                        samples[model][f"historical_excess_defined.{metric}"]
                    )
                    for metric in LABEL_METRICS
                },
                "delta_actual_defined_minus_historical": {
                    metric: base._percentile_interval(samples[model][f"delta.{metric}"])
                    for metric in LABEL_METRICS
                },
            }
            for model in models
        },
    }


def _derived_cohort_description(
    original: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    description = {
        key: copy.deepcopy(value)
        for key, value in original.items()
        if key != "level_counts"
    }
    if description.get("n_source_ids") != len(rows):
        raise ActualDefinedError("cohort description count differs from attached rows")
    ids = sorted(str(row["id"]) for row in rows)
    if description.get("id_roster_sha256") != base._id_roster_hash(ids):
        raise ActualDefinedError("cohort description roster hash differs")
    description["actual_defined_level_counts"] = {
        level: sum(row["actual_defined_level"] == level for row in rows)
        for level in LEVELS
    }
    description["historical_excess_level_counts"] = {
        level: sum(row["historical_excess_level"] == level for row in rows)
        for level in LEVELS
    }
    return description


def _filter_ids(
    rows: Sequence[Mapping[str, Any]], ids: set[str]
) -> list[Mapping[str, Any]]:
    selected = sorted(
        (row for row in rows if str(row["id"]) in ids),
        key=lambda row: str(row["id"]),
    )
    if len(selected) != len(ids):
        raise ActualDefinedError("cohort filter did not return one row per ID")
    return selected


def _definition_comparison(
    rows: Sequence[Mapping[str, Any]],
    bootstrap_ci: Mapping[str, Any],
    *,
    require_defined: bool = True,
) -> dict[str, Any]:
    actual = label_agreement(
        rows, "actual_defined_level", require_defined=require_defined
    )
    historical = label_agreement(
        rows, "historical_excess_level", require_defined=require_defined
    )
    delta = {
        metric: (
            float(actual[metric]) - float(historical[metric])
            if actual[metric] is not None and historical[metric] is not None
            else None
        )
        for metric in LABEL_METRICS
    }
    return {
        "n": len(rows),
        "actual_defined": actual,
        "historical_excess_defined": historical,
        "delta_actual_defined_minus_historical": delta,
        "bootstrap_ci": dict(bootstrap_ci),
    }


def _split_reports(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("dataset", "category", "protocol_group"):
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        result[f"by_{field}"] = {
            name: {
                "n": len(group),
                "definition_comparison": _definition_comparison(
                    group, {}, require_defined=False
                ),
                "actual_defined_gradient": level_gradient(group, "actual_defined_level"),
            }
            for name, group in sorted(groups.items())
        }
    return result


def _compressor_actual_diagnostics(
    rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    matrix = np.asarray(
        [
            [float(row["per_compressor"][name]["actual"]) for name in COMPRESSORS]
            for row in rows
        ],
        dtype=float,
    )
    alpha = base._krippendorff_interval_exact(matrix)
    return {
        "n": len(rows),
        "krippendorff_alpha_interval": float(alpha),
        "by_actual_defined_level": {
            level: {
                "n": sum(row["actual_defined_level"] == level for row in rows),
                "krippendorff_alpha_interval": float(
                    base._krippendorff_interval_exact(
                        np.asarray(
                            [
                                [
                                    float(row["per_compressor"][name]["actual"])
                                    for name in COMPRESSORS
                                ]
                                for row in rows
                                if row["actual_defined_level"] == level
                            ],
                            dtype=float,
                        )
                    )
                ),
            }
            for level in LEVELS
        },
        "per_compressor": {
            name: {
                "overall": _summary(
                    [float(row["per_compressor"][name]["actual"]) for row in rows]
                ),
                "by_actual_defined_level": {
                    level: _summary(
                        [
                            float(row["per_compressor"][name]["actual"])
                            for row in rows
                            if row["actual_defined_level"] == level
                        ]
                    )
                    for level in LEVELS
                },
            }
            for name in COMPRESSORS
        },
    }


def load_historical_snapshot(
    *, snapshot: Path = HISTORICAL_SNAPSHOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    records: dict[str, Any] = {}
    for name, expected_sha in HISTORICAL_HASHES.items():
        path = snapshot / name
        if not path.is_file():
            raise ActualDefinedError(f"historical snapshot artifact is missing: {path}")
        observed = storage.file_sha256(path)
        if observed != expected_sha:
            raise ActualDefinedError(f"historical snapshot hash drift for {name}")
        records[name] = {
            "path": str(path.resolve()),
            "sha256": observed,
            "size": path.stat().st_size,
        }
    try:
        manifest = strict_json_loads(
            (snapshot / "manifest.json").read_text(encoding="utf-8"),
            path=str(snapshot / "manifest.json"),
        )
        metrics = strict_json_loads(
            (snapshot / "metrics.json").read_text(encoding="utf-8"),
            path=str(snapshot / "metrics.json"),
        )
    except ValidationSchemaError as exc:
        raise ActualDefinedError(str(exc)) from exc
    if not isinstance(manifest, Mapping) or not isinstance(metrics, Mapping):
        raise ActualDefinedError("historical snapshot JSON is not an object")
    if (
        manifest.get("schema") != f"{base.SCHEMA}.manifest"
        or manifest.get("schema_version") != base.SCHEMA_VERSION
        or manifest.get("state") != "DERIVED_SNAPSHOT_COMPLETE"
        or metrics.get("schema") != base.SCHEMA
        or metrics.get("schema_version") != base.SCHEMA_VERSION
        or metrics.get("state") != "DERIVED_SNAPSHOT_COMPLETE"
    ):
        raise ActualDefinedError("historical snapshot schema/state is invalid")
    expected_lineage_sha = HISTORICAL_SNAPSHOT.parent.name
    manifest_lineage = manifest.get("active_lineage")
    metrics_lineage = metrics.get("active_lineage")
    if (
        not isinstance(manifest_lineage, Mapping)
        or not isinstance(metrics_lineage, Mapping)
        or storage.canonical_json_bytes(manifest_lineage)
        != storage.canonical_json_bytes(metrics_lineage)
        or manifest_lineage.get("sha256") != expected_lineage_sha
    ):
        raise ActualDefinedError("historical snapshot lineage binding differs")
    expected_coverage = {
        "source_n": base.EXPECTED_SOURCE_TOTAL,
        "validation_total": sum(base.EXPECTED_MODEL_COUNTS.values()),
        "model_counts": base.EXPECTED_MODEL_COUNTS,
        "gpt56_declared_nonresponses": list(base.GPT56_NONRESPONSES),
    }
    for owner_name, owner in (("manifest", manifest), ("metrics", metrics)):
        coverage = owner.get("coverage")
        if not isinstance(coverage, Mapping) or any(
            coverage.get(key) != value for key, value in expected_coverage.items()
        ):
            raise ActualDefinedError(
                f"historical snapshot coverage differs in {owner_name}"
            )
    if set(metrics.get("model_specific_primary", {})) != set(base.MODELS):
        raise ActualDefinedError("historical snapshot model roster differs")
    code_dependencies = manifest.get("code_dependencies")
    analyzer = (
        code_dependencies.get("analyzer")
        if isinstance(code_dependencies, Mapping)
        else None
    )
    if not isinstance(analyzer, Mapping) or analyzer.get("sha256") != BASE_ANALYZER_SHA256:
        raise ActualDefinedError("historical snapshot analyzer dependency differs")
    code_digests = (
        manifest.get("code_inventory_digest_before"),
        manifest.get("code_inventory_digest_after"),
        metrics.get("code_inventory_digest"),
    )
    input_digests = (
        manifest.get("input_inventory_digest_before"),
        manifest.get("input_inventory_digest_after"),
        metrics.get("input_inventory_digest"),
    )
    if len(set(code_digests)) != 1 or not _is_sha256(code_digests[0]):
        raise ActualDefinedError("historical snapshot code-digest binding differs")
    if len(set(input_digests)) != 1 or not _is_sha256(input_digests[0]):
        raise ActualDefinedError("historical snapshot input-digest binding differs")
    if (
        manifest.get("report_fully_recomputed_from_validation_inputs_at_publication")
        is not True
        or manifest.get("report_recomputation_canonical_bytes_equal") is not True
    ):
        raise ActualDefinedError("historical snapshot full-recomputation proof differs")
    internal = manifest.get("artifacts")
    if not isinstance(internal, Mapping) or set(internal) != {"metrics.json", "metrics.csv"}:
        raise ActualDefinedError("historical manifest artifact roster differs")
    for name in ("metrics.json", "metrics.csv"):
        declared = internal.get(name)
        if (
            not isinstance(declared, Mapping)
            or declared.get("path") != name
            or declared.get("sha256") != records[name]["sha256"]
            or declared.get("size") != records[name]["size"]
        ):
            raise ActualDefinedError(
                f"historical manifest declaration differs for {name}"
            )
    expected_execution = {
        "api_calls": 0,
        "model_generation": False,
        "gpu_inference": False,
        "recompression": False,
        "experiment_b_modified": False,
    }
    for owner_name, owner in (("manifest", manifest), ("metrics", metrics)):
        execution = owner.get("execution")
        if not isinstance(execution, Mapping) or any(
            execution.get(key) != value for key, value in expected_execution.items()
        ):
            raise ActualDefinedError(
                f"historical snapshot execution declaration differs in {owner_name}"
            )
    return dict(metrics), records


def _crosscheck_historical(
    model: str,
    rows: Sequence[Mapping[str, Any]],
    historical_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    historical_model = historical_metrics.get("model_specific_primary", {}).get(model)
    if not isinstance(historical_model, Mapping):
        raise ActualDefinedError(f"historical snapshot lacks model {model}")
    historical_result = historical_model.get("results")
    if not isinstance(historical_result, Mapping):
        raise ActualDefinedError(f"historical snapshot result is malformed for {model}")
    expected_continuous = historical_result.get("continuous_source_validation", {}).get(
        "actual"
    )
    expected_label = historical_result.get(
        "secondary_source_excess_quantile_label_alignment", {}
    ).get("validation_actual")
    observed_continuous = base.continuous_metrics(
        [float(row["source_actual"]) for row in rows],
        [float(row["validation_actual"]) for row in rows],
        require_defined=True,
    )
    observed_label = label_agreement(rows, "historical_excess_level")
    if not isinstance(expected_continuous, Mapping) or not isinstance(expected_label, Mapping):
        raise ActualDefinedError(f"historical snapshot fields are missing for {model}")
    for key in ("spearman_rho", "pearson_r", "kendall_tau_b", "krippendorff_alpha_interval"):
        if not _same(float(observed_continuous[key]), float(expected_continuous[key]), atol=1e-15):
            raise ActualDefinedError(f"historical continuous cross-check failed for {model}/{key}")
    for key in ("spearman_rho", "kendall_tau_b"):
        if not _same(float(observed_label[key]), float(expected_label[key]), atol=1e-15):
            raise ActualDefinedError(f"historical label cross-check failed for {model}/{key}")
    return {
        "continuous_actual_point_verified": True,
        "historical_label_spearman_kendall_verified": True,
        "historical_snapshot_model_n": observed_continuous["n"],
    }


def _model_report(
    model: str,
    rows: Sequence[Mapping[str, Any]],
    bootstrap: Mapping[str, Any],
    historical_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    continuous = base.continuous_metrics(
        [float(row["source_actual"]) for row in rows],
        [float(row["validation_actual"]) for row in rows],
        require_defined=True,
    )
    return {
        "n": len(rows),
        "actual_defined_label_agreement": label_agreement(
            rows, "actual_defined_level"
        ),
        "historical_excess_defined_label_agreement": label_agreement(
            rows, "historical_excess_level"
        ),
        "definition_comparison": _definition_comparison(
            rows, bootstrap["models"][model]
        ),
        "actual_defined_level_gradient": level_gradient(
            rows, "actual_defined_level"
        ),
        "continuous_source_actual_validation_actual": continuous,
        "validation_actual_compressor_diagnostics": _compressor_actual_diagnostics(rows),
        "splits": _split_reports(rows),
        "historical_snapshot_crosscheck": _crosscheck_historical(
            model, rows, historical_metrics
        ),
    }


def build_metrics(
    *,
    source_index: Mapping[str, Mapping[str, Any]],
    rows_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    trust_counts: Mapping[str, Mapping[str, int]],
    cohorts: Mapping[str, Any],
    roster: Sequence[Mapping[str, Any]],
    roster_diagnostics: Mapping[str, Any],
    source_authentication: Mapping[str, Any],
    historical_metrics: Mapping[str, Any],
    historical_records: Mapping[str, Any],
    lineage: LineageManifest,
    input_digest: str,
    code_digest: str,
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
) -> dict[str, Any]:
    attached = attach_actual_levels(rows_by_model, roster)
    model_specific: dict[str, Any] = {}
    for model in base.MODELS:
        rows = attached[model]
        bootstrap = label_definition_bootstrap(
            {model: rows},
            cohort_name=f"model_specific:{model}",
            replicates=bootstrap_replicates,
            master_seed=seed,
        )
        model_specific[model] = {
            "cohort": _derived_cohort_description(
                cohorts["model_specific"][model]["description"], rows
            ),
            "trust": dict(trust_counts[model]),
            "bootstrap_method": {
                key: value for key, value in bootstrap.items() if key != "models"
            },
            "results": _model_report(model, rows, bootstrap, historical_metrics),
        }
    common: dict[str, Any] = {}
    for name, models in (
        ("completed_models_common", ("gemini-3.6-flash", "gpt-5.6-sol")),
        ("five_model_common", tuple(base.MODELS)),
    ):
        ids = set(cohorts[name]["ids"])
        selected = {model: _filter_ids(attached[model], ids) for model in models}
        bootstrap = label_definition_bootstrap(
            selected,
            cohort_name=name,
            replicates=bootstrap_replicates,
            master_seed=seed,
        )
        common[name] = {
            "cohort": _derived_cohort_description(
                cohorts[name]["description"], selected[models[0]]
            ),
            "bootstrap_method": {
                key: value for key, value in bootstrap.items() if key != "models"
            },
            "models": {
                model: {
                    "n": len(selected[model]),
                    "actual_defined_label_agreement": label_agreement(
                        selected[model], "actual_defined_level"
                    ),
                    "historical_excess_defined_label_agreement": label_agreement(
                        selected[model], "historical_excess_level"
                    ),
                    "definition_comparison": _definition_comparison(
                        selected[model], bootstrap["models"][model]
                    ),
                    "actual_defined_level_gradient": level_gradient(
                        selected[model], "actual_defined_level"
                    ),
                    "continuous_source_actual_validation_actual": base.continuous_metrics(
                        [float(row["source_actual"]) for row in selected[model]],
                        [float(row["validation_actual"]) for row in selected[model]],
                        require_defined=True,
                    ),
                }
                for model in models
            },
        }
    source_roster = {str(row["id"]): row for row in roster}
    source_level_means = {
        level: _summary(
            [
                float(source_index[item_id]["actual_ratio"])
                for item_id, entry in source_roster.items()
                if entry["actual_defined_level"] == level
            ]
        )
        for level in LEVELS
    }
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
        "code_inventory_digest": code_digest,
        "analysis_contract": {
            "primary_estimand": "canonical_aggregate_actual_ratio",
            "primary_B_function": "cross_generator_reproducibility_on_in_the_wild_prompts",
            "source_level_definition": (
                "stable descending source actual_ratio within each dataset x category; "
                "floor fifths with remainder in L5"
            ),
            "label_orientation": "L1=5 through L5=1",
            "gradient_orientation": "L1=1 through L5=5; expected negative",
            "definition_delta_orientation": "actual_defined_minus_historical_excess_defined",
            "historical_excess_results_role": "counterfactual_sensitivity",
            "canonical_aggregate_only": True,
            "per_compressor_primary": False,
        },
        "coverage": {
            "source_n": len(source_index),
            "validation_total": sum(len(rows) for rows in rows_by_model.values()),
            "model_counts": {model: len(rows_by_model[model]) for model in base.MODELS},
            "trust_counts": {model: dict(trust_counts[model]) for model in base.MODELS},
            "gpt56_declared_nonresponses": list(base.GPT56_NONRESPONSES),
        },
        "actual_defined_roster": {
            **dict(roster_diagnostics),
            "roster_artifact": "roster.jsonl",
            "source_actual_level_means": source_level_means,
            "boundary_tie": dict(BOUNDARY_TIE),
            "source_authentication": copy.deepcopy(source_authentication),
        },
        "bootstrap": {
            "replicates": bootstrap_replicates,
            "master_seed": seed,
            "confidence_level": 0.95,
            "sampling_unit": "source_id",
            "strata": ["dataset", "category"],
            "level_used_as_stratum": False,
            "roster_recomputed_inside_replicate": False,
            "minimum_valid_fraction": 0.99,
        },
        "historical_sensitivity_snapshot": {
            "role": "protected_read_only_input",
            "records": copy.deepcopy(historical_records),
            "schema": historical_metrics.get("schema"),
            "state": historical_metrics.get("state"),
            "active_lineage_sha256": historical_metrics.get("active_lineage", {}).get(
                "sha256"
            ),
        },
        "model_specific_primary": model_specific,
        "common_cohort_sensitivity": common,
        "limitations": [
            "Actual-defined levels are source-score bins, not human labels or criterion truth.",
            "Source actual-to-level separation is constructed; evidence comes from transfer to independently generated validation outputs.",
            "Experiment B supports cross-generator reproducibility, not criterion validity.",
            "Global-pooled alpha_z and alpha_rank are not Experiment A per-item estimators.",
            "Model-specific coverage differs; common cohorts are selection-conditioned and the five-model common cohort excludes OASST1.",
            "Stored validation protocols are mixed and legacy rows have weaker call provenance.",
            "Historical excess-defined results are retained rather than suppressed.",
            "Publication is a hash-recorded snapshot, not a linearizable reader-lease transaction.",
        ],
        "execution": {
            "api_calls": 0,
            "model_generation": False,
            "gpu_inference": False,
            "recompression": False,
            "astra_used": False,
            "experiment_b_modified": False,
        },
        "warnings": [],
    }
    return base._prepare_machine_payload(report)


def _csv_bytes(report: Mapping[str, Any]) -> bytes:
    columns = [
        "cohort",
        "model",
        "definition",
        "namespace",
        "split_type",
        "split_value",
        "level",
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
    rows: list[dict[str, Any]] = []

    def add(**kwargs: Any) -> None:
        rows.append({column: kwargs.get(column) for column in columns})

    entries: list[tuple[str, str, Mapping[str, Any], str]] = []
    for model, entry in report["model_specific_primary"].items():
        entries.append((f"model_specific:{model}", model, entry["results"], "primary"))
    for cohort_name, cohort in report["common_cohort_sensitivity"].items():
        for model, result in cohort["models"].items():
            entries.append((cohort_name, model, result, "sensitivity"))
    for cohort, model, result, cohort_role in entries:
        comparison = result["definition_comparison"]
        for definition in ("actual_defined", "historical_excess_defined"):
            metrics = comparison[definition]
            intervals = comparison["bootstrap_ci"][definition]
            definition_role = (
                cohort_role
                if definition == "actual_defined"
                else "counterfactual_sensitivity"
            )
            for metric in LABEL_METRICS:
                add(
                    cohort=cohort,
                    model=model,
                    definition=definition,
                    namespace="label_agreement",
                    split_type="pooled",
                    split_value="all",
                    metric=metric,
                    estimate=metrics[metric],
                    ci_low=intervals[metric]["low"],
                    ci_high=intervals[metric]["high"],
                    n=comparison["n"],
                    analysis_role=definition_role,
                    metric_role="primary_estimand" if metric == "spearman_rho" else "secondary",
                    primary=(
                        cohort_role == "primary"
                        and definition == "actual_defined"
                        and metric == "spearman_rho"
                    ),
                )
        delta = comparison["delta_actual_defined_minus_historical"]
        delta_ci = comparison["bootstrap_ci"][
            "delta_actual_defined_minus_historical"
        ]
        for metric in LABEL_METRICS:
            add(
                cohort=cohort,
                model=model,
                definition="actual_defined_minus_historical_excess_defined",
                namespace="label_definition_delta",
                split_type="pooled",
                split_value="all",
                metric=metric,
                estimate=delta[metric],
                ci_low=delta_ci[metric]["low"],
                ci_high=delta_ci[metric]["high"],
                n=comparison["n"],
                analysis_role="definition_sensitivity_comparison",
                metric_role=(
                    "primary_definition_comparison"
                    if metric == "spearman_rho"
                    else "secondary"
                ),
                primary=False,
            )
        continuous = result["continuous_source_actual_validation_actual"]
        for metric in (
            "spearman_rho",
            "pearson_r",
            "kendall_tau_b",
            "krippendorff_alpha_interval",
        ):
            add(
                cohort=cohort,
                model=model,
                definition="actual_continuous",
                namespace="source_validation_continuous",
                split_type="pooled",
                split_value="all",
                metric=metric,
                estimate=continuous[metric],
                n=continuous["n"],
                analysis_role=cohort_role,
                metric_role="secondary",
                primary=False,
            )
        gradient = result["actual_defined_level_gradient"]
        for level in LEVELS:
            summary = gradient["by_level"][level]
            add(
                cohort=cohort,
                model=model,
                definition="actual_defined",
                namespace="level_descriptive",
                split_type="pooled",
                split_value="all",
                level=level,
                metric="mean_validation_actual",
                estimate=summary["mean"],
                n=summary["n"],
                analysis_role=cohort_role,
                metric_role="secondary",
                primary=False,
            )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _inventory(
    *,
    lineage: LineageManifest,
    output_dir: Path,
    experiment_root: Path,
) -> dict[str, dict[str, Any]]:
    result = {
        f"base:{key}": value
        for key, value in base.input_inventory(
            output_dir=output_dir,
            experiment_root=experiment_root,
            lineage=lineage,
        ).items()
    }
    for dataset in DATASETS:
        result[f"pipeline:{dataset}"] = base._stream_file_record(
            output_dir / f"{dataset}_pipeline.jsonl", jsonl=True
        )
    for name in HISTORICAL_HASHES:
        result[f"historical:{name}"] = base._stream_file_record(
            HISTORICAL_SNAPSHOT / name, jsonl=False
        )
    return result


def _code_inventory() -> dict[str, Any]:
    base_record = _require_base_sha()
    path = Path(__file__).resolve()
    return {
        "actual_defined_analyzer": {
            "path": str(path),
            "sha256": storage.file_sha256(path),
            "size": path.stat().st_size,
        },
        "completed_base_analyzer": base_record,
        "base_dependency_inventory": base.code_inventory(),
    }


def _digest(value: Any) -> str:
    return storage.sha256_bytes(storage.canonical_json_bytes(value))


def _require_same(before: Any, after: Any, context: str) -> None:
    if storage.canonical_json_bytes(before) != storage.canonical_json_bytes(after):
        raise ActualDefinedError(f"drift during {context}")


def _build_once(
    *,
    lineage: LineageManifest,
    output_dir: Path,
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
    input_digest: str,
    code_digest: str,
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    pipelines, historical, source_auth = load_source_inputs(
        lineage, output_dir=output_dir
    )
    roster, diagnostics = build_actual_roster(pipelines, historical)
    validate_production_roster(roster, diagnostics)
    source_index, rows_by_model, trust = base.load_joined_rows(
        output_dir=output_dir, lineage=lineage
    )
    cohorts = base.build_cohorts(source_index, rows_by_model)
    historical_metrics, historical_records = load_historical_snapshot()
    if historical_metrics.get("active_lineage", {}).get("sha256") != lineage.sha256:
        raise ActualDefinedError("historical snapshot lineage differs")
    metrics = build_metrics(
        source_index=source_index,
        rows_by_model=rows_by_model,
        trust_counts=trust,
        cohorts=cohorts,
        roster=roster,
        roster_diagnostics=diagnostics,
        source_authentication=source_auth,
        historical_metrics=historical_metrics,
        historical_records=historical_records,
        lineage=lineage,
        input_digest=input_digest,
        code_digest=code_digest,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at_utc,
    )
    return roster_jsonl_bytes(roster), metrics, {
        "cohorts": cohorts,
        "roster_diagnostics": diagnostics,
        "source_authentication": source_auth,
        "historical_records": historical_records,
    }


def _validate_interval(
    interval: Any,
    *,
    point: Any,
    context: str,
    lower_bound: float,
    upper_bound: float,
) -> None:
    if not isinstance(interval, Mapping) or set(interval) != {"low", "high"}:
        raise ActualDefinedError(f"{context} interval schema differs")
    low = interval.get("low")
    high = interval.get("high")
    if not all(base._is_finite_number(value) for value in (low, high, point)):
        raise ActualDefinedError(f"{context} interval/point is non-finite")
    low_f, high_f, point_f = float(low), float(high), float(point)
    if (
        low_f < lower_bound
        or high_f > upper_bound
        or low_f > high_f
        or point_f < low_f - 1e-12
        or point_f > high_f + 1e-12
    ):
        raise ActualDefinedError(f"{context} interval is reversed, out of range, or misses point")


def _validate_label_block(block: Any, *, n: int, context: str) -> None:
    if not isinstance(block, Mapping) or block.get("n") != n:
        raise ActualDefinedError(f"{context} label block count differs")
    if block.get("estimator") != "global_pooled_adaptation":
        raise ActualDefinedError(f"{context} label estimator differs")
    if not isinstance(block.get("missing_levels"), list) or not isinstance(
        block.get("warnings"), list
    ):
        raise ActualDefinedError(f"{context} label diagnostics differ")
    for metric in LABEL_METRICS:
        value = block.get(metric)
        if not base._is_finite_number(value) or not -1.0 <= float(value) <= 1.0:
            raise ActualDefinedError(f"{context}/{metric} is invalid")
    for name in ("spearman_p", "kendall_p"):
        value = block.get(name)
        if not base._is_finite_number(value) or not 0.0 <= float(value) <= 1.0:
            raise ActualDefinedError(f"{context}/{name} is invalid")


def _validate_bootstrap_method(
    method: Any,
    *,
    cohort_name: str,
    replicates: int,
    seed: int,
    shared_models: bool,
    context: str,
) -> None:
    required = {
        "method": "paired_source_id_percentile_bootstrap",
        "confidence_level": 0.95,
        "replicates_requested": replicates,
        "replicates_attempted": replicates,
        "minimum_valid_fraction": 0.99,
        "master_seed": seed,
        "cohort_seed": base._cohort_seed(seed, cohort_name),
        "sampling_unit": "source_id",
        "strata": ["dataset", "category"],
        "level_used_as_stratum": False,
        "roster_recomputed_inside_replicate": False,
        "models_share_sampled_ids": shared_models,
    }
    if not isinstance(method, Mapping) or any(
        method.get(key) != value for key, value in required.items()
    ):
        raise ActualDefinedError(f"{context} bootstrap contract differs")
    valid = method.get("replicates_valid")
    undefined = method.get("undefined_replicates")
    if (
        type(valid) is not int
        or type(undefined) is not int
        or valid + undefined != replicates
        or valid < math.ceil(replicates * 0.99)
    ):
        raise ActualDefinedError(f"{context} bootstrap accounting differs")


def _validate_cohort_description(
    cohort: Any,
    *,
    historical_cohort: Any,
    expected_n: int,
    expected_models: Sequence[str],
    context: str,
) -> None:
    if not isinstance(cohort, Mapping) or not isinstance(historical_cohort, Mapping):
        raise ActualDefinedError(f"{context} cohort is missing")
    if "level_counts" in cohort:
        raise ActualDefinedError(f"{context} cohort has ambiguous level_counts")
    for key in (
        "n_source_ids",
        "models",
        "id_roster_sha256",
        "dataset_counts",
        "category_counts",
    ):
        if cohort.get(key) != historical_cohort.get(key):
            raise ActualDefinedError(f"{context} cohort differs for {key}")
    if (
        cohort.get("n_source_ids") != expected_n
        or cohort.get("models") != list(expected_models)
        or not _is_sha256(cohort.get("id_roster_sha256"))
    ):
        raise ActualDefinedError(f"{context} cohort roster differs")
    actual_counts = cohort.get("actual_defined_level_counts")
    historical_counts = cohort.get("historical_excess_level_counts")
    if (
        not isinstance(actual_counts, Mapping)
        or set(actual_counts) != set(LEVELS)
        or sum(actual_counts.values()) != expected_n
        or any(type(value) is not int or value < 0 for value in actual_counts.values())
        or not isinstance(historical_counts, Mapping)
        or set(historical_counts) != set(LEVELS)
        or historical_counts != historical_cohort.get("level_counts")
        or sum(historical_counts.values()) != expected_n
    ):
        raise ActualDefinedError(f"{context} cohort level counts differ")


def _validate_definition_result(
    result: Any,
    *,
    n: int,
    context: str,
) -> None:
    if not isinstance(result, Mapping) or result.get("n") != n:
        raise ActualDefinedError(f"{context} result count differs")
    actual = result.get("actual_defined_label_agreement")
    historical = result.get("historical_excess_defined_label_agreement")
    _validate_label_block(actual, n=n, context=f"{context}/actual")
    _validate_label_block(historical, n=n, context=f"{context}/historical")
    comparison = result.get("definition_comparison")
    if not isinstance(comparison, Mapping) or comparison.get("n") != n:
        raise ActualDefinedError(f"{context} definition comparison differs")
    if storage.canonical_json_bytes(comparison.get("actual_defined")) != storage.canonical_json_bytes(actual):
        raise ActualDefinedError(f"{context} duplicate actual label block differs")
    if storage.canonical_json_bytes(comparison.get("historical_excess_defined")) != storage.canonical_json_bytes(historical):
        raise ActualDefinedError(f"{context} duplicate historical label block differs")
    delta = comparison.get("delta_actual_defined_minus_historical")
    intervals = comparison.get("bootstrap_ci")
    if not isinstance(delta, Mapping) or set(delta) != set(LABEL_METRICS):
        raise ActualDefinedError(f"{context} delta schema differs")
    if not isinstance(intervals, Mapping) or set(intervals) != {
        "actual_defined",
        "historical_excess_defined",
        "delta_actual_defined_minus_historical",
    }:
        raise ActualDefinedError(f"{context} bootstrap CI namespaces differ")
    for namespace in intervals:
        if not isinstance(intervals[namespace], Mapping) or set(intervals[namespace]) != set(LABEL_METRICS):
            raise ActualDefinedError(f"{context}/{namespace} CI metric roster differs")
    for metric in LABEL_METRICS:
        expected_delta = float(actual[metric]) - float(historical[metric])
        if not base._is_finite_number(delta.get(metric)) or not _same(
            float(delta[metric]), expected_delta, atol=1e-15
        ):
            raise ActualDefinedError(f"{context}/{metric} delta arithmetic differs")
        _validate_interval(
            intervals["actual_defined"][metric],
            point=actual[metric],
            context=f"{context}/actual_defined/{metric}",
            lower_bound=-1.0,
            upper_bound=1.0,
        )
        _validate_interval(
            intervals["historical_excess_defined"][metric],
            point=historical[metric],
            context=f"{context}/historical_excess_defined/{metric}",
            lower_bound=-1.0,
            upper_bound=1.0,
        )
        _validate_interval(
            intervals["delta_actual_defined_minus_historical"][metric],
            point=delta[metric],
            context=f"{context}/delta/{metric}",
            lower_bound=-2.0,
            upper_bound=2.0,
        )
    gradient = result.get("actual_defined_level_gradient")
    if (
        not isinstance(gradient, Mapping)
        or gradient.get("n") != n
        or gradient.get("strictly_decreasing_level_means") is not True
        or set(gradient.get("by_level", {})) != set(LEVELS)
        or sum(gradient["by_level"][level].get("n", -1) for level in LEVELS) != n
    ):
        raise ActualDefinedError(f"{context} actual-defined gradient differs")
    for metric in ("spearman_rho", "kendall_tau_b"):
        value = gradient.get(metric)
        if not base._is_finite_number(value) or not -1.0 <= float(value) <= 0.0:
            raise ActualDefinedError(f"{context} gradient {metric} differs")
    continuous = result.get("continuous_source_actual_validation_actual")
    if not isinstance(continuous, Mapping) or continuous.get("n") != n:
        raise ActualDefinedError(f"{context} continuous result differs")
    for metric in (
        "spearman_rho",
        "pearson_r",
        "kendall_tau_b",
        "krippendorff_alpha_interval",
    ):
        value = continuous.get(metric)
        if not base._is_finite_number(value) or not -1.0 <= float(value) <= 1.0:
            raise ActualDefinedError(f"{context} continuous {metric} differs")


def _validate_optional_label_block(block: Any, *, n: int, context: str) -> None:
    if not isinstance(block, Mapping) or block.get("n") != n:
        raise ActualDefinedError(f"{context} optional label block count differs")
    warnings = block.get("warnings")
    if (
        not isinstance(warnings, list)
        or block.get("estimator") != "global_pooled_adaptation"
        or not isinstance(block.get("missing_levels"), list)
    ):
        raise ActualDefinedError(f"{context} optional label diagnostics differ")
    if warnings:
        for name in (*LABEL_METRICS, "spearman_p", "kendall_p"):
            if block.get(name) is not None:
                raise ActualDefinedError(f"{context}/{name} should be null when undefined")
    else:
        _validate_label_block(block, n=n, context=context)


def _validate_split_group(group: Any, *, n: int, context: str) -> None:
    if not isinstance(group, Mapping) or set(group) != {
        "n",
        "definition_comparison",
        "actual_defined_gradient",
    } or group.get("n") != n:
        raise ActualDefinedError(f"{context} split group schema/count differs")
    comparison = group.get("definition_comparison")
    if not isinstance(comparison, Mapping) or comparison.get("n") != n:
        raise ActualDefinedError(f"{context} split definition comparison differs")
    actual = comparison.get("actual_defined")
    historical = comparison.get("historical_excess_defined")
    _validate_optional_label_block(actual, n=n, context=f"{context}/actual")
    _validate_optional_label_block(historical, n=n, context=f"{context}/historical")
    if comparison.get("bootstrap_ci") != {}:
        raise ActualDefinedError(f"{context} split unexpectedly claims bootstrap CIs")
    delta = comparison.get("delta_actual_defined_minus_historical")
    if not isinstance(delta, Mapping) or set(delta) != set(LABEL_METRICS):
        raise ActualDefinedError(f"{context} split delta schema differs")
    for metric in LABEL_METRICS:
        left, right, observed = actual.get(metric), historical.get(metric), delta.get(metric)
        if left is None or right is None:
            if observed is not None:
                raise ActualDefinedError(f"{context}/{metric} undefined delta is not null")
        elif not base._is_finite_number(observed) or not _same(
            float(observed), float(left) - float(right), atol=1e-15
        ):
            raise ActualDefinedError(f"{context}/{metric} split delta arithmetic differs")
    gradient = group.get("actual_defined_gradient")
    if (
        not isinstance(gradient, Mapping)
        or set(gradient) != {
            "n",
            "spearman_rho",
            "spearman_p",
            "kendall_tau_b",
            "kendall_p",
            "by_level",
            "strictly_decreasing_level_means",
            "warnings",
        }
        or gradient.get("n") != n
        or set(gradient.get("by_level", {})) != set(LEVELS)
        or sum(gradient["by_level"][level].get("n", -1) for level in LEVELS) != n
        or not isinstance(gradient.get("warnings"), list)
        or gradient.get("strictly_decreasing_level_means") not in (True, False, None)
    ):
        raise ActualDefinedError(f"{context} split gradient differs")
    for estimate_name, p_name in (
        ("spearman_rho", "spearman_p"),
        ("kendall_tau_b", "kendall_p"),
    ):
        estimate, p_value = gradient.get(estimate_name), gradient.get(p_name)
        if estimate is None or p_value is None:
            if estimate is not None or p_value is not None:
                raise ActualDefinedError(
                    f"{context} split gradient estimate/p pairing differs"
                )
        elif (
            not base._is_finite_number(estimate)
            or not -1.0 <= float(estimate) <= 1.0
            or not base._is_finite_number(p_value)
            or not 0.0 <= float(p_value) <= 1.0
        ):
            raise ActualDefinedError(
                f"{context} split gradient {estimate_name}/{p_name} differs"
            )
    if not gradient["warnings"] and any(
        gradient.get(name) is None
        for name in ("spearman_rho", "spearman_p", "kendall_tau_b", "kendall_p")
    ):
        raise ActualDefinedError(f"{context} defined split gradient has null metrics")
    for level in LEVELS:
        summary = gradient["by_level"][level]
        if not isinstance(summary, Mapping) or set(summary) != {"n", "mean", "sd", "min", "max"}:
            raise ActualDefinedError(f"{context}/{level} split summary schema differs")
        count = summary.get("n")
        if type(count) is not int or count < 0:
            raise ActualDefinedError(f"{context}/{level} split summary count differs")
        for name in ("mean", "sd", "min", "max"):
            value = summary.get(name)
            if value is not None and not base._is_finite_number(value):
                raise ActualDefinedError(f"{context}/{level}/{name} is non-finite")
        if count == 0:
            if any(summary[name] is not None for name in ("mean", "sd", "min", "max")):
                raise ActualDefinedError(f"{context}/{level} empty summary is not null")
        else:
            if any(summary[name] is None for name in ("mean", "min", "max")):
                raise ActualDefinedError(f"{context}/{level} nonempty summary is incomplete")
            if not (
                float(summary["min"])
                <= float(summary["mean"])
                <= float(summary["max"])
            ):
                raise ActualDefinedError(f"{context}/{level} summary ordering differs")
            if count == 1 and summary["sd"] is not None:
                raise ActualDefinedError(f"{context}/{level} singleton SD is not null")
            if count > 1 and (
                summary["sd"] is None or float(summary["sd"]) < 0.0
            ):
                raise ActualDefinedError(f"{context}/{level} SD differs")


def _validate_summary_payload(
    summary: Any, *, expected_n: int, context: str
) -> None:
    if not isinstance(summary, Mapping) or set(summary) != {"n", "mean", "sd", "min", "max"}:
        raise ActualDefinedError(f"{context} summary schema differs")
    if summary.get("n") != expected_n:
        raise ActualDefinedError(f"{context} summary count differs")
    for name in ("mean", "sd", "min", "max"):
        value = summary.get(name)
        if value is not None and not base._is_finite_number(value):
            raise ActualDefinedError(f"{context}/{name} is non-finite")
    if expected_n == 0:
        if any(summary[name] is not None for name in ("mean", "sd", "min", "max")):
            raise ActualDefinedError(f"{context} empty summary is not null")
        return
    if any(summary[name] is None for name in ("mean", "min", "max")):
        raise ActualDefinedError(f"{context} nonempty summary is incomplete")
    if not float(summary["min"]) <= float(summary["mean"]) <= float(summary["max"]):
        raise ActualDefinedError(f"{context} summary ordering differs")
    if expected_n == 1 and summary["sd"] is not None:
        raise ActualDefinedError(f"{context} singleton SD is not null")
    if expected_n > 1 and (summary["sd"] is None or float(summary["sd"]) < 0.0):
        raise ActualDefinedError(f"{context} SD differs")


def _validate_compressor_diagnostics(
    diagnostics: Any,
    *,
    n: int,
    level_counts: Mapping[str, int],
    context: str,
) -> None:
    if not isinstance(diagnostics, Mapping) or set(diagnostics) != {
        "n",
        "krippendorff_alpha_interval",
        "by_actual_defined_level",
        "per_compressor",
    } or diagnostics.get("n") != n:
        raise ActualDefinedError(f"{context} compressor diagnostic schema/count differs")
    alpha = diagnostics.get("krippendorff_alpha_interval")
    if not base._is_finite_number(alpha) or not -1.0 <= float(alpha) <= 1.0:
        raise ActualDefinedError(f"{context} overall compressor alpha differs")
    by_level = diagnostics.get("by_actual_defined_level")
    if not isinstance(by_level, Mapping) or set(by_level) != set(LEVELS):
        raise ActualDefinedError(f"{context} compressor level roster differs")
    for level in LEVELS:
        record = by_level[level]
        if not isinstance(record, Mapping) or set(record) != {
            "n",
            "krippendorff_alpha_interval",
        } or record.get("n") != level_counts[level]:
            raise ActualDefinedError(f"{context}/{level} compressor alpha record differs")
        value = record.get("krippendorff_alpha_interval")
        if not base._is_finite_number(value) or not -1.0 <= float(value) <= 1.0:
            raise ActualDefinedError(f"{context}/{level} compressor alpha differs")
    compressors = diagnostics.get("per_compressor")
    if not isinstance(compressors, Mapping) or set(compressors) != set(COMPRESSORS):
        raise ActualDefinedError(f"{context} per-compressor roster differs")
    for compressor in COMPRESSORS:
        payload = compressors[compressor]
        if not isinstance(payload, Mapping) or set(payload) != {
            "overall",
            "by_actual_defined_level",
        }:
            raise ActualDefinedError(f"{context}/{compressor} payload schema differs")
        _validate_summary_payload(
            payload["overall"], expected_n=n, context=f"{context}/{compressor}/overall"
        )
        compressor_levels = payload["by_actual_defined_level"]
        if not isinstance(compressor_levels, Mapping) or set(compressor_levels) != set(LEVELS):
            raise ActualDefinedError(f"{context}/{compressor} level roster differs")
        for level in LEVELS:
            _validate_summary_payload(
                compressor_levels[level],
                expected_n=level_counts[level],
                context=f"{context}/{compressor}/{level}",
            )


def _validate_metrics(
    metrics: Mapping[str, Any],
    *,
    lineage: LineageManifest,
    input_digest: str,
    code_digest: str,
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
) -> None:
    expected_keys = {
        "schema",
        "schema_version",
        "state",
        "created_at_utc",
        "active_lineage",
        "input_inventory_digest",
        "code_inventory_digest",
        "analysis_contract",
        "coverage",
        "actual_defined_roster",
        "bootstrap",
        "historical_sensitivity_snapshot",
        "model_specific_primary",
        "common_cohort_sensitivity",
        "limitations",
        "execution",
        "warnings",
    }
    if set(metrics) != expected_keys:
        raise ActualDefinedError("metrics top-level schema differs")
    expected = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "state": "DERIVED_SNAPSHOT_COMPLETE",
        "created_at_utc": created_at_utc,
        "input_inventory_digest": input_digest,
        "code_inventory_digest": code_digest,
    }
    if any(metrics.get(key) != value for key, value in expected.items()):
        raise ActualDefinedError("metrics publication binding differs")
    active = metrics.get("active_lineage")
    if (
        not isinstance(active, Mapping)
        or active.get("sha256") != lineage.sha256
        or active.get("config_fingerprint") != lineage.config_fingerprint
        or lineage.path is None
        or active.get("path") != str(lineage.path.resolve())
    ):
        raise ActualDefinedError("metrics lineage binding differs")
    contract = metrics.get("analysis_contract")
    expected_contract = {
        "primary_estimand": "canonical_aggregate_actual_ratio",
        "primary_B_function": "cross_generator_reproducibility_on_in_the_wild_prompts",
        "source_level_definition": (
            "stable descending source actual_ratio within each dataset x category; "
            "floor fifths with remainder in L5"
        ),
        "label_orientation": "L1=5 through L5=1",
        "gradient_orientation": "L1=1 through L5=5; expected negative",
        "definition_delta_orientation": "actual_defined_minus_historical_excess_defined",
        "historical_excess_results_role": "counterfactual_sensitivity",
        "canonical_aggregate_only": True,
        "per_compressor_primary": False,
    }
    if contract != expected_contract:
        raise ActualDefinedError("metrics analysis contract differs")
    historical_metrics, historical_records = load_historical_snapshot()
    coverage = metrics.get("coverage")
    if not isinstance(coverage, Mapping) or storage.canonical_json_bytes(coverage) != storage.canonical_json_bytes(historical_metrics.get("coverage")):
        raise ActualDefinedError("metrics coverage differs from protected historical coverage")
    roster = metrics.get("actual_defined_roster")
    if (
        not isinstance(roster, Mapping)
        or roster.get("mapping_sha256") != EXPECTED_MAPPING_SHA256
        or roster.get("source_n") != base.EXPECTED_SOURCE_TOTAL
        or roster.get("changed_n") != EXPECTED_CHANGED
        or roster.get("level_counts") != EXPECTED_LEVEL_COUNTS
        or roster.get("dataset_level_counts") != EXPECTED_DATASET_LEVEL_COUNTS
        or roster.get("cross_cut_ties") != [BOUNDARY_TIE]
        or roster.get("boundary_tie") != BOUNDARY_TIE
    ):
        raise ActualDefinedError("metrics roster binding differs")
    source_auth = roster.get("source_authentication")
    expected_roles = {
        f"{kind}:{dataset}" for kind in ("pipeline", "stratified") for dataset in DATASETS
    }
    if not isinstance(source_auth, Mapping) or set(source_auth) != expected_roles:
        raise ActualDefinedError("metrics source authentication roster differs")
    for role, record in source_auth.items():
        if (
            not isinstance(record, Mapping)
            or record.get("role") != role
            or not _is_sha256(record.get("sha256"))
            or not _is_sha256(record.get("per_id_mapping_sha256"))
            or record.get("row_count")
            != base.EXPECTED_DATASET_COUNTS[role.split(":", 1)[1]]
        ):
            raise ActualDefinedError(f"metrics source authentication differs for {role}")
    bootstrap = metrics.get("bootstrap")
    expected_bootstrap = {
        "replicates": bootstrap_replicates,
        "master_seed": seed,
        "confidence_level": 0.95,
        "sampling_unit": "source_id",
        "strata": ["dataset", "category"],
        "level_used_as_stratum": False,
        "roster_recomputed_inside_replicate": False,
        "minimum_valid_fraction": 0.99,
    }
    if bootstrap != expected_bootstrap:
        raise ActualDefinedError("metrics bootstrap binding differs")
    historical = metrics.get("historical_sensitivity_snapshot")
    if (
        not isinstance(historical, Mapping)
        or historical.get("role") != "protected_read_only_input"
        or historical.get("records") != historical_records
        or historical.get("schema") != base.SCHEMA
        or historical.get("state") != "DERIVED_SNAPSHOT_COMPLETE"
        or historical.get("active_lineage_sha256") != lineage.sha256
    ):
        raise ActualDefinedError("metrics historical sensitivity binding differs")
    models = metrics.get("model_specific_primary")
    historical_models = historical_metrics.get("model_specific_primary")
    if (
        not isinstance(models, Mapping)
        or set(models) != set(base.MODELS)
        or not isinstance(historical_models, Mapping)
    ):
        raise ActualDefinedError("metrics model roster differs")
    for model in base.MODELS:
        entry = models[model]
        historical_entry = historical_models.get(model)
        expected_n = base.EXPECTED_MODEL_COUNTS[model]
        if not isinstance(entry, Mapping) or not isinstance(historical_entry, Mapping):
            raise ActualDefinedError(f"metrics model entry differs for {model}")
        _validate_cohort_description(
            entry.get("cohort"),
            historical_cohort=historical_entry.get("cohort"),
            expected_n=expected_n,
            expected_models=(model,),
            context=f"model_specific/{model}",
        )
        _validate_bootstrap_method(
            entry.get("bootstrap_method"),
            cohort_name=f"model_specific:{model}",
            replicates=bootstrap_replicates,
            seed=seed,
            shared_models=False,
            context=f"model_specific/{model}",
        )
        result = entry.get("results")
        _validate_definition_result(
            result, n=expected_n, context=f"model_specific/{model}"
        )
        if entry.get("trust") != coverage["trust_counts"][model]:
            raise ActualDefinedError(f"metrics trust counts differ for {model}")
        crosscheck = result.get("historical_snapshot_crosscheck")
        if crosscheck != {
            "continuous_actual_point_verified": True,
            "historical_label_spearman_kendall_verified": True,
            "historical_snapshot_model_n": expected_n,
        }:
            raise ActualDefinedError(f"historical point cross-check differs for {model}")
        _validate_compressor_diagnostics(
            result.get("validation_actual_compressor_diagnostics"),
            n=expected_n,
            level_counts=entry["cohort"]["actual_defined_level_counts"],
            context=f"model_specific/{model}",
        )
        splits = result.get("splits")
        historical_splits = historical_entry.get("results", {}).get("splits")
        split_namespaces = {"by_dataset", "by_category", "by_protocol_group"}
        if (
            not isinstance(splits, Mapping)
            or set(splits) != split_namespaces
            or not isinstance(historical_splits, Mapping)
            or set(historical_splits) != split_namespaces
        ):
            raise ActualDefinedError(f"split diagnostics differ for {model}")
        for namespace in split_namespaces:
            groups = splits[namespace]
            historical_groups = historical_splits[namespace]
            if (
                not isinstance(groups, Mapping)
                or not isinstance(historical_groups, Mapping)
                or set(groups) != set(historical_groups)
                or sum(
                    group.get("n", -1)
                    for group in groups.values()
                    if isinstance(group, Mapping)
                )
                != expected_n
            ):
                raise ActualDefinedError(
                    f"split group roster/count differs for {model}/{namespace}"
                )
            for group_name, group in groups.items():
                historical_group = historical_groups[group_name]
                group_n = historical_group.get("n")
                if type(group_n) is not int or group_n < 1:
                    raise ActualDefinedError(
                        f"historical split count differs for {model}/{namespace}/{group_name}"
                    )
                _validate_split_group(
                    group,
                    n=group_n,
                    context=f"{model}/{namespace}/{group_name}",
                )
    common = metrics.get("common_cohort_sensitivity")
    historical_common = historical_metrics.get("common_cohort_sensitivity")
    expected_common = {
        "completed_models_common": (
            base.EXPECTED_COMPLETED_COMMON,
            ("gemini-3.6-flash", "gpt-5.6-sol"),
        ),
        "five_model_common": (base.EXPECTED_FIVE_MODEL_COMMON, tuple(base.MODELS)),
    }
    if (
        not isinstance(common, Mapping)
        or set(common) != set(expected_common)
        or not isinstance(historical_common, Mapping)
    ):
        raise ActualDefinedError("metrics common-cohort roster differs")
    for cohort_name, (expected_n, expected_models) in expected_common.items():
        entry = common[cohort_name]
        historical_entry = historical_common.get(cohort_name)
        if not isinstance(entry, Mapping) or not isinstance(historical_entry, Mapping):
            raise ActualDefinedError(f"common cohort {cohort_name} is malformed")
        _validate_cohort_description(
            entry.get("cohort"),
            historical_cohort=historical_entry.get("cohort"),
            expected_n=expected_n,
            expected_models=expected_models,
            context=cohort_name,
        )
        _validate_bootstrap_method(
            entry.get("bootstrap_method"),
            cohort_name=cohort_name,
            replicates=bootstrap_replicates,
            seed=seed,
            shared_models=True,
            context=cohort_name,
        )
        common_models = entry.get("models")
        if not isinstance(common_models, Mapping) or set(common_models) != set(expected_models):
            raise ActualDefinedError(f"common cohort model roster differs for {cohort_name}")
        for model in expected_models:
            _validate_definition_result(
                common_models[model],
                n=expected_n,
                context=f"{cohort_name}/{model}",
            )
    execution = metrics.get("execution")
    required_execution = {
        "api_calls": 0,
        "model_generation": False,
        "gpu_inference": False,
        "recompression": False,
        "astra_used": False,
        "experiment_b_modified": False,
    }
    if execution != required_execution:
        raise ActualDefinedError("metrics execution declaration differs")
    if not isinstance(metrics.get("limitations"), list) or not metrics["limitations"]:
        raise ActualDefinedError("metrics limitations are missing")
    if metrics.get("warnings") != []:
        raise ActualDefinedError("metrics top-level warnings differ")
    json.dumps(metrics, ensure_ascii=False, sort_keys=True, allow_nan=False)


def publish(
    *,
    roster_bytes: bytes,
    metrics: Mapping[str, Any],
    context: Mapping[str, Any],
    output_root: Path,
    lineage: LineageManifest,
    inventory_before: Mapping[str, Any],
    code_before: Mapping[str, Any],
    inventory_provider: Callable[[], Mapping[str, Any]],
    code_provider: Callable[[], Mapping[str, Any]],
    rebuild: Callable[[], tuple[bytes, dict[str, Any], dict[str, Any]]],
    state_validator: Callable[[], None],
    bootstrap_replicates: int,
    seed: int,
    created_at_utc: str,
    experiment_root: Path = HERE,
) -> Path:
    del context
    if bootstrap_replicates < MIN_PUBLICATION_REPLICATES:
        raise ActualDefinedError("publication requires at least 1000 bootstrap replicates")
    if not _is_sha256(lineage.sha256):
        raise ActualDefinedError("active lineage SHA is not lowercase 64-hex")
    root = base.validate_output_root(output_root, experiment_root=experiment_root)
    input_digest = _digest(inventory_before)
    code_digest = _digest(code_before)
    _validate_metrics(
        metrics,
        lineage=lineage,
        input_digest=input_digest,
        code_digest=code_digest,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created_at_utc,
    )
    validate_roster_bytes(
        roster_bytes,
        metrics.get("actual_defined_roster", {})
        if isinstance(metrics, Mapping)
        else {},
    )
    state_validator()
    second_roster, second_metrics, _ = rebuild()
    validate_roster_bytes(
        second_roster,
        second_metrics.get("actual_defined_roster", {})
        if isinstance(second_metrics, Mapping)
        else {},
    )
    if roster_bytes != second_roster:
        raise ActualDefinedError("roster differs from independent publication rebuild")
    if storage.canonical_json_bytes(metrics) != storage.canonical_json_bytes(second_metrics):
        raise ActualDefinedError("metrics differ from independent publication rebuild")
    _require_same(inventory_before, inventory_provider(), "publication rebuild")
    _require_same(code_before, code_provider(), "publication rebuild code")

    config = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "lineage_sha256": lineage.sha256,
        "input_inventory_digest": input_digest,
        "code_inventory_digest": code_digest,
        "mapping_sha256": EXPECTED_MAPPING_SHA256,
        "roster_sha256": EXPECTED_ROSTER_SHA256,
        "historical_manifest_sha256": HISTORICAL_HASHES["manifest.json"],
        "bootstrap_replicates": bootstrap_replicates,
        "seed": seed,
    }
    config_digest = _digest(config)
    timestamp = datetime.fromisoformat(created_at_utc.replace("Z", "+00:00")).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    lineage_dir = root / lineage.sha256
    resolved_candidate = lineage_dir.resolve()
    resolved_root = root.resolve()
    protected_root = experiment_root.resolve()
    if not base._path_is_within(resolved_candidate, resolved_root):
        raise ActualDefinedError("lineage output candidate escaped the approved root")
    if base._path_is_within(resolved_candidate, protected_root):
        raise ActualDefinedError("lineage output candidate entered protected Experiment B")
    final_dir = lineage_dir / f"{timestamp}_{config_digest[:12]}"
    if final_dir.exists():
        raise ActualDefinedError(f"refusing to replace existing snapshot: {final_dir}")
    root.mkdir(parents=True, exist_ok=True)
    base._assert_no_link_components(root)
    lineage_dir.mkdir(parents=False, exist_ok=True)
    base._assert_no_link_components(lineage_dir)
    resolved_lineage_dir = lineage_dir.resolve()
    if resolved_lineage_dir != resolved_candidate:
        raise ActualDefinedError("lineage output directory changed during creation")
    if not base._path_is_within(resolved_lineage_dir, resolved_root):
        raise ActualDefinedError("lineage output directory escaped the approved root")
    if base._path_is_within(resolved_lineage_dir, protected_root):
        raise ActualDefinedError("lineage output directory entered protected Experiment B")
    stage = lineage_dir / f".{final_dir.name}.staging-{uuid.uuid4().hex}"
    if stage.exists():
        raise ActualDefinedError(f"unexpected staging collision: {stage}")
    stage.mkdir(parents=False)
    base._assert_no_link_components(stage)
    if stage.resolve().parent != resolved_lineage_dir:
        shutil.rmtree(stage)
        raise ActualDefinedError("staging directory escaped the lineage output directory")
    try:
        storage.atomic_replace_bytes(stage / "roster.jsonl", roster_bytes)
        storage.atomic_replace_json(stage / "metrics.json", metrics)
        storage.atomic_replace_bytes(stage / "metrics.csv", _csv_bytes(metrics))
        after_outputs = inventory_provider()
        _require_same(inventory_before, after_outputs, "artifact staging")
        after_code = code_provider()
        _require_same(code_before, after_code, "artifact staging code")
        artifacts = {
            name: base._artifact_record(stage / name)
            for name in ("roster.jsonl", "metrics.json", "metrics.csv")
        }
        artifacts["roster.jsonl"]["row_count"] = roster_bytes.count(b"\n")
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
            "active_lineage": metrics["active_lineage"],
            "inputs": copy.deepcopy(inventory_before),
            "input_inventory_digest_before": input_digest,
            "input_inventory_digest_after": _digest(after_outputs),
            "code_dependencies": copy.deepcopy(code_before),
            "code_inventory_digest_before": code_digest,
            "code_inventory_digest_after": _digest(after_code),
            "actual_defined_mapping": metrics["actual_defined_roster"],
            "coverage": metrics["coverage"],
            "bootstrap": metrics["bootstrap"],
            "historical_sensitivity_snapshot": metrics[
                "historical_sensitivity_snapshot"
            ],
            "full_independent_rebuild": True,
            "roster_rebuild_bytes_equal": True,
            "metrics_rebuild_canonical_bytes_equal": True,
            "publication_semantics": "hash-recorded derived snapshot; no B reader lease",
            "artifacts": artifacts,
            "execution": metrics["execution"],
        }
        storage.atomic_replace_json(stage / "manifest.json", manifest)
        _require_same(inventory_before, inventory_provider(), "manifest staging")
        _require_same(code_before, code_provider(), "manifest staging code")
        state_validator()
        base._assert_no_link_components(lineage_dir)
        if lineage_dir.resolve() != resolved_lineage_dir:
            raise ActualDefinedError("lineage output directory changed before commit")
        if final_dir.exists():
            raise ActualDefinedError("snapshot destination appeared before commit")
        os.replace(stage, final_dir)
        storage.fsync_directory(final_dir.parent)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return final_dir


def run(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    bootstrap_replicates: int = 2000,
    seed: int = 20260910,
    experiment_root: Path = HERE,
    output_dir: Path = OUTPUTS,
) -> Path:
    if bootstrap_replicates < MIN_PUBLICATION_REPLICATES:
        raise ActualDefinedError("production run requires at least 1000 replicates")
    _require_base_sha()
    _, lineage = base.preflight_state(
        experiment_root=experiment_root, output_dir=output_dir
    )

    def state_validator() -> None:
        _require_base_sha()
        _, current = base.preflight_state(
            experiment_root=experiment_root, output_dir=output_dir
        )
        if current.sha256 != lineage.sha256 or current.path != lineage.path:
            raise ActualDefinedError("active lineage changed during analysis")

    def inventory_provider() -> Mapping[str, Any]:
        state_validator()
        return _inventory(
            lineage=lineage,
            output_dir=output_dir,
            experiment_root=experiment_root,
        )

    code_before = _code_inventory()
    inventory_before = inventory_provider()
    input_digest = _digest(inventory_before)
    code_digest = _digest(code_before)
    created = _utc_now()

    def rebuild() -> tuple[bytes, dict[str, Any], dict[str, Any]]:
        return _build_once(
            lineage=lineage,
            output_dir=output_dir,
            bootstrap_replicates=bootstrap_replicates,
            seed=seed,
            created_at_utc=created,
            input_digest=input_digest,
            code_digest=code_digest,
        )

    roster_bytes, metrics, context = rebuild()
    _require_same(inventory_before, inventory_provider(), "initial metric build")
    _require_same(code_before, _code_inventory(), "initial metric build code")
    return publish(
        roster_bytes=roster_bytes,
        metrics=metrics,
        context=context,
        output_root=output_root,
        lineage=lineage,
        inventory_before=inventory_before,
        code_before=code_before,
        inventory_provider=inventory_provider,
        code_provider=_code_inventory,
        rebuild=rebuild,
        state_validator=state_validator,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        created_at_utc=created,
        experiment_root=experiment_root,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260910)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = run(
        output_root=args.output_root,
        bootstrap_replicates=args.bootstrap_replicates,
        seed=args.seed,
    )
    metrics = json.loads((snapshot / "metrics.json").read_text(encoding="utf-8"))
    print(f"Experiment B actual-defined snapshot: {snapshot}")
    print(f"mapping SHA-256: {metrics['actual_defined_roster']['mapping_sha256']}")
    print(f"changed labels: {metrics['actual_defined_roster']['changed_n']}")
    for model, entry in metrics["model_specific_primary"].items():
        comparison = entry["results"]["definition_comparison"]
        print(
            f"{model}: actual-defined rho="
            f"{comparison['actual_defined']['spearman_rho']:.6f}, historical rho="
            f"{comparison['historical_excess_defined']['spearman_rho']:.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
