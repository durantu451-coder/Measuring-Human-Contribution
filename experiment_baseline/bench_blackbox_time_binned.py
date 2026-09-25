# -*- coding: utf-8 -*-
"""Benchmark canonical black-box pair scoring on one frozen timing sample.

Primary result: aggregate information_gain with zlib+bz2+lzma.  The zlib-only
series is a diagnostic sensitivity analysis, not the primary method.
"""
from __future__ import annotations

from experiment_baseline.whitebox_core import expand_placeholder
from pathlib import Path  # noqa: F401

import argparse
import hashlib
import json
import os
import platform
import random
import statistics as st
import sys
import time
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import atomic_replace_json, canonical_row_sha256, sha256_bytes
from human_contribution import compression
from human_contribution.compression import DEFAULT_COMPRESSORS
from human_contribution.metrics import information_gain

DEFAULT_SAMPLE = Path(expand_placeholder("${HC_DATA_ROOT}/timing_results/sample_pairs_v2.json"))
DEFAULT_OUT = Path(expand_placeholder("${HC_DATA_ROOT}/timing_results/blackbox_binned_v2.json"))
SEED = 20260823


def _load_sample(path: Path) -> tuple[dict, list[dict], str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    declared_hash = data.get("sample_payload_sha256")
    if data.get("schema") == "baseline_timing_sample_v2" and not declared_hash:
        raise RuntimeError("v2 timing sample is missing sample_payload_sha256")
    if declared_hash is not None:
        unhashed = dict(data)
        unhashed.pop("sample_payload_sha256", None)
        actual_hash = canonical_row_sha256(unhashed)
        if actual_hash != declared_hash:
            raise RuntimeError(
                f"timing sample payload hash mismatch: {actual_hash} != {declared_hash}"
            )
    pairs = data.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise RuntimeError("timing sample must contain a non-empty pairs array")
    expected = int(data.get("per_bin", 0))
    bins = data.get("bins")
    if expected <= 0 or not isinstance(bins, list) or not bins:
        raise RuntimeError("timing sample must define bins and positive per_bin")
    counts = {index: 0 for index in range(len(bins))}
    seen = set()
    for index, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            raise RuntimeError(f"pair {index} is not an object")
        bin_index = pair.get("bin")
        if type(bin_index) is not int or bin_index not in counts:
            raise RuntimeError(f"pair {index} has invalid bin")
        prompt, output = pair.get("prompt"), pair.get("output")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RuntimeError(f"pair {index} has empty prompt")
        if not isinstance(output, str) or not output.strip():
            raise RuntimeError(f"pair {index} has empty output")
        identity = pair.get("pair_sha256") or canonical_row_sha256(
            {"prompt": prompt, "output": output, "bin": bin_index}
        )
        if identity in seen:
            raise RuntimeError(f"duplicate timing pair at index {index}")
        seen.add(identity)
        counts[bin_index] += 1
    bad = {key: value for key, value in counts.items() if value != expected}
    if bad:
        raise RuntimeError(f"timing bins do not each contain {expected} rows: {bad}")
    return data, pairs, sha256_bytes(raw)


def _aggregate(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["bin"], []).append(row)
    result = {}
    for bin_index in sorted(grouped):
        values = grouped[bin_index]
        wall = [row["wall_time_s"] for row in values]
        cpu = [row["process_time_s"] for row in values]
        result[str(bin_index)] = {
            "n": len(values),
            "mean_ref_tokens": st.fmean(row["ref_tokens"] for row in values),
            "mean_wall_s": st.fmean(wall),
            "median_wall_s": st.median(wall),
            "std_wall_s": st.pstdev(wall),
            "mean_process_s": st.fmean(cpu),
            "median_process_s": st.median(cpu),
            "std_process_s": st.pstdev(cpu),
        }
    return result


def _bench(
    pairs: list[dict],
    fn: Callable[[str, str], object],
    repetitions: int,
    seed: int,
) -> list[dict]:
    order = list(range(len(pairs)))
    random.Random(seed).shuffle(order)
    rows = []
    for run_order, pair_index in enumerate(order):
        pair = pairs[pair_index]
        wall_start = time.perf_counter_ns()
        process_start = time.process_time_ns()
        for _ in range(repetitions):
            fn(pair["prompt"], pair["output"])
        process_s = (time.process_time_ns() - process_start) / 1e9 / repetitions
        wall_s = (time.perf_counter_ns() - wall_start) / 1e9 / repetitions
        rows.append(
            {
                "pair_index": pair_index,
                "run_order": run_order,
                "pair_sha256": pair.get("pair_sha256")
                or canonical_row_sha256(
                    {
                        "prompt": pair["prompt"],
                        "output": pair["output"],
                        "bin": pair["bin"],
                    }
                ),
                "bin": pair["bin"],
                "ref_tokens": pair["ref_tokens"],
                "prompt_bytes": len(pair["prompt"].encode("utf-8")),
                "output_bytes": len(pair["output"].encode("utf-8")),
                "wall_time_s": wall_s,
                "process_time_s": process_s,
            }
        )
    rows.sort(key=lambda row: row["pair_index"])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--primary-repetitions", type=int, default=5)
    parser.add_argument("--zlib-repetitions", type=int, default=200)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.primary_repetitions <= 0 or args.zlib_repetitions <= 0:
        parser.error("repetition counts must be positive")

    sample, pairs, sample_file_sha256 = _load_sample(args.sample)

    compression._overhead_bits.cache_clear()
    cold_start = time.perf_counter_ns()
    information_gain(
        pairs[0]["prompt"], pairs[0]["output"], DEFAULT_COMPRESSORS
    )
    cold_initialization_s = (time.perf_counter_ns() - cold_start) / 1e9
    cache_after_cold = compression._overhead_bits.cache_info()._asdict()

    variants = {
        "canonical_aggregate_3compressors": (
            lambda prompt, output: information_gain(
                prompt, output, DEFAULT_COMPRESSORS
            ),
            args.primary_repetitions,
        ),
        "diagnostic_zlib_only": (
            lambda prompt, output: information_gain(
                prompt, output, ("zlib",)
            ),
            args.zlib_repetitions,
        ),
    }

    for pair in pairs[:20]:
        for fn, _ in variants.values():
            fn(pair["prompt"], pair["output"])

    results = {}
    for offset, (name, (fn, repetitions)) in enumerate(variants.items()):
        rows = _bench(pairs, fn, repetitions, args.seed + offset)
        results[name] = {
            "role": "primary" if name.startswith("canonical") else "diagnostic",
            "compressors": list(
                DEFAULT_COMPRESSORS if name.startswith("canonical") else ("zlib",)
            ),
            "repetitions": repetitions,
            "per_bin": _aggregate(rows),
            "rows": rows,
        }
        print(f"\n=== {name} ===")
        for bin_index, values in results[name]["per_bin"].items():
            print(
                f"  bin{bin_index} ~{values['mean_ref_tokens']:6.0f}tok "
                f"n={values['n']} mean={values['mean_wall_s'] * 1000:9.4f}ms "
                f"median={values['median_wall_s'] * 1000:9.4f}ms"
            )

    protocol = {
        "schema_version": 2,
        "primary_method": "information_gain",
        "primary_compressors": list(DEFAULT_COMPRESSORS),
        "diagnostics": ["zlib_only"],
        "timer": "perf_counter_ns + process_time_ns",
        "pair_order": "seeded_shuffle",
        "seed": args.seed,
        "overhead_cache": "lru_cache_per_compressor_warm_for_steady_state",
    }
    output = {
        "schema": "blackbox_timing_v2",
        "sample_path": str(args.sample),
        "sample_file_sha256": sample_file_sha256,
        "sample_declared_sha256": sample.get("sample_payload_sha256"),
        "protocol": protocol,
        "protocol_sha256": canonical_row_sha256(protocol),
        "benchmark_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "pid": os.getpid(),
        },
        "cold_initialization_s": cold_initialization_s,
        "overhead_cache_after_cold": cache_after_cold,
        "variants": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(args.out, output)
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
