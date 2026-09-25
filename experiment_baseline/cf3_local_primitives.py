"""Dependency-minimal frozen primitives for the local CF3 derivative.

Only Python's standard library, NumPy, and SciPy are imported.  This module
freezes the exact canonical compression and surface-feature semantics used by the
project so the local runner does not import API adapters, transports, models,
tokenizers, socket helpers, or subprocess helpers.  Regression tests require
exact parity with the canonical project implementations.
"""

from __future__ import annotations

import bisect
import bz2
import hashlib
import json
import lzma
import math
import re
import statistics
import unicodedata
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import kendalltau, rankdata


STRICT_SCHEMA_ID = "experiment_a.strict_cf_v1"
MODELS = (
    "claude-sonnet-5",
    "gemini-3.6-flash",
    "claude-opus-4-8",
    "gpt-5.6-sol",
    "gpt-5.5",
)
DOMAINS = ("arxiv", "news", "patent", "poetry")
LEVELS = ("L1", "L2", "L3", "L4", "L5")
COMPRESSORS = ("zlib", "bz2", "lzma")
SEPARATOR = b"\n<<<HC_CONTEXT_TARGET_SEPARATOR>>>\n"
WORD_RE = re.compile(r"\w+", re.UNICODE)
SPACE_RE = re.compile(r"\s+", re.UNICODE)
FEATURE_PROTOCOL_VERSION = 1

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
PRIMARY_LEXICAL_FEATURES = (
    "word_type_coverage",
    "word_token_coverage",
    "word_bigram_coverage",
    "char5_coverage",
    "rouge_l_recall",
)
LENGTH_FEATURES = (
    "prompt_bytes",
    "output_bytes",
    "prompt_words",
    "output_words",
    "prompt_to_output_byte_ratio",
)
OUTPUT_STRUCTURE_FEATURES = (
    "output_type_token_ratio",
    "output_bigram_repeat_fraction",
)
COMPRESSION_DERIVED_FEATURES = ("output_self_bits_per_byte",)
PRIMARY_BOOTSTRAP_FEATURES = PRIMARY_LEXICAL_FEATURES + (
    "prompt_to_output_byte_ratio",
)


@dataclass(frozen=True)
class AggregateGain:
    self_information_bits: float
    conditional_information_bits: float
    gain_bits: float
    contribution_ratio: float


@dataclass(frozen=True)
class InformationGainProfile:
    aggregate: AggregateGain
    per_compressor: dict[str, dict[str, float]]


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not strict canonical JSON: {exc}") from exc


def canonical_jsonl_row_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def canonical_row_sha256(value: Any) -> str:
    return canonical_sha256(value)


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def actual_pair_sha256(prompt: str, output: str) -> str:
    return canonical_sha256(
        {
            "output": output,
            "prompt": prompt,
            "schema": f"{STRICT_SCHEMA_ID}.actual_pair",
        }
    )


def counterfactual_pair_sha256(index: int, prompt: str, output: str) -> str:
    if type(index) is not int or index < 1:
        raise ValueError("index must be a positive integer")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be nonblank")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("output must be nonblank")
    return canonical_sha256(
        {
            "index": index,
            "output": output,
            "prompt": prompt,
            "schema": f"{STRICT_SCHEMA_ID}.counterfactual_pair",
        }
    )


def _to_bytes(text: str | bytes) -> bytes:
    if isinstance(text, bytes):
        return text
    return text.encode("utf-8", errors="replace")


def _compress(data: bytes, compressor: str) -> bytes:
    if compressor == "zlib":
        return zlib.compress(data, level=9)
    if compressor == "bz2":
        return bz2.compress(data, compresslevel=9)
    if compressor == "lzma":
        return lzma.compress(data, preset=9)
    raise ValueError(f"Unsupported compressor: {compressor}")


@lru_cache(maxsize=None)
def _overhead_bits(compressor: str) -> float:
    return len(_compress(b"", compressor)) * 8.0


def _calibrated_bits(data: bytes, compressor: str) -> float:
    if not data:
        return 0.0
    raw = len(_compress(data, compressor)) * 8.0
    return max(0.0, raw - _overhead_bits(compressor))


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    if math.isclose(denominator, 0.0):
        return default
    return numerator / denominator


def information_gain_profile(
    prompt: str,
    output: str,
    compressors: Sequence[str] = COMPRESSORS,
) -> InformationGainProfile:
    """Exact frozen ratio-of-ordered-mean calibrated bit lengths."""

    compressor_names = tuple(compressors)
    if not compressor_names:
        raise ValueError("at least one compressor is required")
    target = _to_bytes(output)
    context = _to_bytes(prompt)
    entries: list[tuple[str, float, float]] = []
    if not target:
        entries = [(name, 0.0, 0.0) for name in compressor_names]
    else:
        prefix = context + SEPARATOR
        joined = prefix + target
        for name in compressor_names:
            self_bits = _calibrated_bits(target, name)
            prefix_bits = _calibrated_bits(prefix, name)
            joined_bits = _calibrated_bits(joined, name)
            entries.append(
                (name, self_bits, max(0.0, joined_bits - prefix_bits))
            )
    self_bits = float(statistics.fmean(entry[1] for entry in entries))
    conditional_bits = float(statistics.fmean(entry[2] for entry in entries))
    gain_bits = max(0.0, self_bits - conditional_bits)
    ratio = _clamp(_safe_divide(gain_bits, self_bits))
    per_compressor = {}
    for name, self_one, conditional_one in entries:
        gain_one = max(0.0, self_one - conditional_one)
        per_compressor[name] = {
            "self_information_bits": self_one,
            "conditional_information_bits": conditional_one,
            "gain_bits": gain_one,
            "contribution_ratio": _clamp(_safe_divide(gain_one, self_one)),
        }
    return InformationGainProfile(
        aggregate=AggregateGain(
            self_information_bits=self_bits,
            conditional_information_bits=conditional_bits,
            gain_bits=gain_bits,
            contribution_ratio=ratio,
        ),
        per_compressor=per_compressor,
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
    return tuple(
        normalized[index : index + n]
        for index in range(len(normalized) - n + 1)
    )


def ngrams(tokens: Sequence[str], n: int) -> tuple[tuple[str, ...], ...]:
    if n <= 0:
        raise ValueError("n must be positive")
    if len(tokens) < n:
        return ()
    return tuple(
        tuple(tokens[index : index + n])
        for index in range(len(tokens) - n + 1)
    )


def multiset_containment(context: Iterable[Any], target: Iterable[Any]) -> float:
    target_counts = Counter(target)
    total = sum(target_counts.values())
    if total == 0:
        return 0.0
    context_counts = Counter(context)
    matched = sum(
        min(count, context_counts.get(value, 0))
        for value, count in target_counts.items()
    )
    return matched / total


def type_containment(context: Iterable[Any], target: Iterable[Any]) -> float:
    target_types = set(target)
    if not target_types:
        return 0.0
    return len(target_types.intersection(context)) / len(target_types)


def lcs_length(left: Sequence[Any], right: Sequence[Any]) -> int:
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


def compute_surface_features(
    prompt: str,
    output: str,
    *,
    output_self_bits: float,
) -> dict[str, float]:
    prompt_bytes = len(prompt.encode("utf-8", errors="replace"))
    output_bytes = len(output.encode("utf-8", errors="replace"))
    prompt_word_tokens = word_tokens(prompt)
    output_word_tokens = word_tokens(output)
    prompt_bigrams = ngrams(prompt_word_tokens, 2)
    output_bigrams = ngrams(output_word_tokens, 2)
    values = {
        "prompt_bytes": float(prompt_bytes),
        "output_bytes": float(output_bytes),
        "prompt_words": float(len(prompt_word_tokens)),
        "output_words": float(len(output_word_tokens)),
        "prompt_to_output_byte_ratio": (
            prompt_bytes / output_bytes if output_bytes else 0.0
        ),
        "word_type_coverage": type_containment(
            prompt_word_tokens, output_word_tokens
        ),
        "word_token_coverage": multiset_containment(
            prompt_word_tokens, output_word_tokens
        ),
        "word_bigram_coverage": multiset_containment(
            prompt_bigrams, output_bigrams
        ),
        "char3_coverage": multiset_containment(
            char_ngrams(prompt, 3), char_ngrams(output, 3)
        ),
        "char5_coverage": multiset_containment(
            char_ngrams(prompt, 5), char_ngrams(output, 5)
        ),
        "char8_coverage": multiset_containment(
            char_ngrams(prompt, 8), char_ngrams(output, 8)
        ),
        "rouge_l_recall": (
            lcs_length(output_word_tokens, prompt_word_tokens)
            / len(output_word_tokens)
            if output_word_tokens
            else 0.0
        ),
        "output_type_token_ratio": (
            len(set(output_word_tokens)) / len(output_word_tokens)
            if output_word_tokens
            else 0.0
        ),
        "output_bigram_repeat_fraction": (
            1.0 - len(set(output_bigrams)) / len(output_bigrams)
            if output_bigrams
            else 0.0
        ),
        "output_self_bits_per_byte": (
            output_self_bits / output_bytes if output_bytes else 0.0
        ),
    }
    if set(values) != set(FEATURES):
        raise RuntimeError("surface feature inventory drift")
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("surface feature is non-finite")
    return values


def safe_kendall(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    if len(set(left)) < 2 or len(set(right)) < 2:
        return None
    value = float(kendalltau(left, right, variant="b").statistic)
    return value if math.isfinite(value) else None


def fast_spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size != right.size or left.size < 3:
        return None
    left_ranks = rankdata(left, method="average")
    right_ranks = rankdata(right, method="average")
    if float(np.std(left_ranks)) == 0.0 or float(np.std(right_ranks)) == 0.0:
        return None
    value = float(np.corrcoef(left_ranks, right_ranks)[0, 1])
    return value if math.isfinite(value) else None
