"""False-positive-resistant outage classification and per-worker circuit breaking.

The guard never kills a process by PID.  It wraps one Experiment A adapter and
raises :class:`ConfirmedOutage` only after repeated outage-eligible logical-call
failures with no intervening successful API call.  The worker that owns the
adapter then exits through its normal lock-cleanup path.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from experiment_b.storage import atomic_replace_json

OUTAGE_EXIT_CODE = 75
OUTAGE_ELIGIBLE = frozenset({"transport", "server_5xx"})

_HTTP_STATUS = re.compile(
    r"(?:(?:http|api)(?:\s+error)?|status(?:_code)?)\s*[:=]?\s*['\"]?(\d{3})\b",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|api[-_ ]?key\s*[:=]\s*|token\s*[:=]\s*)"
    r"[^\s,;]+"
)


def sanitize_error_text(error: BaseException | str, limit: int = 500) -> str:
    """Return bounded diagnostic text without common credential forms."""
    text = " ".join(str(error).replace("\x00", " ").split())
    text = _SECRET.sub(lambda match: match.group(1) + "<redacted>", text)
    return text[:limit]


def classify_failure(error: BaseException | str) -> str:
    """Classify a failed logical model call without conflating quality and outage.

    A lone read/subprocess timeout is deliberately ``indeterminate``.  HTTP 429
    and 529 are capacity states, not evidence that the machine lost networking.
    """
    text = sanitize_error_text(error).casefold()
    statuses = {int(value) for value in _HTTP_STATUS.findall(text)}

    if 429 in statuses or "too many requests" in text or "rate limit" in text:
        return "rate_limited"
    if 529 in statuses or "overloaded" in text:
        return "overloaded"
    if statuses & {400, 401, 403, 404, 405, 409, 413, 415, 422}:
        return "auth_or_config"
    if statuses & {500, 502, 503, 504}:
        return "server_5xx"

    protocol_markers = (
        "model mismatch", "response status=", "responses api status=",
        "stop_reason", "finish_reason", "incomplete", "content_filter",
        "content filter", "no visible text", "no output_text", "invalid json",
        "response shape is ambiguous", "invalid output", "short output",
    )
    if any(marker in text for marker in protocol_markers):
        return "protocol_or_quality"
    if "slot" in text and any(marker in text for marker in ("timeout", "capacity", "acquire")):
        return "local_capacity"

    transport_markers = (
        "unable to reach proxy", "all endpoints are unavailable",
        "connection refused", "connection reset", "connection aborted",
        "connection closed unexpectedly", "remote end closed connection",
        "remotedisconnected", "network is unreachable", "host is unreachable",
        "name or service not known", "temporary failure in name resolution",
        "nodename nor servname", "getaddrinfo failed", "dns lookup failed",
        "winerror 10061", "winerror 10050", "winerror 10051", "winerror 10053",
        "winerror 10054", "winerror 11001", "unexpected_eof_while_reading",
        "unexpected eof", "eof occurred in violation of protocol",
        "tlsv1 alert internal error", "fetch failed",
    )
    if any(marker in text for marker in transport_markers):
        return "transport"

    timeout_markers = (
        "subprocess timeout", "timed out", "timeout expired", "read timeout",
        "winerror 10060",
    )
    if statuses & {408, 425} or any(marker in text for marker in timeout_markers):
        return "indeterminate_timeout"
    return "other"


@dataclass(frozen=True)
class FailureEvidence:
    observed_at_utc: str
    monotonic_seconds: float
    category: str
    error_type: str
    message: str


class ConfirmedOutage(RuntimeError):
    """Repeated outage-eligible failures confirmed for one owned worker."""

    def __init__(self, report: dict[str, Any], report_path: Path | None = None) -> None:
        self.report = report
        self.report_path = report_path
        suffix = f"; report={report_path}" if report_path else ""
        super().__init__(
            f"confirmed {report['last_category']} outage for {report['model']} after "
            f"{report['failure_count']} consecutive logical-call failures{suffix}"
        )


class OutageCircuitBreaker:
    """Open only on repeated transport/5xx failures with no intervening success."""

    def __init__(
        self,
        *,
        model: str,
        route: str,
        threshold: int = 6,
        minimum_duration_seconds: float = 180.0,
        maximum_gap_seconds: float = 3600.0,
        report_dir: Path | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] | None = None,
    ) -> None:
        if threshold < 2:
            raise ValueError("outage threshold must be at least 2")
        if minimum_duration_seconds < 0:
            raise ValueError("minimum outage duration cannot be negative")
        if maximum_gap_seconds <= 0:
            raise ValueError("maximum outage failure gap must be positive")
        self.model = model
        self.route = route
        self.threshold = int(threshold)
        self.minimum_duration_seconds = float(minimum_duration_seconds)
        self.maximum_gap_seconds = float(maximum_gap_seconds)
        self.report_dir = report_dir
        self._monotonic = monotonic
        self._utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self._failures: list[FailureEvidence] = []
        self.success_count = 0

    @property
    def consecutive_failures(self) -> tuple[FailureEvidence, ...]:
        return tuple(self._failures)

    def record_success(self) -> None:
        """A successful real model call defeats the current outage hypothesis."""
        self.success_count += 1
        self._failures.clear()

    def record_failure(self, error: BaseException) -> str:
        """Record one logical-call failure and raise when the circuit opens."""
        category = classify_failure(error)
        now = self._monotonic()
        observed = self._utcnow().astimezone(timezone.utc)

        if category not in OUTAGE_ELIGIBLE:
            self._failures.clear()
            return category
        if self._failures and now - self._failures[-1].monotonic_seconds > self.maximum_gap_seconds:
            self._failures.clear()

        self._failures.append(FailureEvidence(
            observed_at_utc=observed.isoformat(),
            monotonic_seconds=now,
            category=category,
            error_type=type(error).__name__,
            message=sanitize_error_text(error),
        ))
        duration = now - self._failures[0].monotonic_seconds
        if len(self._failures) < self.threshold or duration < self.minimum_duration_seconds:
            return category

        report = {
            "schema_version": 1,
            "status": "confirmed_outage",
            "scope": "owned_model_worker_only",
            "model": self.model,
            "route": self.route,
            "pid": os.getpid(),
            "confirmed_at_utc": observed.isoformat(),
            "threshold": self.threshold,
            "minimum_duration_seconds": self.minimum_duration_seconds,
            "observed_duration_seconds": round(duration, 6),
            "failure_count": len(self._failures),
            "last_category": category,
            "successes_since_start": self.success_count,
            "evidence": [
                {
                    "observed_at_utc": item.observed_at_utc,
                    "category": item.category,
                    "error_type": item.error_type,
                    "message": item.message,
                }
                for item in self._failures
            ],
            "data_policy": "failed item was not saved; normal resume retries missing IDs",
        }
        report_path = self._write_report(report)
        raise ConfirmedOutage(report, report_path)

    def _write_report(self, report: dict[str, Any]) -> Path | None:
        if self.report_dir is None:
            return None
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = report["confirmed_at_utc"].replace(":", "").replace("-", "").replace("+0000", "Z")
        safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.model)
        path = self.report_dir / f"{stamp}_{safe_model}_{os.getpid()}.json"
        atomic_replace_json(path, report)
        return path


class GuardedAdapter:
    """Transparent adapter wrapper that records every real API success/failure."""

    def __init__(self, adapter: Any, breaker: OutageCircuitBreaker) -> None:
        self._adapter = adapter
        self.breaker = breaker

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            value = getattr(self._adapter, method)(*args, **kwargs)
        except ConfirmedOutage:
            raise
        except Exception as error:
            self.breaker.record_failure(error)
            raise
        self.breaker.record_success()
        return value

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("generate", *args, **kwargs)

    def reconstruct_prompts(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("reconstruct_prompts", *args, **kwargs)

    def consume_last_response_metadata(self) -> Any:
        return self._adapter.consume_last_response_metadata()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)
