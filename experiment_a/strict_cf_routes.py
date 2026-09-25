# -*- coding: utf-8 -*-
"""Exact model routes and adopted-call checks for Experiment A strict-CF v1.

This module deliberately reuses the production adapters.  It does not contain a
fallback route: a route mismatch is data corruption, not a reason to try a
different provider.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableSet

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_a import strict_cf_schema as schema
from experiment_b.storage import lock_is_active, read_lock_owner
from experiment_a.strict_cf_route_bundle import (
    ValidatedCampaignContext,
    load_formal_binding,
)
from experiment_a.strict_cf_transport import (
    SubprocessTransportAdapter,
    TransportExecutionBinding,
)

MAX_OUTPUT_TOKENS = 4096
REASONING_EFFORT = "low"
COPILOT_SLOT_CAPACITY = 4

MODELS = schema.MODELS


class RouteError(RuntimeError):
    """A configured route or returned call provenance is not strict-CF valid."""


class Api3rdHandoffError(RouteError):
    """Experiment B has not explicitly released the shared API3rd route."""


def _hash_jsonl_with_count(path: Path) -> tuple[str, int, int, int, int, int]:
    before = path.stat()
    digest = hashlib.sha256()
    rows = 0
    size = 0
    last_byte = b""
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            rows += chunk.count(b"\n")
            size += len(chunk)
            last_byte = chunk[-1:]
    if size and last_byte != b"\n":
        raise Api3rdHandoffError(f"stable GPT validation file lacks final LF: {path}")
    after = path.stat()
    before_key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_key = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_key != after_key or size != after.st_size:
        raise Api3rdHandoffError(f"stable GPT validation file changed while hashing: {path}")
    return (
        digest.hexdigest(),
        rows,
        size,
        after.st_mtime_ns,
        after.st_dev,
        after.st_ino,
    )


def assert_backend_c_handoff(
    experiment_b_root: Path | None = None,
    *,
    expected_validation_files: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Require a promoted, inactive API3rd scope while allowing B Copilot work."""
    root = (experiment_b_root or (PROJECT / "experiment_b")).resolve(strict=False)
    migration = root / "MIGRATION_IN_PROGRESS"
    status_path = root / "outputs" / "experiment_b_status.json"
    lineage_path = root / "outputs" / "lineage_manifest.json"
    if migration.exists():
        raise Api3rdHandoffError(f"Experiment B migration is active: {migration}")
    if not status_path.is_file() or not lineage_path.is_file():
        raise Api3rdHandoffError("Experiment B status/lineage handoff artifacts are missing")
    try:
        status_bytes = status_path.read_bytes()
        lineage_bytes = lineage_path.read_bytes()
        status = json.loads(status_bytes.decode("utf-8", errors="strict"))
        lineage = json.loads(lineage_bytes.decode("utf-8", errors="strict"))
    except Exception as exc:
        raise Api3rdHandoffError(f"cannot parse Experiment B handoff artifacts: {exc}") from exc
    if not isinstance(status, Mapping):
        raise Api3rdHandoffError("Experiment B status must be an object")

    scope_markers = ("gpt-5.5", "gpt-5.6-sol", "backend_c")
    active_runs = status.get("active_runs")
    if not isinstance(active_runs, list):
        raise Api3rdHandoffError("Experiment B active_runs must be a list")
    relevant_runs = []
    for entry in active_runs:
        try:
            serialized = json.dumps(entry, ensure_ascii=False, sort_keys=True).casefold()
        except Exception:
            serialized = str(entry).casefold()
        if any(marker in serialized for marker in scope_markers):
            relevant_runs.append(entry)
    if relevant_runs:
        raise Api3rdHandoffError(
            f"Experiment B still has API3rd/GPT active runs: {relevant_runs!r}"
        )

    promotion = status.get("verification", {}).get("backend_c_route_promotion", {})
    if not isinstance(promotion, Mapping) or (
        promotion.get("state") != "PROMOTED_READY_FOR_FORMAL_RESUME"
        or tuple(promotion.get("models", ())) != ("gpt-5.5", "gpt-5.6-sol")
    ):
        raise Api3rdHandoffError("Experiment B API3rd promotion handoff is not verified")
    protocols = lineage.get("validation_protocols") if isinstance(lineage, Mapping) else None
    if not isinstance(protocols, Mapping):
        raise Api3rdHandoffError("Experiment B lineage has no validation_protocols")
    for model in ("gpt-5.5", "gpt-5.6-sol"):
        protocol = protocols.get(model)
        if not isinstance(protocol, Mapping) or (
            protocol.get("route") != "backend_c_responses_bounded600_single_call"
            or protocol.get("reasoning_effort") != "low"
            or protocol.get("max_output_tokens") != MAX_OUTPUT_TOKENS
            or protocol.get("backend_pin") is not None
        ):
            raise Api3rdHandoffError(f"Experiment B lineage has no promoted API3rd protocol for {model}")

    lock_dir = root / ".locks"
    active_or_ambiguous: list[str] = []
    if lock_dir.exists():
        for path in sorted(lock_dir.glob("*.scope.lock")):
            try:
                active = lock_is_active(path, clean_stale=False)
                owner = read_lock_owner(path) if active else {}
                scope = str(owner.get("scope", "")).casefold()
                relevant = any(marker in scope for marker in scope_markers)
            except Exception:
                active = True
                relevant = any(marker in path.name.casefold() for marker in scope_markers)
            if active and relevant:
                active_or_ambiguous.append(str(path))
    if active_or_ambiguous:
        raise Api3rdHandoffError(
            f"Experiment B scope activity blocks API3rd handoff: {active_or_ambiguous}"
        )

    counts = status.get("components", {}).get("validation", {}).get("counts", {})
    validation_files: dict[str, dict[str, Any]] = {}
    for model in ("gpt-5.5", "gpt-5.6-sol"):
        path = root / "outputs" / f"validation_{model}.jsonl"
        if not path.is_file():
            raise Api3rdHandoffError(f"stable GPT validation file is missing: {path}")
        expected = expected_validation_files.get(model) if expected_validation_files else None
        stat = path.stat()
        if expected is not None:
            stat_matches = (
                expected.get("path") == str(path.resolve())
                and expected.get("size") == stat.st_size
                and expected.get("mtime_ns") == stat.st_mtime_ns
                and expected.get("st_dev") == stat.st_dev
                and expected.get("st_ino") == stat.st_ino
                and isinstance(expected.get("sha256"), str)
                and isinstance(expected.get("row_count"), int)
            )
            if not stat_matches:
                (
                    observed_sha,
                    observed_rows,
                    observed_size,
                    observed_mtime,
                    _observed_dev,
                    _observed_ino,
                ) = _hash_jsonl_with_count(path)
                raise Api3rdHandoffError(
                    f"stable GPT validation attestation drifted for {model}: "
                    f"sha256={observed_sha}, rows={observed_rows}, "
                    f"size={observed_size}, mtime_ns={observed_mtime}"
                )
            evidence = dict(expected)
        else:
            digest, row_count, size, mtime_ns, st_dev, st_ino = (
                _hash_jsonl_with_count(path)
            )
            evidence = {
                "path": str(path.resolve()),
                "sha256": digest,
                "row_count": row_count,
                "size": size,
                "mtime_ns": mtime_ns,
                "st_dev": st_dev,
                "st_ino": st_ino,
            }
        expected_count = counts.get(model) if isinstance(counts, Mapping) else None
        if expected_count != evidence["row_count"]:
            raise Api3rdHandoffError(
                f"B status/file row-count attestation mismatch for {model}: "
                f"{expected_count!r} != {evidence['row_count']}"
            )
        validation_files[model] = evidence

    return {
        "experiment_b_root": str(root),
        "backend_c_active_runs": 0,
        "backend_c_active_locks": 0,
        "promotion_state": promotion["state"],
        "status_sha256": hashlib.sha256(status_bytes).hexdigest(),
        "lineage_sha256": hashlib.sha256(lineage_bytes).hexdigest(),
        "validation_files": validation_files,
    }


@dataclass(frozen=True)
class RouteSpec:
    model: str
    adapter_kind: str
    route: str
    gateway: str
    client: Path
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    reasoning_effort: str = REASONING_EFFORT

    def protocol_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "adapter_kind": self.adapter_kind,
            "route": self.route,
            "gateway": self.gateway,
            "client": str(self.client),
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
        }


_COPILOT_CLIENT = (PROJECT / "human_contribution" / "copilot_responses_adapter.py").resolve()
_API3RD_CLIENT = (PROJECT / "clients" / "client_gpt_multi_origin.py").resolve()

ROUTES: dict[str, RouteSpec] = {
    model: RouteSpec(
        model=model,
        adapter_kind="copilot",
        route="copilot-2.2.15-formal",
        gateway="local_slot",
        client=_COPILOT_CLIENT,
    )
    for model in MODELS[:3]
}
ROUTES.update({
    model: RouteSpec(
        model=model,
        adapter_kind="backend_c",
        route="backend_c",
        gateway="auto",
        client=_API3RD_CLIENT,
    )
    for model in MODELS[3:]
})


def route_for_model(model: str) -> RouteSpec:
    try:
        return ROUTES[model]
    except KeyError as exc:
        raise RouteError(f"model is not in the strict-CF roster: {model!r}") from exc


def make_adapter(
    model: str,
    *,
    slot_root: Path | None = None,
    retries: int = 0,
    timeout_seconds: float | None = None,
    sleep_seconds: float | None = None,
) -> Any:
    """Construct the one permitted production adapter for *model*."""
    spec = route_for_model(model)
    if retries != 0:
        raise ValueError(
            "strict-CF adapters forbid hidden retries; outer checkpoint retries own every call"
        )
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if sleep_seconds is not None and sleep_seconds < 0:
        raise ValueError("sleep_seconds must be non-negative")

    if spec.adapter_kind == "copilot":
        from human_contribution.copilot_responses_adapter import CopilotResponsesAdapter

        return CopilotResponsesAdapter(
            model_name=model,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            slot_capacity=COPILOT_SLOT_CAPACITY,
            slot_root=slot_root,
            retries=0,
            timeout_seconds=float(timeout_seconds or 180.0),
            sleep_seconds=float(0.0 if sleep_seconds is None else sleep_seconds),
        )
    if spec.adapter_kind == "backend_c":
        from human_contribution.multi_model_adapter import MultiModelAdapter

        # Legacy compatibility only.  New campaigns use make_bound_adapter(),
        # which owns automatic three-origin failover.  A pinned gateway and
        # segmented continuation are intentionally impossible here.
        return MultiModelAdapter(
            model_name=model,
            sleep_seconds=float(0.0 if sleep_seconds is None else sleep_seconds),
            api_timeout=int(timeout_seconds or 120),
            use_alt_backend=True,
            backend_pin=None,
            gpt_route="backend_c",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            segment_output_tokens=None,
            api_retries=1,
        )
    raise AssertionError(f"unhandled adapter kind: {spec.adapter_kind}")


def formal_route_for_model(
    run_root: Path,
    model: str,
    *,
    campaign_context: ValidatedCampaignContext | None = None,
) -> dict[str, Any]:
    """Load the model's sole write-once formal binding."""

    return load_formal_binding(
        Path(run_root), model, campaign_context=campaign_context
    )


def make_bound_adapter(
    run_root: Path,
    model: str,
    *,
    campaign_context: ValidatedCampaignContext | None = None,
    timeout_seconds: float | None = None,
) -> SubprocessTransportAdapter:
    """Construct the generic subprocess adapter from one formal binding."""

    formal = formal_route_for_model(
        run_root, model, campaign_context=campaign_context
    )
    candidate = formal["candidate"]
    bundle_root = Path(candidate["bundle_root"]).resolve(strict=True)
    environment = {
        "STRICT_CF_ROUTE_ID": formal["route_id"],
        "STRICT_CF_CLIENT_ID": formal["client_id"],
        "STRICT_CF_TIMEOUT_SECONDS": str(float(timeout_seconds or 180.0)),
    }
    for external in candidate["external_dependency_inventory"]:
        role = str(external["role"]).upper().replace("-", "_")
        environment[f"STRICT_CF_EXTERNAL_{role}"] = str(external["path"])
        if external["role"] == "backend_c_client":
            environment["STRICT_CF_API3RD_CLIENT_PATH"] = str(external["path"])
    runtime = candidate["runtime_fingerprint"]
    execution = TransportExecutionBinding(
        lineage_id=formal["campaign"]["lineage_id"],
        manifest_sha256=formal["campaign"]["manifest_sha256"],
        cohort_root_sha256=formal["campaign"]["cohort_root_sha256"],
        generation_model=model,
        bundle_sha256=formal["bundle_sha256"],
        formal_pointer_sha256=formal["formal_pointer_sha256"],
        route_id=formal["route_id"],
        client_id=formal["client_id"],
        entrypoint=(bundle_root / candidate["entrypoint"]).resolve(strict=True),
        python_executable=Path(runtime["python_executable"]).resolve(strict=True),
        working_directory=bundle_root,
        environment=environment,
    )
    return SubprocessTransportAdapter(
        execution,
        timeout_seconds=float(timeout_seconds or 180.0),
    )


def make_candidate_adapter(
    run_root: Path,
    model: str,
    bundle_sha256: str,
    *,
    campaign_context: ValidatedCampaignContext | None = None,
    timeout_seconds: float | None = None,
) -> tuple[SubprocessTransportAdapter, dict[str, Any]]:
    """Construct the generic adapter for one unpromoted smoke candidate."""

    from experiment_a.strict_cf_route_bundle import load_candidate_bundle

    root = Path(run_root).resolve(strict=True)
    candidate = load_candidate_bundle(
        root,
        model=model,
        bundle_sha256=bundle_sha256,
        campaign_context=campaign_context,
    )
    bundle_root = Path(candidate["bundle_root"]).resolve(strict=True)
    environment = {
        "STRICT_CF_ROUTE_ID": candidate["route_id"],
        "STRICT_CF_CLIENT_ID": candidate["client_id"],
        "STRICT_CF_TIMEOUT_SECONDS": str(float(timeout_seconds or 180.0)),
    }
    for external in candidate["external_dependency_inventory"]:
        role = str(external["role"]).upper().replace("-", "_")
        environment[f"STRICT_CF_EXTERNAL_{role}"] = str(external["path"])
        if external["role"] == "backend_c_client":
            environment["STRICT_CF_API3RD_CLIENT_PATH"] = str(external["path"])
    campaign = candidate["campaign"]
    execution = TransportExecutionBinding(
        lineage_id=campaign["lineage_id"],
        manifest_sha256=campaign["manifest_sha256"],
        cohort_root_sha256=campaign["cohort_root_sha256"],
        generation_model=model,
        bundle_sha256=bundle_sha256,
        formal_pointer_sha256=None,
        route_id=candidate["route_id"],
        client_id=candidate["client_id"],
        entrypoint=(bundle_root / candidate["entrypoint"]).resolve(strict=True),
        python_executable=Path(candidate["runtime_fingerprint"]["python_executable"]).resolve(strict=True),
        working_directory=bundle_root,
        environment=environment,
    )
    adapter = SubprocessTransportAdapter(
        execution, timeout_seconds=float(timeout_seconds or 180.0)
    )
    binding = {
        "campaign": campaign,
        "formal_pointer_sha256": None,
        "bundle_sha256": bundle_sha256,
        "transport_abi_sha256": candidate["transport_abi_sha256"],
        "route_id": candidate["route_id"],
        "client_id": candidate["client_id"],
        "coordination": candidate["coordination"],
    }
    return adapter, binding


def _validate_bound_call(
    metadata: Mapping[str, Any],
    model: str,
    binding: Mapping[str, Any],
    *,
    used_response_ids: MutableSet[str] | None,
    label: str,
) -> dict[str, Any]:
    value = dict(metadata)
    checks = (
        (value.get("route_id") == binding["route_id"], "route_id mismatch"),
        (value.get("client_id") == binding["client_id"], "client_id mismatch"),
        (value.get("requested_model") == model, "requested_model mismatch"),
        (value.get("returned_model") == model, "returned_model mismatch"),
        (value.get("terminal_status") == "completed", "terminal_status must be completed"),
        (value.get("incomplete_details") in (None, {}), "incomplete_details must be empty"),
        (value.get("max_output_tokens") == 4096, "max_output_tokens must be 4096"),
        (value.get("reasoning_effort") == "low", "reasoning_effort must be low"),
        (value.get("alias_used") is False, "alias is forbidden"),
        (value.get("fallback_used") is False, "fallback is forbidden"),
        (value.get("provider_attempt_count") == 1, "provider_attempt_count must be one"),
        (value.get("transport_abi_sha256") == binding["transport_abi_sha256"], "transport ABI mismatch"),
        (
            value.get("formal_binding") == {
                "formal_pointer_sha256": binding["formal_pointer_sha256"],
                "bundle_sha256": binding["bundle_sha256"],
            },
            "formal binding mismatch",
        ),
        (
            value.get("campaign_binding") == {
                "lineage_id": binding["campaign"]["lineage_id"],
                "manifest_sha256": binding["campaign"]["manifest_sha256"],
                "cohort_root_sha256": binding["campaign"]["cohort_root_sha256"],
            },
            "campaign binding mismatch",
        ),
    )
    for passed, reason in checks:
        if not passed:
            raise RouteError(f"{label}: {reason}")
    response_id = value.get("response_id")
    if not isinstance(response_id, str) or not response_id.strip():
        raise RouteError(f"{label}: response_id must be nonempty")
    response_id = response_id.strip()
    if used_response_ids is not None and response_id in used_response_ids:
        raise RouteError(f"{label}: duplicate response_id {response_id!r}")
    usage = value.get("usage")
    if not isinstance(usage, Mapping) or isinstance(usage.get("output_tokens"), bool) or not isinstance(usage.get("output_tokens"), int) or usage["output_tokens"] < 1:
        raise RouteError(f"{label}: usage.output_tokens must be positive")
    captured = value.get("captured_at_utc")
    if not isinstance(captured, str) or not captured:
        raise RouteError(f"{label}: captured_at_utc is required")
    value["response_id"] = response_id
    value["usage"] = dict(usage)
    if used_response_ids is not None:
        used_response_ids.add(response_id)
    return value


def _resolved_path(value: Any, field: str) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        raise RouteError(f"missing {field} provenance")
    try:
        return Path(value).resolve(strict=False)
    except (OSError, ValueError, TypeError) as exc:
        raise RouteError(f"invalid {field} provenance: {value!r}") from exc


def validate_adopted_call(
    metadata: Mapping[str, Any] | None,
    model: str,
    *,
    used_response_ids: MutableSet[str] | None = None,
    label: str = "call",
    binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a detached strict provenance record or raise :class:`RouteError`.

    ``used_response_ids`` is mutated only after every other check passes, making
    duplicate detection safe for callers that retain rejected attempts.
    """
    if not isinstance(metadata, Mapping):
        raise RouteError(f"{label}: missing call provenance")
    if binding is not None:
        return _validate_bound_call(
            metadata,
            model,
            binding,
            used_response_ids=used_response_ids,
            label=label,
        )
    spec = route_for_model(model)
    value = dict(metadata)

    checks = (
        (value.get("api") == "responses", "api must be 'responses'"),
        (value.get("requested_model") == model, "requested_model mismatch"),
        (value.get("returned_model") == model, "returned_model mismatch"),
        (value.get("status") == "completed", "status must be 'completed'"),
        (value.get("incomplete_details") is None, "incomplete_details must be null"),
        (value.get("route") == spec.route, f"route must be {spec.route!r}"),
        (value.get("gateway") == spec.gateway, f"gateway must be {spec.gateway!r}"),
        (
            value.get("max_output_tokens") == MAX_OUTPUT_TOKENS,
            f"max_output_tokens must be {MAX_OUTPUT_TOKENS}",
        ),
        (
            value.get("reasoning_effort") == REASONING_EFFORT,
            f"reasoning_effort must be explicitly attested as {REASONING_EFFORT!r}",
        ),
    )
    for passed, reason in checks:
        if not passed:
            raise RouteError(f"{label}: {reason}")

    if _resolved_path(value.get("client"), "client") != spec.client:
        raise RouteError(f"{label}: client provenance mismatch")

    response_id = value.get("response_id")
    if not isinstance(response_id, str) or not response_id.strip():
        raise RouteError(f"{label}: response_id must be a non-empty string")
    response_id = response_id.strip()
    if used_response_ids is not None and response_id in used_response_ids:
        raise RouteError(f"{label}: duplicate response_id {response_id!r}")

    usage = value.get("usage")
    if not isinstance(usage, Mapping) or not usage:
        raise RouteError(f"{label}: missing usage provenance")
    output_tokens = usage.get("output_tokens")
    if isinstance(output_tokens, bool) or not isinstance(output_tokens, int) or output_tokens <= 0:
        raise RouteError(f"{label}: usage.output_tokens must be a positive integer")

    value["response_id"] = response_id
    value["usage"] = dict(usage)
    if used_response_ids is not None:
        used_response_ids.add(response_id)
    return value


def protocol_manifest() -> dict[str, dict[str, Any]]:
    """Return a deterministic copy of the complete strict route table."""
    return {model: ROUTES[model].protocol_dict() for model in MODELS}


__all__ = [
    "Api3rdHandoffError",
    "COPILOT_SLOT_CAPACITY",
    "MAX_OUTPUT_TOKENS",
    "MODELS",
    "REASONING_EFFORT",
    "ROUTES",
    "RouteError",
    "RouteSpec",
    "assert_backend_c_handoff",
    "formal_route_for_model",
    "make_adapter",
    "make_bound_adapter",
    "make_candidate_adapter",
    "protocol_manifest",
    "route_for_model",
    "validate_adopted_call",
]
