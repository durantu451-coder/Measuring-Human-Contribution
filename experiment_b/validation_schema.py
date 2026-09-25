# -*- coding: utf-8 -*-
"""Canonical Experiment B validation protocol and row validation.

This module is deliberately independent of the validation runner.  Writers,
resume code, migrations, and metrics can therefore validate the same durable
row without importing API clients or making network calls.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableSet

SCHEMA_VERSION = 2
LEVELS = ("L1", "L2", "L3", "L4", "L5")
COMPRESSORS = ("zlib", "bz2", "lzma")

PROTOCOL_KEYS = frozenset(
    {
        "schema_version",
        "route",
        "use_alt_backend",
        "backend_pin",
        "max_output_tokens",
        "segment_output_tokens",
        "mode",
        "continuation_protocol",
        "reasoning_effort",
    }
)
COMPRESSOR_KEYS = frozenset(
    {"actual_ratio", "baseline_mean", "excess_ratio"}
)
CONTINUATION_MARKER_V1 = "<<<HC_CONTINUATION_7F3A>>>"
API3RD_BOUNDED_ROUTE = "backend_c_responses_bounded600_single_call"
API3RD_CLIENT_PATH = str(
    (Path(__file__).resolve().parent.parent / "clients" / "client_gpt_multi_origin.py").resolve()
)
_BOUNDED600_INSTRUCTIONS = (
    "Answer the user's request directly and completely in no more than 600 words. "
    "Reach a natural conclusion and end with a complete sentence before the output limit. "
    "Compress or omit lower-priority details rather than continuing indefinitely."
)
API3RD_BOUNDED_INSTRUCTIONS_SHA256 = hashlib.sha256(
    _BOUNDED600_INSTRUCTIONS.encode("utf-8")
).hexdigest()
SOURCE_PARITY_FIELDS = ("id", "dataset", "category", "level", "prompt")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ValidationSchemaError(ValueError):
    """A protocol, lineage manifest, provenance object, or row is invalid."""


@dataclass(frozen=True)
class LineageManifest:
    """The small, normalized portion of an active lineage manifest we consume."""

    raw: Mapping[str, Any]
    sha256: str
    path: Path | None
    expected_dataset_counts: Mapping[str, int]
    expected_total: int | None
    config_fingerprint: str | None
    legacy_validation_allowlist: frozenset[tuple[str, str, str]]
    model_identity_aliases: frozenset[tuple[str, str]]
    models: tuple[str, ...]


@dataclass(frozen=True)
class RowValidation:
    """Trust result for one successfully validated row."""

    model: str
    item_id: str
    canonical_row_sha256: str
    legacy_trusted: bool

    @property
    def legacy_unverified(self) -> bool:
        """Legacy rows are hash-trusted but lack complete modern provenance."""

        return self.legacy_trusted


def _error(path: str, message: str) -> ValidationSchemaError:
    return ValidationSchemaError(f"{path}: {message}")


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(path, "must be an object")
    return value


def _require_nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, "must be a non-empty string")
    return value


def _require_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise _error(path, "must be a boolean")
    return value


def _require_int(
    value: Any,
    path: str,
    *,
    minimum: int | None = None,
    allow_none: bool = False,
) -> int | None:
    if value is None and allow_none:
        return None
    if type(value) is not int:
        raise _error(path, "must be a non-boolean integer")
    if minimum is not None and value < minimum:
        raise _error(path, f"must be >= {minimum}")
    return value


def _require_finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, "must be a non-boolean number")
    result = float(value)
    if not math.isfinite(result):
        raise _error(path, "must be finite")
    return result


def assert_no_nonfinite_numbers(value: Any, path: str = "value") -> None:
    """Reject NaN/infinity anywhere in a decoded JSON-compatible tree."""

    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise _error(path, "contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            assert_no_nonfinite_numbers(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_no_nonfinite_numbers(child, f"{path}[{index}]")
        return
    raise _error(path, f"contains unsupported value type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical compact UTF-8 JSON representation."""

    assert_no_nonfinite_numbers(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationSchemaError(f"value is not canonical-JSON serializable: {exc}") from exc
    return text.encode("utf-8")


def canonical_row_sha256(row: Mapping[str, Any]) -> str:
    """Hash a complete row using canonical compact JSON, never line bytes."""

    _require_mapping(row, "row")
    return hashlib.sha256(canonical_json_bytes(row)).hexdigest()


def classify_model_identity(
    requested_model: str,
    returned_model: str,
    model_identity_aliases: Iterable[tuple[str, str]] = (),
) -> str | None:
    """Classify one raw model-identity pair without rewriting either value.

    Equality is always valid.  Additional identities are directed and must be
    declared by the active lineage; reverse, prefix, suffix, and regex matching
    are deliberately unsupported.
    """

    if requested_model == returned_model:
        return "exact"
    if (requested_model, returned_model) in frozenset(model_identity_aliases):
        return "canonical_alias"
    return None


def canonical_protocol(
    *,
    route: str,
    use_alt_backend: bool,
    backend_pin: int | None,
    max_output_tokens: int,
    segment_output_tokens: int | None,
    mode: str,
    continuation_protocol: str | None,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    """Build the sole schema-version-2 generation protocol representation."""

    protocol = {
        "schema_version": SCHEMA_VERSION,
        "route": route,
        "use_alt_backend": use_alt_backend,
        "backend_pin": backend_pin,
        "max_output_tokens": max_output_tokens,
        "segment_output_tokens": segment_output_tokens,
        "mode": mode,
        "continuation_protocol": continuation_protocol,
        "reasoning_effort": reasoning_effort,
    }
    validate_protocol(protocol)
    return protocol


# Descriptive aliases make the factory easy to adopt without creating a second
# representation.
canonical_protocol_factory = canonical_protocol
make_generation_protocol = canonical_protocol
build_generation_protocol = canonical_protocol


def validate_protocol(
    protocol: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
    path: str = "generation_protocol",
) -> None:
    """Validate the exact canonical protocol schema and optional exact value."""

    protocol = _require_mapping(protocol, path)
    keys = frozenset(protocol)
    if keys != PROTOCOL_KEYS:
        missing = sorted(PROTOCOL_KEYS - keys)
        extra = sorted(keys - PROTOCOL_KEYS)
        raise _error(path, f"keys must be exact (missing={missing}, extra={extra})")
    if protocol["schema_version"] != SCHEMA_VERSION:
        raise _error(f"{path}.schema_version", f"must equal {SCHEMA_VERSION}")
    _require_nonempty_string(protocol["route"], f"{path}.route")
    _require_bool(protocol["use_alt_backend"], f"{path}.use_alt_backend")
    gateway = _require_int(
        protocol["backend_pin"], f"{path}.backend_pin", minimum=1, allow_none=True
    )
    total_cap = _require_int(
        protocol["max_output_tokens"], f"{path}.max_output_tokens", minimum=1
    )
    segment_cap = _require_int(
        protocol["segment_output_tokens"],
        f"{path}.segment_output_tokens",
        minimum=1,
        allow_none=True,
    )
    mode = _require_nonempty_string(protocol["mode"], f"{path}.mode")
    continuation = protocol["continuation_protocol"]
    if continuation is not None:
        _require_nonempty_string(continuation, f"{path}.continuation_protocol")
    reasoning = protocol["reasoning_effort"]
    if reasoning is not None:
        _require_nonempty_string(reasoning, f"{path}.reasoning_effort")
    if segment_cap is not None and segment_cap > total_cap:
        raise _error(path, "segment_output_tokens cannot exceed max_output_tokens")
    if mode not in {"single_call", "segmented_budget"}:
        raise _error(f"{path}.mode", "must be single_call or segmented_budget")
    if mode == "segmented_budget":
        if segment_cap is None:
            raise _error(path, "segmented mode requires segment_output_tokens")
        if continuation not in {"marker_v1", "marker_v2_bounded600"}:
            raise _error(
                path,
                "segmented mode requires a supported marker continuation protocol",
            )
        if total_cap != 2 * segment_cap:
            raise _error(path, "segmented mode requires exactly two equal segment caps")
    else:
        if segment_cap is not None or continuation is not None:
            raise _error(
                path,
                "single_call mode requires null segment_output_tokens and continuation_protocol",
            )
    if gateway is not None and not protocol["use_alt_backend"]:
        raise _error(path, "a gateway is only valid when use_alt_backend is true")
    if expected is not None:
        validate_protocol(expected, path="expected_generation_protocol")
        if dict(protocol) != dict(expected):
            raise _error(path, "does not exactly match the configured protocol")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationSchemaError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def _reject_json_constant(token: str) -> None:
    raise ValidationSchemaError(f"non-standard/non-finite JSON constant {token!r}")


def strict_json_loads(text: str, *, path: str = "JSON") -> Any:
    """Decode strict JSON, rejecting duplicate keys and NaN/infinity."""

    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValidationSchemaError) as exc:
        raise _error(path, str(exc)) from exc
    assert_no_nonfinite_numbers(value, path)
    return value


def _extract_expected_counts(raw: Mapping[str, Any]) -> dict[str, int]:
    candidates: list[Any] = [
        raw.get("expected_dataset_counts"),
        raw.get("source_dataset_counts"),
        raw.get("expected_counts"),
    ]
    for parent_key in ("post_state", "expected_post_state", "counts", "coverage"):
        parent = raw.get(parent_key)
        if isinstance(parent, Mapping):
            candidates.extend(
                [
                    parent.get("source_counts"),
                    parent.get("dataset_counts"),
                    parent.get("expected_dataset_counts"),
                    parent.get("source_by_dataset"),
                ]
            )
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or not candidate:
            continue
        normalized: dict[str, int] = {}
        ok = True
        for key, value in candidate.items():
            if not isinstance(key, str) or not key or type(value) is not int or value < 0:
                ok = False
                break
            normalized[key] = value
        if ok:
            return normalized
    return {}


def _iter_legacy_entries(value: Any) -> Iterable[tuple[str, str, str]]:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, Mapping):
                raise ValidationSchemaError("legacy allowlist entries must be objects")
            model = item.get("model")
            item_id = item.get("id")
            digest = item.get("canonical_row_sha256", item.get("row_sha256"))
            yield (model, item_id, digest)  # type: ignore[misc]
        return
    if isinstance(value, Mapping):
        for model, entries in value.items():
            if isinstance(entries, Mapping):
                for item_id, digest in entries.items():
                    yield (model, item_id, digest)  # type: ignore[misc]
            elif isinstance(entries, list):
                for item in entries:
                    if isinstance(item, Mapping):
                        item_id = item.get("id")
                        digest = item.get(
                            "canonical_row_sha256", item.get("row_sha256")
                        )
                    else:
                        raise ValidationSchemaError(
                            "legacy per-model allowlist entries must be objects"
                        )
                    yield (model, item_id, digest)  # type: ignore[misc]
            else:
                raise ValidationSchemaError("invalid legacy allowlist mapping")
        return
    raise ValidationSchemaError("legacy allowlist must be a list or object")


def _extract_legacy_allowlist(
    raw: Mapping[str, Any],
) -> frozenset[tuple[str, str, str]]:
    candidates: list[Any] = [
        raw.get("legacy_validation_allowlist"),
        raw.get("legacy_allowlist"),
        raw.get("legacy_validation_rows"),
    ]
    for parent_key in ("validation", "lineage", "post_state"):
        parent = raw.get(parent_key)
        if isinstance(parent, Mapping):
            candidates.extend(
                [
                    parent.get("legacy_validation_allowlist"),
                    parent.get("legacy_allowlist"),
                    parent.get("legacy_validation_rows"),
                ]
            )
    selected = next((candidate for candidate in candidates if candidate is not None), None)
    if selected is None:
        return frozenset()
    result: set[tuple[str, str, str]] = set()
    for model, item_id, digest in _iter_legacy_entries(selected):
        model = _require_nonempty_string(model, "legacy_allowlist.model")
        item_id = _require_nonempty_string(item_id, "legacy_allowlist.id")
        digest = _require_nonempty_string(
            digest, "legacy_allowlist.canonical_row_sha256"
        ).lower()
        if not _SHA256_RE.fullmatch(digest):
            raise ValidationSchemaError(
                f"legacy allowlist hash for ({model!r}, {item_id!r}) is not SHA-256"
            )
        key = (model, item_id, digest)
        if key in result:
            raise ValidationSchemaError(f"duplicate legacy allowlist entry {key!r}")
        result.add(key)
    return frozenset(result)


def _extract_model_identity_aliases(
    raw: Mapping[str, Any], models: Iterable[str]
) -> frozenset[tuple[str, str]]:
    value = raw.get("model_identity_aliases")
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise ValidationSchemaError("model_identity_aliases must be a list")

    known_models = frozenset(models)
    result: set[tuple[str, str]] = set()
    wildcard_characters = frozenset("*?[]")
    for index, entry_value in enumerate(value):
        path = f"lineage_manifest.model_identity_aliases[{index}]"
        entry = _require_mapping(entry_value, path)
        expected_keys = {"requested_model", "returned_model"}
        if set(entry) != expected_keys:
            missing = sorted(expected_keys - set(entry))
            extra = sorted(set(entry) - expected_keys)
            raise _error(path, f"keys must be exact (missing={missing}, extra={extra})")
        requested = _require_nonempty_string(
            entry["requested_model"], f"{path}.requested_model"
        )
        returned = _require_nonempty_string(
            entry["returned_model"], f"{path}.returned_model"
        )
        if requested not in known_models:
            raise _error(path, f"requested model {requested!r} is absent from manifest models")
        if requested == returned:
            raise _error(path, "self-aliases are redundant and forbidden")
        if any(character in wildcard_characters for character in requested + returned):
            raise _error(path, "wildcard characters are forbidden")
        pair = (requested, returned)
        if pair in result:
            raise _error(path, f"duplicate directed alias {pair!r}")
        result.add(pair)
    return frozenset(result)


def load_lineage_manifest(
    manifest: str | os.PathLike[str] | Mapping[str, Any],
) -> LineageManifest:
    """Load and normalize an explicit lineage manifest.

    File-backed manifests use the SHA-256 of their exact bytes.  In-memory test
    manifests use the canonical JSON SHA-256.
    """

    path: Path | None
    if isinstance(manifest, Mapping):
        raw = dict(manifest)
        digest = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
        path = None
    else:
        path = Path(manifest).resolve()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ValidationSchemaError(f"cannot read lineage manifest {path}: {exc}") from exc
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationSchemaError(f"lineage manifest is not UTF-8: {path}") from exc
        raw_value = strict_json_loads(text, path=str(path))
        raw = dict(_require_mapping(raw_value, str(path)))
        digest = hashlib.sha256(data).hexdigest()

    assert_no_nonfinite_numbers(raw, "lineage_manifest")
    counts = _extract_expected_counts(raw)
    explicit_total = raw.get("expected_total", raw.get("source_total"))
    if explicit_total is not None:
        explicit_total = _require_int(
            explicit_total, "lineage_manifest.expected_total", minimum=0
        )
    count_total = sum(counts.values()) if counts else None
    if explicit_total is not None and count_total is not None and explicit_total != count_total:
        raise ValidationSchemaError(
            "lineage manifest expected_total disagrees with dataset counts"
        )
    expected_total = explicit_total if explicit_total is not None else count_total

    fingerprint = raw.get("config_fingerprint")
    if fingerprint is None and isinstance(raw.get("configuration"), Mapping):
        fingerprint = raw["configuration"].get("fingerprint")
    if fingerprint is not None:
        fingerprint = _require_nonempty_string(
            fingerprint, "lineage_manifest.config_fingerprint"
        )

    models_value = raw.get("models", ())
    if isinstance(models_value, Mapping):
        models_iterable = models_value.keys()
    elif isinstance(models_value, (list, tuple)):
        models_iterable = models_value
    else:
        raise ValidationSchemaError("lineage_manifest.models must be a list or object")
    models: list[str] = []
    for index, model in enumerate(models_iterable):
        value = _require_nonempty_string(model, f"lineage_manifest.models[{index}]")
        if value in models:
            raise ValidationSchemaError(f"duplicate manifest model {value!r}")
        models.append(value)

    return LineageManifest(
        raw=raw,
        sha256=digest,
        path=path,
        expected_dataset_counts=counts,
        expected_total=expected_total,
        config_fingerprint=fingerprint,
        legacy_validation_allowlist=_extract_legacy_allowlist(raw),
        model_identity_aliases=_extract_model_identity_aliases(raw, models),
        models=tuple(models),
    )


def find_active_lineage_manifest(output_dir: str | os.PathLike[str]) -> Path:
    """Resolve the active manifest without guessing from historical backups."""

    env_value = os.environ.get("EXPERIMENT_B_LINEAGE_MANIFEST")
    if env_value:
        path = Path(env_value).expanduser().resolve()
        if not path.is_file():
            raise ValidationSchemaError(
                f"EXPERIMENT_B_LINEAGE_MANIFEST does not name a file: {path}"
            )
        return path

    output = Path(output_dir).resolve()
    status_path = output / "experiment_b_status.json"
    if status_path.is_file():
        status = _require_mapping(
            strict_json_loads(status_path.read_text(encoding="utf-8"), path=str(status_path)),
            str(status_path),
        )
        pointer = status.get("active_lineage_manifest", status.get("lineage_manifest"))
        if pointer is not None:
            pointer = _require_nonempty_string(pointer, f"{status_path}.lineage_manifest")
            candidate = Path(pointer)
            if not candidate.is_absolute():
                candidate = (status_path.parent / candidate).resolve()
            if not candidate.is_file():
                raise ValidationSchemaError(
                    f"status points to a missing lineage manifest: {candidate}"
                )
            return candidate

    candidates = [
        output / "lineage_manifest.json",
        output / "experiment_b_lineage_manifest.json",
        output.parent / "lineage_manifest.json",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        raise ValidationSchemaError(
            f"no active Experiment B lineage manifest found under {output}"
        )
    if len(existing) > 1:
        raise ValidationSchemaError(
            "multiple candidate lineage manifests exist; set "
            "EXPERIMENT_B_LINEAGE_MANIFEST or an active status pointer"
        )
    return existing[0]


def load_active_lineage_manifest(output_dir: str | os.PathLike[str]) -> LineageManifest:
    return load_lineage_manifest(find_active_lineage_manifest(output_dir))


def _normalize_endpoint(provenance: Mapping[str, Any], path: str) -> str:
    explicit: list[str] = []
    for key in ("endpoint", "endpoint_type", "api"):
        value = provenance.get(key)
        if value is not None:
            explicit.append(_require_nonempty_string(value, f"{path}.{key}").lower())
    normalized_explicit: set[str] = set()
    aliases = {
        "responses": "responses",
        "response": "responses",
        "openai_responses": "responses",
        "messages": "messages",
        "anthropic_messages": "messages",
        "chat": "chat",
        "chat_completions": "chat",
        "openai_chat_completions": "chat",
        "responses_segmented": "responses",
        "local": "local",
        "local_fallback": "local",
    }
    for value in explicit:
        normalized = aliases.get(value)
        if normalized is None:
            raise _error(path, f"unknown endpoint {value!r}")
        normalized_explicit.add(normalized)
    if len(normalized_explicit) > 1:
        raise _error(path, "has conflicting endpoint declarations")

    terminal_shapes = {
        "responses": "status" in provenance,
        "messages": "stop_reason" in provenance,
        "chat": "finish_reason" in provenance,
    }
    present_shapes = {name for name, present in terminal_shapes.items() if present}
    if len(present_shapes) > 1:
        raise _error(path, "has ambiguous terminal fields from multiple endpoints")
    if normalized_explicit:
        endpoint = next(iter(normalized_explicit))
        if endpoint != "local" and present_shapes and endpoint not in present_shapes:
            raise _error(path, "endpoint disagrees with its terminal field")
        return endpoint
    if len(present_shapes) != 1:
        raise _error(path, "must identify exactly one endpoint/terminal shape")
    return next(iter(present_shapes))


def _model_field(
    provenance: Mapping[str, Any], keys: tuple[str, ...], path: str
) -> str | None:
    values: list[str] = []
    for key in keys:
        if key in provenance and provenance[key] is not None:
            values.append(_require_nonempty_string(provenance[key], f"{path}.{key}"))
    if len(set(values)) > 1:
        raise _error(path, f"conflicting model fields {keys}")
    return values[0] if values else None


def _reject_bad_completion_signals(provenance: Mapping[str, Any], path: str) -> None:
    for key in (
        "refusal",
        "refused",
        "content_filtered",
        "content_filter_results",
        "safety_blocked",
        "tool_only",
    ):
        value = provenance.get(key)
        if value not in (None, False, "", [], {}):
            raise _error(path, f"{key} indicates unusable output")
    tool_calls = provenance.get("tool_calls")
    text_chars = provenance.get("output_chars", provenance.get("text_chars"))
    if tool_calls not in (None, [], {}) and (text_chars is None or text_chars == 0):
        raise _error(path, "tool-only output is not valid text")


def _incomplete_reason(provenance: Mapping[str, Any]) -> Any:
    reason = provenance.get("incomplete_reason")
    details = provenance.get("incomplete_details")
    if isinstance(details, Mapping):
        detail_reason = details.get("reason")
        if reason is not None and detail_reason is not None and reason != detail_reason:
            raise ValidationSchemaError("conflicting incomplete reasons")
        reason = detail_reason if detail_reason is not None else reason
    return reason


def _validate_terminal(
    provenance: Mapping[str, Any], endpoint: str, path: str, *, allow_incomplete: bool
) -> bool:
    """Validate a terminal shape and return whether it is incomplete."""

    if endpoint == "responses":
        status = provenance.get("status")
        if status == "completed":
            return False
        if status == "incomplete" and allow_incomplete:
            if _incomplete_reason(provenance) != "max_output_tokens":
                raise _error(path, "only max_output_tokens may make segment 1 incomplete")
            return True
        raise _error(f"{path}.status", "Responses must be completed")
    if endpoint == "messages":
        stop_reason = provenance.get("stop_reason")
        if stop_reason not in {"end_turn", "stop_sequence"}:
            raise _error(
                f"{path}.stop_reason",
                "Messages must stop via end_turn or stop_sequence",
            )
        return False
    if endpoint == "chat":
        if provenance.get("finish_reason") != "stop":
            raise _error(f"{path}.finish_reason", "Chat must finish with stop")
        return False
    raise _error(path, f"unsupported terminal endpoint {endpoint!r}")


def _marker_flag(container: Mapping[str, Any], final: Mapping[str, Any]) -> bool | None:
    for key in (
        "continuation_marker_valid",
        "continuation_marker_present",
        "continuation_marker_found",
    ):
        if key in final:
            return final[key]
        if key in container:
            return container[key]
    marker = final.get("continuation_marker", container.get("continuation_marker"))
    if marker is not None:
        return marker == CONTINUATION_MARKER_V1
    return None


def _restart_flag(container: Mapping[str, Any], final: Mapping[str, Any]) -> bool | None:
    for key in ("restart_detected", "continuation_restart_detected"):
        if key in final:
            return final[key]
        if key in container:
            return container[key]
    # Existing marker-v1 metadata records one boundary_verified attestation for
    # both marker presence and the anti-restart check performed by the merger.
    if container.get("boundary_verified") is True:
        return False
    return None


def _validate_identity_attestations(
    provenance: Mapping[str, Any], identity_kind: str, path: str
) -> None:
    exact = identity_kind == "exact"
    expected = {
        "model_identity_kind": identity_kind,
        "model_identity_accepted": True,
        "model_identity_exact": exact,
        "completed_exact_model": exact,
    }
    if not exact:
        missing = [key for key in expected if key not in provenance]
        if missing:
            raise _error(path, f"canonical alias provenance lacks attestations {missing}")
    for key, expected_value in expected.items():
        if key not in provenance:
            continue
        value = provenance[key]
        if isinstance(expected_value, bool):
            _require_bool(value, f"{path}.{key}")
        if value != expected_value:
            raise _error(
                f"{path}.{key}",
                f"must equal {expected_value!r} for {identity_kind} identity",
            )


def validate_endpoint_provenance(
    provenance: Mapping[str, Any],
    *,
    expected_model: str,
    path: str = "provenance",
    require_models: bool = True,
    model_identity_aliases: Iterable[tuple[str, str]] = (),
) -> None:
    """Validate model identity, endpoint terminal state, and segmentation.

    Responses may have two persisted segments.  Only the first may be incomplete,
    and then only with ``max_output_tokens``; the final segment must be completed
    and must attest that the continuation marker was accepted without restart.
    Messages and Chat have no accepted truncation terminal.
    """

    provenance = _require_mapping(provenance, path)
    _require_nonempty_string(expected_model, "expected_model")
    endpoint = _normalize_endpoint(provenance, path)
    if endpoint == "local":
        raise _error(path, "local provenance is not an API completion")
    _reject_bad_completion_signals(provenance, path)

    requested = _model_field(
        provenance, ("requested_model", "model_requested"), path
    )
    returned = _model_field(
        provenance, ("returned_model", "response_model", "model_returned"), path
    )
    if returned is None and "model" in provenance:
        returned = _require_nonempty_string(provenance["model"], f"{path}.model")
    if require_models and (requested is None or returned is None):
        raise _error(path, "must persist requested_model and returned_model")
    if requested is not None and requested != expected_model:
        raise _error(path, f"requested model {requested!r} != {expected_model!r}")
    parent_identity_kind: str | None = None
    if returned is not None:
        parent_identity_kind = classify_model_identity(
            requested or expected_model,
            returned,
            model_identity_aliases,
        )
        if parent_identity_kind is None:
            raise _error(
                path,
                f"returned model {returned!r} is not allowed for {expected_model!r}",
            )
        _validate_identity_attestations(provenance, parent_identity_kind, path)

    segments_value = provenance.get("segments")
    if segments_value is None:
        _validate_terminal(provenance, endpoint, path, allow_incomplete=False)
        return
    if not isinstance(segments_value, list) or not 1 <= len(segments_value) <= 2:
        raise _error(f"{path}.segments", "must contain one or two segment objects")

    segments = [
        _require_mapping(value, f"{path}.segments[{index}]")
        for index, value in enumerate(segments_value)
    ]
    incomplete: list[bool] = []
    for index, segment in enumerate(segments):
        segment_path = f"{path}.segments[{index}]"
        segment_endpoint = _normalize_endpoint(segment, segment_path)
        if segment_endpoint != endpoint:
            raise _error(segment_path, "segment endpoint differs from parent")
        _reject_bad_completion_signals(segment, segment_path)
        segment_requested = _model_field(
            segment, ("requested_model", "model_requested"), segment_path
        )
        segment_returned = _model_field(
            segment,
            ("returned_model", "response_model", "model_returned"),
            segment_path,
        )
        if segment_returned is None and "model" in segment:
            segment_returned = _require_nonempty_string(
                segment["model"], f"{segment_path}.model"
            )
        if (segment_requested is None) != (segment_returned is None):
            raise _error(
                segment_path,
                "segment model provenance must contain both requested and returned models",
            )
        if (
            parent_identity_kind == "canonical_alias"
            and segment_requested is None
            and segment_returned is None
        ):
            raise _error(
                segment_path,
                "canonical alias parent requires explicit segment model provenance",
            )
        if segment_requested is not None and segment_requested != expected_model:
            raise _error(segment_path, "segment requested model mismatch")
        if segment_returned is not None:
            segment_identity_kind = classify_model_identity(
                segment_requested or expected_model,
                segment_returned,
                model_identity_aliases,
            )
            if segment_identity_kind is None:
                raise _error(segment_path, "segment returned model mismatch")
            if (
                parent_identity_kind is not None
                and segment_identity_kind != parent_identity_kind
            ):
                raise _error(segment_path, "segment identity differs from parent identity")
            _validate_identity_attestations(
                segment, segment_identity_kind, segment_path
            )
        incomplete.append(
            _validate_terminal(
                segment,
                segment_endpoint,
                segment_path,
                allow_incomplete=index == 0 and len(segments) == 2,
            )
        )
    if incomplete[-1]:
        raise _error(f"{path}.segments[-1]", "final segment must be completed")
    if len(segments) == 2:
        if not incomplete[0]:
            raise _error(path, "a completed first segment must not be continued")
        marker = _marker_flag(provenance, segments[-1])
        restart = _restart_flag(provenance, segments[-1])
        if marker is not True:
            raise _error(path, "continued response lacks a validated continuation marker")
        if restart is not False:
            raise _error(path, "continued response lacks an explicit no-restart check")
    _validate_terminal(provenance, endpoint, path, allow_incomplete=False)


def _validate_local_reconstruction(provenance: Mapping[str, Any], path: str) -> bool:
    endpoint = _normalize_endpoint(provenance, path)
    local_flag = provenance.get("local_fallback")
    if endpoint != "local":
        if local_flag is True:
            raise _error(path, "local_fallback conflicts with a non-local endpoint")
        return False
    # ``api=local_fallback`` is itself the required explicit marker.  A
    # boolean local_fallback=true is an accepted equivalent for future rows.
    if provenance.get("status") != "fallback":
        raise _error(path, "local reconstruction must have status=fallback")
    _require_nonempty_string(provenance.get("reason"), f"{path}.reason")
    return True


def validate_api_provenance(
    api_provenance: Mapping[str, Any],
    *,
    expected_model: str,
    cf_total: int,
    cf_valid: int,
    path: str = "api_provenance",
    model_identity_aliases: Iterable[tuple[str, str]] = (),
) -> None:
    """Validate main, reconstruction, and all counterfactual provenance."""

    api_provenance = _require_mapping(api_provenance, path)
    required = {"main", "reconstruct", "counterfactuals"}
    missing = required - set(api_provenance)
    if missing:
        raise _error(path, f"missing provenance sections {sorted(missing)}")
    validate_endpoint_provenance(
        _require_mapping(api_provenance["main"], f"{path}.main"),
        expected_model=expected_model,
        path=f"{path}.main",
        model_identity_aliases=model_identity_aliases,
    )
    reconstruction = _require_mapping(
        api_provenance["reconstruct"], f"{path}.reconstruct"
    )
    if not _validate_local_reconstruction(reconstruction, f"{path}.reconstruct"):
        validate_endpoint_provenance(
            reconstruction,
            expected_model=expected_model,
            path=f"{path}.reconstruct",
            model_identity_aliases=model_identity_aliases,
        )

    counterfactuals = api_provenance["counterfactuals"]
    if not isinstance(counterfactuals, list) or len(counterfactuals) != cf_total:
        raise _error(
            f"{path}.counterfactuals", f"must contain exactly cf_total={cf_total} entries"
        )
    valid_count = 0
    for index, raw_entry in enumerate(counterfactuals):
        entry_path = f"{path}.counterfactuals[{index}]"
        entry = _require_mapping(raw_entry, entry_path)
        if entry.get("label") != f"cf_{index + 1}":
            raise _error(entry_path, f"label must equal cf_{index + 1}")
        valid = _require_bool(entry.get("valid"), f"{entry_path}.valid")
        metadata = entry.get(
            "metadata", entry.get("provenance", entry.get("response"))
        )
        if valid:
            valid_count += 1
            validate_endpoint_provenance(
                _require_mapping(metadata, f"{entry_path}.metadata"),
                expected_model=expected_model,
                path=f"{entry_path}.metadata",
                model_identity_aliases=model_identity_aliases,
            )
        else:
            reason = entry.get("invalid_reason", entry.get("error"))
            if metadata is None:
                _require_nonempty_string(reason, f"{entry_path}.error")
            else:
                # A completed request can still be excluded by the shared
                # output/error-marker validator.  Its transport provenance is
                # nevertheless required and must itself be admissible.
                validate_endpoint_provenance(
                    _require_mapping(metadata, f"{entry_path}.metadata"),
                    expected_model=expected_model,
                    path=f"{entry_path}.metadata",
                    model_identity_aliases=model_identity_aliases,
                )
    if valid_count != cf_valid:
        raise _error(path, f"valid CF provenance count {valid_count} != cf_valid {cf_valid}")


def _validate_backend_c_bounded_call(
    metadata: Mapping[str, Any],
    *,
    expected_model: str,
    expected_instructions_sha256: str | None,
    path: str,
) -> None:
    metadata = _require_mapping(metadata, path)
    if metadata.get("api") != "responses":
        raise _error(f"{path}.api", "API3rd bounded calls must use Responses")
    if metadata.get("route") != "backend_c":
        raise _error(f"{path}.route", "must equal 'backend_c'")
    if metadata.get("gateway") != "auto":
        raise _error(f"{path}.gateway", "must equal 'auto'")
    client = _require_nonempty_string(metadata.get("client"), f"{path}.client")
    if str(Path(client).resolve()) != API3RD_CLIENT_PATH:
        raise _error(f"{path}.client", "does not equal the approved API3rd client")
    cap = _require_int(
        metadata.get("max_output_tokens"), f"{path}.max_output_tokens", minimum=1
    )
    if cap != 4096:
        raise _error(f"{path}.max_output_tokens", "must equal 4096")
    requested = _require_nonempty_string(
        metadata.get("requested_model"), f"{path}.requested_model"
    )
    returned = _require_nonempty_string(
        metadata.get("returned_model"), f"{path}.returned_model"
    )
    if requested != expected_model or returned != expected_model:
        raise _error(path, "API3rd bounded calls require exact model identity")
    _require_nonempty_string(metadata.get("response_id"), f"{path}.response_id")
    observed_hash = metadata.get("instructions_sha256")
    if expected_instructions_sha256 is None:
        if observed_hash is not None:
            raise _error(
                f"{path}.instructions_sha256",
                "reconstruction must not receive bounded instructions",
            )
    else:
        observed = _require_nonempty_string(
            observed_hash, f"{path}.instructions_sha256"
        )
        if not _SHA256_RE.fullmatch(observed):
            raise _error(f"{path}.instructions_sha256", "must be lowercase SHA-256")
        if observed != expected_instructions_sha256:
            raise _error(f"{path}.instructions_sha256", "bounded instruction hash mismatch")


def validate_backend_c_bounded_provenance(
    api_provenance: Mapping[str, Any],
    *,
    expected_model: str,
    path: str = "api_provenance",
) -> None:
    """Enforce B's role-specific API3rd bounded600 provenance contract."""

    api_provenance = _require_mapping(api_provenance, path)
    _validate_backend_c_bounded_call(
        _require_mapping(api_provenance.get("main"), f"{path}.main"),
        expected_model=expected_model,
        expected_instructions_sha256=API3RD_BOUNDED_INSTRUCTIONS_SHA256,
        path=f"{path}.main",
    )
    _validate_backend_c_bounded_call(
        _require_mapping(api_provenance.get("reconstruct"), f"{path}.reconstruct"),
        expected_model=expected_model,
        expected_instructions_sha256=None,
        path=f"{path}.reconstruct",
    )
    counterfactuals = api_provenance.get("counterfactuals")
    if not isinstance(counterfactuals, list):
        raise _error(f"{path}.counterfactuals", "must be a list")
    for index, raw_entry in enumerate(counterfactuals):
        entry_path = f"{path}.counterfactuals[{index}]"
        entry = _require_mapping(raw_entry, entry_path)
        metadata = entry.get("metadata", entry.get("provenance", entry.get("response")))
        if metadata is None:
            if entry.get("valid") is True:
                raise _error(entry_path, "valid API3rd CF lacks metadata")
            continue
        _validate_backend_c_bounded_call(
            _require_mapping(metadata, f"{entry_path}.metadata"),
            expected_model=expected_model,
            expected_instructions_sha256=API3RD_BOUNDED_INSTRUCTIONS_SHA256,
            path=f"{entry_path}.metadata",
        )


def validate_source_parity(
    row: Mapping[str, Any], source: Mapping[str, Any], *, path: str = "row"
) -> None:
    """Require durable validation identity and labels to match the source row."""

    row = _require_mapping(row, path)
    source = _require_mapping(source, "source")
    for field in SOURCE_PARITY_FIELDS:
        if field not in row or field not in source:
            raise _error(path, f"source parity field {field!r} is missing")
        if row[field] != source[field]:
            raise _error(path, f"field {field!r} differs from source")
    if row["level"] not in LEVELS:
        raise _error(f"{path}.level", f"must be one of {LEVELS}")
    if "strat_excess_ratio" not in row or "excess_ratio" not in source:
        raise _error(path, "strat_excess_ratio/source excess_ratio parity is missing")
    stratified = _require_finite_number(
        row["strat_excess_ratio"], f"{path}.strat_excess_ratio"
    )
    source_value = _require_finite_number(source["excess_ratio"], "source.excess_ratio")
    if stratified != source_value:
        raise _error(path, "strat_excess_ratio differs from source excess_ratio")


def _validate_arithmetic(values: Mapping[str, Any], path: str) -> None:
    if frozenset(values) != COMPRESSOR_KEYS:
        missing = sorted(COMPRESSOR_KEYS - frozenset(values))
        extra = sorted(frozenset(values) - COMPRESSOR_KEYS)
        raise _error(path, f"keys must be exact (missing={missing}, extra={extra})")
    actual = _require_finite_number(values["actual_ratio"], f"{path}.actual_ratio")
    baseline = _require_finite_number(
        values["baseline_mean"], f"{path}.baseline_mean"
    )
    excess = _require_finite_number(values["excess_ratio"], f"{path}.excess_ratio")
    expected = actual - baseline
    if not math.isclose(excess, expected, rel_tol=0.0, abs_tol=1e-12):
        raise _error(
            f"{path}.excess_ratio",
            f"must equal actual_ratio - baseline_mean within 1e-12 ({expected!r})",
        )


def _validate_core_row(row: Mapping[str, Any], expected_model: str, path: str) -> None:
    item_id = _require_nonempty_string(row.get("id"), f"{path}.id")
    del item_id
    model = _require_nonempty_string(row.get("model"), f"{path}.model")
    if model != expected_model:
        raise _error(f"{path}.model", f"must exactly equal {expected_model!r}")
    if row.get("level") not in LEVELS:
        raise _error(f"{path}.level", f"must be one of {LEVELS}")
    for key in ("dataset", "category", "prompt"):
        _require_nonempty_string(row.get(key), f"{path}.{key}")
    output = _require_nonempty_string(row.get("output"), f"{path}.output")
    output_chars = _require_int(row.get("output_chars"), f"{path}.output_chars", minimum=1)
    if output_chars != len(output):
        raise _error(f"{path}.output_chars", f"must equal len(output)={len(output)}")

    cf_valid = _require_int(row.get("cf_valid"), f"{path}.cf_valid", minimum=0)
    cf_total = _require_int(row.get("cf_total"), f"{path}.cf_total", minimum=0)
    if not 3 <= cf_valid <= cf_total <= 5:
        raise _error(path, "must satisfy 3 <= cf_valid <= cf_total <= 5")
    baseline_n_valid = _require_int(
        row.get("baseline_n_valid"), f"{path}.baseline_n_valid", minimum=0
    )
    if baseline_n_valid != cf_valid:
        raise _error(path, "baseline_n_valid must equal cf_valid")

    top_metrics = {
        "actual_ratio": row.get("actual_ratio"),
        "baseline_mean": row.get("baseline_mean"),
        "excess_ratio": row.get("excess_ratio"),
    }
    _validate_arithmetic(top_metrics, path)
    _require_finite_number(row.get("actual_gain_bits"), f"{path}.actual_gain_bits")
    _require_finite_number(
        row.get("strat_excess_ratio"), f"{path}.strat_excess_ratio"
    )

    per_compressor = _require_mapping(
        row.get("per_compressor"), f"{path}.per_compressor"
    )
    if frozenset(per_compressor) != frozenset(COMPRESSORS):
        raise _error(
            f"{path}.per_compressor",
            f"compressors must be exactly {list(COMPRESSORS)}",
        )
    for compressor in COMPRESSORS:
        metrics = _require_mapping(
            per_compressor[compressor], f"{path}.per_compressor.{compressor}"
        )
        _validate_arithmetic(metrics, f"{path}.per_compressor.{compressor}")
    assert_no_nonfinite_numbers(row, path)


def validate_validation_row(
    row: Mapping[str, Any],
    *,
    expected_model: str | None = None,
    source: Mapping[str, Any] | None = None,
    require_source: bool = False,
    expected_protocol: Mapping[str, Any] | None = None,
    legacy_allowlist: Iterable[tuple[str, str, str]] = (),
    model_identity_aliases: Iterable[tuple[str, str]] = (),
    seen_ids: MutableSet[str] | None = None,
    path: str = "row",
) -> RowValidation:
    """Validate one row and return whether its modern checks were hash-waived.

    A legacy allowlist entry is trusted only when model, ID, and the canonical
    hash of the *entire row* all match.  It waives only schema-v2 protocol and
    API provenance checks; all core/source/arithmetic checks still run.
    """

    row = _require_mapping(row, path)
    model_value = row.get("model") if expected_model is None else expected_model
    model = _require_nonempty_string(model_value, "expected_model")
    _validate_core_row(row, model, path)
    item_id = row["id"]
    if seen_ids is not None:
        if item_id in seen_ids:
            raise _error(f"{path}.id", f"duplicate ID {item_id!r}")

    if source is None:
        if require_source:
            raise _error(path, "source row is required for parity validation")
    else:
        validate_source_parity(row, source, path=path)

    digest = canonical_row_sha256(row)
    allowset = frozenset(legacy_allowlist)
    legacy_trusted = (model, item_id, digest) in allowset
    if not legacy_trusted:
        protocol = _require_mapping(
            row.get("generation_protocol"), f"{path}.generation_protocol"
        )
        validate_protocol(
            protocol, expected=expected_protocol, path=f"{path}.generation_protocol"
        )
        api_provenance = _require_mapping(
            row.get("api_provenance"), f"{path}.api_provenance"
        )
        validate_api_provenance(
            api_provenance,
            expected_model=model,
            cf_total=row["cf_total"],
            cf_valid=row["cf_valid"],
            path=f"{path}.api_provenance",
            model_identity_aliases=model_identity_aliases,
        )
        if protocol.get("route") == API3RD_BOUNDED_ROUTE:
            validate_backend_c_bounded_provenance(
                api_provenance,
                expected_model=model,
                path=f"{path}.api_provenance",
            )
    if seen_ids is not None:
        seen_ids.add(item_id)
    return RowValidation(
        model=model,
        item_id=item_id,
        canonical_row_sha256=digest,
        legacy_trusted=legacy_trusted,
    )


# Short alias for callers that already know they are validating a validation row.
validate_row = validate_validation_row
