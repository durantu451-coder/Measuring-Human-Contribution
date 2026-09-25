"""Local matched-CF3 compression/heuristic analysis primitives.

This module deliberately has no checkpoint discovery, API, model, tokenizer, GPU,
or network code.  It accepts only a detached, hash-bound snapshot containing one
actual pair and the ordered first three strict counterfactual pairs per level.
The formal five-CF Experiment-A lineage is not modified or redefined.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from experiment_baseline import cf3_local_primitives as primitive


SCHEMA = "experiment_baseline.cf3_tiny_local"
SCHEMA_VERSION = 1
LEVELS = tuple(primitive.LEVELS)
CF_INDICES = (1, 2, 3)
EVIDENCE_STATES = {"detached_quiescent_copy", "finalized_source"}
EVIDENCE_KINDS = {"checkpoint", "finalized_source"}

CF3_PROTOCOL = {
    "schema": f"{SCHEMA}.protocol",
    "schema_version": SCHEMA_VERSION,
    "counterfactual_indices": list(CF_INDICES),
    "counterfactual_policy": "ordered-prefix-cf1-through-cf3",
    "contrast_name": "shared-CF3 matched contrast",
    "compressors": [
        {"name": "zlib", "level": 9},
        {"name": "bz2", "compresslevel": 9},
        {"name": "lzma", "preset": 9},
    ],
    "compressor_order": list(primitive.COMPRESSORS),
    "separator_utf8": primitive.SEPARATOR.decode("utf-8"),
    "calibration": "max(0, compressed_bits(payload) - compressed_bits(empty))",
    "conditional_bits": "max(0, calibrated(context+separator+target)-calibrated(context+separator))",
    "blackbox_primary": {
        "self_bits": "statistics.fmean(ordered per-compressor calibrated self bits)",
        "conditional_bits": "statistics.fmean(ordered per-compressor conditional bits)",
        "gain_bits": "max(0, self_bits-conditional_bits)",
        "ratio": "clamp(safe_divide(gain_bits,self_bits),0,1)",
    },
    "blackbox_contrast": "actual_ratio - statistics.fmean(cf1,cf2,cf3 ratios)",
    "heuristic_contrast": (
        "feature(actual) - statistics.fmean(feature(cf1),feature(cf2),feature(cf3))"
    ),
    "surface_feature_protocol_version": primitive.FEATURE_PROTOCOL_VERSION,
    "feature_inventory": list(primitive.FEATURES),
    "primary_lexical_features": list(primitive.PRIMARY_LEXICAL_FEATURES),
    "length_features": list(primitive.LENGTH_FEATURES),
    "output_structure_features": list(primitive.OUTPUT_STRUCTURE_FEATURES),
    "compression_derived_diagnostics": list(
        primitive.COMPRESSION_DERIVED_FEATURES
    ),
    "primary_bootstrap_features": list(primitive.PRIMARY_BOOTSTRAP_FEATURES),
    "publication_status": "exploratory-derivative-not-formal-five-cf",
}
CF3_PROTOCOL_SHA256 = primitive.sha256_bytes(primitive.canonical_json_bytes(CF3_PROTOCOL))

INPUT_ROW_KEYS = {
    "schema",
    "schema_version",
    "row_type",
    "wave_id",
    "semantic_key",
    "generation_model",
    "domain",
    "id",
    "source_id",
    "source_index",
    "source_text_sha256",
    "source_cluster",
    "level",
    "source_row_sha256",
    "evidence",
    "actual",
    "counterfactuals",
    "cf3_protocol_sha256",
    "cf3_scoring_input_sha256",
}
PAIR_KEYS = {"prompt", "output", "pair_sha256"}
CF_PAIR_KEYS = {"index", *PAIR_KEYS}
EVIDENCE_KEYS = {"kind", "relative_path", "sha256"}
SNAPSHOT_KEYS = {
    "schema",
    "schema_version",
    "state",
    "snapshot_id",
    "snapshot_root_sha256",
    "wave_id",
    "created_at_utc",
    "evidence_state",
    "campaign",
    "freeze",
    "selection",
    "cohort_roster",
    "formal_inventory",
    "eligibility",
    "rows",
    "counts",
    "cf3_protocol_sha256",
}
CAMPAIGN_KEYS = {
    "lineage_id",
    "manifest_sha256",
    "cohort_root_sha256",
    "expected_level_rows",
}
FREEZE_KEYS = {
    "frozen_at_utc",
    "actual_snapshot_sha256",
    "checkpoint_inventory_sha256",
    "checkpoint_file_count",
    "formal_inventory_sha256",
    "formal_file_count",
    "exporter_execution_sha256",
    "predecessor_manifest_sha256",
    "previous_cumulative_keys_sha256",
}
SELECTION_POLICY = (
    "all newly eligible model-items whose exact five levels each have the "
    "validated contiguous prefix reconstruction+cf1+cf2+cf3 in the frozen inventory"
)
SELECTION_KEYS = {
    "policy",
    "requires_all_five_levels",
    "counterfactual_indices",
    "outcome_blind",
}
ROWS_ARTIFACT_KEYS = {"path", "sha256", "size", "row_count"}
FORMAL_INVENTORY_ENTRY_KEYS = {
    "generation_model",
    "path",
    "sha256",
    "size",
}
ELIGIBILITY_ROW_KEYS = {
    "schema",
    "schema_version",
    "semantic_key",
    "source_row_sha256",
    "state",
    "evidence_relative_path",
    "evidence_sha256",
    "ready_prefix_count",
}
ELIGIBILITY_STATES = {
    "eligible_new_cf3",
    "previously_emitted",
    "ready_in_incomplete_item",
    "not_ready",
}
COUNT_KEYS = {
    "level_rows",
    "model_items",
    "source_clusters",
    "by_model",
    "by_domain",
    "by_model_domain",
}
SCORED_ROW_KEYS = {
    "schema",
    "schema_version",
    "row_type",
    "input_row_sha256",
    "wave_id",
    "semantic_key",
    "generation_model",
    "domain",
    "id",
    "source_id",
    "source_text_sha256",
    "source_cluster",
    "level",
    "blackbox",
    "surface_features",
}


OUTPUT_ARTIFACT_NAMES = {
    "matched_cf3_rows.jsonl",
    "all_ready_summary.json",
    "balanced_core_manifest.json",
    "balanced_core_rows.jsonl",
    "balanced_core_summary.json",
}
OUTPUT_MANIFEST_KEYS = {
    "schema",
    "schema_version",
    "state",
    "created_at_utc",
    "execution_config_sha256",
    "analysis_request",
    "inputs",
    "cf3_protocol",
    "cf3_protocol_sha256",
    "execution_binding",
    "artifacts",
    "claims",
}
OUTPUT_CLAIM_KEYS = {
    "whitebox_strict_scored",
    "external_api_calls",
    "gpu_inference",
    "formal_five_cf_modified",
    "scoring_journal_fsync_per_row",
}


class CF3LocalError(RuntimeError):
    """Raised when an isolated CF3 invariant fails closed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CF3LocalError(
            f"{path}: keys differ; missing={sorted(expected - actual)!r}, "
            f"unexpected={sorted(actual - expected)!r}"
        )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CF3LocalError(f"{path}: expected object")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CF3LocalError(f"{path}: expected nonblank string")
    return value


def _sha256(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CF3LocalError(f"{path}: expected lowercase SHA-256")
    return value


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CF3LocalError(f"{path}: expected integer")
    if minimum is not None and value < minimum:
        raise CF3LocalError(f"{path}: must be >= {minimum}")
    return value


def _safe_relative_path(value: Any, path: str) -> str:
    text = _text(value, path)
    candidate = Path(text)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise CF3LocalError(f"{path}: expected safe relative path")
    return candidate.as_posix()


def _strict_json(data: bytes, path: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CF3LocalError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CF3LocalError(f"{path}: non-finite JSON constant {value!r}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CF3LocalError(f"{path}: invalid strict JSON: {exc}") from exc


def _inside_active_run(path: Path) -> bool:
    parts = tuple(part.lower() for part in path.resolve(strict=False).parts)
    for index in range(len(parts) - 2):
        if (
            parts[index] == "experiment_a"
            and parts[index + 1].startswith("strict_cf")
            and parts[index + 2] == "runs"
        ):
            return True
    return False


def assert_outside_strict_runs(path: Path, *, label: str) -> Path:
    resolved = path.resolve(strict=False)
    if _inside_active_run(resolved):
        raise CF3LocalError(f"{label} must be outside every strict-CF run tree")
    return resolved


def _exclusive_write(path: Path, payload: bytes) -> None:
    """Atomically publish new bytes; an interrupted write never creates *path*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise CF3LocalError(f"refusing to overwrite existing artifact: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("zero-byte write before payload completion")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if path.exists():
            raise CF3LocalError(f"refusing to overwrite existing artifact: {path}")
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_replace_json(path: Path, value: Any) -> None:
    payload = primitive.canonical_jsonl_row_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _actual_pair_hash(prompt: str, output: str) -> str:
    return primitive.actual_pair_sha256(prompt, output)


def cf3_scoring_input_sha256(row: Mapping[str, Any]) -> str:
    counterfactuals = row.get("counterfactuals")
    if not isinstance(counterfactuals, list):
        raise CF3LocalError("row.counterfactuals: expected list")
    return primitive.sha256_bytes(
        primitive.canonical_json_bytes(
            {
                "schema": f"{SCHEMA}.scoring_input",
                "semantic_key": list(row["semantic_key"]),
                "actual_pair_sha256": row["actual"]["pair_sha256"],
                "counterfactual_pair_sha256": [
                    item["pair_sha256"] for item in counterfactuals
                ],
                "cf3_protocol_sha256": CF3_PROTOCOL_SHA256,
            }
        )
    )


def build_input_row(
    *,
    wave_id: str,
    generation_model: str,
    domain: str,
    item_id: str,
    source_id: str,
    source_index: int | None,
    source_text_sha256: str,
    level: str,
    source_row_sha256: str,
    evidence_kind: str,
    evidence_relative_path: str,
    evidence_sha256: str,
    actual_prompt: str,
    actual_output: str,
    counterfactuals: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    """Build one allowlisted row from already validated detached evidence."""

    domain = domain.lower()
    _text(wave_id, "wave_id")
    if len(counterfactuals) != len(CF_INDICES):
        raise CF3LocalError("counterfactuals must be the ordered first three pairs")
    actual_prompt = _text(actual_prompt, "actual_prompt")
    actual_output = _text(actual_output, "actual_output")
    source_hash = _sha256(source_text_sha256, "source_text_sha256")
    semantic_key = [generation_model, domain, item_id, source_hash, level]
    cf_rows = []
    for index, (prompt, output) in zip(CF_INDICES, counterfactuals):
        prompt = _text(prompt, f"counterfactuals[{index - 1}].prompt")
        output = _text(output, f"counterfactuals[{index - 1}].output")
        cf_rows.append(
            {
                "index": index,
                "prompt": prompt,
                "output": output,
                "pair_sha256": primitive.counterfactual_pair_sha256(
                    index, prompt, output
                ),
            }
        )
    row: dict[str, Any] = {
        "schema": f"{SCHEMA}.input_row",
        "schema_version": SCHEMA_VERSION,
        "row_type": "cf3_level",
        "wave_id": wave_id,
        "semantic_key": semantic_key,
        "generation_model": generation_model,
        "domain": domain,
        "id": item_id,
        "source_id": source_id,
        "source_index": source_index,
        "source_text_sha256": source_hash,
        "source_cluster": [domain, source_hash],
        "level": level,
        "source_row_sha256": source_row_sha256,
        "evidence": {
            "kind": evidence_kind,
            "relative_path": evidence_relative_path,
            "sha256": evidence_sha256,
        },
        "actual": {
            "prompt": actual_prompt,
            "output": actual_output,
            "pair_sha256": _actual_pair_hash(actual_prompt, actual_output),
        },
        "counterfactuals": cf_rows,
        "cf3_protocol_sha256": CF3_PROTOCOL_SHA256,
        "cf3_scoring_input_sha256": "",
    }
    row["cf3_scoring_input_sha256"] = cf3_scoring_input_sha256(row)
    return validate_input_row(row)


def validate_input_row(
    row: Mapping[str, Any],
    *,
    seen_keys: set[tuple[str, ...]] | None = None,
    path: str = "input_row",
) -> dict[str, Any]:
    row = _mapping(row, path)
    _exact_keys(row, INPUT_ROW_KEYS, path)
    if (
        row["schema"] != f"{SCHEMA}.input_row"
        or type(row["schema_version"]) is not int
        or row["schema_version"] != SCHEMA_VERSION
        or row["row_type"] != "cf3_level"
    ):
        raise CF3LocalError(f"{path}: schema/version/row_type mismatch")
    _text(row["wave_id"], f"{path}.wave_id")
    model = _text(row["generation_model"], f"{path}.generation_model")
    domain = _text(row["domain"], f"{path}.domain").lower()
    item_id = _text(row["id"], f"{path}.id")
    source_id = _text(row["source_id"], f"{path}.source_id")
    source_index = row["source_index"]
    if source_index is not None:
        _integer(source_index, f"{path}.source_index")
    source_hash = _sha256(row["source_text_sha256"], f"{path}.source_text_sha256")
    level = _text(row["level"], f"{path}.level")
    if model not in primitive.MODELS:
        raise CF3LocalError(f"{path}.generation_model: not in frozen roster")
    if domain not in primitive.DOMAINS or row["domain"] != domain:
        raise CF3LocalError(f"{path}.domain: invalid or not lowercase canonical")
    if level not in LEVELS:
        raise CF3LocalError(f"{path}.level: not in {LEVELS}")
    expected_key = [model, domain, item_id, source_hash, level]
    if row["semantic_key"] != expected_key:
        raise CF3LocalError(f"{path}.semantic_key: identity mismatch")
    if row["source_cluster"] != [domain, source_hash]:
        raise CF3LocalError(f"{path}.source_cluster: identity mismatch")
    _sha256(row["source_row_sha256"], f"{path}.source_row_sha256")

    evidence = _mapping(row["evidence"], f"{path}.evidence")
    _exact_keys(evidence, EVIDENCE_KEYS, f"{path}.evidence")
    if evidence["kind"] not in EVIDENCE_KINDS:
        raise CF3LocalError(f"{path}.evidence.kind: invalid")
    _safe_relative_path(evidence["relative_path"], f"{path}.evidence.relative_path")
    _sha256(evidence["sha256"], f"{path}.evidence.sha256")

    actual = _mapping(row["actual"], f"{path}.actual")
    _exact_keys(actual, PAIR_KEYS, f"{path}.actual")
    actual_prompt = _text(actual["prompt"], f"{path}.actual.prompt")
    actual_output = _text(actual["output"], f"{path}.actual.output")
    if actual["pair_sha256"] != _actual_pair_hash(actual_prompt, actual_output):
        raise CF3LocalError(f"{path}.actual.pair_sha256: mismatch")

    counterfactuals = row["counterfactuals"]
    if not isinstance(counterfactuals, list) or len(counterfactuals) != 3:
        raise CF3LocalError(f"{path}.counterfactuals: must contain exactly three pairs")
    outputs: set[str] = set()
    for position, (entry, expected_index) in enumerate(
        zip(counterfactuals, CF_INDICES)
    ):
        entry_path = f"{path}.counterfactuals[{position}]"
        entry = _mapping(entry, entry_path)
        _exact_keys(entry, CF_PAIR_KEYS, entry_path)
        if type(entry["index"]) is not int or entry["index"] != expected_index:
            raise CF3LocalError(f"{entry_path}.index: must equal {expected_index}")
        prompt = _text(entry["prompt"], f"{entry_path}.prompt")
        output = _text(entry["output"], f"{entry_path}.output")
        if output.strip() in outputs:
            raise CF3LocalError(f"{entry_path}.output: duplicates an earlier CF")
        outputs.add(output.strip())
        expected_hash = primitive.counterfactual_pair_sha256(
            expected_index, prompt, output
        )
        if entry["pair_sha256"] != expected_hash:
            raise CF3LocalError(f"{entry_path}.pair_sha256: mismatch")
    if row["cf3_protocol_sha256"] != CF3_PROTOCOL_SHA256:
        raise CF3LocalError(f"{path}.cf3_protocol_sha256: mismatch")
    expected_input_hash = cf3_scoring_input_sha256(row)
    if row["cf3_scoring_input_sha256"] != expected_input_hash:
        raise CF3LocalError(f"{path}.cf3_scoring_input_sha256: mismatch")
    key = tuple(expected_key)
    if seen_keys is not None:
        if key in seen_keys:
            raise CF3LocalError(f"{path}.semantic_key: duplicate {key!r}")
        seen_keys.add(key)
    return dict(row)


def _item_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["generation_model"]),
        str(row["domain"]),
        str(row["id"]),
        str(row["source_text_sha256"]),
    )


def complete_item_groups(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str, str], tuple[Mapping[str, Any], ...]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, ...]] = set()
    for index, row in enumerate(rows):
        validated = validate_input_row(row, seen_keys=seen, path=f"rows[{index}]")
        grouped[_item_key(validated)].append(validated)
    result: dict[tuple[str, str, str, str], tuple[Mapping[str, Any], ...]] = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda value: LEVELS.index(str(value["level"])))
        observed = [value["level"] for value in ordered]
        if observed != list(LEVELS):
            raise CF3LocalError(
                f"model-item {key!r}: expected one ordered row per L1-L5, got {observed!r}"
            )
        for field in ("wave_id", "source_id", "source_index"):
            values_for_field = {value[field] for value in ordered}
            if len(values_for_field) != 1:
                raise CF3LocalError(
                    f"model-item {key!r}: cross-level {field} mismatch"
                )
        result[key] = tuple(ordered)
    if not result:
        raise CF3LocalError("snapshot contains no complete model-items")
    return dict(sorted(result.items()))


def snapshot_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = complete_item_groups(rows)
    by_model: dict[str, int] = defaultdict(int)
    by_domain: dict[str, int] = defaultdict(int)
    by_model_domain: dict[str, int] = defaultdict(int)
    clusters: set[tuple[str, str]] = set()
    for key in groups:
        model, domain, _, source_hash = key
        by_model[model] += 1
        by_domain[domain] += 1
        by_model_domain[f"{model}\0{domain}"] += 1
        clusters.add((domain, source_hash))
    return {
        "level_rows": len(rows),
        "model_items": len(groups),
        "source_clusters": len(clusters),
        "by_model": dict(sorted(by_model.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "by_model_domain": dict(sorted(by_model_domain.items())),
    }


def cumulative_keys_sha256(keys: Sequence[Sequence[str]]) -> str:
    return primitive.sha256_bytes(
        primitive.canonical_json_bytes(sorted([list(key) for key in keys]))
    )


def build_eligibility_row(
    *,
    semantic_key: Sequence[str],
    source_row_sha256: str,
    state: str,
    evidence_relative_path: str,
    evidence_sha256: str | None,
    ready_prefix_count: int,
) -> dict[str, Any]:
    row = {
        "schema": f"{SCHEMA}.eligibility_row",
        "schema_version": SCHEMA_VERSION,
        "semantic_key": list(semantic_key),
        "source_row_sha256": source_row_sha256,
        "state": state,
        "evidence_relative_path": evidence_relative_path,
        "evidence_sha256": evidence_sha256,
        "ready_prefix_count": ready_prefix_count,
    }
    return validate_eligibility_row(row)


def validate_eligibility_row(
    value: Mapping[str, Any], *, path: str = "eligibility_row"
) -> dict[str, Any]:
    value = _mapping(value, path)
    _exact_keys(value, ELIGIBILITY_ROW_KEYS, path)
    if (
        value["schema"] != f"{SCHEMA}.eligibility_row"
        or type(value["schema_version"]) is not int
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise CF3LocalError(f"{path}: schema mismatch")
    key = value["semantic_key"]
    if not isinstance(key, list) or len(key) != 5:
        raise CF3LocalError(f"{path}.semantic_key: expected five components")
    model = _text(key[0], f"{path}.semantic_key[0]")
    domain = _text(key[1], f"{path}.semantic_key[1]")
    _text(key[2], f"{path}.semantic_key[2]")
    _sha256(key[3], f"{path}.semantic_key[3]")
    level = _text(key[4], f"{path}.semantic_key[4]")
    if model not in primitive.MODELS or domain not in primitive.DOMAINS or level not in LEVELS:
        raise CF3LocalError(f"{path}.semantic_key: outside frozen roster")
    _sha256(value["source_row_sha256"], f"{path}.source_row_sha256")
    state = value["state"]
    if state not in ELIGIBILITY_STATES:
        raise CF3LocalError(f"{path}.state: invalid")
    _safe_relative_path(
        value["evidence_relative_path"], f"{path}.evidence_relative_path"
    )
    evidence_hash = value["evidence_sha256"]
    if evidence_hash is not None:
        _sha256(evidence_hash, f"{path}.evidence_sha256")
    prefix = _integer(
        value["ready_prefix_count"], f"{path}.ready_prefix_count", minimum=0
    )
    if prefix > 5:
        raise CF3LocalError(f"{path}.ready_prefix_count: must be <= 5")
    if state in {"eligible_new_cf3", "previously_emitted", "ready_in_incomplete_item"}:
        if prefix < 3 or evidence_hash is None:
            raise CF3LocalError(f"{path}: ready state requires prefix >=3 and evidence hash")
    elif prefix >= 3:
        raise CF3LocalError(f"{path}: not_ready must have prefix <3")
    return dict(value)


def _validate_eligibility_ledger(
    values: Sequence[Mapping[str, Any]],
    *,
    expected_level_rows: int,
    selected_rows: Sequence[Mapping[str, Any]],
    path: str = "eligibility",
) -> tuple[list[dict[str, Any]], set[tuple[str, ...]], set[tuple[str, ...]]]:
    if len(values) != expected_level_rows:
        raise CF3LocalError(
            f"{path}: {len(values)} rows != campaign expected {expected_level_rows}"
        )
    ledger: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    by_item: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for index, raw in enumerate(values):
        row = validate_eligibility_row(raw, path=f"{path}[{index}]")
        key = tuple(row["semantic_key"])
        if key in seen:
            raise CF3LocalError(f"{path}[{index}]: duplicate semantic key {key!r}")
        seen.add(key)
        by_item[key[:-1]].append(row)
        ledger.append(row)
    for item_key, item_rows in by_item.items():
        ordered = sorted(item_rows, key=lambda row: LEVELS.index(row["semantic_key"][-1]))
        if [row["semantic_key"][-1] for row in ordered] != list(LEVELS):
            raise CF3LocalError(f"{path}: item {item_key!r} lacks exact L1-L5 ledger")
        prefixes = [row["ready_prefix_count"] for row in ordered]
        states = [row["state"] for row in ordered]
        if all(prefix >= 3 for prefix in prefixes):
            allowed = {"eligible_new_cf3"} if states[0] == "eligible_new_cf3" else {"previously_emitted"}
            if set(states) != allowed:
                raise CF3LocalError(
                    f"{path}: fully ready item {item_key!r} must be wholly new or previous"
                )
        else:
            expected_states = [
                "ready_in_incomplete_item" if prefix >= 3 else "not_ready"
                for prefix in prefixes
            ]
            if states != expected_states:
                raise CF3LocalError(
                    f"{path}: incomplete item {item_key!r} readiness classification mismatch"
                )
    selected_by_key = {tuple(row["semantic_key"]): row for row in selected_rows}
    eligible = {
        tuple(row["semantic_key"])
        for row in ledger
        if row["state"] == "eligible_new_cf3"
    }
    previous = {
        tuple(row["semantic_key"])
        for row in ledger
        if row["state"] == "previously_emitted"
    }
    if set(selected_by_key) != eligible:
        raise CF3LocalError(
            f"{path}: selected rows do not exactly equal newly eligible ledger keys"
        )
    for row in ledger:
        key = tuple(row["semantic_key"])
        selected = selected_by_key.get(key)
        if selected is None:
            continue
        if row["source_row_sha256"] != selected["source_row_sha256"]:
            raise CF3LocalError(f"{path}: source-row hash mismatch for selected key {key!r}")
        evidence = selected["evidence"]
        if (
            row["evidence_relative_path"] != evidence["relative_path"]
            or row["evidence_sha256"] != evidence["sha256"]
        ):
            raise CF3LocalError(f"{path}: evidence mismatch for selected key {key!r}")
    return sorted(ledger, key=lambda row: tuple(row["semantic_key"])), eligible, previous


def _validate_freeze(value: Mapping[str, Any], *, path: str = "freeze") -> dict[str, Any]:
    value = _mapping(value, path)
    _exact_keys(value, FREEZE_KEYS, path)
    _text(value["frozen_at_utc"], f"{path}.frozen_at_utc")
    for name in (
        "actual_snapshot_sha256",
        "checkpoint_inventory_sha256",
        "formal_inventory_sha256",
        "exporter_execution_sha256",
        "previous_cumulative_keys_sha256",
    ):
        _sha256(value[name], f"{path}.{name}")
    _integer(value["checkpoint_file_count"], f"{path}.checkpoint_file_count", minimum=0)
    _integer(value["formal_file_count"], f"{path}.formal_file_count", minimum=0)
    predecessor = value["predecessor_manifest_sha256"]
    if predecessor is not None:
        _sha256(predecessor, f"{path}.predecessor_manifest_sha256")
    return dict(value)


def _validate_formal_inventory_entries(
    values: Sequence[Mapping[str, Any]],
    *,
    path: str = "formal_inventory",
) -> list[dict[str, Any]]:
    result = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(values):
        entry_path = f"{path}[{index}]"
        entry = _mapping(raw, entry_path)
        _exact_keys(entry, FORMAL_INVENTORY_ENTRY_KEYS, entry_path)
        model = _text(entry["generation_model"], f"{entry_path}.generation_model")
        if model not in primitive.MODELS:
            raise CF3LocalError(f"{entry_path}.generation_model: outside roster")
        relative = _safe_relative_path(entry["path"], f"{entry_path}.path")
        if relative in seen_paths:
            raise CF3LocalError(f"{entry_path}.path: duplicate")
        seen_paths.add(relative)
        _sha256(entry["sha256"], f"{entry_path}.sha256")
        _integer(entry["size"], f"{entry_path}.size", minimum=1)
        result.append(dict(entry))
    ordered = sorted(result, key=lambda entry: entry["path"])
    if result != ordered:
        raise CF3LocalError(f"{path}: entries must be in canonical path order")
    return ordered


def formal_inventory_model_roots(
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    validated = _validate_formal_inventory_entries(entries)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in validated:
        grouped[entry["generation_model"]].append(entry)
    return {
        model: primitive.canonical_sha256(values)
        for model, values in sorted(grouped.items())
    }


def _snapshot_root_preimage(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key != "snapshot_root_sha256"
    }


def create_snapshot_bundle(
    output_dir: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    snapshot_id: str,
    wave_id: str,
    evidence_state: str,
    campaign: Mapping[str, Any],
    freeze: Mapping[str, Any],
    formal_inventory_entries: Sequence[Mapping[str, Any]],
    eligibility_rows: Sequence[Mapping[str, Any]],
) -> Path:
    """Write a detached snapshot from rows validated by an external safe exporter."""

    if _inside_active_run(output_dir):
        raise CF3LocalError("snapshot output must be outside any strict-CF run")
    if evidence_state not in EVIDENCE_STATES:
        raise CF3LocalError(f"unsupported evidence_state: {evidence_state!r}")
    _text(snapshot_id, "snapshot_id")
    _text(wave_id, "wave_id")
    campaign = _mapping(campaign, "campaign")
    _exact_keys(campaign, CAMPAIGN_KEYS, "campaign")
    _text(campaign["lineage_id"], "campaign.lineage_id")
    _sha256(campaign["manifest_sha256"], "campaign.manifest_sha256")
    _sha256(campaign["cohort_root_sha256"], "campaign.cohort_root_sha256")
    expected_level_rows = _integer(
        campaign["expected_level_rows"],
        "campaign.expected_level_rows",
        minimum=5,
    )
    freeze = _validate_freeze(freeze)
    formal_inventory = _validate_formal_inventory_entries(formal_inventory_entries)
    formal_payload = b"".join(
        primitive.canonical_jsonl_row_bytes(entry) for entry in formal_inventory
    )
    formal_hash = primitive.sha256_bytes(formal_payload)
    if (
        formal_hash != freeze["formal_inventory_sha256"]
        or len(formal_inventory) != freeze["formal_file_count"]
    ):
        raise CF3LocalError("formal inventory differs from frozen attestation")

    ordered = sorted(
        (validate_input_row(row, path=f"rows[{index}]") for index, row in enumerate(rows)),
        key=lambda row: tuple(row["semantic_key"]),
    )
    if any(row["wave_id"] != wave_id for row in ordered):
        raise CF3LocalError("all input rows must match the bundle wave_id")
    counts = snapshot_counts(ordered)
    ledger, _, previous = _validate_eligibility_ledger(
        eligibility_rows,
        expected_level_rows=expected_level_rows,
        selected_rows=ordered,
    )
    if freeze["previous_cumulative_keys_sha256"] != cumulative_keys_sha256(
        sorted(previous)
    ):
        raise CF3LocalError("freeze previous cumulative key root differs from ledger")
    predecessor = freeze["predecessor_manifest_sha256"]
    if (predecessor is None) != (not previous):
        raise CF3LocalError(
            "first wave must have no predecessor/previous rows; later waves require both"
        )

    formal_name = "formal_inventory.jsonl"
    _exclusive_write(output_dir / formal_name, formal_payload)
    formal_artifact = {
        "path": formal_name,
        "sha256": formal_hash,
        "size": len(formal_payload),
        "row_count": len(formal_inventory),
    }

    roster_rows = [
        {
            "semantic_key": list(row["semantic_key"]),
            "source_row_sha256": row["source_row_sha256"],
        }
        for row in ledger
    ]
    roster_payload = b"".join(
        primitive.canonical_jsonl_row_bytes(row) for row in roster_rows
    )
    roster_name = "cohort_roster.jsonl"
    _exclusive_write(output_dir / roster_name, roster_payload)
    roster_artifact = {
        "path": roster_name,
        "sha256": primitive.sha256_bytes(roster_payload),
        "size": len(roster_payload),
        "row_count": len(roster_rows),
    }

    eligibility_payload = b"".join(
        primitive.canonical_jsonl_row_bytes(row) for row in ledger
    )
    eligibility_name = "eligibility_ledger.jsonl"
    _exclusive_write(output_dir / eligibility_name, eligibility_payload)
    eligibility_artifact = {
        "path": eligibility_name,
        "sha256": primitive.sha256_bytes(eligibility_payload),
        "size": len(eligibility_payload),
        "row_count": len(ledger),
    }

    rows_payload = b"".join(primitive.canonical_jsonl_row_bytes(row) for row in ordered)
    rows_name = "cf3_input_rows.jsonl"
    rows_path = output_dir / rows_name
    _exclusive_write(rows_path, rows_payload)
    rows_artifact = {
        "path": rows_name,
        "sha256": primitive.sha256_bytes(rows_payload),
        "size": len(rows_payload),
        "row_count": len(ordered),
    }
    manifest = {
        "schema": f"{SCHEMA}.snapshot_manifest",
        "schema_version": SCHEMA_VERSION,
        "state": "complete",
        "snapshot_id": snapshot_id,
        "snapshot_root_sha256": "",
        "wave_id": wave_id,
        "created_at_utc": utc_now(),
        "evidence_state": evidence_state,
        "campaign": dict(campaign),
        "freeze": dict(freeze),
        "selection": {
            "policy": SELECTION_POLICY,
            "requires_all_five_levels": True,
            "counterfactual_indices": list(CF_INDICES),
            "outcome_blind": True,
        },
        "cohort_roster": roster_artifact,
        "formal_inventory": formal_artifact,
        "eligibility": eligibility_artifact,
        "rows": rows_artifact,
        "counts": counts,
        "cf3_protocol_sha256": CF3_PROTOCOL_SHA256,
    }
    manifest["snapshot_root_sha256"] = primitive.canonical_sha256(
        _snapshot_root_preimage(manifest)
    )
    manifest_path = output_dir / "snapshot_manifest.json"
    _exclusive_write(
        manifest_path,
        primitive.canonical_jsonl_row_bytes(manifest),
    )
    return manifest_path


def validate_snapshot_manifest(value: Mapping[str, Any], *, path: str) -> dict[str, Any]:
    value = _mapping(value, path)
    _exact_keys(value, SNAPSHOT_KEYS, path)
    if (
        value["schema"] != f"{SCHEMA}.snapshot_manifest"
        or type(value["schema_version"]) is not int
        or value["schema_version"] != SCHEMA_VERSION
        or value["state"] != "complete"
    ):
        raise CF3LocalError(f"{path}: schema/version/state mismatch")
    _text(value["snapshot_id"], f"{path}.snapshot_id")
    _sha256(value["snapshot_root_sha256"], f"{path}.snapshot_root_sha256")
    _text(value["wave_id"], f"{path}.wave_id")
    _text(value["created_at_utc"], f"{path}.created_at_utc")
    if value["evidence_state"] not in EVIDENCE_STATES:
        raise CF3LocalError(f"{path}.evidence_state: live evidence is forbidden")
    campaign = _mapping(value["campaign"], f"{path}.campaign")
    _exact_keys(campaign, CAMPAIGN_KEYS, f"{path}.campaign")
    _text(campaign["lineage_id"], f"{path}.campaign.lineage_id")
    _sha256(campaign["manifest_sha256"], f"{path}.campaign.manifest_sha256")
    _sha256(campaign["cohort_root_sha256"], f"{path}.campaign.cohort_root_sha256")
    _integer(
        campaign["expected_level_rows"],
        f"{path}.campaign.expected_level_rows",
        minimum=5,
    )
    _validate_freeze(value["freeze"], path=f"{path}.freeze")
    selection = _mapping(value["selection"], f"{path}.selection")
    _exact_keys(selection, SELECTION_KEYS, f"{path}.selection")
    if (
        selection["policy"] != SELECTION_POLICY
        or selection["requires_all_five_levels"] is not True
        or selection["counterfactual_indices"] != list(CF_INDICES)
        or selection["outcome_blind"] is not True
    ):
        raise CF3LocalError(f"{path}.selection: not the frozen CF3 policy")
    roster = _mapping(value["cohort_roster"], f"{path}.cohort_roster")
    _exact_keys(roster, ROWS_ARTIFACT_KEYS, f"{path}.cohort_roster")
    _safe_relative_path(roster["path"], f"{path}.cohort_roster.path")
    _sha256(roster["sha256"], f"{path}.cohort_roster.sha256")
    _integer(roster["size"], f"{path}.cohort_roster.size", minimum=1)
    _integer(roster["row_count"], f"{path}.cohort_roster.row_count", minimum=5)
    formal = _mapping(value["formal_inventory"], f"{path}.formal_inventory")
    _exact_keys(formal, ROWS_ARTIFACT_KEYS, f"{path}.formal_inventory")
    _safe_relative_path(formal["path"], f"{path}.formal_inventory.path")
    _sha256(formal["sha256"], f"{path}.formal_inventory.sha256")
    _integer(formal["size"], f"{path}.formal_inventory.size", minimum=1)
    _integer(formal["row_count"], f"{path}.formal_inventory.row_count", minimum=1)
    eligibility = _mapping(value["eligibility"], f"{path}.eligibility")
    _exact_keys(eligibility, ROWS_ARTIFACT_KEYS, f"{path}.eligibility")
    _safe_relative_path(eligibility["path"], f"{path}.eligibility.path")
    _sha256(eligibility["sha256"], f"{path}.eligibility.sha256")
    _integer(eligibility["size"], f"{path}.eligibility.size", minimum=1)
    _integer(
        eligibility["row_count"], f"{path}.eligibility.row_count", minimum=5
    )
    rows = _mapping(value["rows"], f"{path}.rows")
    _exact_keys(rows, ROWS_ARTIFACT_KEYS, f"{path}.rows")
    _safe_relative_path(rows["path"], f"{path}.rows.path")
    _sha256(rows["sha256"], f"{path}.rows.sha256")
    _integer(rows["size"], f"{path}.rows.size", minimum=1)
    _integer(rows["row_count"], f"{path}.rows.row_count", minimum=5)
    counts = _mapping(value["counts"], f"{path}.counts")
    _exact_keys(counts, COUNT_KEYS, f"{path}.counts")
    for name in ("level_rows", "model_items", "source_clusters"):
        _integer(counts[name], f"{path}.counts.{name}", minimum=1)
    for name in ("by_model", "by_domain", "by_model_domain"):
        if not isinstance(counts[name], Mapping):
            raise CF3LocalError(f"{path}.counts.{name}: expected mapping")
    if value["cf3_protocol_sha256"] != CF3_PROTOCOL_SHA256:
        raise CF3LocalError(f"{path}.cf3_protocol_sha256: mismatch")
    expected_root = primitive.canonical_sha256(_snapshot_root_preimage(value))
    if value["snapshot_root_sha256"] != expected_root:
        raise CF3LocalError(f"{path}.snapshot_root_sha256: mismatch")
    return dict(value)


def _read_bound_artifact(
    manifest_path: Path,
    artifact: Mapping[str, Any],
    *,
    label: str,
) -> tuple[Path, bytes]:
    artifact_path = (manifest_path.parent / artifact["path"]).resolve(strict=True)
    try:
        artifact_path.relative_to(manifest_path.parent)
    except ValueError as exc:
        raise CF3LocalError(f"{label} path escapes its detached directory") from exc
    payload = artifact_path.read_bytes()
    if len(payload) != artifact["size"]:
        raise CF3LocalError(f"{label} size drift")
    if primitive.sha256_bytes(payload) != artifact["sha256"]:
        raise CF3LocalError(f"{label} hash drift")
    if not payload.endswith(b"\n"):
        raise CF3LocalError(f"{label} must end with LF")
    return artifact_path, payload


def _load_formal_inventory(
    manifest_path: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    formal_path, payload = _read_bound_artifact(
        manifest_path, manifest["formal_inventory"], label="formal inventory"
    )
    entries = [
        _strict_json(raw, f"{formal_path}:{line_number}")
        for line_number, raw in enumerate(payload.splitlines(), 1)
        if raw
    ]
    validated = _validate_formal_inventory_entries(
        entries, path=str(formal_path)
    )
    if len(validated) != manifest["formal_inventory"]["row_count"]:
        raise CF3LocalError("formal inventory row count drift")
    freeze = manifest["freeze"]
    if (
        manifest["formal_inventory"]["sha256"]
        != freeze["formal_inventory_sha256"]
        or len(validated) != freeze["formal_file_count"]
    ):
        raise CF3LocalError("formal inventory differs from freeze attestation")
    return validated


def _load_cohort_roster(
    manifest_path: Path,
    manifest: Mapping[str, Any],
) -> dict[tuple[str, ...], str]:
    roster_path, payload = _read_bound_artifact(
        manifest_path, manifest["cohort_roster"], label="cohort roster"
    )
    result: dict[tuple[str, ...], str] = {}
    ordered_keys: list[tuple[str, ...]] = []
    for line_number, raw in enumerate(payload.splitlines(), 1):
        value = _strict_json(raw, f"{roster_path}:{line_number}")
        value = _mapping(value, f"{roster_path}:{line_number}")
        _exact_keys(
            value,
            {"semantic_key", "source_row_sha256"},
            f"{roster_path}:{line_number}",
        )
        eligibility_projection = build_eligibility_row(
            semantic_key=value["semantic_key"],
            source_row_sha256=value["source_row_sha256"],
            state="not_ready",
            evidence_relative_path="checkpoints/placeholder.json",
            evidence_sha256=None,
            ready_prefix_count=0,
        )
        key = tuple(eligibility_projection["semantic_key"])
        if key in result:
            raise CF3LocalError(f"cohort roster duplicates semantic key {key!r}")
        result[key] = eligibility_projection["source_row_sha256"]
        ordered_keys.append(key)
    if len(result) != manifest["cohort_roster"]["row_count"]:
        raise CF3LocalError("cohort roster row count drift")
    if ordered_keys != sorted(ordered_keys):
        raise CF3LocalError("cohort roster is not in canonical semantic-key order")
    return result


def _load_eligibility_ledger(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    selected_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], set[tuple[str, ...]], set[tuple[str, ...]]]:
    ledger_path, payload = _read_bound_artifact(
        manifest_path, manifest["eligibility"], label="eligibility ledger"
    )
    values = [
        _strict_json(raw, f"{ledger_path}:{index}")
        for index, raw in enumerate(payload.splitlines(), 1)
        if raw
    ]
    if len(values) != manifest["eligibility"]["row_count"]:
        raise CF3LocalError("eligibility ledger row count drift")
    return _validate_eligibility_ledger(
        values,
        expected_level_rows=manifest["campaign"]["expected_level_rows"],
        selected_rows=selected_rows,
        path=str(ledger_path),
    )


def load_snapshot(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = manifest_path.resolve(strict=True)
    if _inside_active_run(manifest_path):
        raise CF3LocalError("refusing to analyze an input manifest inside the active run")
    manifest = validate_snapshot_manifest(
        _strict_json(manifest_path.read_bytes(), str(manifest_path)),
        path=str(manifest_path),
    )
    rows_path = (manifest_path.parent / manifest["rows"]["path"]).resolve(strict=True)
    try:
        rows_path.relative_to(manifest_path.parent)
    except ValueError as exc:
        raise CF3LocalError("snapshot rows path escapes its detached directory") from exc
    payload = rows_path.read_bytes()
    if len(payload) != manifest["rows"]["size"]:
        raise CF3LocalError("snapshot rows size drift")
    if primitive.sha256_bytes(payload) != manifest["rows"]["sha256"]:
        raise CF3LocalError("snapshot rows hash drift")
    if not payload.endswith(b"\n"):
        raise CF3LocalError("snapshot rows must end with LF")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for line_number, raw in enumerate(payload.splitlines(), 1):
        if not raw:
            raise CF3LocalError(f"snapshot rows line {line_number}: blank")
        row = validate_input_row(
            _strict_json(raw, f"{rows_path}:{line_number}"),
            seen_keys=seen,
            path=f"{rows_path}:{line_number}",
        )
        if row["wave_id"] != manifest["wave_id"]:
            raise CF3LocalError(f"snapshot row {line_number}: wave mismatch")
        rows.append(row)
    if len(rows) != manifest["rows"]["row_count"]:
        raise CF3LocalError("snapshot row count drift")
    observed_counts = snapshot_counts(rows)
    if observed_counts != manifest["counts"]:
        raise CF3LocalError("snapshot count inventory drift")
    _load_formal_inventory(manifest_path, manifest)
    roster = _load_cohort_roster(manifest_path, manifest)
    ledger, _, previous = _load_eligibility_ledger(manifest_path, manifest, rows)
    ledger_roster = {
        tuple(row["semantic_key"]): row["source_row_sha256"] for row in ledger
    }
    if roster != ledger_roster:
        raise CF3LocalError("eligibility ledger differs from immutable cohort roster")
    freeze = manifest["freeze"]
    if freeze["previous_cumulative_keys_sha256"] != cumulative_keys_sha256(
        sorted(previous)
    ):
        raise CF3LocalError("snapshot previous cumulative key root mismatch")
    predecessor = freeze["predecessor_manifest_sha256"]
    if (predecessor is None) != (not previous):
        raise CF3LocalError("snapshot predecessor/previous-row state mismatch")
    return manifest, rows


def load_snapshots(
    manifest_paths: Sequence[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load disjoint immutable waves and reject campaign/key drift."""

    if not manifest_paths:
        raise CF3LocalError("at least one input snapshot manifest is required")
    manifests: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, ...]] = set()
    seen_waves: set[str] = set()
    seen_formal: dict[str, dict[str, Any]] = {}
    campaign: Mapping[str, Any] | None = None
    predecessor_manifest_hash: str | None = None
    for manifest_path in manifest_paths:
        manifest_path = manifest_path.resolve(strict=True)
        manifest, wave_rows = load_snapshot(manifest_path)
        if campaign is None:
            campaign = manifest["campaign"]
        elif manifest["campaign"] != campaign:
            raise CF3LocalError("input snapshot waves bind different campaigns")
        if manifest["wave_id"] in seen_waves:
            raise CF3LocalError(f"duplicate input wave_id {manifest['wave_id']!r}")
        seen_waves.add(manifest["wave_id"])
        _, _, previous = _load_eligibility_ledger(
            manifest_path, manifest, wave_rows
        )
        if previous != seen_keys:
            raise CF3LocalError(
                "wave eligibility ledger previous-emitted keys do not equal prior waves"
            )
        if manifest["freeze"]["predecessor_manifest_sha256"] != predecessor_manifest_hash:
            raise CF3LocalError("snapshot predecessor manifest chain mismatch")
        current_formal = {
            entry["path"]: entry
            for entry in _load_formal_inventory(manifest_path, manifest)
        }
        for path, previous_entry in seen_formal.items():
            if current_formal.get(path) != previous_entry:
                raise CF3LocalError(
                    f"formal evidence changed or disappeared across waves: {path}"
                )
        seen_formal = current_formal
        for row in wave_rows:
            key = tuple(row["semantic_key"])
            if key in seen_keys:
                raise CF3LocalError(
                    f"semantic key repeats across snapshot waves: {key!r}"
                )
            seen_keys.add(key)
            rows.append(row)
        predecessor_manifest_hash = primitive.file_sha256(manifest_path)
        manifests.append(manifest)
    complete_item_groups(rows)
    return manifests, sorted(rows, key=lambda row: tuple(row["semantic_key"]))


def score_input_row(row: Mapping[str, Any]) -> dict[str, Any]:
    row = validate_input_row(row)
    pair_values = [row["actual"], *row["counterfactuals"]]
    profiles = [
        primitive.information_gain_profile(
            pair["prompt"], pair["output"], primitive.COMPRESSORS
        )
        for pair in pair_values
    ]
    feature_vectors = [
        primitive.compute_surface_features(
            pair["prompt"],
            pair["output"],
            output_self_bits=profile.aggregate.self_information_bits,
        )
        for pair, profile in zip(pair_values, profiles)
    ]
    actual_profile = profiles[0]
    cf_profiles = profiles[1:]
    actual_ratio = float(actual_profile.aggregate.contribution_ratio)
    cf_ratios = [float(profile.aggregate.contribution_ratio) for profile in cf_profiles]
    cf_mean = float(statistics.fmean(cf_ratios))

    per_compressor: dict[str, Any] = {}
    for compressor in ("zlib", "bz2", "lzma"):
        actual_value = float(
            actual_profile.per_compressor[compressor]["contribution_ratio"]
        )
        cf_values = [
            float(profile.per_compressor[compressor]["contribution_ratio"])
            for profile in cf_profiles
        ]
        mean_value = float(statistics.fmean(cf_values))
        per_compressor[compressor] = {
            "actual": actual_value,
            "counterfactuals": cf_values,
            "cf_mean": mean_value,
            "shared_cf3_contrast": actual_value - mean_value,
        }

    actual_features = feature_vectors[0]
    cf_features = feature_vectors[1:]
    feature_means = {
        name: float(statistics.fmean(values[name] for values in cf_features))
        for name in primitive.FEATURES
    }
    shared_cf3_contrast_features = {
        name: float(actual_features[name] - feature_means[name])
        for name in primitive.FEATURES
    }
    result = {
        "schema": f"{SCHEMA}.scored_row",
        "schema_version": SCHEMA_VERSION,
        "row_type": "matched_cf3_level",
        "input_row_sha256": primitive.canonical_row_sha256(row),
        "wave_id": row["wave_id"],
        "semantic_key": list(row["semantic_key"]),
        "generation_model": row["generation_model"],
        "domain": row["domain"],
        "id": row["id"],
        "source_id": row["source_id"],
        "source_text_sha256": row["source_text_sha256"],
        "source_cluster": list(row["source_cluster"]),
        "level": row["level"],
        "blackbox": {
            "actual": actual_ratio,
            "counterfactuals": cf_ratios,
            "cf_mean": cf_mean,
            "shared_cf3_contrast": actual_ratio - cf_mean,
            "per_compressor_diagnostic": per_compressor,
        },
        "surface_features": {
            "actual": dict(actual_features),
            "counterfactuals": [dict(values) for values in cf_features],
            "cf_mean": feature_means,
            "shared_cf3_contrast": shared_cf3_contrast_features,
        },
    }
    return validate_scored_row(result)


def validate_scored_row(value: Mapping[str, Any], *, path: str = "scored_row") -> dict[str, Any]:
    value = _mapping(value, path)
    _exact_keys(value, SCORED_ROW_KEYS, path)
    if (
        value["schema"] != f"{SCHEMA}.scored_row"
        or type(value["schema_version"]) is not int
        or value["schema_version"] != SCHEMA_VERSION
        or value["row_type"] != "matched_cf3_level"
    ):
        raise CF3LocalError(f"{path}: schema mismatch")
    _sha256(value["input_row_sha256"], f"{path}.input_row_sha256")
    _text(value["wave_id"], f"{path}.wave_id")
    model = _text(value["generation_model"], f"{path}.generation_model")
    domain = _text(value["domain"], f"{path}.domain")
    item_id = _text(value["id"], f"{path}.id")
    _text(value["source_id"], f"{path}.source_id")
    source_hash = _sha256(
        value["source_text_sha256"], f"{path}.source_text_sha256"
    )
    level = _text(value["level"], f"{path}.level")
    if model not in primitive.MODELS or domain not in primitive.DOMAINS or level not in LEVELS:
        raise CF3LocalError(f"{path}: identity is outside the frozen roster")
    expected_key = [model, domain, item_id, source_hash, level]
    if value["semantic_key"] != expected_key:
        raise CF3LocalError(f"{path}.semantic_key: mismatch")
    if value["source_cluster"] != [domain, source_hash]:
        raise CF3LocalError(f"{path}.source_cluster: mismatch")
    blackbox = _mapping(value["blackbox"], f"{path}.blackbox")
    if set(blackbox) != {
        "actual",
        "counterfactuals",
        "cf_mean",
        "shared_cf3_contrast",
        "per_compressor_diagnostic",
    }:
        raise CF3LocalError(f"{path}.blackbox: key mismatch")
    cf_values = blackbox["counterfactuals"]
    if not isinstance(cf_values, list) or len(cf_values) != 3:
        raise CF3LocalError(f"{path}.blackbox.counterfactuals: expected three")
    numeric = [
        blackbox["actual"],
        *cf_values,
        blackbox["cf_mean"],
        blackbox["shared_cf3_contrast"],
    ]
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for item in numeric
    ):
        raise CF3LocalError(f"{path}.blackbox: non-finite numeric value")
    if any(not 0.0 <= float(item) <= 1.0 for item in numeric[:-1]):
        raise CF3LocalError(f"{path}.blackbox: ratio outside [0,1]")
    if not -1.0 <= float(blackbox["shared_cf3_contrast"]) <= 1.0:
        raise CF3LocalError(f"{path}.blackbox: contrast outside [-1,1]")
    expected_mean = statistics.fmean(float(item) for item in cf_values)
    if blackbox["cf_mean"] != expected_mean:
        raise CF3LocalError(f"{path}.blackbox.cf_mean: exact fmean mismatch")
    if blackbox["shared_cf3_contrast"] != blackbox["actual"] - expected_mean:
        raise CF3LocalError(f"{path}.blackbox.shared_cf3_contrast: arithmetic mismatch")
    diagnostics = _mapping(
        blackbox["per_compressor_diagnostic"],
        f"{path}.blackbox.per_compressor_diagnostic",
    )
    if set(diagnostics) != set(primitive.COMPRESSORS):
        raise CF3LocalError(f"{path}.blackbox.per_compressor_diagnostic: mismatch")
    for compressor in primitive.COMPRESSORS:
        diagnostic_path = f"{path}.blackbox.per_compressor_diagnostic.{compressor}"
        diagnostic = _mapping(diagnostics[compressor], diagnostic_path)
        _exact_keys(
            diagnostic,
            {"actual", "counterfactuals", "cf_mean", "shared_cf3_contrast"},
            diagnostic_path,
        )
        diagnostic_cfs = diagnostic["counterfactuals"]
        if not isinstance(diagnostic_cfs, list) or len(diagnostic_cfs) != 3:
            raise CF3LocalError(f"{diagnostic_path}.counterfactuals: expected three")
        diagnostic_values = [
            diagnostic["actual"],
            *diagnostic_cfs,
            diagnostic["cf_mean"],
            diagnostic["shared_cf3_contrast"],
        ]
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            for item in diagnostic_values
        ):
            raise CF3LocalError(f"{diagnostic_path}: non-finite numeric value")
        if any(not 0.0 <= float(item) <= 1.0 for item in diagnostic_values[:-1]):
            raise CF3LocalError(f"{diagnostic_path}: ratio outside [0,1]")
        diagnostic_mean = statistics.fmean(float(item) for item in diagnostic_cfs)
        if diagnostic["cf_mean"] != diagnostic_mean:
            raise CF3LocalError(f"{diagnostic_path}.cf_mean: exact fmean mismatch")
        if diagnostic["shared_cf3_contrast"] != diagnostic["actual"] - diagnostic_mean:
            raise CF3LocalError(f"{diagnostic_path}.shared_cf3_contrast: mismatch")

    features = _mapping(value["surface_features"], f"{path}.surface_features")
    if set(features) != {"actual", "counterfactuals", "cf_mean", "shared_cf3_contrast"}:
        raise CF3LocalError(f"{path}.surface_features: key mismatch")
    actual_features = _mapping(features["actual"], f"{path}.surface_features.actual")
    cf_features = features["counterfactuals"]
    mean_features = _mapping(features["cf_mean"], f"{path}.surface_features.cf_mean")
    shared_cf3_contrast_features = _mapping(features["shared_cf3_contrast"], f"{path}.surface_features.shared_cf3_contrast")
    if not isinstance(cf_features, list) or len(cf_features) != 3:
        raise CF3LocalError(f"{path}.surface_features.counterfactuals: expected three")
    feature_maps = [actual_features, *[_mapping(item, path) for item in cf_features], mean_features, shared_cf3_contrast_features]
    if any(set(item) != set(primitive.FEATURES) for item in feature_maps):
        raise CF3LocalError(f"{path}.surface_features: feature inventory mismatch")
    for name in primitive.FEATURES:
        values = [actual_features[name], *[item[name] for item in cf_features]]
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in values):
            raise CF3LocalError(f"{path}.surface_features.{name}: non-finite")
        expected = statistics.fmean(float(item) for item in values[1:])
        if mean_features[name] != expected:
            raise CF3LocalError(f"{path}.surface_features.cf_mean.{name}: mismatch")
        if shared_cf3_contrast_features[name] != actual_features[name] - expected:
            raise CF3LocalError(f"{path}.surface_features.shared_cf3_contrast.{name}: mismatch")
    return dict(value)


def validate_scored_against_input(
    scored: Mapping[str, Any],
    input_row: Mapping[str, Any],
    *,
    path: str = "scored_row",
) -> dict[str, Any]:
    scored = validate_scored_row(scored, path=path)
    input_row = validate_input_row(input_row, path="input_row")
    if scored["input_row_sha256"] != primitive.canonical_row_sha256(input_row):
        raise CF3LocalError(f"{path}.input_row_sha256: differs from exact input row")
    for field in (
        "wave_id",
        "semantic_key",
        "generation_model",
        "domain",
        "id",
        "source_id",
        "source_text_sha256",
        "source_cluster",
        "level",
    ):
        if scored[field] != input_row[field]:
            raise CF3LocalError(f"{path}.{field}: differs from exact input row")
    return scored


def _scored_item_groups(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str, str], tuple[Mapping[str, Any], ...]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, ...]] = set()
    for index, raw in enumerate(rows):
        row = validate_scored_row(raw, path=f"scored_rows[{index}]")
        key = tuple(row["semantic_key"])
        if key in seen:
            raise CF3LocalError(f"duplicate scored semantic key {key!r}")
        seen.add(key)
        grouped[_item_key(row)].append(row)
    result = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda row: LEVELS.index(row["level"]))
        if [row["level"] for row in ordered] != list(LEVELS):
            raise CF3LocalError(f"scored model-item {key!r} is not complete L1-L5")
        for field in ("wave_id", "source_id"):
            if len({row[field] for row in ordered}) != 1:
                raise CF3LocalError(
                    f"scored model-item {key!r}: cross-level {field} mismatch"
                )
        result[key] = tuple(ordered)
    return dict(sorted(result.items()))


def select_balanced_core(
    rows: Sequence[Mapping[str, Any]],
    *,
    domains: Sequence[str],
    seed: int,
    per_stratum: int | None = None,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """Select common source hashes across every included model within domain."""

    groups = _scored_item_groups(rows)
    normalized_domains = tuple(dict.fromkeys(domain.lower() for domain in domains))
    if not normalized_domains:
        raise CF3LocalError("balanced core requires at least one domain")
    models = tuple(sorted({key[0] for key in groups}))
    by_domain_source: dict[
        str, dict[str, dict[str, tuple[str, str, str, str]]]
    ] = defaultdict(lambda: defaultdict(dict))
    for key in groups:
        model, domain, _, source_hash = key
        if domain not in normalized_domains:
            continue
        previous = by_domain_source[domain][source_hash].get(model)
        if previous is not None:
            raise CF3LocalError(
                f"multiple model-items for model/source pair: {model}, {domain}, {source_hash}"
            )
        by_domain_source[domain][source_hash][model] = key
    if set(by_domain_source) != set(normalized_domains):
        raise CF3LocalError(
            f"balanced domains missing: {sorted(set(normalized_domains) - set(by_domain_source))!r}"
        )
    common: dict[str, list[str]] = {}
    for domain in normalized_domains:
        common[domain] = sorted(
            source_hash
            for source_hash, model_items in by_domain_source[domain].items()
            if set(model_items) == set(models)
        )
        if not common[domain]:
            raise CF3LocalError(
                f"domain {domain} has no source hash shared by every included model"
            )
    quota = min(len(values) for values in common.values()) if per_stratum is None else per_stratum
    if quota <= 0 or any(len(values) < quota for values in common.values()):
        raise CF3LocalError(
            f"common-source per-domain quota {quota} exceeds availability"
        )
    selected_keys: set[tuple[str, str, str, str]] = set()
    selected_sources: dict[str, list[str]] = {}
    for domain in normalized_domains:
        ranked = sorted(
            common[domain],
            key=lambda source_hash: (
                hashlib.sha256(
                    f"{seed}\0{domain}\0{source_hash}".encode("utf-8")
                ).hexdigest(),
                source_hash,
            ),
        )[:quota]
        selected_sources[domain] = ranked
        for source_hash in ranked:
            selected_keys.update(by_domain_source[domain][source_hash].values())
    selected = [row for key in sorted(selected_keys) for row in groups[key]]
    manifest = {
        "schema": f"{SCHEMA}.balanced_core",
        "schema_version": SCHEMA_VERSION,
        "selection": (
            "deterministic SHA-256 rank of source hashes shared by every included "
            "model within each domain, before outcome analysis"
        ),
        "domains": list(normalized_domains),
        "models": list(models),
        "seed": seed,
        "per_domain_common_sources": quota,
        "available_common_sources": {
            domain: len(common[domain]) for domain in normalized_domains
        },
        "selected_source_hashes_sha256": primitive.canonical_sha256(
            selected_sources
        ),
        "selected_source_clusters": quota * len(normalized_domains),
        "selected_model_items": len(selected_keys),
        "selected_level_rows": len(selected),
        "semantic_keys_sha256": primitive.sha256_bytes(
            primitive.canonical_json_bytes(
                [list(row["semantic_key"]) for row in selected]
            )
        ),
        "interpretation": (
            "common-source model-and-domain balanced sensitivity subset; "
            "all eligible wave rows remain primary"
        ),
    }
    return selected, manifest


def _value(row: Mapping[str, Any], estimand: str, feature: str | None = None) -> float:
    if feature is None:
        key = "actual" if estimand == "raw" else "shared_cf3_contrast"
        return float(row["blackbox"][key])
    key = "actual" if estimand == "raw" else "shared_cf3_contrast"
    return float(row["surface_features"][key][feature])


def _safe_spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return primitive.fast_spearman(
        np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    )


def _association(
    rows: Sequence[Mapping[str, Any]], estimand: str, feature: str
) -> dict[str, Any]:
    groups = _scored_item_groups(rows)
    left = [_value(row, estimand) for row in rows]
    right = [_value(row, estimand, feature) for row in rows]
    within_level = {}
    for level in LEVELS:
        selected = [row for row in rows if row["level"] == level]
        within_level[level] = _safe_spearman(
            [_value(row, estimand) for row in selected],
            [_value(row, estimand, feature) for row in selected],
        )
    valid_within = [value for value in within_level.values() if value is not None]
    centered_left: list[float] = []
    centered_right: list[float] = []
    item_taus: list[float] = []
    for item_rows in groups.values():
        item_left = [_value(row, estimand) for row in item_rows]
        item_right = [_value(row, estimand, feature) for row in item_rows]
        left_mean = statistics.fmean(item_left)
        right_mean = statistics.fmean(item_right)
        centered_left.extend(value - left_mean for value in item_left)
        centered_right.extend(value - right_mean for value in item_right)
        tau = primitive.safe_kendall(item_left, item_right)
        if tau is not None:
            item_taus.append(float(tau))
    return {
        "n_level_rows": len(rows),
        "n_model_items": len(groups),
        "pooled_spearman": _safe_spearman(left, right),
        "within_level_spearman": within_level,
        "macro_mean_within_level_spearman": (
            float(statistics.fmean(valid_within))
            if len(valid_within) == len(LEVELS)
            else None
        ),
        "item_centered_spearman": _safe_spearman(centered_left, centered_right),
        "mean_per_item_vector_tau_b": (
            float(statistics.fmean(item_taus)) if item_taus else None
        ),
        "valid_item_tau_count": len(item_taus),
    }


def _eta_squared(rows: Sequence[Mapping[str, Any]], estimand: str, feature: str | None) -> float | None:
    values = [_value(row, estimand, feature) for row in rows]
    grand_mean = statistics.fmean(values)
    total = sum((value - grand_mean) ** 2 for value in values)
    if total == 0.0:
        return None
    between = 0.0
    for level in LEVELS:
        selected = [_value(row, estimand, feature) for row in rows if row["level"] == level]
        between += len(selected) * (statistics.fmean(selected) - grand_mean) ** 2
    return between / total


def _gradient(
    rows: Sequence[Mapping[str, Any]], estimand: str, feature: str | None
) -> dict[str, Any]:
    groups = _scored_item_groups(rows)
    level_scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    monotonic = 0
    taus: list[float] = []
    for item_rows in groups.values():
        values = [_value(row, estimand, feature) for row in item_rows]
        if all(left >= right for left, right in zip(values, values[1:])):
            monotonic += 1
        tau = primitive.safe_kendall(values, level_scores)
        if tau is not None:
            taus.append(float(tau))
    return {
        "level_means": {
            level: float(
                statistics.fmean(
                    _value(row, estimand, feature)
                    for row in rows
                    if row["level"] == level
                )
            )
            for level in LEVELS
        },
        "pooled_designed_level_spearman": _safe_spearman(
            [_value(row, estimand, feature) for row in rows],
            [float(5 - LEVELS.index(row["level"])) for row in rows],
        ),
        "eta_squared_level": _eta_squared(rows, estimand, feature),
        "perfect_nonincreasing_rate": monotonic / len(groups),
        "perfect_nonincreasing_n": monotonic,
        "mean_per_item_designed_level_tau_b": (
            float(statistics.fmean(taus)) if taus else None
        ),
        "n_model_items": len(groups),
    }


def _source_cluster_arrays(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[np.ndarray]], int]:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[(row["domain"], row["source_text_sha256"])].append(index)
    by_domain: dict[str, list[np.ndarray]] = defaultdict(list)
    for (domain, source_hash), indices in sorted(grouped.items()):
        del source_hash
        by_domain[domain].append(np.asarray(indices, dtype=int))
    return dict(sorted(by_domain.items())), len(grouped)


def _centered_arrays(
    rows: Sequence[Mapping[str, Any]], arrays: Mapping[str, np.ndarray]
) -> dict[str, np.ndarray]:
    grouped_indices: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped_indices[_item_key(row)].append(index)
    result = {name: values.astype(float, copy=True) for name, values in arrays.items()}
    for indices in grouped_indices.values():
        selected = np.asarray(indices, dtype=int)
        for values in result.values():
            values[selected] -= float(np.mean(values[selected]))
    return result


def _bootstrap_associations(
    rows: Sequence[Mapping[str, Any]],
    *,
    replicates: int,
    seed: int,
    checkpoint_path: Path | None = None,
    checkpoint_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clusters_by_domain, cluster_count = _source_cluster_arrays(rows)
    if replicates <= 0:
        return {
            "method": "disabled",
            "replicates": 0,
            "source_cluster_count": cluster_count,
        }
    levels = np.asarray([row["level"] for row in rows], dtype=object)
    features = tuple(primitive.PRIMARY_BOOTSTRAP_FEATURES)
    estimands = ("raw", "shared_cf3_contrast")
    statistic_names = ("pooled", "macro_within_level", "item_centered")
    arrays: dict[str, np.ndarray] = {}
    for estimand in estimands:
        arrays[f"blackbox:{estimand}"] = np.asarray(
            [_value(row, estimand) for row in rows], dtype=float
        )
        for feature in features:
            arrays[f"{feature}:{estimand}"] = np.asarray(
                [_value(row, estimand, feature) for row in rows], dtype=float
            )
    centered = _centered_arrays(rows, arrays)

    def statistics_for(
        blackbox: np.ndarray,
        heuristic: np.ndarray,
        selected_levels: np.ndarray,
        centered_blackbox: np.ndarray,
        centered_heuristic: np.ndarray,
    ) -> dict[str, float | None]:
        level_values = []
        for level in LEVELS:
            mask = selected_levels == level
            value = primitive.fast_spearman(blackbox[mask], heuristic[mask])
            if value is not None:
                level_values.append(value)
        return {
            "pooled": primitive.fast_spearman(blackbox, heuristic),
            "macro_within_level": (
                float(statistics.fmean(level_values))
                if len(level_values) == len(LEVELS)
                else None
            ),
            "item_centered": primitive.fast_spearman(
                centered_blackbox, centered_heuristic
            ),
        }

    observed: dict[str, dict[str, dict[str, float | None]]] = {}
    for estimand in estimands:
        observed[estimand] = {}
        blackbox = arrays[f"blackbox:{estimand}"]
        centered_blackbox = centered[f"blackbox:{estimand}"]
        for feature in features:
            observed[estimand][feature] = statistics_for(
                blackbox,
                arrays[f"{feature}:{estimand}"],
                levels,
                centered_blackbox,
                centered[f"{feature}:{estimand}"],
            )

    checkpoint_config = primitive.canonical_sha256(
        {
            "schema": f"{SCHEMA}.bootstrap_config",
            "cf3_protocol_sha256": CF3_PROTOCOL_SHA256,
            "checkpoint_context": dict(checkpoint_context or {}),
            "ordered_scored_input_row_sha256": [
                [list(row["semantic_key"]), row["input_row_sha256"]]
                for row in sorted(rows, key=lambda item: tuple(item["semantic_key"]))
            ],
            "replicates": replicates,
            "seed": seed,
            "features": list(features),
            "estimands": list(estimands),
            "statistics": list(statistic_names),
        }
    )
    records: list[dict[str, Any]] = []
    if checkpoint_path is not None and checkpoint_path.exists():
        checkpoint = _strict_json(
            checkpoint_path.read_bytes(), str(checkpoint_path)
        )
        expected_keys = {
            "schema",
            "schema_version",
            "config_sha256",
            "completed_replicates",
            "replicates",
            "seed",
            "records",
        }
        if not isinstance(checkpoint, Mapping) or set(checkpoint) != expected_keys:
            raise CF3LocalError("bootstrap checkpoint schema mismatch")
        if (
            checkpoint["schema"] != f"{SCHEMA}.bootstrap_checkpoint"
            or type(checkpoint["schema_version"]) is not int
            or checkpoint["schema_version"] != SCHEMA_VERSION
            or checkpoint["config_sha256"] != checkpoint_config
            or checkpoint["replicates"] != replicates
            or checkpoint["seed"] != seed
            or type(checkpoint["completed_replicates"]) is not int
            or not isinstance(checkpoint["records"], list)
            or len(checkpoint["records"]) != checkpoint["completed_replicates"]
            or not 0 <= checkpoint["completed_replicates"] <= replicates
        ):
            raise CF3LocalError("bootstrap checkpoint binding mismatch")
        records = list(checkpoint["records"])
    elif checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    for replicate in range(len(records), replicates):
        replicate_seed = int.from_bytes(
            hashlib.sha256(f"{seed}\0{replicate}".encode("ascii")).digest()[:8],
            "big",
        )
        rng = np.random.default_rng(replicate_seed)
        domain_parts = []
        for clusters in clusters_by_domain.values():
            chosen = rng.integers(0, len(clusters), size=len(clusters))
            domain_parts.extend(clusters[index] for index in chosen)
        indices = np.concatenate(domain_parts)
        selected_levels = levels[indices]
        record: dict[str, Any] = {}
        for estimand in estimands:
            record[estimand] = {}
            blackbox = arrays[f"blackbox:{estimand}"][indices]
            centered_blackbox = centered[f"blackbox:{estimand}"][indices]
            for feature in features:
                record[estimand][feature] = statistics_for(
                    blackbox,
                    arrays[f"{feature}:{estimand}"][indices],
                    selected_levels,
                    centered_blackbox,
                    centered[f"{feature}:{estimand}"][indices],
                )
        records.append(record)
        if checkpoint_path is not None and (
            len(records) % 25 == 0 or len(records) == replicates
        ):
            _atomic_replace_json(
                checkpoint_path,
                {
                    "schema": f"{SCHEMA}.bootstrap_checkpoint",
                    "schema_version": SCHEMA_VERSION,
                    "config_sha256": checkpoint_config,
                    "completed_replicates": len(records),
                    "replicates": replicates,
                    "seed": seed,
                    "records": records,
                },
            )

    draws = {
        estimand: {
            feature: {name: [] for name in statistic_names}
            for feature in features
        }
        for estimand in estimands
    }
    for record_index, record in enumerate(records):
        if not isinstance(record, Mapping) or set(record) != set(estimands):
            raise CF3LocalError(
                f"bootstrap record {record_index}: estimand inventory mismatch"
            )
        for estimand in estimands:
            by_feature = record[estimand]
            if not isinstance(by_feature, Mapping) or set(by_feature) != set(features):
                raise CF3LocalError(
                    f"bootstrap record {record_index}: feature inventory mismatch"
                )
            for feature in features:
                by_statistic = by_feature[feature]
                if not isinstance(by_statistic, Mapping) or set(by_statistic) != set(
                    statistic_names
                ):
                    raise CF3LocalError(
                        f"bootstrap record {record_index}: statistic inventory mismatch"
                    )
                for name in statistic_names:
                    value = by_statistic[name]
                    if value is None:
                        continue
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                    ):
                        raise CF3LocalError(
                            f"bootstrap record {record_index}: invalid statistic"
                        )
                    draws[estimand][feature][name].append(float(value))

    result: dict[str, Any] = {}
    for estimand, by_feature in draws.items():
        result[estimand] = {}
        for feature, by_statistic in by_feature.items():
            result[estimand][feature] = {}
            for name, values in by_statistic.items():
                result[estimand][feature][name] = {
                    "observed_statistic": observed[estimand][feature][name],
                    "bootstrap_mean": (
                        float(statistics.fmean(values)) if values else None
                    ),
                    "ci95_percentile": (
                        [
                            float(np.percentile(values, 2.5)),
                            float(np.percentile(values, 97.5)),
                        ]
                        if values
                        else None
                    ),
                    "effective_replicates": len(values),
                    "undefined_replicates": replicates - len(values),
                }
    return {
        "method": "deterministic domain-stratified source-cluster percentile bootstrap",
        "cluster_definition": ["domain", "source_text_sha256"],
        "source_cluster_count": cluster_count,
        "domain_cluster_counts": {
            domain: len(clusters) for domain, clusters in clusters_by_domain.items()
        },
        "replicates": replicates,
        "seed": seed,
        "checkpoint_config_sha256": checkpoint_config,
        "checkpointed": checkpoint_path is not None,
        "scope": "direct blackbox-heuristic association; no white-box target",
        "all_five_levels_required_for_macro": True,
        "results": result,
    }


def summarize_scored_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_replicates: int,
    seed: int,
    cohort_label: str,
    created_at_utc: str | None = None,
    bootstrap_checkpoint_path: Path | None = None,
    bootstrap_checkpoint_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [validate_scored_row(row, path=f"rows[{index}]") for index, row in enumerate(rows)]
    groups = _scored_item_groups(rows)
    if not groups:
        raise CF3LocalError("cannot summarize an empty cohort")
    associations = {
        estimand: {
            feature: _association(rows, estimand, feature)
            for feature in primitive.FEATURES
        }
        for estimand in ("raw", "shared_cf3_contrast")
    }
    gradients = {
        estimand: {
            "blackbox": _gradient(rows, estimand, None),
            "surface_features": {
                feature: _gradient(rows, estimand, feature)
                for feature in primitive.FEATURES
            },
        }
        for estimand in ("raw", "shared_cf3_contrast")
    }
    counts = {
        "level_rows": len(rows),
        "model_items": len(groups),
        "source_clusters": len(
            {(row["domain"], row["source_text_sha256"]) for row in rows}
        ),
        "models": dict(
            sorted(
                (model, sum(key[0] == model for key in groups))
                for model in {key[0] for key in groups}
            )
        ),
        "domains": dict(
            sorted(
                (domain, sum(key[1] == domain for key in groups))
                for domain in {key[1] for key in groups}
            )
        ),
        "waves": dict(
            sorted(
                (
                    wave,
                    len(
                        {
                            _item_key(row)
                            for row in rows
                            if row["wave_id"] == wave
                        }
                    ),
                )
                for wave in {row["wave_id"] for row in rows}
            )
        ),
    }
    return {
        "schema": f"{SCHEMA}.summary",
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": created_at_utc or utc_now(),
        "cohort_label": cohort_label,
        "status": "exploratory-local-only-no-whitebox",
        "cf3_protocol_sha256": CF3_PROTOCOL_SHA256,
        "counts": counts,
        "estimands": {
            "raw": "blackbox actual vs heuristic actual",
            "shared_cf3_contrast": (
                "blackbox actual-minus-shared-CF3-mean vs heuristic "
                "actual-minus-the-same-shared-CF3-mean"
            ),
        },
        "feature_groups": {
            "primary_lexical": list(primitive.PRIMARY_LEXICAL_FEATURES),
            "length": list(primitive.LENGTH_FEATURES),
            "output_structure": list(primitive.OUTPUT_STRUCTURE_FEATURES),
            "compression_derived_diagnostics": list(
                primitive.COMPRESSION_DERIVED_FEATURES
            ),
            "all_features_multiple_tested": list(primitive.FEATURES),
        },
        "associations": associations,
        "designed_gradient_diagnostics": gradients,
        "bootstrap": _bootstrap_associations(
            rows,
            replicates=bootstrap_replicates,
            seed=seed,
            checkpoint_path=bootstrap_checkpoint_path,
            checkpoint_context=bootstrap_checkpoint_context,
        ),
        "interpretation_limits": [
            "No white-box strict excess is available in this local-only run.",
            "Direct blackbox-heuristic association does not establish criterion validity.",
            (
                "Both shared-CF3 contrasts subtract functions of the same three control "
                "texts; induced shared-control covariance can inflate association and "
                "does not validate the subtraction."
            ),
            (
                "CF1-CF3 are an ordered non-random prefix; position sensitivity is not "
                "identified by this derivative."
            ),
            (
                "output_self_bits_per_byte is compression-derived and is reported only "
                "as a diagnostic, not as a purely lexical surface comparator."
            ),
            "All-feature analyses are multiple-tested; primary lexical features are declared separately.",
            "Availability in a campaign wave may be completion-order selective.",
            "Formal strict-CF remains the frozen five-counterfactual protocol.",
        ],
    }


def validate_completed_output(output_dir: Path) -> dict[str, Any]:
    output_dir = assert_outside_strict_runs(
        output_dir, label="completed analysis output"
    ).resolve(strict=True)
    manifest_path = output_dir / "output_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CF3LocalError("completed output manifest is missing or symlinked")
    manifest = _strict_json(manifest_path.read_bytes(), str(manifest_path))
    if not isinstance(manifest, Mapping) or set(manifest) != OUTPUT_MANIFEST_KEYS:
        raise CF3LocalError("existing output manifest keys are invalid")
    if (
        manifest["schema"] != f"{SCHEMA}.output_manifest"
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != SCHEMA_VERSION
        or manifest["state"] != "complete"
        or manifest["cf3_protocol"] != CF3_PROTOCOL
        or manifest["cf3_protocol_sha256"] != CF3_PROTOCOL_SHA256
    ):
        raise CF3LocalError("existing output manifest is invalid or incomplete")
    _text(manifest["created_at_utc"], "output_manifest.created_at_utc")
    _sha256(
        manifest["execution_config_sha256"],
        "output_manifest.execution_config_sha256",
    )
    request = manifest["analysis_request"]
    if not isinstance(request, Mapping) or set(request) != {
        "balanced_domains",
        "balanced_common_sources_requested",
        "bootstrap_replicates",
        "seed",
    }:
        raise CF3LocalError("existing output analysis request is invalid")
    if (
        not isinstance(request["balanced_domains"], list)
        or not request["balanced_domains"]
        or any(not isinstance(value, str) or not value for value in request["balanced_domains"])
    ):
        raise CF3LocalError("existing output balanced domains are invalid")
    for field in (
        "balanced_common_sources_requested",
        "bootstrap_replicates",
        "seed",
    ):
        _integer(request[field], f"output_manifest.analysis_request.{field}")
    if not isinstance(manifest["execution_binding"], Mapping):
        raise CF3LocalError("existing output execution binding is invalid")
    inputs = manifest["inputs"]
    input_keys = {
        "manifest_path",
        "manifest_sha256",
        "snapshot_id",
        "snapshot_root_sha256",
        "wave_id",
        "rows_sha256",
    }
    if not isinstance(inputs, list) or not inputs:
        raise CF3LocalError("existing output manifest lacks input waves")
    for index, entry in enumerate(inputs):
        if not isinstance(entry, Mapping) or set(entry) != input_keys:
            raise CF3LocalError(f"existing output input {index} is invalid")
        _text(entry["manifest_path"], f"output_manifest.inputs[{index}].manifest_path")
        _text(entry["snapshot_id"], f"output_manifest.inputs[{index}].snapshot_id")
        _text(entry["wave_id"], f"output_manifest.inputs[{index}].wave_id")
        for field in ("manifest_sha256", "snapshot_root_sha256", "rows_sha256"):
            _sha256(entry[field], f"output_manifest.inputs[{index}].{field}")
    claims = manifest["claims"]
    if not isinstance(claims, Mapping) or set(claims) != OUTPUT_CLAIM_KEYS:
        raise CF3LocalError("existing output claims are invalid")
    if dict(claims) != {
        "whitebox_strict_scored": False,
        "external_api_calls": 0,
        "gpu_inference": False,
        "formal_five_cf_modified": False,
        "scoring_journal_fsync_per_row": True,
    }:
        raise CF3LocalError("existing output claims differ from local-only contract")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, Mapping) or set(artifacts) != OUTPUT_ARTIFACT_NAMES:
        raise CF3LocalError("existing output artifact inventory is not exact")
    for name, metadata in artifacts.items():
        if not isinstance(metadata, Mapping) or set(metadata) != {"sha256", "size"}:
            raise CF3LocalError(f"existing output artifact metadata is invalid: {name}")
        _sha256(metadata["sha256"], f"output_manifest.artifacts.{name}.sha256")
        _integer(metadata["size"], f"output_manifest.artifacts.{name}.size", minimum=1)
        path = output_dir / name
        if path.is_symlink() or not path.is_file():
            raise CF3LocalError(f"existing output artifact missing/symlinked: {name}")
        try:
            path.resolve(strict=True).relative_to(output_dir)
        except ValueError as exc:
            raise CF3LocalError(f"existing output artifact escapes directory: {name}") from exc
        if (
            path.stat().st_size != metadata["size"]
            or primitive.file_sha256(path) != metadata["sha256"]
        ):
            raise CF3LocalError(f"existing completed output artifact drift: {name}")
    return dict(manifest)


def write_analysis_bundle(
    output_dir: Path,
    *,
    input_manifest_paths: Sequence[Path],
    input_manifests: Sequence[Mapping[str, Any]],
    scored_rows: Sequence[Mapping[str, Any]],
    all_ready_summary: Mapping[str, Any],
    balanced_rows: Sequence[Mapping[str, Any]],
    balanced_manifest: Mapping[str, Any],
    balanced_summary: Mapping[str, Any],
    execution_config_sha256: str,
    execution_binding: Mapping[str, Any],
    analysis_request: Mapping[str, Any],
    created_at_utc: str,
) -> Path:
    if _inside_active_run(output_dir):
        raise CF3LocalError("analysis output must be outside the active strict-CF run")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}

    def publish(name: str, payload: bytes) -> None:
        path = output_dir / name
        if path.exists():
            if path.read_bytes() != payload:
                raise CF3LocalError(
                    f"existing partial publication artifact differs: {path}"
                )
        else:
            _exclusive_write(path, payload)
        artifacts[name] = {
            "sha256": primitive.sha256_bytes(payload),
            "size": len(payload),
        }

    ordered_scored = sorted(scored_rows, key=lambda row: tuple(row["semantic_key"]))
    publish(
        "matched_cf3_rows.jsonl",
        b"".join(primitive.canonical_jsonl_row_bytes(row) for row in ordered_scored),
    )
    publish(
        "all_ready_summary.json",
        primitive.canonical_jsonl_row_bytes(all_ready_summary),
    )
    publish(
        "balanced_core_manifest.json",
        primitive.canonical_jsonl_row_bytes(balanced_manifest),
    )
    publish(
        "balanced_core_rows.jsonl",
        b"".join(
            primitive.canonical_jsonl_row_bytes(row)
            for row in sorted(balanced_rows, key=lambda row: tuple(row["semantic_key"]))
        ),
    )
    publish(
        "balanced_core_summary.json",
        primitive.canonical_jsonl_row_bytes(balanced_summary),
    )
    if len(input_manifest_paths) != len(input_manifests) or not input_manifests:
        raise CF3LocalError("input manifest path/document inventory mismatch")
    manifest = {
        "schema": f"{SCHEMA}.output_manifest",
        "schema_version": SCHEMA_VERSION,
        "state": "complete",
        "created_at_utc": created_at_utc,
        "execution_config_sha256": _sha256(
            execution_config_sha256, "execution_config_sha256"
        ),
        "analysis_request": dict(analysis_request),
        "inputs": [
            {
                "manifest_path": str(path.resolve()),
                "manifest_sha256": primitive.file_sha256(path),
                "snapshot_id": document["snapshot_id"],
                "snapshot_root_sha256": document["snapshot_root_sha256"],
                "wave_id": document["wave_id"],
                "rows_sha256": document["rows"]["sha256"],
            }
            for path, document in zip(input_manifest_paths, input_manifests)
        ],
        "cf3_protocol": CF3_PROTOCOL,
        "cf3_protocol_sha256": CF3_PROTOCOL_SHA256,
        "execution_binding": dict(execution_binding),
        "artifacts": artifacts,
        "claims": {
            "whitebox_strict_scored": False,
            "external_api_calls": 0,
            "gpu_inference": False,
            "formal_five_cf_modified": False,
            "scoring_journal_fsync_per_row": True,
        },
    }
    manifest_path = output_dir / "output_manifest.json"
    _exclusive_write(manifest_path, primitive.canonical_jsonl_row_bytes(manifest))
    return manifest_path
