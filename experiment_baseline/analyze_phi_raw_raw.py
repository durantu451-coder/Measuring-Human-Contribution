# -*- coding: utf-8 -*-
"""Pure-local, hash-bound raw/raw derivative of finalized baseline v2."""

from __future__ import annotations

import argparse
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiment_b import storage
from experiment_baseline import analysis_core, whitebox_core, whitebox_schema
from experiment_baseline.whitebox_core import expand_placeholder


ANALYSIS_SCHEMA = "experiment_baseline.phi_v2.raw_raw_derived_analysis"
MANIFEST_SCHEMA = "experiment_baseline.phi_v2.raw_raw_derived.manifest"
SCHEMA_VERSION = 1
MIGRATION_ID = "phi_v2_20260822T180934_7d329704f7ab"
PREPARE_PLAN_SHA256 = "112fec9cadbae99afee401beb66332fdaa7518dafb80f097413d42f6f73841c8"
RELEASE_INVENTORY_SHA256 = (
    "880cf8fe04a92c11a58f70be493a66cbed4e736c3fe6a6f543c7d3bfb5995332"
)
BLACKBOX_ARTIFACT_SET_SHA256 = (
    "a72f3a83d449ca747a85469b869ca5874b3e6a8959d93e2dce5d5b9172f44edd"
)
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260823
EXPECTED_ITEMS = 11222
EXPECTED_PAIRS = 56110
EXPECTED_CLUSTERS = 2551
EXPECTED_EVALUATORS = ("llama", "mixtral")
EXPECTED_GENERATION_MODEL_COUNTS = {
    "claude-opus-4-8": 1892,
    "claude-sonnet-5": 2320,
    "gemini-3.6-flash": 2240,
    "gpt-5.5": 2446,
    "gpt-5.6-sol": 2324,
}
EXPECTED_DOMAIN_COUNTS = {
    "arxiv": 2937,
    "news": 2856,
    "patent": 2760,
    "poetry": 2669,
}
EVALUATOR_DESCRIPTORS = {
    "llama": {
        "model_name": "Meta-Llama-3.1-8B-Instruct",
        "checkpoint": expand_placeholder("${HC_DATA_ROOT}/models/Meta-Llama-3.1-8B-Instruct"),
        "dtype": "bfloat16",
    },
    "mixtral": {
        "model_name": "Mixtral-8x7B-v0.1",
        "checkpoint": expand_placeholder("${HC_DATA_ROOT}/models/Mixtral-8x7B-v0.1"),
        "dtype": "float16",
    },
}
EXPECTED_POOLED = {
    "llama": {
        "spearman_rho": 0.9569662446504178,
        "pearson_r": 0.94824945540786,
    },
    "mixtral": {
        "spearman_rho": 0.9563448913917773,
        "pearson_r": 0.9497027276804683,
    },
}
OUTPUT_ROOT = "experiment_baseline/phi_v2_derived_results"
CODE_PATHS = (
    "experiment_baseline/analyze_phi_raw_raw.py",
    "experiment_baseline/analysis_core.py",
    "experiment_baseline/whitebox_schema.py",
    "experiment_baseline/whitebox_core.py",
    "experiment_b/storage.py",
)


class RawRawAnalysisError(RuntimeError):
    """The fixed raw/raw contract, analysis, or derived bundle is invalid."""


@dataclass(frozen=True)
class ArtifactContract:
    role: str
    relative_path: str
    sha256: str
    row_count: int | None = None


@dataclass(frozen=True)
class RawRawContract:
    project_root: Path
    migration_id: str
    prepare_plan_sha256: str
    artifacts: tuple[ArtifactContract, ...]
    output_root: str = OUTPUT_ROOT
    expected_blackbox_artifact_set_sha256: str = BLACKBOX_ARTIFACT_SET_SHA256
    expected_items: int = EXPECTED_ITEMS
    expected_pairs: int = EXPECTED_PAIRS
    expected_clusters: int = EXPECTED_CLUSTERS
    expected_evaluators: tuple[str, ...] = EXPECTED_EVALUATORS
    expected_generation_model_counts: Mapping[str, int] | None = None
    expected_domain_counts: Mapping[str, int] | None = None
    expected_pooled: Mapping[str, Mapping[str, float]] | None = None
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES
    bootstrap_seed: int = BOOTSTRAP_SEED


@dataclass(frozen=True)
class ValidatedCanonicalInputs:
    contract: RawRawContract
    source_artifact: analysis_core.LoadedRows
    score_artifacts: tuple[analysis_core.LoadedRows, ...]
    lineage_binding: Mapping[str, Any]
    prepared: analysis_core.PreparedAnalysis
    input_snapshot: Mapping[str, Mapping[str, Any]]
    code_snapshot: Mapping[str, Any]
    debug_snapshot: Mapping[str, Any]


def _comparison() -> dict[str, Any]:
    return {
        "id": "raw_phi_vs_aggregate_actual_ratio",
        "whitebox_field": "levels.<level>.phi",
        "whitebox_measure": "raw_phi",
        "whitebox_transform": "none",
        "blackbox_field": "level_metrics.<level>.actual_ratio",
        "blackbox_measure": "aggregate_actual_ratio",
        "blackbox_variant": "aggregate",
        "blackbox_transform": "none",
        "per_compressor_included": False,
    }


def canonical_contract(project_root: str | Path | None = None) -> RawRawContract:
    root = (
        Path(project_root)
        if project_root is not None
        else Path(__file__).resolve().parents[1]
    ).resolve(strict=True)
    artifacts = (
        ArtifactContract(
            "active_pointer",
            "experiment_baseline/ACTIVE_PHI_V2.json",
            "3075bb502ab7d1bdea9ef128b0f009ab22ac54764b3dc8bbb93b16a8dd6f5753",
        ),
        ArtifactContract(
            "sources",
            "experiment_baseline/v2/run_20260823_canonical/sources.jsonl",
            "d545faaf72cd5c35053c056e93cc3ea19827ccb4cca3d422d4cb351339d0dafd",
            EXPECTED_ITEMS,
        ),
        ArtifactContract(
            "scores_llama",
            "experiment_baseline/v2/run_20260823_canonical/final/phi_llama.v2.jsonl",
            "7efc006e6b68b6375f65917a8337ce6ddf9b09e45ec577966aec70dd483ec5e6",
            EXPECTED_ITEMS,
        ),
        ArtifactContract(
            "scores_mixtral",
            "experiment_baseline/v2/run_20260823_canonical/final/phi_mixtral.v2.jsonl",
            "8c52b2d5e8eb21263c34088b80c1e14afd5831201d020dda8dcb9c2850fbe865",
            EXPECTED_ITEMS,
        ),
        ArtifactContract(
            "lineage",
            "experiment_baseline/v2/run_20260823_canonical/final/lineage.json",
            "8faf45595b81be8aef32b149e55140aa514c1afec6bf477ed971249f3b6b78ed",
        ),
        ArtifactContract(
            "runtime_attestation",
            "experiment_baseline/v2/runtime_collected_20260823/runtime_attestation.json",
            "532950d2f2a700671c2c80d07fbbb909473bb0ed85601a9306bd37d07800d998",
        ),
        ArtifactContract(
            "canonical_analysis_summary",
            "experiment_baseline/v2/run_20260823_canonical/final/analysis_summary.json",
            "c027e91c6925dca4338b9cc7e591323b4dab6cb4c8f9a3c40b2478e0bcf40160",
        ),
        ArtifactContract(
            "release_manifest",
            "experiment_baseline/v2/run_20260823_canonical/release_manifest.json",
            "1b8ef0066cd1966e6d76c02eeb9f261793ddc952e1bef63976442030c0b595db",
        ),
        ArtifactContract(
            "prepare_manifest",
            "experiment_baseline/v2/prepare_manifest_canonical.json",
            "1141a509c571b289ac3c16bb2e9d737a5b9b371e418439751b196667f2177cbe",
        ),
    )
    return RawRawContract(
        project_root=root,
        migration_id=MIGRATION_ID,
        prepare_plan_sha256=PREPARE_PLAN_SHA256,
        artifacts=artifacts,
        expected_generation_model_counts=EXPECTED_GENERATION_MODEL_COUNTS,
        expected_domain_counts=EXPECTED_DOMAIN_COUNTS,
        expected_pooled=EXPECTED_POOLED,
    )


def _artifact_by_role(contract: RawRawContract) -> dict[str, ArtifactContract]:
    result: dict[str, ArtifactContract] = {}
    for artifact in contract.artifacts:
        if artifact.role in result:
            raise RawRawAnalysisError(f"duplicate artifact role {artifact.role!r}")
        result[artifact.role] = artifact
    required = {
        "active_pointer",
        "sources",
        "scores_llama",
        "scores_mixtral",
        "lineage",
        "runtime_attestation",
        "canonical_analysis_summary",
        "release_manifest",
        "prepare_manifest",
    }
    if set(result) != required:
        raise RawRawAnalysisError(
            f"fixed artifact roles differ: {sorted(set(result) ^ required)!r}"
        )
    return result


def _bound_path(contract: RawRawContract, artifact: ArtifactContract) -> Path:
    path = contract.project_root / artifact.relative_path
    if path.is_symlink() or not path.is_file():
        raise RawRawAnalysisError(f"bound input missing or symlinked: {path}")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(contract.project_root)
    except ValueError as exc:
        raise RawRawAnalysisError(f"bound input escapes project root: {path}") from exc
    return resolved


def _snapshot_fixed_artifacts(
    contract: RawRawContract,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for artifact in contract.artifacts:
        path = _bound_path(contract, artifact)
        digest = storage.file_sha256(path)
        if digest != artifact.sha256:
            raise RawRawAnalysisError(
                f"{artifact.role} hash drift: {digest} != {artifact.sha256}"
            )
        record: dict[str, Any] = {
            "path": artifact.relative_path,
            "sha256": digest,
            "size": path.stat().st_size,
        }
        if artifact.row_count is not None:
            record["row_count"] = artifact.row_count
        result[artifact.role] = record
    return result


def _code_snapshot(contract: RawRawContract) -> dict[str, Any]:
    files = []
    for relative_path in CODE_PATHS:
        path = contract.project_root / relative_path
        if path.is_symlink() or not path.is_file():
            raise RawRawAnalysisError(f"code dependency missing or symlinked: {path}")
        files.append(
            {
                "path": relative_path,
                "sha256": storage.file_sha256(path),
                "size": path.stat().st_size,
            }
        )
    return {
        "files": files,
        "inventory_sha256": storage.canonical_row_sha256(files),
    }


def _strict_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = whitebox_schema.strict_json_load(path)
    except whitebox_schema.WhiteboxSchemaError as exc:
        raise RawRawAnalysisError(f"{label} is not strict JSON: {path}") from exc
    if not isinstance(value, Mapping):
        raise RawRawAnalysisError(f"{label} must be one JSON object: {path}")
    return value


def _validate_active_pointer(
    contract: RawRawContract, artifacts: Mapping[str, ArtifactContract]
) -> None:
    pointer_path = _bound_path(contract, artifacts["active_pointer"])
    pointer = _strict_object(pointer_path, "active pointer")
    expected_keys = {
        "schema",
        "schema_version",
        "activated_at_utc",
        "migration_id",
        "publication_eligible",
        "lineage_path",
        "lineage_sha256",
        "prepare_manifest_path",
        "prepare_plan_sha256",
        "previous_pointer",
    }
    if set(pointer) != expected_keys:
        raise RawRawAnalysisError("active pointer keys differ from canonical contract")
    if (
        pointer.get("schema") != "experiment_baseline.phi_v2.active_pointer"
        or pointer.get("schema_version") != 2
        or pointer.get("publication_eligible") is not True
        or pointer.get("migration_id") != contract.migration_id
        or pointer.get("prepare_plan_sha256") != contract.prepare_plan_sha256
    ):
        raise RawRawAnalysisError("active pointer identity differs from canonical contract")
    lineage_path = _bound_path(contract, artifacts["lineage"])
    prepare_path = _bound_path(contract, artifacts["prepare_manifest"])
    if Path(str(pointer.get("lineage_path"))).resolve() != lineage_path:
        raise RawRawAnalysisError("active pointer does not select canonical lineage")
    if Path(str(pointer.get("prepare_manifest_path"))).resolve() != prepare_path:
        raise RawRawAnalysisError("active pointer does not select canonical preparation")
    if pointer.get("lineage_sha256") != artifacts["lineage"].sha256:
        raise RawRawAnalysisError("active pointer lineage hash differs")


def _validate_release_manifest(
    contract: RawRawContract, artifacts: Mapping[str, ArtifactContract]
) -> None:
    release = _strict_object(
        _bound_path(contract, artifacts["release_manifest"]), "release manifest"
    )
    if (
        release.get("schema") != "baseline_v2_release_manifest"
        or release.get("schema_version") != 1
        or release.get("file_count") != 30
        or release.get("file_inventory_sha256") != RELEASE_INVENTORY_SHA256
    ):
        raise RawRawAnalysisError("release manifest identity differs")
    files = release.get("files")
    if not isinstance(files, list) or len(files) != 30:
        raise RawRawAnalysisError("release manifest file inventory is incomplete")
    inventory = {
        Path(str(entry["path"])).resolve(): entry
        for entry in files
        if isinstance(entry, Mapping) and "path" in entry
    }
    for role in (
        "active_pointer",
        "lineage",
        "canonical_analysis_summary",
        "scores_llama",
        "scores_mixtral",
        "prepare_manifest",
    ):
        artifact = artifacts[role]
        path = _bound_path(contract, artifact)
        entry = inventory.get(path)
        if entry is None or entry.get("sha256") != artifact.sha256:
            raise RawRawAnalysisError(
                f"release manifest does not bind {role} to the expected hash"
            )


def _validate_runtime_attestation_binding(
    contract: RawRawContract, artifacts: Mapping[str, ArtifactContract]
) -> None:
    lineage = _strict_object(
        _bound_path(contract, artifacts["lineage"]), "finalized lineage"
    )
    records = lineage.get("artifacts")
    if not isinstance(records, list):
        raise RawRawAnalysisError("lineage artifact inventory is missing")
    matches = [
        entry
        for entry in records
        if isinstance(entry, Mapping)
        and entry.get("role") == "runtime_attestation"
    ]
    if len(matches) != 1:
        raise RawRawAnalysisError("lineage runtime-attestation binding is not unique")
    record = matches[0]
    expected = artifacts["runtime_attestation"]
    expected_path = _bound_path(contract, expected)
    if (
        Path(str(record.get("path"))).resolve() != expected_path
        or record.get("sha256") != expected.sha256
        or record.get("size") != expected_path.stat().st_size
    ):
        raise RawRawAnalysisError("lineage runtime-attestation binding differs")


def _debug_artifact_set_sha256(
    contract: RawRawContract,
    source_rows: Sequence[Mapping[str, Any]],
    expected_hashes: Mapping[whitebox_schema.SemanticKey, str],
) -> str:
    entries = []
    seen_paths: set[Path] = set()
    for source in sorted(source_rows, key=whitebox_schema.semantic_key):
        key = whitebox_schema.semantic_key(source)
        declared = source.get("source_file")
        if not isinstance(declared, str) or not declared:
            raise RawRawAnalysisError(f"source {key!r} has no debug path")
        path = Path(declared)
        if not path.is_absolute():
            path = contract.project_root / path
        if path.is_symlink() or not path.is_file():
            raise RawRawAnalysisError(f"debug input missing or symlinked: {path}")
        path = path.resolve(strict=True)
        try:
            path.relative_to(contract.project_root)
        except ValueError as exc:
            raise RawRawAnalysisError(f"debug input escapes project root: {path}") from exc
        if path in seen_paths:
            raise RawRawAnalysisError(f"debug input is reused by multiple keys: {path}")
        seen_paths.add(path)
        expected = expected_hashes.get(key)
        if expected is None:
            raise RawRawAnalysisError(f"lineage lacks debug hash for {key!r}")
        actual = storage.file_sha256(path)
        if actual != expected:
            raise RawRawAnalysisError(f"debug hash drift for {key!r}: {actual} != {expected}")
        entries.append(
            {
                "semantic_key": list(key),
                "source_file": declared,
                "sha256": actual,
            }
        )
    return storage.sha256_bytes(whitebox_schema.canonical_json_bytes(entries))


def _assert_expected_coverage(
    contract: RawRawContract, prepared: analysis_core.PreparedAnalysis
) -> None:
    if set(prepared.by_evaluator) != set(contract.expected_evaluators):
        raise RawRawAnalysisError(
            f"evaluator coverage differs: {sorted(prepared.by_evaluator)!r}"
        )
    if (
        prepared.source_count != contract.expected_items
        or prepared.blackbox_count != contract.expected_items
        or prepared.blackbox_artifact_set_sha256
        != contract.expected_blackbox_artifact_set_sha256
    ):
        raise RawRawAnalysisError("global source/black-box coverage differs")
    for evaluator, items in prepared.by_evaluator.items():
        if len(items) != contract.expected_items:
            raise RawRawAnalysisError(f"{evaluator}: item count differs")
        if len(items) * len(analysis_core.LEVELS) != contract.expected_pairs:
            raise RawRawAnalysisError(f"{evaluator}: level-pair count differs")
        if len({item.source_cluster_key for item in items}) != contract.expected_clusters:
            raise RawRawAnalysisError(f"{evaluator}: source-cluster count differs")
        if contract.expected_generation_model_counts is not None:
            actual = Counter(item.generation_model for item in items)
            if dict(actual) != dict(contract.expected_generation_model_counts):
                raise RawRawAnalysisError(
                    f"{evaluator}: generation-model partition differs: {dict(actual)!r}"
                )
        if contract.expected_domain_counts is not None:
            actual = Counter(item.domain for item in items)
            if dict(actual) != dict(contract.expected_domain_counts):
                raise RawRawAnalysisError(
                    f"{evaluator}: domain partition differs: {dict(actual)!r}"
                )


def validate_canonical_inputs(contract: RawRawContract) -> ValidatedCanonicalInputs:
    artifacts = _artifact_by_role(contract)
    input_snapshot = _snapshot_fixed_artifacts(contract)
    code_snapshot = _code_snapshot(contract)
    _validate_active_pointer(contract, artifacts)
    _validate_release_manifest(contract, artifacts)
    _validate_runtime_attestation_binding(contract, artifacts)

    source_artifact = analysis_core.load_rows(
        _bound_path(contract, artifacts["sources"]), kind="source"
    )
    score_artifacts = tuple(
        analysis_core.load_rows(_bound_path(contract, artifacts[role]), kind="score")
        for role in ("scores_llama", "scores_mixtral")
    )
    if len(source_artifact.rows) != contract.expected_items:
        raise RawRawAnalysisError("source row count differs")
    if any(len(artifact.rows) != contract.expected_items for artifact in score_artifacts):
        raise RawRawAnalysisError("score row count differs")

    lineage_binding = analysis_core.validate_finalized_lineage(
        _bound_path(contract, artifacts["lineage"]),
        source_artifact,
        score_artifacts,
    )
    if (
        lineage_binding.get("migration_id") != contract.migration_id
        or lineage_binding.get("prepare_plan_sha256")
        != contract.prepare_plan_sha256
        or lineage_binding.get("runtime_attestation", {}).get("file_sha256")
        != artifacts["runtime_attestation"].sha256
    ):
        raise RawRawAnalysisError("finalized lineage identity differs")
    expected_debug_hashes = {
        tuple(key.split("\t")): digest
        for key, digest in lineage_binding["debug_file_sha256_by_key"].items()
    }
    if len(expected_debug_hashes) != contract.expected_items:
        raise RawRawAnalysisError("lineage debug-hash coverage differs")

    score_rows = tuple(
        row for artifact in score_artifacts for row in artifact.rows
    )
    prepared = analysis_core.prepare_manifest_bound_analysis(
        source_artifact.rows,
        score_rows,
        source_base_dir=contract.project_root,
        expected_blackbox_file_sha256_by_key=expected_debug_hashes,
    )
    _assert_expected_coverage(contract, prepared)
    debug_snapshot = {
        "count": contract.expected_items,
        "artifact_set_sha256": prepared.blackbox_artifact_set_sha256,
    }
    return ValidatedCanonicalInputs(
        contract=contract,
        source_artifact=source_artifact,
        score_artifacts=score_artifacts,
        lineage_binding=lineage_binding,
        prepared=prepared,
        input_snapshot=input_snapshot,
        code_snapshot=code_snapshot,
        debug_snapshot=debug_snapshot,
    )


def _coverage_document(
    validated: ValidatedCanonicalInputs,
) -> dict[str, Any]:
    contract = validated.contract
    first = validated.prepared.by_evaluator[contract.expected_evaluators[0]]
    return {
        "exact": True,
        "source_rows": validated.prepared.source_count,
        "blackbox_rows": validated.prepared.blackbox_count,
        "score_rows": sum(len(value.rows) for value in validated.score_artifacts),
        "evaluator_count": len(validated.prepared.by_evaluator),
        "evaluators": list(contract.expected_evaluators),
        "items_per_evaluator": contract.expected_items,
        "item_level_pairs_per_evaluator": contract.expected_pairs,
        "evaluator_specific_item_level_pairs": (
            contract.expected_pairs * len(contract.expected_evaluators)
        ),
        "source_clusters": contract.expected_clusters,
        "levels": list(analysis_core.LEVELS),
        "generation_model_items": dict(
            sorted(Counter(item.generation_model for item in first).items())
        ),
        "domain_items": dict(sorted(Counter(item.domain for item in first).items())),
    }


def build_raw_raw_analysis(
    validated: ValidatedCanonicalInputs,
) -> dict[str, Any]:
    contract = validated.contract
    analyses: dict[str, Any] = {}
    for evaluator in contract.expected_evaluators:
        result = analysis_core.analyze_paired_items(
            validated.prepared.by_evaluator[evaluator],
            n_bootstrap=contract.bootstrap_replicates,
            seed=contract.bootstrap_seed,
            mode="manifest_bound_v2",
            comparison_mode="raw",
        )
        result["evaluator_model"] = dict(EVALUATOR_DESCRIPTORS[evaluator])
        analyses[evaluator] = result

    lineage = {
        "migration_id": contract.migration_id,
        "lineage_file_sha256": validated.lineage_binding["lineage_file_sha256"],
        "lineage_payload_sha256": validated.lineage_binding[
            "lineage_payload_sha256"
        ],
        "prepare_plan_sha256": validated.lineage_binding["prepare_plan_sha256"],
        "source_manifest_sha256": validated.prepared.source_manifest_sha256,
        "score_manifest_sha256": validated.prepared.score_manifest_sha256,
        "blackbox_artifact_set_sha256": (
            validated.prepared.blackbox_artifact_set_sha256
        ),
        "source_artifact_sha256": validated.source_artifact.artifact_sha256,
        "score_artifact_sha256_by_evaluator": {
            evaluator: artifact.artifact_sha256
            for evaluator, artifact in zip(
                contract.expected_evaluators, validated.score_artifacts
            )
        },
        "origin_counts": dict(validated.lineage_binding["origin_counts"]),
    }
    document = analysis_core.to_strict_json_value(
        {
            "schema": ANALYSIS_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "mode": "manifest_bound_v2_raw_raw_derived",
            "comparison": _comparison(),
            "lineage": lineage,
            "coverage": _coverage_document(validated),
            "analyses": analyses,
        }
    )
    _validate_analysis_document(document, contract)
    return document


def _validate_analysis_document(
    document: Mapping[str, Any], contract: RawRawContract
) -> None:
    if set(document) != {
        "schema",
        "schema_version",
        "mode",
        "comparison",
        "lineage",
        "coverage",
        "analyses",
    }:
        raise RawRawAnalysisError("raw analysis top-level keys differ")
    if (
        document.get("schema") != ANALYSIS_SCHEMA
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("mode") != "manifest_bound_v2_raw_raw_derived"
        or document.get("comparison") != _comparison()
    ):
        raise RawRawAnalysisError("raw analysis identity differs")
    coverage = document.get("coverage")
    if not isinstance(coverage, Mapping) or (
        coverage.get("source_rows") != contract.expected_items
        or coverage.get("blackbox_rows") != contract.expected_items
        or coverage.get("items_per_evaluator") != contract.expected_items
        or coverage.get("item_level_pairs_per_evaluator") != contract.expected_pairs
        or coverage.get("source_clusters") != contract.expected_clusters
    ):
        raise RawRawAnalysisError("raw analysis coverage differs")
    analyses = document.get("analyses")
    if not isinstance(analyses, Mapping) or set(analyses) != set(
        contract.expected_evaluators
    ):
        raise RawRawAnalysisError("raw analysis evaluator set differs")
    expected_bootstrap_metrics = {
        "pooled_raw_spearman_rho",
        "item_centered_raw_spearman_rho",
        "mean_per_item_raw_vector_kendall_tau_b",
    }
    for evaluator in contract.expected_evaluators:
        result = analyses[evaluator]
        if not isinstance(result, Mapping) or result.get("evaluator") != evaluator:
            raise RawRawAnalysisError(f"raw analysis evaluator identity differs: {evaluator}")
        if result.get("evaluator_model") != EVALUATOR_DESCRIPTORS[evaluator]:
            raise RawRawAnalysisError(f"raw evaluator descriptor differs: {evaluator}")
        evaluator_coverage = result.get("coverage")
        if not isinstance(evaluator_coverage, Mapping) or (
            evaluator_coverage.get("joined_items") != contract.expected_items
            or evaluator_coverage.get("item_level_pairs") != contract.expected_pairs
            or evaluator_coverage.get("source_clusters") != contract.expected_clusters
        ):
            raise RawRawAnalysisError(f"raw evaluator coverage differs: {evaluator}")
        bootstrap = result.get("bootstrap")
        if not isinstance(bootstrap, Mapping) or (
            bootstrap.get("enabled") is not True
            or bootstrap.get("n_resamples") != contract.bootstrap_replicates
            or bootstrap.get("seed") != contract.bootstrap_seed
            or bootstrap.get("cluster_count") != contract.expected_clusters
            or set(bootstrap.get("metrics", {})) != expected_bootstrap_metrics
        ):
            raise RawRawAnalysisError(f"raw bootstrap contract differs: {evaluator}")
        for name, metric in bootstrap["metrics"].items():
            if metric.get("finite_resamples") != contract.bootstrap_replicates:
                raise RawRawAnalysisError(
                    f"raw bootstrap has undefined replicates: {evaluator}/{name}"
                )
        if contract.expected_pooled is not None:
            pooled = result["agreement"]["pooled_raw_agreement"]
            for field, expected in contract.expected_pooled[evaluator].items():
                if pooled.get(field) != expected:
                    raise RawRawAnalysisError(
                        f"canonical pooled {field} differs for {evaluator}: "
                        f"{pooled.get(field)!r} != {expected!r}"
                    )
    payload = storage.canonical_json_bytes(document).lower()
    if b"excess" in payload:
        raise RawRawAnalysisError("raw analysis contains an excess label")


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _validate_relative_output_root(contract: RawRawContract) -> tuple[str, ...]:
    declared = contract.output_root.replace("\\", "/")
    relative = Path(contract.output_root)
    parts = relative.parts
    if (
        relative.is_absolute()
        or not parts
        or any(part in ("", ".", "..") for part in parts)
        or Path(*parts).as_posix() != declared
    ):
        raise RawRawAnalysisError("output_root must be one normalized relative path")
    return parts


def _validate_output_path(
    output_dir: str | Path, contract: RawRawContract
) -> Path:
    project_root = contract.project_root.resolve(strict=True)
    root_parts = _validate_relative_output_root(contract)
    lexical_root = project_root.joinpath(*root_parts)
    requested = Path(output_dir)
    if not requested.is_absolute():
        requested = project_root / requested
    lexical_candidate = Path(os.path.abspath(os.fspath(requested)))
    if lexical_candidate.parent != lexical_root:
        raise RawRawAnalysisError(
            f"output must be a direct child of {lexical_root}, got {lexical_candidate}"
        )
    pattern = re.compile(
        rf"^{re.escape(contract.migration_id)}_raw_raw_\d{{8}}T\d{{6}}Z_v1$"
    )
    if pattern.fullmatch(lexical_candidate.name) is None:
        raise RawRawAnalysisError("output directory name does not match fixed convention")

    for target in (lexical_root, lexical_candidate):
        current = project_root
        try:
            relative_parts = target.relative_to(project_root).parts
        except ValueError as exc:
            raise RawRawAnalysisError("output path escapes project root") from exc
        for part in relative_parts:
            current = current / part
            if _is_reparse_point(current):
                raise RawRawAnalysisError(
                    f"output path contains a symlink/junction/reparse point: {current}"
                )

    resolved_root = lexical_root.resolve()
    resolved_candidate = lexical_candidate.resolve()
    try:
        resolved_root.relative_to(project_root)
        resolved_candidate.relative_to(project_root)
    except ValueError as exc:
        raise RawRawAnalysisError("resolved output path escapes project root") from exc
    if resolved_candidate.parent != resolved_root:
        raise RawRawAnalysisError("resolved output is not a direct derived-root child")
    if resolved_candidate.exists() and not resolved_candidate.is_dir():
        raise RawRawAnalysisError("output path exists and is not a directory")
    if resolved_candidate.exists():
        unknown = {path.name for path in resolved_candidate.iterdir()} - {
            "analysis.json",
            "manifest.json",
        }
        if unknown:
            raise RawRawAnalysisError(
                f"output directory contains unknown artifacts: {sorted(unknown)!r}"
            )
    return resolved_candidate


def _publish_new_or_identical(path: Path, payload: bytes) -> bool:
    """Publish one durable file without ever replacing differing bytes."""

    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise RawRawAnalysisError(f"refusing to overwrite differing artifact: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("xb") as handle:
            created = True
            written = handle.write(payload)
            if written != len(payload):
                raise OSError(f"short write: {written} != {len(payload)}")
            handle.flush()
            os.fsync(handle.fileno())
        storage.fsync_directory(path.parent)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise RawRawAnalysisError(f"concurrent differing artifact: {path}")
        return False
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise
    return True


def _post_run_snapshot(
    validated: ValidatedCanonicalInputs,
) -> dict[str, Any]:
    contract = validated.contract
    expected_debug_hashes = {
        tuple(key.split("\t")): digest
        for key, digest in validated.lineage_binding[
            "debug_file_sha256_by_key"
        ].items()
    }
    debug_hash = _debug_artifact_set_sha256(
        contract,
        validated.source_artifact.rows,
        expected_debug_hashes,
    )
    return {
        "inputs": _snapshot_fixed_artifacts(contract),
        "code": _code_snapshot(contract),
        "debug_files": {
            "count": len(expected_debug_hashes),
            "artifact_set_sha256": debug_hash,
        },
    }


def _require_unchanged(
    validated: ValidatedCanonicalInputs, post: Mapping[str, Any]
) -> None:
    if post.get("inputs") != validated.input_snapshot:
        raise RawRawAnalysisError("bound input artifacts changed during analysis")
    if post.get("code") != validated.code_snapshot:
        raise RawRawAnalysisError("derived analysis code changed during analysis")
    if post.get("debug_files") != validated.debug_snapshot:
        raise RawRawAnalysisError("bound debug-file inventory changed during analysis")


def _build_manifest(
    validated: ValidatedCanonicalInputs,
    output_dir: Path,
    analysis_payload: bytes,
    post: Mapping[str, Any],
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    contract = validated.contract
    protected = {
        role: {
            "before": record["sha256"],
            "after": post["inputs"][role]["sha256"],
            "unchanged": record["sha256"]
            == post["inputs"][role]["sha256"],
        }
        for role, record in validated.input_snapshot.items()
    }
    return {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "state": "complete",
        "created_at_utc": (
            created_at_utc
            if created_at_utc is not None
            else datetime.now(timezone.utc).isoformat()
        ),
        "migration_id": contract.migration_id,
        "comparison": _comparison(),
        "analysis_request": {
            "bootstrap_replicates": contract.bootstrap_replicates,
            "bootstrap_seed": contract.bootstrap_seed,
            "confidence_level": 0.95,
            "interval": "linear empirical percentile (0.025, 0.975)",
            "cluster_definition": [
                "domain",
                "source_id_or_item_id",
                "source_text_sha256_or_legacy_id_fallback",
            ],
            "resampling_unit": (
                "all generation-model rows and all five levels for one source"
            ),
        },
        "inputs": dict(validated.input_snapshot),
        "lineage": {
            key: value
            for key, value in validated.lineage_binding.items()
            if key != "debug_file_sha256_by_key"
        },
        "coverage": _coverage_document(validated),
        "debug_files": {
            "before": dict(validated.debug_snapshot),
            "after": dict(post["debug_files"]),
            "unchanged": post["debug_files"] == validated.debug_snapshot,
        },
        "protected_artifacts": protected,
        "code": {
            "before": dict(validated.code_snapshot),
            "after": dict(post["code"]),
            "unchanged": post["code"] == validated.code_snapshot,
        },
        "artifacts": {
            "analysis.json": {
                "path": "analysis.json",
                "schema": ANALYSIS_SCHEMA,
                "sha256": storage.sha256_bytes(analysis_payload),
                "size": len(analysis_payload),
            }
        },
        "write_scope": {
            "directory": output_dir.relative_to(contract.project_root).as_posix(),
            "files": ["analysis.json", "manifest.json"],
        },
        "claims": {
            "external_api_calls": 0,
            "gpu_inference": False,
            "model_loading": False,
            "recompression": False,
            "input_artifacts_modified": False,
            "experiment_a_modified": False,
            "experiment_b_modified": False,
            "historical_artifacts_modified": False,
        },
    }


def validate_completed_bundle(
    output_dir: Path,
    validated: ValidatedCanonicalInputs,
    *,
    expected_analysis_payload: bytes | None = None,
) -> Mapping[str, Any]:
    output_dir = _validate_output_path(output_dir, validated.contract)
    if not output_dir.is_dir():
        raise RawRawAnalysisError("completed output directory is missing")
    paths = {path.name: path for path in output_dir.iterdir()}
    if set(paths) != {"analysis.json", "manifest.json"}:
        raise RawRawAnalysisError("completed output inventory is not exact")
    if any(
        _is_reparse_point(path) or not path.is_file() for path in paths.values()
    ):
        raise RawRawAnalysisError("completed output contains a reparse point/non-file")

    manifest = _strict_object(paths["manifest.json"], "derived manifest")
    expected_manifest_keys = {
        "schema",
        "schema_version",
        "state",
        "created_at_utc",
        "migration_id",
        "comparison",
        "analysis_request",
        "inputs",
        "lineage",
        "coverage",
        "debug_files",
        "protected_artifacts",
        "code",
        "artifacts",
        "write_scope",
        "claims",
    }
    if set(manifest) != expected_manifest_keys:
        raise RawRawAnalysisError("completed manifest top-level keys differ")
    created_at_utc = manifest.get("created_at_utc")
    if not isinstance(created_at_utc, str):
        raise RawRawAnalysisError("completed manifest timestamp is missing")
    try:
        created = datetime.fromisoformat(created_at_utc)
    except ValueError as exc:
        raise RawRawAnalysisError("completed manifest timestamp is invalid") from exc
    if created.utcoffset() != timezone.utc.utcoffset(None):
        raise RawRawAnalysisError("completed manifest timestamp is not UTC")

    analysis_payload = paths["analysis.json"].read_bytes()
    if not analysis_payload.endswith(b"\n"):
        raise RawRawAnalysisError("completed analysis lacks its canonical final LF")
    try:
        analysis_document = whitebox_schema.strict_json_loads(
            analysis_payload, path=str(paths["analysis.json"])
        )
    except whitebox_schema.WhiteboxSchemaError as exc:
        raise RawRawAnalysisError("completed analysis is not strict JSON") from exc
    if not isinstance(analysis_document, Mapping):
        raise RawRawAnalysisError("completed analysis must be one object")
    _validate_analysis_document(analysis_document, validated.contract)
    if expected_analysis_payload is None:
        expected_analysis_payload = storage.canonical_jsonl_row_bytes(
            build_raw_raw_analysis(validated)
        )
    if analysis_payload != expected_analysis_payload:
        raise RawRawAnalysisError(
            "completed analysis scientific result differs from recomputation"
        )

    current = {
        "inputs": validated.input_snapshot,
        "code": validated.code_snapshot,
        "debug_files": validated.debug_snapshot,
    }
    expected_manifest = _build_manifest(
        validated,
        output_dir,
        analysis_payload,
        current,
        created_at_utc=created_at_utc,
    )
    if dict(manifest) != expected_manifest:
        raise RawRawAnalysisError("completed manifest contract differs")
    return manifest


def run(
    output_dir: str | Path,
    *,
    contract: RawRawContract | None = None,
) -> Path:
    active_contract = contract or canonical_contract()
    destination = _validate_output_path(output_dir, active_contract)
    validated = validate_canonical_inputs(active_contract)
    manifest_path = destination / "manifest.json"
    if manifest_path.exists():
        validate_completed_bundle(destination, validated)
        return manifest_path

    analysis = build_raw_raw_analysis(validated)
    analysis_payload = storage.canonical_jsonl_row_bytes(analysis)
    if _validate_output_path(destination, active_contract) != destination:
        raise RawRawAnalysisError("output path changed before analysis publication")
    _publish_new_or_identical(destination / "analysis.json", analysis_payload)

    post = _post_run_snapshot(validated)
    _require_unchanged(validated, post)
    manifest = _build_manifest(
        validated,
        destination,
        analysis_payload,
        post,
    )
    manifest_payload = storage.canonical_jsonl_row_bytes(manifest)
    if _validate_output_path(destination, active_contract) != destination:
        raise RawRawAnalysisError("output path changed before manifest publication")
    created_manifest = _publish_new_or_identical(manifest_path, manifest_payload)
    try:
        validate_completed_bundle(
            destination,
            validated,
            expected_analysis_payload=analysis_payload,
        )
    except Exception:
        if created_manifest:
            manifest_path.unlink(missing_ok=True)
            storage.fsync_directory(destination)
        raise
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new versioned child of experiment_baseline/phi_v2_derived_results",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = run(args.output_dir)
    print(f"raw/raw derived analysis complete: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
