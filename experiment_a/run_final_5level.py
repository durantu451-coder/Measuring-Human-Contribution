# -*- coding: utf-8 -*-
r"""Final 5-level gradient experiment — 9 models × 4 domains × up to 2000 items.

Usage::

    # Single model (resume-safe):
    python run_final_5level.py --model claude-sonnet-5

    # Batch mode: run N items, then review (default 10):
    python run_final_5level.py --model claude-sonnet-5 --batch 10

    # Sequential run of all resolved models (one at a time):
    python run_final_5level.py --run-all --batch 10

    # Historical cleanup + resume (never use --fresh):
    python repair_token_cap_window.py --prepare
    python run_final_5level.py --model=claude-sonnet-5
"""

from __future__ import annotations

# Max items per domain, processed in rounds of ROUND_SIZE across all 4 domains
MAX_PER_DOMAIN = 2000
ROUND_SIZE = 50

import csv, hashlib, json, os, random, re, statistics, sys, time
from contextlib import contextmanager

# Fix Windows GBK encoding crashes on emoji in API output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent          # experiment_a/
PROJECT = HERE.parent                            # project root ()
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from human_contribution.multi_model_adapter import MultiModelAdapter
from human_contribution.copilot_responses_adapter import CopilotResponsesAdapter
from experiment_a.outage_guard import (
    OUTAGE_EXIT_CODE,
    ConfirmedOutage,
    GuardedAdapter,
    OutageCircuitBreaker,
)
from human_contribution.metrics import (
    CounterfactualSample,
    build_counterfactual_baseline_profile,
    compute_spearman,
    evaluate_session_profile,
)

DATA_DIR = PROJECT / "data" / "experiment_a"   # this experiment's input datasets
RESULTS_DIR = HERE / "results"
DEBUG_DIR = HERE / "debug_logs"
API3RD_CUTOVER_MANIFEST = HERE / "backend_c_cutover_manifest.json"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

LEVELS = ["L1", "L2", "L3", "L4", "L5"]
CF_COUNT = 5
_COMPRESSORS = ("zlib", "bz2", "lzma")  # for per-compressor Krippendorff Alpha
GPT_PROTOCOLS = {
    "gpt-5.5": {
        "route": "backend_c", "gateway": "auto", "max_output_tokens": 4096,
        "client": str((PROJECT / "clients" / "client_gpt_multi_origin.py").resolve()),
        "historical_protocols": (("backend_b", 1),),
    },
    "gpt-5.6-sol": {
        "route": "backend_c", "gateway": "auto", "max_output_tokens": 4096,
        "client": str((PROJECT / "clients" / "client_gpt_multi_origin.py").resolve()),
        "historical_protocols": (("backend_b", 2),),
    },
}
COPILOT_PROTOCOLS = {
    model: {
        "route": "copilot",
        "call_route": "copilot-2.2.15-formal",
        "gateway": "local_slot",
        "max_output_tokens": 4096,
        "client": str((PROJECT / "human_contribution" / "copilot_responses_adapter.py").resolve()),
    }
    for model in ("claude-sonnet-5", "claude-opus-4-8", "gemini-3.6-flash")
}
MODEL_PROTOCOLS = {**GPT_PROTOCOLS, **COPILOT_PROTOCOLS}


def _make_health_adapter(model_name: str, *, timeout: int, sleep_seconds: float):
    """Construct a probe adapter for the model's exact formal route."""
    protocol = MODEL_PROTOCOLS.get(model_name)
    if protocol is not None and protocol["route"] == "copilot":
        return CopilotResponsesAdapter(
            model_name=model_name,
            max_output_tokens=protocol["max_output_tokens"],
            reasoning_effort="low",
            slot_capacity=4,
            retries=2,
            timeout_seconds=timeout,
            sleep_seconds=sleep_seconds,
        )
    return MultiModelAdapter(
        model_name=model_name,
        api_timeout=timeout,
        sleep_seconds=sleep_seconds,
        backend_pin=(
            int(protocol["gateway"])
            if protocol is not None and protocol["route"] == "backend_b"
            else None
        ),
        gpt_route=(
            protocol["route"]
            if protocol is not None and protocol["route"] in {"backend_b", "backend_c"}
            else None
        ),
        max_output_tokens=(
            int(protocol["max_output_tokens"])
            if protocol is not None
            else 4096
        ),
    )

# ── Quality thresholds ─────────────────────────────────────────────────
MIN_OUTPUT_CHARS = 80       # Output shorter than this is suspicious
MIN_CF_OUTPUT_CHARS = 50    # CF output shorter than this is likely broken
MIN_VALID_CFS = 3           # Need at least this many valid CFs for a meaningful baseline

# ── 9-model roster with fallback chains ─────────────────────────────────
_MODEL_POOL = {
    "gpt":    [["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"],
               ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex"],
               ["gpt-5.4", "gpt-5.3-codex"]],
    "claude": [["claude-sonnet-5", "claude-opus-5"],
               ["claude-opus-5", "claude-opus-4-8"],
               ["claude-opus-4-8", "claude-opus-4-7"]],
    "gemini": [["gemini-3.6-flash", "gemini-3.5-flash"],
               ["gemini-3.5-flash", "gemini-3.1-pro-preview"],
               ["gemini-3.1-pro-preview", "gemini-3.5-flash"]],
}


def _resolve_models() -> list[str]:
    """Resolve 9 models: test each candidate, fall back on failure."""
    from human_contribution.multi_model_adapter import MultiModelAdapter
    resolved = []
    for slot_idx in range(3):
        for vendor in ["claude", "gemini", "gpt"]:
            slot = _MODEL_POOL[vendor][slot_idx]
            picked = None
            for candidate in slot:
                try:
                    a = _make_health_adapter(candidate, timeout=45, sleep_seconds=0.3)
                    resp = a.generate("test")
                    if resp and len(resp) > 0:
                        picked = candidate
                        break
                except Exception:
                    continue
            if picked:
                resolved.append(picked)
                print(f"  [{vendor}:{slot_idx}] -> {picked}")
            else:
                print(f"  [{vendor}:{slot_idx}] -> ALL FAILED: {slot}")
    return resolved


ALL_MODELS: list[str] = []


def _model_tag(model_name: str) -> str:
    if "gpt" in model_name: return "gpt"
    if "claude" in model_name: return "claude"
    if "gemini" in model_name: return "gemini"
    return model_name.split("-")[0]


def _extract_keywords(text: str, n: int = 3) -> str:
    words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text)
    stop = {'The','This','That','These','Those','With','From','Into','Their',
            'They','Have','Been','Were','Also','Such','Each','Some','Both',
            'When','While','Which','Where','Other','After','About','Above',
            'Below','Under','During','Between','Through','Without','Within',
            'Using','Based','However','Therefore','Thus','Here','There','More',
            'Its','Can','May','Will','Has','One','Two','New','Due','Over'}
    seen = set(); uniq = []
    for k in words:
        if k.lower() not in seen:
            seen.add(k.lower()); uniq.append(k)
    return ", ".join(uniq[:n]) if uniq else " ".join(text.split()[:3])


def _save(path: Path, data: list[dict]) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _is_valid_output(text: str, min_chars: int = MIN_OUTPUT_CHARS) -> bool:
    """Check if a generated output looks valid (not an error or garbage)."""
    if not text or len(text.strip()) < min_chars:
        return False
    t = text.strip()
    # Error markers
    if t.startswith("[ERROR") or t.startswith("Error:") or t.startswith("[API"):
        return False
    # Garbage: very high repetition
    if len(set(t.split())) < 5 and len(t.split()) > 20:
        return False
    return True


def _gen(adapter: MultiModelAdapter, prompt: str, label: str = "",
         min_chars: int = MIN_OUTPUT_CHARS) -> tuple[str, dict | None]:
    """Generate with validation and return output plus API provenance.

    Raises on failure so the item is skipped (not saved) and auto-backfilled
    on the next run. Incomplete Responses calls are rejected by the adapter
    before they reach this function.
    """
    try:
        out = adapter.generate(prompt).strip()
        metadata = adapter.consume_last_response_metadata()
    except Exception as e:
        print(f"    [{label}] ERROR: {e}")
        raise

    if not _is_valid_output(out, min_chars):
        print(f"    [{label}] INVALID ({len(out)} chars) — raising to skip item")
        raise RuntimeError(f"{label}: invalid output ({len(out)} chars): {out[:80]!r}")
    print(f"    [{label}] done ({len(out)} chars)")
    return out, metadata


def _robust_reconstruct(
    adapter: MultiModelAdapter, gold: str, n: int = CF_COUNT,
    max_retries: int = 3
) -> tuple[list[str], dict | None]:
    """Reconstruct prompts with retries, returning prompts and provenance."""
    import traceback

    for attempt in range(max_retries):
        try:
            prompts = list(adapter.reconstruct_prompts(gold, n))
            metadata = adapter.consume_last_response_metadata()
            # Validate: each prompt should be non-empty and reasonably long
            valid = [p for p in prompts if p.strip() and len(p.strip()) >= 10]
            if len(valid) >= n:
                return valid[:n], metadata
            print(f"    [cf reconstruct] attempt {attempt+1}: only {len(valid)}/{n} valid prompts, retrying...")
        except ConfirmedOutage:
            raise
        except Exception as e:
            print(f"    [cf reconstruct] attempt {attempt+1}: {e}")
            traceback.print_exc()
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))  # Backoff: 2s, 4s

    # Fallback: simple template-based prompts
    print(f"    [cf reconstruct] FALLBACK: using template prompts")
    words = gold.split()
    if len(words) > 30:
        snippet = " ".join(words[:30]) + "..."
    else:
        snippet = gold[:200]
    fallback_prompts = [
        f"Write a text similar to the following:\n\n{snippet}",
        f"Generate content in the style of:\n\n{snippet}",
        f"Create a passage on this topic:\n\n{snippet}",
        f"Produce an article like:\n\n{snippet}",
        f"Write about:\n\n{snippet}",
    ][:n]
    return fallback_prompts, {
        "api": "local_fallback",
        "status": "fallback",
        "attempts": max_retries,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _generate_counterfactuals(
    adapter: MultiModelAdapter, gold: str, n: int = CF_COUNT
) -> tuple[list[CounterfactualSample], dict]:
    """Generate counterfactual samples with validation and provenance."""
    cfs: list[CounterfactualSample] = []
    rev_prompts, reconstruct_meta = _robust_reconstruct(adapter, gold, n)
    provenance: dict = {
        "reconstruct": reconstruct_meta,
        "outputs": [],
    }
    print(f"  [cf] generating {len(rev_prompts)} counterfactuals...")

    for pi, rp in enumerate(rev_prompts):
        label = f"cf_{pi+1}"
        out = ""
        attempt_meta: list[dict] = []
        try:
            out = adapter.generate(rp).strip()
            metadata = adapter.consume_last_response_metadata()
            if metadata:
                attempt_meta.append(metadata)
        except ConfirmedOutage:
            raise
        except Exception as e:
            print(f"    [{label}] ERROR: {e}")
            attempt_meta.append({"status": "error", "error": str(e)[:500]})

        is_ok = _is_valid_output(out, MIN_CF_OUTPUT_CHARS)
        if is_ok:
            print(f"    [{label}] done ({len(out)} chars)")
        else:
            print(f"    [{label}] SUSPICIOUS ({len(out)} chars) — retrying once...")
            time.sleep(2)
            try:
                out = adapter.generate(rp).strip()
                metadata = adapter.consume_last_response_metadata()
                if metadata:
                    attempt_meta.append(metadata)
                is_ok = _is_valid_output(out, MIN_CF_OUTPUT_CHARS)
                if is_ok:
                    print(f"    [{label}] retry OK ({len(out)} chars)")
                else:
                    print(f"    [{label}] retry still suspicious ({len(out)} chars)")
            except ConfirmedOutage:
                raise
            except Exception as e:
                print(f"    [{label}] retry ERROR: {e}")
                attempt_meta.append({"status": "error", "error": str(e)[:500]})

        # Never store an error string as a counterfactual output: empty output
        # is filtered out of the baseline by build_counterfactual_baseline.
        if not is_ok:
            out = ""
        cfs.append(CounterfactualSample(prompt=rp, output=out, label=label))
        provenance["outputs"].append({
            "label": label,
            "valid": is_ok,
            "attempts": attempt_meta,
        })

    return cfs, provenance


def _valid_counterfactual_count(cfs: list[CounterfactualSample]) -> int:
    return sum(
        1 for cf in cfs if _is_valid_output(cf.output, MIN_CF_OUTPUT_CHARS)
    )


def _validate_experiment_item(
    outputs: dict[str, str], cfs: list[CounterfactualSample]
) -> list[str]:
    """Return list of quality warnings for this item."""
    warnings = []

    # Check main outputs
    for lv in LEVELS:
        out = outputs.get(lv, "")
        if not _is_valid_output(out, MIN_OUTPUT_CHARS):
            warnings.append(f"{lv} output suspicious: {len(out)} chars")
        if out.startswith("[ERROR"):
            warnings.append(f"{lv} output is ERROR: {out[:80]}")

    # Check CF outputs
    valid_cf = _valid_counterfactual_count(cfs)
    if valid_cf < MIN_VALID_CFS:
        warnings.append(f"Only {valid_cf}/{len(cfs)} valid CF outputs (need ≥{MIN_VALID_CFS})")

    # Detect all-outputs-same-length (suggests fixed response bug)
    lengths = [len(outputs.get(lv, "")) for lv in LEVELS]
    if len(set(lengths)) == 1 and lengths[0] < 200:
        warnings.append(f"All 5 levels have same output length ({lengths[0]} chars) — likely broken")

    return warnings


def load_arxiv(n: int) -> list[dict]:
    data = json.loads((DATA_DIR / "arxiv_2000.json").read_text(encoding="utf-8"))
    items = []
    for a in data[:n]:
        items.append({"id": a["id"], "title": a["title"], "text": a["text"],
                       "wc": a["wc"], "domain": "arxiv"})
    return items


def load_news(n: int) -> list[dict]:
    data = json.loads((DATA_DIR / "news_2000.json").read_text(encoding="utf-8"))
    random.seed(42); random.shuffle(data)
    items = []
    for a in data[:n]:
        items.append({"id": a["id"], "title": a["title"], "text": a["text"],
                       "wc": a["wc"], "domain": "news"})
    return items


def load_patent(n: int) -> list[dict]:
    data = json.loads((DATA_DIR / "patent_2000.json").read_text(encoding="utf-8"))
    random.seed(42); random.shuffle(data)
    items = []
    for a in data[:n]:
        items.append({"id": a["id"], "title": a["title"], "text": a["text"],
                       "wc": a["wc"], "domain": "patent"})
    return items


def load_poetry(n: int) -> list[dict]:
    raw = json.loads((DATA_DIR / "poetry_2000.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    indexed = []
    for source_index, original in enumerate(raw):
        item = dict(original)
        item["_source_index"] = source_index
        base_id = str(item["id"])
        counts[base_id] = counts.get(base_id, 0) + 1
        indexed.append(item)
    random.seed(42); random.shuffle(indexed)
    items = []
    for a in indexed[:n]:
        base_id = str(a["id"])
        stable_id = base_id
        if counts[base_id] > 1:
            text_hash = hashlib.sha256(a["text"].encode("utf-8")).hexdigest()[:8]
            stable_id = f"{base_id}__row{a['_source_index']:04d}_{text_hash}"
        items.append({
            "id": stable_id,
            "source_id": base_id,
            "source_index": a["_source_index"],
            "title": a["title"],
            "text": a["text"],
            "wc": a["wc"],
            "domain": "poetry",
        })
    return items


def _spearman_pair(xs: list[float], ys: list[float]) -> float:
    """Spearman rho between two equal-length vectors (average ranks, ties ok)."""
    def _ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        rk = [0.0] * len(vs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[order[k]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return rk
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(xs)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = (sum((rx[i] - mx) ** 2 for i in range(n)) *
           sum((ry[i] - my) ** 2 for i in range(n))) ** 0.5
    return num / den if den > 0 else 0.0


def _quick_summary(results: list[dict], label: str) -> dict:
    """Compute key metrics for a set of results. Returns dict."""
    if len(results) < 3:
        return {"label": label, "n": len(results), "sufficient": False}

    means = []
    for lv in LEVELS:
        vals = [r["levels"][lv]["excess_ratio"] for r in results]
        means.append(statistics.fmean(vals))

    mono = all(means[i] > means[i+1] for i in range(len(means)-1))
    deltas = [means[i] - means[i+1] for i in range(len(means)-1)]

    pw = sum(1 for r in results for i in range(len(LEVELS)-1)
             if r["levels"][LEVELS[i]]["excess_ratio"] >
                r["levels"][LEVELS[i+1]]["excess_ratio"])
    pw_total = len(results) * (len(LEVELS)-1)

    # Check baseline health
    zero_bl = sum(1 for r in results
                  if r["levels"]["L1"]["baseline_mean"] < 0.0001)

    return {
        "label": label, "n": len(results), "sufficient": True,
        "means": means, "mono": mono, "deltas": deltas,
        "pairwise_pct": 100 * pw / pw_total if pw_total > 0 else 0,
        "zero_baseline_pct": 100 * zero_bl / len(results) if results else 0,
    }


def print_summary(results: list[dict], name: str) -> dict:
    """Print detailed summary and return metrics dict."""
    s = _quick_summary(results, name)
    if not s["sufficient"]:
        print(f"\n{name}: {len(results)} items (insufficient for analysis)")
        return s

    print(f"\n{'='*60}")
    print(f"{name} ({len(results)} items)")
    print(f"{'='*60}")
    arrow = " > ".join(f"{m:+.4f}" for m in s["means"])
    print(f"  {'PASS' if s['mono'] else 'FAIL'}: {arrow}")
    print(f"  Deltas: {'  '.join(f'{d:+.4f}' for d in s['deltas'])}")
    print(f"  Pairwise monotonic: {s['pairwise_pct']:.1f}%")
    print(f"  Zero-baseline items: {s['zero_baseline_pct']:.0f}%")
    if s["zero_baseline_pct"] > 30:
        print(f"  *** WARNING: {s['zero_baseline_pct']:.0f}% items have baseline=0! ***")

    # Spearman & Alpha — TWO senses, keep both:
    #  (1) label agreement: does excess_ratio reproduce the human-designed
    #      level labels (L1=5 most human ... L5=1)?  -> paper-comparable
    #  (2) inter-compressor alpha lives in compute_reliability_metrics.py
    all_excess = [r["levels"][lv]["excess_ratio"] for r in results for lv in LEVELS]
    all_labels = [lv for _ in results for lv in LEVELS]
    try:
        rho = compute_spearman(all_excess, all_labels)  # pooled label agreement
        # mean per-item label-agreement Spearman (H=5..1 vs excess vector)
        human = [5.0, 4.0, 3.0, 2.0, 1.0]
        item_rhos = []
        for r in results:
            vec = [r["levels"][lv]["excess_ratio"] for lv in LEVELS]
            if len(set(vec)) >= 2:
                item_rhos.append(_spearman_pair(human, vec))
        mean_item_rho = statistics.fmean(item_rhos) if item_rhos else 0.0
        s["spearman"] = rho
        s["label_mean_item_rho"] = mean_item_rho
        print(f"  Label agreement (vs human levels L1=5..L5=1):")
        print(f"    pooled Spearman rho: {rho:+.4f}   mean per-item rho: {mean_item_rho:+.4f}")
        print("    alpha_z/alpha_rank: run compute_reliability_metrics.py (TABLE 6)")
    except Exception as e:
        print(f"  Agreement metrics:  SKIPPED ({e})")

    return s


def _source_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_call_metadata(meta: dict | None, model: str, route: str,
                            gateway: int | str, client: str,
                            max_output_tokens: int, label: str) -> None:
    if not isinstance(meta, dict):
        raise RuntimeError(f"{label}: missing API provenance")
    if meta.get("requested_model") != model or meta.get("returned_model") != model:
        raise RuntimeError(f"{label}: model provenance mismatch")
    if meta.get("status") != "completed":
        raise RuntimeError(f"{label}: unverified terminal status {meta.get('status')!r}")
    if meta.get("route") != route:
        raise RuntimeError(f"{label}: route mismatch {meta.get('route')!r} != {route!r}")
    try:
        actual_client = Path(str(meta.get("client") or "")).resolve()
        expected_client = Path(client).resolve()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{label}: invalid API client provenance") from exc
    if actual_client != expected_client:
        raise RuntimeError(f"{label}: API client mismatch {actual_client} != {expected_client}")
    if meta.get("gateway") != gateway:
        raise RuntimeError(f"{label}: gateway mismatch {meta.get('gateway')!r} != {gateway}")
    if meta.get("max_output_tokens") != max_output_tokens:
        raise RuntimeError(
            f"{label}: token-cap mismatch {meta.get('max_output_tokens')!r} "
            f"!= {max_output_tokens}"
        )
    if not str(meta.get("response_id") or "").strip():
        raise RuntimeError(f"{label}: missing response ID")


def _validate_gpt_item_provenance(model: str, route: str, gateway,
                                  client: str, max_output_tokens: int,
                                  api_provenance: dict) -> None:
    for label, meta in api_provenance.get("main_calls", {}).items():
        _validate_call_metadata(
            meta, model, route, gateway, client, max_output_tokens, label
        )
    if len(api_provenance.get("main_calls", {})) != 7:
        raise RuntimeError("expected provenance for 7 main/intermediate calls")

    counterfactuals = api_provenance.get("counterfactuals") or {}
    reconstruct = counterfactuals.get("reconstruct")
    if not (isinstance(reconstruct, dict) and reconstruct.get("api") == "local_fallback"):
        _validate_call_metadata(
            reconstruct, model, route, gateway, client,
            max_output_tokens, "cf_reconstruct"
        )
    outputs = counterfactuals.get("outputs") or []
    if len(outputs) != CF_COUNT:
        raise RuntimeError(f"expected {CF_COUNT} counterfactual provenance rows")
    for row in outputs:
        if not row.get("valid"):
            continue
        completed = [
            attempt for attempt in row.get("attempts", [])
            if isinstance(attempt, dict) and attempt.get("status") == "completed"
        ]
        if not completed:
            raise RuntimeError(f"{row.get('label')}: valid CF lacks completed provenance")
        _validate_call_metadata(
            completed[-1], model, route, gateway, client,
            max_output_tokens, str(row.get("label"))
        )


def _load_historical_snapshot_ids(model: str, domain: str) -> set[str]:
    """Load and integrity-check the immutable API3rd cutover ID set."""
    try:
        manifest = json.loads(API3RD_CUTOVER_MANIFEST.read_text(encoding="utf-8"))
        entry = manifest["models"][model][domain.lower()]
        ids = [str(item) for item in entry["historical_ids"]]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"invalid API3rd cutover manifest for {model}/{domain}"
        ) from exc
    encoded = "\n".join(ids).encode("utf-8")
    if (
        manifest.get("schema_version") != 1
        or len(ids) != len(set(ids))
        or entry.get("row_count") != len(ids)
        or entry.get("ids_sha256") != hashlib.sha256(encoded).hexdigest()
    ):
        raise RuntimeError(f"API3rd cutover manifest integrity failure for {model}/{domain}")
    return set(ids)


def _validate_resume_rows(done: list[dict], *, model: str, domain: str,
                          source_ids: set[str], debug_keys: set[tuple[str, str, str]],
                          gateway: int | str | None, max_output_tokens: int,
                          route: str | None = None,
                          historical_protocols: tuple[tuple[str, int | str], ...] = (),
                          historical_ids: set[str] | None = None,
                          source_text_hashes: dict[str, str] | None = None,
                          debug_source_hashes: dict[tuple[str, str, str], str | None] | None = None) -> int:
    """Reject corrupt/foreign modern rows; return audited legacy-row count."""
    seen: set[str] = set()
    legacy = 0
    for row in done:
        item_id = str(row.get("id"))
        item_key = (model, domain.lower(), item_id)
        if item_id in seen:
            raise RuntimeError(f"duplicate result ID in {model}/{domain}: {item_id}")
        seen.add(item_id)
        if item_id not in source_ids:
            raise RuntimeError(f"unexpected source ID in {model}/{domain}: {item_id}")
        if item_key not in debug_keys:
            raise RuntimeError(f"result has no debug record: {model}/{domain}/{item_id}")

        expected_hash = (
            source_text_hashes.get(item_id) if source_text_hashes is not None else None
        )
        stored_hash = row.get("source_text_sha256")
        debug_hash = (
            debug_source_hashes.get(item_key)
            if debug_source_hashes is not None
            else None
        )
        for label, observed_hash in (
            ("result", stored_hash),
            ("debug", debug_hash),
        ):
            if observed_hash is not None and expected_hash is not None and observed_hash != expected_hash:
                raise RuntimeError(
                    f"{label} source hash mismatch for {model}/{domain}/{item_id}"
                )

        api = row.get("_api")
        if not isinstance(api, dict):
            if historical_ids is not None and item_id not in historical_ids:
                raise RuntimeError(
                    f"post-cutover legacy row is not in manifest: {model}/{domain}/{item_id}"
                )
            legacy += 1
            continue
        if gateway is not None:
            stored_gateway = api.get("gateway", api.get("backend_pin"))
            stored_route = api.get("route")
            current_protocol = (
                route is not None
                and stored_route == route
                and stored_gateway == gateway
            )
            if route is None:
                protocol_ok = stored_gateway == gateway
                historical_protocol = False
            elif stored_route is None:
                historical_protocol = any(
                    old_gateway == stored_gateway
                    for _, old_gateway in historical_protocols
                )
                protocol_ok = historical_protocol
            else:
                historical_protocol = (
                    stored_route, stored_gateway
                ) in set(historical_protocols)
                protocol_ok = current_protocol or historical_protocol
            if not protocol_ok:
                raise RuntimeError(
                    f"stored route/gateway mismatch for {model}/{domain}/{item_id}: "
                    f"{stored_route!r}/{stored_gateway!r}"
                )
            if (
                historical_protocol
                and historical_ids is not None
                and item_id not in historical_ids
            ):
                raise RuntimeError(
                    f"post-cutover historical row is not in manifest: {model}/{domain}/{item_id}"
                )
            if (
                current_protocol
                and source_text_hashes is not None
                and debug_source_hashes is not None
                and (expected_hash is None or stored_hash is None or debug_hash is None)
            ):
                raise RuntimeError(
                    f"current-protocol row lacks source hash: {model}/{domain}/{item_id}"
                )
            if api.get("max_output_tokens") != max_output_tokens:
                raise RuntimeError(f"stored token cap mismatch for {model}/{domain}/{item_id}")
            statuses = api.get("main_statuses") or {}
            if len(statuses) != 7 or any(value != "completed" for value in statuses.values()):
                raise RuntimeError(f"stored completion status invalid for {model}/{domain}/{item_id}")
            if int(api.get("valid_counterfactuals", 0)) < MIN_VALID_CFS:
                raise RuntimeError(f"stored CF count invalid for {model}/{domain}/{item_id}")
    return legacy


def _load_debug_index(model_name: str) -> dict[tuple[str, str, str], str | None]:
    index: dict[tuple[str, str, str], str | None] = {}
    for path in DEBUG_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"unreadable debug JSON: {path}: {exc}") from exc
        if str(record.get("model")) != model_name:
            continue
        item_key = (
            model_name,
            str(record.get("domain", "")).lower(),
            str(record.get("id")),
        )
        if item_key in index:
            raise RuntimeError(f"duplicate debug key: {item_key}")
        source = record.get("source")
        source_hash = source.get("text_sha256") if isinstance(source, dict) else None
        index[item_key] = source_hash if isinstance(source_hash, str) else None
    return index


def _load_debug_keys(model_name: str) -> set[tuple[str, str, str]]:
    """Compatibility wrapper for read-only audits."""
    return set(_load_debug_index(model_name))


def _debug_log_path(model_name: str, domain_name: str, item_id: str) -> Path:
    """Return a Windows-safe collision-resistant path for one debug record."""
    full_id = str(item_id)
    safe_id = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", full_id).strip(" .") or "item"
    digest = hashlib.sha256(full_id.encode("utf-8")).hexdigest()[:12]
    return DEBUG_DIR / f"{model_name}_{domain_name}_{safe_id[:44]}__{digest}.json"


def _save_debug_log(model_name: str, domain_name: str, item_id: str,
                    outputs: dict[str, str], prompts: dict[str, str],
                    cfs: list[CounterfactualSample],
                    levels: dict, warnings: list[str],
                    api_provenance: dict | None = None,
                    source_metadata: dict | None = None) -> None:
    """Save full prompt/output/CF data and API completion provenance."""
    log_path = _debug_log_path(model_name, domain_name, item_id)
    data = {
        "model": model_name, "domain": domain_name, "id": str(item_id),
        "warnings": warnings,
        "prompts": prompts,
        "outputs": outputs,
        "counterfactuals": [{"prompt": cf.prompt, "output": cf.output, "label": cf.label}
                            for cf in cfs],
        "level_metrics": levels,
        "api_provenance": api_provenance,
        "source": source_metadata,
    }
    tmp = log_path.with_name(log_path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(log_path)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def _model_run_lock(model_name: str):
    """Prevent two processes from rewriting the same model result files."""
    lock_dir = HERE / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    maintenance_lock = lock_dir / "maintenance.lock"
    if maintenance_lock.exists():
        raise RuntimeError("Experiment A maintenance/metrics operation is active")
    lock_path = lock_dir / f"{model_name}.lock"
    for _ in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = json.loads(lock_path.read_text(encoding="utf-8"))
                owner_pid = int(owner.get("pid", 0))
            except Exception:
                raise RuntimeError(f"invalid model lock exists: {lock_path}")
            if _pid_is_running(owner_pid):
                raise RuntimeError(
                    f"model {model_name} is already running in PID {owner_pid}"
                )
            lock_path.unlink(missing_ok=True)
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({
                    "pid": os.getpid(),
                    "model": model_name,
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                }, handle)
            break
    else:
        raise RuntimeError(f"could not acquire model lock: {lock_path}")
    if maintenance_lock.exists():
        lock_path.unlink(missing_ok=True)
        raise RuntimeError("Experiment A maintenance/metrics operation started concurrently")
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _run_one_model_unlocked(model_name: str, batch_size: int = 0, fresh: bool = False,
                  backend_pin: int | None = None,
                  max_output_tokens: int = 4096,
                  outage_threshold: int = 6,
                  outage_min_seconds: float = 180.0,
                  outage_guard_enabled: bool = True) -> dict:
    """Run the 5-level experiment for one model across all 4 domains.

    Parameters
    ----------
    batch_size:
        If > 0, pause after each batch of N items for review.
    fresh:
        Reserved for compatibility; CLI use is disabled because the historical
        per-round implementation could overwrite earlier results.
    """
    tag = _model_tag(model_name)
    protocol = MODEL_PROTOCOLS.get(model_name)
    expected_gateway = None
    if protocol is not None:
        expected_gateway = protocol["gateway"]
        expected_cap = protocol["max_output_tokens"]
        if protocol["route"] == "backend_b":
            if backend_pin is None:
                backend_pin = expected_gateway
            if backend_pin != expected_gateway:
                raise ValueError(
                    f"{model_name} must use GPT gateway {expected_gateway}, got {backend_pin}"
                )
        elif protocol["route"] == "backend_c":
            if backend_pin is not None:
                raise ValueError(
                    f"{model_name} uses backend_c automatic failover and cannot set --gpt-gateway"
                )
        elif backend_pin is not None:
            raise ValueError(f"{model_name} uses Copilot routing and cannot set --gpt-gateway")
        if max_output_tokens != expected_cap:
            raise ValueError(
                f"{model_name} must use max_output_tokens={expected_cap}, "
                f"got {max_output_tokens}"
            )
    # Longer timeouts to reduce subprocess failures
    if "gpt" in model_name:
        timeout = 120
        sleep_s = 1.5
    elif "gemini" in model_name:
        timeout = 90
        sleep_s = 0.6
    else:
        timeout = 90
        sleep_s = 0.5

    if protocol is not None and protocol["route"] == "copilot":
        adapter = CopilotResponsesAdapter(
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            reasoning_effort="low",
            slot_capacity=4,
            retries=2,
            timeout_seconds=180,
            sleep_seconds=sleep_s,
        )
    else:
        adapter = MultiModelAdapter(
            model_name=model_name,
            api_timeout=timeout,
            sleep_seconds=sleep_s,
            backend_pin=backend_pin,
            gpt_route=(
                protocol["route"]
                if protocol is not None and protocol["route"] in {"backend_b", "backend_c"}
                else None
            ),
            max_output_tokens=max_output_tokens,
        )

    if outage_guard_enabled:
        route_name = protocol["route"] if protocol is not None else "legacy"
        breaker = OutageCircuitBreaker(
            model=model_name,
            route=route_name,
            threshold=outage_threshold,
            minimum_duration_seconds=outage_min_seconds,
            report_dir=HERE / "outage_reports",
        )
        adapter = GuardedAdapter(adapter, breaker)

    print(f"\n{'#'*72}")
    print(f"# MODEL: {model_name}  (tag={tag}, CF={CF_COUNT}, "
          f"max={MAX_PER_DOMAIN}/domain, round={ROUND_SIZE})")
    print(f"# Timeout={timeout}s, Sleep={sleep_s}s, Batch={'YES('+str(batch_size)+')' if batch_size else 'NO'}")
    if protocol is not None:
        print(
            f"# Route={protocol['route']}, gateway={expected_gateway}, "
            f"max_output_tokens={max_output_tokens}, reasoning=low, "
            "require_status=completed"
        )
    if outage_guard_enabled:
        print(
            f"# OutageGuard=enabled threshold={outage_threshold}, "
            f"minimum_duration={outage_min_seconds:g}s, "
            "eligible=transport/server_5xx"
        )
    else:
        print("# OutageGuard=DISABLED")
    print(f"{'#'*72}")

    all_domain_items = [
        ("Arxiv",  load_arxiv(MAX_PER_DOMAIN)),
        ("News",   load_news(MAX_PER_DOMAIN)),
        ("Patent", load_patent(MAX_PER_DOMAIN)),
        ("Poetry", load_poetry(MAX_PER_DOMAIN)),
    ]

    all_metrics = {}
    domain_results: dict[str, list[dict]] = {}
    debug_index = _load_debug_index(model_name)
    debug_keys = set(debug_index)
    legacy_rows_reported: set[str] = set()
    num_rounds = (MAX_PER_DOMAIN + ROUND_SIZE - 1) // ROUND_SIZE

    for rd in range(num_rounds):
        start_idx = rd * ROUND_SIZE
        end_idx = start_idx + ROUND_SIZE
        round_has_work = False

        print(f"\n{'#'*72}")
        print(f"# ROUND {rd + 1}/{num_rounds}  (items {start_idx + 1}-{min(end_idx, MAX_PER_DOMAIN)} per domain)")
        print(f"{'#'*72}")

        for domain_name, all_items in all_domain_items:
            round_items = all_items[start_idx:end_idx]
            out_path = RESULTS_DIR / f"final_{domain_name.lower()}_5level_{model_name}.json"
            done = [] if fresh else (
                json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
            )
            source_ids = {str(item["id"]) for item in all_items}
            source_text_hashes = {
                str(item["id"]): _source_text_sha256(item["text"])
                for item in all_items
            }
            legacy_count = _validate_resume_rows(
                done,
                model=model_name,
                domain=domain_name,
                source_ids=source_ids,
                debug_keys=debug_keys,
                gateway=expected_gateway if protocol is not None else None,
                max_output_tokens=max_output_tokens,
                route=(
                    protocol["route"]
                    if protocol is not None and protocol["route"] == "backend_c"
                    else None
                ),
                historical_protocols=tuple(
                    protocol.get("historical_protocols", ()) if protocol is not None else ()
                ),
                historical_ids=(
                    _load_historical_snapshot_ids(model_name, domain_name)
                    if protocol is not None and protocol.get("historical_protocols")
                    else None
                ),
                source_text_hashes=source_text_hashes,
                debug_source_hashes=debug_index,
            )
            if legacy_count and domain_name not in legacy_rows_reported:
                print(
                    f"  [AUDITED LEGACY] {domain_name}: {legacy_count} rows predate "
                    "per-call provenance; retained after the 2026-08-22 data audit"
                )
                legacy_rows_reported.add(domain_name)
            done_ids = {str(d["id"]) for d in done}
            todo = [it for it in round_items if str(it["id"]) not in done_ids]
            domain_results[domain_name] = done

            if not todo:
                continue

            round_has_work = True
            target = min(MAX_PER_DOMAIN, len(all_items))

            print(f"\n{'─'*60}")
            print(f"{domain_name}: {len(done)}/{target} done, +{len(todo)} in this round ({start_idx + 1}-{end_idx} slice)")
            print(f"{'─'*60}")

            batch_warnings: list[str] = []
            batch_count = 0

            for item in todo:
                gold = item["text"]; wc = item["wc"]; item_id = item["id"]
                title = item.get("title", "")
                n = len(done) + 1

                print(f"\n[{n}/{target}] {domain_name}/{str(item_id)[:50]} ({wc}w)")

                item_warnings: list[str] = []

                try:
                    keywords = _extract_keywords(gold)

                    # ── Generate 5-level outputs ───────────────────────────
                    api_calls: dict = {}
                    l1_out, api_calls["L1_polish"] = _gen(adapter,
                        "Please polish the following text to make it more eloquent and professional, "
                        "keeping all original information unchanged:\n\n" + gold, "L1_polish")
                    l2_out, api_calls["L2_rewrite"] = _gen(adapter,
                        "Please rewrite the following text in your own words, keeping all original "
                        "facts but using completely different expressions and sentence structures:\n\n"
                        + gold, "L2_rewrite")
                    bullets, api_calls["L3_bullets"] = _gen(adapter,
                        "Extract 4-5 key points from the following text as bullet points. "
                        "Each bullet should be a complete sentence capturing one core idea. "
                        "Output ONLY the bullet list:\n\n" + gold[:2000], "L3_bullets")
                    l3_out, api_calls["L3_expand"] = _gen(adapter,
                        "Please expand the following bullet points into a complete, well-structured text:\n\n"
                        + bullets, "L3_expand")
                    s2, api_calls["L4_2sent"] = _gen(adapter,
                        "Summarize the following text in exactly TWO sentences. "
                        "The first sentence should cover the problem/topic and method/approach. "
                        "The second sentence should cover the key finding/result and its significance. "
                        "Start directly, no preamble:\n\n" + gold[:2000], "L4_2sent")
                    l4_out, api_calls["L4_expand"] = _gen(adapter,
                        "Please expand the following two-sentence summary into a complete text:\n\n"
                        + s2, "L4_expand")
                    l5_out, api_calls["L5_keywords"] = _gen(adapter,
                        "Please write a text about the following topic:\n\nKeywords: " + keywords,
                        "L5_keywords")

                    outputs = {"L1": l1_out, "L2": l2_out, "L3": l3_out,
                               "L4": l4_out, "L5": l5_out}

                    # ── Generate counterfactuals ───────────────────────────
                    cfs, cf_provenance = _generate_counterfactuals(adapter, gold, CF_COUNT)
                    valid_cf_count = _valid_counterfactual_count(cfs)
                    if valid_cf_count < MIN_VALID_CFS:
                        raise RuntimeError(
                            f"only {valid_cf_count}/{len(cfs)} valid counterfactuals; "
                            f"need at least {MIN_VALID_CFS}"
                        )
                    api_provenance = {
                        "config": {
                            "route": protocol["route"] if protocol is not None else "legacy",
                            "gateway": expected_gateway,
                            "max_output_tokens": max_output_tokens,
                            "require_status": "completed" if protocol is not None else None,
                        },
                        "main_calls": api_calls,
                        "counterfactuals": cf_provenance,
                    }
                    if protocol is not None:
                        _validate_gpt_item_provenance(
                            model_name,
                            protocol.get("call_route", protocol["route"]),
                            expected_gateway,
                            protocol["client"],
                            max_output_tokens,
                            api_provenance,
                        )
                    source_metadata = {
                        "source_id": item.get("source_id", item_id),
                        "source_index": item.get("source_index"),
                        "text_sha256": _source_text_sha256(gold),
                    }

                    # ── Quality check ──────────────────────────────────────
                    prompts_for_eval = {
                        "L1": "Please polish the following text to make it more eloquent and professional, keeping all original information unchanged:\n\n" + gold,
                        "L2": "Please rewrite the following text in your own words, keeping all original facts but using completely different expressions and sentence structures:\n\n" + gold,
                        "L3": "Please expand the following bullet points into a complete, well-structured text:\n\n" + bullets,
                        "L4": "Please expand the following two-sentence summary into a complete text:\n\n" + s2,
                        "L5": "Please write a text about the following topic:\n\nKeywords: " + keywords,
                    }
                    item_warnings = _validate_experiment_item(outputs, cfs)

                    # ── Compute metrics ────────────────────────────────────
                    # The same CF set is shared by all five levels. Build its
                    # aggregate + diagnostic profile once, then reuse it.
                    cf_profile = build_counterfactual_baseline_profile(cfs, _COMPRESSORS)
                    lr = {}
                    for lv in LEVELS:
                        out = outputs[lv] or "[EMPTY]"
                        prompt = prompts_for_eval[lv]
                        sess_profile = evaluate_session_profile(
                            prompt=prompt,
                            output=out,
                            compressors=_COMPRESSORS,
                            precomputed_baseline=cf_profile,
                        )
                        sess = sess_profile.aggregate
                        per_comp = {}
                        if out.strip():
                            for c in _COMPRESSORS:
                                actual = sess_profile.actual.per_compressor[c][
                                    "contribution_ratio"
                                ]
                                bl_mean = cf_profile.per_compressor_mean_ratios[c]
                                per_comp[c] = {
                                    "actual_ratio": actual,
                                    "baseline_mean": bl_mean,
                                    "excess_ratio": actual - bl_mean,
                                }
                        lr[lv] = {
                            "actual_ratio": sess.actual.contribution_ratio,
                            "excess_ratio": sess.excess_contribution_ratio,
                            "baseline_mean": sess.counterfactual_baseline.mean_contribution_ratio,
                            "baseline_n_valid": len(sess.counterfactual_baseline.samples),
                            "output_chars": len(out),
                            "per_compressor": per_comp,
                        }
                        flag = ""
                        if sess.counterfactual_baseline.mean_contribution_ratio < 0.0001:
                            flag = " [BL=0!]"
                        print(f"    [{lv}] excess={sess.excess_contribution_ratio:+.4f}"
                              f"  actual={sess.actual.contribution_ratio:+.4f}"
                              f"  baseline={sess.counterfactual_baseline.mean_contribution_ratio:+.4f}{flag}")

                    # ── Save debug log ─────────────────────────────────────
                    _save_debug_log(model_name, domain_name, str(item_id),
                                    outputs, prompts_for_eval, cfs, lr, item_warnings,
                                    api_provenance, source_metadata)
                    item_key = (model_name, domain_name.lower(), str(item_id))
                    debug_keys.add(item_key)
                    debug_index[item_key] = source_metadata["text_sha256"]

                    # ── Save result ────────────────────────────────────────
                    done.append({
                        "id": item_id,
                        "source_id": item.get("source_id", item_id),
                        "source_index": item.get("source_index"),
                        "source_text_sha256": source_metadata["text_sha256"],
                        "title": title,
                        "word_count": wc,
                        "levels": lr,
                        "_warnings": item_warnings,
                        "_api": {
                            "route": protocol["route"] if protocol is not None else "legacy",
                            "gateway": expected_gateway,
                            "backend_pin": backend_pin,
                            "max_output_tokens": max_output_tokens,
                            "main_statuses": {
                                label: (meta or {}).get("status")
                                for label, meta in api_calls.items()
                            },
                            "valid_counterfactuals": valid_cf_count,
                            "provenance_in_debug": True,
                        },
                    })
                    _save(out_path, done)
                    if item_warnings:
                        print(f"  [WARNINGS] {'; '.join(item_warnings)}")
                    print(f"  [SAVED] -> {len(done)}/{target}")

                except ConfirmedOutage:
                    raise
                except Exception as e:
                    import traceback
                    print(f"  [SKIPPED] {e}")
                    traceback.print_exc()

                # ── Batch review ───────────────────────────────────────────
                if item_warnings:
                    batch_warnings.extend(item_warnings)
                batch_count += 1

                if batch_size > 0 and batch_count >= batch_size:
                    batch_results = done[-batch_count:] if len(done) >= batch_count else done
                    print(f"\n{'─'*60}")
                    print(f"BATCH REVIEW: last {len(batch_results)} items for {domain_name}/{model_name}")
                    print(f"{'─'*60}")
                    s = _quick_summary(batch_results, f"batch-{domain_name}")
                    if s["sufficient"]:
                        print(f"  Means: {'  '.join(f'{lv}={m:+.4f}' for lv, m in zip(LEVELS, s['means']))}")
                        print(f"  Monotonic: {'PASS' if s['mono'] else 'FAIL'}")
                        print(f"  Zero-baseline: {s['zero_baseline_pct']:.0f}%")
                    if batch_warnings:
                        print(f"  Warnings in this batch:")
                        for w in batch_warnings:
                            print(f"    - {w}")
                    print(f"  Continuing to next batch...")
                    print(f"{'─'*60}")
                    batch_warnings = []
                    batch_count = 0

            # ── Save domain state after this round ────────────────────────
            domain_results[domain_name] = done
            _save(out_path, done)

            # Quick round-domain summary
            if len(done) >= 5:
                recent = done[-min(len(done), ROUND_SIZE):]
                s = _quick_summary(recent, f"{domain_name}-rd{rd+1}")
                if s["sufficient"]:
                    arrow = " > ".join(f"{m:+.3f}" for m in s["means"])
                    print(f"\n  {domain_name} snapshot [{len(done)} items]: {arrow}  "
                          f"mono={'PASS' if s['mono'] else 'FAIL'}  bl0={s['zero_baseline_pct']:.0f}%")

        if not round_has_work:
            print(f"\n  All domains complete for round {rd + 1} — continuing...")

    # ── Final per-domain summaries ─────────────────────────────────────────
    for domain_name, ds_items in domain_results.items():
        if ds_items:
            all_metrics[f"{domain_name}/{tag}"] = print_summary(ds_items, f"{domain_name}/{tag}")

    # ── Cross-domain summary ───────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"CROSS-DOMAIN: {model_name}")
    print(f"{'='*72}")
    print(f"{'Domain':<10} {'L1':>9} {'L2':>9} {'L3':>9} {'L4':>9} {'L5':>9}  Mono  BL=0%  N")
    print("-"*85)
    for domain_name, _ in all_domain_items:
        res = domain_results.get(domain_name, [])
        if not res: continue
        means = [statistics.fmean(r["levels"][lv]["excess_ratio"] for r in res)
                 for lv in LEVELS]
        mono = all(means[i] > means[i+1] for i in range(len(means)-1))
        zero_pct = 100 * sum(1 for r in res
                             if r["levels"]["L1"]["baseline_mean"] < 0.0001) / len(res)
        print(f"{domain_name:<10} {means[0]:>+9.4f} {means[1]:>+9.4f} {means[2]:>+9.4f} "
              f"{means[3]:>+9.4f} {means[4]:>+9.4f}  {'PASS' if mono else 'FAIL'}  {zero_pct:>5.0f}%  {len(res):>4d}")

    # Overall
    all_items = []
    for res in domain_results.values():
        all_items.extend(res)
    if all_items:
        ov_means = [statistics.fmean(r["levels"][lv]["excess_ratio"] for r in all_items)
                    for lv in LEVELS]
        mono_ov = all(ov_means[i] > ov_means[i+1] for i in range(len(ov_means)-1))
        diffs = [ov_means[i] - ov_means[i+1] for i in range(len(ov_means)-1)]
        print(f"\nOVERALL: {'PASS' if mono_ov else 'FAIL'}  (N={len(all_items)})")
        print(f"  {' > '.join(f'{m:+.4f}' for m in ov_means)}")
        print(f"  Deltas: {'  '.join(f'{d:+.4f}' for d in diffs)}")
        if min(diffs) > 0 and max(diffs) > 0:
            print(f"  Uniformity: {min(diffs)/max(diffs):.2f}")

    return all_metrics


def run_one_model(model_name: str, batch_size: int = 0, fresh: bool = False,
                  backend_pin: int | None = None,
                  max_output_tokens: int = 4096,
                  outage_threshold: int = 6,
                  outage_min_seconds: float = 180.0,
                  outage_guard_enabled: bool = True) -> dict:
    """Run one model under an exclusive cross-process lock."""
    with _model_run_lock(model_name):
        return _run_one_model_unlocked(
            model_name,
            batch_size=batch_size,
            fresh=fresh,
            backend_pin=backend_pin,
            max_output_tokens=max_output_tokens,
            outage_threshold=outage_threshold,
            outage_min_seconds=outage_min_seconds,
            outage_guard_enabled=outage_guard_enabled,
        )


def _health_check(models: list[str], probe_rounds: int = 4,
                  probe_wait: int = 20) -> list[str]:
    """Quick health check: test each model, flag broken ones.

    Transient 429s are common when several models share an API pool, so each
    probe is retried with a backoff before the model is declared broken.
    """
    print("\n=== MODEL HEALTH CHECK ===")
    healthy = []
    for m in models:
        try:
            tag = _model_tag(m)
            timeout = 45 if "gpt" in m else 60
            a = _make_health_adapter(m, timeout=timeout, sleep_seconds=0.2)
            # Test simple generation (retry on transient rate limits)
            out = ""
            for attempt in range(probe_rounds):
                try:
                    out = a.generate("Say hello in exactly three words.")
                    break
                except Exception as e:
                    if attempt == probe_rounds - 1:
                        raise
                    print(f"    [health probe {attempt + 1}/{probe_rounds} failed, "
                          f"retry in {probe_wait}s: {str(e)[:100]}]")
                    time.sleep(probe_wait)
            ok1 = _is_valid_output(out, 15)
            # Test reconstruct
            try:
                prompts = list(a.reconstruct_prompts(
                    "This paper presents a novel machine learning approach to natural language understanding.", 2
                ))
                ok2 = all(len(p.strip()) >= 10 for p in prompts if p.strip())
            except Exception:
                ok2 = False

            status = "OK" if ok1 and ok2 else "ISSUES"
            print(f"  {m:<30} gen={len(out):>4}ch ok={ok1}  rec_ok={ok2}  -> {status}")
            if ok1:
                healthy.append(m)
            else:
                print(f"    Output: {repr(out[:150])}")
        except Exception as e:
            print(f"  {m:<30} FAILED: {e}")
    print(f"Healthy: {len(healthy)}/{len(models)}")
    return healthy


def main():
    batch_size = 0
    fresh = False
    backend_pin: int | None = None
    max_output_tokens = 4096
    outage_threshold = 6
    outage_min_seconds = 180.0
    outage_guard_enabled = True

    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        next_value = argv[index + 1] if index + 1 < len(argv) else None
        if arg.startswith("--batch="):
            batch_size = int(arg.split("=", 1)[1])
        elif arg == "--batch" and next_value is not None:
            batch_size = int(next_value)
        elif arg == "--fresh":
            fresh = True
        elif arg.startswith("--gpt-gateway="):
            backend_pin = int(arg.split("=", 1)[1])
        elif arg == "--gpt-gateway" and next_value is not None:
            backend_pin = int(next_value)
        elif arg.startswith("--max-output-tokens="):
            max_output_tokens = int(arg.split("=", 1)[1])
        elif arg == "--max-output-tokens" and next_value is not None:
            max_output_tokens = int(next_value)
        elif arg.startswith("--outage-threshold="):
            outage_threshold = int(arg.split("=", 1)[1])
        elif arg == "--outage-threshold" and next_value is not None:
            outage_threshold = int(next_value)
        elif arg.startswith("--outage-min-seconds="):
            outage_min_seconds = float(arg.split("=", 1)[1])
        elif arg == "--outage-min-seconds" and next_value is not None:
            outage_min_seconds = float(next_value)
        elif arg == "--disable-outage-guard":
            outage_guard_enabled = False

    if fresh:
        print("ERROR: --fresh is disabled because it can overwrite earlier rounds. "
              "Use a manifest-based cleanup followed by normal resume.")
        sys.exit(2)
    if backend_pin not in (None, 1, 2, 3):
        print("ERROR: --gpt-gateway must be 1, 2, or 3")
        sys.exit(2)
    if max_output_tokens <= 0:
        print("ERROR: --max-output-tokens must be positive")
        sys.exit(2)
    if outage_threshold < 2:
        print("ERROR: --outage-threshold must be at least 2")
        sys.exit(2)
    if outage_min_seconds < 0:
        print("ERROR: --outage-min-seconds cannot be negative")
        sys.exit(2)

    if "--run-all" in sys.argv:
        if backend_pin is not None:
            print("ERROR: --gpt-gateway is model-specific and cannot be combined with --run-all")
            sys.exit(2)
        global ALL_MODELS
        print("Resolving 9-model roster...")
        ALL_MODELS = _resolve_models()
        if not ALL_MODELS:
            print("FATAL: No models resolved. Aborting.")
            sys.exit(1)
        print(f"Resolved {len(ALL_MODELS)} models: {ALL_MODELS}")

        # Health check
        healthy = _health_check(ALL_MODELS)
        if len(healthy) < len(ALL_MODELS):
            print(f"\n*** WARNING: Only {len(healthy)}/{len(ALL_MODELS)} models passed health check ***")
            print(f"    Will run with healthy models: {healthy}")

        # Sequential execution (one model at a time to avoid API congestion)
        print(f"\nLaunching experiment ({MAX_PER_DOMAIN}/domain each, round={ROUND_SIZE}, "
              f"batch={batch_size if batch_size else 'off'})...")
        print(f"Models: {healthy}")
        print()

        all_metrics = {}
        for i, m in enumerate(healthy):
            print(f"\n{'*'*72}")
            print(f"*** MODEL {i+1}/{len(healthy)}: {m}")
            print(f"{'*'*72}")
            try:
                metrics = run_one_model(
                    m,
                    batch_size=batch_size,
                    fresh=fresh,
                    max_output_tokens=max_output_tokens,
                    outage_threshold=outage_threshold,
                    outage_min_seconds=outage_min_seconds,
                    outage_guard_enabled=outage_guard_enabled,
                )
                all_metrics[m] = metrics
                print(f"\n[{m}] COMPLETED")
            except ConfirmedOutage:
                raise
            except Exception as e:
                import traceback
                print(f"\n[{m}] FAILED: {e}")
                traceback.print_exc()

        print(f"\n{'='*72}")
        print(f"ALL MODELS COMPLETE")
        print(f"{'='*72}")

        # Final summary table
        print(f"\n{'Model':<28} {'Arxiv':>8} {'News':>8} {'Patent':>8} {'Poetry':>8} {'Mono':>6}")
        print("-" * 70)
        for m in healthy:
            parts = []
            for d in ["arxiv", "news", "patent", "poetry"]:
                key = f"{d.capitalize()}/{_model_tag(m)}"
                if key in all_metrics.get(m, {}):
                    s = all_metrics[m][key]
                    parts.append("PASS" if s.get("mono") else "FAIL")
                else:
                    parts.append("N/A")
            mono_count = parts.count("PASS")
            print(f"{m:<28} {parts[0]:>8} {parts[1]:>8} {parts[2]:>8} {parts[3]:>8} {mono_count}/4")

    else:
        # Single model mode
        model_name = None
        for index, arg in enumerate(argv):
            if arg.startswith("--model="):
                model_name = arg.split("=", 1)[1]
            elif arg == "--model" and index + 1 < len(argv):
                model_name = argv[index + 1]
        if not model_name:
            print("Usage: run_final_5level.py --model <name> [--batch N]")
            print("       run_final_5level.py --run-all [--batch N]")
            sys.exit(1)

        skip_health = "--skip-health" in sys.argv
        print(f"\nSingle model: {model_name} (batch={batch_size}, fresh={fresh}, "
              f"gateway={backend_pin}, max_output_tokens={max_output_tokens})")
        if skip_health:
            print("  Health check SKIPPED (--skip-health)")
            run_one_model(
                model_name,
                batch_size=batch_size,
                fresh=fresh,
                backend_pin=backend_pin,
                max_output_tokens=max_output_tokens,
                outage_threshold=outage_threshold,
                outage_min_seconds=outage_min_seconds,
                outage_guard_enabled=outage_guard_enabled,
            )
        else:
            healthy = _health_check([model_name])
            if healthy:
                run_one_model(
                    model_name,
                    batch_size=batch_size,
                    fresh=fresh,
                    backend_pin=backend_pin,
                    max_output_tokens=max_output_tokens,
                    outage_threshold=outage_threshold,
                    outage_min_seconds=outage_min_seconds,
                    outage_guard_enabled=outage_guard_enabled,
                )
            else:
                raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except ConfirmedOutage as error:
        print(f"\n[OUTAGE GUARD] {error}", file=sys.stderr, flush=True)
        raise SystemExit(OUTAGE_EXIT_CODE) from error
