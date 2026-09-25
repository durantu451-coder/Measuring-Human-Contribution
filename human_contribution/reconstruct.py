"""Lightweight prompt reconstruction helpers.

These helpers are not a replacement for an LLM-based inverse-prompt model. They
provide deterministic candidates so the rest of the pipeline can be exercised
offline, and they define the interface expected from stronger model adapters.
"""

from __future__ import annotations

import re
from collections import Counter


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|\d+(?:\.\d+)?", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def infer_prompt_candidates(output: str, n: int = 5) -> list[str]:
    """Infer prompt candidates from an output using the DeepSeek API.

    Requires the ``ANTHROPIC_AUTH_TOKEN`` environment variable to be set to a
    valid DeepSeek API key.  The key is read at call time and never stored.

    Returns a list of *n* plausible human prompts reconstructed from *output*.
    """

    from .deepseek_adapter import DeepSeekAdapter

    output = output.strip()
    if not output or n <= 0:
        return []

    adapter = DeepSeekAdapter()
    return list(adapter.reconstruct_prompts(output, n))


def _keywords(text: str, limit: int) -> list[str]:
    counts: Counter[str] = Counter()
    for token in WORD_RE.findall(text.lower()):
        if len(token) < 3 or token in STOPWORDS:
            continue
        counts[token] += 1
    return [word for word, _ in counts.most_common(limit)]


def _first_sentence(text: str) -> str:
    parts = SENTENCE_RE.split(text.strip())
    if not parts:
        return text[:160]
    sentence = parts[0].strip()
    return sentence[:180] + ("..." if len(sentence) > 180 else "")
