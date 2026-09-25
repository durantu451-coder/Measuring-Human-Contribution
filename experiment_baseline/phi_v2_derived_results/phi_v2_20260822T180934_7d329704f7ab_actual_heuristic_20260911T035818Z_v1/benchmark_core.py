# -*- coding: utf-8 -*-
"""Pure local feature and statistical core for the actual-pair benchmark.

This module has no network, model, GPU, or project-store write capability.  It
contains only deterministic text features and numeric agreement statistics.
"""
from __future__ import annotations

import bisect
import bz2
import hashlib
import json
import lzma
import math
import os
import re
import statistics
import unicodedata
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import numpy as np
from scipy.stats import kendalltau, rankdata

LEVELS = ("L1", "L2", "L3", "L4", "L5")
MODELS = (
    "claude-opus-4-8",
    "claude-sonnet-5",
    "gemini-3.6-flash",
    "gpt-5.5",
    "gpt-5.6-sol",
)
DOMAINS = ("arxiv", "news", "patent", "poetry")
FEATURES = (
    "prompt_bytes",
    "output_bytes",
    "prompt_words",
    "output_words",
    "prompt_to_output_byte_ratio",
    "word_type_coverage",
    "word_token_coverage",
    "word_bigram_coverage",
    "char3_coverage",
    "char5_coverage",
    "char8_coverage",
    "rouge_l_recall",
    "output_type_token_ratio",
    "output_bigram_repeat_fraction",
    "output_self_bits_per_byte",
)
CANDIDATES = ("blackbox_actual_ratio", *FEATURES)
EVALUATORS = ("llama", "mixtral")
SCORE_COLUMNS = (*CANDIDATES, "phi_actual_llama", "phi_actual_mixtral")
PAIRWISE_ALPHA_NAMESPACE = "pairwise_continuous_alpha_z"
JOINT_ALPHA_NAMESPACE = "joint_reference_continuous_alpha_z"
RANK_ALPHA_NAMESPACE = "pairwise_continuous_alpha_rank"
RAW_ALPHA_NAMESPACE = "pairwise_continuous_alpha_raw"
WORD_RE = re.compile(r"\w+", re.UNICODE)
SPACE_RE = re.compile(r"\s+", re.UNICODE)
SHA_RE = re.compile(r"[0-9a-f]{64}")


class BenchmarkError(RuntimeError):
    """A scientific, identity, coverage, or serialization contract failed."""


class CoverageError(BenchmarkError):
    """The complete fixed cohort was not recovered exactly."""


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    payload = json.dumps(
        strict_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def strict_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise BenchmarkError(f"JSON key is not a string: {key!r}")
            result[key] = strict_json_value(child)
        return result
    if isinstance(value, (list, tuple)):
        return [strict_json_value(child) for child in value]
    raise BenchmarkError(f"unsupported JSON type: {type(value).__name__}")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: str | Path, payload: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value, newline=True))


def atomic_write_text(path: str | Path, value: str) -> None:
    atomic_write_bytes(path, value.encode("utf-8"))


def finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{label}: expected a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise BenchmarkError(f"{label}: expected a finite number")
    return result


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise BenchmarkError(f"{label}: expected a lowercase SHA-256")
    return value


def normalize_semantic_key(
    generation_model: Any, domain: Any, item_id: Any
) -> tuple[str, str, str]:
    if not all(isinstance(value, (str, int)) and not isinstance(value, bool)
               for value in (generation_model, domain, item_id)):
        raise BenchmarkError("semantic key components must be strings or integers")
    model = unicodedata.normalize("NFC", str(generation_model).strip())
    domain_value = unicodedata.normalize("NFC", str(domain).strip()).lower()
    identifier = unicodedata.normalize("NFC", str(item_id).strip())
    if not model or not domain_value or not identifier:
        raise BenchmarkError("semantic key components must be non-empty")
    return model, domain_value, identifier


def semantic_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return normalize_semantic_key(
        row.get("generation_model", row.get("model")), row.get("domain"), row.get("id")
    )


def normalize_surface(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("surface input must be a string")
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", text).casefold()).strip()


def word_tokens(text: str) -> tuple[str, ...]:
    return tuple(WORD_RE.findall(normalize_surface(text)))


def char_ngrams(text: str, n: int) -> tuple[str, ...]:
    if n <= 0:
        raise ValueError("n must be positive")
    normalized = normalize_surface(text)
    if len(normalized) < n:
        return ()
    return tuple(normalized[index:index + n] for index in range(len(normalized) - n + 1))


def ngrams(tokens: Sequence[str], n: int) -> tuple[tuple[str, ...], ...]:
    if n <= 0:
        raise ValueError("n must be positive")
    if len(tokens) < n:
        return ()
    return tuple(tuple(tokens[index:index + n]) for index in range(len(tokens) - n + 1))


def multiset_containment(context: Iterable[Any], target: Iterable[Any]) -> float:
    target_counts = Counter(target)
    total = sum(target_counts.values())
    if total == 0:
        return 0.0
    context_counts = Counter(context)
    matched = sum(min(count, context_counts.get(value, 0)) for value, count in target_counts.items())
    return matched / total


def type_containment(context: Iterable[Any], target: Iterable[Any]) -> float:
    target_types = set(target)
    if not target_types:
        return 0.0
    return len(target_types.intersection(context)) / len(target_types)


def lcs_length(left: Sequence[Any], right: Sequence[Any]) -> int:
    """Exact Hunt-Szymanski LCS length, preserving the frozen pilot semantics."""
    if not left or not right:
        return 0
    positions: dict[Any, list[int]] = defaultdict(list)
    for index, value in enumerate(right):
        positions[value].append(index)
    tails: list[int] = []
    for value in left:
        for position in reversed(positions.get(value, ())):
            insertion = bisect.bisect_left(tails, position)
            if insertion == len(tails):
                tails.append(position)
            else:
                tails[insertion] = position
    return len(tails)


def _compress(data: bytes, compressor: str) -> bytes:
    if compressor == "zlib":
        return zlib.compress(data, level=9)
    if compressor == "bz2":
        return bz2.compress(data, compresslevel=9)
    if compressor == "lzma":
        return lzma.compress(data, preset=9)
    raise ValueError(f"unsupported compressor: {compressor}")


def calibrated_self_bits(text: str) -> float:
    """Mean calibrated self-compressed bits across zlib/bz2/lzma."""
    data = text.encode("utf-8", errors="replace")
    if not data:
        return 0.0
    values = []
    for compressor in ("zlib", "bz2", "lzma"):
        raw = len(_compress(data, compressor)) * 8.0
        overhead = len(_compress(b"", compressor)) * 8.0
        values.append(max(0.0, raw - overhead))
    return float(statistics.fmean(values))


def compute_surface_features(prompt: str, output: str) -> dict[str, float]:
    prompt_bytes = len(prompt.encode("utf-8", errors="replace"))
    output_bytes = len(output.encode("utf-8", errors="replace"))
    prompt_word_tokens = word_tokens(prompt)
    output_word_tokens = word_tokens(output)
    prompt_bigrams = ngrams(prompt_word_tokens, 2)
    output_bigrams = ngrams(output_word_tokens, 2)
    output_self_bits = calibrated_self_bits(output)
    values = {
        "prompt_bytes": float(prompt_bytes),
        "output_bytes": float(output_bytes),
        "prompt_words": float(len(prompt_word_tokens)),
        "output_words": float(len(output_word_tokens)),
        "prompt_to_output_byte_ratio": prompt_bytes / output_bytes if output_bytes else 0.0,
        "word_type_coverage": type_containment(prompt_word_tokens, output_word_tokens),
        "word_token_coverage": multiset_containment(prompt_word_tokens, output_word_tokens),
        "word_bigram_coverage": multiset_containment(prompt_bigrams, output_bigrams),
        "char3_coverage": multiset_containment(char_ngrams(prompt, 3), char_ngrams(output, 3)),
        "char5_coverage": multiset_containment(char_ngrams(prompt, 5), char_ngrams(output, 5)),
        "char8_coverage": multiset_containment(char_ngrams(prompt, 8), char_ngrams(output, 8)),
        "rouge_l_recall": (
            lcs_length(output_word_tokens, prompt_word_tokens) / len(output_word_tokens)
            if output_word_tokens else 0.0
        ),
        "output_type_token_ratio": (
            len(set(output_word_tokens)) / len(output_word_tokens)
            if output_word_tokens else 0.0
        ),
        "output_bigram_repeat_fraction": (
            1.0 - len(set(output_bigrams)) / len(output_bigrams)
            if output_bigrams else 0.0
        ),
        "output_self_bits_per_byte": output_self_bits / output_bytes if output_bytes else 0.0,
    }
    if set(values) != set(FEATURES):
        raise BenchmarkError("feature implementation does not match declared protocol")
    if not all(math.isfinite(float(value)) for value in values.values()):
        raise BenchmarkError("surface feature is non-finite")
    return {name: float(values[name]) for name in FEATURES}


def feature_protocol() -> dict[str, Any]:
    return {
        "schema": "actual_heuristic.feature_protocol",
        "schema_version": 1,
        "features": list(FEATURES),
        "text": {
            "unicode_normalization": "NFC",
            "case_normalization": "Unicode casefold",
            "whitespace_normalization": "collapse Unicode whitespace to one ASCII space and strip",
            "word_token_regex": r"\w+ with Python Unicode semantics",
            "byte_encoding": "UTF-8 with errors=replace",
        },
        "coverage": {
            "orientation": "fraction of output units recoverable from prompt units",
            "multiset_numerator": "sum over output-unit types of min(output count, prompt count)",
            "multiset_denominator": "number of output units",
            "type_numerator": "distinct output types also present in prompt",
            "type_denominator": "number of distinct output types",
            "zero_denominator": 0.0,
        },
        "rouge_l_recall": "exact Hunt-Szymanski word-token LCS length divided by output-token count",
        "output_diagnostics": {
            "type_token_ratio": "distinct output word tokens / output word tokens",
            "bigram_repeat_fraction": "1 - distinct output word bigrams / output word bigrams",
            "self_bits_per_byte": "mean calibrated zlib-9/bz2-9/lzma-preset-9 output-only bits / UTF-8 output bytes",
            "empty_output": 0.0,
        },
        "ties": "retained exactly; Spearman uses average midranks",
        "empty_strings": "permitted by feature functions and mapped through explicit zero-denominator rules; canonical cohort requires non-empty actual text",
        "source_protocol": "audited feature semantics from heuristic_overlap_pilot.py protocol version 1",
    }


def krippendorff_interval_exact(ratings: Sequence[Sequence[float]] | np.ndarray) -> float | None:
    """Exact interval Krippendorff alpha in O(m) time and memory."""
    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2:
        raise BenchmarkError("ratings must be a two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise BenchmarkError("ratings contain missing or non-finite values")
    unit_count, rater_count = matrix.shape
    if unit_count < 2 or rater_count < 2:
        return None
    row_sums = matrix.sum(axis=1)
    row_square_sums = np.square(matrix).sum(axis=1)
    observation_count = unit_count * rater_count
    grand_sum = float(row_sums.sum())
    grand_square_sum = float(row_square_sums.sum())
    numerator = 2.0 * (
        grand_square_sum
        - float(np.sum((np.square(row_sums) - row_square_sums) / (rater_count - 1)))
    )
    denominator = (2.0 / (observation_count - 1)) * (
        observation_count * grand_square_sum - grand_sum * grand_sum
    )
    tolerance = np.finfo(float).eps * max(1.0, abs(denominator), abs(numerator)) * 64.0
    if abs(denominator) <= tolerance:
        return 1.0 if abs(numerator) <= tolerance else None
    value = 1.0 - numerator / denominator
    return float(value) if math.isfinite(value) else None


def z_standardize(matrix: np.ndarray) -> np.ndarray | None:
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] < 2:
        return None
    if not np.isfinite(values).all():
        raise BenchmarkError("score matrix contains non-finite values")
    means = values.mean(axis=0)
    stds = values.std(axis=0, ddof=1)
    if np.any(stds == 0.0) or not np.isfinite(stds).all():
        return None
    return (values - means) / stds


def pairwise_continuous_alpha_z(left: Sequence[float], right: Sequence[float]) -> float | None:
    matrix = np.column_stack((left, right)).astype(float, copy=False)
    standardized = z_standardize(matrix)
    return None if standardized is None else krippendorff_interval_exact(standardized)


def joint_reference_continuous_alpha_z(
    candidate: Sequence[float], llama: Sequence[float], mixtral: Sequence[float]
) -> float | None:
    matrix = np.column_stack((candidate, llama, mixtral)).astype(float, copy=False)
    standardized = z_standardize(matrix)
    return None if standardized is None else krippendorff_interval_exact(standardized)


def _correlation_matrix(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        size = matrix.shape[1] if matrix.ndim == 2 else 0
        return np.full((size, size), np.nan), np.zeros(size, dtype=bool)
    if not np.isfinite(matrix).all():
        raise BenchmarkError("score matrix contains non-finite values")
    centered = matrix - matrix.mean(axis=0)
    sums = np.einsum("ij,ij->j", centered, centered)
    valid = sums > 0.0
    denominator = np.sqrt(np.outer(sums, sums))
    with np.errstate(invalid="ignore", divide="ignore"):
        correlation = centered.T @ centered / denominator
    correlation[~np.outer(valid, valid)] = np.nan
    np.fill_diagonal(correlation, np.where(valid, 1.0, np.nan))
    return correlation, valid


def _slice_matrices(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pearson, _ = _correlation_matrix(values)
    ranks = rankdata(values, axis=0, method="average")
    spearman, _ = _correlation_matrix(ranks)
    return spearman, pearson


def _alpha_z_from_r(correlation: float, n: int, raters: int = 2) -> float | None:
    if n < 2 or not math.isfinite(correlation):
        return None
    # Exact simplification of krippendorff_interval_exact after independent
    # sample-z standardization of every complete rater column.
    value = 1.0 - (1.0 - correlation) * (raters * n - 1.0) / (raters * n)
    return float(value) if math.isfinite(value) else None


def _joint_alpha_from_corr(pearson: np.ndarray, candidate: int, n: int) -> float | None:
    refs = (len(SCORE_COLUMNS) - 2, len(SCORE_COLUMNS) - 1)
    correlations = (
        pearson[candidate, refs[0]],
        pearson[candidate, refs[1]],
        pearson[refs[0], refs[1]],
    )
    if n < 2 or not all(math.isfinite(float(value)) for value in correlations):
        return None
    mean_correlation = float(statistics.fmean(float(value) for value in correlations))
    return _alpha_z_from_r(mean_correlation, n, raters=3)


def _metric_key(*parts: str) -> str:
    if any("|" in part for part in parts):
        raise BenchmarkError("metric key component contains separator")
    return "|".join(parts)


def _add_pair_metrics(
    result: dict[str, tuple[float | None, int]],
    spearman: np.ndarray,
    pearson: np.ndarray,
    n: int,
    unit: str,
    *,
    prefix: tuple[str, ...] = (),
) -> None:
    bb = 0
    llama = len(SCORE_COLUMNS) - 2
    mixtral = len(SCORE_COLUMNS) - 1
    for feature_index, feature in enumerate(FEATURES, 1):
        rho = float(spearman[bb, feature_index])
        alpha = _alpha_z_from_r(float(pearson[bb, feature_index]), n)
        result[_metric_key(*prefix, "direct", feature, unit, "rho")] = (
            rho if math.isfinite(rho) else None, n
        )
        result[_metric_key(*prefix, "direct", feature, unit, "alpha_z")] = (alpha, n)
    for evaluator, reference_index in (("llama", llama), ("mixtral", mixtral)):
        for candidate_index, candidate in enumerate(CANDIDATES):
            rho = float(spearman[candidate_index, reference_index])
            alpha = _alpha_z_from_r(float(pearson[candidate_index, reference_index]), n)
            result[_metric_key(*prefix, "convergence", evaluator, candidate, unit, "rho")] = (
                rho if math.isfinite(rho) else None, n
            )
            result[_metric_key(*prefix, "convergence", evaluator, candidate, unit, "alpha_z")] = (
                alpha, n
            )
    for candidate_index, candidate in enumerate(CANDIDATES):
        joint = _joint_alpha_from_corr(pearson, candidate_index, n)
        result[_metric_key(*prefix, "joint", candidate, unit, "alpha_z")] = (joint, n)
        rho_values = (
            spearman[candidate_index, llama], spearman[candidate_index, mixtral]
        )
        mean_rho = (
            float(statistics.fmean(float(value) for value in rho_values))
            if all(math.isfinite(float(value)) for value in rho_values) else None
        )
        result[_metric_key(*prefix, "joint", candidate, unit, "mean_rho")] = (mean_rho, n)


def _add_derived_differences(
    result: dict[str, tuple[float | None, int]],
    *,
    prefix: tuple[str, ...] = (),
    units: Sequence[str],
) -> None:
    for unit in units:
        for evaluator in EVALUATORS:
            for feature in FEATURES:
                for metric in ("rho", "alpha_z"):
                    bb_key = _metric_key(
                        *prefix, "convergence", evaluator, "blackbox_actual_ratio", unit, metric
                    )
                    h_key = _metric_key(*prefix, "convergence", evaluator, feature, unit, metric)
                    left, left_n = result[bb_key]
                    right, right_n = result[h_key]
                    delta = None if left is None or right is None else float(left - right)
                    result[_metric_key(
                        *prefix, "difference", evaluator, feature, unit, f"delta_{metric}"
                    )] = (delta, min(left_n, right_n))
        for feature in FEATURES:
            for metric in ("alpha_z", "mean_rho"):
                bb_key = _metric_key(*prefix, "joint", "blackbox_actual_ratio", unit, metric)
                h_key = _metric_key(*prefix, "joint", feature, unit, metric)
                left, left_n = result[bb_key]
                right, right_n = result[h_key]
                delta = None if left is None or right is None else float(left - right)
                result[_metric_key(
                    *prefix, "joint_difference", feature, unit, f"delta_{metric}"
                )] = (delta, min(left_n, right_n))


def compute_main_metrics(
    values: np.ndarray,
    centered: np.ndarray,
    levels: np.ndarray,
    models: np.ndarray,
    domains: np.ndarray,
) -> dict[str, tuple[float | None, int]]:
    """Compute every bootstrapped rho/alpha/delta from one shared draw."""
    values = np.asarray(values, dtype=float)
    centered = np.asarray(centered, dtype=float)
    if values.shape != centered.shape or values.shape[1] != len(SCORE_COLUMNS):
        raise BenchmarkError("numeric matrix shape differs from score contract")
    if not np.isfinite(values).all() or not np.isfinite(centered).all():
        raise BenchmarkError("numeric matrices contain non-finite values")
    n = values.shape[0]
    if not (len(levels) == len(models) == len(domains) == n):
        raise BenchmarkError("metadata vectors differ from score matrix")
    result: dict[str, tuple[float | None, int]] = {}

    spearman, pearson = _slice_matrices(values)
    _add_pair_metrics(result, spearman, pearson, n, "pooled")

    level_units: list[str] = []
    for level in LEVELS:
        indices = np.flatnonzero(levels == level)
        level_spearman, level_pearson = _slice_matrices(values[indices])
        _add_pair_metrics(result, level_spearman, level_pearson, len(indices), level)
        level_units.append(level)

    centered_spearman, centered_pearson = _slice_matrices(centered)
    _add_pair_metrics(result, centered_spearman, centered_pearson, n, "item_centered")

    # The macro statistic is exactly the arithmetic mean of the five level cells.
    templates = [key.rsplit("|", 2) for key in result if key.endswith("|L1|rho")]
    # Generate macro keys from all direct/convergence/joint rows via explicit prefixes.
    base_specs: list[tuple[str, ...]] = []
    for feature in FEATURES:
        base_specs.extend((("direct", feature),))
    for evaluator in EVALUATORS:
        for candidate in CANDIDATES:
            base_specs.append(("convergence", evaluator, candidate))
    for candidate in CANDIDATES:
        base_specs.append(("joint", candidate))
    for base in base_specs:
        metrics = ("rho", "alpha_z") if base[0] != "joint" else ("alpha_z", "mean_rho")
        for metric in metrics:
            cells = [result[_metric_key(*base, level, metric)] for level in LEVELS]
            finite = [value for value, _ in cells if value is not None]
            value = float(statistics.fmean(finite)) if len(finite) == len(LEVELS) else None
            result[_metric_key(*base, "macro_within_level", metric)] = (
                value, min(count for _, count in cells)
            )

    all_units = ("pooled", *LEVELS, "macro_within_level", "item_centered")
    _add_derived_differences(result, units=all_units)

    # Observed-cohort robustness slices.  Each cell is a macro of its five levels.
    for dimension, vector, names in (
        ("generation_model", models, MODELS),
        ("domain", domains, DOMAINS),
    ):
        for name in names:
            prefix = ("subgroup", dimension, name)
            for level in LEVELS:
                indices = np.flatnonzero((vector == name) & (levels == level))
                group_spearman, group_pearson = _slice_matrices(values[indices])
                _add_pair_metrics(
                    result, group_spearman, group_pearson, len(indices), level, prefix=prefix
                )
            base_specs = []
            for feature in FEATURES:
                base_specs.append(("direct", feature))
            for evaluator in EVALUATORS:
                for candidate in CANDIDATES:
                    base_specs.append(("convergence", evaluator, candidate))
            for base in base_specs:
                for metric in ("rho", "alpha_z"):
                    cells = [
                        result[_metric_key(*prefix, *base, level, metric)]
                        for level in LEVELS
                    ]
                    finite = [value for value, _ in cells if value is not None]
                    value = (
                        float(statistics.fmean(finite))
                        if len(finite) == len(LEVELS) else None
                    )
                    result[_metric_key(
                        *prefix, *base, "macro_within_level", metric
                    )] = (value, min(count for _, count in cells))

    return result


def center_within_items(values: np.ndarray) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] % len(LEVELS):
        raise BenchmarkError("row count is not divisible into five-level items")
    reshaped = matrix.reshape(-1, len(LEVELS), matrix.shape[1])
    return (reshaped - reshaped.mean(axis=1, keepdims=True)).reshape(matrix.shape)


def auxiliary_alpha_records(
    values: np.ndarray,
    centered: np.ndarray,
    levels: np.ndarray,
) -> list[dict[str, Any]]:
    """Point-only alpha_rank/alpha_raw appendix for all main pair comparisons."""
    records: list[dict[str, Any]] = []
    slices: dict[str, np.ndarray] = {"pooled": np.arange(len(values))}
    slices.update({level: np.flatnonzero(levels == level) for level in LEVELS})
    slices["item_centered"] = np.arange(len(values))

    pair_specs: list[tuple[str, str, int, int]] = []
    for feature_index, feature in enumerate(FEATURES, 1):
        pair_specs.append(("direct", feature, 0, feature_index))
    for evaluator_index, evaluator in enumerate(EVALUATORS, len(SCORE_COLUMNS) - 2):
        for candidate_index, candidate in enumerate(CANDIDATES):
            pair_specs.append((f"convergence:{evaluator}", candidate, candidate_index, evaluator_index))

    per_level: dict[tuple[str, str, str], list[float | None]] = defaultdict(list)
    for scope, indices in slices.items():
        matrix = centered[indices] if scope == "item_centered" else values[indices]
        for family, candidate, left_index, right_index in pair_specs:
            pair = matrix[:, [left_index, right_index]]
            raw_alpha = krippendorff_interval_exact(pair)
            ranked = np.column_stack(
                (rankdata(pair[:, 0], method="average"), rankdata(pair[:, 1], method="average"))
            )
            rank_alpha = krippendorff_interval_exact(ranked)
            for namespace, value in (
                (RAW_ALPHA_NAMESPACE, raw_alpha), (RANK_ALPHA_NAMESPACE, rank_alpha)
            ):
                records.append({
                    "family": family,
                    "candidate": candidate,
                    "scope": scope,
                    "metric_namespace": namespace,
                    "point": value,
                    "effective_n": len(indices),
                    "role": "auxiliary",
                })
                if scope in LEVELS:
                    per_level[(family, candidate, namespace)].append(value)
    for (family, candidate, namespace), cells in sorted(per_level.items()):
        finite = [value for value in cells if value is not None]
        records.append({
            "family": family,
            "candidate": candidate,
            "scope": "macro_within_level",
            "metric_namespace": namespace,
            "point": float(statistics.fmean(finite)) if len(finite) == len(LEVELS) else None,
            "effective_n": int(np.sum(levels == LEVELS[0])),
            "role": "auxiliary",
        })
    return records


def tie_diagnostics(
    values: np.ndarray, levels: np.ndarray | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, name in enumerate(SCORE_COLUMNS):
        vector = values[:, index]
        unique, counts = np.unique(vector, return_counts=True)
        tied_observations = int(counts[counts > 1].sum())
        by_level: dict[str, Any] = {}
        if levels is not None:
            for level in LEVELS:
                level_values = vector[np.asarray(levels) == level]
                level_unique, level_counts = np.unique(level_values, return_counts=True)
                level_tied = int(level_counts[level_counts > 1].sum())
                by_level[level] = {
                    "distinct_values": int(len(level_unique)),
                    "tied_observations": level_tied,
                    "tied_observation_fraction": level_tied / len(level_values),
                    "largest_tie_block": int(level_counts.max()),
                    "constant": bool(len(level_unique) == 1),
                }
        result[name] = {
            "distinct_values": int(len(unique)),
            "tied_observations": tied_observations,
            "tied_observation_fraction": tied_observations / len(vector),
            "largest_tie_block": int(counts.max()),
            "pooled_constant": bool(len(unique) == 1),
            "by_level": by_level,
        }
    return result


def mean_per_item_tau_b(values: np.ndarray, left: int, right: int) -> dict[str, Any]:
    reshaped = values[:, [left, right]].reshape(-1, len(LEVELS), 2)
    results: list[float] = []
    undefined = 0
    for item in reshaped:
        statistic = kendalltau(item[:, 0], item[:, 1], variant="b").statistic
        if statistic is None or not math.isfinite(float(statistic)):
            undefined += 1
        else:
            results.append(float(statistic))
    return {
        "mean_tau_b": float(statistics.fmean(results)) if results else None,
        "finite_items": len(results),
        "undefined_items": undefined,
        "role": "auxiliary",
    }


def pair_set_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        [row["generation_model"], row["domain"], row["id"], row["level"], row["scoring_input_sha256"]]
        for row in rows
    ]
    return sha256_bytes(canonical_json_bytes(payload))


def load_feature_rows(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    required = {
        "generation_model", "domain", "id", "level", "scoring_input_sha256",
        "prompt_sha256", "output_sha256", "source_cluster_domain",
        "source_cluster_id", "source_cluster_fingerprint", *SCORE_COLUMNS,
    }
    seen: set[tuple[str, str, str, str]] = set()
    with Path(path).open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                raise CoverageError(f"feature ledger line {line_number} is blank")
            try:
                row = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CoverageError(f"feature ledger line {line_number} is invalid") from exc
            if not isinstance(row, dict) or set(row) != required:
                raise CoverageError(f"feature ledger line {line_number} schema differs")
            key3 = semantic_key(row)
            level = row["level"]
            if level not in LEVELS:
                raise CoverageError(f"feature ledger line {line_number} level differs")
            key = (*key3, level)
            if key in seen:
                raise CoverageError(f"duplicate pair key: {key!r}")
            seen.add(key)
            require_sha256(row["scoring_input_sha256"], "feature scoring hash")
            require_sha256(row["prompt_sha256"], "prompt hash")
            require_sha256(row["output_sha256"], "output hash")
            for name in SCORE_COLUMNS:
                row[name] = finite_float(row[name], f"feature.{name}")
            rows.append(row)
    rows.sort(key=lambda row: (*semantic_key(row), LEVELS.index(row["level"])))
    return rows


def dataset_arrays(
    rows: Sequence[Mapping[str, Any]], *, expected_pairs: int = 56110
) -> dict[str, Any]:
    if len(rows) != expected_pairs:
        raise CoverageError(f"pair count {len(rows)} != {expected_pairs}")
    for start in range(0, len(rows), len(LEVELS)):
        group = rows[start:start + len(LEVELS)]
        keys = {semantic_key(row) for row in group}
        if len(keys) != 1 or [row["level"] for row in group] != list(LEVELS):
            raise CoverageError(f"five-level item contract failed near row {start}")
        if len({row["scoring_input_sha256"] for row in group}) != 1:
            raise CoverageError(f"scoring hash differs within item near row {start}")
    values = np.asarray([[float(row[name]) for name in SCORE_COLUMNS] for row in rows])
    centered = center_within_items(values)
    levels = np.asarray([row["level"] for row in rows], dtype="U2")
    models = np.asarray([row["generation_model"] for row in rows], dtype="U32")
    domains = np.asarray([row["domain"] for row in rows], dtype="U16")
    cluster_keys = [
        (row["source_cluster_domain"], row["source_cluster_id"], row["source_cluster_fingerprint"])
        for row in rows
    ]
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, key in enumerate(cluster_keys):
        grouped[key].append(index)
    clusters = [(key, np.asarray(indices, dtype=np.int64)) for key, indices in sorted(grouped.items())]
    return {
        "values": values,
        "centered": centered,
        "levels": levels,
        "models": models,
        "domains": domains,
        "clusters": clusters,
        "pair_set_sha256": pair_set_sha256(rows),
    }


__all__ = [
    "BenchmarkError", "CoverageError", "LEVELS", "MODELS", "DOMAINS", "FEATURES",
    "CANDIDATES", "EVALUATORS", "SCORE_COLUMNS", "PAIRWISE_ALPHA_NAMESPACE",
    "JOINT_ALPHA_NAMESPACE", "RANK_ALPHA_NAMESPACE", "RAW_ALPHA_NAMESPACE",
    "canonical_json_bytes", "strict_json_value", "sha256_bytes", "sha256_file",
    "atomic_write_bytes", "atomic_write_json", "atomic_write_text", "finite_float",
    "require_sha256", "normalize_semantic_key", "semantic_key", "normalize_surface",
    "word_tokens", "char_ngrams", "ngrams", "multiset_containment", "type_containment",
    "lcs_length", "calibrated_self_bits", "compute_surface_features", "feature_protocol",
    "krippendorff_interval_exact", "z_standardize", "pairwise_continuous_alpha_z",
    "joint_reference_continuous_alpha_z", "compute_main_metrics", "center_within_items",
    "auxiliary_alpha_records", "tie_diagnostics", "mean_per_item_tau_b",
    "pair_set_sha256", "load_feature_rows", "dataset_arrays",
]
