# -*- coding: utf-8 -*-
"""Provider-neutral, one-invocation transport ABI for strict-CF v1.

The core sends one canonical JSON request on stdin and accepts one strict JSON
response on stdout.  Provider wrappers are immutable, model-scoped bundle
artifacts; this module never imports a provider client and never retries.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from experiment_b import storage

TRANSPORT_ABI_VERSION = 1
TRANSPORT_REQUEST_SCHEMA = "experiment_a.strict_cf_v1.transport_request"
TRANSPORT_RESPONSE_SCHEMA = "experiment_a.strict_cf_v1.transport_response"
MAX_STDERR_BYTES = 64 * 1024

_FIXED_CALL_CONTRACT = {
    "max_output_tokens": 4096,
    "reasoning_effort": "low",
    "terminal_status": "completed",
    "provider_attempts": 1,
    "allow_alias": False,
    "allow_fallback": False,
}
TRANSPORT_ABI_SHA256 = storage.canonical_row_sha256(
    {
        "version": TRANSPORT_ABI_VERSION,
        "request_schema": TRANSPORT_REQUEST_SCHEMA,
        "response_schema": TRANSPORT_RESPONSE_SCHEMA,
        "call_contract": _FIXED_CALL_CONTRACT,
        "stdin": "one_canonical_utf8_json",
        "stdout": "one_strict_utf8_json",
    }
)


class TransportError(RuntimeError):
    """A wrapper invocation or returned transport document is invalid."""

    def __init__(
        self,
        message: str,
        *,
        provenance: Mapping[str, Any] | None = None,
        request_may_have_been_sent: bool = False,
    ) -> None:
        super().__init__(message)
        self.provenance = dict(provenance) if provenance is not None else None
        self.request_may_have_been_sent = bool(request_may_have_been_sent)


class TransportProtocolError(TransportError):
    """The wrapper output violates the frozen ABI or call contract."""


class TransportInvocationError(TransportError):
    """The wrapper process failed before yielding an adoptable response."""


def _reject_constant(value: str) -> None:
    raise TransportProtocolError(f"non-finite JSON constant {value!r}")


def strict_json_loads(data: str | bytes) -> Any:
    """Parse one strict UTF-8 JSON document and reject duplicate keys."""

    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise TransportProtocolError(f"wrapper output is not strict UTF-8: {exc}") from exc
    elif isinstance(data, str):
        text = data
    else:
        raise TypeError("strict_json_loads requires str or bytes")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise TransportProtocolError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=_reject_constant)
    except TransportProtocolError:
        raise
    except json.JSONDecodeError as exc:
        raise TransportProtocolError(f"wrapper stdout is not one JSON document: {exc}") from exc


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise TransportProtocolError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise TransportProtocolError(f"{label} must be a lowercase SHA-256 digest") from exc
    if value != value.lower():
        raise TransportProtocolError(f"{label} must be lowercase")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TransportProtocolError(f"{label} must be a nonempty trimmed string")
    return value


def _utc_timestamp(value: Any, label: str) -> str:
    text = _nonempty(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransportProtocolError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransportProtocolError(f"{label} must include a UTC offset")
    if parsed.utcoffset().total_seconds() != 0:
        raise TransportProtocolError(f"{label} must be normalized to UTC")
    return text


def fixed_call_contract() -> dict[str, Any]:
    return dict(_FIXED_CALL_CONTRACT)


def build_transport_request(
    *,
    invocation_id: str,
    lineage_id: str,
    manifest_sha256: str,
    cohort_root_sha256: str,
    generation_model: str,
    prompt: str,
    intent_ordinal: int,
    bundle_sha256: str,
    formal_pointer_sha256: str | None,
    operation: str = "generate",
) -> dict[str, Any]:
    value = {
        "schema": TRANSPORT_REQUEST_SCHEMA,
        "abi_version": TRANSPORT_ABI_VERSION,
        "invocation_id": invocation_id,
        "campaign": {
            "lineage_id": lineage_id,
            "manifest_sha256": manifest_sha256,
            "cohort_root_sha256": cohort_root_sha256,
        },
        "binding": {
            "formal_pointer_sha256": formal_pointer_sha256,
            "bundle_sha256": bundle_sha256,
        },
        "operation": operation,
        "generation_model": generation_model,
        "prompt": prompt,
        "intent_ordinal": intent_ordinal,
        "contract": fixed_call_contract(),
    }
    validate_transport_request(value, allow_candidate=formal_pointer_sha256 is None)
    return value


def validate_transport_request(
    value: Mapping[str, Any], *, allow_candidate: bool = False
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TransportProtocolError("transport request must be an object")
    expected = {
        "schema", "abi_version", "invocation_id", "campaign", "binding",
        "operation", "generation_model", "prompt", "intent_ordinal", "contract",
    }
    if set(value) != expected:
        raise TransportProtocolError("transport request keys are not exact")
    if value["schema"] != TRANSPORT_REQUEST_SCHEMA or value["abi_version"] != TRANSPORT_ABI_VERSION:
        raise TransportProtocolError("transport request schema/version mismatch")
    _nonempty(value["invocation_id"], "invocation_id")
    _nonempty(value["generation_model"], "generation_model")
    if value["operation"] != "generate":
        raise TransportProtocolError("operation must equal 'generate'")
    if not isinstance(value["prompt"], str) or not value["prompt"].strip():
        raise TransportProtocolError("prompt must be nonempty text")
    ordinal = value["intent_ordinal"]
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        raise TransportProtocolError("intent_ordinal must be a positive integer")
    campaign = value["campaign"]
    if not isinstance(campaign, Mapping) or set(campaign) != {
        "lineage_id", "manifest_sha256", "cohort_root_sha256"
    }:
        raise TransportProtocolError("campaign binding keys are not exact")
    _nonempty(campaign["lineage_id"], "campaign.lineage_id")
    _sha256(campaign["manifest_sha256"], "campaign.manifest_sha256")
    _sha256(campaign["cohort_root_sha256"], "campaign.cohort_root_sha256")
    binding = value["binding"]
    if not isinstance(binding, Mapping) or set(binding) != {
        "formal_pointer_sha256", "bundle_sha256"
    }:
        raise TransportProtocolError("transport binding keys are not exact")
    _sha256(binding["bundle_sha256"], "binding.bundle_sha256")
    pointer = binding["formal_pointer_sha256"]
    if pointer is None:
        if not allow_candidate:
            raise TransportProtocolError("formal pointer hash is required")
    else:
        _sha256(pointer, "binding.formal_pointer_sha256")
    if dict(value["contract"]) != _FIXED_CALL_CONTRACT:
        raise TransportProtocolError("transport call contract differs from frozen ABI")
    return value


def validate_transport_response(
    value: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    expected_route_id: str,
    expected_client_id: str,
) -> tuple[str, dict[str, Any]]:
    """Validate one wrapper response and return text plus detached provenance."""

    validate_transport_request(
        request,
        allow_candidate=request["binding"]["formal_pointer_sha256"] is None,
    )
    if not isinstance(value, Mapping):
        raise TransportProtocolError("transport response must be an object")
    common = {
        "schema", "abi_version", "ok", "invocation_id", "campaign", "binding",
        "generation_model", "provider_attempt_count", "provenance",
    }
    if value.get("ok") is True:
        expected = common | {"text", "text_sha256"}
    elif value.get("ok") is False:
        expected = common | {"error"}
    else:
        raise TransportProtocolError("transport response ok must be boolean")
    if set(value) != expected:
        raise TransportProtocolError("transport response keys are not exact")
    if value["schema"] != TRANSPORT_RESPONSE_SCHEMA or value["abi_version"] != TRANSPORT_ABI_VERSION:
        raise TransportProtocolError("transport response schema/version mismatch")
    for field in ("invocation_id", "campaign", "binding", "generation_model"):
        if value[field] != request[field]:
            raise TransportProtocolError(f"transport response {field} does not echo request")
    if value["provider_attempt_count"] != 1:
        raise TransportProtocolError("provider_attempt_count must equal exactly one")
    provenance = value["provenance"]
    if not isinstance(provenance, Mapping):
        raise TransportProtocolError("response provenance must be an object")
    expected_model = request["generation_model"]
    if value["ok"] is False:
        required_failure = {
            "api_family", "route_id", "client_id", "requested_model",
            "returned_model", "response_id", "native_terminal_field",
            "native_terminal_value", "captured_at_utc",
        }
        if set(provenance) != required_failure:
            raise TransportProtocolError("failure provenance keys are not exact")
        if provenance.get("route_id") != expected_route_id:
            raise TransportProtocolError("failure route_id mismatch")
        if provenance.get("client_id") != expected_client_id:
            raise TransportProtocolError("failure client_id mismatch")
        if provenance.get("requested_model") != expected_model:
            raise TransportProtocolError("failure requested_model mismatch")
        returned = provenance.get("returned_model")
        if returned is not None and returned != expected_model:
            raise TransportProtocolError("failure returned_model mismatch")
        _nonempty(provenance.get("api_family"), "provenance.api_family")
        _utc_timestamp(provenance.get("captured_at_utc"), "provenance.captured_at_utc")
        detached = dict(provenance)
        detached["provider_attempt_count"] = 1
        detached["transport_abi_sha256"] = TRANSPORT_ABI_SHA256
        detached["campaign_binding"] = dict(request["campaign"])
        detached["formal_binding"] = dict(request["binding"])
        detached["invocation_id"] = request["invocation_id"]
        error = value["error"]
        if not isinstance(error, Mapping) or set(error) != {
            "category", "message", "request_may_have_been_sent", "retry_after_seconds"
        }:
            raise TransportProtocolError("transport error keys are not exact")
        category = _nonempty(error["category"], "error.category")
        message = _nonempty(error["message"], "error.message")
        may_sent = error["request_may_have_been_sent"]
        if not isinstance(may_sent, bool):
            raise TransportProtocolError("error.request_may_have_been_sent must be boolean")
        retry_after = error["retry_after_seconds"]
        if retry_after is not None and (
            isinstance(retry_after, bool)
            or not isinstance(retry_after, (int, float))
            or not math.isfinite(float(retry_after))
            or float(retry_after) < 0
        ):
            raise TransportProtocolError("error.retry_after_seconds must be null/nonnegative")
        detached["failure_category"] = category
        detached["retry_after_seconds"] = retry_after
        raise TransportInvocationError(
            message,
            provenance=detached,
            request_may_have_been_sent=may_sent,
        )

    required = {
        "api_family", "route_id", "client_id", "requested_model", "returned_model",
        "response_id", "native_terminal_field", "native_terminal_value",
        "terminal_status", "incomplete_details", "usage", "max_output_tokens",
        "reasoning_effort", "alias_used", "fallback_used", "captured_at_utc",
    }
    if set(provenance) != required:
        raise TransportProtocolError("response provenance keys are not exact")
    expected_model = request["generation_model"]
    for field, expected_value in (
        ("route_id", expected_route_id),
        ("client_id", expected_client_id),
        ("requested_model", expected_model),
        ("returned_model", expected_model),
        ("terminal_status", "completed"),
        ("max_output_tokens", 4096),
        ("reasoning_effort", "low"),
        ("alias_used", False),
        ("fallback_used", False),
    ):
        if provenance.get(field) != expected_value:
            raise TransportProtocolError(f"response provenance {field} mismatch")
    _nonempty(provenance.get("api_family"), "provenance.api_family")
    _nonempty(provenance.get("response_id"), "provenance.response_id")
    _nonempty(provenance.get("native_terminal_field"), "provenance.native_terminal_field")
    if provenance.get("native_terminal_value") is None:
        raise TransportProtocolError("native terminal value must be retained")
    if provenance.get("incomplete_details") not in (None, {}):
        raise TransportProtocolError("completed response has incomplete_details")
    usage = provenance.get("usage")
    if not isinstance(usage, Mapping) or not usage:
        raise TransportProtocolError("response usage must be nonempty")
    output_tokens = usage.get("output_tokens")
    if isinstance(output_tokens, bool) or not isinstance(output_tokens, int) or output_tokens < 1:
        raise TransportProtocolError("usage.output_tokens must be a positive integer")
    _utc_timestamp(provenance.get("captured_at_utc"), "provenance.captured_at_utc")
    detached = dict(provenance)
    detached["usage"] = dict(usage)
    detached["provider_attempt_count"] = 1
    detached["transport_abi_sha256"] = TRANSPORT_ABI_SHA256
    detached["campaign_binding"] = dict(request["campaign"])
    detached["formal_binding"] = dict(request["binding"])
    detached["invocation_id"] = request["invocation_id"]

    text = value["text"]
    if not isinstance(text, str) or not text:
        raise TransportProtocolError("successful response text must be nonempty")
    if value["text_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest():
        raise TransportProtocolError("successful response text hash mismatch")
    return text, detached


@dataclass(frozen=True)
class TransportExecutionBinding:
    lineage_id: str
    manifest_sha256: str
    cohort_root_sha256: str
    generation_model: str
    bundle_sha256: str
    formal_pointer_sha256: str | None
    route_id: str
    client_id: str
    entrypoint: Path
    python_executable: Path = Path(sys.executable)
    working_directory: Path | None = None
    environment: Mapping[str, str] | None = None


class SubprocessTransportAdapter:
    """One-shot wrapper adapter.  Each generate_bound call invokes once."""

    def __init__(
        self,
        binding: TransportExecutionBinding,
        *,
        timeout_seconds: float = 180.0,
        run: Any = subprocess.run,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.binding = binding
        self.timeout_seconds = float(timeout_seconds)
        self._run = run
        self._last_response_metadata: dict[str, Any] | None = None
        self._last_raw: dict[str, Any] | None = None

    def generate_bound(
        self,
        prompt: str,
        *,
        invocation_id: str,
        intent_ordinal: int,
    ) -> str:
        self._last_response_metadata = None
        request = build_transport_request(
            invocation_id=invocation_id,
            lineage_id=self.binding.lineage_id,
            manifest_sha256=self.binding.manifest_sha256,
            cohort_root_sha256=self.binding.cohort_root_sha256,
            generation_model=self.binding.generation_model,
            prompt=prompt,
            intent_ordinal=intent_ordinal,
            bundle_sha256=self.binding.bundle_sha256,
            formal_pointer_sha256=self.binding.formal_pointer_sha256,
        )
        request_bytes = storage.canonical_json_bytes(request)
        env: MutableMapping[str, str] = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if self.binding.environment:
            env.update({str(key): str(item) for key, item in self.binding.environment.items()})
        command: Sequence[str] = (
            str(self.binding.python_executable),
            str(self.binding.entrypoint),
        )
        try:
            proc = self._run(
                command,
                input=request_bytes,
                capture_output=True,
                cwd=(
                    str(self.binding.working_directory)
                    if self.binding.working_directory is not None
                    else None
                ),
                env=env,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raw = {
                "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                "stdout_sha256": hashlib.sha256(exc.stdout or b"").hexdigest(),
                "stderr_sha256": hashlib.sha256(exc.stderr or b"").hexdigest(),
                "transport_abi_sha256": TRANSPORT_ABI_SHA256,
                "formal_binding": dict(request["binding"]),
                "campaign_binding": dict(request["campaign"]),
                "invocation_id": invocation_id,
            }
            self._last_raw = raw
            raise TransportInvocationError(
                "transport wrapper timed out",
                provenance=raw,
                request_may_have_been_sent=True,
            ) from exc
        stdout = bytes(proc.stdout or b"")
        stderr = bytes(proc.stderr or b"")
        self._last_raw = {
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "stderr_size": len(stderr),
            "stderr_truncated": len(stderr) > MAX_STDERR_BYTES,
            "returncode": int(proc.returncode),
            "transport_abi_sha256": TRANSPORT_ABI_SHA256,
            "formal_binding": dict(request["binding"]),
            "campaign_binding": dict(request["campaign"]),
            "invocation_id": invocation_id,
        }
        if len(stderr) > MAX_STDERR_BYTES:
            stderr = stderr[:MAX_STDERR_BYTES]
        try:
            response = strict_json_loads(stdout)
            text, provenance = validate_transport_response(
                response,
                request,
                expected_route_id=self.binding.route_id,
                expected_client_id=self.binding.client_id,
            )
        except TransportError as exc:
            if exc.provenance is None:
                exc.provenance = dict(self._last_raw)
            raise
        if proc.returncode != 0:
            raise TransportInvocationError(
                f"transport wrapper exited {proc.returncode} despite success document",
                provenance=self._last_raw,
                request_may_have_been_sent=True,
            )
        provenance["raw_transport"] = dict(self._last_raw)
        self._last_response_metadata = provenance
        return text

    def generate(self, prompt: str) -> str:
        raise TransportProtocolError(
            "formal transport requires generate_bound with a persisted invocation identity"
        )

    def consume_last_response_metadata(self) -> dict[str, Any] | None:
        result = self._last_response_metadata
        self._last_response_metadata = None
        return result

    def consume_last_raw_transport(self) -> dict[str, Any] | None:
        result = self._last_raw
        self._last_raw = None
        return result


__all__ = [
    "MAX_STDERR_BYTES",
    "SubprocessTransportAdapter",
    "TRANSPORT_ABI_SHA256",
    "TRANSPORT_ABI_VERSION",
    "TRANSPORT_REQUEST_SCHEMA",
    "TRANSPORT_RESPONSE_SCHEMA",
    "TransportError",
    "TransportExecutionBinding",
    "TransportInvocationError",
    "TransportProtocolError",
    "build_transport_request",
    "fixed_call_contract",
    "strict_json_loads",
    "validate_transport_request",
    "validate_transport_response",
]
