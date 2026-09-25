# -*- coding: utf-8 -*-
"""Experiment B — Unified Pipeline: Classify + Generate + Contribution + Stratify.

Steps 1–3 executed in a single pass per prompt (方案一):
  1. Classify prompt into 1 of 6 themes (Claude Opus 4.7, all datasets)
  2. If category not full: generate AI output
  3. Empty / non-text output → skip (not counted toward quota)
  4. Generate 5 counterfactuals → compute excess_ratio
  5. After all datasets done: stratify each theme into 5 levels by excess_ratio

Key design rules:
  - No input/output length limit (follow the core compression formula).
  - Only valid-text ("ok") items count toward the per-category quota.
  - "Full" = exactly target (500/300); no buffer overshoot.
  - Each dataset is independent; stop a dataset once 5/6 categories are full
    (the rare 艺术设计 category is left at whatever it reached).
  - Incremental JSONL + tracking.json for resume; failed classifications are
    NOT marked classified, so they are retried on resume.

Counterfactual baseline (aligned with Experiment A):
  - Reconstruct 5 prompts from AI output
  - Generate outputs for each reconstructed prompt
  - Baseline = mean contribution_ratio of the 5 counterfactual pairs
  - excess_ratio = actual_ratio - baseline_mean

Usage::

    # Full run (auto-resumes from where it left off)
    python -X utf8 experiment_b/run_pipeline.py

    # Single dataset
    python -X utf8 experiment_b/run_pipeline.py --dataset wildchat

    # Test mode (3 prompts per dataset, full pipeline)
    python -X utf8 experiment_b/run_pipeline.py --test

    # Dry run (data loading only, no API calls)
    python -X utf8 experiment_b/run_pipeline.py --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# ── Fix Windows encoding ────────────────────────────────────────────────────
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

# Ensure project root is on path for human_contribution imports
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b import storage as b_storage
from human_contribution.compression import DEFAULT_COMPRESSORS
from human_contribution.metrics import (
    CounterfactualSample,
    build_counterfactual_baseline_profile,
    information_gain_profile,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Paths & Constants
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = PROJECT / "data" / "experiment_b"
NEW_API = PROJECT / "clients" / "client_legacy.py"
PYTHON = sys.executable
OUTPUT_DIR = HERE / "outputs"
LOG_DIR = HERE / "logs"

# Model (Claude Opus 4.7 — NOT used in Experiment A)
PIPELINE_MODEL = "claude-opus-4-7"

# API settings
API_TIMEOUT = 180       # seconds per call (longer for generation)
CF_TIMEOUT = 120        # seconds for CF reconstruction/generation
MAX_RETRIES = 3         # retry on failure
RETRY_BACKOFF = 2.0     # seconds base backoff

# Concurrency & Rate Limiting
CONCURRENCY = 6         # workers
RPM_TARGET = 48         # target calls/min (leaves 12 RPM for other conversations)

# Sampling targets per category per dataset
TARGETS = {
    "10k_prompts": 500,
    "wildchat": 500,
    "oasst1": 300,
}
# Counterfactual settings
CF_COUNT = 5
MIN_VALID_CFS = 3

# Durable state schema. Official ``status == "ok"`` JSONL is the only truth;
# tracking files are explicitly advisory and can always be rebuilt.
PIPELINE_SCHEMA_VERSION = 2
TRACKING_SCHEMA = "experiment_b.pipeline_tracking"
TRACKING_SCHEMA_VERSION = 2
PIPELINE_SCOPE_PREFIX = "pipeline"

SOURCE_PATHS = {
    "10k_prompts": DATA_DIR / "10k_prompts" / "full.jsonl",
    "wildchat": DATA_DIR / "wildchat" / "wildchat_10k.jsonl",
    "oasst1": DATA_DIR / "oasst1" / "oasst1_10k.jsonl",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Six Categories
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORIES = {
    "1": "技术实现",
    "2": "专业知识",
    "3": "推理分析",
    "4": "创意生成",
    "5": "艺术设计",
    "6": "经验情境",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFY_SYSTEM = """\
You are a text classifier. Read the user prompt below and classify it into \
EXACTLY ONE of the following 6 categories.

Categories:
1. 技术实现 — programming, coding, debugging, algorithm design, system \
architecture, API usage, software engineering, technical tools
2. 专业知识 — factual knowledge queries about medicine, law, finance, physics, \
chemistry, biology, history, geography, professional/academic knowledge
3. 推理分析 — mathematical proofs, logical reasoning, scientific reasoning, \
data analysis, statistical inference, critical thinking, formal derivation
4. 创意生成 — story writing, poetry, scripts, worldbuilding, character design, \
product ideas, creative brainstorming, fictional content
5. 艺术设计 — visual design, drawing, color schemes, Logo/UI/UX, music, \
architecture, fashion, photography, aesthetic advice
6. 经验情境 — personal experience sharing, case discussions, scenario \
simulations, practical how-to advice, interpersonal relationships, career \
advice, life decisions

Rules:
- If the prompt involves writing/running/debugging code → 技术实现 (1)
- If the prompt requires step-by-step logical derivation → 推理分析 (3)
- If the prompt asks for factual/encyclopedic knowledge → 专业知识 (2)
- If the prompt asks to create a fictional story/poem/script → 创意生成 (4)
- If the prompt is about visual/musical/fashion design → 艺术设计 (5)
- If the prompt shares a personal situation and asks for advice → 经验情境 (6)
- Reply with ONLY the category number (1-6) and nothing else."""

GENERATE_SYSTEM = "You are a helpful AI assistant."

CF_RECONSTRUCT_SYSTEM = """\
You are a reverse prompt engineer. Given an AI-generated response, reconstruct \
what human prompt might have led to it. Output ONLY the reconstructed prompt, \
no other text, no prefixes, no labels."""


def _sha256_text(text: str) -> str:
    return b_storage.sha256_bytes(text.encode("utf-8"))


def source_hash_for_dataset(
    dataset_name: str,
    items: Optional[Iterable[dict]] = None,
) -> str:
    """Return the source hash used by tracking and configuration fingerprints.

    Production datasets use the exact source-file bytes. ``items`` is a
    deterministic fallback for isolated tests or a future loader without a raw
    source file.
    """
    source_path = SOURCE_PATHS.get(dataset_name)
    if source_path is not None and source_path.is_file():
        return b_storage.file_sha256(source_path)
    if items is None:
        raise FileNotFoundError(f"no source file or source items for {dataset_name!r}")
    return b_storage.sha256_bytes(b_storage.canonical_json_bytes(list(items)))


def build_pipeline_configuration(
    dataset_name: str,
    target: int,
    source_sha256: str,
) -> dict:
    """Build the complete, deterministic Step 1–3 configuration payload."""
    if dataset_name not in LOADERS:
        raise ValueError(f"unknown dataset: {dataset_name!r}")
    if isinstance(target, bool) or not isinstance(target, int) or target <= 0:
        raise ValueError("target must be a positive integer")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        raise ValueError("source_sha256 must be a SHA-256 hex digest")
    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "dataset": dataset_name,
        "model": PIPELINE_MODEL,
        "prompt_sha256": {
            "classification": _sha256_text(CLASSIFY_SYSTEM),
            "generation": _sha256_text(GENERATE_SYSTEM),
            "counterfactual_reconstruction": _sha256_text(CF_RECONSTRUCT_SYSTEM),
        },
        "token_caps": {
            "classification": 64,
            "generation": 1024,
            "counterfactual_reconstruction": 512,
            "counterfactual_generation": 1024,
        },
        "counterfactual_count": CF_COUNT,
        "minimum_valid_counterfactuals": MIN_VALID_CFS,
        "compressors": list(DEFAULT_COMPRESSORS),
        "target_per_category": target,
        "source_sha256": source_sha256,
    }


def configuration_fingerprint(
    dataset_name: str,
    target: int,
    source_sha256: str,
) -> str:
    """Hash the full pipeline configuration using canonical strict JSON."""
    configuration = build_pipeline_configuration(
        dataset_name, target, source_sha256
    )
    return b_storage.sha256_bytes(b_storage.canonical_json_bytes(configuration))


# ═══════════════════════════════════════════════════════════════════════════════
# Rate Limiter (sliding window)
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Sliding-window rate limiter shared across threads."""

    def __init__(self, rpm: int = RPM_TARGET, window: float = 60.0):
        self.rpm = rpm
        self.window = window
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self):
        """Block until a call slot is available."""
        with self._lock:
            now = time.time()
            # Evict old timestamps
            cutoff = now - self.window
            self._timestamps = [t for t in self._timestamps if t >= cutoff]
            if len(self._timestamps) >= self.rpm:
                sleep_for = self._timestamps[0] + self.window - now + 0.1
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.time()
                cutoff = now - self.window
                self._timestamps = [t for t in self._timestamps if t >= cutoff]
            self._timestamps.append(time.time())


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_10k_prompts() -> list[dict]:
    """Load all prompts from 10k_prompts (no topic pre-classification)."""
    items = []
    fpath = DATA_DIR / "10k_prompts" / "full.jsonl"
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            text = d.get("prompt", "").strip()
            if len(text) < 10:
                continue
            items.append({
                "id": f"10k_{len(items):05d}",
                "dataset": "10k_prompts",
                "prompt": text,
                "original_topic": d.get("topic", "Unknown"),
                "kind": d.get("kind", "unknown"),
            })
    return items


def load_wildchat() -> list[dict]:
    """Load first-turn user prompts from WildChat."""
    items = []
    fpath = DATA_DIR / "wildchat" / "wildchat_10k.jsonl"
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            conv = d.get("conversation", [])
            if not conv:
                continue
            first_msg = conv[0]
            text = first_msg.get("content", "").strip()
            if len(text) < 10:
                continue
            items.append({
                "id": f"wc_{len(items):05d}",
                "dataset": "wildchat",
                "prompt": text,
                "language": d.get("language", "unknown"),
                "model": d.get("model", "unknown"),
            })
    return items


def load_oasst1() -> list[dict]:
    """Load prompter messages from OASST1."""
    items = []
    fpath = DATA_DIR / "oasst1" / "oasst1_10k.jsonl"
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("role") != "prompter":
                continue
            text = d.get("text", "").strip()
            if len(text) < 10:
                continue
            items.append({
                "id": f"oasst_{d.get('message_id', len(items))}",
                "dataset": "oasst1",
                "prompt": text,
                "language": d.get("lang", "unknown"),
            })
    return items


LOADERS = {
    "10k_prompts": load_10k_prompts,
    "wildchat": load_wildchat,
    "oasst1": load_oasst1,
}

# ═══════════════════════════════════════════════════════════════════════════════
# API Call Helper
# ═══════════════════════════════════════════════════════════════════════════════

def call_api(
    prompt: str,
    rate_limiter: RateLimiter,
    *,
    system: str = "",
    max_tokens: int = 1024,
    timeout: int = API_TIMEOUT,
    model: str = PIPELINE_MODEL,
) -> tuple[bool, str]:
    """Call the new API via subprocess. Returns (success, output_text).

    Thread-safe via rate_limiter. Retries on transient failures.
    """
    for attempt in range(MAX_RETRIES):
        rate_limiter.acquire()
        try:
            cmd = [
                PYTHON, "-u", str(NEW_API),
                "--timeout", str(timeout),
                "ask", prompt,
                "--model", model,
                "--max-output-tokens", str(max_tokens),
                "--reasoning-effort", "low",
            ]
            if system:
                cmd.extend(["--system", system])

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 30,
                cwd=str(NEW_API.parent),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return True, proc.stdout.strip()

            err = proc.stderr.strip()[:200] if proc.stderr else f"rc={proc.returncode}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
        except subprocess.TimeoutExpired:
            err = "TIMEOUT"
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
        except Exception as e:
            err = str(e)[:200]
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))

    return False, err


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1: Classification
# ═══════════════════════════════════════════════════════════════════════════════

def classify_prompt(prompt_text: str, rate_limiter: RateLimiter) -> Optional[str]:
    """Classify a single prompt. Returns category name or None on failure."""
    truncated = prompt_text[:2000] if len(prompt_text) > 2000 else prompt_text
    classify_user = (
        f"Classify the following user prompt into one of the 6 categories.\n"
        f"Reply with ONLY the category number (1-6).\n\n"
        f"[Prompt]: {truncated}"
    )
    ok, output = call_api(
        classify_user, rate_limiter,
        system=CLASSIFY_SYSTEM,
        max_tokens=64,
        timeout=API_TIMEOUT,
    )
    if not ok:
        return None

    # Parse category
    text = output.strip()
    for ch in text:
        if ch in "123456":
            return CATEGORIES[ch]
    for num, name in CATEGORIES.items():
        if name in text:
            return name
    digits = re.findall(r"[1-6]", text)
    if digits:
        return CATEGORIES[digits[0]]
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2a: Output Generation
# ═══════════════════════════════════════════════════════════════════════════════

def generate_output(prompt_text: str, rate_limiter: RateLimiter) -> tuple[bool, str]:
    """Generate AI response for a human prompt. Returns (success, output)."""
    return call_api(
        prompt_text, rate_limiter,
        system=GENERATE_SYSTEM,
        max_tokens=1024,
        timeout=API_TIMEOUT,
    )


def _is_text_output(text: str) -> bool:
    """Check if output has any linguistic content (letter or digit, any script).

    Follows the core formula: no minimum length.  Accepts short answers
    ("27"), math, code, Thai, CJK, etc.  Only rejects outputs with no
    letter or digit at all (pure symbols / whitespace), which the
    compression metric cannot meaningfully score.
    """
    return bool(re.search(r"[^\W_]", text, re.UNICODE))


_ERROR_TEXT_PREFIXES = ("[ERROR", "Error:", "[API", "[Errno")
_ERROR_TEXT_MARKERS = (
    "unsafe content found. please try again with different prompts.",
)


def _is_valid_linguistic_text(text: str) -> bool:
    """Reject empty/non-linguistic output and known API/filter error text."""
    if not isinstance(text, str) or not text.strip() or not _is_text_output(text):
        return False
    stripped = text.strip()
    if stripped.startswith(_ERROR_TEXT_PREFIXES):
        return False
    normalized = " ".join(stripped.casefold().split())
    return not any(marker in normalized for marker in _ERROR_TEXT_MARKERS)


def _require_nonempty_string(row: dict, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_int(row: dict, field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_finite_number(row: dict, field: str) -> float:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def validate_official_pipeline_row(
    row: Any,
    *,
    expected_dataset: Optional[str] = None,
) -> None:
    """Validate the durable identity fields shared by old and new official rows.

    Historical rows predate the hardened writer and contain known bookkeeping
    inconsistencies. Startup therefore validates strict JSON, identity, status,
    dataset, and category without pretending those old rows satisfy the new
    writer's stronger cross-field contract.
    """
    if not isinstance(row, dict):
        raise ValueError("pipeline row must be a JSON object")
    _require_nonempty_string(row, "id")
    if row.get("status") != "ok":
        raise ValueError("official pipeline JSONL may contain only status == 'ok'")
    dataset = _require_nonempty_string(row, "dataset")
    if expected_dataset is not None and dataset != expected_dataset:
        raise ValueError(
            f"dataset mismatch: expected {expected_dataset!r}, found {dataset!r}"
        )
    category = _require_nonempty_string(row, "category")
    if category not in CATEGORIES.values():
        raise ValueError(f"unknown category: {category!r}")


def validate_new_pipeline_record(
    row: Any,
    *,
    expected_dataset: str,
) -> None:
    """Validate a newly assembled record before its durable append."""
    validate_official_pipeline_row(row, expected_dataset=expected_dataset)
    assert isinstance(row, dict)
    prompt = _require_nonempty_string(row, "prompt")
    output = _require_nonempty_string(row, "output")
    if not _is_valid_linguistic_text(prompt):
        raise ValueError("prompt is empty, non-linguistic, or error/filter text")
    if not _is_valid_linguistic_text(output):
        raise ValueError("output is empty, non-linguistic, or error/filter text")
    if _require_int(row, "output_chars") != len(output):
        raise ValueError("output_chars does not match output length")

    cf_valid = _require_int(row, "cf_valid")
    cf_total = _require_int(row, "cf_total")
    baseline_n_valid = _require_int(row, "baseline_n_valid")
    if not (MIN_VALID_CFS <= cf_valid <= cf_total == CF_COUNT):
        raise ValueError(
            f"counterfactual counts must satisfy {MIN_VALID_CFS} <= cf_valid "
            f"<= cf_total == {CF_COUNT}"
        )
    if baseline_n_valid != cf_valid:
        raise ValueError("baseline_n_valid must equal cf_valid")

    actual_ratio = _require_finite_number(row, "actual_ratio")
    baseline_mean = _require_finite_number(row, "baseline_mean")
    excess_ratio = _require_finite_number(row, "excess_ratio")
    for field in (
        "actual_gain_bits",
        "self_information_bits",
        "conditional_information_bits",
    ):
        _require_finite_number(row, field)
    output_tokens = _require_int(row, "output_tokens")
    if output_tokens < 0:
        raise ValueError("output_tokens must be non-negative")
    if not math.isclose(
        excess_ratio,
        actual_ratio - baseline_mean,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("excess_ratio must equal actual_ratio - baseline_mean")

    details = row.get("baseline_cf_details")
    if not isinstance(details, list) or len(details) != cf_valid:
        raise ValueError("baseline_cf_details must contain exactly cf_valid rows")
    detail_valid = 0
    for index, detail in enumerate(details):
        if not isinstance(detail, dict):
            raise ValueError(f"baseline_cf_details[{index}] must be an object")
        _require_nonempty_string(detail, "cf_prompt")
        cf_output = detail.get("cf_output")
        if not isinstance(cf_output, str):
            raise ValueError(f"baseline_cf_details[{index}].cf_output must be a string")
        _require_finite_number(detail, "cf_ratio")
        if cf_output.strip():
            detail_valid += 1
    if detail_valid != cf_valid:
        raise ValueError("cf_valid does not match non-empty baseline CF outputs")

    # Force strict serializability (including nested NaN rejection) before append.
    b_storage.canonical_json_bytes(row)


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2b: Counterfactual Reconstruction & Generation
# ═══════════════════════════════════════════════════════════════════════════════

def reconstruct_one_prompt(output_text: str, rate_limiter: RateLimiter) -> str:
    """Reconstruct ONE plausible human prompt from an AI output."""
    cf_user = (
        f"Below is an AI-generated response. Reconstruct a plausible human "
        f"prompt that could have produced this response. Output ONLY the "
        f"reconstructed prompt, nothing else.\n\n"
        f"[AI Response]: {output_text[:3000]}"
    )
    ok, result = call_api(
        cf_user, rate_limiter,
        system=CF_RECONSTRUCT_SYSTEM,
        max_tokens=512,
        timeout=CF_TIMEOUT,
    )
    if ok and result.strip():
        return result.strip()
    return ""


def generate_counterfactuals(
    output_text: str, rate_limiter: RateLimiter
) -> list[CounterfactualSample]:
    """Generate 5 counterfactual (prompt, output) pairs from an AI output.

    For each CF:
      1. Reconstruct a plausible human prompt from the AI output
      2. Generate a new AI output for that reconstructed prompt
    """
    cfs: list[CounterfactualSample] = []

    for i in range(CF_COUNT):
        # Step 1: Reconstruct prompt from output
        cf_prompt = reconstruct_one_prompt(output_text, rate_limiter)
        if not _is_valid_linguistic_text(cf_prompt):
            # Fallback: use a simple template
            words = output_text.split()
            snippet = " ".join(words[:50]) if len(words) > 50 else output_text[:300]
            cf_prompt = (
                f"Write a detailed response based on the following content:\n\n"
                f"{snippet}"
            )

        # Step 2: Generate output for the reconstructed prompt
        ok, cf_output = call_api(
            cf_prompt, rate_limiter,
            system=GENERATE_SYSTEM,
            max_tokens=1024,
            timeout=CF_TIMEOUT,
        )
        if not ok or not _is_valid_linguistic_text(cf_output):
            cf_output = ""

        cfs.append(CounterfactualSample(
            prompt=cf_prompt,
            output=cf_output,
            label=f"cf_{i + 1}",
        ))

    return cfs


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2c: Contribution Computation
# ═══════════════════════════════════════════════════════════════════════════════

def compute_contribution(
    prompt: str,
    output: str,
    counterfactuals: list[CounterfactualSample],
) -> dict:
    """Compute excess_ratio and related metrics for one prompt-output pair.

    Returns dict with keys:
      actual_ratio, actual_gain_bits, self_bits, cond_bits,
      baseline_mean, baseline_n_valid, excess_ratio
    """
    # Compute actual and the shared CF baseline once each.  The profile retains
    # both canonical aggregate values and diagnostic per-compressor projections.
    actual = information_gain_profile(prompt, output).aggregate
    baseline = build_counterfactual_baseline_profile(counterfactuals).aggregate

    excess_ratio = actual.contribution_ratio - baseline.mean_contribution_ratio

    return {
        "actual_ratio": actual.contribution_ratio,
        "actual_gain_bits": actual.gain_bits,
        "self_information_bits": actual.self_information_bits,
        "conditional_information_bits": actual.conditional_information_bits,
        "output_tokens": actual.output_tokens,
        "baseline_mean": baseline.mean_contribution_ratio,
        "baseline_n_valid": len(baseline.samples),
        "baseline_cf_details": [
            {
                "cf_prompt": sample.prompt[:500],
                "cf_output": sample.output[:500],
                "cf_ratio": sample.contribution_ratio,
            }
            for sample in baseline.samples
        ],
        "excess_ratio": excess_ratio,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline Processor
# ═══════════════════════════════════════════════════════════════════════════════

class FatalPipelineError(RuntimeError):
    """The process must stop because memory and durable JSONL may diverge."""


class PipelineState:
    """Thread-safe committed/reserved state seeded from official JSONL only."""

    def __init__(
        self,
        target: int,
        committed_rows: Iterable[dict] = (),
        *,
        dataset_name: Optional[str] = None,
        source_sha256: Optional[str] = None,
        config_fingerprint: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ):
        if isinstance(target, bool) or not isinstance(target, int) or target <= 0:
            raise ValueError("target must be a positive integer")
        self.target = target
        self.dataset_name = dataset_name
        self.source_sha256 = source_sha256
        self.config_fingerprint = config_fingerprint
        self.output_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR
        self.counts: dict[str, int] = {name: 0 for name in CATEGORIES.values()}
        self.reserved_counts: dict[str, int] = {
            name: 0 for name in CATEGORIES.values()
        }
        self.completed: list[dict] = []
        self.newly_completed: list[dict] = []
        self._committed_ids: set[str] = set()
        self._reservations: dict[str, str] = {}
        self._outcomes: dict[str, str] = {}
        self._fatal_reason: Optional[str] = None
        self._lock = threading.Lock()

        for row in committed_rows:
            item_id = row["id"]
            category = row["category"]
            if item_id in self._committed_ids:
                raise ValueError(f"duplicate committed ID in initial state: {item_id!r}")
            if category not in self.counts:
                raise ValueError(f"unknown committed category: {category!r}")
            self._committed_ids.add(item_id)
            self.counts[category] += 1
            self.completed.append(row)

    @property
    def committed_ids(self) -> set[str]:
        with self._lock:
            return set(self._committed_ids)

    @property
    def classified_ids(self) -> set[str]:
        """Compatibility view: only durable committed IDs are resume-complete."""
        return self.committed_ids

    def _raise_if_fatal_locked(self) -> None:
        if self._fatal_reason is not None:
            raise FatalPipelineError(self._fatal_reason)

    def ensure_healthy(self) -> None:
        with self._lock:
            self._raise_if_fatal_locked()

    def poison(self, reason: str) -> None:
        with self._lock:
            if self._fatal_reason is None:
                self._fatal_reason = reason

    def try_reserve(self, item_id: str, category: str) -> bool:
        """Atomically reserve quota when committed + reserved is below target."""
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("item_id must be a non-empty string")
        if category not in self.counts:
            raise ValueError(f"unknown category: {category!r}")
        with self._lock:
            self._raise_if_fatal_locked()
            if item_id in self._committed_ids or item_id in self._reservations:
                return False
            if self.counts[category] + self.reserved_counts[category] >= self.target:
                return False
            categories_at_capacity = sum(
                1
                for name in CATEGORIES.values()
                if self.counts[name] + self.reserved_counts[name] >= self.target
            )
            # Once five categories are committed/reserved, do not open work in
            # the sixth. Reservations already in flight are still allowed to finish.
            if categories_at_capacity >= len(CATEGORIES) - 1:
                return False
            self._reservations[item_id] = category
            self.reserved_counts[category] += 1
            return True

    def rollback_reservation(self, item_id: str, category: str) -> bool:
        """Release a failed downstream attempt without changing committed state."""
        with self._lock:
            reserved_category = self._reservations.get(item_id)
            if reserved_category is None:
                return False
            if reserved_category != category:
                raise RuntimeError(
                    f"reservation category mismatch for {item_id!r}: "
                    f"{reserved_category!r} != {category!r}"
                )
            del self._reservations[item_id]
            self.reserved_counts[category] -= 1
            if self.reserved_counts[category] < 0:
                raise RuntimeError(f"negative reservation count for {category!r}")
            return True

    def commit_reservation(self, item: dict) -> None:
        """Convert exactly one reservation into a cumulative committed row."""
        item_id = item["id"]
        category = item["category"]
        with self._lock:
            self._raise_if_fatal_locked()
            reserved_category = self._reservations.get(item_id)
            if reserved_category != category:
                raise RuntimeError(
                    f"missing reservation for {item_id!r} in {category!r}"
                )
            if item_id in self._committed_ids:
                raise RuntimeError(f"ID is already committed: {item_id!r}")
            del self._reservations[item_id]
            self.reserved_counts[category] -= 1
            self.counts[category] += 1
            self._committed_ids.add(item_id)
            self.completed.append(item)
            self.newly_completed.append(item)

    def is_full(self, category: str, *, include_reserved: bool = True) -> bool:
        with self._lock:
            count = self.counts.get(category, 0)
            if include_reserved:
                count += self.reserved_counts.get(category, 0)
            return count >= self.target

    def num_full(self, *, include_reserved: bool = False) -> int:
        with self._lock:
            return sum(
                1
                for name in CATEGORIES.values()
                if self.counts.get(name, 0)
                + (self.reserved_counts.get(name, 0) if include_reserved else 0)
                >= self.target
            )

    def num_at_capacity(self) -> int:
        return self.num_full(include_reserved=True)

    def reservation_count(self) -> int:
        with self._lock:
            return len(self._reservations)

    def reservation_rejection_reason(self, item_id: str, category: str) -> str:
        with self._lock:
            if item_id in self._committed_ids:
                return "already_committed"
            if item_id in self._reservations:
                return "already_reserved"
            if self.counts.get(category, 0) + self.reserved_counts.get(category, 0) >= self.target:
                return "category_at_capacity"
            categories_at_capacity = sum(
                1
                for name in CATEGORIES.values()
                if self.counts[name] + self.reserved_counts[name] >= self.target
            )
            if categories_at_capacity >= len(CATEGORIES) - 1:
                return "early_stop_capacity"
            return "reservation_rejected"

    def is_classified(self, item_id: str) -> bool:
        """Classification alone is never complete; this checks durable commit."""
        with self._lock:
            return item_id in self._committed_ids

    def record_outcome(self, item_id: str, outcome: str) -> None:
        with self._lock:
            self._outcomes[item_id] = outcome

    def consume_outcome(self, item_id: str) -> Optional[str]:
        with self._lock:
            return self._outcomes.pop(item_id, None)

    def advisory_snapshot(self) -> dict:
        """Capture one locked, committed-only cumulative state snapshot."""
        with self._lock:
            committed_ids = sorted(self._committed_ids)
            return {
                "counts": dict(self.counts),
                "completed_count": len(committed_ids),
                "completed_ids": committed_ids,
            }

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counts": dict(self.counts),
                "reserved_counts": dict(self.reserved_counts),
                "completed": len(self.completed),
                "committed": len(self._committed_ids),
                "classified": len(self._committed_ids),
                "reserved": len(self._reservations),
                "newly_completed": len(self.newly_completed),
                "fatal_reason": self._fatal_reason,
            }


def process_one_prompt(
    item: dict,
    state: PipelineState,
    rate_limiter: RateLimiter,
    dataset_name: str,
) -> Optional[dict]:
    """Classify, reserve, generate, validate, durably append, then commit.

    Any failure after reservation but before a confirmed append rolls the
    reservation back. A confirmed append followed by a state-commit failure
    poisons the process: startup must rebuild from official JSONL.
    """
    prompt_text = item["prompt"]
    item_id = item["id"]

    if not _is_valid_linguistic_text(prompt_text):
        state.record_outcome(item_id, "invalid_source_prompt")
        log(f"[{dataset_name}] INVALID SOURCE PROMPT: {item_id}")
        return None

    category = classify_prompt(prompt_text, rate_limiter)
    if category is None:
        state.record_outcome(item_id, "classification_failed")
        log(f"[{dataset_name}] CLASSIFY FAILED: {item_id} "
            f"({prompt_text[:60].replace(chr(10), ' ')}...)")
        return None

    if not state.try_reserve(item_id, category):
        reason = state.reservation_rejection_reason(item_id, category)
        state.record_outcome(item_id, reason)
        log(f"[{dataset_name}] SKIP ({reason}): {item_id} → {category} "
            f"(counts: {state.snapshot()['counts']})")
        return None

    append_succeeded = False
    try:
        ok, output = generate_output(prompt_text, rate_limiter)
        if not ok or not _is_valid_linguistic_text(output):
            state.record_outcome(item_id, "generation_failed")
            log(f"[{dataset_name}] GEN FAILED/INVALID: {item_id} → {category} "
                f"(output={len(output)} chars, preview={output[:80]!r})")
            return None

        cfs = generate_counterfactuals(output, rate_limiter)
        valid_cfs = sum(1 for cf in cfs if cf.output.strip())
        if valid_cfs < MIN_VALID_CFS:
            state.record_outcome(item_id, "counterfactual_failed")
            log(f"[{dataset_name}] CF INSUFFICIENT: {item_id} → {category} "
                f"({valid_cfs}/{CF_COUNT} valid; require {MIN_VALID_CFS})")
            return None

        try:
            metrics = compute_contribution(prompt_text, output, cfs)
        except Exception as exc:
            state.record_outcome(item_id, "metric_failed")
            log(f"[{dataset_name}] METRIC FAILED: {item_id} → {category}: {exc}")
            return None

        result = {
            "id": item_id,
            "dataset": item["dataset"],
            "prompt": prompt_text,
            "category": category,
            "output": output,
            "output_chars": len(output),
            "status": "ok",
            "cf_valid": valid_cfs,
            "cf_total": CF_COUNT,
            **metrics,
        }
        try:
            validate_new_pipeline_record(result, expected_dataset=dataset_name)
        except Exception as exc:
            state.record_outcome(item_id, "record_validation_failed")
            log(f"[{dataset_name}] RECORD INVALID: {item_id} → {category}: {exc}")
            return None

        # Serialize append -> state commit -> advisory tracking so the official
        # file hash and committed snapshot cannot observe different worker phases.
        with _SAVE_LOCK:
            state.ensure_healthy()
            try:
                _save_incremental(
                    dataset_name,
                    result,
                    output_dir=state.output_dir,
                )
            except Exception as append_error:
                # If append raised after bytes reached the file, continuing would
                # undercount official truth. Detect that ambiguity and fail closed.
                try:
                    official = load_official_rows(
                        dataset_name,
                        output_dir=state.output_dir,
                    )
                except Exception as scan_error:
                    reason = (
                        f"append for {item_id!r} failed and official JSONL cannot "
                        f"be rescanned: {scan_error}"
                    )
                    state.poison(reason)
                    raise FatalPipelineError(reason) from append_error
                if any(row["id"] == item_id for row in official):
                    reason = (
                        f"append for {item_id!r} raised after the row became "
                        "visible; restart from official JSONL"
                    )
                    state.poison(reason)
                    raise FatalPipelineError(reason) from append_error
                raise

            append_succeeded = True
            try:
                state.commit_reservation(result)
            except Exception as commit_error:
                reason = (
                    f"durable append succeeded for {item_id!r} but state commit "
                    "failed; restart from official JSONL"
                )
                state.poison(reason)
                raise FatalPipelineError(reason) from commit_error

            try:
                _save_tracking(dataset_name, state)
            except Exception as tracking_error:
                # Tracking is explicitly advisory. Official JSONL and in-memory
                # committed state are already correct, so do not undo success.
                log(f"[{dataset_name}] TRACKING ADVISORY WRITE FAILED: "
                    f"{tracking_error}")

        state.record_outcome(item_id, "ok")
        log(f"[{dataset_name}] OK: {item_id} → {category} "
            f"excess={metrics['excess_ratio']:+.4f} "
            f"actual={metrics['actual_ratio']:.4f} "
            f"baseline={metrics['baseline_mean']:.4f} "
            f"cf_ok={valid_cfs}/{CF_COUNT} "
            f"({state.snapshot()['counts']})")
        return result
    finally:
        if not append_succeeded:
            state.rollback_reservation(item_id, category)


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset Runner
# ═══════════════════════════════════════════════════════════════════════════════

_SAVE_LOCK = threading.RLock()


def _official_path(dataset_name: str, output_dir: Optional[Path] = None) -> Path:
    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    return directory / f"{dataset_name}_pipeline.jsonl"


def load_official_rows(
    dataset_name: str,
    *,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """Strictly load the one durable truth map in official file order.

    Malformed JSON/UTF-8, blank rows, unterminated tails, non-ok rows,
    duplicate IDs, and conflicting IDs are all fatal. Nothing is silently
    skipped or repaired by a generation runner.
    """
    path = _official_path(dataset_name, output_dir)
    result = b_storage.scan_jsonl(
        path,
        validator=lambda row: validate_official_pipeline_row(
            row, expected_dataset=dataset_name
        ),
        repair=False,
    )
    return list(result.rows)


def _save_incremental(
    dataset_name: str,
    item: dict,
    *,
    output_dir: Optional[Path] = None,
):
    """Durably append one prevalidated official row and fsync it."""
    return b_storage.append_jsonl_row(_official_path(dataset_name, output_dir), item)


def _tracking_path(dataset_name: str, output_dir: Optional[Path] = None) -> Path:
    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    return directory / f"{dataset_name}_tracking.json"


def build_tracking_snapshot(
    dataset_name: str,
    state: PipelineState,
    *,
    output_dir: Optional[Path] = None,
    source_sha256: Optional[str] = None,
    config_fingerprint: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> dict:
    """Build a committed-only advisory snapshot from one locked state view."""
    directory = Path(output_dir) if output_dir is not None else state.output_dir
    source_digest = source_sha256 or state.source_sha256
    if source_digest is None:
        source_digest = source_hash_for_dataset(dataset_name)
    fingerprint = config_fingerprint or state.config_fingerprint
    if fingerprint is None:
        fingerprint = configuration_fingerprint(
            dataset_name, state.target, source_digest
        )
    moment = timestamp or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("tracking timestamp must be timezone-aware")

    committed = state.advisory_snapshot()
    committed_ids = committed["completed_ids"]
    pipeline_path = _official_path(dataset_name, directory)
    pipeline_hash = (
        b_storage.file_sha256(pipeline_path)
        if pipeline_path.exists()
        else b_storage.sha256_bytes(b"")
    )
    committed_digest = b_storage.sha256_bytes(
        b_storage.canonical_json_bytes(committed_ids)
    )
    return {
        "schema": TRACKING_SCHEMA,
        "schema_version": TRACKING_SCHEMA_VERSION,
        "advisory": True,
        "truth_source": "unique_status_ok_official_jsonl",
        "dataset": dataset_name,
        "counts": committed["counts"],
        "completed_count": committed["completed_count"],
        "completed_ids": committed_ids,
        # Kept only for old consumers. Its semantics are now committed IDs,
        # never classification attempts.
        "classified_ids": committed_ids,
        "classified_ids_semantics": "committed_status_ok_ids_only",
        "committed_ids_sha256": committed_digest,
        "pipeline_jsonl_sha256": pipeline_hash,
        "configuration_fingerprint": fingerprint,
        "source_sha256": source_digest,
        "updated_at_utc": moment.astimezone(timezone.utc).isoformat(),
    }


def _save_tracking(
    dataset_name: str,
    state: PipelineState,
    *,
    timestamp: Optional[datetime] = None,
) -> dict:
    """Atomically replace advisory tracking from committed state."""
    with _SAVE_LOCK:
        data = build_tracking_snapshot(
            dataset_name,
            state,
            output_dir=state.output_dir,
            timestamp=timestamp,
        )
        b_storage.atomic_replace_json(
            _tracking_path(dataset_name, state.output_dir), data
        )
        return data


def _load_tracking(dataset_name: str) -> Optional[dict]:
    """Read advisory tracking for diagnostics only; never for scheduling."""
    track_path = _tracking_path(dataset_name)
    if track_path.exists():
        return json.loads(track_path.read_text(encoding="utf-8"))
    return None


def _load_completed_ids(dataset_name: str) -> set[str]:
    """Return only IDs proven by strict official status-ok JSONL."""
    return {row["id"] for row in load_official_rows(dataset_name)}


def _load_ok_items(dataset_name: str) -> list[dict]:
    """Return the strict cumulative official rows used for stratification."""
    return load_official_rows(dataset_name)


def _validate_source_items(dataset_name: str, items: Iterable[dict]) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"source item {index} is not an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"source item {index} has no non-empty ID")
        if item_id in seen:
            raise ValueError(f"duplicate source ID: {item_id!r}")
        seen.add(item_id)
        if item.get("dataset") != dataset_name:
            raise ValueError(f"source dataset mismatch for {item_id!r}")
        prompt = item.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"source prompt is empty for {item_id!r}")


def _safe_fresh_dataset(dataset_name: str, output_dir: Path) -> None:
    """Backup then atomically empty official data while the scope lock is held."""
    pipeline_path = _official_path(dataset_name, output_dir)
    tracking_path = _tracking_path(dataset_name, output_dir)
    # Strict scan first: --fresh must never erase evidence it cannot understand.
    load_official_rows(dataset_name, output_dir=output_dir)
    backup_dir = output_dir / "backups"
    if pipeline_path.exists():
        b_storage.create_verified_backup(pipeline_path, backup_dir=backup_dir)
    if tracking_path.exists():
        b_storage.create_verified_backup(tracking_path, backup_dir=backup_dir)
    b_storage.atomic_replace_bytes(pipeline_path, b"")


def run_dataset(
    dataset_name: str,
    target: int,
    rate_limiter: RateLimiter,
    test_mode: bool = False,
    resume: bool = True,
    *,
    experiment_root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    source_sha256: Optional[str] = None,
) -> tuple[list[dict], PipelineState]:
    """Run one dataset under its process-wide Step 1–3 scope lock.

    ``resume=False`` performs a verified-backup, atomic fresh reset under the
    same lock. Pause/migration sentinels and maintenance are rechecked by the
    lock helper after acquisition, closing entry races.
    """
    if dataset_name not in LOADERS:
        raise ValueError(f"unknown dataset: {dataset_name!r}")
    root = Path(experiment_root) if experiment_root is not None else HERE
    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    scope = f"{PIPELINE_SCOPE_PREFIX}/{dataset_name}"
    with b_storage.scope_lock(root, scope):
        return _run_dataset_locked(
            dataset_name,
            target,
            rate_limiter,
            test_mode=test_mode,
            resume=resume,
            output_dir=directory,
            source_sha256=source_sha256,
        )


def _run_dataset_locked(
    dataset_name: str,
    target: int,
    rate_limiter: RateLimiter,
    *,
    test_mode: bool,
    resume: bool,
    output_dir: Path,
    source_sha256: Optional[str],
) -> tuple[list[dict], PipelineState]:
    log(f"\n{'=' * 70}")
    log(f"DATASET: {dataset_name}  |  Target: {target}/category  |  "
        f"Workers: {CONCURRENCY}  |  RPM: {RPM_TARGET}")
    log(f"{'=' * 70}")

    output_dir.mkdir(parents=True, exist_ok=True)
    loader = LOADERS[dataset_name]
    all_items = loader()
    _validate_source_items(dataset_name, all_items)
    log(f"Loaded {len(all_items)} prompts")

    source_digest = source_sha256 or source_hash_for_dataset(
        dataset_name, all_items
    )
    fingerprint = configuration_fingerprint(dataset_name, target, source_digest)

    if not resume:
        _safe_fresh_dataset(dataset_name, output_dir)
        log(f"Fresh reset completed with verified backups: {dataset_name}")

    # This strict scan is the sole startup reconstruction. Tracking is ignored.
    official_rows = load_official_rows(dataset_name, output_dir=output_dir)
    state = PipelineState(
        target,
        official_rows,
        dataset_name=dataset_name,
        source_sha256=source_digest,
        config_fingerprint=fingerprint,
        output_dir=output_dir,
    )
    completed_ids = state.committed_ids
    tracking_path = _tracking_path(dataset_name, output_dir)
    tracking_note = "present but ignored" if tracking_path.exists() else "absent"
    log(f"Resume truth: {len(completed_ids)} unique status-ok official rows; "
        f"tracking is {tracking_note}")
    log(f"Resume counts: {state.snapshot()['counts']}")

    # Refresh even a stale advisory snapshot from the just-scanned truth.
    _save_tracking(dataset_name, state)

    to_process = [
        item for item in all_items if item["id"] not in completed_ids
    ]
    random.seed(42)
    random.shuffle(to_process)

    if test_mode:
        to_process = to_process[:3]
        log(f"TEST MODE: processing {len(to_process)} prompts")

    log(f"To process: {len(to_process)} prompts "
        f"(skipping {len(all_items) - len(to_process)} official done IDs)")

    if not to_process:
        log("Nothing to process — every source item is already official.")
        return list(state.completed), state

    if state.num_full() >= len(CATEGORIES) - 1:
        log(f"{len(CATEGORIES) - 1}/{len(CATEGORIES)} categories already "
            "committed full — skipping.")
        return list(state.completed), state

    start_time = time.time()
    processed = 0
    outcome_counts: Counter[str] = Counter()

    executor = ThreadPoolExecutor(max_workers=CONCURRENCY)
    futures = {}
    batch_size = CONCURRENCY * 2
    pending = list(to_process)
    fatal_error: Optional[BaseException] = None

    def submit_next() -> bool:
        if not pending:
            return False
        # committed + reserved capacity stops new work while reservations finish.
        if state.num_at_capacity() >= len(CATEGORIES) - 1:
            return False
        item = pending.pop(0)
        future = executor.submit(
            process_one_prompt, item, state, rate_limiter, dataset_name
        )
        futures[future] = item
        return True

    try:
        for _ in range(min(batch_size, len(pending))):
            if not submit_next():
                break

        while futures:
            done_futures = {
                future for future in list(futures) if future.done()
            }
            if not done_futures:
                time.sleep(0.1)
                continue

            for future in done_futures:
                item = futures.pop(future)
                processed += 1
                try:
                    result = future.result()
                    outcome = state.consume_outcome(item["id"])
                    if result is not None:
                        outcome = outcome or "ok"
                    else:
                        outcome = outcome or "failed_unknown"
                    outcome_counts[outcome] += 1
                except FatalPipelineError as exc:
                    outcome_counts["fatal"] += 1
                    fatal_error = exc
                    log(f"[{dataset_name}] FATAL: {item['id']} — {exc}")
                    break
                except Exception as exc:
                    outcome_counts["exception"] += 1
                    log(f"[{dataset_name}] EXCEPTION: {item['id']} — {exc}")
                    traceback.print_exc()

                if pending:
                    submit_next()

            if fatal_error is not None:
                for future in futures:
                    future.cancel()
                break

            elapsed = time.time() - start_time
            if processed % 20 == 0 and processed > 0:
                rate = processed / elapsed * 60 if elapsed > 0 else 0
                snap = state.snapshot()
                log(f"[{dataset_name}] Progress: {processed} finished, "
                    f"{snap['newly_completed']} new ok, "
                    f"{sum(v for k, v in outcome_counts.items() if k != 'ok')} "
                    f"non-ok | {rate:.0f} items/min | counts: {snap['counts']} | "
                    f"reserved: {snap['reserved_counts']}")

            # Do not submit after five categories have committed/reserved capacity.
            # Existing reservations finish; if one rolls back, a later completion
            # opens submission again.
            if (
                state.num_full() >= len(CATEGORIES) - 1
                and state.reservation_count() == 0
            ):
                log(f"[{dataset_name}] {len(CATEGORIES) - 1}/{len(CATEGORIES)} "
                    "categories committed full — early stop.")
                for future in futures:
                    future.cancel()
                break
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    if fatal_error is not None:
        raise fatal_error

    # All workers are now finished, so this final advisory snapshot has no
    # active reservations and exactly matches the official file.
    _save_tracking(dataset_name, state)

    elapsed = time.time() - start_time
    snap = state.snapshot()
    log(f"\n[{dataset_name}] DONE in {elapsed / 60:.1f} min")
    log(f"  Processed this run: {processed}  |  New OK: "
        f"{snap['newly_completed']}  |  Cumulative OK: {snap['committed']}")
    log(f"  Outcomes: {dict(sorted(outcome_counts.items()))}")
    log(f"  Final committed counts: {snap['counts']}")

    return list(state.completed), state


# ═══════════════════════════════════════════════════════════════════════════════
# Step 3: Stratification
# ═══════════════════════════════════════════════════════════════════════════════

def stratify_by_theme(items: list[dict], n_levels: int = 5) -> list[dict]:
    """Split items within each theme into N equal levels by excess_ratio.

    Items without a valid excess_ratio are excluded.
    """
    stratified = []

    for cat_name in CATEGORIES.values():
        pool = [
            item for item in items
            if item.get("category") == cat_name
            and item.get("excess_ratio") is not None
        ]
        if not pool:
            log(f"  {cat_name}: 0 items — skipping stratification")
            continue

        # Sort by excess_ratio (high to low): L1 = highest contribution,
        # L5 = lowest — aligns with Experiment A (L1=polish … L5=keywords).
        pool.sort(key=lambda x: x["excess_ratio"], reverse=True)
        n = len(pool)
        level_size = n // n_levels

        for level_idx in range(n_levels):
            start = level_idx * level_size
            if level_idx == n_levels - 1:
                end = n  # last level gets the remainder
            else:
                end = start + level_size

            level_name = f"L{level_idx + 1}"
            for item in pool[start:end]:
                item["level"] = level_name
                stratified.append(item)

        # Log distribution
        for level_idx in range(n_levels):
            level_name = f"L{level_idx + 1}"
            level_items = [
                i for i in stratified
                if i.get("category") == cat_name and i.get("level") == level_name
            ]
            if level_items:
                ratios = [i["excess_ratio"] for i in level_items]
                log(f"  {cat_name} {level_name}: n={len(level_items)} "
                    f"range=[{min(ratios):+.4f}, {max(ratios):+.4f}] "
                    f"mean={sum(ratios)/len(ratios):+.4f}")

    return stratified


def build_pipeline_summary(
    datasets: Iterable[str],
    *,
    output_dir: Optional[Path] = None,
) -> dict:
    """Derive every summary count from strict official JSONL, never tracking."""
    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    summary: dict[str, dict] = {}
    for dataset_name in datasets:
        rows = load_official_rows(dataset_name, output_dir=directory)
        counts = Counter(row["category"] for row in rows)
        completed_ids = sorted(row["id"] for row in rows)
        path = _official_path(dataset_name, directory)
        summary[dataset_name] = {
            "target_per_category": TARGETS[dataset_name],
            "counts": {
                category: counts.get(category, 0)
                for category in CATEGORIES.values()
            },
            "completed": len(completed_ids),
            # Compatibility field with corrected semantics.
            "classified": len(completed_ids),
            "classified_semantics": "committed_status_ok_ids_only",
            "committed_ids_sha256": b_storage.sha256_bytes(
                b_storage.canonical_json_bytes(completed_ids)
            ),
            "pipeline_jsonl_sha256": (
                b_storage.file_sha256(path)
                if path.exists()
                else b_storage.sha256_bytes(b"")
            ),
            "derived_from": "strict_unique_status_ok_official_jsonl",
        }
    return summary


def save_pipeline_summary(
    datasets: Iterable[str],
    *,
    output_dir: Optional[Path] = None,
) -> dict:
    directory = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    summary = build_pipeline_summary(datasets, output_dir=directory)
    b_storage.atomic_replace_json(directory / "pipeline_summary.json", summary)
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════════

_LOG_LOCK = threading.Lock()


def log(msg: str):
    """Thread-safe print + append to log file."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / "pipeline.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Experiment B — Unified Pipeline (Steps 1-3)"
    )
    parser.add_argument("--test", action="store_true",
                        help="Test mode: process only 3 prompts per dataset")
    parser.add_argument("--dry-run", action="store_true",
                        help="Data loading only, no API calls")
    parser.add_argument(
        "--dataset",
        choices=tuple(TARGETS),
        default=None,
        help="Process only one dataset",
    )
    parser.add_argument("--fresh", action="store_true",
                        help="Backup and atomically reset previous official results")
    parser.add_argument("--no-stratify", action="store_true",
                        help="Skip stratification (Step 3)")
    args = parser.parse_args()

    datasets_to_run = [args.dataset] if args.dataset else list(TARGETS)

    # Dry-run is read-only/offline and remains available while PAUSED. Every
    # generation-capable entry checks before any output/log mutation; scope_lock
    # checks again after acquiring each dataset lock to close races.
    if not args.dry_run:
        b_storage.check_storage_sentinels(HERE)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log("Experiment B — Unified Pipeline (Steps 1-3)")
    log(f"Model: {PIPELINE_MODEL}  |  Workers: {CONCURRENCY}  |  "
        f"RPM: {RPM_TARGET}  |  CFs: {CF_COUNT}/prompt")
    log("Categories: 6 themes, full pipeline for all")
    log(f"Test: {args.test}  |  Dry-run: {args.dry_run}  |  "
        f"Fresh: {args.fresh}")

    if args.dry_run:
        log("\n=== DRY RUN — data loading only ===\n")
        for dataset_name in datasets_to_run:
            items = LOADERS[dataset_name]()
            _validate_source_items(dataset_name, items)
            log(f"{dataset_name}: {len(items)} prompts loaded; "
                f"source_sha256={source_hash_for_dataset(dataset_name, items)}")
        log("\nDry run complete.")
        return

    rate_limiter = RateLimiter(rpm=RPM_TARGET)
    all_states: dict[str, PipelineState] = {}
    for dataset_name in datasets_to_run:
        _, state = run_dataset(
            dataset_name,
            TARGETS[dataset_name],
            rate_limiter,
            test_mode=args.test,
            resume=not args.fresh,
            experiment_root=HERE,
            output_dir=OUTPUT_DIR,
        )
        all_states[dataset_name] = state

    log("\n" + "=" * 70)
    log("PIPELINE COMPLETE — Official Results Summary")
    log("=" * 70)
    total_ok = 0
    for dataset_name in datasets_to_run:
        counts = all_states[dataset_name].snapshot()["counts"]
        ok_count = sum(counts.values())
        total_ok += ok_count
        log(f"\n{dataset_name}: {ok_count} cumulative official OK items")
        for category in CATEGORIES.values():
            count = counts.get(category, 0)
            target = TARGETS[dataset_name]
            outcome = (
                "TARGET_MET" if count >= target
                else f"SHORTFALL {target - count}"
            )
            log(f"  {category}: {count} [{outcome}]")
    log(f"\nTotal official OK items: {total_ok}")

    if not args.no_stratify:
        log("\n" + "=" * 70)
        log("STEP 3: Stratification (5 levels per theme)")
        log("=" * 70)
        for dataset_name in datasets_to_run:
            scope = f"{PIPELINE_SCOPE_PREFIX}/{dataset_name}"
            with b_storage.scope_lock(HERE, scope):
                ok_items = load_official_rows(
                    dataset_name, output_dir=OUTPUT_DIR
                )
                if not ok_items:
                    log(f"\n{dataset_name}: no official OK items — "
                        "skipping stratification")
                    continue
                stratified = stratify_by_theme(ok_items)
                out_path = OUTPUT_DIR / f"{dataset_name}_stratified.jsonl"
                b_storage.atomic_replace_jsonl(out_path, stratified)
                log(f"\n{dataset_name}: {len(stratified)} items stratified → "
                    f"{out_path}")
                for category in CATEGORIES.values():
                    for level_number in range(1, 6):
                        level_name = f"L{level_number}"
                        pool = [
                            item for item in stratified
                            if item.get("category") == category
                            and item.get("level") == level_name
                        ]
                        if pool:
                            ratios = [item["excess_ratio"] for item in pool]
                            log(f"  {category} {level_name}: n={len(pool)} "
                                f"range=[{min(ratios):+.4f}, "
                                f"{max(ratios):+.4f}]")

    # Freeze all Step 1–3 scopes while deriving and atomically replacing summary.
    with b_storage.maintenance_lock(HERE):
        b_storage.check_migration_sentinel(HERE)
        # The canonical summary always covers every official dataset, even when
        # this invocation generated only one of them.
        save_pipeline_summary(TARGETS, output_dir=OUTPUT_DIR)
    log(f"\nSummary derived from strict official JSONL → "
        f"{OUTPUT_DIR / 'pipeline_summary.json'}")

    log("\n" + "=" * 70)
    log("ALL DONE.")
    log("=" * 70)


if __name__ == "__main__":
    main()
