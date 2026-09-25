"""Hash-bound postanalysis for the completed local CF3 experiment."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from experiment_baseline import cf3_local_core as core
from experiment_baseline import cf3_local_primitives as primitive


SCHEMA = "experiment_baseline.cf3_tiny_postanalysis"
VERSION = 1
LEVELS = tuple(primitive.LEVELS)
FEATURES = (
    "word_type_coverage",
    "word_token_coverage",
    "rouge_l_recall",
    "prompt_to_output_byte_ratio",
)


class PostanalysisError(RuntimeError):
    """Raised when completed CF3 evidence cannot be postanalyzed exactly."""


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    value = float(spearmanr(left, right).statistic)
    return value if np.isfinite(value) else None


def _load_rows(root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = manifest["artifacts"]["matched_cf3_rows.jsonl"]
    path = root / "matched_cf3_rows.jsonl"
    payload = path.read_bytes()
    if (
        len(payload) != metadata["size"]
        or primitive.sha256_bytes(payload) != metadata["sha256"]
        or not payload.endswith(b"\n")
    ):
        raise PostanalysisError("matched CF3 row artifact drift")
    rows = []
    seen: set[tuple[str, ...]] = set()
    for line_number, raw in enumerate(payload.splitlines(), 1):
        value = core._strict_json(raw, f"{path}:{line_number}")
        row = core.validate_scored_row(value, path=f"{path}:{line_number}")
        key = tuple(row["semantic_key"])
        if key in seen:
            raise PostanalysisError(f"duplicate scored row {key!r}")
        seen.add(key)
        rows.append(row)
    core._scored_item_groups(rows)
    return rows


def _value(row: Mapping[str, Any], estimand: str, feature: str | None) -> float:
    key = "actual" if estimand == "raw" else "shared_cf3_contrast"
    if feature is None:
        return float(row["blackbox"][key])
    return float(row["surface_features"][key][feature])


def _stratified(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("generation_model", "domain"):
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        result[field] = {}
        for name, group in sorted(groups.items()):
            report = {
                "model_items": len(group) // len(LEVELS),
                "level_rows": len(group),
                "estimands": {},
            }
            for estimand in ("raw", "shared_cf3_contrast"):
                by_feature = {}
                for feature in FEATURES:
                    by_level = {}
                    for level in LEVELS:
                        selected = [row for row in group if row["level"] == level]
                        by_level[level] = _spearman(
                            [_value(row, estimand, None) for row in selected],
                            [_value(row, estimand, feature) for row in selected],
                        )
                    values = [value for value in by_level.values() if value is not None]
                    by_feature[feature] = {
                        "within_level_spearman": by_level,
                        "macro_mean_within_level_spearman": (
                            float(statistics.fmean(values))
                            if len(values) == len(LEVELS)
                            else None
                        ),
                    }
                report["estimands"][estimand] = by_feature
            result[field][name] = report
    return result


def _slot_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    scopes = {"all": list(rows)}
    for model in sorted({str(row["generation_model"]) for row in rows}):
        scopes[model] = [row for row in rows if row["generation_model"] == model]
    for scope, values in scopes.items():
        by_level = {}
        for level in LEVELS:
            selected = [row for row in values if row["level"] == level]
            if not selected:
                raise PostanalysisError(f"scope {scope} has no rows at {level}")
            actual = float(
                statistics.fmean(row["blackbox"]["actual"] for row in selected)
            )
            slots = [
                float(
                    statistics.fmean(
                        row["blackbox"]["counterfactuals"][index]
                        for row in selected
                    )
                )
                for index in range(3)
            ]
            cf_mean = float(
                statistics.fmean(row["blackbox"]["cf_mean"] for row in selected)
            )
            contrast = float(
                statistics.fmean(
                    row["blackbox"]["shared_cf3_contrast"] for row in selected
                )
            )
            by_level[level] = {
                "n": len(selected),
                "actual_mean": actual,
                "cf_slot_means": slots,
                "cf_slot_range": max(slots) - min(slots),
                "cf_mean": cf_mean,
                "shared_cf3_contrast_mean": contrast,
                "arithmetic_residual": actual - cf_mean - contrast,
            }
        result[scope] = by_level
    return result


def build_postanalysis(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    manifest = core.validate_completed_output(root)
    rows = _load_rows(root, manifest)
    return {
        "schema": SCHEMA,
        "schema_version": VERSION,
        "created_at_utc": manifest["created_at_utc"],
        "input": {
            "output_manifest_path": str((root / "output_manifest.json").resolve()),
            "output_manifest_sha256": primitive.file_sha256(
                root / "output_manifest.json"
            ),
            "matched_rows_sha256": manifest["artifacts"][
                "matched_cf3_rows.jsonl"
            ]["sha256"],
            "execution_config_sha256": manifest["execution_config_sha256"],
            "cf3_protocol_sha256": manifest["cf3_protocol_sha256"],
        },
        "counts": {
            "level_rows": len(rows),
            "model_items": len(rows) // len(LEVELS),
            "source_clusters": len(
                {(row["domain"], row["source_text_sha256"]) for row in rows}
            ),
        },
        "features": list(FEATURES),
        "stratified_associations": _stratified(rows),
        "blackbox_cf_slot_diagnostics": _slot_diagnostics(rows),
        "interpretation": {
            "status": "exploratory-no-whitebox-criterion",
            "shared_control_warning": (
                "Both contrast axes subtract functions of the same three CF texts; "
                "association may include shared-control covariance."
            ),
            "selection_warning": (
                "The all-ready wave is completion-order imbalanced; use the separately "
                "published common-source balanced core as sensitivity evidence."
            ),
        },
    }


def _atomic_publish(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise PostanalysisError(f"refusing to overwrite differing artifact: {path}")
        return
    core._exclusive_write(path, payload)


def run(input_dir: Path, output_dir: Path) -> Path:
    if core._inside_active_run(input_dir) or core._inside_active_run(output_dir):
        raise PostanalysisError("postanalysis paths must be outside strict-CF runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = build_postanalysis(input_dir)
    result_payload = primitive.canonical_jsonl_row_bytes(result)
    _atomic_publish(output_dir / "postanalysis.json", result_payload)
    manifest = {
        "schema": f"{SCHEMA}.manifest",
        "schema_version": VERSION,
        "state": "complete",
        "created_at_utc": result["created_at_utc"],
        "input_output_manifest_sha256": result["input"]["output_manifest_sha256"],
        "postanalysis": {
            "path": "postanalysis.json",
            "sha256": primitive.sha256_bytes(result_payload),
            "size": len(result_payload),
        },
        "code": {
            "path": str(Path(__file__).resolve()),
            "sha256": primitive.file_sha256(Path(__file__)),
            "size": Path(__file__).stat().st_size,
        },
    }
    manifest_path = output_dir / "manifest.json"
    _atomic_publish(manifest_path, primitive.canonical_jsonl_row_bytes(manifest))
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = run(args.input_dir, args.output_dir)
    print(f"CF3 postanalysis complete: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
