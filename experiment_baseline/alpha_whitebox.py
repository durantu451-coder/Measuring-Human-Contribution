# -*- coding: utf-8 -*-
"""Strict inter-evaluator reliability for canonical white-box baseline scores.

Publication analysis consumes the canonical v2 source manifest and one or more
canonical score artifacts.  Evaluator ratings are joined by normalized semantic
key and ``scoring_input_sha256``; physical row order is irrelevant and incomplete
coverage is fatal.  This estimand is inter-evaluator reliability.  It is not the
inter-compressor reliability estimand from Experiment A.

The historical phi JSON format is accepted only behind the explicit
``--legacy-nonpublication`` mode.
"""

from __future__ import annotations

from experiment_baseline.whitebox_core import expand_placeholder
from pathlib import Path  # noqa: F401

import argparse
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from experiment_baseline import analysis_core
from experiment_baseline import whitebox_schema


LEVELS = tuple(whitebox_schema.LEVELS)


def krippendorff_interval_exact(
    ratings: Sequence[Sequence[float]] | np.ndarray,
) -> float | None:
    """Return exact interval Krippendorff alpha in O(m) time and memory.

    ``m`` is the number of supplied ratings.  Missing and non-finite ratings are
    rejected rather than silently dropping units.  ``None`` denotes an
    underdetermined statistic and is safe for strict JSON serialization.
    """

    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2:
        raise analysis_core.AnalysisError("ratings must be a two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise analysis_core.AnalysisError(
            "ratings contain missing or non-finite values; silent unit drops are forbidden"
        )
    unit_count, rater_count = matrix.shape
    if unit_count < 2 or rater_count < 2:
        return None

    row_sums = matrix.sum(axis=1)
    row_square_sums = np.square(matrix).sum(axis=1)
    observation_count = unit_count * rater_count
    grand_sum = row_sums.sum()
    grand_square_sum = row_square_sums.sum()

    # Algebraically identical to the interval coincidence-matrix definition,
    # without constructing its O(V^2) distinct-value matrix.
    numerator = 2.0 * (
        grand_square_sum
        - np.sum((np.square(row_sums) - row_square_sums) / (rater_count - 1))
    )
    denominator = (2.0 / (observation_count - 1)) * (
        observation_count * grand_square_sum - grand_sum * grand_sum
    )
    if denominator == 0.0:
        return 1.0 if numerator == 0.0 else None
    value = 1.0 - numerator / denominator
    return float(value) if math.isfinite(float(value)) else None


def _canonical_set_sha256(
    rows: Sequence[Mapping[str, Any]], *, scores: bool = False
) -> str:
    if scores:
        ordered = sorted(
            rows,
            key=lambda row: (
                str(row.get("evaluator", "")),
                *whitebox_schema.semantic_key(row),
            ),
        )
    else:
        ordered = sorted(rows, key=whitebox_schema.semantic_key)
    return whitebox_schema.sha256_bytes(
        whitebox_schema.canonical_json_bytes(ordered)
    )


def prepare_manifest_bound_evaluators(
    source_rows: Sequence[Mapping[str, Any]],
    score_rows: Sequence[Mapping[str, Any]],
    *,
    expected_evaluators: Sequence[str] | None = None,
) -> tuple[
    dict[str, dict[whitebox_schema.SemanticKey, tuple[float, ...]]],
    tuple[whitebox_schema.SemanticKey, ...],
    dict[str, Any],
]:
    """Validate v2 rows and return complete evaluator vectors keyed by identity."""

    sources = tuple(source_rows)
    scores = tuple(score_rows)
    if not sources:
        raise analysis_core.CoverageError("source manifest is empty")
    if not scores:
        raise analysis_core.CoverageError("score artifact is empty")

    source_index = whitebox_schema.index_source_rows(sources)
    validations = whitebox_schema.validate_score_rows(scores, sources=source_index)
    grouped: dict[
        str, dict[whitebox_schema.SemanticKey, tuple[float, ...]]
    ] = {}
    evaluator_hashes: dict[str, set[str]] = {}
    protocol_hashes: dict[str, set[str]] = {}

    for row, validation in zip(scores, validations):
        evaluator = row["evaluator"]
        # validate_score_rows already binds this hash to the canonical source;
        # retain an explicit check at the pairing boundary.
        source_hash = source_index[validation.semantic_key]["scoring_input_sha256"]
        if validation.scoring_input_sha256 != source_hash:
            raise analysis_core.CoverageError(
                f"score {validation.score_key!r}: scoring_input_sha256 mismatch"
            )
        grouped.setdefault(evaluator, {})[validation.semantic_key] = tuple(
            float(row["level_excess"][level]["phi_excess"]) for level in LEVELS
        )
        evaluator_hashes.setdefault(evaluator, set()).add(
            validation.evaluator_sha256
        )
        protocol_hashes.setdefault(evaluator, set()).add(validation.protocol_sha256)

    actual_evaluators = set(grouped)
    if expected_evaluators is not None:
        expected = set(expected_evaluators)
        if len(expected) != len(tuple(expected_evaluators)):
            raise analysis_core.AnalysisError("expected_evaluators contains duplicates")
        if actual_evaluators != expected:
            missing = sorted(expected - actual_evaluators)
            unexpected = sorted(actual_evaluators - expected)
            raise analysis_core.CoverageError(
                "evaluator coverage mismatch: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
    if len(grouped) < 2:
        raise analysis_core.AnalysisError(
            "inter-evaluator reliability requires at least two evaluators"
        )

    source_keys = set(source_index)
    for evaluator, rows_by_key in sorted(grouped.items()):
        score_keys = set(rows_by_key)
        if score_keys != source_keys:
            missing = sorted(source_keys - score_keys)
            unexpected = sorted(score_keys - source_keys)
            raise analysis_core.CoverageError(
                f"source/score evaluator={evaluator!r} coverage mismatch: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
        if len(evaluator_hashes[evaluator]) != 1:
            raise analysis_core.AnalysisError(
                f"evaluator_sha256 is not uniform for evaluator {evaluator!r}"
            )
        if len(protocol_hashes[evaluator]) != 1:
            raise analysis_core.AnalysisError(
                f"protocol_sha256 is not uniform for evaluator {evaluator!r}"
            )

    ordered_keys = tuple(sorted(source_keys))
    provenance = {
        "source_manifest_sha256": _canonical_set_sha256(sources),
        "score_manifest_sha256": _canonical_set_sha256(scores, scores=True),
        "evaluator_sha256_by_evaluator": {
            evaluator: next(iter(evaluator_hashes[evaluator]))
            for evaluator in sorted(grouped)
        },
        "protocol_sha256_by_evaluator": {
            evaluator: next(iter(protocol_hashes[evaluator]))
            for evaluator in sorted(grouped)
        },
    }
    return grouped, ordered_keys, provenance


def _alpha_cell(rows: Sequence[Sequence[float]], rater_count: int) -> dict[str, Any]:
    return {
        "alpha": krippendorff_interval_exact(rows),
        "units": len(rows),
        "ratings": len(rows) * rater_count,
    }


def _reliability_for_keys(
    by_evaluator: Mapping[
        str, Mapping[whitebox_schema.SemanticKey, tuple[float, ...]]
    ],
    keys: Sequence[whitebox_schema.SemanticKey],
) -> dict[str, Any]:
    evaluators = tuple(sorted(by_evaluator))
    pooled = [
        [by_evaluator[evaluator][key][level_index] for evaluator in evaluators]
        for key in keys
        for level_index in range(len(LEVELS))
    ]
    per_level = {
        level: _alpha_cell(
            [
                [by_evaluator[evaluator][key][level_index] for evaluator in evaluators]
                for key in keys
            ],
            len(evaluators),
        )
        for level_index, level in enumerate(LEVELS)
    }
    return {
        "pooled_item_level": _alpha_cell(pooled, len(evaluators)),
        "by_level": per_level,
        "items": len(keys),
    }


def _assemble_result(
    by_evaluator: Mapping[
        str, Mapping[whitebox_schema.SemanticKey, tuple[float, ...]]
    ],
    keys: Sequence[whitebox_schema.SemanticKey],
    *,
    mode: str,
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    grouped_model: dict[str, list[whitebox_schema.SemanticKey]] = {}
    grouped_domain: dict[str, list[whitebox_schema.SemanticKey]] = {}
    for key in keys:
        grouped_model.setdefault(key[0], []).append(key)
        grouped_domain.setdefault(key[1], []).append(key)

    publication = mode == "manifest_bound_v2"
    result = {
        "analysis_schema_version": 1,
        "analysis_type": "inter_evaluator_reliability",
        "mode": mode,
        "publication_eligible": publication,
        "estimand": {
            "reliability_target": "inter_evaluator",
            "raters": sorted(by_evaluator),
            "unit": "semantic_item_x_designed_level",
            "metric": "krippendorff_interval_alpha",
            "implementation": "exact_algebraic_O(m)_time_O(m)_memory",
            "distinct_from": (
                "Experiment A inter-compressor reliability, whose raters are "
                "zlib, bz2, and lzma"
            ),
        },
        "lineage": dict(lineage),
        "coverage": {
            "exact": publication,
            "source_rows": len(keys),
            "evaluator_count": len(by_evaluator),
            "score_rows": len(keys) * len(by_evaluator),
            "expected_score_rows": len(keys) * len(by_evaluator),
            "item_level_units": len(keys) * len(LEVELS),
            "levels": list(LEVELS),
            "missing_keys": [],
            "unexpected_keys": [],
        },
        "reliability": {
            "overall": _reliability_for_keys(by_evaluator, keys),
            "by_generation_model": {
                name: _reliability_for_keys(by_evaluator, group_keys)
                for name, group_keys in sorted(grouped_model.items())
            },
            "by_domain": {
                name: _reliability_for_keys(by_evaluator, group_keys)
                for name, group_keys in sorted(grouped_domain.items())
            },
        },
    }
    if not publication:
        result["warning"] = (
            "Legacy artifacts lack canonical v2 source/input/protocol binding; "
            "this result must not be used for publication."
        )
    return analysis_core.to_strict_json_value(result)


def analyze_manifest_bound(
    source_rows: Sequence[Mapping[str, Any]],
    score_rows: Sequence[Mapping[str, Any]],
    *,
    expected_evaluators: Sequence[str] | None = None,
    source_artifact_sha256: str | None = None,
    score_artifact_sha256es: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Analyze complete canonical v2 evaluator scores without positional pairing."""

    by_evaluator, keys, lineage = prepare_manifest_bound_evaluators(
        source_rows, score_rows, expected_evaluators=expected_evaluators
    )
    lineage.update(
        {
            "source_artifact_sha256": source_artifact_sha256,
            "score_artifact_sha256es": list(score_artifact_sha256es or []),
        }
    )
    return _assemble_result(
        by_evaluator, keys, mode="manifest_bound_v2", lineage=lineage
    )


def analyze_legacy_nonpublication(
    phi_paths: Sequence[str | Path], debug_dir: str | Path
) -> dict[str, Any]:
    """Analyze legacy files with exact key coverage, explicitly non-publication."""

    by_evaluator: dict[
        str, dict[whitebox_schema.SemanticKey, tuple[float, ...]]
    ] = {}
    legacy_lineage: dict[str, Any] = {}
    expected_keys: set[whitebox_schema.SemanticKey] | None = None
    for path in phi_paths:
        evaluator, items, lineage = analysis_core.load_legacy_paired(path, debug_dir)
        if evaluator in by_evaluator:
            raise analysis_core.CoverageError(
                f"duplicate legacy evaluator {evaluator!r}"
            )
        indexed = {item.semantic_key: item.whitebox_excess for item in items}
        keys = set(indexed)
        if expected_keys is None:
            expected_keys = keys
        elif keys != expected_keys:
            raise analysis_core.CoverageError(
                f"legacy evaluator {evaluator!r} key coverage does not match"
            )
        by_evaluator[evaluator] = indexed
        legacy_lineage[evaluator] = lineage
    if expected_keys is None:
        raise analysis_core.CoverageError("no legacy phi artifacts supplied")
    if len(by_evaluator) < 2:
        raise analysis_core.AnalysisError(
            "inter-evaluator reliability requires at least two legacy evaluators"
        )
    return _assemble_result(
        by_evaluator,
        tuple(sorted(expected_keys)),
        mode="legacy_nonpublication",
        lineage={"legacy_artifacts_by_evaluator": legacy_lineage},
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--publication", action="store_true")
    mode.add_argument("--legacy-nonpublication", action="store_true")
    parser.add_argument("--sources", help="canonical v2 source JSON/JSONL")
    parser.add_argument("--lineage", help="finalized v2 lineage.json")
    parser.add_argument(
        "--scores",
        action="append",
        help="canonical v2 score JSON/JSONL; repeat for each evaluator",
    )
    parser.add_argument(
        "--expected-evaluator",
        action="append",
        help="expected evaluator key; repeat to require an exact evaluator set",
    )
    parser.add_argument(
        "--legacy-phi",
        action="append",
        help="legacy phi JSON; repeat for each evaluator (non-publication only)",
    )
    parser.add_argument(
        "--debug-dir", default=expand_placeholder("${HC_DATA_ROOT}/debug_logs"), help="legacy debug directory"
    )
    parser.add_argument("--out", help="strict JSON output path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.publication:
        if not args.sources or not args.scores or not args.lineage:
            parser.error(
                "--publication requires canonical v2 --sources, --scores, and --lineage"
            )
        if args.legacy_phi:
            parser.error("legacy inputs are forbidden in --publication mode")
        source_artifact = analysis_core.load_rows(args.sources, kind="source")
        score_artifacts = [
            analysis_core.load_rows(path, kind="score") for path in args.scores
        ]
        lineage_binding = analysis_core.validate_finalized_lineage(
            args.lineage, source_artifact, score_artifacts
        )
        result = analyze_manifest_bound(
            source_artifact.rows,
            tuple(row for artifact in score_artifacts for row in artifact.rows),
            expected_evaluators=args.expected_evaluator,
            source_artifact_sha256=source_artifact.artifact_sha256,
            score_artifact_sha256es=[
                artifact.artifact_sha256 for artifact in score_artifacts
            ],
        )
        result["lineage"]["finalized_migration"] = {
            key: value
            for key, value in lineage_binding.items()
            if key != "debug_file_sha256_by_key"
        }
    else:
        if args.sources or args.scores or args.lineage or args.expected_evaluator:
            parser.error("canonical v2 options cannot be combined with legacy mode")
        if not args.legacy_phi or len(args.legacy_phi) < 2:
            parser.error(
                "--legacy-nonpublication requires at least two --legacy-phi artifacts"
            )
        result = analyze_legacy_nonpublication(args.legacy_phi, args.debug_dir)

    if args.out:
        immutable_inputs = (
            [args.sources, *args.scores, args.lineage]
            if args.publication
            else list(args.legacy_phi or [])
        )
        analysis_core.reject_output_alias(args.out, immutable_inputs)
        analysis_core.write_strict_json(args.out, result)
        print(f"summary -> {args.out}")
    else:
        print(analysis_core.strict_json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
