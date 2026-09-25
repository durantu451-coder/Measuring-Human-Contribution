# -*- coding: utf-8 -*-
"""Prepare the immutable strict-CF v1 matched actual snapshot.

The command is deliberately explicit: callers must name all four source files,
all twenty model/domain result files, the debug directory, and the pilot sample
file.  It never discovers or calls a model API.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_a import strict_cf_schema as strict_schema
from experiment_a.strict_cf_schema import (
    ACTUAL_METRIC_STATUS,
    ARTIFACT_SPECS,
    COMPRESSORS,
    DOMAINS,
    EXPECTED_LEVEL_ROWS,
    EXPECTED_MODEL_ITEMS,
    EXPECTED_SOURCE_CLUSTERS,
    EXPECTED_SOURCES_PER_DOMAIN,
    LEVEL_MAIN_CALL,
    LEVELS,
    LINEAGE_SCHEMA,
    MAIN_CALL_LABELS,
    MANIFEST_SCHEMA,
    MODELS,
    MODEL_PROTOCOLS,
    HISTORICAL_API821_CUTOVER_RELATIVE_PATH,
    HISTORICAL_API821_PROTOCOLS,
    PROVENANCE_TIER_EXACT,
    PROVENANCE_TIER_HISTORICAL_API821,
    PROVENANCE_TIER_LEGACY_UNATTESTED,
    STRICT_ACTUAL_PROVENANCE_TIERS,
    RUN_STATUS_PATH,
    RUN_STATUS_SCHEMA,
    SCHEMA_VERSION,
    SCORING_PROTOCOL_SHA256,
    SELECTION_ALGORITHM,
    SELECTION_SEED,
    StrictCFSchemaError,
    actual_pair_sha256,
    assert_path_within_run,
    canonical_runs_root,
    canonical_row_sha256,
    canonical_sha256,
    deterministic_selection_rank,
    file_sha256,
    level_key,
    model_item_key,
    source_cluster_key,
    validate_actual_item_provenance,
    validate_actual_snapshot_row,
    validate_historical_backend_b_actual_item_provenance,
    validate_historical_cutover_attestation,
    validate_historical_cutover_manifest_document,
    validate_lineage_id,
    validate_manifest,
    validate_run_dir,
    validate_run_status,
)
from experiment_b import storage
from human_contribution.metrics import information_gain_profile


class StrictCFPreparationError(RuntimeError):
    """Preparation cannot produce the exact trusted matched cohort."""


def validate_historical_repair_evidence(
    project_root: str | Path,
) -> dict[str, Any]:
    """Pin the approved audit/method/cutover preimage before cohort preparation."""

    root = Path(project_root).resolve()
    evidence: dict[str, Any] = {}
    for name, (relative, expected_sha) in _HISTORICAL_REPAIR_EVIDENCE.items():
        path = (root / relative).resolve()
        if not path.is_file() or file_sha256(path) != expected_sha:
            raise StrictCFPreparationError(
                f"historical repair {name} evidence hash mismatch: {path}"
            )
        evidence[name] = {
            "path": str(path),
            "sha256": expected_sha,
            "source_lineage_only": True,
        }
    audit = _load_json(Path(evidence["audit"]["path"]))
    if not isinstance(audit, Mapping):
        raise StrictCFPreparationError("historical repair audit must be an object")
    expected_fields = {
        "common_nonpilot_canonical_source_counts": _EXPECTED_COMMON_SOURCE_COUNTS,
        "selected_source_hashes_sha256": _EXPECTED_SELECTED_SOURCE_DIGESTS,
        "selected_model_item_provenance_tiers": _EXPECTED_SELECTED_ITEM_TIERS,
        "selected_level_row_provenance_tiers": _EXPECTED_SELECTED_LEVEL_TIERS,
    }
    for field, expected in expected_fields.items():
        if audit.get(field) != expected:
            raise StrictCFPreparationError(
                f"historical repair audit {field} differs from approved preimage"
            )
    if (
        audit.get("api_calls_made") != 0
        or audit.get("backend_c_cutover_manifest", {}).get("sha256")
        != _EXPECTED_CUTOVER_SOURCE_SHA256
    ):
        raise StrictCFPreparationError("historical repair audit/cutover binding mismatch")
    cutover_path = (root / HISTORICAL_API821_CUTOVER_RELATIVE_PATH).resolve()
    if not cutover_path.is_file() or file_sha256(cutover_path) != _EXPECTED_CUTOVER_SOURCE_SHA256:
        raise StrictCFPreparationError("external cutover source differs from approved audit")
    return evidence


def validate_historical_repair_selection(
    selected: Mapping[str, Iterable[str]],
    common_pool_counts: Mapping[str, int],
    selected_item_tiers: Mapping[str, int],
    selected_level_tiers: Mapping[str, int],
) -> None:
    observed_digests = {
        domain: canonical_sha256(list(selected[domain])) for domain in DOMAINS
    }
    if dict(common_pool_counts) != _EXPECTED_COMMON_SOURCE_COUNTS:
        raise StrictCFPreparationError("common source counts differ from approved audit")
    if observed_digests != _EXPECTED_SELECTED_SOURCE_DIGESTS:
        raise StrictCFPreparationError("selected source digests differ from approved audit")
    if dict(sorted(selected_item_tiers.items())) != _EXPECTED_SELECTED_ITEM_TIERS:
        raise StrictCFPreparationError("selected item tiers differ from approved audit")
    if dict(sorted(selected_level_tiers.items())) != _EXPECTED_SELECTED_LEVEL_TIERS:
        raise StrictCFPreparationError("selected level tiers differ from approved audit")


def validate_historical_repair_lineage(
    preparation: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    """Preflight the frozen Stage-0 decisions without rereading external sources."""

    evidence = preparation.get("inputs", {}).get("historical_repair_evidence")
    if preparation.get("historical_tier_semantics") != _HISTORICAL_TIER_SEMANTICS:
        raise StrictCFPreparationError("historical tier semantics changed")
    if not isinstance(evidence, Mapping):
        raise StrictCFPreparationError("preparation lineage lacks repair evidence")
    for name, (relative, expected_sha) in _HISTORICAL_REPAIR_EVIDENCE.items():
        entry = evidence.get(name)
        if (
            not isinstance(entry, Mapping)
            or entry.get("sha256") != expected_sha
            or not Path(str(entry.get("path", ""))).as_posix().replace(
                "\\", "/"
            ).endswith(relative)
            or entry.get("source_lineage_only") is not True
        ):
            raise StrictCFPreparationError(f"repair lineage {name} mismatch")
    source_cutover = preparation.get("inputs", {}).get("backend_c_cutover_manifest")
    if (
        not isinstance(source_cutover, Mapping)
        or source_cutover.get("sha256") != _EXPECTED_CUTOVER_SOURCE_SHA256
    ):
        raise StrictCFPreparationError("source cutover lineage mismatch")
    frozen = preparation.get("frozen_inputs", {}).get(
        "historical_cutover_manifest"
    )
    artifact = manifest.get("artifacts", {}).get("historical_cutover_manifest")
    if (
        not isinstance(frozen, Mapping)
        or not isinstance(artifact, Mapping)
        or frozen.get("path") != artifact.get("path")
        or frozen.get("sha256") != artifact.get("sha256")
        or artifact.get("sha256") != _EXPECTED_CUTOVER_SOURCE_SHA256
        or frozen.get("row_count") != 1
    ):
        raise StrictCFPreparationError("frozen cutover lineage/manifest mismatch")
    for evidence_name, artifact_name in (
        ("audit", "historical_repair_audit"),
        ("method", "historical_repair_method"),
    ):
        expected_sha = _HISTORICAL_REPAIR_EVIDENCE[evidence_name][1]
        frozen_evidence = preparation.get("frozen_inputs", {}).get(artifact_name)
        evidence_artifact = manifest.get("artifacts", {}).get(artifact_name)
        if (
            not isinstance(frozen_evidence, Mapping)
            or not isinstance(evidence_artifact, Mapping)
            or frozen_evidence.get("path") != evidence_artifact.get("path")
            or frozen_evidence.get("sha256") != expected_sha
            or evidence_artifact.get("sha256") != expected_sha
            or frozen_evidence.get("row_count") != 1
            or frozen_evidence.get("source_lineage_only") != evidence[evidence_name]
        ):
            raise StrictCFPreparationError(
                f"frozen historical repair {evidence_name} mismatch"
            )
    selection = preparation.get("selection", {})
    counts = preparation.get("counts", {})
    if (
        selection.get("common_source_pool_counts") != _EXPECTED_COMMON_SOURCE_COUNTS
        or {
            domain: canonical_sha256(selection.get("selected_source_hashes", {}).get(domain, []))
            for domain in DOMAINS
        }
        != _EXPECTED_SELECTED_SOURCE_DIGESTS
        or counts.get("selected_model_item_provenance_tiers")
        != _EXPECTED_SELECTED_ITEM_TIERS
        or counts.get("selected_level_row_provenance_tiers")
        != _EXPECTED_SELECTED_LEVEL_TIERS
    ):
        raise StrictCFPreparationError("prepared selection differs from approved audit")


MIN_ACTUAL_OUTPUT_CHARS = 80
_HISTORICAL_REPAIR_EVIDENCE = {
    "audit": (
        "tmp/strict_cf_historical_tier_audit_20260904.json",
        "5082463234dbe376356223b919806bbffde8cb44c17a5c0d08db20da8bff9853",
    ),
    "method": (
        "tmp/strict_cf_historical_tier_feasibility_method_20260904.md",
        "d3fb6862ce1ce438ca90b8d6bf90ecae691cbd756e4abb518f59c3853bc895b3",
    ),
}
_EXPECTED_CUTOVER_SOURCE_SHA256 = (
    "6e8d99898ddf921fc54b4d9f81131f15e8a93ba3a089530373e88e4ef96be4d8"
)
_EXPECTED_COMMON_SOURCE_COUNTS = {
    "arxiv": 989,
    "news": 924,
    "patent": 991,
    "poetry": 955,
}
_EXPECTED_SELECTED_SOURCE_DIGESTS = {
    "arxiv": "85910bdfb67e19edc92bc15c9dd35b3ba545612edfcba1816a30d157412a63c3",
    "news": "bb2a1ea210242dec6084c8f171e0bdec5c5eb03bd23ce753df14a84ef9713248",
    "patent": "c7b9a7aa0d5ad969d23c2fe45c48814882225338239d7cdc920ebac26245c9ca",
    "poetry": "110c6e1473b0f6100e6fe91f282e1f86dac5b6e79943bd1fe7db2c89c0e7f376",
}
_EXPECTED_SELECTED_ITEM_TIERS = {
    "exact": 2654,
    "historical_backend_b_attested": 1346,
}
_EXPECTED_SELECTED_LEVEL_TIERS = {
    "exact": 13270,
    "historical_backend_b_attested": 6730,
}
_HISTORICAL_TIER_SEMANTICS = {
    "attested": [
        "requested_and_returned_model",
        "completed_status",
        "backend_b_gateway",
        "max_output_tokens_4096",
        "response_id",
        "positive_output_token_usage",
        "utc_capture_timestamp",
        "source_hash_id_index_binding",
        "project_local_cutover_membership",
    ],
    "unattested_when_absent": [
        "per_call_route",
        "client_identity_or_hash",
        "reasoning_effort",
    ],
    "cutover_scope": (
        "project-local consistency boundary only; not an externally trusted timestamp"
    ),
    "repair_preimage_claimed": False,
}
_KNOWN_ERROR_PREFIXES = (
    "[error: all endpoints are unavailable",
    "[error] all endpoints are unavailable",
    "[api error: all endpoints are unavailable",
    "api ask failed",
    "all endpoints are unavailable",
    "the api returned no output_text",
    "error: request failed",
)


def _valid_actual_output(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    folded = text.casefold()
    if len(text) < MIN_ACTUAL_OUTPUT_CHARS or folded.startswith(
        _KNOWN_ERROR_PREFIXES
    ):
        return False
    words = text.split()
    return not (len(words) > 20 and len(set(words)) < 5)


def _actual_text_quality_reason(debug: Mapping[str, Any]) -> str | None:
    prompts = debug.get("prompts")
    outputs = debug.get("outputs")
    if not isinstance(prompts, Mapping) or not isinstance(outputs, Mapping):
        return "missing_actual_prompts_or_outputs"
    if set(prompts) != set(LEVELS) or set(outputs) != set(LEVELS):
        return "incomplete_L1_L5_actual_text"
    for level in LEVELS:
        prompt = prompts[level]
        output = outputs[level]
        if not isinstance(prompt, str) or not prompt.strip():
            return f"invalid_actual_prompt:{level}"
        if not _valid_actual_output(output):
            return f"invalid_actual_output:{level}"
    return None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictCFPreparationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise StrictCFPreparationError(f"non-finite JSON constant {value!r}")


def _load_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StrictCFPreparationError(f"cannot load strict UTF-8 JSON {source}: {exc}") from exc


def _source_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_poetry_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Assign the same deterministic duplicate-safe Poetry IDs as Experiment A."""

    copied: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for source_index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise StrictCFPreparationError(f"poetry source row {source_index} is not an object")
        item = dict(raw)
        base_id = str(item.get("id", ""))
        text = item.get("text")
        if not base_id or not isinstance(text, str) or not text:
            raise StrictCFPreparationError(
                f"poetry source row {source_index} requires non-empty id/text"
            )
        item["_source_index"] = source_index
        copied.append(item)
        counts[base_id] += 1

    stable: list[dict[str, Any]] = []
    for item in copied:
        base_id = str(item["id"])
        source_index = int(item.pop("_source_index"))
        stable_id = base_id
        if counts[base_id] > 1:
            text_hash = _source_text_sha256(item["text"])
            stable_id = f"{base_id}__row{source_index:04d}_{text_hash[:8]}"
        item["id"] = stable_id
        item["source_id"] = base_id
        item["source_index"] = source_index
        stable.append(item)
    return stable


def extract_pilot_source_hashes(value: Any) -> frozenset[str]:
    """Recursively collect text hashes; exclusion never trusts pilot IDs."""

    hashes: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, Mapping):
            text = node.get("text")
            if isinstance(text, str) and text:
                hashes.add(_source_text_sha256(text))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return frozenset(hashes)


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    keys = set(value)
    if keys != expected:
        raise StrictCFPreparationError(
            f"{label} keys must be exact: missing={sorted(expected - keys)}, "
            f"extra={sorted(keys - expected)}"
        )


def normalize_data_paths(data_paths: Mapping[str, str | Path]) -> dict[str, Path]:
    _require_exact_keys(data_paths, set(DOMAINS), "data_paths")
    normalized = {domain: Path(data_paths[domain]).resolve() for domain in DOMAINS}
    for domain, path in normalized.items():
        if not path.is_file():
            raise StrictCFPreparationError(f"missing {domain} source file: {path}")
    return normalized


def normalize_result_paths(
    result_paths: Mapping[str, Mapping[str, str | Path]],
) -> dict[str, dict[str, Path]]:
    _require_exact_keys(result_paths, set(MODELS), "result_paths")
    normalized: dict[str, dict[str, Path]] = {}
    observed_paths: set[Path] = set()
    for model in MODELS:
        per_domain = result_paths[model]
        _require_exact_keys(per_domain, set(DOMAINS), f"result_paths[{model}]")
        normalized[model] = {}
        for domain in DOMAINS:
            path = Path(per_domain[domain]).resolve()
            if not path.is_file():
                raise StrictCFPreparationError(
                    f"missing result file for {model}/{domain}: {path}"
                )
            if path in observed_paths:
                raise StrictCFPreparationError(f"result path reused by multiple scopes: {path}")
            observed_paths.add(path)
            normalized[model][domain] = path
    return normalized


def load_source_catalog(
    data_paths: Mapping[str, str | Path],
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Load explicit source files and return ID indices plus input lineage."""

    paths = normalize_data_paths(data_paths)
    catalog: dict[str, dict[str, dict[str, Any]]] = {}
    lineage: dict[str, dict[str, Any]] = {}
    for domain in DOMAINS:
        path = paths[domain]
        raw = _load_json(path)
        if not isinstance(raw, list):
            raise StrictCFPreparationError(f"{domain} source file must contain a JSON list")
        rows = stable_poetry_rows(raw) if domain == "poetry" else [dict(row) for row in raw]
        by_id: dict[str, dict[str, Any]] = {}
        by_hash: dict[str, list[str]] = {}
        for source_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise StrictCFPreparationError(f"{domain} source row {source_index} is not an object")
            item_id = str(row.get("id", ""))
            text = row.get("text")
            title = row.get("title")
            if not item_id or not isinstance(text, str) or not text:
                raise StrictCFPreparationError(
                    f"{domain} source row {source_index} requires non-empty id/text"
                )
            if not isinstance(title, str) or not title:
                raise StrictCFPreparationError(
                    f"{domain} source row {source_index} requires non-empty title"
                )
            if item_id in by_id:
                raise StrictCFPreparationError(f"duplicate stable source ID in {domain}: {item_id}")
            digest = _source_text_sha256(text)
            if domain != "poetry":
                source_id = item_id
                stable_index: int | None = None
            else:
                source_id = str(row["source_id"])
                stable_index = int(row["source_index"])
            wc = row.get("wc", row.get("word_count", len(text.split())))
            if isinstance(wc, bool) or not isinstance(wc, int) or wc < 0:
                raise StrictCFPreparationError(f"invalid word count for {domain}/{item_id}")
            normalized = {
                "id": item_id,
                "source_id": source_id,
                "source_index": stable_index,
                "title": title,
                "text": text,
                "word_count": wc,
                "source_text_sha256": digest,
                "_catalog_index": source_index,
            }
            by_id[item_id] = normalized
            by_hash.setdefault(digest, []).append(item_id)
        duplicate_groups = []
        for digest, item_ids in sorted(by_hash.items()):
            canonical_id = min(
                item_ids,
                key=lambda value: (by_id[value]["_catalog_index"], value),
            )
            for item_id in item_ids:
                by_id[item_id]["strict_canonical_id"] = canonical_id
                by_id[item_id]["strict_canonical_for_text"] = item_id == canonical_id
                by_id[item_id]["content_duplicate_count"] = len(item_ids)
            if len(item_ids) > 1:
                duplicate_groups.append(
                    {
                        "source_text_sha256": digest,
                        "canonical_id": canonical_id,
                        "ids": list(item_ids),
                    }
                )
        catalog[domain] = by_id
        lineage[domain] = {
            "path": str(path),
            "sha256": file_sha256(path),
            "row_count": len(rows),
            "unique_text_hashes": len(by_hash),
            "duplicate_text_hashes": len(duplicate_groups),
            "duplicate_source_rows": sum(len(group["ids"]) for group in duplicate_groups),
            "duplicate_groups_sha256": canonical_sha256(duplicate_groups),
        }
    return catalog, lineage


def _load_cutover_manifest_path(
    path: str | Path,
    *,
    expected_path: str | Path | None = None,
    expected_sha256: str | None = None,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any], Mapping[str, Any]]:
    resolved = Path(path).resolve()
    if expected_path is not None and resolved != Path(expected_path).resolve():
        raise StrictCFPreparationError(
            f"cutover manifest path {resolved} != {Path(expected_path).resolve()}"
        )
    if not resolved.is_file():
        raise StrictCFPreparationError(f"missing cutover manifest: {resolved}")
    digest = file_sha256(resolved)
    if expected_sha256 is not None and digest != expected_sha256:
        raise StrictCFPreparationError(
            f"cutover manifest hash {digest} != {expected_sha256}"
        )
    raw = _load_json(resolved)
    if not isinstance(raw, Mapping):
        raise StrictCFPreparationError("API3rd cutover manifest must be an object")
    try:
        parsed = validate_historical_cutover_manifest_document(raw)
    except StrictCFSchemaError as exc:
        raise StrictCFPreparationError(str(exc)) from exc
    membership: dict[tuple[str, str], dict[str, Any]] = {}
    scopes: dict[str, dict[str, Any]] = {
        model: {} for model in sorted(HISTORICAL_API821_PROTOCOLS)
    }
    total_ids = 0
    for (model, domain), entry in parsed.items():
        membership[(model, domain)] = {
            "ids": entry["ids"],
            "manifest_path": str(resolved),
            "manifest_sha256": digest,
            "scope_ids_sha256": entry["ids_sha256"],
            "scope_row_count": entry["row_count"],
        }
        scopes[model][domain] = {
            "ids_sha256": entry["ids_sha256"],
            "row_count": entry["row_count"],
            "result_file": entry["result_file"],
        }
        total_ids += entry["row_count"]
    lineage = {
        "path": str(resolved),
        "sha256": digest,
        "schema_version": 1,
        "created_at_utc": raw["created_at_utc"],
        "purpose": raw["purpose"],
        "total_historical_ids": total_ids,
        "scopes": scopes,
    }
    return membership, lineage, raw


def load_backend_c_cutover_manifest(
    project_root: str | Path,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    """Load the external cutover source used only during preparation."""

    root = Path(project_root).resolve()
    expected = (root / "experiment_a" / "backend_c_cutover_manifest.json").resolve()
    configured = (root / HISTORICAL_API821_CUTOVER_RELATIVE_PATH).resolve()
    if configured != expected:
        raise StrictCFPreparationError("canonical external cutover path mismatch")
    membership, lineage, _ = _load_cutover_manifest_path(
        configured, expected_path=expected
    )
    return membership, lineage


def load_frozen_backend_c_cutover_manifest(
    run_root: str | Path,
    manifest: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    """Load only the manifest-bound run-local cutover snapshot."""

    root = Path(run_root).resolve(strict=True)
    entry = manifest["artifacts"]["historical_cutover_manifest"]
    path = assert_path_within_run(root, entry["path"], must_exist=True)
    membership, lineage, _ = _load_cutover_manifest_path(
        path, expected_sha256=entry["sha256"]
    )
    return membership, lineage


def _load_results(
    result_paths: Mapping[str, Mapping[str, str | Path]],
) -> tuple[
    dict[tuple[str, str], dict[str, dict[str, Any]]],
    dict[str, dict[str, dict[str, Any]]],
]:
    paths = normalize_result_paths(result_paths)
    results: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    lineage: dict[str, dict[str, dict[str, Any]]] = {}
    for model in MODELS:
        lineage[model] = {}
        for domain in DOMAINS:
            path = paths[model][domain]
            raw = _load_json(path)
            if not isinstance(raw, list):
                raise StrictCFPreparationError(f"result file must contain a list: {path}")
            by_id: dict[str, dict[str, Any]] = {}
            for index, value in enumerate(raw):
                if not isinstance(value, Mapping):
                    raise StrictCFPreparationError(f"result row {path}:{index + 1} is not an object")
                row = dict(value)
                item_id = str(row.get("id", ""))
                if not item_id:
                    raise StrictCFPreparationError(f"result row {path}:{index + 1} has no ID")
                if item_id in by_id:
                    raise StrictCFPreparationError(f"duplicate result ID in {model}/{domain}: {item_id}")
                by_id[item_id] = row
            results[(model, domain)] = by_id
            lineage[model][domain] = {
                "path": str(path),
                "sha256": file_sha256(path),
                "row_count": len(by_id),
            }
    return results, lineage


def _load_debug_index(
    debug_dir: str | Path,
    expected_ids: Mapping[tuple[str, str], set[str]],
) -> tuple[
    dict[tuple[str, str, str], Path],
    dict[str, Any],
]:
    directory = Path(debug_dir).resolve()
    if not directory.is_dir():
        raise StrictCFPreparationError(f"debug directory does not exist: {directory}")
    index: dict[tuple[str, str, str], Path] = {}
    scoped_ids = {scope: set() for scope in expected_ids}
    candidate_files = sorted(directory.glob("*.json"))
    for path in candidate_files:
        value = _load_json(path)
        if not isinstance(value, Mapping):
            raise StrictCFPreparationError(f"debug record is not an object: {path}")
        record = dict(value)
        model = str(record.get("model", ""))
        domain = str(record.get("domain", "")).lower()
        if (model, domain) not in expected_ids:
            continue
        item_id = str(record.get("id", ""))
        if not item_id:
            raise StrictCFPreparationError(f"debug record has no ID: {path}")
        key = (model, domain, item_id)
        if key in index:
            raise StrictCFPreparationError(f"duplicate debug key {key}: {path}")
        index[key] = path
        scoped_ids[(model, domain)].add(item_id)

    for scope, result_ids in expected_ids.items():
        debug_ids = scoped_ids[scope]
        if debug_ids != result_ids:
            raise StrictCFPreparationError(
                f"result/debug join mismatch for {scope[0]}/{scope[1]}: "
                f"result_only={len(result_ids - debug_ids)}, "
                f"debug_only={len(debug_ids - result_ids)}"
            )
    return index, {
        "path": str(directory),
        "scoped_file_count": len(index),
        "directory_entry_count": len(candidate_files),
    }


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrictCFPreparationError(f"{label} must be a non-boolean number")
    number = float(value)
    if not math.isfinite(number):
        raise StrictCFPreparationError(f"{label} must be finite")
    return number


def _same_number(left: Any, right: Any, label: str) -> None:
    a = _finite_number(left, label)
    b = _finite_number(right, label)
    if not math.isclose(a, b, rel_tol=0.0, abs_tol=1e-12):
        raise StrictCFPreparationError(f"{label} parity failure: {a!r} != {b!r}")


def _validate_level_parity_and_recompute(
    *,
    model: str,
    domain: str,
    item_id: str,
    result: Mapping[str, Any],
    debug: Mapping[str, Any],
    recompute_actual: bool,
) -> None:
    result_levels = result.get("levels")
    debug_levels = debug.get("level_metrics")
    prompts = debug.get("prompts")
    outputs = debug.get("outputs")
    if not all(isinstance(value, Mapping) for value in (result_levels, debug_levels, prompts, outputs)):
        raise StrictCFPreparationError(
            f"missing result/debug levels/prompts/outputs for {model}/{domain}/{item_id}"
        )
    if set(prompts) != set(LEVELS) or set(outputs) != set(LEVELS):
        raise StrictCFPreparationError(
            f"full L1-L5 prompt/output keys required for {model}/{domain}/{item_id}"
        )
    for level in LEVELS:
        result_metric = result_levels.get(level)
        debug_metric = debug_levels.get(level)
        if not isinstance(result_metric, Mapping) or not isinstance(debug_metric, Mapping):
            raise StrictCFPreparationError(
                f"missing {level} metrics for {model}/{domain}/{item_id}"
            )
        prompt = prompts[level]
        output = outputs[level]
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(output, str) or not output.strip():
            raise StrictCFPreparationError(
                f"empty {level} actual text for {model}/{domain}/{item_id}"
            )
        _same_number(
            result_metric.get("actual_ratio"),
            debug_metric.get("actual_ratio"),
            f"{model}/{domain}/{item_id}/{level}.actual_ratio",
        )
        if result_metric.get("output_chars") != len(output) or debug_metric.get("output_chars") != len(output):
            raise StrictCFPreparationError(
                f"output length parity failure for {model}/{domain}/{item_id}/{level}"
            )
        result_pc = result_metric.get("per_compressor")
        debug_pc = debug_metric.get("per_compressor")
        if not isinstance(result_pc, Mapping) or not isinstance(debug_pc, Mapping):
            raise StrictCFPreparationError(
                f"missing per-compressor metrics for {model}/{domain}/{item_id}/{level}"
            )
        if set(result_pc) != set(COMPRESSORS) or set(debug_pc) != set(COMPRESSORS):
            raise StrictCFPreparationError(
                f"incomplete compressors for {model}/{domain}/{item_id}/{level}"
            )
        for compressor in COMPRESSORS:
            _same_number(
                result_pc[compressor].get("actual_ratio"),
                debug_pc[compressor].get("actual_ratio"),
                f"{model}/{domain}/{item_id}/{level}/{compressor}.actual_ratio",
            )
        if recompute_actual:
            profile = information_gain_profile(prompt, output, COMPRESSORS)
            _same_number(
                result_metric.get("actual_ratio"),
                profile.aggregate.contribution_ratio,
                f"recomputed {model}/{domain}/{item_id}/{level}.actual_ratio",
            )
            for compressor in COMPRESSORS:
                _same_number(
                    result_pc[compressor].get("actual_ratio"),
                    profile.per_compressor[compressor]["contribution_ratio"],
                    f"recomputed {model}/{domain}/{item_id}/{level}/{compressor}.actual_ratio",
                )


def _source_for_result(
    catalog: Mapping[str, Mapping[str, Mapping[str, Any]]],
    domain: str,
    result: Mapping[str, Any],
) -> Mapping[str, Any]:
    item_id = str(result.get("id", ""))
    source = catalog[domain].get(item_id)
    if source is None:
        raise StrictCFPreparationError(f"result ID has no source row: {domain}/{item_id}")
    return source


def _result_protocol_is_exact(result: Mapping[str, Any], model: str) -> bool:
    api = result.get("_api")
    protocol = MODEL_PROTOCOLS[model]
    if not isinstance(api, Mapping) or (
        api.get("route") != protocol["config_route"]
        or api.get("gateway") != protocol["gateway"]
        or api.get("max_output_tokens") != protocol["max_output_tokens"]
        or api.get("provenance_in_debug") is not True
    ):
        return False
    statuses = api.get("main_statuses")
    return (
        isinstance(statuses, Mapping)
        and set(statuses) == set(MAIN_CALL_LABELS)
        and all(statuses[label] == "completed" for label in MAIN_CALL_LABELS)
    )


def _result_protocol_is_historical_backend_b(
    result: Mapping[str, Any], model: str
) -> bool:
    protocol = HISTORICAL_API821_PROTOCOLS.get(model)
    api = result.get("_api")
    if protocol is None or not isinstance(api, Mapping) or (
        api.get("route") != "backend_b"
        or api.get("gateway") != protocol["gateway"]
        or api.get("max_output_tokens") != protocol["max_output_tokens"]
        or api.get("provenance_in_debug") is not True
    ):
        return False
    statuses = api.get("main_statuses")
    return (
        isinstance(statuses, Mapping)
        and set(statuses) == set(MAIN_CALL_LABELS)
        and all(statuses[label] == "completed" for label in MAIN_CALL_LABELS)
    )


def _actual_candidate_item(
    *,
    model: str,
    domain: str,
    result: Mapping[str, Any],
    debug_path: Path,
    debug: Mapping[str, Any],
    source: Mapping[str, Any],
    project_root: Path,
    recompute_actual: bool,
    seen_response_ids: set[str],
    historical_cutover_scope: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return any source-matched valid actual item, explicitly tiered."""

    # Cross-item response-ID collisions are resolved symmetrically only after all
    # candidates are collected; never mutate a first-wins registry here.
    del seen_response_ids
    item_id = str(result.get("id", ""))
    if (
        str(debug.get("model")) != model
        or str(debug.get("domain", "")).lower() != domain
        or str(debug.get("id")) != item_id
    ):
        raise StrictCFPreparationError(
            f"result/debug identity mismatch for {model}/{domain}/{item_id}"
        )
    quality_reason = _actual_text_quality_reason(debug)
    if quality_reason is not None:
        return None, quality_reason

    expected_hash = source["source_text_sha256"]
    result_hash = result.get("source_text_sha256")
    debug_source = debug.get("source")
    debug_hash = (
        debug_source.get("text_sha256") if isinstance(debug_source, Mapping) else None
    )
    for label, observed in (("result", result_hash), ("debug", debug_hash)):
        if observed is not None and observed != expected_hash:
            raise StrictCFPreparationError(
                f"{label} source hash mismatch for {model}/{domain}/{item_id}"
            )
    for field in ("source_id", "source_index"):
        if field in result and result[field] is not None and result[field] != source[field]:
            raise StrictCFPreparationError(
                f"{field} mismatch for {model}/{domain}/{item_id}"
            )

    _validate_level_parity_and_recompute(
        model=model,
        domain=domain,
        item_id=item_id,
        result=result,
        debug=debug,
        recompute_actual=recompute_actual,
    )

    provenance_tier = PROVENANCE_TIER_LEGACY_UNATTESTED
    actual_provenance: dict[str, Any] | None = None
    historical_cutover_attestation: dict[str, Any] | None = None
    provenance_hash: str | None = None
    source_metadata_exact = (
        result_hash == expected_hash
        and debug_hash == expected_hash
        and result.get("source_id") == source["source_id"]
        and "source_index" in result
        and result.get("source_index") == source["source_index"]
    )
    provenance = debug.get("api_provenance")
    item_response_ids: set[str] = set()
    validated_provenance: dict[str, Any] | None = None
    historical_provenance: dict[str, Any] | None = None
    # Call IDs are independently attestable even when source/protocol/cutover
    # membership is insufficient for strict status. They still participate in
    # the symmetric global collision registry.
    if isinstance(provenance, Mapping):
        current_ids: set[str] = set()
        try:
            validate_actual_item_provenance(
                provenance,
                expected_model=model,
                project_root=project_root,
                seen_response_ids=current_ids,
                path=f"api_provenance[{model}/{domain}/{item_id}]",
            )
        except StrictCFSchemaError:
            historical_ids: set[str] = set()
            try:
                validate_historical_backend_b_actual_item_provenance(
                    provenance,
                    expected_model=model,
                    seen_response_ids=historical_ids,
                    path=f"historical_backend_b[{model}/{domain}/{item_id}]",
                )
            except StrictCFSchemaError:
                pass
            else:
                item_response_ids = historical_ids
                historical_provenance = {
                    "config": dict(provenance["config"]),
                    "main_calls": {
                        label: dict(provenance["main_calls"][label])
                        for label in MAIN_CALL_LABELS
                    },
                }
        else:
            item_response_ids = current_ids
            validated_provenance = {
                "config": dict(provenance["config"]),
                "main_calls": {
                    label: dict(provenance["main_calls"][label])
                    for label in MAIN_CALL_LABELS
                },
            }
    if (
        validated_provenance is not None
        and source_metadata_exact
        and _result_protocol_is_exact(result, model)
    ):
        provenance_tier = PROVENANCE_TIER_EXACT
        actual_provenance = validated_provenance
        provenance_hash = canonical_row_sha256(actual_provenance)
    elif (
        historical_provenance is not None
        and source_metadata_exact
        and source.get("strict_canonical_for_text", True) is True
        and _result_protocol_is_historical_backend_b(result, model)
        and historical_cutover_scope is not None
        and item_id in historical_cutover_scope.get("ids", ())
    ):
        historical_cutover_attestation = {
            "manifest_path": historical_cutover_scope.get("manifest_path"),
            "manifest_sha256": historical_cutover_scope.get("manifest_sha256"),
            "scope_ids_sha256": historical_cutover_scope.get("scope_ids_sha256"),
            "scope_row_count": historical_cutover_scope.get("scope_row_count"),
            "generation_model": model,
            "domain": domain,
            "id": item_id,
        }
        validate_historical_cutover_attestation(
            historical_cutover_attestation,
            expected_model=model,
            expected_domain=domain,
            expected_id=item_id,
            path=f"historical_cutover[{model}/{domain}/{item_id}]",
        )
        provenance_tier = PROVENANCE_TIER_HISTORICAL_API821
        actual_provenance = historical_provenance
        provenance_hash = canonical_row_sha256(
            {
                "api_provenance": actual_provenance,
                "cutover_attestation": historical_cutover_attestation,
                "provenance_tier": provenance_tier,
            }
        )

    source_result_hash = canonical_row_sha256(result)
    source_debug_hash = canonical_row_sha256(debug)
    source_identity = {
        field: source[field]
        for field in ("id", "source_id", "source_index", "source_text_sha256")
    }
    result_actual = {
        "levels": {
            level: dict(result["levels"][level]) for level in LEVELS
        }
    }
    debug_actual = {
        "prompts": {level: debug["prompts"][level] for level in LEVELS},
        "outputs": {level: debug["outputs"][level] for level in LEVELS},
        "level_metrics": {
            level: dict(debug["level_metrics"][level]) for level in LEVELS
        },
    }
    return {
        "model": model,
        "domain": domain,
        "id": item_id,
        "source": source_identity,
        "result": result_actual,
        "debug": debug_actual,
        "debug_path": debug_path,
        "source_result_row_sha256": source_result_hash,
        "source_debug_row_sha256": source_debug_hash,
        "actual_provenance": actual_provenance,
        "historical_cutover_attestation": historical_cutover_attestation,
        "item_provenance_sha256": provenance_hash,
        "_actual_response_ids": tuple(sorted(item_response_ids)),
        "_strict_canonical_for_text": bool(
            source.get("strict_canonical_for_text", True)
        ),
        "_strict_canonical_id": source.get("strict_canonical_id", source["id"]),
        "provenance_tier": provenance_tier,
        "verification_tier": (
            "recomputed_actual_and_per_compressor"
            if recompute_actual
            else "stored_result_debug_actual_parity"
        ),
    }, None


def _eligible_item(
    **kwargs: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Compatibility wrapper returning only strictly attested candidates."""

    candidate, reason = _actual_candidate_item(**kwargs)
    if candidate is None:
        return None, reason
    if candidate["provenance_tier"] not in STRICT_ACTUAL_PROVENANCE_TIERS:
        return None, PROVENANCE_TIER_LEGACY_UNATTESTED
    if not candidate.get("_strict_canonical_for_text", True):
        return None, "duplicate_text_noncanonical"
    return candidate, None


def select_common_source_hashes(
    eligible: Mapping[tuple[str, str], Mapping[str, Any]],
    excluded_hashes: Iterable[str],
    *,
    per_domain: int = EXPECTED_SOURCES_PER_DOMAIN,
) -> dict[str, tuple[str, ...]]:
    """Intersect five model cohorts and deterministically SHA-rank each domain."""

    if type(per_domain) is not int or per_domain <= 0:
        raise ValueError("per_domain must be a positive integer")
    excluded = frozenset(excluded_hashes)
    selected: dict[str, tuple[str, ...]] = {}
    for domain in DOMAINS:
        sets = [set(eligible[(model, domain)]) for model in MODELS]
        common = set.intersection(*sets) - excluded
        if len(common) < per_domain:
            raise StrictCFPreparationError(
                f"{domain} has only {len(common)} common non-pilot eligible sources; "
                f"need exactly {per_domain}"
            )
        ranked = sorted(
            common,
            key=lambda digest: (deterministic_selection_rank(domain, digest), digest),
        )
        selected[domain] = tuple(ranked[:per_domain])
    return selected


def verify_selected_actual_metrics(
    eligible: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    selected: Mapping[str, Iterable[str]],
) -> None:
    """Recompute all 20k selected level metrics before any snapshot is written."""

    verified_items = 0
    for domain in DOMAINS:
        for source_hash in selected[domain]:
            for model in MODELS:
                item = eligible[(model, domain)].get(source_hash)
                if item is None:
                    raise StrictCFPreparationError(
                        f"selected source missing during metric verification: "
                        f"{model}/{domain}/{source_hash}"
                    )
                _validate_level_parity_and_recompute(
                    model=model,
                    domain=domain,
                    item_id=item["id"],
                    result=item["result"],
                    debug=item["debug"],
                    recompute_actual=True,
                )
                verified_items += 1
    if verified_items != EXPECTED_MODEL_ITEMS:
        raise StrictCFPreparationError(
            f"selected metric verification covered {verified_items} model-items; "
            f"expected {EXPECTED_MODEL_ITEMS}"
        )


def partition_candidate_provenance(
    candidates: Mapping[tuple[str, str], Mapping[str, dict[str, Any]]],
) -> tuple[
    dict[tuple[str, str], dict[str, dict[str, Any]]],
    dict[str, Any],
]:
    """Symmetrically downgrade every owner of a reused historical response ID."""

    eligible = {scope: {} for scope in candidates}
    owners: dict[str, list[tuple[tuple[str, str], str]]] = {}
    for scope, scope_items in candidates.items():
        for candidate_key, item in scope_items.items():
            for response_id in item.get("_actual_response_ids", ()):
                owners.setdefault(response_id, []).append((scope, candidate_key))
    colliding_ids = {
        response_id for response_id, locations in owners.items() if len(locations) > 1
    }
    collision_owners: set[tuple[tuple[str, str], str]] = set()
    for response_id in colliding_ids:
        collision_owners.update(owners[response_id])
    for scope, scope_items in candidates.items():
        for candidate_key, item in scope_items.items():
            item.pop("_actual_response_ids", None)
            collided = (scope, candidate_key) in collision_owners
            item["_collision_downgraded"] = collided
            if collided:
                item["provenance_tier"] = PROVENANCE_TIER_LEGACY_UNATTESTED
                item["actual_provenance"] = None
                item["historical_cutover_attestation"] = None
                item["item_provenance_sha256"] = None
            if (
                item["provenance_tier"] in STRICT_ACTUAL_PROVENANCE_TIERS
                and item.get("_strict_canonical_for_text", True)
            ):
                source_hash = item["source"]["source_text_sha256"]
                if source_hash in eligible[scope]:
                    raise StrictCFPreparationError(
                        f"multiple strict-canonical IDs for {scope[0]}/{scope[1]}/"
                        f"{source_hash}"
                    )
                eligible[scope][source_hash] = item
    accepted_ids = {
        response_id
        for response_id, locations in owners.items()
        if len(locations) == 1
        and candidates[locations[0][0]][locations[0][1]]["provenance_tier"]
        in STRICT_ACTUAL_PROVENANCE_TIERS
    }
    report = {
        "validated_unique_response_ids": len(accepted_ids),
        "response_id_count": len(colliding_ids),
        "candidate_count": len(collision_owners),
        "response_id_sha256": sorted(
            hashlib.sha256(response_id.encode("utf-8")).hexdigest()
            for response_id in colliding_ids
        ),
    }
    return eligible, report


def collect_eligible_items(
    *,
    data_paths: Mapping[str, str | Path],
    result_paths: Mapping[str, Mapping[str, str | Path]],
    debug_dir: str | Path,
    project_root: str | Path = PROJECT,
    recompute_actual: bool = False,
    return_candidates: bool = False,
) -> Any:
    """Audit explicit scopes; optionally return the full current actual corpus."""

    root = Path(project_root).resolve()
    catalog, source_lineage = load_source_catalog(data_paths)
    historical_cutover, cutover_lineage = load_backend_c_cutover_manifest(root)
    results, result_lineage = _load_results(result_paths)
    expected_ids = {scope: set(rows) for scope, rows in results.items()}
    debug_index, debug_lineage = _load_debug_index(debug_dir, expected_ids)
    eligible: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    candidates: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    rejections: dict[str, Counter[str]] = {}
    seen_response_ids: set[str] = set()
    for model in MODELS:
        for domain in DOMAINS:
            scope = (model, domain)
            eligible[scope] = {}
            candidates[scope] = {}
            counter: Counter[str] = Counter()
            for item_id, result in results[scope].items():
                debug_path = debug_index.pop((model, domain, item_id))
                loaded_debug = _load_json(debug_path)
                if not isinstance(loaded_debug, Mapping):
                    raise StrictCFPreparationError(
                        f"debug record is not an object: {debug_path}"
                    )
                debug = dict(loaded_debug)
                source = _source_for_result(catalog, domain, result)
                item, reason = _actual_candidate_item(
                    model=model,
                    domain=domain,
                    result=result,
                    debug_path=debug_path,
                    debug=debug,
                    source=source,
                    project_root=root,
                    recompute_actual=recompute_actual,
                    seen_response_ids=seen_response_ids,
                    historical_cutover_scope=historical_cutover.get(scope),
                )
                if item is None:
                    counter[reason or "invalid_actual_candidate"] += 1
                    continue
                source_hash = source["source_text_sha256"]
                candidate_key = f"{source_hash}\0{item_id}"
                if candidate_key in candidates[scope]:
                    raise StrictCFPreparationError(
                        f"duplicate actual model-item identity for {model}/{domain}: "
                        f"{item_id}/{source_hash}"
                    )
                candidates[scope][candidate_key] = item
            rejections[f"{model}/{domain}"] = counter

    if debug_index:
        raise StrictCFPreparationError(
            f"internal debug projection left {len(debug_index)} unconsumed joined records"
        )
    eligible, collision_report = partition_candidate_provenance(candidates)
    for scope, scope_items in candidates.items():
        counter = rejections[f"{scope[0]}/{scope[1]}"]
        for item in scope_items.values():
            if item.pop("_collision_downgraded", False):
                counter["cross_candidate_response_id_collision"] += 1
            if not item.get("_strict_canonical_for_text", True):
                counter["duplicate_text_noncanonical"] += 1
            if item["provenance_tier"] == PROVENANCE_TIER_LEGACY_UNATTESTED:
                counter[PROVENANCE_TIER_LEGACY_UNATTESTED] += 1

    lineage = {
        "source_inputs": source_lineage,
        "result_inputs": result_lineage,
        "debug_input": debug_lineage,
        "backend_c_cutover_manifest": cutover_lineage,
        "validated_unique_response_ids": collision_report[
            "validated_unique_response_ids"
        ],
        "cross_candidate_response_id_collisions": {
            key: collision_report[key]
            for key in ("response_id_count", "candidate_count", "response_id_sha256")
        },
        "strict_eligibility_counts": {
            f"{model}/{domain}": len(eligible[(model, domain)])
            for model in MODELS
            for domain in DOMAINS
        },
        "strict_eligibility_provenance_tiers": dict(
            sorted(
                Counter(
                    item["provenance_tier"]
                    for scope in eligible.values()
                    for item in scope.values()
                ).items()
            )
        ),
        "full_actual_candidate_counts": {
            f"{model}/{domain}": len(candidates[(model, domain)])
            for model in MODELS
            for domain in DOMAINS
        },
        "full_actual_provenance_tiers": dict(
            sorted(
                Counter(
                    item["provenance_tier"]
                    for scope in candidates.values()
                    for item in scope.values()
                ).items()
            )
        ),
        "rejections": {
            scope: dict(sorted(counter.items())) for scope, counter in rejections.items()
        },
    }
    if return_candidates:
        return eligible, candidates, lineage
    return eligible, lineage


def bind_historical_candidates_to_frozen_cutover(
    candidates: Mapping[tuple[str, str], Mapping[str, dict[str, Any]]],
    *,
    frozen_path: str | Path,
    frozen_sha256: str,
    frozen_membership: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[
    dict[tuple[str, str], dict[str, dict[str, Any]]],
    dict[tuple[str, str], dict[str, dict[str, Any]]],
    int,
]:
    """Return detached full/strict maps rebound to one run-local cutover copy."""

    path = Path(frozen_path).resolve()
    rebound = 0
    detached_candidates: dict[tuple[str, str], dict[str, dict[str, Any]]] = {
        scope: {} for scope in candidates
    }
    detached_eligible: dict[tuple[str, str], dict[str, dict[str, Any]]] = {
        scope: {} for scope in candidates
    }

    def detach(item: Mapping[str, Any], model: str, domain: str) -> dict[str, Any]:
        result = copy.deepcopy(dict(item))
        if result["provenance_tier"] == PROVENANCE_TIER_HISTORICAL_API821:
            scope = frozen_membership.get((model, domain))
            if scope is None or result["id"] not in scope["ids"]:
                raise StrictCFPreparationError(
                    f"historical candidate left frozen cutover scope: "
                    f"{model}/{domain}/{result['id']}"
                )
            attestation = {
                "manifest_path": str(path),
                "manifest_sha256": frozen_sha256,
                "scope_ids_sha256": scope["scope_ids_sha256"],
                "scope_row_count": scope["scope_row_count"],
                "generation_model": model,
                "domain": domain,
                "id": result["id"],
            }
            validate_historical_cutover_attestation(
                attestation,
                expected_model=model,
                expected_domain=domain,
                expected_id=result["id"],
            )
            result["historical_cutover_attestation"] = attestation
            result["item_provenance_sha256"] = canonical_row_sha256(
                {
                    "api_provenance": result["actual_provenance"],
                    "cutover_attestation": attestation,
                    "provenance_tier": PROVENANCE_TIER_HISTORICAL_API821,
                }
            )
        return result

    for (model, domain), scope_items in candidates.items():
        for candidate_key, item in scope_items.items():
            full_item = detach(item, model, domain)
            detached_candidates[(model, domain)][candidate_key] = full_item
            if full_item["provenance_tier"] == PROVENANCE_TIER_HISTORICAL_API821:
                rebound += 1
            if (
                full_item["provenance_tier"] in STRICT_ACTUAL_PROVENANCE_TIERS
                and full_item.get("_strict_canonical_for_text", True)
            ):
                source_hash = full_item["source"]["source_text_sha256"]
                if source_hash in detached_eligible[(model, domain)]:
                    raise StrictCFPreparationError(
                        f"multiple rebound canonical items for {model}/{domain}/{source_hash}"
                    )
                # Rebind independently rather than relying on candidate/eligible aliasing.
                detached_eligible[(model, domain)][source_hash] = detach(
                    item, model, domain
                )
    return detached_candidates, detached_eligible, rebound


def _build_actual_row(
    item: Mapping[str, Any],
    level: str,
    *,
    verification_tier: str | None = None,
) -> dict[str, Any]:
    model = item["model"]
    domain = item["domain"]
    source = item["source"]
    result = item["result"]
    debug = item["debug"]
    metrics = result["levels"][level]
    debug_prompts = debug["prompts"]
    debug_outputs = debug["outputs"]
    per_compressor = {
        compressor: {
            "actual_ratio": metrics["per_compressor"][compressor]["actual_ratio"],
            "legacy_shared_baseline_mean": metrics["per_compressor"][compressor].get("baseline_mean"),
            "legacy_shared_excess_ratio": metrics["per_compressor"][compressor].get("excess_ratio"),
        }
        for compressor in COMPRESSORS
    }
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "row_type": "actual_level",
        "semantic_key": [],
        "generation_model": model,
        "domain": domain,
        "id": source["id"],
        "source_id": source["source_id"],
        "source_index": source["source_index"],
        "source_text_sha256": source["source_text_sha256"],
        "level": level,
        "source_cluster": source_cluster_key(domain, source["source_text_sha256"]),
        "provenance_tier": item["provenance_tier"],
        "verification_tier": verification_tier or item["verification_tier"],
        "actual": {
            "prompt": debug_prompts[level],
            "output": debug_outputs[level],
            "output_chars": len(debug_outputs[level]),
            "actual_ratio": metrics["actual_ratio"],
            "per_compressor": per_compressor,
            "legacy_shared_baseline_mean": metrics.get("baseline_mean"),
            "legacy_shared_excess_ratio": metrics.get("excess_ratio"),
            "legacy_shared_baseline_n_valid": metrics.get("baseline_n_valid"),
            "metric_status": dict(ACTUAL_METRIC_STATUS),
            "generation_provenance": (
                item["actual_provenance"]["main_calls"][LEVEL_MAIN_CALL[level]]
                if item["provenance_tier"] == PROVENANCE_TIER_EXACT
                else {
                    "call": item["actual_provenance"]["main_calls"][
                        LEVEL_MAIN_CALL[level]
                    ],
                    "cutover_attestation": item[
                        "historical_cutover_attestation"
                    ],
                }
                if item["provenance_tier"]
                == PROVENANCE_TIER_HISTORICAL_API821
                else None
            ),
            "item_provenance_sha256": item["item_provenance_sha256"],
            "source_result_row_sha256": item["source_result_row_sha256"],
            "source_debug_row_sha256": item["source_debug_row_sha256"],
        },
        "actual_pair_sha256": "",
    }
    row["semantic_key"] = level_key(row)
    row["actual_pair_sha256"] = actual_pair_sha256(row)
    validate_actual_snapshot_row(row)
    return row


def _build_model_item_row(
    item: Mapping[str, Any],
    level_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    model = item["model"]
    domain = item["domain"]
    source = item["source"]
    source_hash = source["source_text_sha256"]
    return {
        "schema_version": SCHEMA_VERSION,
        "row_type": "model_item",
        "model_item_key": model_item_key(
            model, domain, source["id"], source_hash
        ),
        "generation_model": model,
        "domain": domain,
        "id": source["id"],
        "source_id": source["source_id"],
        "source_index": source["source_index"],
        "source_text_sha256": source_hash,
        "source_cluster": source_cluster_key(domain, source_hash),
        "semantic_keys": [row["semantic_key"] for row in level_rows],
        "actual_level_row_sha256": [
            canonical_row_sha256(row) for row in level_rows
        ],
        "actual_api_provenance": item["actual_provenance"],
        "provenance_tier": item["provenance_tier"],
        "historical_cutover_attestation": item[
            "historical_cutover_attestation"
        ],
        "item_provenance_sha256": item["item_provenance_sha256"],
        "source_result_row_sha256": item["source_result_row_sha256"],
        "source_debug_row_sha256": item["source_debug_row_sha256"],
    }


def build_snapshots(
    eligible: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    selected: Mapping[str, Iterable[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build canonical cluster, model-item, and 20k actual-level rows."""

    clusters: list[dict[str, Any]] = []
    model_items: list[dict[str, Any]] = []
    actual_rows: list[dict[str, Any]] = []
    seen_semantic: set[tuple[str, ...]] = set()
    for domain in DOMAINS:
        selected_hashes = tuple(selected[domain])
        for source_hash in selected_hashes:
            representative = eligible[(MODELS[0], domain)][source_hash]["source"]
            clusters.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "row_type": "source_cluster",
                    "source_cluster": source_cluster_key(domain, source_hash),
                    "domain": domain,
                    "id": representative["id"],
                    "source_id": representative["source_id"],
                    "source_index": representative["source_index"],
                    "source_text_sha256": source_hash,
                    "selection_rank": deterministic_selection_rank(domain, source_hash),
                }
            )
            for model in MODELS:
                item = eligible[(model, domain)].get(source_hash)
                if item is None:
                    raise StrictCFPreparationError(
                        f"selected source vanished from {model}/{domain}: {source_hash}"
                    )
                source = item["source"]
                if (
                    source["id"] != representative["id"]
                    or source["source_id"] != representative["source_id"]
                    or source["source_index"] != representative["source_index"]
                ):
                    raise StrictCFPreparationError(
                        f"cross-model source identity mismatch for {domain}/{source_hash}"
                    )
                level_rows = [
                    _build_actual_row(
                        item,
                        level,
                        verification_tier="recomputed_actual_and_per_compressor",
                    )
                    for level in LEVELS
                ]
                for row in level_rows:
                    validate_actual_snapshot_row(row, seen_keys=seen_semantic)
                actual_rows.extend(level_rows)
                model_items.append(_build_model_item_row(item, level_rows))
    return clusters, model_items, actual_rows


def build_full_snapshots(
    eligible: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    *,
    excluded_hashes: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the full model-item/actual graph, including explicit legacy nulls."""

    excluded = frozenset(excluded_hashes)
    model_items: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for model in MODELS:
        for domain in DOMAINS:
            ordered = sorted(
                eligible[(model, domain)].values(),
                key=lambda item: (
                    deterministic_selection_rank(
                        domain, item["source"]["source_text_sha256"]
                    ),
                    item["source"]["source_text_sha256"],
                    item["id"],
                ),
            )
            for item in ordered:
                source_hash = item["source"]["source_text_sha256"]
                if source_hash in excluded:
                    continue
                level_rows = [_build_actual_row(item, level) for level in LEVELS]
                for row in level_rows:
                    validate_actual_snapshot_row(row, seen_keys=seen)
                rows.extend(level_rows)
                model_items.append(_build_model_item_row(item, level_rows))
    if (
        not rows
        or len(rows) % len(LEVELS) != 0
        or len(model_items) * len(LEVELS) != len(rows)
    ):
        raise StrictCFPreparationError(
            "full-corpus snapshots must form a complete model-item/L1-L5 graph"
        )
    return model_items, rows


def build_full_actual_snapshot(
    eligible: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    *,
    excluded_hashes: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning the full graph's actual rows."""

    _, rows = build_full_snapshots(eligible, excluded_hashes=excluded_hashes)
    return rows


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_canonical_runs_root(
    value: str | Path, project_root: str | Path
) -> Path:
    root = Path(value).resolve()
    expected = canonical_runs_root(project_root)
    if root != expected:
        raise StrictCFPreparationError(
            f"runs_root must resolve exactly to {expected}, got {root}"
        )
    return root


def _write_new_json(path: Path, value: Any) -> storage.AtomicWriteResult:
    if path.exists():
        raise StrictCFPreparationError(f"refusing to replace immutable file: {path}")
    return storage.atomic_replace_json(path, value)


def _write_new_jsonl(path: Path, rows: Iterable[Any]) -> storage.AtomicWriteResult:
    if path.exists():
        raise StrictCFPreparationError(f"refusing to replace immutable file: {path}")
    return storage.atomic_replace_jsonl(path, rows)


def _creation_inventory(project_root: Path) -> dict[str, Any]:
    code_specs = (
        ("schema", HERE / "strict_cf_schema.py"),
        ("preparation", HERE / "prepare_strict_cf_v1.py"),
        ("routes", HERE / "strict_cf_routes.py"),
        ("transport", HERE / "strict_cf_transport.py"),
        ("route_bundle", HERE / "strict_cf_route_bundle.py"),
        ("route_registration", HERE / "register_strict_cf_route_v1.py"),
        ("runner", HERE / "run_strict_cf_v1.py"),
        ("launcher", HERE / "run_strict_cf_parallel.py"),
        ("finalizer", HERE / "finalize_strict_cf_v1.py"),
        ("actual_analysis", HERE / "analyze_strict_cf_v1.py"),
        ("metrics", project_root / "human_contribution" / "metrics.py"),
        ("compression", project_root / "human_contribution" / "compression.py"),
        ("outage_guard", HERE / "outage_guard.py"),
        (
            "copilot_global_slots",
            project_root / "human_contribution" / "copilot_global_slots.py",
        ),
        ("storage", project_root / "experiment_b" / "storage.py"),
    )
    client_specs: tuple[tuple[str, Path], ...] = ()

    def inventory_entry(role: str, path: Path) -> dict[str, str]:
        resolved = path.resolve()
        if not resolved.is_file():
            raise StrictCFPreparationError(
                f"missing creation inventory file for {role}: {resolved}"
            )
        return {
            "role": role,
            "path": str(resolved),
            "sha256": file_sha256(resolved),
        }

    return {
        "scoring_protocol_sha256": SCORING_PROTOCOL_SHA256,
        "code": [inventory_entry(role, path) for role, path in code_specs],
        "clients": [inventory_entry(role, path) for role, path in client_specs],
    }


@contextmanager
def preparation_lock(project_root: str | Path):
    """Exclude every legacy/new Experiment-A writer while freezing inputs."""

    lock_dir = Path(project_root).resolve() / "experiment_a" / ".locks"
    try:
        with ExitStack() as stack:
            stack.enter_context(
                storage.ProcessLock(
                    lock_dir / "maintenance.lock",
                    scope="experiment-a-strict-cf-preparation",
                    timeout=0.0,
                )
            )
            for model in MODELS:
                stack.enter_context(
                    storage.ProcessLock(
                        lock_dir / f"{model}.lock",
                        scope=f"experiment-a-strict-cf-preparation:{model}",
                        timeout=0.0,
                    )
                )
            yield
    except storage.LockError as exc:
        raise StrictCFPreparationError(
            f"Experiment A is not quiescent; cannot freeze strict-CF inputs: {exc}"
        ) from exc


def _create_run_unlocked(
    *,
    lineage_id: str,
    runs_root: str | Path,
    data_paths: Mapping[str, str | Path],
    result_paths: Mapping[str, Mapping[str, str | Path]],
    debug_dir: str | Path,
    pilot_samples_path: str | Path,
    project_root: str | Path = PROJECT,
    created_at_utc: str | None = None,
    verify_selected_actual: bool = True,
) -> Path:
    """Audit inputs, select the exact cohort, and create one immutable run."""

    lineage_id = validate_lineage_id(lineage_id)
    project = Path(project_root).resolve()
    if verify_selected_actual is not True:
        raise StrictCFPreparationError(
            "selected actual metric recomputation is mandatory and cannot be disabled"
        )
    root = _assert_canonical_runs_root(runs_root, project)
    pilot_path = Path(pilot_samples_path).resolve()
    if not pilot_path.is_file():
        raise StrictCFPreparationError(f"missing pilot sample file: {pilot_path}")
    historical_repair_evidence = validate_historical_repair_evidence(project)
    frozen_repair_evidence_bytes = {
        name: Path(entry["path"]).read_bytes()
        for name, entry in historical_repair_evidence.items()
    }
    eligible, full_actual_candidates, input_lineage = collect_eligible_items(
        data_paths=data_paths,
        result_paths=result_paths,
        debug_dir=debug_dir,
        project_root=project,
        recompute_actual=False,
        return_candidates=True,
    )
    run_dir = validate_run_dir(
        root / lineage_id,
        project_root=project,
        lineage_id=lineage_id,
    )
    if run_dir.exists():
        raise StrictCFPreparationError(f"run already exists and is immutable: {run_dir}")
    external_cutover = input_lineage.get("backend_c_cutover_manifest")
    if not isinstance(external_cutover, Mapping):
        raise StrictCFPreparationError("missing external cutover source lineage")
    external_path = Path(str(external_cutover.get("path", ""))).resolve()
    external_sha = external_cutover.get("sha256")
    external_membership, rechecked_lineage, cutover_document = (
        _load_cutover_manifest_path(
            external_path,
            expected_path=project / HISTORICAL_API821_CUTOVER_RELATIVE_PATH,
            expected_sha256=external_sha,
        )
    )
    if rechecked_lineage != external_cutover:
        raise StrictCFPreparationError(
            "external cutover source changed after eligibility collection"
        )
    frozen_cutover_bytes = storage.canonical_json_bytes(cutover_document)
    frozen_cutover_sha = storage.sha256_bytes(frozen_cutover_bytes)
    frozen_cutover_path = assert_path_within_run(
        run_dir, ARTIFACT_SPECS["historical_cutover_manifest"][0]
    )
    frozen_repair_evidence_paths = {
        "audit": assert_path_within_run(
            run_dir, ARTIFACT_SPECS["historical_repair_audit"][0]
        ),
        "method": assert_path_within_run(
            run_dir, ARTIFACT_SPECS["historical_repair_method"][0]
        ),
    }
    frozen_membership = {
        scope: {
            **entry,
            "manifest_path": str(frozen_cutover_path),
            "manifest_sha256": frozen_cutover_sha,
        }
        for scope, entry in external_membership.items()
    }
    (
        full_actual_candidates,
        eligible,
        rebound_historical_items,
    ) = bind_historical_candidates_to_frozen_cutover(
        full_actual_candidates,
        frozen_path=frozen_cutover_path,
        frozen_sha256=frozen_cutover_sha,
        frozen_membership=frozen_membership,
    )
    pilot_hashes = extract_pilot_source_hashes(_load_json(pilot_path))
    if not pilot_hashes:
        raise StrictCFPreparationError(
            "pilot exclusion extracted zero source hashes; refusing unsafe preparation"
        )
    selected = select_common_source_hashes(eligible, pilot_hashes)
    verify_selected_actual_metrics(eligible, selected)
    clusters, model_items, actual_rows = build_snapshots(eligible, selected)
    full_model_items, full_actual_rows = build_full_snapshots(
        full_actual_candidates
    )
    if (
        len(clusters) != EXPECTED_SOURCE_CLUSTERS
        or len(model_items) != EXPECTED_MODEL_ITEMS
        or len(actual_rows) != EXPECTED_LEVEL_ROWS
        or len(full_model_items) * len(LEVELS) != len(full_actual_rows)
    ):
        raise StrictCFPreparationError(
            f"snapshot count failure: clusters={len(clusters)}, "
            f"model_items={len(model_items)}, levels={len(actual_rows)}"
        )
    common_pool_counts = {
        domain: len(
            set.intersection(
                *(set(eligible[(model, domain)]) for model in MODELS)
            )
            - set(pilot_hashes)
        )
        for domain in DOMAINS
    }
    selected_item_tiers = Counter(
        eligible[(model, domain)][source_hash]["provenance_tier"]
        for domain in DOMAINS
        for source_hash in selected[domain]
        for model in MODELS
    )
    selected_level_tiers = Counter(
        row["provenance_tier"] for row in actual_rows
    )
    validate_historical_repair_selection(
        selected,
        common_pool_counts,
        selected_item_tiers,
        selected_level_tiers,
    )
    creation_inventory = _creation_inventory(project)

    timestamp = created_at_utc or _utc_now()
    # Reuse schema timestamp validation through the initial status object.
    initial_status = {
        "schema": RUN_STATUS_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "lineage_id": lineage_id,
        "updated_at_utc": timestamp,
        "state": "prepared",
        "completed_level_rows": 0,
        "adopted_calls": 0,
        "model_progress": {
            model: {
                "binding_state": "deferred",
                "execution_state": "waiting",
                "formal_pointer_sha256": None,
                "bundle_sha256": None,
                "completed_level_rows": 0,
                "adopted_calls": 0,
            }
            for model in MODELS
        },
        "events": [],
    }
    validate_run_status(initial_status, expected_lineage_id=lineage_id)

    root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise StrictCFPreparationError(
            f"run already exists and is immutable: {run_dir}"
        ) from exc

    try:
        (run_dir / "snapshots").mkdir()
        (run_dir / "final").mkdir()
        cutover_result = storage.atomic_replace_bytes(
            frozen_cutover_path,
            frozen_cutover_bytes,
        )
        if cutover_result.sha256 != frozen_cutover_sha:
            raise StrictCFPreparationError("frozen cutover write hash mismatch")
        repair_evidence_results = {
            name: storage.atomic_replace_bytes(
                frozen_repair_evidence_paths[name],
                frozen_repair_evidence_bytes[name],
            )
            for name in ("audit", "method")
        }
        for name, result in repair_evidence_results.items():
            if result.sha256 != historical_repair_evidence[name]["sha256"]:
                raise StrictCFPreparationError(
                    f"frozen historical repair {name} hash mismatch"
                )
        cluster_result = _write_new_jsonl(
            assert_path_within_run(run_dir, ARTIFACT_SPECS["source_clusters"][0]),
            clusters,
        )
        model_result = _write_new_jsonl(
            assert_path_within_run(run_dir, ARTIFACT_SPECS["model_items"][0]),
            model_items,
        )
        full_model_result = _write_new_jsonl(
            assert_path_within_run(run_dir, ARTIFACT_SPECS["full_model_items"][0]),
            full_model_items,
        )
        actual_result = _write_new_jsonl(
            assert_path_within_run(run_dir, ARTIFACT_SPECS["actual_levels"][0]),
            actual_rows,
        )
        full_actual_result = _write_new_jsonl(
            assert_path_within_run(
                run_dir, ARTIFACT_SPECS["full_actual_levels"][0]
            ),
            full_actual_rows,
        )
        selected_debug_rows = [
            {
                "generation_model": model,
                "domain": domain,
                "id": eligible[(model, domain)][source_hash]["id"],
                "path": str(eligible[(model, domain)][source_hash]["debug_path"]),
                "file_sha256": file_sha256(
                    eligible[(model, domain)][source_hash]["debug_path"]
                ),
                "row_sha256": eligible[(model, domain)][source_hash][
                    "source_debug_row_sha256"
                ],
            }
            for domain in DOMAINS
            for source_hash in selected[domain]
            for model in MODELS
        ]
        preparation_lineage = {
            "schema": LINEAGE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "lineage_id": lineage_id,
            "created_at_utc": timestamp,
            "historical_tier_semantics": _HISTORICAL_TIER_SEMANTICS,
            "inputs": {
                **input_lineage,
                "historical_repair_evidence": historical_repair_evidence,
                "pilot_samples": {
                    "path": str(pilot_path),
                    "sha256": file_sha256(pilot_path),
                    "source_hash_count": len(pilot_hashes),
                },
            },
            "frozen_inputs": {
                "historical_cutover_manifest": {
                    "path": ARTIFACT_SPECS["historical_cutover_manifest"][0],
                    "sha256": cutover_result.sha256,
                    "row_count": 1,
                    "source_lineage_only": input_lineage[
                        "backend_c_cutover_manifest"
                    ],
                },
                "historical_repair_audit": {
                    "path": ARTIFACT_SPECS["historical_repair_audit"][0],
                    "sha256": repair_evidence_results["audit"].sha256,
                    "row_count": 1,
                    "source_lineage_only": historical_repair_evidence["audit"],
                },
                "historical_repair_method": {
                    "path": ARTIFACT_SPECS["historical_repair_method"][0],
                    "sha256": repair_evidence_results["method"].sha256,
                    "row_count": 1,
                    "source_lineage_only": historical_repair_evidence["method"],
                },
            },
            "selection": {
                "seed": SELECTION_SEED,
                "algorithm": SELECTION_ALGORITHM,
                "provenance_policy": list(STRICT_ACTUAL_PROVENANCE_TIERS),
                "common_source_pool_counts": common_pool_counts,
                "excluded_pilot_source_hashes": sorted(pilot_hashes),
                "selected_source_hashes": {
                    domain: list(selected[domain]) for domain in DOMAINS
                },
            },
            "selected_debug_records": selected_debug_rows,
            "selected_debug_records_sha256": canonical_sha256(selected_debug_rows),
            "counts": {
                "source_clusters": len(clusters),
                "model_items": len(model_items),
                "full_model_items": len(full_model_items),
                "level_rows": len(actual_rows),
                "full_actual_level_rows": len(full_actual_rows),
                "historical_items_rebound_to_frozen_cutover": rebound_historical_items,
                "selected_model_item_provenance_tiers": dict(
                    sorted(selected_item_tiers.items())
                ),
                "selected_level_row_provenance_tiers": dict(
                    sorted(selected_level_tiers.items())
                ),
            },
            "creation_inventory": creation_inventory,
        }
        preparation_lineage_result = _write_new_json(
            assert_path_within_run(
                run_dir, ARTIFACT_SPECS["preparation_lineage"][0]
            ),
            preparation_lineage,
        )
        creation_hashes = {
            "preparation_lineage": preparation_lineage_result.sha256,
            "historical_cutover_manifest": cutover_result.sha256,
            "historical_repair_audit": repair_evidence_results["audit"].sha256,
            "historical_repair_method": repair_evidence_results["method"].sha256,
            "source_clusters": cluster_result.sha256,
            "model_items": model_result.sha256,
            "full_model_items": full_model_result.sha256,
            "actual_levels": actual_result.sha256,
            "full_actual_levels": full_actual_result.sha256,
        }
        artifacts = {}
        for name, (relative, row_count, required) in ARTIFACT_SPECS.items():
            actual_row_count = (
                len(full_actual_rows)
                if name == "full_actual_levels"
                else len(full_model_items)
                if name == "full_model_items"
                else row_count
            )
            artifacts[name] = {
                "path": relative,
                "row_count": actual_row_count,
                "sha256": creation_hashes.get(name),
                "required_at_creation": required,
            }
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "lineage_id": lineage_id,
            "created_at_utc": timestamp,
            "immutable": True,
            "models": list(MODELS),
            "domains": list(DOMAINS),
            "levels": list(LEVELS),
            "actual_source_protocols": strict_schema.ACTUAL_SOURCE_PROTOCOLS,
            "route_slots": strict_schema.STRICT_CF_SLOT_CONTRACTS,
            "transport": {
                "abi_version": strict_schema.TRANSPORT_ABI_VERSION,
                "abi_sha256": strict_schema.TRANSPORT_ABI_SHA256,
                "request_schema": "experiment_a.strict_cf_v1.transport_request",
                "response_schema": "experiment_a.strict_cf_v1.transport_response",
            },
            "expected_counts": {
                "source_clusters": EXPECTED_SOURCE_CLUSTERS,
                "model_items": EXPECTED_MODEL_ITEMS,
                "level_rows": EXPECTED_LEVEL_ROWS,
                "sources_per_domain": EXPECTED_SOURCES_PER_DOMAIN,
                "level_rows_per_model": strict_schema.EXPECTED_LEVEL_ROWS_PER_MODEL,
                "adopted_calls_per_level": strict_schema.EXPECTED_ADOPTED_CALLS_PER_LEVEL,
                "adopted_calls_per_model": strict_schema.EXPECTED_ADOPTED_CALLS_PER_MODEL,
                "adopted_calls_total": strict_schema.EXPECTED_ADOPTED_CALLS,
                "full_actual_level_rows": len(full_actual_rows),
            },
            "selection": {
                "algorithm": SELECTION_ALGORITHM,
                "seed": SELECTION_SEED,
            },
            "cohort": {
                "selected_source_hashes_sha256": {
                    domain: canonical_sha256(list(selected[domain]))
                    for domain in DOMAINS
                },
                "selected_model_item_provenance_tiers": dict(
                    sorted(selected_item_tiers.items())
                ),
                "selected_level_row_provenance_tiers": dict(
                    sorted(selected_level_tiers.items())
                ),
                "root_sha256": "0" * 64,
            },
            "creation_inventory": creation_inventory,
            "artifacts": artifacts,
        }
        manifest["cohort"]["root_sha256"] = strict_schema.compute_cohort_root(
            manifest
        )
        validate_historical_repair_lineage(preparation_lineage, manifest)
        validate_manifest(
            manifest,
            run_dir=run_dir,
            project_root=project,
            verify_files=True,
        )
        _write_new_json(run_dir / RUN_STATUS_PATH, initial_status)
        # Publish the immutable manifest last; its presence marks a complete
        # preparation rather than an intermediate directory.
        _write_new_json(run_dir / "manifest.json", manifest)
    except Exception:
        # The manifest is written last.  A failed creator owns this still-unpublished
        # directory and removes it; an existing immutable run is never touched.
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run_dir


def create_run(
    *,
    lineage_id: str,
    runs_root: str | Path,
    data_paths: Mapping[str, str | Path],
    result_paths: Mapping[str, Mapping[str, str | Path]],
    debug_dir: str | Path,
    pilot_samples_path: str | Path,
    project_root: str | Path = PROJECT,
    created_at_utc: str | None = None,
    verify_selected_actual: bool = True,
) -> Path:
    """Create one immutable run while all Experiment-A writers are excluded."""

    with preparation_lock(project_root):
        return _create_run_unlocked(
            lineage_id=lineage_id,
            runs_root=runs_root,
            data_paths=data_paths,
            result_paths=result_paths,
            debug_dir=debug_dir,
            pilot_samples_path=pilot_samples_path,
            project_root=project_root,
            created_at_utc=created_at_utc,
            verify_selected_actual=verify_selected_actual,
        )


def _parse_assignments(values: list[str], expected: set[str], label: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for raw in values:
        if "=" not in raw:
            raise StrictCFPreparationError(f"{label} assignment must be KEY=PATH: {raw!r}")
        key, path_text = raw.split("=", 1)
        key = key.strip().lower()
        if key not in expected or key in parsed or not path_text.strip():
            raise StrictCFPreparationError(f"invalid/duplicate {label} assignment: {raw!r}")
        parsed[key] = Path(path_text).expanduser()
    _require_exact_keys(parsed, expected, label)
    return parsed


def _parse_result_assignments(values: list[str]) -> dict[str, dict[str, Path]]:
    parsed: dict[str, dict[str, Path]] = {model: {} for model in MODELS}
    for raw in values:
        if "=" not in raw:
            raise StrictCFPreparationError(
                f"result assignment must be MODEL/DOMAIN=PATH: {raw!r}"
            )
        scope, path_text = raw.split("=", 1)
        separator = "/" if "/" in scope else ","
        parts = [part.strip() for part in scope.split(separator)]
        if len(parts) != 2:
            raise StrictCFPreparationError(
                f"result assignment must be MODEL/DOMAIN=PATH: {raw!r}"
            )
        model, domain = parts[0], parts[1].lower()
        if (
            model not in MODELS
            or domain not in DOMAINS
            or domain in parsed[model]
            or not path_text.strip()
        ):
            raise StrictCFPreparationError(f"invalid/duplicate result assignment: {raw!r}")
        parsed[model][domain] = Path(path_text).expanduser()
    normalize_result_paths(parsed)
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineage-id", required=True)
    parser.add_argument(
        "--runs-root",
        default=str(canonical_runs_root(PROJECT)),
        help="must resolve exactly to experiment_a/strict_cf_v1_1/runs",
    )
    parser.add_argument(
        "--data",
        action="append",
        default=[],
        metavar="DOMAIN=PATH",
        help="repeat exactly once for arxiv, news, patent, poetry",
    )
    parser.add_argument(
        "--result",
        action="append",
        default=[],
        metavar="MODEL/DOMAIN=PATH",
        help="repeat exactly once for every one of the 20 model/domain scopes",
    )
    parser.add_argument("--debug-dir", required=True)
    parser.add_argument("--pilot-samples", required=True)
    args = parser.parse_args(argv)
    try:
        data_paths = _parse_assignments(args.data, set(DOMAINS), "data")
        result_paths = _parse_result_assignments(args.result)
        run_dir = create_run(
            lineage_id=args.lineage_id,
            runs_root=args.runs_root,
            data_paths=data_paths,
            result_paths=result_paths,
            debug_dir=args.debug_dir,
            pilot_samples_path=args.pilot_samples,
        )
    except (StrictCFPreparationError, StrictCFSchemaError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
