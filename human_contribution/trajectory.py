"""Conversation trajectory features inspired by semantic-path analysis.

When external embedding models are unavailable, this module uses normalized
compression distance and simple lexical vectors. The names mirror the semantic
trajectory features in Hu et al. (2026), but the estimator is intentionally local
and dependency-free.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .compression import (
    clamp,
    compressed_bits,
    conditional_compressed_bits,
    normalized_compression_distance,
    safe_divide,
)


WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class TrajectoryFeatures:
    turn_count: int
    local_coherence: float
    global_coherence: float
    path_length: float
    convergence_ratio: float
    max_distance: float
    trajectory_curvature: float
    topic_switching_rate: float
    revisit_score: float
    semantic_spread: float
    exploration_efficiency: float
    composite_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_trajectory(
    turns: Sequence[str],
    compressors: Sequence[str] | None = None,
) -> TrajectoryFeatures:
    clean_turns = [turn.strip() for turn in turns if turn and turn.strip()]
    n = len(clean_turns)
    if n == 0:
        return _empty_features()
    if n == 1:
        return TrajectoryFeatures(
            turn_count=1,
            local_coherence=1.0,
            global_coherence=1.0,
            path_length=0.0,
            convergence_ratio=0.0,
            max_distance=0.0,
            trajectory_curvature=0.0,
            topic_switching_rate=0.0,
            revisit_score=1.0,
            semantic_spread=0.0,
            exploration_efficiency=0.0,
            composite_score=0.5,
        )

    distances = _pairwise_distances(clean_turns, compressors)
    consecutive = [distances[i][i + 1] for i in range(n - 1)]
    local_coherence = statistics.fmean(1.0 - value for value in consecutive)
    path_length = sum(consecutive)
    max_distance = max(max(row) for row in distances)

    whole = "\n".join(clean_turns)
    to_whole = [
        normalized_compression_distance(turn, whole, compressors) for turn in clean_turns
    ]
    global_coherence = statistics.fmean(1.0 - value for value in to_whole)
    semantic_spread = statistics.pstdev(to_whole) if len(to_whole) > 1 else 0.0

    early = clean_turns[: max(1, n // 2)]
    late = clean_turns[n // 2 :]
    early_dispersion = _mean_pairwise_distance(early, compressors)
    late_dispersion = _mean_pairwise_distance(late, compressors)
    convergence_ratio = safe_divide(
        early_dispersion - late_dispersion,
        early_dispersion,
        default=0.0,
    )

    revisit_score = _revisit_score(clean_turns, distances)
    topic_switching_rate = _topic_switching_rate(distances)
    curvature = _trajectory_curvature(clean_turns)
    exploration_efficiency = safe_divide(max_distance, path_length, default=0.0)

    composite = (
        0.25 * clamp(max_distance)
        + 0.20 * clamp(exploration_efficiency)
        + 0.20 * clamp(local_coherence)
        + 0.15 * clamp((convergence_ratio + 1.0) / 2.0)
        + 0.10 * clamp(revisit_score)
        + 0.10 * clamp(1.0 - safe_divide(curvature, math.pi, default=0.0))
    )

    return TrajectoryFeatures(
        turn_count=n,
        local_coherence=clamp(local_coherence),
        global_coherence=clamp(global_coherence),
        path_length=path_length,
        convergence_ratio=convergence_ratio,
        max_distance=clamp(max_distance),
        trajectory_curvature=curvature,
        topic_switching_rate=topic_switching_rate,
        revisit_score=clamp(revisit_score),
        semantic_spread=semantic_spread,
        exploration_efficiency=clamp(exploration_efficiency),
        composite_score=clamp(composite),
    )


def guidance_by_turn(
    conversation: Sequence[Mapping[str, str]],
    compressors: Sequence[str] | None = None,
) -> float:
    """Estimate how much each user turn reduces next assistant-turn uncertainty."""

    total_gain = 0.0
    total_base = 0.0
    history: list[str] = []
    pending_user: str | None = None

    for turn in conversation:
        role = (turn.get("role") or "").lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role in {"user", "human"}:
            pending_user = content
            history.append(f"user: {content}")
            continue
        if role in {"assistant", "ai", "model"} and pending_user is not None:
            before_prompt = "\n".join(history[:-1])
            with_prompt = "\n".join(history)
            base = conditional_compressed_bits(content, before_prompt, compressors)
            guided = conditional_compressed_bits(content, with_prompt, compressors)
            total_gain += max(0.0, base - guided)
            total_base += compressed_bits(content, compressors)
            history.append(f"assistant: {content}")
            pending_user = None
        else:
            history.append(f"{role or 'turn'}: {content}")

    return clamp(safe_divide(total_gain, total_base))


def _empty_features() -> TrajectoryFeatures:
    return TrajectoryFeatures(
        turn_count=0,
        local_coherence=0.0,
        global_coherence=0.0,
        path_length=0.0,
        convergence_ratio=0.0,
        max_distance=0.0,
        trajectory_curvature=0.0,
        topic_switching_rate=0.0,
        revisit_score=0.0,
        semantic_spread=0.0,
        exploration_efficiency=0.0,
        composite_score=0.0,
    )


def _pairwise_distances(
    turns: Sequence[str],
    compressors: Sequence[str] | None,
) -> list[list[float]]:
    n = len(turns)
    distances = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            distance = normalized_compression_distance(turns[i], turns[j], compressors)
            distances[i][j] = distance
            distances[j][i] = distance
    return distances


def _mean_pairwise_distance(
    turns: Sequence[str],
    compressors: Sequence[str] | None,
) -> float:
    if len(turns) < 2:
        return 0.0
    distances = []
    for i in range(len(turns)):
        for j in range(i + 1, len(turns)):
            distances.append(normalized_compression_distance(turns[i], turns[j], compressors))
    return float(statistics.fmean(distances)) if distances else 0.0


def _revisit_score(turns: Sequence[str], distances: Sequence[Sequence[float]]) -> float:
    n = len(turns)
    window = max(1, math.ceil(n * 0.3))
    early = range(0, window)
    late = range(max(0, n - window), n)
    best_similarity = 0.0
    for i in early:
        for j in late:
            if i == j:
                continue
            best_similarity = max(best_similarity, 1.0 - distances[i][j])
    return best_similarity


def _topic_switching_rate(distances: Sequence[Sequence[float]]) -> float:
    n = len(distances)
    if n < 2:
        return 0.0
    k = min(3, n)
    medoids = [round(i * (n - 1) / max(1, k - 1)) for i in range(k)]
    assignments = [0 for _ in range(n)]
    for _ in range(8):
        for i in range(n):
            assignments[i] = min(range(k), key=lambda c: distances[i][medoids[c]])
        new_medoids = medoids[:]
        for cluster in range(k):
            members = [i for i, item in enumerate(assignments) if item == cluster]
            if not members:
                continue
            new_medoids[cluster] = min(
                members,
                key=lambda candidate: sum(distances[candidate][other] for other in members),
            )
        if new_medoids == medoids:
            break
        medoids = new_medoids
    switches = sum(1 for i in range(n - 1) if assignments[i] != assignments[i + 1])
    return safe_divide(switches, n - 1)


def _trajectory_curvature(turns: Sequence[str]) -> float:
    vectors = [_word_vector(turn) for turn in turns]
    if len(vectors) < 3:
        return 0.0
    step_vectors = [_subtract(vectors[i + 1], vectors[i]) for i in range(len(vectors) - 1)]
    angles = []
    for i in range(len(step_vectors) - 1):
        norm_a = _norm(step_vectors[i])
        norm_b = _norm(step_vectors[i + 1])
        if norm_a == 0.0 or norm_b == 0.0:
            continue
        cosine = clamp(_dot(step_vectors[i], step_vectors[i + 1]) / (norm_a * norm_b), -1.0, 1.0)
        angles.append(math.acos(cosine))
    return float(statistics.fmean(angles)) if angles else 0.0


def _word_vector(text: str) -> Counter[str]:
    return Counter(token.lower() for token in WORD_RE.findall(text))


def _subtract(right: Counter[str], left: Counter[str]) -> dict[str, float]:
    keys = set(right) | set(left)
    return {key: float(right.get(key, 0) - left.get(key, 0)) for key in keys}


def _dot(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    keys = set(left) & set(right)
    return sum(left[key] * right[key] for key in keys)


def _norm(vector: Mapping[str, float]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))
