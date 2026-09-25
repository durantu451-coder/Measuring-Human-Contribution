# -*- coding: utf-8 -*-
"""Designed-level ordinal concordance for baseline measurements.

The filename is retained for compatibility, but this analysis does *not* compare
measurements with observed human annotations or ground truth.  It quantifies
ordinal concordance with the study-imposed L1..L5 contribution design.  In
publication mode, canonical v2 sources and scores are mandatory and all joins
are delegated to :mod:`experiment_baseline.analysis_core`.

Reliability is deliberately out of scope: inter-evaluator reliability belongs in
``alpha_whitebox.py``; inter-compressor reliability is a separate Experiment A
estimand.  Legacy inputs require explicit ``--legacy-nonpublication`` mode.
"""

from __future__ import annotations

from experiment_baseline.whitebox_core import expand_placeholder
from pathlib import Path  # noqa: F401

import argparse
import math
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

from scipy.stats import spearmanr

from experiment_baseline import analysis_core
from experiment_baseline import whitebox_schema


LEVELS = tuple(whitebox_schema.LEVELS)
# Higher values mean more designed human contribution; this is a design axis,
# not a set of collected human ratings.
DESIGNED_CONTRIBUTION_ORDINAL = (5.0, 4.0, 3.0, 2.0, 1.0)


def _statistic_value(result: Any) -> float | None:
    value = getattr(result, "statistic", result)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _safe_spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    if min(xs) == max(xs) or min(ys) == max(ys):
        return None
    return _statistic_value(spearmanr(xs, ys))


def _mean_defined(values: Sequence[float | None]) -> float | None:
    finite = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.fmean(finite) if finite else None


def summarize_ordinal_concordance(
    vectors_by_key: Mapping[whitebox_schema.SemanticKey, Sequence[float]],
) -> dict[str, Any]:
    """Summarize tie-aware concordance with the designed contribution order."""

    ordered = [(key, tuple(vectors_by_key[key])) for key in sorted(vectors_by_key)]
    for key, vector in ordered:
        if len(vector) != len(LEVELS):
            raise analysis_core.AnalysisError(
                f"method vector for {key!r} must contain exactly {len(LEVELS)} levels"
            )
        if any(not math.isfinite(float(value)) for value in vector):
            raise analysis_core.AnalysisError(
                f"method vector for {key!r} contains a non-finite value"
            )

    flat_design = [
        value for _key, _vector in ordered for value in DESIGNED_CONTRIBUTION_ORDINAL
    ]
    flat_scores = [float(value) for _key, vector in ordered for value in vector]
    item_spearman = [
        _safe_spearman(DESIGNED_CONTRIBUTION_ORDINAL, vector)
        for _key, vector in ordered
    ]
    item_tau = [
        analysis_core.kendall_tau_b(DESIGNED_CONTRIBUTION_ORDINAL, vector)
        for _key, vector in ordered
    ]
    defined_spearman = sum(value is not None for value in item_spearman)
    defined_tau = sum(value is not None for value in item_tau)
    return {
        "pooled": {
            "spearman_rho": _safe_spearman(flat_design, flat_scores),
            "kendall_tau_b": analysis_core.kendall_tau_b(
                flat_design, flat_scores
            ),
            "effective_n_item_level_pairs": len(flat_scores),
        },
        "per_item": {
            "mean_spearman_rho": _mean_defined(item_spearman),
            "mean_kendall_tau_b": _mean_defined(item_tau),
            "effective_n_spearman": defined_spearman,
            "undefined_n_spearman": len(item_spearman) - defined_spearman,
            "effective_n_kendall_tau_b": defined_tau,
            "undefined_n_kendall_tau_b": len(item_tau) - defined_tau,
            "total_items": len(ordered),
        },
        "methods": {
            "spearman": "scipy.stats.spearmanr",
            "kendall": "scipy.stats.kendalltau(variant='b')",
        },
    }


def _method_report(
    vectors_by_key: Mapping[whitebox_schema.SemanticKey, Sequence[float]],
) -> dict[str, Any]:
    by_model: dict[str, dict[whitebox_schema.SemanticKey, Sequence[float]]] = {}
    by_domain: dict[str, dict[whitebox_schema.SemanticKey, Sequence[float]]] = {}
    for key, vector in vectors_by_key.items():
        by_model.setdefault(key[0], {})[key] = vector
        by_domain.setdefault(key[1], {})[key] = vector
    return {
        "overall": summarize_ordinal_concordance(vectors_by_key),
        "by_generation_model": {
            name: summarize_ordinal_concordance(rows)
            for name, rows in sorted(by_model.items())
        },
        "by_domain": {
            name: summarize_ordinal_concordance(rows)
            for name, rows in sorted(by_domain.items())
        },
    }


def _vectors_from_prepared(
    prepared: analysis_core.PreparedAnalysis,
) -> dict[str, dict[whitebox_schema.SemanticKey, tuple[float, ...]]]:
    methods: dict[
        str, dict[whitebox_schema.SemanticKey, tuple[float, ...]]
    ] = {}
    for evaluator, items in sorted(prepared.by_evaluator.items()):
        methods[f"whitebox/{evaluator}"] = {
            item.semantic_key: item.whitebox_excess for item in items
        }

    first_evaluator = next(iter(sorted(prepared.by_evaluator)))
    methods["blackbox/aggregate"] = {
        item.semantic_key: item.blackbox_excess
        for item in prepared.by_evaluator[first_evaluator]
    }
    return methods


def _assemble_result(
    methods: Mapping[
        str, Mapping[whitebox_schema.SemanticKey, Sequence[float]]
    ],
    *,
    mode: str,
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    if not methods:
        raise analysis_core.AnalysisError("no methods supplied")
    key_sets = {name: set(rows) for name, rows in methods.items()}
    first_name = sorted(key_sets)[0]
    expected_keys = key_sets[first_name]
    for name, keys in sorted(key_sets.items()):
        if keys != expected_keys:
            raise analysis_core.CoverageError(
                f"method {name!r} key coverage does not match {first_name!r}"
            )

    publication = mode == "manifest_bound_v2"
    result = {
        "analysis_schema_version": 1,
        "analysis_type": "designed_level_ordinal_concordance",
        "mode": mode,
        "publication_eligible": publication,
        "construct": {
            "name": "designed_level_ordinal_concordance",
            "ordinal_scores": {
                level: score
                for level, score in zip(LEVELS, DESIGNED_CONTRIBUTION_ORDINAL)
            },
            "interpretation": (
                "Concordance with the study-imposed level order; this is not an "
                "observed human-rating target and is not a reliability coefficient."
            ),
        },
        "reliability_scope": {
            "computed_here": False,
            "inter_evaluator": "reported separately by alpha_whitebox.py",
            "inter_compressor": "separate Experiment A estimand",
        },
        "lineage": dict(lineage),
        "coverage": {
            "exact": publication,
            "semantic_items": len(expected_keys),
            "item_level_pairs_per_method": len(expected_keys) * len(LEVELS),
            "method_count": len(methods),
            "methods": sorted(methods),
            "levels": list(LEVELS),
            "missing_keys": [],
            "unexpected_keys": [],
        },
        "designed_level_ordinal_concordance": {
            name: _method_report(rows) for name, rows in sorted(methods.items())
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
    blackbox_rows: Sequence[Mapping[str, Any]] | None = None,
    source_base_dir: str | Path | None = None,
    expected_blackbox_file_sha256_by_key: Mapping[
        whitebox_schema.SemanticKey, str
    ] | None = None,
    expected_evaluator: str | None = None,
    expected_protocol_sha256: str | None = None,
    source_artifact_sha256: str | None = None,
    score_artifact_sha256es: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run publication-eligible concordance on strict canonical v2 joins."""

    prepared = analysis_core.prepare_manifest_bound_analysis(
        source_rows,
        score_rows,
        blackbox_rows=blackbox_rows,
        source_base_dir=source_base_dir,
        expected_blackbox_file_sha256_by_key=expected_blackbox_file_sha256_by_key,
        expected_evaluator=expected_evaluator,
        expected_protocol_sha256=expected_protocol_sha256,
    )
    methods = _vectors_from_prepared(prepared)
    lineage = {
        "source_manifest_sha256": prepared.source_manifest_sha256,
        "score_manifest_sha256": prepared.score_manifest_sha256,
        "blackbox_artifact_set_sha256": prepared.blackbox_artifact_set_sha256,
        "source_artifact_sha256": source_artifact_sha256,
        "score_artifact_sha256es": list(score_artifact_sha256es or []),
        "evaluator_sha256_by_evaluator": {
            evaluator: _uniform_item_value(items, "evaluator_sha256")
            for evaluator, items in sorted(prepared.by_evaluator.items())
        },
        "protocol_sha256_by_evaluator": {
            evaluator: _uniform_item_value(items, "protocol_sha256")
            for evaluator, items in sorted(prepared.by_evaluator.items())
        },
    }
    return _assemble_result(
        methods, mode="manifest_bound_v2", lineage=lineage
    )


def _uniform_item_value(
    items: Sequence[analysis_core.PairedItem], attribute: str
) -> Any:
    values = {getattr(item, attribute) for item in items}
    if len(values) != 1:
        raise analysis_core.AnalysisError(
            f"{attribute} must be uniform within an evaluator"
        )
    return next(iter(values))


def analyze_legacy_nonpublication(
    phi_paths: Sequence[str | Path], debug_dir: str | Path
) -> dict[str, Any]:
    """Analyze legacy artifacts without ever treating list position as identity."""

    methods: dict[
        str, dict[whitebox_schema.SemanticKey, tuple[float, ...]]
    ] = {}
    lineage_by_evaluator: dict[str, Any] = {}
    blackbox_reference: dict[
        whitebox_schema.SemanticKey, tuple[float, ...]
    ] | None = None
    for path in phi_paths:
        evaluator, items, lineage = analysis_core.load_legacy_paired(path, debug_dir)
        method_name = f"whitebox/{evaluator}"
        if method_name in methods:
            raise analysis_core.CoverageError(
                f"duplicate legacy evaluator {evaluator!r}"
            )
        methods[method_name] = {
            item.semantic_key: item.whitebox_excess for item in items
        }
        current_blackbox = {
            item.semantic_key: item.blackbox_excess for item in items
        }
        if blackbox_reference is None:
            blackbox_reference = current_blackbox
        elif current_blackbox != blackbox_reference:
            raise analysis_core.CoverageError(
                f"legacy evaluator {evaluator!r} black-box/key coverage differs"
            )
        lineage_by_evaluator[evaluator] = lineage
    if blackbox_reference is None:
        raise analysis_core.CoverageError("no legacy phi artifacts supplied")
    methods["blackbox/aggregate"] = blackbox_reference
    return _assemble_result(
        methods,
        mode="legacy_nonpublication",
        lineage={"legacy_artifacts_by_evaluator": lineage_by_evaluator},
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--publication", action="store_true")
    mode.add_argument("--legacy-nonpublication", action="store_true")
    parser.add_argument("--sources", help="canonical v2 source JSON/JSONL")
    parser.add_argument("--lineage", help="finalized v2 lineage.json")
    parser.add_argument(
        "--scores", action="append", help="canonical v2 score JSON/JSONL; repeatable"
    )
    parser.add_argument(
        "--blackbox-root",
        help="base directory for source_file paths (defaults to source manifest directory)",
    )
    parser.add_argument("--expected-evaluator")
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument(
        "--legacy-phi", action="append", help="legacy phi JSON (non-publication only)"
    )
    parser.add_argument("--debug-dir", default=expand_placeholder("${HC_DATA_ROOT}/debug_logs"))
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
        if not args.blackbox_root:
            parser.error("--publication requires explicit --blackbox-root")
        if args.legacy_phi:
            parser.error("legacy inputs are forbidden in --publication mode")
        source_artifact = analysis_core.load_rows(args.sources, kind="source")
        score_artifacts = [
            analysis_core.load_rows(path, kind="score") for path in args.scores
        ]
        base_dir = Path(args.blackbox_root)
        if args.out:
            analysis_core.reject_output_alias(
                args.out,
                [args.sources, *args.scores, args.lineage]
                + [base_dir / row["source_file"] for row in source_artifact.rows],
            )
        lineage_binding = analysis_core.validate_finalized_lineage(
            args.lineage, source_artifact, score_artifacts
        )
        expected_debug_hashes = {
            tuple(key.split("\t")): digest
            for key, digest in lineage_binding[
                "debug_file_sha256_by_key"
            ].items()
        }
        result = analyze_manifest_bound(
            source_artifact.rows,
            tuple(row for artifact in score_artifacts for row in artifact.rows),
            source_base_dir=base_dir,
            expected_blackbox_file_sha256_by_key=expected_debug_hashes,
            expected_evaluator=args.expected_evaluator,
            expected_protocol_sha256=args.expected_protocol_sha256,
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
        if args.sources or args.scores or args.lineage or args.blackbox_root:
            parser.error("canonical v2 inputs cannot be combined with legacy mode")
        if args.expected_evaluator or args.expected_protocol_sha256:
            parser.error("canonical validation options are unavailable in legacy mode")
        if not args.legacy_phi:
            parser.error("--legacy-nonpublication requires --legacy-phi")
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
