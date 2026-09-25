# -*- coding: utf-8 -*-
"""Benchmark the optimized full-item black-box workload on a frozen v2 source.

One item consists of one shared valid-CF baseline and five actual level scores.
The primary method is the canonical aggregate over zlib+bz2+lzma; zlib-only is
reported only as a diagnostic sensitivity analysis.  File I/O is excluded.
"""
from __future__ import annotations

from experiment_baseline.whitebox_core import expand_placeholder
from pathlib import Path  # noqa: F401

import argparse
import hashlib
import json
import platform
import statistics as st
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import (
    atomic_replace_json,
    canonical_row_sha256,
    sha256_bytes,
)
from experiment_baseline.whitebox_schema import LEVELS, strict_jsonl_loads, validate_source_rows
from human_contribution import compression
from human_contribution import metrics as metrics_module
from human_contribution.compression import DEFAULT_COMPRESSORS
from human_contribution.metrics import (
    CounterfactualSample,
    build_counterfactual_baseline_profile,
    evaluate_session_profile,
)

DEFAULT_SOURCE = Path(expand_placeholder("${HC_DATA_ROOT}/baseline_v2_stage/runtime/sources.jsonl"))
DEFAULT_OUT = Path(expand_placeholder("${HC_DATA_ROOT}/timing_results/blackbox_full_item_v2.json"))


def _peak_rss_bytes() -> int | None:
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value * 1024) if sys.platform != "darwin" else int(value)
    except (ImportError, OSError):
        return None


def _counterfactuals(source: dict) -> list[CounterfactualSample]:
    return [
        CounterfactualSample(
            prompt=entry["prompt"], output=entry["output"], label=f"cf_{entry['index'] + 1}"
        )
        for entry in source["counterfactuals"]
        if entry["included"]
    ]


def _score_item(source: dict, compressors: tuple[str, ...]) -> None:
    baseline = build_counterfactual_baseline_profile(
        _counterfactuals(source), compressors
    )
    for level in LEVELS:
        pair = source["levels"][level]
        evaluate_session_profile(
            pair["prompt"],
            pair["output"],
            compressors=compressors,
            precomputed_baseline=baseline,
        )


def _bench(sources: list[dict], compressors: tuple[str, ...], repetitions: int) -> dict:
    wall_start = time.perf_counter_ns()
    process_start = time.process_time_ns()
    per_item = []
    for source in sources:
        item_start = time.perf_counter_ns()
        for _ in range(repetitions):
            _score_item(source, compressors)
        per_item.append((time.perf_counter_ns() - item_start) / 1e9 / repetitions)
    process_s = (time.process_time_ns() - process_start) / 1e9 / repetitions
    wall_s = (time.perf_counter_ns() - wall_start) / 1e9 / repetitions
    return {
        "n_items": len(sources),
        "repetitions": repetitions,
        "total_wall_s": wall_s,
        "total_process_s": process_s,
        "mean_item_wall_s": st.fmean(per_item),
        "median_item_wall_s": st.median(per_item),
        "std_item_wall_s": st.pstdev(per_item),
        "throughput_items_per_s": len(sources) / wall_s,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-jsonl", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--primary-repetitions", type=int, default=1)
    parser.add_argument("--zlib-repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.primary_repetitions <= 0 or args.zlib_repetitions <= 0:
        parser.error("repetitions must be positive")

    source_bytes = args.source_jsonl.read_bytes()
    source_file_sha256 = sha256_bytes(source_bytes)
    rows = strict_jsonl_loads(source_bytes, path=str(args.source_jsonl))
    validate_source_rows(rows)
    sources = rows if args.limit is None else rows[: args.limit]
    if not sources:
        raise RuntimeError("source manifest is empty")

    compression._overhead_bits.cache_clear()
    cold_start = time.perf_counter_ns()
    _score_item(sources[0], DEFAULT_COMPRESSORS)
    cold_s = (time.perf_counter_ns() - cold_start) / 1e9
    for source in sources[: min(10, len(sources))]:
        _score_item(source, DEFAULT_COMPRESSORS)
        _score_item(source, ("zlib",))

    primary = _bench(sources, DEFAULT_COMPRESSORS, args.primary_repetitions)
    zlib = _bench(sources, ("zlib",), args.zlib_repetitions)
    protocol = {
        "schema_version": 2,
        "workload": "one shared valid-CF baseline plus five level actuals per item",
        "primary": "canonical aggregate ratio(mean calibrated bits)",
        "primary_compressors": list(DEFAULT_COMPRESSORS),
        "diagnostics": ["zlib_only"],
        "overhead_cache": "warmed process-local per-compressor constant",
        "input_preload": (
            "entire source JSONL retained as raw bytes and strict decoded rows; "
            "schema validation and 10-item warmup excluded from timed region"
        ),
        "warmup_items": min(10, len(sources)),
        "io_in_timed_region": False,
    }
    output = {
        "schema": "blackbox_full_item_timing_v2",
        "source_jsonl": str(args.source_jsonl),
        "source_file_sha256": source_file_sha256,
        "source_count": len(rows),
        "source_raw_bytes": len(source_bytes),
        "timed_count": len(sources),
        "protocol": protocol,
        "protocol_sha256": canonical_row_sha256(protocol),
        "benchmark_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cold_first_item_s": cold_s,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "compression_module": {
                "path": str(Path(compression.__file__).resolve()),
                "sha256": hashlib.sha256(
                    Path(compression.__file__).read_bytes()
                ).hexdigest(),
            },
            "metrics_module": {
                "path": str(Path(metrics_module.__file__).resolve()),
                "sha256": hashlib.sha256(
                    Path(metrics_module.__file__).read_bytes()
                ).hexdigest(),
            },
            "peak_rss_bytes_after_benchmark": _peak_rss_bytes(),
        },
        "primary_canonical_3compressors": primary,
        "diagnostic_zlib_only": zlib,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(args.out, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
