"""Multi-model adapter implementing the PromptOutputSampler protocol.

Delegates generate() to pluggable standalone API client scripts and
reconstruct_prompts() via a system prompt sent through the same generate
pipeline.

This release does not ship those client scripts: they are private,
credential-bearing wrappers around a third-party inference router. Point the
backend script paths below at your own OpenAI-compatible client to use this
adapter. See the README section "External generation clients".
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# Fix Windows GBK encoding crashes on emoji in API output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .adapters import PromptOutputSampler

AVAILABLE_MODELS = {
    "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra",
    "gpt-5.5", "gpt-5.5-2", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
    "gpt-5.4-pro", "gpt-5.3-codex", "gpt-5-mini",
    "claude-sonnet-5", "claude-opus-5",
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
    "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-pro-preview",
    "grok-4.5", "mai-code-1-flash-picker",
}
DEFAULT_MODEL = "gpt-5.6-sol"


def _api_script() -> str:
    script = os.environ.get("HC_CLIENT_SCRIPT")
    if script:
        return script
    return str(Path(__file__).resolve().parent.parent / "clients" / "client_multi_provider.py")


def _new_gpt_api_script() -> str:
    """Return the GPT client with automatic gateway failover."""
    return str(Path(__file__).resolve().parent.parent / "clients" / "client_gpt.py")


def _backend_b_gpt_api_script() -> str:
    """Return the backend_b client that supports explicit gateway pinning."""
    return str(Path(__file__).resolve().parent.parent / "clients" / "client_gpt_pinned.py")


def _backend_c_gpt_api_script() -> str:
    """Return the replacement GPT client with three-origin failover."""
    return str(Path(__file__).resolve().parent.parent / "clients" / "client_gpt_multi_origin.py")


def _legacy_new_api_script() -> str:
    """Return the legacy multi-provider client used by use_alt_backend."""
    return str(Path(__file__).resolve().parent.parent / "clients" / "client_legacy.py")


# GPT models route to the Responses API client. All other models stay on the
# old multi-provider client unless use_alt_backend is explicitly requested.
_NEW_API_MODELS = {
    "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra",
    "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5-mini",
    "gpt-5.5-2", "gpt-5.4-nano", "gpt-5.4-pro",
}


def _extract_responses_text(response: Any) -> str:
    """Extract visible text from Responses, Messages, or Chat JSON."""
    if not isinstance(response, dict):
        return ""
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct

    texts: list[str] = []

    # Anthropic Messages shape.
    content = response.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
    if texts:
        return "\n".join(texts)

    # OpenAI Chat Completions shape.
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                chat_content = message.get("content")
                if isinstance(chat_content, str) and chat_content:
                    return chat_content
            choice_text = first.get("text")
            if isinstance(choice_text, str) and choice_text:
                return choice_text

    # OpenAI Responses shape.
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
    return "\n".join(texts)


def _responses_metadata(
    response: dict[str, Any], *, requested_model: str, script: str,
    route: str, gateway: int | None, max_output_tokens: int,
    reasoning_effort: str, instructions: str | None,
) -> dict[str, Any]:
    """Build the compact provenance record persisted by Experiments A and B."""
    return {
        "api": "responses",
        "client": str(Path(script).resolve()),
        "route": route,
        "gateway": gateway if gateway is not None else "auto",
        "requested_model": requested_model,
        "returned_model": response.get("model"),
        "response_id": response.get("id"),
        "status": response.get("status"),
        "incomplete_details": response.get("incomplete_details"),
        "usage": response.get("usage"),
        "max_output_tokens": max_output_tokens,
        "reasoning_effort": reasoning_effort,
        "instructions_sha256": (
            hashlib.sha256(instructions.encode("utf-8")).hexdigest()
            if instructions is not None else None
        ),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _verified_portable_response(
    response: Any, *, requested_model: str, script: str, max_output_tokens: int,
) -> tuple[str, dict[str, Any]]:
    """Validate a force-new non-GPT response and return text plus provenance."""
    if not isinstance(response, dict):
        raise RuntimeError("portable API returned a non-object response")
    returned_model = response.get("model")
    if returned_model != requested_model:
        raise RuntimeError(
            f"portable API model mismatch: requested={requested_model!r}, "
            f"returned={returned_model!r}"
        )

    endpoint: str
    terminal_field: str
    terminal_value: Any
    if "status" in response or "output" in response:
        endpoint = "responses"
        terminal_field = "status"
        terminal_value = response.get("status")
        if terminal_value != "completed":
            details = response.get("incomplete_details")
            reason = details.get("reason") if isinstance(details, dict) else None
            raise RuntimeError(
                f"Responses status={terminal_value!r}, reason={reason!r}"
            )
    elif "stop_reason" in response or "content" in response:
        endpoint = "messages"
        terminal_field = "stop_reason"
        terminal_value = response.get("stop_reason")
        if terminal_value not in {"end_turn", "stop_sequence"}:
            raise RuntimeError(f"Messages stop_reason={terminal_value!r}")
    elif isinstance(response.get("choices"), list):
        endpoint = "chat_completions"
        terminal_field = "finish_reason"
        choices = response["choices"]
        if not choices or not isinstance(choices[0], dict):
            raise RuntimeError("Chat response contained no usable choice")
        terminal_value = choices[0].get("finish_reason")
        if terminal_value != "stop":
            raise RuntimeError(f"Chat finish_reason={terminal_value!r}")
    else:
        raise RuntimeError("portable API response shape is ambiguous")

    text = _extract_responses_text(response)
    if not text.strip():
        raise RuntimeError(f"{endpoint} response contained no visible text")
    metadata = {
        "api": endpoint,
        "client": str(Path(script).resolve()),
        "gateway": "auto",
        "requested_model": requested_model,
        "returned_model": returned_model,
        "response_id": response.get("id"),
        "status": response.get("status"),
        "stop_reason": response.get("stop_reason"),
        "finish_reason": terminal_value if terminal_field == "finish_reason" else None,
        "terminal_field": terminal_field,
        "terminal_value": terminal_value,
        "incomplete_details": response.get("incomplete_details"),
        "usage": response.get("usage"),
        "max_output_tokens": max_output_tokens,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return text, metadata


_CONTINUATION_MARKER = "<<<HC_CONTINUATION_7F3A>>>"


def _continuation_prompt(original_prompt: str, response_so_far: str) -> str:
    """Build a continuation request with a machine-verifiable start marker."""
    return (
        "Continue the response below exactly where it stopped. Start your output "
        f"with exactly {_CONTINUATION_MARKER} and then immediately continue the "
        "unfinished response. HARD REQUIREMENT: the continuation after the marker "
        "must be at most 600 words, must reach a natural conclusion, and must end "
        "with a complete sentence before the token limit. Compress or omit lower-priority "
        "details as needed. Do not restart, summarize prior sections, repeat prior "
        "sections, or add any other preface.\n\n"
        f"ORIGINAL REQUEST:\n{original_prompt}\n\n"
        f"RESPONSE SO FAR:\n{response_so_far}"
    )


def _merge_continuation(first: str, second: str) -> str:
    """Validate the continuation marker and reject an obvious full restart."""
    candidate = second.lstrip()
    if not candidate.startswith(_CONTINUATION_MARKER):
        raise RuntimeError("continuation did not emit the required boundary marker")
    continuation = candidate[len(_CONTINUATION_MARKER):]
    if not continuation.strip():
        raise RuntimeError("continuation was empty after its boundary marker")

    # A common failure mode is restarting the answer from its first paragraph.
    # Reject an exact normalized prefix repeat; natural local overlap at the seam
    # is allowed because it is not the beginning of the full response.
    normalize = lambda value: " ".join(value.split()).casefold()
    first_prefix = normalize(first)[:160]
    continuation_prefix = normalize(continuation)[:500]
    if len(first_prefix) >= 80 and first_prefix[:80] in continuation_prefix:
        raise RuntimeError("continuation restarted from the beginning of the response")
    return first + continuation


def _call_api(
    prompt: str, model: str, timeout: int = 60, retries: int = 3,
    use_alt_backend: bool = False, backend_pin: int | None = None,
    gpt_route: str | None = None,
    max_output_tokens: int = 4096,
    accept_incomplete_at_limit: bool = False,
    instructions: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Invoke the appropriate client and return text plus call provenance.

    GPT calls request full JSON. Completed responses are always accepted; a partial
    response at ``max_output_tokens`` is accepted only when explicitly requested
    by the segmented-generation path. Other incomplete/failed responses raise.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    is_gpt_route = model in _NEW_API_MODELS
    if gpt_route not in (None, "backend_b", "backend_c"):
        raise ValueError("gpt_route must be None, 'backend_b', or 'backend_c'")
    if gpt_route is not None and not is_gpt_route:
        raise ValueError("gpt_route can only be used with GPT models")

    use_new_api = is_gpt_route or use_alt_backend
    reasoning_effort = "low"
    resolved_gpt_route: str | None = None
    if is_gpt_route:
        if gpt_route == "backend_c":
            if backend_pin is not None:
                raise ValueError("backend_c uses automatic failover and cannot pin backend_pin")
            script = _backend_c_gpt_api_script()
            resolved_gpt_route = "backend_c"
        elif gpt_route == "backend_b":
            if backend_pin is None:
                raise ValueError("backend_b requires an explicit backend_pin")
            script = _backend_b_gpt_api_script()
            resolved_gpt_route = "backend_b"
        elif backend_pin is not None:
            script = _backend_b_gpt_api_script()
            resolved_gpt_route = "backend_b"
        else:
            script = _new_gpt_api_script()
            resolved_gpt_route = "new_api"
    elif use_alt_backend:
        script = _legacy_new_api_script()
    else:
        script = _api_script()

    if instructions is not None:
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError("instructions must be a non-empty string or None")
        if resolved_gpt_route != "backend_c":
            raise ValueError("generation instructions are supported only on backend_c")

    args = [
        sys.executable,
        script,
        "--timeout", str(timeout),
    ]
    if is_gpt_route and resolved_gpt_route == "backend_b":
        args.extend(["--gateway", str(backend_pin)])

    # Use stdin for portable clients so long prompts and continuation context
    # cannot exceed Windows' ~32K process command-line limit.
    prompt_stdin = use_alt_backend or resolved_gpt_route == "backend_c"
    if prompt_stdin:
        if is_gpt_route:
            args.extend(["call", "--prompt-file", "-"])
        else:
            args.extend(["ask", "--prompt-file", "-"])
    else:
        args.extend(["ask", prompt])
    args.extend(["--model", model])
    if use_new_api:
        args.extend(["--reasoning-effort", reasoning_effort])
        args.extend(["--max-output-tokens", str(max_output_tokens)])
    if instructions is not None:
        args.extend(["--instructions", instructions])
    if is_gpt_route or use_alt_backend:
        args.append("--json")

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            process_timeout = (
                timeout * 3 + 30
                if resolved_gpt_route in {"backend_b", "backend_c"}
                else timeout + 30
            )
            run_kwargs: dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "env": env,
                "timeout": process_timeout,
            }
            if prompt_stdin:
                run_kwargs["input"] = prompt
            proc = subprocess.run(args, **run_kwargs)
            stdout = proc.stdout.strip()
            if proc.returncode == 0 and stdout:
                if is_gpt_route or use_alt_backend:
                    try:
                        response = json.loads(stdout)
                    except json.JSONDecodeError as exc:
                        last_error = f"invalid JSON response from API client: {exc}"
                    else:
                        if not is_gpt_route:
                            try:
                                return _verified_portable_response(
                                    response,
                                    requested_model=model,
                                    script=script,
                                    max_output_tokens=max_output_tokens,
                                )
                            except RuntimeError as exc:
                                last_error = str(exc)
                        else:
                            metadata = _responses_metadata(
                                response,
                                requested_model=model,
                                script=script,
                                route=resolved_gpt_route or "unknown",
                                gateway=backend_pin,
                                max_output_tokens=max_output_tokens,
                                reasoning_effort=reasoning_effort,
                                instructions=instructions,
                            )
                            returned_model = response.get("model")
                            if returned_model != model:
                                last_error = (
                                    f"Responses API model mismatch: requested={model!r}, "
                                    f"returned={returned_model!r}"
                                )
                            else:
                                status = response.get("status")
                                details = response.get("incomplete_details")
                                reason = details.get("reason") if isinstance(details, dict) else None
                                usage = response.get("usage")
                                output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
                                output_text = _extract_responses_text(response)
                                if status == "completed":
                                    if output_text.strip():
                                        return output_text, metadata
                                    last_error = "completed Responses result contained no output_text"
                                elif (
                                    accept_incomplete_at_limit
                                    and status == "incomplete"
                                    and reason == "max_output_tokens"
                                    and output_text.strip()
                                ):
                                    return output_text, metadata
                                else:
                                    last_error = (
                                        f"Responses API status={status!r}, reason={reason!r}, "
                                        f"output_tokens={output_tokens!r}"
                                    )
                else:
                    # Preserve the legacy text-only path used by Experiment A.
                    return stdout, {
                        "api": "text_only",
                        "client": str(Path(script).resolve()),
                        "gateway": None,
                        "requested_model": model,
                        "returned_model": None,
                        "response_id": None,
                        "status": "unverified_text_response",
                        "incomplete_details": None,
                        "usage": None,
                        "max_output_tokens": None,
                        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
            else:
                last_error = proc.stderr.strip() or (
                    "empty output" if proc.returncode == 0 else f"rc={proc.returncode}"
                )
        except subprocess.TimeoutExpired:
            last_error = "subprocess timeout"
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            # Respect Retry-After header from 429 responses.
            import re as _re
            match = _re.search(r"Retry-After:\s*(\d+)", last_error)
            wait = max(1, int(match.group(1))) if match else 1
            wait = min(wait, 60)
            print(
                f"    [API retry {attempt}/{retries} in {wait}s: {last_error[:120]}]",
                flush=True,
            )
            time.sleep(wait)
    raise RuntimeError(f"API ask failed for '{model}' after {retries} tries: {last_error}")


class MultiModelAdapter:
    """PromptOutputSampler backed by the multi-model API."""

    model_name: str

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        sleep_seconds: float = 1.0,
        reconstruct_model: str | None = None,
        api_timeout: int = 60,
        api_retries: int = 3,
        use_alt_backend: bool = False,
        backend_pin: int | None = None,
        gpt_route: str | None = None,
        max_output_tokens: int = 4096,
        segment_output_tokens: int | None = None,
        generation_instructions: str | None = None,
    ) -> None:
        if model_name not in AVAILABLE_MODELS:
            raise ValueError(
                f"Unknown model '{model_name}'. Available: {sorted(AVAILABLE_MODELS)}"
            )
        if backend_pin not in (None, 1, 2, 3):
            raise ValueError("backend_pin must be None, 1, 2, or 3")
        if backend_pin is not None and model_name not in _NEW_API_MODELS:
            raise ValueError("backend_pin can only be used with GPT models")
        if gpt_route not in (None, "backend_b", "backend_c"):
            raise ValueError("gpt_route must be None, 'backend_b', or 'backend_c'")
        if gpt_route is not None and model_name not in _NEW_API_MODELS:
            raise ValueError("gpt_route can only be used with GPT models")
        if gpt_route == "backend_b" and backend_pin is None:
            raise ValueError("backend_b requires an explicit backend_pin")
        if gpt_route == "backend_c" and backend_pin is not None:
            raise ValueError("backend_c uses automatic failover and cannot pin backend_pin")
        if generation_instructions is not None:
            if not isinstance(generation_instructions, str) or not generation_instructions.strip():
                raise ValueError("generation_instructions must be a non-empty string or None")
            if gpt_route != "backend_c":
                raise ValueError("generation_instructions require gpt_route='backend_c'")
        if isinstance(api_retries, bool) or not isinstance(api_retries, int) or api_retries < 1:
            raise ValueError("api_retries must be a positive integer")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if segment_output_tokens is not None:
            if model_name not in _NEW_API_MODELS:
                raise ValueError("segment_output_tokens can only be used with GPT models")
            if segment_output_tokens <= 0:
                raise ValueError("segment_output_tokens must be positive")
            if segment_output_tokens * 2 != max_output_tokens:
                raise ValueError("segment_output_tokens must equal half of max_output_tokens")
        self.model_name = model_name
        self.sleep_seconds = sleep_seconds
        self.reconstruct_model = reconstruct_model or model_name
        self.api_timeout = api_timeout
        self.api_retries = api_retries
        self.use_alt_backend = use_alt_backend
        self.backend_pin = backend_pin
        self.gpt_route = gpt_route
        self.max_output_tokens = max_output_tokens
        self.segment_output_tokens = segment_output_tokens
        self.generation_instructions = generation_instructions
        self._last_response_metadata: dict[str, Any] | None = None

    def consume_last_response_metadata(self) -> dict[str, Any] | None:
        """Return and clear metadata for the most recent successful API call."""
        metadata = self._last_response_metadata
        self._last_response_metadata = None
        return metadata

    # -- PromptOutputSampler protocol -----------------------------------

    def reconstruct_prompts(self, output: str, n: int) -> Sequence[str]:
        """Infer *n* plausible human prompts that could have produced *output*."""
        self._last_response_metadata = None
        if n <= 0:
            return []
        if not output.strip():
            return [""] * n

        system_prompt = (
            "You are a research assistant. Given an AI-generated output, "
            "infer plausible human prompts that could have produced it. "
            "Return exactly the requested number of distinct prompts, "
            "each on its own line prefixed with a number (1. 2. etc.). "
            "Make prompts diverse in style, length, and specificity. "
            "Output ONLY the numbered list, no other text."
        )
        full_prompt = (
            f"{system_prompt}\n\n"
            f"AI-generated output:\n\n---\n{output}\n---\n\n"
            f"Infer {n} plausible human prompts that could have produced "
            f"this output. Return exactly {n} numbered prompts."
        )

        response, metadata = _call_api(
            full_prompt,
            self.reconstruct_model,
            timeout=self.api_timeout,
            retries=self.api_retries,
            use_alt_backend=self.use_alt_backend,
            backend_pin=self.backend_pin,
            gpt_route=self.gpt_route,
            max_output_tokens=self.max_output_tokens,
        )
        self._last_response_metadata = metadata
        prompts = _parse_numbered_list(response, n)
        time.sleep(self.sleep_seconds)
        return prompts

    def generate(self, prompt: str) -> str:
        """Generate one output, optionally using two segments for a GPT budget."""
        self._last_response_metadata = None
        if not prompt.strip():
            return ""

        if self.segment_output_tokens is None:
            result, metadata = _call_api(
                prompt,
                self.model_name,
                timeout=self.api_timeout,
                retries=self.api_retries,
                use_alt_backend=self.use_alt_backend,
                backend_pin=self.backend_pin,
                gpt_route=self.gpt_route,
                max_output_tokens=self.max_output_tokens,
                instructions=self.generation_instructions,
                )
        else:
            segment_tokens = self.segment_output_tokens
            first, first_meta = _call_api(
                prompt,
                self.model_name,
                timeout=self.api_timeout,
                retries=self.api_retries,
                use_alt_backend=self.use_alt_backend,
                backend_pin=self.backend_pin,
                gpt_route=self.gpt_route,
                max_output_tokens=segment_tokens,
                accept_incomplete_at_limit=True,
                instructions=self.generation_instructions,
                )
            first_incomplete = (
                first_meta.get("status") == "incomplete"
                and isinstance(first_meta.get("incomplete_details"), dict)
                and first_meta["incomplete_details"].get("reason") == "max_output_tokens"
            )
            if not first_incomplete:
                result = first
                metadata = dict(first_meta)
                metadata["generation_mode"] = "single_segment_completed"
                metadata["total_token_budget"] = self.max_output_tokens
                metadata["segment_output_tokens"] = segment_tokens
            else:
                second, second_meta = _call_api(
                    _continuation_prompt(prompt, first),
                    self.model_name,
                    timeout=self.api_timeout,
                    use_alt_backend=self.use_alt_backend,
                    backend_pin=self.backend_pin,
                    gpt_route=self.gpt_route,
                    max_output_tokens=segment_tokens,
                    accept_incomplete_at_limit=False,
                    instructions=self.generation_instructions,
                        )
                result = _merge_continuation(first, second)
                segment_usage = []
                total_output_tokens = 0
                for item in (first_meta, second_meta):
                    usage = item.get("usage")
                    segment_usage.append(usage)
                    if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
                        total_output_tokens += usage["output_tokens"]
                metadata = {
                    "api": "responses_segmented",
                    "client": first_meta.get("client"),
                    "route": first_meta.get("route"),
                    "gateway": first_meta.get("gateway"),
                    "requested_model": self.model_name,
                    "returned_model": second_meta.get("returned_model"),
                    "response_id": [first_meta.get("response_id"), second_meta.get("response_id")],
                    "status": second_meta.get("status"),
                    "incomplete_details": second_meta.get("incomplete_details"),
                    "usage": {
                        "output_tokens": total_output_tokens,
                        "segments": segment_usage,
                    },
                    "max_output_tokens": self.max_output_tokens,
                    "segment_output_tokens": segment_tokens,
                    "generation_mode": "two_segment_continuation",
                    "continuation_marker": _CONTINUATION_MARKER,
                    "boundary_verified": True,
                    "instructions_sha256": first_meta.get("instructions_sha256"),
                    "segments": [first_meta, second_meta],
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                }

        self._last_response_metadata = metadata
        time.sleep(self.sleep_seconds)
        return result


def _parse_numbered_list(text: str, expected: int) -> list[str]:
    """Parse numbered prompts while preserving wrapped continuation lines."""
    import re

    numbered = re.compile(r"^\d+[\.\)\-:：]\s*")
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not any(numbered.match(line) for line in lines):
        return lines[:expected]

    prompts: list[str] = []
    current: list[str] = []
    for line in lines:
        match = numbered.match(line)
        if match:
            if current:
                prompts.append(" ".join(current).strip())
            current = [line[match.end():].strip()]
        elif current:
            current.append(line)
    if current:
        prompts.append(" ".join(current).strip())
    return [prompt for prompt in prompts if prompt][:expected]
