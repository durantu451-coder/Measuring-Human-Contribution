"""
Compute Krippendorff's Alpha and Spearman rank correlation
for the 5-level information gradient experiment data.

TRUE Krippendorff's Alpha: measures inter-rater reliability.
  "Raters" = 3 compressors (zlib, bz2, lzma), each producing an independent
  excess_ratio per level per item. A (n_items × 3) reliability matrix is
  built and passed to the krippendorff package with interval metric.

  This requires the ``per_compressor`` field in result JSONs, which stores
  individual compressor values alongside the aggregate mean.

Spearman's ρ: rank correlation between information level (1=polish
  through 5=keywords, decreasing human contribution) and excess_ratio.
  Tests the monotonic gradient hypothesis. A strong NEGATIVE correlation
  is expected (higher level → lower excess_ratio).

Pseudo-Krippendorff (retained for reference): treats the 5 levels as
  5 "raters" — this measures cross-level gradient consistency, not
  inter-compressor reliability. Negative values are expected because
  levels are designed to differ.

TABLE 6 — Label agreement (PRIMARY paper-comparable metric):
agreement between the measurement and the HUMAN-DESIGNED level labels
(L1 polish=5 most human ... L5 keywords=1 least human), mirroring the
paper's Spearman/Krippendorff vs human subjective ratings. Two
"raters": rater H = label (per item constant 5,4,3,2,1), rater M =
excess_ratio. Reports pooled & per-item Spearman/Kendall, plus
Krippendorff interval alpha on per-item z-standardized values (alpha_z)
and per-item ranks (alpha_rank). Same computation as
experiment_baseline/human_label_agreement.py.
"""

from __future__ import annotations

import atexit
import json
import os
import math
from collections import defaultdict
from scipy.stats import spearmanr, kendalltau
import numpy as np

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
LOCK_DIR = os.path.join(os.path.dirname(__file__), ".locks")
DOMAINS = ["arxiv", "news", "patent", "poetry"]
LEVELS = ["L1", "L2", "L3", "L4", "L5"]
COMPRESSORS = ["zlib", "bz2", "lzma"]
LEVEL_NUM = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
# L1=polish (most human), L5=keywords (least human)
# Expected gradient: L1_excess > L2_excess > L3_excess > L4_excess > L5_excess


def _pid_is_running(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _acquire_metrics_lock():
    os.makedirs(LOCK_DIR, exist_ok=True)
    model_locks = [name for name in os.listdir(LOCK_DIR) if name.endswith('.lock') and name != 'maintenance.lock']
    if model_locks:
        raise RuntimeError(f"cannot compute metrics while model writers are active: {model_locks}")
    path = os.path.join(LOCK_DIR, 'maintenance.lock')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                owner = json.load(handle)
            pid = int(owner.get('pid', 0))
        except Exception as exc:
            raise RuntimeError(f"invalid maintenance lock: {path}") from exc
        if _pid_is_running(pid):
            raise RuntimeError(f"metrics/maintenance already active in PID {pid}")
        os.unlink(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump({'pid': os.getpid(), 'purpose': 'metrics'}, handle)
    # Close the race where a model lock appeared just before maintenance.lock.
    model_locks = [name for name in os.listdir(LOCK_DIR) if name.endswith('.lock') and name != 'maintenance.lock']
    if model_locks:
        os.unlink(path)
        raise RuntimeError(f"model writer started concurrently: {model_locks}")
    atexit.register(lambda: os.path.exists(path) and os.unlink(path))
    return path


def load_model_domain(model_tag, domain):
    """Load one result file and reject duplicate IDs."""
    fname = f"final_{domain}_5level_{model_tag}.json"
    fpath = os.path.join(RESULTS_DIR, fname)
    if not os.path.exists(fpath):
        return None
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{fname}: expected a JSON list")
    ids = [str(item.get('id')) for item in data]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{fname}: duplicate item IDs")
    return data


def get_valid_items(data):
    """Return rows satisfying the canonical numeric result schema."""
    valid = []
    for item in data:
        levels = item.get('levels')
        if not isinstance(levels, dict):
            continue
        ok = True
        for lvl in LEVELS:
            ld = levels.get(lvl)
            if not isinstance(ld, dict) or ld.get('baseline_n_valid', 0) < 3:
                ok = False
                break
            try:
                actual = float(ld['actual_ratio'])
                baseline = float(ld['baseline_mean'])
                excess = float(ld['excess_ratio'])
                output_chars = int(ld['output_chars'])
            except (KeyError, TypeError, ValueError, OverflowError):
                ok = False
                break
            if not all(math.isfinite(value) for value in (actual, baseline, excess)):
                ok = False
                break
            if abs((actual - baseline) - excess) > 1e-9 or output_chars < 80:
                ok = False
                break
        if ok:
            valid.append(item)
    return valid


def _has_complete_per_compressor(item):
    for level in LEVELS:
        pc = item['levels'][level].get('per_compressor')
        if not isinstance(pc, dict) or set(pc) != set(COMPRESSORS):
            return False
        for compressor in COMPRESSORS:
            try:
                values = [float(pc[compressor][field]) for field in (
                    'actual_ratio', 'baseline_mean', 'excess_ratio'
                )]
            except (KeyError, TypeError, ValueError, OverflowError):
                return False
            if not all(math.isfinite(value) for value in values):
                return False
            if abs((values[0] - values[1]) - values[2]) > 1e-9:
                return False
    return True


def has_per_compressor_data(data):
    """True only when every canonical row has all three compressor values."""
    valid = get_valid_items(data)
    return bool(valid) and all(_has_complete_per_compressor(item) for item in valid)


def _krippendorff_interval_exact(ratings):
    """
    Exact Krippendorff's Alpha for interval level of measurement.

    The reference ``krippendorff`` package builds a coincidence matrix of
    shape (V, V) where V = number of distinct values; for continuous data
    V ~ n_units * n_raters, so memory is O(V^2) and blows up for large
    datasets (MemoryError). This function computes the SAME value via the
    algebraic expansion of the coincidence formula — O(m) memory, O(m) time,
    exact to machine precision.

    ``ratings``: (n_units, n_raters) array; NaN marks a missing rating.
    """
    valid_rows = ~np.any(np.isnan(ratings), axis=1)
    mat = ratings[valid_rows]
    if mat.shape[0] < 2 or mat.shape[1] < 2:
        return float('nan')

    n_u = mat.shape[1]          # raters per unit (NaN rows already dropped)
    S = mat.sum(axis=1)         # per-unit sum of values
    Q = (mat ** 2).sum(axis=1)  # per-unit sum of squared values

    N = n_u * mat.shape[0]      # total observations
    T = S.sum()                 # grand sum of values
    U = Q.sum()                 # grand sum of squared values

    # numerator   = 2 * [ U - sum_u (S_u^2 - Q_u) / (n_u - 1) ]
    # denominator = (2 / (N - 1)) * (N * U - T^2)
    num = 2.0 * (U - ((S ** 2 - Q) / (n_u - 1)).sum())
    den = (2.0 / (N - 1)) * (N * U - T * T)

    if den == 0.0:
        return 1.0 if num == 0.0 else float('nan')
    return 1.0 - num / den


def compute_true_krippendorff(data):
    """
    Compute TRUE Krippendorff's Alpha with 3 compressors as raters.

    For each level separately, builds a (n_items × 3) matrix where
    columns = zlib, bz2, lzma excess_ratios. Then pools across all
    5 levels for an overall alpha.

    Uses the ``krippendorff`` package with interval metric.

    Returns:
        dict with per-level alphas, pooled alpha, and n_items.
        None if per_compressor data is not available.
    """
    if not has_per_compressor_data(data):
        return None

    valid = get_valid_items(data)
    n_items = len(valid)

    # Per-level alpha
    per_level = {}
    n_effective_per_level = {}
    all_ratings = []  # for pooled computation

    for lv in LEVELS:
        # Build (n_items × 3) matrix
        ratings = np.zeros((n_items, 3))
        for i, item in enumerate(valid):
            pc = item['levels'][lv].get('per_compressor', {})
            for j, c in enumerate(COMPRESSORS):
                ratings[i, j] = pc.get(c, {}).get('excess_ratio', np.nan)

        # Remove rows where any compressor is NaN
        valid_rows = ~np.any(np.isnan(ratings), axis=1)
        ratings_clean = ratings[valid_rows]
        n_effective_per_level[lv] = int(ratings_clean.shape[0])

        if ratings_clean.shape[0] < 2:
            per_level[lv] = float('nan')
            continue

        alpha = _krippendorff_interval_exact(ratings_clean)

        per_level[lv] = alpha
        all_ratings.append(ratings_clean)

    # Pooled: stack all levels → (5 * n_items, 3)
    if all_ratings:
        all_stacked = np.vstack(all_ratings)
        pooled_alpha = _krippendorff_interval_exact(all_stacked)
    else:
        pooled_alpha = float('nan')

    return {
        'n_items': n_items,
        'n_effective_per_level': n_effective_per_level,
        'n_effective_pooled': int(all_stacked.shape[0]) if all_ratings else 0,
        'per_level': per_level,
        'pooled': pooled_alpha,
    }


def compute_gradient_consistency(data):
    """
    For each item, check if the gradient L1>L2>L3>L4>L5 holds
    for excess_ratio. Returns fraction consistent and per-pair fractions.
    """
    valid = get_valid_items(data)
    if not valid:
        return None

    n = len(valid)
    pairs = [(0, 1), (1, 2), (2, 3), (3, 4)]
    pair_names = ["L1>L2", "L2>L3", "L3>L4", "L4>L5"]

    fully_consistent = 0
    pair_ok = {p: 0 for p in pair_names}

    for item in valid:
        vals = [item['levels'][lvl]['excess_ratio'] for lvl in LEVELS]
        if all(vals[i] > vals[i + 1] for i in range(4)):
            fully_consistent += 1
        for i, pn in enumerate(pair_names):
            if vals[i] > vals[i + 1]:
                pair_ok[pn] += 1

    return {
        'n_valid': n,
        'fully_consistent': fully_consistent / n,
        'pair_consistency': {k: v / n for k, v in pair_ok.items()},
    }


def compute_spearman(data):
    """
    Compute Spearman's ρ between level number (1-5) and excess_ratio.
    Pool all items: each contributes 5 data points (level_num, excess_ratio).
    Negative ρ = gradient holds (higher level → lower excess).
    """
    valid = get_valid_items(data)
    if not valid:
        return None

    all_level_nums = []
    all_excess = []

    per_item_rhos = []
    for item in valid:
        item_vals = [item['levels'][lvl]['excess_ratio'] for lvl in LEVELS]
        item_levels = [1, 2, 3, 4, 5]
        all_level_nums.extend(item_levels)
        all_excess.extend(item_vals)
        if len(set(item_vals)) >= 2:
            rho, _ = spearmanr(item_levels, item_vals)
            per_item_rhos.append(rho)
        else:
            per_item_rhos.append(0.0)

    pooled_rho, pooled_p = spearmanr(all_level_nums, all_excess)
    tau, tau_p = kendalltau(all_level_nums, all_excess)

    return {
        'n_valid': len(valid),
        'n_observations': len(all_level_nums),
        'spearman_rho': pooled_rho,
        'spearman_p': pooled_p,
        'kendall_tau': tau,
        'kendall_p': tau_p,
        'mean_per_item_rho': np.mean(per_item_rhos),
        'median_per_item_rho': np.median(per_item_rhos),
        'per_item_rho_std': np.std(per_item_rhos),
        'frac_negative_rho': sum(1 for r in per_item_rhos if r < 0) / len(per_item_rhos),
    }


def krippendorff_alpha_ordinal(ratings, level_of_measurement='interval'):
    """
    Compute Krippendorff's Alpha from a (n_units × n_raters) matrix.
    NaN for missing values.
    """
    n_units, n_raters = ratings.shape

    observed = []
    for u in range(n_units):
        for r in range(n_raters):
            if not np.isnan(ratings[u, r]):
                observed.append((u, r, ratings[u, r]))

    if len(observed) < 2:
        return float('nan')

    Do = 0.0
    n_pairs = 0

    for i in range(len(observed)):
        for j in range(i + 1, len(observed)):
            u1, r1, v1 = observed[i]
            u2, r2, v2 = observed[j]
            if u1 != u2:
                n_pairs += 1
                Do += (v1 - v2) ** 2

    if n_pairs == 0:
        return float('nan')

    Do /= n_pairs

    all_vals = np.array([v for _, _, v in observed])
    overall_mean = np.mean(all_vals)
    De = 2.0 * np.mean((all_vals - overall_mean) ** 2)

    if De == 0:
        return 1.0 if Do == 0 else float('nan')

    return 1.0 - Do / De


def compute_pseudo_krippendorff(data):
    """
    Compute pseudo-Krippendorff's Alpha treating 5 levels as 5 "raters".
    This measures gradient pattern consistency across items, NOT
    inter-compressor reliability (use compute_true_krippendorff for that).
    """
    valid = get_valid_items(data)
    if not valid:
        return None

    n_items = len(valid)
    ratings = np.zeros((n_items, 5))
    for i, item in enumerate(valid):
        for j, lvl in enumerate(LEVELS):
            ratings[i, j] = item['levels'][lvl]['excess_ratio']

    # z-score within each level
    ratings_z = np.zeros_like(ratings)
    for j in range(5):
        col = ratings[:, j]
        mean_j = np.mean(col)
        std_j = np.std(col)
        if std_j > 0:
            ratings_z[:, j] = (col - mean_j) / std_j

    alpha_z = krippendorff_alpha_ordinal(ratings_z)
    alpha_raw = krippendorff_alpha_ordinal(ratings)

    # Ordinal binned
    ratings_ord = np.zeros_like(ratings)
    for j in range(5):
        col = ratings[:, j]
        if len(set(col)) > 1:
            try:
                ratings_ord[:, j] = np.digitize(
                    col, np.percentile(col, np.arange(10, 100, 10))
                )
            except Exception:
                ratings_ord[:, j] = col
    alpha_ord = krippendorff_alpha_ordinal(ratings_ord)

    return {
        'n_items': n_items,
        'alpha_raw': alpha_raw,
        'alpha_z_standardized': alpha_z,
        'alpha_ordinal_binned': alpha_ord,
    }


def compute_label_agreement(data):
    """PRIMARY paper-comparable metric: agreement between the measurement
    (excess_ratio) and the HUMAN-DESIGNED level labels.

    Treat the 5-level gradient as a human subjective rating:
        L1 polish = 5 (most human) ... L5 keywords = 1 (least human).
    Two "raters" per item: rater H = label (5,4,3,2,1 constant),
    rater M = the item's excess_ratio vector. Measures how well the
    measurement reproduces the human-imposed ordering.

    Mirrors experiment_baseline/human_label_agreement.py so black-box and
    white-box numbers are directly comparable.

    Returns dict with pooled/per-item Spearman & Kendall and two
    Krippendorff interval alphas (z-standardized, rank-based), or None.
    """
    valid = get_valid_items(data)
    if not valid:
        return None

    # Human-imposed contribution scale, high→low over L1..L5
    human = [5.0, 4.0, 3.0, 2.0, 1.0]

    rows = [[item['levels'][lv]['excess_ratio'] for lv in LEVELS]
            for item in valid]

    # Pooled Spearman / Kendall over all (item × level) rows
    flat_h = [h for _ in rows for h in human]
    flat_s = [v for r in rows for v in r]
    pooled_rho, _ = spearmanr(flat_h, flat_s)
    pooled_tau, _ = kendalltau(flat_h, flat_s)

    # Mean per-item Spearman / Kendall (within-item agreement)
    item_rhos, item_taus = [], []
    for r in rows:
        if len(set(r)) >= 2:
            rho, _ = spearmanr(human, r)
            tau, _ = kendalltau(human, r)
            item_rhos.append(rho)
            item_taus.append(tau)
        else:
            item_rhos.append(0.0)
            item_taus.append(0.0)

    # alpha_z: per-item z-standardized values, 2 raters (H, M)
    def _zstd(xs):
        n = len(xs)
        m = sum(xs) / n
        var = sum((x - m) ** 2 for x in xs) / (n - 1)
        sd = var ** 0.5
        return None if sd == 0 else [(x - m) / sd for x in xs]

    hz = _zstd(human)
    z_pairs = []
    for r in rows:
        zs = _zstd(r)
        if zs is not None:
            z_pairs.extend(zip(hz, zs))
    a_z = (_krippendorff_interval_exact(np.array(z_pairs))
           if z_pairs else float('nan'))

    # alpha_rank: per-item ranks (H rank fixed 5..1, score rank 1..5)
    hr = [5.0, 4.0, 3.0, 2.0, 1.0]
    r_pairs = []
    for r in rows:
        sr = _rankdata_local(r)
        r_pairs.extend(zip(hr, sr))
    a_rk = (_krippendorff_interval_exact(np.array(r_pairs))
            if r_pairs else float('nan'))

    n = len(rows)
    return {
        'n_valid': n,
        'pooled_spearman': pooled_rho,
        'pooled_kendall': pooled_tau,
        'mean_item_spearman': float(np.mean(item_rhos)),
        'mean_item_kendall': float(np.mean(item_taus)),
        'alpha_z': a_z,
        'alpha_rank': a_rk,
    }


def _rankdata_local(xs):
    """Average-rank of xs (1-based), ties get mean rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def compute_level_stats(data):
    """Compute per-level mean and std of excess_ratio."""
    valid = get_valid_items(data)
    if not valid:
        return None

    stats = {}
    for lvl in LEVELS:
        vals = [item['levels'][lvl]['excess_ratio'] for item in valid]
        actual_vals = [item['levels'][lvl]['actual_ratio'] for item in valid]
        stats[lvl] = {
            'mean_excess': np.mean(vals),
            'std_excess': np.std(vals),
            'median_excess': np.median(vals),
            'mean_actual': np.mean(actual_vals),
            'std_actual': np.std(actual_vals),
        }
    return stats


def main():
    _acquire_metrics_lock()
    # Find all model tags from files
    model_tags = set()
    for f in os.listdir(RESULTS_DIR):
        if f.startswith('final_') and f.endswith('.json'):
            parts = f.replace('final_', '').replace('.json', '').split('_5level_')
            if len(parts) == 2:
                model_tags.add(parts[1])

    model_tags = sorted(model_tags)
    if not model_tags:
        raise SystemExit(
            "no result files found in %s\n"
            "Expected files named final_<domain>_5level_<model>.json for domains %s.\n"
            "Refusing to emit an empty label_agreement_summary.json."
            % (RESULTS_DIR, DOMAINS)
        )
    print(f"Found models: {model_tags}")
    print(f"Domains: {DOMAINS}")
    print("=" * 100)

    # ── TABLE 1: Mean Excess Ratio ──
    print("\n" + "=" * 100)
    print("TABLE 1: MEAN EXCESS RATIO PER LEVEL, PER MODEL, PER DOMAIN")
    print("=" * 100)

    for model in model_tags:
        print(f"\n{'─' * 90}")
        print(f"  MODEL: {model}")
        print(f"{'─' * 90}")
        header = (f"{'Domain':<10}"
                  + "".join(f"{'L' + str(i + 1):>18}" for i in range(5))
                  + f"{'N_items':>10}")
        print(header)
        print("-" * len(header))
        for domain in DOMAINS:
            data = load_model_domain(model, domain)
            if data is None:
                continue
            stats = compute_level_stats(data)
            if stats is None:
                print(f"{domain:<10}{'NO VALID DATA':>80}")
                continue
            valid = get_valid_items(data)
            vals = [f"{stats[f'L{i + 1}']['mean_excess']:+.4f}" for i in range(5)]
            print(f"{domain:<10}" + "".join(f"{v:>18}" for v in vals) + f"{len(valid):>10}")

    # ── TABLE 2: Spearman's ρ ──
    print("\n" + "=" * 100)
    print("TABLE 2: SPEARMAN'S ρ (Level Number vs. Excess Ratio)")
    print("  Expected: NEGATIVE ρ (higher level → lower human contribution)")
    print("=" * 100)

    spearman_results = {}
    for model in model_tags:
        spearman_results[model] = {}
        print(f"\n  MODEL: {model}")
        print(f"  {'Domain':<10} {'ρ':>10} {'p-value':>12} {'Kendall τ':>12} "
              f"{'Mean per-item ρ':>18} {'% negative ρ':>15} {'N_items':>10}")
        print(f"  {'─' * 90}")
        for domain in DOMAINS:
            data = load_model_domain(model, domain)
            if data is None:
                continue
            result = compute_spearman(data)
            if result is None:
                print(f"  {domain:<10} {'NO DATA':>50}")
                continue
            spearman_results[model][domain] = result
            print(f"  {domain:<10} {result['spearman_rho']:>+10.4f} {result['spearman_p']:>12.2e} "
                  f"{result['kendall_tau']:>+12.4f} {result['mean_per_item_rho']:>+18.4f} "
                  f"{result['frac_negative_rho']:>15.2%} {result['n_valid']:>10}")

    # ── TABLE 3: TRUE Krippendorff's Alpha ──
    print("\n" + "=" * 100)
    print("TABLE 3: TRUE KRIPPENDORFF'S ALPHA (3 Compressors as Raters)")
    print("  Raters: zlib, bz2, lzma — each produces an independent excess_ratio")
    print("  Measures: do the 3 compressors agree on contribution level?")
    print("  α ≥ 0.80 → good reliability; α ≥ 0.667 → acceptable")
    print("  α < 0 → systematic disagreement (compressors rank items differently)")
    print("=" * 100)

    krippendorff_results = {}
    any_has_pc = False
    for model in model_tags:
        krippendorff_results[model] = {}
        print(f"\n  MODEL: {model}")
        header = (f"  {'Domain':<10} {'α pooled':>10} "
                  + "".join(f"{'α ' + lv:>10}" for lv in LEVELS)
                  + f"  {'N_items':>8} {'N_eff':>8}")
        print(header)
        print(f"  {'─' * 75}")
        for domain in DOMAINS:
            data = load_model_domain(model, domain)
            if data is None:
                continue
            result = compute_true_krippendorff(data)
            if result is None:
                # Fall back to "NOT AVAILABLE"
                print(f"  {domain:<10} {'PER-COMPRESSOR DATA NOT AVAILABLE':>60}")
                continue
            any_has_pc = True
            krippendorff_results[model][domain] = result
            parts = [f"{result['pooled']:>10.4f}"]
            for lv in LEVELS:
                parts.append(f"{result['per_level'].get(lv, float('nan')):>10.4f}")
            n_effective = min(result['n_effective_per_level'].values())
            print(f"  {domain:<10}" + "".join(parts)
                  + f"  {result['n_items']:>8} {n_effective:>8}")

    if not any_has_pc:
        print("\n  *** NO PER-COMPRESSOR DATA FOUND. Run recompute_per_compressor.py first. ***")

    # TABLE 4 was removed on 2026-08-22. Its historical pseudo-alpha paired
    # observations from different units and was not a valid Krippendorff alpha.
    # Gradient consistency is reported directly in TABLE 5 instead.

    # ── TABLE 5: Gradient Consistency ──
    print("\n" + "=" * 100)
    print("TABLE 5: GRADIENT CONSISTENCY (fraction of items with monotonic L1>L2>L3>L4>L5)")
    print("=" * 100)

    for model in model_tags:
        print(f"\n  MODEL: {model}")
        print(f"  {'Domain':<10} {'Full L1>...>L5':>16} {'L1>L2':>10} {'L2>L3':>10} "
              f"{'L3>L4':>10} {'L4>L5':>10} {'N_items':>10}")
        print(f"  {'─' * 75}")
        for domain in DOMAINS:
            data = load_model_domain(model, domain)
            if data is None:
                continue
            result = compute_gradient_consistency(data)
            if result is None:
                print(f"  {domain:<10} {'NO DATA':>45}")
                continue
            pc = result['pair_consistency']
            print(f"  {domain:<10} {result['fully_consistent']:>16.2%} "
                  f"{pc['L1>L2']:>10.2%} {pc['L2>L3']:>10.2%} "
                  f"{pc['L3>L4']:>10.2%} {pc['L4>L5']:>10.2%} "
                  f"{result['n_valid']:>10}")

    # ── TABLE 6: Label Agreement (PRIMARY paper-comparable) ──
    print("\n" + "=" * 100)
    print("TABLE 6: LABEL AGREEMENT — measurement vs HUMAN-DESIGNED level labels")
    print("  Labels: L1 polish=5 (most human) ... L5 keywords=1 (least human),")
    print("          treated as human subjective ratings (as in the MI paper).")
    print("  Raters: H = label (5,4,3,2,1), M = excess_ratio.")
    print("  pooled ρ/τ over all (item×level) rows; item ρ/τ = mean within-item;")
    print("  α_z = Krippendorff interval on per-item z-scores; α_rk = on per-item ranks.")
    print("  Positive & high = measurement reproduces the human gradient.")
    print("=" * 100)

    label_agreement_results = {}
    for model in model_tags:
        label_agreement_results[model] = {}
        print(f"\n  MODEL: {model}")
        print(f"  {'Domain':<10} {'pool ρ':>9} {'pool τ':>9} {'item ρ':>9} "
              f"{'item τ':>9} {'α_z':>9} {'α_rk':>9} {'N_items':>9}")
        print(f"  {'─' * 84}")
        for domain in DOMAINS:
            data = load_model_domain(model, domain)
            if data is None:
                continue
            result = compute_label_agreement(data)
            if result is None:
                print(f"  {domain:<10} {'NO DATA':>50}")
                continue
            label_agreement_results[model][domain] = result
            print(f"  {domain:<10} {result['pooled_spearman']:>+9.4f} "
                  f"{result['pooled_kendall']:>+9.4f} "
                  f"{result['mean_item_spearman']:>+9.4f} "
                  f"{result['mean_item_kendall']:>+9.4f} "
                  f"{result['alpha_z']:>9.4f} {result['alpha_rank']:>9.4f} "
                  f"{result['n_valid']:>9}")

    # ── Comparison with Paper ──
    print("\n" + "=" * 100)
    print("COMPARISON WITH PAPER (arXiv:2408.14792 / 互信息.pdf)")
    print("=" * 100)
    print("""
    IMPORTANT: Neither version of the paper reports Krippendorff's Alpha or
    Spearman's ρ. The papers use descriptive statistics (box plots,
    distribution comparisons) and the proposed information-theoretic measure
    itself as validation.

    The ONLY statistical reliability metric reported in the paper is:
      → Inter-annotator agreement rate: 91.47%
        (proportion of cases where all 3 human annotators gave the same label
        for whether the measured contribution gap between two items was >0.1)

    Our Spearman's ρ tests the monotonic gradient hypothesis
    (higher level → lower excess_ratio) — same validation framework
    the paper uses (via box plots rather than rank correlation).

    Our Krippendorff's Alpha (3 compressors as raters) measures
    inter-compressor reliability — analogous to the paper's
    inter-annotator agreement, but for the measurement instrument itself.

    KEY DIFFERENCES:
    - Paper uses GPT-3.5, Llama-3, Mixtral as generation models
    - We use Claude-Sonnet-5, Gemini-3.6-Flash, Gemini-3.1-Pro-Preview
    - Paper has 2000 items/domain (same as our target)
    - Paper uses GPT-3.5 as the measurement (compressor) model
    - We use counterfactual baseline with zlib/bz2/lzma (model-free)
    - Paper requires access to model output probabilities p_θ(y|x)
    - Our method works with any black-box API
    """)

    # ── INTERIM SUMMARY ──
    print("=" * 100)
    print("INTERIM WITHIN-MODEL DESCRIPTIVES — NOT A CROSS-MODEL RANKING")
    print("Counts remain below the 2,000/domain target and differ by model/domain.")
    print("Compare models only after matched coverage or an explicit common-ID analysis.")
    print("=" * 100)
    print(f"\n{'Model':<30} {'Domains':>7} {'Total N':>9} {'Min/Max N':>13} "
          f"{'Avg |ρ|':>10} {'Avg Grad%':>10} {'α pooled':>10} "
          f"{'Lbl pool ρ':>11} {'Lbl α_z':>9}")
    print("-" * 125)
    for model in model_tags:
        rhos = []
        grads = []
        alphas = []
        lbl_rhos = []
        lbl_alpha_z = []
        domain_ns = []
        best_domain = ('', 0.0)
        worst_domain = ('', 1.0)
        for domain in DOMAINS:
            if domain in spearman_results.get(model, {}):
                r = abs(spearman_results[model][domain]['spearman_rho'])
                rhos.append(r)
                if r > best_domain[1]:
                    best_domain = (domain, r)
                if r < worst_domain[1]:
                    worst_domain = (domain, r)
            data = load_model_domain(model, domain)
            if data:
                domain_ns.append(len(get_valid_items(data)))
                gc = compute_gradient_consistency(data)
                if gc:
                    grads.append(gc['fully_consistent'])
            if domain in krippendorff_results.get(model, {}):
                a = krippendorff_results[model][domain].get('pooled', float('nan'))
                if not math.isnan(a):
                    alphas.append(a)
            if domain in label_agreement_results.get(model, {}):
                la = label_agreement_results[model][domain]
                if not math.isnan(la['pooled_spearman']):
                    lbl_rhos.append(la['pooled_spearman'])
                if not math.isnan(la['alpha_z']):
                    lbl_alpha_z.append(la['alpha_z'])
        if rhos:
            avg_rho = np.mean(rhos)
            avg_grad = np.mean(grads) if grads else 0.0
            avg_alpha = np.mean(alphas) if alphas else float('nan')
            avg_lbl_rho = np.mean(lbl_rhos) if lbl_rhos else float('nan')
            avg_lbl_az = np.mean(lbl_alpha_z) if lbl_alpha_z else float('nan')
            alpha_str = f"{avg_alpha:>10.4f}" if not math.isnan(avg_alpha) else f"{'N/A':>10}"
            lbl_rho_str = f"{avg_lbl_rho:>+11.4f}" if not math.isnan(avg_lbl_rho) else f"{'N/A':>11}"
            lbl_az_str = f"{avg_lbl_az:>9.4f}" if not math.isnan(avg_lbl_az) else f"{'N/A':>9}"
            coverage = f"{min(domain_ns)}/{max(domain_ns)}" if domain_ns else "0/0"
            print(f"{model:<30} {len(domain_ns):>7} {sum(domain_ns):>9} {coverage:>13} "
                  f"{avg_rho:>10.4f} {avg_grad:>10.2%} {alpha_str} "
                  f"{lbl_rho_str} {lbl_az_str}")

    # Keep the machine-readable TABLE 6 artifact synchronized with stdout.
    output_path = os.path.join(RESULTS_DIR, "label_agreement_summary.json")
    temporary_path = output_path + f".tmp.{os.getpid()}"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(
            label_agreement_results,
            handle,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=lambda value: value.item() if isinstance(value, np.generic) else value,
        )
        handle.write("\n")
    os.replace(temporary_path, output_path)
    print(f"\nSaved TABLE 6 JSON: {output_path}")


if __name__ == '__main__':
    main()
