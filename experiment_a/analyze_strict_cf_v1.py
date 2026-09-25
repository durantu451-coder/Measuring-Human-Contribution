# -*- coding: utf-8 -*-
"""Produce the complete matched strict-CF v1 actual-only analysis.

Only aggregate and per-compressor ``actual_ratio`` values enter statistics.  The
legacy shared baseline and legacy excess fields remain in immutable snapshots
for audit, but are never read by analysis calculations.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_a.strict_cf_schema import (
    COMPRESSORS,
    DOMAINS,
    EXPECTED_LEVEL_ROWS,
    EXPECTED_MODEL_ITEMS,
    EXPECTED_SOURCE_CLUSTERS,
    EXPECTED_SOURCES_PER_DOMAIN,
    LEVELS,
    MODELS,
    PROVENANCE_TIER_EXACT,
    STRICT_ACTUAL_PROVENANCE_TIERS,
    SCHEMA_ID,
    SCHEMA_VERSION,
    STATUS_ACTUAL_VALID,
    StrictCFSchemaError,
    assert_path_within_run,
    canonical_json_text,
    file_sha256,
    validate_actual_snapshot_row,
    validate_manifest,
    validate_run_dir,
)
from experiment_b import storage


class StrictCFAnalysisError(RuntimeError):
    """The actual snapshot cannot support the requested matched analysis."""


BOOTSTRAP_SEED = 20260903
BOOTSTRAP_REPLICATES = 1000


def _rankdata(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        rank = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[order[position]] = rank
        index = end + 1
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    numerator = math.fsum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    left_ss = math.fsum((x - left_mean) ** 2 for x in left)
    right_ss = math.fsum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator > 0 else None


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _pearson(_rankdata(left), _rankdata(right))


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("quantile requires values")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def describe(values: Sequence[float]) -> dict[str, float | int]:
    """Return deterministic finite descriptive statistics with no NaN output."""

    if not values:
        raise StrictCFAnalysisError("cannot describe an empty group")
    if any(not math.isfinite(value) for value in values):
        raise StrictCFAnalysisError("actual-only values must all be finite")
    ordered = sorted(values)
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
    return {
        "n": len(values),
        "mean": mean,
        "std_population": math.sqrt(variance),
        "min": ordered[0],
        "q25": _quantile(ordered, 0.25),
        "median": statistics.median(ordered),
        "q75": _quantile(ordered, 0.75),
        "max": ordered[-1],
    }


def _validate_coverage(
    rows: Sequence[Mapping[str, Any]],
    *,
    require_full: bool,
    require_matched: bool,
) -> dict[str, Any]:
    semantic_keys: set[tuple[str, ...]] = set()
    clusters: set[tuple[str, str]] = set()
    items: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    cluster_models: dict[tuple[str, str], set[str]] = defaultdict(set)
    domain_clusters: dict[str, set[tuple[str, str]]] = defaultdict(set)
    scope_items: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    provenance_tiers: Counter[str] = Counter()
    verification_tiers: Counter[str] = Counter()
    joint_tiers: Counter[str] = Counter()

    for index, row in enumerate(rows):
        validate_actual_snapshot_row(
            row, seen_keys=semantic_keys, path=f"actual_rows[{index}]"
        )
        model = row["generation_model"]
        domain = row["domain"]
        item_id = row["id"]
        source_hash = row["source_text_sha256"]
        level = row["level"]
        cluster = (domain, source_hash)
        item = (model, domain, item_id, source_hash)
        clusters.add(cluster)
        items[item].add(level)
        cluster_models[cluster].add(model)
        domain_clusters[domain].add(cluster)
        scope_items[(model, domain)].add((item_id, source_hash))
        provenance_tiers[row["provenance_tier"]] += 1
        verification_tiers[row["verification_tier"]] += 1
        joint_tiers[
            f"{row['provenance_tier']}/{row['verification_tier']}"
        ] += 1

    incomplete = [item for item, levels in items.items() if levels != set(LEVELS)]
    if incomplete:
        raise StrictCFAnalysisError(
            f"{len(incomplete)} model-items do not contain exactly L1-L5"
        )
    unmatched = [
        cluster for cluster, models in cluster_models.items() if models != set(MODELS)
    ]
    if require_matched and unmatched:
        raise StrictCFAnalysisError(
            f"{len(unmatched)} source clusters are not shared by all five models"
        )

    counts = {
        "level_rows": len(rows),
        "semantic_keys": len(semantic_keys),
        "source_clusters": len(clusters),
        "model_items": len(items),
        "by_domain_source_clusters": {
            domain: len(domain_clusters[domain]) for domain in DOMAINS
        },
        "by_model_domain_items": {
            f"{model}/{domain}": len(scope_items[(model, domain)])
            for model in MODELS
            for domain in DOMAINS
        },
        "by_provenance_tier": dict(sorted(provenance_tiers.items())),
        "by_verification_tier": dict(sorted(verification_tiers.items())),
        "by_provenance_verification_tier": dict(sorted(joint_tiers.items())),
    }
    if require_full:
        if any(
            tier not in STRICT_ACTUAL_PROVENANCE_TIERS
            for tier in provenance_tiers
        ):
            raise StrictCFAnalysisError(
                "matched strict snapshot contains unattested provenance rows"
            )
        if verification_tiers != Counter(
            {"recomputed_actual_and_per_compressor": len(rows)}
        ):
            raise StrictCFAnalysisError(
                "matched strict snapshot must contain only recomputed actual rows"
            )
        if len(rows) != EXPECTED_LEVEL_ROWS:
            raise StrictCFAnalysisError(
                f"actual snapshot has {len(rows)} rows; expected {EXPECTED_LEVEL_ROWS}"
            )
        if len(clusters) != EXPECTED_SOURCE_CLUSTERS:
            raise StrictCFAnalysisError(
                f"snapshot has {len(clusters)} clusters; expected {EXPECTED_SOURCE_CLUSTERS}"
            )
        if len(items) != EXPECTED_MODEL_ITEMS:
            raise StrictCFAnalysisError(
                f"snapshot has {len(items)} model-items; expected {EXPECTED_MODEL_ITEMS}"
            )
        for domain in DOMAINS:
            if len(domain_clusters[domain]) != EXPECTED_SOURCES_PER_DOMAIN:
                raise StrictCFAnalysisError(
                    f"{domain} has {len(domain_clusters[domain])} clusters; "
                    f"expected {EXPECTED_SOURCES_PER_DOMAIN}"
                )
        for model in MODELS:
            for domain in DOMAINS:
                if len(scope_items[(model, domain)]) != EXPECTED_SOURCES_PER_DOMAIN:
                    raise StrictCFAnalysisError(
                        f"{model}/{domain} does not have exactly "
                        f"{EXPECTED_SOURCES_PER_DOMAIN} model-items"
                    )
    return counts


def _stats_by_keys(
    records: Sequence[tuple[Mapping[str, Any], float]],
    fields: Sequence[str],
) -> dict[str, dict[str, float | int]]:
    grouped: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row, value in records:
        grouped[tuple(str(row[field]) for field in fields)].append(value)
    return {
        "/".join(key): describe(values)
        for key, values in sorted(grouped.items())
    }


def _gradient_summary(
    records: Sequence[tuple[Mapping[str, Any], float]],
) -> dict[str, Any]:
    treatment_score = {level: float(len(LEVELS) - index) for index, level in enumerate(LEVELS)}
    pooled_treatment: list[float] = []
    pooled_actual: list[float] = []
    per_item: dict[tuple[str, str, str, str], dict[str, float]] = defaultdict(dict)
    for row, value in records:
        level = row["level"]
        pooled_treatment.append(treatment_score[level])
        pooled_actual.append(value)
        key = (
            row["generation_model"],
            row["domain"],
            row["id"],
            row["source_text_sha256"],
        )
        per_item[key][level] = value

    item_rhos: list[float] = []
    full_monotonic = 0
    pair_counts = {f"{left}>{right}": 0 for left, right in zip(LEVELS, LEVELS[1:])}
    for values in per_item.values():
        if set(values) != set(LEVELS):
            raise StrictCFAnalysisError("gradient item lacks one or more levels")
        vector = [values[level] for level in LEVELS]
        rho = _spearman([5.0, 4.0, 3.0, 2.0, 1.0], vector)
        if rho is not None:
            item_rhos.append(rho)
        comparisons = []
        for left, right in zip(LEVELS, LEVELS[1:]):
            passed = values[left] > values[right]
            comparisons.append(passed)
            if passed:
                pair_counts[f"{left}>{right}"] += 1
        if all(comparisons):
            full_monotonic += 1

    n_items = len(per_item)
    level_means = {
        level: describe(
            [value for row, value in records if row["level"] == level]
        )["mean"]
        for level in LEVELS
    }
    return {
        "investigator_designed_treatment_scores": {
            level: treatment_score[level] for level in LEVELS
        },
        "level_means": level_means,
        "mean_gradient_strictly_monotonic": all(
            level_means[LEVELS[index]] > level_means[LEVELS[index + 1]]
            for index in range(len(LEVELS) - 1)
        ),
        "adjacent_mean_deltas": {
            f"{left}-{right}": level_means[left] - level_means[right]
            for left, right in zip(LEVELS, LEVELS[1:])
        },
        "pooled_treatment_level_spearman": _spearman(
            pooled_treatment, pooled_actual
        ),
        "mean_per_item_treatment_level_spearman": (
            math.fsum(item_rhos) / len(item_rhos) if item_rhos else None
        ),
        "median_per_item_treatment_level_spearman": (
            statistics.median(item_rhos) if item_rhos else None
        ),
        "fully_monotonic_items": full_monotonic,
        "fully_monotonic_fraction": full_monotonic / n_items if n_items else None,
        "adjacent_pair_fractions": {
            name: count / n_items if n_items else None
            for name, count in pair_counts.items()
        },
        "n_model_items": n_items,
    }


def _cluster_bootstrap(
    records: Sequence[tuple[Mapping[str, Any], float]],
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    """Percentile intervals from deterministic source-cluster resampling."""

    if type(replicates) is not int or replicates <= 0:
        raise ValueError("bootstrap replicates must be a positive integer")
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row, value in records:
        grouped[(row["domain"], row["source_text_sha256"])][row["level"]].append(value)
    clusters = sorted(grouped)
    if not clusters:
        raise StrictCFAnalysisError("cluster bootstrap requires at least one cluster")
    cluster_stats = {
        cluster: {
            level: (math.fsum(values), len(values))
            for level, values in per_level.items()
        }
        for cluster, per_level in grouped.items()
    }
    rng = random.Random(seed)
    level_replicates = {level: [] for level in LEVELS}
    delta_names = [f"{left}-{right}" for left, right in zip(LEVELS, LEVELS[1:])]
    delta_replicates = {name: [] for name in delta_names}
    for _ in range(replicates):
        sampled = Counter(
            clusters[rng.randrange(len(clusters))] for _ in clusters
        )
        means: dict[str, float] = {}
        for level in LEVELS:
            numerator = math.fsum(
                frequency * cluster_stats[cluster].get(level, (0.0, 0))[0]
                for cluster, frequency in sampled.items()
            )
            denominator = sum(
                frequency * cluster_stats[cluster].get(level, (0.0, 0))[1]
                for cluster, frequency in sampled.items()
            )
            if denominator == 0:
                raise StrictCFAnalysisError(
                    f"bootstrap sample has no values for treatment {level}"
                )
            means[level] = numerator / denominator
            level_replicates[level].append(means[level])
        for left, right in zip(LEVELS, LEVELS[1:]):
            delta_replicates[f"{left}-{right}"].append(means[left] - means[right])

    def interval(values: list[float]) -> dict[str, float]:
        ordered = sorted(values)
        return {
            "lower_2_5pct": _quantile(ordered, 0.025),
            "median": _quantile(ordered, 0.5),
            "upper_97_5pct": _quantile(ordered, 0.975),
        }

    return {
        "unit": "source_cluster=[domain,source_text_sha256]",
        "seed": seed,
        "replicates": replicates,
        "cluster_count": len(clusters),
        "level_mean_95pct_interval": {
            level: interval(level_replicates[level]) for level in LEVELS
        },
        "adjacent_delta_95pct_interval": {
            name: interval(delta_replicates[name]) for name in delta_names
        },
    }


def _per_compressor_actual_diagnostics(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Diagnostics consume only each compressor's stored ``actual_ratio``."""

    diagnostics: dict[str, Any] = {}
    for compressor in COMPRESSORS:
        records = [
            (
                row,
                float(row["actual"]["per_compressor"][compressor]["actual_ratio"]),
            )
            for row in rows
        ]
        diagnostics[compressor] = {
            "overall": describe([value for _, value in records]),
            "by_level": _stats_by_keys(records, ("level",)),
            "gradient": _gradient_summary(records),
        }
    return diagnostics


def analyze_actual_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    require_full: bool = True,
    require_matched: bool = True,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
    bootstrap_seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Analyze only aggregate and per-compressor ``actual_ratio`` fields."""

    materialized = [dict(row) for row in rows]
    counts = _validate_coverage(
        materialized,
        require_full=require_full,
        require_matched=require_matched,
    )

    # Aggregate extraction point.  The only additional numeric measurements used
    # below are each compressor's own actual_ratio diagnostics; legacy
    # baseline/excess fields never enter a statistic.
    records = [
        (row, float(row["actual"]["actual_ratio"])) for row in materialized
    ]
    values = [value for _, value in records]

    model_domain_gradient: dict[str, Any] = {}
    for model in MODELS:
        for domain in DOMAINS:
            subset = [
                pair
                for pair in records
                if pair[0]["generation_model"] == model
                and pair[0]["domain"] == domain
            ]
            if subset:
                model_domain_gradient[f"{model}/{domain}"] = _gradient_summary(subset)

    model_gradient = {}
    for model in MODELS:
        subset = [pair for pair in records if pair[0]["generation_model"] == model]
        if subset:
            model_gradient[model] = _gradient_summary(subset)

    domain_gradient = {}
    for domain in DOMAINS:
        subset = [pair for pair in records if pair[0]["domain"] == domain]
        if subset:
            domain_gradient[domain] = _gradient_summary(subset)

    current_exact_records = [
        pair
        for pair in records
        if pair[0]["provenance_tier"] == PROVENANCE_TIER_EXACT
    ]
    current_exact_sensitivity = None
    if current_exact_records:
        current_exact_sensitivity = {
            "scope": "current-route exact actual rows only; not rematched across models",
            "level_rows": len(current_exact_records),
            "model_items": len(current_exact_records) // len(LEVELS),
            "overall": describe([value for _, value in current_exact_records]),
            "by_level": _stats_by_keys(current_exact_records, ("level",)),
            "by_model": _stats_by_keys(
                current_exact_records, ("generation_model",)
            ),
            "by_model_level": _stats_by_keys(
                current_exact_records, ("generation_model", "level")
            ),
            "gradient": _gradient_summary(current_exact_records),
        }

    return {
        "schema": f"{SCHEMA_ID}.actual_only_report",
        "schema_version": SCHEMA_VERSION,
        "metric_contract": {
            "consumed_numeric_fields": [
                "actual.actual_ratio",
                "actual.per_compressor.*.actual_ratio",
            ],
            "required_semantic_status": STATUS_ACTUAL_VALID,
            "legacy_shared_baseline_consumed": False,
            "legacy_shared_excess_consumed": False,
        },
        "counts": counts,
        "overall": describe(values),
        "by_level": _stats_by_keys(records, ("level",)),
        "by_model": _stats_by_keys(records, ("generation_model",)),
        "by_domain": _stats_by_keys(records, ("domain",)),
        "by_provenance_tier": _stats_by_keys(records, ("provenance_tier",)),
        "by_verification_tier": _stats_by_keys(records, ("verification_tier",)),
        "by_model_level": _stats_by_keys(records, ("generation_model", "level")),
        "by_domain_level": _stats_by_keys(records, ("domain", "level")),
        "by_model_domain": _stats_by_keys(records, ("generation_model", "domain")),
        "by_model_domain_level": _stats_by_keys(
            records, ("generation_model", "domain", "level")
        ),
        "current_exact_sensitivity": current_exact_sensitivity,
        "per_compressor_actual_diagnostics": _per_compressor_actual_diagnostics(
            materialized
        ),
        "cluster_bootstrap": _cluster_bootstrap(
            records,
            replicates=bootstrap_replicates,
            seed=bootstrap_seed,
        ),
        "gradient": {
            "overall": _gradient_summary(records),
            "by_model": model_gradient,
            "by_domain": domain_gradient,
            "by_model_domain": model_domain_gradient,
        },
    }


def _load_manifest(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StrictCFAnalysisError(f"cannot load manifest {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise StrictCFAnalysisError("manifest must be a JSON object")
    return value


def load_actual_artifact(
    run_dir: str | Path,
    *,
    artifact_name: str,
    project_root: str | Path = PROJECT,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]], str]:
    """Load and hash-verify one manifest-declared immutable actual snapshot."""

    if artifact_name not in {"actual_levels", "full_actual_levels"}:
        raise StrictCFAnalysisError(f"unsupported actual artifact {artifact_name!r}")
    root = validate_run_dir(
        run_dir, project_root=project_root, must_exist=True
    )
    manifest_path = assert_path_within_run(root, "manifest.json", must_exist=True)
    manifest = _load_manifest(manifest_path)
    validate_manifest(
        manifest,
        run_dir=root,
        project_root=project_root,
        verify_files=True,
    )
    artifact = manifest["artifacts"][artifact_name]
    actual_path = assert_path_within_run(root, artifact["path"], must_exist=True)
    seen: set[tuple[str, ...]] = set()
    scan = storage.scan_jsonl(
        actual_path,
        validator=lambda row: validate_actual_snapshot_row(row, seen_keys=seen),
        id_getter=lambda row: canonical_json_text(row["semantic_key"]),
        repair=False,
    )
    if len(scan) != artifact["row_count"]:
        raise StrictCFAnalysisError(
            f"actual snapshot row count {len(scan)} != {artifact['row_count']}"
        )
    if scan.file_sha256 != artifact["sha256"]:
        raise StrictCFAnalysisError("actual snapshot SHA-256 differs from manifest")
    return manifest, list(scan.rows), scan.file_sha256


def load_actual_run(
    run_dir: str | Path,
    *,
    project_root: str | Path = PROJECT,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]], str]:
    """Compatibility wrapper for the selected matched actual snapshot."""

    return load_actual_artifact(
        run_dir, artifact_name="actual_levels", project_root=project_root
    )


def canonical_actual_report_relative(
    cohort: str, requested: str | None = None
) -> str:
    """Return one of the two reserved analysis paths; reject every other path."""

    if cohort not in {"matched", "full_corpus"}:
        raise StrictCFAnalysisError("cohort must be 'matched' or 'full_corpus'")
    canonical = f"analysis/actual_only_{cohort}.json"
    if requested is not None and Path(requested).as_posix() != canonical:
        raise StrictCFAnalysisError(
            f"{cohort} report path is reserved as {canonical!r}; "
            "arbitrary run outputs are forbidden"
        )
    return canonical


def write_actual_only_report(
    run_dir: str | Path,
    *,
    cohort: str = "matched",
    output_relative: str | None = None,
    project_root: str | Path = PROJECT,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
) -> Path:
    """Write one exclusive cohort report without changing frozen artifacts."""

    canonical_output = canonical_actual_report_relative(cohort, output_relative)
    root = validate_run_dir(
        run_dir, project_root=project_root, must_exist=True
    )
    artifact_name = "actual_levels" if cohort == "matched" else "full_actual_levels"
    manifest, rows, actual_hash = load_actual_artifact(
        root, artifact_name=artifact_name, project_root=project_root
    )
    report = analyze_actual_rows(
        rows,
        require_full=cohort == "matched",
        require_matched=cohort == "matched",
        bootstrap_replicates=bootstrap_replicates,
    )
    report["cohort"] = cohort
    report["lineage"] = {
        "lineage_id": manifest["lineage_id"],
        "manifest_sha256": file_sha256(root / "manifest.json"),
        "actual_artifact": artifact_name,
        "actual_levels_sha256": actual_hash,
    }
    output = assert_path_within_run(root, canonical_output)
    if output.exists():
        raise StrictCFAnalysisError(f"refusing to replace existing report: {output}")
    result = storage.atomic_replace_json(output, report)
    if result.sha256 != file_sha256(output):
        output.unlink(missing_ok=True)
        raise StrictCFAnalysisError("written report hash verification failed")
    return output


def write_actual_only_reports(
    run_dir: str | Path,
    *,
    project_root: str | Path = PROJECT,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
) -> tuple[Path, Path]:
    """Write separate matched and full-corpus actual-only reports."""

    matched = write_actual_only_report(
        run_dir,
        cohort="matched",
        project_root=project_root,
        bootstrap_replicates=bootstrap_replicates,
    )
    full = write_actual_only_report(
        run_dir,
        cohort="full_corpus",
        project_root=project_root,
        bootstrap_replicates=bootstrap_replicates,
    )
    return matched, full


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--cohort",
        choices=("matched", "full_corpus", "both"),
        default="both",
    )
    parser.add_argument(
        "--output-relative",
        default=None,
        help="exclusive run-relative output (single-cohort mode only)",
    )
    parser.add_argument(
        "--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES
    )
    args = parser.parse_args(argv)
    if args.cohort == "both" and args.output_relative is not None:
        parser.error("--output-relative cannot be combined with --cohort=both")
    try:
        if args.cohort == "both":
            outputs = write_actual_only_reports(
                args.run_dir,
                bootstrap_replicates=args.bootstrap_replicates,
            )
        else:
            outputs = (
                write_actual_only_report(
                    args.run_dir,
                    cohort=args.cohort,
                    output_relative=args.output_relative,
                    bootstrap_replicates=args.bootstrap_replicates,
                ),
            )
    except (StrictCFAnalysisError, StrictCFSchemaError, storage.StorageError) as exc:
        parser.error(str(exc))
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
