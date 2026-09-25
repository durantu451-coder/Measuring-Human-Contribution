# -*- coding: utf-8 -*-
"""Exactly-five-process launcher for Experiment A strict-CF v1.

The launcher performs one all-or-none, no-network preflight.  It never resets a
run, never invokes legacy metrics, and never finalizes outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_a import strict_cf_schema as schema
from experiment_a.run_strict_cf_v1 import (
    FINALIZED_NAME,
    MANIFEST_NAME,
    _guard_run_root,
    _strict_json_loads,
    build_reconstruction_prompt,
    load_run_inputs,
    parse_five_numbered_prompts,
    validate_generated_output,
)
from experiment_a.strict_cf_routes import (
    MODELS,
    assert_backend_c_handoff,
    make_candidate_adapter,
    validate_adopted_call,
)
from experiment_a.strict_cf_route_bundle import (
    FullValidationScope,
    ValidatedCampaignContext,
    build_validated_campaign_context,
    exclusive_create_json,
    load_candidate_bundle,
    load_formal_binding,
    set_full_validation_decision_state,
    validate_route_smoke_report,
)
from experiment_b.storage import (
    ProcessLock,
    atomic_replace_json,
    lock_is_active,
    read_lock_owner,
)

WORKER_SCRIPT = HERE / "run_strict_cf_v1.py"


class LaunchError(RuntimeError):
    """Five-worker preflight or launch failed."""


class SmokeError(RuntimeError):
    """The quarantined exact-30-call smoke did not pass."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _validate_status(run_root: Path) -> Mapping[str, Any]:
    path = run_root / schema.RUN_STATUS_PATH
    if not path.is_file():
        raise LaunchError(f"strict-CF status is missing: {path}")
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
        schema.validate_run_status(value, expected_lineage_id=run_root.name)
    except Exception as exc:
        raise LaunchError(f"strict-CF status is invalid: {exc}") from exc
    if value["state"] in {"finalizing", "finalized"}:
        raise LaunchError(f"run status forbids generation: {value['state']}")
    return value


def canonical_model_subset(models: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(models, Sequence) or isinstance(models, (str, bytes)) or not models:
        raise LaunchError("an explicit nonempty model subset is required")
    if len(models) != len(set(models)):
        raise LaunchError("model subset contains duplicates")
    unknown = set(models) - set(MODELS)
    if unknown:
        raise LaunchError(f"model subset contains out-of-roster models: {sorted(unknown)}")
    return tuple(model for model in MODELS if model in set(models))


def build_worker_commands(
    run_root: Path,
    *,
    models: Sequence[str],
    launch_id: str,
    python: Path,
    retries: int = 0,
    timeout: float | None = None,
    sleep_seconds: float | None = None,
    outage_threshold: int = 6,
    outage_min_seconds: float = 180.0,
    rate_limit_retries: int = 3,
    rate_limit_base_seconds: float = 2.0,
    resume_probe_rounds: int = 3,
    launch_wait_seconds: float = 180.0,
) -> dict[str, list[str]]:
    """Build one command per explicit subset model; no process starts here."""
    subset = canonical_model_subset(models)
    commands: dict[str, list[str]] = {}
    for model in subset:
        command = [
            str(python),
            "-u",
            str(WORKER_SCRIPT),
            "--run-root",
            str(run_root),
            "--model",
            model,
            "--launch-id",
            launch_id,
            "--launch-wait-seconds",
            str(launch_wait_seconds),
            "--retries",
            str(retries),
            "--outage-threshold",
            str(outage_threshold),
            "--outage-min-seconds",
            str(outage_min_seconds),
            "--rate-limit-retries",
            str(rate_limit_retries),
            "--rate-limit-base-seconds",
            str(rate_limit_base_seconds),
            "--resume-probe-rounds",
            str(resume_probe_rounds),
        ]
        if timeout is not None:
            command.extend(["--timeout", str(timeout)])
        if sleep_seconds is not None:
            command.extend(["--sleep", str(sleep_seconds)])
        commands[model] = command
    if tuple(commands) != subset:
        raise AssertionError("launcher command order differs from canonical subset")
    return commands


def preflight(
    run_root: Path,
    *,
    models: Sequence[str],
    launch_id: str,
    python: Path | None = None,
    **command_options: Any,
) -> dict[str, Any]:
    """Validate campaign plus requested formal subset before any spawn."""
    subset = canonical_model_subset(models)
    root = _guard_run_root(run_root)
    executable = (python or Path(sys.executable)).expanduser().resolve(strict=False)
    if not executable.is_file():
        raise LaunchError(f"Python executable does not exist: {executable}")
    if not WORKER_SCRIPT.is_file():
        raise LaunchError(f"worker script does not exist: {WORKER_SCRIPT}")
    if (root / FINALIZED_NAME).exists():
        raise LaunchError(f"run is already finalized: {root / FINALIZED_NAME}")
    try:
        manifest, rows, campaign_bindings = load_run_inputs(root)
        campaign_context = build_validated_campaign_context(
            root, manifest, campaign_bindings
        )
    except Exception as exc:
        raise LaunchError(f"immutable campaign preflight failed: {exc}") from exc
    _validate_status(root)
    counts = {model: 0 for model in MODELS}
    for row in rows:
        model = row["generation_model"]
        if model not in counts:
            raise LaunchError(f"snapshot contains an out-of-roster model: {model!r}")
        counts[model] += 1
    if any(value != schema.EXPECTED_LEVEL_ROWS_PER_MODEL for value in counts.values()):
        raise LaunchError(f"snapshot model slices differ from campaign slots: {counts}")

    formal_bindings: dict[str, dict[str, Any]] = {}
    backend_c_handoff = None
    for model in subset:
        try:
            formal = load_formal_binding(
                root, model, campaign_context=campaign_context
            )
        except Exception as exc:
            raise LaunchError(f"requested model {model} is not formally bound: {exc}") from exc
        formal_bindings[model] = formal
        if formal["coordination"]["kind"] == "experiment_b_backend_c":
            try:
                evidence = assert_backend_c_handoff(
                    expected_validation_files=(
                        backend_c_handoff["validation_files"]
                        if backend_c_handoff is not None
                        else None
                    )
                )
            except Exception as exc:
                raise LaunchError(f"Experiment B API3rd handoff gate failed: {exc}") from exc
            backend_c_handoff = evidence

    lock_dir = HERE / ".locks"
    lock_paths = [
        lock_dir / "maintenance.lock",
        *(lock_dir / f"{model}.lock" for model in subset),
    ]
    occupied = [str(path) for path in lock_paths if path.exists()]
    if occupied:
        raise LaunchError(f"Experiment A requested lock namespace is not clear: {occupied}")
    commands = build_worker_commands(
        root,
        models=subset,
        launch_id=launch_id,
        python=executable,
        **command_options,
    )
    return {
        "run_root": root,
        "python": executable,
        "manifest": manifest,
        "campaign_bindings": campaign_bindings,
        "campaign_context": campaign_context,
        "counts": counts,
        "models": subset,
        "formal_bindings": formal_bindings,
        "commands": commands,
        "backend_c_handoff": backend_c_handoff,
    }


def _formal_snapshot(run_root: Path) -> dict[str, dict[str, Any]]:
    """Hash formal artifacts so smoke can prove it stayed quarantined."""
    candidates: set[Path] = {
        run_root / MANIFEST_NAME,
        run_root / schema.RUN_STATUS_PATH,
        run_root / FINALIZED_NAME,
    }
    for key in ("lineage", "preparation_lineage", "source", "blackbox"):
        if key in schema.ARTIFACT_SPECS:
            candidates.add(run_root / schema.ARTIFACT_SPECS[key][0])
    for directory in (run_root / "snapshots", run_root / "checkpoints"):
        if directory.exists():
            candidates.update(path for path in directory.rglob("*") if path.is_file())
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(candidates):
        relative = path.relative_to(run_root).as_posix()
        if not path.is_file():
            result[relative] = {"exists": False, "sha256": None, "size": None}
            continue
        data = path.read_bytes()
        result[relative] = {
            "exists": True,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
    return result


def _protected_external_specs(
    run_root: Path,
    *,
    project_root: Path = PROJECT,
    experiment_b_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve every external artifact the quarantined smoke must not change."""
    project = project_root.resolve()
    preparation_path = run_root / schema.ARTIFACT_SPECS["preparation_lineage"][0]
    try:
        preparation = _strict_json_loads(
            preparation_path.read_text(encoding="utf-8", errors="strict")
        )
    except Exception as exc:
        raise SmokeError(f"cannot read preparation lineage for protected snapshot: {exc}") from exc
    specs: dict[str, dict[str, Any]] = {}

    def add(label: str, raw_path: Any, declared_sha256: Any = None) -> None:
        if not isinstance(raw_path, str) or not raw_path:
            raise SmokeError(f"protected artifact {label} has no path")
        path = Path(raw_path).resolve(strict=False)
        try:
            path.relative_to(project)
        except ValueError as exc:
            raise SmokeError(f"protected artifact escapes project workspace: {path}") from exc
        if label in specs or any(entry["path"] == str(path) for entry in specs.values()):
            raise SmokeError(f"duplicate protected artifact declaration: {label}/{path}")
        if declared_sha256 is not None and (
            not isinstance(declared_sha256, str)
            or len(declared_sha256) != 64
        ):
            raise SmokeError(f"protected artifact {label} has invalid declared SHA-256")
        specs[label] = {
            "path": str(path),
            "declared_sha256": declared_sha256,
        }

    inputs = preparation.get("inputs")
    if not isinstance(inputs, Mapping):
        raise SmokeError("preparation lineage has no inputs object")
    source_inputs = inputs.get("source_inputs")
    result_inputs = inputs.get("result_inputs")
    if not isinstance(source_inputs, Mapping) or not isinstance(result_inputs, Mapping):
        raise SmokeError("preparation lineage source/result inputs are invalid")
    for domain in schema.DOMAINS:
        entry = source_inputs.get(domain)
        if not isinstance(entry, Mapping):
            raise SmokeError(f"missing prepared source input for {domain}")
        add(f"prepared/source/{domain}", entry.get("path"), entry.get("sha256"))
    for model in schema.MODELS:
        per_model = result_inputs.get(model)
        if not isinstance(per_model, Mapping):
            raise SmokeError(f"missing prepared result inputs for {model}")
        for domain in schema.DOMAINS:
            entry = per_model.get(domain)
            if not isinstance(entry, Mapping):
                raise SmokeError(f"missing prepared result input for {model}/{domain}")
            add(
                f"prepared/result/{model}/{domain}",
                entry.get("path"),
                entry.get("sha256"),
            )
    pilot = inputs.get("pilot_samples")
    if not isinstance(pilot, Mapping):
        raise SmokeError("preparation lineage has no pilot_samples binding")
    add("prepared/pilot_samples", pilot.get("path"), pilot.get("sha256"))

    debug_records = preparation.get("selected_debug_records")
    if not isinstance(debug_records, list) or len(debug_records) != schema.EXPECTED_MODEL_ITEMS:
        raise SmokeError("preparation lineage selected_debug_records count is invalid")
    for index, entry in enumerate(debug_records):
        if not isinstance(entry, Mapping):
            raise SmokeError(f"selected debug declaration {index} is invalid")
        add(
            f"prepared/debug/{index:04d}",
            entry.get("path"),
            entry.get("file_sha256"),
        )

    active_pointer = project / "experiment_baseline" / "ACTIVE_PHI_V2.json"
    if active_pointer.is_file():
        add("baseline/ACTIVE_PHI_V2.json", str(active_pointer))
        try:
            pointer = _strict_json_loads(
                active_pointer.read_text(encoding="utf-8", errors="strict")
            )
        except Exception as exc:
            raise SmokeError(f"cannot parse ACTIVE_PHI_V2.json: {exc}") from exc
        lineage_path = pointer.get("lineage_path") if isinstance(pointer, Mapping) else None
        if lineage_path is not None:
            add(
                "baseline/active_lineage",
                lineage_path,
                pointer.get("lineage_sha256"),
            )

    b_root = (experiment_b_root or (project / "experiment_b")).resolve()
    b_outputs = b_root / "outputs"
    status_path = b_outputs / "experiment_b_status.json"
    specs["experiment_b/backend_c_status_projection"] = {
        "kind": "backend_c_status_projection",
        "path": str(status_path),
        "experiment_b_root": str(b_root),
        "declared_sha256": None,
    }
    for name in (
        "lineage_manifest.json",
        "validation_gpt-5.5.jsonl",
        "validation_gpt-5.6-sol.jsonl",
    ):
        add(f"experiment_b/{name}", str(b_outputs / name))
    return specs


def _backend_c_status_projection(spec: Mapping[str, Any]) -> dict[str, Any]:
    status_path = Path(spec["path"])
    b_root = Path(spec["experiment_b_root"])
    status = _strict_json_loads(status_path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(status, Mapping):
        raise SmokeError("Experiment B status is not an object")
    markers = ("gpt-5.5", "gpt-5.6-sol", "backend_c")
    active = status.get("active_runs")
    if not isinstance(active, list):
        raise SmokeError("Experiment B active_runs is invalid")
    relevant_runs = []
    for entry in active:
        text = json.dumps(entry, ensure_ascii=False, sort_keys=True).casefold()
        if any(marker in text for marker in markers):
            relevant_runs.append(entry)
    relevant_locks: list[dict[str, Any]] = []
    lock_dir = b_root / ".locks"
    if lock_dir.exists():
        for path in sorted(lock_dir.glob("*.scope.lock")):
            try:
                if not lock_is_active(path, clean_stale=False):
                    continue
                owner = read_lock_owner(path)
                scope = str(owner.get("scope", "")).casefold()
            except Exception:
                owner = {"scope": None, "pid": None}
                scope = path.name.casefold()
            if any(marker in scope for marker in markers):
                relevant_locks.append({
                    "path": str(path.resolve()),
                    "pid": owner.get("pid"),
                    "scope": owner.get("scope"),
                })
    promotion = status.get("verification", {}).get("backend_c_route_promotion")
    counts = status.get("components", {}).get("validation", {}).get("counts", {})
    return {
        "active_runs": relevant_runs,
        "active_locks": relevant_locks,
        "promotion": promotion,
        "validation_counts": {
            model: counts.get(model) if isinstance(counts, Mapping) else None
            for model in ("gpt-5.5", "gpt-5.6-sol")
        },
    }


def _protected_external_snapshot(
    specs: Mapping[str, Mapping[str, Any]],
    *,
    require_declared_match: bool,
) -> dict[str, dict[str, Any]]:
    """Read-only hash snapshot; no dynamic discovery, repair, or mutation."""
    snapshot: dict[str, dict[str, Any]] = {}
    for label in sorted(specs):
        spec = specs[label]
        path = Path(spec["path"])
        if spec.get("kind") == "backend_c_status_projection":
            try:
                projection = _backend_c_status_projection(spec)
            except Exception as exc:
                if require_declared_match:
                    raise SmokeError(
                        f"cannot build protected API3rd status projection: {exc}"
                    ) from exc
                state = {
                    "path": str(path),
                    "exists": False,
                    "size": None,
                    "sha256": None,
                    "declared_sha256": None,
                    "projection": None,
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                }
            else:
                state = {
                    "path": str(path),
                    "exists": True,
                    "size": None,
                    "sha256": schema.canonical_sha256(projection),
                    "declared_sha256": None,
                    "projection": projection,
                    "error": None,
                }
            snapshot[label] = state
            continue
        if not path.is_file():
            state = {
                "path": str(path),
                "exists": False,
                "size": None,
                "sha256": None,
                "declared_sha256": spec.get("declared_sha256"),
            }
        else:
            stat = path.stat()
            state = {
                "path": str(path),
                "exists": True,
                "size": stat.st_size,
                "sha256": schema.file_sha256(path),
                "declared_sha256": spec.get("declared_sha256"),
            }
        declared = state["declared_sha256"]
        if require_declared_match and (
            not state["exists"]
            or (declared is not None and state["sha256"] != declared)
        ):
            raise SmokeError(
                f"protected external artifact does not match preparation/handoff: {label}"
            )
        snapshot[label] = state
    return snapshot


def _snapshot_diff(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    return [
        key
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


def _run_candidate_smoke_under_startup_scope(
    run_root: Path,
    *,
    models: Sequence[str],
    bundle_sha256s: Mapping[str, str],
    smoke_id: str,
    adapters: Mapping[str, Any] | None = None,
    candidate_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run one concurrent six-call quarantine chain per requested candidate."""

    subset = canonical_model_subset(models)
    if set(bundle_sha256s) != set(subset):
        raise SmokeError("candidate smoke requires one bundle hash per requested model")
    root = _guard_run_root(run_root)
    manifest, rows, campaign_bindings = load_run_inputs(root)
    campaign_context = build_validated_campaign_context(
        root, manifest, campaign_bindings
    )
    selected = {}
    for model in subset:
        choices = sorted(
            (row for row in rows if row["generation_model"] == model),
            key=lambda row: (
                schema.DOMAINS.index(row["domain"]),
                str(row["id"]),
                schema.LEVELS.index(row["level"]),
            ),
        )
        if not choices:
            raise SmokeError(f"no smoke row for {model}")
        selected[model] = choices[0]

    adapter_map: dict[str, Any] = {}
    binding_map: dict[str, Mapping[str, Any] | None] = {}
    for model in subset:
        if adapters is not None:
            adapter_map[model] = adapters[model]
            binding_map[model] = (
                candidate_bindings.get(model) if candidate_bindings is not None else None
            )
        else:
            adapter, binding = make_candidate_adapter(
                root,
                model,
                bundle_sha256s[model],
                campaign_context=campaign_context,
                timeout_seconds=timeout_seconds,
            )
            adapter_map[model] = adapter
            binding_map[model] = binding

    for model in subset:
        binding = binding_map[model]
        if binding is None:
            raise SmokeError(
                f"candidate smoke requires immutable candidate binding for {model}"
            )
        expected_campaign = campaign_context.campaign_identity()
        if (
            binding.get("bundle_sha256") != bundle_sha256s[model]
            or binding.get("campaign") != expected_campaign
            or not isinstance(binding.get("route_id"), str)
            or not binding["route_id"]
            or not isinstance(binding.get("client_id"), str)
            or not binding["client_id"]
        ):
            raise SmokeError(f"candidate smoke binding mismatch for {model}")
        if binding["coordination"]["kind"] == "experiment_b_backend_c":
            assert_backend_c_handoff()

    aggregate_dir = root / "quarantine" / "route_smoke" / "aggregate" / smoke_id
    aggregate_dir.mkdir(parents=True, exist_ok=False)
    aggregate_path = aggregate_dir / "report.json"
    formal_before = _formal_snapshot(root)
    protected_specs = _protected_external_specs(root)
    protected_before = _protected_external_snapshot(
        protected_specs, require_declared_match=True
    )
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    reports: dict[str, dict[str, Any]] = {}
    report_paths: dict[str, Path] = {}
    for model in subset:
        path = root / "quarantine" / "route_smoke" / model / smoke_id / "report.json"
        path.parent.mkdir(parents=True, exist_ok=False)
        report = {
            "schema": "experiment_a.strict_cf_v1.route_smoke",
            "schema_version": 1,
            "smoke_id": smoke_id,
            "candidate_campaign": campaign_context.campaign_identity(),
            "generation_model": model,
            "bundle_sha256": bundle_sha256s[model],
            "started_at_utc": started,
            "finished_at_utc": None,
            "calls": [],
            "adopted_calls": 0,
            "accepted": False,
            "formal_unchanged": False,
            "protected_external_unchanged": False,
            "response_ids_sha256": schema.canonical_sha256([]),
        }
        reports[model] = report
        report_paths[model] = path
        atomic_replace_json(path, report)

    barrier = threading.Barrier(len(subset))
    state_lock = threading.Lock()
    used_ids: set[str] = set()
    errors: dict[str, str] = {}

    def persist(model: str) -> None:
        atomic_replace_json(report_paths[model], reports[model])

    def chain(model: str) -> None:
        adapter = adapter_map[model]
        binding = binding_map[model]
        row = selected[model]
        queue: list[tuple[str, str]] = [
            ("reconstruction", build_reconstruction_prompt(row["actual"]["output"]))
        ]
        outputs: list[str] = []
        index = 0
        while index < len(queue):
            stage, prompt = queue[index]
            invocation_id = hashlib.sha256(
                f"{smoke_id}\0{model}\0{stage}".encode("utf-8")
            ).hexdigest()
            call = {
                "stage": stage,
                "outcome": "outcome_unknown",
                "invocation_id": invocation_id,
                "request_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "response_sha256": None,
                "provenance": None,
                "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "finished_at_utc": None,
            }
            with state_lock:
                reports[model]["calls"].append(call)
                persist(model)
            if index == 0:
                barrier.wait(timeout=60.0)
            try:
                if binding is not None and binding["coordination"]["kind"] == "experiment_b_backend_c":
                    assert_backend_c_handoff()
                if hasattr(adapter, "generate_bound"):
                    text = adapter.generate_bound(
                        prompt,
                        invocation_id=invocation_id,
                        intent_ordinal=index + 1,
                    )
                else:
                    text = adapter.generate(prompt)
                metadata = adapter.consume_last_response_metadata()
                with state_lock:
                    call["response_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    call["provenance"] = metadata
                    persist(model)
                    provenance = validate_adopted_call(
                        metadata,
                        model,
                        used_response_ids=used_ids,
                        label=f"smoke:{model}:{stage}",
                        binding=binding,
                    )
                if stage == "reconstruction":
                    prompts = parse_five_numbered_prompts(text)
                    queue.extend(
                        (f"cf_{number}", value)
                        for number, value in enumerate(prompts, start=1)
                    )
                else:
                    outputs.append(validate_generated_output(text, outputs))
            except Exception:
                with state_lock:
                    call["outcome"] = "rejected"
                    call["finished_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    persist(model)
                raise
            with state_lock:
                call["outcome"] = "adopted"
                call["provenance"] = provenance
                call["finished_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                persist(model)
            index += 1
        if len(outputs) != 5:
            raise SmokeError(f"{model} smoke did not adopt five outputs")

    with ThreadPoolExecutor(max_workers=len(subset)) as executor:
        futures = {executor.submit(chain, model): model for model in subset}
        for future in as_completed(futures):
            model = futures[future]
            try:
                future.result()
            except Exception as exc:
                errors[model] = f"{type(exc).__name__}: {str(exc)[:500]}"

    formal_after = _formal_snapshot(root)
    protected_after = _protected_external_snapshot(
        protected_specs, require_declared_match=False
    )
    formal_unchanged = not _snapshot_diff(formal_before, formal_after)
    protected_unchanged = not _snapshot_diff(protected_before, protected_after)
    finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for model in subset:
        report = reports[model]
        response_ids = sorted(
            call["provenance"]["response_id"]
            for call in report["calls"]
            if call.get("outcome") == "adopted"
            and isinstance(call.get("provenance"), Mapping)
        )
        report["finished_at_utc"] = finished
        report["adopted_calls"] = sum(
            call.get("outcome") == "adopted" for call in report["calls"]
        )
        report["formal_unchanged"] = formal_unchanged
        report["protected_external_unchanged"] = protected_unchanged
        report["response_ids_sha256"] = schema.canonical_sha256(response_ids)
        report["accepted"] = (
            model not in errors
            and report["adopted_calls"] == 6
            and len(report["calls"]) == 6
            and formal_unchanged
            and protected_unchanged
        )
        if report["accepted"]:
            binding = binding_map[model]
            try:
                validate_route_smoke_report(
                    report,
                    campaign=report["candidate_campaign"],
                    model=model,
                    bundle_sha256=bundle_sha256s[model],
                    route_id=binding["route_id"],
                    client_id=binding["client_id"],
                )
            except Exception as exc:
                report["accepted"] = False
                errors[model] = f"{type(exc).__name__}: {str(exc)[:500]}"
        persist(model)
    aggregate = {
        "schema": "experiment_a.strict_cf_v1.route_smoke_aggregate",
        "schema_version": 1,
        "smoke_id": smoke_id,
        "models": list(subset),
        "report_paths": {
            model: report_paths[model].relative_to(root).as_posix() for model in subset
        },
        "report_sha256": {
            model: schema.file_sha256(report_paths[model]) for model in subset
        },
        "expected_adopted_calls": 6 * len(subset),
        "adopted_calls": sum(reports[model]["adopted_calls"] for model in subset),
        "accepted_models": [model for model in subset if reports[model]["accepted"]],
        "errors": errors,
        "accepted": all(reports[model]["accepted"] for model in subset),
    }
    atomic_replace_json(aggregate_path, aggregate)
    return aggregate, aggregate_path


def run_candidate_smoke(
    run_root: Path,
    *,
    models: Sequence[str],
    bundle_sha256s: Mapping[str, str],
    adapters: Mapping[str, Any] | None = None,
    candidate_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run one candidate smoke startup under one full-validation budget."""

    smoke_id = f"strict-cf-candidate-smoke-{_utc_stamp()}-{os.getpid()}"
    with FullValidationScope(role="smoke", operation_id=smoke_id):
        return _run_candidate_smoke_under_startup_scope(
            run_root,
            models=models,
            bundle_sha256s=bundle_sha256s,
            smoke_id=smoke_id,
            adapters=adapters,
            candidate_bindings=candidate_bindings,
            timeout_seconds=timeout_seconds,
        )


def run_quarantined_smoke(
    run_root: Path,
    *,
    models: Sequence[str],
    bundle_sha256s: Mapping[str, str],
    adapters: Mapping[str, Any] | None = None,
    candidate_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    retries: int = 0,
    timeout_seconds: float | None = None,
    sleep_seconds: float | None = None,
) -> tuple[dict[str, Any], Path]:
    if retries != 0:
        raise SmokeError("candidate wrappers forbid hidden retries")
    return run_candidate_smoke(
        run_root,
        models=models,
        bundle_sha256s=bundle_sha256s,
        adapters=adapters,
        candidate_bindings=candidate_bindings,
        timeout_seconds=timeout_seconds,
    )


def _validate_ready_token(
    root: Path,
    request: Mapping[str, Any],
    model: str,
    path: Path,
) -> dict[str, str]:
    ready = _strict_json_loads(path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(ready, Mapping):
        raise LaunchError(f"invalid READY token for {model}")
    expected_keys = {
        "schema", "schema_version", "launch_id", "request_sha256", "nonce",
        "generation_model", "pid", "worker_token", "formal_pointer_sha256",
        "bundle_sha256", "protocol_sha256", "ready_at_utc",
    }
    expected_binding = request["bindings"][model]
    try:
        ready_time = datetime.fromisoformat(
            str(ready.get("ready_at_utc", "")).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise LaunchError(f"invalid READY timestamp for {model}") from exc
    if (
        not isinstance(ready, Mapping)
        or set(ready) != expected_keys
        or ready.get("schema") != "experiment_a.strict_cf_v1.launch_ready"
        or ready.get("schema_version") != 1
        or ready.get("launch_id") != request["launch_id"]
        or ready.get("generation_model") != model
        or ready.get("request_sha256")
        != schema.file_sha256(root / "launches" / request["launch_id"] / "request.json")
        or ready.get("nonce") != request["nonce"]
        or ready.get("formal_pointer_sha256")
        != expected_binding["formal_pointer_sha256"]
        or ready.get("bundle_sha256") != expected_binding["bundle_sha256"]
        or ready.get("protocol_sha256") != expected_binding["protocol_sha256"]
        or isinstance(ready.get("pid"), bool)
        or not isinstance(ready.get("pid"), int)
        or ready["pid"] < 1
        or not isinstance(ready.get("worker_token"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", ready["worker_token"])
        or ready_time.tzinfo is None
        or ready_time.utcoffset() is None
        or ready_time.utcoffset().total_seconds() != 0
    ):
        raise LaunchError(f"invalid READY token for {model}")
    return {
        "generation_model": model,
        "path": path.relative_to(root).as_posix(),
        "sha256": schema.file_sha256(path),
    }


def _launch_decision(
    root: Path,
    request: Mapping[str, Any],
    ready_tokens: Sequence[Mapping[str, Any]],
    decision: str,
) -> dict[str, Any]:
    if decision not in {"START", "ABORT"}:
        raise LaunchError("launch decision must be START/ABORT")
    value = {
        "schema": "experiment_a.strict_cf_v1.launch_decision",
        "schema_version": 1,
        "launch_id": request["launch_id"],
        "decision": decision,
        "request_sha256": schema.file_sha256(
            root / "launches" / request["launch_id"] / "request.json"
        ),
        "nonce": request["nonce"],
        "campaign": request["campaign"],
        "models": request["models"],
        "bindings": request["bindings"],
        "review_path": request["review_path"],
        "review_sha256": request["review_sha256"],
        "ready_tokens": list(ready_tokens),
        "ready_tokens_sha256": schema.canonical_sha256(list(ready_tokens)),
        "decided_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    exclusive_create_json(
        root / "launches" / request["launch_id"] / "decision.json", value
    )
    set_full_validation_decision_state(decision)
    return value


def _launch_subset_under_startup_scope(
    run_root: Path,
    *,
    models: Sequence[str],
    review_path: Path,
    launch_id: str,
    python: Path | None = None,
    popen: Any = subprocess.Popen,
    ready_timeout_seconds: float = 180.0,
    **command_options: Any,
) -> dict[str, Any]:
    """Start one explicit subset only after every child commits READY."""

    subset = canonical_model_subset(models)
    root = _guard_run_root(run_root)
    review = schema.assert_path_within_run(root, review_path, must_exist=True)
    context = preflight(
        root,
        models=subset,
        launch_id=launch_id,
        python=python,
        launch_wait_seconds=max(ready_timeout_seconds + 30.0, 60.0),
        **command_options,
    )
    launch_root = root / "launches" / launch_id
    launch_root.mkdir(parents=True, exist_ok=False)
    (launch_root / "ready").mkdir()
    (launch_root / "consumed").mkdir()
    campaign_context = context["campaign_context"]
    if not isinstance(campaign_context, ValidatedCampaignContext):
        raise LaunchError("preflight did not return a validated campaign context")
    campaign = campaign_context.campaign_identity()
    request = {
        "schema": "experiment_a.strict_cf_v1.launch_request",
        "schema_version": 1,
        "launch_id": launch_id,
        "nonce": hashlib.sha256(os.urandom(32)).hexdigest(),
        "campaign": campaign,
        "models": list(subset),
        "bindings": {
            model: {
                "formal_pointer_sha256": context["formal_bindings"][model]["formal_pointer_sha256"],
                "bundle_sha256": context["formal_bindings"][model]["bundle_sha256"],
                "protocol_sha256": context["formal_bindings"][model]["protocol_sha256"],
            }
            for model in subset
        },
        "review_path": review.relative_to(root).as_posix(),
        "review_sha256": schema.file_sha256(review),
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    exclusive_create_json(launch_root / "request.json", request)
    logs_dir = root / "logs" / launch_id
    logs_dir.mkdir(parents=True, exist_ok=False)
    launcher_lock = ProcessLock(
        root / ".locks" / "subset_launcher.lock",
        scope="strict-cf-subset-launcher",
    )
    processes: dict[str, Any] = {}
    handles: dict[str, Any] = {}
    log_paths: dict[str, Path] = {}
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    decision: dict[str, Any] | None = None

    def terminate_all() -> None:
        for process in processes.values():
            try:
                process.terminate()
            except Exception:
                pass
        for process in processes.values():
            try:
                process.wait(timeout=15)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    with launcher_lock:
        occupied = [
            HERE / ".locks" / name
            for name in ("maintenance.lock", *(f"{model}.lock" for model in subset))
            if (HERE / ".locks" / name).exists()
        ]
        if occupied:
            _launch_decision(root, request, [], "ABORT")
            raise LaunchError(f"Experiment A lock appeared after preflight: {occupied}")
        try:
            for model in subset:
                log_path = logs_dir / f"{model}.log"
                handle = log_path.open("x", encoding="utf-8", errors="replace")
                handles[model] = handle
                log_paths[model] = log_path
                command = context["commands"][model]
                handle.write(json.dumps({"model": model, "command": command}) + "\n")
                handle.flush()
                processes[model] = popen(
                    command,
                    cwd=str(PROJECT),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                )
        except Exception as exc:
            ready_tokens: list[dict[str, Any]] = []
            for model in subset:
                path = launch_root / "ready" / f"{model}.json"
                if path.is_file():
                    ready_tokens.append({
                        "generation_model": model,
                        "path": path.relative_to(root).as_posix(),
                        "sha256": schema.file_sha256(path),
                    })
            _launch_decision(root, request, ready_tokens, "ABORT")
            terminate_all()
            for handle in handles.values():
                handle.close()
            raise LaunchError(f"could not spawn requested subset: {exc}") from exc

        deadline = __import__("time").monotonic() + ready_timeout_seconds
        ready_tokens = []
        try:
            while True:
                if any(
                    callable(getattr(process, "poll", None))
                    and process.poll() is not None
                    for process in processes.values()
                ):
                    raise LaunchError("requested subset child exited before START")
                ready_tokens = []
                for model in subset:
                    path = launch_root / "ready" / f"{model}.json"
                    if path.is_file():
                        ready_tokens.append(
                            _validate_ready_token(root, request, model, path)
                        )
                # A child may exit while its READY file is being read.  Failure is
                # terminal even when the exact READY set became visible in that race.
                if any(
                    callable(getattr(process, "poll", None))
                    and process.poll() is not None
                    for process in processes.values()
                ):
                    raise LaunchError("requested subset child exited before START")
                if len(ready_tokens) == len(subset):
                    decision = _launch_decision(root, request, ready_tokens, "START")
                    break
                if __import__("time").monotonic() >= deadline:
                    raise LaunchError("requested subset failed before exact READY set")
                __import__("time").sleep(0.1)
        except Exception as exc:
            abort_error: Exception | None = None
            if not (launch_root / "decision.json").exists():
                try:
                    _launch_decision(root, request, ready_tokens, "ABORT")
                except Exception as abort_exc:
                    abort_error = abort_exc
            terminate_all()
            for handle in handles.values():
                handle.close()
            if abort_error is not None:
                raise LaunchError(
                    f"launch failed and ABORT could not be persisted: {abort_error}"
                ) from exc
            if isinstance(exc, LaunchError):
                raise
            raise LaunchError(f"invalid READY transaction: {exc}") from exc

    return_codes: dict[str, int] = {}
    try:
        for model in subset:
            return_codes[model] = int(processes[model].wait())
    finally:
        for handle in handles.values():
            handle.close()
    result = {
        "schema": "experiment_a.strict_cf_v1.launch_result",
        "schema_version": 1,
        "launch_id": launch_id,
        "models": list(subset),
        "decision_sha256": schema.file_sha256(launch_root / "decision.json"),
        "return_codes": return_codes,
        "finished_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    atomic_replace_json(launch_root / "result.json", result)
    return {
        "launch_id": launch_id,
        "logs_dir": logs_dir,
        "logs": log_paths,
        "return_codes": return_codes,
        "ok": decision is not None and decision["decision"] == "START" and all(
            code == 0 for code in return_codes.values()
        ),
    }


def launch_subset(
    run_root: Path,
    *,
    models: Sequence[str],
    review_path: Path,
    python: Path | None = None,
    popen: Any = subprocess.Popen,
    ready_timeout_seconds: float = 180.0,
    **command_options: Any,
) -> dict[str, Any]:
    """Start one formal subset under one launcher-local validation budget."""

    launch_id = f"strict-cf-{_utc_stamp()}-{os.getpid()}"
    with FullValidationScope(role="launcher", operation_id=launch_id):
        return _launch_subset_under_startup_scope(
            run_root,
            models=models,
            review_path=review_path,
            launch_id=launch_id,
            python=python,
            popen=popen,
            ready_timeout_seconds=ready_timeout_seconds,
            **command_options,
        )


def launch_five(
    run_root: Path,
    *,
    review_path: Path,
    python: Path | None = None,
    popen: Any = subprocess.Popen,
    **command_options: Any,
) -> dict[str, Any]:
    """Compatibility wrapper: explicitly launch the complete campaign roster."""
    return launch_subset(
        run_root,
        models=MODELS,
        review_path=review_path,
        python=python,
        popen=popen,
        **command_options,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--model", action="append", required=True, choices=MODELS)
    parser.add_argument("--review-path", type=Path, default=None)
    parser.add_argument(
        "--bundle",
        action="append",
        default=[],
        metavar="MODEL=SHA256",
        help="candidate bundle mapping required for quarantine smoke",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        choices=(0,),
        help="strict adapter retries are disabled; worker stage retries are checkpointed",
    )
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--sleep", type=float, default=None)
    parser.add_argument("--outage-threshold", type=int, default=6)
    parser.add_argument("--outage-min-seconds", type=float, default=180.0)
    parser.add_argument("--rate-limit-retries", type=int, default=3)
    parser.add_argument("--rate-limit-base-seconds", type=float, default=2.0)
    parser.add_argument("--resume-probe-rounds", type=int, default=3)
    parser.add_argument(
        "--quarantined-smoke",
        action="store_true",
        help="run one six-call candidate smoke per requested model; launch no workers",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    subset = canonical_model_subset(args.model)
    if args.quarantined_smoke:
        bundles = {}
        for raw in args.bundle:
            if "=" not in raw:
                raise SystemExit(f"--bundle must be MODEL=SHA256: {raw!r}")
            model, digest = raw.split("=", 1)
            if model in bundles:
                raise SystemExit(f"duplicate --bundle model: {model}")
            bundles[model] = digest
        report, path = run_quarantined_smoke(
            args.run_root,
            models=subset,
            bundle_sha256s=bundles,
            retries=args.retries,
            timeout_seconds=args.timeout,
            sleep_seconds=args.sleep,
        )
        print(json.dumps({
            "report": str(path),
            "accepted": report["accepted"],
            "adopted_calls": report.get("adopted_calls", 0),
        }, sort_keys=True))
        return 0 if report["accepted"] else 1
    if args.review_path is None:
        raise SystemExit("--review-path is required for formal subset launch")
    result = launch_subset(
        args.run_root,
        models=subset,
        review_path=args.review_path,
        python=args.python,
        retries=args.retries,
        timeout=args.timeout,
        sleep_seconds=args.sleep,
        outage_threshold=args.outage_threshold,
        outage_min_seconds=args.outage_min_seconds,
        rate_limit_retries=args.rate_limit_retries,
        rate_limit_base_seconds=args.rate_limit_base_seconds,
        resume_probe_rounds=args.resume_probe_rounds,
    )
    print(json.dumps({
        "launch_id": result["launch_id"],
        "logs_dir": str(result["logs_dir"]),
        "return_codes": result["return_codes"],
    }, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LaunchError",
    "SmokeError",
    "WORKER_SCRIPT",
    "build_parser",
    "build_worker_commands",
    "canonical_model_subset",
    "launch_five",
    "launch_subset",
    "main",
    "preflight",
    "run_candidate_smoke",
    "run_quarantined_smoke",
]
