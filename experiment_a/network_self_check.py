"""Preflight the exact formal Experiment A model routes without killing processes.

Healthy models are probed once.  Only outage-eligible failures are repeated, so
rate limits, overload, authentication, protocol, and content-quality failures
cannot be promoted into a network-outage verdict.  Runtime workers use
``outage_guard.py`` to stop only themselves after the same conservative policy.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_a.outage_guard import OUTAGE_ELIGIBLE, classify_failure, sanitize_error_text
from experiment_b.storage import atomic_replace_json
from human_contribution.copilot_responses_adapter import CopilotResponsesAdapter
from human_contribution.multi_model_adapter import _call_api

FORMAL_MODELS = {
    "claude-sonnet-5": {"route": "copilot", "gateway": "local_slot"},
    "claude-opus-4-8": {"route": "copilot", "gateway": "local_slot"},
    "gemini-3.6-flash": {"route": "copilot", "gateway": "local_slot"},
    "gpt-5.5": {"route": "backend_c", "gateway": "auto"},
    "gpt-5.6-sol": {"route": "backend_c", "gateway": "auto"},
}
MAX_OUTPUT_TOKENS = 4096


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copilot_listener(timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection(("127.0.0.1", 44141), timeout=timeout):
            pass
    except OSError as error:
        return {
            "ok": False,
            "category": "local_service_down",
            "latency_seconds": round(time.perf_counter() - started, 6),
            "error": sanitize_error_text(error),
        }
    return {
        "ok": True,
        "category": "healthy",
        "latency_seconds": round(time.perf_counter() - started, 6),
    }


def probe_model(model: str, timeout: float) -> dict[str, Any]:
    """Perform one explicit-budget probe through the model's formal route."""
    config = FORMAL_MODELS[model]
    marker = "HC_HEALTH_" + secrets.token_hex(8).upper()
    prompt = f"Return exactly {marker} and nothing else."
    started = time.perf_counter()
    result: dict[str, Any] = {
        "model": model,
        "route": config["route"],
        "gateway": config["gateway"],
        "started_at_utc": utc_now(),
    }

    if config["route"] == "copilot":
        listener = _copilot_listener(min(timeout, 5.0))
        result["local_listener"] = listener
        if not listener["ok"]:
            result.update({
                "ok": False,
                "category": "local_service_down",
                "latency_seconds": round(time.perf_counter() - started, 6),
                "error": listener["error"],
            })
            return result

    try:
        if config["route"] == "copilot":
            adapter = CopilotResponsesAdapter(
                model_name=model,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                reasoning_effort="low",
                slot_capacity=4,
                retries=0,
                timeout_seconds=timeout,
                sleep_seconds=0,
            )
            text = adapter.generate(prompt)
            metadata = adapter.consume_last_response_metadata() or {}
        else:
            text, metadata = _call_api(
                prompt,
                model,
                timeout=max(1, int(timeout)),
                retries=1,
                backend_pin=(
                    int(config["gateway"])
                    if config["route"] == "backend_b"
                    else None
                ),
                gpt_route=config["route"],
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
    except Exception as error:
        result.update({
            "ok": False,
            "category": classify_failure(error),
            "latency_seconds": round(time.perf_counter() - started, 6),
            "error_type": type(error).__name__,
            "error": sanitize_error_text(error),
        })
        return result

    returned_model = metadata.get("returned_model")
    status = metadata.get("status")
    protocol_ok = (
        returned_model == model
        and status == "completed"
        and marker.casefold() in text.casefold()
        and metadata.get("response_id")
        and metadata.get("gateway") == config["gateway"]
        and metadata.get("max_output_tokens") == MAX_OUTPUT_TOKENS
    )
    result.update({
        "ok": protocol_ok,
        "category": "healthy" if protocol_ok else "protocol_or_quality",
        "latency_seconds": round(time.perf_counter() - started, 6),
        "returned_model": returned_model,
        "response_id": metadata.get("response_id"),
        "status": status,
        "marker_present": marker.casefold() in text.casefold(),
        "output_chars": len(text),
    })
    return result


def probe_control(url: str, timeout: float) -> dict[str, Any]:
    """Probe an optional independent URL; never send experiment credentials."""
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "experiment-a-health/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            response.read(256)
    except Exception as error:
        return {
            "ok": False,
            "category": classify_failure(error),
            "latency_seconds": round(time.perf_counter() - started, 6),
            "error": sanitize_error_text(error),
        }
    return {
        "ok": 200 <= status < 400,
        "category": "healthy" if 200 <= status < 400 else f"http_{status}",
        "http_status": status,
        "latency_seconds": round(time.perf_counter() - started, 6),
    }


def assess(probes: dict[str, list[dict[str, Any]]], control: dict[str, Any] | None) -> str:
    latest = [attempts[-1] for attempts in probes.values()]
    healthy = [item for item in latest if item["ok"]]
    failed = [item for item in latest if not item["ok"]]
    if not failed:
        return "healthy"
    if healthy:
        return "degraded_not_global_outage"
    if any(item["category"] not in OUTAGE_ELIGIBLE for item in failed):
        return "blocked_non_outage_failure"
    if control is None:
        return "indeterminate_no_independent_control"
    if control.get("ok"):
        return "provider_outage_likely"
    return "network_suspected"


def run_preflight(
    models: list[str], *, rounds: int, wait_seconds: float, timeout: float,
    control_url: str | None,
) -> dict[str, Any]:
    probes: dict[str, list[dict[str, Any]]] = {model: [] for model in models}
    pending = set(models)
    for round_index in range(1, rounds + 1):
        if not pending:
            break
        print(f"Probe round {round_index}/{rounds}: {', '.join(sorted(pending))}", flush=True)
        retry: set[str] = set()
        for model in sorted(pending):
            attempt = probe_model(model, timeout)
            attempt["round"] = round_index
            probes[model].append(attempt)
            print(f"  {model}: {attempt['category']}", flush=True)
            if not attempt["ok"] and attempt["category"] in OUTAGE_ELIGIBLE:
                retry.add(model)
        pending = retry
        if pending and round_index < rounds:
            time.sleep(wait_seconds)

    control = probe_control(control_url, timeout) if control_url else None
    status = assess(probes, control)
    return {
        "schema_version": 1,
        "status": status,
        "checked_at_utc": utc_now(),
        "models": models,
        "rounds_configured": rounds,
        "wait_seconds": wait_seconds,
        "timeout_seconds": timeout,
        "control_url_configured": bool(control_url),
        "control": control,
        "probes": probes,
        "safe_to_start_all": status == "healthy",
        "policy": {
            "outage_eligible": sorted(OUTAGE_ELIGIBLE),
            "rate_limit_is_outage": False,
            "overload_is_outage": False,
            "single_timeout_is_outage": False,
            "one_success_defeats_global_outage": True,
        },
    }


def _report_path(report_dir: Path, report: dict[str, Any]) -> Path:
    stamp = report["checked_at_utc"].replace(":", "").replace("-", "").replace("+00:00", "Z")
    return report_dir / f"preflight_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", choices=sorted(FORMAL_MODELS), dest="models")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--wait-seconds", type=float, default=20.0)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--control-url",
        default=os.environ.get("EXPERIMENT_A_CONTROL_URL") or None,
        help="optional independent HTTPS control; no experiment credential is sent",
    )
    parser.add_argument("--report-dir", type=Path, default=HERE / "outage_reports")
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be at least 1")
    if args.wait_seconds < 0 or args.timeout <= 0:
        parser.error("--wait-seconds must be nonnegative and --timeout positive")

    models = args.models or list(FORMAL_MODELS)
    report = run_preflight(
        models,
        rounds=args.rounds,
        wait_seconds=args.wait_seconds,
        timeout=args.timeout,
        control_url=args.control_url,
    )
    report_path = None
    if not args.no_write_report:
        report_path = _report_path(args.report_dir, report)
        atomic_replace_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "safe_to_start_all": report["safe_to_start_all"],
        "report": str(report_path) if report_path else None,
    }, ensure_ascii=False, indent=2))
    if report["status"] == "healthy":
        return 0
    if report["status"] in {"network_suspected", "provider_outage_likely"}:
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
