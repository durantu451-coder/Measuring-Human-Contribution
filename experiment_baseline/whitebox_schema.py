# -*- coding: utf-8 -*-
"""Strict canonical source and score schemas for white-box baseline v2.

The schemas bind every score to a normalized Experiment A semantic key, the
exact ordered scoring inputs, the evaluator identity, and the frozen scorer
protocol.  Validation is intentionally fail-closed: keys are exact, arithmetic
is exact (not tolerance based), booleans are never accepted as numbers, and all
numbers must be finite.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from experiment_b import storage as b_storage
from experiment_baseline import whitebox_core


SCHEMA_VERSION = 2
LEVELS = whitebox_core.LEVELS
CF_INDICES = (0, 1, 2, 3, 4)
MIN_VALID_CFS = 3
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SOURCE_KEYS = frozenset(
    {
        "schema_version",
        "generation_model",
        "domain",
        "id",
        "source_file",
        "levels",
        "counterfactuals",
        "scoring_input_sha256",
    }
)
SOURCE_LEVEL_KEYS = frozenset({"prompt", "output"})
SOURCE_CF_KEYS = frozenset({"index", "prompt", "output", "included"})

SCORE_KEYS = frozenset(
    {
        "schema_version",
        "generation_model",
        "domain",
        "id",
        "scoring_input_sha256",
        "evaluator",
        "evaluator_sha256",
        "protocol_sha256",
        "levels",
        "cf_phis",
        "valid_cf_indices",
        "cf_valid",
        "cf_phi_mean",
        "level_excess",
    }
)
LEVEL_SCORE_KEYS = frozenset({"nll1", "nll2", "phi"})
LEVEL_EXCESS_KEYS = frozenset({"phi", "phi_excess"})

SemanticKey = tuple[str, str, str]
ScoreKey = tuple[str, str, str, str]


class WhiteboxSchemaError(ValueError):
    """A baseline-v2 source, score, protocol, or JSON value is invalid."""


class DuplicateSemanticKeyError(WhiteboxSchemaError):
    """The same semantic key and canonical row occur more than once."""


class ConflictingSemanticKeyError(WhiteboxSchemaError):
    """The same semantic key is associated with different canonical rows."""


class ProtocolMismatchError(WhiteboxSchemaError):
    """A score was produced under a different scoring protocol."""


class EvaluatorMismatchError(WhiteboxSchemaError):
    """A score's evaluator identity or fingerprint does not match."""


# Short aliases for callers that prefer generic schema terminology.
SchemaError = WhiteboxSchemaError
DuplicateKeyError = DuplicateSemanticKeyError
ConflictingKeyError = ConflictingSemanticKeyError


@dataclass(frozen=True)
class SourceValidation:
    semantic_key: SemanticKey
    scoring_input_sha256: str
    canonical_row_sha256: str
    valid_cf_indices: tuple[int, ...]


@dataclass(frozen=True)
class ScoreValidation:
    semantic_key: SemanticKey
    score_key: ScoreKey
    scoring_input_sha256: str
    evaluator_sha256: str
    protocol_sha256: str
    canonical_row_sha256: str
    valid_cf_indices: tuple[int, ...]


# Reuse the repository's single canonical JSON/hash implementation rather than
# creating a subtly different serialization for baseline artifacts.
canonical_json_text = b_storage.canonical_json_text
canonical_json_bytes = b_storage.canonical_json_bytes
canonical_jsonl_row_bytes = b_storage.canonical_jsonl_row_bytes
canonical_row_sha256 = b_storage.canonical_row_sha256
sha256_bytes = b_storage.sha256_bytes


def _error(path: str, message: str) -> WhiteboxSchemaError:
    return WhiteboxSchemaError(f"{path}: {message}")


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(path, "must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], path: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise _error(path, f"keys must be exact (missing={missing}, extra={extra})")


def _require_string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise _error(path, "must be a string")
    if not allow_empty and not value.strip():
        raise _error(path, "must be a non-empty string")
    return value


def _require_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise _error(path, "must be a boolean")
    return value


def _require_int(
    value: Any,
    path: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise _error(path, "must be a non-boolean integer")
    if minimum is not None and value < minimum:
        raise _error(path, f"must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise _error(path, f"must be <= {maximum}")
    return value


def _require_finite_number(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, "must be a non-boolean number")
    if not math.isfinite(float(value)):
        raise _error(path, "must be finite")
    return value


def _require_sha256(value: Any, path: str) -> str:
    value = _require_string(value, path)
    if not _SHA256_RE.fullmatch(value):
        raise _error(path, "must be a lowercase 64-character SHA-256 digest")
    return value


def assert_no_nonfinite_numbers(value: Any, path: str = "value") -> None:
    """Reject non-finite numbers and values outside the strict JSON data model."""

    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise _error(path, "contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise _error(path, "contains a non-string object key")
            assert_no_nonfinite_numbers(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_no_nonfinite_numbers(child, f"{path}[{index}]")
        return
    raise _error(path, f"contains unsupported value type {type(value).__name__}")


def _normalize_text(value: Any, path: str) -> str:
    text = _require_string(value, path).strip()
    return unicodedata.normalize("NFC", text)


def normalize_generation_model(value: Any) -> str:
    """Normalize an Experiment A generation-model component."""

    return _normalize_text(value, "generation_model")


def normalize_domain(value: Any) -> str:
    """Normalize domains using Experiment A's established lowercase key rule."""

    return _normalize_text(value, "domain").lower()


def normalize_item_id(value: Any) -> str:
    """Normalize an item ID without case-folding semantically meaningful titles."""

    return _normalize_text(value, "id")


def normalize_semantic_key(
    generation_model: Any, domain: Any, item_id: Any
) -> SemanticKey:
    """Return the sole source/result join identity."""

    return (
        normalize_generation_model(generation_model),
        normalize_domain(domain),
        normalize_item_id(item_id),
    )


def semantic_key(row: Mapping[str, Any]) -> SemanticKey:
    """Extract a normalized key; filenames are deliberately ignored."""

    row = _require_mapping(row, "row")
    model = row.get("generation_model", row.get("model"))
    return normalize_semantic_key(model, row.get("domain"), row.get("id"))


def score_key(row: Mapping[str, Any]) -> ScoreKey:
    """Return evaluator plus semantic identity for duplicate detection."""

    row = _require_mapping(row, "row")
    evaluator = _require_string(row.get("evaluator"), "row.evaluator")
    return (evaluator, *semantic_key(row))


def _validate_source_levels(
    levels: Any, path: str = "source.levels"
) -> Mapping[str, Any]:
    levels = _require_mapping(levels, path)
    if frozenset(levels) != frozenset(LEVELS):
        missing = sorted(set(LEVELS) - set(levels))
        extra = sorted(set(levels) - set(LEVELS))
        raise _error(path, f"levels must be exactly L1-L5 (missing={missing}, extra={extra})")
    for level in LEVELS:
        entry_path = f"{path}.{level}"
        entry = _require_mapping(levels[level], entry_path)
        _require_exact_keys(entry, SOURCE_LEVEL_KEYS, entry_path)
        _require_string(entry["prompt"], f"{entry_path}.prompt")
        _require_string(entry["output"], f"{entry_path}.output")
    return levels


def _validate_source_counterfactuals(
    counterfactuals: Any, path: str = "source.counterfactuals"
) -> tuple[int, ...]:
    if not isinstance(counterfactuals, list):
        raise _error(path, "must be an ordered JSON array")
    if len(counterfactuals) != len(CF_INDICES):
        raise _error(path, f"must contain exactly {len(CF_INDICES)} entries")
    included: list[int] = []
    for expected_index, raw_entry in enumerate(counterfactuals):
        entry_path = f"{path}[{expected_index}]"
        entry = _require_mapping(raw_entry, entry_path)
        _require_exact_keys(entry, SOURCE_CF_KEYS, entry_path)
        index = _require_int(
            entry["index"], entry_path + ".index", minimum=0, maximum=4
        )
        if index != expected_index:
            raise _error(entry_path + ".index", f"must equal ordered index {expected_index}")
        prompt = _require_string(
            entry["prompt"], entry_path + ".prompt", allow_empty=True
        )
        output = _require_string(
            entry["output"], entry_path + ".output", allow_empty=True
        )
        is_included = _require_bool(entry["included"], entry_path + ".included")
        if is_included and (not prompt.strip() or not output.strip()):
            raise _error(entry_path, "included CF must have non-empty prompt and output")
        if is_included:
            included.append(index)
    if len(included) < MIN_VALID_CFS:
        raise _error(path, f"must include at least {MIN_VALID_CFS} valid CFs")
    return tuple(included)


def scoring_input_payload(
    levels: Mapping[str, Any], counterfactuals: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Build the sole ordered payload whose canonical bytes are input-hashed."""

    _validate_source_levels(levels, "scoring_input.levels")
    # Copy to a list because sequence order, including excluded slots, is part of
    # the scientific input identity.
    cfs = [dict(entry) for entry in counterfactuals]
    _validate_source_counterfactuals(cfs, "scoring_input.counterfactuals")
    return {
        "levels": [
            {
                "level": level,
                "prompt": levels[level]["prompt"],
                "output": levels[level]["output"],
            }
            for level in LEVELS
        ],
        "counterfactuals": [
            {
                "index": entry["index"],
                "prompt": entry["prompt"],
                "output": entry["output"],
                "included": entry["included"],
            }
            for entry in cfs
        ],
    }


def scoring_input_sha256(
    levels: Mapping[str, Any], counterfactuals: Sequence[Mapping[str, Any]]
) -> str:
    """Hash ordered L1-L5 and CF prompt/output/inclusion inputs."""

    return canonical_row_sha256(scoring_input_payload(levels, counterfactuals))


compute_scoring_input_sha256 = scoring_input_sha256


def build_source_row(
    raw: Mapping[str, Any],
    *,
    source_file: str | None = None,
    cf_included: Sequence[bool] | None = None,
) -> dict[str, Any]:
    """Freeze one Experiment A debug record into the canonical source schema.

    When explicit inclusion decisions are not supplied, the established metric
    rule is used: a CF is included iff both prompt and output contain non-space
    text.  The decision is persisted and hashed, never inferred during scoring.
    """

    raw = _require_mapping(raw, "raw")
    model, domain, item_id = normalize_semantic_key(
        raw.get("generation_model", raw.get("model")),
        raw.get("domain"),
        raw.get("id"),
    )
    prompts = _require_mapping(raw.get("prompts"), "raw.prompts")
    outputs = _require_mapping(raw.get("outputs"), "raw.outputs")
    levels: dict[str, dict[str, str]] = {}
    for level in LEVELS:
        levels[level] = {
            "prompt": _require_string(prompts.get(level), f"raw.prompts.{level}"),
            "output": _require_string(outputs.get(level), f"raw.outputs.{level}"),
        }

    raw_cfs = raw.get("counterfactuals")
    if not isinstance(raw_cfs, list) or len(raw_cfs) != len(CF_INDICES):
        raise _error(
            "raw.counterfactuals",
            f"must contain exactly {len(CF_INDICES)} entries",
        )
    if cf_included is not None:
        if isinstance(cf_included, (str, bytes)) or len(cf_included) != len(raw_cfs):
            raise _error("cf_included", "must contain exactly one flag per CF")
        decisions = [
            _require_bool(value, f"cf_included[{index}]")
            for index, value in enumerate(cf_included)
        ]
    else:
        decisions = []

    counterfactuals: list[dict[str, Any]] = []
    for index, raw_cf in enumerate(raw_cfs):
        cf = _require_mapping(raw_cf, f"raw.counterfactuals[{index}]")
        prompt = _require_string(
            cf.get("prompt"), f"raw.counterfactuals[{index}].prompt", allow_empty=True
        )
        output = _require_string(
            cf.get("output"), f"raw.counterfactuals[{index}].output", allow_empty=True
        )
        if cf_included is None:
            if "included" in cf:
                included = _require_bool(
                    cf["included"], f"raw.counterfactuals[{index}].included"
                )
            else:
                included = bool(prompt.strip() and output.strip())
        else:
            included = decisions[index]
        counterfactuals.append(
            {
                "index": index,
                "prompt": prompt,
                "output": output,
                "included": included,
            }
        )

    provenance = source_file
    if provenance is None:
        provenance = raw.get("source_file", raw.get("file"))
    if provenance is not None:
        provenance = _require_string(provenance, "source_file")

    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generation_model": model,
        "domain": domain,
        "id": item_id,
        "source_file": provenance,
        "levels": levels,
        "counterfactuals": counterfactuals,
        "scoring_input_sha256": scoring_input_sha256(levels, counterfactuals),
    }
    validate_source_row(row)
    return row


freeze_source_row = build_source_row
make_source_row = build_source_row


def _register_unique(
    seen: MutableMapping[Any, str], key: Any, row: Mapping[str, Any], path: str
) -> str:
    digest = canonical_row_sha256(row)
    previous = seen.get(key)
    if previous is not None:
        if previous == digest:
            raise DuplicateSemanticKeyError(f"{path}: duplicate semantic key {key!r}")
        raise ConflictingSemanticKeyError(
            f"{path}: conflicting rows for semantic key {key!r}: "
            f"{previous} != {digest}"
        )
    seen[key] = digest
    return digest


def validate_source_row(
    row: Mapping[str, Any],
    *,
    seen: MutableMapping[SemanticKey, str] | None = None,
    path: str = "source",
) -> SourceValidation:
    """Validate one canonical frozen source row."""

    row = _require_mapping(row, path)
    _require_exact_keys(row, SOURCE_KEYS, path)
    if row["schema_version"] != SCHEMA_VERSION:
        raise _error(path + ".schema_version", f"must equal {SCHEMA_VERSION}")

    key = normalize_semantic_key(
        row["generation_model"], row["domain"], row["id"]
    )
    stored_key = (row["generation_model"], row["domain"], row["id"])
    if stored_key != key:
        raise _error(path, f"identity fields must be normalized as {key!r}")

    source_file = row["source_file"]
    if source_file is not None:
        _require_string(source_file, path + ".source_file")
    levels = _validate_source_levels(row["levels"], path + ".levels")
    valid_indices = _validate_source_counterfactuals(
        row["counterfactuals"], path + ".counterfactuals"
    )
    stored_hash = _require_sha256(
        row["scoring_input_sha256"], path + ".scoring_input_sha256"
    )
    expected_hash = scoring_input_sha256(levels, row["counterfactuals"])
    if stored_hash != expected_hash:
        raise _error(
            path + ".scoring_input_sha256",
            f"does not match ordered scoring inputs ({expected_hash})",
        )
    assert_no_nonfinite_numbers(row, path)
    digest = canonical_row_sha256(row)
    if seen is not None:
        digest = _register_unique(seen, key, row, path)
    return SourceValidation(key, stored_hash, digest, valid_indices)


validate_source = validate_source_row


def evaluator_fingerprint(evaluator: str) -> str:
    """Return the expected evaluator identity hash for a supported key."""

    return whitebox_core.evaluator_sha256(evaluator)


def protocol_fingerprint(protocol: Mapping[str, Any] | None = None) -> str:
    """Hash a protocol, or return the accepted scorer protocol hash."""

    if protocol is None:
        return whitebox_core.SCORING_PROTOCOL_SHA256
    protocol = _require_mapping(protocol, "protocol")
    assert_no_nonfinite_numbers(protocol, "protocol")
    return canonical_row_sha256(protocol)


make_evaluator_fingerprint = evaluator_fingerprint
make_protocol_fingerprint = protocol_fingerprint


def _validate_level_scores(levels: Any, path: str) -> Mapping[str, Any]:
    levels = _require_mapping(levels, path)
    if frozenset(levels) != frozenset(LEVELS):
        missing = sorted(set(LEVELS) - set(levels))
        extra = sorted(set(levels) - set(LEVELS))
        raise _error(path, f"levels must be exactly L1-L5 (missing={missing}, extra={extra})")
    for level in LEVELS:
        entry_path = f"{path}.{level}"
        entry = _require_mapping(levels[level], entry_path)
        _require_exact_keys(entry, LEVEL_SCORE_KEYS, entry_path)
        nll1 = _require_finite_number(entry["nll1"], entry_path + ".nll1")
        nll2 = _require_finite_number(entry["nll2"], entry_path + ".nll2")
        phi = _require_finite_number(entry["phi"], entry_path + ".phi")
        if nll1 < 0 or nll2 < 0:
            raise _error(entry_path, "NLL values must be non-negative")
        expected_phi = (nll1 - nll2) / nll1 if nll1 > 0 else 0.0
        if phi != expected_phi:
            raise _error(
                entry_path + ".phi",
                f"must exactly equal legacy NLL arithmetic ({expected_phi!r})",
            )
    return levels


def _validate_valid_cf_indices(value: Any, path: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise _error(path, "must be an ordered JSON array")
    indices = tuple(
        _require_int(item, f"{path}[{offset}]", minimum=0, maximum=4)
        for offset, item in enumerate(value)
    )
    if tuple(sorted(set(indices))) != indices:
        raise _error(path, "must be unique and strictly increasing")
    if len(indices) < MIN_VALID_CFS:
        raise _error(path, f"must contain at least {MIN_VALID_CFS} indices")
    return indices


def build_score_row(
    source: Mapping[str, Any],
    *,
    evaluator: str,
    levels: Mapping[str, Any],
    cf_phis: Sequence[int | float] | Mapping[int, int | float],
    valid_cf_indices: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Build a canonical score row and derive every redundant arithmetic field."""

    source_validation = validate_source_row(source)
    _validate_level_scores(levels, "levels")
    expected_indices = source_validation.valid_cf_indices
    if valid_cf_indices is None:
        indices = expected_indices
    else:
        indices = tuple(valid_cf_indices)
    # Validate through its canonical JSON-list representation.
    indices = _validate_valid_cf_indices(list(indices), "valid_cf_indices")
    if indices != expected_indices:
        raise _error(
            "valid_cf_indices",
            f"must equal source inclusion indices {list(expected_indices)!r}",
        )

    if isinstance(cf_phis, Mapping):
        if set(cf_phis) != set(indices):
            raise _error("cf_phis", "mapping keys must exactly equal valid_cf_indices")
        phi_values = [cf_phis[index] for index in indices]
    else:
        if isinstance(cf_phis, (str, bytes)):
            raise _error("cf_phis", "must be an ordered numeric array")
        phi_values = list(cf_phis)
        if len(phi_values) != len(indices):
            raise _error("cf_phis", "length must equal valid_cf_indices length")
    for offset, value in enumerate(phi_values):
        _require_finite_number(value, f"cf_phis[{offset}]")

    evaluator = _require_string(evaluator, "evaluator")
    evaluator_digest = evaluator_fingerprint(evaluator)
    baseline = statistics.fmean(phi_values)
    level_copy = {
        level: {
            "nll1": levels[level]["nll1"],
            "nll2": levels[level]["nll2"],
            "phi": levels[level]["phi"],
        }
        for level in LEVELS
    }
    excess = {
        level: {
            "phi": level_copy[level]["phi"],
            "phi_excess": level_copy[level]["phi"] - baseline,
        }
        for level in LEVELS
    }
    model, domain, item_id = source_validation.semantic_key
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generation_model": model,
        "domain": domain,
        "id": item_id,
        "scoring_input_sha256": source_validation.scoring_input_sha256,
        "evaluator": evaluator,
        "evaluator_sha256": evaluator_digest,
        "protocol_sha256": protocol_fingerprint(),
        "levels": level_copy,
        "cf_phis": phi_values,
        "valid_cf_indices": list(indices),
        "cf_valid": len(indices),
        "cf_phi_mean": baseline,
        "level_excess": excess,
    }
    validate_score_row(row, source=source, expected_evaluator=evaluator)
    return row


make_score_row = build_score_row


def validate_score_row(
    row: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    expected_evaluator: str | None = None,
    expected_protocol_sha256: str | None = None,
    seen: MutableMapping[ScoreKey, str] | None = None,
    path: str = "score",
) -> ScoreValidation:
    """Validate one score, its exact arithmetic, and optional source parity."""

    row = _require_mapping(row, path)
    _require_exact_keys(row, SCORE_KEYS, path)
    if row["schema_version"] != SCHEMA_VERSION:
        raise _error(path + ".schema_version", f"must equal {SCHEMA_VERSION}")

    key = normalize_semantic_key(
        row["generation_model"], row["domain"], row["id"]
    )
    stored_key = (row["generation_model"], row["domain"], row["id"])
    if stored_key != key:
        raise _error(path, f"identity fields must be normalized as {key!r}")
    input_hash = _require_sha256(
        row["scoring_input_sha256"], path + ".scoring_input_sha256"
    )

    evaluator = _require_string(row["evaluator"], path + ".evaluator")
    if expected_evaluator is not None and evaluator != expected_evaluator:
        raise EvaluatorMismatchError(
            f"{path}.evaluator: {evaluator!r} != expected {expected_evaluator!r}"
        )
    try:
        expected_evaluator_hash = evaluator_fingerprint(evaluator)
    except ValueError as exc:
        raise EvaluatorMismatchError(f"{path}.evaluator: {exc}") from exc
    evaluator_hash = _require_sha256(
        row["evaluator_sha256"], path + ".evaluator_sha256"
    )
    if evaluator_hash != expected_evaluator_hash:
        raise EvaluatorMismatchError(
            f"{path}.evaluator_sha256: does not match evaluator {evaluator!r}"
        )

    protocol_hash = _require_sha256(
        row["protocol_sha256"], path + ".protocol_sha256"
    )
    expected_protocol = (
        protocol_fingerprint()
        if expected_protocol_sha256 is None
        else _require_sha256(
            expected_protocol_sha256, "expected_protocol_sha256"
        )
    )
    if protocol_hash != expected_protocol:
        raise ProtocolMismatchError(
            f"{path}.protocol_sha256: {protocol_hash} != expected {expected_protocol}"
        )

    levels = _validate_level_scores(row["levels"], path + ".levels")
    indices = _validate_valid_cf_indices(
        row["valid_cf_indices"], path + ".valid_cf_indices"
    )
    cf_valid = _require_int(row["cf_valid"], path + ".cf_valid", minimum=MIN_VALID_CFS)
    if cf_valid != len(indices):
        raise _error(path + ".cf_valid", "must equal len(valid_cf_indices)")
    cf_phis = row["cf_phis"]
    if not isinstance(cf_phis, list):
        raise _error(path + ".cf_phis", "must be an ordered JSON array")
    if len(cf_phis) != cf_valid:
        raise _error(path + ".cf_phis", "length must equal cf_valid")
    for offset, value in enumerate(cf_phis):
        _require_finite_number(value, f"{path}.cf_phis[{offset}]")
    cf_mean = _require_finite_number(row["cf_phi_mean"], path + ".cf_phi_mean")
    expected_mean = statistics.fmean(cf_phis)
    if cf_mean != expected_mean:
        raise _error(
            path + ".cf_phi_mean",
            f"must exactly equal ordered CF mean ({expected_mean!r})",
        )

    level_excess = _require_mapping(row["level_excess"], path + ".level_excess")
    if frozenset(level_excess) != frozenset(LEVELS):
        missing = sorted(set(LEVELS) - set(level_excess))
        extra = sorted(set(level_excess) - set(LEVELS))
        raise _error(
            path + ".level_excess",
            f"levels must be exactly L1-L5 (missing={missing}, extra={extra})",
        )
    for level in LEVELS:
        entry_path = f"{path}.level_excess.{level}"
        entry = _require_mapping(level_excess[level], entry_path)
        _require_exact_keys(entry, LEVEL_EXCESS_KEYS, entry_path)
        copied_phi = _require_finite_number(entry["phi"], entry_path + ".phi")
        phi_excess = _require_finite_number(
            entry["phi_excess"], entry_path + ".phi_excess"
        )
        actual_phi = levels[level]["phi"]
        if copied_phi != actual_phi:
            raise _error(entry_path + ".phi", "must exactly equal levels phi")
        expected_excess = actual_phi - cf_mean
        if phi_excess != expected_excess:
            raise _error(
                entry_path + ".phi_excess",
                f"must exactly equal phi - cf_phi_mean ({expected_excess!r})",
            )

    if source is not None:
        source_validation = validate_source_row(source, path="source")
        if source_validation.semantic_key != key:
            raise _error(path, "semantic key does not match source")
        if source_validation.scoring_input_sha256 != input_hash:
            raise _error(path + ".scoring_input_sha256", "does not match source")
        if source_validation.valid_cf_indices != indices:
            raise _error(
                path + ".valid_cf_indices", "does not match source inclusion decisions"
            )

    assert_no_nonfinite_numbers(row, path)
    canonical_hash = canonical_row_sha256(row)
    key_with_evaluator: ScoreKey = (evaluator, *key)
    if seen is not None:
        canonical_hash = _register_unique(seen, key_with_evaluator, row, path)
    return ScoreValidation(
        semantic_key=key,
        score_key=key_with_evaluator,
        scoring_input_sha256=input_hash,
        evaluator_sha256=evaluator_hash,
        protocol_sha256=protocol_hash,
        canonical_row_sha256=canonical_hash,
        valid_cf_indices=indices,
    )


validate_score = validate_score_row


def validate_source_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[SourceValidation, ...]:
    """Validate source rows and reject duplicate or conflicting semantic keys."""

    seen: dict[SemanticKey, str] = {}
    return tuple(
        validate_source_row(row, seen=seen, path=f"sources[{index}]")
        for index, row in enumerate(rows)
    )


def index_source_rows(
    rows: Iterable[Mapping[str, Any]],
) -> dict[SemanticKey, Mapping[str, Any]]:
    """Return a strict semantic-key index over canonical source rows."""

    result: dict[SemanticKey, Mapping[str, Any]] = {}
    seen: dict[SemanticKey, str] = {}
    for index, row in enumerate(rows):
        validation = validate_source_row(row, seen=seen, path=f"sources[{index}]")
        result[validation.semantic_key] = row
    return result


def validate_score_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    sources: Mapping[SemanticKey, Mapping[str, Any]] | None = None,
    expected_evaluator: str | None = None,
    expected_protocol_sha256: str | None = None,
) -> tuple[ScoreValidation, ...]:
    """Validate score rows with strict duplicate/conflict and optional source joins."""

    seen: dict[ScoreKey, str] = {}
    results: list[ScoreValidation] = []
    for index, row in enumerate(rows):
        source = None
        if sources is not None:
            key = semantic_key(row)
            if key not in sources:
                raise _error(f"scores[{index}]", f"no source for semantic key {key!r}")
            source = sources[key]
        results.append(
            validate_score_row(
                row,
                source=source,
                expected_evaluator=expected_evaluator,
                expected_protocol_sha256=expected_protocol_sha256,
                seen=seen,
                path=f"scores[{index}]",
            )
        )
    return tuple(results)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WhiteboxSchemaError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(token: str) -> None:
    raise WhiteboxSchemaError(f"non-standard/non-finite JSON constant {token!r}")


def strict_json_loads(data: str | bytes, *, path: str = "JSON") -> Any:
    """Decode strict UTF-8 JSON, rejecting duplicate keys and NaN/Infinity."""

    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise _error(path, f"invalid UTF-8: {exc}") from exc
    elif isinstance(data, str):
        text = data
    else:
        raise _error(path, "input must be str or bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, WhiteboxSchemaError) as exc:
        if isinstance(exc, WhiteboxSchemaError):
            raise _error(path, str(exc)) from exc
        raise _error(path, str(exc)) from exc
    assert_no_nonfinite_numbers(value, path)
    return value


def strict_json_load(path: str | Path) -> Any:
    """Read and decode one strict UTF-8 JSON file."""

    source = Path(path)
    return strict_json_loads(source.read_bytes(), path=str(source))


def strict_jsonl_loads(data: str | bytes, *, path: str = "JSONL") -> list[Any]:
    """Decode strict JSONL without accepting blank physical records."""

    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise _error(path, f"invalid UTF-8: {exc}") from exc
    elif isinstance(data, str):
        text = data
    else:
        raise _error(path, "input must be str or bytes")
    if not text:
        return []
    lines = text.splitlines()
    if any(not line.strip() for line in lines):
        raise _error(path, "blank JSONL rows are forbidden")
    return [
        strict_json_loads(line, path=f"{path}:{index}")
        for index, line in enumerate(lines, start=1)
    ]


__all__ = [
    "CF_INDICES",
    "ConflictingKeyError",
    "ConflictingSemanticKeyError",
    "DuplicateKeyError",
    "DuplicateSemanticKeyError",
    "EvaluatorMismatchError",
    "LEVELS",
    "LEVEL_EXCESS_KEYS",
    "LEVEL_SCORE_KEYS",
    "MIN_VALID_CFS",
    "PROTOCOL_SHA256",
    "ProtocolMismatchError",
    "SCHEMA_VERSION",
    "SCORE_KEYS",
    "SOURCE_KEYS",
    "SchemaError",
    "ScoreKey",
    "ScoreValidation",
    "SemanticKey",
    "SourceValidation",
    "WhiteboxSchemaError",
    "assert_no_nonfinite_numbers",
    "build_score_row",
    "build_source_row",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_jsonl_row_bytes",
    "canonical_row_sha256",
    "compute_scoring_input_sha256",
    "evaluator_fingerprint",
    "freeze_source_row",
    "index_source_rows",
    "make_evaluator_fingerprint",
    "make_protocol_fingerprint",
    "make_score_row",
    "make_source_row",
    "normalize_domain",
    "normalize_generation_model",
    "normalize_item_id",
    "normalize_semantic_key",
    "protocol_fingerprint",
    "score_key",
    "scoring_input_payload",
    "scoring_input_sha256",
    "semantic_key",
    "sha256_bytes",
    "strict_json_load",
    "strict_json_loads",
    "strict_jsonl_loads",
    "validate_score",
    "validate_score_row",
    "validate_score_rows",
    "validate_source",
    "validate_source_row",
    "validate_source_rows",
]

# Public constant after helper definitions, so it cannot accidentally diverge
# from the canonical scorer module.
PROTOCOL_SHA256 = whitebox_core.SCORING_PROTOCOL_SHA256
