# Actual-only heuristic benchmark runbook

This directory is the sole write scope for the paper-final Experiment A heuristic benchmark.

## Fixed scientific contract

- 11,222 model-items; five actual prompt-output pairs per item; 56,110 pairs.
- 2,551 underlying source clusters.
- Aggregate `actual_ratio` is the black-box score.
- Llama and Mixtral use only `levels.<L>.phi` as separate operational references.
- Fifteen frozen heuristic features are defined in `feature_protocol.json`.
- Primary summaries: macro within-level and item-centered.
- Every main comparison pairs Spearman rho with `pairwise_continuous_alpha_z`.
- 2,000 shared paired source-cluster bootstrap draws; seed 20260823.

## Deterministic execution

Run from this directory with the research Python environment:

```bash
python test_benchmark.py
python run_benchmark.py run
python audit_benchmark.py --write
python run_benchmark.py finalize
```

`run_benchmark.py run` is checkpoint/resume safe for feature extraction and bootstrap. `feature_ledger_receipt.json` binds the completed ledger, and `scientific_completion.json` is the sole manifest-last scientific completion sentinel; partial projections are regenerated safely. A completed run is an exact hash-verification no-op. The independent auditor replays all 2,000 draws and all metrics, then binds every scientific/code artifact. `manifest.json` is written last and self-verifies the exact directory and audit.

> **Note.** The frozen bundle in this directory was produced with one additional
> step, an OOXML report updater that patched a manuscript DOCX. That updater,
> its transaction/receipt records, and the manuscript itself are outside the
> scope of this release and are **not** included, so `run`→`audit`→`finalize`
> here ends at the frozen statistics rather than at the DOCX. The `manifest.json`
> shipped in this directory was written by the original full pipeline and still
> records those Word-binding fields (`word_update`, and the extra backup entry);
> treat them as historical provenance, not as files you are expected to produce.

No script imports network clients, model libraries, or GPU libraries. The process is single-threaded at the Python orchestration layer and keeps source text one item at a time.
