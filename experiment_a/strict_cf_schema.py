# -*- coding: utf-8 -*-
"""Strict-CF v1 constants, canonical identities, and durable row validators.

The module is intentionally API-client-free.  Preparation, generation,
finalization, scoring, and analysis import this one contract so that identities,
text pairs, metric semantics, and provenance cannot drift between stages.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, MutableSet, Sequence

from experiment_b import storage
from experiment_a.strict_cf_transport import (
    TRANSPORT_ABI_SHA256,
    TRANSPORT_ABI_VERSION,
)

SCHEMA_VERSION = 2
SCHEMA_ID = "experiment_a.strict_cf_v1"
MANIFEST_SCHEMA = f"{SCHEMA_ID}.manifest"
PREPARATION_LINEAGE_SCHEMA = f"{SCHEMA_ID}.preparation_lineage"
# Backward-compatible name for code that imports the preparation lineage ID.
LINEAGE_SCHEMA = PREPARATION_LINEAGE_SCHEMA

MODELS = (
    "claude-sonnet-5",
    "gemini-3.6-flash",
    "claude-opus-4-8",
    "gpt-5.6-sol",
    "gpt-5.5",
)
MODEL_NAMES = MODELS
DOMAINS = ("arxiv", "news", "patent", "poetry")
LEVELS = ("L1", "L2", "L3", "L4", "L5")
COMPRESSORS = ("zlib", "bz2", "lzma")
MAIN_CALL_LABELS = (
    "L1_polish",
    "L2_rewrite",
    "L3_bullets",
    "L3_expand",
    "L4_2sent",
    "L4_expand",
    "L5_keywords",
)
LEVEL_MAIN_CALL = {
    "L1": "L1_polish",
    "L2": "L2_rewrite",
    "L3": "L3_expand",
    "L4": "L4_expand",
    "L5": "L5_keywords",
}

EXPECTED_MODELS = 5
EXPECTED_DOMAINS = 4
EXPECTED_LEVELS = 5
EXPECTED_SOURCES_PER_DOMAIN = 200
EXPECTED_SOURCE_CLUSTERS = 800
EXPECTED_MODEL_ITEMS = 4000
EXPECTED_LEVEL_ROWS = 20000
EXPECTED_SELECTED_SOURCE_HASHES_SHA256 = {
    "arxiv": "85910bdfb67e19edc92bc15c9dd35b3ba545612edfcba1816a30d157412a63c3",
    "news": "bb2a1ea210242dec6084c8f171e0bdec5c5eb03bd23ce753df14a84ef9713248",
    "patent": "c7b9a7aa0d5ad969d23c2fe45c48814882225338239d7cdc920ebac26245c9ca",
    "poetry": "110c6e1473b0f6100e6fe91f282e1f86dac5b6e79943bd1fe7db2c89c0e7f376",
}
EXPECTED_SELECTED_MODEL_ITEM_PROVENANCE_TIERS = {
    "exact": 2654,
    "historical_backend_b_attested": 1346,
}
EXPECTED_SELECTED_LEVEL_PROVENANCE_TIERS = {
    "exact": 13270,
    "historical_backend_b_attested": 6730,
}
STRICT_CF_COUNT = 5
SELECTION_SEED = "strict-cf-v1:sha256-rank:2026-09-03"
SELECTION_ALGORITHM = "sha256(seed\\0domain\\0source_text_sha256), ascending"

STATUS_ACTUAL_VALID = "actual_valid"
STATUS_LEGACY_SHARED_BASELINE_INVALID = "legacy_shared_baseline_invalid_for_strict_cf"
STATUS_LEGACY_SHARED_EXCESS_INVALID = "legacy_shared_excess_invalid_for_strict_cf"
PROVENANCE_TIER_EXACT = "exact"
PROVENANCE_TIER_HISTORICAL_API821 = "historical_backend_b_attested"
PROVENANCE_TIER_LEGACY_UNATTESTED = "legacy_unattested"
PROVENANCE_TIERS = (
    PROVENANCE_TIER_EXACT,
    PROVENANCE_TIER_HISTORICAL_API821,
    PROVENANCE_TIER_LEGACY_UNATTESTED,
)
STRICT_ACTUAL_PROVENANCE_TIERS = (
    PROVENANCE_TIER_EXACT,
    PROVENANCE_TIER_HISTORICAL_API821,
)
VERIFICATION_TIERS = (
    "recomputed_actual_and_per_compressor",
    "stored_result_debug_actual_parity",
)
ACTUAL_METRIC_STATUS = {
    "actual_ratio": STATUS_ACTUAL_VALID,
    "per_compressor_actual_ratio": STATUS_ACTUAL_VALID,
    "legacy_shared_baseline_mean": STATUS_LEGACY_SHARED_BASELINE_INVALID,
    "legacy_shared_excess_ratio": STATUS_LEGACY_SHARED_EXCESS_INVALID,
    "legacy_per_compressor_baseline_mean": STATUS_LEGACY_SHARED_BASELINE_INVALID,
    "legacy_per_compressor_excess_ratio": STATUS_LEGACY_SHARED_EXCESS_INVALID,
}

SCORING_METHOD = "strict_cf_v1_compression_information_gain"
SCORING_PROTOCOL_VERSION = 1
SCORING_PROTOCOL = {
    "actual_input": "actual.prompt + actual.output",
    "baseline": "arithmetic_mean_of_five_counterfactual_ratios",
    "compressors": list(COMPRESSORS),
    "counterfactual_input": "counterfactual.prompt + counterfactual.output",
    "counterfactuals": STRICT_CF_COUNT,
    "method": SCORING_METHOD,
    "schema_version": SCORING_PROTOCOL_VERSION,
}

# Existing actual rows are admitted only from these exact historical collection
# routes.  They are observation-source protocols, never future CF transports.
ACTUAL_SOURCE_PROTOCOLS = {
    model: {
        "config_route": "copilot",
        "call_route": "copilot-2.2.15-formal",
        "gateway": "local_slot",
        "max_output_tokens": 4096,
        "client_relative_path": "human_contribution/copilot_responses_adapter.py",
        "reasoning_effort": "low",
    }
    for model in MODELS[:3]
}
ACTUAL_SOURCE_PROTOCOLS.update(
    {
        model: {
            "config_route": "backend_c",
            "call_route": "backend_c",
            "gateway": "auto",
            "max_output_tokens": 4096,
            "client_relative_path": "backend_c/api_call_1(1).py",
            "reasoning_effort": "low",
        }
        for model in MODELS[3:]
    }
)

# Compatibility alias for Stage-0 actual provenance readers.  New strict-CF
# generation must consume a run-local formal route binding instead.
MODEL_PROTOCOLS = ACTUAL_SOURCE_PROTOCOLS

EXPECTED_ADOPTED_CALLS_PER_LEVEL = 6
EXPECTED_LEVEL_ROWS_PER_MODEL = EXPECTED_LEVEL_ROWS // len(MODELS)
EXPECTED_ADOPTED_CALLS_PER_MODEL = (
    EXPECTED_LEVEL_ROWS_PER_MODEL * EXPECTED_ADOPTED_CALLS_PER_LEVEL
)
EXPECTED_ADOPTED_CALLS = EXPECTED_LEVEL_ROWS * EXPECTED_ADOPTED_CALLS_PER_LEVEL

STRICT_CF_SLOT_CONTRACTS = {
    model: {
        "generation_model": model,
        "expected_level_rows": EXPECTED_LEVEL_ROWS_PER_MODEL,
        "expected_adopted_calls": EXPECTED_ADOPTED_CALLS_PER_MODEL,
        "reconstruction_calls_per_level": 1,
        "counterfactual_calls_per_level": STRICT_CF_COUNT,
        "max_output_tokens": 4096,
        "reasoning_effort": "low",
        "terminal_status": "completed",
        "exact_returned_model": True,
        "alias_policy": "forbid",
        "fallback_policy": "forbid",
        "provider_attempts_per_intent": 1,
        "formal_pointer_path": f"formal/{model}.json",
    }
    for model in MODELS
}

# A separately attested historical actual tier.  These protocols are valid only
# for immutable pre-API3rd actual observations named by the cutover manifest;
# every newly generated strict-CF call continues to use MODEL_PROTOCOLS.
HISTORICAL_API821_PROTOCOLS = {
    "gpt-5.6-sol": {"gateway": 2, "max_output_tokens": 4096},
    "gpt-5.5": {"gateway": 1, "max_output_tokens": 4096},
}
HISTORICAL_API821_CUTOVER_RELATIVE_PATH = (
    "experiment_a/backend_c_cutover_manifest.json"
)

CREATION_CODE_ROLES = frozenset(
    {
        "schema",
        "preparation",
        "routes",
        "transport",
        "route_bundle",
        "route_registration",
        "runner",
        "launcher",
        "finalizer",
        "actual_analysis",
        "metrics",
        "compression",
        "outage_guard",
        "copilot_global_slots",
        "storage",
    }
)
CREATION_CLIENT_ROLES = frozenset()

ARTIFACT_SPECS = {
    "preparation_lineage": ("snapshots/preparation_lineage.json", 1, True),
    "historical_cutover_manifest": (
        "snapshots/backend_c_cutover_manifest.json",
        1,
        True,
    ),
    "historical_repair_audit": (
        "snapshots/strict_cf_historical_tier_audit_20260904.json",
        1,
        True,
    ),
    "historical_repair_method": (
        "snapshots/strict_cf_historical_tier_feasibility_method_20260904.md",
        1,
        True,
    ),
    "source_clusters": ("snapshots/source_clusters.jsonl", EXPECTED_SOURCE_CLUSTERS, True),
    "model_items": ("snapshots/model_items.jsonl", EXPECTED_MODEL_ITEMS, True),
    "full_model_items": ("snapshots/full_model_items.jsonl", None, True),
    "actual_levels": ("snapshots/actual_levels.jsonl", EXPECTED_LEVEL_ROWS, True),
    # The full eligible corpus is intentionally unmatched and its size is fixed
    # by input lineage rather than a study-design constant.
    "full_actual_levels": ("snapshots/full_actual_levels.jsonl", None, True),
    "lineage": ("lineage.json", 1, False),
    "blackbox": ("final/blackbox.jsonl", EXPECTED_LEVEL_ROWS, False),
    "source": ("final/source.jsonl", EXPECTED_LEVEL_ROWS, False),
    "finalized": ("FINALIZED", 1, False),
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LINEAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class StrictCFSchemaError(ValueError):
    """A strict-CF manifest, row, identity, or provenance is invalid."""


def _error(path: str, message: str) -> StrictCFSchemaError:
    return StrictCFSchemaError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(path, "must be an object")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, "must be a non-empty string")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise _error(path, f"must be a non-boolean integer >= {minimum}")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, "must be a non-boolean number")
    result = float(value)
    if not math.isfinite(result):
        raise _error(path, "must be finite")
    return result


def _sha256(value: Any, path: str) -> str:
    value = _string(value, path)
    if not _SHA256_RE.fullmatch(value):
        raise _error(path, "must be a lowercase SHA-256 hex digest")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    keys = set(value)
    if keys != expected:
        raise _error(
            path,
            f"keys must be exact (missing={sorted(expected - keys)}, "
            f"extra={sorted(keys - expected)})",
        )


def _timestamp(value: Any, path: str) -> str:
    text = _string(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(path, "must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(path, "must include a UTC offset")
    if parsed.utcoffset().total_seconds() != 0:
        raise _error(path, "must be normalized to UTC")
    return text


# Canonical serialization/digest wrappers deliberately delegate to the shared
# Experiment B storage implementation; this module defines no second dialect.
def canonical_json_text(value: Any) -> str:
    return storage.canonical_json_text(value)


def canonical_json_bytes(value: Any) -> bytes:
    return storage.canonical_json_bytes(value)


def canonical_sha256(value: Any) -> str:
    return storage.sha256_bytes(storage.canonical_json_bytes(value))


def canonical_digest(value: Any) -> str:
    return canonical_sha256(value)


def canonical_row_sha256(value: Any) -> str:
    return storage.canonical_row_sha256(value)


def cohort_root_preimage(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable scientific cohort preimage, excluding its own hash."""

    cohort = dict(_mapping(manifest.get("cohort"), "manifest.cohort"))
    cohort.pop("root_sha256", None)
    artifacts = _mapping(manifest.get("artifacts"), "manifest.artifacts")
    selected_artifacts = {}
    for name in ("source_clusters", "model_items", "actual_levels"):
        entry = _mapping(artifacts.get(name), f"manifest.artifacts.{name}")
        selected_artifacts[name] = {
            "path": entry.get("path"),
            "row_count": entry.get("row_count"),
            "sha256": entry.get("sha256"),
        }
    return {
        "models": list(manifest.get("models", ())),
        "domains": list(manifest.get("domains", ())),
        "levels": list(manifest.get("levels", ())),
        "expected_counts": dict(_mapping(manifest.get("expected_counts"), "manifest.expected_counts")),
        "selection": dict(_mapping(manifest.get("selection"), "manifest.selection")),
        "cohort": cohort,
        "selected_artifacts": selected_artifacts,
    }


def compute_cohort_root(manifest: Mapping[str, Any]) -> str:
    return canonical_sha256(cohort_root_preimage(manifest))


def file_sha256(path: str | Path) -> str:
    return storage.file_sha256(path)


SCORING_PROTOCOL_SHA256 = canonical_sha256(SCORING_PROTOCOL)


def validate_lineage_id(value: Any, path: str = "lineage_id") -> str:
    value = _string(value, path)
    if not _LINEAGE_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise _error(path, "contains unsafe characters")
    return value


def canonical_runs_root(project_root: str | Path) -> Path:
    """Return the sole permitted strict-CF runs root for a project checkout."""

    return (
        Path(project_root).resolve()
        / "experiment_a"
        / "strict_cf_v1_1"
        / "runs"
    )


def validate_run_dir(
    run_dir: str | Path,
    *,
    project_root: str | Path,
    lineage_id: str | None = None,
    must_exist: bool = False,
) -> Path:
    """Require the exact isolated PROJECT/experiment_a/strict_cf_v1_1 run path."""

    resolved = Path(run_dir).resolve(strict=must_exist)
    actual_lineage = validate_lineage_id(
        lineage_id if lineage_id is not None else resolved.name
    )
    expected = (canonical_runs_root(project_root) / actual_lineage).resolve(
        strict=must_exist
    )
    if resolved != expected:
        raise StrictCFSchemaError(
            f"run directory must resolve exactly to {expected}, got {resolved}"
        )
    return resolved


def assert_path_within_run(
    run_dir: str | Path,
    candidate: str | Path,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve *candidate* and prove it is a child of the resolved run root."""

    root = Path(run_dir).resolve(strict=must_exist)
    raw = Path(candidate)
    resolved = (
        (root / raw).resolve(strict=must_exist)
        if not raw.is_absolute()
        else raw.resolve(strict=must_exist)
    )
    try:
        relative = resolved.relative_to(root)
    except (ValueError, OSError) as exc:
        raise StrictCFSchemaError(
            f"path escapes strict-CF run root: {resolved} is not under {root}"
        ) from exc
    if not relative.parts:
        raise StrictCFSchemaError("artifact path must name a child of the run root")
    return resolved


def source_cluster_key(domain: str, source_text_sha256: str) -> list[str]:
    if domain not in DOMAINS:
        raise _error("domain", f"must be one of {DOMAINS}")
    _sha256(source_text_sha256, "source_text_sha256")
    return [domain, source_text_sha256]


def model_item_key(model: str, domain: str, item_id: str, source_text_sha256: str) -> list[str]:
    if model not in MODELS:
        raise _error("generation_model", f"must be one of {MODELS}")
    _string(item_id, "id")
    source_cluster_key(domain, source_text_sha256)
    return [model, domain, item_id, source_text_sha256]


def _model_from(row: Mapping[str, Any]) -> str:
    value = row.get("generation_model", row.get("model"))
    return _string(value, "row.generation_model")


def level_key(row: Mapping[str, Any]) -> list[str]:
    """Return canonical semantic identity [model, domain, id, hash, level]."""

    row = _mapping(row, "row")
    model = _model_from(row)
    domain = _string(row.get("domain"), "row.domain").lower()
    item_id = _string(row.get("id"), "row.id")
    source_hash = _sha256(row.get("source_text_sha256"), "row.source_text_sha256")
    level = _string(row.get("level"), "row.level")
    if model not in MODELS or domain not in DOMAINS or level not in LEVELS:
        raise _error("row", "has an out-of-roster model, domain, or level")
    return [model, domain, item_id, source_hash, level]


semantic_level_key = level_key
semantic_key = level_key


def actual_pair_sha256(row: Mapping[str, Any]) -> str:
    """Hash the exact actual prompt/output pair with explicit field boundaries."""

    row = _mapping(row, "row")
    actual_value = row.get("actual")
    actual = _mapping(actual_value, "row.actual") if actual_value is not None else row
    prompt = _string(actual.get("prompt", actual.get("actual_prompt")), "row.actual.prompt")
    output = _string(actual.get("output", actual.get("actual_output")), "row.actual.output")
    return canonical_sha256(
        {"output": output, "prompt": prompt, "schema": f"{SCHEMA_ID}.actual_pair"}
    )


def strict_scoring_input_sha256(row: Mapping[str, Any]) -> str:
    """Hash semantic identity and the ordered six text-pair hashes for scoring."""

    row = _mapping(row, "row")
    counterfactuals = row.get("counterfactuals")
    if not isinstance(counterfactuals, Sequence) or isinstance(counterfactuals, (str, bytes)):
        raise _error("row.counterfactuals", "must be a list")
    pair_hashes: list[str] = []
    for index, raw in enumerate(counterfactuals):
        entry = _mapping(raw, f"row.counterfactuals[{index}]")
        pair_hashes.append(_sha256(entry.get("pair_sha256"), f"row.counterfactuals[{index}].pair_sha256"))
    return canonical_sha256(
        {
            "actual_pair_sha256": _sha256(
                row.get("actual_pair_sha256"), "row.actual_pair_sha256"
            ),
            "counterfactual_pair_sha256": pair_hashes,
            "schema": f"{SCHEMA_ID}.strict_scoring_input",
            "semantic_key": level_key(row),
        }
    )


scoring_input_sha256 = strict_scoring_input_sha256


def deterministic_selection_rank(domain: str, source_text_sha256: str) -> str:
    if domain not in DOMAINS:
        raise _error("domain", f"must be one of {DOMAINS}")
    _sha256(source_text_sha256, "source_text_sha256")
    payload = f"{SELECTION_SEED}\0{domain}\0{source_text_sha256}".encode("utf-8")
    return storage.sha256_bytes(payload)


def counterfactual_pair_sha256(index: int, prompt: str, output: str) -> str:
    _integer(index, "index", minimum=1)
    _string(prompt, "prompt")
    _string(output, "output")
    return canonical_sha256(
        {
            "index": index,
            "output": output,
            "prompt": prompt,
            "schema": f"{SCHEMA_ID}.counterfactual_pair",
        }
    )


def _validate_identity(row: Mapping[str, Any], path: str) -> None:
    model = _string(row.get("generation_model"), f"{path}.generation_model")
    domain = _string(row.get("domain"), f"{path}.domain")
    _string(row.get("id"), f"{path}.id")
    _string(row.get("source_id"), f"{path}.source_id")
    source_index = row.get("source_index")
    if source_index is not None:
        _integer(source_index, f"{path}.source_index")
    source_hash = _sha256(row.get("source_text_sha256"), f"{path}.source_text_sha256")
    level = _string(row.get("level"), f"{path}.level")
    if model not in MODELS:
        raise _error(f"{path}.generation_model", f"must be one of {MODELS}")
    if domain not in DOMAINS:
        raise _error(f"{path}.domain", f"must be one of {DOMAINS}")
    if level not in LEVELS:
        raise _error(f"{path}.level", f"must be one of {LEVELS}")
    if row.get("source_cluster") != [domain, source_hash]:
        raise _error(f"{path}.source_cluster", "must equal [domain, source_text_sha256]")
    if row.get("semantic_key") != level_key(row):
        raise _error(
            f"{path}.semantic_key",
            "must equal [generation_model, domain, id, source_text_sha256, level]",
        )


def _validate_actual_per_compressor(value: Any, path: str) -> Mapping[str, Any]:
    value = _mapping(value, path)
    if set(value) != set(COMPRESSORS):
        raise _error(path, f"compressors must be exactly {COMPRESSORS}")
    for compressor in COMPRESSORS:
        metrics = _mapping(value[compressor], f"{path}.{compressor}")
        _exact_keys(
            metrics,
            {"actual_ratio", "legacy_shared_baseline_mean", "legacy_shared_excess_ratio"},
            f"{path}.{compressor}",
        )
        _number(metrics["actual_ratio"], f"{path}.{compressor}.actual_ratio")
        # Legacy shared values are audit-only and deliberately do not participate
        # in arithmetic validation or actual-only cohort membership.  Null is an
        # admissible record of an unavailable legacy baseline.
        for field in (
            "legacy_shared_baseline_mean",
            "legacy_shared_excess_ratio",
        ):
            if metrics[field] is not None:
                _number(metrics[field], f"{path}.{compressor}.{field}")
    return value


ACTUAL_KEYS = {
    "prompt",
    "output",
    "output_chars",
    "actual_ratio",
    "per_compressor",
    "legacy_shared_baseline_mean",
    "legacy_shared_excess_ratio",
    "legacy_shared_baseline_n_valid",
    "metric_status",
    "generation_provenance",
    "item_provenance_sha256",
    "source_result_row_sha256",
    "source_debug_row_sha256",
}
ACTUAL_SNAPSHOT_KEYS = {
    "schema_version",
    "row_type",
    "semantic_key",
    "generation_model",
    "domain",
    "id",
    "source_id",
    "source_index",
    "source_text_sha256",
    "level",
    "source_cluster",
    "provenance_tier",
    "verification_tier",
    "actual",
    "actual_pair_sha256",
}


def validate_actual_snapshot_row(
    row: Mapping[str, Any],
    *,
    seen_keys: MutableSet[tuple[str, ...]] | None = None,
    path: str = "actual_snapshot_row",
) -> Mapping[str, Any]:
    """Validate one immutable actual level and its legacy semantic quarantine."""

    row = _mapping(row, path)
    _exact_keys(row, ACTUAL_SNAPSHOT_KEYS, path)
    if row["schema_version"] != SCHEMA_VERSION or row["row_type"] != "actual_level":
        raise _error(path, "has the wrong schema_version or row_type")
    _validate_identity(row, path)
    actual = _mapping(row["actual"], f"{path}.actual")
    _exact_keys(actual, ACTUAL_KEYS, f"{path}.actual")
    _string(actual["prompt"], f"{path}.actual.prompt")
    output = _string(actual["output"], f"{path}.actual.output")
    if _integer(actual["output_chars"], f"{path}.actual.output_chars", minimum=1) != len(output):
        raise _error(f"{path}.actual.output_chars", f"must equal len(output)={len(output)}")
    _number(actual["actual_ratio"], f"{path}.actual.actual_ratio")
    for field in (
        "legacy_shared_baseline_mean",
        "legacy_shared_excess_ratio",
    ):
        if actual[field] is not None:
            _number(actual[field], f"{path}.actual.{field}")
    legacy_n = actual["legacy_shared_baseline_n_valid"]
    if legacy_n is not None:
        _integer(legacy_n, f"{path}.actual.legacy_shared_baseline_n_valid")
    _validate_actual_per_compressor(
        actual["per_compressor"], f"{path}.actual.per_compressor"
    )
    if dict(_mapping(actual["metric_status"], f"{path}.actual.metric_status")) != ACTUAL_METRIC_STATUS:
        raise _error(f"{path}.actual.metric_status", "does not declare exact actual/legacy semantics")
    provenance_tier = row["provenance_tier"]
    verification_tier = row["verification_tier"]
    if provenance_tier not in PROVENANCE_TIERS:
        raise _error(
            f"{path}.provenance_tier", f"must be one of {PROVENANCE_TIERS}"
        )
    if verification_tier not in VERIFICATION_TIERS:
        raise _error(
            f"{path}.verification_tier", f"must be one of {VERIFICATION_TIERS}"
        )
    provenance = actual["generation_provenance"]
    provenance_hash = actual["item_provenance_sha256"]
    if provenance_tier == PROVENANCE_TIER_EXACT:
        _mapping(provenance, f"{path}.actual.generation_provenance")
        _sha256(provenance_hash, f"{path}.actual.item_provenance_sha256")
    elif provenance_tier == PROVENANCE_TIER_HISTORICAL_API821:
        historical = _mapping(
            provenance, f"{path}.actual.generation_provenance"
        )
        _exact_keys(
            historical,
            {"call", "cutover_attestation"},
            f"{path}.actual.generation_provenance",
        )
        validate_historical_backend_b_call_provenance(
            historical["call"],
            expected_model=row["generation_model"],
            path=f"{path}.actual.generation_provenance.call",
        )
        validate_historical_cutover_attestation(
            historical["cutover_attestation"],
            expected_model=row["generation_model"],
            expected_domain=row["domain"],
            expected_id=row["id"],
            path=f"{path}.actual.generation_provenance.cutover_attestation",
        )
        _sha256(provenance_hash, f"{path}.actual.item_provenance_sha256")
    elif provenance is not None or provenance_hash is not None:
        raise _error(
            f"{path}.actual",
            "legacy_unattested rows require null generation provenance/hash",
        )
    for field in (
        "source_result_row_sha256",
        "source_debug_row_sha256",
    ):
        _sha256(actual[field], f"{path}.actual.{field}")
    pair_hash = actual_pair_sha256(row)
    if row["actual_pair_sha256"] != pair_hash:
        raise _error(f"{path}.actual_pair_sha256", f"must equal {pair_hash}")
    key = tuple(row["semantic_key"])
    if seen_keys is not None:
        if key in seen_keys:
            raise _error(f"{path}.semantic_key", f"duplicate semantic key {key!r}")
        seen_keys.add(key)
    return row


def validate_bound_call_provenance(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    seen_response_ids: MutableSet[str] | None = None,
    path: str = "bound_call_provenance",
) -> Mapping[str, Any]:
    """Validate model-independent strict-call evidence carried by a formal bundle."""

    value = _mapping(value, path)
    for field, expected in (
        ("requested_model", expected_model),
        ("returned_model", expected_model),
        ("terminal_status", "completed"),
        ("max_output_tokens", 4096),
        ("reasoning_effort", "low"),
        ("alias_used", False),
        ("fallback_used", False),
        ("provider_attempt_count", 1),
        ("transport_abi_sha256", TRANSPORT_ABI_SHA256),
    ):
        if value.get(field) != expected:
            raise _error(f"{path}.{field}", f"must equal {expected!r}")
    if value.get("incomplete_details") not in (None, {}):
        raise _error(f"{path}.incomplete_details", "must be null/empty")
    for field in ("api_family", "route_id", "client_id", "invocation_id"):
        _string(value.get(field), f"{path}.{field}")
    response_id = _string(value.get("response_id"), f"{path}.response_id")
    if response_id != response_id.strip():
        raise _error(f"{path}.response_id", "must be trimmed")
    if seen_response_ids is not None:
        if response_id in seen_response_ids:
            raise _error(f"{path}.response_id", f"duplicate response ID {response_id!r}")
        seen_response_ids.add(response_id)
    _timestamp(value.get("captured_at_utc"), f"{path}.captured_at_utc")
    usage = _mapping(value.get("usage"), f"{path}.usage")
    _integer(usage.get("output_tokens"), f"{path}.usage.output_tokens", minimum=1)
    campaign = _mapping(value.get("campaign_binding"), f"{path}.campaign_binding")
    _exact_keys(
        campaign,
        {"lineage_id", "manifest_sha256", "cohort_root_sha256"},
        f"{path}.campaign_binding",
    )
    validate_lineage_id(campaign["lineage_id"], f"{path}.campaign_binding.lineage_id")
    _sha256(campaign["manifest_sha256"], f"{path}.campaign_binding.manifest_sha256")
    _sha256(campaign["cohort_root_sha256"], f"{path}.campaign_binding.cohort_root_sha256")
    binding = _mapping(value.get("formal_binding"), f"{path}.formal_binding")
    _exact_keys(
        binding,
        {"formal_pointer_sha256", "bundle_sha256"},
        f"{path}.formal_binding",
    )
    _sha256(binding["formal_pointer_sha256"], f"{path}.formal_binding.formal_pointer_sha256")
    _sha256(binding["bundle_sha256"], f"{path}.formal_binding.bundle_sha256")
    return value


def validate_call_provenance(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    project_root: str | Path | None = None,
    allow_legacy_gpt_reasoning_omission: bool = False,
    seen_response_ids: MutableSet[str] | None = None,
    path: str = "call_provenance",
) -> Mapping[str, Any]:
    """Validate one exact, completed call from the approved model protocol.

    Existing GPT actual records omitted ``reasoning_effort`` even though their
    adapter invocation was pinned to low.  Preparation may opt into that one
    metadata omission.  New strict-CF calls must persist explicit ``low``.
    """

    value = _mapping(value, path)
    if "formal_binding" in value or "campaign_binding" in value:
        return validate_bound_call_provenance(
            value,
            expected_model=expected_model,
            seen_response_ids=seen_response_ids,
            path=path,
        )
    protocol = MODEL_PROTOCOLS.get(expected_model)
    if protocol is None:
        raise _error("expected_model", f"must be one of {MODELS}")
    if value.get("api") != "responses":
        raise _error(f"{path}.api", "must equal 'responses'")
    for field, expected in (
        ("route", protocol["call_route"]),
        ("gateway", protocol["gateway"]),
        ("requested_model", expected_model),
        ("returned_model", expected_model),
        ("status", "completed"),
        ("max_output_tokens", protocol["max_output_tokens"]),
    ):
        if value.get(field) != expected:
            raise _error(f"{path}.{field}", f"must equal {expected!r}")
    if value.get("incomplete_details") not in (None, {}):
        raise _error(f"{path}.incomplete_details", "must be null/empty for completed output")
    response_id = _string(value.get("response_id"), f"{path}.response_id")
    if response_id != response_id.strip():
        raise _error(f"{path}.response_id", "must not contain surrounding whitespace")
    if seen_response_ids is not None:
        if response_id in seen_response_ids:
            raise _error(f"{path}.response_id", f"duplicate response ID {response_id!r}")
        seen_response_ids.add(response_id)
    _timestamp(value.get("captured_at_utc"), f"{path}.captured_at_utc")
    usage = _mapping(value.get("usage"), f"{path}.usage")
    if not usage:
        raise _error(f"{path}.usage", "must be non-empty")
    _integer(usage.get("output_tokens"), f"{path}.usage.output_tokens", minimum=1)
    client = _string(value.get("client"), f"{path}.client")
    if project_root is not None:
        expected_client = (
            Path(project_root).resolve() / protocol["client_relative_path"]
        ).resolve()
        if Path(client).resolve() != expected_client:
            raise _error(f"{path}.client", f"must resolve to {expected_client}")
    reasoning = protocol["reasoning_effort"]
    observed_reasoning = value.get("reasoning_effort")
    legacy_omission = (
        allow_legacy_gpt_reasoning_omission
        and expected_model in MODELS[3:]
        and "reasoning_effort" not in value
    )
    if not legacy_omission and observed_reasoning != reasoning:
        raise _error(f"{path}.reasoning_effort", f"must explicitly equal {reasoning!r}")
    if "reasoning_effort" in value and observed_reasoning != "low":
        raise _error(f"{path}.reasoning_effort", "an explicit non-low value is forbidden")
    return value


def validate_historical_backend_b_call_provenance(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    seen_response_ids: MutableSet[str] | None = None,
    path: str = "historical_backend_b_call",
) -> Mapping[str, Any]:
    """Validate one completed pre-API3rd call without claiming current-route status."""

    value = _mapping(value, path)
    protocol = HISTORICAL_API821_PROTOCOLS.get(expected_model)
    if protocol is None:
        raise _error(
            "expected_model", "historical backend_b attestation is GPT-only"
        )
    for field, expected in (
        ("api", "responses"),
        ("gateway", protocol["gateway"]),
        ("requested_model", expected_model),
        ("returned_model", expected_model),
        ("status", "completed"),
        ("max_output_tokens", protocol["max_output_tokens"]),
    ):
        if value.get(field) != expected:
            raise _error(f"{path}.{field}", f"must equal {expected!r}")
    if value.get("incomplete_details") not in (None, {}):
        raise _error(
            f"{path}.incomplete_details", "must be null/empty for completed output"
        )
    response_id = _string(value.get("response_id"), f"{path}.response_id")
    if response_id != response_id.strip():
        raise _error(f"{path}.response_id", "must not contain surrounding whitespace")
    if seen_response_ids is not None:
        if response_id in seen_response_ids:
            raise _error(
                f"{path}.response_id", f"duplicate response ID {response_id!r}"
            )
        seen_response_ids.add(response_id)
    _timestamp(value.get("captured_at_utc"), f"{path}.captured_at_utc")
    usage = _mapping(value.get("usage"), f"{path}.usage")
    if not usage:
        raise _error(f"{path}.usage", "must be non-empty")
    _integer(usage.get("output_tokens"), f"{path}.usage.output_tokens", minimum=1)
    return value


def validate_historical_backend_b_actual_item_provenance(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    seen_response_ids: MutableSet[str] | None = None,
    path: str = "historical_backend_b_provenance",
) -> Mapping[str, Any]:
    """Validate the exact seven-call backend_b actual/intermediate attestation."""

    value = _mapping(value, path)
    protocol = HISTORICAL_API821_PROTOCOLS.get(expected_model)
    if protocol is None:
        raise _error(
            "expected_model", "historical backend_b attestation is GPT-only"
        )
    config = _mapping(value.get("config"), f"{path}.config")
    expected_config = {
        "route": "backend_b",
        "gateway": protocol["gateway"],
        "max_output_tokens": protocol["max_output_tokens"],
        "require_status": "completed",
    }
    if dict(config) != expected_config:
        raise _error(
            f"{path}.config", "does not exactly match the historical backend_b protocol"
        )
    main = _mapping(value.get("main_calls"), f"{path}.main_calls")
    if set(main) != set(MAIN_CALL_LABELS):
        raise _error(f"{path}.main_calls", f"labels must be exactly {MAIN_CALL_LABELS}")
    response_ids: MutableSet[str] = (
        seen_response_ids if seen_response_ids is not None else set()
    )
    for label in MAIN_CALL_LABELS:
        validate_historical_backend_b_call_provenance(
            main[label],
            expected_model=expected_model,
            seen_response_ids=response_ids,
            path=f"{path}.main_calls.{label}",
        )
    return value


HISTORICAL_CUTOVER_ATTESTATION_KEYS = {
    "manifest_path",
    "manifest_sha256",
    "scope_ids_sha256",
    "scope_row_count",
    "generation_model",
    "domain",
    "id",
}


def validate_historical_cutover_attestation(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    expected_domain: str,
    expected_id: str,
    path: str = "historical_cutover_attestation",
) -> Mapping[str, Any]:
    """Bind a historical item to one hash-checked cutover-manifest scope."""

    value = _mapping(value, path)
    _exact_keys(value, HISTORICAL_CUTOVER_ATTESTATION_KEYS, path)
    _string(value["manifest_path"], f"{path}.manifest_path")
    _sha256(value["manifest_sha256"], f"{path}.manifest_sha256")
    _sha256(value["scope_ids_sha256"], f"{path}.scope_ids_sha256")
    _integer(value["scope_row_count"], f"{path}.scope_row_count", minimum=1)
    for field, expected in (
        ("generation_model", expected_model),
        ("domain", expected_domain),
        ("id", expected_id),
    ):
        if value[field] != expected:
            raise _error(f"{path}.{field}", f"must equal {expected!r}")
    if expected_model not in HISTORICAL_API821_PROTOCOLS:
        raise _error(f"{path}.generation_model", "historical tier is GPT-only")
    if expected_domain not in DOMAINS:
        raise _error(f"{path}.domain", f"must be one of {DOMAINS}")
    return value


def validate_historical_cutover_manifest_document(
    value: Mapping[str, Any],
    *,
    path: str = "historical_cutover_manifest",
) -> dict[tuple[str, str], dict[str, Any]]:
    """Strictly parse the immutable backend_b-to-API3rd membership boundary."""

    value = _mapping(value, path)
    _exact_keys(
        value,
        {
            "created_at_utc",
            "current_protocol",
            "models",
            "purpose",
            "schema_version",
        },
        path,
    )
    if value["schema_version"] != 1:
        raise _error(f"{path}.schema_version", "must equal 1")
    if value["purpose"] != "Bound legacy/API821 resume acceptance at API3rd cutover":
        raise _error(f"{path}.purpose", "does not match the frozen boundary purpose")
    _timestamp(value["created_at_utc"], f"{path}.created_at_utc")
    current = _mapping(value["current_protocol"], f"{path}.current_protocol")
    if dict(current) != {
        "route": "backend_c",
        "gateway": "auto",
        "max_output_tokens": 4096,
    }:
        raise _error(f"{path}.current_protocol", "does not match API3rd cutover")
    models = _mapping(value["models"], f"{path}.models")
    _exact_keys(models, set(HISTORICAL_API821_PROTOCOLS), f"{path}.models")
    membership: dict[tuple[str, str], dict[str, Any]] = {}
    for model in sorted(HISTORICAL_API821_PROTOCOLS):
        domains = _mapping(models[model], f"{path}.models.{model}")
        _exact_keys(domains, set(DOMAINS), f"{path}.models.{model}")
        for domain in DOMAINS:
            entry_path = f"{path}.models.{model}.{domain}"
            entry = _mapping(domains[domain], entry_path)
            _exact_keys(
                entry,
                {"historical_ids", "ids_sha256", "result_file", "row_count"},
                entry_path,
            )
            ids = entry["historical_ids"]
            if not isinstance(ids, list) or any(
                not isinstance(item_id, str)
                or not item_id
                or item_id != item_id.strip()
                for item_id in ids
            ):
                raise _error(f"{entry_path}.historical_ids", "contains an invalid ID")
            if len(ids) != len(set(ids)):
                raise _error(f"{entry_path}.historical_ids", "contains duplicate IDs")
            ids_sha256 = storage.sha256_bytes("\n".join(ids).encode("utf-8"))
            expected_result = f"final_{domain}_5level_{model}.json"
            if _integer(entry["row_count"], f"{entry_path}.row_count") != len(ids):
                raise _error(f"{entry_path}.row_count", "differs from ID count")
            if entry["ids_sha256"] != ids_sha256:
                raise _error(f"{entry_path}.ids_sha256", "does not hash the ordered IDs")
            if entry["result_file"] != expected_result:
                raise _error(
                    f"{entry_path}.result_file", f"must equal {expected_result!r}"
                )
            membership[(model, domain)] = {
                "ids": frozenset(ids),
                "ids_sha256": ids_sha256,
                "row_count": len(ids),
                "result_file": expected_result,
            }
    return membership


def validate_actual_item_provenance(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    project_root: str | Path | None = None,
    seen_response_ids: MutableSet[str] | None = None,
    path: str = "api_provenance",
) -> Mapping[str, Any]:
    """Validate only provenance causally required for the five actual outputs.

    Legacy shared counterfactual reconstruction/generation is intentionally not
    inspected here: its success, failure, or fallback status must never alter
    actual-only cohort membership.
    """

    value = _mapping(value, path)
    protocol = MODEL_PROTOCOLS.get(expected_model)
    if protocol is None:
        raise _error("expected_model", f"must be one of {MODELS}")
    config = _mapping(value.get("config"), f"{path}.config")
    expected_config = {
        "route": protocol["config_route"],
        "gateway": protocol["gateway"],
        "max_output_tokens": protocol["max_output_tokens"],
        "require_status": "completed",
    }
    if dict(config) != expected_config:
        raise _error(f"{path}.config", "does not exactly match the approved protocol")
    main = _mapping(value.get("main_calls"), f"{path}.main_calls")
    if set(main) != set(MAIN_CALL_LABELS):
        raise _error(f"{path}.main_calls", f"labels must be exactly {MAIN_CALL_LABELS}")
    response_ids: MutableSet[str] = (
        seen_response_ids if seen_response_ids is not None else set()
    )
    for label in MAIN_CALL_LABELS:
        validate_call_provenance(
            main[label],
            expected_model=expected_model,
            project_root=project_root,
            allow_legacy_gpt_reasoning_omission=True,
            seen_response_ids=response_ids,
            path=f"{path}.main_calls.{label}",
        )
    return value


MODEL_ITEM_KEYS = {
    "schema_version",
    "row_type",
    "model_item_key",
    "generation_model",
    "domain",
    "id",
    "source_id",
    "source_index",
    "source_text_sha256",
    "source_cluster",
    "semantic_keys",
    "actual_level_row_sha256",
    "actual_api_provenance",
    "provenance_tier",
    "historical_cutover_attestation",
    "item_provenance_sha256",
    "source_result_row_sha256",
    "source_debug_row_sha256",
}


def validate_model_item_row(
    row: Mapping[str, Any],
    *,
    project_root: str | Path | None = None,
    seen_response_ids: MutableSet[str] | None = None,
    seen_keys: MutableSet[tuple[str, ...]] | None = None,
    allow_legacy_unattested: bool = False,
    path: str = "model_item_row",
) -> Mapping[str, Any]:
    """Validate one full five-level item and its seven-call provenance preimage."""

    row = _mapping(row, path)
    _exact_keys(row, MODEL_ITEM_KEYS, path)
    if row["schema_version"] != SCHEMA_VERSION or row["row_type"] != "model_item":
        raise _error(path, "has the wrong schema_version or row_type")
    model = _string(row["generation_model"], f"{path}.generation_model")
    domain = _string(row["domain"], f"{path}.domain")
    item_id = _string(row["id"], f"{path}.id")
    source_id = _string(row["source_id"], f"{path}.source_id")
    source_index = row["source_index"]
    if source_index is not None:
        _integer(source_index, f"{path}.source_index")
    source_hash = _sha256(row["source_text_sha256"], f"{path}.source_text_sha256")
    if model not in MODELS or domain not in DOMAINS:
        raise _error(path, "has an out-of-roster model or domain")
    expected_key = model_item_key(model, domain, item_id, source_hash)
    if row["model_item_key"] != expected_key:
        raise _error(f"{path}.model_item_key", "does not match model-item identity")
    if row["source_cluster"] != source_cluster_key(domain, source_hash):
        raise _error(f"{path}.source_cluster", "does not match source identity")
    expected_semantic = [expected_key + [level] for level in LEVELS]
    if row["semantic_keys"] != expected_semantic:
        raise _error(f"{path}.semantic_keys", "must be ordered exact L1-L5 keys")
    row_hashes = row["actual_level_row_sha256"]
    if not isinstance(row_hashes, list) or len(row_hashes) != len(LEVELS):
        raise _error(
            f"{path}.actual_level_row_sha256", "must contain five ordered hashes"
        )
    for index, digest in enumerate(row_hashes):
        _sha256(digest, f"{path}.actual_level_row_sha256[{index}]")
    for field in ("source_result_row_sha256", "source_debug_row_sha256"):
        _sha256(row[field], f"{path}.{field}")

    tier = row["provenance_tier"]
    provenance_value = row["actual_api_provenance"]
    attestation = row["historical_cutover_attestation"]
    if tier == PROVENANCE_TIER_EXACT:
        provenance = _mapping(
            provenance_value, f"{path}.actual_api_provenance"
        )
        if attestation is not None:
            raise _error(
                f"{path}.historical_cutover_attestation",
                "must be null for current-route exact provenance",
            )
        validate_actual_item_provenance(
            provenance,
            expected_model=model,
            project_root=project_root,
            seen_response_ids=seen_response_ids,
            path=f"{path}.actual_api_provenance",
        )
        expected_provenance_hash = canonical_row_sha256(provenance)
    elif tier == PROVENANCE_TIER_HISTORICAL_API821:
        provenance = _mapping(
            provenance_value, f"{path}.actual_api_provenance"
        )
        validate_historical_backend_b_actual_item_provenance(
            provenance,
            expected_model=model,
            seen_response_ids=seen_response_ids,
            path=f"{path}.actual_api_provenance",
        )
        validate_historical_cutover_attestation(
            attestation,
            expected_model=model,
            expected_domain=domain,
            expected_id=item_id,
            path=f"{path}.historical_cutover_attestation",
        )
        expected_provenance_hash = canonical_row_sha256(
            {
                "api_provenance": provenance,
                "cutover_attestation": attestation,
                "provenance_tier": tier,
            }
        )
    elif tier == PROVENANCE_TIER_LEGACY_UNATTESTED and allow_legacy_unattested:
        if (
            provenance_value is not None
            or attestation is not None
            or row["item_provenance_sha256"] is not None
        ):
            raise _error(
                path,
                "legacy_unattested model items require null provenance/attestation/hash",
            )
        expected_provenance_hash = None
    else:
        allowed = (
            PROVENANCE_TIERS
            if allow_legacy_unattested
            else STRICT_ACTUAL_PROVENANCE_TIERS
        )
        raise _error(
            f"{path}.provenance_tier",
            f"must be one of {allowed}",
        )
    if row["item_provenance_sha256"] != expected_provenance_hash:
        raise _error(
            f"{path}.item_provenance_sha256",
            "does not hash the complete tier-specific provenance preimage",
        )
    key = tuple(expected_key)
    if seen_keys is not None:
        if key in seen_keys:
            raise _error(f"{path}.model_item_key", f"duplicate model item {key!r}")
        seen_keys.add(key)
    # These reads make source_id/index part of the exact-key validated object even
    # though model_item_key intentionally follows the existing semantic identity.
    del source_id, source_index
    return row


def validate_actual_against_model_item(
    actual_row: Mapping[str, Any],
    model_item: Mapping[str, Any],
    *,
    model_item_validated: bool = False,
    allow_legacy_unattested: bool = False,
    project_root: str | Path | None = None,
    path: str = "actual_model_item_binding",
) -> Mapping[str, Any]:
    """Require one level to be the exact projection hashed by its full model item."""

    validate_actual_snapshot_row(actual_row, path=f"{path}.actual")
    if not model_item_validated:
        validate_model_item_row(
            model_item,
            project_root=project_root,
            allow_legacy_unattested=allow_legacy_unattested,
            path=f"{path}.model_item",
        )
    item_key = tuple(model_item["model_item_key"])
    if tuple(actual_row["semantic_key"][:-1]) != item_key:
        raise _error(path, "actual semantic key has no matching model item")
    for field in (
        "generation_model",
        "domain",
        "id",
        "source_id",
        "source_index",
        "source_text_sha256",
        "source_cluster",
        "provenance_tier",
    ):
        if actual_row[field] != model_item[field]:
            raise _error(f"{path}.{field}", "differs from full model item")
    actual = actual_row["actual"]
    if actual["item_provenance_sha256"] != model_item["item_provenance_sha256"]:
        raise _error(
            f"{path}.item_provenance_sha256", "differs from full model item"
        )
    for field in ("source_result_row_sha256", "source_debug_row_sha256"):
        if actual[field] != model_item[field]:
            raise _error(f"{path}.{field}", "differs from full model item")
    level = actual_row["level"]
    if actual_row["provenance_tier"] == PROVENANCE_TIER_EXACT:
        call = model_item["actual_api_provenance"]["main_calls"][
            LEVEL_MAIN_CALL[level]
        ]
        if actual["generation_provenance"] != call:
            raise _error(
                f"{path}.generation_provenance",
                "is not the exact level-call projection from the model item",
            )
    elif actual_row["provenance_tier"] == PROVENANCE_TIER_HISTORICAL_API821:
        call = model_item["actual_api_provenance"]["main_calls"][
            LEVEL_MAIN_CALL[level]
        ]
        generation = actual["generation_provenance"]
        if (
            generation["call"] != call
            or generation["cutover_attestation"]
            != model_item["historical_cutover_attestation"]
        ):
            raise _error(
                f"{path}.generation_provenance",
                "is not the exact historical call/cutover projection",
            )
    elif (
        actual["generation_provenance"] is not None
        or model_item["actual_api_provenance"] is not None
    ):
        raise _error(
            f"{path}.generation_provenance",
            "legacy_unattested rows cannot fabricate provenance",
        )
    level_index = LEVELS.index(level)
    if (
        actual_row["semantic_key"] != model_item["semantic_keys"][level_index]
        or canonical_row_sha256(actual_row)
        != model_item["actual_level_row_sha256"][level_index]
    ):
        raise _error(path, "actual row is not the model item's hashed level row")
    return actual_row


def validate_item_api_provenance(
    value: Mapping[str, Any],
    *,
    expected_model: str,
    project_root: str | Path | None = None,
    seen_response_ids: MutableSet[str] | None = None,
    path: str = "api_provenance",
) -> Mapping[str, Any]:
    """Validate seven actual/intermediate calls and reject local CF fallback."""

    item_response_ids: MutableSet[str] = (
        seen_response_ids if seen_response_ids is not None else set()
    )

    value = _mapping(value, path)
    protocol = MODEL_PROTOCOLS.get(expected_model)
    if protocol is None:
        raise _error("expected_model", f"must be one of {MODELS}")
    config = _mapping(value.get("config"), f"{path}.config")
    expected_config = {
        "route": protocol["config_route"],
        "gateway": protocol["gateway"],
        "max_output_tokens": protocol["max_output_tokens"],
        "require_status": "completed",
    }
    if dict(config) != expected_config:
        raise _error(f"{path}.config", "does not exactly match the approved protocol")
    main = _mapping(value.get("main_calls"), f"{path}.main_calls")
    if set(main) != set(MAIN_CALL_LABELS):
        raise _error(f"{path}.main_calls", f"labels must be exactly {MAIN_CALL_LABELS}")
    for label in MAIN_CALL_LABELS:
        validate_call_provenance(
            main[label],
            expected_model=expected_model,
            project_root=project_root,
            allow_legacy_gpt_reasoning_omission=True,
            seen_response_ids=item_response_ids,
            path=f"{path}.main_calls.{label}",
        )
    counterfactuals = _mapping(value.get("counterfactuals"), f"{path}.counterfactuals")
    reconstruct = _mapping(
        counterfactuals.get("reconstruct"), f"{path}.counterfactuals.reconstruct"
    )
    if reconstruct.get("api") == "local_fallback" or reconstruct.get("status") == "fallback":
        raise _error(f"{path}.counterfactuals.reconstruct", "local fallback is forbidden")
    validate_call_provenance(
        reconstruct,
        expected_model=expected_model,
        project_root=project_root,
        allow_legacy_gpt_reasoning_omission=True,
        seen_response_ids=item_response_ids,
        path=f"{path}.counterfactuals.reconstruct",
    )
    outputs = counterfactuals.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != STRICT_CF_COUNT:
        raise _error(
            f"{path}.counterfactuals.outputs",
            f"must contain exactly {STRICT_CF_COUNT} rows",
        )
    for index, raw in enumerate(outputs):
        entry_path = f"{path}.counterfactuals.outputs[{index}]"
        entry = _mapping(raw, entry_path)
        if entry.get("label") != f"cf_{index + 1}" or entry.get("valid") is not True:
            raise _error(entry_path, "must have its positional label and valid=true")
        attempts = entry.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            raise _error(f"{entry_path}.attempts", "must contain completed call provenance")
        if not isinstance(attempts[-1], Mapping) or attempts[-1].get("status") != "completed":
            raise _error(f"{entry_path}.attempts[-1]", "final attempt must be completed")
        completed_attempts = [
            attempt
            for attempt in attempts
            if isinstance(attempt, Mapping) and attempt.get("status") == "completed"
        ]
        for attempt_index, attempt in enumerate(completed_attempts):
            validate_call_provenance(
                attempt,
                expected_model=expected_model,
                project_root=project_root,
                allow_legacy_gpt_reasoning_omission=True,
                seen_response_ids=item_response_ids,
                path=f"{entry_path}.completed_attempts[{attempt_index}]",
            )
    return value


def _validate_counterfactuals(
    value: Any,
    path: str,
    model: str,
    project_root: str | Path | None,
    formal_binding: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != STRICT_CF_COUNT:
        raise _error(path, f"must contain exactly {STRICT_CF_COUNT} rows")
    result: list[Mapping[str, Any]] = []
    response_ids: set[str] = set()
    for zero_index, raw in enumerate(value):
        entry_path = f"{path}[{zero_index}]"
        entry = _mapping(raw, entry_path)
        _exact_keys(
            entry,
            {"index", "prompt", "output", "pair_sha256", "provenance"},
            entry_path,
        )
        index = _integer(entry["index"], f"{entry_path}.index", minimum=1)
        if index != zero_index + 1:
            raise _error(f"{entry_path}.index", "must be one-based and positional")
        prompt = _string(entry["prompt"], f"{entry_path}.prompt")
        output = _string(entry["output"], f"{entry_path}.output")
        expected_hash = counterfactual_pair_sha256(index, prompt, output)
        if entry["pair_sha256"] != expected_hash:
            raise _error(f"{entry_path}.pair_sha256", f"must equal {expected_hash}")
        provenance = _mapping(entry["provenance"], f"{entry_path}.provenance")
        if provenance.get("api") == "local_fallback" or provenance.get("status") == "fallback":
            raise _error(f"{entry_path}.provenance", "local fallback is forbidden")
        if provenance.get("transport_abi_sha256") is not None:
            validate_bound_call_provenance(
                provenance,
                expected_model=model,
                seen_response_ids=response_ids,
                path=f"{entry_path}.provenance",
            )
            if formal_binding is not None:
                expected_campaign = {
                    "lineage_id": formal_binding["campaign"]["lineage_id"],
                    "manifest_sha256": formal_binding["campaign"]["manifest_sha256"],
                    "cohort_root_sha256": formal_binding["campaign"]["cohort_root_sha256"],
                }
                expected_binding = {
                    "formal_pointer_sha256": formal_binding["formal_pointer_sha256"],
                    "bundle_sha256": formal_binding["bundle_sha256"],
                }
                if (
                    provenance.get("route_id") != formal_binding["route_id"]
                    or provenance.get("client_id") != formal_binding["client_id"]
                    or provenance.get("campaign_binding") != expected_campaign
                    or provenance.get("formal_binding") != expected_binding
                    or provenance.get("transport_abi_sha256")
                    != formal_binding["transport_abi_sha256"]
                ):
                    raise _error(
                        f"{entry_path}.provenance",
                        "does not match the model formal binding",
                    )
        else:
            validate_call_provenance(
                provenance,
                expected_model=model,
                project_root=project_root,
                seen_response_ids=response_ids,
                path=f"{entry_path}.provenance",
            )
        result.append(entry)
    return result


STRICT_SOURCE_KEYS = ACTUAL_SNAPSHOT_KEYS | {"counterfactuals", "scoring_input_sha256"}


def validate_strict_source_row(
    row: Mapping[str, Any],
    *,
    actual_row: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
    seen_keys: MutableSet[tuple[str, ...]] | None = None,
    path: str = "strict_source_row",
    formal_binding: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Validate one finalized six-pair source row for strict scoring."""

    row = _mapping(row, path)
    _exact_keys(row, STRICT_SOURCE_KEYS, path)
    if row["schema_version"] != SCHEMA_VERSION or row["row_type"] != "strict_cf_source":
        raise _error(path, "has the wrong schema_version or row_type")
    _validate_identity(row, path)
    # Validate the common actual payload by projecting its canonical snapshot.
    actual_projection = {key: row[key] for key in ACTUAL_SNAPSHOT_KEYS}
    actual_projection["row_type"] = "actual_level"
    validate_actual_snapshot_row(actual_projection, path=f"{path}.actual_projection")
    if (
        row["provenance_tier"] not in STRICT_ACTUAL_PROVENANCE_TIERS
        or row["verification_tier"] != "recomputed_actual_and_per_compressor"
    ):
        raise _error(
            path,
            "strict source requires attested provenance and recomputed actual metrics",
        )
    _validate_counterfactuals(
        row["counterfactuals"],
        f"{path}.counterfactuals",
        row["generation_model"],
        project_root,
        formal_binding=formal_binding,
    )
    expected_scoring = strict_scoring_input_sha256(row)
    if row["scoring_input_sha256"] != expected_scoring:
        raise _error(f"{path}.scoring_input_sha256", f"must equal {expected_scoring}")
    if actual_row is not None:
        validate_actual_snapshot_row(actual_row, path="actual_row")
        if actual_projection != dict(actual_row):
            raise _error(path, "actual projection differs from immutable actual snapshot")
    key = tuple(row["semantic_key"])
    if seen_keys is not None:
        if key in seen_keys:
            raise _error(f"{path}.semantic_key", f"duplicate semantic key {key!r}")
        seen_keys.add(key)
    return row


BLACKBOX_KEYS = {
    "schema_version",
    "row_type",
    "semantic_key",
    "generation_model",
    "domain",
    "id",
    "source_id",
    "source_index",
    "source_text_sha256",
    "level",
    "source_cluster",
    "scoring_input_sha256",
    "method",
    "protocol_sha256",
    "actual_ratio",
    "cf_ratios",
    "baseline_mean",
    "strict_excess_ratio",
    "baseline_n_valid",
    "per_compressor",
}


def _validate_scored_metrics(
    *,
    actual: Any,
    cf_values: Any,
    baseline: Any,
    excess: Any,
    path: str,
) -> tuple[float, list[float], float, float]:
    actual_n = _number(actual, f"{path}.actual_ratio")
    if not isinstance(cf_values, list) or len(cf_values) != STRICT_CF_COUNT:
        raise _error(f"{path}.cf_ratios", f"must contain exactly {STRICT_CF_COUNT} values")
    cfs = [_number(value, f"{path}.cf_ratios[{index}]") for index, value in enumerate(cf_values)]
    baseline_n = _number(baseline, f"{path}.baseline_mean")
    excess_n = _number(excess, f"{path}.strict_excess_ratio")
    expected_baseline = math.fsum(cfs) / STRICT_CF_COUNT
    if not math.isclose(baseline_n, expected_baseline, rel_tol=0.0, abs_tol=1e-12):
        raise _error(f"{path}.baseline_mean", "must equal arithmetic mean of cf_ratios")
    if not math.isclose(excess_n, actual_n - baseline_n, rel_tol=0.0, abs_tol=1e-12):
        raise _error(f"{path}.strict_excess_ratio", "must equal actual_ratio - baseline_mean")
    return actual_n, cfs, baseline_n, excess_n


def validate_blackbox_row(
    row: Mapping[str, Any],
    *,
    source_row: Mapping[str, Any] | None = None,
    actual_row: Mapping[str, Any] | None = None,
    seen_keys: MutableSet[tuple[str, ...]] | None = None,
    path: str = "blackbox_row",
) -> Mapping[str, Any]:
    """Validate compression scores bound to one finalized strict source row."""

    row = _mapping(row, path)
    _exact_keys(row, BLACKBOX_KEYS, path)
    if row["schema_version"] != SCHEMA_VERSION or row["row_type"] != "strict_cf_blackbox":
        raise _error(path, "has the wrong schema_version or row_type")
    _validate_identity(row, path)
    _sha256(row["scoring_input_sha256"], f"{path}.scoring_input_sha256")
    if row["method"] != SCORING_METHOD:
        raise _error(f"{path}.method", f"must equal {SCORING_METHOD!r}")
    if row["protocol_sha256"] != SCORING_PROTOCOL_SHA256:
        raise _error(f"{path}.protocol_sha256", "does not match strict-CF scoring protocol")
    actual_n, _, _, _ = _validate_scored_metrics(
        actual=row["actual_ratio"],
        cf_values=row["cf_ratios"],
        baseline=row["baseline_mean"],
        excess=row["strict_excess_ratio"],
        path=path,
    )
    if _integer(row["baseline_n_valid"], f"{path}.baseline_n_valid") != STRICT_CF_COUNT:
        raise _error(f"{path}.baseline_n_valid", f"must equal {STRICT_CF_COUNT}")
    per_compressor = _mapping(row["per_compressor"], f"{path}.per_compressor")
    if set(per_compressor) != set(COMPRESSORS):
        raise _error(f"{path}.per_compressor", f"compressors must be exactly {COMPRESSORS}")
    for compressor in COMPRESSORS:
        values = _mapping(per_compressor[compressor], f"{path}.per_compressor.{compressor}")
        _exact_keys(
            values,
            {"actual_ratio", "cf_ratios", "baseline_mean", "strict_excess_ratio"},
            f"{path}.per_compressor.{compressor}",
        )
        _validate_scored_metrics(
            actual=values["actual_ratio"],
            cf_values=values["cf_ratios"],
            baseline=values["baseline_mean"],
            excess=values["strict_excess_ratio"],
            path=f"{path}.per_compressor.{compressor}",
        )
    reference = source_row if source_row is not None else actual_row
    if reference is not None:
        if source_row is not None:
            validate_strict_source_row(source_row, path="source_row")
            expected_scoring = source_row["scoring_input_sha256"]
        else:
            validate_actual_snapshot_row(actual_row, path="actual_row")  # type: ignore[arg-type]
            expected_scoring = None
        for field in (
            "semantic_key",
            "generation_model",
            "domain",
            "id",
            "source_id",
            "source_index",
            "source_text_sha256",
            "level",
            "source_cluster",
        ):
            if row[field] != reference[field]:
                raise _error(f"{path}.{field}", "differs from source identity")
        if expected_scoring is not None and row["scoring_input_sha256"] != expected_scoring:
            raise _error(f"{path}.scoring_input_sha256", "differs from strict source")
        expected_actual = reference["actual"]["actual_ratio"]
        if actual_n != expected_actual:
            raise _error(f"{path}.actual_ratio", "differs from immutable actual ratio")
        for compressor in COMPRESSORS:
            expected_comp = reference["actual"]["per_compressor"][compressor]["actual_ratio"]
            if per_compressor[compressor]["actual_ratio"] != expected_comp:
                raise _error(
                    f"{path}.per_compressor.{compressor}.actual_ratio",
                    "differs from immutable actual ratio",
                )
    key = tuple(row["semantic_key"])
    if seen_keys is not None:
        if key in seen_keys:
            raise _error(f"{path}.semantic_key", f"duplicate semantic key {key!r}")
        seen_keys.add(key)
    return row


RUN_STATUS_SCHEMA = f"{SCHEMA_ID}.run_status"
RUN_STATUS_PATH = "status.json"
RUN_STATES = (
    "prepared",
    "waiting_for_routes",
    "ready",
    "running",
    "held",
    "finalizing",
    "finalized",
    "failed",
)
RUN_EVENT_TYPES = (
    "binding_promoted",
    "launch_ready",
    "launch_started",
    "launch_aborted",
    "run_started",
    "checkpoint",
    "route_hold",
    "outage",
    "route_resume",
    "finalization_started",
    "finalized",
    "failed",
)


def validate_run_status(
    status: Mapping[str, Any],
    *,
    expected_lineage_id: str | None = None,
    path: str = "run_status",
) -> Mapping[str, Any]:
    """Validate the mutable atomic checkpoint, including route/outage history."""

    status = _mapping(status, path)
    _exact_keys(
        status,
        {
            "schema",
            "schema_version",
            "lineage_id",
            "updated_at_utc",
            "state",
            "completed_level_rows",
            "adopted_calls",
            "model_progress",
            "events",
        },
        path,
    )
    if status["schema"] != RUN_STATUS_SCHEMA or status["schema_version"] != SCHEMA_VERSION:
        raise _error(path, "has the wrong schema identifier/version")
    lineage_id = validate_lineage_id(status["lineage_id"], f"{path}.lineage_id")
    if expected_lineage_id is not None and lineage_id != expected_lineage_id:
        raise _error(f"{path}.lineage_id", "differs from expected lineage")
    _timestamp(status["updated_at_utc"], f"{path}.updated_at_utc")
    if status["state"] not in RUN_STATES:
        raise _error(f"{path}.state", f"must be one of {RUN_STATES}")
    completed = _integer(
        status["completed_level_rows"], f"{path}.completed_level_rows"
    )
    if completed > EXPECTED_LEVEL_ROWS:
        raise _error(
            f"{path}.completed_level_rows", f"cannot exceed {EXPECTED_LEVEL_ROWS}"
        )
    adopted_calls = _integer(status["adopted_calls"], f"{path}.adopted_calls")
    if adopted_calls > EXPECTED_ADOPTED_CALLS:
        raise _error(
            f"{path}.adopted_calls", f"cannot exceed {EXPECTED_ADOPTED_CALLS}"
        )
    progress = _mapping(status["model_progress"], f"{path}.model_progress")
    _exact_keys(progress, set(MODELS), f"{path}.model_progress")
    progress_levels = 0
    progress_calls = 0
    for model in MODELS:
        entry_path = f"{path}.model_progress.{model}"
        entry = _mapping(progress[model], entry_path)
        _exact_keys(
            entry,
            {
                "binding_state", "execution_state", "formal_pointer_sha256",
                "bundle_sha256", "completed_level_rows", "adopted_calls",
            },
            entry_path,
        )
        if entry["binding_state"] not in {"deferred", "formal"}:
            raise _error(f"{entry_path}.binding_state", "must be deferred/formal")
        if entry["execution_state"] not in {
            "waiting", "ready", "running", "held", "complete"
        }:
            raise _error(f"{entry_path}.execution_state", "invalid model execution state")
        pointer = entry["formal_pointer_sha256"]
        bundle = entry["bundle_sha256"]
        if entry["binding_state"] == "deferred":
            if pointer is not None or bundle is not None:
                raise _error(entry_path, "deferred model must have null pointer/bundle")
        else:
            _sha256(pointer, f"{entry_path}.formal_pointer_sha256")
            _sha256(bundle, f"{entry_path}.bundle_sha256")
        model_levels = _integer(
            entry["completed_level_rows"], f"{entry_path}.completed_level_rows"
        )
        model_calls = _integer(entry["adopted_calls"], f"{entry_path}.adopted_calls")
        if model_levels > EXPECTED_LEVEL_ROWS_PER_MODEL:
            raise _error(entry_path, "model completed-level count exceeds slot")
        if model_calls > EXPECTED_ADOPTED_CALLS_PER_MODEL:
            raise _error(entry_path, "model adopted-call count exceeds slot")
        if model_calls != model_levels * EXPECTED_ADOPTED_CALLS_PER_LEVEL:
            raise _error(entry_path, "model adopted calls must equal six per complete level")
        progress_levels += model_levels
        progress_calls += model_calls
    if progress_levels != completed or progress_calls != adopted_calls:
        raise _error(path, "aggregate progress differs from model projections")
    events = status["events"]
    if not isinstance(events, list):
        raise _error(f"{path}.events", "must be a list")
    previous_time: datetime | None = None
    for index, raw in enumerate(events):
        event_path = f"{path}.events[{index}]"
        event = _mapping(raw, event_path)
        _exact_keys(
            event,
            {
                "sequence",
                "at_utc",
                "type",
                "generation_model",
                "route",
                "formal_pointer_sha256",
                "bundle_sha256",
                "cohort_root_sha256",
                "protocol_sha256",
                "detail",
            },
            event_path,
        )
        if _integer(event["sequence"], f"{event_path}.sequence") != index:
            raise _error(f"{event_path}.sequence", "must be zero-based and contiguous")
        text = _timestamp(event["at_utc"], f"{event_path}.at_utc")
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if previous_time is not None and moment < previous_time:
            raise _error(f"{event_path}.at_utc", "events must be chronological")
        previous_time = moment
        if event["type"] not in RUN_EVENT_TYPES:
            raise _error(f"{event_path}.type", f"must be one of {RUN_EVENT_TYPES}")
        model = event["generation_model"]
        if model is not None and model not in MODELS:
            raise _error(f"{event_path}.generation_model", f"must be null or one of {MODELS}")
        route = event["route"]
        if route is not None:
            _string(route, f"{event_path}.route")
        binding_values = (
            event["formal_pointer_sha256"],
            event["bundle_sha256"],
            event["cohort_root_sha256"],
            event["protocol_sha256"],
        )
        if any(value is not None for value in binding_values):
            if model is None or not all(value is not None for value in binding_values):
                raise _error(event_path, "model binding fields must be all-null or all-hashed")
            for name, value in zip(
                ("formal_pointer_sha256", "bundle_sha256", "cohort_root_sha256", "protocol_sha256"),
                binding_values,
            ):
                _sha256(value, f"{event_path}.{name}")
        detail = event["detail"]
        if detail is not None and not isinstance(detail, str):
            raise _error(f"{event_path}.detail", "must be null or a string")
        if event["type"] in {"route_hold", "outage", "route_resume"}:
            if model is None or route is None:
                raise _error(event_path, "route events require generation_model and route")
    return status


MANIFEST_KEYS = {
    "schema",
    "schema_version",
    "lineage_id",
    "created_at_utc",
    "immutable",
    "models",
    "domains",
    "levels",
    "actual_source_protocols",
    "route_slots",
    "transport",
    "cohort",
    "expected_counts",
    "selection",
    "creation_inventory",
    "artifacts",
}


def _validate_hashed_inventory(
    value: Any,
    path: str,
    *,
    required_roles: set[str] | None = None,
    verify_files: bool = False,
    require_absolute: bool = False,
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise _error(path, "must be a list" if allow_empty else "must be a non-empty list")
    seen_paths: set[str] = set()
    roles: set[str] = set()
    for index, raw in enumerate(value):
        entry_path = f"{path}[{index}]"
        entry = _mapping(raw, entry_path)
        _exact_keys(entry, {"role", "path", "sha256"}, entry_path)
        role = _string(entry["role"], f"{entry_path}.role")
        item_path = _string(entry["path"], f"{entry_path}.path")
        digest = _sha256(entry["sha256"], f"{entry_path}.sha256")
        resolved = Path(item_path)
        if require_absolute and not resolved.is_absolute():
            raise _error(f"{entry_path}.path", "must be an absolute path")
        resolved = resolved.resolve()
        if item_path in seen_paths:
            raise _error(f"{entry_path}.path", "duplicate inventory path")
        seen_paths.add(item_path)
        roles.add(role)
        if verify_files:
            if not resolved.is_file():
                raise _error(f"{entry_path}.path", f"inventory file is missing: {resolved}")
            if storage.file_sha256(resolved) != digest:
                raise _error(
                    f"{entry_path}.sha256",
                    f"current file differs from creation inventory: {resolved}",
                )
    if required_roles is not None and not required_roles.issubset(roles):
        raise _error(path, f"missing required roles {sorted(required_roles - roles)}")


def validate_creation_inventory(
    value: Any,
    path: str = "creation_inventory",
    *,
    verify_files: bool = False,
) -> Mapping[str, Any]:
    value = _mapping(value, path)
    _exact_keys(value, {"scoring_protocol_sha256", "code", "clients"}, path)
    if value["scoring_protocol_sha256"] != SCORING_PROTOCOL_SHA256:
        raise _error(f"{path}.scoring_protocol_sha256", "does not match scoring protocol")
    _validate_hashed_inventory(
        value["code"],
        f"{path}.code",
        required_roles=set(CREATION_CODE_ROLES),
        verify_files=verify_files,
        require_absolute=True,
    )
    _validate_hashed_inventory(
        value["clients"],
        f"{path}.clients",
        required_roles=set(CREATION_CLIENT_ROLES),
        verify_files=verify_files,
        require_absolute=True,
        allow_empty=not CREATION_CLIENT_ROLES,
    )
    return value


def _strict_json_document(data: bytes, path: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise _error(path, f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(path, f"non-finite JSON constant {value!r}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _error(path, f"is not strict UTF-8 JSON: {exc}") from exc


def _strict_jsonl_documents(file_path: Path, path: str):
    with file_path.open("rb") as handle:
        for index, raw_line in enumerate(handle, start=1):
            if not raw_line.endswith(b"\n"):
                raise _error(f"{path}[{index}]", "JSONL row must end with LF")
            line = raw_line[:-1]
            if not line:
                raise _error(f"{path}[{index}]", "JSONL row must not be blank")
            yield index, _strict_json_document(line, f"{path}[{index}]")


def validate_run_actual_model_item_bindings(
    manifest: Mapping[str, Any],
    *,
    run_dir: str | Path,
    project_root: str | Path | None = None,
    path: str = "run_snapshot_bindings",
) -> dict[str, Any]:
    """Validate frozen cutover membership and every actual-to-item projection."""

    root = Path(run_dir).resolve(strict=True)
    artifacts = _mapping(manifest["artifacts"], f"{path}.artifacts")
    cutover_entry = artifacts["historical_cutover_manifest"]
    cutover_path = assert_path_within_run(
        root, cutover_entry["path"], must_exist=True
    )
    cutover_bytes = cutover_path.read_bytes()
    if storage.sha256_bytes(cutover_bytes) != cutover_entry["sha256"]:
        raise _error(f"{path}.historical_cutover_manifest", "hash mismatch")
    cutover_document = _strict_json_document(
        cutover_bytes, f"{path}.historical_cutover_manifest"
    )
    cutover_membership = validate_historical_cutover_manifest_document(
        cutover_document, path=f"{path}.historical_cutover_manifest"
    )

    model_entry = artifacts["model_items"]
    model_path = assert_path_within_run(root, model_entry["path"], must_exist=True)
    model_bytes = model_path.read_bytes()
    if model_bytes and not model_bytes.endswith(b"\n"):
        raise _error(f"{path}.model_items", "JSONL must end with LF")
    if storage.sha256_bytes(model_bytes) != model_entry["sha256"]:
        raise _error(f"{path}.model_items", "hash mismatch")
    model_items: dict[tuple[str, ...], Mapping[str, Any]] = {}
    response_ids: set[str] = set()
    seen_items: set[tuple[str, ...]] = set()
    for index, line in enumerate(model_bytes.splitlines(), start=1):
        row = _strict_json_document(line, f"{path}.model_items[{index}]")
        validate_model_item_row(
            row,
            project_root=project_root,
            seen_response_ids=response_ids,
            seen_keys=seen_items,
            path=f"{path}.model_items[{index}]",
        )
        tier = row["provenance_tier"]
        if tier == PROVENANCE_TIER_HISTORICAL_API821:
            scope = cutover_membership[(row["generation_model"], row["domain"])]
            attestation = row["historical_cutover_attestation"]
            if (
                row["id"] not in scope["ids"]
                or Path(attestation["manifest_path"]).resolve() != cutover_path
                or attestation["manifest_sha256"] != cutover_entry["sha256"]
                or attestation["scope_ids_sha256"] != scope["ids_sha256"]
                or attestation["scope_row_count"] != scope["row_count"]
            ):
                raise _error(
                    f"{path}.model_items[{index}]",
                    "historical item is not bound to the frozen cutover scope",
                )
        model_items[tuple(row["model_item_key"])] = row
    if len(model_items) != EXPECTED_MODEL_ITEMS:
        raise _error(
            f"{path}.model_items",
            f"row count {len(model_items)} != {EXPECTED_MODEL_ITEMS}",
        )

    actual_entry = artifacts["actual_levels"]
    actual_path = assert_path_within_run(root, actual_entry["path"], must_exist=True)
    actual_bytes = actual_path.read_bytes()
    if actual_bytes and not actual_bytes.endswith(b"\n"):
        raise _error(f"{path}.actual_levels", "JSONL must end with LF")
    if storage.sha256_bytes(actual_bytes) != actual_entry["sha256"]:
        raise _error(f"{path}.actual_levels", "hash mismatch")
    seen_actual: set[tuple[str, ...]] = set()
    levels_by_item: dict[tuple[str, ...], set[str]] = {}
    actual_rows: list[Mapping[str, Any]] = []
    for index, line in enumerate(actual_bytes.splitlines(), start=1):
        row = _strict_json_document(line, f"{path}.actual_levels[{index}]")
        validate_actual_snapshot_row(
            row,
            seen_keys=seen_actual,
            path=f"{path}.actual_levels[{index}]",
        )
        item_key = tuple(row["semantic_key"][:-1])
        model_item = model_items.get(item_key)
        if model_item is None:
            raise _error(
                f"{path}.actual_levels[{index}]",
                "semantic key has no model-item provenance preimage",
            )
        validate_actual_against_model_item(
            row,
            model_item,
            model_item_validated=True,
            project_root=project_root,
            path=f"{path}.actual_levels[{index}]",
        )
        levels_by_item.setdefault(item_key, set()).add(row["level"])
        actual_rows.append(row)
    if len(actual_rows) != EXPECTED_LEVEL_ROWS:
        raise _error(
            f"{path}.actual_levels",
            f"row count {len(actual_rows)} != {EXPECTED_LEVEL_ROWS}",
        )
    if set(levels_by_item) != set(model_items) or any(
        levels != set(LEVELS) for levels in levels_by_item.values()
    ):
        raise _error(path, "actual/model-item relation is not an exact L1-L5 bijection")

    full_model_entry = artifacts["full_model_items"]
    full_model_path = assert_path_within_run(
        root, full_model_entry["path"], must_exist=True
    )
    if storage.file_sha256(full_model_path) != full_model_entry["sha256"]:
        raise _error(f"{path}.full_model_items", "hash mismatch")
    full_model_items: dict[tuple[str, ...], Mapping[str, Any]] = {}
    full_response_ids: set[str] = set()
    full_seen_items: set[tuple[str, ...]] = set()
    for index, row in _strict_jsonl_documents(
        full_model_path, f"{path}.full_model_items"
    ):
        validate_model_item_row(
            row,
            project_root=project_root,
            seen_response_ids=full_response_ids,
            seen_keys=full_seen_items,
            allow_legacy_unattested=True,
            path=f"{path}.full_model_items[{index}]",
        )
        if row["provenance_tier"] == PROVENANCE_TIER_HISTORICAL_API821:
            scope = cutover_membership[(row["generation_model"], row["domain"])]
            attestation = row["historical_cutover_attestation"]
            if (
                row["id"] not in scope["ids"]
                or Path(attestation["manifest_path"]).resolve() != cutover_path
                or attestation["manifest_sha256"] != cutover_entry["sha256"]
                or attestation["scope_ids_sha256"] != scope["ids_sha256"]
                or attestation["scope_row_count"] != scope["row_count"]
            ):
                raise _error(
                    f"{path}.full_model_items[{index}]",
                    "historical item is not bound to the frozen cutover scope",
                )
        full_model_items[tuple(row["model_item_key"])] = row
    if len(full_model_items) != full_model_entry["row_count"]:
        raise _error(f"{path}.full_model_items", "row count differs from manifest")

    full_actual_entry = artifacts["full_actual_levels"]
    full_actual_path = assert_path_within_run(
        root, full_actual_entry["path"], must_exist=True
    )
    if storage.file_sha256(full_actual_path) != full_actual_entry["sha256"]:
        raise _error(f"{path}.full_actual_levels", "hash mismatch")
    full_seen_actual: set[tuple[str, ...]] = set()
    full_levels_by_item: dict[tuple[str, ...], set[str]] = {}
    full_actual_by_key: dict[tuple[str, ...], Mapping[str, Any]] = {}
    full_actual_count = 0
    for index, row in _strict_jsonl_documents(
        full_actual_path, f"{path}.full_actual_levels"
    ):
        validate_actual_snapshot_row(
            row,
            seen_keys=full_seen_actual,
            path=f"{path}.full_actual_levels[{index}]",
        )
        item_key = tuple(row["semantic_key"][:-1])
        model_item = full_model_items.get(item_key)
        if model_item is None:
            raise _error(
                f"{path}.full_actual_levels[{index}]",
                "semantic key has no full model item",
            )
        validate_actual_against_model_item(
            row,
            model_item,
            model_item_validated=True,
            allow_legacy_unattested=True,
            project_root=project_root,
            path=f"{path}.full_actual_levels[{index}]",
        )
        full_levels_by_item.setdefault(item_key, set()).add(row["level"])
        semantic_key = tuple(row["semantic_key"])
        if semantic_key in seen_actual:
            full_actual_by_key[semantic_key] = row
        full_actual_count += 1
    if full_actual_count != full_actual_entry["row_count"]:
        raise _error(f"{path}.full_actual_levels", "row count differs from manifest")
    if set(full_levels_by_item) != set(full_model_items) or any(
        levels != set(LEVELS) for levels in full_levels_by_item.values()
    ):
        raise _error(path, "full actual/model-item graph is not an exact L1-L5 bijection")

    stable_model_fields = MODEL_ITEM_KEYS - {"actual_level_row_sha256"}
    for item_key, selected_item in model_items.items():
        full_item = full_model_items.get(item_key)
        if full_item is None or any(
            selected_item[field] != full_item[field]
            for field in stable_model_fields
        ):
            raise _error(path, "selected model item is not a consistent full-graph subset")
    for selected_row in actual_rows:
        full_row = full_actual_by_key.get(tuple(selected_row["semantic_key"]))
        if full_row is None:
            raise _error(path, "selected actual row is absent from full graph")
        comparable_full = dict(full_row)
        comparable_full["verification_tier"] = selected_row["verification_tier"]
        if comparable_full != selected_row:
            raise _error(path, "selected actual differs from its full-graph observation")
    return {
        "actual_rows": actual_rows,
        "cutover_membership": cutover_membership,
        "cutover_path": cutover_path,
        "selected_full_actual_rows": list(full_actual_by_key.values()),
        "full_actual_row_count": full_actual_count,
        "full_model_items": full_model_items,
        "model_items": model_items,
        "response_ids": response_ids,
    }


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    run_dir: str | Path | None = None,
    project_root: str | Path | None = None,
    verify_files: bool = False,
    require_finalized: bool = False,
    path: str = "manifest",
) -> Mapping[str, Any]:
    """Validate the exact manifest and, optionally, its on-disk artifacts."""

    manifest = _mapping(manifest, path)
    _exact_keys(manifest, MANIFEST_KEYS, path)
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["schema_version"] != SCHEMA_VERSION:
        raise _error(path, "has the wrong schema identifier/version")
    validate_lineage_id(manifest["lineage_id"], f"{path}.lineage_id")
    _timestamp(manifest["created_at_utc"], f"{path}.created_at_utc")
    if manifest["immutable"] is not True:
        raise _error(f"{path}.immutable", "must be true")
    if (
        tuple(manifest["models"]) != MODELS
        or tuple(manifest["domains"]) != DOMAINS
        or tuple(manifest["levels"]) != LEVELS
    ):
        raise _error(path, "model/domain/level rosters must exactly match strict-CF v1")
    if manifest["actual_source_protocols"] != ACTUAL_SOURCE_PROTOCOLS:
        raise _error(
            f"{path}.actual_source_protocols",
            "must exactly match approved actual-observation protocols",
        )
    if manifest["route_slots"] != STRICT_CF_SLOT_CONTRACTS:
        raise _error(f"{path}.route_slots", "must equal the five deferred slot contracts")
    if manifest["transport"] != {
        "abi_version": TRANSPORT_ABI_VERSION,
        "abi_sha256": TRANSPORT_ABI_SHA256,
        "request_schema": "experiment_a.strict_cf_v1.transport_request",
        "response_schema": "experiment_a.strict_cf_v1.transport_response",
    }:
        raise _error(f"{path}.transport", "does not match the frozen transport ABI")
    expected_counts = {
        "source_clusters": EXPECTED_SOURCE_CLUSTERS,
        "model_items": EXPECTED_MODEL_ITEMS,
        "level_rows": EXPECTED_LEVEL_ROWS,
        "sources_per_domain": EXPECTED_SOURCES_PER_DOMAIN,
        "level_rows_per_model": EXPECTED_LEVEL_ROWS_PER_MODEL,
        "adopted_calls_per_level": EXPECTED_ADOPTED_CALLS_PER_LEVEL,
        "adopted_calls_per_model": EXPECTED_ADOPTED_CALLS_PER_MODEL,
        "adopted_calls_total": EXPECTED_ADOPTED_CALLS,
    }
    observed_counts = _mapping(manifest["expected_counts"], f"{path}.expected_counts")
    if set(observed_counts) != set(expected_counts) | {"full_actual_level_rows"}:
        raise _error(f"{path}.expected_counts", "has incorrect count keys")
    for name, expected in expected_counts.items():
        if observed_counts[name] != expected:
            raise _error(f"{path}.expected_counts.{name}", f"must equal {expected}")
    full_count = _integer(
        observed_counts["full_actual_level_rows"],
        f"{path}.expected_counts.full_actual_level_rows",
        minimum=1,
    )
    if full_count % len(LEVELS) != 0:
        raise _error(
            f"{path}.expected_counts.full_actual_level_rows",
            "must be divisible by five",
        )
    if manifest["selection"] != {
        "algorithm": SELECTION_ALGORITHM,
        "seed": SELECTION_SEED,
    }:
        raise _error(f"{path}.selection", "does not match deterministic selection protocol")
    cohort = _mapping(manifest["cohort"], f"{path}.cohort")
    _exact_keys(
        cohort,
        {
            "selected_source_hashes_sha256",
            "selected_model_item_provenance_tiers",
            "selected_level_row_provenance_tiers",
            "root_sha256",
        },
        f"{path}.cohort",
    )
    if cohort["selected_source_hashes_sha256"] != EXPECTED_SELECTED_SOURCE_HASHES_SHA256:
        raise _error(f"{path}.cohort.selected_source_hashes_sha256", "differs from approved sample")
    if cohort["selected_model_item_provenance_tiers"] != EXPECTED_SELECTED_MODEL_ITEM_PROVENANCE_TIERS:
        raise _error(f"{path}.cohort.selected_model_item_provenance_tiers", "differs from approved sample")
    if cohort["selected_level_row_provenance_tiers"] != EXPECTED_SELECTED_LEVEL_PROVENANCE_TIERS:
        raise _error(f"{path}.cohort.selected_level_row_provenance_tiers", "differs from approved sample")
    _sha256(cohort["root_sha256"], f"{path}.cohort.root_sha256")
    if cohort["root_sha256"] != compute_cohort_root(manifest):
        raise _error(f"{path}.cohort.root_sha256", "does not hash the scientific cohort preimage")
    validate_creation_inventory(
        manifest["creation_inventory"],
        f"{path}.creation_inventory",
        verify_files=verify_files,
    )
    artifacts = _mapping(manifest["artifacts"], f"{path}.artifacts")
    if set(artifacts) != set(ARTIFACT_SPECS):
        raise _error(f"{path}.artifacts", f"names must be exactly {tuple(ARTIFACT_SPECS)}")
    for name, (expected_path, expected_count, required_at_creation) in ARTIFACT_SPECS.items():
        entry_path = f"{path}.artifacts.{name}"
        entry = _mapping(artifacts[name], entry_path)
        _exact_keys(entry, {"path", "row_count", "sha256", "required_at_creation"}, entry_path)
        if entry["path"] != expected_path or entry["required_at_creation"] is not required_at_creation:
            raise _error(entry_path, "path/lifecycle differs from canonical artifact spec")
        row_count = entry["row_count"]
        if expected_count is None:
            if type(row_count) is not int or row_count <= 0:
                raise _error(
                    f"{entry_path}.row_count",
                    "dynamic snapshot count must be positive",
                )
            if name == "full_actual_levels" and (
                row_count % len(LEVELS) != 0 or row_count != full_count
            ):
                raise _error(
                    f"{entry_path}.row_count",
                    "must equal full_actual_level_rows and be divisible by five",
                )
            if name == "full_model_items" and row_count * len(LEVELS) != full_count:
                raise _error(
                    f"{entry_path}.row_count",
                    "must equal full_actual_level_rows / five",
                )
        elif row_count != expected_count:
            raise _error(f"{entry_path}.row_count", f"must equal {expected_count}")
        digest = entry["sha256"]
        if digest is not None:
            _sha256(digest, f"{entry_path}.sha256")
        if required_at_creation and digest is None:
            raise _error(f"{entry_path}.sha256", "immutable creation artifact requires a digest")
        if not required_at_creation and digest is not None:
            raise _error(f"{entry_path}.sha256", "future artifact digest must be null in immutable manifest")
        if run_dir is not None:
            artifact_path = assert_path_within_run(run_dir, entry["path"])
            exists = artifact_path.is_file()
            required_now = required_at_creation or (
                require_finalized
                and name in {"lineage", "blackbox", "source", "finalized"}
            )
            if verify_files and required_now and not exists:
                raise _error(entry_path, f"required artifact is missing: {artifact_path}")
            if (
                verify_files
                and exists
                and digest is not None
                and storage.file_sha256(artifact_path) != digest
            ):
                raise _error(f"{entry_path}.sha256", "on-disk artifact hash mismatch")
    if run_dir is not None and Path(run_dir).resolve().name != manifest["lineage_id"]:
        raise _error(f"{path}.lineage_id", "does not match run directory name")
    if verify_files and run_dir is not None:
        validate_run_actual_model_item_bindings(
            manifest,
            run_dir=run_dir,
            project_root=project_root,
            path=f"{path}.snapshot_bindings",
        )
    return manifest


FINAL_LINEAGE_SCHEMA = f"{SCHEMA_ID}.final_lineage"
FINALIZED_SCHEMA = f"{SCHEMA_ID}.finalized"
CHECKPOINTS_REL = "checkpoints"
ROUTE_STATES_REL = "status/routes"
_CHECKPOINT_PATH_RE = re.compile(
    r"^checkpoints/([^/]+)/([^/]+)/([^/]+)/L([1-5])\.json$"
)
_ROUTE_STATE_PATH_RE = re.compile(r"^status/routes/[^/]+\.json$")


def canonical_checkpoint_inventory_from_run(
    run_dir: str | Path,
    *,
    expected_count: int = EXPECTED_LEVEL_ROWS,
) -> tuple[list[dict[str, str]], str]:
    """Hash the exact path-sorted checkpoint-file preimage under one run.

    Every file below ``checkpoints/`` must be a canonical model/domain/source/Lx
    JSON path.  The digest binds both relative paths and exact file bytes.
    """

    if type(expected_count) is not int or expected_count < 0:
        raise ValueError("expected_count must be a non-negative integer")
    root = Path(run_dir).resolve(strict=True)
    checkpoint_root = assert_path_within_run(root, CHECKPOINTS_REL)
    files = (
        sorted(path for path in checkpoint_root.rglob("*") if path.is_file())
        if checkpoint_root.exists()
        else []
    )
    if len(files) != expected_count:
        raise _error(
            "checkpoint_inventory.entry_count",
            f"on-disk checkpoint file count {len(files)} != {expected_count}",
        )
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, path in enumerate(files):
        resolved = assert_path_within_run(root, path, must_exist=True)
        relative = resolved.relative_to(root).as_posix()
        match = _CHECKPOINT_PATH_RE.fullmatch(relative)
        if match is None:
            raise _error(
                f"checkpoint_inventory.files[{index}]",
                f"noncanonical checkpoint path {relative!r}",
            )
        model, domain, source_component, level_number = match.groups()
        if model not in MODELS or domain not in DOMAINS:
            raise _error(
                f"checkpoint_inventory.files[{index}]",
                f"out-of-roster checkpoint path {relative!r}",
            )
        if not source_component or source_component in {".", ".."}:
            raise _error(
                f"checkpoint_inventory.files[{index}]",
                "invalid source path component",
            )
        if relative in seen:
            raise _error(
                f"checkpoint_inventory.files[{index}]", "duplicate checkpoint path"
            )
        seen.add(relative)
        entries.append({"path": relative, "sha256": storage.file_sha256(resolved)})
    entries.sort(key=lambda entry: entry["path"])
    return entries, canonical_sha256(entries)


def canonical_route_state_inventory_from_run(
    run_dir: str | Path,
) -> tuple[list[dict[str, str]], str]:
    """Hash exact durable route-state JSON; transient lock files are excluded."""

    root = Path(run_dir).resolve(strict=True)
    route_root = assert_path_within_run(root, ROUTE_STATES_REL)
    files: list[Path] = []
    if route_root.exists():
        for path in route_root.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative_to_route = path.relative_to(route_root)
            except ValueError as exc:
                raise _error("route_state_inventory", "route-state path escaped root") from exc
            if ".locks" in relative_to_route.parts:
                continue
            files.append(path)
    entries: list[dict[str, str]] = []
    for index, path in enumerate(sorted(files)):
        resolved = assert_path_within_run(root, path, must_exist=True)
        relative = resolved.relative_to(root).as_posix()
        if _ROUTE_STATE_PATH_RE.fullmatch(relative) is None:
            raise _error(
                f"route_state_inventory.files[{index}]",
                f"noncanonical route-state path {relative!r}",
            )
        entries.append({"path": relative, "sha256": storage.file_sha256(resolved)})
    entries.sort(key=lambda entry: entry["path"])
    return entries, canonical_sha256(entries)


def _validate_artifact_binding(
    value: Any,
    path: str,
    *,
    expected_path: str,
    expected_count: int,
    run_dir: str | Path | None,
    verify_files: bool,
) -> None:
    value = _mapping(value, path)
    _exact_keys(value, {"path", "sha256", "row_count"}, path)
    if value["path"] != expected_path:
        raise _error(f"{path}.path", f"must equal {expected_path!r}")
    if value["row_count"] != expected_count:
        raise _error(f"{path}.row_count", f"must equal {expected_count}")
    digest = _sha256(value["sha256"], f"{path}.sha256")
    if run_dir is not None and verify_files:
        artifact = assert_path_within_run(run_dir, expected_path, must_exist=True)
        if storage.file_sha256(artifact) != digest:
            raise _error(f"{path}.sha256", "on-disk artifact hash mismatch")


def validate_final_lineage(
    lineage: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] | None = None,
    run_dir: str | Path | None = None,
    verify_files: bool = False,
    path: str = "final_lineage",
) -> Mapping[str, Any]:
    """Validate the one-object final lineage consumed by white-box analysis."""

    lineage = _mapping(lineage, path)
    _exact_keys(
        lineage,
        {
            "schema",
            "schema_version",
            "lineage_id",
            "finalized_at_utc",
            "manifest",
            "preparation_lineage",
            "historical_cutover_manifest",
            "historical_repair_audit",
            "historical_repair_method",
            "full_model_items",
            "actual",
            "source",
            "blackbox",
            "checkpoint_inventory",
            "route_state_inventory",
            "formal_binding_inventory",
            "launch_inventory",
            "cohort_root_sha256",
            "per_model_counts",
            "scoring",
            "schema_inventory",
            "code_inventory",
        },
        path,
    )
    if lineage["schema"] != FINAL_LINEAGE_SCHEMA or lineage["schema_version"] != SCHEMA_VERSION:
        raise _error(path, "has the wrong schema identifier/version")
    lineage_id = validate_lineage_id(lineage["lineage_id"], f"{path}.lineage_id")
    _timestamp(lineage["finalized_at_utc"], f"{path}.finalized_at_utc")
    _validate_artifact_binding(
        lineage["manifest"],
        f"{path}.manifest",
        expected_path="manifest.json",
        expected_count=1,
        run_dir=run_dir,
        verify_files=verify_files,
    )
    _validate_artifact_binding(
        lineage["preparation_lineage"],
        f"{path}.preparation_lineage",
        expected_path=ARTIFACT_SPECS["preparation_lineage"][0],
        expected_count=1,
        run_dir=run_dir,
        verify_files=verify_files,
    )
    _validate_artifact_binding(
        lineage["historical_cutover_manifest"],
        f"{path}.historical_cutover_manifest",
        expected_path=ARTIFACT_SPECS["historical_cutover_manifest"][0],
        expected_count=1,
        run_dir=run_dir,
        verify_files=verify_files,
    )
    for evidence_name in (
        "historical_repair_audit",
        "historical_repair_method",
    ):
        _validate_artifact_binding(
            lineage[evidence_name],
            f"{path}.{evidence_name}",
            expected_path=ARTIFACT_SPECS[evidence_name][0],
            expected_count=1,
            run_dir=run_dir,
            verify_files=verify_files,
        )
    _validate_artifact_binding(
        lineage["full_model_items"],
        f"{path}.full_model_items",
        expected_path=ARTIFACT_SPECS["full_model_items"][0],
        expected_count=lineage["full_model_items"]["row_count"],
        run_dir=run_dir,
        verify_files=verify_files,
    )
    if (
        type(lineage["full_model_items"]["row_count"]) is not int
        or lineage["full_model_items"]["row_count"] <= 0
    ):
        raise _error(f"{path}.full_model_items.row_count", "must be positive")
    for name in ("actual", "source", "blackbox"):
        artifact_name = "actual_levels" if name == "actual" else name
        expected_path, expected_count, _ = ARTIFACT_SPECS[artifact_name]
        _validate_artifact_binding(
            lineage[name],
            f"{path}.{name}",
            expected_path=expected_path,
            expected_count=expected_count,  # type: ignore[arg-type]
            run_dir=run_dir,
            verify_files=verify_files,
        )
    checkpoint = _mapping(lineage["checkpoint_inventory"], f"{path}.checkpoint_inventory")
    _exact_keys(checkpoint, {"entry_count", "sha256"}, f"{path}.checkpoint_inventory")
    if _integer(checkpoint["entry_count"], f"{path}.checkpoint_inventory.entry_count", minimum=0) != EXPECTED_LEVEL_ROWS:
        raise _error(
            f"{path}.checkpoint_inventory.entry_count",
            f"must equal exactly {EXPECTED_LEVEL_ROWS}",
        )
    checkpoint_digest = _sha256(
        checkpoint["sha256"], f"{path}.checkpoint_inventory.sha256"
    )
    if run_dir is not None and verify_files:
        _, observed_checkpoint_digest = canonical_checkpoint_inventory_from_run(
            run_dir, expected_count=EXPECTED_LEVEL_ROWS
        )
        if observed_checkpoint_digest != checkpoint_digest:
            raise _error(
                f"{path}.checkpoint_inventory.sha256",
                "does not match canonical on-disk checkpoint preimage",
            )
    route_state = _mapping(
        lineage["route_state_inventory"], f"{path}.route_state_inventory"
    )
    _exact_keys(
        route_state,
        {"entry_count", "sha256"},
        f"{path}.route_state_inventory",
    )
    route_count = _integer(
        route_state["entry_count"],
        f"{path}.route_state_inventory.entry_count",
        minimum=0,
    )
    route_digest = _sha256(
        route_state["sha256"], f"{path}.route_state_inventory.sha256"
    )
    if run_dir is not None and verify_files:
        route_entries, observed_route_digest = canonical_route_state_inventory_from_run(
            run_dir
        )
        if len(route_entries) != route_count:
            raise _error(
                f"{path}.route_state_inventory.entry_count",
                f"on-disk route-state count {len(route_entries)} != {route_count}",
            )
        if observed_route_digest != route_digest:
            raise _error(
                f"{path}.route_state_inventory.sha256",
                "does not match canonical on-disk route-state preimage",
            )
    for inventory_name, expected_entries in (
        ("formal_binding_inventory", len(MODELS)),
        ("launch_inventory", None),
    ):
        inventory = _mapping(lineage[inventory_name], f"{path}.{inventory_name}")
        _exact_keys(
            inventory,
            {"entry_count", "sha256"},
            f"{path}.{inventory_name}",
        )
        entry_count = _integer(
            inventory["entry_count"],
            f"{path}.{inventory_name}.entry_count",
            minimum=0,
        )
        if expected_entries is not None and entry_count != expected_entries:
            raise _error(
                f"{path}.{inventory_name}.entry_count",
                f"must equal {expected_entries}",
            )
        _sha256(inventory["sha256"], f"{path}.{inventory_name}.sha256")
    cohort_root = _sha256(lineage["cohort_root_sha256"], f"{path}.cohort_root_sha256")
    counts = _mapping(lineage["per_model_counts"], f"{path}.per_model_counts")
    _exact_keys(counts, {"checkpoints", "adopted_calls"}, f"{path}.per_model_counts")
    for count_name, expected in (
        ("checkpoints", EXPECTED_LEVEL_ROWS_PER_MODEL),
        ("adopted_calls", EXPECTED_ADOPTED_CALLS_PER_MODEL),
    ):
        values = _mapping(counts[count_name], f"{path}.per_model_counts.{count_name}")
        _exact_keys(values, set(MODELS), f"{path}.per_model_counts.{count_name}")
        if any(value != expected for value in values.values()):
            raise _error(f"{path}.per_model_counts.{count_name}", f"all values must equal {expected}")
    scoring = _mapping(lineage["scoring"], f"{path}.scoring")
    if dict(scoring) != {
        "method": SCORING_METHOD,
        "protocol_sha256": SCORING_PROTOCOL_SHA256,
    }:
        raise _error(f"{path}.scoring", "does not match strict-CF scoring contract")
    schema_inventory = lineage["schema_inventory"]
    if not isinstance(schema_inventory, list) or not schema_inventory:
        raise _error(f"{path}.schema_inventory", "must be a non-empty list")
    seen_schemas: set[str] = set()
    for index, raw in enumerate(schema_inventory):
        entry_path = f"{path}.schema_inventory[{index}]"
        entry = _mapping(raw, entry_path)
        _exact_keys(entry, {"name", "version", "sha256"}, entry_path)
        name = _string(entry["name"], f"{entry_path}.name")
        _integer(entry["version"], f"{entry_path}.version", minimum=1)
        _sha256(entry["sha256"], f"{entry_path}.sha256")
        if name in seen_schemas:
            raise _error(f"{entry_path}.name", "duplicate schema inventory name")
        seen_schemas.add(name)
    _validate_hashed_inventory(lineage["code_inventory"], f"{path}.code_inventory")
    if manifest is not None:
        validate_manifest(manifest, run_dir=run_dir, verify_files=verify_files)
        if manifest["lineage_id"] != lineage_id:
            raise _error(f"{path}.lineage_id", "differs from manifest")
        if cohort_root != manifest["cohort"]["root_sha256"]:
            raise _error(f"{path}.cohort_root_sha256", "differs from manifest")
        for lineage_name, artifact_name in (
            ("preparation_lineage", "preparation_lineage"),
            ("historical_cutover_manifest", "historical_cutover_manifest"),
            ("historical_repair_audit", "historical_repair_audit"),
            ("historical_repair_method", "historical_repair_method"),
            ("full_model_items", "full_model_items"),
            ("actual", "actual_levels"),
        ):
            expected = manifest["artifacts"][artifact_name]
            observed = lineage[lineage_name]
            if dict(observed) != {
                "path": expected["path"],
                "sha256": expected["sha256"],
                "row_count": expected["row_count"],
            }:
                raise _error(
                    f"{path}.{lineage_name}",
                    "path/hash/count differ from immutable manifest",
                )
        if verify_files and run_dir is not None:
            from experiment_a.strict_cf_route_bundle import (
                canonical_formal_binding_inventory,
                canonical_launch_inventory,
            )

            formal_entries, formal_digest = canonical_formal_binding_inventory(
                Path(run_dir), require_all=True
            )
            launch_entries, launch_digest = canonical_launch_inventory(Path(run_dir))
            if lineage["formal_binding_inventory"] != {
                "entry_count": len(formal_entries),
                "sha256": formal_digest,
            }:
                raise _error(f"{path}.formal_binding_inventory", "on-disk inventory mismatch")
            if lineage["launch_inventory"] != {
                "entry_count": len(launch_entries),
                "sha256": launch_digest,
            }:
                raise _error(f"{path}.launch_inventory", "on-disk inventory mismatch")
    return lineage


def validate_finalized_sentinel(
    value: Mapping[str, Any],
    *,
    lineage: Mapping[str, Any] | None = None,
    path: str = "FINALIZED",
) -> Mapping[str, Any]:
    """Validate the exclusive sentinel binding the final lineage bytes."""

    value = _mapping(value, path)
    _exact_keys(
        value,
        {
            "schema",
            "schema_version",
            "lineage_id",
            "finalized_at_utc",
            "lineage_path",
            "lineage_sha256",
        },
        path,
    )
    if value["schema"] != FINALIZED_SCHEMA or value["schema_version"] != SCHEMA_VERSION:
        raise _error(path, "has the wrong schema identifier/version")
    validate_lineage_id(value["lineage_id"], f"{path}.lineage_id")
    _timestamp(value["finalized_at_utc"], f"{path}.finalized_at_utc")
    if value["lineage_path"] != ARTIFACT_SPECS["lineage"][0]:
        raise _error(f"{path}.lineage_path", "must name canonical lineage.json")
    _sha256(value["lineage_sha256"], f"{path}.lineage_sha256")
    if lineage is not None:
        validate_final_lineage(lineage)
        if value["lineage_id"] != lineage["lineage_id"]:
            raise _error(f"{path}.lineage_id", "differs from final lineage")
        if value["finalized_at_utc"] != lineage["finalized_at_utc"]:
            raise _error(f"{path}.finalized_at_utc", "differs from final lineage")
        if value["lineage_sha256"] != canonical_row_sha256(lineage):
            raise _error(f"{path}.lineage_sha256", "does not hash final lineage")
    return value


__all__ = [
    "ACTUAL_METRIC_STATUS",
    "ACTUAL_SOURCE_PROTOCOLS",
    "ARTIFACT_SPECS",
    "COMPRESSORS",
    "CHECKPOINTS_REL",
    "CREATION_CLIENT_ROLES",
    "CREATION_CODE_ROLES",
    "DOMAINS",
    "EXPECTED_DOMAINS",
    "EXPECTED_LEVEL_ROWS",
    "EXPECTED_LEVEL_ROWS_PER_MODEL",
    "EXPECTED_ADOPTED_CALLS_PER_LEVEL",
    "EXPECTED_ADOPTED_CALLS_PER_MODEL",
    "EXPECTED_ADOPTED_CALLS",
    "EXPECTED_SELECTED_SOURCE_HASHES_SHA256",
    "EXPECTED_SELECTED_MODEL_ITEM_PROVENANCE_TIERS",
    "EXPECTED_SELECTED_LEVEL_PROVENANCE_TIERS",
    "EXPECTED_LEVELS",
    "EXPECTED_MODEL_ITEMS",
    "EXPECTED_MODELS",
    "EXPECTED_SOURCE_CLUSTERS",
    "EXPECTED_SOURCES_PER_DOMAIN",
    "LEVEL_MAIN_CALL",
    "LEVELS",
    "LINEAGE_SCHEMA",
    "MAIN_CALL_LABELS",
    "MANIFEST_SCHEMA",
    "MODELS",
    "MODEL_NAMES",
    "MODEL_PROTOCOLS",
    "STRICT_CF_SLOT_CONTRACTS",
    "TRANSPORT_ABI_VERSION",
    "TRANSPORT_ABI_SHA256",
    "MODEL_ITEM_KEYS",
    "HISTORICAL_API821_PROTOCOLS",
    "HISTORICAL_API821_CUTOVER_RELATIVE_PATH",
    "PROVENANCE_TIER_EXACT",
    "PROVENANCE_TIER_HISTORICAL_API821",
    "PROVENANCE_TIER_LEGACY_UNATTESTED",
    "PROVENANCE_TIERS",
    "STRICT_ACTUAL_PROVENANCE_TIERS",
    "PREPARATION_LINEAGE_SCHEMA",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "SCORING_METHOD",
    "SCORING_PROTOCOL_VERSION",
    "SCORING_PROTOCOL",
    "SCORING_PROTOCOL_SHA256",
    "FINALIZED_SCHEMA",
    "FINAL_LINEAGE_SCHEMA",
    "RUN_EVENT_TYPES",
    "RUN_STATES",
    "RUN_STATUS_PATH",
    "RUN_STATUS_SCHEMA",
    "ROUTE_STATES_REL",
    "SELECTION_ALGORITHM",
    "SELECTION_SEED",
    "STATUS_ACTUAL_VALID",
    "STATUS_LEGACY_SHARED_BASELINE_INVALID",
    "STATUS_LEGACY_SHARED_EXCESS_INVALID",
    "STRICT_CF_COUNT",
    "VERIFICATION_TIERS",
    "StrictCFSchemaError",
    "actual_pair_sha256",
    "assert_path_within_run",
    "canonical_runs_root",
    "canonical_digest",
    "canonical_checkpoint_inventory_from_run",
    "canonical_route_state_inventory_from_run",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_row_sha256",
    "cohort_root_preimage",
    "compute_cohort_root",
    "canonical_sha256",
    "counterfactual_pair_sha256",
    "deterministic_selection_rank",
    "file_sha256",
    "level_key",
    "model_item_key",
    "scoring_input_sha256",
    "semantic_key",
    "semantic_level_key",
    "source_cluster_key",
    "strict_scoring_input_sha256",
    "validate_actual_item_provenance",
    "validate_actual_snapshot_row",
    "validate_actual_against_model_item",
    "validate_model_item_row",
    "validate_historical_cutover_manifest_document",
    "validate_run_actual_model_item_bindings",
    "validate_historical_backend_b_call_provenance",
    "validate_historical_backend_b_actual_item_provenance",
    "validate_historical_cutover_attestation",
    "validate_blackbox_row",
    "validate_call_provenance",
    "validate_bound_call_provenance",
    "validate_creation_inventory",
    "validate_final_lineage",
    "validate_finalized_sentinel",
    "validate_item_api_provenance",
    "validate_lineage_id",
    "validate_manifest",
    "validate_run_dir",
    "validate_run_status",
    "validate_strict_source_row",
]
