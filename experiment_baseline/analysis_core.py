# -*- coding: utf-8 -*-
"""Strict, manifest-bound analysis for the white-box baseline.

The canonical v2 source rows are the frozen source manifest.  Every score is
joined to that manifest by the normalized semantic key *and* the ordered
``scoring_input_sha256``.  The referenced Experiment A debug record supplies
the black-box measurements and underlying-source cluster identity.

This module deliberately keeps statistical policy separate from the CLI.  It
never drops a source, score, level, or primary black-box value silently.
Undefined statistics are represented as ``None`` and JSON serialization is
strict (``allow_nan=False``).
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
import statistics
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from scipy.stats import kendalltau, pearsonr, spearmanr, wilcoxon

from experiment_b.storage import atomic_replace_bytes, file_sha256
from experiment_baseline import whitebox_schema


LEVELS = tuple(whitebox_schema.LEVELS)
COMPRESSORS = ("zlib", "bz2", "lzma")
DEFAULT_SEED = 20260819
_SHA256_LENGTH = 64


class AnalysisError(ValueError):
    """A manifest, join, black-box record, or requested analysis is invalid."""


class CoverageError(AnalysisError):
    """The source, score, and black-box key sets do not have exact coverage."""


class BlackboxValidationError(AnalysisError):
    """An Experiment A black-box record is not valid for strict analysis."""


@dataclass(frozen=True)
class LoadedRows:
    """Strictly decoded rows and the SHA-256 of the exact input artifact."""

    rows: tuple[Mapping[str, Any], ...]
    artifact_sha256: str
    path: str


@dataclass(frozen=True)
class PairedItem:
    """One completely joined generation-model item with all five levels."""

    semantic_key: whitebox_schema.SemanticKey
    scoring_input_sha256: str
    evaluator: str
    evaluator_sha256: str | None
    protocol_sha256: str | None
    source_cluster_key: tuple[str, str, str]
    whitebox_phi: tuple[float, ...]
    whitebox_excess: tuple[float, ...]
    blackbox_excess: tuple[float, ...]
    blackbox_actual: tuple[float, ...]
    blackbox_per_compressor: Mapping[str, tuple[float, ...]]

    @property
    def generation_model(self) -> str:
        return self.semantic_key[0]

    @property
    def domain(self) -> str:
        return self.semantic_key[1]


@dataclass(frozen=True)
class PreparedAnalysis:
    """Validated joins plus immutable lineage metadata."""

    by_evaluator: Mapping[str, tuple[PairedItem, ...]]
    source_manifest_sha256: str
    score_manifest_sha256: str
    blackbox_artifact_set_sha256: str
    source_count: int
    blackbox_count: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_set_sha256(
    rows: Iterable[Mapping[str, Any]], *, score_rows: bool = False
) -> str:
    """Hash a row set independently of physical row order."""

    if score_rows:
        ordered = sorted(
            rows,
            key=lambda row: (
                str(row.get("evaluator", "")),
                *whitebox_schema.semantic_key(row),
            ),
        )
    else:
        ordered = sorted(rows, key=whitebox_schema.semantic_key)
    return _sha256(whitebox_schema.canonical_json_bytes(ordered))


def load_rows(path: str | Path, *, kind: str) -> LoadedRows:
    """Load a strict JSON/JSONL v2 row artifact without permissive fallbacks."""

    source = Path(path)
    raw = source.read_bytes()
    if source.suffix.lower() == ".jsonl":
        value = whitebox_schema.strict_jsonl_loads(raw, path=str(source))
    else:
        value = whitebox_schema.strict_json_loads(source)
    if not isinstance(value, list):
        raise AnalysisError(f"{source}: {kind} artifact must be a JSON array or JSONL")
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise AnalysisError(f"{source}: {kind}[{index}] must be an object")
    return LoadedRows(tuple(value), _sha256(raw), str(source.resolve()))


def validate_finalized_lineage(
    lineage_path: str | Path,
    source_artifact: LoadedRows,
    score_artifacts: Sequence[LoadedRows],
) -> dict[str, Any]:
    """Bind canonical rows to one finalized migration lineage."""

    path = Path(lineage_path)
    value = whitebox_schema.strict_json_load(path)
    if not isinstance(value, Mapping):
        raise AnalysisError(f"{path}: lineage must be an object")
    if value.get("schema") != "experiment_baseline.phi_v2.lineage":
        raise AnalysisError(f"{path}: not a finalized baseline-v2 lineage")
    if value.get("publication_eligible") is not True:
        raise AnalysisError(f"{path}: lineage is not publication-eligible")
    if not isinstance(value.get("migration_id"), str) or not value["migration_id"]:
        raise AnalysisError(f"{path}: missing migration_id")
    stored_payload_hash = value.get("lineage_payload_sha256")
    if not isinstance(stored_payload_hash, str):
        raise AnalysisError(f"{path}: missing lineage_payload_sha256")
    payload = dict(value)
    payload.pop("lineage_payload_sha256", None)
    actual_payload_hash = whitebox_schema.canonical_row_sha256(payload)
    if actual_payload_hash != stored_payload_hash:
        raise AnalysisError(f"{path}: lineage payload hash mismatch")

    artifact_records = value.get("artifacts")
    if not isinstance(artifact_records, list):
        raise AnalysisError(f"{path}: lineage artifacts must be an array")
    by_role: dict[str, Mapping[str, Any]] = {}
    for raw in artifact_records:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("role"), str):
            raise AnalysisError(f"{path}: invalid lineage artifact record")
        role = raw["role"]
        if role in by_role:
            raise AnalysisError(f"{path}: duplicate lineage artifact role {role!r}")
        by_role[role] = raw

    attestation_summary = value.get("runtime_attestation")
    attestation_record = by_role.get("runtime_attestation")
    if not isinstance(attestation_summary, Mapping) or attestation_record is None:
        raise AnalysisError(f"{path}: publication lineage lacks runtime attestation")
    attestation_path = Path(str(attestation_record.get("path")))
    if not attestation_path.is_file():
        raise AnalysisError(f"{path}: runtime attestation file is missing")
    attestation_file_hash = file_sha256(attestation_path)
    if attestation_file_hash != attestation_record.get("sha256"):
        raise AnalysisError(f"{path}: runtime attestation file hash mismatch")
    attestation = whitebox_schema.strict_json_load(attestation_path)
    if not isinstance(attestation, Mapping):
        raise AnalysisError(f"{attestation_path}: attestation must be an object")
    attestation_payload_hash = attestation.get("attestation_payload_sha256")
    attestation_payload = dict(attestation)
    attestation_payload.pop("attestation_payload_sha256", None)
    if attestation_payload_hash != whitebox_schema.canonical_row_sha256(
        attestation_payload
    ):
        raise AnalysisError(f"{attestation_path}: attestation payload hash mismatch")
    if attestation.get("scoring_protocol_sha256") != value.get("protocol_sha256"):
        raise AnalysisError(f"{attestation_path}: scorer protocol mismatch")
    if attestation_summary.get("file_sha256") != attestation_file_hash:
        raise AnalysisError(f"{path}: attestation summary file hash mismatch")
    if attestation_summary.get("payload_sha256") != attestation_payload_hash:
        raise AnalysisError(f"{path}: attestation summary payload hash mismatch")
    scorer_inventory = attestation.get("scorer_code", {}).get("inventory_sha256")
    if attestation_summary.get("scorer_code_inventory_sha256") != scorer_inventory:
        raise AnalysisError(f"{path}: scorer code inventory hash mismatch")
    model_inventory_summary = attestation_summary.get(
        "model_inventory_sha256_by_evaluator"
    )
    if not isinstance(model_inventory_summary, Mapping):
        raise AnalysisError(f"{path}: model inventory summary is missing")
    for evaluator, descriptor in attestation.get("evaluators", {}).items():
        inventory_hash = descriptor.get("model_inventory", {}).get("inventory_sha256")
        if model_inventory_summary.get(evaluator) != inventory_hash:
            raise AnalysisError(
                f"{path}: model inventory hash mismatch for {evaluator}"
            )

    source_record = by_role.get("sources")
    if source_record is None:
        raise AnalysisError(f"{path}: missing sources artifact binding")
    if source_record.get("sha256") != source_artifact.artifact_sha256:
        raise AnalysisError(f"{path}: source artifact hash does not match lineage")
    if source_record.get("row_count") != len(source_artifact.rows):
        raise AnalysisError(f"{path}: source artifact count does not match lineage")

    expected_source_entries = [
        {
            "semantic_key": list(whitebox_schema.semantic_key(row)),
            "scoring_input_sha256": row["scoring_input_sha256"],
            "row_sha256": whitebox_schema.canonical_row_sha256(row),
        }
        for row in sorted(source_artifact.rows, key=whitebox_schema.semantic_key)
    ]
    lineage_source = value.get("source")
    if not isinstance(lineage_source, Mapping):
        raise AnalysisError(f"{path}: missing source lineage")
    raw_source_entries = lineage_source.get("entries")
    if not isinstance(raw_source_entries, list):
        raise AnalysisError(f"{path}: source lineage entries are missing")
    lineage_source_by_key = {
        tuple(entry["semantic_key"]): entry
        for entry in raw_source_entries
        if isinstance(entry, Mapping) and isinstance(entry.get("semantic_key"), list)
    }
    if len(lineage_source_by_key) != len(expected_source_entries):
        raise AnalysisError(f"{path}: source lineage entry count mismatch")
    debug_file_sha256_by_key: dict[
        whitebox_schema.SemanticKey, str
    ] = {}
    for expected in expected_source_entries:
        key = tuple(expected["semantic_key"])
        entry = lineage_source_by_key.get(key)
        if entry is None:
            raise AnalysisError(f"{path}: source lineage is missing {key!r}")
        for field in ("scoring_input_sha256", "row_sha256"):
            if entry.get(field) != expected[field]:
                raise AnalysisError(
                    f"{path}: source {field} mismatch for {key!r}"
                )
        debug_hash = entry.get("debug_file_sha256")
        if not isinstance(debug_hash, str) or len(debug_hash) != 64:
            raise AnalysisError(
                f"{path}: source debug_file_sha256 missing for {key!r}"
            )
        debug_file_sha256_by_key[key] = debug_hash
    if lineage_source.get("entries_sha256") != _sha256(
        whitebox_schema.canonical_json_bytes(raw_source_entries)
    ):
        raise AnalysisError(f"{path}: source entry-set hash mismatch")

    lineage_scores = value.get("scores")
    if not isinstance(lineage_scores, Mapping):
        raise AnalysisError(f"{path}: missing score lineages")
    origin_counts: dict[str, Mapping[str, Any]] = {}
    seen_evaluators = set()
    for artifact in score_artifacts:
        evaluators = {str(row.get("evaluator")) for row in artifact.rows}
        if len(evaluators) != 1:
            raise AnalysisError(f"{artifact.path}: score evaluator is not uniform")
        evaluator = next(iter(evaluators))
        if evaluator in seen_evaluators:
            raise AnalysisError(f"duplicate score artifact for evaluator {evaluator!r}")
        seen_evaluators.add(evaluator)
        artifact_record = by_role.get(f"scores:{evaluator}")
        if artifact_record is None:
            raise AnalysisError(f"{path}: missing score artifact for {evaluator}")
        if artifact_record.get("sha256") != artifact.artifact_sha256:
            raise AnalysisError(f"{path}: {evaluator} score artifact hash mismatch")
        if artifact_record.get("row_count") != len(artifact.rows):
            raise AnalysisError(f"{path}: {evaluator} score count mismatch")

        score_lineage = lineage_scores.get(evaluator)
        if not isinstance(score_lineage, Mapping):
            raise AnalysisError(f"{path}: missing score lineage for {evaluator}")
        expected_rows = {
            tuple(entry["semantic_key"]): entry
            for entry in score_lineage.get("entries", [])
            if isinstance(entry, Mapping) and isinstance(entry.get("semantic_key"), list)
        }
        if len(expected_rows) != len(artifact.rows):
            raise AnalysisError(f"{path}: {evaluator} lineage entry count mismatch")
        for row in artifact.rows:
            key = whitebox_schema.semantic_key(row)
            entry = expected_rows.get(key)
            if entry is None:
                raise AnalysisError(f"{path}: missing lineage row for {evaluator}/{key!r}")
            if entry.get("scoring_input_sha256") != row.get("scoring_input_sha256"):
                raise AnalysisError(f"{path}: input hash mismatch for {evaluator}/{key!r}")
            if entry.get("row_sha256") != whitebox_schema.canonical_row_sha256(row):
                raise AnalysisError(f"{path}: row hash mismatch for {evaluator}/{key!r}")
        origin = score_lineage.get("origin_counts")
        if not isinstance(origin, Mapping) or sum(origin.values()) != len(artifact.rows):
            raise AnalysisError(f"{path}: invalid origin counts for {evaluator}")
        origin_counts[evaluator] = dict(origin)

    if set(lineage_scores) != seen_evaluators:
        raise AnalysisError(
            f"{path}: supplied evaluator set does not match finalized lineage"
        )
    return {
        "migration_id": value.get("migration_id"),
        "lineage_file_sha256": file_sha256(path),
        "lineage_payload_sha256": stored_payload_hash,
        "prepare_plan_sha256": value.get("prepare_plan_sha256"),
        "runtime_attestation": dict(attestation_summary),
        "debug_file_sha256_by_key": {
            "\t".join(key): digest
            for key, digest in sorted(debug_file_sha256_by_key.items())
        },
        "origin_counts": origin_counts,
    }


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BlackboxValidationError(f"{path}: must be a non-boolean number")
    result = float(value)
    if not math.isfinite(result):
        raise BlackboxValidationError(f"{path}: must be finite")
    return result


def _nonnegative_int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise BlackboxValidationError(f"{path}: must be a non-negative integer")
    return value


def _normalize_source_id(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise BlackboxValidationError(f"{path}: must be a string or integer identity")
    result = unicodedata.normalize("NFC", str(value).strip())
    if not result:
        raise BlackboxValidationError(f"{path}: must not be empty")
    return result


def _require_sha256(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise BlackboxValidationError(
            f"{path}: must be a lowercase 64-character SHA-256 digest"
        )
    return value


def _coverage_error(label: str, expected: set[Any], actual: set[Any]) -> CoverageError:
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    return CoverageError(
        f"{label} coverage mismatch: missing={missing!r}, unexpected={unexpected!r}"
    )


def _source_cluster_candidate(
    raw: Mapping[str, Any],
    expected_key: whitebox_schema.SemanticKey,
    *,
    path: str,
) -> tuple[str, str, str]:
    metadata = raw.get("source")
    if isinstance(metadata, Mapping):
        source_id = _normalize_source_id(
            metadata.get("source_id"), f"{path}.source.source_id"
        )
        source_hash = _require_sha256(
            metadata.get("text_sha256"), f"{path}.source.text_sha256"
        )
        return expected_key[1], source_id, source_hash
    return expected_key[1], expected_key[2], "legacy-id-fallback"


def _resolve_source_clusters(
    blackbox_index: Mapping[whitebox_schema.SemanticKey, Mapping[str, Any]],
) -> dict[whitebox_schema.SemanticKey, tuple[str, str, str]]:
    candidates = {
        key: _source_cluster_candidate(row, key, path=f"blackbox[{key!r}]")
        for key, row in blackbox_index.items()
    }
    metadata_by_legacy_alias: dict[tuple[str, str], tuple[str, str, str]] = {}
    for key, candidate in candidates.items():
        if candidate[2] == "legacy-id-fallback":
            continue
        alias = (key[1], key[2])
        previous = metadata_by_legacy_alias.get(alias)
        if previous is not None and previous != candidate:
            raise BlackboxValidationError(
                f"conflicting source metadata for audited alias {alias!r}"
            )
        metadata_by_legacy_alias[alias] = candidate
    return {
        key: (
            metadata_by_legacy_alias.get((key[1], key[2]), candidate)
            if candidate[2] == "legacy-id-fallback"
            else candidate
        )
        for key, candidate in candidates.items()
    }


def _validate_blackbox_record(
    raw: Mapping[str, Any],
    canonical_source: Mapping[str, Any],
    *,
    path: str,
    resolved_cluster_key: tuple[str, str, str] | None = None,
) -> tuple[
    tuple[str, str, str],
    tuple[float, ...],
    tuple[float, ...],
    dict[str, tuple[float, ...]],
]:
    """Validate source parity, primary aggregate values, and diagnostics."""

    if not isinstance(raw, Mapping):
        raise BlackboxValidationError(f"{path}: must be an object")

    expected_key = whitebox_schema.semantic_key(canonical_source)
    try:
        raw_key = whitebox_schema.semantic_key(raw)
    except (TypeError, ValueError) as exc:
        raise BlackboxValidationError(f"{path}: invalid semantic key: {exc}") from exc
    if raw_key != expected_key:
        raise BlackboxValidationError(
            f"{path}: semantic key {raw_key!r} does not match manifest {expected_key!r}"
        )

    # Re-freeze the exact scored text from the referenced record.  The manifest's
    # persisted inclusion decisions are authoritative and part of the input hash.
    try:
        rebuilt = whitebox_schema.build_source_row(
            raw,
            source_file=canonical_source["source_file"],
            cf_included=[
                entry["included"] for entry in canonical_source["counterfactuals"]
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BlackboxValidationError(
            f"{path}: cannot reconstruct canonical source inputs: {exc}"
        ) from exc
    if rebuilt["scoring_input_sha256"] != canonical_source["scoring_input_sha256"]:
        raise BlackboxValidationError(
            f"{path}: scoring_input_sha256 does not match frozen source manifest"
        )

    cluster_key = resolved_cluster_key or _source_cluster_candidate(
        raw, expected_key, path=path
    )

    metrics = raw.get("level_metrics")
    if not isinstance(metrics, Mapping) or set(metrics) != set(LEVELS):
        raise BlackboxValidationError(
            f"{path}.level_metrics: levels must be exactly {list(LEVELS)!r}"
        )

    aggregate_excess: list[float] = []
    aggregate_actual: list[float] = []
    diagnostic_values: dict[str, list[float]] = {name: [] for name in COMPRESSORS}
    diagnostic_complete = {name: True for name in COMPRESSORS}
    expected_cf_n = sum(
        bool(entry["included"]) for entry in canonical_source["counterfactuals"]
    )

    for level in LEVELS:
        level_path = f"{path}.level_metrics.{level}"
        entry = metrics[level]
        if not isinstance(entry, Mapping):
            raise BlackboxValidationError(f"{level_path}: must be an object")
        actual = _finite_number(entry.get("actual_ratio"), level_path + ".actual_ratio")
        baseline = _finite_number(entry.get("baseline_mean"), level_path + ".baseline_mean")
        excess = _finite_number(entry.get("excess_ratio"), level_path + ".excess_ratio")
        if not math.isclose(actual - baseline, excess, rel_tol=0.0, abs_tol=1e-12):
            raise BlackboxValidationError(
                f"{level_path}.excess_ratio: must equal actual_ratio - baseline_mean"
            )
        baseline_n = _nonnegative_int(
            entry.get("baseline_n_valid"), level_path + ".baseline_n_valid"
        )
        if baseline_n != expected_cf_n:
            raise BlackboxValidationError(
                f"{level_path}.baseline_n_valid: {baseline_n} != manifest inclusion count {expected_cf_n}"
            )
        output_chars = _nonnegative_int(entry.get("output_chars"), level_path + ".output_chars")
        if output_chars != len(canonical_source["levels"][level]["output"]):
            raise BlackboxValidationError(
                f"{level_path}.output_chars: does not match frozen level output"
            )
        aggregate_actual.append(actual)
        aggregate_excess.append(excess)

        per_compressor = entry.get("per_compressor")
        if per_compressor in (None, {}):
            for compressor in COMPRESSORS:
                diagnostic_complete[compressor] = False
            continue
        if not isinstance(per_compressor, Mapping) or set(per_compressor) != set(COMPRESSORS):
            raise BlackboxValidationError(
                f"{level_path}.per_compressor: when present, keys must be exactly {list(COMPRESSORS)!r}"
            )
        for compressor in COMPRESSORS:
            pc_path = f"{level_path}.per_compressor.{compressor}"
            pc = per_compressor[compressor]
            if not isinstance(pc, Mapping):
                raise BlackboxValidationError(f"{pc_path}: must be an object")
            pc_actual = _finite_number(pc.get("actual_ratio"), pc_path + ".actual_ratio")
            pc_baseline = _finite_number(pc.get("baseline_mean"), pc_path + ".baseline_mean")
            pc_excess = _finite_number(pc.get("excess_ratio"), pc_path + ".excess_ratio")
            if not math.isclose(
                pc_actual - pc_baseline, pc_excess, rel_tol=0.0, abs_tol=1e-12
            ):
                raise BlackboxValidationError(
                    f"{pc_path}.excess_ratio: must equal actual_ratio - baseline_mean"
                )
            diagnostic_values[compressor].append(pc_excess)

    diagnostics = {
        compressor: tuple(values)
        for compressor, values in diagnostic_values.items()
        if diagnostic_complete[compressor] and len(values) == len(LEVELS)
    }
    return cluster_key, tuple(aggregate_excess), tuple(aggregate_actual), diagnostics


def _index_explicit_blackbox_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[whitebox_schema.SemanticKey, Mapping[str, Any]], str]:
    result: dict[whitebox_schema.SemanticKey, Mapping[str, Any]] = {}
    row_hashes: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise BlackboxValidationError(f"blackbox[{index}]: must be an object")
        key = whitebox_schema.semantic_key(row)
        if key in result:
            raise CoverageError(f"blackbox[{index}]: duplicate semantic key {key!r}")
        result[key] = row
        row_hashes.append(
            {
                "semantic_key": list(key),
                "sha256": whitebox_schema.canonical_row_sha256(row),
            }
        )
    row_hashes.sort(key=lambda entry: tuple(entry["semantic_key"]))
    return result, _sha256(whitebox_schema.canonical_json_bytes(row_hashes))


def _load_manifest_blackbox_rows(
    source_index: Mapping[whitebox_schema.SemanticKey, Mapping[str, Any]],
    *,
    source_base_dir: str | Path | None,
    expected_file_sha256_by_key: Mapping[
        whitebox_schema.SemanticKey, str
    ] | None = None,
) -> tuple[dict[whitebox_schema.SemanticKey, Mapping[str, Any]], str]:
    base = Path(source_base_dir) if source_base_dir is not None else Path.cwd()
    result: dict[whitebox_schema.SemanticKey, Mapping[str, Any]] = {}
    artifact_hashes: list[dict[str, Any]] = []
    used_paths: dict[Path, whitebox_schema.SemanticKey] = {}

    for key, source in sorted(source_index.items()):
        declared = source.get("source_file")
        if not isinstance(declared, str) or not declared.strip():
            raise CoverageError(f"source {key!r}: source_file is required for manifest-bound analysis")
        path = Path(declared)
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
        previous = used_paths.get(path)
        if previous is not None:
            raise CoverageError(
                f"source_file {path} is shared by semantic keys {previous!r} and {key!r}"
            )
        used_paths[path] = key
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            raise CoverageError(f"source {key!r}: cannot read {path}: {exc}") from exc
        actual_file_hash = _sha256(raw_bytes)
        if expected_file_sha256_by_key is not None:
            expected_file_hash = expected_file_sha256_by_key.get(key)
            if expected_file_hash is None:
                raise CoverageError(f"source {key!r}: no frozen debug-file hash")
            if actual_file_hash != expected_file_hash:
                raise CoverageError(
                    f"source {key!r}: debug file hash drift "
                    f"{actual_file_hash} != {expected_file_hash}"
                )
        raw = whitebox_schema.strict_json_loads(raw_bytes, path=str(path))
        if not isinstance(raw, Mapping):
            raise BlackboxValidationError(f"{path}: must contain one JSON object")
        raw_key = whitebox_schema.semantic_key(raw)
        if raw_key != key:
            raise CoverageError(
                f"source {key!r}: declared file {path} contains {raw_key!r}"
            )
        if raw_key in result:
            raise CoverageError(f"duplicate black-box semantic key {raw_key!r}")
        result[raw_key] = raw
        artifact_hashes.append(
            {
                "semantic_key": list(key),
                "source_file": declared,
                "sha256": actual_file_hash,
            }
        )

    return result, _sha256(whitebox_schema.canonical_json_bytes(artifact_hashes))


def prepare_manifest_bound_analysis(
    source_rows: Sequence[Mapping[str, Any]],
    score_rows: Sequence[Mapping[str, Any]],
    *,
    blackbox_rows: Sequence[Mapping[str, Any]] | None = None,
    source_base_dir: str | Path | None = None,
    expected_blackbox_file_sha256_by_key: Mapping[
        whitebox_schema.SemanticKey, str
    ] | None = None,
    expected_evaluator: str | None = None,
    expected_protocol_sha256: str | None = None,
) -> PreparedAnalysis:
    """Validate all artifacts and perform exact v2 source/score/black-box joins.

    Multiple evaluators may be supplied together.  Every evaluator must cover
    the complete source manifest exactly once.
    """

    sources = tuple(source_rows)
    scores = tuple(score_rows)
    if not sources:
        raise CoverageError("source manifest is empty")
    if not scores:
        raise CoverageError("score artifact is empty")

    # These are the canonical validators; duplicate/conflicting rows fail here.
    source_index = whitebox_schema.index_source_rows(sources)
    score_validations = whitebox_schema.validate_score_rows(
        scores,
        sources=source_index,
        expected_evaluator=expected_evaluator,
        expected_protocol_sha256=expected_protocol_sha256,
    )

    if blackbox_rows is None:
        blackbox_index, blackbox_hash = _load_manifest_blackbox_rows(
            source_index,
            source_base_dir=source_base_dir,
            expected_file_sha256_by_key=expected_blackbox_file_sha256_by_key,
        )
    else:
        blackbox_index, blackbox_hash = _index_explicit_blackbox_rows(
            tuple(blackbox_rows)
        )

    source_keys = set(source_index)
    blackbox_keys = set(blackbox_index)
    if source_keys != blackbox_keys:
        raise _coverage_error("source/black-box", source_keys, blackbox_keys)
    resolved_clusters = _resolve_source_clusters(blackbox_index)

    scores_by_evaluator: dict[str, dict[whitebox_schema.SemanticKey, Mapping[str, Any]]] = {}
    validations_by_evaluator: dict[
        str, dict[whitebox_schema.SemanticKey, whitebox_schema.ScoreValidation]
    ] = {}
    for row, validation in zip(scores, score_validations):
        evaluator = row["evaluator"]
        scores_by_evaluator.setdefault(evaluator, {})[validation.semantic_key] = row
        validations_by_evaluator.setdefault(evaluator, {})[
            validation.semantic_key
        ] = validation

    by_evaluator: dict[str, tuple[PairedItem, ...]] = {}
    for evaluator in sorted(scores_by_evaluator):
        evaluator_scores = scores_by_evaluator[evaluator]
        score_keys = set(evaluator_scores)
        if score_keys != source_keys:
            raise _coverage_error(
                f"source/score evaluator={evaluator!r}", source_keys, score_keys
            )

        paired: list[PairedItem] = []
        for key in sorted(source_keys):
            source = source_index[key]
            score = evaluator_scores[key]
            score_validation = validations_by_evaluator[evaluator][key]
            if score_validation.scoring_input_sha256 != source["scoring_input_sha256"]:
                # Normally caught by validate_score_rows(source=...), retained as
                # an explicit invariant at the actual join boundary.
                raise CoverageError(
                    f"score {score_validation.score_key!r}: scoring_input_sha256 mismatch"
                )
            cluster, bb_excess, bb_actual, per_compressor = _validate_blackbox_record(
                blackbox_index[key],
                source,
                path=f"blackbox[{key!r}]",
                resolved_cluster_key=resolved_clusters[key],
            )
            paired.append(
                PairedItem(
                    semantic_key=key,
                    scoring_input_sha256=score_validation.scoring_input_sha256,
                    evaluator=evaluator,
                    evaluator_sha256=score_validation.evaluator_sha256,
                    protocol_sha256=score_validation.protocol_sha256,
                    source_cluster_key=cluster,
                    whitebox_phi=tuple(
                        float(score["levels"][level]["phi"])
                        for level in LEVELS
                    ),
                    whitebox_excess=tuple(
                        float(score["level_excess"][level]["phi_excess"])
                        for level in LEVELS
                    ),
                    blackbox_excess=bb_excess,
                    blackbox_actual=bb_actual,
                    blackbox_per_compressor=per_compressor,
                )
            )
        by_evaluator[evaluator] = tuple(paired)

    return PreparedAnalysis(
        by_evaluator=by_evaluator,
        source_manifest_sha256=_canonical_set_sha256(sources),
        score_manifest_sha256=_canonical_set_sha256(scores, score_rows=True),
        blackbox_artifact_set_sha256=blackbox_hash,
        source_count=len(sources),
        blackbox_count=len(blackbox_index),
    )


def _flat(items: Sequence[PairedItem], attribute: str) -> list[float]:
    return [value for item in items for value in getattr(item, attribute)]


def _same_constant(values: Sequence[float]) -> bool:
    return not values or min(values) == max(values)


def _statistic_value(result: Any) -> float | None:
    value = getattr(result, "statistic", result)
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _safe_spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2 or _same_constant(xs) or _same_constant(ys):
        return None
    return _statistic_value(spearmanr(xs, ys))


def _safe_pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2 or _same_constant(xs) or _same_constant(ys):
        return None
    return _statistic_value(pearsonr(xs, ys))


def kendall_tau_b(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Return SciPy Kendall tau-b, with undefined results represented by None."""

    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return _statistic_value(kendalltau(xs, ys, variant="b"))


def mann_whitney_auc(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Tie-aware unpaired AUC = P(X>Y) + 0.5 P(X=Y), in O(n log n)."""

    if not xs or not ys:
        return None
    ordered_y = sorted(float(value) for value in ys)
    wins = 0.0
    for raw_x in xs:
        x = float(raw_x)
        lower = bisect.bisect_left(ordered_y, x)
        upper = bisect.bisect_right(ordered_y, x)
        wins += lower + 0.5 * (upper - lower)
    value = wins / (len(xs) * len(ys))
    return value if math.isfinite(value) else None


def _mean_or_none(values: Sequence[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(value)]
    return statistics.fmean(finite) if finite else None


def _median_or_none(values: Sequence[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(value)]
    return statistics.median(finite) if finite else None


def _agreement_metrics(items: Sequence[PairedItem]) -> dict[str, Any]:
    wb = _flat(items, "whitebox_excess")
    bb = _flat(items, "blackbox_excess")
    n_pairs = len(wb)

    within_level: dict[str, Any] = {}
    for index, level in enumerate(LEVELS):
        level_wb = [item.whitebox_excess[index] for item in items]
        level_bb = [item.blackbox_excess[index] for item in items]
        within_level[level] = {
            "spearman_rho": _safe_spearman(level_wb, level_bb),
            "effective_n": len(level_wb),
            "method": "scipy.stats.spearmanr",
        }

    centered_wb: list[float] = []
    centered_bb: list[float] = []
    vector_taus: list[float | None] = []
    for item in items:
        wb_mean = statistics.fmean(item.whitebox_excess)
        bb_mean = statistics.fmean(item.blackbox_excess)
        centered_wb.extend(value - wb_mean for value in item.whitebox_excess)
        centered_bb.extend(value - bb_mean for value in item.blackbox_excess)
        vector_taus.append(kendall_tau_b(item.whitebox_excess, item.blackbox_excess))

    effective_taus = [value for value in vector_taus if value is not None]
    wb_level_means = [
        statistics.fmean(item.whitebox_excess[index] for item in items)
        for index in range(len(LEVELS))
    ]
    bb_level_means = [
        statistics.fmean(item.blackbox_excess[index] for item in items)
        for index in range(len(LEVELS))
    ]

    return {
        "pooled_gradient_agreement": {
            "description": (
                "White-box phi_excess vs aggregate black-box excess_ratio pooled "
                "over items and designed levels; this is gradient agreement, not "
                "within-level item agreement."
            ),
            "spearman_rho": _safe_spearman(wb, bb),
            "pearson_r": _safe_pearson(wb, bb),
            "effective_n": n_pairs,
            "methods": {
                "spearman": "scipy.stats.spearmanr",
                "pearson": "scipy.stats.pearsonr",
            },
        },
        "within_level_spearman": within_level,
        "item_centered_spearman": {
            "description": "Each method is mean-centered within semantic item before pooling.",
            "spearman_rho": _safe_spearman(centered_wb, centered_bb),
            "effective_n": len(centered_wb),
            "items": len(items),
            "method": "scipy.stats.spearmanr",
        },
        "per_item_vector_kendall_tau_b": {
            "description": "Tau-b between each item's white-box and aggregate black-box five-level vectors.",
            "mean_tau_b": _mean_or_none(vector_taus),
            "median_tau_b": _median_or_none(vector_taus),
            "effective_n": len(effective_taus),
            "undefined_n": len(vector_taus) - len(effective_taus),
            "method": "scipy.stats.kendalltau(variant='b')",
        },
        "level_mean_gradient_shape_agreement": {
            "whitebox_level_means": wb_level_means,
            "blackbox_level_means": bb_level_means,
            "spearman_rho": _safe_spearman(wb_level_means, bb_level_means),
            "pearson_r": _safe_pearson(wb_level_means, bb_level_means),
            "effective_n": len(LEVELS),
        },
    }


def _monotonic_rate(items: Sequence[PairedItem], attribute: str) -> float | None:
    if not items:
        return None
    return sum(
        all(left >= right for left, right in zip(values, values[1:]))
        for values in (getattr(item, attribute) for item in items)
    ) / len(items)


def _eta_squared(items: Sequence[PairedItem], attribute: str) -> float | None:
    values = _flat(items, attribute)
    if not values:
        return None
    grand_mean = statistics.fmean(values)
    total = sum((value - grand_mean) ** 2 for value in values)
    if total == 0.0:
        return None
    between = 0.0
    for index in range(len(LEVELS)):
        level_values = [getattr(item, attribute)[index] for item in items]
        between += len(level_values) * (statistics.fmean(level_values) - grand_mean) ** 2
    return between / total


def _sample_sd(values: Sequence[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def _cohens_d(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(ys) < 2:
        return None
    sx = _sample_sd(xs)
    sy = _sample_sd(ys)
    assert sx is not None and sy is not None
    denominator_df = len(xs) + len(ys) - 2
    pooled_variance = (
        (len(xs) - 1) * sx * sx + (len(ys) - 1) * sy * sy
    ) / denominator_df
    if pooled_variance <= 0.0:
        return None
    return (statistics.fmean(xs) - statistics.fmean(ys)) / math.sqrt(pooled_variance)


def _level_tau_values(
    items: Sequence[PairedItem], attribute: str
) -> list[float | None]:
    levels = list(range(1, len(LEVELS) + 1))
    return [kendall_tau_b(levels, getattr(item, attribute)) for item in items]


def _paired_wilcoxon(
    whitebox: Sequence[float | None],
    blackbox: Sequence[float | None],
    *,
    unit: str = "paired observations",
) -> dict[str, Any]:
    diffs = [
        float(bb) - float(wb)
        for wb, bb in zip(whitebox, blackbox)
        if wb is not None and bb is not None
    ]
    nonzero = [value for value in diffs if value != 0.0]
    if not nonzero:
        return {
            "statistic": None,
            "p_two_sided": None,
            "effective_n_nonzero": 0,
            "unit": unit,
            "method": "scipy.stats.wilcoxon",
        }
    try:
        result = wilcoxon(nonzero, alternative="two-sided")
        statistic = _statistic_value(result)
        pvalue = float(result.pvalue)
        if not math.isfinite(pvalue):
            pvalue = None
    except ValueError:
        statistic = None
        pvalue = None
    return {
        "statistic": statistic,
        "p_two_sided": pvalue,
        "effective_n_nonzero": len(nonzero),
        "unit": unit,
        "method": "scipy.stats.wilcoxon",
    }


def _precision_metrics(items: Sequence[PairedItem]) -> dict[str, Any]:
    adjacent_d: dict[str, Any] = {}
    adjacent_auc: dict[str, Any] = {}
    for index in range(len(LEVELS) - 1):
        pair = f"{LEVELS[index]}_vs_{LEVELS[index + 1]}"
        wb_left = [item.whitebox_excess[index] for item in items]
        wb_right = [item.whitebox_excess[index + 1] for item in items]
        bb_left = [item.blackbox_excess[index] for item in items]
        bb_right = [item.blackbox_excess[index + 1] for item in items]
        adjacent_d[pair] = {
            "whitebox": _cohens_d(wb_left, wb_right),
            "blackbox_aggregate": _cohens_d(bb_left, bb_right),
            "effective_n_per_group": len(items),
        }
        adjacent_auc[pair] = {
            "whitebox": mann_whitney_auc(wb_left, wb_right),
            "blackbox_aggregate": mann_whitney_auc(bb_left, bb_right),
            "effective_n_left": len(items),
            "effective_n_right": len(items),
        }

    wb_taus = _level_tau_values(items, "whitebox_excess")
    bb_taus = _level_tau_values(items, "blackbox_excess")
    wb_tau_n = sum(value is not None for value in wb_taus)
    bb_tau_n = sum(value is not None for value in bb_taus)
    tau_pairs_by_source: dict[
        tuple[str, str, str], list[tuple[float, float]]
    ] = {}
    for item, wb_tau, bb_tau in zip(items, wb_taus, bb_taus):
        if wb_tau is None or bb_tau is None:
            continue
        tau_pairs_by_source.setdefault(item.source_cluster_key, []).append(
            (float(wb_tau), float(bb_tau))
        )
    source_wb_taus = [
        statistics.fmean(pair[0] for pair in pairs)
        for _key, pairs in sorted(tau_pairs_by_source.items())
    ]
    source_bb_taus = [
        statistics.fmean(pair[1] for pair in pairs)
        for _key, pairs in sorted(tau_pairs_by_source.items())
    ]
    return {
        "monotonic_nonincreasing_rate": {
            "whitebox": _monotonic_rate(items, "whitebox_excess"),
            "blackbox_aggregate": _monotonic_rate(items, "blackbox_excess"),
            "effective_n": len(items),
        },
        "eta_squared_level_effect": {
            "whitebox": _eta_squared(items, "whitebox_excess"),
            "blackbox_aggregate": _eta_squared(items, "blackbox_excess"),
            "effective_n_item_level_pairs": len(items) * len(LEVELS),
        },
        "adjacent_unpaired_cohens_d": adjacent_d,
        "adjacent_unpaired_mann_whitney_auc": {
            "description": (
                "Tie-aware unpaired AUC P(score at earlier level > later level) "
                "+ 0.5 P(tie), computed in O(n log n)."
            ),
            "pairs": adjacent_auc,
        },
        "per_item_score_vs_level_kendall_tau_b": {
            "description": "Level index is 1..5; a decreasing contribution gradient has negative tau-b.",
            "mean_whitebox": _mean_or_none(wb_taus),
            "mean_blackbox_aggregate": _mean_or_none(bb_taus),
            "effective_n_whitebox": wb_tau_n,
            "effective_n_blackbox": bb_tau_n,
            "source_cluster_wilcoxon_blackbox_minus_whitebox": _paired_wilcoxon(
                source_wb_taus,
                source_bb_taus,
                unit="underlying source; generation-model tau values averaged within source",
            ),
            "method": "scipy.stats.kendalltau(variant='b')",
        },
    }


def _slice_metrics(items: Sequence[PairedItem], attribute: str) -> dict[str, Any]:
    grouped: dict[str, list[PairedItem]] = {}
    for item in items:
        grouped.setdefault(getattr(item, attribute), []).append(item)
    result: dict[str, Any] = {}
    for name in sorted(grouped):
        rows = grouped[name]
        wb = _flat(rows, "whitebox_excess")
        bb = _flat(rows, "blackbox_excess")
        result[name] = {
            "pooled_gradient_spearman_rho": _safe_spearman(wb, bb),
            "items": len(rows),
            "effective_n_item_level_pairs": len(wb),
        }
    return result


def _per_compressor_diagnostics(items: Sequence[PairedItem]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for compressor in COMPRESSORS:
        complete = [
            item for item in items if compressor in item.blackbox_per_compressor
        ]
        replaced = [
            replace(item, blackbox_excess=item.blackbox_per_compressor[compressor])
            for item in complete
        ]
        diagnostics[compressor] = {
            "role": "diagnostic_only_not_primary_blackbox_measure",
            "available_items": len(complete),
            "missing_items": len(items) - len(complete),
            "effective_n_item_level_pairs": len(complete) * len(LEVELS),
            "agreement": _agreement_metrics(replaced) if replaced else None,
        }
    return diagnostics


def _secondary_correlations(items: Sequence[PairedItem]) -> dict[str, Any]:
    """Legacy-comparable correlations kept outside the primary estimands."""

    whitebox_phi = _flat(items, "whitebox_phi")
    blackbox_excess = _flat(items, "blackbox_excess")
    blackbox_actual = _flat(items, "blackbox_actual")

    def correlation(xs: Sequence[float], ys: Sequence[float]) -> dict[str, Any]:
        return {
            "spearman_rho": _safe_spearman(xs, ys),
            "pearson_r": _safe_pearson(xs, ys),
            "effective_n": len(xs),
        }

    return {
        "role": "diagnostic_only_not_primary_agreement",
        "whitebox_raw_phi_vs_blackbox_aggregate_excess": correlation(
            whitebox_phi, blackbox_excess
        ),
        "whitebox_raw_phi_vs_blackbox_aggregate_actual": correlation(
            whitebox_phi, blackbox_actual
        ),
    }


def _source_clusters(
    items: Sequence[PairedItem],
) -> list[tuple[tuple[str, str, str], tuple[PairedItem, ...]]]:
    grouped: dict[tuple[str, str, str], list[PairedItem]] = {}
    for item in items:
        grouped.setdefault(item.source_cluster_key, []).append(item)
    return [
        (key, tuple(sorted(rows, key=lambda item: item.semantic_key)))
        for key, rows in sorted(grouped.items())
    ]


def resample_source_clusters(
    items: Sequence[PairedItem], *, seed: int, replicate: int = 0
) -> tuple[tuple[PairedItem, ...], tuple[tuple[str, str, str], ...]]:
    """Return one deterministic source-cluster resample (useful for audit/tests)."""

    if type(seed) is not int or type(replicate) is not int or replicate < 0:
        raise AnalysisError("seed and non-negative replicate must be integers")
    clusters = _source_clusters(items)
    if not clusters:
        raise AnalysisError("cannot bootstrap an empty item set")
    rng = random.Random(seed)
    selected: list[int] = []
    for _ in range(replicate + 1):
        selected = [rng.randrange(len(clusters)) for _ in clusters]
    sampled = tuple(
        item for cluster_index in selected for item in clusters[cluster_index][1]
    )
    selected_keys = tuple(clusters[index][0] for index in selected)
    return sampled, selected_keys


def _bootstrap_point_statistics(
    items: Sequence[PairedItem],
    *,
    item_tau_cache: dict[int, tuple[float | None, float | None, float | None]] | None = None,
) -> dict[str, tuple[float | None, int]]:
    wb = _flat(items, "whitebox_excess")
    bb = _flat(items, "blackbox_excess")
    centered_wb: list[float] = []
    centered_bb: list[float] = []
    vector_taus: list[float | None] = []
    wb_level_taus: list[float | None] = []
    bb_level_taus: list[float | None] = []
    level_numbers = list(range(1, len(LEVELS) + 1))
    cache = item_tau_cache if item_tau_cache is not None else {}
    for item in items:
        wb_mean = statistics.fmean(item.whitebox_excess)
        bb_mean = statistics.fmean(item.blackbox_excess)
        centered_wb.extend(value - wb_mean for value in item.whitebox_excess)
        centered_bb.extend(value - bb_mean for value in item.blackbox_excess)
        cached = cache.get(id(item))
        if cached is None:
            cached = (
                kendall_tau_b(item.whitebox_excess, item.blackbox_excess),
                kendall_tau_b(level_numbers, item.whitebox_excess),
                kendall_tau_b(level_numbers, item.blackbox_excess),
            )
            cache[id(item)] = cached
        vector_tau, wb_level_tau, bb_level_tau = cached
        vector_taus.append(vector_tau)
        wb_level_taus.append(wb_level_tau)
        bb_level_taus.append(bb_level_tau)
    paired_level_taus = [
        (wb_tau, bb_tau)
        for wb_tau, bb_tau in zip(wb_level_taus, bb_level_taus)
        if wb_tau is not None and bb_tau is not None
    ]
    eta_wb = _eta_squared(items, "whitebox_excess")
    eta_bb = _eta_squared(items, "blackbox_excess")
    mono_wb = _monotonic_rate(items, "whitebox_excess")
    mono_bb = _monotonic_rate(items, "blackbox_excess")
    result: dict[str, tuple[float | None, int]] = {
        "pooled_gradient_agreement_spearman_rho": (
            _safe_spearman(wb, bb),
            len(wb),
        ),
        "item_centered_spearman_rho": (
            _safe_spearman(centered_wb, centered_bb),
            len(centered_wb),
        ),
        "mean_per_item_vector_kendall_tau_b": (
            _mean_or_none(vector_taus),
            sum(value is not None for value in vector_taus),
        ),
        "eta_squared_whitebox": (eta_wb, len(wb)),
        "eta_squared_blackbox_aggregate": (eta_bb, len(bb)),
        "eta_squared_difference_blackbox_minus_whitebox": (
            None if eta_wb is None or eta_bb is None else eta_bb - eta_wb,
            min(len(wb), len(bb)),
        ),
        "mean_level_tau_b_whitebox": (
            _mean_or_none(wb_level_taus),
            sum(value is not None for value in wb_level_taus),
        ),
        "mean_level_tau_b_blackbox_aggregate": (
            _mean_or_none(bb_level_taus),
            sum(value is not None for value in bb_level_taus),
        ),
        "mean_level_tau_b_difference_blackbox_minus_whitebox": (
            _mean_or_none(
                [bb_tau - wb_tau for wb_tau, bb_tau in paired_level_taus]
            ),
            len(paired_level_taus),
        ),
        "monotonic_rate_whitebox": (mono_wb, len(items)),
        "monotonic_rate_blackbox_aggregate": (mono_bb, len(items)),
        "monotonic_rate_difference_blackbox_minus_whitebox": (
            None if mono_wb is None or mono_bb is None else mono_bb - mono_wb,
            len(items),
        ),
    }
    return result


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def source_cluster_bootstrap(
    items: Sequence[PairedItem], *, n_resamples: int, seed: int = DEFAULT_SEED
) -> dict[str, Any]:
    """Deterministic 95% percentile bootstrap over underlying source clusters."""

    if type(n_resamples) is not int or n_resamples < 0:
        raise AnalysisError("n_resamples must be a non-negative integer")
    if type(seed) is not int:
        raise AnalysisError("seed must be an integer")
    clusters = _source_clusters(items)
    if not clusters:
        raise AnalysisError("cannot bootstrap an empty item set")
    if n_resamples == 0:
        return {
            "enabled": False,
            "method": "source-cluster percentile bootstrap",
            "confidence_level": 0.95,
            "seed": seed,
            "n_resamples": 0,
            "cluster_count": len(clusters),
            "cluster_definition": ["domain", "canonical_item_id"],
            "resampling_unit": "all generation-model rows and all five levels for one source",
            "metrics": {},
        }

    rng = random.Random(seed)
    item_tau_cache: dict[
        int, tuple[float | None, float | None, float | None]
    ] = {}
    point = _bootstrap_point_statistics(items, item_tau_cache=item_tau_cache)
    accumulators: dict[str, list[float]] = {name: [] for name in point}
    effective_ns: dict[str, list[int]] = {name: [] for name in point}
    sampled_item_ns: list[int] = []

    for _ in range(n_resamples):
        selected = [rng.randrange(len(clusters)) for _ in clusters]
        sample = tuple(
            item for cluster_index in selected for item in clusters[cluster_index][1]
        )
        sampled_item_ns.append(len(sample))
        values = _bootstrap_point_statistics(
            sample, item_tau_cache=item_tau_cache
        )
        for name, (value, effective_n) in values.items():
            if value is not None and math.isfinite(value):
                accumulators[name].append(float(value))
                effective_ns[name].append(effective_n)

    metrics: dict[str, Any] = {}
    for name in point:
        finite_values = accumulators[name]
        finite_ns = effective_ns[name]
        metrics[name] = {
            "point": point[name][0],
            "point_effective_n": point[name][1],
            "ci_95_percentile": {
                "lower": _percentile(finite_values, 0.025),
                "upper": _percentile(finite_values, 0.975),
            },
            "finite_resamples": len(finite_values),
            "undefined_resamples": n_resamples - len(finite_values),
            "resample_effective_n_min": min(finite_ns) if finite_ns else 0,
            "resample_effective_n_max": max(finite_ns) if finite_ns else 0,
        }

    return {
        "enabled": True,
        "method": "source-cluster percentile bootstrap",
        "confidence_level": 0.95,
        "seed": seed,
        "n_resamples": n_resamples,
        "cluster_count": len(clusters),
        "cluster_definition": [
            "domain",
            "source_id_or_item_id",
            "source_text_sha256_or_legacy_id_fallback",
        ],
        "resampling_unit": "all generation-model rows and all five levels for one source",
        "sampled_cluster_count_per_resample": len(clusters),
        "sampled_item_n_min": min(sampled_item_ns),
        "sampled_item_n_max": max(sampled_item_ns),
        "metrics": metrics,
    }


def _single_hash(items: Sequence[PairedItem], attribute: str, label: str) -> str | None:
    values = {getattr(item, attribute) for item in items}
    if len(values) != 1:
        raise AnalysisError(f"{label} must be uniform within one evaluator: {sorted(values)!r}")
    return next(iter(values))


def _raw_bootstrap_view(bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the agreement CIs requested for the raw/raw derivative."""

    metric_names = {
        "pooled_raw_spearman_rho": "pooled_gradient_agreement_spearman_rho",
        "item_centered_raw_spearman_rho": "item_centered_spearman_rho",
        "mean_per_item_raw_vector_kendall_tau_b": (
            "mean_per_item_vector_kendall_tau_b"
        ),
    }
    source_metrics = bootstrap["metrics"]
    result = {key: value for key, value in bootstrap.items() if key != "metrics"}
    result["metrics"] = {
        output_name: source_metrics[source_name]
        for output_name, source_name in metric_names.items()
        if source_name in source_metrics
    }
    return result


def _raw_slice_view(slices: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dimension, groups in slices.items():
        result[dimension] = {
            name: {
                "pooled_raw_spearman_rho": row[
                    "pooled_gradient_spearman_rho"
                ],
                "items": row["items"],
                "effective_n_item_level_pairs": row[
                    "effective_n_item_level_pairs"
                ],
            }
            for name, row in groups.items()
        }
    return result


def _analyze_raw_paired_items(
    items: Sequence[PairedItem],
    *,
    n_bootstrap: int,
    seed: int,
    mode: str,
) -> dict[str, Any]:
    """Reuse the frozen excess statistics on an immutable raw/raw value view."""

    raw_items = tuple(
        replace(
            item,
            whitebox_excess=item.whitebox_phi,
            blackbox_excess=item.blackbox_actual,
            blackbox_per_compressor={},
        )
        for item in items
    )
    base = analyze_paired_items(
        raw_items,
        n_bootstrap=n_bootstrap,
        seed=seed,
        mode=mode,
        comparison_mode="excess",
    )
    agreement = base["agreement"]
    pooled = agreement["pooled_gradient_agreement"]
    centered = agreement["item_centered_spearman"]
    vector_tau = agreement["per_item_vector_kendall_tau_b"]
    return to_strict_json_value(
        {
            "analysis_schema_version": 1,
            "mode": f"{mode}_raw_raw_derived",
            "comparison": {
                "id": "raw_phi_vs_aggregate_actual_ratio",
                "whitebox_field": "levels.<level>.phi",
                "whitebox_measure": "raw_phi",
                "whitebox_transform": "none",
                "blackbox_field": "level_metrics.<level>.actual_ratio",
                "blackbox_measure": "aggregate_actual_ratio",
                "blackbox_variant": "aggregate",
                "blackbox_transform": "none",
                "per_compressor_included": False,
            },
            "evaluator": base["evaluator"],
            "evaluator_sha256": base["evaluator_sha256"],
            "protocol_sha256": base["protocol_sha256"],
            "coverage": base["coverage"],
            "agreement": {
                "pooled_raw_agreement": {
                    "description": (
                        "Raw white-box phi vs aggregate black-box actual_ratio pooled "
                        "over items and designed levels; this is gradient agreement, "
                        "not within-level item agreement."
                    ),
                    "spearman_rho": pooled["spearman_rho"],
                    "pearson_r": pooled["pearson_r"],
                    "effective_n": pooled["effective_n"],
                    "methods": pooled["methods"],
                },
                "within_level_raw_spearman": agreement[
                    "within_level_spearman"
                ],
                "item_centered_raw_spearman": {
                    "description": centered["description"],
                    "spearman_rho": centered["spearman_rho"],
                    "effective_n": centered["effective_n"],
                    "items": centered["items"],
                    "method": centered["method"],
                },
                "per_item_raw_vector_kendall_tau_b": {
                    "description": (
                        "Tau-b between each item's raw white-box and aggregate "
                        "black-box five-level vectors."
                    ),
                    "mean_tau_b": vector_tau["mean_tau_b"],
                    "median_tau_b": vector_tau["median_tau_b"],
                    "effective_n": vector_tau["effective_n"],
                    "undefined_n": vector_tau["undefined_n"],
                    "method": vector_tau["method"],
                },
            },
            "slices": _raw_slice_view(base["slices"]),
            "bootstrap": _raw_bootstrap_view(base["bootstrap"]),
        }
    )


def analyze_paired_items(
    items: Sequence[PairedItem],
    *,
    n_bootstrap: int = 0,
    seed: int = DEFAULT_SEED,
    mode: str = "manifest_bound_v2",
    comparison_mode: str = "excess",
) -> dict[str, Any]:
    """Analyze one evaluator's already validated and exactly covered pairs."""

    if comparison_mode not in ("excess", "raw"):
        raise AnalysisError(
            f"comparison_mode must be 'excess' or 'raw', got {comparison_mode!r}"
        )
    ordered = tuple(sorted(items, key=lambda item: item.semantic_key))
    if not ordered:
        raise AnalysisError("cannot analyze an empty paired dataset")
    evaluators = {item.evaluator for item in ordered}
    if len(evaluators) != 1:
        raise AnalysisError(f"expected one evaluator, got {sorted(evaluators)!r}")
    evaluator = next(iter(evaluators))
    if comparison_mode == "raw":
        return _analyze_raw_paired_items(
            ordered,
            n_bootstrap=n_bootstrap,
            seed=seed,
            mode=mode,
        )
    clusters = _source_clusters(ordered)
    agreement = _agreement_metrics(ordered)
    coverage = {
        "exact": mode == "manifest_bound_v2",
        "source_rows": len(ordered),
        "score_rows": len(ordered),
        "blackbox_rows": len(ordered),
        "joined_items": len(ordered),
        "item_level_pairs": len(ordered) * len(LEVELS),
        "source_clusters": len(clusters),
        "cluster_identity_policy": (
            "verified source metadata when present; a legacy row inherits metadata "
            "from the same audited (domain, item_id) group, otherwise that stable "
            "domain/item identity is the fallback"
        ),
        "levels": list(LEVELS),
        "level_effective_n": {level: len(ordered) for level in LEVELS},
        "generation_models": sorted({item.generation_model for item in ordered}),
        "domains": sorted({item.domain for item in ordered}),
        "missing_source_keys": [],
        "missing_score_keys": [],
        "missing_blackbox_keys": [],
        "unexpected_score_keys": [],
        "unexpected_blackbox_keys": [],
    }
    return to_strict_json_value(
        {
            "analysis_schema_version": 1,
            "mode": mode,
            "evaluator": evaluator,
            "evaluator_sha256": _single_hash(
                ordered, "evaluator_sha256", "evaluator_sha256"
            ),
            "protocol_sha256": _single_hash(
                ordered, "protocol_sha256", "protocol_sha256"
            ),
            "blackbox_primary_measure": {
                "field": "level_metrics.<level>.excess_ratio",
                "variant": "aggregate",
                "note": (
                    "Primary results use the canonical aggregate ratio; "
                    "per_compressor values are diagnostics only."
                ),
            },
            "coverage": coverage,
            "agreement": agreement,
            "precision_observables": _precision_metrics(ordered),
            "slices": {
                "by_generation_model": _slice_metrics(ordered, "generation_model"),
                "by_domain": _slice_metrics(ordered, "domain"),
            },
            "diagnostics": {
                "secondary_correlations": _secondary_correlations(ordered),
                "per_compressor": _per_compressor_diagnostics(ordered),
            },
            "bootstrap": source_cluster_bootstrap(
                ordered, n_resamples=n_bootstrap, seed=seed
            ),
        }
    )


def analyze_manifest_bound(
    source_rows: Sequence[Mapping[str, Any]],
    score_rows: Sequence[Mapping[str, Any]],
    *,
    blackbox_rows: Sequence[Mapping[str, Any]] | None = None,
    source_base_dir: str | Path | None = None,
    expected_blackbox_file_sha256_by_key: Mapping[
        whitebox_schema.SemanticKey, str
    ] | None = None,
    expected_evaluator: str | None = None,
    expected_protocol_sha256: str | None = None,
    n_bootstrap: int = 0,
    seed: int = DEFAULT_SEED,
    source_artifact_sha256: str | None = None,
    score_artifact_sha256es: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Prepare and analyze canonical v2 artifacts for one or more evaluators."""

    prepared = prepare_manifest_bound_analysis(
        source_rows,
        score_rows,
        blackbox_rows=blackbox_rows,
        source_base_dir=source_base_dir,
        expected_blackbox_file_sha256_by_key=expected_blackbox_file_sha256_by_key,
        expected_evaluator=expected_evaluator,
        expected_protocol_sha256=expected_protocol_sha256,
    )
    analyses = {
        evaluator: analyze_paired_items(
            items,
            n_bootstrap=n_bootstrap,
            seed=seed,
            mode="manifest_bound_v2",
        )
        for evaluator, items in sorted(prepared.by_evaluator.items())
    }
    evaluator_hashes = {
        evaluator: analysis["evaluator_sha256"]
        for evaluator, analysis in analyses.items()
    }
    protocol_hashes = {
        evaluator: analysis["protocol_sha256"]
        for evaluator, analysis in analyses.items()
    }
    result = {
        "analysis_schema_version": 1,
        "mode": "manifest_bound_v2",
        "lineage": {
            "source_manifest_sha256": prepared.source_manifest_sha256,
            "score_manifest_sha256": prepared.score_manifest_sha256,
            "blackbox_artifact_set_sha256": prepared.blackbox_artifact_set_sha256,
            "source_artifact_sha256": source_artifact_sha256,
            "score_artifact_sha256es": list(score_artifact_sha256es or []),
            "evaluator_sha256_by_evaluator": evaluator_hashes,
            "protocol_sha256_by_evaluator": protocol_hashes,
        },
        "coverage": {
            "exact": True,
            "source_rows": prepared.source_count,
            "blackbox_rows": prepared.blackbox_count,
            "evaluator_count": len(analyses),
            "evaluators": sorted(analyses),
            "score_rows": len(score_rows),
            "expected_score_rows": prepared.source_count * len(analyses),
        },
        "analyses": analyses,
    }
    return to_strict_json_value(result)


def to_strict_json_value(value: Any) -> Any:
    """Convert non-finite numeric results to null and reject unsupported values."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    # NumPy/SciPy scalar values expose item(); convert without importing NumPy.
    if hasattr(value, "item") and callable(value.item):
        return to_strict_json_value(value.item())
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise AnalysisError(f"JSON output key must be a string, got {key!r}")
            result[key] = to_strict_json_value(child)
        return result
    if isinstance(value, (list, tuple)):
        return [to_strict_json_value(child) for child in value]
    raise AnalysisError(f"unsupported JSON output value type: {type(value).__name__}")


def strict_json_dumps(value: Any, *, indent: int | None = 2) -> str:
    """Serialize analysis output as finite RFC-compatible JSON."""

    return json.dumps(
        to_strict_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        allow_nan=False,
    )


def reject_output_alias(
    output_path: str | Path,
    input_paths: Iterable[str | Path],
) -> None:
    """Refuse to overwrite any immutable analysis input."""

    output = Path(output_path).resolve()
    for raw in input_paths:
        candidate = Path(raw).resolve()
        if output == candidate:
            raise AnalysisError(f"analysis output aliases immutable input: {output}")


def write_strict_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    payload = (strict_json_dumps(value) + "\n").encode("utf-8")
    atomic_replace_bytes(destination, payload)


def load_legacy_paired(
    phi_path: str | Path, debug_dir: str | Path
) -> tuple[str, tuple[PairedItem, ...], dict[str, Any]]:
    """Strictly adapt the old ``--phi/--debug_dir`` inputs for non-publication use.

    This compatibility path has no canonical evaluator/protocol binding and is
    intentionally labeled ``legacy_nonpublication`` by callers.  Unlike the old
    analyzer it fails on every missing or incomplete row.
    """

    phi_file = Path(phi_path)
    raw_bytes = phi_file.read_bytes()
    document = whitebox_schema.strict_json_loads(raw_bytes, path=str(phi_file))
    if not isinstance(document, Mapping) or not isinstance(document.get("items"), list):
        raise AnalysisError(f"{phi_file}: expected legacy object with an items array")
    meta = document.get("meta")
    if not isinstance(meta, Mapping) or not isinstance(meta.get("eval_model"), str):
        raise AnalysisError(f"{phi_file}: missing meta.eval_model")
    evaluator = meta["eval_model"]
    seen: set[whitebox_schema.SemanticKey] = set()
    paired: list[PairedItem] = []
    debug_hashes: list[dict[str, Any]] = []

    for index, whitebox in enumerate(document["items"]):
        if not isinstance(whitebox, Mapping):
            raise AnalysisError(f"{phi_file}: items[{index}] must be an object")
        key = whitebox_schema.semantic_key(whitebox)
        if key in seen:
            raise CoverageError(f"{phi_file}: duplicate legacy semantic key {key!r}")
        seen.add(key)
        filename = whitebox.get("file")
        if not isinstance(filename, str) or not filename:
            raise CoverageError(f"{phi_file}: item {key!r} has no debug filename")
        debug_path = Path(debug_dir) / filename
        try:
            debug_bytes = debug_path.read_bytes()
        except OSError as exc:
            raise CoverageError(f"item {key!r}: cannot read {debug_path}: {exc}") from exc
        debug = whitebox_schema.strict_json_loads(debug_bytes, path=str(debug_path))
        if not isinstance(debug, Mapping) or whitebox_schema.semantic_key(debug) != key:
            raise CoverageError(f"{debug_path}: semantic key does not match {key!r}")
        metrics = debug.get("level_metrics")
        if not isinstance(metrics, Mapping) or set(metrics) != set(LEVELS):
            raise CoverageError(f"{debug_path}: incomplete level_metrics")

        def legacy_vector(container: Any, field: str, path: str) -> tuple[float, ...]:
            if not isinstance(container, Mapping) or set(container) != set(LEVELS):
                raise CoverageError(f"{path}: levels must be exactly L1-L5")
            return tuple(
                _finite_number(container[level].get(field), f"{path}.{level}.{field}")
                for level in LEVELS
            )

        source_metadata = debug.get("source")
        if isinstance(source_metadata, Mapping):
            _normalize_source_id(
                source_metadata.get("source_id"), f"{debug_path}.source.source_id"
            )
            _require_sha256(
                source_metadata.get("text_sha256"), f"{debug_path}.source.text_sha256"
            )
        bb_excess = legacy_vector(metrics, "excess_ratio", f"{debug_path}.level_metrics")
        bb_actual = legacy_vector(metrics, "actual_ratio", f"{debug_path}.level_metrics")
        pc: dict[str, tuple[float, ...]] = {}
        for compressor in COMPRESSORS:
            if all(
                isinstance(metrics[level].get("per_compressor"), Mapping)
                and compressor in metrics[level]["per_compressor"]
                for level in LEVELS
            ):
                pc[compressor] = tuple(
                    _finite_number(
                        metrics[level]["per_compressor"][compressor].get("excess_ratio"),
                        f"{debug_path}.level_metrics.{level}.per_compressor.{compressor}.excess_ratio",
                    )
                    for level in LEVELS
                )
        paired.append(
            PairedItem(
                semantic_key=key,
                scoring_input_sha256="legacy-unbound",
                evaluator=evaluator,
                evaluator_sha256=None,
                protocol_sha256=None,
                source_cluster_key=(key[1], key[2], "canonical-domain-item-id"),
                whitebox_phi=legacy_vector(
                    whitebox.get("level_excess"), "phi", f"items[{index}].level_excess"
                ),
                whitebox_excess=legacy_vector(
                    whitebox.get("level_excess"),
                    "phi_excess",
                    f"items[{index}].level_excess",
                ),
                blackbox_excess=bb_excess,
                blackbox_actual=bb_actual,
                blackbox_per_compressor=pc,
            )
        )
        debug_hashes.append(
            {"semantic_key": list(key), "sha256": _sha256(debug_bytes)}
        )

    debug_hashes.sort(key=lambda entry: tuple(entry["semantic_key"]))
    lineage = {
        "legacy_phi_artifact_sha256": _sha256(raw_bytes),
        "legacy_debug_artifact_set_sha256": _sha256(
            whitebox_schema.canonical_json_bytes(debug_hashes)
        ),
    }
    return evaluator, tuple(sorted(paired, key=lambda item: item.semantic_key)), lineage


__all__ = [
    "AnalysisError",
    "BlackboxValidationError",
    "COMPRESSORS",
    "CoverageError",
    "DEFAULT_SEED",
    "LEVELS",
    "LoadedRows",
    "PairedItem",
    "PreparedAnalysis",
    "analyze_manifest_bound",
    "analyze_paired_items",
    "kendall_tau_b",
    "load_legacy_paired",
    "load_rows",
    "mann_whitney_auc",
    "prepare_manifest_bound_analysis",
    "reject_output_alias",
    "resample_source_clusters",
    "source_cluster_bootstrap",
    "strict_json_dumps",
    "to_strict_json_value",
    "validate_finalized_lineage",
    "write_strict_json",
]
