"""Strict Copilot Responses adapter for formal Experiment A generation."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Sequence

from .copilot_global_slots import CopilotGlobalSlotPool
from .multi_model_adapter import _parse_numbered_list

DEFAULT_BASE_URL = "http://127.0.0.1:44141"
DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_SLOT_CAPACITY = 4
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}


class NonRetryableResponseError(RuntimeError):
    """A completed transport attempt whose response must not be retried internally."""


def default_key_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "copilot-api-canary" / "2.2.15" / "api-home" / "client_api_key"


def _visible_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    parts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for block in item.get("content", []):
            if isinstance(block, dict) and block.get("type") == "output_text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _retry_after_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return min(60.0, max(0.0, float(value)))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            now = datetime.now(target.tzinfo or timezone.utc)
            return min(60.0, max(0.0, (target - now).total_seconds()))
        except Exception:
            return 0.0


class CopilotResponsesAdapter:
    """PromptOutputSampler-compatible adapter with cross-process concurrency slots."""

    def __init__(
        self,
        model_name: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        key_file: Path | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        reasoning_effort: str = "low",
        slot_capacity: int = DEFAULT_SLOT_CAPACITY,
        slot_root: Path | None = None,
        retries: int = 2,
        timeout_seconds: float = 180.0,
        sleep_seconds: float = 0.0,
    ) -> None:
        if base_url != DEFAULT_BASE_URL:
            raise ValueError(f"formal Copilot route must use {DEFAULT_BASE_URL}")
        if max_output_tokens != DEFAULT_MAX_OUTPUT_TOKENS:
            raise ValueError("formal Copilot route must use max_output_tokens=4096")
        if reasoning_effort != "low":
            raise ValueError("formal Copilot route must use reasoning_effort='low'")
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.key_file = key_file or default_key_file()
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.retries = int(retries)
        self.timeout_seconds = float(timeout_seconds)
        self.sleep_seconds = float(sleep_seconds)
        self.pool = CopilotGlobalSlotPool(root=slot_root, capacity=slot_capacity)
        self._last_response_metadata: dict[str, Any] | None = None

    def _read_key(self) -> str:
        value = self.key_file.read_text(encoding="utf-8").strip()
        if not value:
            raise RuntimeError(f"empty Copilot key file: {self.key_file}")
        return value

    def _call(self, prompt: str) -> tuple[str, dict[str, Any]]:
        key = self._read_key()
        payload = {
            "model": self.model_name,
            "max_output_tokens": self.max_output_tokens,
            "input": prompt,
            "reasoning": {"effort": self.reasoning_effort},
        }
        attempt_log: list[dict[str, Any]] = []
        last_error = ""
        for attempt in range(1, self.retries + 2):
            wait_after = 0.0
            try:
                lease = self.pool.acquire(
                    f"experiment-a:{self.model_name}:attempt-{attempt}"
                )
                with lease as acquisition:
                    started = time.perf_counter()
                    request = urllib.request.Request(
                        self.base_url + "/v1/responses",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Authorization": "Bearer " + key,
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    try:
                        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                            body = json.load(response)
                            http_status = int(response.status)
                    except urllib.error.HTTPError as exc:
                        http_status = int(exc.code)
                        wait_after = _retry_after_seconds(exc.headers.get("Retry-After"))
                        raise
                    latency = time.perf_counter() - started
                    record = {
                        "attempt": attempt,
                        "slot_index": acquisition.slot_index,
                        "slot_wait_seconds": round(acquisition.wait_seconds, 6),
                        "http_status": http_status,
                        "latency_seconds": round(latency, 6),
                    }
                    if body.get("model") != self.model_name:
                        raise NonRetryableResponseError(
                            f"model mismatch: requested={self.model_name!r}, returned={body.get('model')!r}"
                        )
                    if body.get("status") != "completed":
                        details = body.get("incomplete_details")
                        reason = details.get("reason") if isinstance(details, dict) else None
                        raise NonRetryableResponseError(
                            f"response status={body.get('status')!r}, reason={reason!r}"
                        )
                    text = _visible_text(body)
                    if not text.strip():
                        raise RuntimeError("completed response contained no visible text")
                    record["adopted"] = True
                    attempt_log.append(record)
                    metadata = {
                        "api": "responses",
                        "route": "copilot-2.2.15-formal",
                        "client": str(Path(__file__).resolve()),
                        "gateway": "local_slot",
                        "requested_model": self.model_name,
                        "returned_model": body.get("model"),
                        "response_id": body.get("id"),
                        "status": body.get("status"),
                        "incomplete_details": body.get("incomplete_details"),
                        "usage": body.get("usage"),
                        "max_output_tokens": self.max_output_tokens,
                        "reasoning_effort": self.reasoning_effort,
                        "attempts": attempt,
                        "attempt_log": attempt_log,
                        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                    return text, metadata
            except NonRetryableResponseError as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
                attempt_log.append({"attempt": attempt, "http_status": 200, "error_kind": type(exc).__name__})
                break
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
                attempt_log.append({"attempt": attempt, "http_status": int(exc.code), "error_kind": "http_status"})
                if exc.code not in RETRYABLE_HTTP:
                    break
            except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
                attempt_log.append({"attempt": attempt, "http_status": None, "error_kind": type(exc).__name__})
            if attempt <= self.retries:
                time.sleep(max(wait_after, min(8.0, 2.0 * attempt)))
        raise RuntimeError(
            f"Copilot Responses call failed for {self.model_name} after "
            f"{self.retries + 1} attempts: {last_error}"
        )

    def generate(self, prompt: str) -> str:
        self._last_response_metadata = None
        text, metadata = self._call(prompt)
        self._last_response_metadata = metadata
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        return text

    def reconstruct_prompts(self, output: str, n: int) -> Sequence[str]:
        self._last_response_metadata = None
        prompt = (
            "Infer plausible human prompts that could have produced the output below. "
            f"Return exactly {n} distinct numbered prompts and nothing else.\n\n"
            f"OUTPUT:\n{output}"
        )
        text, metadata = self._call(prompt)
        self._last_response_metadata = metadata
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        return _parse_numbered_list(text, n)

    def consume_last_response_metadata(self) -> dict[str, Any] | None:
        metadata = self._last_response_metadata
        self._last_response_metadata = None
        return metadata
