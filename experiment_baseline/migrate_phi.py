# -*- coding: utf-8 -*-
"""Fail-closed, append-only migration of legacy white-box phi data to v2.

The migration is deliberately split into six commands:

``prepare``
    Freeze the authoritative Experiment A source set, reconstruct the historical
    source snapshot from its two archives, and write an immutable hash manifest.
``seed``
    Convert only source-identical legacy scores to strict v2 JSONL.  A malformed
    legacy score is not trusted: its evaluator/key pair is promoted to the queue.
``run``
    Score only entries in that explicit queue with :mod:`whitebox_core`.
``finalize``
    Require exact source/score set parity and publish immutable score, lineage,
    and legacy-compatible JSON artifacts.
``activate`` / ``rollback``
    Atomically replace (or restore) one pointer.  No Experiment A, legacy phi,
    or Experiment B file is ever rewritten.

All paths stored in manifests are absolute.  Canonical JSON, durable replacement,
fsynced append, and process locks come from ``experiment_b.storage``.  Imports of
GPU libraries remain lazy in ``whitebox_core``; in particular, prepare/seed and
all dry-runs are CPU-only.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import os
import re
import sys
import tarfile
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

if __package__ in (None, ""):
    _PROJECT_FOR_IMPORT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_FOR_IMPORT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_FOR_IMPORT))

from experiment_b import storage
from experiment_baseline import whitebox_core, whitebox_schema


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_ROOT = Path(__file__).resolve().parent
TARGET_MODELS = (
    "claude-sonnet-5",
    "gemini-3.6-flash",
    "claude-opus-4-8",
    "gpt-5.6-sol",
    "gpt-5.5",
)
DOMAINS = ("arxiv", "news", "patent", "poetry")
EVALUATORS = tuple(sorted(whitebox_core.EVAL_MODELS))
KNOWN_LEGACY_OMISSION = ("gpt-5.5", "poetry", "Petition")

PRODUCTION_COUNTS = {
    "current": 11222,
    "legacy": 7763,
    "reusable": 7552,
    "same_key_changed": 12,
    "current_only": 3658,
    "old_only": 199,
    "nominal_recompute": 3670,
    "partial_reused": 76,
    "partial_reused_four": 63,
    "partial_reused_three": 13,
    "dropped_reused_cf_slots": 89,
}
PRODUCTION_CURRENT_SCIENTIFIC_SHA256 = (
    "37a6c9a3d00111ab32e6404522e16f3b3bb8aac54d289b922c340ae91329c41f"
)
PRODUCTION_LEGACY_SCIENTIFIC_SHA256 = (
    "b669882b17f9bc12254c0b98748ecd6d71b92f0f7406fe596c43884d263115e2"
)

MANIFEST_SCHEMA = "experiment_baseline.phi_v2.prepare"
QUEUE_SCHEMA = "experiment_baseline.phi_v2.recompute_queue"
SEED_SCHEMA = "experiment_baseline.phi_v2.seed_state"
LINEAGE_SCHEMA = "experiment_baseline.phi_v2.lineage"
COMPATIBILITY_SCHEMA = "experiment_baseline.phi_v2.compatibility_index"
POINTER_SCHEMA = "experiment_baseline.phi_v2.active_pointer"
SCHEMA_VERSION = 2
LEGACY_REDUNDANT_ABS_TOL = 1e-12

_DEFAULT_RESULTS = PROJECT_ROOT / "experiment_a" / "results"
_DEFAULT_DEBUG = PROJECT_ROOT / "experiment_a" / "debug_logs"
_DEFAULT_ARCHIVES = (
    PROJECT_ROOT / "experiment_a" / "debug_logs.tar.gz",
    PROJECT_ROOT / "tmp" / "missing_logs.tar.gz",
)
_DEFAULT_LEGACY_SCORES = {
    evaluator: BASELINE_ROOT
    / "legacy_artifacts"
    / "20260818"
    / f"phi_{evaluator}.json"
    for evaluator in EVALUATORS
}
_DEFAULT_MANIFEST = BASELINE_ROOT / "v2" / "prepare_manifest.json"
_DEFAULT_POINTER = BASELINE_ROOT / "ACTIVE_PHI_V2.json"
_RESULT_RE = re.compile(r"^final_(?P<domain>.+)_5level_(?P<model>.+)\.json$")

SemanticKey = tuple[str, str, str]


class MigrationError(RuntimeError):
    """Base class for baseline-v2 migration failures."""


class PreconditionError(MigrationError):
    """An input, state, or command precondition is not satisfied."""


class InvariantError(MigrationError):
    """A scientific or storage invariant cannot be proved."""


class DuplicateKeyError(InvariantError):
    """An identical semantic key occurs more than once where uniqueness is required."""


class ConflictingKeyError(InvariantError):
    """One semantic key is associated with different canonical content."""


class HashDriftError(PreconditionError):
    """A manifest-bound file or row changed after preparation."""


class NotReadyError(PreconditionError):
    """A preceding migration stage has not completed and verified."""


def _now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(now: datetime | None = None) -> str:
    return _now(now).strftime("%Y%m%dT%H%M%S.%fZ")


def _absolute(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _reject_protected_output_paths(
    *,
    project: Path,
    artifact_root: Path,
    manifest_path: Path,
    pointer_path: Path,
    legacy_score_paths: Mapping[str, Path],
    input_paths: Iterable[Path],
) -> None:
    """Prevent configuration from turning additive migration into data mutation."""

    protected_roots = [
        (project / "experiment_a").resolve(),
        (project / "experiment_b").resolve(),
        *(path.parent.resolve() for path in legacy_score_paths.values()),
    ]
    protected_inputs = {path.resolve() for path in input_paths}
    for label, candidate in (
        ("artifact_root", artifact_root),
        ("manifest", manifest_path),
        ("active_pointer", pointer_path),
    ):
        resolved = candidate.resolve()
        if resolved in protected_inputs or any(
            _is_within(resolved, root) for root in protected_roots
        ):
            raise PreconditionError(
                f"{label} may not overwrite or live inside protected A/B/legacy data: "
                f"{resolved}"
            )


def _key_list(key: SemanticKey) -> list[str]:
    return [key[0], key[1], key[2]]


def _key_from_value(value: Any, *, path: str) -> SemanticKey:
    if not isinstance(value, list) or len(value) != 3 or not all(
        isinstance(item, str) for item in value
    ):
        raise InvariantError(f"{path}: semantic_key must be a three-string array")
    return whitebox_schema.normalize_semantic_key(*value)


def _key_id(key: SemanticKey) -> str:
    return whitebox_schema.canonical_json_text(_key_list(key))


def _semantic_key_from_debug(row: Mapping[str, Any], *, path: str) -> SemanticKey:
    try:
        return whitebox_schema.normalize_semantic_key(
            row.get("model", row.get("generation_model")),
            row.get("domain"),
            row.get("id"),
        )
    except Exception as exc:
        raise InvariantError(f"{path}: invalid semantic identity: {exc}") from exc


def _semantic_key_from_legacy(row: Mapping[str, Any], *, path: str) -> SemanticKey:
    try:
        return whitebox_schema.normalize_semantic_key(
            row.get("model", row.get("generation_model")),
            row.get("domain"),
            row.get("id"),
        )
    except Exception as exc:
        raise InvariantError(f"{path}: invalid semantic identity: {exc}") from exc


def _strict_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvariantError(f"{path}: expected a JSON object")
    return value


def _strict_load_file(path: Path) -> Any:
    if not path.is_file():
        raise PreconditionError(f"required file does not exist: {path}")
    try:
        return whitebox_schema.strict_json_loads(path.read_bytes(), path=str(path))
    except Exception as exc:
        raise InvariantError(f"cannot read strict JSON {path}: {exc}") from exc


def _strict_load_bytes(data: bytes, *, path: str) -> Any:
    try:
        return whitebox_schema.strict_json_loads(data, path=path)
    except Exception as exc:
        raise InvariantError(f"cannot read strict JSON {path}: {exc}") from exc


def _file_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PreconditionError(f"required file does not exist: {path}")
    return {
        "path": str(path),
        "sha256": storage.file_sha256(path),
        "size": path.stat().st_size,
    }


def _canonical_set_sha256(entries: Iterable[Mapping[str, Any]]) -> str:
    return storage.canonical_row_sha256(list(entries))


def _jsonl_digest(rows: Iterable[Mapping[str, Any]]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for row in rows:
        payload = storage.canonical_jsonl_row_bytes(row)
        digest.update(payload)
        size += len(payload)
    return digest.hexdigest(), size


def _canonical_jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(storage.canonical_jsonl_row_bytes(row) for row in rows)


def _write_or_verify_bytes(path: Path, payload: bytes) -> storage.AtomicWriteResult:
    expected_hash = storage.sha256_bytes(payload)
    if path.exists():
        actual_hash = storage.file_sha256(path)
        if actual_hash != expected_hash or path.stat().st_size != len(payload):
            raise HashDriftError(
                f"existing phase artifact differs from intended bytes: {path}"
            )
        return storage.AtomicWriteResult(path, actual_hash, len(payload))
    return storage.atomic_replace_bytes(path, payload)


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> storage.AtomicWriteResult:
    return _write_or_verify_bytes(path, storage.canonical_json_bytes(value))


def _write_or_verify_jsonl(
    path: Path, rows: Sequence[Mapping[str, Any]]
) -> storage.AtomicWriteResult:
    return _write_or_verify_bytes(path, _canonical_jsonl_bytes(rows))


def _payload_hash(value: Mapping[str, Any], hash_field: str) -> str:
    payload = dict(value)
    payload.pop(hash_field, None)
    return storage.canonical_row_sha256(payload)


def _add_payload_hash(value: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    result = dict(value)
    result[hash_field] = _payload_hash(result, hash_field)
    return result


def _verify_payload_hash(value: Mapping[str, Any], hash_field: str, *, path: str) -> None:
    actual = value.get(hash_field)
    expected = _payload_hash(value, hash_field)
    if actual != expected:
        raise HashDriftError(f"{path}: {hash_field} mismatch ({actual!r} != {expected})")


def _register_unique(
    seen: MutableMapping[SemanticKey, tuple[str, str]],
    key: SemanticKey,
    row_hash: str,
    location: str,
) -> None:
    previous = seen.get(key)
    if previous is None:
        seen[key] = (row_hash, location)
        return
    previous_hash, previous_location = previous
    if previous_hash == row_hash:
        raise DuplicateKeyError(
            f"duplicate semantic key {key!r}: {previous_location} and {location}"
        )
    raise ConflictingKeyError(
        f"conflicting semantic key {key!r}: {previous_location}={previous_hash}, "
        f"{location}={row_hash}"
    )


def _is_valid_a_output(text: Any, min_chars: int) -> bool:
    """Exact current ``run_final_5level._is_valid_output`` policy."""

    if not isinstance(text, str) or not text or len(text.strip()) < min_chars:
        return False
    stripped = text.strip()
    if stripped.startswith("[ERROR") or stripped.startswith("Error:") or stripped.startswith("[API"):
        return False
    if len(set(stripped.split())) < 5 and len(stripped.split()) > 20:
        return False
    return True


def _debug_inputs(
    debug: Mapping[str, Any],
    *,
    path: str,
    require_current_quality: bool,
) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]], tuple[int, ...]]:
    prompts = _strict_mapping(debug.get("prompts"), path + ".prompts")
    outputs = _strict_mapping(debug.get("outputs"), path + ".outputs")
    if set(prompts) != set(whitebox_schema.LEVELS):
        raise InvariantError(f"{path}.prompts: keys must be exactly L1-L5")
    if set(outputs) != set(whitebox_schema.LEVELS):
        raise InvariantError(f"{path}.outputs: keys must be exactly L1-L5")

    levels: dict[str, dict[str, str]] = {}
    for level in whitebox_schema.LEVELS:
        prompt = prompts[level]
        output = outputs[level]
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvariantError(f"{path}.prompts.{level}: expected non-empty string")
        if not isinstance(output, str):
            raise InvariantError(f"{path}.outputs.{level}: expected string")
        if require_current_quality and not _is_valid_a_output(output, 80):
            raise InvariantError(
                f"{path}.outputs.{level}: fails current Experiment A output policy"
            )
        levels[level] = {"prompt": prompt, "output": output}

    raw_cfs = debug.get("counterfactuals")
    if not isinstance(raw_cfs, list) or len(raw_cfs) != 5:
        raise InvariantError(f"{path}.counterfactuals: expected exactly five entries")
    counterfactuals: list[dict[str, Any]] = []
    included: list[int] = []
    for index, value in enumerate(raw_cfs):
        cf = _strict_mapping(value, f"{path}.counterfactuals[{index}]")
        prompt = cf.get("prompt")
        output = cf.get("output")
        if not isinstance(prompt, str) or not isinstance(output, str):
            raise InvariantError(
                f"{path}.counterfactuals[{index}]: prompt/output must be strings"
            )
        keep = bool(prompt.strip()) and _is_valid_a_output(output, 50)
        # Since 2026-08-22 the runner blanks rejected outputs.  Requiring exact
        # equivalence here prevents a future policy change from silently changing
        # the scientific source identity.
        persisted_keep = bool(prompt.strip() and output.strip())
        if require_current_quality and keep != persisted_keep:
            raise InvariantError(
                f"{path}.counterfactuals[{index}]: current validity policy and "
                "persisted effective blanking disagree"
            )
        counterfactuals.append(
            {"index": index, "prompt": prompt, "output": output, "included": keep}
        )
        if keep:
            included.append(index)
    return levels, counterfactuals, tuple(included)


def _verify_current_result_evidence(
    result: Mapping[str, Any],
    debug: Mapping[str, Any],
    valid_indices: Sequence[int],
    *,
    path: str,
) -> None:
    result_levels = _strict_mapping(result.get("levels"), path + ".levels")
    if set(result_levels) != set(whitebox_schema.LEVELS):
        raise InvariantError(f"{path}.levels: keys must be exactly L1-L5")
    debug_metrics = debug.get("level_metrics")
    if debug_metrics is not None and debug_metrics != result_levels:
        raise InvariantError(f"{path}: result levels differ from joined debug level_metrics")

    observed_counts: list[int] = []
    fields_present = 0
    for level in whitebox_schema.LEVELS:
        entry = _strict_mapping(result_levels[level], f"{path}.levels.{level}")
        if "baseline_n_valid" in entry:
            fields_present += 1
            value = entry["baseline_n_valid"]
            if type(value) is not int:
                raise InvariantError(
                    f"{path}.levels.{level}.baseline_n_valid: expected integer"
                )
            observed_counts.append(value)
    if fields_present not in (0, len(whitebox_schema.LEVELS)):
        raise InvariantError(f"{path}: baseline_n_valid must be present for all levels or none")
    if observed_counts and any(value != len(valid_indices) for value in observed_counts):
        raise InvariantError(
            f"{path}: persisted baseline_n_valid does not prove CF inclusion decisions"
        )

    api = result.get("_api")
    if isinstance(api, Mapping) and "valid_counterfactuals" in api:
        if api["valid_counterfactuals"] != len(valid_indices):
            raise InvariantError(
                f"{path}._api.valid_counterfactuals disagrees with CF inclusion"
            )


def _historical_input_hash(
    debug: Mapping[str, Any], *, path: str
) -> tuple[str, tuple[int, ...]]:
    levels, cfs, included = _debug_inputs(
        debug, path=path, require_current_quality=False
    )
    # Old-only records can have fewer than three usable CFs.  They remain part of
    # the historical key audit but can never be reused; hash the same ordered
    # payload without weakening the strict v2 source schema.
    payload = {
        "levels": [
            {
                "level": level,
                "prompt": levels[level]["prompt"],
                "output": levels[level]["output"],
            }
            for level in whitebox_schema.LEVELS
        ],
        "counterfactuals": [dict(cf) for cf in cfs],
    }
    return storage.canonical_row_sha256(payload), included


def _load_result_truth(
    results_dir: Path,
    *,
    target_models: Sequence[str],
    domains: Sequence[str],
) -> tuple[dict[SemanticKey, dict[str, Any]], list[dict[str, Any]]]:
    if not results_dir.is_dir():
        raise PreconditionError(f"results directory does not exist: {results_dir}")
    target_set = set(target_models)
    domain_set = {domain.lower() for domain in domains}
    files: dict[tuple[str, str], Path] = {}
    for candidate in sorted(results_dir.glob("final_*_5level_*.json")):
        match = _RESULT_RE.fullmatch(candidate.name)
        if match is None:
            continue
        model = match.group("model")
        domain = match.group("domain").lower()
        if model not in target_set:
            continue
        if domain not in domain_set:
            raise InvariantError(
                f"target-model result has unexpected domain {domain!r}: {candidate}"
            )
        pair = (model, domain)
        if pair in files:
            raise DuplicateKeyError(f"multiple result files for {pair!r}")
        files[pair] = candidate.resolve()

    expected_pairs = {(model, domain.lower()) for model in target_models for domain in domains}
    if set(files) != expected_pairs:
        missing = sorted(expected_pairs - set(files))
        extra = sorted(set(files) - expected_pairs)
        raise PreconditionError(
            f"authoritative result file matrix mismatch (missing={missing}, extra={extra})"
        )

    rows: dict[SemanticKey, dict[str, Any]] = {}
    seen: dict[SemanticKey, tuple[str, str]] = {}
    file_records: list[dict[str, Any]] = []
    for model, domain in sorted(files):
        path = files[(model, domain)]
        value = _strict_load_file(path)
        if not isinstance(value, list):
            raise InvariantError(f"{path}: result root must be an array")
        file_record = _file_record(path)
        file_record.update({"model": model, "domain": domain, "row_count": len(value)})
        file_records.append(file_record)
        for index, raw in enumerate(value):
            row = dict(_strict_mapping(raw, f"{path}[{index}]"))
            item_id = row.get("id")
            if not isinstance(item_id, str):
                raise InvariantError(f"{path}[{index}].id: expected string")
            key = whitebox_schema.normalize_semantic_key(model, domain, item_id)
            digest = storage.canonical_row_sha256(row)
            _register_unique(seen, key, digest, f"{path}[{index}]")
            rows[key] = {
                "row": row,
                "row_sha256": digest,
                "path": str(path),
                "index": index,
            }
    return rows, file_records


def _load_current_debug(
    debug_dir: Path,
    *,
    target_models: Sequence[str],
) -> dict[SemanticKey, dict[str, Any]]:
    if not debug_dir.is_dir():
        raise PreconditionError(f"debug directory does not exist: {debug_dir}")
    target_set = set(target_models)
    records: dict[SemanticKey, dict[str, Any]] = {}
    seen: dict[SemanticKey, tuple[str, str]] = {}
    for path in sorted(debug_dir.glob("*.json")):
        raw_bytes = path.read_bytes()
        value = _strict_load_bytes(raw_bytes, path=str(path))
        row = _strict_mapping(value, str(path))
        if row.get("model", row.get("generation_model")) not in target_set:
            continue
        key = _semantic_key_from_debug(row, path=str(path))
        digest = storage.canonical_row_sha256(row)
        _register_unique(seen, key, digest, str(path))
        records[key] = {
            "row": dict(row),
            "row_sha256": digest,
            "file_sha256": storage.sha256_bytes(raw_bytes),
            "path": str(path.resolve()),
        }
    return records


def _load_archive_union(
    archives: Sequence[Path],
    *,
    target_models: Sequence[str],
) -> tuple[dict[SemanticKey, dict[str, Any]], list[dict[str, Any]]]:
    target_set = set(target_models)
    union: dict[SemanticKey, dict[str, Any]] = {}
    input_records: list[dict[str, Any]] = []
    for archive in archives:
        archive = archive.resolve()
        input_record = _file_record(archive)
        member_names: set[str] = set()
        archive_seen: dict[SemanticKey, tuple[str, str]] = {}
        target_count = 0
        try:
            handle = tarfile.open(archive, mode="r:gz")
        except (tarfile.TarError, OSError) as exc:
            raise InvariantError(f"cannot open legacy archive {archive}: {exc}") from exc
        with handle:
            for member in handle.getmembers():
                if member.name in member_names:
                    raise DuplicateKeyError(
                        f"duplicate tar member name {member.name!r} in {archive}"
                    )
                member_names.add(member.name)
                if not member.isfile() or not member.name.lower().endswith(".json"):
                    continue
                extracted = handle.extractfile(member)
                if extracted is None:
                    raise InvariantError(f"cannot read tar member {archive}!/{member.name}")
                raw_bytes = extracted.read()
                location = f"{archive}!/{member.name}"
                row = _strict_mapping(_strict_load_bytes(raw_bytes, path=location), location)
                if row.get("model", row.get("generation_model")) not in target_set:
                    continue
                target_count += 1
                key = _semantic_key_from_debug(row, path=location)
                digest = storage.canonical_row_sha256(row)
                _register_unique(archive_seen, key, digest, location)
                provenance = {
                    "archive": str(archive),
                    "member": member.name,
                    "member_sha256": storage.sha256_bytes(raw_bytes),
                }
                previous = union.get(key)
                if previous is None:
                    union[key] = {
                        "row": dict(row),
                        "row_sha256": digest,
                        "provenance": [provenance],
                    }
                elif previous["row_sha256"] != digest:
                    raise ConflictingKeyError(
                        f"legacy archives conflict for {key!r}: "
                        f"{previous['row_sha256']} != {digest} at {location}"
                    )
                else:
                    previous["provenance"].append(provenance)
        input_record["target_row_count"] = target_count
        input_record["member_count"] = len(member_names)
        input_records.append(input_record)
    for record in union.values():
        record["provenance"].sort(key=lambda item: (item["archive"], item["member"]))
    return union, input_records


def _load_legacy_scores(
    score_paths: Mapping[str, Path],
    *,
    evaluators: Sequence[str],
    target_models: Sequence[str],
) -> tuple[dict[str, dict[SemanticKey, dict[str, Any]]], list[dict[str, Any]]]:
    target_set = set(target_models)
    by_evaluator: dict[str, dict[SemanticKey, dict[str, Any]]] = {}
    file_records: list[dict[str, Any]] = []
    reference_keys: set[SemanticKey] | None = None
    for evaluator in evaluators:
        if evaluator not in score_paths:
            raise PreconditionError(f"missing legacy score path for evaluator {evaluator!r}")
        path = score_paths[evaluator].resolve()
        value = _strict_mapping(_strict_load_file(path), str(path))
        meta = _strict_mapping(value.get("meta"), str(path) + ".meta")
        if meta.get("eval_model") != evaluator:
            raise InvariantError(
                f"{path}: meta.eval_model={meta.get('eval_model')!r}, expected {evaluator!r}"
            )
        items = value.get("items")
        if not isinstance(items, list):
            raise InvariantError(f"{path}.items: expected array")
        if meta.get("total_items") != len(items):
            raise InvariantError(
                f"{path}: meta.total_items does not equal len(items)"
            )
        seen: dict[SemanticKey, tuple[str, str]] = {}
        rows: dict[SemanticKey, dict[str, Any]] = {}
        for index, raw in enumerate(items):
            row = dict(_strict_mapping(raw, f"{path}.items[{index}]"))
            key = _semantic_key_from_legacy(row, path=f"{path}.items[{index}]")
            if key[0] not in target_set:
                raise InvariantError(f"{path}.items[{index}]: non-target model {key[0]!r}")
            digest = storage.canonical_row_sha256(row)
            _register_unique(seen, key, digest, f"{path}.items[{index}]")
            rows[key] = {"row": row, "row_sha256": digest, "index": index}
        keys = set(rows)
        if reference_keys is not None and keys != reference_keys:
            raise InvariantError(
                f"legacy evaluator key sets differ for {evaluator}: "
                f"missing={len(reference_keys - keys)}, extra={len(keys - reference_keys)}"
            )
        reference_keys = keys
        by_evaluator[evaluator] = rows
        record = _file_record(path)
        record.update({"evaluator": evaluator, "row_count": len(rows)})
        file_records.append(record)
    return by_evaluator, file_records


def _artifact_paths(
    artifact_root: Path,
    *,
    manifest_path: Path,
    evaluators: Sequence[str],
    active_pointer: Path,
) -> dict[str, Any]:
    return {
        "manifest": str(manifest_path),
        "artifact_root": str(artifact_root),
        "sources": str(artifact_root / "sources.jsonl"),
        "seed_state": str(artifact_root / "seed_state.json"),
        "queue": str(artifact_root / "recompute_queue.json"),
        "working_scores": {
            evaluator: str(artifact_root / "working" / f"phi_{evaluator}.v2.jsonl")
            for evaluator in evaluators
        },
        "evaluator_locks": {
            evaluator: str(artifact_root / ".locks" / f"{evaluator}.lock")
            for evaluator in evaluators
        },
        "finalize_lock": str(artifact_root / ".locks" / "finalize.lock"),
        "final_scores": {
            evaluator: str(artifact_root / "final" / f"phi_{evaluator}.v2.jsonl")
            for evaluator in evaluators
        },
        "compatibility_scores": {
            evaluator: str(artifact_root / "final" / f"phi_{evaluator}.json")
            for evaluator in evaluators
        },
        "compatibility_index": str(artifact_root / "final" / "compatibility.json"),
        "lineage": str(artifact_root / "final" / "lineage.json"),
        "active_pointer": str(active_pointer),
    }


def _flatten_artifact_files(paths: Mapping[str, Any]) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for name, value in paths.items():
        if name == "artifact_root":
            continue
        if isinstance(value, Mapping):
            for child_name, child in value.items():
                result.append((f"{name}.{child_name}", _absolute(str(child))))
        elif isinstance(value, str):
            result.append((name, _absolute(value)))
    return result


def _require_distinct_output_paths(
    paths: Mapping[str, Any], *, artifact_root: Path
) -> None:
    files = _flatten_artifact_files(paths)
    seen: dict[Path, str] = {}
    for label, path in files:
        previous = seen.get(path)
        if previous is not None:
            raise PreconditionError(
                f"output paths alias: {previous} and {label} both resolve to {path}"
            )
        if path == artifact_root:
            raise PreconditionError(
                f"output file {label} aliases artifact_root directory: {path}"
            )
        seen[path] = label


def _manifest_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": "DRY_RUN" if manifest.get("dry_run") else "PREPARED",
        "migration_id": manifest["migration_id"],
        "manifest": manifest["paths"]["manifest"],
        "counts": manifest["partition"]["counts"],
        "plan_sha256": manifest["plan_sha256"],
    }


def prepare(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    project_root: str | os.PathLike[str] = PROJECT_ROOT,
    results_dir: str | os.PathLike[str] | None = None,
    current_debug_dir: str | os.PathLike[str] | None = None,
    legacy_archives: Sequence[str | os.PathLike[str]] | None = None,
    legacy_score_paths: Mapping[str, str | os.PathLike[str]] | None = None,
    artifact_root: str | os.PathLike[str] | None = None,
    active_pointer: str | os.PathLike[str] | None = None,
    target_models: Sequence[str] = TARGET_MODELS,
    domains: Sequence[str] = DOMAINS,
    evaluators: Sequence[str] = EVALUATORS,
    enforce_production: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Prepare and optionally persist the immutable baseline-v2 migration plan."""

    project = _absolute(project_root)
    manifest_file = _absolute(manifest_path)
    result_root = _absolute(results_dir or project / "experiment_a" / "results")
    debug_root = _absolute(current_debug_dir or project / "experiment_a" / "debug_logs")
    archive_paths = tuple(
        _absolute(path)
        for path in (
            legacy_archives
            if legacy_archives is not None
            else (
                project / "experiment_a" / "debug_logs.tar.gz",
                project / "tmp" / "missing_logs.tar.gz",
            )
        )
    )
    score_paths = {
        evaluator: _absolute(path)
        for evaluator, path in (
            legacy_score_paths
            if legacy_score_paths is not None
            else {
                evaluator: project
                / "experiment_baseline"
                / "legacy_artifacts"
                / "20260818"
                / f"phi_{evaluator}.json"
                for evaluator in evaluators
            }
        ).items()
    }
    pointer_path = _absolute(
        active_pointer or project / "experiment_baseline" / "ACTIVE_PHI_V2.json"
    )

    if len(set(target_models)) != len(tuple(target_models)) or not target_models:
        raise PreconditionError("target_models must be non-empty and unique")
    if len(set(domain.lower() for domain in domains)) != len(tuple(domains)) or not domains:
        raise PreconditionError("domains must be non-empty and unique")
    if len(set(evaluators)) != len(tuple(evaluators)) or not evaluators:
        raise PreconditionError("evaluators must be non-empty and unique")
    for evaluator in evaluators:
        try:
            whitebox_core.evaluator_descriptor(evaluator)
        except ValueError as exc:
            raise PreconditionError(str(exc)) from exc

    result_rows, result_files = _load_result_truth(
        result_root, target_models=target_models, domains=domains
    )
    current_debug = _load_current_debug(debug_root, target_models=target_models)
    result_keys = set(result_rows)
    debug_keys = set(current_debug)
    if result_keys != debug_keys:
        raise InvariantError(
            "authoritative result/debug key parity failed "
            f"(missing_debug={len(result_keys - debug_keys)}, "
            f"debug_without_result={len(debug_keys - result_keys)})"
        )

    current_sources: dict[SemanticKey, dict[str, Any]] = {}
    current_entries: list[dict[str, Any]] = []
    for key in sorted(result_keys):
        result_record = result_rows[key]
        debug_record = current_debug[key]
        debug_row = debug_record["row"]
        levels, cfs, valid_indices = _debug_inputs(
            debug_row,
            path=debug_record["path"],
            require_current_quality=True,
        )
        _verify_current_result_evidence(
            result_record["row"],
            debug_row,
            valid_indices,
            path=f"{result_record['path']}[{result_record['index']}]",
        )
        if len(valid_indices) < whitebox_schema.MIN_VALID_CFS:
            raise InvariantError(f"current source {key!r} has fewer than three valid CFs")
        try:
            source_file = Path(debug_record["path"]).relative_to(project).as_posix()
        except ValueError:
            # Tests and operators may stage read-only inputs outside the project;
            # retain an absolute provenance string rather than weakening the join.
            source_file = Path(debug_record["path"]).as_posix()
        source = whitebox_schema.build_source_row(
            debug_row,
            source_file=source_file,
            cf_included=[index in valid_indices for index in range(5)],
        )
        validation = whitebox_schema.validate_source_row(source)
        if validation.semantic_key != key:
            raise InvariantError(f"internal source join changed semantic key {key!r}")
        current_sources[key] = source
        current_entries.append(
            {
                "semantic_key": _key_list(key),
                "scoring_input_sha256": validation.scoring_input_sha256,
                "source_row_sha256": validation.canonical_row_sha256,
                "result_row_sha256": result_record["row_sha256"],
                "debug_row_sha256": debug_record["row_sha256"],
                "debug_file_sha256": debug_record["file_sha256"],
                "source_file": source_file,
                "valid_cf_indices": list(valid_indices),
            }
        )

    legacy_scores, legacy_score_files = _load_legacy_scores(
        score_paths,
        evaluators=evaluators,
        target_models=target_models,
    )
    legacy_score_keys = set(legacy_scores[evaluators[0]])
    archive_union, archive_files = _load_archive_union(
        archive_paths, target_models=target_models
    )
    archive_keys = set(archive_union)
    missing_from_archives = legacy_score_keys - archive_keys
    archive_extras = archive_keys - legacy_score_keys
    omission: dict[str, Any] | None = None
    if missing_from_archives:
        raise InvariantError(
            f"legacy archives are missing {len(missing_from_archives)} scored keys"
        )
    if archive_extras:
        if archive_extras != {KNOWN_LEGACY_OMISSION}:
            raise InvariantError(
                "legacy archive/score parity has unexpected extras: "
                f"{sorted(archive_extras)!r}"
            )
        if len(archive_keys) - 1 != len(legacy_score_keys):
            raise InvariantError("Petition omission does not produce the exact old count")
        omitted = archive_union[KNOWN_LEGACY_OMISSION]
        omission = {
            "semantic_key": _key_list(KNOWN_LEGACY_OMISSION),
            "reason": "known legacy scorer omission",
            "archive_row_sha256": omitted["row_sha256"],
            "provenance": omitted["provenance"],
        }
        archive_union = {
            key: value for key, value in archive_union.items() if key != KNOWN_LEGACY_OMISSION
        }
    if set(archive_union) != legacy_score_keys:
        raise InvariantError("legacy snapshot cannot be reconstructed exactly")

    historical_hashes: dict[SemanticKey, str] = {}
    historical_indices: dict[SemanticKey, tuple[int, ...]] = {}
    legacy_entries: list[dict[str, Any]] = []
    for key in sorted(legacy_score_keys):
        archive_record = archive_union[key]
        input_hash, valid_indices = _historical_input_hash(
            archive_record["row"],
            path=(
                archive_record["provenance"][0]["archive"]
                + "!/"
                + archive_record["provenance"][0]["member"]
            ),
        )
        historical_hashes[key] = input_hash
        historical_indices[key] = valid_indices
        legacy_entries.append(
            {
                "semantic_key": _key_list(key),
                "historical_scoring_input_sha256": input_hash,
                "historical_valid_cf_indices": list(valid_indices),
                "archive_row_sha256": archive_record["row_sha256"],
                "archive_provenance": archive_record["provenance"],
                "legacy_score_row_sha256": {
                    evaluator: legacy_scores[evaluator][key]["row_sha256"]
                    for evaluator in evaluators
                },
            }
        )

    current_keys = set(current_sources)
    same_keys = current_keys & legacy_score_keys
    reusable_keys = {
        key
        for key in same_keys
        if current_sources[key]["scoring_input_sha256"] == historical_hashes[key]
    }
    changed_keys = same_keys - reusable_keys
    current_only_keys = current_keys - legacy_score_keys
    old_only_keys = legacy_score_keys - current_keys
    recompute_keys = current_keys - reusable_keys

    reusable_entries = []
    for key in sorted(reusable_keys):
        valid = tuple(
            index
            for index, cf in enumerate(current_sources[key]["counterfactuals"])
            if cf["included"]
        )
        reusable_entries.append(
            {
                "semantic_key": _key_list(key),
                "scoring_input_sha256": current_sources[key]["scoring_input_sha256"],
                "source_row_sha256": storage.canonical_row_sha256(current_sources[key]),
                "valid_cf_indices": list(valid),
                "legacy_score_row_sha256": {
                    evaluator: legacy_scores[evaluator][key]["row_sha256"]
                    for evaluator in evaluators
                },
            }
        )
    changed_entries = [
        {
            "semantic_key": _key_list(key),
            "current_scoring_input_sha256": current_sources[key]["scoring_input_sha256"],
            "historical_scoring_input_sha256": historical_hashes[key],
            "source_row_sha256": storage.canonical_row_sha256(current_sources[key]),
        }
        for key in sorted(changed_keys)
    ]
    current_only_entries = [
        {
            "semantic_key": _key_list(key),
            "scoring_input_sha256": current_sources[key]["scoring_input_sha256"],
            "source_row_sha256": storage.canonical_row_sha256(current_sources[key]),
        }
        for key in sorted(current_only_keys)
    ]
    old_only_entries = [
        {
            "semantic_key": _key_list(key),
            "historical_scoring_input_sha256": historical_hashes[key],
            "archive_row_sha256": archive_union[key]["row_sha256"],
            "legacy_score_row_sha256": {
                evaluator: legacy_scores[evaluator][key]["row_sha256"]
                for evaluator in evaluators
            },
        }
        for key in sorted(old_only_keys)
    ]
    recompute_entries = [
        {
            "semantic_key": _key_list(key),
            "reason": "same_key_changed" if key in changed_keys else "current_only",
            "scoring_input_sha256": current_sources[key]["scoring_input_sha256"],
            "source_row_sha256": storage.canonical_row_sha256(current_sources[key]),
        }
        for key in sorted(recompute_keys)
    ]

    partial_four = sum(
        len(entry["valid_cf_indices"]) == 4 for entry in reusable_entries
    )
    partial_three = sum(
        len(entry["valid_cf_indices"]) == 3 for entry in reusable_entries
    )
    partial_reused = partial_four + partial_three
    dropped_slots = sum(5 - len(entry["valid_cf_indices"]) for entry in reusable_entries)
    counts = {
        "current": len(current_keys),
        "legacy": len(legacy_score_keys),
        "reusable": len(reusable_keys),
        "same_key_changed": len(changed_keys),
        "current_only": len(current_only_keys),
        "old_only": len(old_only_keys),
        "nominal_recompute": len(recompute_keys),
        "partial_reused": partial_reused,
        "partial_reused_four": partial_four,
        "partial_reused_three": partial_three,
        "dropped_reused_cf_slots": dropped_slots,
    }
    if counts["reusable"] + counts["same_key_changed"] != len(same_keys):
        raise InvariantError("same-key partition arithmetic failed")
    if counts["reusable"] + counts["nominal_recompute"] != counts["current"]:
        raise InvariantError("current partition arithmetic failed")
    if counts["reusable"] + counts["same_key_changed"] + counts["old_only"] != counts["legacy"]:
        raise InvariantError("legacy partition arithmetic failed")
    current_scientific_sha256 = _canonical_set_sha256(
        {
            "semantic_key": entry["semantic_key"],
            "scoring_input_sha256": entry["scoring_input_sha256"],
        }
        for entry in current_entries
    )
    legacy_scientific_sha256 = _canonical_set_sha256(
        {
            "semantic_key": entry["semantic_key"],
            "scoring_input_sha256": entry["historical_scoring_input_sha256"],
        }
        for entry in legacy_entries
    )
    if enforce_production:
        if counts != PRODUCTION_COUNTS:
            raise InvariantError(
                f"production partition mismatch: observed={counts}, expected={PRODUCTION_COUNTS}"
            )
        if current_scientific_sha256 != PRODUCTION_CURRENT_SCIENTIFIC_SHA256:
            raise InvariantError(
                "current production scientific-set digest mismatch: "
                f"{current_scientific_sha256}"
            )
        if legacy_scientific_sha256 != PRODUCTION_LEGACY_SCIENTIFIC_SHA256:
            raise InvariantError(
                "legacy production scientific-set digest mismatch: "
                f"{legacy_scientific_sha256}"
            )

    source_rows = [current_sources[key] for key in sorted(current_sources)]
    source_file_hash, source_file_size = _jsonl_digest(source_rows)
    created = _now(now)
    input_identity = {
        "result_files": result_files,
        "archive_files": archive_files,
        "legacy_score_files": legacy_score_files,
        "current_set_sha256": _canonical_set_sha256(current_entries),
        "legacy_set_sha256": _canonical_set_sha256(legacy_entries),
    }
    migration_id = (
        "phi_v2_"
        + created.strftime("%Y%m%dT%H%M%S")
        + "_"
        + storage.canonical_row_sha256(input_identity)[:12]
    )
    artifacts = _absolute(
        artifact_root
        if artifact_root is not None
        else manifest_file.parent / f"{manifest_file.stem}.artifacts"
    )
    paths = _artifact_paths(
        artifacts,
        manifest_path=manifest_file,
        evaluators=evaluators,
        active_pointer=pointer_path,
    )
    _require_distinct_output_paths(paths, artifact_root=artifacts)
    _reject_protected_output_paths(
        project=project,
        artifact_root=artifacts,
        manifest_path=manifest_file,
        pointer_path=pointer_path,
        legacy_score_paths=score_paths,
        input_paths=(
            *(Path(item["path"]) for item in result_files),
            *(Path(item["path"]) for item in current_debug.values()),
            *archive_paths,
            *score_paths.values(),
        ),
    )

    manifest_without_hash: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "migration_id": migration_id,
        "created_at_utc": created.isoformat(),
        "dry_run": bool(dry_run),
        "production_checks_enforced": bool(enforce_production),
        "target_models": list(target_models),
        "domains": [domain.lower() for domain in domains],
        "evaluators": {
            evaluator: {
                **whitebox_core.evaluator_descriptor(evaluator),
                "evaluator_sha256": whitebox_core.evaluator_sha256(evaluator),
            }
            for evaluator in evaluators
        },
        "protocol": {
            "sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
            "description": whitebox_core.scoring_protocol(),
        },
        "roots": {
            "project": str(project),
            "results": str(result_root),
            "current_debug": str(debug_root),
        },
        "inputs": input_identity,
        "current_sources": {
            "count": len(current_entries),
            "set_sha256": _canonical_set_sha256(current_entries),
            "scientific_set_sha256": current_scientific_sha256,
            "entries": current_entries,
            "jsonl": {
                "path": paths["sources"],
                "sha256": source_file_hash,
                "size": source_file_size,
                "row_count": len(source_rows),
            },
        },
        "legacy_snapshot": {
            "count": len(legacy_entries),
            "set_sha256": _canonical_set_sha256(legacy_entries),
            "scientific_set_sha256": legacy_scientific_sha256,
            "entries": legacy_entries,
            "known_omission": omission,
        },
        "partition": {
            "counts": counts,
            "reusable": reusable_entries,
            "same_key_changed": changed_entries,
            "current_only": current_only_entries,
            "old_only": old_only_entries,
            "nominal_recompute": recompute_entries,
        },
        "paths": paths,
    }
    manifest = _add_payload_hash(manifest_without_hash, "plan_sha256")

    if dry_run:
        return manifest
    if manifest_file.exists():
        raise PreconditionError(f"immutable prepare manifest already exists: {manifest_file}")
    source_path = Path(paths["sources"])
    if source_path.exists():
        raise PreconditionError(f"immutable source artifact already exists: {source_path}")
    storage.atomic_replace_jsonl(source_path, source_rows)
    if storage.file_sha256(source_path) != source_file_hash:
        raise InvariantError("written source JSONL hash does not match prepare plan")
    storage.atomic_replace_json(manifest_file, manifest)
    return manifest


def _load_manifest(path: str | os.PathLike[str]) -> tuple[Path, dict[str, Any]]:
    manifest_path = _absolute(path)
    value = dict(_strict_mapping(_strict_load_file(manifest_path), str(manifest_path)))
    if value.get("schema") != MANIFEST_SCHEMA or value.get("schema_version") != SCHEMA_VERSION:
        raise InvariantError(f"unsupported prepare manifest schema: {manifest_path}")
    _verify_payload_hash(value, "plan_sha256", path=str(manifest_path))
    if value.get("dry_run"):
        raise PreconditionError("a dry-run manifest is not executable")
    if value.get("production_checks_enforced"):
        current_entries = value.get("current_sources", {}).get("entries")
        legacy_entries = value.get("legacy_snapshot", {}).get("entries")
        if not isinstance(current_entries, list) or not isinstance(legacy_entries, list):
            raise InvariantError("production manifest is missing scientific entries")
        current_digest = _canonical_set_sha256(
            {
                "semantic_key": entry["semantic_key"],
                "scoring_input_sha256": entry["scoring_input_sha256"],
            }
            for entry in current_entries
        )
        legacy_digest = _canonical_set_sha256(
            {
                "semantic_key": entry["semantic_key"],
                "scoring_input_sha256": entry["historical_scoring_input_sha256"],
            }
            for entry in legacy_entries
        )
        if current_digest != PRODUCTION_CURRENT_SCIENTIFIC_SHA256:
            raise HashDriftError("production current scientific-set digest mismatch")
        if legacy_digest != PRODUCTION_LEGACY_SCIENTIFIC_SHA256:
            raise HashDriftError("production legacy scientific-set digest mismatch")
        omission = value.get("legacy_snapshot", {}).get("known_omission")
        if not isinstance(omission, Mapping) or omission.get("semantic_key") != list(
            KNOWN_LEGACY_OMISSION
        ):
            raise InvariantError("production manifest known omission mismatch")
    return manifest_path, value


def _runtime_manifest_view(
    manifest: Mapping[str, Any], runtime_root: str | os.PathLike[str]
) -> dict[str, Any]:
    """Relocate mutable run artifacts without changing the signed manifest.

    The immutable manifest is verified before this in-memory view is built.  File
    content hashes and scientific fingerprints remain unchanged; only paths to a
    byte-identical staging bundle are replaced (for example on the GPU server).
    """

    root = _absolute(runtime_root)
    view = copy.deepcopy(dict(manifest))
    paths = view["paths"]
    evaluators = tuple(sorted(view["evaluators"]))
    paths.update(
        {
            "artifact_root": str(root),
            "sources": str(root / "sources.jsonl"),
            "seed_state": str(root / "seed_state.json"),
            "queue": str(root / "recompute_queue.json"),
            "working_scores": {
                evaluator: str(root / "working" / f"phi_{evaluator}.v2.jsonl")
                for evaluator in evaluators
            },
            "evaluator_locks": {
                evaluator: str(root / ".locks" / f"{evaluator}.lock")
                for evaluator in evaluators
            },
            "finalize_lock": str(root / ".locks" / "finalize.lock"),
            "final_scores": {
                evaluator: str(root / "final" / f"phi_{evaluator}.v2.jsonl")
                for evaluator in evaluators
            },
            "compatibility_scores": {
                evaluator: str(root / "final" / f"phi_{evaluator}.json")
                for evaluator in evaluators
            },
            "compatibility_index": str(root / "final" / "compatibility.json"),
            "lineage": str(root / "final" / "lineage.json"),
            "active_pointer": str(root / "ACTIVE_PHI_V2.json"),
        }
    )
    view["current_sources"]["jsonl"]["path"] = paths["sources"]
    return view


def _manifest_evaluators(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    values = manifest.get("evaluators")
    if not isinstance(values, Mapping) or not values:
        raise InvariantError("manifest evaluators are missing")
    evaluators = tuple(sorted(values))
    for evaluator in evaluators:
        descriptor = _strict_mapping(values[evaluator], f"evaluators.{evaluator}")
        expected = whitebox_core.evaluator_sha256(evaluator)
        if descriptor.get("evaluator_sha256") != expected:
            raise HashDriftError(f"manifest evaluator fingerprint drift for {evaluator}")
    if manifest.get("protocol", {}).get("sha256") != whitebox_core.SCORING_PROTOCOL_SHA256:
        raise HashDriftError("accepted scorer protocol differs from prepare manifest")
    return evaluators


def _load_bound_sources(
    manifest: Mapping[str, Any],
) -> tuple[dict[SemanticKey, dict[str, Any]], dict[SemanticKey, str]]:
    source_info = _strict_mapping(
        manifest.get("current_sources", {}).get("jsonl"), "current_sources.jsonl"
    )
    path = Path(str(source_info.get("path")))
    if not path.is_file():
        raise NotReadyError(f"prepared source JSONL is missing: {path}")
    actual_file_hash = storage.file_sha256(path)
    if actual_file_hash != source_info.get("sha256"):
        raise HashDriftError(
            f"prepared source JSONL drift: {actual_file_hash} != {source_info.get('sha256')}"
        )
    try:
        scan = storage.scan_jsonl(
            path,
            validator=whitebox_schema.validate_source_row,
            id_getter=lambda row: _key_id(whitebox_schema.semantic_key(row)),
            repair=False,
        )
    except Exception as exc:
        raise InvariantError(f"cannot validate prepared sources {path}: {exc}") from exc
    if len(scan) != source_info.get("row_count"):
        raise InvariantError("prepared source row count differs from manifest")
    rows: dict[SemanticKey, dict[str, Any]] = {}
    row_hashes: dict[SemanticKey, str] = {}
    for entry in scan.entries:
        key = whitebox_schema.semantic_key(entry.value)
        rows[key] = dict(entry.value)
        row_hashes[key] = entry.row_sha256

    manifest_entries = manifest.get("current_sources", {}).get("entries")
    if not isinstance(manifest_entries, list):
        raise InvariantError("manifest current source entries are missing")
    expected = {
        _key_from_value(item.get("semantic_key"), path="current_sources.entries"): item
        for item in manifest_entries
        if isinstance(item, Mapping)
    }
    if len(expected) != len(manifest_entries):
        raise DuplicateKeyError("manifest current source entries contain duplicate keys")
    if set(rows) != set(expected):
        raise InvariantError("prepared source key set differs from manifest")
    for key, row in rows.items():
        item = expected[key]
        if row_hashes[key] != item.get("source_row_sha256"):
            raise HashDriftError(f"source row hash drift for {key!r}")
        if row["scoring_input_sha256"] != item.get("scoring_input_sha256"):
            raise HashDriftError(f"source input hash drift for {key!r}")
    return rows, row_hashes


def _bound_legacy_score_paths(manifest: Mapping[str, Any]) -> dict[str, Path]:
    records = manifest.get("inputs", {}).get("legacy_score_files")
    if not isinstance(records, list):
        raise InvariantError("manifest legacy score file records are missing")
    result: dict[str, Path] = {}
    for record in records:
        record = _strict_mapping(record, "legacy_score_files[]")
        evaluator = record.get("evaluator")
        if not isinstance(evaluator, str) or evaluator in result:
            raise InvariantError("invalid/duplicate legacy evaluator file record")
        path = Path(str(record.get("path")))
        if not path.is_file():
            raise PreconditionError(f"legacy score file is missing: {path}")
        actual = storage.file_sha256(path)
        if actual != record.get("sha256"):
            raise HashDriftError(f"legacy score file drift for {evaluator}: {actual}")
        result[evaluator] = path
    return result


def _finite_number(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvariantError(f"{path}: expected non-boolean number")
    if not math.isfinite(float(value)):
        raise InvariantError(f"{path}: expected finite number")
    return value


def _convert_legacy_score(
    legacy: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    evaluator: str,
) -> dict[str, Any]:
    expected_keys = {
        "file",
        "model",
        "domain",
        "id",
        "levels",
        "cf_phis",
        "cf_phi_mean",
        "level_excess",
    }
    if set(legacy) != expected_keys:
        raise InvariantError(
            f"legacy score keys are not exact (missing={sorted(expected_keys - set(legacy))}, "
            f"extra={sorted(set(legacy) - expected_keys)})"
        )
    if _semantic_key_from_legacy(legacy, path="legacy") != whitebox_schema.semantic_key(source):
        raise InvariantError("legacy score semantic key differs from source")
    levels = _strict_mapping(legacy["levels"], "legacy.levels")
    if set(levels) != set(whitebox_schema.LEVELS):
        raise InvariantError("legacy.levels must be exactly L1-L5")
    level_copy: dict[str, dict[str, int | float]] = {}
    for level in whitebox_schema.LEVELS:
        value = _strict_mapping(levels[level], f"legacy.levels.{level}")
        if set(value) != {"nll1", "nll2", "phi"}:
            raise InvariantError(f"legacy.levels.{level}: keys are not exact")
        nll1 = _finite_number(value["nll1"], f"legacy.levels.{level}.nll1")
        nll2 = _finite_number(value["nll2"], f"legacy.levels.{level}.nll2")
        phi = _finite_number(value["phi"], f"legacy.levels.{level}.phi")
        if nll1 < 0 or nll2 < 0:
            raise InvariantError(f"legacy.levels.{level}: NLL must be non-negative")
        expected_phi = (nll1 - nll2) / nll1 if nll1 > 0 else 0.0
        if phi != expected_phi:
            raise InvariantError(f"legacy.levels.{level}.phi: arithmetic mismatch")
        level_copy[level] = {"nll1": nll1, "nll2": nll2, "phi": phi}

    cfs = legacy["cf_phis"]
    if not isinstance(cfs, list) or len(cfs) != 5:
        raise InvariantError("legacy.cf_phis must contain exactly five values")
    cf_values = [_finite_number(value, f"legacy.cf_phis[{i}]") for i, value in enumerate(cfs)]
    old_mean = _finite_number(legacy["cf_phi_mean"], "legacy.cf_phi_mean")
    recomputed_old_mean = sum(cf_values) / len(cf_values)
    if not math.isclose(
        old_mean,
        recomputed_old_mean,
        rel_tol=0.0,
        abs_tol=LEGACY_REDUNDANT_ABS_TOL,
    ):
        raise InvariantError("legacy.cf_phi_mean arithmetic mismatch")
    excess = _strict_mapping(legacy["level_excess"], "legacy.level_excess")
    if set(excess) != set(whitebox_schema.LEVELS):
        raise InvariantError("legacy.level_excess must be exactly L1-L5")
    for level in whitebox_schema.LEVELS:
        value = _strict_mapping(excess[level], f"legacy.level_excess.{level}")
        if set(value) != {"phi", "phi_excess"}:
            raise InvariantError(f"legacy.level_excess.{level}: keys are not exact")
        if _finite_number(value["phi"], f"legacy.level_excess.{level}.phi") != level_copy[level]["phi"]:
            raise InvariantError(f"legacy.level_excess.{level}.phi mismatch")
        stored_excess = _finite_number(
            value["phi_excess"], f"legacy.level_excess.{level}.phi_excess"
        )
        expected_excess = level_copy[level]["phi"] - old_mean
        if not math.isclose(
            stored_excess,
            expected_excess,
            rel_tol=0.0,
            abs_tol=LEGACY_REDUNDANT_ABS_TOL,
        ):
            raise InvariantError(f"legacy.level_excess.{level}.phi_excess mismatch")

    valid_indices = tuple(
        cf["index"] for cf in source["counterfactuals"] if cf["included"]
    )
    compact = [cf_values[index] for index in valid_indices]
    return whitebox_schema.build_score_row(
        source,
        evaluator=evaluator,
        levels=level_copy,
        cf_phis=compact,
        valid_cf_indices=valid_indices,
    )


def _queue_payload(
    manifest: Mapping[str, Any], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    return _add_payload_hash(
        {
            "schema": QUEUE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "migration_id": manifest["migration_id"],
            "prepare_plan_sha256": manifest["plan_sha256"],
            "protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
            "count": len(entries),
            "entries": entries,
        },
        "queue_sha256",
    )


def seed(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Seed validated v2 scores and freeze the explicit recomputation queue."""

    _, manifest = _load_manifest(manifest_path)
    evaluators = _manifest_evaluators(manifest)
    sources, source_hashes = _load_bound_sources(manifest)
    score_paths = _bound_legacy_score_paths(manifest)
    legacy_scores, _ = _load_legacy_scores(
        score_paths,
        evaluators=evaluators,
        target_models=tuple(manifest["target_models"]),
    )

    legacy_manifest_entries = manifest.get("legacy_snapshot", {}).get("entries")
    if not isinstance(legacy_manifest_entries, list):
        raise InvariantError("legacy snapshot entries are missing")
    legacy_expected: dict[SemanticKey, Mapping[str, Any]] = {}
    for item in legacy_manifest_entries:
        item = _strict_mapping(item, "legacy_snapshot.entries[]")
        key = _key_from_value(item.get("semantic_key"), path="legacy_snapshot.entries")
        if key in legacy_expected:
            raise DuplicateKeyError(f"duplicate manifest legacy key {key!r}")
        legacy_expected[key] = item
    for evaluator in evaluators:
        if set(legacy_scores[evaluator]) != set(legacy_expected):
            raise HashDriftError(f"legacy score key set drift for {evaluator}")
        for key, record in legacy_scores[evaluator].items():
            expected_hash = legacy_expected[key]["legacy_score_row_sha256"][evaluator]
            if record["row_sha256"] != expected_hash:
                raise HashDriftError(f"legacy score row drift for {evaluator}/{key!r}")

    reusable_items = manifest.get("partition", {}).get("reusable")
    nominal_items = manifest.get("partition", {}).get("nominal_recompute")
    if not isinstance(reusable_items, list) or not isinstance(nominal_items, list):
        raise InvariantError("manifest partition lists are missing")
    reusable = {
        _key_from_value(item.get("semantic_key"), path="partition.reusable"): item
        for item in reusable_items
        if isinstance(item, Mapping)
    }
    nominal = {
        _key_from_value(item.get("semantic_key"), path="partition.nominal_recompute"): item
        for item in nominal_items
        if isinstance(item, Mapping)
    }
    if len(reusable) != len(reusable_items) or len(nominal) != len(nominal_items):
        raise DuplicateKeyError("manifest partition contains duplicate semantic keys")
    if set(reusable) | set(nominal) != set(sources) or set(reusable) & set(nominal):
        raise InvariantError("manifest reusable/recompute partition is not exact")

    seeded: dict[str, list[dict[str, Any]]] = {evaluator: [] for evaluator in evaluators}
    queue_entries: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    for evaluator in evaluators:
        for key in sorted(sources):
            source = sources[key]
            base_queue = {
                "evaluator": evaluator,
                "semantic_key": _key_list(key),
                "scoring_input_sha256": source["scoring_input_sha256"],
                "source_row_sha256": source_hashes[key],
                "evaluator_sha256": whitebox_core.evaluator_sha256(evaluator),
                "protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
            }
            if key in nominal:
                queue_entries.append({**base_queue, "reason": nominal[key]["reason"]})
                continue
            legacy_record = legacy_scores[evaluator].get(key)
            if legacy_record is None:
                raise InvariantError(f"reusable key has no legacy score: {evaluator}/{key!r}")
            try:
                converted = _convert_legacy_score(
                    legacy_record["row"], source, evaluator=evaluator
                )
            except Exception as exc:
                reason = f"invalid_legacy_row: {type(exc).__name__}: {exc}"
                queue_entries.append({**base_queue, "reason": reason})
                promoted.append(
                    {
                        "evaluator": evaluator,
                        "semantic_key": _key_list(key),
                        "legacy_score_row_sha256": legacy_record["row_sha256"],
                        "reason": reason,
                    }
                )
                continue
            whitebox_schema.validate_score_row(
                converted,
                source=source,
                expected_evaluator=evaluator,
                expected_protocol_sha256=whitebox_core.SCORING_PROTOCOL_SHA256,
            )
            seeded[evaluator].append(converted)

    queue_entries.sort(key=lambda item: (item["evaluator"], *item["semantic_key"]))
    queue = _queue_payload(manifest, queue_entries)
    working_info: dict[str, Any] = {}
    for evaluator in evaluators:
        seeded[evaluator].sort(key=whitebox_schema.semantic_key)
        digest, size = _jsonl_digest(seeded[evaluator])
        working_info[evaluator] = {
            "path": manifest["paths"]["working_scores"][evaluator],
            "seed_sha256": digest,
            "seed_size": size,
            "seed_count": len(seeded[evaluator]),
            "seed_entries": [
                {
                    "semantic_key": _key_list(whitebox_schema.semantic_key(row)),
                    "row_sha256": storage.canonical_row_sha256(row),
                    "scoring_input_sha256": row["scoring_input_sha256"],
                }
                for row in seeded[evaluator]
            ],
        }
    seed_state = _add_payload_hash(
        {
            "schema": SEED_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "migration_id": manifest["migration_id"],
            "prepare_plan_sha256": manifest["plan_sha256"],
            "source_jsonl_sha256": manifest["current_sources"]["jsonl"]["sha256"],
            "protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
            "queue": {
                "path": manifest["paths"]["queue"],
                "sha256": storage.canonical_row_sha256(queue),
                "queue_sha256": queue["queue_sha256"],
                "count": len(queue_entries),
            },
            "working_scores": working_info,
            "promoted_invalid_legacy": promoted,
        },
        "seed_state_sha256",
    )
    report = {
        "state": "DRY_RUN" if dry_run else "SEEDED",
        "migration_id": manifest["migration_id"],
        "seeded": {evaluator: len(seeded[evaluator]) for evaluator in evaluators},
        "queue_count": len(queue_entries),
        "promoted_invalid_legacy_count": len(promoted),
        "queue_sha256": queue["queue_sha256"],
        "seed_state_sha256": seed_state["seed_state_sha256"],
    }
    if dry_run:
        return report

    for evaluator in evaluators:
        path = Path(manifest["paths"]["working_scores"][evaluator])
        result = _write_or_verify_jsonl(path, seeded[evaluator])
        if result.sha256 != working_info[evaluator]["seed_sha256"]:
            raise InvariantError(f"seed score write hash mismatch for {evaluator}")
    queue_result = _write_or_verify_json(
        Path(manifest["paths"]["queue"]), queue
    )
    if queue_result.sha256 != storage.canonical_row_sha256(queue):
        raise InvariantError("queue write hash mismatch")
    _write_or_verify_json(Path(manifest["paths"]["seed_state"]), seed_state)
    return report


def _load_seed_state(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(manifest["paths"]["seed_state"])
    if not path.is_file():
        raise NotReadyError(f"seed state is missing: {path}")
    state = dict(_strict_mapping(_strict_load_file(path), str(path)))
    if state.get("schema") != SEED_SCHEMA or state.get("schema_version") != SCHEMA_VERSION:
        raise InvariantError("unsupported seed-state schema")
    _verify_payload_hash(state, "seed_state_sha256", path=str(path))
    if state.get("migration_id") != manifest.get("migration_id") or state.get(
        "prepare_plan_sha256"
    ) != manifest.get("plan_sha256"):
        raise HashDriftError("seed state is not bound to this prepare manifest")
    queue_path = Path(manifest["paths"]["queue"])
    if not queue_path.is_file():
        raise NotReadyError(f"recompute queue is missing: {queue_path}")
    queue_file_hash = storage.file_sha256(queue_path)
    if queue_file_hash != state.get("queue", {}).get("sha256"):
        raise HashDriftError("recompute queue file hash drift")
    queue = dict(_strict_mapping(_strict_load_file(queue_path), str(queue_path)))
    if queue.get("schema") != QUEUE_SCHEMA or queue.get("schema_version") != SCHEMA_VERSION:
        raise InvariantError("unsupported recompute queue schema")
    _verify_payload_hash(queue, "queue_sha256", path=str(queue_path))
    if queue.get("queue_sha256") != state.get("queue", {}).get("queue_sha256"):
        raise HashDriftError("recompute queue payload drift")
    if queue.get("count") != len(queue.get("entries", [])):
        raise InvariantError("recompute queue count mismatch")
    return state, queue


def _queue_index(
    queue: Mapping[str, Any],
    *,
    evaluator: str,
    sources: Mapping[SemanticKey, Mapping[str, Any]],
    source_hashes: Mapping[SemanticKey, str],
) -> dict[SemanticKey, Mapping[str, Any]]:
    entries = queue.get("entries")
    if not isinstance(entries, list):
        raise InvariantError("queue entries are missing")
    result: dict[SemanticKey, Mapping[str, Any]] = {}
    for index, raw in enumerate(entries):
        item = _strict_mapping(raw, f"queue.entries[{index}]")
        if item.get("evaluator") != evaluator:
            continue
        key = _key_from_value(item.get("semantic_key"), path=f"queue.entries[{index}]")
        if key in result:
            raise DuplicateKeyError(f"duplicate queue entry for {evaluator}/{key!r}")
        if key not in sources:
            raise InvariantError(f"queue key has no current source: {key!r}")
        if item.get("scoring_input_sha256") != sources[key]["scoring_input_sha256"]:
            raise HashDriftError(f"queue input hash drift for {evaluator}/{key!r}")
        if item.get("source_row_sha256") != source_hashes[key]:
            raise HashDriftError(f"queue source row hash drift for {evaluator}/{key!r}")
        if item.get("evaluator_sha256") != whitebox_core.evaluator_sha256(evaluator):
            raise HashDriftError(f"queue evaluator hash drift for {evaluator}/{key!r}")
        if item.get("protocol_sha256") != whitebox_core.SCORING_PROTOCOL_SHA256:
            raise HashDriftError(f"queue protocol hash drift for {evaluator}/{key!r}")
        result[key] = item
    return result


def _scan_working_scores(
    manifest: Mapping[str, Any],
    seed_state: Mapping[str, Any],
    queue: Mapping[str, Any],
    *,
    evaluator: str,
    sources: Mapping[SemanticKey, Mapping[str, Any]],
    source_hashes: Mapping[SemanticKey, str],
) -> tuple[dict[SemanticKey, dict[str, Any]], dict[SemanticKey, Mapping[str, Any]]]:
    path = Path(manifest["paths"]["working_scores"][evaluator])
    if not path.is_file():
        raise NotReadyError(f"working score file is missing: {path}")
    queue_index = _queue_index(
        queue, evaluator=evaluator, sources=sources, source_hashes=source_hashes
    )
    seed_entries = seed_state.get("working_scores", {}).get(evaluator, {}).get("seed_entries")
    if not isinstance(seed_entries, list):
        raise InvariantError(f"seed entries missing for evaluator {evaluator}")
    seeded: dict[SemanticKey, Mapping[str, Any]] = {}
    for item in seed_entries:
        item = _strict_mapping(item, f"seed_state.working_scores.{evaluator}.seed_entries")
        key = _key_from_value(item.get("semantic_key"), path="seed entry")
        if key in seeded:
            raise DuplicateKeyError(f"duplicate seed entry for {evaluator}/{key!r}")
        seeded[key] = item
    if set(seeded) & set(queue_index):
        raise InvariantError(f"seeded and queued key sets overlap for {evaluator}")
    if set(seeded) | set(queue_index) != set(sources):
        raise InvariantError(f"seeded and queued key sets are not exhaustive for {evaluator}")

    def validate(row: Any) -> Any:
        key = whitebox_schema.semantic_key(row)
        source = sources.get(key)
        if source is None:
            raise InvariantError(f"score has no source: {key!r}")
        return whitebox_schema.validate_score_row(
            row,
            source=source,
            expected_evaluator=evaluator,
            expected_protocol_sha256=whitebox_core.SCORING_PROTOCOL_SHA256,
        )

    try:
        scan = storage.scan_jsonl(
            path,
            validator=validate,
            id_getter=lambda row: _key_id(whitebox_schema.semantic_key(row)),
            repair=True,
            quarantine_dir=path.parent / "quarantine",
        )
    except Exception as exc:
        raise InvariantError(f"cannot resume strict score JSONL {path}: {exc}") from exc
    rows: dict[SemanticKey, dict[str, Any]] = {}
    for entry in scan.entries:
        key = whitebox_schema.semantic_key(entry.value)
        if key not in seeded and key not in queue_index:
            raise InvariantError(f"working score was neither seeded nor queued: {key!r}")
        if key in seeded and entry.row_sha256 != seeded[key].get("row_sha256"):
            raise HashDriftError(f"seeded score row drift for {evaluator}/{key!r}")
        rows[key] = dict(entry.value)
    if not set(seeded).issubset(rows):
        raise HashDriftError(f"one or more immutable seeded rows disappeared for {evaluator}")
    return rows, queue_index


def _score_source(
    source: Mapping[str, Any],
    *,
    evaluator: str,
    model: Any,
    tokenizer: Any,
) -> dict[str, Any]:
    levels: dict[str, dict[str, float]] = {}
    for level in whitebox_schema.LEVELS:
        value = source["levels"][level]
        # This exact accepted boundary is intentional; do not substitute the
        # timing-only prepared-input path in migration runs.
        levels[level] = whitebox_core.score_phi(
            tokenizer, model, value["prompt"], value["output"]
        )
    cf_values: dict[int, float] = {}
    for cf in source["counterfactuals"]:
        if not cf["included"]:
            continue
        result = whitebox_core.score_phi(
            tokenizer, model, cf["prompt"], cf["output"]
        )
        if not isinstance(result, Mapping) or "phi" not in result:
            raise InvariantError("accepted scorer returned no phi value")
        cf_values[cf["index"]] = result["phi"]
    return whitebox_schema.build_score_row(
        source,
        evaluator=evaluator,
        levels=levels,
        cf_phis=cf_values,
    )


def run(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    evaluator: str,
    limit: int | None = None,
    dry_run: bool = False,
    lock_timeout: float | None = 0.0,
    runtime_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Score pending entries for one evaluator, and only those explicit entries."""

    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be a non-negative integer or None")
    _, manifest = _load_manifest(manifest_path)
    if runtime_root is not None:
        manifest = _runtime_manifest_view(manifest, runtime_root)
    evaluators = _manifest_evaluators(manifest)
    if evaluator not in evaluators:
        raise PreconditionError(f"evaluator {evaluator!r} is not in the manifest")
    if Path(manifest["paths"]["lineage"]).exists():
        raise PreconditionError("migration is already finalized; working scores are immutable")
    sources, source_hashes = _load_bound_sources(manifest)
    seed_state, queue = _load_seed_state(manifest)
    lock_path = Path(manifest["paths"]["evaluator_locks"][evaluator])

    with storage.ProcessLock(
        lock_path,
        scope=f"baseline-v2:{manifest['migration_id']}:{evaluator}",
        timeout=lock_timeout,
    ):
        # Close the check/acquire race with finalize: once lineage is published,
        # no working score file may receive another append.
        if Path(manifest["paths"]["lineage"]).exists():
            raise PreconditionError(
                "migration is already finalized; working scores are immutable"
            )
        existing, explicit_queue = _scan_working_scores(
            manifest,
            seed_state,
            queue,
            evaluator=evaluator,
            sources=sources,
            source_hashes=source_hashes,
        )
        pending = [key for key in sorted(explicit_queue) if key not in existing]
        selected = pending if limit is None else pending[:limit]
        if dry_run:
            return {
                "state": "DRY_RUN",
                "evaluator": evaluator,
                "already_complete": len(explicit_queue) - len(pending),
                "pending": len(pending),
                "would_score": len(selected),
            }
        if not selected:
            return {
                "state": "NO_WORK",
                "evaluator": evaluator,
                "already_complete": len(explicit_queue) - len(pending),
                "pending": len(pending),
                "scored": 0,
            }

        model, tokenizer, _dtype = whitebox_core.load_model(evaluator)
        output_path = Path(manifest["paths"]["working_scores"][evaluator])
        scored = 0
        started = time.monotonic()
        for key in selected:
            # Recheck the immutable queue binding immediately before expensive work.
            queue_item = explicit_queue[key]
            source = sources[key]
            if queue_item["scoring_input_sha256"] != source["scoring_input_sha256"]:
                raise HashDriftError(f"queue/source input drift for {evaluator}/{key!r}")
            row = _score_source(
                source,
                evaluator=evaluator,
                model=model,
                tokenizer=tokenizer,
            )
            whitebox_schema.validate_score_row(
                row,
                source=source,
                expected_evaluator=evaluator,
                expected_protocol_sha256=whitebox_core.SCORING_PROTOCOL_SHA256,
            )
            storage.append_jsonl_row(output_path, row)
            scored += 1
            if scored % 10 == 0 or scored == len(selected):
                elapsed = time.monotonic() - started
                rate = scored / elapsed if elapsed > 0 else 0.0
                remaining = len(selected) - scored
                eta_minutes = (
                    0.0
                    if remaining == 0
                    else remaining / rate / 60.0 if rate > 0 else float("inf")
                )
                print(
                    f"[{evaluator}] {scored}/{len(selected)} scored; "
                    f"elapsed={elapsed / 60.0:.1f}min eta={eta_minutes:.1f}min",
                    flush=True,
                )
        return {
            "state": "RAN",
            "evaluator": evaluator,
            "already_complete": len(explicit_queue) - len(pending),
            "pending_before": len(pending),
            "scored": scored,
            "pending_after": len(pending) - scored,
        }


def collect_runtime(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    runtime_root: str | os.PathLike[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate a relocated completed runtime and collect its journals locally."""

    _, manifest = _load_manifest(manifest_path)
    runtime_manifest = _runtime_manifest_view(manifest, runtime_root)
    evaluators = _manifest_evaluators(runtime_manifest)
    sources, source_hashes = _load_bound_sources(runtime_manifest)
    seed_state, queue = _load_seed_state(runtime_manifest)
    collected: dict[str, Any] = {}

    for evaluator in evaluators:
        rows, _queue_index_value = _scan_working_scores(
            runtime_manifest,
            seed_state,
            queue,
            evaluator=evaluator,
            sources=sources,
            source_hashes=source_hashes,
        )
        if set(rows) != set(sources):
            raise NotReadyError(
                f"runtime {evaluator} incomplete: {len(rows)}/{len(sources)}"
            )
        runtime_path = Path(runtime_manifest["paths"]["working_scores"][evaluator])
        target = Path(manifest["paths"]["working_scores"][evaluator])
        raw = runtime_path.read_bytes()
        runtime_hash = storage.sha256_bytes(raw)
        collected[evaluator] = {
            "count": len(rows),
            "runtime_path": str(runtime_path),
            "runtime_sha256": runtime_hash,
            "target_path": str(target),
        }
        if dry_run:
            continue
        if target.exists() and storage.file_sha256(target) != runtime_hash:
            storage.create_verified_backup(
                target, backup_dir=target.parent / "collect_backups"
            )
        storage.atomic_replace_bytes(target, raw)
        if storage.file_sha256(target) != runtime_hash:
            raise InvariantError(f"collected journal hash mismatch for {evaluator}")

    if not dry_run:
        local_sources, local_source_hashes = _load_bound_sources(manifest)
        local_seed, local_queue = _load_seed_state(manifest)
        for evaluator in evaluators:
            rows, _ = _scan_working_scores(
                manifest,
                local_seed,
                local_queue,
                evaluator=evaluator,
                sources=local_sources,
                source_hashes=local_source_hashes,
            )
            if len(rows) != len(local_sources):
                raise InvariantError(f"collected local journal incomplete for {evaluator}")
    return {
        "state": "DRY_RUN" if dry_run else "COLLECTED",
        "migration_id": manifest["migration_id"],
        "source_count": len(sources),
        "evaluators": collected,
    }


def _compatibility_document(
    evaluator: str,
    rows: Sequence[Mapping[str, Any]],
    sources: Mapping[SemanticKey, Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in rows:
        key = whitebox_schema.semantic_key(row)
        source = sources[key]
        items.append(
            {
                "file": Path(str(source["source_file"])).name,
                "model": row["generation_model"],
                "domain": row["domain"],
                "id": row["id"],
                "levels": row["levels"],
                "cf_phis": row["cf_phis"],
                "valid_cf_indices": row["valid_cf_indices"],
                "cf_valid": row["cf_valid"],
                "cf_phi_mean": row["cf_phi_mean"],
                "level_excess": row["level_excess"],
                "scoring_input_sha256": row["scoring_input_sha256"],
            }
        )
    return {
        "meta": {
            "eval_model": evaluator,
            "total_items": len(items),
            "schema_version": SCHEMA_VERSION,
            "migration_id": manifest["migration_id"],
            "protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
            "evaluator_sha256": whitebox_core.evaluator_sha256(evaluator),
            "note": "v2 compatibility view; partial CF arrays use valid_cf_indices",
        },
        "items": items,
    }


def _validate_final_lineage(
    manifest: Mapping[str, Any],
) -> tuple[Path, dict[str, Any], str]:
    path = Path(manifest["paths"]["lineage"])
    if not path.is_file():
        raise NotReadyError(f"final lineage is missing: {path}")
    value = dict(_strict_mapping(_strict_load_file(path), str(path)))
    if value.get("schema") != LINEAGE_SCHEMA or value.get("schema_version") != SCHEMA_VERSION:
        raise InvariantError("unsupported lineage schema")
    _verify_payload_hash(value, "lineage_payload_sha256", path=str(path))
    if value.get("migration_id") != manifest.get("migration_id") or value.get(
        "prepare_plan_sha256"
    ) != manifest.get("plan_sha256"):
        raise HashDriftError("lineage is not bound to this prepare manifest")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise InvariantError("lineage artifact list is missing")
    for item in artifacts:
        item = _strict_mapping(item, "lineage.artifacts[]")
        artifact = Path(str(item.get("path")))
        if not artifact.is_file():
            raise NotReadyError(f"lineage artifact is missing: {artifact}")
        if storage.file_sha256(artifact) != item.get("sha256"):
            raise HashDriftError(f"lineage artifact hash drift: {artifact}")
    return path, value, storage.file_sha256(path)


def _load_runtime_attestation(
    path: str | os.PathLike[str], evaluators: Sequence[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = _absolute(path)
    value = dict(_strict_mapping(_strict_load_file(source), str(source)))
    if value.get("schema") != "baseline_v2_runtime_attestation":
        raise InvariantError("invalid runtime attestation schema")
    _verify_payload_hash(value, "attestation_payload_sha256", path=str(source))
    if value.get("scoring_protocol_sha256") != whitebox_core.SCORING_PROTOCOL_SHA256:
        raise HashDriftError("runtime attestation scorer protocol mismatch")
    declared = value.get("evaluators")
    if not isinstance(declared, Mapping) or set(declared) != set(evaluators):
        raise InvariantError("runtime attestation evaluator set mismatch")
    for evaluator in evaluators:
        descriptor = _strict_mapping(declared[evaluator], f"attestation.{evaluator}")
        if descriptor.get("descriptor_sha256") != whitebox_core.evaluator_sha256(evaluator):
            raise HashDriftError(
                f"runtime attestation evaluator descriptor mismatch: {evaluator}"
            )
        inventory = _strict_mapping(
            descriptor.get("model_inventory"), f"attestation.{evaluator}.model_inventory"
        )
        files = inventory.get("files")
        if not isinstance(files, list) or not files:
            raise InvariantError(f"runtime attestation has no model files: {evaluator}")
        if inventory.get("inventory_sha256") != storage.canonical_row_sha256(files):
            raise HashDriftError(f"runtime model inventory hash mismatch: {evaluator}")
    return value, _file_record(source)


def finalize(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    dry_run: bool = False,
    lock_timeout: float | None = 0.0,
    runtime_attestation: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Publish immutable v2 outputs only after exact all-evaluator set parity."""

    _, manifest = _load_manifest(manifest_path)
    evaluators = _manifest_evaluators(manifest)
    attestation = None
    attestation_record = None
    if runtime_attestation is not None:
        attestation, attestation_record = _load_runtime_attestation(
            runtime_attestation, evaluators
        )
    elif manifest.get("production_checks_enforced"):
        raise PreconditionError(
            "production finalization requires --runtime-attestation"
        )
    sources, source_hashes = _load_bound_sources(manifest)
    seed_state, queue = _load_seed_state(manifest)
    lineage_path = Path(manifest["paths"]["lineage"])
    if lineage_path.exists():
        _path, lineage, lineage_hash = _validate_final_lineage(manifest)
        return {
            "state": "DRY_RUN" if dry_run else "ALREADY_FINALIZED",
            "migration_id": manifest["migration_id"],
            "source_count": lineage["source"]["count"],
            "score_counts": {
                evaluator: lineage["scores"][evaluator]["count"]
                for evaluator in evaluators
            },
            "lineage": str(lineage_path),
            "lineage_sha256": lineage_hash,
            "lineage_payload_sha256": lineage["lineage_payload_sha256"],
        }

    lock_paths = [Path(manifest["paths"]["finalize_lock"])] + [
        Path(manifest["paths"]["evaluator_locks"][evaluator])
        for evaluator in evaluators
    ]
    with ExitStack() as stack:
        for path in lock_paths:
            stack.enter_context(
                storage.ProcessLock(
                    path,
                    scope=f"baseline-v2:{manifest['migration_id']}:finalize",
                    timeout=lock_timeout,
                )
            )
        if lineage_path.exists():
            _path, lineage, lineage_hash = _validate_final_lineage(manifest)
            return {
                "state": "DRY_RUN" if dry_run else "ALREADY_FINALIZED",
                "migration_id": manifest["migration_id"],
                "source_count": lineage["source"]["count"],
                "score_counts": {
                    evaluator: lineage["scores"][evaluator]["count"]
                    for evaluator in evaluators
                },
                "lineage": str(lineage_path),
                "lineage_sha256": lineage_hash,
                "lineage_payload_sha256": lineage["lineage_payload_sha256"],
            }
        complete: dict[str, list[dict[str, Any]]] = {}
        score_entries: dict[str, list[dict[str, Any]]] = {}
        origin_counts: dict[str, dict[str, int]] = {}
        for evaluator in evaluators:
            rows, queue_index_value = _scan_working_scores(
                manifest,
                seed_state,
                queue,
                evaluator=evaluator,
                sources=sources,
                source_hashes=source_hashes,
            )
            if set(rows) != set(sources):
                missing = sorted(set(sources) - set(rows))
                extra = sorted(set(rows) - set(sources))
                raise NotReadyError(
                    f"{evaluator} is incomplete (missing={len(missing)}, extra={len(extra)})"
                )
            ordered = [rows[key] for key in sorted(rows)]
            complete[evaluator] = ordered
            evaluator_origins: dict[str, int] = {
                "legacy_exact": 0,
                "legacy_partial_cf_derived": 0,
                "gpu_recomputed": 0,
            }
            score_entries[evaluator] = []
            for row in ordered:
                key = whitebox_schema.semantic_key(row)
                if key in queue_index_value:
                    origin = "gpu_recomputed"
                elif row["cf_valid"] < 5:
                    origin = "legacy_partial_cf_derived"
                else:
                    origin = "legacy_exact"
                evaluator_origins[origin] += 1
                score_entries[evaluator].append(
                    {
                        "semantic_key": _key_list(key),
                        "scoring_input_sha256": row["scoring_input_sha256"],
                        "row_sha256": storage.canonical_row_sha256(row),
                        "origin": origin,
                    }
                )
            origin_counts[evaluator] = evaluator_origins

        if dry_run:
            return {
                "state": "DRY_RUN",
                "migration_id": manifest["migration_id"],
                "source_count": len(sources),
                "score_counts": {
                    evaluator: len(complete[evaluator]) for evaluator in evaluators
                },
                "origin_counts": origin_counts,
            }

        source_path = Path(manifest["paths"]["sources"])
        artifact_records: list[dict[str, Any]] = [
            {
                "role": "sources",
                "path": str(source_path),
                "sha256": manifest["current_sources"]["jsonl"]["sha256"],
                "size": source_path.stat().st_size,
                "row_count": len(sources),
            }
        ]
        if attestation_record is not None and attestation is not None:
            artifact_records.append(
                {
                    "role": "runtime_attestation",
                    **attestation_record,
                    "payload_sha256": attestation["attestation_payload_sha256"],
                }
            )
        compatibility_records: dict[str, Any] = {}
        for evaluator in evaluators:
            final_path = Path(manifest["paths"]["final_scores"][evaluator])
            result = _write_or_verify_jsonl(final_path, complete[evaluator])
            artifact_records.append(
                {
                    "role": f"scores:{evaluator}",
                    "path": str(final_path),
                    "sha256": result.sha256,
                    "size": result.size,
                    "row_count": len(complete[evaluator]),
                }
            )
            compatibility = _compatibility_document(
                evaluator, complete[evaluator], sources, manifest=manifest
            )
            compatibility_path = Path(
                manifest["paths"]["compatibility_scores"][evaluator]
            )
            compatibility_result = _write_or_verify_json(
                compatibility_path, compatibility
            )
            compatibility_record = {
                "path": str(compatibility_path),
                "sha256": compatibility_result.sha256,
                "size": compatibility_result.size,
                "row_count": len(complete[evaluator]),
            }
            compatibility_records[evaluator] = compatibility_record
            artifact_records.append(
                {"role": f"compatibility:{evaluator}", **compatibility_record}
            )

        compatibility_index = _add_payload_hash(
            {
                "schema": COMPATIBILITY_SCHEMA,
                "schema_version": SCHEMA_VERSION,
                "migration_id": manifest["migration_id"],
                "prepare_plan_sha256": manifest["plan_sha256"],
                "protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
                "evaluators": compatibility_records,
            },
            "compatibility_payload_sha256",
        )
        compatibility_index_path = Path(manifest["paths"]["compatibility_index"])
        index_result = _write_or_verify_json(
            compatibility_index_path, compatibility_index
        )
        artifact_records.append(
            {
                "role": "compatibility:index",
                "path": str(compatibility_index_path),
                "sha256": index_result.sha256,
                "size": index_result.size,
            }
        )

        source_manifest_entries = {
            _key_from_value(entry["semantic_key"], path="current_sources.entries"): entry
            for entry in manifest["current_sources"]["entries"]
        }
        source_entries = [
            {
                "semantic_key": _key_list(key),
                "scoring_input_sha256": sources[key]["scoring_input_sha256"],
                "row_sha256": source_hashes[key],
                "debug_file_sha256": source_manifest_entries[key][
                    "debug_file_sha256"
                ],
            }
            for key in sorted(sources)
        ]
        lineage = _add_payload_hash(
            {
                "schema": LINEAGE_SCHEMA,
                "schema_version": SCHEMA_VERSION,
                "migration_id": manifest["migration_id"],
                "publication_eligible": bool(
                    manifest.get("production_checks_enforced")
                ),
                "created_at_utc": _now(now).isoformat(),
                "prepare_manifest_path": manifest["paths"]["manifest"],
                "prepare_plan_sha256": manifest["plan_sha256"],
                "seed_state_sha256": seed_state["seed_state_sha256"],
                "queue_sha256": queue["queue_sha256"],
                "protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
                "runtime_attestation": (
                    None
                    if attestation is None
                    else {
                        "file_sha256": attestation_record["sha256"],
                        "payload_sha256": attestation["attestation_payload_sha256"],
                        "scorer_code_inventory_sha256": attestation["scorer_code"][
                            "inventory_sha256"
                        ],
                        "model_inventory_sha256_by_evaluator": {
                            evaluator: attestation["evaluators"][evaluator][
                                "model_inventory"
                            ]["inventory_sha256"]
                            for evaluator in evaluators
                        },
                        "legacy_reuse_attestation": attestation[
                            "legacy_reuse_attestation"
                        ],
                    }
                ),
                "source": {
                    "count": len(source_entries),
                    "jsonl_sha256": manifest["current_sources"]["jsonl"]["sha256"],
                    "entries_sha256": _canonical_set_sha256(source_entries),
                    "entries": source_entries,
                },
                "scores": {
                    evaluator: {
                        "count": len(score_entries[evaluator]),
                        "evaluator_sha256": whitebox_core.evaluator_sha256(evaluator),
                        "origin_counts": origin_counts[evaluator],
                        "entries_sha256": _canonical_set_sha256(score_entries[evaluator]),
                        "entries": score_entries[evaluator],
                    }
                    for evaluator in evaluators
                },
                "artifacts": artifact_records,
            },
            "lineage_payload_sha256",
        )
        lineage_path = Path(manifest["paths"]["lineage"])
        lineage_result = _write_or_verify_json(lineage_path, lineage)
        return {
            "state": "FINALIZED",
            "migration_id": manifest["migration_id"],
            "source_count": len(sources),
            "score_counts": {
                evaluator: len(complete[evaluator]) for evaluator in evaluators
            },
            "lineage": str(lineage_path),
            "lineage_sha256": lineage_result.sha256,
            "lineage_payload_sha256": lineage["lineage_payload_sha256"],
        }


def _pointer_lock_path(pointer: Path) -> Path:
    return pointer.with_name(f".{pointer.name}.lock")


def _bound_pointer_path(
    manifest: Mapping[str, Any], override: str | os.PathLike[str] | None
) -> Path:
    expected = _absolute(manifest["paths"]["active_pointer"])
    if override is None:
        return expected
    requested = _absolute(override)
    if requested != expected:
        raise PreconditionError(
            f"pointer override is not the path bound by prepare: {requested} != {expected}"
        )
    return expected


def _load_pointer_bytes(pointer: Path) -> tuple[bytes, Mapping[str, Any]]:
    raw = pointer.read_bytes()
    value = _strict_mapping(_strict_load_bytes(raw, path=str(pointer)), str(pointer))
    return raw, value


def activate(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    pointer_path: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    lock_timeout: float | None = 0.0,
    allow_nonproduction: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically activate finalized v2 lineage by changing one pointer only."""

    _, manifest = _load_manifest(manifest_path)
    lineage_path, lineage, lineage_hash = _validate_final_lineage(manifest)
    publication_eligible = lineage.get("publication_eligible") is True
    if not publication_eligible and not allow_nonproduction:
        raise PreconditionError(
            "refusing to activate a non-production lineage without "
            "allow_nonproduction=True"
        )
    pointer = _bound_pointer_path(manifest, pointer_path)
    with storage.ProcessLock(
        _pointer_lock_path(pointer),
        scope=f"baseline-v2:pointer:{pointer}",
        timeout=lock_timeout,
    ):
        previous_raw: bytes | None = None
        if pointer.exists():
            previous_raw, previous_value = _load_pointer_bytes(pointer)
            if (
                previous_value.get("schema") == POINTER_SCHEMA
                and previous_value.get("migration_id") == manifest["migration_id"]
            ):
                if (
                    previous_value.get("lineage_sha256") != lineage_hash
                    or previous_value.get("lineage_path") != str(lineage_path)
                    or previous_value.get("prepare_plan_sha256")
                    != manifest["plan_sha256"]
                ):
                    raise HashDriftError(
                        "active pointer for this migration has different lineage/binding"
                    )
                return {
                    "state": "DRY_RUN" if dry_run else "ALREADY_ACTIVE",
                    "pointer": str(pointer),
                    "lineage_sha256": lineage_hash,
                }
        previous = {
            "exists": previous_raw is not None,
            "sha256": storage.sha256_bytes(previous_raw) if previous_raw is not None else None,
            "bytes_b64": base64.b64encode(previous_raw).decode("ascii")
            if previous_raw is not None
            else None,
        }
        value = {
            "schema": POINTER_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "migration_id": manifest["migration_id"],
            "publication_eligible": publication_eligible,
            "activated_at_utc": _now(now).isoformat(),
            "prepare_manifest_path": manifest["paths"]["manifest"],
            "prepare_plan_sha256": manifest["plan_sha256"],
            "lineage_path": str(lineage_path),
            "lineage_sha256": lineage_hash,
            "previous_pointer": previous,
        }
        if dry_run:
            return {
                "state": "DRY_RUN",
                "pointer": str(pointer),
                "lineage_sha256": lineage_hash,
                "would_replace_existing": previous_raw is not None,
            }
        storage.atomic_replace_json(pointer, value)
        return {
            "state": "ACTIVATED",
            "pointer": str(pointer),
            "pointer_sha256": storage.file_sha256(pointer),
            "lineage_sha256": lineage_hash,
            "replaced_existing": previous_raw is not None,
        }


def rollback(
    manifest_path: str | os.PathLike[str] = _DEFAULT_MANIFEST,
    *,
    pointer_path: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    lock_timeout: float | None = 0.0,
) -> dict[str, Any]:
    """Restore the exact prior pointer bytes; never alter migration artifacts."""

    _, manifest = _load_manifest(manifest_path)
    pointer = _bound_pointer_path(manifest, pointer_path)
    with storage.ProcessLock(
        _pointer_lock_path(pointer),
        scope=f"baseline-v2:pointer:{pointer}",
        timeout=lock_timeout,
    ):
        if not pointer.is_file():
            raise PreconditionError(f"active pointer does not exist: {pointer}")
        _raw, value = _load_pointer_bytes(pointer)
        if value.get("schema") != POINTER_SCHEMA or value.get("schema_version") != SCHEMA_VERSION:
            raise PreconditionError("active pointer is not a baseline-v2 pointer")
        if value.get("migration_id") != manifest.get("migration_id") or value.get(
            "prepare_plan_sha256"
        ) != manifest.get("plan_sha256"):
            raise PreconditionError("active pointer belongs to another migration")
        previous = _strict_mapping(value.get("previous_pointer"), "pointer.previous_pointer")
        exists = previous.get("exists")
        if type(exists) is not bool:
            raise InvariantError("pointer.previous_pointer.exists must be boolean")
        previous_raw: bytes | None = None
        if exists:
            encoded = previous.get("bytes_b64")
            expected_hash = previous.get("sha256")
            if not isinstance(encoded, str) or not isinstance(expected_hash, str):
                raise InvariantError("previous pointer snapshot is incomplete")
            try:
                previous_raw = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise InvariantError(f"invalid previous pointer base64: {exc}") from exc
            if storage.sha256_bytes(previous_raw) != expected_hash:
                raise HashDriftError("previous pointer snapshot hash mismatch")
            _strict_load_bytes(previous_raw, path="previous pointer snapshot")
        elif previous.get("bytes_b64") is not None or previous.get("sha256") is not None:
            raise InvariantError("absent previous pointer must not contain snapshot bytes")

        if dry_run:
            return {
                "state": "DRY_RUN",
                "pointer": str(pointer),
                "would_restore_previous": exists,
                "would_remove_pointer": not exists,
            }
        if previous_raw is None:
            pointer.unlink()
            storage.fsync_directory(pointer.parent)
            state = "ROLLED_BACK_TO_ABSENT"
        else:
            storage.atomic_replace_bytes(pointer, previous_raw)
            state = "ROLLED_BACK_TO_PREVIOUS"
        return {"state": state, "pointer": str(pointer)}


def _parse_legacy_score_args(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--legacy-score must be EVALUATOR=PATH")
        evaluator, raw_path = value.split("=", 1)
        if not evaluator or not raw_path or evaluator in result:
            raise ValueError(f"invalid/duplicate --legacy-score value: {value!r}")
        result[evaluator] = Path(raw_path)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="freeze sources and manifest")
    prepare_parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    prepare_parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    prepare_parser.add_argument("--results-dir", type=Path)
    prepare_parser.add_argument("--debug-dir", type=Path)
    prepare_parser.add_argument("--legacy-archive", action="append", type=Path)
    prepare_parser.add_argument("--legacy-score", action="append", default=[])
    prepare_parser.add_argument("--artifact-root", type=Path)
    prepare_parser.add_argument("--active-pointer", type=Path)
    prepare_parser.add_argument("--no-production-checks", action="store_true")
    prepare_parser.add_argument("--dry-run", action="store_true")

    for name in ("seed", "finalize", "activate", "rollback"):
        command = subparsers.add_parser(name)
        command.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
        command.add_argument("--dry-run", action="store_true")
    collect_parser = subparsers.add_parser(
        "collect-runtime", help="validate and collect completed relocated journals"
    )
    collect_parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    collect_parser.add_argument("--runtime-root", type=Path, required=True)
    collect_parser.add_argument("--dry-run", action="store_true")
    run_parser = subparsers.add_parser("run", help="score an explicit evaluator queue")
    run_parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    run_parser.add_argument("--evaluator", choices=EVALUATORS, required=True)
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--runtime-root", type=Path)
    run_parser.add_argument("--dry-run", action="store_true")
    subparsers.choices["finalize"].add_argument(
        "--runtime-attestation", type=Path
    )
    subparsers.choices["activate"].add_argument("--pointer", type=Path)
    subparsers.choices["activate"].add_argument(
        "--allow-nonproduction", action="store_true"
    )
    subparsers.choices["rollback"].add_argument("--pointer", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            legacy_scores = (
                _parse_legacy_score_args(args.legacy_score)
                if args.legacy_score
                else None
            )
            result = prepare(
                args.manifest,
                project_root=args.project_root,
                results_dir=args.results_dir,
                current_debug_dir=args.debug_dir,
                legacy_archives=args.legacy_archive,
                legacy_score_paths=legacy_scores,
                artifact_root=args.artifact_root,
                active_pointer=args.active_pointer,
                enforce_production=not args.no_production_checks,
                dry_run=args.dry_run,
            )
            output = _manifest_summary(result)
        elif args.command == "seed":
            output = seed(args.manifest, dry_run=args.dry_run)
        elif args.command == "collect-runtime":
            output = collect_runtime(
                args.manifest,
                runtime_root=args.runtime_root,
                dry_run=args.dry_run,
            )
        elif args.command == "run":
            output = run(
                args.manifest,
                evaluator=args.evaluator,
                limit=args.limit,
                dry_run=args.dry_run,
                runtime_root=args.runtime_root,
            )
        elif args.command == "finalize":
            output = finalize(
                args.manifest,
                dry_run=args.dry_run,
                runtime_attestation=args.runtime_attestation,
            )
        elif args.command == "activate":
            output = activate(
                args.manifest,
                pointer_path=args.pointer,
                dry_run=args.dry_run,
                allow_nonproduction=args.allow_nonproduction,
            )
        elif args.command == "rollback":
            output = rollback(
                args.manifest, pointer_path=args.pointer, dry_run=args.dry_run
            )
        else:  # pragma: no cover - argparse enforces this
            raise AssertionError(args.command)
    except (MigrationError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


__all__ = [
    "COMPATIBILITY_SCHEMA",
    "ConflictingKeyError",
    "DOMAINS",
    "DuplicateKeyError",
    "EVALUATORS",
    "HashDriftError",
    "InvariantError",
    "KNOWN_LEGACY_OMISSION",
    "LINEAGE_SCHEMA",
    "MANIFEST_SCHEMA",
    "MigrationError",
    "NotReadyError",
    "POINTER_SCHEMA",
    "PRODUCTION_COUNTS",
    "PreconditionError",
    "QUEUE_SCHEMA",
    "SCHEMA_VERSION",
    "SEED_SCHEMA",
    "TARGET_MODELS",
    "activate",
    "collect_runtime",
    "finalize",
    "main",
    "prepare",
    "rollback",
    "run",
    "seed",
]


if __name__ == "__main__":
    raise SystemExit(main())
