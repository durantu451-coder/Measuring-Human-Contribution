# -*- coding: utf-8 -*-
"""CLI for strict white-box/black-box baseline analysis.

Publication mode consumes canonical baseline-v2 source and score artifacts::

    python -m experiment_baseline.analyze_phi_ext \
        --publication --sources frozen_sources.jsonl --scores phi_llama.jsonl \
        --blackbox-root . --out summary.json

The historical ``--phi``/``--debug_dir`` interface remains available only as a
clearly labeled, non-publication compatibility path.  Statistical definitions,
joining, validation, bootstrapping, and JSON policy all live in
:mod:`experiment_baseline.analysis_core`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from experiment_baseline import analysis_core
from experiment_baseline.whitebox_core import expand_placeholder


LEVELS = list(analysis_core.LEVELS)


def load_paired(phi_path: str, debug_dir: str):
    """Compatibility wrapper for callers of the historical helper."""

    evaluator, items, _ = analysis_core.load_legacy_paired(phi_path, debug_dir)
    return evaluator, list(items)


def analyze(
    eval_model: str,
    items: Sequence[analysis_core.PairedItem],
    label: str,
    out_sum: dict[str, Any],
    n_boot: int = 0,
    seed: int = analysis_core.DEFAULT_SEED,
):
    """Compatibility wrapper that delegates every statistic to analysis_core."""

    summary = analysis_core.analyze_paired_items(
        items,
        n_bootstrap=n_boot,
        seed=seed,
        mode="legacy_nonpublication",
    )
    if summary["evaluator"] != eval_model:
        raise analysis_core.AnalysisError(
            f"evaluator mismatch: {summary['evaluator']!r} != {eval_model!r}"
        )
    summary["label"] = label
    out_sum.clear()
    out_sum.update(summary)
    _print_evaluator_summary(summary)
    return summary


def _format_stat(value: Any) -> str:
    return "undefined" if value is None else f"{float(value):+.4f}"


def _print_evaluator_summary(summary: dict[str, Any]) -> None:
    coverage = summary["coverage"]
    agreement = summary["agreement"]
    pooled = agreement["pooled_gradient_agreement"]
    centered = agreement["item_centered_spearman"]
    vector_tau = agreement["per_item_vector_kendall_tau_b"]
    print("=" * 88)
    print(f"EVALUATOR: {summary['evaluator']}  MODE: {summary['mode']}")
    print(
        "coverage: "
        f"{coverage['joined_items']} items, "
        f"{coverage['item_level_pairs']} item-level pairs, "
        f"{coverage['source_clusters']} source clusters"
    )
    print(
        "pooled gradient agreement rho: "
        f"{_format_stat(pooled['spearman_rho'])} "
        f"(effective n={pooled['effective_n']})"
    )
    print(
        "item-centered rho: "
        f"{_format_stat(centered['spearman_rho'])}; "
        "mean per-item vector tau-b: "
        f"{_format_stat(vector_tau['mean_tau_b'])}"
    )
    print("within-level rho:")
    for level in LEVELS:
        row = agreement["within_level_spearman"][level]
        print(
            f"  {level}: {_format_stat(row['spearman_rho'])} "
            f"(effective n={row['effective_n']})"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Strict manifest-bound white-box baseline analysis"
    )
    parser.add_argument(
        "--publication",
        action="store_true",
        help="fail unless explicit canonical v2 --sources and --scores are supplied",
    )
    parser.add_argument(
        "--sources",
        "--source",
        "--source-manifest",
        dest="sources",
        help="canonical v2 source manifest (.json array or .jsonl)",
    )
    parser.add_argument(
        "--scores",
        "--score",
        dest="scores",
        action="append",
        help="canonical v2 score artifact; repeat for multiple evaluators",
    )
    parser.add_argument(
        "--lineage",
        default=None,
        help="finalized v2 lineage.json (required with --publication)",
    )
    parser.add_argument(
        "--blackbox-root",
        default=None,
        help="base directory for source_file paths (default: source manifest directory)",
    )
    parser.add_argument(
        "--expected-evaluator",
        default=None,
        help="optional evaluator key required in every supplied score row",
    )
    parser.add_argument(
        "--expected-protocol-sha256",
        default=None,
        help="optional protocol fingerprint (default: current canonical scorer protocol)",
    )

    # Historical interface.  It is intentionally impossible in --publication mode.
    parser.add_argument("--phi", default=None, help="legacy phi JSON (non-publication only)")
    parser.add_argument(
        "--debug_dir",
        "--debug-dir",
        dest="debug_dir",
        default=expand_placeholder("${HC_DATA_ROOT}/debug_logs"),
        help="legacy debug-log directory",
    )
    parser.add_argument("--out", default=None, help="strict JSON output path")
    parser.add_argument(
        "--bootstrap",
        type=int,
        default=2000,
        help="source-cluster bootstrap resamples (0 disables; default: 2000)",
    )
    parser.add_argument("--seed", type=int, default=analysis_core.DEFAULT_SEED)
    return parser


def _run_v2(args: argparse.Namespace) -> dict[str, Any]:
    source_artifact = analysis_core.load_rows(args.sources, kind="source")
    score_artifacts = [
        analysis_core.load_rows(path, kind="score") for path in args.scores
    ]
    score_rows = tuple(
        row for artifact in score_artifacts for row in artifact.rows
    )
    base_dir = Path(args.blackbox_root)
    if args.out:
        immutable_inputs = [args.sources, *args.scores]
        if args.lineage:
            immutable_inputs.append(args.lineage)
        immutable_inputs.extend(
            base_dir / row["source_file"] for row in source_artifact.rows
        )
        analysis_core.reject_output_alias(args.out, immutable_inputs)
    lineage_binding = (
        analysis_core.validate_finalized_lineage(
            args.lineage, source_artifact, score_artifacts
        )
        if args.lineage
        else None
    )
    expected_debug_hashes = None
    if lineage_binding is not None:
        expected_debug_hashes = {
            tuple(key.split("\t")): digest
            for key, digest in lineage_binding[
                "debug_file_sha256_by_key"
            ].items()
        }
    result = analysis_core.analyze_manifest_bound(
        source_artifact.rows,
        score_rows,
        source_base_dir=base_dir,
        expected_blackbox_file_sha256_by_key=expected_debug_hashes,
        expected_evaluator=args.expected_evaluator,
        expected_protocol_sha256=args.expected_protocol_sha256,
        n_bootstrap=args.bootstrap,
        seed=args.seed,
        source_artifact_sha256=source_artifact.artifact_sha256,
        score_artifact_sha256es=[
            artifact.artifact_sha256 for artifact in score_artifacts
        ],
    )
    if lineage_binding is not None:
        result["lineage"]["finalized_migration"] = {
            key: value
            for key, value in lineage_binding.items()
            if key != "debug_file_sha256_by_key"
        }
    return result


def _run_legacy(args: argparse.Namespace) -> dict[str, Any]:
    evaluator, items, lineage = analysis_core.load_legacy_paired(
        args.phi, args.debug_dir
    )
    summary = analysis_core.analyze_paired_items(
        items,
        n_bootstrap=args.bootstrap,
        seed=args.seed,
        mode="legacy_nonpublication",
    )
    return analysis_core.to_strict_json_value(
        {
            "analysis_schema_version": 1,
            "mode": "legacy_nonpublication",
            "publication_eligible": False,
            "warning": (
                "Legacy inputs lack canonical source/score evaluator and protocol "
                "binding; this output must not be used for publication."
            ),
            "lineage": lineage,
            "coverage": {
                "exact_for_listed_legacy_rows": True,
                "joined_items": len(items),
                "evaluator_count": 1,
            },
            "analyses": {evaluator: summary},
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    has_v2 = bool(args.sources or args.scores)
    if args.publication and (not args.sources or not args.scores or not args.lineage):
        parser.error(
            "--publication requires explicit v2 --sources, --scores, and --lineage"
        )
    if has_v2 and (not args.sources or not args.scores):
        parser.error("v2 analysis requires both --sources and at least one --scores")
    if has_v2 and not args.blackbox_root:
        parser.error("v2 analysis requires explicit --blackbox-root")
    if has_v2 and args.phi:
        parser.error("canonical v2 inputs cannot be combined with legacy --phi")
    if not has_v2 and not args.phi:
        parser.error("provide v2 --sources/--scores, or legacy --phi")
    if args.publication and args.phi:
        parser.error("legacy --phi is forbidden in --publication mode")
    if args.bootstrap < 0:
        parser.error("--bootstrap must be non-negative")
    if args.out and not has_v2:
        analysis_core.reject_output_alias(args.out, [args.phi])
        if Path(args.out).resolve().parent == Path(args.debug_dir).resolve():
            parser.error("legacy --out may not be written inside --debug-dir")

    result = _run_v2(args) if has_v2 else _run_legacy(args)
    for evaluator in sorted(result["analyses"]):
        _print_evaluator_summary(result["analyses"][evaluator])

    if args.out:
        analysis_core.write_strict_json(args.out, result)
        print(f"summary -> {args.out}")
    else:
        print("No --out path supplied; summary was not written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
