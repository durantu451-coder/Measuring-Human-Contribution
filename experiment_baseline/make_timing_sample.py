# -*- coding: utf-8 -*-
"""Build a deterministic, manifest-bound timing sample from baseline-v2 source rows."""
from __future__ import annotations

from experiment_baseline.whitebox_core import expand_placeholder
from pathlib import Path  # noqa: F401

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import (
    atomic_replace_json,
    canonical_row_sha256,
    file_sha256,
    sha256_bytes,
)
from experiment_baseline.whitebox_schema import LEVELS, strict_jsonl_loads, validate_source_rows

DEFAULT_TOKENIZER = Path(expand_placeholder("${HC_DATA_ROOT}/models/Meta-Llama-3.1-8B-Instruct"))
BINS = ((85, 115), (180, 220), (320, 380), (500, 600), (720, 880), (1050, 1400))
PER_BIN = 100
SEED = 20260819


def _stable_rank(seed: int, pair_sha256: str) -> str:
    return hashlib.sha256(f"{seed}:{pair_sha256}".encode("ascii")).hexdigest()


def _pair_sha256(source: dict, level: str) -> str:
    return canonical_row_sha256(
        {
            "semantic_key": [
                source["generation_model"], source["domain"], source["id"]
            ],
            "scoring_input_sha256": source["scoring_input_sha256"],
            "level": level,
            "prompt": source["levels"][level]["prompt"],
            "output": source["levels"][level]["output"],
        }
    )


def build_sample(
    sources: list[dict], tokenizer, *, seed: int = SEED, per_bin: int = PER_BIN
) -> dict:
    validate_source_rows(sources)
    buckets: dict[int, list[dict]] = {index: [] for index in range(len(BINS))}
    seen = set()
    for source in sources:
        for level in LEVELS:
            prompt = source["levels"][level]["prompt"]
            output = source["levels"][level]["output"]
            pair_hash = _pair_sha256(source, level)
            if pair_hash in seen:
                raise RuntimeError(f"duplicate timing pair hash: {pair_hash}")
            seen.add(pair_hash)
            response_ids = tokenizer(output, add_special_tokens=False)["input_ids"]
            prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
            response_tokens = len(response_ids)
            for bin_index, (lower, upper) in enumerate(BINS):
                if lower <= response_tokens < upper:
                    buckets[bin_index].append(
                        {
                            "pair_sha256": pair_hash,
                            "generation_model": source["generation_model"],
                            "domain": source["domain"],
                            "id": source["id"],
                            "scoring_input_sha256": source["scoring_input_sha256"],
                            "source_file": source["source_file"],
                            "level": level,
                            "prompt": prompt,
                            "output": output,
                            "ref_tokens": response_tokens,
                            "prompt_ref_tokens": len(prompt_ids),
                            "combined_ref_tokens": len(prompt_ids) + response_tokens,
                            "prompt_bytes": len(prompt.encode("utf-8")),
                            "output_bytes": len(output.encode("utf-8")),
                            "bin": bin_index,
                            "bin_range": [lower, upper],
                        }
                    )
                    break

    selected = []
    availability = {}
    composition = {}
    for bin_index, candidates in buckets.items():
        candidates.sort(key=lambda row: _stable_rank(seed, row["pair_sha256"]))
        if len(candidates) < per_bin:
            raise RuntimeError(
                f"bin {bin_index} has {len(candidates)} candidates; need {per_bin}"
            )
        picks = candidates[:per_bin]
        selected.extend(picks)
        availability[str(bin_index)] = len(candidates)
        counts = {}
        for row in picks:
            group = f"{row['generation_model']}|{row['domain']}|{row['level']}"
            counts[group] = counts.get(group, 0) + 1
        composition[str(bin_index)] = counts

    payload = {
        "schema": "baseline_timing_sample_v2",
        "seed": seed,
        "bins": [list(value) for value in BINS],
        "per_bin": per_bin,
        "availability": availability,
        "composition": composition,
        "pairs": selected,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-jsonl", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tokenizer", type=Path, default=DEFAULT_TOKENIZER)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--per-bin", type=int, default=PER_BIN)
    args = parser.parse_args()
    if args.per_bin <= 0:
        parser.error("--per-bin must be positive")

    from transformers import AutoTokenizer

    source_bytes = args.source_jsonl.read_bytes()
    source_file_sha256 = sha256_bytes(source_bytes)
    tokenizer_config = args.tokenizer / "tokenizer_config.json"
    tokenizer_config_sha256 = (
        file_sha256(tokenizer_config) if tokenizer_config.is_file() else None
    )
    sources = strict_jsonl_loads(source_bytes, path=str(args.source_jsonl))
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, use_fast=True)
    sample = build_sample(sources, tokenizer, seed=args.seed, per_bin=args.per_bin)
    sample["source_jsonl"] = str(args.source_jsonl)
    sample["source_file_sha256"] = source_file_sha256
    sample["reference_tokenizer"] = str(args.tokenizer)
    sample["reference_tokenizer_config_sha256"] = tokenizer_config_sha256
    sample["generator_code_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    sample["sample_payload_sha256"] = canonical_row_sha256(sample)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(args.out, sample)
    print(f"wrote {len(sample['pairs'])} pairs -> {args.out}")
    for bin_index, count in sample["availability"].items():
        chosen = sum(1 for row in sample["pairs"] if str(row["bin"]) == bin_index)
        print(f"  bin{bin_index}: candidates={count}, selected={chosen}")


if __name__ == "__main__":
    main()
