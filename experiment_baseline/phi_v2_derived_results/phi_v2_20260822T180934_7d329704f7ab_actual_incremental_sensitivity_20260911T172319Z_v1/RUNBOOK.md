# Actual-only incremental/sensitivity bundle runbook

## Scope

This sibling bundle consumes only the completed numeric ledger in:

`../phi_v2_20260822T180934_7d329704f7ab_actual_heuristic_20260911T035818Z_v1/actual_pair_features.jsonl`

It does **not** call APIs, access a network, use a GPU, generate text, read prompt/output text, recompress data, calculate a counterfactual-derived estimand, modify the authority bundle, or modify Word.

Main estimand: aggregate `R_actual` on the 56,110 real prompt/output pairs. The source-cluster key is always the full triple `(source_cluster_domain, source_cluster_id, source_cluster_fingerprint)`.

## Frozen lifecycle

Run from this staging directory with the existing research Python environment. BLAS/OpenMP variables are forced to one thread in every script.

```bash
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B -c "from pathlib import Path; [compile(Path(p).read_text(encoding='utf-8'), p, 'exec') for p in ('analysis_core.py','run_analysis.py','audit_analysis.py','test_analysis.py')]"
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B -m unittest -v test_analysis.py
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B run_analysis.py prepare
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B run_analysis.py validate-prepared
```

These commands use the existing research interpreter (NumPy 2.5.1 / scikit-learn 1.9.0) and suppress bytecode writes. Compilation is performed with Python's built-in `compile()` into memory, so no `__pycache__` is created inside staging.

`prepare` is the only command intended for the preflight window. It validates every unresolved path component and every immutable authority artifact (including all ten authority-declared protected inputs), streams the exact 28-field ledger through one ordinary-file handle while hashing the same bytes, audits the raw-gain algebra, constructs row-order-invariant nested source-grouped folds, verifies the 2,000-draw SHA-256, and writes:

1. `run_config.json` (first derived scientific artifact; immutable after creation),
2. `fold_assignments.json`,
3. `derived_features_receipt.json`,
4. `prepare_receipt.json`.

If interrupted during preparation, rerunning `prepare` accepts only an exact, ordinary-file ordered prefix of those four artifacts, reconstructs every deterministic byte independently, and appends only the missing suffix. Before doing so it requires the exact source-only tree (the four scripts, this runbook, and the three declared empty checkpoint directories); stale formal/checkpoint files, unknown paths, and links/reparse points are fatal.

Do not run formal statistics until these files and code have been reviewed.

## Formal analysis (after review)

```bash
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B run_analysis.py analyze
```

This performs nested grouped Ridge fits for the six frozen primary sets (`L/O/H/H+R/R-only/G-only`), one separately labeled auxiliary `AUX-strongest-single` set selected only from the old authority (expected feature: `rouge_l_recall`), fixed HGB robustness fits for the same primary-plus-auxiliary inventory, cross-fitted length residualization, exact point statistics, and the shared 2,000-draw source-cluster bootstrap. The auxiliary model is never presented as a seventh primary set. It never refits inside bootstrap draws. Each model×outer-fold fit is first committed as an immutable resumable block; merged OOF/model ledgers are create-or-identical. OOF and bootstrap checkpoints use deterministic NPZ serialization with fixed ZIP metadata and `allow_pickle=False`; they bind the frozen config, exact key inventory (including the key array itself), rows/range, dtype, shape, fit metadata, numeric payload SHA-256, and whole-file bytes. Immutable publication uses atomic fail-if-exists hard-link creation rather than overwrite-capable replacement. Existing blocks are reused only after semantic and deterministic-byte validation. The CSV exports point effective N plus all-resample and finite-resample effective-N minima/maxima for every bootstrap contrast.

After scientific outputs complete:

```bash
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B audit_analysis.py
```

The auditor does not import `analysis_core.py` or `run_analysis.py`. It independently parses the ledger, reconstructs algebra/folds/consensus/order/calipers, performs a full-row permutation fold check, refits every Ridge/HGB model, compares complete scaler/coefficient/inner-score/fold metadata, checks every OOF row and the exact unique checkpoint path↔logical-key inventory, replays all 2,000 draws, recomputes every effective-N matrix element and summary field, validates the exact frozen model/bootstrap inventory, and independently regenerates all CSV/Markdown/report projections for byte comparison. An existing `audit.json` never short-circuits this work: the full refits, replay, checkpoint-to-ledger checks, and projections run again before the old receipt can be accepted as a no-op. It has a separate RSS/tracemalloc monitor with the same sampled-RSS policy.

Only after `audit.json` reports `state=pass`:

```bash
PYTHONDONTWRITEBYTECODE=1 ${HC_ENV}/python -B run_analysis.py finalize
```

`finalize` revalidates authority and all bindings, writes `manifest.json` last, validates the exact recursive inventory, and atomically renames staging to:

`../phi_v2_20260822T180934_7d329704f7ab_actual_incremental_sensitivity_20260911T172319Z_v1/`

## Failure and resume rules

- Any authority, lineage, key, cluster, schema, raw-algebra, or bootstrap-draw conflict is fatal. Do not guess a repair.
- Existing formal artifacts are never overwritten with different bytes. Valid model×outer-fold and bootstrap blocks are resumed after exact metadata/key/payload validation; merged ledgers and projections are regenerated create-or-identically.
- Any handled `Exception` raised after command dispatch writes a command-scoped sibling diagnostic `.<bundle-id>.<command>.FAILED.json`; only a later successful run of that same command removes it, so success in one phase cannot erase another phase's failure evidence. Argument-parser exits, `KeyboardInterrupt`, forced termination, and power loss are intentionally outside this receipt guarantee and may leave only hash-valid resumable checkpoints. Failure receipts are outside the publishable bundle inventory.
- A resource monitor samples process RSS every 50 ms, records tracemalloc, targets less than 1 GiB, and performs a synchronous final RSS sample that fails above 1.5 GiB. Receipts name this honestly as `sampled_process_rss_hard_limit`: it is not a mathematical guarantee against a sub-50-ms transient between samples. The independent auditor uses its own implementation of the same policy. A detected resource breach cannot publish a manifest.
- `scientific_completion.json` binds the exact scientific artifact inventory and every size/hash; analysis no-op, fresh/no-op audit, and finalization all revalidate those bytes. A valid manifest left by an interruption is resumed rather than rejected.
- An existing non-identical final directory is never overwritten.
- The old Word path recorded in the authority manifest has moved. It is a non-input warning (`relocated_same_sha_not_consumed`): this workflow does not follow, read, repair, or modify that file.

## Interpretation boundary

Every main agreement cell reports Spearman rho beside explicitly named `pairwise_continuous_alpha_z`; the separately named three-rater statistic is `joint_reference_continuous_alpha_z`. L1–L5 are investigator-specified ordinal treatment labels, not independent human annotations. Per-level treatment agreement is mathematically undefined because the treatment reference is constant within level and is emitted as `NA(reference_constant_within_level)` rather than zero.
