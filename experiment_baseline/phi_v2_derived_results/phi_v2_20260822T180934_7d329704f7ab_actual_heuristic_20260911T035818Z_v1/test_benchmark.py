# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
import math
import random
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import audit_benchmark as auditor
import benchmark_core as core
import run_benchmark as runner


def brute_interval_alpha(matrix: np.ndarray) -> float | None:
    values = np.asarray(matrix, dtype=float)
    n, k = values.shape
    if n < 2 or k < 2:
        return None
    observed = 0.0
    for row in values:
        for left in range(k):
            for right in range(k):
                if left != right:
                    observed += (row[left] - row[right]) ** 2 / (k - 1)
    flat = values.ravel()
    expected = 0.0
    for left in range(len(flat)):
        for right in range(len(flat)):
            if left != right:
                expected += (flat[left] - flat[right]) ** 2 / (len(flat) - 1)
    if expected == 0.0:
        return 1.0 if observed == 0.0 else None
    return 1.0 - observed / expected


class FeatureProtocolTests(unittest.TestCase):
    def test_word_coverage_multiplicity_and_types(self):
        prompt = core.word_tokens("Alpha beta beta")
        output = core.word_tokens("beta beta gamma")
        self.assertEqual(core.type_containment(prompt, output), 0.5)
        self.assertEqual(core.multiset_containment(prompt, output), 2.0 / 3.0)

    def test_unicode_normalization_and_whitespace(self):
        self.assertEqual(core.normalize_surface("  STRASSE\n Straße  "), "strasse strasse")
        self.assertEqual(core.char_ngrams("你好世界", 2), ("你好", "好世", "世界"))

    def test_exact_lcs_repeated_tokens(self):
        self.assertEqual(core.lcs_length(("a", "b", "a", "c", "d"), ("b", "a", "d", "c")), 3)
        self.assertEqual(core.lcs_length((), ("x",)), 0)

    def test_surface_features_full_finite_contract(self):
        values = core.compute_surface_features("提示：你好 🌍", "你好！")
        self.assertEqual(set(values), set(core.FEATURES))
        self.assertTrue(all(math.isfinite(value) for value in values.values()))
        self.assertGreater(values["prompt_bytes"], values["prompt_words"])

    def test_empty_denominators_are_zero(self):
        values = core.compute_surface_features("abc", "")
        for name in (
            "prompt_to_output_byte_ratio", "word_type_coverage", "word_token_coverage",
            "word_bigram_coverage", "rouge_l_recall", "output_type_token_ratio",
            "output_bigram_repeat_fraction", "output_self_bits_per_byte",
        ):
            self.assertEqual(values[name], 0.0)


class AlphaTests(unittest.TestCase):
    def test_identical_columns_equal_one(self):
        values = np.asarray([1.0, 2.0, 4.0, 8.0])
        self.assertEqual(core.pairwise_continuous_alpha_z(values, values), 1.0)
        self.assertEqual(core.krippendorff_interval_exact(np.column_stack((values, values))), 1.0)

    def test_row_shuffle_invariant(self):
        matrix = np.asarray([[1.0, 2.0, 1.5], [4.0, 3.0, 2.0], [2.0, 8.0, 7.0], [9.0, 5.0, 4.0]])
        expected = core.krippendorff_interval_exact(matrix)
        self.assertEqual(expected, core.krippendorff_interval_exact(matrix[[2, 0, 3, 1]]))

    def test_pairwise_column_swap_invariant(self):
        matrix = np.asarray([[1.0, 2.0], [4.0, 3.0], [2.0, 8.0], [9.0, 5.0]])
        self.assertEqual(
            core.krippendorff_interval_exact(matrix),
            core.krippendorff_interval_exact(matrix[:, ::-1]),
        )

    def test_small_matrices_match_brute_definition(self):
        rng = np.random.default_rng(42)
        for n in (2, 3, 7):
            for k in (2, 3, 4):
                matrix = rng.normal(size=(n, k))
                self.assertAlmostEqual(
                    core.krippendorff_interval_exact(matrix), brute_interval_alpha(matrix), places=14
                )

    def test_constant_and_nonfinite_contract(self):
        self.assertEqual(core.krippendorff_interval_exact(np.ones((5, 2))), 1.0)
        self.assertIsNone(core.pairwise_continuous_alpha_z(np.ones(5), np.ones(5)))
        with self.assertRaises(core.BenchmarkError):
            core.krippendorff_interval_exact([[1.0, float("nan")], [2.0, 3.0]])

    def test_large_distinct_matrix_uses_linear_storage_path(self):
        values = np.arange(200_000, dtype=float).reshape(100_000, 2)
        result = core.krippendorff_interval_exact(values)
        self.assertTrue(math.isfinite(result))

    def test_alpha_z_fast_identity_matches_exact(self):
        rng = np.random.default_rng(9)
        values = rng.normal(size=(100, 3))
        points = core.compute_main_metrics(
            np.column_stack((values[:, :1], np.tile(values[:, 1:2], (1, 15)), values[:, 1:])),
            np.column_stack((values[:, :1], np.tile(values[:, 1:2], (1, 15)), values[:, 1:])),
            np.asarray([core.LEVELS[index % 5] for index in range(100)]),
            np.asarray([core.MODELS[index % 5] for index in range(100)]),
            np.asarray([core.DOMAINS[index % 4] for index in range(100)]),
        )
        fast = points["convergence|llama|blackbox_actual_ratio|pooled|alpha_z"][0]
        exact = core.pairwise_continuous_alpha_z(values[:, 0], values[:, 1])
        self.assertAlmostEqual(fast, exact, places=14)


class StatisticalTests(unittest.TestCase):
    def fixture(self, items: int = 20):
        rng = np.random.default_rng(123)
        values = rng.normal(size=(items * 5, len(core.SCORE_COLUMNS)))
        levels = np.asarray(core.LEVELS * items)
        models = np.asarray([core.MODELS[(i // 5) % 5] for i in range(items * 5)])
        domains = np.asarray([core.DOMAINS[(i // 5) % 4] for i in range(items * 5)])
        return values, core.center_within_items(values), levels, models, domains

    def test_direct_delta_is_exact_difference(self):
        values, centered, levels, models, domains = self.fixture()
        result = core.compute_main_metrics(values, centered, levels, models, domains)
        for evaluator in core.EVALUATORS:
            expected = (
                result[f"convergence|{evaluator}|blackbox_actual_ratio|pooled|rho"][0]
                - result[f"convergence|{evaluator}|word_type_coverage|pooled|rho"][0]
            )
            self.assertAlmostEqual(
                result[f"difference|{evaluator}|word_type_coverage|pooled|delta_rho"][0],
                expected,
            )

    def test_item_order_shuffle_invariance(self):
        values, centered, levels, models, domains = self.fixture()
        expected = core.compute_main_metrics(values, centered, levels, models, domains)
        item_order = np.asarray([3, 0, 19, *[i for i in range(20) if i not in {3, 0, 19}]])
        indices = np.concatenate([np.arange(item * 5, item * 5 + 5) for item in item_order])
        actual = core.compute_main_metrics(
            values[indices], core.center_within_items(values[indices]), levels[indices], models[indices], domains[indices]
        )
        self.assertEqual(set(expected), set(actual))
        for metric in expected:
            left, left_n = expected[metric]; right, right_n = actual[metric]
            self.assertEqual(left_n, right_n)
            if left is None or right is None:
                self.assertEqual(left, right)
            else:
                self.assertAlmostEqual(left, right, places=12, msg=metric)

    def test_macro_is_arithmetic_mean_of_five_levels(self):
        values, centered, levels, models, domains = self.fixture()
        result = core.compute_main_metrics(values, centered, levels, models, domains)
        key_base = "direct|word_type_coverage"
        expected = statistics.fmean(result[f"{key_base}|{level}|rho"][0] for level in core.LEVELS)
        self.assertAlmostEqual(result[f"{key_base}|macro_within_level|rho"][0], expected)

    def test_independent_auditor_matches_production_inventory(self):
        values, centered, levels, models, domains = self.fixture(items=40)
        production = core.compute_main_metrics(values, centered, levels, models, domains)
        production = {key: value for key, value in production.items() if runner._keep_bootstrap_key(key)}
        rows = []
        for index in range(len(values)):
            row = {
                "generation_model": str(models[index]),
                "domain": str(domains[index]),
                "id": f"item-{index // 5}",
                "level": str(levels[index]),
            }
            row.update({name: float(values[index, column]) for column, name in enumerate(core.SCORE_COLUMNS)})
            rows.append(row)
        independent = auditor.independent_points(rows)
        self.assertEqual(set(production), set(independent))
        for metric_id in production:
            self.assertEqual(production[metric_id][1], independent[metric_id][1])
            left, right = production[metric_id][0], independent[metric_id][0]
            if left is None or right is None:
                self.assertEqual(left, right, metric_id)
            else:
                self.assertAlmostEqual(left, right, places=12, msg=metric_id)


class FailClosedTests(unittest.TestCase):
    def valid_rows(self):
        rows = []
        for item in range(2):
            for level in core.LEVELS:
                row = {
                    "generation_model": "claude-opus-4-8", "domain": "arxiv", "id": f"id-{item}",
                    "level": level, "scoring_input_sha256": "a" * 64,
                    "prompt_sha256": "b" * 64, "output_sha256": "c" * 64,
                    "source_cluster_domain": "arxiv", "source_cluster_id": f"id-{item}",
                    "source_cluster_fingerprint": "legacy-id-fallback",
                    **{name: float(item + core.LEVELS.index(level) + index / 100) for index, name in enumerate(core.SCORE_COLUMNS)},
                }
                rows.append(row)
        return rows

    def test_missing_pair_fails_fixed_coverage(self):
        with self.assertRaises(core.CoverageError):
            core.dataset_arrays(self.valid_rows())

    def test_bad_hash_fails(self):
        with self.assertRaises(core.BenchmarkError):
            core.require_sha256("not-a-hash", "test")

    def test_duplicate_key_fails_ledger(self):
        rows = self.valid_rows() * 5611
        # Use a tiny direct JSONL duplicate fixture; failure occurs before global count.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rows.jsonl"
            path.write_bytes(b"".join(core.canonical_json_bytes(row, newline=True) for row in self.valid_rows()[:1] * 2))
            with self.assertRaises(core.CoverageError):
                core.load_feature_rows(path)

    def test_strict_json_converts_nonfinite_to_null(self):
        payload = core.canonical_json_bytes({"value": float("nan")})
        self.assertEqual(json.loads(payload), {"value": None})

    def test_replicate_seed_is_deterministic_and_distinct(self):
        self.assertEqual(runner._replicate_seed(17), runner._replicate_seed(17))
        self.assertNotEqual(runner._replicate_seed(17), runner._replicate_seed(18))

    def test_lineage_row_hash_mismatch_is_fatal(self):
        row = {
            "schema_version": 2,
            "generation_model": "claude-opus-4-8",
            "domain": "arxiv",
            "id": "x",
            "scoring_input_sha256": "a" * 64,
            "evaluator": "llama",
            "levels": {level: {"phi": 0.1} for level in core.LEVELS},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scores.jsonl"
            path.write_bytes(core.canonical_json_bytes(row, newline=True))
            entries = {
                ("claude-opus-4-8", "arxiv", "x"): {
                    "row_sha256": "0" * 64,
                    "scoring_input_sha256": "a" * 64,
                }
            }
            with patch.object(runner, "_path", return_value=path):
                with self.assertRaises(core.CoverageError):
                    runner.load_actual_scores("llama", entries)

    def test_ledger_exact_schema_rejects_extra_fields(self):
        row = self.valid_rows()[0]
        row["unexpected"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.jsonl"
            path.write_bytes(core.canonical_json_bytes(row, newline=True))
            with self.assertRaises(core.CoverageError):
                core.load_feature_rows(path)

    def test_completion_receipt_not_metrics_is_the_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "scientific_completion.json"
            with patch.object(runner, "SCIENTIFIC_COMPLETION", missing):
                with self.assertRaisesRegex(core.BenchmarkError, "receipt missing"):
                    runner.verify_scientific_completion("a" * 64, {})


class OfflineImportTests(unittest.TestCase):
    def test_scripts_have_no_network_or_model_imports(self):
        forbidden = {
            "requests", "httpx", "urllib", "socket", "anthropic", "openai", "google",
            "transformers", "torch", "multi_model_adapter",
        }
        for path in Path(__file__).resolve().parent.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertFalse(imports & forbidden, f"{path.name}: {imports & forbidden}")

    def test_feature_output_schema_contains_no_disallowed_score_fields(self):
        expected = {
            "generation_model", "domain", "id", "level", "scoring_input_sha256",
            "prompt_sha256", "output_sha256", "source_cluster_domain", "source_cluster_id",
            "source_cluster_fingerprint", *core.SCORE_COLUMNS,
        }
        disallowed = {
            "level_excess", "blackbox_excess", "llama_excess", "mixtral_excess",
            "baseline_mean", "excess_ratio", "phi_excess", "cf_phi_mean", "cf_phis",
        }
        self.assertEqual(expected, auditor.LEDGER_FIELDS)
        self.assertFalse(expected & disallowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
