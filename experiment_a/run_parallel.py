# -*- coding: utf-8 -*-
"""Launch Experiment A with five model-isolated worker threads.

Usage::

    python run_parallel.py [--batch=50]

Architecture:
  - Copilot 2.2.15 Responses (3 workers sharing machine-wide capacity 4):
      claude-sonnet-5  |  gemini-3.6-flash  |  claude-opus-4-8
  - API3rd GPT Responses route (2 workers sharing automatic three-origin failover):
      gpt-5.5  |  gpt-5.6-sol
"""

from __future__ import annotations

import subprocess
import sys
import os
import time
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

HERE = Path(__file__).resolve().parent

# ── Model roster ──────────────────────────────────────────────────────
# Each entry = one process-isolated model worker. Copilot attempts coordinate
# through CopilotGlobalSlotPool; API3rd GPT workers share automatic failover.
VENDOR_MODELS: list[tuple[str, list[str], str]] = [
    # (label, [models], api_source)
    ("claude",       ["claude-sonnet-5"],               "copilot"),
    ("gemini",       ["gemini-3.6-flash"],               "copilot"),
    ("claude2",      ["claude-opus-4-8"],                "copilot"),
    ("gpt-sol",      ["gpt-5.6-sol"],                    "backend_c"),
    ("gpt-5.5",      ["gpt-5.5"],                        "backend_c"),
]

PYTHON = "python"
GPT_MODELS = {"gpt-5.5", "gpt-5.6-sol"}
GPT_MAX_OUTPUT_TOKENS = 4096


def _run_model(vendor: str, model: str, batch_size: int, fresh: bool,
               log_path: Path, api_source: str) -> tuple[subprocess.Popen, object]:
    """Launch a model subprocess, return (proc, log_file_handle)."""
    args = [
        PYTHON, "-u", str(HERE / "run_final_5level.py"),
        f"--model={model}",
    ]
    if model in GPT_MODELS:
        args.append(f"--max-output-tokens={GPT_MAX_OUTPUT_TOKENS}")
    if batch_size > 0:
        args.append(f"--batch={batch_size}")
    if fresh:
        args.append("--fresh")
    # Skip health check for models known to produce short outputs
    SKIP_HEALTH = {
        "claude-sonnet-5", "claude-opus-4-8", "gemini-3.6-flash",
        "gpt-5.5", "gpt-5.6-sol", "gpt-5.4", "grok-4.5",
    }
    if model in SKIP_HEALTH:
        args.append("--skip-health")

    log_f = open(log_path, "w", encoding="utf-8", errors="replace")
    log_f.write(f"# [{api_source.upper()} API] {vendor} — {model}\n")
    log_f.write(f"# CMD: {' '.join(args)}\n\n")
    log_f.flush()

    proc = subprocess.Popen(
        args,
        cwd=str(HERE),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc, log_f


def _run_vendor_thread(vendor: str, models: list[str], batch_size: int,
                        fresh: bool, api_source: str):
    """Run models for one vendor sequentially, streaming to per-model log files."""
    LOGS_DIR = HERE / "run_logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    for i, model in enumerate(models):
        log_path = LOGS_DIR / f"{vendor}_{model}.log"
        t0 = time.time()
        print(f"[{vendor}] [{i+1}/{len(models)}] Starting: {model}  "
              f"(api={api_source}, log={log_path.name})")

        proc, log_f = _run_model(vendor, model, batch_size, fresh, log_path, api_source)

        # Stream output to log
        for line in proc.stdout:
            log_f.write(line)
            log_f.flush()

        proc.wait()
        log_f.close()

        elapsed = time.time() - t0
        mins, secs = divmod(int(elapsed), 60)
        rc = proc.returncode

        # Show last lines
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            for line in tail:
                print(f"[{vendor}]   | {line}")
        except Exception:
            pass

        status = "OK" if rc == 0 else f"FAIL(rc={rc})"
        print(f"[{vendor}] [{i+1}/{len(models)}] DONE: {model}  "
              f"({mins}m{secs}s)  {status}")
        if rc != 0:
            print(f"[{vendor}] *** {model} FAILED — continuing with next model ***")
        print()


def main():
    batch_size = 0
    fresh = False
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg.startswith("--batch="):
            batch_size = int(arg.split("=", 1)[1])
        elif arg == "--batch" and index + 1 < len(argv):
            batch_size = int(argv[index + 1])
        elif arg == "--fresh":
            fresh = True

    if fresh:
        raise SystemExit("--fresh is disabled; use a backed-up manifest cleanup and normal resume")

    total_models = sum(len(models) for _, models, _ in VENDOR_MODELS)
    print(f"{'='*70}")
    print(f"PARALLEL LAUNCH: {len(VENDOR_MODELS)} threads, {total_models} models total")
    print(f"  Batch size: {batch_size if batch_size else 'continuous'}")
    print(f"  Fresh: {fresh}")
    for label, models, api in VENDOR_MODELS:
        print(f"    [{api.upper()} API] {label}: {models}")
    print(f"{'='*70}\n")

    import threading

    threads = []
    for label, models, api_source in VENDOR_MODELS:
        print(f"[{label}] Launching: {models}  (api={api_source})")
        t = threading.Thread(
            target=_run_vendor_thread,
            args=(label, models, batch_size, fresh, api_source),
            daemon=True,
        )
        t.start()
        threads.append((label, t))

    print(f"\nLaunched {len(threads)} threads. Waiting for completion...\n")

    for label, t in threads:
        t.join()

    print(f"\n{'='*70}")
    print("ALL THREADS COMPLETE")
    print(f"{'='*70}")

    # Summary
    results_dir = HERE / "results"
    debug_dir = HERE / "debug_logs"
    print(f"\nResults files:")
    for f in sorted(results_dir.glob("final_*_5level_*.json")):
        import json
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            model_name = f.stem.replace("final_", "").replace("_5level_", " | ")
            print(f"  {model_name}: {len(data)} items")
        except Exception:
            print(f"  {f.name}: (unreadable)")

    n_debug = len(list(debug_dir.glob("*.json")))
    print(f"\nDebug logs: {n_debug} total")

    # Post-processing. Per-compressor fields are generated in the main runner;
    # never run the legacy global recompute here because it can rewrite primary
    # aggregate metrics and resurrect stale debug records.
    print(f"\n{'='*70}")
    print("POST-PROCESSING: reliability metrics")
    print(f"{'='*70}")
    for script in ["compute_reliability_metrics.py"]:
        spath = HERE / script
        if spath.exists():
            print(f"\nRunning {script}...")
            result = subprocess.run(
                [PYTHON, "-u", str(spath)],
                cwd=str(HERE),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out = result.stdout
            print(out[-3000:] if len(out) > 3000 else out)
            if result.returncode != 0:
                print(f"WARNING: {script} returned {result.returncode}")
        else:
            print(f"  {script} — not found, skipping")


if __name__ == "__main__":
    main()
