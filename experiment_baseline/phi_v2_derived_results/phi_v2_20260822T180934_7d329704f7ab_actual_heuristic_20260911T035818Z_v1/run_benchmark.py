# -*- coding: utf-8 -*-
"""Build the hash-bound, paper-final actual-pair heuristic benchmark.

Phases are restartable and manifest-last: ``run`` creates features/statistics,
``audit_benchmark.py`` independently writes audit.json, and ``finalize``
publishes manifest.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import numpy as np

import benchmark_core as core

BUNDLE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUNDLE_DIR.parents[2]
BASELINE = PROJECT_ROOT / "experiment_baseline"
CANONICAL = BASELINE / "v2" / "run_20260823_canonical"
MIGRATION_ID = "phi_v2_20260822T180934_7d329704f7ab"
BUNDLE_ID = f"{MIGRATION_ID}_actual_heuristic_20260911T035818Z_v1"
EXPECTED_BUNDLE = BASELINE / "phi_v2_derived_results" / BUNDLE_ID
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260823
EXPECTED_ITEMS = 11222
EXPECTED_PAIRS = 56110
EXPECTED_CLUSTERS = 2551
EXPECTED_MODEL_COUNTS = {
    "claude-opus-4-8": 1892,
    "claude-sonnet-5": 2320,
    "gemini-3.6-flash": 2240,
    "gpt-5.5": 2446,
    "gpt-5.6-sol": 2324,
}
EXPECTED_DOMAIN_COUNTS = {"arxiv": 2937, "news": 2856, "patent": 2760, "poetry": 2669}
EXPECTED_INPUTS = {
    "active_pointer": (
        "experiment_baseline/ACTIVE_PHI_V2.json",
        "8e17b22a30a80e25a8548561931928930019a4610b7edbdc1dbcad7ee2ba8dee",
    ),
    "lineage": (
        "experiment_baseline/v2/run_20260823_canonical/final/lineage.json",
        "c6d0b0410ee2a51a01d3b6cba88671a9d86075cc121b39f2ddbd6e1915fae7c1",
    ),
    "sources": (
        "experiment_baseline/v2/run_20260823_canonical/sources.jsonl",
        "d545faaf72cd5c35053c056e93cc3ea19827ccb4cca3d422d4cb351339d0dafd",
    ),
    "scores_llama": (
        "experiment_baseline/v2/run_20260823_canonical/final/phi_llama.v2.jsonl",
        "7efc006e6b68b6375f65917a8337ce6ddf9b09e45ec577966aec70dd483ec5e6",
    ),
    "scores_mixtral": (
        "experiment_baseline/v2/run_20260823_canonical/final/phi_mixtral.v2.jsonl",
        "8c52b2d5e8eb21263c34088b80c1e14afd5831201d020dda8dcb9c2850fbe865",
    ),
    "raw_authority_analysis": (
        "experiment_baseline/phi_v2_derived_results/phi_v2_20260822T180934_7d329704f7ab_raw_raw_20260910T100648Z_v1/analysis.json",
        "aac49d41156fe6b34520d955936c2b1c48440da90e7b590613d1b50f15657ea1",
    ),
    "raw_authority_manifest": (
        "experiment_baseline/phi_v2_derived_results/phi_v2_20260822T180934_7d329704f7ab_raw_raw_20260910T100648Z_v1/manifest.json",
        "40ff089f5d4fa0c8aa635bb36ca586c38a7c09a6527a2f55979f21e4528946a4",
    ),
    "pilot_output_manifest": (
        "experiment_baseline/v2/run_20260823_canonical/heuristic_pilot_large/output_manifest.json",
        "54530567d93fc7c47d67b68dda1b94abcb52116c6b9570f1f82309c0ebce5e94",
    ),
    "pilot_summary": (
        "experiment_baseline/v2/run_20260823_canonical/heuristic_pilot_large/summary.json",
        "afcce3807943a0adcdddaf19aab2f95f62319d494a4d3c3a7f3106b88a6c20fb",
    ),
    "pilot_features": (
        "experiment_baseline/v2/run_20260823_canonical/heuristic_pilot_large/pair_features.csv",
        "42dbac90dba5c602fe846dbfb9136f7a0af04efd48eb1123d7b3d86fe39b1d84",
    ),
}
EXPECTED_LINEAGE_PAYLOAD_SHA = "f0e914d08492e88005e3c3e6df7e0abb359fefd4d501a45b7093736db8487d14"
EXPECTED_BLACKBOX_SET_SHA = "a72f3a83d449ca747a85469b869ca5874b3e6a8959d93e2dce5d5b9172f44edd"
EXPECTED_PILOT_SAMPLE_SHA = "1393aab0096a1094ac321752063ab8874db81909c99866a316b29d362b6cd6e3"
EXPECTED_PILOT_SCRIPT_SHA = "3f5a17ae122a1a61278fbf5b05e008b240eb0958473222f2cf895a67c7ca98ca"
FEATURE_LEDGER = BUNDLE_DIR / "actual_pair_features.jsonl"
FEATURE_LEDGER_RECEIPT = BUNDLE_DIR / "feature_ledger_receipt.json"
FEATURE_CHECKPOINT = BUNDLE_DIR / "feature_checkpoint.jsonl"
BOOTSTRAP_CHECKPOINT = BUNDLE_DIR / "bootstrap_checkpoint.npz"
SCIENTIFIC_COMPLETION = BUNDLE_DIR / "scientific_completion.json"
TABLE_FILES = (
    "table1_direct.md", "table2_llama.md", "table3_mixtral.md",
    "table4_paired_differences.md", "table5_joint_reference.md",
    "table6_subgroups.md",
)
APPENDIX_FILES = (
    "appendix_per_level.md", "appendix_auxiliary_alpha.md",
    "appendix_ties_undefined.md", "appendix_feature_definitions.md",
)
SCIENTIFIC_FILES = (
    "feature_protocol.json", "run_config.json", "actual_pair_features.jsonl",
    "feature_ledger_receipt.json", "bootstrap_checkpoint.npz",
    "bootstrap_summary.json", "metrics.json", "metrics.csv", *TABLE_FILES,
    *APPENDIX_FILES, "REPORT_ZH.md", "execution.json",
)
AUDIT_BOUND_FILES = (
# NOTE (release): the word-receipt subsystem and `update_word.py` were
# removed for de-identification -- that helper carried a machine-specific
# DOCX path.  It plays no part in the benchmark's own reproducibility.
    "benchmark_core.py", "run_benchmark.py", "audit_benchmark.py",
    "test_benchmark.py", "RUNBOOK.md", *SCIENTIFIC_FILES,
    "scientific_completion.json",
)


def _path(role: str) -> Path:
    return PROJECT_ROOT / EXPECTED_INPUTS[role][0]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise core.BenchmarkError(f"invalid JSON input: {path}") from exc


def _canonical_row_sha(row: Mapping[str, Any]) -> str:
    return core.sha256_bytes(core.canonical_json_bytes(row))


def _lower_priority() -> str:
    if os.name == "nt":
        try:
            import ctypes
            if ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000
            ):
                return "windows-below-normal"
        except (AttributeError, OSError):
            pass
        return "windows-default"
    try:
        os.nice(5)
        return "posix-nice+5"
    except OSError:
        return "posix-default"


def verify_bundle_path() -> None:
    if BUNDLE_DIR.resolve() != EXPECTED_BUNDLE.resolve():
        raise core.BenchmarkError(f"script is outside the fixed isolated bundle: {BUNDLE_DIR}")
    for parent in (BASELINE / "phi_v2_derived_results", BUNDLE_DIR):
        if parent.is_symlink():
            raise core.BenchmarkError(f"reparse/symlink output path forbidden: {parent}")


def snapshot_inputs() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for role, (relative, expected) in EXPECTED_INPUTS.items():
        path = PROJECT_ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise core.BenchmarkError(f"bound input missing or linked: {path}")
        actual = core.sha256_file(path)
        if actual != expected:
            raise core.BenchmarkError(f"{role} hash drift: {actual} != {expected}")
        result[role] = {"path": relative, "sha256": actual, "size": path.stat().st_size}
    return result


def validate_authorities() -> tuple[Mapping[str, Any], dict[tuple[str, str, str], dict[str, str]], dict[str, dict[tuple[str, str, str], dict[str, str]]]]:
    pointer = _load_json(_path("active_pointer"))
    if (
        pointer.get("migration_id") != MIGRATION_ID
        or pointer.get("lineage_sha256") != EXPECTED_INPUTS["lineage"][1]
        or pointer.get("publication_eligible") is not True
        or Path(pointer.get("lineage_path", "")).resolve() != _path("lineage").resolve()
    ):
        raise core.BenchmarkError("active pointer does not select the frozen publication lineage")
    lineage = _load_json(_path("lineage"))
    payload = dict(lineage)
    stored_payload_hash = payload.pop("lineage_payload_sha256", None)
    if stored_payload_hash != EXPECTED_LINEAGE_PAYLOAD_SHA or _canonical_row_sha(payload) != stored_payload_hash:
        raise core.BenchmarkError("lineage payload identity differs")
    if lineage.get("migration_id") != MIGRATION_ID or lineage.get("publication_eligible") is not True:
        raise core.BenchmarkError("lineage is not the required publication migration")

    source_entries: dict[tuple[str, str, str], dict[str, str]] = {}
    for entry in lineage.get("source", {}).get("entries", []):
        key = tuple(entry.get("semantic_key", ()))
        if len(key) != 3 or key in source_entries:
            raise core.BenchmarkError("lineage source entries are invalid or duplicated")
        source_entries[key] = {
            "scoring_input_sha256": core.require_sha256(entry.get("scoring_input_sha256"), "lineage source input hash"),
            "row_sha256": core.require_sha256(entry.get("row_sha256"), "lineage source row hash"),
            "debug_file_sha256": core.require_sha256(entry.get("debug_file_sha256"), "lineage debug hash"),
        }
    if len(source_entries) != EXPECTED_ITEMS:
        raise core.CoverageError("lineage source entry count differs")

    score_entries: dict[str, dict[tuple[str, str, str], dict[str, str]]] = {}
    for evaluator in core.EVALUATORS:
        by_key: dict[tuple[str, str, str], dict[str, str]] = {}
        block = lineage.get("scores", {}).get(evaluator, {})
        for entry in block.get("entries", []):
            key = tuple(entry.get("semantic_key", ()))
            if len(key) != 3 or key in by_key:
                raise core.BenchmarkError(f"lineage {evaluator} score entries invalid")
            by_key[key] = {
                "scoring_input_sha256": core.require_sha256(entry.get("scoring_input_sha256"), "score input hash"),
                "row_sha256": core.require_sha256(entry.get("row_sha256"), "score row hash"),
            }
        if len(by_key) != EXPECTED_ITEMS:
            raise core.CoverageError(f"lineage {evaluator} score count differs")
        score_entries[evaluator] = by_key

    raw_analysis = _load_json(_path("raw_authority_analysis"))
    raw_manifest = _load_json(_path("raw_authority_manifest"))
    coverage = raw_analysis.get("coverage", {})
    if (
        coverage.get("items_per_evaluator") != EXPECTED_ITEMS
        or coverage.get("item_level_pairs_per_evaluator") != EXPECTED_PAIRS
        or coverage.get("source_clusters") != EXPECTED_CLUSTERS
        or raw_manifest.get("state") != "complete"
    ):
        raise core.BenchmarkError("frozen raw authority coverage/state differs")
    return lineage, source_entries, score_entries


def load_actual_scores(
    evaluator: str,
    lineage_entries: Mapping[tuple[str, str, str], Mapping[str, str]],
) -> dict[tuple[str, str, str], tuple[str, tuple[float, ...]]]:
    path = _path(f"scores_{evaluator}")
    result: dict[tuple[str, str, str], tuple[str, tuple[float, ...]]] = {}
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                raise core.CoverageError(f"{path}:{line_number}: blank row")
            row = json.loads(raw)
            if not isinstance(row, Mapping):
                raise core.CoverageError(f"{path}:{line_number}: row is not an object")
            key = core.semantic_key(row)
            if key in result:
                raise core.CoverageError(f"{path}:{line_number}: duplicate key {key}")
            expected = lineage_entries.get(key)
            if expected is None or _canonical_row_sha(row) != expected["row_sha256"]:
                raise core.CoverageError(f"{evaluator} score row lineage mismatch: {key}")
            scoring_hash = core.require_sha256(row.get("scoring_input_sha256"), "score scoring hash")
            if scoring_hash != expected["scoring_input_sha256"] or row.get("evaluator") != evaluator:
                raise core.CoverageError(f"{evaluator} score identity mismatch: {key}")
            levels = row.get("levels")
            if not isinstance(levels, Mapping) or set(levels) != set(core.LEVELS):
                raise core.CoverageError(f"{evaluator} score levels differ: {key}")
            # Positive numeric allowlist: only levels.<L>.phi is extracted.
            values = tuple(
                core.finite_float(levels[level].get("phi"), f"{evaluator}.{key}.{level}.phi")
                for level in core.LEVELS
            )
            result[key] = (scoring_hash, values)
    if len(result) != EXPECTED_ITEMS or set(result) != set(lineage_entries):
        raise core.CoverageError(f"{evaluator} score coverage differs")
    return result


def validate_pilot_cache() -> tuple[
    dict[tuple[str, str, str], str],
    dict[tuple[str, str, str, str], dict[str, float]],
    dict[str, Any],
]:
    root = CANONICAL / "heuristic_pilot_large"
    output = _load_json(root / "output_manifest.json")
    if output.get("state") != "complete" or output.get("lineage_sha256") != EXPECTED_INPUTS["lineage"][1]:
        raise core.BenchmarkError("historical feature cache is not complete/lineage-bound")
    bound_outputs = output.get("outputs", {})
    for name, expected in (
        ("pair_features.csv", EXPECTED_INPUTS["pilot_features"][1]),
        ("sample_manifest.json", EXPECTED_PILOT_SAMPLE_SHA),
    ):
        record = bound_outputs.get(name, {})
        path = root / name
        if record.get("sha256") != expected or core.sha256_file(path) != expected:
            raise core.BenchmarkError(f"historical cache binding differs: {name}")
    run_config_path = root / "run_config.json"
    if core.sha256_file(run_config_path) != bound_outputs.get("run_config.json", {}).get("sha256"):
        raise core.BenchmarkError("historical cache run config hash differs")
    run_config = _load_json(run_config_path)
    old_script = BASELINE / "heuristic_overlap_pilot.py"
    if (
        run_config.get("feature_protocol_version") != 1
        or run_config.get("lineage_sha256") != EXPECTED_INPUTS["lineage"][1]
        or run_config.get("script_sha256") != EXPECTED_PILOT_SCRIPT_SHA
        or core.sha256_file(old_script) != EXPECTED_PILOT_SCRIPT_SHA
    ):
        raise core.BenchmarkError("historical cache feature implementation differs")
    sample = _load_json(root / "sample_manifest.json")
    if sample.get("lineage_sha256") != EXPECTED_INPUTS["lineage"][1]:
        raise core.BenchmarkError("historical cache sample lineage differs")
    counts = sample.get("counts", {})
    if counts.get("items") != 8060 or counts.get("level_pairs") != 40300 or counts.get("source_clusters") != 1612:
        raise core.CoverageError("historical cache sample counts differ")
    sample_hashes: dict[tuple[str, str, str], str] = {}
    for entry in sample.get("items", []):
        key = tuple(entry.get("semantic_key", ()))
        if len(key) != 3 or key in sample_hashes:
            raise core.CoverageError("historical sample keys invalid")
        sample_hashes[key] = core.require_sha256(entry.get("scoring_input_sha256"), "pilot sample input hash")
    if len(sample_hashes) != 8060:
        raise core.CoverageError("historical sample item coverage differs")

    feature_cache: dict[tuple[str, str, str, str], dict[str, float]] = {}
    with (root / "pair_features.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"generation_model", "domain", "id", "level", *core.FEATURES}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise core.CoverageError("historical feature CSV lacks required actual feature fields")
        for line_number, row in enumerate(reader, 2):
            key3 = core.normalize_semantic_key(row["generation_model"], row["domain"], row["id"])
            level = row["level"]
            key = (*key3, level)
            if level not in core.LEVELS or key in feature_cache:
                raise core.CoverageError(f"historical feature duplicate/level error at line {line_number}")
            # The mixed cache is accessed only through this feature allowlist.
            feature_cache[key] = {
                name: core.finite_float(float(row[name]), f"pilot feature {name}")
                for name in core.FEATURES
            }
    if len(feature_cache) != 40300 or {key[:3] for key in feature_cache} != set(sample_hashes):
        raise core.CoverageError("historical feature cache coverage differs")
    return sample_hashes, feature_cache, {
        "cache_items": 8060,
        "cache_pairs": 40300,
        "sample_manifest_sha256": EXPECTED_PILOT_SAMPLE_SHA,
        "pair_features_sha256": EXPECTED_INPUTS["pilot_features"][1],
        "feature_script_sha256": EXPECTED_PILOT_SCRIPT_SHA,
    }


def _load_feature_checkpoint() -> dict[tuple[str, str, str], Mapping[str, Any]]:
    if not FEATURE_CHECKPOINT.exists():
        return {}
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    valid_end = 0
    with FEATURE_CHECKPOINT.open("rb") as handle:
        while True:
            raw = handle.readline()
            if not raw:
                break
            try:
                record = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                break
            key = tuple(record.get("semantic_key", ()))
            if len(key) != 3 or key in result or len(record.get("rows", [])) != 5:
                raise core.CoverageError("feature checkpoint contains invalid/duplicate item")
            stored_record_hash = record.get("record_sha256")
            payload = dict(record)
            payload.pop("record_sha256", None)
            if (
                not isinstance(stored_record_hash, str)
                or core.sha256_bytes(core.canonical_json_bytes(payload)) != stored_record_hash
            ):
                raise core.CoverageError("feature checkpoint record hash differs")
            result[key] = record
            valid_end = handle.tell()
    if FEATURE_CHECKPOINT.stat().st_size != valid_end:
        with FEATURE_CHECKPOINT.open("r+b") as handle:
            handle.truncate(valid_end)
            handle.flush()
            os.fsync(handle.fileno())
    return result


def _debug_cluster_candidate(debug: Mapping[str, Any], key: tuple[str, str, str]) -> tuple[str, str] | None:
    metadata = debug.get("source")
    if not isinstance(metadata, Mapping):
        return None
    source_id = unicodedata.normalize("NFC", str(metadata.get("source_id", "")).strip())
    text_hash = metadata.get("text_sha256")
    if not source_id:
        raise core.CoverageError(f"debug source_id empty: {key}")
    return source_id, core.require_sha256(text_hash, "debug source text hash")


def _debug_actual(
    source: Mapping[str, Any],
    key: tuple[str, str, str],
    expected_debug_hash: str,
) -> tuple[tuple[float, ...], tuple[str, str] | None, str]:
    declared = source.get("source_file")
    if not isinstance(declared, str) or not declared:
        raise core.CoverageError(f"source file path missing: {key}")
    path = Path(declared)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise core.CoverageError(f"debug path escapes project: {path}") from exc
    if path.is_symlink() or not path.is_file():
        raise core.CoverageError(f"debug path missing/linked: {path}")
    digest = core.sha256_file(path)
    if digest != expected_debug_hash:
        raise core.CoverageError(f"debug hash drift: {key}")
    debug = _load_json(path)
    if core.semantic_key(debug) != key:
        raise core.CoverageError(f"debug semantic key differs: {key}")
    prompts = debug.get("prompts")
    outputs = debug.get("outputs")
    metrics = debug.get("level_metrics")
    if not all(isinstance(value, Mapping) for value in (prompts, outputs, metrics)):
        raise core.CoverageError(f"debug actual fields missing: {key}")
    values = []
    for level in core.LEVELS:
        pair = source["levels"][level]
        if prompts.get(level) != pair["prompt"] or outputs.get(level) != pair["output"]:
            raise core.CoverageError(f"debug/source actual text mismatch: {key}/{level}")
        entry = metrics.get(level)
        if not isinstance(entry, Mapping):
            raise core.CoverageError(f"debug actual metric missing: {key}/{level}")
        # Positive numeric allowlist: only aggregate actual_ratio is extracted.
        values.append(core.finite_float(entry.get("actual_ratio"), f"debug.{key}.{level}.actual_ratio"))
    return tuple(values), _debug_cluster_candidate(debug, key), digest


def _source_levels(source: Mapping[str, Any], key: tuple[str, str, str]) -> Mapping[str, Mapping[str, str]]:
    levels = source.get("levels")
    if not isinstance(levels, Mapping) or set(levels) != set(core.LEVELS):
        raise core.CoverageError(f"source levels differ: {key}")
    result: dict[str, Mapping[str, str]] = {}
    for level in core.LEVELS:
        entry = levels[level]
        if not isinstance(entry, Mapping) or set(entry) != {"prompt", "output"}:
            raise core.CoverageError(f"source actual pair schema differs: {key}/{level}")
        if not isinstance(entry["prompt"], str) or not isinstance(entry["output"], str):
            raise core.CoverageError(f"source actual pair is not text: {key}/{level}")
        if not entry["prompt"].strip() or not entry["output"].strip():
            raise core.CoverageError(f"source actual pair is empty: {key}/{level}")
        result[level] = entry
    return result


def _audit_pair_keys(feature_cache: Mapping[tuple[str, str, str, str], Any], n: int = 64) -> set[tuple[str, str, str, str]]:
    return set(sorted(feature_cache, key=lambda key: (core.sha256_bytes("\0".join(key).encode("utf-8")), key))[:n])


def _exact_feature_equal(expected: Mapping[str, float], actual: Mapping[str, float]) -> bool:
    return all(float(expected[name]).hex() == float(actual[name]).hex() for name in core.FEATURES)


def _ledger_receipt(
    rows: Sequence[Mapping[str, Any]], dataset: Mapping[str, Any], config_sha256: str
) -> dict[str, Any]:
    model_counts = Counter(core.semantic_key(row)[0] for row in rows[::5])
    domain_counts = Counter(core.semantic_key(row)[1] for row in rows[::5])
    return {
        "schema": "actual_heuristic.feature_ledger_receipt",
        "schema_version": 1,
        "state": "complete",
        "config_sha256": config_sha256,
        "feature_protocol_sha256": core.sha256_bytes(
            core.canonical_json_bytes(core.feature_protocol())
        ),
        "ledger_sha256": core.sha256_file(FEATURE_LEDGER),
        "items": len(rows) // len(core.LEVELS),
        "pairs": len(rows),
        "source_clusters": len(dataset["clusters"]),
        "pair_set_sha256": dataset["pair_set_sha256"],
        "generation_model_items": dict(sorted(model_counts.items())),
        "domain_items": dict(sorted(domain_counts.items())),
    }


def _verify_ledger_receipt(config_sha256: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not FEATURE_LEDGER.is_file() or not FEATURE_LEDGER_RECEIPT.is_file():
        raise core.BenchmarkError("complete feature ledger/receipt pair is missing")
    receipt = _load_json(FEATURE_LEDGER_RECEIPT)
    rows = core.load_feature_rows(FEATURE_LEDGER)
    dataset = core.dataset_arrays(rows)
    expected = _ledger_receipt(rows, dataset, config_sha256)
    if receipt != expected:
        raise core.BenchmarkError("feature ledger receipt or authority binding differs")
    if (
        receipt["items"] != EXPECTED_ITEMS
        or receipt["pairs"] != EXPECTED_PAIRS
        or receipt["source_clusters"] != EXPECTED_CLUSTERS
        or receipt["generation_model_items"] != EXPECTED_MODEL_COUNTS
        or receipt["domain_items"] != EXPECTED_DOMAIN_COUNTS
    ):
        raise core.CoverageError("feature ledger receipt coverage differs")
    return rows, dataset


def build_feature_ledger(
    source_entries: Mapping[tuple[str, str, str], Mapping[str, str]],
    llama: Mapping[tuple[str, str, str], tuple[str, tuple[float, ...]]],
    mixtral: Mapping[tuple[str, str, str], tuple[str, tuple[float, ...]]],
    pilot_hashes: Mapping[tuple[str, str, str], str],
    feature_cache: Mapping[tuple[str, str, str, str], Mapping[str, float]],
    config_sha256: str,
) -> dict[str, Any]:
    if FEATURE_LEDGER.exists() and FEATURE_LEDGER_RECEIPT.exists():
        rows, arrays = _verify_ledger_receipt(config_sha256)
        return {
            "state": "reused_receipt_bound_ledger",
            "items": len(rows) // 5,
            "pairs": len(rows),
            "source_clusters": len(arrays["clusters"]),
            "pair_set_sha256": arrays["pair_set_sha256"],
            "ledger_sha256": core.sha256_file(FEATURE_LEDGER),
            "receipt_sha256": core.sha256_file(FEATURE_LEDGER_RECEIPT),
        }
    if FEATURE_LEDGER.exists():
        # A ledger without its manifest-last receipt is an interrupted projection,
        # never a completion sentinel.  Rebuild it from the durable item journal.
        FEATURE_LEDGER.unlink()
    if FEATURE_LEDGER_RECEIPT.exists():
        raise core.BenchmarkError("orphaned feature ledger receipt")

    checkpoint = _load_feature_checkpoint()
    audit_pairs = _audit_pair_keys(feature_cache)
    source_seen: set[tuple[str, str, str]] = set()
    debug_inventory: list[dict[str, Any]] = []
    model_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    cache_audited = 0
    computed_pairs = 0
    reused_pairs = 0
    source_path = _path("sources")
    with FEATURE_CHECKPOINT.open("ab") as checkpoint_handle, source_path.open("rb") as source_handle:
        for line_number, raw in enumerate(source_handle, 1):
            source = json.loads(raw)
            if not isinstance(source, Mapping):
                raise core.CoverageError(f"source line {line_number} is not an object")
            key = core.semantic_key(source)
            if key in source_seen:
                raise core.CoverageError(f"duplicate source key: {key}")
            source_seen.add(key)
            expected = source_entries.get(key)
            if expected is None:
                raise core.CoverageError(f"source not in lineage: {key}")
            scoring_hash = core.require_sha256(source.get("scoring_input_sha256"), "source scoring hash")
            if (
                scoring_hash != expected["scoring_input_sha256"]
                or _canonical_row_sha(source) != expected["row_sha256"]
            ):
                raise core.CoverageError(f"source lineage mismatch: {key}")
            levels = _source_levels(source, key)
            if llama[key][0] != scoring_hash or mixtral[key][0] != scoring_hash:
                raise core.CoverageError(f"score/source input hash mismatch: {key}")
            if key in pilot_hashes and pilot_hashes[key] != scoring_hash:
                raise core.CoverageError(f"pilot cache/source input hash mismatch: {key}")
            actual, cluster_candidate, debug_hash = _debug_actual(
                source, key, expected["debug_file_sha256"]
            )
            debug_inventory.append({
                "semantic_key": list(key),
                "source_file": source["source_file"],
                "sha256": debug_hash,
            })
            model_counts[key[0]] += 1
            domain_counts[key[1]] += 1
            existing = checkpoint.get(key)
            if existing is not None:
                if existing.get("scoring_input_sha256") != scoring_hash:
                    raise core.CoverageError(f"checkpoint input hash mismatch: {key}")
                existing_by_level = {
                    row.get("level"): row for row in existing.get("rows", [])
                }
                if set(existing_by_level) != set(core.LEVELS):
                    raise core.CoverageError(f"checkpoint levels differ: {key}")
                for level_index, level in enumerate(core.LEVELS):
                    existing_row = existing_by_level[level]
                    pair = levels[level]
                    expected_scalars = (
                        ("blackbox_actual_ratio", actual[level_index]),
                        ("phi_actual_llama", llama[key][1][level_index]),
                        ("phi_actual_mixtral", mixtral[key][1][level_index]),
                    )
                    if any(
                        float(existing_row.get(name)).hex() != float(expected_value).hex()
                        for name, expected_value in expected_scalars
                    ):
                        raise core.CoverageError(
                            f"checkpoint authority score mismatch: {key}/{level}"
                        )
                    if (
                        existing_row.get("prompt_sha256")
                        != core.sha256_bytes(pair["prompt"].encode("utf-8"))
                        or existing_row.get("output_sha256")
                        != core.sha256_bytes(pair["output"].encode("utf-8"))
                    ):
                        raise core.CoverageError(
                            f"checkpoint actual text hash mismatch: {key}/{level}"
                        )
                    cache_key = (*key, level)
                    if cache_key in audit_pairs:
                        recomputed = core.compute_surface_features(
                            pair["prompt"], pair["output"]
                        )
                        if not _exact_feature_equal(existing_by_level[level], recomputed):
                            raise core.BenchmarkError(
                                f"resumed cache feature parity failed: {cache_key}"
                            )
                        cache_audited += 1
                continue
            item_rows = []
            for level_index, level in enumerate(core.LEVELS):
                pair = levels[level]
                cache_key = (*key, level)
                cached = feature_cache.get(cache_key)
                if cached is None:
                    features = core.compute_surface_features(pair["prompt"], pair["output"])
                    computed_pairs += 1
                else:
                    features = dict(cached)
                    reused_pairs += 1
                    if cache_key in audit_pairs:
                        recomputed = core.compute_surface_features(pair["prompt"], pair["output"])
                        if not _exact_feature_equal(features, recomputed):
                            raise core.BenchmarkError(f"historical cache feature parity failed: {cache_key}")
                        cache_audited += 1
                row = {
                    "generation_model": key[0],
                    "domain": key[1],
                    "id": key[2],
                    "level": level,
                    "scoring_input_sha256": scoring_hash,
                    "prompt_sha256": core.sha256_bytes(pair["prompt"].encode("utf-8")),
                    "output_sha256": core.sha256_bytes(pair["output"].encode("utf-8")),
                    "cluster_source_id_candidate": cluster_candidate[0] if cluster_candidate else None,
                    "cluster_fingerprint_candidate": cluster_candidate[1] if cluster_candidate else None,
                    "blackbox_actual_ratio": actual[level_index],
                    "phi_actual_llama": llama[key][1][level_index],
                    "phi_actual_mixtral": mixtral[key][1][level_index],
                    **features,
                }
                item_rows.append(row)
            record = {
                "semantic_key": list(key),
                "scoring_input_sha256": scoring_hash,
                "rows": item_rows,
            }
            record["record_sha256"] = core.sha256_bytes(
                core.canonical_json_bytes(record)
            )
            payload = core.canonical_json_bytes(record, newline=True)
            checkpoint_handle.write(payload)
            checkpoint_handle.flush()
            if line_number % 10 == 0:
                os.fsync(checkpoint_handle.fileno())
            checkpoint[key] = record
            if len(checkpoint) % 100 == 0:
                print(f"features {len(checkpoint)}/{EXPECTED_ITEMS}", flush=True)
        checkpoint_handle.flush()
        os.fsync(checkpoint_handle.fileno())

    if set(source_seen) != set(source_entries) or len(checkpoint) != EXPECTED_ITEMS:
        raise core.CoverageError("source/checkpoint complete coverage failed")
    if dict(model_counts) != EXPECTED_MODEL_COUNTS or dict(domain_counts) != EXPECTED_DOMAIN_COUNTS:
        raise core.CoverageError("source model/domain partitions differ")
    debug_inventory.sort(key=lambda entry: tuple(entry["semantic_key"]))
    if core.sha256_bytes(core.canonical_json_bytes(debug_inventory)) != EXPECTED_BLACKBOX_SET_SHA:
        raise core.CoverageError("debug artifact-set identity differs")
    if cache_audited != len(audit_pairs):
        raise core.CoverageError("historical cache parity sample coverage differs")

    metadata_by_alias: dict[tuple[str, str], tuple[str, str]] = {}
    for key, record in checkpoint.items():
        first = record["rows"][0]
        source_id = first["cluster_source_id_candidate"]
        fingerprint = first["cluster_fingerprint_candidate"]
        if source_id is None:
            continue
        alias = (key[1], key[2])
        candidate = (source_id, fingerprint)
        previous = metadata_by_alias.get(alias)
        if previous is not None and previous != candidate:
            raise core.CoverageError(f"conflicting source metadata: {alias}")
        metadata_by_alias[alias] = candidate

    flattened: list[dict[str, Any]] = []
    for key in sorted(checkpoint):
        record = checkpoint[key]
        rows = record["rows"]
        if [row["level"] for row in rows] != list(core.LEVELS):
            raise core.CoverageError(f"checkpoint levels differ: {key}")
        first = rows[0]
        candidate = (
            (first["cluster_source_id_candidate"], first["cluster_fingerprint_candidate"])
            if first["cluster_source_id_candidate"] is not None
            else metadata_by_alias.get((key[1], key[2]), (key[2], "legacy-id-fallback"))
        )
        for raw_row in rows:
            row = {
                name: value
                for name, value in raw_row.items()
                if name not in {"cluster_source_id_candidate", "cluster_fingerprint_candidate"}
            }
            row["source_cluster_domain"] = key[1]
            row["source_cluster_id"] = candidate[0]
            row["source_cluster_fingerprint"] = candidate[1]
            ordered = {
                "generation_model": row["generation_model"],
                "domain": row["domain"],
                "id": row["id"],
                "level": row["level"],
                "scoring_input_sha256": row["scoring_input_sha256"],
                "prompt_sha256": row["prompt_sha256"],
                "output_sha256": row["output_sha256"],
                "source_cluster_domain": row["source_cluster_domain"],
                "source_cluster_id": row["source_cluster_id"],
                "source_cluster_fingerprint": row["source_cluster_fingerprint"],
                "blackbox_actual_ratio": row["blackbox_actual_ratio"],
                **{name: row[name] for name in core.FEATURES},
                "phi_actual_llama": row["phi_actual_llama"],
                "phi_actual_mixtral": row["phi_actual_mixtral"],
            }
            flattened.append(ordered)
    arrays = core.dataset_arrays(flattened)
    if len(arrays["clusters"]) != EXPECTED_CLUSTERS:
        raise core.CoverageError(f"source cluster count {len(arrays['clusters'])} != {EXPECTED_CLUSTERS}")
    payload = b"".join(core.canonical_json_bytes(row, newline=True) for row in flattened)
    core.atomic_write_bytes(FEATURE_LEDGER, payload)
    receipt = _ledger_receipt(flattened, arrays, config_sha256)
    core.atomic_write_json(FEATURE_LEDGER_RECEIPT, receipt)
    return {
        "state": "complete",
        "items": EXPECTED_ITEMS,
        "pairs": EXPECTED_PAIRS,
        "source_clusters": EXPECTED_CLUSTERS,
        "pair_set_sha256": arrays["pair_set_sha256"],
        "ledger_sha256": core.sha256_bytes(payload),
        "receipt_sha256": core.sha256_file(FEATURE_LEDGER_RECEIPT),
        "cache_reused_pairs": len(feature_cache),
        "locally_computed_pairs": EXPECTED_PAIRS - len(feature_cache),
        "cache_exact_parity_pairs": cache_audited,
        "debug_artifact_set_sha256": EXPECTED_BLACKBOX_SET_SHA,
    }


def _keep_bootstrap_key(key: str) -> bool:
    if not key.startswith("subgroup|"):
        return True
    parts = key.split("|")
    return "macro_within_level" in parts and parts[-1] in {"rho", "alpha_z"} and "joint" not in parts


def _replicate_seed(replicate: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{BOOTSTRAP_SEED}\0{replicate}".encode("ascii")).digest()[:8], "big"
    )


def _load_bootstrap_checkpoint(keys: Sequence[str], config_sha256: str) -> tuple[np.ndarray, np.ndarray, int]:
    shape = (BOOTSTRAP_REPLICATES, len(keys))
    values = np.full(shape, np.nan, dtype=np.float64)
    effective = np.zeros(shape, dtype=np.int32)
    if not BOOTSTRAP_CHECKPOINT.exists():
        return values, effective, 0
    with np.load(BOOTSTRAP_CHECKPOINT, allow_pickle=False) as stored:
        if str(stored["config_sha256"].item()) != config_sha256:
            raise core.BenchmarkError("bootstrap checkpoint config differs")
        stored_keys = [str(value) for value in stored["keys"]]
        if stored_keys != list(keys):
            raise core.BenchmarkError("bootstrap checkpoint metric inventory differs")
        completed = int(stored["completed"].item())
        old_values = stored["values"]
        old_effective = stored["effective"]
        if old_values.shape != (completed, len(keys)) or old_effective.shape != old_values.shape:
            raise core.BenchmarkError("bootstrap checkpoint shape differs")
        values[:completed] = old_values
        effective[:completed] = old_effective
    return values, effective, completed


def _save_bootstrap_checkpoint(
    keys: Sequence[str], values: np.ndarray, effective: np.ndarray, completed: int, config_sha256: str
) -> None:
    temporary = BOOTSTRAP_CHECKPOINT.with_name(f".{BOOTSTRAP_CHECKPOINT.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        np.savez(
            handle,
            config_sha256=np.asarray(config_sha256),
            keys=np.asarray(keys),
            completed=np.asarray(completed),
            values=values[:completed],
            effective=effective[:completed],
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, BOOTSTRAP_CHECKPOINT)


def run_bootstrap(dataset: Mapping[str, Any], config_sha256: str) -> tuple[dict[str, Any], dict[str, tuple[float | None, int]]]:
    point_all = core.compute_main_metrics(
        dataset["values"], dataset["centered"], dataset["levels"], dataset["models"], dataset["domains"]
    )
    point = {key: value for key, value in point_all.items() if _keep_bootstrap_key(key)}
    keys = sorted(point)
    values, effective, completed = _load_bootstrap_checkpoint(keys, config_sha256)
    clusters = dataset["clusters"]
    draw_digest = hashlib.sha256()
    for replicate in range(BOOTSTRAP_REPLICATES):
        rng = np.random.default_rng(_replicate_seed(replicate))
        selected = rng.integers(0, len(clusters), size=len(clusters), dtype=np.int32)
        draw_digest.update(selected.tobytes())
        if replicate < completed:
            continue
        indices = np.concatenate([clusters[int(index)][1] for index in selected])
        sampled = core.compute_main_metrics(
            dataset["values"][indices],
            dataset["centered"][indices],
            dataset["levels"][indices],
            dataset["models"][indices],
            dataset["domains"][indices],
        )
        filtered = {key: sampled[key] for key in keys}
        for column, key in enumerate(keys):
            value, n = filtered[key]
            values[replicate, column] = np.nan if value is None else value
            effective[replicate, column] = n
        if (replicate + 1) % 25 == 0 or replicate + 1 == BOOTSTRAP_REPLICATES:
            _save_bootstrap_checkpoint(keys, values, effective, replicate + 1, config_sha256)
            print(f"bootstrap {replicate + 1}/{BOOTSTRAP_REPLICATES}", flush=True)

    summaries: dict[str, Any] = {}
    for column, key in enumerate(keys):
        series = values[:, column]
        finite_mask = np.isfinite(series)
        finite = series[finite_mask]
        finite_n = effective[:, column][finite_mask]
        summaries[key] = {
            "point": point[key][0],
            "point_effective_n": point[key][1],
            "ci_95_percentile": {
                "lower": float(np.percentile(finite, 2.5)) if len(finite) else None,
                "upper": float(np.percentile(finite, 97.5)) if len(finite) else None,
            },
            "finite_resamples": int(len(finite)),
            "undefined_resamples": int(BOOTSTRAP_REPLICATES - len(finite)),
            "resample_effective_n_all_min": int(effective[:, column].min()),
            "resample_effective_n_all_max": int(effective[:, column].max()),
            "resample_effective_n_finite_min": int(finite_n.min()) if len(finite_n) else None,
            "resample_effective_n_finite_max": int(finite_n.max()) if len(finite_n) else None,
        }
    summary = {
        "schema": "actual_heuristic.bootstrap_summary",
        "schema_version": 1,
        "method": "paired source-cluster empirical percentile bootstrap",
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "confidence_level": 0.95,
        "cluster_count": len(clusters),
        "sampled_cluster_count_per_replicate": len(clusters),
        "cluster_definition": [
            "domain", "source_id_or_item_id", "source_text_sha256_or_legacy_id_fallback"
        ],
        "shared_draws_for_all_scores_and_metrics": True,
        "draw_sequence_sha256": draw_digest.hexdigest(),
        "metrics": summaries,
    }
    return summary, point_all


def _ci_direction(cell: Mapping[str, Any]) -> int:
    interval = cell.get("ci_95_percentile", {})
    lower, upper = interval.get("lower"), interval.get("upper")
    if lower is None or upper is None:
        return 0
    if lower > 0.0:
        return 1
    if upper < 0.0:
        return -1
    return 0


def _winner(direction: int) -> str:
    return "BB_actual" if direction > 0 else ("heuristic" if direction < 0 else "inconclusive")


def _robust_label(bootstrap: Mapping[str, Any], feature: str, unit: str) -> str:
    signs: dict[tuple[str, str], int] = {}
    for evaluator in core.EVALUATORS:
        for metric in ("rho", "alpha_z"):
            key = "|".join(("difference", evaluator, feature, unit, f"delta_{metric}"))
            signs[(evaluator, metric)] = _ci_direction(bootstrap["metrics"][key])
    nonzero = set(signs.values()) - {0}
    if set(signs.values()) == {1}:
        return "robust_BB_convergence_winner"
    if set(signs.values()) == {-1}:
        return "robust_heuristic_convergence_winner"
    if signs[("llama", "rho")] * signs[("mixtral", "rho")] == -1 or signs[("llama", "alpha_z")] * signs[("mixtral", "alpha_z")] == -1:
        return "evaluator-dependent"
    if any(signs[(evaluator, "rho")] * signs[(evaluator, "alpha_z")] == -1 for evaluator in core.EVALUATORS):
        return "metric-dependent"
    if len(nonzero) > 1:
        return "mixed"
    return "inconclusive"


def _regression_checks(rows: Sequence[Mapping[str, Any]], dataset: Mapping[str, Any], point: Mapping[str, tuple[float | None, int]]) -> dict[str, Any]:
    pilot = _load_json(_path("pilot_summary"))
    safe_expected = {
        "word_type_coverage": 0.92562698,
        "word_token_coverage": 0.92751524,
        "word_bigram_coverage": 0.77921868,
        "char5_coverage": 0.91779765,
        "rouge_l_recall": 0.92882778,
        "prompt_to_output_byte_ratio": 0.80870533,
        "prompt_bytes": -0.02048099,
        "prompt_words": -0.02078926,
    }
    # Historical safe fields are checked before independently reproducing them.
    pilot_checks = {}
    for feature, expected in safe_expected.items():
        stored = float(pilot["heuristics"][feature]["against_blackbox_actual"]["macro_mean_within_level_spearman"])
        if abs(stored - expected) > 5e-8:
            raise core.BenchmarkError(f"historical safe regression field differs: {feature}")
        pilot_checks[feature] = {"stored": stored, "expected_approx": expected}

    sample = _load_json(CANONICAL / "heuristic_pilot_large" / "sample_manifest.json")
    sample_keys = {tuple(entry["semantic_key"]) for entry in sample["items"]}
    subset = [row for row in rows if core.semantic_key(row) in sample_keys]
    if len(subset) != 40300:
        raise core.CoverageError("historical regression cohort extraction differs")
    subset_data = core.dataset_arrays(subset, expected_pairs=40300)
    subset_point = core.compute_main_metrics(
        subset_data["values"], subset_data["centered"], subset_data["levels"],
        subset_data["models"], subset_data["domains"]
    )
    reproduced = {}
    for feature, expected in safe_expected.items():
        key = f"direct|{feature}|macro_within_level|rho"
        value = subset_point[key][0]
        if value is None or abs(value - expected) > 5e-8:
            raise core.BenchmarkError(f"historical cohort direct regression failed: {feature}: {value}")
        reproduced[key] = value
    whitebox_expected = {
        "convergence|llama|blackbox_actual_ratio|macro_within_level|rho": 0.76628305,
        "convergence|mixtral|blackbox_actual_ratio|macro_within_level|rho": 0.75638988,
        "convergence|llama|word_type_coverage|macro_within_level|rho": 0.76716668,
        "convergence|mixtral|word_type_coverage|macro_within_level|rho": 0.75703792,
        "convergence|llama|rouge_l_recall|macro_within_level|rho": 0.79784259,
        "convergence|mixtral|rouge_l_recall|macro_within_level|rho": 0.78460206,
    }
    for key, expected in whitebox_expected.items():
        value = subset_point[key][0]
        if value is None or abs(value - expected) > 5e-8:
            raise core.BenchmarkError(f"historical cohort whitebox regression failed: {key}: {value}")
        reproduced[key] = value

    authority_expected = {
        "convergence|llama|blackbox_actual_ratio|pooled|rho": 0.9569662446504178,
        "convergence|llama|blackbox_actual_ratio|item_centered|rho": 0.9653669807336983,
        "convergence|mixtral|blackbox_actual_ratio|pooled|rho": 0.9563448913917773,
        "convergence|mixtral|blackbox_actual_ratio|item_centered|rho": 0.9648403447233318,
    }
    authority = {}
    for key, expected in authority_expected.items():
        value = point[key][0]
        if value is None or abs(value - expected) > 1e-12:
            raise core.BenchmarkError(f"full raw authority regression failed: {key}: {value}")
        authority[key] = value
    return {
        "historical_overlap_cohort": {
            "items": 8060, "pairs": 40300, "tolerance": 5e-8,
            "stored_safe_fields": pilot_checks, "reproduced": reproduced, "passed": True,
        },
        "full_raw_authority": {"tolerance": 1e-12, "reproduced": authority, "passed": True},
    }


def _record(bootstrap: Mapping[str, Any], key: str) -> dict[str, Any]:
    return dict(bootstrap["metrics"][key])


def build_metrics(
    rows: Sequence[Mapping[str, Any]], dataset: Mapping[str, Any], bootstrap: Mapping[str, Any],
    point_all: Mapping[str, tuple[float | None, int]], regression: Mapping[str, Any]
) -> dict[str, Any]:
    point_filtered = {key: value for key, value in point_all.items() if _keep_bootstrap_key(key)}
    if set(point_filtered) != set(bootstrap["metrics"]):
        raise core.BenchmarkError("point/bootstrap metric inventories differ")
    records = {key: _record(bootstrap, key) for key in sorted(point_filtered)}
    robust = {
        feature: {
            unit: _robust_label(bootstrap, feature, unit)
            for unit in ("macro_within_level", "item_centered")
        }
        for feature in core.FEATURES
    }
    joint_rankings = {
        unit: [
            {
                "rank": rank,
                "candidate": candidate,
                "joint_reference_continuous_alpha_z": bootstrap["metrics"][
                    f"joint|{candidate}|{unit}|alpha_z"
                ]["point"],
                "mean_reference_spearman_rho": bootstrap["metrics"][
                    f"joint|{candidate}|{unit}|mean_rho"
                ]["point"],
            }
            for rank, candidate in enumerate(
                sorted(
                    core.CANDIDATES,
                    key=lambda name: (
                        bootstrap["metrics"][f"joint|{name}|{unit}|alpha_z"]["point"]
                        is not None,
                        bootstrap["metrics"][f"joint|{name}|{unit}|alpha_z"]["point"]
                        if bootstrap["metrics"][f"joint|{name}|{unit}|alpha_z"]["point"]
                        is not None
                        else -math.inf,
                    ),
                    reverse=True,
                ),
                1,
            )
        ]
        for unit in ("macro_within_level", "item_centered", "pooled")
    }
    direct_taus = {
        feature: core.mean_per_item_tau_b(dataset["values"], 0, index)
        for index, feature in enumerate(core.FEATURES, 1)
    }
    return {
        "schema": "actual_heuristic.metrics",
        "schema_version": 1,
        "estimand": "aggregate R_actual on recorded prompt-output pairs",
        "coverage": {
            "exact": True,
            "model_items": EXPECTED_ITEMS,
            "actual_pairs": EXPECTED_PAIRS,
            "pairs_per_item": 5,
            "evaluator_pairs_each": EXPECTED_PAIRS,
            "source_clusters": EXPECTED_CLUSTERS,
            "missing_join": 0,
            "duplicate_key": 0,
            "nonfinite_core_score": 0,
            "generation_model_items": EXPECTED_MODEL_COUNTS,
            "domain_items": EXPECTED_DOMAIN_COUNTS,
            "pair_set_sha256": dataset["pair_set_sha256"],
        },
        "metric_namespaces": {
            "association": "Spearman rho with average midranks",
            "primary_agreement": core.PAIRWISE_ALPHA_NAMESPACE,
            "joint_agreement": core.JOINT_ALPHA_NAMESPACE,
            "primary_agreement_definition": "independent sample-z standardization (ddof=1), units x raters, interval Krippendorff alpha, exact O(m) algebra",
            "joint_raters": ["candidate", "phi_actual_llama", "phi_actual_mixtral"],
        },
        "primary_scopes": ["macro_within_level", "item_centered"],
        "secondary_scope": "pooled",
        "per_level_scopes": list(core.LEVELS),
        "feature_protocol": core.feature_protocol(),
        "records": records,
        "robust_winner_classification": robust,
        "joint_reference_rankings": joint_rankings,
        "auxiliary": {
            "alpha_records": core.auxiliary_alpha_records(
                dataset["values"], dataset["centered"], dataset["levels"]
            ),
            "direct_mean_per_item_kendall_tau_b": direct_taus,
            "tie_diagnostics": core.tie_diagnostics(
                dataset["values"], dataset["levels"]
            ),
            "alpha_rank_note": "ordinal auxiliary; overlaps substantially with Spearman rank information",
            "alpha_raw_note": "scale/calibration sensitive; not used for cross-feature ranking",
        },
        "regression_checks": regression,
        "scientific_limits": [
            "High direct agreement indicates co-variation with lexical, length, or output observables; it is not a causal mechanism estimate.",
            "Closer agreement with a white-box operational reference is estimator convergence, not criterion truth or human-contribution accuracy.",
            "Pooled results mix the investigator-designed L1-L5 treatment gradient; primary interpretation uses within-level macro and item-centered results.",
            "Model and domain slices describe the observed benchmark cohort and do not establish transportability to unseen distributions.",
        ],
    }


def _fmt(value: Any, digits: int = 4) -> str:
    return "NA" if value is None else f"{float(value):.{digits}f}"


def _cell(metrics: Mapping[str, Any], key: str) -> str:
    record = metrics["records"][key]
    interval = record["ci_95_percentile"]
    return f"{_fmt(record['point'])} [{_fmt(interval['lower'])}, {_fmt(interval['upper'])}]"


def _delta_cell(metrics: Mapping[str, Any], key: str) -> tuple[str, str]:
    record = metrics["records"][key]
    direction = _ci_direction(record)
    return _cell(metrics, key), _winner(direction)


def render_tables(metrics: Mapping[str, Any]) -> dict[str, str]:
    tables: dict[str, str] = {}
    lines = [
        "# Table 1 — Direct BB_actual ↔ H_actual",
        "",
        f"| Heuristic | Macro within-level ρ | Macro {core.PAIRWISE_ALPHA_NAMESPACE} | Item-centered ρ | Item-centered {core.PAIRWISE_ALPHA_NAMESPACE} | Pooled ρ (secondary) | Pooled {core.PAIRWISE_ALPHA_NAMESPACE} (secondary) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for feature in core.FEATURES:
        lines.append(
            f"| `{feature}` | {_cell(metrics, f'direct|{feature}|macro_within_level|rho')} | "
            f"{_cell(metrics, f'direct|{feature}|macro_within_level|alpha_z')} | "
            f"{_cell(metrics, f'direct|{feature}|item_centered|rho')} | "
            f"{_cell(metrics, f'direct|{feature}|item_centered|alpha_z')} | "
            f"{_cell(metrics, f'direct|{feature}|pooled|rho')} | "
            f"{_cell(metrics, f'direct|{feature}|pooled|alpha_z')} |"
        )
    tables["table1_direct.md"] = "\n".join(lines) + "\n"

    for table_number, evaluator in ((2, "llama"), (3, "mixtral")):
        lines = [
            f"# Table {table_number} — {evaluator.title()} white-box convergence",
            "",
            f"| Candidate | Macro within-level ρ | Macro {core.PAIRWISE_ALPHA_NAMESPACE} | Item-centered ρ | Item-centered {core.PAIRWISE_ALPHA_NAMESPACE} | Pooled ρ (secondary) | Pooled {core.PAIRWISE_ALPHA_NAMESPACE} (secondary) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for candidate in core.CANDIDATES:
            base = f"convergence|{evaluator}|{candidate}"
            lines.append(
                f"| `{candidate}` | {_cell(metrics, base+'|macro_within_level|rho')} | "
                f"{_cell(metrics, base+'|macro_within_level|alpha_z')} | "
                f"{_cell(metrics, base+'|item_centered|rho')} | "
                f"{_cell(metrics, base+'|item_centered|alpha_z')} | "
                f"{_cell(metrics, base+'|pooled|rho')} | "
                f"{_cell(metrics, base+'|pooled|alpha_z')} |"
            )
        tables[f"table{table_number}_{evaluator}.md"] = "\n".join(lines) + "\n"

    lines = [
        "# Table 4 — Paired BB-minus-heuristic differences",
        "",
        f"| Heuristic | Evaluator | Scope | Δρ (BB−H) 95% CI | ρ winner | Δ{core.PAIRWISE_ALPHA_NAMESPACE} (BB−H) 95% CI | α winner | Classification |",
        "|---|---|---|---:|---|---:|---|---|",
    ]
    for feature in core.FEATURES:
        for evaluator in core.EVALUATORS:
            for unit in ("macro_within_level", "item_centered", "pooled"):
                rho, rho_winner = _delta_cell(metrics, f"difference|{evaluator}|{feature}|{unit}|delta_rho")
                alpha, alpha_winner = _delta_cell(metrics, f"difference|{evaluator}|{feature}|{unit}|delta_alpha_z")
                classification = metrics["robust_winner_classification"].get(feature, {}).get(unit, "secondary")
                lines.append(
                    f"| `{feature}` | {evaluator.title()} | {unit} | {rho} | {rho_winner} | {alpha} | {alpha_winner} | {classification} |"
                )
    tables["table4_paired_differences.md"] = "\n".join(lines) + "\n"

    lines = [
        "# Table 5 — Joint two-white-box agreement",
        "",
        f"| Candidate | Scope | Mean reference Spearman ρ | {core.JOINT_ALPHA_NAMESPACE} | Δmean ρ (BB−H) 95% CI | Δjoint α_z (BB−H) 95% CI |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for candidate in core.CANDIDATES:
        for unit in ("macro_within_level", "item_centered", "pooled"):
            base = f"joint|{candidate}|{unit}"
            if candidate == "blackbox_actual_ratio":
                delta_rho = delta_alpha = "reference"
            else:
                delta_rho = _cell(metrics, f"joint_difference|{candidate}|{unit}|delta_mean_rho")
                delta_alpha = _cell(metrics, f"joint_difference|{candidate}|{unit}|delta_alpha_z")
            lines.append(
                f"| `{candidate}` | {unit} | {_cell(metrics, base+'|mean_rho')} | "
                f"{_cell(metrics, base+'|alpha_z')} | {delta_rho} | {delta_alpha} |"
            )
    tables["table5_joint_reference.md"] = "\n".join(lines) + "\n"

    lines = [
        "# Table 6 — Observed-cohort generation-model/domain robustness",
        "",
        f"| Dimension | Subgroup | Comparison | Evaluator | Candidate/heuristic | Macro within-level ρ | Macro {core.PAIRWISE_ALPHA_NAMESPACE} |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for dimension, names in (("generation_model", core.MODELS), ("domain", core.DOMAINS)):
        for name in names:
            prefix = f"subgroup|{dimension}|{name}"
            for feature in core.FEATURES:
                lines.append(
                    f"| {dimension} | {name} | BB↔H | — | `{feature}` | "
                    f"{_cell(metrics, prefix+f'|direct|{feature}|macro_within_level|rho')} | "
                    f"{_cell(metrics, prefix+f'|direct|{feature}|macro_within_level|alpha_z')} |"
                )
            for evaluator in core.EVALUATORS:
                for candidate in core.CANDIDATES:
                    base = prefix + f"|convergence|{evaluator}|{candidate}|macro_within_level"
                    lines.append(
                        f"| {dimension} | {name} | candidate↔φ | {evaluator.title()} | `{candidate}` | "
                        f"{_cell(metrics, base+'|rho')} | {_cell(metrics, base+'|alpha_z')} |"
                    )
    tables["table6_subgroups.md"] = "\n".join(lines) + "\n"
    return tables


def render_appendices(metrics: Mapping[str, Any]) -> dict[str, str]:
    appendices: dict[str, str] = {}
    lines = [
        "# Appendix A — Per-level agreement",
        "",
        f"| Comparison | Evaluator | Candidate/heuristic | Level | Spearman ρ | {core.PAIRWISE_ALPHA_NAMESPACE} |",
        "|---|---|---|---|---:|---:|",
    ]
    for feature in core.FEATURES:
        for level in core.LEVELS:
            base = f"direct|{feature}|{level}"
            lines.append(
                f"| BB↔H | — | `{feature}` | {level} | {_cell(metrics, base+'|rho')} | "
                f"{_cell(metrics, base+'|alpha_z')} |"
            )
    for evaluator in core.EVALUATORS:
        for candidate in core.CANDIDATES:
            for level in core.LEVELS:
                base = f"convergence|{evaluator}|{candidate}|{level}"
                lines.append(
                    f"| candidate↔φ | {evaluator.title()} | `{candidate}` | {level} | "
                    f"{_cell(metrics, base+'|rho')} | {_cell(metrics, base+'|alpha_z')} |"
                )
    lines.extend([
        "", "## Joint-reference per-level auxiliary", "",
        f"| Candidate | Level | Mean reference Spearman ρ | {core.JOINT_ALPHA_NAMESPACE} |",
        "|---|---|---:|---:|",
    ])
    for candidate in core.CANDIDATES:
        for level in core.LEVELS:
            base = f"joint|{candidate}|{level}"
            lines.append(
                f"| `{candidate}` | {level} | {_cell(metrics, base+'|mean_rho')} | "
                f"{_cell(metrics, base+'|alpha_z')} |"
            )
    appendices["appendix_per_level.md"] = "\n".join(lines) + "\n"

    lines = [
        "# Appendix B — Auxiliary agreement alphas", "",
        "`pairwise_continuous_alpha_rank` is ordinal and overlaps with Spearman; "
        "`pairwise_continuous_alpha_raw` is scale/calibration sensitive. Neither is used for primary cross-feature ranking.",
        "", "| Family | Evaluator | Candidate/heuristic | Scope | Exact alpha namespace | Point | Effective n |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for record in metrics["auxiliary"]["alpha_records"]:
        family = str(record["family"])
        if ":" in family:
            family_name, evaluator = family.split(":", 1)
        else:
            family_name, evaluator = family, "—"
        lines.append(
            f"| {family_name} | {evaluator} | `{record['candidate']}` | {record['scope']} | "
            f"`{record['metric_namespace']}` | {_fmt(record['point'])} | {record['effective_n']} |"
        )
    appendices["appendix_auxiliary_alpha.md"] = "\n".join(lines) + "\n"

    lines = [
        "# Appendix C — Tie and undefined diagnostics", "",
        "| Score | Distinct values | Tied observations | Tied fraction | Largest tie block | Pooled constant | Constant level cells |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for score, diagnostic in metrics["auxiliary"]["tie_diagnostics"].items():
        constant_levels = [level for level, cell in diagnostic["by_level"].items() if cell["constant"]]
        lines.append(
            f"| `{score}` | {diagnostic['distinct_values']} | {diagnostic['tied_observations']} | "
            f"{_fmt(diagnostic['tied_observation_fraction'])} | {diagnostic['largest_tie_block']} | "
            f"{diagnostic['pooled_constant']} | {', '.join(constant_levels) if constant_levels else 'none'} |"
        )
    undefined = [
        (metric_id, record) for metric_id, record in metrics["records"].items()
        if record["undefined_resamples"]
    ]
    lines.extend([
        "", "## Bootstrap undefined replicates", "",
        "| Metric ID | Finite | Undefined | Effective n all draws | Effective n finite draws |",
        "|---|---:|---:|---|---|",
    ])
    if undefined:
        for metric_id, record in undefined:
            finite_range = (
                "NA" if record["resample_effective_n_finite_min"] is None else
                f"{record['resample_effective_n_finite_min']}–{record['resample_effective_n_finite_max']}"
            )
            lines.append(
                f"| `{metric_id}` | {record['finite_resamples']} | {record['undefined_resamples']} | "
                f"{record['resample_effective_n_all_min']}–{record['resample_effective_n_all_max']} | {finite_range} |"
            )
    else:
        lines.append("| none | 2000 for every metric | 0 | recorded in metrics.json | recorded in metrics.json |")
    appendices["appendix_ties_undefined.md"] = "\n".join(lines) + "\n"

    protocol = metrics["feature_protocol"]
    lines = [
        "# Appendix D — Feature definitions", "",
        f"- Unicode normalization: {protocol['text']['unicode_normalization']}",
        f"- Case normalization: {protocol['text']['case_normalization']}",
        f"- Whitespace normalization: {protocol['text']['whitespace_normalization']}",
        f"- Word-token regex: `{protocol['text']['word_token_regex']}`",
        f"- Byte encoding: {protocol['text']['byte_encoding']}",
        f"- Coverage orientation: {protocol['coverage']['orientation']}",
        f"- Coverage numerator: {protocol['coverage']['multiset_numerator']}",
        f"- Coverage denominator: {protocol['coverage']['multiset_denominator']}",
        f"- Zero denominator: {protocol['coverage']['zero_denominator']}",
        f"- ROUGE-L: {protocol['rouge_l_recall']}",
        f"- Empty-string handling: {protocol['empty_strings']}",
        "", "| Feature | Frozen definition |", "|---|---|",
        "| `prompt_bytes` | UTF-8 byte length of actual prompt |",
        "| `output_bytes` | UTF-8 byte length of actual output |",
        "| `prompt_words` | Number of normalized prompt word tokens |",
        "| `output_words` | Number of normalized output word tokens |",
        "| `prompt_to_output_byte_ratio` | prompt bytes / output bytes |",
        "| `word_type_coverage` | Distinct output word types present in prompt / distinct output word types |",
        "| `word_token_coverage` | Multiset output word tokens recoverable from prompt / output word tokens |",
        "| `word_bigram_coverage` | Multiset output word bigrams recoverable from prompt / output word bigrams |",
        "| `char3_coverage` / `char5_coverage` / `char8_coverage` | Multiset normalized output character n-grams recoverable from prompt / output n-grams |",
        f"| `rouge_l_recall` | {protocol['rouge_l_recall']} |",
        f"| `output_type_token_ratio` | {protocol['output_diagnostics']['type_token_ratio']} |",
        f"| `output_bigram_repeat_fraction` | {protocol['output_diagnostics']['bigram_repeat_fraction']} |",
        f"| `output_self_bits_per_byte` | {protocol['output_diagnostics']['self_bits_per_byte']} |",
    ]
    appendices["appendix_feature_definitions.md"] = "\n".join(lines) + "\n"
    return appendices


def _write_metrics_csv(metrics: Mapping[str, Any], path: Path) -> None:
    fields = [
        "metric_id", "point", "ci_lower", "ci_upper", "point_effective_n",
        "finite_resamples", "undefined_resamples", "resample_effective_n_all_min",
        "resample_effective_n_all_max", "resample_effective_n_finite_min",
        "resample_effective_n_finite_max",
    ]
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key, record in sorted(metrics["records"].items()):
            writer.writerow({
                "metric_id": key,
                "point": record["point"],
                "ci_lower": record["ci_95_percentile"]["lower"],
                "ci_upper": record["ci_95_percentile"]["upper"],
                "point_effective_n": record["point_effective_n"],
                "finite_resamples": record["finite_resamples"],
                "undefined_resamples": record["undefined_resamples"],
                "resample_effective_n_all_min": record["resample_effective_n_all_min"],
                "resample_effective_n_all_max": record["resample_effective_n_all_max"],
                "resample_effective_n_finite_min": record["resample_effective_n_finite_min"],
                "resample_effective_n_finite_max": record["resample_effective_n_finite_max"],
            })
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def render_report(
    metrics: Mapping[str, Any], tables: Mapping[str, str], appendices: Mapping[str, str]
) -> str:
    robust = metrics["robust_winner_classification"]
    robust_rows = [
        (feature, unit, label)
        for feature, units in robust.items()
        for unit, label in units.items()
        if label.startswith("robust_")
    ]
    lines = [
        "# Experiment A：paper-final actual-only heuristic benchmark",
        "",
        "## 分析合同",
        "",
        f"- 完整冻结 cohort：**{EXPECTED_ITEMS:,} model-items / {EXPECTED_PAIRS:,} actual prompt-output pairs / {EXPECTED_CLUSTERS:,} underlying source clusters**。",
        "- 黑盒主分数：aggregate `actual_ratio`；白盒分别为 Llama 与 Mixtral 的 `levels.<L>.phi`。",
        f"- 每项主比较同时报告 Spearman ρ 与明确命名的 `{core.PAIRWISE_ALPHA_NAMESPACE}`；后者先对每个 scorer 独立按 sample SD（ddof=1）做 z 标准化，再用 interval Krippendorff α 的 O(m) 精确代数式。",
        f"- 推断：{BOOTSTRAP_REPLICATES:,} 次 paired source-cluster bootstrap，seed={BOOTSTRAP_SEED}；同一 draw 同时用于全部候选、两个 evaluator、ρ、α 和直接差值。",
        "- pooled 只作 secondary 描述；主解释使用 macro within-level 与 item-centered。",
        "",
        "## 科学解释边界",
        "",
        "BB_actual 与某个 H_actual 高度一致，只说明压缩分数与相应 lexical/length/output observable 共变。某个 heuristic 对白盒 operational estimator 的 convergence 更强，也不等于它更接近真实人类贡献；白盒不是 criterion truth。L1–L5 是联合改变 coverage、prompt length、representation form 与 generation stages 的 investigator-designed treatments，不是人工标签或纯信息量单因素干预。",
        "",
    ]
    for name in TABLE_FILES:
        lines.append(tables[name].strip())
        lines.append("")
    lines.extend([
        "## Robust convergence winner",
        "",
        (
            "满足两个 evaluator 的 paired Δρ CI 同方向且不跨 0，并且相应 continuous alpha_z 的 paired Δ CI 也同方向且不跨 0 的结果如下："
            if robust_rows else
            "没有 candidate 在指定主统计单位上同时满足两个 evaluator 的 paired Δρ 与 continuous alpha_z CI 同方向且不跨 0；因此不存在 robust convergence winner。"
        ),
    ])
    for feature, unit, label in robust_rows:
        lines.append(f"- `{feature}` / {unit}: **{label}**")
    lines.extend([
        "",
        "## 附录",
        "",
        "以下附录全部由 `metrics.json` 自动生成；alpha_rank 与 alpha_raw 不用于跨 feature 主排名。",
        "",
    ])
    for name in APPENDIX_FILES:
        lines.append(appendices[name].strip())
        lines.append("")
    return "\n".join(lines)


def _environment() -> dict[str, Any]:
    packages = {}
    for name in ("numpy", "scipy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
    }


def code_snapshot() -> dict[str, Any]:
    files = []
    for path in sorted(BUNDLE_DIR.glob("*.py")):
        files.append({"path": path.name, "sha256": core.sha256_file(path), "size": path.stat().st_size})
    return {"files": files, "inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(files))}


def build_run_config(inputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "actual_heuristic.run_config",
        "schema_version": 1,
        "bundle_id": BUNDLE_ID,
        "migration_id": MIGRATION_ID,
        "created_at_utc": "2026-09-11T03:58:18Z",
        "input_artifacts": inputs,
        "feature_protocol_sha256": core.sha256_bytes(core.canonical_json_bytes(core.feature_protocol())),
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "confidence_interval": "95% empirical percentile",
            "paired_shared_draws": True,
        },
        "execution": {
            "external_api_calls": 0,
            "model_generation": False,
            "gpu_inference": False,
            "network_access": False,
            "parallelism": "single process",
            "text_loading": "one source/debug record at a time; only numeric feature ledger retained",
        },
        "environment": _environment(),
        "code": code_snapshot(),
    }


def _config_payload_sha(config: Mapping[str, Any]) -> str:
    payload = dict(config)
    stored = payload.pop("run_config_payload_sha256", None)
    actual = core.sha256_bytes(core.canonical_json_bytes(payload))
    if stored is not None and stored != actual:
        raise core.BenchmarkError("run config self-hash differs")
    return actual


def _records_for(names: Sequence[str]) -> list[dict[str, Any]]:
    records = []
    for name in names:
        path = BUNDLE_DIR / name
        if Path(name).name != name or path.is_symlink() or not path.is_file():
            raise core.BenchmarkError(f"required bound artifact missing/unsafe: {name}")
        records.append({"path": name, "sha256": core.sha256_file(path), "size": path.stat().st_size})
    return records


def _scientific_completion_document(
    config_sha256: str, inputs: Mapping[str, Any]
) -> dict[str, Any]:
    artifacts = _records_for(SCIENTIFIC_FILES)
    base = {
        "schema": "actual_heuristic.scientific_completion",
        "schema_version": 1,
        "state": "complete",
        "config_sha256": config_sha256,
        "input_snapshot": inputs,
        "code_snapshot": code_snapshot(),
        "artifacts": artifacts,
        "artifact_inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(artifacts)),
    }
    return {
        **base,
        "receipt_payload_sha256_excluding_this_field": core.sha256_bytes(
            core.canonical_json_bytes(base)
        ),
    }


def verify_scientific_completion(
    config_sha256: str, inputs: Mapping[str, Any]
) -> Mapping[str, Any]:
    if not SCIENTIFIC_COMPLETION.is_file():
        raise core.BenchmarkError("scientific completion receipt missing")
    receipt = _load_json(SCIENTIFIC_COMPLETION)
    payload = dict(receipt)
    stored_payload = payload.pop("receipt_payload_sha256_excluding_this_field", None)
    if stored_payload != core.sha256_bytes(core.canonical_json_bytes(payload)):
        raise core.BenchmarkError("scientific completion receipt self-hash differs")
    expected = _scientific_completion_document(config_sha256, inputs)
    if receipt != expected:
        raise core.BenchmarkError("scientific completion artifact/input/code binding differs")
    if [entry["path"] for entry in receipt["artifacts"]] != list(SCIENTIFIC_FILES):
        raise core.BenchmarkError("scientific completion inventory differs")
    return receipt


def verify_audit_binding() -> Mapping[str, Any]:
    audit_path = BUNDLE_DIR / "audit.json"
    if not audit_path.is_file():
        raise core.BenchmarkError("independent audit is missing")
    audit = _load_json(audit_path)
    if audit.get("state") != "pass":
        raise core.BenchmarkError("independent audit did not pass")
    records = _records_for(AUDIT_BOUND_FILES)
    expected_mapping = {entry["path"]: {"sha256": entry["sha256"], "size": entry["size"]} for entry in records}
    if audit.get("audited_artifacts") != expected_mapping:
        raise core.BenchmarkError("audited artifact hashes no longer match")
    if audit.get("audited_artifact_inventory_sha256") != core.sha256_bytes(
        core.canonical_json_bytes(records)
    ):
        raise core.BenchmarkError("audited artifact inventory digest differs")
    return audit


def run() -> None:
    verify_bundle_path()
    priority = _lower_priority()
    started = time.perf_counter()
    inputs_before = snapshot_inputs()
    lineage, source_entries, score_entries = validate_authorities()
    protocol = core.feature_protocol()
    core.atomic_write_json(BUNDLE_DIR / "feature_protocol.json", protocol)
    config = build_run_config(inputs_before)
    config["execution"]["process_priority"] = priority
    config_sha = core.sha256_bytes(core.canonical_json_bytes(config))
    config["run_config_payload_sha256"] = config_sha
    config_path = BUNDLE_DIR / "run_config.json"
    if config_path.exists():
        existing = _load_json(config_path)
        if existing != config or _config_payload_sha(existing) != config_sha:
            raise core.BenchmarkError("existing run config differs; refuse mixed resume")
    else:
        core.atomic_write_json(config_path, config)

    if SCIENTIFIC_COMPLETION.exists():
        verify_scientific_completion(config_sha, inputs_before)
        if snapshot_inputs() != inputs_before:
            raise core.BenchmarkError("bound inputs changed during idempotence verification")
        print("existing scientific completion receipt and all bound files verified; no files changed")
        return

    llama = load_actual_scores("llama", score_entries["llama"])
    mixtral = load_actual_scores("mixtral", score_entries["mixtral"])
    pilot_hashes, feature_cache, cache_info = validate_pilot_cache()
    feature_run = build_feature_ledger(
        source_entries, llama, mixtral, pilot_hashes, feature_cache, config_sha
    )
    rows = core.load_feature_rows(FEATURE_LEDGER)
    dataset = core.dataset_arrays(rows)
    bootstrap, point = run_bootstrap(dataset, config_sha)
    regression = _regression_checks(rows, dataset, point)
    metrics = build_metrics(rows, dataset, bootstrap, point, regression)
    core.atomic_write_json(BUNDLE_DIR / "bootstrap_summary.json", bootstrap)
    core.atomic_write_json(BUNDLE_DIR / "metrics.json", metrics)
    # Every human/machine-readable projection is generated from the exact
    # published strict-JSON authority, never from manually transcribed values.
    metrics = _load_json(BUNDLE_DIR / "metrics.json")
    tables = render_tables(metrics)
    appendices = render_appendices(metrics)

    _write_metrics_csv(metrics, BUNDLE_DIR / "metrics.csv")
    for name, content in {**tables, **appendices}.items():
        core.atomic_write_text(BUNDLE_DIR / name, content)
    core.atomic_write_text(
        BUNDLE_DIR / "REPORT_ZH.md", render_report(metrics, tables, appendices)
    )

    inputs_after = snapshot_inputs()
    if inputs_after != inputs_before:
        raise core.BenchmarkError("bound inputs changed during run")
    FEATURE_CHECKPOINT.unlink(missing_ok=True)
    execution = {
        "schema": "actual_heuristic.execution",
        "schema_version": 1,
        "state": "scientific_outputs_complete_pending_independent_audit",
        "elapsed_seconds": time.perf_counter() - started,
        "feature_run": feature_run,
        "pilot_cache": cache_info,
        "input_snapshot_before": inputs_before,
        "input_snapshot_after": inputs_after,
        "inputs_unchanged": True,
        "code_snapshot": code_snapshot(),
    }
    core.atomic_write_json(BUNDLE_DIR / "execution.json", execution)
    completion = _scientific_completion_document(config_sha, inputs_after)
    core.atomic_write_json(SCIENTIFIC_COMPLETION, completion)
    verify_scientific_completion(config_sha, inputs_after)
    print(f"scientific outputs complete in {execution['elapsed_seconds']:.1f}s; run independent audit next")


def _validate_final_manifest() -> Mapping[str, Any]:
    manifest_path = BUNDLE_DIR / "manifest.json"
    manifest = _load_json(manifest_path)
    payload = dict(manifest)
    stored_payload = payload.pop("manifest_payload_sha256_excluding_this_field", None)
    if stored_payload != core.sha256_bytes(core.canonical_json_bytes(payload)):
        raise core.BenchmarkError("final manifest self-hash differs")
    if (
        manifest.get("schema") != "actual_heuristic.manifest"
        or manifest.get("schema_version") != 1
        or manifest.get("state") != "complete"
        or manifest.get("bundle_id") != BUNDLE_ID
        or manifest.get("migration_id") != MIGRATION_ID
    ):
        raise core.BenchmarkError("final manifest identity differs")
    records = manifest.get("artifacts")
    if not isinstance(records, list):
        raise core.BenchmarkError("final manifest artifacts are invalid")
    paths = [record.get("path") for record in records if isinstance(record, Mapping)]
    if len(paths) != len(records) or len(set(paths)) != len(paths):
        raise core.BenchmarkError("final manifest artifact paths are duplicated/invalid")
    if any(not isinstance(name, str) or Path(name).name != name for name in paths):
        raise core.BenchmarkError("final manifest artifact path is unsafe")
    if manifest.get("artifact_inventory_sha256") != core.sha256_bytes(
        core.canonical_json_bytes(records)
    ):
        raise core.BenchmarkError("final manifest artifact-inventory hash differs")
    actual_names = sorted(
        path.name for path in BUNDLE_DIR.iterdir()
        if path.name != "manifest.json" and not path.name.startswith(".")
    )
    if sorted(paths) != actual_names:
        raise core.BenchmarkError("final directory inventory is not exactly manifest-bound")
    for record in records:
        path = BUNDLE_DIR / record["path"]
        if path.is_symlink() or not path.is_file():
            raise core.BenchmarkError(f"final artifact missing/unsafe: {path.name}")
        if core.sha256_file(path) != record.get("sha256") or path.stat().st_size != record.get("size"):
            raise core.BenchmarkError(f"final artifact drift: {path.name}")
    inputs = snapshot_inputs()
    config = _load_json(BUNDLE_DIR / "run_config.json")
    config_sha = _config_payload_sha(config)
    verify_scientific_completion(config_sha, inputs)
    verify_audit_binding()
    return manifest


def finalize() -> None:
    verify_bundle_path()
    if (BUNDLE_DIR / "manifest.json").exists():
        _validate_final_manifest()
        print("existing final manifest, exact inventory, and audit verified; no files changed")
        return
    post_inputs = snapshot_inputs()
    config = _load_json(BUNDLE_DIR / "run_config.json")
    config_sha = _config_payload_sha(config)
    verify_scientific_completion(config_sha, post_inputs)
    audit = verify_audit_binding()
    execution = _load_json(BUNDLE_DIR / "execution.json")
    if execution.get("input_snapshot_before") != post_inputs:
        raise core.BenchmarkError("protected input drift before finalization")
    bytecode_cache = BUNDLE_DIR / "__pycache__"
    if bytecode_cache.is_dir():
        shutil.rmtree(bytecode_cache)
    expected_names = set(AUDIT_BOUND_FILES) | {"audit.json"}
    actual_names = {
        path.name for path in BUNDLE_DIR.iterdir()
        if path.name != "manifest.json" and not path.name.startswith(".")
    }
    if actual_names != expected_names:
        raise core.BenchmarkError(
            f"prospective final inventory differs: missing={sorted(expected_names-actual_names)!r}, "
            f"extra={sorted(actual_names-expected_names)!r}"
        )
    artifacts = _records_for(sorted(expected_names))
    base = {
        "schema": "actual_heuristic.manifest",
        "schema_version": 1,
        "state": "complete",
        "bundle_id": BUNDLE_ID,
        "migration_id": MIGRATION_ID,
        "created_at_utc": "2026-09-11T03:58:18Z",
        "coverage": _load_json(BUNDLE_DIR / "metrics.json")["coverage"],
        "analysis_request": {
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "primary_metrics": ["Spearman rho", core.PAIRWISE_ALPHA_NAMESPACE],
            "joint_metric": core.JOINT_ALPHA_NAMESPACE,
        },
        "claims": {
            "external_api_calls": 0,
            "model_generation": False,
            "gpu_inference": False,
            "network_access": False,
            "experiment_a_modified": False,
            "experiment_b_modified": False,
            "canonical_inputs_modified": False,
            "historical_artifacts_modified": False,
            "disallowed_derived_score_fields_absent": True,
        },
        "inputs": post_inputs,
        "artifacts": artifacts,
        "artifact_inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(artifacts)),
        "audit_sha256": core.sha256_file(BUNDLE_DIR / "audit.json"),
        "audited_artifact_inventory_sha256": audit["audited_artifact_inventory_sha256"],
        "write_scope": str(BUNDLE_DIR.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    payload_sha = core.sha256_bytes(core.canonical_json_bytes(base))
    manifest = {**base, "manifest_payload_sha256_excluding_this_field": payload_sha}
    core.atomic_write_json(BUNDLE_DIR / "manifest.json", manifest)
    _validate_final_manifest()
    print(f"final manifest -> {BUNDLE_DIR / 'manifest.json'}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "finalize"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "run":
        run()
    else:
        finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
