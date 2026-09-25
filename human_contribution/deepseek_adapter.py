"""DeepSeek adapter implementing the PromptOutputSampler protocol.

Uses the DeepSeek API (https://api.deepseek.com/v1/chat/completions) for
prompt reconstruction and output generation.  Reads the API key from the
ANTHROPIC_AUTH_TOKEN environment variable at call time — the key is never
written to disk or stored in any file.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.error
from typing import Sequence

from .adapters import PromptOutputSampler

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_URL = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.7


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_AUTH_TOKEN environment variable is not set. "
            "Set it to your DeepSeek API key."
        )
    return key


def _deepseek_chat(
    messages: list[dict[str, str]],
    temperature: float = DEFAULT_TEMPERATURE,
    model: str = DEFAULT_MODEL,
) -> str:
    """Send a chat request to the DeepSeek API; return the response text."""
    api_key = _get_api_key()
    payload = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature}
    ).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_CHAT_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"DeepSeek API returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to reach DeepSeek API at {DEEPSEEK_CHAT_URL}: {exc}"
        ) from exc

    return body["choices"][0]["message"]["content"]


_NUMBERED_RE = re.compile(r"^\d+[\.\)\-:：]\s*")


def _parse_numbered_list(text: str, expected: int) -> list[str]:
    """Parse a numbered-list response (e.g. '1. foo') into individual items."""
    prompts: list[str] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _NUMBERED_RE.match(line)
        if match:
            prompts.append(line[match.end() :].strip())
        else:
            prompts.append(line)
    return prompts[:expected]


class DeepSeekAdapter:
    """PromptOutputSampler backed by the DeepSeek API.

    Reads *ANTHROPIC_AUTH_TOKEN* from the environment at every call; the key
    is never stored as an instance attribute or written to disk.

    Parameters
    ----------
    model:
        DeepSeek model name (default ``"deepseek-chat"``).
    temperature:
        Sampling temperature, fixed at ``0.7`` by default.
    """

    model_name: str

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> None:
        self.model_name = model
        self.model = model
        self.temperature = temperature

    # -- PromptOutputSampler protocol --------------------------------

    def reconstruct_prompts(self, output: str, n: int) -> Sequence[str]:
        """Infer *n* plausible human prompts that could have produced *output*."""
        if n <= 0:
            return []
        if not output.strip():
            return [""] * n

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Given an AI-generated output, "
                    "infer plausible human prompts that could have produced it. "
                    "Return exactly the requested number of distinct prompts, "
                    "each on its own line prefixed with a number (1. 2. etc.). "
                    "Make prompts diverse in style, length, and specificity. "
                    "Output ONLY the numbered list, no other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"AI-generated output:\n\n---\n{output}\n---\n\n"
                    f"Infer {n} plausible human prompts that could have produced "
                    f"this output. Return exactly {n} numbered prompts."
                ),
            },
        ]

        response = _deepseek_chat(
            messages, temperature=self.temperature, model=self.model
        )
        return _parse_numbered_list(response, n)

    def generate(self, prompt: str) -> str:
        """Generate one output from the fixed model for *prompt*."""
        if not prompt.strip():
            return ""

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful AI assistant. Generate a detailed, "
                    "coherent response to the user's prompt."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        return _deepseek_chat(
            messages, temperature=self.temperature, model=self.model
        )


# Convenience alias
DeepSeekSampler = DeepSeekAdapter
