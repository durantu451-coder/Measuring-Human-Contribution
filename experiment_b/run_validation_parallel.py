# -*- coding: utf-8 -*-
"""Experiment B — Step 4 parallel launcher (5 models, one process each).

Mirrors Experiment A's run_parallel.py: each model runs run_validation.py in
its own subprocess, streaming to experiment_b/logs/validation_{model}.log.

Routing / contention:
  - ALL 5 models run on the NEW API only — Experiment A keeps the old API's
    3 ports.  run_validation.py passes use_alt_backend=True.
  - The new API is a shared 60 RPM pool; every model is throttled via --sleep
    (MODEL_SLEEP) so 5 B processes + Experiment A's 2 GPT processes stay sane.

Usage::

    python -X utf8 experiment_b/run_validation_parallel.py
    ... --limit 20        # smoke slice across all 5 models
    ... --dataset wildchat
    ... --no-metrics      # skip the final compute_validation_metrics.py pass
"""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import check_storage_sentinels

PYTHON = "python"

# (label, [models], api_source)  — one thread per entry
VENDOR_MODELS: list[tuple[str, list[str], str]] = [
    ("claude",       ["claude-sonnet-5"],  "old"),
    ("gemini",       ["gemini-3.6-flash"], "old"),
    ("claude2",      ["claude-opus-4-8"],  "old"),
    ("gpt-sol",      ["gpt-5.6-sol"],      "new"),
    ("gpt-5.5",      ["gpt-5.5"],          "new"),
]

# All 5 models run on the new API (shared 60 RPM pool) — throttle every one.
MODEL_SLEEP = {
    "claude-sonnet-5": 1.5,
    "gemini-3.6-flash": 1.5,
    "claude-opus-4-8": 1.5,
    "gpt-5.6-sol": 2.0,
    "gpt-5.5": 2.0,
}

# backend_b cannot keep a non-streaming 4096-token response alive through the
# tunnel. Both Experiment-B GPT models use the isolated gateway 3 and the
# audited 2048×2 continuation protocol (total budget remains 4096).
MODEL_EXTRA_ARGS = {
    "gpt-5.6-sol": ["--gpt-gateway=3", "--max-output-tokens=4096", "--segment-output-tokens=2048"],
    "gpt-5.5": ["--gpt-gateway=3", "--max-output-tokens=4096", "--segment-output-tokens=2048"],
}


def _run_model(vendor: str, model: str, args_extra: list[str], log_path: Path) -> tuple[subprocess.Popen, object]:
    args = [
        PYTHON, "-u", "-X", "utf8",
        str(HERE / "run_validation.py"),
        f"--model={model}",
    ]
    if model in MODEL_SLEEP:
        args.append(f"--sleep={MODEL_SLEEP[model]}")
    if "--api-route=copilot" not in args_extra:
        args.extend(MODEL_EXTRA_ARGS.get(model, []))
    args.extend(args_extra)

    # Append logs across resumes so routing/errors remain auditable.
    log_f = open(log_path, "ab")
    log_f.write(f"# [{vendor}] {model}\n".encode("utf-8"))
    log_f.write(f"# CMD: {' '.join(args)}\n\n".encode("utf-8"))
    log_f.flush()

    proc = subprocess.Popen(
        args,
        cwd=str(PROJECT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    return proc, log_f


def _run_vendor_thread(vendor: str, models: list[str], args_extra: list[str]):
    logs_dir = HERE / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for model in models:
        log_path = logs_dir / f"validation_{model}.log"
        print(f"[{vendor}] starting {model} → {log_path.name}", flush=True)
        proc, log_f = _run_model(vendor, model, args_extra, log_path)
        proc.wait()
        log_f.close()
        rc = proc.returncode
        print(f"[{vendor}] {model} DONE rc={rc}", flush=True)
        if rc != 0:
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
                for line in tail:
                    print(f"[{vendor}]   | {line}", flush=True)
            except Exception:
                pass


def main() -> None:
    check_storage_sentinels(HERE)
    limit = 0
    dataset = None
    no_metrics = False
    api_route = "current"
    copilot_slots = 8
    copilot_retries = 2
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])
        elif arg.startswith("--dataset="):
            dataset = arg.split("=", 1)[1]
        elif arg == "--no-metrics":
            no_metrics = True
        elif arg.startswith("--api-route="):
            api_route = arg.split("=", 1)[1]
        elif arg.startswith("--copilot-slots="):
            copilot_slots = int(arg.split("=", 1)[1])
        elif arg.startswith("--copilot-retries="):
            copilot_retries = int(arg.split("=", 1)[1])

    args_extra: list[str] = []
    if limit > 0:
        args_extra.append(f"--limit={limit}")
    if dataset:
        args_extra.append(f"--dataset={dataset}")
    args_extra.append(f"--api-route={api_route}")
    if api_route == "copilot":
        args_extra.extend([
            f"--copilot-slots={copilot_slots}",
            f"--copilot-retries={copilot_retries}",
        ])

    total_models = sum(len(models) for _, models, _ in VENDOR_MODELS)
    print(f"{'=' * 70}")
    print(f"EXPERIMENT B — STEP 4 PARALLEL LAUNCH: {total_models} models")
    print(f"  limit={limit or 'all'}  dataset={dataset or 'all 3'}  route={api_route}"
          f"  copilot_slots={copilot_slots if api_route == 'copilot' else 'n/a'}")
    for label, models, api in VENDOR_MODELS:
        parts = ", ".join(f"{m} (sleep={MODEL_SLEEP.get(m, 'default')}s)" for m in models)
        print(f"    [NEW API] {label}: {parts}")
    print(f"{'=' * 70}\n", flush=True)

    import threading
    threads = []
    for label, models, api in VENDOR_MODELS:
        t = threading.Thread(target=_run_vendor_thread, args=(label, models, args_extra), daemon=True)
        t.start()
        threads.append((label, t))

    for label, t in threads:
        t.join()

    print(f"\n{'=' * 70}")
    print("ALL MODELS COMPLETE")
    print(f"{'=' * 70}", flush=True)

    if not no_metrics:
        print("\nComputing reliability metrics...", flush=True)
        result = subprocess.run(
            [PYTHON, "-u", "-X", "utf8", str(HERE / "compute_validation_metrics.py")],
            cwd=str(PROJECT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = result.stdout
        print(out[-6000:] if len(out) > 6000 else out, flush=True)
        if result.returncode != 0:
            print(f"WARNING: compute_validation_metrics.py rc={result.returncode}", flush=True)


if __name__ == "__main__":
    main()
