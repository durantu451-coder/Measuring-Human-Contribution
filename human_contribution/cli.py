"""Command line interface for human contribution measurement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .metrics import (
    ContributionWeights,
    CounterfactualSample,
    evaluate_session,
    information_gain,
)
from .reconstruct import infer_prompt_candidates


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    payload: dict[str, Any] = {}
    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))

    prompt = args.prompt if args.prompt is not None else payload.get("prompt", "")
    output = args.output if args.output is not None else payload.get("output", "")
    if args.output_file:
        output = Path(args.output_file).read_text(encoding="utf-8")
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")

    if not prompt or not output:
        parser.error("Both prompt and output are required.")

    compressors = args.compressor or payload.get("compressors")
    weights = _weights_from_payload(payload.get("weights"))
    counterfactuals = _counterfactuals(payload.get("counterfactuals", []))
    conversation = payload.get("conversation")

    result = evaluate_session(
        prompt=prompt,
        output=output,
        counterfactuals=counterfactuals,
        conversation=conversation,
        compressors=compressors,
        weights=weights,
    )

    data = result.to_dict()
    if args.infer_prompts:
        data["inverse_prompt_candidates"] = infer_prompt_candidates(
            output, n=args.infer_prompts
        )
    if args.pair_only:
        data = information_gain(prompt, output, compressors).to_dict()

    indent = 2 if args.pretty else None
    print(json.dumps(data, ensure_ascii=False, indent=indent))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure human contribution in AI-assisted generation.",
    )
    parser.add_argument("--input", help="JSON session file.")
    parser.add_argument("--prompt", help="Human prompt text.")
    parser.add_argument("--output", help="AI-assisted output text.")
    parser.add_argument("--prompt-file", help="Read prompt from a text file.")
    parser.add_argument("--output-file", help="Read output from a text file.")
    parser.add_argument(
        "--compressor",
        action="append",
        choices=("zlib", "bz2", "lzma"),
        help="Compression backend. Repeat to use an ensemble.",
    )
    parser.add_argument(
        "--infer-prompts",
        type=int,
        default=0,
        help="Include deterministic inverse-prompt candidates.",
    )
    parser.add_argument(
        "--pair-only",
        action="store_true",
        help="Only compute the prompt-output information gain.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser


def _counterfactuals(items: list[dict[str, Any]]) -> list[CounterfactualSample]:
    samples = []
    for item in items:
        samples.append(
            CounterfactualSample(
                prompt=str(item.get("prompt", "")),
                output=str(item.get("output", "")),
                label=item.get("label"),
            )
        )
    return samples


def _weights_from_payload(payload: dict[str, Any] | None) -> ContributionWeights | None:
    if not payload:
        return None
    return ContributionWeights(
        absolute=float(payload.get("absolute", 0.45)),
        excess=float(payload.get("excess", 0.45)),
        trajectory=float(payload.get("trajectory", 0.10)),
    )


if __name__ == "__main__":
    sys.exit(main())
