"""Information-theoretic primitives approximated with compression.

The implementation uses compressed code length as a practical proxy for
self-information. Conditional information is approximated by the extra compressed
length needed to encode a target after a context has already been encoded.
"""

from __future__ import annotations

import bz2
import lzma
import math
import re
import statistics
import zlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence


DEFAULT_COMPRESSORS = ("zlib", "bz2", "lzma")
SEPARATOR = b"\n<<<HC_CONTEXT_TARGET_SEPARATOR>>>\n"


@dataclass(frozen=True)
class CompressionPairEntry:
    """Calibrated self/conditional lengths for one compressor."""

    compressor: str
    self_information_bits: float
    conditional_information_bits: float


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
    """Return the deterministic empty-stream overhead for one compressor."""

    return len(_compress(b"", compressor)) * 8.0


def _calibrated_bits_bytes(data: bytes, compressor: str) -> float:
    if not data:
        return 0.0
    raw = len(_compress(data, compressor)) * 8.0
    return max(0.0, raw - _overhead_bits(compressor))


def compressed_bits_one(text: str | bytes, compressor: str = "zlib") -> float:
    """Return calibrated compressed length in bits for one compressor."""

    return _calibrated_bits_bytes(_to_bytes(text), compressor)


def compression_pair_profile(
    target: str | bytes,
    context: str | bytes,
    compressors: Sequence[str] | None = DEFAULT_COMPRESSORS,
) -> tuple[CompressionPairEntry, ...]:
    """Compute ordered self/conditional lengths with one raw pass per payload.

    The returned entries preserve compressor order so callers can reproduce the
    canonical aggregate exactly.  Only the constant empty-stream overhead is
    memoized; prompt/output payloads are never cached globally.
    """

    compressor_names = tuple(compressors or DEFAULT_COMPRESSORS)
    target_bytes = _to_bytes(target)
    context_bytes = _to_bytes(context)
    if not target_bytes:
        return tuple(
            CompressionPairEntry(name, 0.0, 0.0) for name in compressor_names
        )

    prefix = context_bytes + SEPARATOR
    with_target = prefix + target_bytes
    entries = []
    for name in compressor_names:
        self_bits = _calibrated_bits_bytes(target_bytes, name)
        prefix_bits = _calibrated_bits_bytes(prefix, name)
        joined_bits = _calibrated_bits_bytes(with_target, name)
        entries.append(
            CompressionPairEntry(
                compressor=name,
                self_information_bits=self_bits,
                conditional_information_bits=max(0.0, joined_bits - prefix_bits),
            )
        )
    return tuple(entries)


def compressed_bits(
    text: str | bytes,
    compressors: Sequence[str] | None = DEFAULT_COMPRESSORS,
) -> float:
    """Return mean calibrated compressed length in bits across compressors."""

    compressors = compressors or DEFAULT_COMPRESSORS
    if not compressors:
        raise ValueError("At least one compressor is required.")
    values = [compressed_bits_one(text, compressor) for compressor in compressors]
    return float(statistics.fmean(values))


def compressed_bits_per_compressor(
    text: str | bytes,
    compressors: Sequence[str] | None = None,
) -> dict[str, float]:
    """Return calibrated compressed length in bits for each compressor individually.

    Unlike ``compressed_bits`` which averages across compressors, this retains the
    per-compressor values needed for inter-rater reliability metrics (Krippendorff's α).
    """
    compressors = compressors or DEFAULT_COMPRESSORS
    if not compressors:
        raise ValueError("At least one compressor is required.")
    return {compressor: compressed_bits_one(text, compressor) for compressor in compressors}


def conditional_compressed_bits_per_compressor(
    target: str | bytes,
    context: str | bytes,
    compressors: Sequence[str] | None = None,
) -> dict[str, float]:
    """Approximate C(target | context) for each compressor individually.

    Unlike ``conditional_compressed_bits`` which averages across compressors, this
    retains the per-compressor values needed for inter-rater reliability metrics.
    """
    compressors = compressors or DEFAULT_COMPRESSORS
    target_bytes = _to_bytes(target)
    context_bytes = _to_bytes(context)
    if not target_bytes:
        return {compressor: 0.0 for compressor in compressors}

    result: dict[str, float] = {}
    prefix = context_bytes + SEPARATOR
    with_target = prefix + target_bytes
    for compressor in compressors:
        increment = compressed_bits_one(with_target, compressor) - compressed_bits_one(
            prefix, compressor
        )
        result[compressor] = max(0.0, increment)
    return result


def conditional_compressed_bits(
    target: str | bytes,
    context: str | bytes,
    compressors: Sequence[str] | None = DEFAULT_COMPRESSORS,
) -> float:
    """Approximate C(target | context) with incremental compressed length."""

    compressors = compressors or DEFAULT_COMPRESSORS
    target_bytes = _to_bytes(target)
    context_bytes = _to_bytes(context)
    if not target_bytes:
        return 0.0

    values: list[float] = []
    prefix = context_bytes + SEPARATOR
    with_target = prefix + target_bytes
    for compressor in compressors:
        increment = compressed_bits_one(with_target, compressor) - compressed_bits_one(
            prefix, compressor
        )
        values.append(max(0.0, increment))
    return float(statistics.fmean(values))


def normalized_compression_distance(
    left: str | bytes,
    right: str | bytes,
    compressors: Sequence[str] | None = DEFAULT_COMPRESSORS,
) -> float:
    """Return a clipped normalized compression distance between two strings."""

    compressors = compressors or DEFAULT_COMPRESSORS
    c_left = compressed_bits(left, compressors)
    c_right = compressed_bits(right, compressors)
    denom = max(c_left, c_right)
    if denom <= 0:
        return 0.0
    joined = _to_bytes(left) + SEPARATOR + _to_bytes(right)
    c_joined = compressed_bits(joined, compressors)
    distance = (c_joined - min(c_left, c_right)) / denom
    return clamp(distance, 0.0, 1.0)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    if math.isclose(denominator, 0.0):
        return default
    return numerator / denominator


@dataclass(frozen=True)
class CompressionConfig:
    """Configuration shared by metric functions."""

    compressors: tuple[str, ...] = DEFAULT_COMPRESSORS

    @classmethod
    def from_iterable(cls, compressors: Iterable[str] | None) -> "CompressionConfig":
        if compressors is None:
            return cls()
        return cls(tuple(compressors))
