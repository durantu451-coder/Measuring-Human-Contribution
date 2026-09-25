# -*- coding: utf-8 -*-
"""Canonical white-box phi scorer for the baseline experiment.

This module deliberately preserves the evaluator and scoring semantics of
``experiment_baseline.batch_phi``.  Imports of torch and transformers are lazy so
schema tooling and CPU-only migration code can import this module without loading
an evaluator (or even requiring transformers to be installed).

Two scoring boundaries are public:

``compute_phi`` / ``score_phi``
    The accepted end-to-end path.  It includes tokenization, tensor construction,
    device transfer, two model calls, and the final arithmetic.

``prepare_phi_inputs`` + ``score_prepared_inputs``
    The timing path.  Preparation (including transfer to the requested device) is
    completed first, so the latter function measures only two forward/loss calls
    and the final arithmetic.
"""

from __future__ import annotations

import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from experiment_b.storage import canonical_row_sha256


LEVELS = ("L1", "L2", "L3", "L4", "L5")
SYSTEM_PROMPT = "You are a helpful assistant."

# Local storage roots are written as placeholders so no author machine path is
# published.  The canonical form is what gets fingerprinted; the expanded form is
# what gets loaded from disk.  Keeping them separate means a reviewer's own
# HC_DATA_ROOT does not change any recorded evaluator hash.
def _root(name: str, default_suffix: str) -> str:
    return os.environ.get(name) or str(Path.home() / default_suffix)


# The interpreter's own layout is the only reliable source for the environment
# and executable tokens: a reviewer running this module has a working interpreter
# but no reason to have exported where it lives.
def _env_root() -> str:
    explicit = os.environ.get("HC_ENV")
    if explicit:
        return explicit
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix:
        return prefix
    # sys.prefix is the environment root that is running us, which is what the
    # recorded runtime paths were relative to.
    return sys.prefix


PLACEHOLDERS = {
    "HC_DATA_ROOT": _root("HC_DATA_ROOT", "hc_data"),
    "HC_HOME": _root("HC_HOME", "hc_home"),
    "HC_ENV": _env_root(),
    "HC_PYTHON": os.environ.get("HC_PYTHON") or sys.executable,
}


def expand_placeholder(value: str) -> str:
    """Resolve every ``${HC_*}`` token in a configured path.

    Unknown tokens are left untouched so a typo is visible rather than silently
    becoming a relative path.
    """

    for name, replacement in PLACEHOLDERS.items():
        value = value.replace("${%s}" % name, replacement)
    return value


def canonical_path(value: str) -> str:
    """The machine-independent form of a configured path, for fingerprinting.

    Collapses whichever storage root the current environment supplied back to a
    fixed token, so the resulting digest identifies the evaluator and not the
    reviewer's disk layout.
    """

    for name in PLACEHOLDERS:
        resolved = PLACEHOLDERS[name]
        if resolved:
            value = value.replace(resolved, "<%s>" % name)
    return value


def evaluator_spec(model_key: str) -> dict[str, str]:
    """Alias of :func:`evaluator_descriptor` for callers that want the name."""

    return evaluator_descriptor(model_key)


# These paths and dtypes are intentionally frozen to the current batch_phi.py
# evaluator setup.  They are adapted surrogate evaluators, not interchangeable
# checkpoints that callers may silently replace.
EVAL_MODELS: dict[str, str] = {
    "mixtral": expand_placeholder("${HC_DATA_ROOT}/models/Mixtral-8x7B-v0.1"),
    "llama": expand_placeholder("${HC_DATA_ROOT}/models/Meta-Llama-3.1-8B-Instruct"),
}
EVAL_DTYPES: dict[str, str] = {
    "mixtral": "float16",
    "llama": "bfloat16",
}

# A machine-readable statement of every scoring choice that can change a value.
# Text descriptions are intentional: they fingerprint calls whose exact behavior
# is delegated to the tokenizer/model APIs rather than reimplementing that logic.
_SCORING_PROTOCOL: dict[str, Any] = {
    "schema_version": 2,
    "name": "experiment_baseline.batch_phi",
    "batch_size": 1,
    "system_prompt": SYSTEM_PROMPT,
    "conditional_template": "[INST] {system_prompt}\n{prompt} [/INST]",
    "unconditional": {
        "text": "response + tokenizer.eos_token",
        "tokenizer_add_special_tokens": "default",
        "sequence": "tokenizer(text).input_ids",
        "mask": "target_ids[:, :1] = -100",
    },
    "conditional": {
        "prompt_add_special_tokens": False,
        "response_add_special_tokens": False,
        "sequence": [
            "tokenizer.bos_token_id",
            "prompt_ids",
            "response_ids",
            "tokenizer.eos_token_id",
        ],
        "mask": "target_ids[:, :len(prompt_ids) + 1] = -100",
    },
    "loss": {
        "call": "model(input_ids, labels=target_ids).loss.item()",
        "reduction": "model causal-LM default mean",
        "gradients": False,
    },
    "phi": "(nll1 - nll2) / nll1 if nll1 > 0 else 0.0",
    "counterfactual_baseline": {
        "selection": "manifest valid_cf_indices in ascending original order",
        "reduction": "statistics.fmean(valid_cf_phis)",
        "excess": "phi_actual - cf_phi_mean",
    },
}


def scoring_protocol() -> dict[str, Any]:
    """Return a detached copy of the frozen scorer protocol description."""

    return deepcopy(_SCORING_PROTOCOL)


SCORING_PROTOCOL_SHA256 = canonical_row_sha256(_SCORING_PROTOCOL)
# Descriptive aliases used by migration/analysis code.
PROTOCOL_SHA256 = SCORING_PROTOCOL_SHA256


def evaluator_descriptor(model_key: str) -> dict[str, str]:
    """Return the canonical identity of one supported evaluator.

    The descriptor is machine-independent: it names the checkpoint under a fixed
    storage token rather than the local path, so this fingerprint is stable
    across environments and is what the frozen records bind to.
    """

    if model_key not in EVAL_MODELS:
        choices = ", ".join(sorted(EVAL_MODELS))
        raise ValueError(f"unknown evaluator {model_key!r}; expected one of: {choices}")
    return {
        "evaluator": model_key,
        "model_path": canonical_path(EVAL_MODELS[model_key]),
        "dtype": EVAL_DTYPES[model_key],
    }


def evaluator_sha256(model_key: str) -> str:
    """Fingerprint an evaluator key, canonical model path, and exact load dtype."""

    return canonical_row_sha256(evaluator_descriptor(model_key))


EVALUATOR_SHA256: Mapping[str, str] = {
    key: evaluator_sha256(key) for key in EVAL_MODELS
}


@dataclass(frozen=True)
class PreparedLossInput:
    """One already-materialized model input and its masked labels."""

    input_ids: Any
    target_ids: Any

    @property
    def labels(self) -> Any:
        """The name used by the causal-LM call."""

        return self.target_ids

    def to(self, device: Any) -> "PreparedLossInput":
        """Return this pair transferred to ``device``."""

        return PreparedLossInput(
            input_ids=self.input_ids.to(device),
            target_ids=self.target_ids.to(device),
        )


@dataclass(frozen=True)
class PreparedPhiInputs:
    """Unconditional and conditional inputs for one prompt/response pair."""

    unconditional: PreparedLossInput
    conditional: PreparedLossInput

    def to(self, device: Any) -> "PreparedPhiInputs":
        """Return both input pairs transferred to ``device``."""

        return PreparedPhiInputs(
            unconditional=self.unconditional.to(device),
            conditional=self.conditional.to(device),
        )

    # Flat aliases make the timing boundary convenient without introducing a
    # second representation.
    @property
    def uncond_input_ids(self) -> Any:
        return self.unconditional.input_ids

    @property
    def uncond_target_ids(self) -> Any:
        return self.unconditional.target_ids

    @property
    def cond_input_ids(self) -> Any:
        return self.conditional.input_ids

    @property
    def cond_target_ids(self) -> Any:
        return self.conditional.target_ids


def _torch_module() -> Any:
    import torch

    return torch


def _transformer_classes() -> tuple[Any, Any]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    return AutoModelForCausalLM, AutoTokenizer


def load_model(model_key: str) -> tuple[Any, Any, Any]:
    """Load one frozen evaluator exactly as ``batch_phi.py`` currently does."""

    descriptor = evaluator_descriptor(model_key)  # validates before imports/work
    torch = _torch_module()
    auto_model, auto_tokenizer = _transformer_classes()
    dtype = torch.float16 if model_key == "mixtral" else torch.bfloat16
    model = auto_model.from_pretrained(
        descriptor["model_path"],
        dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    tokenizer = auto_tokenizer.from_pretrained(
        descriptor["model_path"], trust_remote_code=True
    )
    return model, tokenizer, dtype


def _prepare_unconditional(tokenizer: Any, response: str) -> PreparedLossInput:
    """Materialize the legacy response-alone sequence and labels on CPU."""

    torch = _torch_module()
    text = response + tokenizer.eos_token
    ids = tokenizer(text).input_ids
    input_ids = torch.tensor([ids])
    target_ids = input_ids.clone()
    target_ids[:, :1] = -100
    return PreparedLossInput(input_ids=input_ids, target_ids=target_ids)


def _prepare_conditional(
    tokenizer: Any, prompt: str, response: str
) -> PreparedLossInput:
    """Materialize the legacy ``[INST]`` sequence and labels on CPU."""

    torch = _torch_module()
    prompt_str = f"[INST] {SYSTEM_PROMPT}\n{prompt} [/INST]"
    prompt_ids = tokenizer(prompt_str, add_special_tokens=False).input_ids
    response_ids = tokenizer(response, add_special_tokens=False).input_ids
    ids = (
        [tokenizer.bos_token_id]
        + prompt_ids
        + response_ids
        + [tokenizer.eos_token_id]
    )
    input_ids = torch.tensor([ids])
    target_ids = input_ids.clone()
    target_ids[:, : len(prompt_ids) + 1] = -100
    return PreparedLossInput(input_ids=input_ids, target_ids=target_ids)


def prepare_phi_inputs(
    tokenizer: Any,
    prompt: str,
    response: str,
    *,
    device: Any | None = None,
) -> PreparedPhiInputs:
    """Tokenize and mask a pair, optionally transferring it before timing.

    Passing ``device=model.device`` creates the accepted device-ready input for
    :func:`score_prepared_inputs`.  Omitting it leaves ordinary CPU tensors.
    """

    prepared = PreparedPhiInputs(
        unconditional=_prepare_unconditional(tokenizer, response),
        conditional=_prepare_conditional(tokenizer, prompt, response),
    )
    return prepared if device is None else prepared.to(device)


def _score_loss(model: Any, prepared: PreparedLossInput) -> float:
    out = model(prepared.input_ids, labels=prepared.target_ids)
    return out.loss.item()


def _phi_result(nll1: float, nll2: float) -> dict[str, float]:
    return {
        "nll1": nll1,
        "nll2": nll2,
        "phi": (nll1 - nll2) / nll1 if nll1 > 0 else 0.0,
    }


def score_prepared_inputs(
    model: Any, prepared: PreparedPhiInputs
) -> dict[str, float]:
    """Run the two losses and φ arithmetic on already-device-ready inputs."""

    if not isinstance(prepared, PreparedPhiInputs):
        raise TypeError("prepared must be PreparedPhiInputs")
    torch = _torch_module()
    with torch.no_grad():
        nll1 = _score_loss(model, prepared.unconditional)
        nll2 = _score_loss(model, prepared.conditional)
    return _phi_result(nll1, nll2)


def nll_uncond(tokenizer: Any, model: Any, response: str) -> float:
    """I(y): legacy mean NLL of the response alone."""

    prepared = _prepare_unconditional(tokenizer, response).to(model.device)
    torch = _torch_module()
    with torch.no_grad():
        return _score_loss(model, prepared)


def nll_cond(tokenizer: Any, model: Any, prompt: str, response: str) -> float:
    """I(y|x): legacy mean NLL of the response after the ``[INST]`` prompt."""

    prepared = _prepare_conditional(tokenizer, prompt, response).to(model.device)
    torch = _torch_module()
    with torch.no_grad():
        return _score_loss(model, prepared)


def compute_phi(
    tokenizer: Any, model: Any, prompt: str, response: str
) -> dict[str, float]:
    """Accepted end-to-end scorer, preserving ``batch_phi.py`` call order."""

    nll1 = nll_uncond(tokenizer, model, response)
    nll2 = nll_cond(tokenizer, model, prompt, response)
    return _phi_result(nll1, nll2)


# Stable descriptive aliases for callers and benchmarks.
score_phi = compute_phi
prepare_inputs = prepare_phi_inputs
score_prepared = score_prepared_inputs
protocol_fingerprint = lambda: SCORING_PROTOCOL_SHA256


__all__ = [
    "EVALUATOR_SHA256",
    "EVAL_DTYPES",
    "EVAL_MODELS",
    "LEVELS",
    "PROTOCOL_SHA256",
    "PreparedLossInput",
    "PreparedPhiInputs",
    "SCORING_PROTOCOL_SHA256",
    "SYSTEM_PROMPT",
    "compute_phi",
    "evaluator_descriptor",
    "evaluator_sha256",
    "load_model",
    "nll_cond",
    "nll_uncond",
    "prepare_inputs",
    "prepare_phi_inputs",
    "protocol_fingerprint",
    "score_phi",
    "score_prepared",
    "score_prepared_inputs",
    "scoring_protocol",
]
