# -*- coding: utf-8 -*-
"""Experiment B Step 4 validation metrics with fail-closed lineage checks.

The four reported concepts are intentionally separate:

* ``compressor_agreement``: zlib/bz2/lzma instrument agreement;
* ``score_retest_agreement``: continuous reference-score/retest agreement;
* ``global_pooled_true_label_agreement``: association with the one L1--L5
  label attached to each unrelated prompt; and
* ``level_order_gradient``: level ordering and per-level score means.

Experiment B cannot identify Experiment A's per-item five-vector label
estimator: B has one level for each unrelated prompt.  Its z/rank label alpha
is therefore a global-pooled adaptation, not the Experiment A per-item
estimator and not exact Table 6 numerical parity.  No per-item label metric is
claimed here.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import math
import os
import sys
import tempfile
import warnings as python_warnings
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import kendalltau, rankdata, spearmanr

try:
    from experiment_b.validation_schema import (
        COMPRESSORS,
        LEVELS,
        LineageManifest,
        ValidationSchemaError,
        assert_no_nonfinite_numbers,
        load_active_lineage_manifest,
        load_lineage_manifest,
        strict_json_loads,
        validate_validation_row,
    )
except ModuleNotFoundError:  # Support direct execution from experiment_b/.
    from validation_schema import (  # type: ignore[no-redef]
        COMPRESSORS,
        LEVELS,
        LineageManifest,
        ValidationSchemaError,
        assert_no_nonfinite_numbers,
        load_active_lineage_manifest,
        load_lineage_manifest,
        strict_json_loads,
        validate_validation_row,
    )

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation):
        pass

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "outputs"
LEVEL_NUM = {level: index + 1 for index, level in enumerate(LEVELS)}
MODELS = [
    "claude-sonnet-5",
    "gemini-3.6-flash",
    "claude-opus-4-8",
    "gpt-5.6-sol",
    "gpt-5.5",
]

METHODOLOGY_NOTES = [
    (
        "Experiment B has one level per unrelated prompt, so Experiment A's "
        "per-item five-vector estimator is not identifiable."
    ),
    (
        "Experiment B's z/rank label alpha is a global-pooled adaptation, not "
        "Experiment A's per-item estimator and not exact Table 6 numerical parity."
    ),
    "No per-item label metric is claimed.",
]


class _WarningCollector:
    def __init__(self) -> None:
        self._items: list[str] = []
        self._seen: set[str] = set()

    def add(self, message: str) -> None:
        if message not in self._seen:
            self._items.append(message)
            self._seen.add(message)

    @property
    def items(self) -> list[str]:
        return list(self._items)


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float, np.integer, np.floating))
        and math.isfinite(float(value))
    )


def _as_float_or_none(value: Any) -> float | None:
    if not _is_finite_number(value):
        return None
    return float(value)


def _undefined(collector: _WarningCollector, context: str, reason: str) -> None:
    collector.add(f"{context}: undefined ({reason}); serialized as JSON null")


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    """Read all rows, rejecting blanks, duplicate keys, and non-finite trees."""

    rows: list[Mapping[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise RuntimeError(f"cannot open {path}: {exc}") from exc
    with handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                raise RuntimeError(f"blank JSONL row at {path}:{line_no}")
            try:
                value = strict_json_loads(line, path=f"{path}:{line_no}")
            except ValidationSchemaError as exc:
                raise RuntimeError(str(exc)) from exc
            if not isinstance(value, Mapping):
                raise RuntimeError(f"JSONL row is not an object at {path}:{line_no}")
            rows.append(value)
    return rows


def _normalize_lineage(
    lineage: LineageManifest | str | os.PathLike[str] | Mapping[str, Any] | None,
    output_dir: Path,
) -> LineageManifest:
    if lineage is None:
        return load_active_lineage_manifest(output_dir)
    if isinstance(lineage, LineageManifest):
        return lineage
    return load_lineage_manifest(lineage)


def _expected_protocol_for_model(
    lineage: LineageManifest, model: str
) -> Mapping[str, Any] | None:
    raw = lineage.raw
    candidates: list[Any] = []
    for key in (
        "validation_protocols",
        "generation_protocols",
        "protocols_by_model",
    ):
        value = raw.get(key)
        if isinstance(value, Mapping):
            candidates.append(value.get(model))
    validation = raw.get("validation")
    if isinstance(validation, Mapping):
        for key in ("protocols", "generation_protocols", "protocols_by_model"):
            value = validation.get(key)
            if isinstance(value, Mapping):
                candidates.append(value.get(model))
    nonnull = [candidate for candidate in candidates if candidate is not None]
    if len(nonnull) > 1 and any(dict(value) != dict(nonnull[0]) for value in nonnull[1:]):
        raise RuntimeError(f"lineage manifest has conflicting protocols for {model}")
    if not nonnull:
        return None
    if not isinstance(nonnull[0], Mapping):
        raise RuntimeError(f"lineage protocol for {model} is not an object")
    return nonnull[0]


def load_source_index(
    *,
    output_dir: str | os.PathLike[str] | None = None,
    lineage: LineageManifest | str | os.PathLike[str] | Mapping[str, Any] | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Strictly load the manifest-declared active stratified source universe."""

    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    manifest = _normalize_lineage(lineage, directory)
    counts = dict(manifest.expected_dataset_counts)
    if not counts or manifest.expected_total is None:
        raise RuntimeError("active lineage manifest lacks dynamic source dataset counts")

    source_index: dict[str, Mapping[str, Any]] = {}
    observed_counts: dict[str, int] = {}
    for dataset, expected in counts.items():
        path = directory / f"{dataset}_stratified.jsonl"
        if not path.is_file():
            raise RuntimeError(f"manifest-declared source file is missing: {path}")
        rows = _strict_jsonl(path)
        observed_counts[dataset] = len(rows)
        if len(rows) != expected:
            raise RuntimeError(
                f"source count mismatch for {dataset}: observed {len(rows)}, expected {expected}"
            )
        for line_no, row in enumerate(rows, 1):
            item_id = row.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise RuntimeError(f"missing source id at {path}:{line_no}")
            if item_id in source_index:
                raise RuntimeError(f"duplicate source id {item_id!r} at {path}:{line_no}")
            if row.get("dataset") != dataset:
                raise RuntimeError(
                    f"source dataset mismatch at {path}:{line_no}: {row.get('dataset')!r}"
                )
            if row.get("level") not in LEVEL_NUM:
                raise RuntimeError(f"invalid source level at {path}:{line_no}")
            for key in ("category", "prompt"):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise RuntimeError(f"invalid source {key} at {path}:{line_no}")
            if not _is_finite_number(row.get("excess_ratio")):
                raise RuntimeError(f"non-finite source excess_ratio at {path}:{line_no}")
            try:
                assert_no_nonfinite_numbers(row, f"{path}:{line_no}")
            except ValidationSchemaError as exc:
                raise RuntimeError(str(exc)) from exc
            source_index[item_id] = row
    if len(source_index) != manifest.expected_total:
        raise RuntimeError(
            f"source total mismatch: observed {len(source_index)}, "
            f"expected {manifest.expected_total}"
        )
    return source_index


def load_validated_model_items(
    model: str,
    *,
    output_dir: str | os.PathLike[str] | None = None,
    lineage: LineageManifest | str | os.PathLike[str] | Mapping[str, Any] | None = None,
    source_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Strictly load, deduplicate, source-check, and schema-check one model file."""

    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    path = directory / f"validation_{model}.jsonl"
    if not path.exists():
        return [], {"total_n": 0, "valid_n": 0, "legacy_unverified_count": 0}
    manifest = _normalize_lineage(lineage, directory)
    sources = (
        dict(source_index)
        if source_index is not None
        else load_source_index(output_dir=directory, lineage=manifest)
    )
    expected_protocol = _expected_protocol_for_model(manifest, model)
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    legacy_count = 0
    for line_no, raw_row in enumerate(_strict_jsonl(path), 1):
        row = dict(raw_row)
        item_id = row.get("id")
        source = sources.get(item_id) if isinstance(item_id, str) else None
        if source is None:
            raise RuntimeError(f"unknown source id {item_id!r} at {path}:{line_no}")
        try:
            validation = validate_validation_row(
                row,
                expected_model=model,
                source=source,
                require_source=True,
                expected_protocol=expected_protocol,
                legacy_allowlist=manifest.legacy_validation_allowlist,
                model_identity_aliases=manifest.model_identity_aliases,
                seen_ids=seen,
                path=f"{path}:{line_no}",
            )
        except ValidationSchemaError as exc:
            raise RuntimeError(str(exc)) from exc
        legacy_count += int(validation.legacy_unverified)
        items.append(row)
    diagnostics = {
        "total_n": len(items),
        "valid_n": len(items),
        "legacy_unverified_count": legacy_count,
    }
    return items, diagnostics


def load_model_items(
    model: str,
    *,
    output_dir: str | os.PathLike[str] | None = None,
    lineage: LineageManifest | str | os.PathLike[str] | Mapping[str, Any] | None = None,
    source_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning only validated rows."""

    items, _ = load_validated_model_items(
        model,
        output_dir=output_dir,
        lineage=lineage,
        source_index=source_index,
    )
    return items


def _krippendorff_interval_exact(ratings: np.ndarray) -> float:
    """Exact interval Krippendorff alpha in O(number of units) memory.

    Callers must prefilter explicitly.  Unlike the former implementation this
    function never silently removes rows containing NaN or infinity.
    """

    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("ratings must be a two-dimensional matrix")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("ratings contain non-finite values; prefilter explicitly")
    if matrix.shape[0] < 2 or matrix.shape[1] < 2:
        return float("nan")

    raters_per_unit = matrix.shape[1]
    row_sum = matrix.sum(axis=1)
    row_squares = (matrix**2).sum(axis=1)
    value_count = raters_per_unit * matrix.shape[0]
    total = row_sum.sum()
    total_squares = row_squares.sum()

    numerator = 2.0 * (
        total_squares
        - ((row_sum**2 - row_squares) / (raters_per_unit - 1)).sum()
    )
    denominator = (2.0 / (value_count - 1)) * (
        value_count * total_squares - total * total
    )
    if denominator == 0.0:
        return 1.0 if numerator == 0.0 else float("nan")
    result = 1.0 - numerator / denominator
    return float(result) if math.isfinite(float(result)) else float("nan")


def _safe_correlations(
    left: Sequence[float],
    right: Sequence[float],
    *,
    collector: _WarningCollector,
    context: str,
) -> dict[str, float | None]:
    if len(left) != len(right):
        raise ValueError("correlation vectors have different lengths")
    if len(left) < 2:
        _undefined(collector, context, "fewer than two valid pairs")
        return {"rho": None, "p": None, "tau": None, "tau_p": None}
    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    if not np.all(np.isfinite(left_array)) or not np.all(np.isfinite(right_array)):
        raise ValueError("non-finite value reached correlation after prefilter")
    constant = np.ptp(left_array) == 0.0 or np.ptp(right_array) == 0.0
    if constant:
        _undefined(collector, context, "a correlation input is constant")
        return {"rho": None, "p": None, "tau": None, "tau_p": None}
    with python_warnings.catch_warnings():
        python_warnings.simplefilter("ignore")
        rho, p_value = spearmanr(left_array, right_array)
        tau, tau_p = kendalltau(left_array, right_array)
    values = {
        "rho": _as_float_or_none(rho),
        "p": _as_float_or_none(p_value),
        "tau": _as_float_or_none(tau),
        "tau_p": _as_float_or_none(tau_p),
    }
    if any(value is None for value in values.values()):
        _undefined(collector, context, "correlation library returned non-finite output")
    return values


def _safe_alpha(
    matrix: np.ndarray,
    *,
    collector: _WarningCollector,
    context: str,
) -> float | None:
    if matrix.shape[0] < 2:
        _undefined(collector, context, "fewer than two valid units for alpha")
        return None
    value = _krippendorff_interval_exact(matrix)
    if not math.isfinite(value):
        _undefined(collector, context, "alpha denominator/estimate is undefined")
        return None
    return float(value)


def _missing_levels(items: Sequence[Mapping[str, Any]]) -> list[str]:
    present = {item.get("level") for item in items}
    return [level for level in LEVELS if level not in present]


def _metric_result_warnings(
    collector: _WarningCollector, start: int
) -> list[str]:
    return collector.items[start:]


def _level_order_gradient(
    items: Sequence[Mapping[str, Any]],
    *,
    collector: _WarningCollector | None = None,
    context: str = "level_order_gradient",
) -> dict[str, Any]:
    collector = collector or _WarningCollector()
    warning_start = len(collector.items)
    valid: list[Mapping[str, Any]] = []
    excluded = 0
    for item in items:
        if item.get("level") in LEVEL_NUM and _is_finite_number(item.get("excess_ratio")):
            valid.append(item)
        else:
            excluded += 1
    if excluded:
        collector.add(f"{context}: excluded {excluded} invalid/non-finite primary rows")
    missing = _missing_levels(valid)
    if missing:
        collector.add(f"{context}: missing levels {missing}")
    level_means: dict[str, float | None] = {}
    level_ns: dict[str, int] = {}
    for level in LEVELS:
        values = [
            float(item["excess_ratio"]) for item in valid if item.get("level") == level
        ]
        level_ns[level] = len(values)
        if values:
            level_means[level] = float(np.mean(values))
        else:
            level_means[level] = None
            _undefined(collector, f"{context}.{level}.mean", "level has no valid rows")
    correlations = _safe_correlations(
        [float(LEVEL_NUM[item["level"]]) for item in valid],
        [float(item["excess_ratio"]) for item in valid],
        collector=collector,
        context=f"{context}.correlation",
    )
    means = [level_means[level] for level in LEVELS]
    monotonic = (
        all(means[index] > means[index + 1] for index in range(4))
        if all(value is not None for value in means)
        else None
    )
    if monotonic is None:
        _undefined(collector, f"{context}.monotonic", "one or more levels are missing")
    return {
        "total_n": len(items),
        "valid_n": len(valid),
        "alpha_effective_n": 0,
        **correlations,
        "level_means": level_means,
        "level_ns": level_ns,
        "missing_levels": missing,
        "monotonic_strictly_decreasing": monotonic,
        "warnings": _metric_result_warnings(collector, warning_start),
    }


def _compressor_agreement(
    items: Sequence[Mapping[str, Any]],
    *,
    collector: _WarningCollector | None = None,
    context: str = "compressor_agreement",
) -> dict[str, Any]:
    collector = collector or _WarningCollector()
    warning_start = len(collector.items)
    rows: list[list[float]] = []
    excluded = 0
    for item in items:
        per_compressor = item.get("per_compressor")
        if not isinstance(per_compressor, Mapping) or set(per_compressor) != set(COMPRESSORS):
            excluded += 1
            continue
        values: list[float] = []
        valid = True
        for compressor in COMPRESSORS:
            nested = per_compressor.get(compressor)
            if not isinstance(nested, Mapping) or not _is_finite_number(
                nested.get("excess_ratio")
            ):
                valid = False
                break
            values.append(float(nested["excess_ratio"]))
        if valid:
            rows.append(values)
        else:
            excluded += 1
    if excluded:
        collector.add(f"{context}: excluded {excluded} incomplete/non-finite compressor rows")
    matrix = np.asarray(rows, dtype=float).reshape((-1, len(COMPRESSORS)))
    alpha = _safe_alpha(matrix, collector=collector, context=f"{context}.alpha")
    return {
        "total_n": len(items),
        "valid_n": len(rows),
        "alpha_effective_n": len(rows),
        "alpha": alpha,
        "warnings": _metric_result_warnings(collector, warning_start),
    }


def _score_retest_agreement(
    items: Sequence[Mapping[str, Any]],
    *,
    collector: _WarningCollector | None = None,
    context: str = "score_retest_agreement",
) -> dict[str, Any]:
    """Continuous reference-score/retest agreement, never label agreement."""

    collector = collector or _WarningCollector()
    warning_start = len(collector.items)
    pairs: list[tuple[float, float]] = []
    valid_items: list[Mapping[str, Any]] = []
    excluded = 0
    for item in items:
        reference = item.get("strat_excess_ratio")
        retest = item.get("excess_ratio")
        if _is_finite_number(reference) and _is_finite_number(retest):
            pairs.append((float(reference), float(retest)))
            valid_items.append(item)
        else:
            excluded += 1
    if excluded:
        collector.add(f"{context}: excluded {excluded} missing/non-finite score pairs")
    missing = _missing_levels(valid_items)
    if missing:
        collector.add(f"{context}: missing levels {missing}")
    correlations = _safe_correlations(
        [pair[0] for pair in pairs],
        [pair[1] for pair in pairs],
        collector=collector,
        context=f"{context}.correlation",
    )
    matrix = np.asarray(pairs, dtype=float).reshape((-1, 2))
    alpha = _safe_alpha(matrix, collector=collector, context=f"{context}.alpha")
    return {
        "total_n": len(items),
        "valid_n": len(pairs),
        "alpha_effective_n": len(pairs),
        "n": len(pairs),  # Backward-compatible display alias.
        **correlations,
        "alpha": alpha,
        "missing_levels": missing,
        "warnings": _metric_result_warnings(collector, warning_start),
    }


def _five_level_label_agreement(
    items: Sequence[Mapping[str, Any]],
    *,
    collector: _WarningCollector | None = None,
    context: str = "global_pooled_true_label_agreement",
) -> dict[str, Any]:
    """Global-pooled adaptation for L1=5 ... L5=1 subjective labels.

    This is intentionally not named or described as a per-item label metric.
    """

    collector = collector or _WarningCollector()
    warning_start = len(collector.items)
    valid_items: list[Mapping[str, Any]] = []
    excluded = 0
    for item in items:
        if item.get("level") in LEVEL_NUM and _is_finite_number(item.get("excess_ratio")):
            valid_items.append(item)
        else:
            excluded += 1
    if excluded:
        collector.add(f"{context}: excluded {excluded} invalid/non-finite label-score pairs")
    missing = _missing_levels(valid_items)
    if missing:
        collector.add(f"{context}: missing levels {missing}")
    human = np.asarray(
        [6.0 - LEVEL_NUM[item["level"]] for item in valid_items], dtype=float
    )
    measured = np.asarray(
        [float(item["excess_ratio"]) for item in valid_items], dtype=float
    )
    correlations = _safe_correlations(
        human.tolist(),
        measured.tolist(),
        collector=collector,
        context=f"{context}.correlation",
    )

    alpha_z: float | None = None
    alpha_rank: float | None = None
    if len(valid_items) < 2:
        _undefined(collector, f"{context}.alpha_z", "fewer than two valid pairs")
        _undefined(collector, f"{context}.alpha_rank", "fewer than two valid pairs")
    elif np.ptp(human) == 0.0 or np.ptp(measured) == 0.0:
        _undefined(collector, f"{context}.alpha_z", "a rating vector is constant")
        _undefined(collector, f"{context}.alpha_rank", "a rating vector is constant")
    else:
        human_sd = human.std(ddof=1)
        measured_sd = measured.std(ddof=1)
        human_z = (human - human.mean()) / human_sd
        measured_z = (measured - measured.mean()) / measured_sd
        alpha_z = _safe_alpha(
            np.column_stack([human_z, measured_z]),
            collector=collector,
            context=f"{context}.alpha_z",
        )
        human_rank = rankdata(human, method="average")
        measured_rank = rankdata(measured, method="average")
        alpha_rank = _safe_alpha(
            np.column_stack([human_rank, measured_rank]),
            collector=collector,
            context=f"{context}.alpha_rank",
        )
    return {
        "total_n": len(items),
        "valid_n": len(valid_items),
        "alpha_effective_n": len(valid_items),
        "n": len(valid_items),  # Backward-compatible display alias.
        **correlations,
        "alpha_z": alpha_z,
        "alpha_rank": alpha_rank,
        "missing_levels": missing,
        "estimator": "global_pooled_adaptation",
        "warnings": _metric_result_warnings(collector, warning_start),
    }


def _spearman(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Backward-compatible level-order helper with hardened N reporting."""

    result = _level_order_gradient(items)
    return {
        "total_n": result["total_n"],
        "valid_n": result["valid_n"],
        "alpha_effective_n": 0,
        "n": result["valid_n"],
        "rho": result["rho"],
        "p": result["p"],
        "tau": result["tau"],
        "tau_p": result["tau_p"],
        "warnings": result["warnings"],
    }


def _alpha(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Backward-compatible compressor helper; details retain effective Ns."""

    collector = _WarningCollector()
    pooled = _compressor_agreement(items, collector=collector)
    per_level_details: dict[str, dict[str, Any]] = {}
    for level in LEVELS:
        per_level_details[level] = _compressor_agreement(
            [item for item in items if item.get("level") == level],
            collector=collector,
            context=f"compressor_agreement.by_level.{level}",
        )
    return {
        "pooled": pooled["alpha"],
        "n": pooled["valid_n"],
        "total_n": pooled["total_n"],
        "valid_n": pooled["valid_n"],
        "alpha_effective_n": pooled["alpha_effective_n"],
        "per_level": {
            level: details["alpha"] for level, details in per_level_details.items()
        },
        "per_level_details": per_level_details,
        "warnings": collector.items,
    }


def _level_means(items: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    return _level_order_gradient(items)["level_means"]


def _group_by(
    items: Sequence[Mapping[str, Any]], key: str
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        value = item.get(key)
        grouped[value if isinstance(value, str) and value else "?"] .append(item)
    return dict(grouped)


def _build_split_namespace(
    items: Sequence[Mapping[str, Any]],
    metric: Callable[..., dict[str, Any]],
    *,
    collector: _WarningCollector,
    namespace: str,
    include_level: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "pooled": metric(items, collector=collector, context=f"{namespace}.pooled"),
        "by_dataset": {},
        "by_category": {},
    }
    for dataset, subset in sorted(_group_by(items, "dataset").items()):
        result["by_dataset"][dataset] = metric(
            subset,
            collector=collector,
            context=f"{namespace}.by_dataset.{dataset}",
        )
    for category, subset in sorted(_group_by(items, "category").items()):
        result["by_category"][category] = metric(
            subset,
            collector=collector,
            context=f"{namespace}.by_category.{category}",
        )
    if include_level:
        result["by_level"] = {}
        for level in LEVELS:
            subset = [item for item in items if item.get("level") == level]
            result["by_level"][level] = metric(
                subset,
                collector=collector,
                context=f"{namespace}.by_level.{level}",
            )
    return result


def _ordered_models(
    lineage: LineageManifest, model_items: Mapping[str, Sequence[Mapping[str, Any]]]
) -> list[str]:
    result: list[str] = []
    configured = lineage.models if lineage.models else tuple(MODELS)
    for model in (*configured, *model_items.keys()):
        if model not in result:
            result.append(model)
    return result


def compute_validation_report(
    model_items: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    lineage: LineageManifest | Mapping[str, Any] | str | os.PathLike[str],
    validation_diagnostics: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute a machine report from already strictly validated model rows."""

    manifest = lineage if isinstance(lineage, LineageManifest) else load_lineage_manifest(lineage)
    if manifest.expected_total is None or not manifest.expected_dataset_counts:
        raise RuntimeError("lineage manifest lacks expected total/dataset counts")
    diagnostics = validation_diagnostics or {}
    collector = _WarningCollector()
    models_report: dict[str, Any] = {}
    complete_models = 0

    for model in _ordered_models(manifest, model_items):
        items = list(model_items.get(model, []))
        dataset_counts = {
            dataset: len(subset)
            for dataset, subset in sorted(_group_by(items, "dataset").items())
        }
        coverage_complete = len(items) == manifest.expected_total and all(
            dataset_counts.get(dataset, 0) == expected
            for dataset, expected in manifest.expected_dataset_counts.items()
        )
        if coverage_complete:
            complete_models += 1
        else:
            collector.add(
                f"{model}.coverage: incomplete {len(items)}/{manifest.expected_total}; "
                "metrics are INTERIM"
            )
        model_diagnostics = diagnostics.get(model, {})
        valid_n = model_diagnostics.get("valid_n", len(items))
        total_n = model_diagnostics.get("total_n", len(items))
        legacy_count = model_diagnostics.get("legacy_unverified_count", 0)
        models_report[model] = {
            "coverage": {
                "total_n": total_n,
                "valid_n": valid_n,
                "alpha_effective_n": 0,
                "expected_n": manifest.expected_total,
                "fraction": (
                    float(valid_n / manifest.expected_total)
                    if manifest.expected_total
                    else None
                ),
                "dataset_counts": dataset_counts,
                "expected_dataset_counts": dict(manifest.expected_dataset_counts),
                "complete": coverage_complete,
                "legacy_unverified_count": legacy_count,
            },
            "compressor_agreement": _build_split_namespace(
                items,
                _compressor_agreement,
                collector=collector,
                namespace=f"{model}.compressor_agreement",
                include_level=True,
            ),
            "score_retest_agreement": _build_split_namespace(
                items,
                _score_retest_agreement,
                collector=collector,
                namespace=f"{model}.score_retest_agreement",
                include_level=True,
            ),
            "global_pooled_true_label_agreement": _build_split_namespace(
                items,
                _five_level_label_agreement,
                collector=collector,
                namespace=f"{model}.global_pooled_true_label_agreement",
            ),
            "level_order_gradient": _build_split_namespace(
                items,
                _level_order_gradient,
                collector=collector,
                namespace=f"{model}.level_order_gradient",
            ),
        }

    status = "COMPLETE" if models_report and complete_models == len(models_report) else "INTERIM"
    legacy_unverified_count = sum(
        int(model_report["coverage"]["legacy_unverified_count"])
        for model_report in models_report.values()
    )
    return {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "lineage_sha256": manifest.sha256,
        "config_fingerprint": manifest.config_fingerprint,
        "legacy_unverified_count": legacy_unverified_count,
        "coverage": {
            "total_n": sum(
                int(model_report["coverage"]["total_n"])
                for model_report in models_report.values()
            ),
            "valid_n": sum(
                int(model_report["coverage"]["valid_n"])
                for model_report in models_report.values()
            ),
            "alpha_effective_n": 0,
            "models_complete": complete_models,
            "models_total": len(models_report),
        },
        "lineage": {
            "sha256": manifest.sha256,
            "path": str(manifest.path) if manifest.path is not None else None,
            "config_fingerprint": manifest.config_fingerprint,
        },
        "expected": {
            "total_n": manifest.expected_total,
            "dataset_counts": dict(manifest.expected_dataset_counts),
        },
        "methodology_notes": list(METHODOLOGY_NOTES),
        "warnings": collector.items,
        "models": models_report,
    }


def _json_safe(value: Any, collector: _WarningCollector, path: str = "report") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating, np.integer)):
        number = float(value)
        if not math.isfinite(number):
            collector.add(f"{path}: non-finite result replaced with JSON null")
            return None
        if isinstance(value, np.integer):
            return int(value)
        return number
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(child, collector, f"{path}.{key}")
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _json_safe(child, collector, f"{path}[{index}]")
            for index, child in enumerate(value)
        ]
    raise TypeError(f"{path}: unsupported JSON report type {type(value).__name__}")


def _prepare_machine_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    collector = _WarningCollector()
    for warning in report.get("warnings", []):
        collector.add(str(warning))
    payload = _json_safe(copy.deepcopy(dict(report)), collector)
    payload["warnings"] = collector.items
    # This is an intentional final gate, not merely a serialization preference.
    json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return payload


def _fallback_atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Isolated fallback until experiment_b.storage is installed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_machine_report(path: str | os.PathLike[str], report: Mapping[str, Any]) -> None:
    """Write strict machine JSON atomically, preferring the shared B utility."""

    output_path = Path(path)
    payload = _prepare_machine_payload(report)
    try:
        from experiment_b import storage as shared_storage  # type: ignore[attr-defined]
    except (ImportError, ModuleNotFoundError):
        shared_storage = None
    atomic_writer = None
    if shared_storage is not None:
        atomic_writer = getattr(shared_storage, "atomic_write_json", None)
        if not callable(atomic_writer):
            atomic_writer = getattr(shared_storage, "atomic_replace_json", None)
    if callable(atomic_writer):
        atomic_writer(output_path, payload)
    else:
        _fallback_atomic_write_json(output_path, payload)


def _metrics_read_lock(output_dir: Path):
    """Hold a B scope lock while allowing offline metrics under PAUSED.

    Migration obtains the maintenance lock and refuses active scope locks; this
    reader performs the inverse check after acquiring its scope lock.  The PAUSED
    sentinel intentionally does not block read-only metrics.
    """
    try:
        from experiment_b.storage import (
            MigrationInProgressError,
            ProcessLock,
            check_migration_sentinel,
            lock_is_active,
            maintenance_lock_path,
            scope_lock_path,
        )
    except ModuleNotFoundError:  # Support direct execution from experiment_b/.
        from storage import (  # type: ignore[no-redef]
            MigrationInProgressError,
            ProcessLock,
            check_migration_sentinel,
            lock_is_active,
            maintenance_lock_path,
            scope_lock_path,
        )

    experiment_root = output_dir.resolve().parent

    @contextmanager
    def held():
        with ProcessLock(
            scope_lock_path(experiment_root, "metrics:validation"),
            scope="metrics:validation",
        ):
            check_migration_sentinel(experiment_root)
            maintenance = maintenance_lock_path(experiment_root)
            if lock_is_active(maintenance, clean_stale=True):
                raise MigrationInProgressError(
                    f"cannot compute metrics while maintenance lock is active: {maintenance}"
                )
            yield

    return held()


def _verify_status_lineage_binding(
    output_dir: Path, manifest: LineageManifest,
) -> None:
    """Require an active status pointer to pin the exact lineage bytes used."""
    status_path = output_dir.resolve() / "experiment_b_status.json"
    if not status_path.is_file():
        return
    try:
        status_value = strict_json_loads(
            status_path.read_text(encoding="utf-8"), path=str(status_path)
        )
    except (OSError, ValidationSchemaError) as exc:
        raise RuntimeError(f"cannot validate active status/lineage binding: {exc}") from exc
    if not isinstance(status_value, Mapping):
        raise RuntimeError(f"active status is not an object: {status_path}")
    expected_hash = status_value.get("active_lineage_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise RuntimeError("active status lacks a valid active_lineage_sha256")
    if manifest.sha256 != expected_hash:
        raise RuntimeError(
            f"active lineage hash drift: status={expected_hash}, actual={manifest.sha256}"
        )
    pointer = status_value.get("active_lineage_manifest")
    if pointer is not None and manifest.path is not None:
        pointer_path = Path(pointer)
        if not pointer_path.is_absolute():
            pointer_path = (status_path.parent / pointer_path).resolve()
        if pointer_path != manifest.path.resolve():
            raise RuntimeError(
                f"metrics lineage differs from active status pointer: "
                f"{manifest.path.resolve()} != {pointer_path}"
            )


def run_metrics(
    *,
    output_dir: str | os.PathLike[str] = OUTPUT_DIR,
    lineage: LineageManifest | str | os.PathLike[str] | Mapping[str, Any] | None = None,
    output_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load official inputs, compute metrics, and atomically write machine JSON."""

    directory = Path(output_dir)
    with _metrics_read_lock(directory):
        manifest = _normalize_lineage(lineage, directory)
        _verify_status_lineage_binding(directory, manifest)
        if manifest.expected_total is None or not manifest.expected_dataset_counts:
            raise RuntimeError("active lineage manifest lacks dynamic expected counts")
        sources = load_source_index(output_dir=directory, lineage=manifest)
        models = list(manifest.models) if manifest.models else list(MODELS)
        model_items: dict[str, list[dict[str, Any]]] = {}
        diagnostics: dict[str, dict[str, Any]] = {}
        for model in models:
            items, model_diagnostics = load_validated_model_items(
                model,
                output_dir=directory,
                lineage=manifest,
                source_index=sources,
            )
            model_items[model] = items
            diagnostics[model] = model_diagnostics
        report = compute_validation_report(
            model_items,
            lineage=manifest,
            validation_diagnostics=diagnostics,
        )
        destination = directory.resolve() / "validation_metrics.json"
        if output_path is not None and Path(output_path).resolve() != destination:
            raise RuntimeError(
                "metrics output must be exactly the managed file "
                f"{destination}; refusing cross-root or managed-artifact overwrite"
            )
        write_machine_report(destination, report)
        return _prepare_machine_payload(report)


def _fmt(value: Any, *, signed: bool = True, digits: int = 4) -> str:
    if value is None or not _is_finite_number(value):
        return "null"
    spec = f"{'+' if signed else ''}.{digits}f"
    return format(float(value), spec)


def print_text_report(report: Mapping[str, Any]) -> None:
    """Retain a useful human-readable companion to the machine report."""

    expected = report["expected"]
    print("=" * 108)
    print("EXPERIMENT B — STEP 4 RELIABILITY METRICS")
    print("  Four namespaces: compressor | score-retest | global-pooled true label | level gradient")
    print(f"  Expected coverage per model from lineage: {expected['total_n']} {expected['dataset_counts']}")
    print(f"  Lineage SHA-256: {report['lineage_sha256']}")
    print("  NOTE: B global-pooled label alpha is not A's per-item estimator; no per-item label claim.")
    print("=" * 108)
    for model, model_report in report["models"].items():
        coverage = model_report["coverage"]
        compressor = model_report["compressor_agreement"]["pooled"]
        score = model_report["score_retest_agreement"]["pooled"]
        label = model_report["global_pooled_true_label_agreement"]["pooled"]
        gradient = model_report["level_order_gradient"]["pooled"]
        readiness = "COMPLETE" if coverage["complete"] else "INCOMPLETE — INTERIM ONLY"
        print(f"\n{'─' * 108}")
        print(
            f"  MODEL {model}: {coverage['valid_n']}/{coverage['expected_n']} "
            f"({coverage['fraction']:.1%}) [{readiness}] "
            f"legacy-unverified={coverage['legacy_unverified_count']}"
        )
        print(
            "  pooled: "
            f"alpha(compressor)={_fmt(compressor['alpha'])} "
            f"alpha(score-retest)={_fmt(score['alpha'])} "
            f"rho(score-retest)={_fmt(score['rho'])} "
            f"rho(label)={_fmt(label['rho'])} "
            f"alpha(label-z)={_fmt(label['alpha_z'])} "
            f"alpha(label-rank)={_fmt(label['alpha_rank'])} "
            f"rho(level-order)={_fmt(gradient['rho'])}"
        )
        means = " > ".join(
            f"{level}:{_fmt(gradient['level_means'][level])}" for level in LEVELS
        )
        print(
            f"  gradient: {means}; monotonic={gradient['monotonic_strictly_decreasing']}"
        )
        print(
            "  Ns: "
            f"compressor={compressor['valid_n']}/{compressor['total_n']} "
            f"score={score['valid_n']}/{score['total_n']} "
            f"label={label['valid_n']}/{label['total_n']}"
        )
        for split_kind in ("by_dataset", "by_category"):
            split_names = model_report["level_order_gradient"][split_kind]
            if not split_names:
                continue
            print(f"  {split_kind.replace('_', ' ')}:")
            for split, split_gradient in split_names.items():
                split_score = model_report["score_retest_agreement"][split_kind][split]
                split_label = model_report["global_pooled_true_label_agreement"][split_kind][split]
                print(
                    f"    {split:<20} n={split_gradient['valid_n']:<6} "
                    f"rho(order)={_fmt(split_gradient['rho'])} "
                    f"rho(score)={_fmt(split_score['rho'])} "
                    f"rho(label)={_fmt(split_label['rho'])} "
                    f"missing={split_gradient['missing_levels']}"
                )
    print(f"\nSTATUS: {report['status']}")
    if report.get("warnings"):
        print(f"WARNINGS ({len(report['warnings'])}):")
        for warning in report["warnings"]:
            print(f"  - {warning}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--lineage-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_metrics(
        output_dir=args.output_dir,
        lineage=args.lineage_manifest,
        output_path=args.output,
    )
    print_text_report(report)


if __name__ == "__main__":
    main()
