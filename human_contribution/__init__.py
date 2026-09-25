"""Compression-based human contribution measurement."""

from .metrics import (
    ContributionWeights,
    CounterfactualSample,
    InformationGain,
    SessionContribution,
    compute_krippendorff_alpha,
    compute_spearman,
    evaluate_session,
    information_gain,
)
from .adapters import PromptOutputSampler, counterfactuals_from_sampler, evaluate_with_sampler
from .deepseek_adapter import DeepSeekAdapter
from .multi_model_adapter import MultiModelAdapter
from .compression_embedding import (
    CompressionEmbeddingResult,
    EmbeddingProvider,
    EmbeddingTrajectoryFeatures,
    HashingEmbeddingProvider,
    APIScriptEmbeddingProvider,
    Qwen3EmbeddingProvider,
    embedding_prompt_guidance_alignment,
    embedding_semantic_trajectory,
    evaluate_compression_embedding,
)
from .trajectory import TrajectoryFeatures, analyze_trajectory

__all__ = [
    "ContributionWeights",
    "CounterfactualSample",
    "DeepSeekAdapter",
    "InformationGain",
    "CompressionEmbeddingResult",
    "EmbeddingProvider",
    "EmbeddingTrajectoryFeatures",
    "HashingEmbeddingProvider",
    "APIScriptEmbeddingProvider",
    "MultiModelAdapter",
    "PromptOutputSampler",
    "Qwen3EmbeddingProvider",
    "SessionContribution",
    "TrajectoryFeatures",
    "analyze_trajectory",
    "compute_krippendorff_alpha",
    "compute_spearman",
    "counterfactuals_from_sampler",
    "embedding_prompt_guidance_alignment",
    "embedding_semantic_trajectory",
    "evaluate_compression_embedding",
    "evaluate_session",
    "evaluate_with_sampler",
    "information_gain",
]
