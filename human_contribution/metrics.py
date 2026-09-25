"""Human contribution metrics."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .compression import (
    CompressionConfig,
    DEFAULT_COMPRESSORS,
    clamp,
    compression_pair_profile,
    count_tokens,
    safe_divide,
)
from .trajectory import TrajectoryFeatures, analyze_trajectory, guidance_by_turn


# --------------------------------------------------------------------------
# Agreement / correlation helpers
# --------------------------------------------------------------------------

LEVEL_LABEL_MAP = {"L1": 5, "L2": 4, "L3": 3, "L4": 2, "L5": 1}


def _rankdata(values: Sequence[float]) -> list[float]:
    """Return fractional ranks (average for ties)."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and indexed[j][1] == indexed[i][1]:
            j += 1
        avg = (i + j + 1) / 2.0  # 1-indexed average
        for k in range(i, j):
            ranks[indexed[k][0]] = avg
        i = j
    return ranks


def compute_spearman(
    excess_ratios: Sequence[float],
    labels: Sequence[str],
    label_map: dict[str, int] | None = None,
) -> float:
    """Spearman rank correlation between *excess_ratios* and numeric *labels*.

    Parameters
    ----------
    excess_ratios:
        The per-sample ``excess_ratio`` values.
    labels:
        Level labels (``"L1"`` … ``"L5"``) for each sample.
    label_map:
        Mapping from label string to integer rank (default: L1=5 … L5=1).
    """
    mapping = label_map or LEVEL_LABEL_MAP
    n = len(excess_ratios)
    if n < 2:
        return 0.0
    label_vals = [mapping.get(l, 0) for l in labels]
    rx = _rankdata(list(excess_ratios))
    ry = _rankdata([float(v) for v in label_vals])
    mean_x = statistics.fmean(rx)
    mean_y = statistics.fmean(ry)
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    den = (sum((rx[i] - mean_x) ** 2 for i in range(n)) *
           sum((ry[i] - mean_y) ** 2 for i in range(n))) ** 0.5
    return num / den if den > 0 else 0.0


def compute_krippendorff_alpha(
    excess_ratios: Sequence[float],
    labels: Sequence[str],
    label_map: dict[str, int] | None = None,
) -> float:
    """Krippendorff's Alpha: inter-rater agreement with interval metric.

    Treats level labels as rating categories and *excess_ratio* values as
    continuous measurements.  Requires the ``krippendorff`` package.

    Parameters
    ----------
    excess_ratios:
        The per-sample ``excess_ratio`` values.
    labels:
        Level labels (``"L1"`` … ``"L5"``) for each sample.
    label_map:
        Mapping from label string to integer rank (default: L1=5 … L5=1).
    """
    try:
        import krippendorff
    except ImportError:
        raise ImportError(
            "krippendorff package is required for compute_krippendorff_alpha. "
            "Install it with: pip install krippendorff"
        )
    mapping = label_map or LEVEL_LABEL_MAP
    label_vals = [mapping.get(l, 0) for l in labels]
    # Build reliability data matrix: 2 raters × N items
    # Rater 1: label values; Rater 2: excess_ratios (bucketed for agreement)
    # Use interval metric (default) suitable for continuous data
    reliability_data = [
        [float(v) for v in label_vals],
        [float(v) for v in excess_ratios],
    ]
    return float(krippendorff.alpha(
        reliability_data=reliability_data,
        level_of_measurement="interval",
    ))


@dataclass(frozen=True)
class InformationGain:
    """Compression approximation of I(prompt; output)."""

    prompt: str
    output: str
    self_information_bits: float
    conditional_information_bits: float
    gain_bits: float
    contribution_ratio: float
    output_tokens: int
    gain_bits_per_token: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["prompt"] = self.prompt
        data["output"] = self.output
        return data


@dataclass(frozen=True)
class InformationGainProfile:
    """One compression pass projected to aggregate and diagnostic metrics."""

    aggregate: InformationGain
    per_compressor: dict[str, dict[str, float]]


@dataclass(frozen=True)
class CounterfactualSample:
    """A prompt reconstructed from the output and the output it generated."""

    prompt: str
    output: str
    label: str | None = None


@dataclass(frozen=True)
class ContributionWeights:
    """Weights for the transparent composite score."""

    absolute: float = 0.45
    excess: float = 0.45
    trajectory: float = 0.10

    def normalized(self) -> "ContributionWeights":
        total = self.absolute + self.excess + self.trajectory
        if total <= 0:
            return ContributionWeights()
        return ContributionWeights(
            absolute=self.absolute / total,
            excess=self.excess / total,
            trajectory=self.trajectory / total,
        )


@dataclass(frozen=True)
class CounterfactualBaseline:
    samples: list[InformationGain] = field(default_factory=list)
    mean_gain_bits: float = 0.0
    mean_contribution_ratio: float = 0.0
    mean_gain_bits_per_token: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": [sample.to_dict() for sample in self.samples],
            "mean_gain_bits": self.mean_gain_bits,
            "mean_contribution_ratio": self.mean_contribution_ratio,
            "mean_gain_bits_per_token": self.mean_gain_bits_per_token,
        }


@dataclass(frozen=True)
class CounterfactualBaselineProfile:
    """Canonical CF baseline plus projections from the same raw passes."""

    aggregate: CounterfactualBaseline
    samples: tuple[InformationGainProfile, ...]
    per_compressor_mean_ratios: dict[str, float]
    compressors: tuple[str, ...]

    def for_actual(
        self,
        prompt: str,
        output: str,
        *,
        conversation: Sequence[Mapping[str, str]] | None = None,
        compressors: Sequence[str] | None = None,
        weights: ContributionWeights | None = None,
    ) -> "SessionContributionProfile":
        return evaluate_session_profile(
            prompt,
            output,
            conversation=conversation,
            compressors=self.compressors if compressors is None else compressors,
            weights=weights,
            precomputed_baseline=self,
        )


@dataclass(frozen=True)
class SessionContribution:
    actual: InformationGain
    counterfactual_baseline: CounterfactualBaseline
    excess_gain_bits: float
    excess_contribution_ratio: float
    excess_gain_bits_per_token: float
    trajectory: TrajectoryFeatures | None
    prompt_guidance_ratio: float
    composite_score: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "actual": self.actual.to_dict(),
            "counterfactual_baseline": self.counterfactual_baseline.to_dict(),
            "excess_gain_bits": self.excess_gain_bits,
            "excess_contribution_ratio": self.excess_contribution_ratio,
            "excess_gain_bits_per_token": self.excess_gain_bits_per_token,
            "trajectory": self.trajectory.to_dict() if self.trajectory else None,
            "prompt_guidance_ratio": self.prompt_guidance_ratio,
            "composite_score": self.composite_score,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SessionContributionProfile:
    """Canonical session result and its shared diagnostic projections."""

    aggregate: SessionContribution
    actual: InformationGainProfile
    counterfactual_baseline: CounterfactualBaselineProfile


def _effective_compressors(
    compressors: Sequence[str] | None,
) -> tuple[str, ...]:
    configured = CompressionConfig.from_iterable(compressors).compressors
    return tuple(configured or DEFAULT_COMPRESSORS)


def information_gain_profile(
    prompt: str,
    output: str,
    compressors: Sequence[str] | None = None,
) -> InformationGainProfile:
    """Compute canonical and per-compressor metrics from one raw bit pass."""

    compressor_names = _effective_compressors(compressors)
    entries = compression_pair_profile(output, prompt, compressor_names)
    self_bits = float(
        statistics.fmean(entry.self_information_bits for entry in entries)
    )
    conditional_bits = float(
        statistics.fmean(entry.conditional_information_bits for entry in entries)
    )
    gain_bits = max(0.0, self_bits - conditional_bits)
    ratio = clamp(safe_divide(gain_bits, self_bits))
    output_tokens = count_tokens(output)
    aggregate = InformationGain(
        prompt=prompt,
        output=output,
        self_information_bits=self_bits,
        conditional_information_bits=conditional_bits,
        gain_bits=gain_bits,
        contribution_ratio=ratio,
        output_tokens=output_tokens,
        gain_bits_per_token=safe_divide(gain_bits, output_tokens),
    )
    per_compressor: dict[str, dict[str, float]] = {}
    for entry in entries:
        gain_one = max(
            0.0,
            entry.self_information_bits - entry.conditional_information_bits,
        )
        per_compressor[entry.compressor] = {
            "self_information_bits": entry.self_information_bits,
            "conditional_information_bits": entry.conditional_information_bits,
            "gain_bits": gain_one,
            "contribution_ratio": clamp(
                safe_divide(gain_one, entry.self_information_bits)
            ),
        }
    return InformationGainProfile(
        aggregate=aggregate,
        per_compressor=per_compressor,
    )


def information_gain(
    prompt: str,
    output: str,
    compressors: Sequence[str] | None = None,
) -> InformationGain:
    """Compute the canonical aggregate information gain for one pair."""

    return information_gain_profile(prompt, output, compressors).aggregate


def information_gain_per_compressor(
    prompt: str,
    output: str,
    compressors: Sequence[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Return diagnostic information-gain metrics for each compressor."""

    return information_gain_profile(prompt, output, compressors).per_compressor


def build_counterfactual_baseline_profile(
    samples: Iterable[CounterfactualSample],
    compressors: Sequence[str] | None = None,
) -> CounterfactualBaselineProfile:
    """Build aggregate and diagnostic CF baselines from shared pair profiles."""

    compressor_names = _effective_compressors(compressors)
    profiles = tuple(
        information_gain_profile(sample.prompt, sample.output, compressor_names)
        for sample in samples
        if sample.prompt.strip() and sample.output.strip()
    )
    if not profiles:
        return CounterfactualBaselineProfile(
            aggregate=CounterfactualBaseline(),
            samples=(),
            per_compressor_mean_ratios={name: 0.0 for name in compressor_names},
            compressors=compressor_names,
        )

    gains = [profile.aggregate for profile in profiles]
    aggregate = CounterfactualBaseline(
        samples=gains,
        mean_gain_bits=float(statistics.fmean(item.gain_bits for item in gains)),
        mean_contribution_ratio=float(
            statistics.fmean(item.contribution_ratio for item in gains)
        ),
        mean_gain_bits_per_token=float(
            statistics.fmean(item.gain_bits_per_token for item in gains)
        ),
    )
    per_compressor_mean_ratios: dict[str, float] = {}
    for name in compressor_names:
        if name in per_compressor_mean_ratios:
            continue
        per_compressor_mean_ratios[name] = float(
            statistics.fmean(
                profile.per_compressor[name]["contribution_ratio"]
                for profile in profiles
            )
        )
    return CounterfactualBaselineProfile(
        aggregate=aggregate,
        samples=profiles,
        per_compressor_mean_ratios=per_compressor_mean_ratios,
        compressors=compressor_names,
    )


def build_counterfactual_baseline(
    samples: Iterable[CounterfactualSample],
    compressors: Sequence[str] | None = None,
) -> CounterfactualBaseline:
    """Build the canonical aggregate counterfactual baseline."""

    return build_counterfactual_baseline_profile(samples, compressors).aggregate


def evaluate_session_profile(
    prompt: str,
    output: str,
    counterfactuals: Iterable[CounterfactualSample] | None = None,
    conversation: Sequence[Mapping[str, str]] | None = None,
    compressors: Sequence[str] | None = None,
    weights: ContributionWeights | None = None,
    precomputed_baseline: CounterfactualBaselineProfile | None = None,
) -> SessionContributionProfile:
    """Evaluate a session once and retain canonical/diagnostic projections."""

    compressor_names = _effective_compressors(compressors)
    if precomputed_baseline is not None:
        if counterfactuals is not None:
            raise ValueError(
                "counterfactuals and precomputed_baseline are mutually exclusive"
            )
        if precomputed_baseline.compressors != compressor_names:
            raise ValueError("precomputed baseline compressor configuration mismatch")
        baseline_profile = precomputed_baseline
    else:
        baseline_profile = build_counterfactual_baseline_profile(
            counterfactuals or [], compressor_names
        )

    normalized_weights = (weights or ContributionWeights()).normalized()
    actual_profile = information_gain_profile(prompt, output, compressor_names)
    actual = actual_profile.aggregate
    baseline = baseline_profile.aggregate
    excess_ratio = actual.contribution_ratio - baseline.mean_contribution_ratio
    excess_bits = actual.gain_bits - baseline.mean_gain_bits
    excess_per_token = actual.gain_bits_per_token - baseline.mean_gain_bits_per_token

    trajectory = None
    prompt_guidance_ratio = 0.0
    if conversation:
        turns = [turn.get("content", "") for turn in conversation if turn.get("content")]
        if len(turns) >= 2:
            trajectory = analyze_trajectory(turns, compressor_names)
        prompt_guidance_ratio = guidance_by_turn(conversation, compressor_names)

    trajectory_score = trajectory.composite_score if trajectory else prompt_guidance_ratio
    composite = (
        normalized_weights.absolute * actual.contribution_ratio
        + normalized_weights.excess * clamp(excess_ratio)
        + normalized_weights.trajectory
        * clamp(max(trajectory_score, prompt_guidance_ratio))
    )

    notes = [
        "Scores use compressed code length as a proxy for information, not raw token count.",
        "Counterfactuals should be generated by the same or a fixed surrogate model for fair comparison.",
    ]
    if not baseline.samples:
        notes.append("No counterfactual outputs were supplied; excess terms equal actual minus zero.")
    if not conversation:
        notes.append("No multi-turn conversation was supplied; trajectory score is unavailable.")

    aggregate = SessionContribution(
        actual=actual,
        counterfactual_baseline=baseline,
        excess_gain_bits=excess_bits,
        excess_contribution_ratio=excess_ratio,
        excess_gain_bits_per_token=excess_per_token,
        trajectory=trajectory,
        prompt_guidance_ratio=prompt_guidance_ratio,
        composite_score=clamp(composite),
        notes=notes,
    )
    return SessionContributionProfile(
        aggregate=aggregate,
        actual=actual_profile,
        counterfactual_baseline=baseline_profile,
    )


def evaluate_session(
    prompt: str,
    output: str,
    counterfactuals: Iterable[CounterfactualSample] | None = None,
    conversation: Sequence[Mapping[str, str]] | None = None,
    compressors: Sequence[str] | None = None,
    weights: ContributionWeights | None = None,
) -> SessionContribution:
    """Evaluate a whole human-AI generation session."""

    return evaluate_session_profile(
        prompt,
        output,
        counterfactuals=counterfactuals,
        conversation=conversation,
        compressors=compressors,
        weights=weights,
    ).aggregate
