# -*- coding: utf-8 -*-
"""Finalize a complete Experiment A strict-CF v1 run.

Only manifest-bound checkpoints are accepted.  The finalizer builds deterministic
``final/source.jsonl`` and ``final/blackbox.jsonl`` files, writes lineage, and
installs ``FINALIZED`` last.  It never reads legacy A results/debug files,
Experiment B, or any canonical output path supplied by a caller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_a import strict_cf_schema as schema
from experiment_a.run_strict_cf_v1 import (
    CHECKPOINTS_REL,
    FINALIZED_NAME,
    MANIFEST_NAME,
    _append_run_status_event,
    _guard_run_root,
    _iter_checkpoint_files,
    _strict_json_loads,
    build_reconstruction_prompt,
    checkpoint_path,
    collect_historical_response_ids,
    collect_response_ids,
    load_checkpoint,
    load_run_inputs,
    model_checkpoint_bindings,
    verify_creation_inventory,
)
from experiment_a.strict_cf_routes import MODELS, validate_adopted_call
from experiment_a.strict_cf_route_bundle import (
    canonical_formal_binding_inventory,
    canonical_launch_inventory,
    load_formal_bindings,
)
from experiment_b.storage import (
    ProcessLock,
    atomic_replace_json,
    atomic_replace_jsonl,
    canonical_json_bytes,
    canonical_jsonl_row_bytes,
    file_sha256,
)
from human_contribution.metrics import information_gain_profile

EXPECTED_LEVEL_ROWS = schema.EXPECTED_LEVEL_ROWS
EXPECTED_ADOPTED_CALLS = EXPECTED_LEVEL_ROWS * 6
SOURCE_REL = schema.ARTIFACT_SPECS["source"][0]
BLACKBOX_REL = schema.ARTIFACT_SPECS["blackbox"][0]
LINEAGE_REL = schema.ARTIFACT_SPECS["lineage"][0]
PREPARATION_LINEAGE_REL = schema.ARTIFACT_SPECS["preparation_lineage"][0]
COMPRESSORS = schema.COMPRESSORS


class FinalizationError(RuntimeError):
    """A strict-CF run cannot be finalized without weakening invariants."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def finalization_lock():
    """Exclude all old/new A model runners through their shared lock namespace."""
    lock_dir = HERE / ".locks"
    maintenance = ProcessLock(
        lock_dir / "maintenance.lock",
        scope="experiment-a-strict-cf-finalization",
    )
    with maintenance:
        occupied = [lock_dir / f"{model}.lock" for model in MODELS if (lock_dir / f"{model}.lock").exists()]
        if occupied:
            raise FinalizationError(f"model workers are active or ambiguous: {occupied}")
        yield maintenance


def _sort_key(row: Mapping[str, Any]) -> tuple[int, int, str, str, int]:
    return (
        schema.MODELS.index(row["generation_model"]),
        schema.DOMAINS.index(row["domain"]),
        str(row["id"]),
        str(row["source_text_sha256"]),
        schema.LEVELS.index(row["level"]),
    )


def _read_route_breakers(
    run_root: Path,
    formal_bindings: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    directory = run_root / "status" / "routes"
    states: list[dict[str, Any]] = []
    if not directory.exists():
        return states
    for path in sorted(directory.glob("*.json")):
        try:
            value = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
        except Exception as exc:
            raise FinalizationError(f"invalid route-breaker state {path}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise FinalizationError(f"route-breaker state is not an object: {path}")
        value = dict(value)
        if value.get("schema") != "experiment_a.strict_cf_v1.route_breaker":
            raise FinalizationError(f"foreign route status file: {path}")
        if formal_bindings is not None:
            model = value.get("generation_model")
            formal = formal_bindings.get(model)
            expected_binding = (
                {
                    "formal_pointer_sha256": formal["formal_pointer_sha256"],
                    "bundle_sha256": formal["bundle_sha256"],
                    "cohort_root_sha256": formal["campaign"]["cohort_root_sha256"],
                    "protocol_sha256": formal["protocol_sha256"],
                }
                if formal is not None
                else None
            )
            if formal is None or value.get("formal_binding") != expected_binding:
                raise FinalizationError(f"route state is not bound to model formal pointer: {path}")
        states.append(value)
    held = [state for state in states if state.get("state") == "held"]
    if held:
        identities = [f"{state.get('generation_model')}/{state.get('route')}" for state in held]
        raise FinalizationError(f"cannot finalize while routes are held: {identities}")
    return states


def _adopted_calls(checkpoint: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    attempts = checkpoint.get("attempts")
    if not isinstance(attempts, list):
        raise FinalizationError("checkpoint has no attempt history")
    adopted = [
        attempt
        for attempt in attempts
        if isinstance(attempt, Mapping) and attempt.get("outcome") == "adopted"
    ]
    if len(adopted) != 6:
        raise FinalizationError(f"complete checkpoint has {len(adopted)} adopted calls instead of six")
    if [attempt.get("stage") for attempt in adopted] != [
        "reconstruction", "cf_1", "cf_2", "cf_3", "cf_4", "cf_5"
    ]:
        raise FinalizationError("checkpoint adopted calls are not the exact six ordered stages")
    return adopted


def build_source_row(
    actual_row: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    *,
    formal_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one complete checkpoint to the schema's strict six-pair source row."""
    if checkpoint.get("complete") is not True:
        raise FinalizationError("cannot build source from an incomplete checkpoint")
    adopted = _adopted_calls(checkpoint)
    reconstruction = checkpoint.get("reconstruction")
    if not isinstance(reconstruction, Mapping):
        raise FinalizationError("complete checkpoint has no reconstruction payload")
    expected_requests = [
        (
            "reconstruction",
            build_reconstruction_prompt(actual_row["actual"]["output"]),
        )
    ]
    expected_requests.extend(
        (f"cf_{index}", prompt)
        for index, prompt in enumerate(reconstruction.get("prompts", ()), start=1)
    )
    if len(expected_requests) != 6:
        raise FinalizationError("checkpoint does not expose exactly five reconstructed prompts")
    for attempt, (stage, request) in zip(adopted, expected_requests):
        expected_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        if attempt.get("stage") != stage or attempt.get("request_sha256") != expected_hash:
            raise FinalizationError(f"{stage} adopted call is not bound to its canonical request")
        if formal_binding is not None:
            try:
                validate_adopted_call(
                    attempt.get("provenance"),
                    actual_row["generation_model"],
                    label=f"finalizer:{stage}",
                    binding=formal_binding,
                )
            except Exception as exc:
                raise FinalizationError(
                    f"{stage} adopted call differs from formal binding: {exc}"
                ) from exc
    counterfactuals = []
    for expected_index, entry in enumerate(checkpoint["counterfactuals"], start=1):
        index = entry["index"]
        if index != expected_index:
            raise FinalizationError("checkpoint counterfactual indexes are not positional")
        prompt = entry["prompt"]
        output = entry["output"]
        counterfactuals.append({
            "index": index,
            "prompt": prompt,
            "output": output,
            "pair_sha256": schema.counterfactual_pair_sha256(index, prompt, output),
            "provenance": entry["provenance"],
        })
    source = dict(actual_row)
    source["row_type"] = "strict_cf_source"
    source["counterfactuals"] = counterfactuals
    source["scoring_input_sha256"] = schema.strict_scoring_input_sha256(source)
    try:
        schema.validate_strict_source_row(
            source,
            actual_row=actual_row,
            project_root=PROJECT,
            formal_binding=formal_binding,
        )
    except Exception as exc:
        raise FinalizationError(f"strict source row validation failed: {exc}") from exc
    return source


def _mean(values: Sequence[float]) -> float:
    if len(values) != schema.STRICT_CF_COUNT:
        raise FinalizationError("strict mean requires exactly five counterfactual values")
    return math.fsum(values) / schema.STRICT_CF_COUNT


def build_blackbox_row(source: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute aggregate and per-compressor blackbox-v1 scores from six pairs."""
    actual = source["actual"]
    actual_profile = information_gain_profile(
        actual["prompt"], actual["output"], COMPRESSORS
    )
    cf_profiles = [
        information_gain_profile(entry["prompt"], entry["output"], COMPRESSORS)
        for entry in source["counterfactuals"]
    ]
    if len(cf_profiles) != schema.STRICT_CF_COUNT:
        raise FinalizationError("blackbox scoring requires exactly five CF profiles")

    actual_ratio = actual_profile.aggregate.contribution_ratio
    immutable_actual_ratio = actual["actual_ratio"]
    if actual_ratio != immutable_actual_ratio:
        raise FinalizationError(
            f"recomputed actual ratio differs from immutable actual ratio: "
            f"{actual_ratio!r} != {immutable_actual_ratio!r}"
        )
    cf_ratios = [profile.aggregate.contribution_ratio for profile in cf_profiles]
    baseline = _mean(cf_ratios)
    per_compressor: dict[str, dict[str, Any]] = {}
    for compressor in COMPRESSORS:
        actual_comp = actual_profile.per_compressor[compressor]["contribution_ratio"]
        immutable_comp = actual["per_compressor"][compressor]["actual_ratio"]
        if actual_comp != immutable_comp:
            raise FinalizationError(
                f"recomputed {compressor} actual ratio differs from immutable actual ratio"
            )
        cf_values = [
            profile.per_compressor[compressor]["contribution_ratio"]
            for profile in cf_profiles
        ]
        comp_baseline = _mean(cf_values)
        per_compressor[compressor] = {
            "actual_ratio": actual_comp,
            "cf_ratios": cf_values,
            "baseline_mean": comp_baseline,
            "strict_excess_ratio": actual_comp - comp_baseline,
        }

    identity_fields = (
        "semantic_key",
        "generation_model",
        "domain",
        "id",
        "source_id",
        "source_index",
        "source_text_sha256",
        "level",
        "source_cluster",
    )
    row = {
        "schema_version": schema.SCHEMA_VERSION,
        "row_type": "strict_cf_blackbox",
        **{field: source[field] for field in identity_fields},
        "scoring_input_sha256": source["scoring_input_sha256"],
        "method": schema.SCORING_METHOD,
        "protocol_sha256": schema.SCORING_PROTOCOL_SHA256,
        "actual_ratio": actual_ratio,
        "cf_ratios": cf_ratios,
        "baseline_mean": baseline,
        "strict_excess_ratio": actual_ratio - baseline,
        "baseline_n_valid": schema.STRICT_CF_COUNT,
        "per_compressor": per_compressor,
    }
    try:
        schema.validate_blackbox_row(row, source_row=source)
    except Exception as exc:
        raise FinalizationError(f"strict blackbox row validation failed: {exc}") from exc
    return row


def _read_canonical_launch_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise FinalizationError(f"START launch lacks {label}: {path}")
    raw = path.read_bytes()
    value = _strict_json_loads(raw.decode("utf-8", errors="strict"))
    if raw != canonical_json_bytes(value):
        raise FinalizationError(f"{label} is not canonical JSON: {path}")
    return value


def _require_launch_object(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise FinalizationError(f"{label} keys are invalid")
    return value


def _require_launch_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FinalizationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_launch_utc(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FinalizationError(f"{label} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinalizationError(f"{label} must be ISO-8601") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise FinalizationError(f"{label} must be normalized to UTC")
    return value


def _launch_inventory_entry(
    root: Path,
    launch_id: str,
    kind: str,
    path: Path,
    model: str | None = None,
) -> dict[str, str]:
    if not path.is_file():
        raise FinalizationError(f"START launch lacks {kind} artifact: {path}")
    entry = {
        "launch_id": launch_id,
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
    }
    if model is not None:
        entry["generation_model"] = model
    return entry


def _validate_start_launch_transactions(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    campaign_bindings: Mapping[str, str],
    formal_bindings: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, str]], set[str]]:
    """Rebuild every START transaction from request through worker result."""

    expected_campaign = {
        "lineage_id": manifest["lineage_id"],
        "manifest_sha256": campaign_bindings["manifest_sha256"],
        "cohort_root_sha256": campaign_bindings["cohort_root_sha256"],
        "core_inventory_sha256": campaign_bindings["creation_inventory_sha256"],
    }
    launch_entries: list[dict[str, str]] = []
    started_models: set[str] = set()
    launches_root = root / "launches"
    if not launches_root.exists():
        return launch_entries, started_models
    for decision_path in sorted(launches_root.glob("*/decision.json")):
        decision = _read_canonical_launch_json(
            decision_path, f"launch {decision_path.parent.name} decision"
        )
        if not isinstance(decision, Mapping) or decision.get("decision") not in {
            "START", "ABORT"
        }:
            raise FinalizationError(f"invalid launch decision document: {decision_path}")
        if decision["decision"] == "ABORT":
            continue
        launch_root = decision_path.parent
        launch_id = launch_root.name
        request_path = launch_root / "request.json"
        request = _read_canonical_launch_json(
            request_path, f"launch {launch_id} request"
        )
        _require_launch_object(
            request,
            {
                "schema", "schema_version", "launch_id", "nonce", "campaign",
                "models", "bindings", "review_path", "review_sha256", "created_at_utc",
            },
            f"launch {launch_id} request",
        )
        models = request["models"]
        if (
            request["schema"] != "experiment_a.strict_cf_v1.launch_request"
            or request["schema_version"] != 1
            or request["launch_id"] != launch_id
            or request["campaign"] != expected_campaign
            or not isinstance(models, list)
            or not models
            or len(models) != len(set(models))
            or models != [model for model in MODELS if model in models]
            or any(model not in formal_bindings for model in models)
        ):
            raise FinalizationError(f"launch {launch_id} request identity is invalid")
        _require_launch_sha(request["nonce"], f"launch {launch_id} nonce")
        _require_launch_sha(request["review_sha256"], f"launch {launch_id} review hash")
        _require_launch_utc(request["created_at_utc"], f"launch {launch_id} created_at_utc")
        review_path = schema.assert_path_within_run(
            root, request["review_path"], must_exist=True
        )
        if file_sha256(review_path) != request["review_sha256"]:
            raise FinalizationError(f"launch {launch_id} review hash mismatch")
        expected_bindings = {
            model: {
                "formal_pointer_sha256": formal_bindings[model]["formal_pointer_sha256"],
                "bundle_sha256": formal_bindings[model]["bundle_sha256"],
                "protocol_sha256": formal_bindings[model]["protocol_sha256"],
            }
            for model in models
        }
        if request["bindings"] != expected_bindings:
            raise FinalizationError(f"launch {launch_id} request binding mismatch")
        request_sha = file_sha256(request_path)
        _require_launch_object(
            decision,
            {
                "schema", "schema_version", "launch_id", "decision", "request_sha256",
                "nonce", "campaign", "models", "bindings", "review_path",
                "review_sha256", "ready_tokens", "ready_tokens_sha256", "decided_at_utc",
            },
            f"launch {launch_id} decision",
        )
        if (
            decision["schema"] != "experiment_a.strict_cf_v1.launch_decision"
            or decision["schema_version"] != 1
            or decision["launch_id"] != launch_id
            or decision["request_sha256"] != request_sha
            or decision["nonce"] != request["nonce"]
            or decision["campaign"] != expected_campaign
            or decision["models"] != models
            or decision["bindings"] != expected_bindings
            or decision["review_path"] != request["review_path"]
            or decision["review_sha256"] != request["review_sha256"]
        ):
            raise FinalizationError(f"launch {launch_id} START does not bind request")
        _require_launch_utc(decision["decided_at_utc"], f"launch {launch_id} decided_at_utc")
        ready_dir = launch_root / "ready"
        consumed_dir = launch_root / "consumed"
        expected_ready_paths = {ready_dir / f"{model}.json" for model in models}
        expected_consumed_paths = {consumed_dir / f"{model}.json" for model in models}
        if (
            not ready_dir.is_dir()
            or set(ready_dir.iterdir()) != expected_ready_paths
            or not consumed_dir.is_dir()
            or set(consumed_dir.iterdir()) != expected_consumed_paths
        ):
            raise FinalizationError(f"launch {launch_id} READY/consumed roster is not exact")
        ready_tokens: list[dict[str, str]] = []
        ready_values: dict[str, Mapping[str, Any]] = {}
        launch_entries.append(
            _launch_inventory_entry(root, launch_id, "request", request_path)
        )
        for model in models:
            ready_path = ready_dir / f"{model}.json"
            ready = _read_canonical_launch_json(
                ready_path, f"launch {launch_id} READY {model}"
            )
            _require_launch_object(
                ready,
                {
                    "schema", "schema_version", "launch_id", "request_sha256", "nonce",
                    "generation_model", "pid", "worker_token", "formal_pointer_sha256",
                    "bundle_sha256", "protocol_sha256", "ready_at_utc",
                },
                f"launch {launch_id} READY {model}",
            )
            if (
                ready["schema"] != "experiment_a.strict_cf_v1.launch_ready"
                or ready["schema_version"] != 1
                or ready["launch_id"] != launch_id
                or ready["request_sha256"] != request_sha
                or ready["nonce"] != request["nonce"]
                or ready["generation_model"] != model
                or isinstance(ready["pid"], bool)
                or not isinstance(ready["pid"], int)
                or ready["pid"] < 1
                or ready["formal_pointer_sha256"]
                != expected_bindings[model]["formal_pointer_sha256"]
                or ready["bundle_sha256"] != expected_bindings[model]["bundle_sha256"]
                or ready["protocol_sha256"] != expected_bindings[model]["protocol_sha256"]
            ):
                raise FinalizationError(f"launch {launch_id} READY identity mismatch for {model}")
            _require_launch_sha(ready["worker_token"], f"launch {launch_id} worker token")
            _require_launch_utc(ready["ready_at_utc"], f"launch {launch_id} ready_at_utc")
            entry = _launch_inventory_entry(
                root, launch_id, "ready", ready_path, model
            )
            ready_tokens.append({
                "generation_model": model,
                "path": entry["path"],
                "sha256": entry["sha256"],
            })
            ready_values[model] = ready
            launch_entries.append(entry)
        if (
            decision["ready_tokens"] != ready_tokens
            or schema.canonical_sha256(ready_tokens) != decision["ready_tokens_sha256"]
        ):
            raise FinalizationError(f"launch {launch_id} READY set/digest mismatch")
        launch_entries.append(
            _launch_inventory_entry(root, launch_id, "decision", decision_path)
        )
        decision_sha = file_sha256(decision_path)
        for model in models:
            consumed_path = consumed_dir / f"{model}.json"
            consumed = _read_canonical_launch_json(
                consumed_path, f"launch {launch_id} consumed {model}"
            )
            _require_launch_object(
                consumed,
                {
                    "schema", "schema_version", "launch_id", "request_sha256",
                    "decision_sha256", "ready_sha256", "generation_model",
                    "worker_token", "consumed_at_utc",
                },
                f"launch {launch_id} consumed {model}",
            )
            ready_path = ready_dir / f"{model}.json"
            if (
                consumed["schema"] != "experiment_a.strict_cf_v1.launch_consumed"
                or consumed["schema_version"] != 1
                or consumed["launch_id"] != launch_id
                or consumed["request_sha256"] != request_sha
                or consumed["decision_sha256"] != decision_sha
                or consumed["ready_sha256"] != file_sha256(ready_path)
                or consumed["generation_model"] != model
                or consumed["worker_token"] != ready_values[model]["worker_token"]
            ):
                raise FinalizationError(f"launch {launch_id} consumed identity mismatch for {model}")
            _require_launch_utc(
                consumed["consumed_at_utc"], f"launch {launch_id} consumed_at_utc"
            )
            launch_entries.append(
                _launch_inventory_entry(root, launch_id, "consumed", consumed_path, model)
            )
            started_models.add(model)
        result_path = launch_root / "result.json"
        result = _read_canonical_launch_json(
            result_path, f"launch {launch_id} result"
        )
        _require_launch_object(
            result,
            {
                "schema", "schema_version", "launch_id", "models", "decision_sha256",
                "return_codes", "finished_at_utc",
            },
            f"launch {launch_id} result",
        )
        return_codes = result["return_codes"]
        if (
            result["schema"] != "experiment_a.strict_cf_v1.launch_result"
            or result["schema_version"] != 1
            or result["launch_id"] != launch_id
            or result["models"] != models
            or result["decision_sha256"] != decision_sha
            or not isinstance(return_codes, Mapping)
            or set(return_codes) != set(models)
            or any(isinstance(code, bool) or not isinstance(code, int) for code in return_codes.values())
        ):
            raise FinalizationError(f"launch {launch_id} result identity mismatch")
        _require_launch_utc(result["finished_at_utc"], f"launch {launch_id} finished_at_utc")
        launch_entries.append(
            _launch_inventory_entry(root, launch_id, "result", result_path)
        )
    return launch_entries, started_models


def load_complete_rows(run_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Require an exact 20,000-checkpoint bijection and build validated rows."""
    root = _guard_run_root(run_root)
    manifest, actual_rows, campaign_bindings = load_run_inputs(root)
    try:
        formal_bindings = load_formal_bindings(root, require_all=True)
    except Exception as exc:
        raise FinalizationError(f"all five formal route bindings are required: {exc}") from exc
    if set(formal_bindings) != set(MODELS):
        raise FinalizationError("formal binding set differs from five-model roster")
    if len(actual_rows) != EXPECTED_LEVEL_ROWS:
        raise FinalizationError(
            f"finalizer requires {EXPECTED_LEVEL_ROWS} snapshot rows, got {len(actual_rows)}"
        )
    _read_route_breakers(root, formal_bindings)

    expected_paths = {checkpoint_path(root, row).resolve(): row for row in actual_rows}
    actual_paths = {path.resolve() for path in _iter_checkpoint_files(root)}
    all_json_paths = {
        path.resolve()
        for path in (root / CHECKPOINTS_REL).rglob("*.json")
        if path.is_file()
    } if (root / CHECKPOINTS_REL).exists() else set()
    if actual_paths != all_json_paths:
        extras = sorted(str(path) for path in all_json_paths - actual_paths)
        raise FinalizationError(f"checkpoint tree contains noncanonical JSON paths: {extras[:10]}")
    if set(expected_paths) != actual_paths:
        missing = sorted(str(path) for path in set(expected_paths) - actual_paths)
        extra = sorted(str(path) for path in actual_paths - set(expected_paths))
        raise FinalizationError(
            f"checkpoint set is not the exact {EXPECTED_LEVEL_ROWS}-row snapshot bijection; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )

    # This enforces global uniqueness across adopted, rejected, pending attempts,
    # and recovery probes whenever a response ID is known, then excludes every
    # immutable actual/intermediate response ID from the strict universe.
    response_ids = collect_response_ids(root)
    historical_ids = collect_historical_response_ids(root)
    contamination = response_ids & historical_ids
    if contamination:
        raise FinalizationError(
            f"strict/probe response IDs collide with immutable actual provenance: "
            f"{sorted(contamination)[:5]}"
        )
    source_rows: list[dict[str, Any]] = []
    checkpoint_hash_entries: list[dict[str, str]] = []
    adopted_total = 0
    model_checkpoint_counts = {model: 0 for model in MODELS}
    model_adopted_counts = {model: 0 for model in MODELS}
    for path in sorted(expected_paths, key=lambda item: _sort_key(expected_paths[item])):
        actual_row = expected_paths[path]
        checkpoint = load_checkpoint(
            path,
            actual_row,
            model_checkpoint_bindings(
                campaign_bindings,
                formal_bindings[actual_row["generation_model"]],
            ),
            formal_binding=formal_bindings[actual_row["generation_model"]],
        )
        if checkpoint.get("complete") is not True:
            raise FinalizationError(f"incomplete checkpoint: {path}")
        adopted = len(_adopted_calls(checkpoint))
        adopted_total += adopted
        model_name = actual_row["generation_model"]
        model_checkpoint_counts[model_name] += 1
        model_adopted_counts[model_name] += adopted
        source_rows.append(
            build_source_row(
                actual_row,
                checkpoint,
                formal_binding=formal_bindings[model_name],
            )
        )
        checkpoint_hash_entries.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": file_sha256(path),
        })
    if len(source_rows) != EXPECTED_LEVEL_ROWS:
        raise FinalizationError(f"requires exactly {EXPECTED_LEVEL_ROWS} complete checkpoints")
    if adopted_total != EXPECTED_ADOPTED_CALLS:
        raise FinalizationError(
            f"requires exactly {EXPECTED_ADOPTED_CALLS} adopted calls, got {adopted_total}"
        )
    for model in MODELS:
        if model_checkpoint_counts[model] != schema.EXPECTED_LEVEL_ROWS_PER_MODEL:
            raise FinalizationError(
                f"{model} has {model_checkpoint_counts[model]} checkpoints; "
                f"requires {schema.EXPECTED_LEVEL_ROWS_PER_MODEL}"
            )
        if model_adopted_counts[model] != schema.EXPECTED_ADOPTED_CALLS_PER_MODEL:
            raise FinalizationError(
                f"{model} has {model_adopted_counts[model]} adopted calls; "
                f"requires {schema.EXPECTED_ADOPTED_CALLS_PER_MODEL}"
            )
    formal_entries, formal_set_sha256 = canonical_formal_binding_inventory(
        root, require_all=True
    )
    validated_launch_entries, started_models = _validate_start_launch_transactions(
        root,
        manifest=manifest,
        campaign_bindings=campaign_bindings,
        formal_bindings=formal_bindings,
    )
    launch_entries, launch_set_sha256 = canonical_launch_inventory(root)
    if launch_entries != validated_launch_entries:
        raise FinalizationError(
            "canonical launch inventory differs from fully validated START transactions"
        )
    if started_models != set(MODELS):
        raise FinalizationError(
            f"committed START transactions do not cover exact roster: {sorted(started_models)}"
        )
    # Six adopted IDs per checkpoint are a subset of all known unique IDs.
    if len(response_ids) < adopted_total:
        raise FinalizationError("known unique response-ID count is below adopted-call count")

    source_rows.sort(key=_sort_key)
    seen_source: set[tuple[str, ...]] = set()
    actual_by_key = {tuple(row["semantic_key"]): row for row in actual_rows}
    for index, row in enumerate(source_rows):
        schema.validate_strict_source_row(
            row,
            actual_row=actual_by_key[tuple(row["semantic_key"])],
            project_root=PROJECT,
            seen_keys=seen_source,
            path=f"source[{index}]",
            formal_binding=formal_bindings[row["generation_model"]],
        )
    blackbox_rows = [build_blackbox_row(row) for row in source_rows]
    seen_blackbox: set[tuple[str, ...]] = set()
    for index, (blackbox, source) in enumerate(zip(blackbox_rows, source_rows)):
        schema.validate_blackbox_row(
            blackbox,
            source_row=source,
            seen_keys=seen_blackbox,
            path=f"blackbox[{index}]",
        )
    expected_inventory = sorted(
        checkpoint_hash_entries,
        key=lambda entry: entry["path"],
    )
    observed_inventory, checkpoint_set_sha256 = (
        schema.canonical_checkpoint_inventory_from_run(
            root,
            expected_count=EXPECTED_LEVEL_ROWS,
        )
    )
    if observed_inventory != expected_inventory:
        raise FinalizationError(
            "schema checkpoint inventory differs from validated checkpoint preimage"
        )
    checkpoint_entry_count = len(observed_inventory)
    route_state_entries, route_state_set_sha256 = (
        schema.canonical_route_state_inventory_from_run(root)
    )
    return manifest, source_rows, blackbox_rows, {
        **campaign_bindings,
        "formal_binding_set_sha256": formal_set_sha256,
        "formal_binding_entry_count": str(len(formal_entries)),
        "launch_set_sha256": launch_set_sha256,
        "launch_entry_count": str(len(launch_entries)),
        "per_model_checkpoint_counts": json.dumps(model_checkpoint_counts, sort_keys=True),
        "per_model_adopted_counts": json.dumps(model_adopted_counts, sort_keys=True),
        "checkpoint_set_sha256": checkpoint_set_sha256,
        "checkpoint_entry_count": str(checkpoint_entry_count),
        "route_state_set_sha256": route_state_set_sha256,
        "route_state_entry_count": str(len(route_state_entries)),
        "known_unique_response_ids": str(len(response_ids)),
        "adopted_calls": str(adopted_total),
    }


def _write_once_or_verify_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Create canonical JSONL once, or verify an exact existing preimage."""
    if not path.exists():
        atomic_replace_jsonl(path, rows)
        return
    if not path.is_file():
        raise FinalizationError(f"final artifact is not a file: {path}")
    with path.open("rb") as handle:
        for index, row in enumerate(rows):
            expected = canonical_jsonl_row_bytes(row)
            observed = handle.read(len(expected))
            if observed != expected:
                raise FinalizationError(
                    f"existing final JSONL differs from deterministic preimage at row {index}: {path}"
                )
        if handle.read(1):
            raise FinalizationError(f"existing final JSONL has extra bytes: {path}")


def _write_once_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    """Create canonical JSON once, or require byte-identical recovery content."""
    expected = canonical_json_bytes(value)
    if path.exists():
        if not path.is_file() or path.read_bytes() != expected:
            raise FinalizationError(f"existing final JSON differs from deterministic preimage: {path}")
        return
    atomic_replace_json(path, value)


def _schema_inventory() -> list[dict[str, Any]]:
    definitions = (
        ("actual_snapshot", schema.ACTUAL_SNAPSHOT_KEYS),
        ("model_item", schema.MODEL_ITEM_KEYS),
        ("strict_source", schema.STRICT_SOURCE_KEYS),
        ("strict_blackbox", schema.BLACKBOX_KEYS),
        (
            "checkpoint",
            {
                "schema", "schema_version", "level_key", "source_row_sha256",
                "input_binding", "key", "actual", "reconstruction",
                "counterfactuals", "attempts", "complete",
            },
        ),
        ("final_lineage", {
            "schema", "schema_version", "lineage_id", "finalized_at_utc",
            "manifest", "preparation_lineage", "historical_cutover_manifest",
            "historical_repair_audit", "historical_repair_method",
            "full_model_items", "actual", "source", "blackbox",
            "checkpoint_inventory", "route_state_inventory", "formal_binding_inventory",
            "launch_inventory", "cohort_root_sha256", "per_model_counts",
            "scoring", "schema_inventory", "code_inventory",
        }),
        ("finalized", {
            "schema", "schema_version", "lineage_id", "finalized_at_utc",
            "lineage_path", "lineage_sha256",
        }),
    )
    return [
        {
            "name": name,
            "version": schema.SCHEMA_VERSION,
            "sha256": schema.canonical_sha256({"keys": sorted(keys), "name": name}),
        }
        for name, keys in definitions
    ]


def _build_final_lineage(
    root: Path,
    manifest: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    source_hash: str,
    blackbox_hash: str,
    finalized_at_utc: str,
) -> dict[str, Any]:
    preparation_path = schema.assert_path_within_run(root, PREPARATION_LINEAGE_REL, must_exist=True)
    verified_inventory = verify_creation_inventory(root, manifest)
    preparation_hash = file_sha256(preparation_path)
    if preparation_hash != manifest["artifacts"]["preparation_lineage"]["sha256"]:
        raise FinalizationError("immutable preparation lineage differs from manifest")
    try:
        preparation = _strict_json_loads(
            preparation_path.read_text(encoding="utf-8", errors="strict")
        )
        creation_inventory = preparation["creation_inventory"]
        schema.validate_creation_inventory(creation_inventory)
    except Exception as exc:
        raise FinalizationError(f"invalid immutable creation inventory: {exc}") from exc
    if creation_inventory != verified_inventory:
        raise FinalizationError("creation inventory changed between verification and lineage build")
    if schema.canonical_sha256(creation_inventory) != bindings["creation_inventory_sha256"]:
        raise FinalizationError("creation inventory differs from worker-verified binding")
    code_inventory = [dict(entry) for entry in creation_inventory["code"]]
    lineage = {
        "schema": schema.FINAL_LINEAGE_SCHEMA,
        "schema_version": schema.SCHEMA_VERSION,
        "lineage_id": manifest["lineage_id"],
        "finalized_at_utc": finalized_at_utc,
        "manifest": {
            "path": MANIFEST_NAME,
            "sha256": bindings["manifest_sha256"],
            "row_count": 1,
        },
        "preparation_lineage": {
            "path": PREPARATION_LINEAGE_REL,
            "sha256": preparation_hash,
            "row_count": 1,
        },
        "historical_cutover_manifest": {
            "path": manifest["artifacts"]["historical_cutover_manifest"]["path"],
            "sha256": manifest["artifacts"]["historical_cutover_manifest"]["sha256"],
            "row_count": 1,
        },
        "historical_repair_audit": {
            "path": manifest["artifacts"]["historical_repair_audit"]["path"],
            "sha256": manifest["artifacts"]["historical_repair_audit"]["sha256"],
            "row_count": 1,
        },
        "historical_repair_method": {
            "path": manifest["artifacts"]["historical_repair_method"]["path"],
            "sha256": manifest["artifacts"]["historical_repair_method"]["sha256"],
            "row_count": 1,
        },
        "full_model_items": {
            "path": manifest["artifacts"]["full_model_items"]["path"],
            "sha256": manifest["artifacts"]["full_model_items"]["sha256"],
            "row_count": manifest["artifacts"]["full_model_items"]["row_count"],
        },
        "actual": {
            "path": bindings["snapshot_relative_path"],
            "sha256": bindings["snapshot_sha256"],
            "row_count": EXPECTED_LEVEL_ROWS,
        },
        "source": {
            "path": SOURCE_REL,
            "sha256": source_hash,
            "row_count": EXPECTED_LEVEL_ROWS,
        },
        "blackbox": {
            "path": BLACKBOX_REL,
            "sha256": blackbox_hash,
            "row_count": EXPECTED_LEVEL_ROWS,
        },
        "checkpoint_inventory": {
            "entry_count": int(bindings["checkpoint_entry_count"]),
            "sha256": bindings["checkpoint_set_sha256"],
        },
        "route_state_inventory": {
            "entry_count": int(bindings["route_state_entry_count"]),
            "sha256": bindings["route_state_set_sha256"],
        },
        "formal_binding_inventory": {
            "entry_count": int(bindings["formal_binding_entry_count"]),
            "sha256": bindings["formal_binding_set_sha256"],
        },
        "launch_inventory": {
            "entry_count": int(bindings["launch_entry_count"]),
            "sha256": bindings["launch_set_sha256"],
        },
        "cohort_root_sha256": bindings["cohort_root_sha256"],
        "per_model_counts": {
            "checkpoints": json.loads(bindings["per_model_checkpoint_counts"]),
            "adopted_calls": json.loads(bindings["per_model_adopted_counts"]),
        },
        "scoring": {
            "method": schema.SCORING_METHOD,
            "protocol_sha256": schema.SCORING_PROTOCOL_SHA256,
        },
        "schema_inventory": _schema_inventory(),
        "code_inventory": code_inventory,
    }
    schema.validate_final_lineage(
        lineage,
        manifest=manifest,
        run_dir=root,
        verify_files=True,
    )
    return lineage


def finalize(run_root: Path) -> dict[str, Any]:
    """Finalize one run transactionally enough for sentinel-based recovery."""
    root = _guard_run_root(run_root)
    if (root / FINALIZED_NAME).exists():
        raise FinalizationError(f"final sentinel already exists: {root / FINALIZED_NAME}")
    with finalization_lock():
        if (root / FINALIZED_NAME).exists():
            raise FinalizationError(f"final sentinel appeared concurrently: {root / FINALIZED_NAME}")
        # Completeness is a pure read-only gate.  Deferred/partial campaigns must
        # not be mutated merely because finalization was queried.
        manifest, source_rows, blackbox_rows, bindings = load_complete_rows(root)
        _append_run_status_event(
            root,
            event_type="finalization_started",
            model=None,
            route=None,
            detail=f"requiring {EXPECTED_LEVEL_ROWS} complete checkpoints",
            state="finalizing",
        )
        try:
            source_path = schema.assert_path_within_run(root, SOURCE_REL)
            blackbox_path = schema.assert_path_within_run(root, BLACKBOX_REL)
            lineage_path = schema.assert_path_within_run(root, LINEAGE_REL)
            finalized_path = schema.assert_path_within_run(root, FINALIZED_NAME)

            _write_once_or_verify_jsonl(source_path, source_rows)
            _write_once_or_verify_jsonl(blackbox_path, blackbox_rows)
            source_hash = file_sha256(source_path)
            blackbox_hash = file_sha256(blackbox_path)

            if lineage_path.exists():
                try:
                    existing_lineage = _strict_json_loads(
                        lineage_path.read_text(encoding="utf-8", errors="strict")
                    )
                    finalized_at = existing_lineage["finalized_at_utc"]
                except Exception as exc:
                    raise FinalizationError(
                        f"existing final lineage is not a recoverable preimage: {exc}"
                    ) from exc
            else:
                finalized_at = _utc_now()
            lineage = _build_final_lineage(
                root,
                manifest,
                bindings,
                source_hash=source_hash,
                blackbox_hash=blackbox_hash,
                finalized_at_utc=finalized_at,
            )
            _write_once_or_verify_json(lineage_path, lineage)
            lineage_hash = file_sha256(lineage_path)
            _append_run_status_event(
                root,
                event_type="finalized",
                model=None,
                route=None,
                detail=f"lineage_sha256={lineage_hash}",
                state="finalized",
                completed_level_rows=EXPECTED_LEVEL_ROWS,
            )
            sentinel = {
                "schema": schema.FINALIZED_SCHEMA,
                "schema_version": schema.SCHEMA_VERSION,
                "lineage_id": manifest["lineage_id"],
                "finalized_at_utc": finalized_at,
                "lineage_path": LINEAGE_REL,
                "lineage_sha256": lineage_hash,
            }
            schema.validate_finalized_sentinel(sentinel, lineage=lineage)
            # The sentinel is deliberately the final filesystem write of the
            # artifact transaction.  Its presence means every referenced hash
            # was already materialized and verified.
            _write_once_or_verify_json(finalized_path, sentinel)
            return sentinel
        except Exception as exc:
            try:
                _append_run_status_event(
                    root,
                    event_type="failed",
                    model=None,
                    route=None,
                    detail=str(exc)[:500],
                    state="failed",
                )
            except Exception:
                pass
            if isinstance(exc, FinalizationError):
                raise
            raise FinalizationError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sentinel = finalize(args.run_root)
    print(json.dumps(sentinel, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BLACKBOX_REL",
    "EXPECTED_ADOPTED_CALLS",
    "FinalizationError",
    "LINEAGE_REL",
    "PREPARATION_LINEAGE_REL",
    "SOURCE_REL",
    "build_blackbox_row",
    "build_parser",
    "build_source_row",
    "finalization_lock",
    "finalize",
    "load_complete_rows",
    "main",
]
