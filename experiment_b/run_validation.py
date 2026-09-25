# -*- coding: utf-8 -*-
"""Experiment B — Step 4: multi-model external-validity validation.

Experiment A constructs a natural information gradient (5 rephrasings of one
text); Experiment B instead stratifies *real* prompts by their measured human
contribution (excess_ratio, computed with claude-opus-4-7) into L1 (highest)
… L5 (lowest).  This script runs the same 5 mainline models over the stratified
items and computes each model's own excess_ratio + per-compressor breakdown, so
that compute_validation_metrics.py can test whether the other models reproduce
the gradient (Spearman's ρ) and whether the 3 compressors agree (Krippendorff's
α) — the identical reliability framework used by Experiment A.

For each stratified item, per model:
  1. generate an output for the real human prompt
  2. reconstruct 5 counterfactual prompts (reverse prompt engineering)
  3. generate 5 counterfactual outputs
  4. excess_ratio = actual_ratio - baseline_mean (aggregate + zlib/bz2/lzma)

Usage::

    # One model, all three datasets (resume-safe)
    python -X utf8 experiment_b/run_validation.py \
        --model claude-sonnet-5

    # One dataset / a small slice (smoke test)
    ... --model gpt-5.6-sol --dataset 10k_prompts
    ... --model claude-sonnet-5 --limit 20

Errors avoided (from Experiment A):
  - ``_gen`` raises on API failure / invalid output → the item is SKIPPED and
    retried on resume; an error string is never saved as data.
  - ``per_compressor`` is saved for every item (required for Krippendorff's α).
  - ``PYTHONIOENCODING=utf-8`` on Windows (GBK crash guard).
  - resume-safe: already-completed IDs are read back from the JSONL.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import time
from pathlib import Path

# ── Fix Windows encoding ────────────────────────────────────────────────────
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation):
        pass

# Ensure project root is on path for human_contribution imports
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import (
    append_jsonl_row,
    atomic_replace_bytes,
    create_verified_backup,
    scan_jsonl,
    scope_lock,
)
from experiment_b.validation_schema import (
    LineageManifest,
    ValidationSchemaError,
    canonical_protocol,
    load_active_lineage_manifest,
    validate_validation_row,
)
from human_contribution.multi_model_adapter import MultiModelAdapter
from human_contribution.copilot_global_slots import CopilotGlobalSlotPool
from experiment_b.pilot_copilot_five_models import (
    COPILOT_BASE_URL,
    CopilotResponsesClient,
    build_reconstruction_prompt as build_copilot_reconstruction_prompt,
    parse_five_numbered_prompts,
)
from human_contribution.metrics import (
    CounterfactualSample,
    evaluate_session_profile,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

OUTPUT_DIR = HERE / "outputs"
LOG_DIR = HERE / "logs"

CF_COUNT = 5
_COMPRESSORS = ("zlib", "bz2", "lzma")  # raters for Krippendorff's α
MIN_VALID_CFS = 3  # need ≥3 valid counterfactuals for a meaningful baseline
BOUNDED600_INSTRUCTIONS = (
    "Answer the user's request directly and completely in no more than 600 words. "
    "Reach a natural conclusion and end with a complete sentence before the output limit. "
    "Compress or omit lower-priority details rather than continuing indefinitely."
)

DATASETS = ["10k_prompts", "wildchat", "oasst1"]

# The 5 mainline models (Experiment A already validated these across all domains).
MODELS = [
    "claude-sonnet-5",
    "gemini-3.6-flash",
    "claude-opus-4-8",
    "gpt-5.6-sol",
    "gpt-5.5",
]

_LEVEL_NUM = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


class CopilotFormalAdapter:
    """Prompt sampler backed by the strict, slotted local Copilot Responses client."""

    _ROUTES = {
        "original": "copilot_2_2_15_local_responses",
        "bounded600": "copilot_2_2_15_local_responses_bounded600",
    }
    _BOUNDED600_INSTRUCTIONS = BOUNDED600_INSTRUCTIONS
    use_alt_backend = True
    backend_pin = None
    max_output_tokens = 4096
    segment_output_tokens = None

    def __init__(
        self,
        model_name: str,
        *,
        slots: int = 8,
        slot_root: Path | None = None,
        retries: int = 2,
        sleep_seconds: float = 0.0,
        api_timeout: int = 180,
        profile: str = "bounded600",
        model_identity_aliases: tuple[tuple[str, str], ...] | frozenset[tuple[str, str]] = (),
    ) -> None:
        if profile not in self._ROUTES:
            raise ValueError(f"unknown Copilot formal profile: {profile!r}")
        self.route_name = self._ROUTES[profile]
        self.generation_instructions = (
            self._BOUNDED600_INSTRUCTIONS if profile == "bounded600" else None
        )
        self.model_name = model_name
        self.sleep_seconds = sleep_seconds
        key_path = Path(os.environ["LOCALAPPDATA"]) / "copilot-api-canary" / "2.2.15" / "api-home" / "client_api_key"
        key = key_path.read_text(encoding="utf-8").strip()
        if not key:
            raise RuntimeError(f"empty Copilot API key file: {key_path}")
        pool = CopilotGlobalSlotPool(root=slot_root, capacity=slots)
        self._client = CopilotResponsesClient(
            key,
            pool,
            base_url=COPILOT_BASE_URL,
            retries=retries,
            timeout_seconds=api_timeout,
            model_identity_aliases=model_identity_aliases,
        )
        self._last_response_metadata: dict | None = None
        self._call_index = 0

    def consume_last_response_metadata(self) -> dict | None:
        value = self._last_response_metadata
        self._last_response_metadata = None
        return value

    def generate(self, prompt: str) -> str:
        self._last_response_metadata = None
        self._call_index += 1
        text, metadata = self._client.call(
            self.model_name,
            prompt,
            f"formal_generate_{self._call_index}",
            instructions=self.generation_instructions,
        )
        self._last_response_metadata = metadata
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        return text

    def reconstruct_prompts(self, output: str, n: int) -> list[str]:
        if n != 5:
            raise ValueError("Copilot Experiment B reconstruction requires exactly 5 prompts")
        self._last_response_metadata = None
        text, metadata = self._client.call(
            self.model_name,
            build_copilot_reconstruction_prompt(output),
            "formal_reconstruction",
        )
        self._last_response_metadata = metadata
        return parse_five_numbered_prompts(text)


class Api3rdBoundedFormalAdapter(MultiModelAdapter):
    """Strict API3rd adapter for B's single-call bounded600 GPT protocol."""

    route_name = "backend_c_responses_bounded600_single_call"
    require_api_reconstruction = True

    def __init__(
        self,
        model_name: str,
        *,
        sleep_seconds: float = 0.0,
        api_timeout: int = 120,
    ) -> None:
        super().__init__(
            model_name=model_name,
            sleep_seconds=sleep_seconds,
            api_timeout=api_timeout,
            use_alt_backend=True,
            backend_pin=None,
            gpt_route="backend_c",
            max_output_tokens=4096,
            segment_output_tokens=None,
            generation_instructions=BOUNDED600_INSTRUCTIONS,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════════

def _manifest_file_hash(lineage: LineageManifest, path: Path) -> str | None:
    """Return a declared official-file SHA-256 when the lineage provides one."""
    candidates = []
    for key in ("official_files", "files", "artifacts"):
        value = lineage.raw.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    names = {
        path.name,
        str(path),
        str(path.resolve()),
        f"outputs/{path.name}",
        f"experiment_b/outputs/{path.name}",
    }
    for mapping in candidates:
        for name in names:
            entry = mapping.get(name)
            if isinstance(entry, str):
                return entry
            if isinstance(entry, dict):
                digest = entry.get("sha256")
                if isinstance(digest, str):
                    return digest
    return None


def _validate_source_row(row: object, dataset: str) -> None:
    if not isinstance(row, dict):
        raise ValueError("source row must be an object")
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise ValueError("source row has no non-empty ID")
    if row.get("dataset") != dataset:
        raise ValueError(f"source dataset mismatch: {row.get('dataset')!r} != {dataset!r}")
    if row.get("level") not in _LEVEL_NUM:
        raise ValueError(f"invalid source level {row.get('level')!r}")
    for key in ("category", "prompt"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"source {key} must be non-empty")
    value = row.get("excess_ratio")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("source excess_ratio must be finite")


def load_stratified(
    datasets: list[str], lineage: LineageManifest | None = None,
) -> tuple[list[dict], dict[str, dict]]:
    """Strictly load the manifest-declared stratified source universe."""
    lineage = lineage or load_active_lineage_manifest(OUTPUT_DIR)
    items: list[dict] = []
    source_index: dict[str, dict] = {}
    for dataset in datasets:
        if dataset not in lineage.expected_dataset_counts:
            raise RuntimeError(f"dataset {dataset!r} is absent from active lineage")
        path = OUTPUT_DIR / f"{dataset}_stratified.jsonl"
        scan = scan_jsonl(
            path,
            validator=lambda row, ds=dataset: _validate_source_row(row, ds),
            repair=True,
        )
        expected_count = lineage.expected_dataset_counts[dataset]
        if len(scan) != expected_count:
            raise RuntimeError(
                f"source count mismatch for {dataset}: {len(scan)} != {expected_count}"
            )
        declared_hash = _manifest_file_hash(lineage, path)
        if declared_hash is not None and scan.file_sha256 != declared_hash:
            raise RuntimeError(
                f"source hash mismatch for {path}: {scan.file_sha256} != {declared_hash}"
            )
        for entry in scan.entries:
            row = dict(entry.value)
            item_id = row["id"]
            if item_id in source_index:
                raise RuntimeError(f"duplicate source ID across datasets: {item_id}")
            source_index[item_id] = row
            items.append(row)
    return items, source_index


def load_done_map(
    path: Path,
    model_name: str,
    expected_protocol: dict,
    *,
    source_index: dict[str, dict],
    lineage: LineageManifest,
) -> dict[str, dict]:
    """Load the durable, schema-validated completion map for resume."""
    if not path.exists():
        return {}

    def validator(row: object) -> None:
        if not isinstance(row, dict):
            raise ValidationSchemaError("validation row must be an object")
        item_id = row.get("id")
        source = source_index.get(item_id) if isinstance(item_id, str) else None
        validate_validation_row(
            row,
            expected_model=model_name,
            source=source,
            require_source=True,
            expected_protocol=expected_protocol,
            legacy_allowlist=lineage.legacy_validation_allowlist,
            model_identity_aliases=lineage.model_identity_aliases,
        )

    scan = scan_jsonl(path, validator=validator, repair=True)
    return {entry.item_id: dict(entry.value) for entry in scan.entries if entry.item_id}


def load_done_ids(
    path: Path,
    model_name: str,
    expected_protocol: dict,
    *,
    source_index: dict[str, dict] | None = None,
    lineage: LineageManifest | None = None,
) -> set[str]:
    """Compatibility wrapper returning IDs from the strict done map."""
    lineage = lineage or load_active_lineage_manifest(OUTPUT_DIR)
    if source_index is None:
        _, source_index = load_stratified(DATASETS, lineage)
    return set(
        load_done_map(
            path,
            model_name,
            expected_protocol,
            source_index=source_index,
            lineage=lineage,
        )
    )


class InfrastructureOutageError(RuntimeError):
    """Local circuit-breaker signal for consecutive transport/service failures."""


_INFRASTRUCTURE_ERROR_MARKERS = (
    "fetch_failed",
    "fetch failed",
    "http status 500",
    "http status 502",
    "http status 503",
    "http status 504",
    "unable to reach proxy",
    "all endpoints are unavailable",
    "connection refused",
    "actively refused",
    "积极拒绝",
    "getaddrinfo failed",
    "unexpected_eof",
    "unexpected eof",
    "remote end closed",
    "network error",
    "proxy request timed out",
    "subprocess timeout",
    "urlerror",
)


def _is_infrastructure_failure(error: BaseException | str) -> bool:
    if isinstance(error, InfrastructureOutageError):
        return True
    text = str(error).casefold()
    return any(marker in text for marker in _INFRASTRUCTURE_ERROR_MARKERS)


class InfrastructureCircuitBreaker:
    def __init__(self, threshold: int = 3) -> None:
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError("circuit-breaker threshold must be a positive integer")
        self.threshold = threshold
        self.consecutive_failures = 0

    def success(self) -> None:
        self.consecutive_failures = 0

    def failure(self, error: BaseException | str) -> int:
        if not _is_infrastructure_failure(error):
            self.consecutive_failures = 0
            return 0
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            raise InfrastructureOutageError(
                f"infrastructure circuit breaker opened after "
                f"{self.consecutive_failures} consecutive failures: {error}"
            )
        return self.consecutive_failures


# ═══════════════════════════════════════════════════════════════════════════════
# Output validation
# ═══════════════════════════════════════════════════════════════════════════════

def _is_text_output(text: str) -> bool:
    """True if the output has any letter/digit (any script)."""
    return bool(re.search(r"[^\W_]", text, re.UNICODE))


def _is_valid_output(text: str) -> bool:
    """Real text AND not an error/garbage string.

    No minimum length: Experiment B uses *real* prompts, some of which
    legitimately yield short answers ("2+2" → "4").  The stratification that
    defined the gradient used the same lenient rule, so validation must too,
    otherwise we'd silently drop the shortest-output items and bias the
    comparison against L5.
    """
    if not text or not _is_text_output(text):
        return False
    t = text.strip()
    if t.startswith("[ERROR") or t.startswith("Error:") or t.startswith("[API") \
            or t.startswith("[Errno"):
        return False
    return True


def _gen(
    adapter: MultiModelAdapter, prompt: str, label: str = ""
) -> tuple[str, dict | None]:
    """Generate one validated output plus its API provenance."""
    try:
        out = adapter.generate(prompt).strip()
        metadata = adapter.consume_last_response_metadata()
    except Exception as e:
        print(f"    [{label}] API ERROR: {e}", flush=True)
        raise

    if not _is_valid_output(out):
        print(f"    [{label}] INVALID ({len(out)} chars) — raising to skip item", flush=True)
        raise RuntimeError(f"{label}: invalid output ({len(out)} chars)")
    print(f"    [{label}] ok ({len(out)} chars)", flush=True)
    return out, metadata


# ═══════════════════════════════════════════════════════════════════════════════
# Counterfactuals
# ═══════════════════════════════════════════════════════════════════════════════

def _reconstruct(
    adapter: MultiModelAdapter, output: str
) -> tuple[list[str], dict | None]:
    """Reconstruct prompts and return provenance, marking local fallback use."""
    api_metadata: dict | None = None
    fallback_reason = "too_few_valid_prompts"
    try:
        prompts = list(adapter.reconstruct_prompts(output, CF_COUNT))
        api_metadata = adapter.consume_last_response_metadata()
        valid = [p for p in prompts if p.strip() and len(p.strip()) >= 10]
        if len(valid) >= MIN_VALID_CFS:
            return valid[:CF_COUNT], api_metadata
    except Exception as exc:
        if getattr(adapter, "require_api_reconstruction", False):
            raise RuntimeError(f"API reconstruction failed: {exc}") from exc
        fallback_reason = f"api_error: {str(exc)[:500]}"

    if getattr(adapter, "require_api_reconstruction", False):
        raise RuntimeError("API reconstruction returned fewer than three valid prompts")

    words = output.split()
    snippet = " ".join(words[:50]) if len(words) > 50 else output[:300]
    fallback = [
        f"Write a detailed response based on the following content:\n\n{snippet}",
        f"Generate content in the style of:\n\n{snippet}",
        f"Create a passage on this topic:\n\n{snippet}",
        f"Produce an article like:\n\n{snippet}",
        f"Write about:\n\n{snippet}",
    ][:CF_COUNT]
    return fallback, {
        "api": "local_fallback",
        "status": "fallback",
        "reason": fallback_reason,
        "attempt": api_metadata,
    }


def _generate_cfs(
    adapter: MultiModelAdapter, rev_prompts: list[str]
) -> tuple[list[CounterfactualSample], list[dict]]:
    """Generate counterfactuals plus per-call provenance."""
    cfs: list[CounterfactualSample] = []
    provenance: list[dict] = []
    for i, rp in enumerate(rev_prompts):
        label = f"cf_{i + 1}"
        out = ""
        metadata: dict | None = None
        error: str | None = None
        try:
            out = adapter.generate(rp).strip()
            metadata = adapter.consume_last_response_metadata()
        except Exception as exc:
            error = str(exc)[:500]
            print(f"    [{label}] API ERROR: {exc}", flush=True)
        valid = _is_valid_output(out)
        if not valid:
            print(f"    [{label}] invalid/empty ({len(out)} chars) — excluded from baseline", flush=True)
            out = ""
        cfs.append(CounterfactualSample(prompt=rp, output=out, label=label))
        provenance.append({
            "label": label,
            "valid": valid,
            "metadata": metadata,
            "error": error,
        })
    return cfs, provenance


# ═══════════════════════════════════════════════════════════════════════════════
# Contribution computation
# ═══════════════════════════════════════════════════════════════════════════════

def compute_metrics(prompt: str, output: str, cfs: list[CounterfactualSample]) -> dict:
    """Aggregate excess_ratio + diagnostics from one compression profile."""
    profile = evaluate_session_profile(
        prompt=prompt,
        output=output,
        counterfactuals=cfs,
        compressors=_COMPRESSORS,
    )
    sess = profile.aggregate

    per_comp: dict[str, dict[str, float]] = {}
    if output.strip():
        for compressor in _COMPRESSORS:
            actual = profile.actual.per_compressor[compressor]["contribution_ratio"]
            baseline = profile.counterfactual_baseline.per_compressor_mean_ratios[
                compressor
            ]
            per_comp[compressor] = {
                "actual_ratio": actual,
                "baseline_mean": baseline,
                "excess_ratio": actual - baseline,
            }

    return {
        "actual_ratio": sess.actual.contribution_ratio,
        "excess_ratio": sess.excess_contribution_ratio,
        "baseline_mean": sess.counterfactual_baseline.mean_contribution_ratio,
        "baseline_n_valid": len(sess.counterfactual_baseline.samples),
        "actual_gain_bits": sess.actual.gain_bits,
        "per_compressor": per_comp,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Per-item processing
# ═══════════════════════════════════════════════════════════════════════════════

def protocol_for_adapter(adapter: MultiModelAdapter) -> dict:
    """Return the exact schema-v2 protocol persisted and required on resume."""
    explicit_route = getattr(adapter, "route_name", None)
    if isinstance(explicit_route, str) and explicit_route:
        route = explicit_route
    elif adapter.backend_pin is not None:
        route = "api8_21_gateway_pinned_json_verified"
    elif adapter.use_alt_backend:
        route = "new_api_json_verified"
    else:
        route = "legacy_text_route"
    segmented = adapter.segment_output_tokens is not None
    return canonical_protocol(
        route=route,
        use_alt_backend=adapter.use_alt_backend,
        backend_pin=adapter.backend_pin,
        max_output_tokens=adapter.max_output_tokens,
        segment_output_tokens=adapter.segment_output_tokens,
        mode="segmented_budget" if segmented else "single_call",
        continuation_protocol="marker_v2_bounded600" if segmented else None,
        reasoning_effort="low" if adapter.use_alt_backend or adapter.backend_pin else None,
    )


def _require_active_lineage_protocol(
    lineage: LineageManifest, model_name: str, generation_protocol: dict,
) -> None:
    """Fail closed when a formal route differs from the active lineage."""
    protocols = lineage.raw.get("validation_protocols")
    if protocols is None:
        return
    if not isinstance(protocols, dict):
        raise RuntimeError("active lineage validation_protocols must be an object")
    expected = protocols.get(model_name)
    if not isinstance(expected, dict):
        raise RuntimeError(
            f"active lineage has no validation protocol for {model_name!r}"
        )
    if expected != generation_protocol:
        raise RuntimeError(
            f"active-lineage protocol mismatch for {model_name}: "
            f"expected={json.dumps(expected, sort_keys=True)}, "
            f"actual={json.dumps(generation_protocol, sort_keys=True)}"
        )


def process_item(
    adapter: MultiModelAdapter, item: dict, generation_protocol: dict | None = None,
) -> dict | None:
    """Full validation for one stratified item.  Returns result or None (skip).

    Raises on invalid main output (item retried on resume).  Returns None when
    the baseline is too weak (< MIN_VALID_CFS counterfactuals)."""
    generation_protocol = generation_protocol or protocol_for_adapter(adapter)
    prompt = item["prompt"]

    output, main_metadata = _gen(adapter, prompt, "main")
    rev_prompts, reconstruct_metadata = _reconstruct(adapter, output)
    cfs, cf_metadata = _generate_cfs(adapter, rev_prompts)

    valid_cfs = sum(1 for cf in cfs if cf.output.strip())
    if valid_cfs < MIN_VALID_CFS:
        infrastructure_errors = [
            entry.get("error")
            for entry in cf_metadata
            if entry.get("error") and _is_infrastructure_failure(entry["error"])
        ]
        if infrastructure_errors:
            raise InfrastructureOutageError(
                f"only {valid_cfs}/{CF_COUNT} valid CFs during infrastructure failures: "
                f"{infrastructure_errors[-1]}"
            )
        print(f"    [skip] only {valid_cfs}/{CF_COUNT} valid CFs (<{MIN_VALID_CFS})", flush=True)
        return None

    m = compute_metrics(prompt, output, cfs)
    return {
        "id": item["id"],
        "dataset": item.get("dataset", ""),
        "category": item.get("category", ""),
        "level": item["level"],
        "model": adapter.model_name,
        "generation_protocol": generation_protocol,
        "api_provenance": {
            "main": main_metadata,
            "reconstruct": reconstruct_metadata,
            "counterfactuals": cf_metadata,
        },
        "prompt": prompt,
        "output": output,
        "output_chars": len(output),
        "cf_valid": valid_cfs,
        "cf_total": len(cfs),
        "strat_excess_ratio": item.get("excess_ratio"),  # opus-4-7 reference score
        **m,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Model runner
# ═══════════════════════════════════════════════════════════════════════════════

def _run_model_locked(
    model_name: str,
    datasets: list[str],
    limit: int = 0,
    fresh: bool = False,
    sleep_s: float | None = None,
    timeout: int | None = None,
    backend_pin: int | None = None,
    max_output_tokens: int = 4096,
    segment_output_tokens: int | None = None,
    api_route: str = "current",
    copilot_slots: int = 8,
    copilot_slot_root: Path | None = None,
    copilot_retries: int = 2,
    outage_threshold: int = 3,
) -> None:
    # Per-model timeout/sleep (mirrors Experiment A's run_final_5level.py)
    if timeout is None:
        timeout = 120 if "gpt" in model_name else 90
    if sleep_s is None:
        sleep_s = 1.5 if "gpt" in model_name else (0.6 if "gemini" in model_name else 0.5)

    lineage = load_active_lineage_manifest(OUTPUT_DIR)
    model_identity_aliases = frozenset(
        pair for pair in lineage.model_identity_aliases if pair[0] == model_name
    )
    if api_route in {"copilot", "copilot-original"}:
        adapter = CopilotFormalAdapter(
            model_name,
            slots=copilot_slots,
            slot_root=copilot_slot_root,
            retries=copilot_retries,
            sleep_seconds=sleep_s,
            api_timeout=max(timeout, 180),
            profile="bounded600" if api_route == "copilot" else "original",
            model_identity_aliases=model_identity_aliases,
        )
    elif api_route == "backend_c-bounded600":
        adapter = Api3rdBoundedFormalAdapter(
            model_name,
            sleep_seconds=sleep_s,
            api_timeout=timeout,
        )
    elif api_route == "current":
        adapter = MultiModelAdapter(
            model_name=model_name, api_timeout=timeout, sleep_seconds=sleep_s,
            use_alt_backend=True,  # Experiment B runs entirely on the new API
            backend_pin=backend_pin,
            max_output_tokens=max_output_tokens,
            segment_output_tokens=segment_output_tokens,
        )
    else:
        raise ValueError(f"unknown api_route: {api_route!r}")

    generation_protocol = protocol_for_adapter(adapter)
    _require_active_lineage_protocol(lineage, model_name, generation_protocol)
    items, source_index = load_stratified(datasets, lineage)
    out_path = OUTPUT_DIR / f"validation_{model_name}.jsonl"
    if fresh and out_path.exists():
        backup = create_verified_backup(
            out_path,
            backup_dir=HERE / "backups" / "fresh" / model_name,
        )
        atomic_replace_bytes(out_path, b"")
        print(
            f"# FRESH: backed up {out_path.name} to {backup.backup_path} and reset atomically",
            flush=True,
        )
    done_map = load_done_map(
        out_path,
        model_name,
        generation_protocol,
        source_index=source_index,
        lineage=lineage,
    )
    todo = [it for it in items if it["id"] not in done_map]
    if limit > 0:
        todo = todo[:limit]

    print(f"\n{'#' * 72}")
    print(f"# MODEL: {model_name}  |  route={api_route} timeout={timeout}s  sleep={sleep_s}s"
          f"  backend_pin={backend_pin or 'auto'}  max_output_tokens={max_output_tokens}"
          f"  segment_output_tokens={segment_output_tokens or 'off'}")
    print(f"# Stratified items: {len(items)}  |  already done: {len(done_map)}  |  todo: {len(todo)}")
    print(f"{'#' * 72}\n", flush=True)

    if not todo:
        print("Nothing to do — all items already validated for this model.", flush=True)
        return

    t0 = time.time()
    saved = 0
    skipped_cf = 0
    skipped_invalid = 0
    circuit_breaker = InfrastructureCircuitBreaker(outage_threshold)
    for idx, item in enumerate(todo):
        try:
            result = process_item(adapter, item, generation_protocol)
        except Exception as e:
            skipped_invalid += 1
            try:
                consecutive = circuit_breaker.failure(e)
            except InfrastructureOutageError as outage:
                print(
                    f"[{idx + 1}/{len(todo)}] CIRCUIT-OPEN {item['id']} "
                    f"after {circuit_breaker.consecutive_failures} consecutive "
                    f"infrastructure failures: {outage}",
                    flush=True,
                )
                raise
            print(
                f"[{idx + 1}/{len(todo)}] SKIP-INVALID {item['id']} "
                f"({item['level']}): {e}"
                + (f" [infra_streak={consecutive}/{outage_threshold}]" if consecutive else ""),
                flush=True,
            )
            continue

        if result is None:
            circuit_breaker.success()
            skipped_cf += 1
            print(f"[{idx + 1}/{len(todo)}] SKIP-CF {item['id']} ({item['level']})", flush=True)
            continue

        item_id = result["id"]
        if item_id in done_map:
            raise RuntimeError(f"fatal duplicate append attempt for {item_id}")
        validate_validation_row(
            result,
            expected_model=model_name,
            source=source_index[item_id],
            require_source=True,
            expected_protocol=generation_protocol,
            legacy_allowlist=lineage.legacy_validation_allowlist,
            model_identity_aliases=lineage.model_identity_aliases,
            path=f"new_result[{item_id}]",
        )
        append_jsonl_row(out_path, result)
        done_map[item_id] = result
        circuit_breaker.success()
        saved += 1

        if (idx + 1) % 20 == 0 or idx + 1 == len(todo):
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed * 60 if elapsed > 0 else 0
            print(f"[{idx + 1}/{len(todo)}] saved={saved} skip_cf={skipped_cf} "
                  f"skip_invalid={skipped_invalid} | {rate:.1f} items/min | "
                  f"last={item['id']} {item['level']} excess={result['excess_ratio']:+.4f}",
                  flush=True)

    elapsed = time.time() - t0
    print(f"\n[{model_name}] DONE in {elapsed / 60:.1f} min — "
          f"saved={saved} skip_cf={skipped_cf} skip_invalid={skipped_invalid}", flush=True)


def run_model(
    model_name: str,
    datasets: list[str],
    limit: int = 0,
    fresh: bool = False,
    sleep_s: float | None = None,
    timeout: int | None = None,
    backend_pin: int | None = None,
    max_output_tokens: int = 4096,
    segment_output_tokens: int | None = None,
    api_route: str = "current",
    copilot_slots: int = 8,
    copilot_slot_root: Path | None = None,
    copilot_retries: int = 2,
    outage_threshold: int = 3,
) -> None:
    """Run one model under the B-only process lock and storage sentinels."""
    with scope_lock(HERE, f"validation:{model_name}"):
        _run_model_locked(
            model_name,
            datasets,
            limit=limit,
            fresh=fresh,
            sleep_s=sleep_s,
            timeout=timeout,
            backend_pin=backend_pin,
            max_output_tokens=max_output_tokens,
            segment_output_tokens=segment_output_tokens,
            api_route=api_route,
            copilot_slots=copilot_slots,
            copilot_slot_root=copilot_slot_root,
            copilot_retries=copilot_retries,
            outage_threshold=outage_threshold,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment B — Step 4 validation (single model)")
    parser.add_argument("--model", type=str, required=True, help="Model name (one of MODELS)")
    parser.add_argument("--dataset", type=str, default=None, help="Single dataset (10k_prompts|wildchat|oasst1)")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N items (smoke test)")
    parser.add_argument("--fresh", action="store_true", help="Backup and atomically reset this model's result file")
    parser.add_argument("--confirm-fresh", type=str, default=None,
                        help="Required with --fresh; must exactly equal --model")
    parser.add_argument("--sleep", type=float, default=None, help="Override sleep between calls")
    parser.add_argument("--timeout", type=int, default=None, help="Override API timeout")
    parser.add_argument("--gpt-gateway", type=int, choices=(1, 2, 3), default=None,
                        help="Pin a GPT model to one backend_b gateway (1-3)")
    parser.add_argument("--max-output-tokens", type=int, default=4096,
                        help="Total generated-token budget (default 4096, matching legacy API)")
    parser.add_argument("--segment-output-tokens", type=int, default=None,
                        help="Optional per-call GPT segment cap; use 2048 with a 4096 total budget")
    parser.add_argument(
        "--api-route",
        choices=("current", "copilot", "copilot-original", "backend_c-bounded600"),
        default="current",
    )
    parser.add_argument("--copilot-slots", type=int, default=8)
    parser.add_argument("--copilot-slot-root", type=Path, default=None)
    parser.add_argument("--copilot-retries", type=int, default=2)
    parser.add_argument("--outage-threshold", type=int, default=3,
                        help="Stop locally after this many consecutive infrastructure failures")
    args = parser.parse_args()

    if args.fresh and args.confirm_fresh != args.model:
        parser.error("--fresh requires --confirm-fresh to exactly equal --model")

    if args.model not in MODELS:
        print(f"WARNING: '{args.model}' not in the 5 mainline models {MODELS} — "
              f"proceeding anyway (routing via multi_model_adapter).", flush=True)

    datasets = [args.dataset] if args.dataset else DATASETS
    run_model(args.model, datasets, limit=args.limit, fresh=args.fresh,
              sleep_s=args.sleep, timeout=args.timeout,
              backend_pin=args.backend_pin,
              max_output_tokens=args.max_output_tokens,
              segment_output_tokens=args.segment_output_tokens,
              api_route=args.api_route,
              copilot_slots=args.copilot_slots,
              copilot_slot_root=args.copilot_slot_root,
              copilot_retries=args.copilot_retries,
              outage_threshold=args.outage_threshold)


if __name__ == "__main__":
    main()
