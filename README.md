# Measuring Human Contribution to Human–AI Collaborative Content Generation in the Wild

Reference code and derived artifacts for the paper
[*Measuring Human Contribution in AI-Assisted Content Generation*](https://arxiv.org/abs/2408.14792).

This is a **reproduction and extension** of the original paper. It contributes an
operational, black-box estimator of human contribution, validates it against a
white-box information-theoretic reference, reproduces the effect across
generators, and stress-tests it under four ablations. This repository is
released anonymously for review.

---

## 1. What the metric is

Let `x` be the human prompt and `y` the model's output. The quantity of interest
is the share of `y`'s information that is attributable to `x`:

```text
phi = I(x; y) / I(y) = ( I(y) - I(y | x) ) / I(y)
```

Token probabilities are unavailable for most deployed generators, so the
black-box score substitutes a compression-code-length proxy. With a compressor
ensemble `c` in {zlib, bz2, lzma} and `C_c(z) = 8 * (|compress_c(z)| - |compress_c(empty)|)`:

```text
R_actual(x, y) = clamp( max(0, C(y) - D(y | x)) / C(y), 0, 1 )
D_c(y | x)     = max(0, C_c(x || S || y) - C_c(x || S))
```

where `||` is byte concatenation and `S` is the literal sentinel
`b"\n<<<HC_CONTEXT_TARGET_SEPARATOR>>>\n"`.

> **`R_actual` is an operational score under a finite compressor ensemble.** It
> is not an unbiased estimate of mutual information and not a calibrated
> percentage. Length and compressibility both influence it; the length-robustness
> analysis in the paper quantifies that sensitivity rather than hiding it.

The white-box reference is the same ratio computed from next-token
log-probabilities:

```text
phi_actual = ( NLL_uncond - NLL_cond ) / NLL_uncond
```

with `Llama-3.1-8B-Instruct` and `Mixtral-8x7B-v0.1` as evaluators.

### Strict vs. legacy counterfactual baseline — read this before comparing numbers

An earlier "excess" variant subtracted a **counterfactual baseline**:
reconstruct `N` plausible prompts `q_i` from `y`, regenerate `z_i`, and report
`excess = phi(x,y) - mean_i phi(q_i,z_i)`.

The legacy Experiment A lineage shares **one source-derived baseline across all
five treatment levels L1–L5**. That baseline is not output-conditioned on the
specific observed `y`, so:

- its **`actual_ratio` field is valid** and is the source of the RQ1 numbers;
- its **baseline / excess fields are invalid** for any strict-CF claim and must
  not be used.

The isolated `experiment_a/strict_cf_v1` lineage repairs this on a balanced
confirmatory sample, and Experiment B reconstructs from each observed output
already. The paper's CF-sensitivity analysis (Appendix B.5) rests on the
strict-CF derivations, not on the legacy `excess` column.

---

## 2. Repository layout

```
human_contribution/     Core library: compression metric, adapters, trajectory
                        features, optional Qwen3-embedding hybrid path.
experiment_a/           RQ1 — controlled gradient (5 treatment levels x 5 models
                        x 4 domains). Includes the strict-CF repair lineage.
experiment_b/           RQ3 — cross-generator reproducibility in the wild
                        (10k_prompts / WildChat / OASST1).
experiment_baseline/    RQ2 + RQ4 — white-box phi, alpha reliability, the four
                        ablations, CF3 sheet, and the heuristic benchmark bundle.
data/experiment_a/      RQ1 domain inputs (arxiv / news / patent / poetry).
data/experiment_b/      RQ3 source pools (10k_prompts / wildchat / oasst1).
data/_upstream/         Raw upstream downloads kept for provenance; unused.
derived_outputs/        Frozen per-row artifacts backing the paper's tables.
```

The cross-experiment coupling is real: `experiment_a` reads through
`experiment_b.storage`. Run B's storage layer before touching A.

### Paper ↔ directory map

| Paper unit | Directory |
|---|---|
| RQ1 §5.2 Controlled Gradient (Tables 2–3) | `experiment_a/` |
| RQ2 §5.3 White-Box Convergence (Table 4) | `experiment_baseline/` (`phi_v2_derived_results/`) |
| RQ3 §5.4 Cross-Generator Reproducibility (Tables 5–6) | `experiment_b/` |
| RQ4 §5.5.1 normalization ablation (Table 7) | `experiment_baseline/` |
| RQ4 §5.5.2 length robustness (Table 8) | `experiment_baseline/` |
| RQ4 §5.5.3 lexical heuristics (Table 9) | `experiment_baseline/` |
| RQ4 §5.5.4 CF sensitivity (Table 10) | `experiment_a/strict_cf_v1` + `experiment_baseline/` |
| RQ5 §5.6 Computational cost (Table 11) | `experiment_baseline/` (`assemble_timing.py`, `bench_*`) |
| Appendix B.5 CF3 derivative (Table B6) | `experiment_baseline/cf3_tiny_results/` |

---

## 3. Setup and reproduction

### Environment

```bash
python -m venv .venv && . .venv/bin/activate   # or your conda env
pip install -r requirements.txt
```

Python 3.12 is what the reported runs used.

**Run the auditors single-threaded.** The shipped `audit.json` receipts record
the refit error maxima as exactly `0.0`, and the auditor compares them with exact
equality rather than a tolerance (`validate_recomputed_audit_evidence`). A
multi-threaded BLAS sums in a different order, which perturbs the last ULP and
yields ~5e-15 instead of `0.0` — still four orders of magnitude inside the
auditor's own `atol=1e-12`, but not bit-identical to the recorded receipt. Set
these before running `audit_benchmark.py` or `audit_analysis.py`:

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
```

With those set, the refits reproduce the recorded `0.0` exactly.

### Restoring the four oversized files — do this first

GitHub rejects any single file over 100 MB, so four artifacts are **not stored in
place**. They are packed under `large_files/` at the repository root, and
**nothing works until you put them back**:

```bash
python restore_large_files.py            # restore + verify SHA-256
python restore_large_files.py --check    # report only, writes nothing
python restore_large_files.py --delete-archives   # restore, then free the space
```

Run it before anything else — `audit_benchmark.py`, `audit_analysis.py`,
`run_analysis.py` and the hash verifier all read these files. The script restores
into a temporary file and checks the recorded SHA-256 *before* publishing it, so
a failed restore never leaves a half-correct tree.

| File | Packed as | Archive | Restores to |
|---|---|---|---|
| `experiment_baseline/v2/run_20260823_canonical/sources.jsonl` | split | 4 × ≤95 MB | 344.7 MB |
| `.../actual_incremental_sensitivity_20260911T172319Z_v1/oof_predictions.jsonl` | gzip | 45.8 MB | 240.4 MB |
| `data/experiment_b/wildchat/wildchat_10k.jsonl` | gzip | 36.7 MB | 164.3 MB |
| `data/_upstream/wildchat_train.parquet` | split | 3 × ≤95 MB | 220.1 MB |

Total 969.5 MB → 647.3 MB. `gzip` is used where compression gets under the cap
and byte-range `split` where it does not — `wildchat_train.parquet` is already
internally deflated, so it compresses to only 86% and has to be split instead.

The archives sit at the repository root, not inside any bundle, because the
auditors enforce an exact directory inventory of the bundle they live in
(`audit_analysis.py`, `ALLOWED_DIRECTORIES`) and would reject an undeclared
subdirectory.

Two of the four are hash-pinned by the release's own manifests —
`sources.jsonl` by nine of them, `oof_predictions.jsonl` by `manifest.json` and
`scientific_completion.json` — and `audit_analysis.py` reads
`oof_predictions.jsonl` directly, so every restore is verified byte-exact rather
than line-exact. `.gitattributes` marks all paths `-text -crlf` so git cannot
translate line endings and break those digests.

### Paths

Data and model checkpoints live outside the repository. Five placeholders appear
in recorded paths and are resolved at run time:

| Placeholder | Meaning | Default in code |
|---|---|---|
| `${HC_DATA_ROOT}` | Root holding corpora, model checkpoints, and runtime staging | `HC_DATA_ROOT`, else `~/hc_data` |
| `${HC_HOME}` | Where derived debug/timing output is written | `HC_HOME`, else `~/hc_home` |
| `${HC_ENV}` | Conda environment root recorded by the runtime binding | `HC_ENV`, else `CONDA_PREFIX`, else `sys.prefix` |
| `${HC_PYTHON}` | Interpreter executable recorded by the runtime binding | `HC_PYTHON`, else `sys.executable` |
| `${HC_CLIENT_SCRIPT}` | External generation-client script (see *External generation clients* below) | `HC_CLIENT_SCRIPT`, else `clients/client_multi_provider.py` |

`${HC_ENV}` and `${HC_PYTHON}` appear only inside recorded execution metadata
(which interpreter and stdlib the reported runs used), not in code that loads
data. Set them if you want to reproduce those records byte-for-byte; otherwise
the interpreter you are running already supplies the right values.

Model checkpoints are expected under `${HC_DATA_ROOT}/models/`
(`Meta-Llama-3.1-8B-Instruct`, `Mixtral-8x7B-v0.1`).

### Credentials

The API-backed adapters read the credential from the environment at call time:

```bash
export ANTHROPIC_AUTH_TOKEN=...     # never committed; no key lives in this repo
```

### External generation clients

The generation stage of Experiments A and B does **not** call a provider
directly. It shells out to standalone single-file client scripts that wrap a
third-party inference router — these carry embedded credentials and private
gateway endpoints, so **they are not part of this release**.

What this means for you:

- Everything needed to **recompute the reported statistics from the frozen
  artifacts** is included and does not need any client. This is the intended
  reproduction path for review.
- To **regenerate text** (Experiment A/B pipelines), supply your own
  OpenAI-compatible client and point the code at it. The adapters look for
  client scripts under `clients/`; override the primary one with:

  ```bash
  export HC_CLIENT_SCRIPT=/path/to/your/client.py
  ```

- Model identifiers (e.g. `gpt-5.6-sol`, `claude-opus-4-8`) are the router's own
  names and are recorded verbatim in the frozen artifacts. Substitute whatever
  endpoints you have access to; the metric itself is model-agnostic.

### Minimal smoke test

```bash
python -m human_contribution.cli \
  --prompt "Write a patent-style abstract about a compression-based contribution metric." \
  --output "The method estimates human contribution by comparing output code length with conditional code length under the prompt." \
  --pretty
```

Run the test suites:

```bash
python -m unittest discover -s experiment_baseline
```

### Full pipelines

```bash
# RQ3: in-the-wild validation across the three source pools
python -m experiment_b.run_validation_parallel

# RQ2/RQ4: white-box reference + reliability + ablations
python experiment_baseline/batch_phi.py --manifest "$HC_DATA_ROOT/baseline_v2_stage/prepare_manifest_canonical.json"

# RQ1: controlled gradient (see experiment_a/ for the level runner)
python experiment_a/run_parallel.py
```

Reproduce-then-compare: the frozen numbers each script should print are in
`derived_outputs/` and alongside each experiment directory.

---

## 4. Data provenance and privacy

`data/` is organized by the experiment that consumes it, mirroring the code
layout:

```
data/experiment_a/          # RQ1 controlled gradient — 4 domains
    arxiv_2000.json  news_2000.json  patent_2000.json  poetry_2000.json
data/experiment_b/          # RQ3 in-the-wild — 3 source pools
    10k_prompts/full.jsonl
    wildchat/wildchat_10k.jsonl
    oasst1/oasst1_10k.jsonl
data/_upstream/             # source files not read by any code path
    wildchat_train.parquet  oasst1_train.parquet
    poetry/ (PoetryFoundationData.csv + preview)
    10k_prompts_preview.txt
```

Only the files under `experiment_a/` and `experiment_b/` are read by the
pipelines. `_upstream/` holds the raw upstream downloads and descriptive
previews for provenance; nothing imports them.

All of this is **third-party corpora redistributed under their original
licenses**:

| Source | Content |
|---|---|
| WildChat | Real user–assistant conversations, including prompts and outputs |
| OASST1 | Crowd-sourced assistant conversation tree |
| 10k_prompts | Public prompt collection |
| Poetry Foundation | Public-domain and licensed poems |
| arxiv / news / patent | Document samples for the controlled-gradient domains |

These corpora contain **real user-written text**. They include, in the natural
course of the data, personal identifiers, IP addresses, and password-like
strings that participants typed. They are included here unmodified so the
validation split is reproducible; they are **not** authored by us and are **not**
subject to the anonymization applied to our own code and configuration. If you
redistribute or deploy against them, apply the upstream licenses and the
appropriate handling for user-generated content.

Our own code, configuration, metadata, and logs have been scrubbed of local
paths, usernames, host addresses, and credentials.

Two datasets used during development are **not** redistributed here — obtain
them from their official sources if you need to rerun those paths:
`coauthor` and `hupd_2018`.

### Note on recorded hashes

Several artifacts ship with a companion manifest recording a SHA-256 for each
file, so a reader can verify the frozen outputs were not altered. Every
artifact hash recorded against the shipped tree **verifies against the shipped
bytes**. The same is true for all but a small set of provenance records: the
raw provenance manifests also snapshot hashes from the *original* pre-release
runs, and a handful of those entries are stale relative to this tree — either
their recorded size is out of date while the SHA-256 still matches, or the
file was rewritten during de-identification. These provenance-only entries do
not participate in any shipped-artifact verification path; the list is
recorded under `claims.scrubbed_inputs` and `claims.scrub_note` in the raw
analysis manifest.

Two things a reader should know:

1. **Hashes cover exact bytes, so do not let anything rewrite line endings.**
   These manifests pin file digests, and a checkout that converts `\n` to
   `\r\n` (or back) will change those bytes and make every hash fail. The
   bundled `.gitattributes` pins `-text -crlf` on every extension, which
   disables line-ending translation in both directions, so a plain `git clone`
   reproduces the recorded digests exactly. If you copy individual files out of
   the tree, preserve them byte-for-byte.
2. **The experiment bundles' upstream inputs are included, and the auditors run
   end to end.** The heuristic and sensitivity auditors verify a set of protected
   Experiment A inputs — `experiment_baseline/ACTIVE_PHI_V2.json`, the
   `experiment_baseline/v2/run_20260823_canonical/` tree, and the 11,222 per-item
   source records under `experiment_a/debug_logs/`. All of these ship with the
   release, so `audit_benchmark.py` and `audit_analysis.py` run to completion
   from a fresh clone.

   **De-identification note.** Two groups of inputs were rewritten before release
   because they embedded machine-specific absolute paths.

   *Five raw-provenance inputs*: `ACTIVE_PHI_V2.json`,
   `v2/prepare_manifest_canonical.json`,
   `v2/run_20260823_canonical/final/lineage.json`,
   `v2/run_20260823_canonical/final/compatibility.json`, and
   `v2/runtime_collected_20260823/runtime_attestation.json`. In each, an absolute
   data-root path was folded to the `${HC_DATA_ROOT}` placeholder token that the
   project's own path resolver already understands. These are the files listed in
   the raw analysis manifest under `claims.scrubbed_inputs`, with an accompanying
   `claims.scrub_note`.

   *413 of the 11,222 per-item records* under `experiment_a/debug_logs/`: each
   recorded the absolute path of the external generation-client script. That
   value was folded to the `${HC_CLIENT_SCRIPT}` placeholder — the same token the
   adapters already read from the environment — in the 13 fields that carry it
   (seven `api_provenance.main_calls.*.client` entries, one
   `api_provenance.counterfactuals.reconstruct.client`, and five
   `api_provenance.counterfactuals.outputs[*].attempts[0].client`). Every affected
   record shrank by exactly 819 bytes. These fields are provenance bookkeeping
   only: they are not inputs to any statistic, and no scoring, fitting, or
   bootstrap value reads them. The remaining 10,809 debug records are
   byte-identical to the original run.

   In both groups the digests therefore differ from the original run, and the
   auditors' pinned digests were re-recorded against the shipped bytes so the
   chain verifies.

   For completeness: Experiment A's strict-CF schema constants
   (`experiment_a/strict_cf_schema.py`) still name the same external client, but
   by an internal *relative* path rather than an absolute one, and the
   surrounding route labels are opaque internal tags. No user, machine, or
   institution information appears there, so it was left as shipped rather than
   rewritten; those constants are provenance bookkeeping and feed no statistic.

The word-receipt subsystem is not part of this release: the helper that performed
the Word `.docx` export carried a machine-specific document path, so it was
removed for de-identification, together with the receipt checks that depended on
it. The remaining auditors, manifests, and receipts verify without it, and a
comment in `run_benchmark.py` records the removal.

---

## 5. Caveats

- Compression is an estimator of information, not a semantic model. Read the
  black-box score as an operational ranking signal, not a calibrated share.
- The same compressor ensemble and framing protocol must be used across any two
  sessions you compare.
- Counterfactual prompts and outputs must come from fixed models at fixed
  sampling settings; a CF baseline is output-conditioned only when the
  reconstruction receives the specific observed output being scored.
- Prefer normalized ratios or bits-per-token when comparing outputs of very
  different lengths.
- `experiment_a/run_final_5level.py` is **deprecated** and kept only because its
  `actual_ratio` column is the RQ1 source. Its `excess_ratio` output uses the
  legacy shared baseline — do not report it as a strict-CF result.

## 6. License

See `LICENSE`. Third-party corpora in `data/` remain under their upstream
licenses.
