# -*- coding: utf-8 -*-
"""Independent auditor for the paper-final actual-pair heuristic bundle.

Deliberately does not import run_benchmark.py or benchmark_core.py.  It repeats
identity, feature, agreement, point-estimate, and bootstrap-summary checks with
separate code and writes audit.json only after every invariant passes.
"""
from __future__ import annotations

import argparse
import bisect
import bz2
import csv
import hashlib
import json
import lzma
import math
import os
import re
import statistics
import time
import unicodedata
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import numpy as np
from scipy.stats import rankdata, spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEVELS = ("L1", "L2", "L3", "L4", "L5")
FEATURES = (
    "prompt_bytes", "output_bytes", "prompt_words", "output_words",
    "prompt_to_output_byte_ratio", "word_type_coverage", "word_token_coverage",
    "word_bigram_coverage", "char3_coverage", "char5_coverage", "char8_coverage",
    "rouge_l_recall", "output_type_token_ratio", "output_bigram_repeat_fraction",
    "output_self_bits_per_byte",
)
CANDIDATES = ("blackbox_actual_ratio", *FEATURES)
SCORES = (*CANDIDATES, "phi_actual_llama", "phi_actual_mixtral")
MODELS = (
    "claude-opus-4-8", "claude-sonnet-5", "gemini-3.6-flash", "gpt-5.5", "gpt-5.6-sol"
)
DOMAINS = ("arxiv", "news", "patent", "poetry")
EXPECTED_INPUTS = {
    "experiment_baseline/ACTIVE_PHI_V2.json": "8e17b22a30a80e25a8548561931928930019a4610b7edbdc1dbcad7ee2ba8dee",
    "experiment_baseline/v2/run_20260823_canonical/final/lineage.json": "c6d0b0410ee2a51a01d3b6cba88671a9d86075cc121b39f2ddbd6e1915fae7c1",
    "experiment_baseline/v2/run_20260823_canonical/sources.jsonl": "d545faaf72cd5c35053c056e93cc3ea19827ccb4cca3d422d4cb351339d0dafd",
    "experiment_baseline/v2/run_20260823_canonical/final/phi_llama.v2.jsonl": "7efc006e6b68b6375f65917a8337ce6ddf9b09e45ec577966aec70dd483ec5e6",
    "experiment_baseline/v2/run_20260823_canonical/final/phi_mixtral.v2.jsonl": "8c52b2d5e8eb21263c34088b80c1e14afd5831201d020dda8dcb9c2850fbe865",
    "experiment_baseline/phi_v2_derived_results/phi_v2_20260822T180934_7d329704f7ab_raw_raw_20260910T100648Z_v1/analysis.json": "aac49d41156fe6b34520d955936c2b1c48440da90e7b590613d1b50f15657ea1",
    "experiment_baseline/phi_v2_derived_results/phi_v2_20260822T180934_7d329704f7ab_raw_raw_20260910T100648Z_v1/manifest.json": "40ff089f5d4fa0c8aa635bb36ca586c38a7c09a6527a2f55979f21e4528946a4",
    "experiment_baseline/v2/run_20260823_canonical/heuristic_pilot_large/output_manifest.json": "54530567d93fc7c47d67b68dda1b94abcb52116c6b9570f1f82309c0ebce5e94",
    "experiment_baseline/v2/run_20260823_canonical/heuristic_pilot_large/summary.json": "afcce3807943a0adcdddaf19aab2f95f62319d494a4d3c3a7f3106b88a6c20fb",
    "experiment_baseline/v2/run_20260823_canonical/heuristic_pilot_large/pair_features.csv": "42dbac90dba5c602fe846dbfb9136f7a0af04efd48eb1123d7b3d86fe39b1d84",
}
WORD_RE = re.compile(r"\w+", re.UNICODE)
SPACE_RE = re.compile(r"\s+", re.UNICODE)
LEDGER_FIELDS = {
    "generation_model", "domain", "id", "level", "scoring_input_sha256",
    "prompt_sha256", "output_sha256", "source_cluster_domain",
    "source_cluster_id", "source_cluster_fingerprint", *SCORES,
}
TABLE_FILES = (
    "table1_direct.md", "table2_llama.md", "table3_mixtral.md",
    "table4_paired_differences.md", "table5_joint_reference.md",
    "table6_subgroups.md",
)
APPENDIX_FILES = (
    "appendix_per_level.md", "appendix_auxiliary_alpha.md",
    "appendix_ties_undefined.md", "appendix_feature_definitions.md",
)
SCIENTIFIC_FILES = (
    "feature_protocol.json", "run_config.json", "actual_pair_features.jsonl",
    "feature_ledger_receipt.json", "bootstrap_checkpoint.npz",
    "bootstrap_summary.json", "metrics.json", "metrics.csv", *TABLE_FILES,
    *APPENDIX_FILES, "REPORT_ZH.md", "execution.json",
)
AUDIT_BOUND_FILES = (
    "benchmark_core.py", "run_benchmark.py", "audit_benchmark.py",
    "test_benchmark.py", "RUNBOOK.md", *SCIENTIFIC_FILES,
    "scientific_completion.json",
)
FORBIDDEN_LABELS = (
    "counter" + "factual", "cf" + "_phi", "level" + "_excess",
    "blackbox" + "_excess", "llama" + "_excess", "mixtral" + "_excess",
    "excess" + "_ratio", "phi" + "_excess", "baseline" + "_mean",
    "sub" + "traction",
)


class AuditError(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any, newline: bool = False) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def atomic_json(path: Path, value: Any) -> None:
    payload = canonical(value, newline=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("wb") as handle:
        handle.write(payload); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, path)


def key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    model = unicodedata.normalize("NFC", str(row.get("generation_model", row.get("model"))).strip())
    domain = unicodedata.normalize("NFC", str(row.get("domain")).strip()).lower()
    item = unicodedata.normalize("NFC", str(row.get("id")).strip())
    if not model or not domain or not item:
        raise AuditError("empty semantic key")
    return model, domain, item


def load_rows() -> list[dict[str, Any]]:
    rows = []
    seen = set()
    with (HERE / "actual_pair_features.jsonl").open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            row = json.loads(raw)
            pair_key = (*key(row), row.get("level"))
            if pair_key in seen or pair_key[-1] not in LEVELS:
                raise AuditError(f"duplicate/invalid pair at {line_number}")
            seen.add(pair_key)
            if set(row) != LEDGER_FIELDS:
                raise AuditError(f"feature ledger schema differs at {line_number}")
            if any(not math.isfinite(float(row[name])) for name in SCORES):
                raise AuditError(f"nonfinite score at {line_number}")
            rows.append(row)
    rows.sort(key=lambda row: (*key(row), LEVELS.index(row["level"])))
    if len(rows) != 56110 or len({key(row) for row in rows}) != 11222:
        raise AuditError("full feature coverage differs")
    for offset in range(0, len(rows), 5):
        group = rows[offset:offset + 5]
        if len({key(row) for row in group}) != 1 or [row["level"] for row in group] != list(LEVELS):
            raise AuditError("five-level grouping differs")
    clusters = {
        (row["source_cluster_domain"], row["source_cluster_id"], row["source_cluster_fingerprint"])
        for row in rows
    }
    if len(clusters) != 2551:
        raise AuditError("cluster coverage differs")
    if Counter(key(row)[0] for row in rows[::5]) != Counter({
        "claude-opus-4-8": 1892, "claude-sonnet-5": 2320, "gemini-3.6-flash": 2240,
        "gpt-5.5": 2446, "gpt-5.6-sol": 2324,
    }):
        raise AuditError("model partition differs")
    if Counter(key(row)[1] for row in rows[::5]) != Counter({
        "arxiv": 2937, "news": 2856, "patent": 2760, "poetry": 2669,
    }):
        raise AuditError("domain partition differs")
    return rows


def interval_alpha(matrix: np.ndarray) -> float | None:
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise AuditError("invalid alpha matrix")
    n, k = values.shape
    if n < 2 or k < 2:
        return None
    row_sum = values.sum(axis=1)
    row_sq = np.square(values).sum(axis=1)
    total_n = n * k
    num = 2.0 * (row_sq.sum() - np.sum((np.square(row_sum) - row_sq) / (k - 1)))
    den = (2.0 / (total_n - 1.0)) * (total_n * row_sq.sum() - row_sum.sum() ** 2)
    if den == 0.0:
        return 1.0 if num == 0.0 else None
    value = 1.0 - num / den
    return float(value) if math.isfinite(float(value)) else None


def alpha_z(*vectors: np.ndarray) -> float | None:
    matrix = np.column_stack(vectors).astype(float)
    sd = matrix.std(axis=0, ddof=1)
    if np.any(sd == 0.0):
        return None
    matrix = (matrix - matrix.mean(axis=0)) / sd
    return interval_alpha(matrix)


def rho(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2 or np.ptp(left) == 0.0 or np.ptp(right) == 0.0:
        return None
    value = float(spearmanr(left, right).statistic)
    return value if math.isfinite(value) else None


def center(matrix: np.ndarray) -> np.ndarray:
    shaped = matrix.reshape(-1, 5, matrix.shape[1])
    return (shaped - shaped.mean(axis=1, keepdims=True)).reshape(matrix.shape)


def pair_summary(matrix: np.ndarray, level_vector: np.ndarray, left: int, right: int) -> dict[str, tuple[float | None, int]]:
    result = {}
    for scope, indices in (("pooled", np.arange(len(matrix))), ("item_centered", np.arange(len(matrix)))):
        data = center(matrix)[indices] if scope == "item_centered" else matrix[indices]
        result[f"{scope}|rho"] = (rho(data[:, left], data[:, right]), len(indices))
        result[f"{scope}|alpha_z"] = (alpha_z(data[:, left], data[:, right]), len(indices))
    cells = defaultdict(list)
    for level in LEVELS:
        indices = np.flatnonzero(level_vector == level)
        data = matrix[indices]
        rv = rho(data[:, left], data[:, right])
        av = alpha_z(data[:, left], data[:, right])
        result[f"{level}|rho"] = (rv, len(indices))
        result[f"{level}|alpha_z"] = (av, len(indices))
        cells["rho"].append(rv); cells["alpha_z"].append(av)
    for metric in ("rho", "alpha_z"):
        result[f"macro_within_level|{metric}"] = (
            float(statistics.fmean(cells[metric])) if all(v is not None for v in cells[metric]) else None,
            int(np.sum(level_vector == "L1")),
        )
    return result


def _matrix_correlations(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    def correlation(values: np.ndarray) -> np.ndarray:
        centered = values - values.mean(axis=0)
        sums = np.einsum("ij,ij->j", centered, centered)
        denominator = np.sqrt(np.outer(sums, sums))
        with np.errstate(invalid="ignore", divide="ignore"):
            result = centered.T @ centered / denominator
        result[~np.outer(sums > 0.0, sums > 0.0)] = np.nan
        return result
    return correlation(rankdata(data, axis=0, method="average")), correlation(data)


def _alpha_from_correlation(value: float, n: int, raters: int = 2) -> float | None:
    if n < 2 or not math.isfinite(float(value)):
        return None
    return float(1.0 - (1.0 - float(value)) * (raters * n - 1.0) / (raters * n))


def _add_matrix_metrics(
    result: dict[str, tuple[float | None, int]],
    spearman: np.ndarray,
    pearson: np.ndarray,
    n: int,
    unit: str,
    prefix: str = "",
) -> None:
    lead = prefix + ("|" if prefix else "")
    for feature_index, feature in enumerate(FEATURES, 1):
        rv = float(spearman[0, feature_index])
        result[f"{lead}direct|{feature}|{unit}|rho"] = (rv if math.isfinite(rv) else None, n)
        result[f"{lead}direct|{feature}|{unit}|alpha_z"] = (
            _alpha_from_correlation(float(pearson[0, feature_index]), n), n
        )
    for evaluator, reference in (("llama", 16), ("mixtral", 17)):
        for candidate_index, candidate in enumerate(CANDIDATES):
            rv = float(spearman[candidate_index, reference])
            result[f"{lead}convergence|{evaluator}|{candidate}|{unit}|rho"] = (
                rv if math.isfinite(rv) else None, n
            )
            result[f"{lead}convergence|{evaluator}|{candidate}|{unit}|alpha_z"] = (
                _alpha_from_correlation(float(pearson[candidate_index, reference]), n), n
            )
    reference_correlation = float(pearson[16, 17])
    for candidate_index, candidate in enumerate(CANDIDATES):
        pair_correlations = (
            float(pearson[candidate_index, 16]),
            float(pearson[candidate_index, 17]),
            reference_correlation,
        )
        joint = (
            _alpha_from_correlation(statistics.fmean(pair_correlations), n, raters=3)
            if all(math.isfinite(value) for value in pair_correlations)
            else None
        )
        rhos = (float(spearman[candidate_index, 16]), float(spearman[candidate_index, 17]))
        mean_rho = statistics.fmean(rhos) if all(math.isfinite(value) for value in rhos) else None
        result[f"{lead}joint|{candidate}|{unit}|alpha_z"] = (joint, n)
        result[f"{lead}joint|{candidate}|{unit}|mean_rho"] = (mean_rho, n)


def _macro_rows(
    result: dict[str, tuple[float | None, int]], prefix: str = ""
) -> None:
    lead = prefix + ("|" if prefix else "")
    specs: list[tuple[str, ...]] = [("direct", feature) for feature in FEATURES]
    specs.extend(
        ("convergence", evaluator, candidate)
        for evaluator in ("llama", "mixtral") for candidate in CANDIDATES
    )
    specs.extend(("joint", candidate) for candidate in CANDIDATES)
    for spec in specs:
        metric_names = ("alpha_z", "mean_rho") if spec[0] == "joint" else ("rho", "alpha_z")
        for metric in metric_names:
            cells = [result[f"{lead}{'|'.join(spec)}|{level}|{metric}"] for level in LEVELS]
            values = [value for value, _ in cells]
            result[f"{lead}{'|'.join(spec)}|macro_within_level|{metric}"] = (
                statistics.fmean(values) if all(value is not None for value in values) else None,
                min(count for _, count in cells),
            )


def _difference_rows(result: dict[str, tuple[float | None, int]]) -> None:
    units = ("pooled", *LEVELS, "macro_within_level", "item_centered")
    for evaluator in ("llama", "mixtral"):
        for feature in FEATURES:
            for unit in units:
                for metric in ("rho", "alpha_z"):
                    left = result[f"convergence|{evaluator}|blackbox_actual_ratio|{unit}|{metric}"]
                    right = result[f"convergence|{evaluator}|{feature}|{unit}|{metric}"]
                    result[f"difference|{evaluator}|{feature}|{unit}|delta_{metric}"] = (
                        None if left[0] is None or right[0] is None else left[0] - right[0],
                        min(left[1], right[1]),
                    )
    for feature in FEATURES:
        for unit in units:
            for metric in ("alpha_z", "mean_rho"):
                left = result[f"joint|blackbox_actual_ratio|{unit}|{metric}"]
                right = result[f"joint|{feature}|{unit}|{metric}"]
                result[f"joint_difference|{feature}|{unit}|delta_{metric}"] = (
                    None if left[0] is None or right[0] is None else left[0] - right[0],
                    min(left[1], right[1]),
                )


def independent_points(rows: Sequence[Mapping[str, Any]]) -> dict[str, tuple[float | None, int]]:
    matrix = np.asarray([[float(row[name]) for name in SCORES] for row in rows])
    levels = np.asarray([row["level"] for row in rows])
    models = np.asarray([row["generation_model"] for row in rows])
    domains = np.asarray([row["domain"] for row in rows])
    centered_matrix = center(matrix)
    result: dict[str, tuple[float | None, int]] = {}
    spearman, pearson = _matrix_correlations(matrix)
    _add_matrix_metrics(result, spearman, pearson, len(matrix), "pooled")
    for level in LEVELS:
        selected = np.flatnonzero(levels == level)
        spearman, pearson = _matrix_correlations(matrix[selected])
        _add_matrix_metrics(result, spearman, pearson, len(selected), level)
    spearman, pearson = _matrix_correlations(centered_matrix)
    _add_matrix_metrics(result, spearman, pearson, len(matrix), "item_centered")
    _macro_rows(result)
    _difference_rows(result)

    for dimension, vector, names in (("generation_model", models, MODELS), ("domain", domains, DOMAINS)):
        for name in names:
            prefix = f"subgroup|{dimension}|{name}"
            temporary: dict[str, tuple[float | None, int]] = {}
            for level in LEVELS:
                selected = np.flatnonzero((vector == name) & (levels == level))
                spearman, pearson = _matrix_correlations(matrix[selected])
                _add_matrix_metrics(temporary, spearman, pearson, len(selected), level)
            _macro_rows(temporary)
            for feature in FEATURES:
                for metric in ("rho", "alpha_z"):
                    key_name = f"direct|{feature}|macro_within_level|{metric}"
                    result[f"{prefix}|{key_name}"] = temporary[key_name]
            for evaluator in ("llama", "mixtral"):
                for candidate in CANDIDATES:
                    for metric in ("rho", "alpha_z"):
                        key_name = f"convergence|{evaluator}|{candidate}|macro_within_level|{metric}"
                        result[f"{prefix}|{key_name}"] = temporary[key_name]
    return result


def _norm(text: str) -> str:
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", text).casefold()).strip()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(WORD_RE.findall(_norm(text)))


def _ngrams(values: Sequence[Any], n: int) -> tuple[Any, ...]:
    return tuple(tuple(values[i:i+n]) for i in range(len(values)-n+1)) if len(values) >= n else ()


def _chars(text: str, n: int) -> tuple[str, ...]:
    text = _norm(text)
    return tuple(text[i:i+n] for i in range(len(text)-n+1)) if len(text) >= n else ()


def _multi(context: Iterable[Any], target: Iterable[Any]) -> float:
    tc = Counter(target); total = sum(tc.values()); cc = Counter(context)
    return sum(min(v, cc.get(k, 0)) for k, v in tc.items()) / total if total else 0.0


def _types(context: Iterable[Any], target: Iterable[Any]) -> float:
    target = set(target)
    return len(target.intersection(context)) / len(target) if target else 0.0


def _lcs(left: Sequence[Any], right: Sequence[Any]) -> int:
    positions = defaultdict(list)
    for i, value in enumerate(right): positions[value].append(i)
    tails = []
    for value in left:
        for pos in reversed(positions.get(value, ())):
            insert = bisect.bisect_left(tails, pos)
            if insert == len(tails): tails.append(pos)
            else: tails[insert] = pos
    return len(tails)


def _self_bits(output: str) -> float:
    data = output.encode("utf-8", errors="replace")
    if not data: return 0.0
    funcs = (
        lambda x: zlib.compress(x, 9),
        lambda x: bz2.compress(x, compresslevel=9),
        lambda x: lzma.compress(x, preset=9),
    )
    return statistics.fmean(max(0, (len(f(data))-len(f(b"")))*8) for f in funcs)


def independent_features(prompt: str, output: str) -> dict[str, float]:
    pb = len(prompt.encode("utf-8", errors="replace")); ob = len(output.encode("utf-8", errors="replace"))
    pt = _tokens(prompt); ot = _tokens(output); p2 = _ngrams(pt,2); o2 = _ngrams(ot,2)
    return {
        "prompt_bytes": float(pb), "output_bytes": float(ob), "prompt_words": float(len(pt)),
        "output_words": float(len(ot)), "prompt_to_output_byte_ratio": pb/ob if ob else 0.0,
        "word_type_coverage": _types(pt,ot), "word_token_coverage": _multi(pt,ot),
        "word_bigram_coverage": _multi(p2,o2), "char3_coverage": _multi(_chars(prompt,3),_chars(output,3)),
        "char5_coverage": _multi(_chars(prompt,5),_chars(output,5)), "char8_coverage": _multi(_chars(prompt,8),_chars(output,8)),
        "rouge_l_recall": _lcs(ot,pt)/len(ot) if ot else 0.0,
        "output_type_token_ratio": len(set(ot))/len(ot) if ot else 0.0,
        "output_bigram_repeat_fraction": 1-len(set(o2))/len(o2) if o2 else 0.0,
        "output_self_bits_per_byte": _self_bits(output)/ob if ob else 0.0,
    }


def authority_full_audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_pair = {(*key(row), row["level"]): row for row in rows}
    lineage_path = ROOT / "experiment_baseline/v2/run_20260823_canonical/final/lineage.json"
    lineage = json.loads(lineage_path.read_bytes())
    debug_hash_by_key = {
        tuple(entry["semantic_key"]): entry["debug_file_sha256"]
        for entry in lineage["source"]["entries"]
    }
    if len(debug_hash_by_key) != 11222:
        raise AuditError("lineage debug inventory differs")
    source_scoring: dict[tuple[str, str, str], str] = {}
    source_rows: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    debug_inventory = []
    cluster_candidates: dict[tuple[str, str, str], tuple[str, str] | None] = {}
    source_path = ROOT / "experiment_baseline/v2/run_20260823_canonical/sources.jsonl"
    with source_path.open("rb") as handle:
        for raw in handle:
            source = json.loads(raw); skey = key(source)
            if skey in source_rows:
                raise AuditError(f"duplicate canonical source: {skey}")
            source_rows[skey] = source
            scoring = source.get("scoring_input_sha256")
            source_scoring[skey] = scoring
            declared = Path(source["source_file"])
            debug_path = declared if declared.is_absolute() else ROOT / declared
            debug_digest = sha_file(debug_path)
            if debug_digest != debug_hash_by_key.get(skey):
                raise AuditError(f"debug hash differs: {skey}")
            debug = json.loads(debug_path.read_bytes())
            if key(debug) != skey:
                raise AuditError(f"debug semantic identity differs: {skey}")
            metadata = debug.get("source")
            if isinstance(metadata, Mapping):
                sid = unicodedata.normalize("NFC", str(metadata.get("source_id", "")).strip())
                fingerprint = metadata.get("text_sha256")
                if not sid or not isinstance(fingerprint, str) or len(fingerprint) != 64:
                    raise AuditError(f"debug source metadata differs: {skey}")
                cluster_candidates[skey] = (sid, fingerprint)
            else:
                cluster_candidates[skey] = None
            for level in LEVELS:
                pair = source["levels"][level]
                stored = by_pair[(*skey, level)]
                if hashlib.sha256(pair["prompt"].encode()).hexdigest() != stored["prompt_sha256"]:
                    raise AuditError(f"full prompt hash differs: {skey}/{level}")
                if hashlib.sha256(pair["output"].encode()).hexdigest() != stored["output_sha256"]:
                    raise AuditError(f"full output hash differs: {skey}/{level}")
                if debug["prompts"][level] != pair["prompt"] or debug["outputs"][level] != pair["output"]:
                    raise AuditError(f"full source/debug pair differs: {skey}/{level}")
                actual = float(debug["level_metrics"][level]["actual_ratio"])
                if actual.hex() != float(stored["blackbox_actual_ratio"]).hex():
                    raise AuditError(f"full aggregate actual score differs: {skey}/{level}")
                if stored["scoring_input_sha256"] != scoring:
                    raise AuditError(f"full scoring hash differs: {skey}/{level}")
            debug_inventory.append({
                "semantic_key": list(skey), "source_file": source["source_file"], "sha256": debug_digest
            })
    if len(source_rows) != 11222:
        raise AuditError("canonical source count differs")
    debug_inventory.sort(key=lambda entry: tuple(entry["semantic_key"]))
    debug_set_sha = hashlib.sha256(canonical(debug_inventory)).hexdigest()
    if debug_set_sha != "a72f3a83d449ca747a85469b869ca5874b3e6a8959d93e2dce5d5b9172f44edd":
        raise AuditError("debug artifact set differs")

    aliases: dict[tuple[str, str], tuple[str, str]] = {}
    for skey, candidate in cluster_candidates.items():
        if candidate is None:
            continue
        alias = (skey[1], skey[2])
        if alias in aliases and aliases[alias] != candidate:
            raise AuditError(f"conflicting source cluster metadata: {alias}")
        aliases[alias] = candidate
    for skey, candidate in cluster_candidates.items():
        resolved = candidate or aliases.get((skey[1], skey[2]), (skey[2], "legacy-id-fallback"))
        stored = by_pair[(*skey, "L1")]
        if (
            stored["source_cluster_domain"] != skey[1]
            or stored["source_cluster_id"] != resolved[0]
            or stored["source_cluster_fingerprint"] != resolved[1]
        ):
            raise AuditError(f"source cluster resolution differs: {skey}")

    evaluator_counts = {}
    for evaluator in ("llama", "mixtral"):
        score_path = ROOT / f"experiment_baseline/v2/run_20260823_canonical/final/phi_{evaluator}.v2.jsonl"
        seen = set()
        with score_path.open("rb") as handle:
            for raw in handle:
                score = json.loads(raw); skey = key(score)
                if skey in seen or skey not in source_rows:
                    raise AuditError(f"score coverage differs: {evaluator}/{skey}")
                seen.add(skey)
                if score.get("scoring_input_sha256") != source_scoring[skey] or score.get("evaluator") != evaluator:
                    raise AuditError(f"score/source join differs: {evaluator}/{skey}")
                for level in LEVELS:
                    actual = float(score["levels"][level]["phi"])
                    stored = float(by_pair[(*skey, level)][f"phi_actual_{evaluator}"])
                    if actual.hex() != stored.hex():
                        raise AuditError(f"white-box actual score differs: {evaluator}/{skey}/{level}")
        if len(seen) != 11222:
            raise AuditError(f"score count differs: {evaluator}")
        evaluator_counts[evaluator] = len(seen)
    return {
        "source_items": len(source_rows), "actual_pairs": len(by_pair),
        "debug_files": len(debug_inventory), "debug_artifact_set_sha256": debug_set_sha,
        "evaluator_rows": evaluator_counts, "all_actual_values_bit_exact": True,
        "all_prompt_output_hashes_exact": True, "all_source_clusters_exact": True,
    }


def feature_spot_check(rows: Sequence[Mapping[str, Any]], n: int = 257) -> dict[str, Any]:
    selected_rows = sorted(rows, key=lambda row: hashlib.sha256("\0".join((*key(row),row["level"])).encode()).hexdigest())[:n]
    selected = {(*key(row), row["level"]): row for row in selected_rows}
    item_keys = {pair[:3] for pair in selected}
    sources_path = ROOT / "experiment_baseline/v2/run_20260823_canonical/sources.jsonl"
    seen = set()
    with sources_path.open("rb") as handle:
        for raw in handle:
            source = json.loads(raw); skey = key(source)
            if skey not in item_keys: continue
            for level in LEVELS:
                pkey = (*skey, level)
                if pkey not in selected: continue
                pair = source["levels"][level]
                recomputed = independent_features(pair["prompt"], pair["output"])
                stored = selected[pkey]
                for feature in FEATURES:
                    if float(recomputed[feature]).hex() != float(stored[feature]).hex():
                        raise AuditError(f"feature parity differs: {pkey}/{feature}")
                if hashlib.sha256(pair["prompt"].encode()).hexdigest() != stored["prompt_sha256"]:
                    raise AuditError(f"prompt digest differs: {pkey}")
                if hashlib.sha256(pair["output"].encode()).hexdigest() != stored["output_sha256"]:
                    raise AuditError(f"output digest differs: {pkey}")
                seen.add(pkey)
    if seen != set(selected):
        raise AuditError("feature spot-check source coverage differs")
    return {"pairs": n, "selection": "lowest SHA-256 semantic pair keys", "bit_exact": True}


def audit_bootstrap(metrics: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary = json.loads((HERE / "bootstrap_summary.json").read_bytes())
    with np.load(HERE / "bootstrap_checkpoint.npz", allow_pickle=False) as checkpoint:
        if set(checkpoint.files) != {"config_sha256", "keys", "completed", "values", "effective"}:
            raise AuditError("bootstrap checkpoint schema differs")
        completed = int(checkpoint["completed"].item())
        config_sha = str(checkpoint["config_sha256"].item())
        keys = [str(value) for value in checkpoint["keys"]]
        values = checkpoint["values"]
        effective = checkpoint["effective"]
    if len(config_sha) != 64 or any(label in key.lower() for key in keys for label in FORBIDDEN_LABELS):
        raise AuditError("bootstrap checkpoint config/key allowlist differs")
    if completed != 2000 or values.shape != (2000, len(keys)) or set(keys) != set(summary["metrics"]):
        raise AuditError("bootstrap checkpoint inventory differs")
    if effective.shape != values.shape:
        raise AuditError("bootstrap effective-n matrix shape differs")

    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[(row["source_cluster_domain"], row["source_cluster_id"], row["source_cluster_fingerprint"])].append(index)
    clusters = [(cluster, np.asarray(indices, dtype=int)) for cluster, indices in sorted(grouped.items())]
    if len(clusters) != 2551:
        raise AuditError("bootstrap source-cluster count differs")

    independent_values = np.full(values.shape, np.nan, dtype=float)
    independent_effective = np.zeros(effective.shape, dtype=np.int32)
    draw_digest = hashlib.sha256()
    key_position = {metric_key: index for index, metric_key in enumerate(keys)}
    maximum_replay_error = 0.0
    for replicate in range(2000):
        replicate_seed = int.from_bytes(
            hashlib.sha256(f"20260823\0{replicate}".encode("ascii")).digest()[:8], "big"
        )
        rng = np.random.default_rng(replicate_seed)
        selected = rng.integers(0, len(clusters), size=len(clusters), dtype=np.int32)
        draw_digest.update(selected.tobytes())
        indices = np.concatenate([clusters[int(index)][1] for index in selected])
        sampled_rows = [rows[int(index)] for index in indices]
        recomputed = independent_points(sampled_rows)
        if set(recomputed) != set(keys):
            raise AuditError(f"replayed metric inventory differs: replicate {replicate}")
        for metric_key, (expected_value, expected_n) in recomputed.items():
            column = key_position[metric_key]
            independent_effective[replicate, column] = expected_n
            observed_value = float(values[replicate, column])
            if expected_value is None:
                if math.isfinite(observed_value):
                    raise AuditError(f"replayed undefined metric differs: {replicate}/{metric_key}")
            else:
                independent_values[replicate, column] = expected_value
                error = abs(float(expected_value) - observed_value)
                maximum_replay_error = max(maximum_replay_error, error)
                if error > 3e-12:
                    raise AuditError(f"replayed metric differs: {replicate}/{metric_key}: {error}")
            if int(effective[replicate, column]) != expected_n:
                raise AuditError(f"replayed effective n differs: {replicate}/{metric_key}")
        if (replicate + 1) % 100 == 0:
            print(f"independent bootstrap replay {replicate + 1}/2000", flush=True)
    if draw_digest.hexdigest() != summary["draw_sequence_sha256"]:
        raise AuditError("bootstrap shared-draw sequence digest differs")
    if not np.array_equal(independent_effective, effective):
        raise AuditError("independent effective-n matrix differs")

    for column, metric_key in enumerate(keys):
        series = independent_values[:, column]
        finite = np.isfinite(series)
        selected = series[finite]
        stored = summary["metrics"][metric_key]
        expected_interval = {
            "lower": float(np.percentile(selected, 2.5)) if len(selected) else None,
            "upper": float(np.percentile(selected, 97.5)) if len(selected) else None,
        }
        finite_n = independent_effective[:, column][finite]
        expected_fields = {
            "ci_95_percentile": expected_interval,
            "finite_resamples": int(finite.sum()),
            "undefined_resamples": int(2000 - finite.sum()),
            "resample_effective_n_all_min": int(independent_effective[:, column].min()),
            "resample_effective_n_all_max": int(independent_effective[:, column].max()),
            "resample_effective_n_finite_min": int(finite_n.min()) if len(finite_n) else None,
            "resample_effective_n_finite_max": int(finite_n.max()) if len(finite_n) else None,
        }
        for field, expected_value in expected_fields.items():
            if stored.get(field) != expected_value:
                raise AuditError(f"independent bootstrap summary differs: {metric_key}/{field}")
        if metric_key in metrics["records"] and metrics["records"][metric_key] != stored:
            raise AuditError(f"metrics/bootstrap projection differs: {metric_key}")
    return {
        "replicates": completed,
        "metrics": len(keys),
        "all_replicates_all_metrics_independently_recomputed": True,
        "all_percentiles_independently_recomputed": True,
        "all_effective_n_ranges_independently_recomputed": True,
        "draw_sequence_sha256": summary["draw_sequence_sha256"],
        "maximum_replay_absolute_error": maximum_replay_error,
        "replay_tolerance": 3e-12,
    }


def audit_metrics_csv(metrics: Mapping[str, Any]) -> dict[str, Any]:
    seen = set()
    with (HERE / "metrics.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected_fields = [
            "metric_id", "point", "ci_lower", "ci_upper", "point_effective_n",
            "finite_resamples", "undefined_resamples", "resample_effective_n_all_min",
            "resample_effective_n_all_max", "resample_effective_n_finite_min",
            "resample_effective_n_finite_max",
        ]
        if reader.fieldnames != expected_fields:
            raise AuditError("metrics CSV exact schema differs")
        for row in reader:
            metric_id = row["metric_id"]
            if metric_id in seen or metric_id not in metrics["records"]:
                raise AuditError(f"metrics CSV key differs: {metric_id}")
            seen.add(metric_id)
            record = metrics["records"][metric_id]
            comparisons = {
                "point": record["point"],
                "ci_lower": record["ci_95_percentile"]["lower"],
                "ci_upper": record["ci_95_percentile"]["upper"],
                "point_effective_n": record["point_effective_n"],
                "finite_resamples": record["finite_resamples"],
                "undefined_resamples": record["undefined_resamples"],
                "resample_effective_n_all_min": record["resample_effective_n_all_min"],
                "resample_effective_n_all_max": record["resample_effective_n_all_max"],
                "resample_effective_n_finite_min": record["resample_effective_n_finite_min"],
                "resample_effective_n_finite_max": record["resample_effective_n_finite_max"],
            }
            for field, expected in comparisons.items():
                raw = row[field]
                observed = None if raw == "" else (int(raw) if field not in {"point", "ci_lower", "ci_upper"} else float(raw))
                if observed != expected:
                    raise AuditError(f"metrics CSV projection differs: {metric_id}/{field}")
    if seen != set(metrics["records"]):
        raise AuditError("metrics CSV coverage differs")
    return {"rows": len(seen), "all_columns_exact": True}


def scan_outputs() -> dict[str, Any]:
    checked = {}
    for name in SCIENTIFIC_FILES:
        path = HERE / name
        if not path.is_file() or path.is_symlink():
            raise AuditError(f"scientific output missing/unsafe: {name}")
        if name != "bootstrap_checkpoint.npz":
            data = path.read_bytes().lower()
            found = [label for label in FORBIDDEN_LABELS if label.encode() in data]
            if found:
                raise AuditError(f"disallowed result label in {name}: {found}")
        checked[name] = {"sha256": sha_file(path), "size": path.stat().st_size}

    expected_json_keys = {
        "feature_protocol.json": {
            "schema", "schema_version", "features", "text", "coverage",
            "rouge_l_recall", "output_diagnostics", "ties", "empty_strings",
            "source_protocol",
        },
        "run_config.json": {
            "schema", "schema_version", "bundle_id", "migration_id",
            "created_at_utc", "input_artifacts", "feature_protocol_sha256",
            "bootstrap", "execution", "environment", "code",
            "run_config_payload_sha256",
        },
        "feature_ledger_receipt.json": {
            "schema", "schema_version", "state", "config_sha256",
            "feature_protocol_sha256", "ledger_sha256", "items", "pairs",
            "source_clusters", "pair_set_sha256", "generation_model_items",
            "domain_items",
        },
        "bootstrap_summary.json": {
            "schema", "schema_version", "method", "replicates", "seed",
            "confidence_level", "cluster_count",
            "sampled_cluster_count_per_replicate", "cluster_definition",
            "shared_draws_for_all_scores_and_metrics", "draw_sequence_sha256",
            "metrics",
        },
        "metrics.json": {
            "schema", "schema_version", "estimand", "coverage",
            "metric_namespaces", "primary_scopes", "secondary_scope",
            "per_level_scopes", "feature_protocol", "records",
            "robust_winner_classification", "joint_reference_rankings",
            "auxiliary", "regression_checks", "scientific_limits",
        },
        "execution.json": {
            "schema", "schema_version", "state", "elapsed_seconds",
            "feature_run", "pilot_cache", "input_snapshot_before",
            "input_snapshot_after", "inputs_unchanged", "code_snapshot",
        },
    }
    for name, expected_keys in expected_json_keys.items():
        value = json.loads((HERE / name).read_bytes())
        if not isinstance(value, Mapping) or set(value) != expected_keys:
            raise AuditError(f"exact JSON top-level schema differs: {name}")

    receipt_path = HERE / "scientific_completion.json"
    receipt = json.loads(receipt_path.read_bytes())
    payload = dict(receipt)
    stored_payload = payload.pop("receipt_payload_sha256_excluding_this_field", None)
    if stored_payload != hashlib.sha256(canonical(payload)).hexdigest():
        raise AuditError("scientific completion receipt self-hash differs")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or [entry.get("path") for entry in artifacts] != list(SCIENTIFIC_FILES):
        raise AuditError("scientific completion inventory differs")
    expected = [
        {"path": name, "sha256": checked[name]["sha256"], "size": checked[name]["size"]}
        for name in SCIENTIFIC_FILES
    ]
    if artifacts != expected or receipt.get("artifact_inventory_sha256") != hashlib.sha256(
        canonical(expected)
    ).hexdigest():
        raise AuditError("scientific completion artifact binding differs")
    config = json.loads((HERE / "run_config.json").read_bytes())
    config_payload = dict(config)
    config_sha = config_payload.pop("run_config_payload_sha256", None)
    if config_sha != hashlib.sha256(canonical(config_payload)).hexdigest():
        raise AuditError("run config self-hash differs")
    if receipt.get("config_sha256") != config_sha:
        raise AuditError("scientific completion/run config binding differs")
    checked["scientific_completion.json"] = {
        "sha256": sha_file(receipt_path), "size": receipt_path.stat().st_size
    }
    return checked


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write audit.json after a complete pass")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    input_snapshot = {}
    for relative, expected in EXPECTED_INPUTS.items():
        path = ROOT / relative
        actual = sha_file(path)
        if actual != expected:
            raise AuditError(f"protected input drift: {relative}")
        input_snapshot[relative] = actual
    rows = load_rows()
    metrics = json.loads((HERE / "metrics.json").read_bytes())
    if metrics["coverage"]["actual_pairs"] != 56110 or metrics["coverage"]["source_clusters"] != 2551:
        raise AuditError("metrics coverage differs")
    independent = independent_points(rows)
    if set(independent) != set(metrics["records"]):
        missing = sorted(set(metrics["records"]) - set(independent))[:5]
        extra = sorted(set(independent) - set(metrics["records"]))[:5]
        raise AuditError(f"independent metric inventory differs: missing={missing}, extra={extra}")
    max_error = 0.0
    for metric_key, (expected, expected_n) in independent.items():
        stored = metrics["records"][metric_key]
        observed = stored["point"]
        if expected is None or observed is None:
            if expected != observed:
                raise AuditError(f"undefined point mismatch: {metric_key}")
        else:
            error = abs(float(expected) - float(observed)); max_error = max(max_error, error)
            if error > 2e-12:
                raise AuditError(f"point estimate mismatch: {metric_key}: {error}")
        if stored["point_effective_n"] != expected_n:
            raise AuditError(f"point effective n mismatch: {metric_key}")
    # Restore canonical item/level order after reversing physical rows; all values
    # and statistics must be identical.
    reshuffled = sorted(list(reversed(rows)), key=lambda row: (*key(row), LEVELS.index(row["level"])))
    reversed_points = independent_points(reshuffled)
    if independent != reversed_points:
        raise AuditError("row-order invariance failed")
    authority_check = authority_full_audit(rows)
    feature_check = feature_spot_check(rows)
    bootstrap_check = audit_bootstrap(metrics, rows)
    csv_check = audit_metrics_csv(metrics)
    output_hashes = scan_outputs()
    audited_records = []
    audited_mapping = {}
    for name in AUDIT_BOUND_FILES:
        path = HERE / name
        if Path(name).name != name or path.is_symlink() or not path.is_file():
            raise AuditError(f"audited artifact missing/unsafe: {name}")
        record = {"path": name, "sha256": sha_file(path), "size": path.stat().st_size}
        audited_records.append(record)
        audited_mapping[name] = {"sha256": record["sha256"], "size": record["size"]}
    report = {
        "schema": "actual_heuristic.independent_audit",
        "schema_version": 1,
        "state": "pass",
        "auditor_independence": "does not import benchmark_core.py or run_benchmark.py",
        "coverage": {"items": 11222, "pairs": 56110, "clusters": 2551},
        "input_snapshot": input_snapshot,
        "full_actual_join_audit": authority_check,
        "feature_spot_check": feature_check,
        "point_rebuild": {
            "all_metric_records_recomputed": True,
            "metric_count": len(independent),
            "maximum_absolute_error": max_error,
            "tolerance": 2e-12,
        },
        "row_order_invariance": True,
        "bootstrap": bootstrap_check,
        "metrics_csv_projection": csv_check,
        "output_label_allowlist_scan": {"passed": True, "artifacts": output_hashes},
        "audited_artifacts": audited_mapping,
        "audited_artifact_inventory_sha256": hashlib.sha256(
            canonical(audited_records)
        ).hexdigest(),
        "strict_json": True,
        "elapsed_seconds": time.perf_counter() - started,
    }
    if args.write:
        atomic_json(HERE / "audit.json", report)
        print(f"independent audit PASS -> {HERE / 'audit.json'}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
