# -*- coding: utf-8 -*-
"""Experiment B — Step 1: Theme classification of prompts.

Classify prompts from 3 datasets (10k_prompts / WildChat / OASST1) into
6 themes using topic-mapping + Claude Opus 4.7 model classification.

Usage::

    # Dry run (test data loading + topic mapping only, no API calls)
    python classify_prompts.py --dry-run

    # Test mode (classify only 10 prompts per dataset)
    python classify_prompts.py --test

    # Full run
    python classify_prompts.py

    # Single dataset
    python classify_prompts.py --dataset wildchat

Design notes:
    - 10k_prompts has ``topic`` field → pre-mapped, model fills short categories
    - WildChat & OASST1 → fully model-classified
    - Concurrency = 8, RPM target = 48 (leaves 12 RPM for other conversations)
    - Incremental save after each batch → resume-safe
    - Early stopping: stop classifying when all categories have enough + buffer
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    # Reconfigure stdout to use UTF-8, avoiding GBK encoding errors
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

# ── Paths ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
DATA_DIR = PROJECT / "data" / "experiment_b"
NEW_API = PROJECT / "clients" / "client_legacy.py"
PYTHON = sys.executable  # python
OUTPUT_DIR = HERE / "outputs"
LOG_DIR = HERE / "logs"

# ── Model ──────────────────────────────────────────────────────────────────
CLASSIFY_MODEL = "claude-opus-4-7"
API_TIMEOUT = 120  # seconds per call
MAX_OUTPUT_TOKENS = 64  # classification only needs a short label
REASONING_EFFORT = "low"  # simple task, no deep reasoning needed

# ── Concurrency & Rate Limiting ────────────────────────────────────────────
CONCURRENCY = 8
RPM_TARGET = 48  # target calls/min (60 total, leave 12 for other conversations)
RPM_WINDOW = 60  # seconds

# ── Sampling targets ───────────────────────────────────────────────────────
TARGETS = {
    "10k_prompts": 500,
    "wildchat": 500,
    "oasst1": 300,
}
BUFFER_RATIO = 0.05  # 5% extra to account for noise

# ── Six categories ─────────────────────────────────────────────────────────
CATEGORIES = {
    "1": "技术实现",
    "2": "专业知识",
    "3": "推理分析",
    "4": "创意生成",
    "5": "艺术设计",
    "6": "经验情境",
}

CATEGORY_NAMES = {
    "技术实现": "Technical Implementation",
    "专业知识": "Domain Knowledge",
    "推理分析": "Reasoning & Analysis",
    "创意生成": "Creative Generation",
    "艺术设计": "Art & Design",
    "经验情境": "Experiential Context",
}

# ── Topic → Category mapping for 10k_prompts ───────────────────────────────
TOPIC_TO_CATEGORY = {
    "Software Development": "技术实现",
    "Math": "推理分析",
    "Science and Technology": "推理分析",
    "Legal and Government": "专业知识",
    "Environmental Issues": "专业知识",
    "Health and Wellness": "专业知识",
    "Literature and Arts": "创意生成",
    "Business and Marketing": "经验情境",
    "Travel and Leisure": "经验情境",
    # "Others" → model classification
}
TOPICS_NEED_MODEL = {"Others"}  # topics that always need model classification

# ── Classification prompt ──────────────────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════════
# Rate Limiter
# ═══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Sliding-window rate limiter shared across threads."""

    def __init__(self, rpm: int = RPM_TARGET, window: float = RPM_WINDOW):
        self.rpm = rpm
        self.window = window
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self):
        """Block until a call slot is available."""
        with self._lock:
            now = time.time()
            # Evict timestamps outside the window
            while self._timestamps and now - self._timestamps[0] >= self.window:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.rpm:
                sleep_for = self._timestamps[0] + self.window - now + 0.1
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.time()
                while self._timestamps and now - self._timestamps[0] >= self.window:
                    self._timestamps.popleft()
            self._timestamps.append(time.time())

    @property
    def recent_count(self) -> int:
        """Number of calls in the current window (approx, no lock)."""
        now = time.time()
        return sum(1 for t in self._timestamps if now - t < self.window)


# ═══════════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════════

def load_10k_prompts() -> list[dict]:
    """Load prompts from 10k_prompts/full.jsonl."""
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
                "category": None,       # to be filled
                "classification_method": None,
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
                "category": None,
                "classification_method": None,
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
                "category": None,
                "classification_method": None,
            })
    return items


LOADERS = {
    "10k_prompts": load_10k_prompts,
    "wildchat": load_wildchat,
    "oasst1": load_oasst1,
}


# ═══════════════════════════════════════════════════════════════════════════
# Topic-based pre-classification (10k_prompts only)
# ═══════════════════════════════════════════════════════════════════════════

def pre_classify_by_topic(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pre-classify items using topic→category mapping.

    Returns:
        (classified, unclassified) — items with a known topic are classified;
        items with ``topic == "Others"`` or unknown topic need model classification.
    """
    classified = []
    unclassified = []

    for item in items:
        topic = item.get("original_topic", "Unknown")
        cat = TOPIC_TO_CATEGORY.get(topic)
        if cat is not None:
            item["category"] = cat
            item["classification_method"] = "topic_mapping"
            classified.append(item)
        else:
            unclassified.append(item)

    return classified, unclassified


# ═══════════════════════════════════════════════════════════════════════════
# Model Classification
# ═══════════════════════════════════════════════════════════════════════════

def _build_classify_prompt(prompt_text: str) -> str:
    """Build the user message for a single classification call."""
    # Truncate very long prompts (model doesn't need full text to classify)
    truncated = prompt_text[:2000] if len(prompt_text) > 2000 else prompt_text
    return (
        f"Classify the following user prompt into one of the 6 categories.\n"
        f"Reply with ONLY the category number (1-6).\n\n"
        f"[Prompt]: {truncated}"
    )


def call_api(prompt: str, rate_limiter: RateLimiter) -> tuple[bool, str]:
    """Call Claude Opus 4.7 for classification. Returns (success, output)."""
    rate_limiter.acquire()
    classify_prompt = _build_classify_prompt(prompt)
    try:
        proc = subprocess.run(
            [
                PYTHON, "-u", str(NEW_API),
                "--timeout", str(API_TIMEOUT),
                "ask", classify_prompt,
                "--model", CLASSIFY_MODEL,
                "--system", CLASSIFY_SYSTEM,
                "--max-output-tokens", str(MAX_OUTPUT_TOKENS),
                "--reasoning-effort", REASONING_EFFORT,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=API_TIMEOUT + 30,
            cwd=str(NEW_API.parent),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return True, proc.stdout.strip()
        err = proc.stderr.strip()[:200] if proc.stderr else f"rc={proc.returncode}"
        return False, err
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)[:200]


def parse_category(output: str) -> Optional[str]:
    """Parse model output to extract category label (1-6).

    Handles common variations: '1', '1.', 'Category 1', '技术实现', etc.
    """
    text = output.strip()
    # Try direct digit match
    for ch in text:
        if ch in "123456":
            return CATEGORIES[ch]
    # Try category name match
    for num, name in CATEGORIES.items():
        if name in text:
            return name
    # Return first digit found anywhere as fallback
    import re
    digits = re.findall(r"[1-6]", text)
    if digits:
        return CATEGORIES[digits[0]]
    return None


def classify_one(item: dict, rate_limiter: RateLimiter) -> dict:
    """Classify a single item using the model. Updates item in place."""
    ok, output = call_api(item["prompt"], rate_limiter)
    if ok:
        cat = parse_category(output)
        if cat:
            item["category"] = cat
            item["classification_method"] = "model"
            item["model_raw_output"] = output[:100]
        else:
            item["category"] = None
            item["classification_method"] = "model_parse_failed"
            item["model_raw_output"] = output[:100]
    else:
        item["category"] = None
        item["classification_method"] = "model_error"
        item["model_error"] = output[:200]
    return item


# ═══════════════════════════════════════════════════════════════════════════
# Category-aware batch classification
# ═══════════════════════════════════════════════════════════════════════════

def _category_counts(items: list[dict]) -> Counter:
    """Count classified items per category."""
    c = Counter()
    for item in items:
        if item["category"]:
            c[item["category"]] += 1
    return c


def _categories_needed(counts: Counter, target: int, buffer: int = 0) -> set[str]:
    """Return set of categories that haven't reached target + buffer yet."""
    needed = set()
    for cat_name in CATEGORIES.values():
        if counts.get(cat_name, 0) < target + buffer:
            needed.add(cat_name)
    return needed


def classify_dataset(
    items: list[dict],
    dataset_name: str,
    target: int,
    rate_limiter: RateLimiter,
    pre_classified: list[dict] | None = None,
    test_mode: bool = False,
) -> list[dict]:
    """Classify items with early stopping when all categories are filled.

    Args:
        items: All items from the dataset (unclassified).
        dataset_name: For logging.
        target: Items needed per category.
        rate_limiter: Shared rate limiter.
        pre_classified: Items already classified via topic mapping.
        test_mode: If True, only classify 10 items.

    Returns:
        All classified items (pre_classified + newly classified).
    """
    all_classified = list(pre_classified) if pre_classified else []
    buffer = max(1, int(target * BUFFER_RATIO))

    counts = _category_counts(all_classified)
    needed = _categories_needed(counts, target, buffer)

    log(f"\n{'='*60}")
    log(f"Dataset: {dataset_name}  |  Target: {target}/category  |  Buffer: {buffer}")
    log(f"Pre-classified: {len(all_classified)}")
    log(f"Initial counts: {dict(counts)}")
    log(f"Categories to fill: {needed}")

    if not needed:
        log("All categories already filled — skipping model classification.")
        return all_classified

    # ── Filter items that need classification ────────────────────────────
    # Remove already-classified items (by id)
    classified_ids = {item["id"] for item in all_classified}
    to_classify = [item for item in items if item["id"] not in classified_ids]

    # Shuffle for random sampling
    random.seed(42)
    random.shuffle(to_classify)

    if test_mode:
        to_classify = to_classify[:10]
        log(f"TEST MODE: only classifying {len(to_classify)} items")

    log(f"Items to classify: {len(to_classify)}")

    # ── Process in batches ───────────────────────────────────────────────
    BATCH_SIZE = CONCURRENCY * 5  # 40 items per batch
    total_done = 0
    start_time = time.time()

    for batch_start in range(0, len(to_classify), BATCH_SIZE):
        # Check if we still need more
        needed = _categories_needed(counts, target, buffer)
        if not needed:
            log(f"All categories filled! Stopping early at {total_done}/{len(to_classify)} classified.")
            break

        batch = to_classify[batch_start:batch_start + BATCH_SIZE]
        batch_results = []

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            futures = {
                executor.submit(classify_one, item, rate_limiter): item
                for item in batch
            }
            for future in as_completed(futures):
                result = future.result()
                batch_results.append(result)

        # Update counts
        for item in batch_results:
            if item["category"]:
                counts[item["category"]] += 1
            all_classified.append(item)
            total_done += 1

        # Progress report
        elapsed = time.time() - start_time
        rate = total_done / elapsed * 60 if elapsed > 0 else 0
        log(
            f"  [{dataset_name}] {total_done}/{len(to_classify)} done | "
            f"{rate:.0f} calls/min | counts: {dict(counts)}"
        )

        # Incremental save
        _save_incremental(dataset_name, batch_results)

        # Small delay between batches to smooth out rate
        time.sleep(0.5)

    # ── Final report ─────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    log(f"\n[{dataset_name}] Classification complete in {elapsed/60:.1f} min")
    log(f"Final counts: {dict(counts)}")
    for cat_name in CATEGORIES.values():
        n = counts.get(cat_name, 0)
        status = "[OK]" if n >= target else f"[SHORT by {target - n}]"
        log(f"  {cat_name}: {n} {status}")

    return all_classified


# ═══════════════════════════════════════════════════════════════════════════
# Sampling
# ═══════════════════════════════════════════════════════════════════════════

def sample_per_category(items: list[dict], target: int) -> list[dict]:
    """Select exactly `target` items per category by random sampling."""
    random.seed(123)
    selected = []
    for cat_name in CATEGORIES.values():
        pool = [item for item in items if item["category"] == cat_name]
        if len(pool) <= target:
            selected.extend(pool)
        else:
            selected.extend(random.sample(pool, target))
    return selected


# ═══════════════════════════════════════════════════════════════════════════
# I/O helpers
# ═══════════════════════════════════════════════════════════════════════════

def _save_incremental(dataset_name: str, items: list[dict]):
    """Append newly classified items to the output JSONL."""
    out_path = OUTPUT_DIR / f"{dataset_name}_classified.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def save_final(dataset_name: str, items: list[dict]):
    """Save the final sampled output."""
    out_path = OUTPUT_DIR / f"{dataset_name}_sampled.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for item in items:
            # Strip internal fields
            clean = {
                "id": item["id"],
                "dataset": item["dataset"],
                "prompt": item["prompt"],
                "category": item["category"],
            }
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")
    log(f"Saved {len(items)} items → {out_path}")


def save_summary(all_sampled: dict[str, list[dict]]):
    """Save a JSON summary of classification results."""
    summary = {}
    for ds_name, items in all_sampled.items():
        summary[ds_name] = {
            "total": len(items),
            "per_category": dict(Counter(item["category"] for item in items)),
        }
    summary_path = OUTPUT_DIR / "classification_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log(f"Summary saved → {summary_path}")


# ═══════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════

_LOG_LOCK = threading.Lock()


def log(msg: str):
    """Thread-safe print + append to log file."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
        log_path = LOG_DIR / "classify.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Experiment B — Theme Classification")
    parser.add_argument("--dry-run", action="store_true",
                        help="Test data loading and topic mapping only (no API calls)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: classify only 10 items per dataset")
    parser.add_argument("--dataset", type=str, default=None,
                        help="Process only one dataset (10k_prompts | wildchat | oasst1)")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not save intermediate results (for testing)")
    args = parser.parse_args()

    # Ensure output directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 60)
    log("Experiment B — Theme Classification")
    log(f"Model: {CLASSIFY_MODEL}  |  Concurrency: {CONCURRENCY}  |  RPM target: {RPM_TARGET}")
    log(f"Test mode: {args.test}  |  Dry run: {args.dry_run}")

    datasets_to_run = [args.dataset] if args.dataset else list(TARGETS.keys())

    rate_limiter = RateLimiter(rpm=RPM_TARGET)
    all_sampled: dict[str, list[dict]] = {}

    for ds_name in datasets_to_run:
        log(f"\n{'─'*50}")
        log(f"Loading dataset: {ds_name}")

        # ── Load ─────────────────────────────────────────────────────────
        loader = LOADERS[ds_name]
        all_items = loader()
        log(f"Loaded {len(all_items)} prompts (min 10 chars)")

        target = TARGETS[ds_name]

        # ── Pre-classify (10k_prompts only) ──────────────────────────────
        pre_classified = []
        to_classify = all_items

        if ds_name == "10k_prompts":
            pre_classified, to_classify = pre_classify_by_topic(all_items)
            log(f"Topic-mapped: {len(pre_classified)}, Need model: {len(to_classify)}")
            pre_counts = _category_counts(pre_classified)
            log(f"Pre-map counts: {dict(pre_counts)}")

        if args.dry_run:
            log("DRY RUN — skipping model classification.")
            # Show what we have from pre-classification
            all_classified = pre_classified + to_classify  # unclassified stay uncategorized
            sampled = sample_per_category(
                [i for i in all_classified if i["category"]], target
            )
            all_sampled[ds_name] = sampled
            continue

        # ── Model classify ───────────────────────────────────────────────
        # Clear previous incremental output for this dataset
        inc_path = OUTPUT_DIR / f"{ds_name}_classified.jsonl"
        if inc_path.exists() and not args.test:
            inc_path.unlink()

        all_classified = classify_dataset(
            items=to_classify,
            dataset_name=ds_name,
            target=target,
            rate_limiter=rate_limiter,
            pre_classified=pre_classified,
            test_mode=args.test,
        )

        # ── Sample ───────────────────────────────────────────────────────
        sampled = sample_per_category(all_classified, target)
        all_sampled[ds_name] = sampled

        # ── Report ───────────────────────────────────────────────────────
        counts = _category_counts(sampled)
        log(f"\n[{ds_name}] Sampled {len(sampled)} items:")
        for cat_name in CATEGORIES.values():
            log(f"  {cat_name}: {counts.get(cat_name, 0)}")

        if not args.no_save:
            save_final(ds_name, sampled)

    # ── Final summary ────────────────────────────────────────────────────
    if not args.no_save and not args.dry_run:
        save_summary(all_sampled)

    log("\n" + "=" * 60)
    log("Classification complete!")
    for ds_name, items in all_sampled.items():
        log(f"  {ds_name}: {len(items)} sampled")
    log(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
