# -*- coding: utf-8 -*-
"""Exploratory model-size × text-length systems benchmark.

This is deliberately a standardized raw-sequence protocol (no chat template),
not the production white-box φ protocol.  It reports both prepared-device and
end-to-end batch-1 latency for two causal-LM loss calls.
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

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import atomic_replace_json, canonical_row_sha256
from experiment_baseline.bench_blackbox_time_binned import _load_sample

DEFAULT_SAMPLE = Path(expand_placeholder("${HC_DATA_ROOT}/timing_results/sample_pairs_v2.json"))
DEFAULT_OUT_ROOT = Path(expand_placeholder("${HC_DATA_ROOT}/timing_results"))
SEED = 20260823


def _load_tokenizer(auto_tokenizer, path: str, log) -> object:
    try:
        return auto_tokenizer.from_pretrained(path, use_fast=True, trust_remote_code=True)
    except Exception as exc:
        log(f"fast tokenizer failed ({type(exc).__name__}); use_fast=False")
        tokenizer = auto_tokenizer.from_pretrained(
            path, use_fast=False, trust_remote_code=True
        )
        if not callable(tokenizer):
            raise RuntimeError("slow tokenizer loader returned a non-callable value")
        return tokenizer


def _prepare(torch, tokenizer, prompt: str, output: str, device):
    unconditional = tokenizer(
        output, add_special_tokens=True, return_tensors="pt"
    ).input_ids.to(device)
    if unconditional.shape[1] < 2:
        raise RuntimeError("unconditional sequence has fewer than two tokens")
    unconditional_labels = unconditional.clone()
    unconditional_labels[:, :1] = -100

    prompt_ids = tokenizer(prompt, add_special_tokens=True).input_ids
    response_ids = tokenizer(output, add_special_tokens=False).input_ids
    conditional = torch.tensor([prompt_ids + response_ids], device=device)
    if not response_ids:
        raise RuntimeError("response tokenization is empty")
    conditional_labels = conditional.clone()
    conditional_labels[:, : len(prompt_ids)] = -100
    return {
        "unconditional": unconditional,
        "unconditional_labels": unconditional_labels,
        "conditional": conditional,
        "conditional_labels": conditional_labels,
        "prompt_tokens": len(prompt_ids),
        "response_tokens": len(response_ids),
    }


def _score(model, prepared):
    first = model(
        prepared["unconditional"],
        labels=prepared["unconditional_labels"],
        use_cache=False,
    ).loss.item()
    second = model(
        prepared["conditional"],
        labels=prepared["conditional_labels"],
        use_cache=False,
    ).loss.item()
    return first, second


def _cuda_devices(torch, model):
    devices = set()
    for value in getattr(model, "hf_device_map", {}).values():
        if isinstance(value, int):
            devices.add(torch.device(f"cuda:{value}"))
        elif str(value).startswith("cuda"):
            devices.add(torch.device(str(value)))
    if not devices:
        device = next(model.parameters()).device
        if device.type == "cuda":
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


def _sync(torch, devices):
    for device in devices:
        torch.cuda.synchronize(device)


def _aggregate(rows, scope):
    field = f"{scope}_s"
    result = {}
    for bin_index in sorted({row["bin"] for row in rows}):
        selected = [row for row in rows if row["bin"] == bin_index]
        times = [row[field] for row in selected]
        result[str(bin_index)] = {
            "n": len(selected),
            "mean_ref_tokens": st.fmean(row["ref_tokens"] for row in selected),
            "mean_prompt_tokens": st.fmean(row["prompt_tokens"] for row in selected),
            "mean_conditional_tokens": st.fmean(
                row["conditional_tokens"] for row in selected
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
    parser.add_argument("--tag", required=True)
    parser.add_argument("--model-path", "--model_path", dest="model_path", required=True)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--attn", default=None)
    parser.add_argument("--warmup", type=int, default=6)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.warmup < 0 or args.repetitions <= 0:
        parser.error("warmup must be non-negative and repetitions positive")
    out_path = args.out or DEFAULT_OUT_ROOT / f"whitebox_scaling_{args.tag}_v2.json"

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    def log(message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

    sample, pairs, sample_file_sha256 = _load_sample(args.sample)
    tokenizer = _load_tokenizer(AutoTokenizer, args.model_path, log)
    kwargs = {
        "dtype": torch.bfloat16,
        "device_map": "auto",
        "trust_remote_code": True,
    }
    if args.attn:
        kwargs["attn_implementation"] = args.attn
    load_started = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(args.model_path, **kwargs)
    model.eval()
    load_s = time.perf_counter() - load_started
    devices = _cuda_devices(torch, model)
    if not devices:
        raise RuntimeError("scaling benchmark requires CUDA")
    device_map = {str(key): str(value) for key, value in getattr(model, "hf_device_map", {}).items()}
    if any(value in {"cpu", "disk"} for value in device_map.values()):
        raise RuntimeError(f"CPU/disk offload is not allowed: {device_map}")
    input_device = _input_device(model)

    for pair in _warmup_pairs(pairs, args.warmup):
        prepared = _prepare(
            torch, tokenizer, pair["prompt"], pair["output"], input_device
        )
        with torch.no_grad():
            _score(model, prepared)
    _sync(torch, devices)

    order = list(range(len(pairs)))
    random.Random(args.seed).shuffle(order)
    rows = []
    for run_order, pair_index in enumerate(order):
        pair = pairs[pair_index]
        prepared = _prepare(
            torch, tokenizer, pair["prompt"], pair["output"], input_device
        )
        def time_device_scope():
            _sync(torch, devices)
            started = time.perf_counter_ns()
            with torch.no_grad():
                for _ in range(args.repetitions):
                    result = _score(model, prepared)
            _sync(torch, devices)
            return result, (time.perf_counter_ns() - started) / 1e9 / args.repetitions

        def time_end_to_end_scope():
            _sync(torch, devices)
            started = time.perf_counter_ns()
            with torch.no_grad():
                for _ in range(args.repetitions):
                    fresh = _prepare(
                        torch, tokenizer, pair["prompt"], pair["output"], input_device
                    )
                    result = _score(model, fresh)
            _sync(torch, devices)
            return result, (time.perf_counter_ns() - started) / 1e9 / args.repetitions

        if run_order % 2:
            end_to_end_losses, end_to_end_s = time_end_to_end_scope()
            prepared_losses, device_s = time_device_scope()
            scope_order = "end_to_end_then_device"
        else:
            prepared_losses, device_s = time_device_scope()
            end_to_end_losses, end_to_end_s = time_end_to_end_scope()
            scope_order = "device_then_end_to_end"
        if prepared_losses != end_to_end_losses:
            raise RuntimeError(f"prepared/end-to-end loss mismatch for pair {pair_index}")

        rows.append(
            {
                "pair_index": pair_index,
                "run_order": run_order,
                "scope_order": scope_order,
                "pair_sha256": pair.get("pair_sha256"),
                "bin": pair["bin"],
                "ref_tokens": pair["ref_tokens"],
                "prompt_tokens": prepared["prompt_tokens"],
                "response_tokens": prepared["response_tokens"],
                "conditional_tokens": int(prepared["conditional"].shape[1]),
                "device_only_s": device_s,
                "end_to_end_s": end_to_end_s,
            }
        )
        if len(rows) % 50 == 0:
            log(f"{args.tag}: {len(rows)}/{len(pairs)}")
    rows.sort(key=lambda row: row["pair_index"])

    protocol = {
        "schema_version": 2,
        "role": "exploratory_model_size_scaling",
        "serialization": "raw prompt and output; no chat template",
        "loss": "causal LM labels mean loss; use_cache=False",
        "batch_size": 1,
        "dtype": "bfloat16",
        "warmup": args.warmup,
        "repetitions": args.repetitions,
        "pair_order": "seeded_shuffle",
        "scope_order": "alternating_by_run_order",
        "warmup_selection": "first available pair from each length bin, then fill",
        "seed": args.seed,
    }
    output = {
        "schema": "whitebox_scaling_timing_v2",
        "tag": args.tag,
        "model_path": args.model_path,
        "sample_path": str(args.sample),
        "sample_file_sha256": sample_file_sha256,
        "sample_declared_sha256": sample.get("sample_payload_sha256"),
        "protocol": protocol,
        "protocol_sha256": canonical_row_sha256(protocol),
        "benchmark_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "load_s": load_s,
        "n_params": sum(parameter.numel() for parameter in model.parameters()),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "participating_devices": [str(device) for device in devices],
        "hf_device_map": device_map,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
            "attention_implementation": getattr(model.config, "_attn_implementation", None),
        },
        "per_bin": {
            "device_only": _aggregate(rows, "device_only"),
            "end_to_end": _aggregate(rows, "end_to_end"),
        },
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(out_path, output)
    log(f"wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
