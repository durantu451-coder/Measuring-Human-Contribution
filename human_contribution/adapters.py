"""Adapter protocol for model-based counterfactual sampling."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from .metrics import (
    ContributionWeights,
    CounterfactualSample,
    SessionContribution,
    evaluate_session,
)


class PromptOutputSampler(Protocol):
    """Protocol for the model-dependent part of the algorithm.

    A production implementation should freeze the model, sampling settings,
    system prompt, and decoding parameters so scores are comparable.
    """

    def reconstruct_prompts(self, output: str, n: int) -> Sequence[str]:
        """Infer plausible prompts that could have produced `output`."""

    def generate(self, prompt: str) -> str:
        """Generate one output from the fixed model for `prompt`."""


def counterfactuals_from_sampler(
    output: str,
    sampler: PromptOutputSampler,
    n: int,
) -> list[CounterfactualSample]:
    prompts = sampler.reconstruct_prompts(output, n)
    return [
        CounterfactualSample(
            prompt=prompt,
            output=sampler.generate(prompt),
            label=f"reconstructed_{index + 1}",
        )
        for index, prompt in enumerate(prompts[:n])
    ]


def evaluate_with_sampler(
    prompt: str,
    output: str,
    sampler: PromptOutputSampler,
    n_counterfactuals: int = 5,
    conversation: Sequence[Mapping[str, str]] | None = None,
    compressors: Sequence[str] | None = None,
    weights: ContributionWeights | None = None,
) -> SessionContribution:
    counterfactuals = counterfactuals_from_sampler(output, sampler, n_counterfactuals)
    return evaluate_session(
        prompt=prompt,
        output=output,
        counterfactuals=counterfactuals,
        conversation=conversation,
        compressors=compressors,
        weights=weights,
    )
