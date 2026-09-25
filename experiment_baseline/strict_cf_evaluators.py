# -*- coding: utf-8 -*-
"""Isolated seven-evaluator white-box protocol for strict-CF v1.

This module reuses :mod:`experiment_baseline.whitebox_core` for its prepared
loss scorer and phi arithmetic, but deliberately replaces legacy tokenization.
One response-with-EOS target event is built once and used identically in the
unconditional and conditional losses for all seven model families.  The module
does not mutate the canonical two-model registry and has separate phases:

* ``actual`` can score immutable ``snapshots/actual_levels.jsonl`` before any
  counterfactual exists;
* ``counterfactual`` exact-joins a finalized six-pair source to the durable
  actual result and scores only its five ordered CF pairs.

Torch and transformers imports are lazy so validation and finalized no-op paths
cannot initialize CUDA.
"""
from __future__ import annotations

import importlib.metadata
import math
import os
import platform
import statistics
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from experiment_a import strict_cf_schema as strict_schema
from experiment_b import storage
from experiment_baseline import whitebox_core

SCHEMA_VERSION = 1
SCHEMA_ID = "experiment_baseline.strict_cf_whitebox_v1"
EXPECTED_LEVEL_ROWS = strict_schema.EXPECTED_LEVEL_ROWS
STRICT_CF_COUNT = strict_schema.STRICT_CF_COUNT
IDENTITY_FIELDS = (
    "semantic_key", "generation_model", "domain", "id", "source_id",
    "source_index", "source_text_sha256", "level", "source_cluster",
)
ROLE_CANONICAL_PRIMARY = "canonical_primary"
ROLE_EXPANDED_ROBUSTNESS = "expanded_robustness"

# Independent deployed-checkpoint registry.  In particular these objects are
# not aliases of whitebox_core.EVAL_MODELS / EVAL_DTYPES.
EVALUATORS: dict[str, dict[str, Any]] = {
    "llama3.2-3b": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/Llama-3.2-3B-Instruct"), "dtype": "bfloat16", "attention": None, "trust_remote_code": False, "tokenizer_use_fast": None, "role": ROLE_EXPANDED_ROBUSTNESS},
    "llama3.1-8b": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/Meta-Llama-3.1-8B-Instruct"), "dtype": "bfloat16", "attention": None, "trust_remote_code": False, "tokenizer_use_fast": None, "role": ROLE_CANONICAL_PRIMARY},
    "qwen2.5-14b": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/Qwen2.5-14B-Instruct"), "dtype": "bfloat16", "attention": None, "trust_remote_code": False, "tokenizer_use_fast": None, "role": ROLE_EXPANDED_ROBUSTNESS},
    "internlm2.5-20b": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/internlm2_5-20b-chat"), "dtype": "bfloat16", "attention": "sdpa", "trust_remote_code": True, "tokenizer_use_fast": False, "role": ROLE_EXPANDED_ROBUSTNESS},
    "qwen2.5-32b": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/Qwen2.5-32B-Instruct"), "dtype": "bfloat16", "attention": None, "trust_remote_code": False, "tokenizer_use_fast": None, "role": ROLE_EXPANDED_ROBUSTNESS},
    "llama3-42b": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/llama3-42b-v0"), "dtype": "bfloat16", "attention": None, "trust_remote_code": False, "tokenizer_use_fast": None, "role": ROLE_EXPANDED_ROBUSTNESS},
    "mixtral": {"model_path": whitebox_core.expand_placeholder("${HC_DATA_ROOT}/models/Mixtral-8x7B-v0.1"), "dtype": "float16", "attention": None, "trust_remote_code": False, "tokenizer_use_fast": None, "role": ROLE_CANONICAL_PRIMARY},
}
EVAL_MODELS = {key: value["model_path"] for key, value in EVALUATORS.items()}
EVAL_DTYPES = {key: value["dtype"] for key, value in EVALUATORS.items()}
EVAL_ROLES = {key: value["role"] for key, value in EVALUATORS.items()}
EVAL_ATTENTION = {key: value["attention"] for key, value in EVALUATORS.items()}

PAIR_SCORING_PROTOCOL = {
    "schema": SCHEMA_ID + ".uniform_pair_protocol",
    "schema_version": SCHEMA_VERSION,
    "system_prompt": whitebox_core.SYSTEM_PROMPT,
    "conditional_template": "[INST] {system_prompt}\\n{prompt} [/INST]",
    "tokenization": {
        "prompt_add_special_tokens": False,
        "response_add_special_tokens": False,
        "target": "tokenizer(response, add_special_tokens=False).input_ids + [eos_token_id]",
        "exactly_one_eos_appended": True,
    },
    "anchor_precedence": [
        "tokenizer.bos_token_id",
        "model.config.bos_token_id",
        "tokenizer.eos_token_id",
    ],
    "unconditional": {
        "sequence": "[anchor] + target",
        "mask": "labels[:, :1] = -100",
    },
    "conditional": {
        "sequence": "[anchor] + prompt_ids + target",
        "mask": "labels[:, :len(prompt_ids) + 1] = -100",
    },
    "target_event_identity": "same materialized target token list in both sequences",
    "loss_and_phi": {
        "boundary": "whitebox_core.score_prepared_inputs(model, PreparedPhiInputs)",
        "semantics_source_sha256": whitebox_core.SCORING_PROTOCOL_SHA256,
    },
    "legacy_score_phi_compatibility": "diagnostic_only_not_a_gate",
}
PAIR_PROTOCOL_SHA256 = storage.canonical_row_sha256(PAIR_SCORING_PROTOCOL)
ACTUAL_SCORING_PROTOCOL = {
    "schema": SCHEMA_ID + ".actual_protocol",
    "schema_version": SCHEMA_VERSION,
    "source": "manifest-bound snapshots/actual_levels.jsonl",
    "pair_scorer_protocol_sha256": PAIR_PROTOCOL_SHA256,
    "pair_calls": 1,
}
ACTUAL_PROTOCOL_SHA256 = storage.canonical_row_sha256(ACTUAL_SCORING_PROTOCOL)
_STRICT_PROTOCOL = {
    "schema": SCHEMA_ID + ".counterfactual_protocol",
    "schema_version": SCHEMA_VERSION,
    "source": "FINALIZED -> lineage.json -> final/source.jsonl",
    "actual_protocol_sha256": ACTUAL_PROTOCOL_SHA256,
    "pair_scorer_protocol_sha256": PAIR_PROTOCOL_SHA256,
    "actual": "exact join by semantic_key and actual_pair_sha256; no rescoring",
    "counterfactual_order": [1, 2, 3, 4, 5],
    "counterfactual_pair_calls": STRICT_CF_COUNT,
    "cf_reduction": "statistics.fmean of five ordered CF phis",
    "strict_excess": "phi_actual - cf_phi_mean",
}
STRICT_SCORING_PROTOCOL_SHA256 = storage.canonical_row_sha256(_STRICT_PROTOCOL)
PROTOCOL_SHA256 = STRICT_SCORING_PROTOCOL_SHA256

_MODEL_SUFFIXES = {".bin", ".json", ".model", ".py", ".safetensors", ".tiktoken"}
_TOKENIZER_MARKERS = ("tokenizer", "special_tokens", "added_tokens", "vocab", "merges", "sentencepiece")


class StrictWhiteboxError(RuntimeError):
    pass


class EvaluatorError(StrictWhiteboxError):
    pass


class TargetEventMismatchError(EvaluatorError):
    pass


class ScoreValidationError(StrictWhiteboxError):
    pass


def scoring_protocol() -> dict[str, Any]:
    return deepcopy(_STRICT_PROTOCOL)


def evaluator_descriptor(evaluator: str) -> dict[str, Any]:
    try:
        raw = EVALUATORS[evaluator]
    except KeyError as exc:
        raise EvaluatorError(f"unknown evaluator {evaluator!r}; expected one of {tuple(EVALUATORS)}") from exc
    return {
        "evaluator": evaluator,
        "model_path": raw["model_path"],
        "dtype": raw["dtype"],
        "attention": raw["attention"],
        "trust_remote_code": raw["trust_remote_code"],
        "tokenizer_use_fast": raw["tokenizer_use_fast"],
        "device_map": "auto",
        "role": raw["role"],
    }


def evaluator_sha256(evaluator: str) -> str:
    return storage.canonical_row_sha256(evaluator_descriptor(evaluator))


EVALUATOR_SHA256 = {key: evaluator_sha256(key) for key in EVALUATORS}


def _actual_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    projection = {key: deepcopy(row[key]) for key in strict_schema.ACTUAL_SNAPSHOT_KEYS}
    projection["row_type"] = "actual_level"
    strict_schema.validate_actual_snapshot_row(projection)
    return projection


def actual_scoring_sha256(evaluator: str, actual_row: Mapping[str, Any]) -> str:
    """Resume key independent of every counterfactual byte and protocol."""

    actual = _actual_projection(actual_row)
    return storage.canonical_row_sha256({
        "evaluator": evaluator,
        "evaluator_sha256": evaluator_sha256(evaluator),
        "semantic_key": list(actual["semantic_key"]),
        "actual_pair_sha256": actual["actual_pair_sha256"],
        "pair_scorer_protocol_sha256": PAIR_PROTOCOL_SHA256,
    })


def scoring_sha256(evaluator: str, source: Mapping[str, Any]) -> str:
    strict_schema.validate_strict_source_row(source)
    return storage.canonical_row_sha256({
        "evaluator": evaluator,
        "evaluator_sha256": evaluator_sha256(evaluator),
        "semantic_key": list(source["semantic_key"]),
        "strict_scoring_input_sha256": source["scoring_input_sha256"],
        "protocol_sha256": STRICT_SCORING_PROTOCOL_SHA256,
    })


def _inventory_kind(relative: str) -> str:
    lowered = relative.casefold()
    if any(marker in lowered for marker in _TOKENIZER_MARKERS) or Path(lowered).name.endswith((".model", ".tiktoken")):
        return "tokenizer"
    return "model"


def checkpoint_inventory(root: str | os.PathLike[str]) -> dict[str, Any]:
    """Hash model and tokenizer file bytes into separate inventories."""

    directory = Path(root)
    if not directory.is_dir():
        raise EvaluatorError(f"model directory does not exist: {directory}")
    grouped: dict[str, list[dict[str, Any]]] = {"model": [], "tokenizer": []}
    files = sorted((item for item in directory.rglob("*") if item.is_file()), key=lambda item: item.relative_to(directory).as_posix())
    for path in files:
        relative = path.relative_to(directory).as_posix()
        if path.name.endswith((".lock", ".incomplete")):
            continue
        if path.suffix.casefold() not in _MODEL_SUFFIXES and not any(marker in relative.casefold() for marker in _TOKENIZER_MARKERS):
            continue
        grouped[_inventory_kind(relative)].append({"path": relative, "size": path.stat().st_size, "sha256": storage.file_sha256(path)})
    if not grouped["model"] or not any(row["path"].endswith((".safetensors", ".bin")) for row in grouped["model"]):
        raise EvaluatorError(f"no model weight inventory under {directory}")
    if not grouped["tokenizer"]:
        raise EvaluatorError(f"no tokenizer inventory under {directory}")
    result: dict[str, Any] = {"root": str(directory)}
    for kind in ("model", "tokenizer"):
        entries = grouped[kind]
        result[f"{kind}_inventory"] = {
            "file_count": len(entries), "total_bytes": sum(row["size"] for row in entries),
            "files": entries, "inventory_sha256": storage.canonical_row_sha256(entries),
        }
    result["combined_inventory_sha256"] = storage.canonical_row_sha256({
        "model_inventory_sha256": result["model_inventory"]["inventory_sha256"],
        "tokenizer_inventory_sha256": result["tokenizer_inventory"]["inventory_sha256"],
    })
    return result


def _token_ids(value: Any, path: str) -> list[int]:
    ids = getattr(value, "input_ids", None)
    if ids is None and isinstance(value, Mapping):
        ids = value.get("input_ids")
    if hasattr(ids, "tolist"):
        ids = ids.tolist()
    if isinstance(ids, Sequence) and ids and isinstance(ids[0], Sequence):
        if len(ids) != 1:
            raise TargetEventMismatchError(f"{path} must contain one sequence")
        ids = ids[0]
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        raise TargetEventMismatchError(f"{path} exposes no token ID sequence")
    result = list(ids)
    if not result or any(type(token) is not int for token in result):
        raise TargetEventMismatchError(f"{path} token IDs must be non-empty integers")
    return result


def legacy_target_event_compatibility(
    tokenizer: Any,
    response: str = "Strict target-event identity smoke response.",
) -> dict[str, Any]:
    """Diagnose legacy ``score_phi`` target identity without gating strict runs."""

    try:
        eos_text = getattr(tokenizer, "eos_token", None)
        eos_id = getattr(tokenizer, "eos_token_id", None)
        if not isinstance(eos_text, str) or type(eos_id) is not int:
            raise ValueError("tokenizer has no scalar EOS token")
        unconditional = _token_ids(tokenizer(response + eos_text), "legacy_unconditional")
        response_ids = _token_ids(
            tokenizer(response, add_special_tokens=False), "legacy_response"
        )
        unconditional_target = unconditional[1:]
        conditional_target = response_ids + [eos_id]
        return {
            "compatible": bool(
                unconditional_target
                and unconditional_target == conditional_target
            ),
            "unconditional_target_sha256": storage.canonical_row_sha256(
                unconditional_target
            ) if unconditional_target else None,
            "conditional_target_sha256": storage.canonical_row_sha256(
                conditional_target
            ),
            "error_type": None,
        }
    except Exception as exc:
        return {
            "compatible": False,
            "unconditional_target_sha256": None,
            "conditional_target_sha256": None,
            "error_type": type(exc).__name__,
        }


def _strict_pair_token_ids(
    tokenizer: Any,
    model: Any,
    prompt: str,
    response: str,
) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise TargetEventMismatchError("prompt must be non-empty text")
    if not isinstance(response, str) or not response.strip():
        raise TargetEventMismatchError("response must be non-empty text")
    eos_id = getattr(tokenizer, "eos_token_id", None)
    if type(eos_id) is not int:
        raise TargetEventMismatchError("tokenizer must expose scalar eos_token_id")
    response_ids = _token_ids(
        tokenizer(response, add_special_tokens=False), "strict_response"
    )
    target = response_ids + [eos_id]
    tokenizer_bos = getattr(tokenizer, "bos_token_id", None)
    model_bos = getattr(getattr(model, "config", None), "bos_token_id", None)
    if type(tokenizer_bos) is int:
        anchor, anchor_source = tokenizer_bos, "tokenizer.bos_token_id"
    elif type(model_bos) is int:
        anchor, anchor_source = model_bos, "model.config.bos_token_id"
    else:
        anchor, anchor_source = eos_id, "tokenizer.eos_token_id"
    prompt_text = (
        f"[INST] {whitebox_core.SYSTEM_PROMPT}\n{prompt} [/INST]"
    )
    prompt_ids = _token_ids(
        tokenizer(prompt_text, add_special_tokens=False), "strict_prompt"
    )
    return {
        "anchor": anchor,
        "anchor_source": anchor_source,
        "prompt_ids": prompt_ids,
        "target_ids": target,
    }


def validate_target_event_identity(
    tokenizer: Any,
    model: Any,
    response: str = "Strict target-event identity smoke response.",
    prompt: str = "Strict target-event identity smoke prompt.",
) -> dict[str, Any]:
    """Attest the uniform target and retain legacy behavior as a diagnostic."""

    tokens = _strict_pair_token_ids(tokenizer, model, prompt, response)
    target = tokens["target_ids"]
    return {
        "anchor_source": tokens["anchor_source"],
        "anchor_token_id": tokens["anchor"],
        "event_token_count": len(target),
        "event_sha256": storage.canonical_row_sha256(target),
        "legacy_compatibility": legacy_target_event_compatibility(
            tokenizer, response
        ),
    }


def _model_input_device(model: Any) -> Any:
    get_embeddings = getattr(model, "get_input_embeddings", None)
    if callable(get_embeddings):
        embeddings = get_embeddings()
        parameters = getattr(embeddings, "parameters", None)
        if callable(parameters):
            try:
                return next(parameters()).device
            except StopIteration:
                pass
    device = getattr(model, "device", None)
    if device is not None:
        return device
    parameters = getattr(model, "parameters", None)
    if callable(parameters):
        try:
            return next(parameters()).device
        except StopIteration:
            pass
    raise EvaluatorError("cannot determine evaluator input device")


def prepare_strict_pair_inputs(
    tokenizer: Any,
    model: Any,
    prompt: str,
    response: str,
) -> whitebox_core.PreparedPhiInputs:
    """Build unconditional/conditional inputs with one identical target event."""

    tokens = _strict_pair_token_ids(tokenizer, model, prompt, response)
    anchor = tokens["anchor"]
    prompt_ids = tokens["prompt_ids"]
    target_ids = tokens["target_ids"]
    torch = _torch_module()
    uncond_ids = torch.tensor([[anchor] + target_ids])
    uncond_labels = uncond_ids.clone()
    uncond_labels[:, :1] = -100
    cond_ids = torch.tensor([[anchor] + prompt_ids + target_ids])
    cond_labels = cond_ids.clone()
    cond_labels[:, : len(prompt_ids) + 1] = -100
    prepared = whitebox_core.PreparedPhiInputs(
        unconditional=whitebox_core.PreparedLossInput(
            input_ids=uncond_ids, target_ids=uncond_labels
        ),
        conditional=whitebox_core.PreparedLossInput(
            input_ids=cond_ids, target_ids=cond_labels
        ),
    )
    return prepared.to(_model_input_device(model))


smoke_target_event_identity = validate_target_event_identity
tokenizer_target_event_smoke = validate_target_event_identity


def _torch_module() -> Any:
    import torch
    return torch


def _transformer_classes() -> tuple[Any, Any]:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    return AutoModelForCausalLM, AutoTokenizer


def _normalize_device_map(model: Any) -> dict[str, Any]:
    raw = getattr(model, "hf_device_map", None)
    if not isinstance(raw, Mapping) or not raw:
        raise EvaluatorError("device_map='auto' produced no auditable hf_device_map")
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        rendered: Any = value if type(value) is int else str(value)
        lowered = str(rendered).casefold()
        is_cuda = (
            (type(rendered) is int and rendered >= 0)
            or lowered == "cuda"
            or lowered.startswith("cuda:")
        )
        if not is_cuda:
            raise EvaluatorError(
                "only realized CUDA placement is permitted; "
                f"hf_device_map[{key!r}]={rendered!r}"
            )
        normalized[str(key)] = rendered
    return dict(sorted(normalized.items()))


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def scorer_code_inventory() -> dict[str, Any]:
    """Hash every source file that can change pair or wrapper score values."""

    paths = (
        ("canonical_pair_scorer", Path(whitebox_core.__file__).resolve()),
        ("strict_evaluator_wrapper", Path(__file__).resolve()),
        ("strict_runner", Path(__file__).with_name("run_strict_cf_v1.py").resolve()),
    )
    entries: list[dict[str, Any]] = []
    for role, path in paths:
        if not path.is_file():
            raise EvaluatorError(f"scorer code file is missing: {path}")
        entries.append(
            {
                "role": role,
                "path": path.name,
                "size": path.stat().st_size,
                "sha256": storage.file_sha256(path),
            }
        )
    return {
        "files": entries,
        "inventory_sha256": storage.canonical_row_sha256(entries),
    }


def _validate_file_inventory(
    value: Any,
    path: str,
    *,
    required_roles: set[str] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluatorError(f"{path} must be an object")
    expected = {"files", "inventory_sha256"}
    if required_roles is None:
        expected |= {"file_count", "total_bytes"}
    if set(value) != expected:
        raise EvaluatorError(f"{path} keys are not exact")
    files = value["files"]
    if not isinstance(files, list) or not files:
        raise EvaluatorError(f"{path}.files must be non-empty")
    roles: set[str] = set()
    for index, entry in enumerate(files):
        if not isinstance(entry, Mapping):
            raise EvaluatorError(f"{path}.files[{index}] must be an object")
        entry_keys = {"path", "size", "sha256"}
        if required_roles is not None:
            entry_keys.add("role")
        if set(entry) != entry_keys:
            raise EvaluatorError(f"{path}.files[{index}] keys are not exact")
        if not isinstance(entry["path"], str) or not entry["path"]:
            raise EvaluatorError(f"{path}.files[{index}].path is invalid")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise EvaluatorError(f"{path}.files[{index}].size is invalid")
        _digest(entry["sha256"], f"{path}.files[{index}].sha256")
        if required_roles is not None:
            role = entry["role"]
            if not isinstance(role, str) or not role:
                raise EvaluatorError(f"{path}.files[{index}].role is invalid")
            roles.add(role)
    if value["inventory_sha256"] != storage.canonical_row_sha256(files):
        raise EvaluatorError(f"{path}.inventory_sha256 mismatch")
    if required_roles is None:
        if value["file_count"] != len(files) or value["total_bytes"] != sum(entry["size"] for entry in files):
            raise EvaluatorError(f"{path} file count/size mismatch")
    elif roles != required_roles:
        raise EvaluatorError(f"{path} scorer roles mismatch")
    return value


def validate_runtime_attestation(
    value: Mapping[str, Any],
    *,
    expected_evaluator: str | None = None,
) -> Mapping[str, Any]:
    """Validate every nested runtime-provenance binding exactly."""

    if not isinstance(value, Mapping):
        raise EvaluatorError("runtime attestation must be an object")
    expected_keys = {
        "schema", "schema_version", "captured_at_utc", "evaluator",
        "evaluator_sha256", "actual_protocol_sha256", "strict_protocol_sha256",
        "pair_protocol_sha256", "inventory", "scorer_code_inventory",
        "realized_device_map", "strict_target_event_smoke", "software",
        "protobuf_python_implementation", "visible_devices", "gpu_names",
        "attestation_payload_sha256",
    }
    if set(value) != expected_keys:
        raise EvaluatorError("runtime attestation keys are not exact")
    if value["schema"] != SCHEMA_ID + ".runtime_attestation" or value["schema_version"] != SCHEMA_VERSION:
        raise EvaluatorError("runtime attestation schema mismatch")
    try:
        captured = datetime.fromisoformat(str(value["captured_at_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluatorError("runtime attestation timestamp is invalid") from exc
    if captured.tzinfo is None or captured.utcoffset() is None or captured.utcoffset().total_seconds() != 0:
        raise EvaluatorError("runtime attestation timestamp must be UTC")
    descriptor = value["evaluator"]
    if not isinstance(descriptor, Mapping):
        raise EvaluatorError("runtime attestation evaluator must be an object")
    evaluator = descriptor.get("evaluator")
    if expected_evaluator is not None and evaluator != expected_evaluator:
        raise EvaluatorError("runtime attestation evaluator mismatch")
    if descriptor != evaluator_descriptor(evaluator) or value["evaluator_sha256"] != evaluator_sha256(evaluator):
        raise EvaluatorError("runtime attestation evaluator identity mismatch")
    if (
        value["actual_protocol_sha256"] != ACTUAL_PROTOCOL_SHA256
        or value["strict_protocol_sha256"] != STRICT_SCORING_PROTOCOL_SHA256
        or value["pair_protocol_sha256"] != PAIR_PROTOCOL_SHA256
    ):
        raise EvaluatorError("runtime attestation protocol mismatch")
    inventory = value["inventory"]
    if not isinstance(inventory, Mapping) or set(inventory) != {
        "root", "model_inventory", "tokenizer_inventory", "combined_inventory_sha256"
    }:
        raise EvaluatorError("runtime checkpoint inventory keys are not exact")
    if inventory["root"] != descriptor["model_path"]:
        raise EvaluatorError("runtime checkpoint inventory root mismatch")
    _validate_file_inventory(inventory["model_inventory"], "inventory.model_inventory")
    _validate_file_inventory(inventory["tokenizer_inventory"], "inventory.tokenizer_inventory")
    expected_combined = storage.canonical_row_sha256({
        "model_inventory_sha256": inventory["model_inventory"]["inventory_sha256"],
        "tokenizer_inventory_sha256": inventory["tokenizer_inventory"]["inventory_sha256"],
    })
    if inventory["combined_inventory_sha256"] != expected_combined:
        raise EvaluatorError("runtime combined checkpoint inventory hash mismatch")
    _validate_file_inventory(
        value["scorer_code_inventory"],
        "scorer_code_inventory",
        required_roles={"canonical_pair_scorer", "strict_evaluator_wrapper", "strict_runner"},
    )
    device_map = value["realized_device_map"]
    if not isinstance(device_map, Mapping) or not device_map:
        raise EvaluatorError("runtime realized device map is invalid")
    for key, placement in device_map.items():
        rendered = placement if type(placement) is int else str(placement)
        is_cuda = (
            (type(rendered) is int and rendered >= 0)
            or str(rendered).casefold() == "cuda"
            or str(rendered).casefold().startswith("cuda:")
        )
        if not is_cuda:
            raise EvaluatorError(f"runtime device map contains non-CUDA placement {key!r}={placement!r}")
    smoke = value["strict_target_event_smoke"]
    smoke_keys = {
        "anchor_source", "anchor_token_id", "event_token_count",
        "event_sha256", "legacy_compatibility",
    }
    if not isinstance(smoke, Mapping) or set(smoke) != smoke_keys:
        raise EvaluatorError("runtime strict target-event smoke keys are not exact")
    if smoke["anchor_source"] not in {
        "tokenizer.bos_token_id", "model.config.bos_token_id",
        "tokenizer.eos_token_id",
    } or type(smoke["anchor_token_id"]) is not int:
        raise EvaluatorError("runtime strict target-event anchor is invalid")
    if type(smoke["event_token_count"]) is not int or smoke["event_token_count"] <= 0:
        raise EvaluatorError("runtime strict target-event token count is invalid")
    _digest(smoke["event_sha256"], "strict_target_event_smoke.event_sha256")
    legacy = smoke["legacy_compatibility"]
    legacy_keys = {
        "compatible", "unconditional_target_sha256",
        "conditional_target_sha256", "error_type",
    }
    if not isinstance(legacy, Mapping) or set(legacy) != legacy_keys or type(legacy["compatible"]) is not bool:
        raise EvaluatorError("runtime legacy compatibility diagnostic is invalid")
    for field in ("unconditional_target_sha256", "conditional_target_sha256"):
        if legacy[field] is not None:
            _digest(legacy[field], f"legacy_compatibility.{field}")
    if legacy["error_type"] is not None and not isinstance(legacy["error_type"], str):
        raise EvaluatorError("runtime legacy diagnostic error_type is invalid")
    protobuf_implementation = value["protobuf_python_implementation"]
    if protobuf_implementation is not None and not isinstance(protobuf_implementation, str):
        raise EvaluatorError("runtime protobuf implementation must be text or null")
    if evaluator == "internlm2.5-20b" and protobuf_implementation != "python":
        raise EvaluatorError("InternLM runtime must attest Python protobuf implementation")
    software = value["software"]
    software_keys = {"python", "platform", "torch", "transformers", "accelerate", "tokenizers", "sentencepiece", "cuda"}
    if not isinstance(software, Mapping) or set(software) != software_keys:
        raise EvaluatorError("runtime software keys are not exact")
    if not isinstance(software["python"], str) or not isinstance(software["platform"], str):
        raise EvaluatorError("runtime Python/platform provenance is invalid")
    if value["visible_devices"] is not None and not isinstance(value["visible_devices"], str):
        raise EvaluatorError("runtime visible_devices must be text or null")
    if not isinstance(value["gpu_names"], list) or not value["gpu_names"] or not all(isinstance(name, str) and name for name in value["gpu_names"]):
        raise EvaluatorError("runtime GPU names must be a non-empty text list")
    stored = _digest(value["attestation_payload_sha256"], "attestation_payload_sha256")
    payload = dict(value)
    payload.pop("attestation_payload_sha256")
    if stored != storage.canonical_row_sha256(payload):
        raise EvaluatorError("runtime attestation payload hash mismatch")
    return value


def build_runtime_attestation(evaluator: str, model: Any, inventory: Mapping[str, Any], *, target_event_smoke: Mapping[str, Any], torch_module: Any | None = None) -> dict[str, Any]:
    torch = torch_module if torch_module is not None else _torch_module()
    cuda = getattr(torch, "cuda", None)
    count = int(cuda.device_count()) if cuda is not None else 0
    payload = {
        "schema": SCHEMA_ID + ".runtime_attestation", "schema_version": SCHEMA_VERSION,
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evaluator": evaluator_descriptor(evaluator), "evaluator_sha256": evaluator_sha256(evaluator),
        "actual_protocol_sha256": ACTUAL_PROTOCOL_SHA256,
        "strict_protocol_sha256": STRICT_SCORING_PROTOCOL_SHA256,
        "pair_protocol_sha256": PAIR_PROTOCOL_SHA256,
        "inventory": deepcopy(dict(inventory)),
        "scorer_code_inventory": scorer_code_inventory(),
        "realized_device_map": _normalize_device_map(model),
        "strict_target_event_smoke": dict(target_event_smoke),
        "protobuf_python_implementation": os.environ.get(
            "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"
        ),
        "software": {
            "python": sys.version, "platform": platform.platform(),
            "torch": _package_version("torch"), "transformers": _package_version("transformers"),
            "accelerate": _package_version("accelerate"), "tokenizers": _package_version("tokenizers"),
            "sentencepiece": _package_version("sentencepiece"),
            "cuda": getattr(getattr(torch, "version", None), "cuda", None),
        },
        "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "gpu_names": [cuda.get_device_name(index) for index in range(count)] if cuda is not None else [],
    }
    payload["attestation_payload_sha256"] = storage.canonical_row_sha256(payload)
    validate_runtime_attestation(payload, expected_evaluator=evaluator)
    return payload


def load_evaluator(evaluator: str, *, inventory: Mapping[str, Any] | None = None) -> tuple[Any, Any, dict[str, Any]]:
    descriptor = evaluator_descriptor(evaluator)
    checkpoint = checkpoint_inventory(descriptor["model_path"]) if inventory is None else deepcopy(dict(inventory))
    if evaluator == "internlm2.5-20b":
        # InternLM's slow tokenizer avoids the protobuf descriptor failure.  The
        # implementation selector must be set before transformers is imported.
        os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
    torch = _torch_module()
    auto_model, auto_tokenizer = _transformer_classes()
    try:
        dtype = getattr(torch, descriptor["dtype"])
    except AttributeError as exc:
        raise EvaluatorError(f"torch lacks dtype {descriptor['dtype']!r}") from exc
    model_kwargs: dict[str, Any] = {"dtype": dtype, "device_map": "auto"}
    tokenizer_kwargs: dict[str, Any] = {}
    if descriptor["attention"] is not None:
        model_kwargs["attn_implementation"] = descriptor["attention"]
    if descriptor["trust_remote_code"]:
        model_kwargs["trust_remote_code"] = True
        tokenizer_kwargs["trust_remote_code"] = True
    if descriptor["tokenizer_use_fast"] is not None:
        tokenizer_kwargs["use_fast"] = descriptor["tokenizer_use_fast"]
    model = auto_model.from_pretrained(descriptor["model_path"], **model_kwargs)
    model.eval()
    _normalize_device_map(model)
    tokenizer = auto_tokenizer.from_pretrained(descriptor["model_path"], **tokenizer_kwargs)
    smoke = validate_target_event_identity(tokenizer, model)
    return model, tokenizer, build_runtime_attestation(evaluator, model, checkpoint, target_event_smoke=smoke, torch_module=torch)


def _finite(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ScoreValidationError(f"{path} must be a finite non-boolean number")
    return value


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ScoreValidationError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _source_identity(source: Mapping[str, Any]) -> dict[str, Any]:
    return {field: deepcopy(source[field]) for field in IDENTITY_FIELDS}


def _actual_arithmetic_sha256(nll1: int | float, nll2: int | float, phi: int | float) -> str:
    return storage.canonical_row_sha256({"formula": "(nll1 - nll2) / nll1 if nll1 > 0 else 0.0", "nll1": nll1, "nll2": nll2, "phi_actual": phi})


def arithmetic_sha256(nll1: int | float, nll2: int | float, phi_actual: int | float, cf_phis: Sequence[int | float], cf_phi_mean: int | float, strict_excess: int | float) -> str:
    return storage.canonical_row_sha256({
        "actual": {"nll1": nll1, "nll2": nll2, "phi_actual": phi_actual},
        "cf_phis": list(cf_phis), "cf_reduction": "statistics.fmean",
        "cf_phi_mean": cf_phi_mean, "strict_excess": strict_excess,
    })


def _score_pair(tokenizer: Any, model: Any, prompt: str, output: str) -> dict[str, int | float]:
    prepared = prepare_strict_pair_inputs(tokenizer, model, prompt, output)
    value = whitebox_core.score_prepared_inputs(model, prepared)
    if not isinstance(value, Mapping):
        raise ScoreValidationError("prepared pair scorer returned a non-object")
    nll1, nll2, phi = _finite(value.get("nll1"), "pair.nll1"), _finite(value.get("nll2"), "pair.nll2"), _finite(value.get("phi"), "pair.phi")
    expected = (nll1 - nll2) / nll1 if nll1 > 0 else 0.0
    if phi != expected:
        raise ScoreValidationError("prepared pair scorer returned inconsistent phi arithmetic")
    return {"nll1": nll1, "nll2": nll2, "phi": phi}


def build_actual_phase_row(actual_source: Mapping[str, Any], *, evaluator: str, runtime_attestation_sha256: str, pair_score: Mapping[str, Any]) -> dict[str, Any]:
    actual = _actual_projection(actual_source)
    nll1, nll2, phi = _finite(pair_score.get("nll1"), "pair.nll1"), _finite(pair_score.get("nll2"), "pair.nll2"), _finite(pair_score.get("phi"), "pair.phi")
    if phi != ((nll1 - nll2) / nll1 if nll1 > 0 else 0.0):
        raise ScoreValidationError("actual phi does not exactly match NLL arithmetic")
    row = {
        "schema": SCHEMA_ID + ".actual_phase", "schema_version": SCHEMA_VERSION,
        "row_type": "strict_cf_whitebox_actual", "evaluator": evaluator,
        "evaluator_role": evaluator_descriptor(evaluator)["role"],
        "evaluator_sha256": evaluator_sha256(evaluator), **_source_identity(actual),
        "actual_snapshot_row_sha256": storage.canonical_row_sha256(actual),
        "actual_pair_sha256": actual["actual_pair_sha256"],
        "pair_scorer_protocol_sha256": PAIR_PROTOCOL_SHA256,
        "actual_protocol_sha256": ACTUAL_PROTOCOL_SHA256,
        "actual_scoring_sha256": actual_scoring_sha256(evaluator, actual),
        "runtime_attestation_sha256": _digest(runtime_attestation_sha256, "runtime_attestation_sha256"),
        "nll1": nll1, "nll2": nll2, "phi_actual": phi,
        "actual_arithmetic_sha256": _actual_arithmetic_sha256(nll1, nll2, phi),
    }
    validate_actual_phase_row(row, actual_source=actual, expected_evaluator=evaluator)
    return row


def validate_actual_phase_row(row: Mapping[str, Any], *, actual_source: Mapping[str, Any], expected_evaluator: str, expected_attestation_sha256: str | None = None) -> Mapping[str, Any]:
    expected_keys = {
        "schema", "schema_version", "row_type", "evaluator", "evaluator_role", "evaluator_sha256",
        *IDENTITY_FIELDS, "actual_snapshot_row_sha256", "actual_pair_sha256",
        "pair_scorer_protocol_sha256", "actual_protocol_sha256", "actual_scoring_sha256",
        "runtime_attestation_sha256", "nll1", "nll2", "phi_actual", "actual_arithmetic_sha256",
    }
    if not isinstance(row, Mapping) or set(row) != expected_keys:
        raise ScoreValidationError("actual phase keys are not exact")
    actual = _actual_projection(actual_source)
    if row["schema"] != SCHEMA_ID + ".actual_phase" or row["schema_version"] != SCHEMA_VERSION or row["row_type"] != "strict_cf_whitebox_actual":
        raise ScoreValidationError("actual phase schema mismatch")
    descriptor = evaluator_descriptor(expected_evaluator)
    if row["evaluator"] != expected_evaluator or row["evaluator_role"] != descriptor["role"] or row["evaluator_sha256"] != evaluator_sha256(expected_evaluator):
        raise ScoreValidationError("actual phase evaluator identity mismatch")
    for field in IDENTITY_FIELDS:
        if row[field] != actual[field]:
            raise ScoreValidationError(f"actual phase {field} differs from snapshot")
    if row["actual_snapshot_row_sha256"] != storage.canonical_row_sha256(actual) or row["actual_pair_sha256"] != actual["actual_pair_sha256"]:
        raise ScoreValidationError("actual snapshot/pair hash mismatch")
    if (
        row["pair_scorer_protocol_sha256"] != PAIR_PROTOCOL_SHA256
        or row["actual_protocol_sha256"] != ACTUAL_PROTOCOL_SHA256
    ):
        raise ScoreValidationError("actual phase protocol hash mismatch")
    if row["actual_scoring_sha256"] != actual_scoring_sha256(expected_evaluator, actual):
        raise ScoreValidationError("actual phase resume key mismatch")
    attestation = _digest(row["runtime_attestation_sha256"], "runtime_attestation_sha256")
    if expected_attestation_sha256 is not None and attestation != expected_attestation_sha256:
        raise ScoreValidationError("actual phase runtime attestation mismatch")
    nll1, nll2, phi = _finite(row["nll1"], "actual.nll1"), _finite(row["nll2"], "actual.nll2"), _finite(row["phi_actual"], "actual.phi_actual")
    if phi != ((nll1 - nll2) / nll1 if nll1 > 0 else 0.0) or row["actual_arithmetic_sha256"] != _actual_arithmetic_sha256(nll1, nll2, phi):
        raise ScoreValidationError("actual phase arithmetic/hash mismatch")
    return row


def build_score_row(source: Mapping[str, Any], *, evaluator: str, actual_phase: Mapping[str, Any], cf_phis: Sequence[int | float]) -> dict[str, Any]:
    strict_schema.validate_strict_source_row(source)
    validate_actual_phase_row(actual_phase, actual_source=source, expected_evaluator=evaluator)
    if isinstance(cf_phis, (str, bytes)) or len(cf_phis) != STRICT_CF_COUNT:
        raise ScoreValidationError(f"cf_phis must contain exactly {STRICT_CF_COUNT} values")
    values = [_finite(value, f"cf_phis[{index}]") for index, value in enumerate(cf_phis)]
    mean = statistics.fmean(values)
    excess = actual_phase["phi_actual"] - mean
    row = {
        "schema": SCHEMA_ID + ".score", "schema_version": SCHEMA_VERSION,
        "row_type": "strict_cf_whitebox_score", "evaluator": evaluator,
        "evaluator_role": evaluator_descriptor(evaluator)["role"], "evaluator_sha256": evaluator_sha256(evaluator),
        **_source_identity(source), "source_row_sha256": storage.canonical_row_sha256(source),
        "actual_snapshot_row_sha256": actual_phase["actual_snapshot_row_sha256"],
        "actual_pair_sha256": actual_phase["actual_pair_sha256"],
        "actual_scoring_sha256": actual_phase["actual_scoring_sha256"],
        "input_sha256": source["scoring_input_sha256"], "scoring_input_sha256": source["scoring_input_sha256"],
        "protocol_sha256": STRICT_SCORING_PROTOCOL_SHA256, "scoring_sha256": scoring_sha256(evaluator, source),
        "runtime_attestation_sha256": actual_phase["runtime_attestation_sha256"],
        "nll1": actual_phase["nll1"], "nll2": actual_phase["nll2"], "phi_actual": actual_phase["phi_actual"],
        "cf_phis": values, "cf_phi_mean": mean, "strict_excess": excess,
        "arithmetic_sha256": arithmetic_sha256(actual_phase["nll1"], actual_phase["nll2"], actual_phase["phi_actual"], values, mean, excess),
    }
    validate_score_row(row, source=source, actual_phase=actual_phase, expected_evaluator=evaluator)
    return row


def validate_score_row(row: Mapping[str, Any], *, source: Mapping[str, Any], actual_phase: Mapping[str, Any], expected_evaluator: str, expected_attestation_sha256: str | None = None) -> Mapping[str, Any]:
    expected_keys = {
        "schema", "schema_version", "row_type", "evaluator", "evaluator_role", "evaluator_sha256", *IDENTITY_FIELDS,
        "source_row_sha256", "actual_snapshot_row_sha256", "actual_pair_sha256", "actual_scoring_sha256",
        "input_sha256", "scoring_input_sha256", "protocol_sha256", "scoring_sha256", "runtime_attestation_sha256",
        "nll1", "nll2", "phi_actual", "cf_phis", "cf_phi_mean", "strict_excess", "arithmetic_sha256",
    }
    if not isinstance(row, Mapping) or set(row) != expected_keys:
        raise ScoreValidationError("score row keys are not exact")
    strict_schema.validate_strict_source_row(source)
    validate_actual_phase_row(actual_phase, actual_source=source, expected_evaluator=expected_evaluator, expected_attestation_sha256=expected_attestation_sha256)
    if row["schema"] != SCHEMA_ID + ".score" or row["schema_version"] != SCHEMA_VERSION or row["row_type"] != "strict_cf_whitebox_score":
        raise ScoreValidationError("score row schema mismatch")
    if row["evaluator"] != expected_evaluator or row["evaluator_role"] != evaluator_descriptor(expected_evaluator)["role"] or row["evaluator_sha256"] != evaluator_sha256(expected_evaluator):
        raise ScoreValidationError("score evaluator identity mismatch")
    for field in IDENTITY_FIELDS:
        if row[field] != source[field]:
            raise ScoreValidationError(f"score {field} differs from strict source")
    if row["source_row_sha256"] != storage.canonical_row_sha256(source):
        raise ScoreValidationError("score source hash mismatch")
    for field in ("actual_snapshot_row_sha256", "actual_pair_sha256", "actual_scoring_sha256", "runtime_attestation_sha256", "nll1", "nll2", "phi_actual"):
        if row[field] != actual_phase[field]:
            raise ScoreValidationError(f"score/actual join mismatch in {field}")
    input_hash = source["scoring_input_sha256"]
    if row["input_sha256"] != input_hash or row["scoring_input_sha256"] != input_hash:
        raise ScoreValidationError("score strict input hash mismatch")
    if row["protocol_sha256"] != STRICT_SCORING_PROTOCOL_SHA256 or row["scoring_sha256"] != scoring_sha256(expected_evaluator, source):
        raise ScoreValidationError("score protocol/resume hash mismatch")
    cf_phis = row["cf_phis"]
    if not isinstance(cf_phis, list) or len(cf_phis) != STRICT_CF_COUNT:
        raise ScoreValidationError(f"score requires exactly {STRICT_CF_COUNT} CF phis")
    values = [_finite(value, f"score.cf_phis[{index}]") for index, value in enumerate(cf_phis)]
    mean = _finite(row["cf_phi_mean"], "score.cf_phi_mean")
    excess = _finite(row["strict_excess"], "score.strict_excess")
    if mean != statistics.fmean(values) or excess != row["phi_actual"] - mean:
        raise ScoreValidationError("score mean/excess arithmetic mismatch")
    if row["arithmetic_sha256"] != arithmetic_sha256(row["nll1"], row["nll2"], row["phi_actual"], values, mean, excess):
        raise ScoreValidationError("score arithmetic hash mismatch")
    return row


def score_actual_phase(actual_source: Mapping[str, Any], *, evaluator: str, tokenizer: Any, model: Any, runtime_attestation_sha256: str) -> dict[str, Any]:
    actual = _actual_projection(actual_source)
    pair = _score_pair(tokenizer, model, actual["actual"]["prompt"], actual["actual"]["output"])
    return build_actual_phase_row(actual, evaluator=evaluator, runtime_attestation_sha256=runtime_attestation_sha256, pair_score=pair)


def score_counterfactual_phase(source: Mapping[str, Any], *, evaluator: str, tokenizer: Any, model: Any, actual_phase: Mapping[str, Any]) -> dict[str, Any]:
    strict_schema.validate_strict_source_row(source)
    validate_actual_phase_row(actual_phase, actual_source=source, expected_evaluator=evaluator)
    counterfactuals = source["counterfactuals"]
    if not isinstance(counterfactuals, list) or len(counterfactuals) != STRICT_CF_COUNT:
        raise ScoreValidationError("strict source must contain exactly five CF pairs")
    phis: list[int | float] = []
    for index, counterfactual in enumerate(counterfactuals, start=1):
        if counterfactual.get("index") != index:
            raise ScoreValidationError("strict CF indexes must be one-based and positional")
        phis.append(_score_pair(tokenizer, model, counterfactual["prompt"], counterfactual["output"])["phi"])
    return build_score_row(source, evaluator=evaluator, actual_phase=actual_phase, cf_phis=phis)


def score_source_row(source: Mapping[str, Any], *, evaluator: str, tokenizer: Any, model: Any, runtime_attestation_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Test/operator helper: a fresh finalized row makes exactly six pair calls."""
    actual = score_actual_phase(source, evaluator=evaluator, tokenizer=tokenizer, model=model, runtime_attestation_sha256=runtime_attestation_sha256)
    return actual, score_counterfactual_phase(source, evaluator=evaluator, tokenizer=tokenizer, model=model, actual_phase=actual)


__all__ = [
    "ACTUAL_PROTOCOL_SHA256", "ACTUAL_SCORING_PROTOCOL", "EVALUATORS", "EVALUATOR_SHA256",
    "EVAL_ATTENTION", "EVAL_DTYPES", "EVAL_MODELS", "EVAL_ROLES", "EXPECTED_LEVEL_ROWS",
    "EvaluatorError", "IDENTITY_FIELDS", "PROTOCOL_SHA256", "ROLE_CANONICAL_PRIMARY",
    "ROLE_EXPANDED_ROBUSTNESS", "SCHEMA_ID", "SCHEMA_VERSION", "STRICT_CF_COUNT",
    "STRICT_SCORING_PROTOCOL_SHA256", "ScoreValidationError", "StrictWhiteboxError",
    "TargetEventMismatchError", "actual_scoring_sha256", "arithmetic_sha256",
    "build_actual_phase_row", "build_runtime_attestation", "build_score_row", "checkpoint_inventory",
    "evaluator_descriptor", "evaluator_sha256", "load_evaluator", "score_actual_phase",
    "score_counterfactual_phase", "score_source_row", "scorer_code_inventory", "scoring_protocol", "scoring_sha256",
    "smoke_target_event_identity", "tokenizer_target_event_smoke", "validate_actual_phase_row",
    "validate_runtime_attestation", "validate_score_row", "validate_target_event_identity",
]
