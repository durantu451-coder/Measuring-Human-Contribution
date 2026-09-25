# -*- coding: utf-8 -*-
"""Immutable, model-scoped route bundles and formal bindings for strict-CF v1."""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from experiment_a import strict_cf_schema as schema
from experiment_a.strict_cf_transport import (
    TRANSPORT_ABI_SHA256,
    TRANSPORT_ABI_VERSION,
    fixed_call_contract,
    strict_json_loads,
)
from experiment_b import storage

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
CANDIDATES_REL = "route_candidates"
FORMAL_REL = "formal"
SMOKE_REL = "quarantine/route_smoke"
LAUNCHES_REL = "launches"
BUNDLE_SCHEMA = "experiment_a.strict_cf_v1.route_bundle"
BUNDLE_COMMIT_SCHEMA = "experiment_a.strict_cf_v1.route_bundle_committed"
FORMAL_BINDING_SCHEMA = "experiment_a.strict_cf_v1.formal_route_binding"
SMOKE_SCHEMA = "experiment_a.strict_cf_v1.route_smoke"
BUNDLE_SCHEMA_VERSION = 1
FORMAL_SCHEMA_VERSION = 1
COORDINATION_POLICIES = ("none", "experiment_b_backend_c")


class RouteBundleError(RuntimeError):
    """A route candidate, bundle, smoke, or formal pointer is invalid."""


class FullValidationBudgetError(RouteBundleError):
    """An opted-in startup tried to walk the campaign graph more than once."""


VALIDATION_EVENT_PREFIX = "STRICT_CF_VALIDATION_EVENT "
CONTROL_EVENT_PREFIX = "STRICT_CF_CONTROL_EVENT "
_DECISION_STATES = {"PRE_START", "START", "ABORT", "INVALID"}
_SCOPE_ROLES = {"launcher", "worker", "smoke"}
_FULL_VALIDATION_SCOPE: ContextVar[FullValidationScope | None] = ContextVar(
    "strict_cf_full_validation_scope",
    default=None,
)


@dataclass(frozen=True, slots=True)
class ValidatedCampaignContext:
    """Small process-local identity derived from one successful full validation."""

    run_root: Path
    lineage_id: str
    manifest_sha256: str
    cohort_root_sha256: str
    core_inventory_sha256: str

    def campaign_identity(self) -> dict[str, str]:
        return {
            "lineage_id": self.lineage_id,
            "manifest_sha256": self.manifest_sha256,
            "cohort_root_sha256": self.cohort_root_sha256,
            "core_inventory_sha256": self.core_inventory_sha256,
        }


@dataclass(slots=True)
class FullValidationScope:
    """Opt-in, process-local startup budget and telemetry context."""

    role: str
    operation_id: str
    model: str | None = None
    budget: int = 1
    decision_state: str = "PRE_START"
    calls: int = field(init=False, default=0)
    _token: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.role not in _SCOPE_ROLES:
            raise ValueError(f"invalid full-validation scope role: {self.role!r}")
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("full-validation operation_id must be nonempty")
        if self.role == "worker":
            _model(str(self.model))
        elif self.model is not None:
            raise ValueError(f"{self.role} validation scope must not name a model")
        if self.budget != 1:
            raise ValueError("strict-CF startup full-validation budget must equal one")
        if self.decision_state not in _DECISION_STATES:
            raise ValueError("invalid initial validation decision state")

    def __enter__(self) -> FullValidationScope:
        if _FULL_VALIDATION_SCOPE.get() is not None:
            raise FullValidationBudgetError("full-validation scopes cannot be nested")
        self._token = _FULL_VALIDATION_SCOPE.set(self)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._token is None:
            raise RuntimeError("full-validation scope was not entered")
        _FULL_VALIDATION_SCOPE.reset(self._token)
        self._token = None

    def set_decision_state(self, value: str) -> None:
        if value not in _DECISION_STATES:
            raise ValueError(f"invalid strict-CF decision state: {value!r}")
        if self.decision_state in {"START", "ABORT"} and value != self.decision_state:
            raise FullValidationBudgetError(
                f"terminal decision state cannot change: {self.decision_state} -> {value}"
            )
        self.decision_state = value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strict_json_file(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_bytes())
    except Exception as exc:
        raise RouteBundleError(f"invalid strict JSON {path}: {exc}") from exc


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        raise RouteBundleError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise RouteBundleError(f"{label} must be a lowercase SHA-256 digest") from exc
    return value


def current_full_validation_scope() -> FullValidationScope | None:
    """Return the active opt-in startup scope, if any."""

    return _FULL_VALIDATION_SCOPE.get()


def set_full_validation_decision_state(value: str) -> None:
    """Advance the active startup scope without affecting unscoped callers."""

    scope = current_full_validation_scope()
    if scope is not None:
        scope.set_decision_state(value)


def _safe_manifest_event_identity(
    manifest: Mapping[str, Any], run_dir: str | Path | None
) -> dict[str, Any]:
    root = Path(run_dir).resolve(strict=False) if run_dir is not None else None
    digest = None
    if root is not None:
        manifest_path = root / "manifest.json"
        try:
            digest = storage.file_sha256(manifest_path)
        except OSError:
            pass
    return {
        "run_root": str(root) if root is not None else None,
        "lineage_id": manifest.get("lineage_id"),
        "manifest_sha256": digest,
    }


def _scope_event(
    scope: FullValidationScope,
    *,
    event: str,
    ordinal: int | None = None,
    **fields: Any,
) -> None:
    payload = {
        "schema": "experiment_a.strict_cf_v1.validation_telemetry",
        "schema_version": 1,
        "event": event,
        "role": scope.role,
        "model": scope.model,
        "operation_id": scope.operation_id,
        "launch_id": scope.operation_id if scope.role in {"launcher", "worker"} else None,
        "smoke_id": scope.operation_id if scope.role == "smoke" else None,
        "pid": os.getpid(),
        "ordinal": ordinal,
        **fields,
    }
    print(
        VALIDATION_EVENT_PREFIX
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        file=sys.stderr,
        flush=True,
    )


def validate_manifest_full(
    manifest: Mapping[str, Any],
    *,
    run_dir: str | Path | None = None,
    project_root: str | Path | None = None,
    require_finalized: bool = False,
    path: str = "manifest",
) -> Mapping[str, Any]:
    """Run the real full validator under an optional one-call startup budget."""

    scope = current_full_validation_scope()
    if scope is None:
        return schema.validate_manifest(
            manifest,
            run_dir=run_dir,
            project_root=project_root,
            verify_files=True,
            require_finalized=require_finalized,
            path=path,
        )

    scope.calls += 1
    ordinal = scope.calls
    started_at_utc = _utc_now()
    started_monotonic = time.perf_counter()
    entry_state = scope.decision_state
    identity = _safe_manifest_event_identity(manifest, run_dir)
    _scope_event(
        scope,
        event="full_validation_started",
        ordinal=ordinal,
        started_at_utc=started_at_utc,
        entry_decision_state=entry_state,
        **identity,
    )
    if ordinal > scope.budget:
        duration = time.perf_counter() - started_monotonic
        _scope_event(
            scope,
            event="full_validation_rejected",
            ordinal=ordinal,
            started_at_utc=started_at_utc,
            finished_at_utc=_utc_now(),
            duration_seconds=duration,
            entry_decision_state=entry_state,
            exit_decision_state=scope.decision_state,
            success=False,
            error_type=FullValidationBudgetError.__name__,
            **identity,
        )
        raise FullValidationBudgetError(
            f"{scope.role} startup exceeded its one-call full-validation budget"
        )
    try:
        result = schema.validate_manifest(
            manifest,
            run_dir=run_dir,
            project_root=project_root,
            verify_files=True,
            require_finalized=require_finalized,
            path=path,
        )
    except BaseException as exc:
        _scope_event(
            scope,
            event="full_validation_finished",
            ordinal=ordinal,
            started_at_utc=started_at_utc,
            finished_at_utc=_utc_now(),
            duration_seconds=time.perf_counter() - started_monotonic,
            entry_decision_state=entry_state,
            exit_decision_state=scope.decision_state,
            success=False,
            error_type=type(exc).__name__,
            **identity,
        )
        raise
    _scope_event(
        scope,
        event="full_validation_finished",
        ordinal=ordinal,
        started_at_utc=started_at_utc,
        finished_at_utc=_utc_now(),
        duration_seconds=time.perf_counter() - started_monotonic,
        entry_decision_state=entry_state,
        exit_decision_state=scope.decision_state,
        success=True,
        error_type=None,
        **identity,
    )
    return result


def build_validated_campaign_context(
    run_root: Path,
    manifest: Mapping[str, Any],
    bindings: Mapping[str, str],
) -> ValidatedCampaignContext:
    """Build a small identity only after the caller's successful full load."""

    root = Path(run_root).resolve(strict=True)
    try:
        lineage_id = schema.validate_lineage_id(manifest["lineage_id"])
        manifest_sha256 = _require_sha(
            bindings["manifest_sha256"], "validated manifest_sha256"
        )
        cohort_root_sha256 = _require_sha(
            bindings["cohort_root_sha256"], "validated cohort_root_sha256"
        )
        core_inventory_sha256 = _require_sha(
            bindings["creation_inventory_sha256"],
            "validated creation_inventory_sha256",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RouteBundleError(f"cannot build validated campaign context: {exc}") from exc
    if root.name != lineage_id:
        raise RouteBundleError("validated campaign lineage differs from run directory")
    manifest_path = root / "manifest.json"
    if storage.file_sha256(manifest_path) != manifest_sha256:
        raise RouteBundleError("validated manifest bytes changed before context creation")
    if manifest["cohort"]["root_sha256"] != cohort_root_sha256:
        raise RouteBundleError("validated cohort root differs from context bindings")
    if schema.canonical_sha256(manifest["creation_inventory"]) != core_inventory_sha256:
        raise RouteBundleError("validated core inventory differs from context bindings")
    return ValidatedCampaignContext(
        run_root=root,
        lineage_id=lineage_id,
        manifest_sha256=manifest_sha256,
        cohort_root_sha256=cohort_root_sha256,
        core_inventory_sha256=core_inventory_sha256,
    )


def emit_adapter_constructed(
    *, model: str, campaign_context: ValidatedCampaignContext
) -> dict[str, Any]:
    """Emit the post-START/pre-provider adapter boundary for a formal worker."""

    scope = current_full_validation_scope()
    if scope is None or scope.role != "worker" or scope.model != model:
        raise FullValidationBudgetError(
            "adapter construction telemetry requires the model's worker startup scope"
        )
    if scope.decision_state != "START":
        raise FullValidationBudgetError("adapter was constructed before exact START")
    if campaign_context.run_root != campaign_context.run_root.resolve(strict=True):
        raise RouteBundleError("adapter campaign context run root is not canonical")
    payload = {
        "schema": "experiment_a.strict_cf_v1.control_telemetry",
        "schema_version": 1,
        "event": "adapter_constructed",
        "role": scope.role,
        "model": model,
        "operation_id": scope.operation_id,
        "launch_id": scope.operation_id,
        "pid": os.getpid(),
        "decision_state": scope.decision_state,
        "observed_at_utc": _utc_now(),
        **campaign_context.campaign_identity(),
    }
    print(
        CONTROL_EVENT_PREFIX
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        file=sys.stderr,
        flush=True,
    )
    return payload


def _require_utc(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RouteBundleError(f"{label} must be a nonempty UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RouteBundleError(f"{label} must be ISO-8601") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise RouteBundleError(f"{label} must be normalized to UTC")
    return value


def _within(root: Path, path: str | Path, *, must_exist: bool = False) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RouteBundleError(f"path escapes route campaign root: {path}") from exc
    return resolved


def _model(value: str) -> str:
    if value not in schema.MODELS:
        raise RouteBundleError(f"model is not in strict-CF roster: {value!r}")
    if value in {"", ".", ".."} or "/" in value or "\\" in value:
        raise RouteBundleError(f"unsafe model path component: {value!r}")
    return value


def exclusive_create_bytes(path: Path, data: bytes) -> str:
    """Durably create bytes exactly once; never replace an existing path."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        raise RouteBundleError(f"refusing to replace write-once file: {path}")
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(fd, view[written:])
            if count <= 0:
                raise OSError("zero-byte write")
            written += count
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    storage.fsync_directory(path.parent)
    return hashlib.sha256(data).hexdigest()


def exclusive_create_json(path: Path, value: Mapping[str, Any]) -> str:
    return exclusive_create_bytes(path, storage.canonical_json_bytes(value))


def _campaign_identity(
    run_root: Path,
    *,
    campaign_context: ValidatedCampaignContext | None = None,
) -> dict[str, str]:
    root = Path(run_root).resolve(strict=True)
    manifest_path = root / "manifest.json"
    manifest = _strict_json_file(manifest_path)
    try:
        if campaign_context is None:
            validate_manifest_full(manifest, run_dir=root)
        else:
            if root != campaign_context.run_root:
                raise RouteBundleError(
                    "validated campaign context belongs to a different run root"
                )
            schema.validate_manifest(
                manifest,
                run_dir=root,
                project_root=PROJECT,
                verify_files=False,
            )
        observed = {
            "lineage_id": manifest["lineage_id"],
            "manifest_sha256": storage.file_sha256(manifest_path),
            "cohort_root_sha256": _require_sha(
                manifest["cohort"]["root_sha256"], "cohort root"
            ),
            "core_inventory_sha256": schema.canonical_sha256(
                manifest["creation_inventory"]
            ),
        }
        if campaign_context is not None and (
            observed != campaign_context.campaign_identity()
        ):
            raise RouteBundleError(
                "current campaign identity differs from validated process context"
            )
    except Exception as exc:
        raise RouteBundleError(f"invalid immutable campaign manifest: {exc}") from exc
    return observed


def _secret_like_path(path: Path) -> bool:
    lowered = path.name.casefold()
    if lowered in {".env", "id_rsa", "id_ed25519"}:
        return True
    return any(marker in lowered for marker in ("credential", "private_key", "secret.pem", "token.txt"))


def _resolve_project_imports(path: Path, project_root: Path) -> set[Path]:
    """Resolve conservative static project imports from one Python source file."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"), filename=str(path))
    except Exception as exc:
        raise RouteBundleError(f"cannot parse bundle Python source {path}: {exc}") from exc
    result: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dynamic = (
                isinstance(node.func, ast.Name) and node.func.id == "__import__"
            ) or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
            if dynamic:
                raise RouteBundleError(
                    f"dynamic import requires an explicit bundle dependency declaration: {path}:{node.lineno}"
                )
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package_parts = list(path.relative_to(project_root).with_suffix("").parts[:-1])
                trim = max(0, node.level - 1)
                if trim:
                    package_parts = package_parts[:-trim]
                base = ".".join([*package_parts, *([base] if base else [])])
            names = [base]
            if base:
                names.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
        else:
            continue
        for name in names:
            if not name:
                continue
            candidate = project_root.joinpath(*name.split("."))
            choices = (candidate.with_suffix(".py"), candidate / "__init__.py")
            for choice in choices:
                if choice.is_file():
                    result.add(choice.resolve())
                    # Include package initializers along the path.
                    relative = choice.relative_to(project_root)
                    current = project_root
                    for part in relative.parts[:-1]:
                        current = current / part
                        init = current / "__init__.py"
                        if init.is_file():
                            result.add(init.resolve())
                    break
    return result


def project_dependency_closure(
    entrypoint: Path,
    *,
    project_root: Path = PROJECT,
    explicit_files: Iterable[Path] = (),
) -> list[Path]:
    project = Path(project_root).resolve(strict=True)
    initial = [Path(entrypoint).resolve(strict=True), *(Path(item).resolve(strict=True) for item in explicit_files)]
    pending: list[Path] = []
    seen: set[Path] = set()
    for path in initial:
        try:
            path.relative_to(project)
        except ValueError as exc:
            raise RouteBundleError(f"project bundle dependency escapes project: {path}") from exc
        pending.append(path)
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        if path.is_symlink() or not path.is_file():
            raise RouteBundleError(f"bundle dependency must be a regular non-symlink file: {path}")
        if _secret_like_path(path):
            raise RouteBundleError(f"secret-like file cannot be copied into a route bundle: {path}")
        seen.add(path)
        if path.suffix == ".py":
            for dependency in _resolve_project_imports(path, project):
                if dependency not in seen:
                    pending.append(dependency)
    return sorted(seen, key=lambda item: item.relative_to(project).as_posix())


def _distribution_fingerprint(import_roots: Iterable[str]) -> list[dict[str, str]]:
    packages = importlib.metadata.packages_distributions()
    names: set[str] = set()
    for root in import_roots:
        names.update(packages.get(root, ()))
    entries = []
    for name in sorted(names):
        try:
            distribution = importlib.metadata.distribution(name)
            version = distribution.version
            metadata_text = json.dumps(dict(distribution.metadata), sort_keys=True, default=str)
            files = sorted(str(item) for item in (distribution.files or ()))
        except Exception as exc:
            raise RouteBundleError(f"cannot fingerprint distribution {name}: {exc}") from exc
        entries.append(
            {
                "name": name,
                "version": version,
                "metadata_sha256": hashlib.sha256(metadata_text.encode("utf-8")).hexdigest(),
                "file_list_sha256": schema.canonical_sha256(files),
            }
        )
    return entries


def runtime_fingerprint(
    *,
    python_executable: Path = Path(sys.executable),
    external_packages: Iterable[str] = (),
) -> dict[str, Any]:
    executable = Path(python_executable).resolve(strict=True)
    return {
        "python_executable": str(executable),
        "python_sha256": storage.file_sha256(executable),
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "cache_tag": sys.implementation.cache_tag,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "utf8_mode": int(sys.flags.utf8_mode),
        "distributions": _distribution_fingerprint(external_packages),
    }


def _copy_project_files(
    files: Sequence[Path], staging: Path, project_root: Path
) -> tuple[list[dict[str, Any]], dict[Path, Path]]:
    inventory: list[dict[str, Any]] = []
    mapping: dict[Path, Path] = {}
    for source in files:
        relative = source.relative_to(project_root).as_posix()
        destination = staging / "src" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=False)
        if destination.is_symlink():
            raise RouteBundleError(f"bundle copy unexpectedly produced a symlink: {destination}")
        mapping[source] = destination
        inventory.append(
            {
                "path": f"src/{relative}",
                "size": destination.stat().st_size,
                "sha256": storage.file_sha256(destination),
                "role": "entrypoint" if source == files[0] else "project_dependency",
            }
        )
    inventory.sort(key=lambda entry: entry["path"])
    return inventory, mapping


def _validate_inventory_files(bundle_root: Path, inventory: Sequence[Mapping[str, Any]]) -> None:
    declared: set[Path] = set()
    for index, entry in enumerate(inventory):
        if not isinstance(entry, Mapping) or set(entry) != {"path", "size", "sha256", "role"}:
            raise RouteBundleError(f"bundle inventory entry {index} keys are invalid")
        path = _within(bundle_root, entry["path"], must_exist=True)
        if path in declared or path.is_symlink() or not path.is_file():
            raise RouteBundleError(f"bundle inventory path is duplicate/nonregular: {path}")
        declared.add(path)
        if path.stat().st_size != entry["size"] or storage.file_sha256(path) != entry["sha256"]:
            raise RouteBundleError(f"bundle inventory file drift: {path}")
    actual = {
        path.resolve()
        for path in bundle_root.rglob("*")
        if path.is_file() and path.name not in {"bundle.json", "COMMITTED"}
    }
    if actual != declared:
        raise RouteBundleError("bundle contains undeclared or missing files")


def _validate_external_dependencies(entries: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {
            "role", "path", "sha256", "contains_credentials"
        }:
            raise RouteBundleError(f"external dependency {index} keys are invalid")
        role = str(entry["role"])
        if role in seen:
            raise RouteBundleError(f"duplicate external dependency role {role!r}")
        seen.add(role)
        path = Path(str(entry["path"])).resolve(strict=True)
        _require_sha(entry["sha256"], f"external dependency {role} hash")
        if not path.is_file() or storage.file_sha256(path) != entry["sha256"]:
            raise RouteBundleError(f"external dependency drift: {path}")
        if not isinstance(entry["contains_credentials"], bool):
            raise RouteBundleError("contains_credentials must be boolean")


def _validate_environment_contract(contract: Mapping[str, Any]) -> None:
    if not isinstance(contract, Mapping) or set(contract) != {
        "required_names", "optional_names", "presence"
    }:
        raise RouteBundleError("environment contract keys are invalid")
    required = contract["required_names"]
    optional = contract["optional_names"]
    presence = contract["presence"]
    if not isinstance(required, list) or not isinstance(optional, list) or not isinstance(presence, Mapping):
        raise RouteBundleError("environment contract types are invalid")
    names = [*required, *optional]
    if len(names) != len(set(names)) or any(not isinstance(name, str) or not name for name in names):
        raise RouteBundleError("environment names must be unique nonempty strings")
    if set(presence) != set(names) or any(type(value) is not bool for value in presence.values()):
        raise RouteBundleError("environment presence projection is invalid")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RouteBundleError(f"required route environment variables are absent: {missing}")


def _protocol() -> dict[str, Any]:
    return {
        "max_output_tokens": 4096,
        "reasoning_effort": "low",
        "terminal_status": "completed",
        "provider_attempts_per_invocation": 1,
        "alias_policy": "forbid",
        "fallback_policy": "forbid",
    }


def build_candidate_bundle(
    run_root: Path,
    *,
    model: str,
    entrypoint: Path,
    route_id: str,
    client_id: str,
    coordination: str = "none",
    project_root: Path = PROJECT,
    explicit_project_files: Iterable[Path] = (),
    external_dependencies: Iterable[Mapping[str, Any]] = (),
    required_environment_names: Iterable[str] = (),
    optional_environment_names: Iterable[str] = (),
    external_packages: Iterable[str] = (),
    external_runtime_fingerprint: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Build and COMMIT one run-local immutable route candidate without networking."""

    root = Path(run_root).resolve(strict=True)
    model = _model(model)
    if coordination not in COORDINATION_POLICIES:
        raise RouteBundleError(f"unknown coordination policy: {coordination!r}")
    if not isinstance(route_id, str) or not route_id.strip():
        raise RouteBundleError("route_id must be nonempty")
    if not isinstance(client_id, str) or not client_id.strip():
        raise RouteBundleError("client_id must be nonempty")
    campaign = _campaign_identity(root)
    project = Path(project_root).resolve(strict=True)
    closure = project_dependency_closure(
        entrypoint,
        project_root=project,
        explicit_files=explicit_project_files,
    )
    staging_parent = _within(root, f"{CANDIDATES_REL}/{model}")
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = staging_parent / f".staging-{uuid.uuid4().hex}"
    staging.mkdir(exist_ok=False)
    try:
        inventory, mapping = _copy_project_files(closure, staging, project)
        source_entrypoint = Path(entrypoint).resolve(strict=True)
        bundled_entrypoint = mapping[source_entrypoint]
        external_entries = []
        for raw in external_dependencies:
            entry = dict(raw)
            path = Path(str(entry["path"])).resolve(strict=True)
            external_entries.append(
                {
                    "role": str(entry["role"]),
                    "path": str(path),
                    "sha256": storage.file_sha256(path),
                    "contains_credentials": bool(entry.get("contains_credentials", False)),
                }
            )
        external_entries.sort(key=lambda entry: entry["role"])
        _validate_external_dependencies(external_entries)
        required_names = sorted(set(str(name) for name in required_environment_names))
        optional_names = sorted(set(str(name) for name in optional_environment_names))
        environment_contract = {
            "required_names": required_names,
            "optional_names": optional_names,
            "presence": {
                name: bool(os.environ.get(name))
                for name in [*required_names, *optional_names]
            },
        }
        _validate_environment_contract(environment_contract)
        runtime = runtime_fingerprint(external_packages=external_packages)
        manifest = {
            "schema": BUNDLE_SCHEMA,
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "campaign": campaign,
            "generation_model": model,
            "route_id": route_id.strip(),
            "client_id": client_id.strip(),
            "transport_abi_version": TRANSPORT_ABI_VERSION,
            "transport_abi_sha256": TRANSPORT_ABI_SHA256,
            "protocol": _protocol(),
            "entrypoint": bundled_entrypoint.relative_to(staging).as_posix(),
            "project_dependency_inventory": inventory,
            "project_dependency_inventory_sha256": schema.canonical_sha256(inventory),
            "external_dependency_inventory": external_entries,
            "external_dependency_inventory_sha256": schema.canonical_sha256(external_entries),
            "environment_contract": environment_contract,
            "runtime_fingerprint": runtime,
            "runtime_fingerprint_sha256": schema.canonical_sha256(runtime),
            "external_runtime_fingerprint": dict(external_runtime_fingerprint or {}),
            "coordination": {"kind": coordination, "version": 1},
        }
        bundle_sha = schema.canonical_sha256(manifest)
        destination = staging_parent / bundle_sha
        storage.atomic_replace_json(staging / "bundle.json", manifest)
        if destination.exists():
            shutil.rmtree(staging)
            existing = load_candidate_bundle(root, model=model, bundle_sha256=bundle_sha)
            return existing, destination
        os.replace(staging, destination)
        storage.fsync_directory(destination.parent)
        commit = {
            "schema": BUNDLE_COMMIT_SCHEMA,
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "generation_model": model,
            "bundle_sha256": bundle_sha,
            "bundle_manifest_sha256": storage.file_sha256(destination / "bundle.json"),
            "committed_at_utc": _utc_now(),
        }
        exclusive_create_json(destination / "COMMITTED", commit)
        return load_candidate_bundle(root, model=model, bundle_sha256=bundle_sha), destination
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_candidate_bundle(
    bundle_root: Path,
    manifest: Mapping[str, Any],
    *,
    expected_model: str,
    expected_campaign: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    expected_model = _model(expected_model)
    if not isinstance(manifest, Mapping):
        raise RouteBundleError("bundle manifest must be an object")
    expected_keys = {
        "schema", "schema_version", "campaign", "generation_model", "route_id",
        "client_id", "transport_abi_version", "transport_abi_sha256", "protocol",
        "entrypoint", "project_dependency_inventory", "project_dependency_inventory_sha256",
        "external_dependency_inventory", "external_dependency_inventory_sha256",
        "environment_contract", "runtime_fingerprint", "runtime_fingerprint_sha256",
        "external_runtime_fingerprint", "coordination",
    }
    if set(manifest) != expected_keys:
        raise RouteBundleError("bundle manifest keys are not exact")
    if manifest["schema"] != BUNDLE_SCHEMA or manifest["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise RouteBundleError("bundle schema/version mismatch")
    if manifest["generation_model"] != expected_model:
        raise RouteBundleError("bundle model mismatch")
    if expected_campaign is not None and dict(manifest["campaign"]) != dict(expected_campaign):
        raise RouteBundleError("bundle campaign identity mismatch")
    if manifest["transport_abi_version"] != TRANSPORT_ABI_VERSION or manifest["transport_abi_sha256"] != TRANSPORT_ABI_SHA256:
        raise RouteBundleError("bundle transport ABI mismatch")
    if dict(manifest["protocol"]) != _protocol():
        raise RouteBundleError("bundle protocol differs from strict slot contract")
    coordination = manifest["coordination"]
    if not isinstance(coordination, Mapping) or dict(coordination) not in (
        {"kind": "none", "version": 1},
        {"kind": "experiment_b_backend_c", "version": 1},
    ):
        raise RouteBundleError("bundle coordination policy is invalid")
    inventory = manifest["project_dependency_inventory"]
    if not isinstance(inventory, list) or not inventory:
        raise RouteBundleError("bundle project inventory must be nonempty")
    if schema.canonical_sha256(inventory) != manifest["project_dependency_inventory_sha256"]:
        raise RouteBundleError("bundle project inventory digest mismatch")
    _validate_inventory_files(bundle_root, inventory)
    external = manifest["external_dependency_inventory"]
    if not isinstance(external, list):
        raise RouteBundleError("bundle external inventory must be a list")
    if schema.canonical_sha256(external) != manifest["external_dependency_inventory_sha256"]:
        raise RouteBundleError("bundle external inventory digest mismatch")
    _validate_external_dependencies(external)
    _validate_environment_contract(manifest["environment_contract"])
    if schema.canonical_sha256(manifest["runtime_fingerprint"]) != manifest["runtime_fingerprint_sha256"]:
        raise RouteBundleError("bundle runtime fingerprint digest mismatch")
    observed_runtime = runtime_fingerprint(
        python_executable=Path(manifest["runtime_fingerprint"]["python_executable"]),
        external_packages=(entry["name"] for entry in manifest["runtime_fingerprint"]["distributions"]),
    )
    if observed_runtime != manifest["runtime_fingerprint"]:
        raise RouteBundleError("bundle Python/distribution runtime drift")
    entrypoint = _within(bundle_root, manifest["entrypoint"], must_exist=True)
    declared = {entry["path"] for entry in inventory}
    if manifest["entrypoint"] not in declared or not entrypoint.is_file():
        raise RouteBundleError("bundle entrypoint is not inventory-bound")
    return manifest


def load_candidate_bundle(
    run_root: Path,
    *,
    model: str,
    bundle_sha256: str,
    campaign_context: ValidatedCampaignContext | None = None,
) -> dict[str, Any]:
    root = Path(run_root).resolve(strict=True)
    model = _model(model)
    _require_sha(bundle_sha256, "bundle_sha256")
    bundle_root = _within(root, f"{CANDIDATES_REL}/{model}/{bundle_sha256}", must_exist=True)
    manifest_path = bundle_root / "bundle.json"
    commit_path = bundle_root / "COMMITTED"
    if not manifest_path.is_file() or not commit_path.is_file():
        raise RouteBundleError("candidate bundle is not COMMITTED")
    manifest = _strict_json_file(manifest_path)
    expected_campaign = _campaign_identity(
        root, campaign_context=campaign_context
    )
    validate_candidate_bundle(
        bundle_root,
        manifest,
        expected_model=model,
        expected_campaign=expected_campaign,
    )
    if schema.canonical_sha256(manifest) != bundle_sha256:
        raise RouteBundleError("candidate directory digest differs from bundle manifest")
    commit = _strict_json_file(commit_path)
    expected_commit_keys = {
        "schema", "schema_version", "generation_model", "bundle_sha256",
        "bundle_manifest_sha256", "committed_at_utc",
    }
    if not isinstance(commit, Mapping) or set(commit) != expected_commit_keys:
        raise RouteBundleError("candidate COMMITTED keys are invalid")
    if (
        commit["schema"] != BUNDLE_COMMIT_SCHEMA
        or commit["schema_version"] != BUNDLE_SCHEMA_VERSION
        or commit["generation_model"] != model
        or commit["bundle_sha256"] != bundle_sha256
        or commit["bundle_manifest_sha256"] != storage.file_sha256(manifest_path)
    ):
        raise RouteBundleError("candidate COMMITTED binding mismatch")
    return {
        **dict(manifest),
        "bundle_root": str(bundle_root),
        "bundle_sha256": bundle_sha256,
        "bundle_manifest_sha256": storage.file_sha256(manifest_path),
        "committed_sha256": storage.file_sha256(commit_path),
    }


def validate_route_smoke_report(
    value: Mapping[str, Any],
    *,
    campaign: Mapping[str, str],
    model: str,
    bundle_sha256: str,
    route_id: str,
    client_id: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RouteBundleError("route smoke report must be an object")
    expected = {
        "schema", "schema_version", "smoke_id", "candidate_campaign",
        "generation_model", "bundle_sha256", "started_at_utc", "finished_at_utc",
        "calls", "adopted_calls", "accepted", "formal_unchanged",
        "protected_external_unchanged", "response_ids_sha256",
    }
    if set(value) != expected:
        raise RouteBundleError("route smoke report keys are not exact")
    if value["schema"] != SMOKE_SCHEMA or value["schema_version"] != 1:
        raise RouteBundleError("route smoke schema/version mismatch")
    if dict(value["candidate_campaign"]) != dict(campaign):
        raise RouteBundleError("route smoke campaign mismatch")
    if value["generation_model"] != model or value["bundle_sha256"] != bundle_sha256:
        raise RouteBundleError("route smoke model/bundle mismatch")
    _require_sha(bundle_sha256, "route smoke bundle_sha256")
    _require_utc(value["started_at_utc"], "route smoke started_at_utc")
    _require_utc(value["finished_at_utc"], "route smoke finished_at_utc")
    calls = value["calls"]
    if not isinstance(calls, list) or len(calls) != 6 or value["adopted_calls"] != 6:
        raise RouteBundleError("route smoke must contain exactly six adopted calls")
    expected_stages = ["reconstruction", "cf_1", "cf_2", "cf_3", "cf_4", "cf_5"]
    if [entry.get("stage") for entry in calls if isinstance(entry, Mapping)] != expected_stages:
        raise RouteBundleError("route smoke stages are not exact")
    campaign_binding = {
        "lineage_id": campaign["lineage_id"],
        "manifest_sha256": campaign["manifest_sha256"],
        "cohort_root_sha256": campaign["cohort_root_sha256"],
    }
    candidate_binding = {
        "formal_pointer_sha256": None,
        "bundle_sha256": bundle_sha256,
    }
    provenance_keys = {
        "api_family", "route_id", "client_id", "requested_model",
        "returned_model", "response_id", "native_terminal_field",
        "native_terminal_value", "terminal_status", "incomplete_details", "usage",
        "max_output_tokens", "reasoning_effort", "alias_used", "fallback_used",
        "captured_at_utc", "provider_attempt_count", "transport_abi_sha256",
        "campaign_binding", "formal_binding", "invocation_id", "raw_transport",
    }
    raw_keys = {
        "request_sha256", "stdout_sha256", "stderr_sha256", "stderr_size",
        "stderr_truncated", "returncode", "transport_abi_sha256",
        "formal_binding", "campaign_binding", "invocation_id",
    }
    response_ids: list[str] = []
    for index, entry in enumerate(calls):
        label = f"route smoke calls[{index}]"
        if not isinstance(entry, Mapping) or set(entry) != {
            "stage", "outcome", "invocation_id", "request_sha256",
            "response_sha256", "provenance", "started_at_utc", "finished_at_utc",
        }:
            raise RouteBundleError(f"{label} keys are not exact")
        if entry["outcome"] != "adopted":
            raise RouteBundleError(f"{label} is not adopted")
        invocation_id = _require_sha(entry["invocation_id"], f"{label}.invocation_id")
        _require_sha(entry["request_sha256"], f"{label}.request_sha256")
        _require_sha(entry["response_sha256"], f"{label}.response_sha256")
        _require_utc(entry["started_at_utc"], f"{label}.started_at_utc")
        _require_utc(entry["finished_at_utc"], f"{label}.finished_at_utc")
        provenance = entry["provenance"]
        if not isinstance(provenance, Mapping) or set(provenance) != provenance_keys:
            raise RouteBundleError(f"{label} transport provenance keys are not exact")
        for field, expected_value in (
            ("route_id", route_id),
            ("client_id", client_id),
            ("requested_model", model),
            ("returned_model", model),
            ("terminal_status", "completed"),
            ("max_output_tokens", 4096),
            ("reasoning_effort", "low"),
            ("alias_used", False),
            ("fallback_used", False),
            ("provider_attempt_count", 1),
            ("transport_abi_sha256", TRANSPORT_ABI_SHA256),
            ("campaign_binding", campaign_binding),
            ("formal_binding", candidate_binding),
            ("invocation_id", invocation_id),
        ):
            if provenance.get(field) != expected_value:
                raise RouteBundleError(f"{label} {field} mismatch")
        if provenance.get("incomplete_details") not in (None, {}):
            raise RouteBundleError(f"{label} incomplete_details must be empty")
        for field in ("api_family", "native_terminal_field"):
            if not isinstance(provenance.get(field), str) or not provenance[field].strip():
                raise RouteBundleError(f"{label} {field} must be nonempty")
        if provenance.get("native_terminal_value") is None:
            raise RouteBundleError(f"{label} native terminal value is missing")
        usage = provenance.get("usage")
        if (
            not isinstance(usage, Mapping)
            or isinstance(usage.get("output_tokens"), bool)
            or not isinstance(usage.get("output_tokens"), int)
            or usage["output_tokens"] < 1
        ):
            raise RouteBundleError(f"{label} usage.output_tokens must be positive")
        _require_utc(provenance.get("captured_at_utc"), f"{label}.captured_at_utc")
        response_id = provenance.get("response_id")
        if not isinstance(response_id, str) or not response_id or response_id != response_id.strip():
            raise RouteBundleError(f"{label} response_id must be nonempty and trimmed")
        response_ids.append(response_id)
        raw = provenance.get("raw_transport")
        if not isinstance(raw, Mapping) or set(raw) != raw_keys:
            raise RouteBundleError(f"{label} raw transport evidence keys are not exact")
        for field in ("request_sha256", "stdout_sha256", "stderr_sha256"):
            _require_sha(raw.get(field), f"{label}.raw_transport.{field}")
        if (
            isinstance(raw.get("stderr_size"), bool)
            or not isinstance(raw.get("stderr_size"), int)
            or raw["stderr_size"] < 0
            or not isinstance(raw.get("stderr_truncated"), bool)
            or raw.get("returncode") != 0
            or raw.get("transport_abi_sha256") != TRANSPORT_ABI_SHA256
            or raw.get("formal_binding") != candidate_binding
            or raw.get("campaign_binding") != campaign_binding
            or raw.get("invocation_id") != invocation_id
        ):
            raise RouteBundleError(f"{label} raw transport evidence mismatch")
    if len(response_ids) != len(set(response_ids)):
        raise RouteBundleError("route smoke response IDs are not unique")
    if schema.canonical_sha256(sorted(response_ids)) != value["response_ids_sha256"]:
        raise RouteBundleError("route smoke response-ID digest mismatch")
    if (
        value["accepted"] is not True
        or value["formal_unchanged"] is not True
        or value["protected_external_unchanged"] is not True
    ):
        raise RouteBundleError("route smoke is not accepted/quarantined")
    return value


def _formal_side_effects(run_root: Path, model: str) -> list[str]:
    root = Path(run_root).resolve(strict=True)
    paths: list[Path] = []
    checkpoint = root / "checkpoints" / model
    if checkpoint.exists():
        paths.extend(path for path in checkpoint.rglob("*") if path.is_file())
    route_states = root / "status" / "routes"
    if route_states.exists():
        paths.extend(path for path in route_states.glob(f"{model}-*.json") if path.is_file())
    launches = root / LAUNCHES_REL
    if launches.exists():
        for path in launches.rglob("*.json"):
            try:
                payload = _strict_json_file(path)
            except Exception:
                paths.append(path)
                continue
            serialized = storage.canonical_json_text(payload)
            if model in serialized and any(part in path.parts for part in ("ready", "consumed")):
                paths.append(path)
            elif model in serialized and path.name == "decision.json" and payload.get("decision") == "START":
                paths.append(path)
    return sorted(str(path) for path in set(paths))


def promote_candidate(
    run_root: Path,
    *,
    model: str,
    bundle_sha256: str,
    smoke_report_path: Path,
) -> dict[str, Any]:
    root = Path(run_root).resolve(strict=True)
    model = _model(model)
    candidate = load_candidate_bundle(root, model=model, bundle_sha256=bundle_sha256)
    campaign = _campaign_identity(root)
    smoke_path = _within(root, smoke_report_path, must_exist=True)
    smoke = _strict_json_file(smoke_path)
    validate_route_smoke_report(
        smoke,
        campaign=campaign,
        model=model,
        bundle_sha256=bundle_sha256,
        route_id=candidate["route_id"],
        client_id=candidate["client_id"],
    )
    side_effects = _formal_side_effects(root, model)
    if side_effects:
        raise RouteBundleError(
            f"cannot bind a model after formal side effects: {side_effects[:5]}"
        )
    pointer = {
        "schema": FORMAL_BINDING_SCHEMA,
        "schema_version": FORMAL_SCHEMA_VERSION,
        "campaign": campaign,
        "generation_model": model,
        "bundle_path": Path(candidate["bundle_root"]).relative_to(root).as_posix(),
        "bundle_sha256": bundle_sha256,
        "bundle_manifest_sha256": candidate["bundle_manifest_sha256"],
        "committed_sha256": candidate["committed_sha256"],
        "transport_abi_version": TRANSPORT_ABI_VERSION,
        "transport_abi_sha256": TRANSPORT_ABI_SHA256,
        "protocol_sha256": schema.canonical_sha256(candidate["protocol"]),
        "route_id": candidate["route_id"],
        "client_id": candidate["client_id"],
        "coordination": dict(candidate["coordination"]),
        "smoke_report_path": smoke_path.relative_to(root).as_posix(),
        "smoke_report_sha256": storage.file_sha256(smoke_path),
        "promoted_at_utc": _utc_now(),
    }
    pointer_path = _within(root, f"{FORMAL_REL}/{model}.json")
    if pointer_path.exists():
        existing = _strict_json_file(pointer_path)
        validate_formal_binding(existing, run_root=root, expected_model=model)
        comparable_existing = dict(existing)
        comparable_new = dict(pointer)
        comparable_existing.pop("promoted_at_utc", None)
        comparable_new.pop("promoted_at_utc", None)
        if comparable_existing != comparable_new:
            raise RouteBundleError("model already has a different immutable formal binding")
        return dict(existing)
    exclusive_create_json(pointer_path, pointer)
    return load_formal_binding(root, model)


def validate_formal_binding(
    value: Mapping[str, Any],
    *,
    run_root: Path,
    expected_model: str,
    campaign_context: ValidatedCampaignContext | None = None,
) -> Mapping[str, Any]:
    root = Path(run_root).resolve(strict=True)
    model = _model(expected_model)
    expected = {
        "schema", "schema_version", "campaign", "generation_model", "bundle_path",
        "bundle_sha256", "bundle_manifest_sha256", "committed_sha256",
        "transport_abi_version", "transport_abi_sha256", "protocol_sha256",
        "route_id", "client_id", "coordination", "smoke_report_path",
        "smoke_report_sha256", "promoted_at_utc",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RouteBundleError("formal binding keys are not exact")
    if value["schema"] != FORMAL_BINDING_SCHEMA or value["schema_version"] != FORMAL_SCHEMA_VERSION:
        raise RouteBundleError("formal binding schema/version mismatch")
    campaign = _campaign_identity(root, campaign_context=campaign_context)
    if dict(value["campaign"]) != campaign or value["generation_model"] != model:
        raise RouteBundleError("formal binding campaign/model mismatch")
    candidate = load_candidate_bundle(
        root,
        model=model,
        bundle_sha256=value["bundle_sha256"],
        campaign_context=campaign_context,
    )
    if Path(candidate["bundle_root"]).relative_to(root).as_posix() != value["bundle_path"]:
        raise RouteBundleError("formal binding bundle path mismatch")
    for field in ("bundle_manifest_sha256", "committed_sha256"):
        if value[field] != candidate[field]:
            raise RouteBundleError(f"formal binding {field} mismatch")
    if value["transport_abi_version"] != TRANSPORT_ABI_VERSION or value["transport_abi_sha256"] != TRANSPORT_ABI_SHA256:
        raise RouteBundleError("formal binding transport ABI mismatch")
    if value["protocol_sha256"] != schema.canonical_sha256(candidate["protocol"]):
        raise RouteBundleError("formal binding protocol hash mismatch")
    if value["route_id"] != candidate["route_id"] or value["client_id"] != candidate["client_id"]:
        raise RouteBundleError("formal binding route/client mismatch")
    if dict(value["coordination"]) != dict(candidate["coordination"]):
        raise RouteBundleError("formal binding coordination mismatch")
    smoke_path = _within(root, value["smoke_report_path"], must_exist=True)
    if storage.file_sha256(smoke_path) != value["smoke_report_sha256"]:
        raise RouteBundleError("formal binding smoke report hash mismatch")
    smoke = _strict_json_file(smoke_path)
    validate_route_smoke_report(
        smoke,
        campaign=campaign,
        model=model,
        bundle_sha256=value["bundle_sha256"],
        route_id=candidate["route_id"],
        client_id=candidate["client_id"],
    )
    return value


def load_formal_binding(
    run_root: Path,
    model: str,
    *,
    campaign_context: ValidatedCampaignContext | None = None,
) -> dict[str, Any]:
    root = Path(run_root).resolve(strict=True)
    model = _model(model)
    path = _within(root, f"{FORMAL_REL}/{model}.json", must_exist=True)
    value = _strict_json_file(path)
    validate_formal_binding(
        value,
        run_root=root,
        expected_model=model,
        campaign_context=campaign_context,
    )
    result = dict(value)
    result["formal_pointer_path"] = path.relative_to(root).as_posix()
    result["formal_pointer_sha256"] = storage.file_sha256(path)
    candidate = load_candidate_bundle(
        root,
        model=model,
        bundle_sha256=result["bundle_sha256"],
        campaign_context=campaign_context,
    )
    result["candidate"] = candidate
    return result


def load_formal_bindings(
    run_root: Path,
    *,
    require_all: bool = False,
    campaign_context: ValidatedCampaignContext | None = None,
) -> dict[str, dict[str, Any]]:
    root = Path(run_root).resolve(strict=True)
    bindings: dict[str, dict[str, Any]] = {}
    for model in schema.MODELS:
        path = root / FORMAL_REL / f"{model}.json"
        if path.exists():
            bindings[model] = load_formal_binding(
                root, model, campaign_context=campaign_context
            )
        elif require_all:
            raise RouteBundleError(f"formal binding is missing for {model}")
    return bindings


def canonical_formal_binding_inventory(run_root: Path, *, require_all: bool) -> tuple[list[dict[str, str]], str]:
    root = Path(run_root).resolve(strict=True)
    bindings = load_formal_bindings(root, require_all=require_all)
    entries = [
        {
            "model": model,
            "path": bindings[model]["formal_pointer_path"],
            "sha256": bindings[model]["formal_pointer_sha256"],
            "bundle_sha256": bindings[model]["bundle_sha256"],
            "smoke_report_sha256": bindings[model]["smoke_report_sha256"],
        }
        for model in schema.MODELS
        if model in bindings
    ]
    return entries, schema.canonical_sha256(entries)


def canonical_launch_inventory(run_root: Path) -> tuple[list[dict[str, str]], str]:
    root = Path(run_root).resolve(strict=True)
    launches = root / LAUNCHES_REL
    entries: list[dict[str, str]] = []
    if launches.exists():
        for decision_path in sorted(launches.glob("*/decision.json")):
            decision = _strict_json_file(decision_path)
            if not isinstance(decision, Mapping) or decision.get("decision") != "START":
                continue
            launch_root = decision_path.parent
            launch_id = launch_root.name
            artifacts: list[tuple[str, str | None, Path]] = [
                ("request", None, launch_root / "request.json"),
            ]
            models = decision.get("models")
            if isinstance(models, list):
                artifacts.extend(
                    ("ready", str(model), launch_root / "ready" / f"{model}.json")
                    for model in models
                )
            artifacts.append(("decision", None, decision_path))
            if isinstance(models, list):
                artifacts.extend(
                    ("consumed", str(model), launch_root / "consumed" / f"{model}.json")
                    for model in models
                )
            artifacts.append(("result", None, launch_root / "result.json"))
            for kind, model, path in artifacts:
                if not path.is_file():
                    continue
                entry = {
                    "launch_id": launch_id,
                    "kind": kind,
                    "path": path.relative_to(root).as_posix(),
                    "sha256": storage.file_sha256(path),
                }
                if model is not None:
                    entry["generation_model"] = model
                entries.append(entry)
    return entries, schema.canonical_sha256(entries)


__all__ = [
    "BUNDLE_COMMIT_SCHEMA",
    "BUNDLE_SCHEMA",
    "BUNDLE_SCHEMA_VERSION",
    "CONTROL_EVENT_PREFIX",
    "CANDIDATES_REL",
    "COORDINATION_POLICIES",
    "FORMAL_BINDING_SCHEMA",
    "FORMAL_REL",
    "FORMAL_SCHEMA_VERSION",
    "FullValidationBudgetError",
    "FullValidationScope",
    "LAUNCHES_REL",
    "RouteBundleError",
    "SMOKE_REL",
    "SMOKE_SCHEMA",
    "VALIDATION_EVENT_PREFIX",
    "ValidatedCampaignContext",
    "build_candidate_bundle",
    "build_validated_campaign_context",
    "canonical_formal_binding_inventory",
    "canonical_launch_inventory",
    "current_full_validation_scope",
    "emit_adapter_constructed",
    "exclusive_create_bytes",
    "exclusive_create_json",
    "load_candidate_bundle",
    "load_formal_binding",
    "load_formal_bindings",
    "project_dependency_closure",
    "promote_candidate",
    "runtime_fingerprint",
    "set_full_validation_decision_state",
    "validate_candidate_bundle",
    "validate_formal_binding",
    "validate_manifest_full",
    "validate_route_smoke_report",
]
