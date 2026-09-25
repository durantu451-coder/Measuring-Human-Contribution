# -*- coding: utf-8 -*-
"""Resumable per-level generator for Experiment A strict-CF v1.

One snapshot row represents one already-generated actual L1--L5 pair.  This
runner performs exactly the missing stages for that row: one strict prompt
reconstruction followed by five counterfactual generations.  Every logical
attempt is durably recorded before control moves on; no local fallback exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableSet, Sequence

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import experiment_a.strict_cf_schema as schema
from experiment_a.outage_guard import (
    OUTAGE_EXIT_CODE,
    ConfirmedOutage,
    sanitize_error_text,
)
from experiment_a.strict_cf_routes import (
    MODELS,
    assert_backend_c_handoff,
    formal_route_for_model,
    make_adapter,
    make_bound_adapter,
    route_for_model,
    validate_adopted_call,
)
from experiment_a.strict_cf_route_bundle import (
    FullValidationScope,
    ValidatedCampaignContext,
    build_validated_campaign_context,
    emit_adapter_constructed,
    exclusive_create_json,
    load_formal_binding,
    set_full_validation_decision_state,
    validate_manifest_full,
)
from experiment_a.strict_cf_transport import SubprocessTransportAdapter
from experiment_b.storage import (
    ProcessLock,
    atomic_replace_json,
    canonical_row_sha256,
    file_sha256,
)

MANIFEST_NAME = "manifest.json"
ACTUAL_SNAPSHOT_REL = schema.ARTIFACT_SPECS["actual_levels"][0]
CHECKPOINTS_REL = "checkpoints"
FINALIZED_NAME = schema.ARTIFACT_SPECS["finalized"][0]
EXPECTED_LEVEL_ROWS = schema.EXPECTED_LEVEL_ROWS
CANONICAL_RUNS_ROOT = schema.canonical_runs_root(PROJECT)
CF_COUNT = 5
MIN_OUTPUT_CHARS = 50
_CHECKPOINT_SCHEMA = "experiment_a.strict_cf_checkpoint"
_CHECKPOINT_VERSION = 2
_NUMBERED = re.compile(r"^([1-5])[.)\-:：]\s*(\S.*)$")
_ERROR_PREFIXES = (
    "[error",
    "error:",
    "[api",
    "[errno",
    "api ask failed",
    "all endpoints are unavailable",
    "the api returned no output_text",
    "fetch failed",
    "failed to fetch",
    "request failed",
    "network error",
    "http error",
    "server error",
    "upstream error",
)
_TEXTUAL_REFUSAL_STARTS = (
    re.compile(
        r"^(?:i(?:'|’)m|i am)\s+sorry\b.{0,120}\b"
        r"(?:can(?:not|'t)|unable to)\s+(?:assist|help|comply|provide)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sorry[,;:]?\s+)?(?:i\s+)?(?:can(?:not|'t)|am unable to|cannot)\s+"
        r"(?:assist|help|comply|provide)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:for safety reasons|due to (?:safety|policy) restrictions|"
        r"under (?:my|the) safety policy)\b.{0,120}\b"
        r"(?:cannot|can't|unable to|won't)\b",
        re.IGNORECASE,
    ),
)


class StrictCFError(RuntimeError):
    """Base class for strict-CF runner failures."""


class InputIntegrityError(StrictCFError):
    """The immutable manifest/snapshot bundle is invalid or changed."""


class StageAttemptError(StrictCFError):
    """A stage did not produce adoptable data; its attempt is checkpointed."""

    def __init__(self, message: str, *, category: str | None = None) -> None:
        self.category = category
        super().__init__(message)


class RateLimitExhaustedError(StrictCFError):
    """Checkpointed rate-limit attempts were exhausted; resume this model later."""

    def __init__(self, model: str, failure_id: str, attempts: int) -> None:
        self.model = model
        self.failure_id = failure_id
        self.attempts = attempts
        super().__init__(
            f"{model} exhausted {attempts} checkpointed rate-limit attempts at {failure_id}"
        )


class CheckpointError(StrictCFError):
    """A checkpoint is corrupt, foreign, or inconsistent with its snapshot row."""


class IncompleteRunError(StrictCFError):
    """Bounded retries ended with one or more selected checkpoints incomplete."""

    def __init__(self, counts: Mapping[str, int]) -> None:
        self.counts = dict(counts)
        super().__init__(
            f"strict-CF worker remains incomplete after bounded retries: {self.counts}"
        )


class LaunchBarrierError(StrictCFError):
    """A worker did not receive one exact, committed subset START decision."""


class RouteHeldError(StrictCFError):
    """A model route is persistently held and this worker must stop immediately."""

    def __init__(self, message: str, state: Mapping[str, Any]) -> None:
        self.state = dict(state)
        super().__init__(message)


_HTTP_STATUS = re.compile(
    r"(?:(?:http|api)(?:\s+error)?|status(?:_code)?)\s*[:=]?\s*['\"]?(\d{3,4})\b",
    re.IGNORECASE,
)


def classify_route_failure(error: BaseException | str) -> str:
    """Classify failures without treating 429 or content quality as an outage."""
    text = sanitize_error_text(error, limit=2000).casefold()
    statuses = {int(value) for value in _HTTP_STATUS.findall(text)}
    if 429 in statuses or "rate limit" in text or "too many requests" in text:
        return "rate_limited"
    permanent_markers = (
        "model_not_supported",
        "model not supported",
        "unsupported model",
        "authentication",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "requested_model mismatch",
        "returned_model mismatch",
        "model mismatch",
        "route must be",
        "route mismatch",
        "client provenance mismatch",
        "gateway must be",
        "max_output_tokens must be",
        "reasoning_effort must be",
    )
    if statuses & {400, 401, 403, 404, 405, 409, 413, 415, 422} or any(
        marker in text for marker in permanent_markers
    ):
        return "permanent_route_failure"
    infrastructure_markers = (
        "cloudflare",
        "origin is unreachable",
        "web server is down",
        "fetch_failed",
        "fetch failed",
        "failed to fetch",
        "unable to reach proxy",
        "all endpoints are unavailable",
        "connection refused",
        "connection reset",
        "connection aborted",
        "connection closed unexpectedly",
        "remote end closed",
        "network is unreachable",
        "host is unreachable",
        "getaddrinfo failed",
        "name resolution",
        "dns lookup failed",
        "unexpected_eof",
        "unexpected eof",
        "eof occurred in violation of protocol",
        "ssl eof",
        "sslerror",
        "tlsv1 alert",
        "timed out",
        "timeout expired",
        "read timeout",
        "subprocess timeout",
        "winerror 10060",
        "winerror 10061",
        "winerror 10050",
        "winerror 10051",
        "winerror 10053",
        "winerror 10054",
        "winerror 11001",
    )
    # Cloudflare 1016/1033 and all HTTP 5xx (including 529/530) are route
    # infrastructure evidence.  They require a streak plus minimum duration.
    if statuses & {1016, 1033} or any(500 <= status <= 599 for status in statuses):
        return "infrastructure"
    if any(marker in text for marker in infrastructure_markers):
        return "infrastructure"
    content_markers = (
        "response status",
        "incomplete",
        "content filter",
        "refusal",
        "no visible text",
        "no output_text",
        "invalid output",
        "reconstruction",
        "numbered prompt",
        "repetitious",
        "shorter than",
        "duplicate response_id",
        "missing usage provenance",
    )
    if any(marker in text for marker in content_markers):
        return "protocol_or_quality"
    return "other"


def _route_state_paths(
    run_root: Path,
    model: str,
    route: str,
    binding_sha256: str | None = None,
) -> tuple[Path, Path]:
    identity = f"{model}\0{route}\0{binding_sha256 or 'legacy'}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{model}-{route}").strip("._")[:72]
    directory = run_root / "status" / "routes"
    return directory / f"{slug}-{digest}.json", directory / ".locks" / f"{digest}.lock"


class PersistentRouteCircuitBreaker:
    """Durable model-route breaker with immediate permanent-failure holds."""

    def __init__(
        self,
        *,
        run_root: Path,
        model: str,
        route: str,
        threshold: int = 6,
        minimum_duration_seconds: float = 180.0,
        rate_limit_retries: int = 3,
        rate_limit_base_seconds: float = 2.0,
        resume_probe_rounds: int = 3,
        expected_backend_c_validation_files: Mapping[str, Mapping[str, Any]] | None = None,
        formal_binding: Mapping[str, Any] | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        if threshold < 2:
            raise ValueError("route breaker threshold must be at least 2")
        if minimum_duration_seconds < 0:
            raise ValueError("minimum duration must be non-negative")
        if rate_limit_retries < 0 or rate_limit_base_seconds < 0:
            raise ValueError("rate-limit retry settings must be non-negative")
        if resume_probe_rounds < 1:
            raise ValueError("resume probe rounds must be positive")
        self.run_root = _guard_run_root(run_root)
        self.model = model
        self.route = route
        self.formal_binding = dict(formal_binding) if formal_binding is not None else None
        self.threshold = threshold
        self.minimum_duration_seconds = float(minimum_duration_seconds)
        self.rate_limit_retries = rate_limit_retries
        self.rate_limit_base_seconds = float(rate_limit_base_seconds)
        self.resume_probe_rounds = resume_probe_rounds
        self.expected_backend_c_validation_files = (
            {
                model_name: dict(evidence)
                for model_name, evidence in expected_backend_c_validation_files.items()
            }
            if expected_backend_c_validation_files is not None
            else None
        )
        self._sleep = sleep
        self._failure_id: str | None = None
        self._stage: str | None = None
        binding_sha = (
            self.formal_binding.get("formal_pointer_sha256")
            if self.formal_binding is not None
            else None
        )
        self.path, self.lock_path = _route_state_paths(
            self.run_root, model, route, binding_sha
        )

    def set_context(self, failure_id: str, stage: str) -> None:
        self._failure_id = failure_id
        self._stage = stage

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema": "experiment_a.strict_cf_v1.route_breaker",
            "schema_version": 1,
            "generation_model": self.model,
            "route": self.route,
            "formal_binding": (
                {
                    "formal_pointer_sha256": self.formal_binding["formal_pointer_sha256"],
                    "bundle_sha256": self.formal_binding["bundle_sha256"],
                    "cohort_root_sha256": self.formal_binding["campaign"]["cohort_root_sha256"],
                    "protocol_sha256": self.formal_binding["protocol_sha256"],
                }
                if self.formal_binding is not None
                else None
            ),
            "state": "healthy",
            "hold_kind": None,
            "consecutive_infrastructure_failures": 0,
            "infrastructure_streak_started_at_utc": None,
            "held_at_utc": None,
            "failures": [],
            "rate_limit_events": [],
            "recovery_probes": [],
            "updated_at_utc": _utc_now(),
        }

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            state = _strict_json_loads(self.path.read_text(encoding="utf-8", errors="strict"))
        except Exception as exc:
            raise RouteHeldError(f"invalid persisted route-breaker state: {self.path}: {exc}", {}) from exc
        if not isinstance(state, Mapping):
            raise RouteHeldError("persisted route-breaker state is not an object", {})
        state = dict(state)
        if (
            state.get("schema") != "experiment_a.strict_cf_v1.route_breaker"
            or state.get("schema_version") != 1
            or state.get("generation_model") != self.model
            or state.get("route") != self.route
            or state.get("formal_binding") != self._empty_state()["formal_binding"]
        ):
            raise RouteHeldError("persisted route-breaker identity/schema mismatch", state)
        return state

    @contextmanager
    def _locked_state(self):
        with ProcessLock(
            self.lock_path,
            scope=f"strict-cf-route-state:{self.model}:{self.route}",
            timeout=30.0,
        ):
            state = self._load_unlocked()
            yield state

    def snapshot(self) -> dict[str, Any]:
        with self._locked_state() as state:
            return dict(state)

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _write(self, state: dict[str, Any]) -> None:
        state["updated_at_utc"] = _utc_now()
        atomic_replace_json(self.path, state)

    def record_success(self) -> None:
        with self._locked_state() as state:
            if state.get("state") == "held":
                raise RouteHeldError(
                    f"route is held for {self.model}/{self.route}; recovery probes are required",
                    state,
                )
            if state.get("consecutive_infrastructure_failures", 0):
                state["consecutive_infrastructure_failures"] = 0
                state["infrastructure_streak_started_at_utc"] = None
                state["state"] = "healthy"
                self._write(state)

    def record_failure(self, error: BaseException | str) -> str:
        category = classify_route_failure(error)
        now = _utc_now()
        failure = {
            "at_utc": now,
            "failure_id": self._failure_id,
            "stage": self._stage,
            "category": category,
            "error_type": type(error).__name__ if isinstance(error, BaseException) else "str",
            "message": sanitize_error_text(error),
        }
        with self._locked_state() as state:
            if state.get("state") == "held":
                raise RouteHeldError(
                    f"route remains held for {self.model}/{self.route}", state
                )
            if category == "rate_limited":
                state["rate_limit_events"].append(failure)
                state["consecutive_infrastructure_failures"] = 0
                state["infrastructure_streak_started_at_utc"] = None
                self._write(state)
                return category
            state["failures"].append(failure)
            if category == "permanent_route_failure":
                state["state"] = "held"
                state["hold_kind"] = "permanent_route_failure"
                state["held_at_utc"] = now
                self._write(state)
                _append_run_status_event(
                    self.run_root,
                    event_type="route_hold",
                    model=self.model,
                    route=self.route,
                    detail=f"permanent failure {self._failure_id}/{self._stage}: {failure['message']}",
                    state="held",
                    formal_binding=self.formal_binding,
                )
                raise RouteHeldError(
                    f"permanent route failure held {self.model}/{self.route}: {failure['message']}",
                    state,
                )
            if category != "infrastructure":
                state["consecutive_infrastructure_failures"] = 0
                state["infrastructure_streak_started_at_utc"] = None
                self._write(state)
                return category

            count = int(state.get("consecutive_infrastructure_failures", 0)) + 1
            state["consecutive_infrastructure_failures"] = count
            started = state.get("infrastructure_streak_started_at_utc")
            if not isinstance(started, str):
                started = now
                state["infrastructure_streak_started_at_utc"] = started
            duration = max(0.0, (self._parse_time(now) - self._parse_time(started)).total_seconds())
            if count >= self.threshold and duration >= self.minimum_duration_seconds:
                state["state"] = "held"
                state["hold_kind"] = "confirmed_infrastructure_outage"
                state["held_at_utc"] = now
                self._write(state)
                _append_run_status_event(
                    self.run_root,
                    event_type="outage",
                    model=self.model,
                    route=self.route,
                    detail=(
                        f"confirmed after {count} consecutive failures over {duration:.3f}s; "
                        f"last={self._failure_id}/{self._stage}"
                    ),
                    state="held",
                    formal_binding=self.formal_binding,
                )
                raise RouteHeldError(
                    f"confirmed infrastructure outage held {self.model}/{self.route} "
                    f"after {count} failures/{duration:.3f}s",
                    state,
                )
            state["state"] = "observing"
            self._write(state)
            return category

    def hold_handoff_conflict(self, error: BaseException | str) -> None:
        """Immediately hold API3rd when Experiment B reclaims or drifts the route."""
        now = _utc_now()
        failure = {
            "at_utc": now,
            "failure_id": self._failure_id,
            "stage": self._stage,
            "category": "handoff_conflict",
            "error_type": type(error).__name__ if isinstance(error, BaseException) else "str",
            "message": sanitize_error_text(error),
        }
        with self._locked_state() as state:
            state["failures"].append(failure)
            state["state"] = "held"
            state["hold_kind"] = "handoff_conflict"
            state["held_at_utc"] = now
            self._write(state)
        _append_run_status_event(
            self.run_root,
            event_type="route_hold",
            model=self.model,
            route=self.route,
            detail=(
                f"handoff_conflict {self._failure_id}/{self._stage}: "
                f"{failure['message']}"
            ),
            state="held",
            formal_binding=self.formal_binding,
        )
        raise RouteHeldError(
            f"Experiment B API3rd handoff conflict held {self.model}/{self.route}: "
            f"{failure['message']}",
            self.snapshot(),
        )

    def hold_execution_stack_drift(self, error: BaseException | str) -> None:
        """Hold locally before another request can use changed pinned code/client bytes."""
        now = _utc_now()
        failure = {
            "at_utc": now,
            "failure_id": self._failure_id,
            "stage": self._stage,
            "category": "execution_stack_drift",
            "error_type": type(error).__name__ if isinstance(error, BaseException) else "str",
            "message": sanitize_error_text(error),
        }
        with self._locked_state() as state:
            state["failures"].append(failure)
            state["state"] = "held"
            state["hold_kind"] = "execution_stack_drift"
            state["held_at_utc"] = now
            self._write(state)
        _append_run_status_event(
            self.run_root,
            event_type="route_hold",
            model=self.model,
            route=self.route,
            detail=(
                f"execution_stack_drift {self._failure_id}/{self._stage}: "
                f"{failure['message']}"
            ),
            state="held",
            formal_binding=self.formal_binding,
        )
        raise RouteHeldError(
            f"pinned execution-stack drift held {self.model}/{self.route}: "
            f"{failure['message']}",
            self.snapshot(),
        )

    def require_recovery_probes(self, adapter: Any) -> None:
        """Release a hold after durable consecutive exact-model/completed probes."""
        state = self.snapshot()
        if state.get("state") != "held":
            return
        request = "Strict route recovery probe. Reply with exactly: ROUTE_RECOVERED"
        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        # Includes IDs from checkpoints and every persisted route probe, so a
        # recovery response can never be reused by a later formal call.
        probe_ids = collect_response_ids(self.run_root)

        # First adjudicate every response that was durably received before a
        # prior process died.  Only an intent with no raw response may be called
        # again; received bytes are deterministic evidence.
        pending = [
            index
            for index, probe in enumerate(state["recovery_probes"])
            if (
                probe.get("outcome") == "outcome_unknown"
                and isinstance(probe.get("response_text"), str)
                and isinstance(probe.get("provenance"), Mapping)
            )
        ]
        for probe_index in pending:
            with self._locked_state() as current:
                probe = dict(current["recovery_probes"][probe_index])
            try:
                replayed = validate_adopted_call(
                    probe["provenance"],
                    self.model,
                    label=f"recovery_probe_replay_{probe_index}",
                    binding=self.formal_binding,
                )
                schema.validate_call_provenance(
                    replayed,
                    expected_model=self.model,
                    project_root=PROJECT,
                )
                if probe["response_text"].strip() != "ROUTE_RECOVERED":
                    raise ValueError("persisted recovery response text is not exactly ROUTE_RECOVERED")
            except Exception as exc:
                with self._locked_state() as current:
                    target = current["recovery_probes"][probe_index]
                    target["outcome"] = "rejected"
                    target["finished_at_utc"] = _utc_now()
                    target["error"] = sanitize_error_text(exc)
                    self._write(current)
                raise RouteHeldError(
                    f"persisted route recovery response was rejected: {exc}",
                    self.snapshot(),
                ) from exc
            with self._locked_state() as current:
                target = current["recovery_probes"][probe_index]
                target["outcome"] = "adopted"
                target["finished_at_utc"] = _utc_now()
                target["error"] = None
                self._write(current)

        state = self.snapshot()
        consecutive = 0
        for probe in reversed(state["recovery_probes"]):
            if probe.get("outcome") != "adopted":
                break
            consecutive += 1
        consecutive = min(consecutive, self.resume_probe_rounds)

        while consecutive < self.resume_probe_rounds:
            round_number = consecutive + 1
            self.set_context(f"recovery_probe_{round_number}", "recovery_probe")
            with self._locked_state() as current:
                probe_index = len(current["recovery_probes"])
                invocation_id = (
                    f"{self.model}:recovery:{probe_index + 1}:"
                    f"{hashlib.sha256((request_hash + str(probe_index)).encode()).hexdigest()[:16]}"
                )
                current["recovery_probes"].append({
                    "round": round_number,
                    "invocation_id": invocation_id,
                    "formal_binding": self._empty_state()["formal_binding"],
                    "started_at_utc": _utc_now(),
                    "finished_at_utc": None,
                    "outcome": "outcome_unknown",
                    "request_sha256": request_hash,
                    "provenance": None,
                    "response_text": None,
                    "response_sha256": None,
                    "error": "intent_persisted_before_external_call",
                })
                self._write(current)
            try:
                needs_backend_c = (
                    self.formal_binding is not None
                    and self.formal_binding.get("coordination", {}).get("kind")
                    == "experiment_b_backend_c"
                ) or (
                    self.formal_binding is None
                    and route_for_model(self.model).adapter_kind == "backend_c"
                )
                if needs_backend_c:
                    try:
                        assert_backend_c_handoff(
                            expected_validation_files=self.expected_backend_c_validation_files
                        )
                    except Exception as exc:
                        self.hold_handoff_conflict(exc)
                if hasattr(adapter, "generate_bound"):
                    text = adapter.generate_bound(
                        request,
                        invocation_id=invocation_id,
                        intent_ordinal=probe_index + 1,
                    )
                else:
                    text = adapter.generate(request)
                metadata = adapter.consume_last_response_metadata()
            except Exception as exc:
                with self._locked_state() as current:
                    target = current["recovery_probes"][probe_index]
                    target["finished_at_utc"] = _utc_now()
                    target["outcome"] = "outcome_unknown"
                    target["provenance"] = _json_safe(_exception_provenance(exc))
                    target["error"] = sanitize_error_text(exc)
                    self._write(current)
                raise RouteHeldError(
                    f"route recovery probe {round_number}/{self.resume_probe_rounds} had unknown outcome: {exc}",
                    self.snapshot(),
                ) from exc

            raw_metadata = dict(metadata) if isinstance(metadata, Mapping) else None
            response_text = text if isinstance(text, str) else str(text)
            with self._locked_state() as current:
                target = current["recovery_probes"][probe_index]
                target["provenance"] = _json_safe(raw_metadata)
                target["response_text"] = response_text
                target["response_sha256"] = hashlib.sha256(
                    response_text.encode("utf-8")
                ).hexdigest()
                target["error"] = "response_received_validation_pending"
                self._write(current)
            try:
                provenance = validate_adopted_call(
                    metadata,
                    self.model,
                    used_response_ids=probe_ids,
                    label=f"recovery_probe_{round_number}",
                    binding=self.formal_binding,
                )
                schema.validate_call_provenance(
                    provenance,
                    expected_model=self.model,
                    project_root=PROJECT,
                )
                if response_text.strip() != "ROUTE_RECOVERED":
                    raise ValueError(
                        f"recovery probe text must be exactly 'ROUTE_RECOVERED', got {response_text!r}"
                    )
            except Exception as exc:
                with self._locked_state() as current:
                    target = current["recovery_probes"][probe_index]
                    target["finished_at_utc"] = _utc_now()
                    target["outcome"] = "rejected"
                    target["error"] = sanitize_error_text(exc)
                    self._write(current)
                raise RouteHeldError(
                    f"route recovery probe {round_number}/{self.resume_probe_rounds} failed: {exc}",
                    self.snapshot(),
                ) from exc
            with self._locked_state() as current:
                target = current["recovery_probes"][probe_index]
                target["finished_at_utc"] = _utc_now()
                target["outcome"] = "adopted"
                target["provenance"] = provenance
                target["error"] = None
                self._write(current)
            consecutive += 1

        with self._locked_state() as current:
            current["state"] = "healthy"
            current["hold_kind"] = None
            current["held_at_utc"] = None
            current["consecutive_infrastructure_failures"] = 0
            current["infrastructure_streak_started_at_utc"] = None
            self._write(current)
        _append_run_status_event(
            self.run_root,
            event_type="route_resume",
            model=self.model,
            route=self.route,
            detail=f"passed {self.resume_probe_rounds} exact-model/completed probes",
            state="running",
            formal_binding=self.formal_binding,
        )


class RouteGuardedAdapter:
    """Adapter wrapper implementing durable holds and exponential 429 retry."""

    def __init__(self, adapter: Any, breaker: PersistentRouteCircuitBreaker) -> None:
        self._adapter = adapter
        self.route_breaker = breaker
        self._rate_limit_streak = 0

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        try:
            value = self._adapter.generate(*args, **kwargs)
        except RouteHeldError:
            raise
        except Exception as exc:
            category = self.route_breaker.record_failure(exc)
            if category == "rate_limited":
                self._rate_limit_streak += 1
                if self._rate_limit_streak <= self.route_breaker.rate_limit_retries:
                    delay = self.route_breaker.rate_limit_base_seconds * (
                        2 ** (self._rate_limit_streak - 1)
                    )
                    if delay:
                        self.route_breaker._sleep(delay)
            else:
                self._rate_limit_streak = 0
            raise
        self._rate_limit_streak = 0
        self.route_breaker.record_success()
        return value

    def generate_bound(self, *args: Any, **kwargs: Any) -> Any:
        try:
            if hasattr(self._adapter, "generate_bound"):
                value = self._adapter.generate_bound(*args, **kwargs)
            else:
                # Test/diagnostic adapters use the legacy one-argument protocol;
                # production formal adapters always implement generate_bound.
                value = self._adapter.generate(args[0])
        except RouteHeldError:
            raise
        except Exception as exc:
            category = self.route_breaker.record_failure(exc)
            if category == "rate_limited":
                self._rate_limit_streak += 1
                if self._rate_limit_streak <= self.route_breaker.rate_limit_retries:
                    delay = self.route_breaker.rate_limit_base_seconds * (
                        2 ** (self._rate_limit_streak - 1)
                    )
                    self.route_breaker._sleep(delay)
            else:
                self._rate_limit_streak = 0
            raise
        self._rate_limit_streak = 0
        self.route_breaker.record_success()
        return value

    def consume_last_response_metadata(self) -> Any:
        return self._adapter.consume_last_response_metadata()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


def _strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_strict_object,
        parse_constant=_reject_constant,
    )


def _read_strict_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
        return _strict_json_loads(text)
    except Exception as exc:
        raise InputIntegrityError(f"invalid strict JSON at {path}: {exc}") from exc


def _append_run_status_event(
    run_root: Path,
    *,
    event_type: str,
    model: str | None,
    route: str | None,
    detail: str | None,
    state: str | None = None,
    completed_level_rows: int | None = None,
    adopted_calls: int | None = None,
    formal_binding: Mapping[str, Any] | None = None,
) -> None:
    """Atomically append one schema-valid run event across all five workers."""
    root = _guard_run_root(run_root)
    status_path = root / schema.RUN_STATUS_PATH
    lock_path = root / ".locks" / "strict_cf_run_status.lock"
    with ProcessLock(lock_path, scope="strict-cf-run-status", timeout=30.0):
        if not status_path.is_file():
            raise InputIntegrityError(f"strict-CF run status is missing: {status_path}")
        try:
            status = _strict_json_loads(status_path.read_text(encoding="utf-8", errors="strict"))
            schema.validate_run_status(status, expected_lineage_id=root.name)
        except Exception as exc:
            raise InputIntegrityError(f"invalid strict-CF run status: {exc}") from exc
        status = dict(status)
        events = list(status["events"])
        now = _utc_now()
        binding_projection = (
            {
                "formal_pointer_sha256": formal_binding["formal_pointer_sha256"],
                "bundle_sha256": formal_binding["bundle_sha256"],
                "cohort_root_sha256": formal_binding["campaign"]["cohort_root_sha256"],
                "protocol_sha256": formal_binding["protocol_sha256"],
            }
            if formal_binding is not None
            else {
                "formal_pointer_sha256": None,
                "bundle_sha256": None,
                "cohort_root_sha256": None,
                "protocol_sha256": None,
            }
        )
        events.append({
            "sequence": len(events),
            "at_utc": now,
            "type": event_type,
            "generation_model": model,
            "route": route,
            **binding_projection,
            "detail": detail,
        })
        status["events"] = events
        status["updated_at_utc"] = now
        if state is not None:
            status["state"] = state
        if completed_level_rows is not None and (
            isinstance(completed_level_rows, bool)
            or not isinstance(completed_level_rows, int)
        ):
            raise InputIntegrityError("completed_level_rows update must be an integer")
        if adopted_calls is not None and (
            isinstance(adopted_calls, bool) or not isinstance(adopted_calls, int)
        ):
            raise InputIntegrityError("adopted_calls update must be an integer")
        progress = {name: dict(entry) for name, entry in status["model_progress"].items()}
        if model is not None and formal_binding is not None:
            model_root = root / CHECKPOINTS_REL / model
            model_complete = 0
            if model_root.exists():
                for checkpoint_file in model_root.glob("*/*/L[1-5].json"):
                    try:
                        checkpoint_value = _strict_json_loads(
                            checkpoint_file.read_text(encoding="utf-8", errors="strict")
                        )
                    except Exception as exc:
                        raise InputIntegrityError(
                            f"cannot derive status from checkpoint {checkpoint_file}: {exc}"
                        ) from exc
                    if isinstance(checkpoint_value, Mapping) and checkpoint_value.get("complete") is True:
                        model_complete += 1
            execution_state = progress[model]["execution_state"]
            if event_type in {"route_hold", "outage"}:
                execution_state = "held"
            elif event_type == "launch_ready":
                execution_state = "ready"
            elif event_type in {"run_started", "route_resume", "launch_started"}:
                execution_state = "running"
            elif model_complete == schema.EXPECTED_LEVEL_ROWS_PER_MODEL:
                execution_state = "complete"
            progress[model] = {
                "binding_state": "formal",
                "execution_state": execution_state,
                "formal_pointer_sha256": formal_binding["formal_pointer_sha256"],
                "bundle_sha256": formal_binding["bundle_sha256"],
                "completed_level_rows": model_complete,
                "adopted_calls": model_complete * schema.EXPECTED_ADOPTED_CALLS_PER_LEVEL,
            }
        status["model_progress"] = progress
        status["completed_level_rows"] = sum(
            entry["completed_level_rows"] for entry in progress.values()
        )
        status["adopted_calls"] = sum(entry["adopted_calls"] for entry in progress.values())
        if completed_level_rows is not None and status["completed_level_rows"] < completed_level_rows:
            raise InputIntegrityError("derived checkpoint progress is below requested status count")
        if adopted_calls is not None and status["adopted_calls"] < adopted_calls:
            raise InputIntegrityError("derived adopted progress is below requested status count")
        schema.validate_run_status(status, expected_lineage_id=root.name)
        atomic_replace_json(status_path, status)


def _schema_call(names: Sequence[str], *args: Any, **kwargs: Any) -> Any:
    """Call the first public schema helper present in the concurrent schema."""
    for name in names:
        function = getattr(schema, name, None)
        if callable(function):
            return function(*args, **kwargs)
    return None


def _guard_run_root(run_root: Path) -> Path:
    root = run_root.expanduser().resolve(strict=False)
    lowered = {part.casefold() for part in root.parts}
    forbidden = {"experiment_b", "results", "debug_logs", "canonical"}
    bad = sorted(lowered & forbidden)
    if bad:
        raise InputIntegrityError(
            f"strict-CF refuses legacy/canonical/Experiment-B paths: {bad}"
        )
    try:
        lineage_id = schema.validate_lineage_id(root.name)
    except Exception as exc:
        raise InputIntegrityError(f"invalid strict-CF run directory name: {exc}") from exc
    expected = (CANONICAL_RUNS_ROOT / lineage_id).resolve(strict=False)
    if root != expected:
        raise InputIntegrityError(
            f"run directory must be the canonical strict-CF path {expected}, got {root}"
        )
    return root


def _manifest_file_entry(manifest: Mapping[str, Any], relative: str) -> Mapping[str, Any]:
    """Find the unique manifest declaration for one exact relative path."""
    candidates: list[Mapping[str, Any]] = []
    names = {relative, Path(relative).as_posix()}
    for container_name in ("files", "artifacts", "snapshots", "inputs"):
        container = manifest.get(container_name)
        if not isinstance(container, Mapping):
            continue
        for key, value in container.items():
            if str(key).replace("\\", "/") in names and isinstance(value, Mapping):
                candidates.append(value)
            elif isinstance(value, Mapping):
                declared_path = value.get("path", value.get("relative_path"))
                if isinstance(declared_path, str) and declared_path.replace("\\", "/") in names:
                    candidates.append(value)
    for key in ("actual_snapshot", "actual_levels", "snapshot"):
        value = manifest.get(key)
        if isinstance(value, Mapping):
            declared_path = value.get("path", value.get("relative_path", relative))
            if isinstance(declared_path, str) and declared_path.replace("\\", "/") in names:
                candidates.append(value)
    unique: list[Mapping[str, Any]] = []
    for item in candidates:
        if not any(item is existing for existing in unique):
            unique.append(item)
    if len(unique) != 1:
        raise InputIntegrityError(
            f"manifest must declare {relative!r} exactly once; found {len(unique)} declarations"
        )
    return unique[0]


def _entry_hash(entry: Mapping[str, Any]) -> str:
    value = entry.get("sha256", entry.get("file_sha256"))
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise InputIntegrityError("snapshot declaration lacks lowercase SHA-256")
    return value


def _entry_count(entry: Mapping[str, Any]) -> int:
    value = entry.get("row_count", entry.get("count", entry.get("rows")))
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputIntegrityError("snapshot declaration lacks integer row_count")
    return value


def _validate_actual_row(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise InputIntegrityError(f"snapshot row {index} is not an object")
    detached = dict(row)
    try:
        validated = schema.validate_actual_snapshot_row(
            detached,
            path=f"actual_snapshot_row[{index}]",
        )
    except Exception as exc:
        raise InputIntegrityError(f"snapshot row {index} fails strict schema: {exc}") from exc
    detached = dict(validated)
    required_strings = (
        "generation_model",
        "domain",
        "id",
        "source_text_sha256",
        "level",
    )
    for field in required_strings:
        if not isinstance(detached.get(field), str) or not detached[field]:
            raise InputIntegrityError(f"snapshot row {index} has invalid {field}")
    actual = detached.get("actual")
    if not isinstance(actual, Mapping):
        raise InputIntegrityError(f"snapshot row {index} has no actual pair")
    for field in ("prompt", "output"):
        if not isinstance(actual.get(field), str) or not actual[field].strip():
            raise InputIntegrityError(f"snapshot row {index} has invalid actual.{field}")
    if detached["generation_model"] not in MODELS:
        raise InputIntegrityError(f"snapshot row {index} has unknown model")
    if detached["level"] not in {"L1", "L2", "L3", "L4", "L5"}:
        raise InputIntegrityError(f"snapshot row {index} has invalid level")
    return detached


def _level_key(row: Mapping[str, Any]) -> str:
    result = _schema_call(("level_key", "actual_level_key"), row)
    if result is not None:
        if isinstance(result, str):
            return result
        if isinstance(result, Sequence):
            return "\x1f".join(str(value) for value in result)
        return str(result)
    return "\x1f".join(
        str(row[field])
        for field in ("generation_model", "domain", "id", "source_text_sha256", "level")
    )


def verify_creation_inventory(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed if any prepared execution-stack file changed before resume."""
    root = _guard_run_root(run_root)
    preparation_path = root / schema.ARTIFACT_SPECS["preparation_lineage"][0]
    expected_hash = manifest["artifacts"]["preparation_lineage"]["sha256"]
    if file_sha256(preparation_path) != expected_hash:
        raise InputIntegrityError("preparation lineage hash differs from immutable manifest")
    try:
        preparation = _strict_json_loads(
            preparation_path.read_text(encoding="utf-8", errors="strict")
        )
        inventory = preparation["creation_inventory"]
        schema.validate_creation_inventory(inventory)
        from experiment_a.prepare_strict_cf_v1 import (
            validate_historical_repair_lineage,
        )

        validate_historical_repair_lineage(preparation, manifest)
    except Exception as exc:
        raise InputIntegrityError(f"invalid preparation creation inventory: {exc}") from exc

    entries = [*inventory["code"], *inventory["clients"]]
    seen_paths: set[Path] = set()
    for entry in entries:
        path = Path(entry["path"]).resolve(strict=False)
        try:
            path.relative_to(PROJECT.resolve())
        except ValueError as exc:
            raise InputIntegrityError(f"creation inventory path escapes project: {path}") from exc
        if path in seen_paths:
            raise InputIntegrityError(f"creation inventory repeats path: {path}")
        seen_paths.add(path)
        if not path.is_file() or file_sha256(path) != entry["sha256"]:
            raise InputIntegrityError(f"prepared execution-stack file changed: {path}")

    required = {
        (HERE / "strict_cf_schema.py").resolve(),
        (HERE / "prepare_strict_cf_v1.py").resolve(),
        (HERE / "analyze_strict_cf_v1.py").resolve(),
        (HERE / "strict_cf_routes.py").resolve(),
        (HERE / "strict_cf_transport.py").resolve(),
        (HERE / "strict_cf_route_bundle.py").resolve(),
        (HERE / "register_strict_cf_route_v1.py").resolve(),
        (HERE / "run_strict_cf_v1.py").resolve(),
        (HERE / "run_strict_cf_parallel.py").resolve(),
        (HERE / "finalize_strict_cf_v1.py").resolve(),
        (PROJECT / "human_contribution" / "metrics.py").resolve(),
        (PROJECT / "human_contribution" / "compression.py").resolve(),
    }
    missing = sorted(str(path) for path in required - seen_paths)
    if missing:
        raise InputIntegrityError(
            f"creation inventory does not pin the complete strict-CF execution stack: {missing}"
        )
    return dict(inventory)


def load_run_inputs(run_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    """Load and integrity-check the immutable manifest plus 20,000-row snapshot."""
    root = _guard_run_root(run_root)
    manifest_path = root / MANIFEST_NAME
    snapshot_path = root / ACTUAL_SNAPSHOT_REL
    if not manifest_path.is_file() or not snapshot_path.is_file():
        raise InputIntegrityError(
            f"run requires {manifest_path} and manifest-declared {snapshot_path}"
        )
    if (root / FINALIZED_NAME).exists():
        raise InputIntegrityError(f"run is already finalized: {root / FINALIZED_NAME}")

    manifest_bytes = manifest_path.read_bytes()
    manifest = _read_strict_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise InputIntegrityError("manifest root must be an object")
    manifest = dict(manifest)
    try:
        validated = validate_manifest_full(
            manifest,
            run_dir=root,
            project_root=PROJECT,
            require_finalized=False,
        )
    except Exception as exc:
        raise InputIntegrityError(f"manifest fails strict schema: {exc}") from exc
    manifest = dict(validated)
    creation_inventory = verify_creation_inventory(root, manifest)

    entry = _manifest_file_entry(manifest, Path(ACTUAL_SNAPSHOT_REL).as_posix())
    expected_hash = _entry_hash(entry)
    expected_count = _entry_count(entry)
    if expected_count != EXPECTED_LEVEL_ROWS:
        raise InputIntegrityError(
            f"manifest snapshot row count must be {EXPECTED_LEVEL_ROWS}, got {expected_count}"
        )
    snapshot_bytes = snapshot_path.read_bytes()
    actual_hash = hashlib.sha256(snapshot_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise InputIntegrityError(
            f"snapshot hash mismatch: {actual_hash} != {expected_hash}"
        )
    if snapshot_bytes and not snapshot_bytes.endswith(b"\n"):
        raise InputIntegrityError("snapshot JSONL must end with LF")

    rows: list[dict[str, Any]] = []
    keys: set[str] = set()
    try:
        lines = snapshot_bytes.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise InputIntegrityError(f"snapshot is not strict UTF-8: {exc}") from exc
    for index, line in enumerate(lines, start=1):
        if not line:
            raise InputIntegrityError(f"blank snapshot row at line {index}")
        try:
            row = _validate_actual_row(_strict_json_loads(line), index)
        except InputIntegrityError:
            raise
        except Exception as exc:
            raise InputIntegrityError(f"invalid snapshot row {index}: {exc}") from exc
        key = _level_key(row)
        if key in keys:
            raise InputIntegrityError(f"duplicate level key at snapshot row {index}: {key!r}")
        keys.add(key)
        rows.append(row)
    if len(rows) != expected_count:
        raise InputIntegrityError(
            f"snapshot row count mismatch: {len(rows)} != {expected_count}"
        )

    bindings = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "snapshot_sha256": actual_hash,
        "snapshot_relative_path": Path(ACTUAL_SNAPSHOT_REL).as_posix(),
        "creation_inventory_sha256": schema.canonical_sha256(creation_inventory),
        "cohort_root_sha256": manifest["cohort"]["root_sha256"],
    }
    return manifest, rows, bindings


class ImmutableInputs:
    """Cheap stat gate plus definitive hashes for a run's immutable inputs."""

    def __init__(
        self,
        run_root: Path,
        bindings: Mapping[str, str],
        formal_binding: Mapping[str, Any] | None = None,
    ) -> None:
        self.root = _guard_run_root(run_root)
        self.manifest = self.root / MANIFEST_NAME
        self.snapshot = self.root / ACTUAL_SNAPSHOT_REL
        self.bindings = dict(bindings)
        try:
            manifest = _strict_json_loads(
                self.manifest.read_text(encoding="utf-8", errors="strict")
            )
            preparation_path = self.root / schema.ARTIFACT_SPECS["preparation_lineage"][0]
            preparation = _strict_json_loads(
                preparation_path.read_text(encoding="utf-8", errors="strict")
            )
            inventory = preparation["creation_inventory"]
        except Exception as exc:
            raise InputIntegrityError(f"cannot initialize immutable execution watcher: {exc}") from exc
        expected_hashes: dict[Path, str] = {
            self.manifest: self.bindings["manifest_sha256"],
            self.snapshot: self.bindings["snapshot_sha256"],
        }
        for artifact in manifest["artifacts"].values():
            digest = artifact.get("sha256")
            if isinstance(digest, str):
                expected_hashes[
                    schema.assert_path_within_run(self.root, artifact["path"], must_exist=True)
                ] = digest
        for entry in [*inventory["code"], *inventory["clients"]]:
            expected_hashes[Path(entry["path"]).resolve(strict=True)] = entry["sha256"]
        if formal_binding is not None:
            formal_path = schema.assert_path_within_run(
                self.root,
                formal_binding["formal_pointer_path"],
                must_exist=True,
            )
            expected_hashes[formal_path] = formal_binding["formal_pointer_sha256"]
            candidate = formal_binding["candidate"]
            bundle_root = Path(candidate["bundle_root"]).resolve(strict=True)
            expected_hashes[bundle_root / "bundle.json"] = candidate[
                "bundle_manifest_sha256"
            ]
            expected_hashes[bundle_root / "COMMITTED"] = candidate["committed_sha256"]
            for entry in candidate["project_dependency_inventory"]:
                expected_hashes[bundle_root / entry["path"]] = entry["sha256"]
            for entry in candidate["external_dependency_inventory"]:
                expected_hashes[Path(entry["path"]).resolve(strict=True)] = entry["sha256"]
        self._expected_hashes = expected_hashes
        self._stats = {path: path.stat() for path in expected_hashes}

    def assert_unchanged(self, *, definitive: bool = False) -> None:
        changed_stats: list[tuple[Path, os.stat_result]] = []
        for path, before in self._stats.items():
            try:
                after = path.stat()
            except OSError as exc:
                raise InputIntegrityError(f"immutable input disappeared: {path}") from exc
            before_key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            after_key = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if after_key != before_key:
                changed_stats.append((path, after))
        paths_to_hash = (
            list(self._expected_hashes)
            if definitive
            else [path for path, _ in changed_stats]
        )
        for path in paths_to_hash:
            if file_sha256(path) != self._expected_hashes[path]:
                raise InputIntegrityError(
                    f"immutable input/execution-stack bytes changed during run: {path}"
                )
        # Metadata-only touches are harmless after their bytes re-verify; use the
        # new stat tuple so they do not trigger a full hash on every later call.
        for path, after in changed_stats:
            self._stats[path] = after


def normalize_prompt(text: str) -> str:
    """Unicode/whitespace/case normalization used only for uniqueness checks."""
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def parse_five_numbered_prompts(text: str) -> list[str]:
    """Accept exactly five one-line entries numbered 1..5 and no other prose."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("reconstruction response is empty")
    if "```" in text:
        raise ValueError("reconstruction response contains a code fence")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != CF_COUNT:
        raise ValueError(f"reconstruction must have exactly five nonblank lines; got {len(lines)}")
    prompts: list[str] = []
    numbers: list[int] = []
    for line in lines:
        match = _NUMBERED.fullmatch(line)
        if match is None:
            raise ValueError("every reconstruction line must be one numbered prompt with no prose")
        numbers.append(int(match.group(1)))
        prompt = " ".join(match.group(2).split())
        if len(prompt) < 10 or not any(character.isalnum() for character in prompt):
            raise ValueError("each reconstructed prompt must contain at least 10 content characters")
        prompts.append(prompt)
    if numbers != [1, 2, 3, 4, 5]:
        raise ValueError(f"reconstruction numbering must be exactly 1..5; got {numbers!r}")
    normalized = [normalize_prompt(prompt) for prompt in prompts]
    if len(set(normalized)) != CF_COUNT:
        raise ValueError("reconstructed prompts are not normalized-unique")
    return prompts


def build_reconstruction_prompt(actual_output: str) -> str:
    return (
        "Infer five plausible human prompts that could independently have produced "
        "the AI output below. Return exactly five distinct prompts as exactly five "
        "single lines numbered 1. through 5. Do not write a preamble, epilogue, "
        "heading, code fence, bullet, explanation, or any unnumbered line. Each "
        "prompt must be complete and must not contain a newline.\n\n"
        "AI OUTPUT:\n---\n"
        f"{actual_output}\n"
        "---\n\nReturn only lines 1. through 5."
    )


def _obvious_repetition(text: str) -> bool:
    normalized = normalize_prompt(text)
    if not normalized:
        return True
    if len(set(normalized)) <= 3 and len(normalized) >= 30:
        return True
    words = re.findall(r"\w+", normalized, flags=re.UNICODE)
    if len(words) >= 20 and len(set(words)) < 5:
        return True
    if len(words) >= 12:
        longest_run = run = 1
        for previous, current in zip(words, words[1:]):
            run = run + 1 if current == previous else 1
            longest_run = max(longest_run, run)
        if longest_run >= 8:
            return True
        trigrams = list(zip(words, words[1:], words[2:]))
        if trigrams and max(trigrams.count(item) for item in set(trigrams)) >= 6:
            return True
    return False


def validate_generated_output(text: Any, previous_outputs: Iterable[str] = ()) -> str:
    """Return stripped CF text after length/error/repetition/duplicate checks."""
    if not isinstance(text, str):
        raise ValueError("generated output is not text")
    value = text.strip()
    if len(value) < MIN_OUTPUT_CHARS:
        raise ValueError(f"generated output is shorter than {MIN_OUTPUT_CHARS} characters")
    if not any(character.isalnum() for character in value):
        raise ValueError("generated output has no letter or digit")
    lowered = value.casefold()
    if any(lowered.startswith(prefix) for prefix in _ERROR_PREFIXES):
        raise ValueError("generated output is error-like")
    refusal_prefix = " ".join(unicodedata.normalize("NFKC", value).split())[:400]
    if any(pattern.search(refusal_prefix) for pattern in _TEXTUAL_REFUSAL_STARTS):
        raise ValueError("generated output is a textual refusal")
    if _obvious_repetition(value):
        raise ValueError("generated output is repetitious")
    normalized = normalize_prompt(value)
    if normalized in {normalize_prompt(item) for item in previous_outputs}:
        raise ValueError("generated output duplicates an earlier counterfactual")
    return value


def _safe_source_key(row: Mapping[str, Any]) -> str:
    result = _schema_call(("safe_source_key", "checkpoint_source_key"), row)
    if isinstance(result, str) and result and result not in {".", ".."}:
        return result
    identity = schema.model_item_key(
        str(row["generation_model"]),
        str(row["domain"]),
        str(row["id"]),
        str(row["source_text_sha256"]),
    )
    source = schema.canonical_json_text(identity)
    slug_source = str(row.get("id") or row.get("source_id") or "source")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug_source).strip(" ._") or "source"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"{slug[:48]}-{digest}"


def checkpoint_path(run_root: Path, row: Mapping[str, Any]) -> Path:
    root = _guard_run_root(run_root)
    model = str(row["generation_model"])
    domain = str(row["domain"])
    level = str(row["level"])
    for value, label in ((model, "model"), (domain, "domain"), (level, "level")):
        if value in {"", ".", ".."} or "/" in value or "\\" in value:
            raise CheckpointError(f"unsafe checkpoint {label}: {value!r}")
    path = root / CHECKPOINTS_REL / model / domain / _safe_source_key(row) / f"{level}.json"
    try:
        path.resolve(strict=False).relative_to((root / CHECKPOINTS_REL).resolve(strict=False))
    except ValueError as exc:
        raise CheckpointError("checkpoint path escaped the checkpoint root") from exc
    return path


def model_checkpoint_bindings(
    campaign_bindings: Mapping[str, str],
    formal_binding: Mapping[str, Any],
) -> dict[str, str]:
    return {
        **dict(campaign_bindings),
        "formal_pointer_path": str(formal_binding["formal_pointer_path"]),
        "formal_pointer_sha256": str(formal_binding["formal_pointer_sha256"]),
        "bundle_sha256": str(formal_binding["bundle_sha256"]),
        "protocol_sha256": str(formal_binding["protocol_sha256"]),
        "transport_abi_sha256": str(formal_binding["transport_abi_sha256"]),
    }


def _new_checkpoint(row: Mapping[str, Any], bindings: Mapping[str, str]) -> dict[str, Any]:
    actual = row["actual"]
    return {
        "schema": _CHECKPOINT_SCHEMA,
        "schema_version": _CHECKPOINT_VERSION,
        "level_key": _level_key(row),
        "source_row_sha256": canonical_row_sha256(row),
        "input_binding": dict(bindings),
        "key": {
            field: row.get(field)
            for field in (
                "generation_model",
                "domain",
                "id",
                "source_id",
                "source_index",
                "source_text_sha256",
                "level",
                "source_cluster",
                "semantic_key",
            )
        },
        "actual": {"prompt": actual["prompt"], "output": actual["output"]},
        "reconstruction": None,
        "counterfactuals": [],
        "attempts": [],
        "complete": False,
    }


def _validate_checkpoint(
    value: Any,
    row: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    formal_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if bindings.get("formal_pointer_sha256") is not None:
        if formal_binding is None:
            raise CheckpointError("formal checkpoint validation requires its route binding")
        campaign = formal_binding.get("campaign")
        if not isinstance(campaign, Mapping) or (
            formal_binding.get("generation_model") != row["generation_model"]
            or formal_binding.get("formal_pointer_sha256")
            != bindings.get("formal_pointer_sha256")
            or formal_binding.get("bundle_sha256") != bindings.get("bundle_sha256")
            or formal_binding.get("protocol_sha256") != bindings.get("protocol_sha256")
            or formal_binding.get("transport_abi_sha256")
            != bindings.get("transport_abi_sha256")
            or campaign.get("manifest_sha256") != bindings.get("manifest_sha256")
            or campaign.get("cohort_root_sha256") != bindings.get("cohort_root_sha256")
        ):
            raise CheckpointError("formal route binding differs from checkpoint inputs")
    if not isinstance(value, Mapping):
        raise CheckpointError("checkpoint root is not an object")
    checkpoint = dict(value)
    if checkpoint.get("schema") != _CHECKPOINT_SCHEMA or checkpoint.get("schema_version") != _CHECKPOINT_VERSION:
        raise CheckpointError("checkpoint schema mismatch")
    if checkpoint.get("level_key") != _level_key(row):
        raise CheckpointError("checkpoint level key mismatch")
    if checkpoint.get("source_row_sha256") != canonical_row_sha256(row):
        raise CheckpointError("checkpoint source row hash mismatch")
    if checkpoint.get("input_binding") != dict(bindings):
        raise CheckpointError("checkpoint immutable-input binding mismatch")
    if checkpoint.get("actual") != {
        "prompt": row["actual"]["prompt"],
        "output": row["actual"]["output"],
    }:
        raise CheckpointError("checkpoint actual pair differs from snapshot")
    if not isinstance(checkpoint.get("attempts"), list):
        raise CheckpointError("checkpoint attempts must be a list")
    stage_ordinals: dict[str, int] = {}
    adopted_by_stage: dict[str, Mapping[str, Any]] = {}
    attempt_response_ids: set[str] = set()
    allowed_stages = {"reconstruction", *(f"cf_{index}" for index in range(1, CF_COUNT + 1))}
    for position, raw_attempt in enumerate(checkpoint["attempts"]):
        if not isinstance(raw_attempt, Mapping):
            raise CheckpointError(f"checkpoint attempt {position} is not an object")
        stage = raw_attempt.get("stage")
        outcome = raw_attempt.get("outcome")
        if stage not in allowed_stages:
            raise CheckpointError(f"checkpoint attempt has invalid stage: {stage!r}")
        if outcome not in {"adopted", "rejected", "outcome_unknown"}:
            raise CheckpointError(f"checkpoint attempt has invalid outcome: {outcome!r}")
        invocation_id = raw_attempt.get("invocation_id")
        if not isinstance(invocation_id, str) or not re.fullmatch(r"[0-9a-f]{64}", invocation_id):
            raise CheckpointError(f"checkpoint {stage} attempt lacks invocation_id")
        expected_attempt_binding = {
            "formal_pointer_sha256": bindings.get("formal_pointer_sha256"),
            "bundle_sha256": bindings.get("bundle_sha256"),
            "cohort_root_sha256": bindings.get("cohort_root_sha256"),
            "protocol_sha256": bindings.get("protocol_sha256"),
        }
        if raw_attempt.get("formal_binding") != expected_attempt_binding:
            raise CheckpointError(f"checkpoint {stage} attempt binding mismatch")
        expected_ordinal = stage_ordinals.get(stage, 0) + 1
        if raw_attempt.get("ordinal") != expected_ordinal:
            raise CheckpointError(f"checkpoint {stage} attempt ordinals are not contiguous")
        stage_ordinals[stage] = expected_ordinal
        request_hash = raw_attempt.get("request_sha256")
        if not isinstance(request_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", request_hash):
            raise CheckpointError(f"checkpoint {stage} attempt lacks request_sha256")
        response_text = raw_attempt.get("response_text")
        response_hash = raw_attempt.get("response_sha256")
        if response_text is None:
            if response_hash is not None:
                raise CheckpointError(f"checkpoint {stage} has response hash without text")
        elif not isinstance(response_text, str) or response_hash != hashlib.sha256(
            response_text.encode("utf-8")
        ).hexdigest():
            raise CheckpointError(f"checkpoint {stage} response text/hash mismatch")
        if outcome in {"adopted", "rejected"} and not isinstance(
            raw_attempt.get("finished_at_utc"), str
        ):
            raise CheckpointError(f"checkpoint finished {stage} attempt lacks timestamp")
        provenance = raw_attempt.get("provenance")
        response_id = provenance.get("response_id") if isinstance(provenance, Mapping) else None
        if isinstance(response_id, str) and response_id.strip():
            response_id = response_id.strip()
            if response_id in attempt_response_ids:
                raise CheckpointError(f"checkpoint reuses response ID {response_id!r}")
            attempt_response_ids.add(response_id)
        if outcome == "adopted":
            if stage in adopted_by_stage:
                raise CheckpointError(f"checkpoint has multiple adopted attempts for {stage}")
            try:
                checked = validate_adopted_call(
                    provenance,
                    row["generation_model"],
                    label=stage,
                    binding=formal_binding,
                )
                if formal_binding is not None:
                    schema.validate_bound_call_provenance(
                        checked,
                        expected_model=row["generation_model"],
                        path=f"checkpoint.{stage}.provenance",
                    )
                    if checked.get("invocation_id") != invocation_id:
                        raise CheckpointError(
                            f"checkpoint {stage} provenance invocation mismatch"
                        )
                else:
                    schema.validate_call_provenance(
                        checked,
                        expected_model=row["generation_model"],
                        project_root=PROJECT,
                        path=f"checkpoint.{stage}.provenance",
                    )
            except Exception as exc:
                raise CheckpointError(f"checkpoint adopted {stage} provenance invalid: {exc}") from exc
            adopted_by_stage[stage] = raw_attempt
    reconstruction = checkpoint.get("reconstruction")
    counterfactuals = checkpoint.get("counterfactuals")
    if reconstruction is not None:
        if not isinstance(reconstruction, Mapping):
            raise CheckpointError("checkpoint reconstruction is invalid")
        try:
            parsed = parse_five_numbered_prompts(str(reconstruction.get("response_text", "")))
        except ValueError as exc:
            raise CheckpointError(f"checkpoint reconstruction parse failed: {exc}") from exc
        if reconstruction.get("prompts") != parsed:
            raise CheckpointError("checkpoint prompts do not match reconstruction text")
        adopted = adopted_by_stage.get("reconstruction")
        if adopted is None or adopted.get("provenance") != reconstruction.get("provenance"):
            raise CheckpointError("checkpoint reconstruction lacks its one matching adopted attempt")
        if adopted.get("response_text") != reconstruction.get("response_text"):
            raise CheckpointError("checkpoint reconstruction text differs from adopted attempt")
    elif "reconstruction" in adopted_by_stage:
        raise CheckpointError("checkpoint adopted reconstruction is missing its stage payload")
    if not isinstance(counterfactuals, list) or len(counterfactuals) > CF_COUNT:
        raise CheckpointError("checkpoint counterfactual list is invalid")
    expected_indexes = list(range(1, len(counterfactuals) + 1))
    if [item.get("index") if isinstance(item, Mapping) else None for item in counterfactuals] != expected_indexes:
        raise CheckpointError("checkpoint CF indexes are not a contiguous prefix")
    if reconstruction is None and counterfactuals:
        raise CheckpointError("checkpoint has CFs without an adopted reconstruction")
    previous_outputs: list[str] = []
    if reconstruction is not None:
        prompts = reconstruction["prompts"]
        for index, item in enumerate(counterfactuals, start=1):
            if not isinstance(item, Mapping) or item.get("prompt") != prompts[index - 1]:
                raise CheckpointError(f"checkpoint cf_{index} prompt mismatch")
            try:
                output = validate_generated_output(item.get("output"), previous_outputs)
            except ValueError as exc:
                raise CheckpointError(f"checkpoint cf_{index} output invalid: {exc}") from exc
            previous_outputs.append(output)
            stage = f"cf_{index}"
            adopted = adopted_by_stage.get(stage)
            if adopted is None or adopted.get("provenance") != item.get("provenance"):
                raise CheckpointError(f"checkpoint {stage} lacks its one matching adopted attempt")
            if adopted.get("response_text") != item.get("output"):
                raise CheckpointError(f"checkpoint {stage} output differs from adopted attempt")
    for index in range(len(counterfactuals) + 1, CF_COUNT + 1):
        if f"cf_{index}" in adopted_by_stage:
            raise CheckpointError(f"checkpoint adopted cf_{index} is missing its stage payload")
    expected_requests = {
        "reconstruction": build_reconstruction_prompt(str(row["actual"]["output"]))
    }
    if reconstruction is not None:
        if reconstruction.get("request_sha256") != hashlib.sha256(
            expected_requests["reconstruction"].encode("utf-8")
        ).hexdigest():
            raise CheckpointError("checkpoint reconstruction request hash is not canonical")
        expected_requests.update({
            f"cf_{index}": prompt
            for index, prompt in enumerate(reconstruction["prompts"], start=1)
        })
    for raw_attempt in checkpoint["attempts"]:
        stage = raw_attempt["stage"]
        request = expected_requests.get(stage)
        if request is None:
            raise CheckpointError(f"checkpoint has {stage} attempt without canonical prompt")
        expected_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        if raw_attempt.get("request_sha256") != expected_hash:
            raise CheckpointError(f"checkpoint {stage} request hash is not bound to canonical request")
    should_complete = reconstruction is not None and len(counterfactuals) == CF_COUNT
    expected_adopted = ({"reconstruction"} if reconstruction is not None else set()) | {
        f"cf_{index}" for index in range(1, len(counterfactuals) + 1)
    }
    if set(adopted_by_stage) != expected_adopted:
        raise CheckpointError("checkpoint adopted-attempt set differs from completed stages")
    if should_complete and len(adopted_by_stage) != 6:
        raise CheckpointError("complete checkpoint must contain exactly six adopted calls")
    if checkpoint.get("complete") is not should_complete:
        raise CheckpointError("checkpoint complete flag is inconsistent")
    result = _schema_call(("validate_checkpoint",), checkpoint, row)
    return dict(result) if isinstance(result, Mapping) else checkpoint


def load_checkpoint(
    path: Path,
    row: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    formal_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if bindings.get("formal_pointer_sha256") is not None and formal_binding is None:
        raise CheckpointError("formal checkpoint load requires its route binding")
    if not path.exists():
        return _new_checkpoint(row, bindings)
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
    except Exception as exc:
        raise CheckpointError(f"invalid checkpoint JSON {path}: {exc}") from exc
    return _validate_checkpoint(
        value,
        row,
        bindings,
        formal_binding=formal_binding,
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _begin_attempt(
    checkpoint: dict[str, Any],
    path: Path,
    *,
    stage: str,
    request: str,
) -> int:
    """Persist an outcome-unknown intent before an external call is possible."""
    ordinal = 1 + sum(
        1 for item in checkpoint["attempts"] if item.get("stage") == stage
    )
    now = _utc_now()
    binding = checkpoint["input_binding"]
    invocation_id = hashlib.sha256(
        (
            f"{checkpoint['level_key']}\0{stage}\0{ordinal}\0"
            f"{binding.get('formal_pointer_sha256', 'legacy')}"
        ).encode("utf-8")
    ).hexdigest()
    record = {
        "stage": stage,
        "ordinal": ordinal,
        "invocation_id": invocation_id,
        "formal_binding": {
            "formal_pointer_sha256": binding.get("formal_pointer_sha256"),
            "bundle_sha256": binding.get("bundle_sha256"),
            "cohort_root_sha256": binding.get("cohort_root_sha256"),
            "protocol_sha256": binding.get("protocol_sha256"),
        },
        "outcome": "outcome_unknown",
        "started_at_utc": now,
        "finished_at_utc": None,
        "request_sha256": hashlib.sha256(request.encode("utf-8")).hexdigest(),
        "provenance": None,
        "response_text": None,
        "response_sha256": None,
        "reason": "intent_persisted_before_external_call",
    }
    checkpoint["attempts"].append(record)
    _write_checkpoint(path, checkpoint)
    return len(checkpoint["attempts"]) - 1


def _update_attempt(
    checkpoint: dict[str, Any],
    path: Path,
    attempt_index: int,
    *,
    outcome: str,
    provenance: Mapping[str, Any] | None = None,
    response_text: str | None = None,
    reason: str | None = None,
    finished: bool = True,
) -> None:
    """Atomically update the same pre-call intent; never append a result copy."""
    if outcome not in {"adopted", "rejected", "outcome_unknown"}:
        raise ValueError(f"invalid attempt outcome: {outcome!r}")
    record = checkpoint["attempts"][attempt_index]
    record["outcome"] = outcome
    record["provenance"] = _json_safe(provenance) if provenance is not None else None
    record["response_text"] = response_text
    record["response_sha256"] = (
        hashlib.sha256(response_text.encode("utf-8")).hexdigest()
        if response_text is not None
        else None
    )
    record["reason"] = reason
    record["finished_at_utc"] = _utc_now() if finished else None
    _write_checkpoint(path, checkpoint)


def _write_checkpoint(path: Path, checkpoint: Mapping[str, Any]) -> None:
    atomic_replace_json(path, checkpoint)


def _exception_provenance(error: BaseException) -> Mapping[str, Any] | None:
    value = getattr(error, "provenance", None)
    return value if isinstance(value, Mapping) else None


def _validate_raw_call(
    adapter: Any,
    raw_metadata: Mapping[str, Any] | None,
    *,
    model: str,
    stage: str,
    used_response_ids: MutableSet[str],
    replay: bool,
) -> dict[str, Any]:
    breaker = getattr(adapter, "route_breaker", None)
    formal_binding = breaker.formal_binding if breaker is not None else None
    try:
        provenance = validate_adopted_call(
            raw_metadata,
            model,
            used_response_ids=None if replay else used_response_ids,
            label=stage,
            binding=formal_binding,
        )
        if formal_binding is not None:
            schema.validate_bound_call_provenance(
                provenance,
                expected_model=model,
                path=stage,
            )
        else:
            schema.validate_call_provenance(
                provenance,
                expected_model=model,
                project_root=PROJECT,
                path=stage,
            )
    except Exception as exc:
        if breaker is not None:
            breaker.record_failure(exc)
        raise
    if replay:
        used_response_ids.add(provenance["response_id"])
    return provenance


def _pending_received_attempt(
    checkpoint: Mapping[str, Any], stage: str
) -> int | None:
    """Return the earliest undecided attempt that already has a raw response."""
    for index, attempt in enumerate(checkpoint["attempts"]):
        if (
            attempt.get("stage") == stage
            and attempt.get("outcome") == "outcome_unknown"
            and isinstance(attempt.get("response_text"), str)
            and isinstance(attempt.get("provenance"), Mapping)
        ):
            return index
    return None


def _replay_received_call(
    adapter: Any,
    checkpoint: dict[str, Any],
    path: Path,
    attempt_index: int,
    *,
    model: str,
    stage: str,
    used_response_ids: MutableSet[str],
) -> tuple[str, dict[str, Any], int]:
    """Deterministically adjudicate a persisted raw response without an API call."""
    attempt = checkpoint["attempts"][attempt_index]
    response_text = attempt["response_text"]
    raw_metadata = attempt["provenance"]
    try:
        provenance = _validate_raw_call(
            adapter,
            raw_metadata,
            model=model,
            stage=stage,
            used_response_ids=used_response_ids,
            replay=True,
        )
    except Exception as exc:
        _update_attempt(
            checkpoint,
            path,
            attempt_index,
            outcome="rejected",
            provenance=raw_metadata,
            response_text=response_text,
            reason=sanitize_error_text(exc),
        )
        raise
    return response_text, provenance, attempt_index


def _call_with_intent(
    adapter: Any,
    checkpoint: dict[str, Any],
    path: Path,
    request: str,
    *,
    model: str,
    stage: str,
    failure_id: str,
    used_response_ids: MutableSet[str],
) -> tuple[str, dict[str, Any], int]:
    """Persist intent/raw outcome around one call, then validate provenance."""
    attempt_index = _begin_attempt(checkpoint, path, stage=stage, request=request)
    breaker = getattr(adapter, "route_breaker", None)
    if breaker is not None:
        breaker.set_context(failure_id, stage)
    try:
        formal_binding = breaker.formal_binding if breaker is not None else None
        needs_backend_c = (
            formal_binding is not None
            and formal_binding.get("coordination", {}).get("kind")
            == "experiment_b_backend_c"
        ) or (
            formal_binding is None and route_for_model(model).adapter_kind == "backend_c"
        )
        if needs_backend_c:
            try:
                assert_backend_c_handoff(
                    expected_validation_files=(
                        breaker.expected_backend_c_validation_files
                        if breaker is not None
                        else None
                    )
                )
            except Exception as exc:
                if breaker is not None:
                    breaker.hold_handoff_conflict(exc)
                raise
        attempt = checkpoint["attempts"][attempt_index]
        if hasattr(adapter, "generate_bound"):
            response_text = adapter.generate_bound(
                request,
                invocation_id=attempt["invocation_id"],
                intent_ordinal=attempt["ordinal"],
            )
        else:
            response_text = adapter.generate(request)
        raw_metadata = adapter.consume_last_response_metadata()
    except Exception as exc:
        _update_attempt(
            checkpoint,
            path,
            attempt_index,
            outcome="outcome_unknown",
            provenance=_exception_provenance(exc),
            reason=sanitize_error_text(exc),
        )
        raise

    # Preserve the raw returned text and metadata before any parser/protocol
    # validation.  A crash after receipt can never erase what was observed.
    raw_provenance = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else None
    _update_attempt(
        checkpoint,
        path,
        attempt_index,
        outcome="outcome_unknown",
        provenance=raw_provenance,
        response_text=response_text if isinstance(response_text, str) else str(response_text),
        reason="response_received_validation_pending",
        finished=False,
    )
    try:
        provenance = _validate_raw_call(
            adapter,
            raw_metadata,
            model=model,
            stage=stage,
            used_response_ids=used_response_ids,
            replay=False,
        )
    except Exception as exc:
        _update_attempt(
            checkpoint,
            path,
            attempt_index,
            outcome="rejected",
            provenance=raw_provenance,
            response_text=response_text if isinstance(response_text, str) else str(response_text),
            reason=sanitize_error_text(exc),
        )
        raise
    return str(response_text), provenance, attempt_index


def _assert_execution_stack(
    adapter: Any,
    immutable_inputs: ImmutableInputs | None,
    *,
    failure_id: str,
    stage: str,
) -> None:
    if immutable_inputs is None:
        return
    try:
        immutable_inputs.assert_unchanged()
    except InputIntegrityError as exc:
        breaker = getattr(adapter, "route_breaker", None)
        if breaker is not None:
            breaker.set_context(failure_id, stage)
            breaker.hold_execution_stack_drift(exc)
        raise


def process_level(
    adapter: Any,
    row: Mapping[str, Any],
    *,
    run_root: Path,
    bindings: Mapping[str, str],
    used_response_ids: MutableSet[str],
    immutable_inputs: ImmutableInputs | None = None,
    formal_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attempt all missing stages for one level, checkpointing every outcome.

    The first failed/rejected missing stage raises :class:`StageAttemptError`.
    Calling this function again resumes from the next genuinely missing stage.
    """
    path = checkpoint_path(run_root, row)
    breaker = getattr(adapter, "route_breaker", None)
    effective_binding = (
        formal_binding
        if formal_binding is not None
        else (breaker.formal_binding if breaker is not None else None)
    )
    checkpoint = load_checkpoint(
        path,
        row,
        bindings,
        formal_binding=effective_binding,
    )
    model = str(row["generation_model"])
    if checkpoint["complete"]:
        return checkpoint

    if checkpoint["reconstruction"] is None:
        stage = "reconstruction"
        request = build_reconstruction_prompt(str(row["actual"]["output"]))
        pending_index = _pending_received_attempt(checkpoint, stage)
        try:
            if pending_index is not None:
                response_text, provenance, attempt_index = _replay_received_call(
                    adapter,
                    checkpoint,
                    path,
                    pending_index,
                    model=model,
                    stage=stage,
                    used_response_ids=used_response_ids,
                )
            else:
                _assert_execution_stack(
                    adapter,
                    immutable_inputs,
                    failure_id=_level_key(row),
                    stage=stage,
                )
                response_text, provenance, attempt_index = _call_with_intent(
                    adapter,
                    checkpoint,
                    path,
                    request,
                    model=model,
                    stage=stage,
                    failure_id=_level_key(row),
                    used_response_ids=used_response_ids,
                )
        except (ConfirmedOutage, RouteHeldError):
            raise
        except Exception as exc:
            if immutable_inputs is not None:
                immutable_inputs.assert_unchanged()
            raise StageAttemptError(
                f"{_level_key(row)} {stage}: {exc}",
                category=classify_route_failure(exc),
            ) from exc
        try:
            prompts = parse_five_numbered_prompts(response_text)
        except Exception as exc:
            _update_attempt(
                checkpoint,
                path,
                attempt_index,
                outcome="rejected",
                provenance=provenance,
                response_text=response_text,
                reason=sanitize_error_text(exc),
            )
            if immutable_inputs is not None:
                immutable_inputs.assert_unchanged()
            raise StageAttemptError(
                f"{_level_key(row)} {stage}: {exc}",
                category=classify_route_failure(exc),
            ) from exc
        checkpoint["reconstruction"] = {
            "request_sha256": hashlib.sha256(request.encode("utf-8")).hexdigest(),
            "response_text": response_text,
            "prompts": prompts,
            "provenance": provenance,
        }
        _update_attempt(
            checkpoint,
            path,
            attempt_index,
            outcome="adopted",
            provenance=provenance,
            response_text=response_text,
        )
        _assert_execution_stack(
            adapter,
            immutable_inputs,
            failure_id=_level_key(row),
            stage=stage,
        )

    prompts = checkpoint["reconstruction"]["prompts"]
    while len(checkpoint["counterfactuals"]) < CF_COUNT:
        index = len(checkpoint["counterfactuals"]) + 1
        stage = f"cf_{index}"
        prompt = prompts[index - 1]
        pending_index = _pending_received_attempt(checkpoint, stage)
        try:
            if pending_index is not None:
                response_text, provenance, attempt_index = _replay_received_call(
                    adapter,
                    checkpoint,
                    path,
                    pending_index,
                    model=model,
                    stage=stage,
                    used_response_ids=used_response_ids,
                )
            else:
                _assert_execution_stack(
                    adapter,
                    immutable_inputs,
                    failure_id=_level_key(row),
                    stage=stage,
                )
                response_text, provenance, attempt_index = _call_with_intent(
                    adapter,
                    checkpoint,
                    path,
                    prompt,
                    model=model,
                    stage=stage,
                    failure_id=_level_key(row),
                    used_response_ids=used_response_ids,
                )
        except (ConfirmedOutage, RouteHeldError):
            raise
        except Exception as exc:
            if immutable_inputs is not None:
                immutable_inputs.assert_unchanged()
            raise StageAttemptError(
                f"{_level_key(row)} {stage}: {exc}",
                category=classify_route_failure(exc),
            ) from exc
        try:
            output = validate_generated_output(
                response_text,
                (item["output"] for item in checkpoint["counterfactuals"]),
            )
        except Exception as exc:
            _update_attempt(
                checkpoint,
                path,
                attempt_index,
                outcome="rejected",
                provenance=provenance,
                response_text=response_text,
                reason=sanitize_error_text(exc),
            )
            if immutable_inputs is not None:
                immutable_inputs.assert_unchanged()
            raise StageAttemptError(
                f"{_level_key(row)} {stage}: {exc}",
                category=classify_route_failure(exc),
            ) from exc
        checkpoint["counterfactuals"].append({
            "index": index,
            "prompt": prompt,
            "output": output,
            "provenance": provenance,
        })
        checkpoint["complete"] = len(checkpoint["counterfactuals"]) == CF_COUNT
        _update_attempt(
            checkpoint,
            path,
            attempt_index,
            outcome="adopted",
            provenance=provenance,
            response_text=output,
        )
        _assert_execution_stack(
            adapter,
            immutable_inputs,
            failure_id=_level_key(row),
            stage=stage,
        )

    return _validate_checkpoint(
        checkpoint,
        row,
        bindings,
        formal_binding=effective_binding,
    )


def _iter_checkpoint_files(run_root: Path) -> Iterable[Path]:
    checkpoint_root = _guard_run_root(run_root) / CHECKPOINTS_REL
    if checkpoint_root.exists():
        yield from sorted(checkpoint_root.glob("*/*/*/L[1-5].json"))


def collect_historical_response_ids(run_root: Path) -> set[str]:
    """Reserve all seven actual/intermediate call IDs from immutable model items."""
    root = _guard_run_root(run_root)
    path = root / schema.ARTIFACT_SPECS["model_items"][0]
    if not path.is_file():
        raise InputIntegrityError(f"immutable model-items snapshot is missing: {path}")
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise InputIntegrityError("model-items JSONL must end with LF")
    try:
        lines = data.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise InputIntegrityError(f"model-items snapshot is not strict UTF-8: {exc}") from exc
    if len(lines) != schema.EXPECTED_MODEL_ITEMS:
        raise InputIntegrityError(
            f"model-items row count mismatch: {len(lines)} != {schema.EXPECTED_MODEL_ITEMS}"
        )
    seen: set[str] = set()
    cutover_membership: Mapping[tuple[str, str], Mapping[str, Any]] | None = None
    cutover_lineage: Mapping[str, Any] | None = None
    cutover_artifact: Mapping[str, Any] | None = None
    for line_number, line in enumerate(lines, start=1):
        try:
            row = _strict_json_loads(line)
            model = row["generation_model"]
            tier = row["provenance_tier"]
            provenance = row["actual_api_provenance"]
            attestation = row["historical_cutover_attestation"]
            if tier == schema.PROVENANCE_TIER_EXACT:
                if attestation is not None:
                    raise InputIntegrityError(
                        "current exact item carries historical cutover attestation"
                    )
                schema.validate_actual_item_provenance(
                    provenance,
                    expected_model=model,
                    project_root=PROJECT,
                    seen_response_ids=seen,
                )
                expected_hash = schema.canonical_row_sha256(provenance)
            elif tier == schema.PROVENANCE_TIER_HISTORICAL_API821:
                schema.validate_historical_backend_b_actual_item_provenance(
                    provenance,
                    expected_model=model,
                    seen_response_ids=seen,
                )
                schema.validate_historical_cutover_attestation(
                    attestation,
                    expected_model=model,
                    expected_domain=row["domain"],
                    expected_id=row["id"],
                )
                if (
                    cutover_membership is None
                    or cutover_lineage is None
                    or cutover_artifact is None
                ):
                    from experiment_a.prepare_strict_cf_v1 import (
                        load_frozen_backend_c_cutover_manifest,
                    )

                    manifest = _read_strict_json(root / MANIFEST_NAME)
                    cutover_artifact = manifest["artifacts"][
                        "historical_cutover_manifest"
                    ]
                    cutover_membership, cutover_lineage = (
                        load_frozen_backend_c_cutover_manifest(root, manifest)
                    )
                scope = cutover_membership.get((model, row["domain"]))
                scope_lineage = cutover_lineage["scopes"][model][row["domain"]]
                if (
                    scope is None
                    or row["id"] not in scope["ids"]
                    or attestation["scope_ids_sha256"]
                    != scope_lineage["ids_sha256"]
                    or attestation["scope_row_count"]
                    != scope_lineage["row_count"]
                ):
                    raise InputIntegrityError(
                        "historical item is not bound to its cutover-manifest scope"
                    )
                cutover_path = Path(attestation["manifest_path"]).resolve(strict=True)
                expected_cutover = schema.assert_path_within_run(
                    root,
                    cutover_artifact["path"],
                    must_exist=True,
                )
                if cutover_path != expected_cutover:
                    raise InputIntegrityError("historical cutover path is not run-local")
                if (
                    cutover_artifact["sha256"] != attestation["manifest_sha256"]
                    or cutover_lineage["sha256"] != attestation["manifest_sha256"]
                ):
                    raise InputIntegrityError("historical cutover manifest hash mismatch")
                expected_hash = schema.canonical_row_sha256(
                    {
                        "api_provenance": provenance,
                        "cutover_attestation": attestation,
                        "provenance_tier": tier,
                    }
                )
            else:
                raise InputIntegrityError(
                    f"unattested actual provenance tier {tier!r}"
                )
            if row["item_provenance_sha256"] != expected_hash:
                raise InputIntegrityError("actual item provenance hash mismatch")
        except Exception as exc:
            raise InputIntegrityError(
                f"invalid model-items provenance at line {line_number}: {exc}"
            ) from exc
    expected = schema.EXPECTED_MODEL_ITEMS * len(schema.MAIN_CALL_LABELS)
    if len(seen) != expected:
        raise InputIntegrityError(f"historical response-ID count mismatch: {len(seen)} != {expected}")
    return seen


def collect_response_ids(run_root: Path) -> set[str]:
    """Collect checkpoint/probe IDs and reject reuse across both durable stores."""
    root = _guard_run_root(run_root)
    seen: set[str] = set()

    def reserve(response_id: Any, location: str) -> None:
        if not isinstance(response_id, str) or not response_id.strip():
            return
        normalized = response_id.strip()
        if normalized in seen:
            raise CheckpointError(
                f"duplicate response ID across strict calls/probes at {location}: {normalized!r}"
            )
        seen.add(normalized)

    for path in _iter_checkpoint_files(root):
        try:
            checkpoint = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
        except Exception as exc:
            raise CheckpointError(f"cannot scan response IDs from {path}: {exc}") from exc
        attempts = checkpoint.get("attempts") if isinstance(checkpoint, Mapping) else None
        if not isinstance(attempts, list):
            raise CheckpointError(f"checkpoint has no attempts list: {path}")
        for index, attempt in enumerate(attempts):
            provenance = attempt.get("provenance") if isinstance(attempt, Mapping) else None
            response_id = provenance.get("response_id") if isinstance(provenance, Mapping) else None
            reserve(response_id, f"{path}:attempt[{index}]")

    route_dir = root / "status" / "routes"
    if route_dir.exists():
        for path in sorted(route_dir.glob("*.json")):
            try:
                state = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
                probes = state["recovery_probes"]
            except Exception as exc:
                raise CheckpointError(f"cannot scan recovery probe IDs from {path}: {exc}") from exc
            if not isinstance(probes, list):
                raise CheckpointError(f"route state has invalid recovery_probes: {path}")
            for index, probe in enumerate(probes):
                provenance = probe.get("provenance") if isinstance(probe, Mapping) else None
                response_id = (
                    provenance.get("response_id")
                    if isinstance(provenance, Mapping)
                    else probe.get("response_id") if isinstance(probe, Mapping) else None
                )
                reserve(response_id, f"{path}:recovery_probes[{index}]")
    smoke_root = root / "quarantine" / "route_smoke"
    if smoke_root.exists():
        for path in sorted(smoke_root.glob("*/*/report.json")):
            if "aggregate" in path.parts:
                continue
            try:
                report = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
                calls = report["calls"]
            except Exception as exc:
                raise CheckpointError(f"cannot scan candidate smoke IDs from {path}: {exc}") from exc
            if not isinstance(calls, list):
                raise CheckpointError(f"candidate smoke has invalid calls: {path}")
            for index, call in enumerate(calls):
                provenance = call.get("provenance") if isinstance(call, Mapping) else None
                response_id = provenance.get("response_id") if isinstance(provenance, Mapping) else None
                reserve(response_id, f"{path}:calls[{index}]")
    return seen


def _join_launch_barrier(
    run_root: Path,
    model: str,
    formal_binding: Mapping[str, Any],
    campaign_context: ValidatedCampaignContext,
    launch_id: str,
    *,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Publish READY, then cross the network boundary only after exact START."""

    if not isinstance(launch_id, str) or not launch_id or any(
        marker in launch_id for marker in ("/", "\\", "..")
    ):
        raise LaunchBarrierError("invalid launch transaction ID")
    root = _guard_run_root(run_root)
    if campaign_context.run_root != root:
        raise LaunchBarrierError("worker campaign context belongs to another run root")
    launch_root = root / "launches" / launch_id
    request_path = launch_root / "request.json"
    if not request_path.is_file():
        raise LaunchBarrierError("launch request is missing")
    request = _read_strict_json(request_path)
    expected_request_keys = {
        "schema", "schema_version", "launch_id", "nonce", "campaign",
        "models", "bindings", "review_path", "review_sha256", "created_at_utc",
    }
    if not isinstance(request, Mapping) or set(request) != expected_request_keys:
        raise LaunchBarrierError("launch request keys are invalid")
    if (
        request["schema"] != "experiment_a.strict_cf_v1.launch_request"
        or request["schema_version"] != 1
        or request["launch_id"] != launch_id
        or model not in request["models"]
    ):
        raise LaunchBarrierError("launch request identity/model mismatch")
    expected_campaign = campaign_context.campaign_identity()
    if (
        dict(request["campaign"]) != expected_campaign
        or dict(formal_binding["campaign"]) != expected_campaign
    ):
        raise LaunchBarrierError(
            "launch request, worker context, and formal binding campaign differ"
        )
    review_path = schema.assert_path_within_run(
        run_root, request["review_path"], must_exist=True
    )
    if file_sha256(review_path) != request["review_sha256"]:
        raise LaunchBarrierError("launch review acknowledgment hash mismatch")
    expected_binding = {
        "formal_pointer_sha256": formal_binding["formal_pointer_sha256"],
        "bundle_sha256": formal_binding["bundle_sha256"],
        "protocol_sha256": formal_binding["protocol_sha256"],
    }
    if request["bindings"].get(model) != expected_binding:
        raise LaunchBarrierError("launch request model binding mismatch")
    request_sha = file_sha256(request_path)
    ready_path = launch_root / "ready" / f"{model}.json"
    ready = {
        "schema": "experiment_a.strict_cf_v1.launch_ready",
        "schema_version": 1,
        "launch_id": launch_id,
        "request_sha256": request_sha,
        "nonce": request["nonce"],
        "generation_model": model,
        "pid": os.getpid(),
        "worker_token": hashlib.sha256(os.urandom(32)).hexdigest(),
        "formal_pointer_sha256": formal_binding["formal_pointer_sha256"],
        "bundle_sha256": formal_binding["bundle_sha256"],
        "protocol_sha256": formal_binding["protocol_sha256"],
        "ready_at_utc": _utc_now(),
    }
    exclusive_create_json(ready_path, ready)
    deadline = time.monotonic() + timeout_seconds
    decision_path = launch_root / "decision.json"
    while not decision_path.is_file():
        if time.monotonic() >= deadline:
            raise LaunchBarrierError("launch decision timed out before START")
        time.sleep(0.1)
    decision = _read_strict_json(decision_path)
    expected_decision_keys = {
        "schema", "schema_version", "launch_id", "decision", "request_sha256",
        "nonce", "campaign", "models", "bindings", "review_path", "review_sha256", "ready_tokens",
        "ready_tokens_sha256", "decided_at_utc",
    }
    if not isinstance(decision, Mapping) or set(decision) != expected_decision_keys:
        raise LaunchBarrierError("launch decision keys are invalid")
    if (
        decision["schema"] != "experiment_a.strict_cf_v1.launch_decision"
        or decision["schema_version"] != 1
        or decision["launch_id"] != launch_id
        or decision["request_sha256"] != request_sha
        or decision["nonce"] != request["nonce"]
        or decision["campaign"] != request["campaign"]
        or decision["models"] != request["models"]
        or decision["bindings"] != request["bindings"]
        or decision["review_path"] != request["review_path"]
        or decision["review_sha256"] != request["review_sha256"]
    ):
        raise LaunchBarrierError("launch decision does not bind the request")
    ready_tokens = decision["ready_tokens"]
    if not isinstance(ready_tokens, list) or schema.canonical_sha256(ready_tokens) != decision["ready_tokens_sha256"]:
        raise LaunchBarrierError("launch decision ready-token digest mismatch")
    expected_models = list(request["models"])
    observed_models = [entry.get("generation_model") for entry in ready_tokens]
    if observed_models != expected_models:
        raise LaunchBarrierError("launch decision READY set is incomplete or unordered")
    own = next((entry for entry in ready_tokens if entry.get("generation_model") == model), None)
    if own is None or own.get("path") != ready_path.relative_to(_guard_run_root(run_root)).as_posix() or own.get("sha256") != file_sha256(ready_path):
        raise LaunchBarrierError("launch decision does not bind this worker READY token")
    if decision["decision"] != "START":
        if decision["decision"] != "ABORT":
            set_full_validation_decision_state("INVALID")
            raise LaunchBarrierError("launch decision must be START or ABORT")
        set_full_validation_decision_state("ABORT")
        raise LaunchBarrierError("launch transaction is ABORT-terminal")
    set_full_validation_decision_state("START")
    consumed_path = launch_root / "consumed" / f"{model}.json"
    consumed = {
        "schema": "experiment_a.strict_cf_v1.launch_consumed",
        "schema_version": 1,
        "launch_id": launch_id,
        "request_sha256": request_sha,
        "decision_sha256": file_sha256(decision_path),
        "ready_sha256": file_sha256(ready_path),
        "generation_model": model,
        "worker_token": ready["worker_token"],
        "consumed_at_utc": _utc_now(),
    }
    exclusive_create_json(consumed_path, consumed)
    return {"request": request, "decision": decision, "consumed": consumed}


@contextmanager
def model_lock(model: str):
    """Use the exact Experiment-A lock namespace shared with the old runner."""
    if model not in MODELS:
        raise StrictCFError(f"model is outside strict-CF roster: {model!r}")
    lock_dir = HERE / ".locks"
    maintenance = lock_dir / "maintenance.lock"
    if maintenance.exists():
        raise StrictCFError("Experiment A maintenance/finalization is active")
    lock = ProcessLock(lock_dir / f"{model}.lock", scope=f"experiment-a:{model}")
    with lock:
        if maintenance.exists():
            raise StrictCFError("Experiment A maintenance/finalization started concurrently")
        yield lock


def preflight_model(run_root: Path, model: str) -> dict[str, Any]:
    """Perform a no-network worker preflight for one formally bound model."""
    if model not in MODELS:
        raise InputIntegrityError(f"model is outside the campaign roster: {model!r}")
    manifest, rows, campaign_bindings = load_run_inputs(run_root)
    campaign_context = build_validated_campaign_context(
        Path(run_root), manifest, campaign_bindings
    )
    selected = [row for row in rows if row["generation_model"] == model]
    if len(selected) != schema.EXPECTED_LEVEL_ROWS_PER_MODEL:
        raise InputIntegrityError(
            f"immutable snapshot has {len(selected)} rows for {model}; "
            f"expected {schema.EXPECTED_LEVEL_ROWS_PER_MODEL}"
        )
    formal_binding = load_formal_binding(
        Path(run_root), model, campaign_context=campaign_context
    )
    if formal_binding["campaign"] != campaign_context.campaign_identity():
        raise InputIntegrityError("formal binding campaign differs from validated context")
    if formal_binding["campaign"]["cohort_root_sha256"] != campaign_bindings["cohort_root_sha256"]:
        raise InputIntegrityError("formal binding cohort differs from immutable campaign")
    checkpoint_bindings = model_checkpoint_bindings(campaign_bindings, formal_binding)
    needs_backend_c = (
        formal_binding["coordination"]["kind"] == "experiment_b_backend_c"
    )
    backend_c_handoff = assert_backend_c_handoff() if needs_backend_c else None
    return {
        "manifest": manifest,
        "rows": rows,
        "selected_rows": selected,
        "campaign_context": campaign_context,
        "campaign_bindings": campaign_bindings,
        "bindings": checkpoint_bindings,
        "formal_binding": formal_binding,
        "backend_c_handoff": backend_c_handoff,
    }


def _count_complete_checkpoint_files(run_root: Path) -> int:
    count = 0
    for path in _iter_checkpoint_files(run_root):
        try:
            value = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
        except Exception as exc:
            raise CheckpointError(f"cannot count checkpoint {path}: {exc}") from exc
        if isinstance(value, Mapping) and value.get("complete") is True:
            count += 1
    return count


def _run_model_under_startup_scope(
    run_root: Path,
    model: str,
    *,
    adapter: Any | None = None,
    limit: int = 0,
    slot_root: Path | None = None,
    retries: int = 0,
    timeout_seconds: float | None = None,
    sleep_seconds: float | None = None,
    outage_threshold: int = 6,
    outage_min_seconds: float = 180.0,
    rate_limit_retries: int = 3,
    rate_limit_base_seconds: float = 2.0,
    resume_probe_rounds: int = 3,
    max_stage_attempts_per_run: int = 3,
    route_breaker: PersistentRouteCircuitBreaker | None = None,
    launch_id: str | None = None,
    launch_wait_seconds: float = 180.0,
) -> dict[str, int]:
    """Resume all missing levels for one model under the shared A model lock."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    if max_stage_attempts_per_run < 1:
        raise ValueError("max_stage_attempts_per_run must be positive")
    if launch_id is None:
        raise LaunchBarrierError(
            "formal production worker requires a READY/START launch transaction"
        )
    if adapter is not None:
        raise LaunchBarrierError(
            "formal production worker forbids adapter overrides"
        )
    root = _guard_run_root(run_root)
    with model_lock(model):
        context = preflight_model(root, model)
        rows = context["selected_rows"][:limit or None]
        immutable = ImmutableInputs(
            root, context["campaign_bindings"], context["formal_binding"]
        )
        historical_ids = collect_historical_response_ids(root)
        strict_ids = collect_response_ids(root)
        collision = historical_ids & strict_ids
        if collision:
            raise CheckpointError(
                f"strict/probe response ID collides with immutable actual provenance: "
                f"{sorted(collision)[:5]}"
            )
        used_ids = historical_ids | strict_ids
        _join_launch_barrier(
            root,
            model,
            context["formal_binding"],
            context["campaign_context"],
            launch_id,
            timeout_seconds=launch_wait_seconds,
        )
        immutable.assert_unchanged(definitive=True)
        _append_run_status_event(
            root,
            event_type="run_started",
            model=model,
            route=context["formal_binding"]["route_id"],
            detail=f"resume worker over {len(rows)} selected level rows",
            state="running",
            formal_binding=context["formal_binding"],
        )
        if adapter is None:
            raw_adapter = make_bound_adapter(
                root,
                model,
                campaign_context=context["campaign_context"],
                timeout_seconds=timeout_seconds,
            )
            emit_adapter_constructed(
                model=model,
                campaign_context=context["campaign_context"],
            )
            breaker = route_breaker or PersistentRouteCircuitBreaker(
                run_root=root,
                model=model,
                route=context["formal_binding"]["route_id"],
                threshold=outage_threshold,
                minimum_duration_seconds=outage_min_seconds,
                rate_limit_retries=rate_limit_retries,
                rate_limit_base_seconds=rate_limit_base_seconds,
                resume_probe_rounds=resume_probe_rounds,
                expected_backend_c_validation_files=(
                    context["backend_c_handoff"]["validation_files"]
                    if context["backend_c_handoff"] is not None
                    else None
                ),
                formal_binding=context["formal_binding"],
            )
            # No experimental item is touched while held.  Recovery itself must
            # pass the configured consecutive exact-model/completed probes.
            immutable.assert_unchanged(definitive=True)
            breaker.require_recovery_probes(raw_adapter)
            immutable.assert_unchanged(definitive=True)
            strict_ids = collect_response_ids(root)
            collision = historical_ids & strict_ids
            if collision:
                raise CheckpointError(
                    f"recovery/strict response ID collides with immutable actual provenance: "
                    f"{sorted(collision)[:5]}"
                )
            used_ids = historical_ids | strict_ids
            adapter = RouteGuardedAdapter(raw_adapter, breaker)

        counts = {
            "complete_before": 0,
            "completed_now": 0,
            "stage_failures": 0,
            "incomplete": 0,
        }
        for ordinal, row in enumerate(rows, start=1):
            path = checkpoint_path(root, row)
            before = load_checkpoint(
                path,
                row,
                context["bindings"],
                formal_binding=context["formal_binding"],
            )
            if before["complete"]:
                counts["complete_before"] += 1
                continue
            after = before
            last_error: StageAttemptError | None = None
            rate_limit_attempts = 0
            non_rate_attempts = 0
            attempt_budget = max_stage_attempts_per_run + rate_limit_retries + 1
            for stage_attempt in range(1, attempt_budget + 1):
                try:
                    after = process_level(
                        adapter,
                        row,
                        run_root=root,
                        bindings=context["bindings"],
                        used_response_ids=used_ids,
                        immutable_inputs=immutable,
                        formal_binding=context["formal_binding"],
                    )
                    last_error = None
                    break
                except (ConfirmedOutage, RouteHeldError):
                    try:
                        immutable.assert_unchanged(definitive=True)
                    except InputIntegrityError:
                        pass  # preserve the durable hold as the primary exit signal
                    raise
                except StageAttemptError as exc:
                    counts["stage_failures"] += 1
                    last_error = exc
                    if exc.category == "rate_limited":
                        rate_limit_attempts += 1
                        if rate_limit_attempts >= rate_limit_retries + 1:
                            immutable.assert_unchanged(definitive=True)
                            total_complete = _count_complete_checkpoint_files(root)
                            _append_run_status_event(
                                root,
                                event_type="failed",
                                model=model,
                                route=context["formal_binding"]["route_id"],
                                detail=(
                                    f"rate-limit attempts exhausted at {row['semantic_key']}; "
                                    "model worker stopped without global outage hold"
                                ),
                                state="failed",
                                completed_level_rows=total_complete,
                                formal_binding=context["formal_binding"],
                            )
                            raise RateLimitExhaustedError(
                                model,
                                _level_key(row),
                                rate_limit_attempts,
                            ) from exc
                    else:
                        non_rate_attempts += 1
                    print(
                        f"[{ordinal}/{len(rows)}] RETRY {stage_attempt}/"
                        f"{attempt_budget} {row['semantic_key']}: {exc}",
                        flush=True,
                    )
                    if non_rate_attempts >= max_stage_attempts_per_run:
                        break
            if after.get("complete") is True:
                counts["completed_now"] += 1
                print(f"[{ordinal}/{len(rows)}] COMPLETE {row['semantic_key']}", flush=True)
            else:
                counts["incomplete"] += 1
                print(
                    f"[{ordinal}/{len(rows)}] RETAINED-INCOMPLETE {row['semantic_key']}: "
                    f"{last_error}",
                    flush=True,
                )
        immutable.assert_unchanged(definitive=True)
        total_complete = _count_complete_checkpoint_files(root)
        _append_run_status_event(
            root,
            event_type="checkpoint",
            model=model,
            route=context["formal_binding"]["route_id"],
            detail=json.dumps(counts, sort_keys=True),
            state="running",
            completed_level_rows=total_complete,
            formal_binding=context["formal_binding"],
        )
        print(json.dumps({"model": model, **counts}, sort_keys=True), flush=True)
        if counts["incomplete"]:
            _append_run_status_event(
                root,
                event_type="failed",
                model=model,
                route=context["formal_binding"]["route_id"],
                detail=f"bounded retries left {counts['incomplete']} selected levels incomplete",
                state="failed",
                completed_level_rows=total_complete,
            )
            raise IncompleteRunError(counts)
        return counts


def run_model(
    run_root: Path,
    model: str,
    *,
    adapter: Any | None = None,
    limit: int = 0,
    slot_root: Path | None = None,
    retries: int = 0,
    timeout_seconds: float | None = None,
    sleep_seconds: float | None = None,
    outage_threshold: int = 6,
    outage_min_seconds: float = 180.0,
    rate_limit_retries: int = 3,
    rate_limit_base_seconds: float = 2.0,
    resume_probe_rounds: int = 3,
    max_stage_attempts_per_run: int = 3,
    route_breaker: PersistentRouteCircuitBreaker | None = None,
    launch_id: str | None = None,
    launch_wait_seconds: float = 180.0,
) -> dict[str, int]:
    """Run one formal worker inside an explicit one-validation startup scope."""

    operation_id = launch_id if isinstance(launch_id, str) and launch_id else "INVALID"
    with FullValidationScope(
        role="worker",
        model=model,
        operation_id=operation_id,
    ):
        return _run_model_under_startup_scope(
            run_root,
            model,
            adapter=adapter,
            limit=limit,
            slot_root=slot_root,
            retries=retries,
            timeout_seconds=timeout_seconds,
            sleep_seconds=sleep_seconds,
            outage_threshold=outage_threshold,
            outage_min_seconds=outage_min_seconds,
            rate_limit_retries=rate_limit_retries,
            rate_limit_base_seconds=rate_limit_base_seconds,
            resume_probe_rounds=resume_probe_rounds,
            max_stage_attempts_per_run=max_stage_attempts_per_run,
            route_breaker=route_breaker,
            launch_id=launch_id,
            launch_wait_seconds=launch_wait_seconds,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--launch-id", required=True)
    parser.add_argument("--launch-wait-seconds", type=float, default=180.0)
    parser.add_argument("--slot-root", type=Path, default=None)
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="hidden adapter retries; strict-CF requires 0 (outer stage attempts are checkpointed)",
    )
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--sleep", type=float, default=None)
    parser.add_argument("--outage-threshold", type=int, default=6)
    parser.add_argument("--outage-min-seconds", type=float, default=180.0)
    parser.add_argument("--rate-limit-retries", type=int, default=3)
    parser.add_argument("--rate-limit-base-seconds", type=float, default=2.0)
    parser.add_argument("--resume-probe-rounds", type=int, default=3)
    parser.add_argument("--max-stage-attempts", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.retries != 0:
        raise SystemExit("--retries must be 0; strict-CF outer checkpoint attempts own retries")
    try:
        run_model(
            args.run_root,
            args.model,
            slot_root=args.slot_root,
            retries=args.retries,
            timeout_seconds=args.timeout,
            sleep_seconds=args.sleep,
            outage_threshold=args.outage_threshold,
            outage_min_seconds=args.outage_min_seconds,
            rate_limit_retries=args.rate_limit_retries,
            rate_limit_base_seconds=args.rate_limit_base_seconds,
            resume_probe_rounds=args.resume_probe_rounds,
            max_stage_attempts_per_run=args.max_stage_attempts,
            launch_id=args.launch_id,
            launch_wait_seconds=args.launch_wait_seconds,
        )
    except ConfirmedOutage as exc:
        print(f"[OUTAGE GUARD] {exc}", file=sys.stderr, flush=True)
        return OUTAGE_EXIT_CODE
    except RouteHeldError as exc:
        print(f"[ROUTE HELD] {exc}", file=sys.stderr, flush=True)
        return OUTAGE_EXIT_CODE
    except IncompleteRunError as exc:
        print(f"[INCOMPLETE] {exc}", file=sys.stderr, flush=True)
        return 1
    except RateLimitExhaustedError as exc:
        print(f"[RATE LIMITED] {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANONICAL_RUNS_ROOT",
    "CF_COUNT",
    "CheckpointError",
    "ImmutableInputs",
    "IncompleteRunError",
    "InputIntegrityError",
    "MIN_OUTPUT_CHARS",
    "PersistentRouteCircuitBreaker",
    "RateLimitExhaustedError",
    "RouteGuardedAdapter",
    "RouteHeldError",
    "StageAttemptError",
    "StrictCFError",
    "build_parser",
    "build_reconstruction_prompt",
    "checkpoint_path",
    "classify_route_failure",
    "collect_response_ids",
    "load_checkpoint",
    "load_run_inputs",
    "main",
    "model_lock",
    "normalize_prompt",
    "parse_five_numbered_prompts",
    "preflight_model",
    "process_level",
    "run_model",
    "validate_generated_output",
]
