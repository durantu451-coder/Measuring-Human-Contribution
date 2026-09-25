# -*- coding: utf-8 -*-
"""Manifest-bound white-box φ runner for baseline v2.

This command no longer discovers mutable debug directories or resumes by
``(model, domain, id)`` alone.  It delegates to :mod:`migrate_phi`, whose queue
binds every item to source-input, evaluator, and scoring-protocol hashes.

Examples::

    python -m experiment_baseline.batch_phi \
      --manifest experiment_baseline/v2/prepare_manifest_canonical.json \
      --eval-model llama --dry-run

    CUDA_VISIBLE_DEVICES=5 python -m experiment_baseline.batch_phi \
      --manifest ${HC_DATA_ROOT}/baseline_v2_stage/prepare_manifest_canonical.json \
      --runtime-root ${HC_DATA_ROOT}/baseline_v2_stage/runtime \
      --eval-model llama
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from experiment_baseline.migrate_phi import run
from experiment_baseline.whitebox_core import (
    EVAL_MODELS,
    LEVELS,
    SYSTEM_PROMPT,
    compute_phi,
    load_model,
    nll_cond,
    nll_uncond,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--eval-model", "--eval_model", dest="eval_model",
        choices=sorted(EVAL_MODELS), required=True,
    )
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run(
        args.manifest,
        evaluator=args.eval_model,
        runtime_root=args.runtime_root,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


__all__ = [
    "EVAL_MODELS",
    "LEVELS",
    "SYSTEM_PROMPT",
    "compute_phi",
    "load_model",
    "main",
    "nll_cond",
    "nll_uncond",
]


if __name__ == "__main__":
    raise SystemExit(main())
