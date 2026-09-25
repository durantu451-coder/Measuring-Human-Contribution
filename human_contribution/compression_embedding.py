"""Hybrid metric: compression information gain plus embedding trajectory.

This module keeps the information-gain part compression-based and computes the
conversation trajectory in embedding space. The default model name is Qwen3
Embedding 4B, but the model is loaded lazily and can be replaced by any object
that implements the EmbeddingProvider protocol.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .compression import clamp, safe_divide
from .metrics import InformationGain, information_gain


DEFAULT_QWEN3_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-4B"


class EmbeddingProvider(Protocol):
    """Minimal interface for embedding backends."""

    model_name: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for each input text."""


@dataclass(frozen=True)
class EmbeddingTrajectoryFeatures:
    """Semantic trajectory features computed from embeddings."""

    model_name: str
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


@dataclass(frozen=True)
class CompressionEmbeddingResult:
    """Combined compression and embedding-based contribution result."""

    information_gain: InformationGain
    trajectory: EmbeddingTrajectoryFeatures | None
    prompt_output_alignment: float
    prompt_guidance_alignment: float
    hybrid_score: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "information_gain": self.information_gain.to_dict(),
            "trajectory": self.trajectory.to_dict() if self.trajectory else None,
            "prompt_output_alignment": self.prompt_output_alignment,
            "prompt_guidance_alignment": self.prompt_guidance_alignment,
            "hybrid_score": self.hybrid_score,
            "notes": self.notes,
        }


class Qwen3EmbeddingProvider:
    """Lazy Qwen3 embedding backend.

    The provider first tries `sentence_transformers`, which is the most compact
    runtime path. If that is unavailable, it falls back to Hugging Face
    `transformers` with mean pooling. Both paths require the model weights to be
    available locally or downloadable in the runtime environment.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_QWEN3_EMBEDDING_MODEL,
        device: str | None = None,
        batch_size: int = 8,
        normalize: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.normalize = normalize
        self._sentence_model: Any | None = None
        self._transformers_bundle: tuple[Any, Any, Any] | None = None

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        clean_texts = [text or "" for text in texts]
        if not clean_texts:
            return []
        try:
            return self._encode_sentence_transformers(clean_texts)
        except ImportError:
            return self._encode_transformers(clean_texts)

    def _encode_sentence_transformers(self, texts: Sequence[str]) -> list[list[float]]:
        if self._sentence_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError("sentence_transformers is unavailable.") from exc

            kwargs: dict[str, Any] = {}
            if self.device:
                kwargs["device"] = self.device
            self._sentence_model = SentenceTransformer(self.model_name, **kwargs)

        embeddings = self._sentence_model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return [_as_float_list(vector) for vector in embeddings]

    def _encode_transformers(self, texts: Sequence[str]) -> list[list[float]]:
        if self._transformers_bundle is None:
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer
            except ImportError as exc:
                raise RuntimeError(
                    "Qwen3EmbeddingProvider requires sentence-transformers or "
                    "transformers+torch. Install one path or pass a custom "
                    "EmbeddingProvider."
                ) from exc

            tokenizer = AutoTokenizer.from_pretrained(self.model_name, padding_side="left")
            model = AutoModel.from_pretrained(self.model_name)
            if self.device:
                model = model.to(self.device)
            model.eval()
            self._transformers_bundle = (torch, tokenizer, model)

        torch, tokenizer, model = self._transformers_bundle
        all_vectors: list[list[float]] = []
        with torch.no_grad():
            for start in range(0, len(texts), self.batch_size):
                batch = list(texts[start : start + self.batch_size])
                encoded = tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    return_tensors="pt",
                )
                if self.device:
                    encoded = {key: value.to(self.device) for key, value in encoded.items()}
                outputs = model(**encoded)
                hidden = outputs.last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
                if self.normalize:
                    pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                all_vectors.extend(_as_float_list(vector) for vector in pooled.cpu())
        return all_vectors


class APIScriptEmbeddingProvider:
    """Embedding backend that shells out to an external API client script.

    This repository does not ship the client script; point ``api_script`` at
    your own OpenAI-compatible ``embed`` helper. For fully local runs use
    ``LocalTransformersEmbeddingProvider`` or ``Qwen3EmbeddingProvider`` instead.

    Parameters
    ----------
    model_name:
        Embedding model ID passed to the API (default ``"text-embedding-3-small"``).
    sleep_seconds:
        Seconds to sleep between individual calls to stay under RPM limits.
    api_script:
        Path to the external client. Defaults to ``clients/client_multi_provider.py``
        relative to the repository root, which is absent from this release.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        sleep_seconds: float = 1.0,
        api_script: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.sleep_seconds = sleep_seconds
        self._api_script = api_script or str(
            Path(__file__).resolve().parent.parent / "clients" / "client_multi_provider.py"
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for text in texts:
            try:
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                proc = subprocess.run(
                    [
                        sys.executable, self._api_script,
                        "--timeout", "120",
                        "embed", text,
                        "--model", self.model_name,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    timeout=180,
                )
                if proc.returncode != 0:
                    stderr = proc.stderr.strip() or "unknown error"
                    raise RuntimeError(
                        f"Embedding API call failed (rc={proc.returncode}): {stderr}"
                    )
                response = json.loads(proc.stdout)
                embedding = response["data"][0]["embedding"]
                result.append([float(v) for v in embedding])
            except Exception:
                raise
            time.sleep(self.sleep_seconds)
        return result


class HashingEmbeddingProvider:
    """Deterministic dependency-free provider for tests and offline smoke runs."""

    def __init__(self, dimensions: int = 256) -> None:
        self.model_name = f"hashing-{dimensions}"
        self.dimensions = dimensions

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [_normalize(_hash_embedding(text, self.dimensions)) for text in texts]


def evaluate_compression_embedding(
    prompt: str,
    output: str,
    conversation: Sequence[Mapping[str, str]] | Sequence[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    compressors: Sequence[str] | None = None,
) -> CompressionEmbeddingResult:
    """Compute compression gain and embedding trajectory together.

    Uses ``Qwen3EmbeddingProvider`` by default; pass ``embedding_provider`` to
    override (e.g. ``HashingEmbeddingProvider`` for shape tests).
    """

    provider = embedding_provider or Qwen3EmbeddingProvider()
    info_gain = information_gain(prompt, output, compressors)

    prompt_output_alignment = _prompt_output_alignment(prompt, output, provider)
    prompt_guidance_alignment = 0.0
    trajectory = None

    turns = _extract_turns(conversation)
    if len(turns) >= 2:
        trajectory = embedding_semantic_trajectory(turns, provider)
    if conversation and not isinstance(conversation[0], str):  # type: ignore[index]
        prompt_guidance_alignment = embedding_prompt_guidance_alignment(
            conversation, provider  # type: ignore[arg-type]
        )

    trajectory_score = trajectory.composite_score if trajectory else 0.0
    hybrid_score = (
        0.55 * info_gain.contribution_ratio
        + 0.20 * clamp(prompt_output_alignment)
        + 0.15 * clamp(prompt_guidance_alignment)
        + 0.10 * clamp(trajectory_score)
    )

    notes = [
        "Compression information gain remains the primary contribution signal.",
        "Embedding trajectory uses cosine geometry; default backend is Qwen/Qwen3-Embedding-4B.",
        "For comparable experiments, freeze the embedding model, generation model, and sampling settings.",
    ]

    return CompressionEmbeddingResult(
        information_gain=info_gain,
        trajectory=trajectory,
        prompt_output_alignment=prompt_output_alignment,
        prompt_guidance_alignment=prompt_guidance_alignment,
        hybrid_score=clamp(hybrid_score),
        notes=notes,
    )


def embedding_semantic_trajectory(
    turns: Sequence[str],
    embedding_provider: EmbeddingProvider | None = None,
) -> EmbeddingTrajectoryFeatures:
    """Compute semantic trajectory features from Qwen3 or compatible embeddings."""

    provider = embedding_provider or Qwen3EmbeddingProvider()
    clean_turns = [turn.strip() for turn in turns if turn and turn.strip()]
    n = len(clean_turns)
    if n == 0:
        return _empty_features(provider.model_name)
    if n == 1:
        return EmbeddingTrajectoryFeatures(
            model_name=provider.model_name,
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

    vectors = [_normalize(vector) for vector in provider.encode(clean_turns)]
    distances = _pairwise_cosine_distances(vectors)
    consecutive = [distances[i][i + 1] for i in range(n - 1)]

    local_coherence = statistics.fmean(1.0 - distance for distance in consecutive)
    path_length = sum(consecutive)
    max_distance = max(max(row) for row in distances)

    centroid = _normalize(_mean_vector(vectors))
    centroid_similarities = [_cosine(vector, centroid) for vector in vectors]
    global_coherence = statistics.fmean(centroid_similarities)
    centroid_distances = [_euclidean_distance(vector, centroid) for vector in vectors]
    semantic_spread = (
        statistics.pstdev(centroid_distances) if len(centroid_distances) > 1 else 0.0
    )

    early_vectors = vectors[: max(1, n // 2)]
    late_vectors = vectors[n // 2 :]
    early_dispersion = _mean_pairwise_cosine_distance(early_vectors)
    late_dispersion = _mean_pairwise_cosine_distance(late_vectors)
    convergence_ratio = safe_divide(
        early_dispersion - late_dispersion,
        early_dispersion,
        default=0.0,
    )

    curvature = _embedding_trajectory_curvature(vectors)
    topic_switching_rate = _topic_switching_rate(distances)
    revisit_score = _revisit_score(distances)
    exploration_efficiency = safe_divide(max_distance, path_length, default=0.0)
    composite = _trajectory_composite(
        max_distance=max_distance,
        exploration_efficiency=exploration_efficiency,
        local_coherence=local_coherence,
        convergence_ratio=convergence_ratio,
        revisit_score=revisit_score,
        curvature=curvature,
    )

    return EmbeddingTrajectoryFeatures(
        model_name=provider.model_name,
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


def embedding_prompt_guidance_alignment(
    conversation: Sequence[Mapping[str, str]],
    embedding_provider: EmbeddingProvider | None = None,
) -> float:
    """Average semantic alignment between each user turn and the next response."""

    provider = embedding_provider or Qwen3EmbeddingProvider()
    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None

    for turn in conversation:
        role = (turn.get("role") or "").lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role in {"user", "human"}:
            pending_user = content
        elif role in {"assistant", "ai", "model"} and pending_user is not None:
            pairs.append((pending_user, content))
            pending_user = None

    if not pairs:
        return 0.0

    texts = [item for pair in pairs for item in pair]
    vectors = [_normalize(vector) for vector in provider.encode(texts)]
    similarities = []
    for index in range(0, len(vectors), 2):
        similarities.append(_cosine(vectors[index], vectors[index + 1]))
    return clamp(statistics.fmean(similarities))


def _prompt_output_alignment(
    prompt: str,
    output: str,
    provider: EmbeddingProvider,
) -> float:
    prompt_vector, output_vector = [_normalize(vector) for vector in provider.encode([prompt, output])]
    return clamp(_cosine(prompt_vector, output_vector))


def _extract_turns(
    conversation: Sequence[Mapping[str, str]] | Sequence[str] | None,
) -> list[str]:
    if conversation is None:
        return []
    if not conversation:
        return []
    first = conversation[0]
    if isinstance(first, str):
        return [turn for turn in conversation if isinstance(turn, str)]
    return [
        str(turn.get("content", ""))
        for turn in conversation
        if isinstance(turn, Mapping) and turn.get("content")
    ]


def _empty_features(model_name: str) -> EmbeddingTrajectoryFeatures:
    return EmbeddingTrajectoryFeatures(
        model_name=model_name,
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


def _pairwise_cosine_distances(vectors: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(vectors)
    distances = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            distance = 1.0 - _cosine(vectors[i], vectors[j])
            distance = clamp(distance)
            distances[i][j] = distance
            distances[j][i] = distance
    return distances


def _mean_pairwise_cosine_distance(vectors: Sequence[Sequence[float]]) -> float:
    if len(vectors) < 2:
        return 0.0
    values = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            values.append(1.0 - _cosine(vectors[i], vectors[j]))
    return float(statistics.fmean(values)) if values else 0.0


def _embedding_trajectory_curvature(vectors: Sequence[Sequence[float]]) -> float:
    if len(vectors) < 3:
        return 0.0
    steps = [_subtract(vectors[i + 1], vectors[i]) for i in range(len(vectors) - 1)]
    angles = []
    for i in range(len(steps) - 1):
        norm_a = _norm(steps[i])
        norm_b = _norm(steps[i + 1])
        if norm_a == 0.0 or norm_b == 0.0:
            continue
        cosine = clamp(_dot(steps[i], steps[i + 1]) / (norm_a * norm_b), -1.0, 1.0)
        angles.append(math.acos(cosine))
    return float(statistics.fmean(angles)) if angles else 0.0


def _topic_switching_rate(distances: Sequence[Sequence[float]]) -> float:
    n = len(distances)
    if n < 2:
        return 0.0
    k = min(3, n)
    medoids = [round(i * (n - 1) / max(1, k - 1)) for i in range(k)]
    assignments = [0 for _ in range(n)]
    for _ in range(10):
        for i in range(n):
            assignments[i] = min(range(k), key=lambda c: distances[i][medoids[c]])
        new_medoids = medoids[:]
        for cluster in range(k):
            members = [i for i, value in enumerate(assignments) if value == cluster]
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


def _revisit_score(distances: Sequence[Sequence[float]]) -> float:
    n = len(distances)
    if n < 2:
        return 0.0
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


def _trajectory_composite(
    max_distance: float,
    exploration_efficiency: float,
    local_coherence: float,
    convergence_ratio: float,
    revisit_score: float,
    curvature: float,
) -> float:
    return (
        0.25 * clamp(max_distance)
        + 0.20 * clamp(exploration_efficiency)
        + 0.20 * clamp(local_coherence)
        + 0.15 * clamp((convergence_ratio + 1.0) / 2.0)
        + 0.10 * clamp(revisit_score)
        + 0.10 * clamp(1.0 - safe_divide(curvature, math.pi, default=0.0))
    )


def _hash_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0 for _ in range(dimensions)]
    for token in text.lower().split():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        vector[index] += sign
    return vector


def _as_float_list(vector: Any) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        return []
    width = len(vectors[0])
    return [statistics.fmean(vector[i] for vector in vectors) for i in range(width)]


def _normalize(vector: Sequence[float]) -> list[float]:
    norm = _norm(vector)
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def _subtract(right: Sequence[float], left: Sequence[float]) -> list[float]:
    return [float(r) - float(l) for r, l in zip(right, left)]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(l) * float(r) for l, r in zip(left, right))


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    denom = _norm(left) * _norm(right)
    if denom == 0.0:
        return 0.0
    return clamp(_dot(left, right) / denom, -1.0, 1.0)


def _euclidean_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((float(l) - float(r)) ** 2 for l, r in zip(left, right)))
