# -*- coding: utf-8 -*-
"""Production-equivalent white-box φ timing on a frozen v2 sample."""
from __future__ import annotations

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

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import atomic_replace_json, canonical_row_sha256
from experiment_baseline.bench_blackbox_time_binned import _load_sample
from experiment_baseline import whitebox_core

DEFAULT_SAMPLE = Path(whitebox_core.expand_placeholder("${HC_DATA_ROOT}/timing_results/sample_pairs_v2.json"))
DEFAULT_OUT_ROOT = Path(whitebox_core.expand_placeholder("${HC_DATA_ROOT}/timing_results"))
SEED = 20260823


def _cuda_devices(torch, model) -> tuple:
    devices = set()
    for value in getattr(model, "hf_device_map", {}).values():
        text = str(value)
        if isinstance(value, int):
            devices.add(torch.device(f"cuda:{value}"))
        elif text.startswith("cuda"):
            devices.add(torch.device(text))
    if not devices:
        device = getattr(model, "device", next(model.parameters()).device)
        if getattr(device, "type", None) == "cuda":
            devices.add(device)
    return tuple(sorted(devices, key=str))


def _input_device(model):
    embeddings = model.get_input_embeddings()
    try:
        return next(embeddings.parameters()).device
    except StopIteration:
        return next(model.parameters()).device


def _warmup_pairs(pairs: list[dict], count: int) -> list[dict]:
    if count <= 0:
        return []
    selected = []
    seen_bins = set()
    for pair in pairs:
        if pair["bin"] not in seen_bins:
            selected.append(pair)
            seen_bins.add(pair["bin"])
        if len(selected) == count:
            return selected
    for pair in pairs:
        if len(selected) == count:
            break
        selected.append(pair)
    return selected


def _synchronize(torch, devices) -> None:
    for device in devices:
        torch.cuda.synchronize(device)


def _aggregate(rows: list[dict], scope: str) -> dict:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["bin"], []).append(row)
    result = {}
    field = f"{scope}_s"
    for bin_index in sorted(grouped):
        values = grouped[bin_index]
        times = [row[field] for row in values]
        result[str(bin_index)] = {
            "n": len(values),
            "mean_ref_tokens": st.fmean(row["ref_tokens"] for row in values),
            "mean_prompt_ref_tokens": st.fmean(
                row["prompt_ref_tokens"] for row in values
            ),
            "mean_unconditional_tokens": st.fmean(
                row["unconditional_tokens"] for row in values
            ),
            "mean_conditional_tokens": st.fmean(
                row["conditional_tokens"] for row in values
            ),
            "mean_s": st.fmean(times),
            "median_s": st.median(times),
            "std_s": st.pstdev(times),
            "min_s": min(times),
            "max_s": max(times),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator", choices=sorted(whitebox_core.EVAL_MODELS), required=True)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--warmup", type=int, default=6)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.warmup < 0 or args.repetitions <= 0:
        parser.error("warmup must be non-negative and repetitions positive")
    out_path = args.out or DEFAULT_OUT_ROOT / f"whitebox_production_{args.evaluator}_v2.json"

    import torch
    import transformers

    sample, pairs, sample_file_sha256 = _load_sample(args.sample)
    load_started = time.perf_counter()
    model, tokenizer, dtype = whitebox_core.load_model(args.evaluator)
    load_s = time.perf_counter() - load_started
    devices = _cuda_devices(torch, model)
    if not devices:
        raise RuntimeError("white-box timing requires CUDA with no CPU/disk offload")
    device_map = {str(key): str(value) for key, value in getattr(model, "hf_device_map", {}).items()}
    if any(value in {"cpu", "disk"} for value in device_map.values()):
        raise RuntimeError(f"CPU/disk offload is not allowed: {device_map}")
    input_device = _input_device(model)

    for pair in _warmup_pairs(pairs, args.warmup):
        whitebox_core.score_phi(tokenizer, model, pair["prompt"], pair["output"])
    _synchronize(torch, devices)

    order = list(range(len(pairs)))
    random.Random(args.seed).shuffle(order)
    rows = []
    for run_order, pair_index in enumerate(order):
        pair = pairs[pair_index]
        prepared = whitebox_core.prepare_phi_inputs(
            tokenizer, pair["prompt"], pair["output"], device=input_device
        )

        def time_device_scope():
            _synchronize(torch, devices)
            started = time.perf_counter_ns()
            for _ in range(args.repetitions):
                result = whitebox_core.score_prepared_inputs(model, prepared)
            _synchronize(torch, devices)
            return result, (time.perf_counter_ns() - started) / 1e9 / args.repetitions

        def time_end_to_end_scope():
            _synchronize(torch, devices)
            started = time.perf_counter_ns()
            for _ in range(args.repetitions):
                result = whitebox_core.score_phi(
                    tokenizer, model, pair["prompt"], pair["output"]
                )
            _synchronize(torch, devices)
            return result, (time.perf_counter_ns() - started) / 1e9 / args.repetitions

        if run_order % 2:
            end_to_end_result, end_to_end_s = time_end_to_end_scope()
            prepared_result, device_s = time_device_scope()
            scope_order = "end_to_end_then_device"
        else:
            prepared_result, device_s = time_device_scope()
            end_to_end_result, end_to_end_s = time_end_to_end_scope()
            scope_order = "device_then_end_to_end"
        if prepared_result != end_to_end_result:
            raise RuntimeError(f"prepared/end-to-end score mismatch for pair {pair_index}")

        rows.append(
            {
                "pair_index": pair_index,
                "run_order": run_order,
                "scope_order": scope_order,
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
                "prompt_ref_tokens": pair.get("prompt_ref_tokens", 0),
                "unconditional_tokens": int(prepared.unconditional.input_ids.shape[1]),
                "conditional_tokens": int(prepared.conditional.input_ids.shape[1]),
                "device_only_s": device_s,
                "end_to_end_s": end_to_end_s,
            }
        )
        if len(rows) % 50 == 0:
            print(f"[{args.evaluator}] {len(rows)}/{len(pairs)}", flush=True)
    rows.sort(key=lambda row: row["pair_index"])

    protocol = {
        "schema_version": 2,
        "scorer_protocol_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
        "timing_scopes": {
            "device_only": "prepared device tensors + exact two forward/loss calls + phi arithmetic",
            "end_to_end": "tokenization + tensor construction + transfer + exact two forward/loss calls + phi arithmetic",
            "model_load": "reported separately and excluded from both scopes",
        },
        "batch_size": 1,
        "warmup": args.warmup,
        "repetitions": args.repetitions,
        "pair_order": "seeded_shuffle",
        "scope_order": "alternating_by_run_order",
        "warmup_selection": "first available pair from each length bin, then fill",
        "seed": args.seed,
    }
    output = {
        "schema": "whitebox_production_timing_v2",
        "evaluator": args.evaluator,
        "evaluator_descriptor": whitebox_core.evaluator_descriptor(args.evaluator),
        "evaluator_sha256": whitebox_core.evaluator_sha256(args.evaluator),
        "sample_path": str(args.sample),
        "sample_file_sha256": sample_file_sha256,
        "sample_declared_sha256": sample.get("sample_payload_sha256"),
        "protocol": protocol,
        "protocol_sha256": canonical_row_sha256(protocol),
        "benchmark_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "load_s": load_s,
        "n_params": sum(parameter.numel() for parameter in model.parameters()),
        "dtype": str(dtype),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "participating_devices": [str(device) for device in devices],
        "hf_device_map": device_map,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
            "attention_implementation": getattr(
                model.config, "_attn_implementation", None
            ),
        },
        "per_bin": {
            "device_only": _aggregate(rows, "device_only"),
            "end_to_end": _aggregate(rows, "end_to_end"),
        },
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(out_path, output)
    print(f"wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
