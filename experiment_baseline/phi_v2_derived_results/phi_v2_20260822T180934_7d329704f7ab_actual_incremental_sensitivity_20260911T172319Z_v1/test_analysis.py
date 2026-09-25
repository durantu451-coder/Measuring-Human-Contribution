#!/usr/bin/env python3
"""Unit and synthetic end-to-end tests for the frozen sensitivity bundle."""
from __future__ import annotations

import builtins
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.dont_write_bytecode = True
import analysis_core as core
import run_analysis as runner
import audit_analysis as independent_audit


class CoreTests(unittest.TestCase):
    def test_strict_json_duplicate_and_nonfinite(self) -> None:
        with self.assertRaises(core.AnalysisError):
            core.strict_json_loads('{"a":1,"a":2}')
        with self.assertRaises(core.AnalysisError):
            core.strict_json_loads('{"a":NaN}')
        self.assertEqual(core.strict_json_loads('{"a":1}'), {"a": 1})

    def test_strict_json_record_binds_parsed_bytes_hash_and_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"; payload = b'{"a":1}\n'; path.write_bytes(payload)
            value, digest, size = core.strict_json_load_record(path)
            self.assertEqual(value, {"a": 1}); self.assertEqual(digest, hashlib.sha256(payload).hexdigest()); self.assertEqual(size, len(payload))

    def test_key_normalization_and_domain_sensitive_cluster(self) -> None:
        self.assertEqual(core.normalize_semantic_key(" m ", "NEWS", "é"), ("m", "news", "é"))
        composed = core.normalize_semantic_key("m", "news", "é")
        self.assertEqual(composed[2], "é")
        self.assertNotEqual(
            core.normalize_cluster_key("news", "7", "legacy-id-fallback"),
            core.normalize_cluster_key("patent", "7", "legacy-id-fallback"),
        )

    def test_alpha_matches_direct_pair_formula(self) -> None:
        matrix = np.asarray([[0.0, 1.0, 3.0], [2.0, 2.0, 5.0], [4.0, 8.0, 7.0]])
        n, k = matrix.shape
        observed = 0.0
        for row in matrix:
            observed += sum((row[i] - row[j]) ** 2 for i in range(k) for j in range(k) if i != j) / (k - 1)
        flat = matrix.ravel(); expected = 0.0
        for left in range(len(flat)):
            for right in range(len(flat)):
                if left != right:
                    expected += (flat[left] - flat[right]) ** 2 / (len(flat) - 1)
        brute = 1.0 - observed / expected
        self.assertAlmostEqual(core.krippendorff_interval_exact(matrix), brute, places=14)

    def test_constant_alpha_and_ties(self) -> None:
        self.assertIsNone(core.pairwise_continuous_alpha_z(np.ones(5), np.arange(5.0)))
        self.assertIsNone(core.spearman_rho(np.ones(5), np.arange(5.0)))
        tied = core.spearman_rho(np.asarray([1., 1., 2., 3.]), np.asarray([4., 3., 2., 1.]))
        self.assertTrue(math.isfinite(tied))

    def test_bootstrap_draw_sha(self) -> None:
        self.assertEqual(core.bootstrap_draw_sequence_sha256(), core.EXPECTED_DRAW_SHA256)
        first = core.bootstrap_draw(0)
        self.assertEqual(first.dtype, np.int32)
        self.assertEqual(first.shape, (2551,))

    def test_fold_assignment_invariant_and_domain_sensitive(self) -> None:
        domains = np.asarray([domain for domain in ("a", "b") for _ in range(50)], dtype="U1")
        keys = tuple((domains[i], str(i), "f") for i in range(100))
        rows = tuple(np.asarray([i], dtype=np.int32) for i in range(100))
        left = core.assign_grouped_folds(keys, rows, domains, seed=17)
        right = core.assign_grouped_folds(tuple(reversed(keys)), tuple(reversed(rows)), domains, seed=17)
        self.assertEqual(left, right)
        self.assertEqual(set(left.values()), set(range(5)))
        for domain in ("a", "b"):
            self.assertEqual(set(left[key] for key in keys if key[0] == domain), set(range(5)))

    def test_alpha_tie_break_prefers_larger(self) -> None:
        scores = [
            {"alpha": alpha, "mse": (2.0 if alpha == 1.0 else 2.0 + 1e-12 if alpha == 10.0 else 9.0), "holdout_rows": 100}
            for alpha in core.RIDGE_ALPHAS
        ]
        self.assertEqual(core.select_ridge_alpha(scores), 10.0)
        corrupt = list(scores); corrupt[0] = {**corrupt[0], "alpha": 999.0}
        with self.assertRaises(core.AnalysisError):
            core.select_ridge_alpha(corrupt)

    def test_checkpoint_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "block.npz"
            values = np.arange(6.0).reshape(2, 3)
            effective = np.full(values.shape, 5, dtype=np.int32)
            keys = np.asarray(["a", "b", "c"])
            arrays = {"values": values, "effective": effective, "keys": keys}
            metadata = {
                "schema": "actual_incremental_sensitivity.bootstrap_checkpoint",
                "schema_version": 1,
                "arrays": core.checkpoint_array_descriptor(arrays),
                "payload_sha256": core.checkpoint_payload_sha256(arrays),
            }
            core.write_npz_atomic(path, arrays, metadata)
            with np.load(path, allow_pickle=False) as stored:
                metadata_json = np.asarray(stored["metadata_json"])
            with path.open("wb") as handle:
                np.savez(handle, values=values, effective=effective, keys=np.asarray(["a", "b", "wrong"]), metadata_json=metadata_json)
            with self.assertRaises(core.AnalysisError):
                core.write_npz_atomic(path, arrays, metadata)

    def test_ancestor_identity_swap_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); parent = root / "parent"; child = parent / "child"; child.mkdir(parents=True)
            snapshot = core._plain_component_snapshot(child)
            parent.rename(root / "old-parent"); parent.mkdir(); (parent / "child").mkdir()
            with self.assertRaises(core.AnalysisError): core.verify_plain_component_snapshot(snapshot)

    def test_atomic_create_never_overwrites_concurrent_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "immutable.json"
            real_link = os.link
            def race(source, target, **kwargs):
                destination.write_bytes(b"concurrent")
                raise FileExistsError(str(destination))
            with mock.patch("os.link", side_effect=race):
                with self.assertRaises(core.AnalysisError): core.atomic_write_bytes(destination, b"intended")
            self.assertEqual(destination.read_bytes(), b"concurrent")
            self.assertIs(real_link, os.link)

    def test_command_scoped_failure_receipts_are_distinct(self) -> None:
        paths = {runner._failure_receipt_path(command) for command in ("prepare", "validate-prepared", "analyze", "finalize")}
        self.assertEqual(len(paths), 4)
        self.assertTrue(all(path.name.endswith(".FAILED.json") for path in paths))

    def test_existing_audit_requires_fresh_checkpoint_evidence(self) -> None:
        fields = ("authority", "coverage", "auditor_independence", "folds", "raw_algebra", "models", "point_statistics", "bootstrap", "checkpoints", "projection_byte_comparison", "structured_output_scan")
        existing = {field: {"value": field} for field in fields}; rebuilt = json.loads(json.dumps(existing))
        independent_audit.validate_recomputed_audit_evidence(existing, rebuilt)
        rebuilt["checkpoints"]["value"] = "tampered"
        with self.assertRaises(independent_audit.AuditFailure): independent_audit.validate_recomputed_audit_evidence(existing, rebuilt)

    def test_checkpoint_index_header_rejects_version_and_extra_fields(self) -> None:
        base = {"schema": "actual_incremental_sensitivity.checkpoint_index", "schema_version": 1, "config_sha256": "d" * 64, "oof": [], "bootstrap": []}
        valid = core.payload_with_hash(base); runner._validate_checkpoint_index_header(valid, "d" * 64)
        wrong_version = dict(valid); wrong_version["schema_version"] = 2
        with self.assertRaises(core.AnalysisError): runner._validate_checkpoint_index_header(wrong_version, "d" * 64)
        extra = {**valid, "forged": True}
        with self.assertRaises(core.AnalysisError): runner._validate_checkpoint_index_header(extra, "d" * 64)

    def test_checkpoint_noncanonical_bytes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "block.npz"
            arrays = {"values": np.arange(4.0), "effective": np.arange(4, dtype=np.int32), "keys": np.asarray(["a", "b", "c", "d"])}
            metadata = {"schema": "actual_incremental_sensitivity.bootstrap_checkpoint", "schema_version": 1, "arrays": core.checkpoint_array_descriptor(arrays), "payload_sha256": core.checkpoint_payload_sha256(arrays)}
            core.write_npz_atomic(path, arrays, metadata)
            deterministic_sha = core.sha256_file(path)
            with path.open("wb") as handle:
                np.savez(handle, **arrays, metadata_json=np.asarray(core.canonical_json_bytes(metadata).decode("utf-8")))
            self.assertNotEqual(core.sha256_file(path), deterministic_sha)
            with self.assertRaises(core.AnalysisError):
                core.write_npz_atomic(path, arrays, metadata)

    def test_independent_checkpoint_audit_rejects_count_only_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); oof = root / "checkpoints" / "oof"; boot = root / "checkpoints" / "bootstrap"; oof.mkdir(parents=True); boot.mkdir()
            oof_paths = []
            for index in range(10):
                path = oof / f"duplicate_{index}.npz"; path.write_bytes(b""); oof_paths.append(path)
            boot_paths = []
            for index in range(80):
                path = boot / f"duplicate_{index}.npz"; path.write_bytes(b""); boot_paths.append(path)
            def record(path): return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(b"").hexdigest(), "size": 0}
            base = {"schema": "actual_incremental_sensitivity.checkpoint_index", "schema_version": 1, "config_sha256": "d" * 64, "oof": sorted(map(record, oof_paths), key=lambda row: row["path"]), "bootstrap": sorted(map(record, boot_paths), key=lambda row: row["path"])}
            index = {**base, "payload_sha256_excluding_this_field": hashlib.sha256(independent_audit.canonical(base)).hexdigest()}
            core.atomic_write_json(root / "checkpoint_index.json", index)
            original = independent_audit.HERE
            try:
                independent_audit.HERE = root
                with mock.patch.object(independent_audit, "expected_prediction_keys", return_value=["label"]), mock.patch.object(independent_audit, "hgb_import_available", return_value=False):
                    with self.assertRaises(independent_audit.AuditFailure): independent_audit.audit_checkpoints("d" * 64, {}, {}, {}, {}, [])
            finally: independent_audit.HERE = original

    def test_resource_monitor_fails_closed_at_exit(self) -> None:
        monitor = core.ResourceMonitor(hard_limit=1, interval_seconds=10.0)
        with mock.patch.object(monitor, "_rss", return_value=2):
            with self.assertRaises(core.ResourceLimitError):
                with monitor:
                    pass

    def test_empty_hidden_or_unknown_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".unmanifested").mkdir()
            with self.assertRaises(core.AnalysisError):
                core.inspect_plain_tree(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "checkpoints").mkdir()
            self.assertEqual(core.inspect_plain_tree(root, allowed_directories={"checkpoints"}), [])

    def test_documented_in_memory_compile_creates_no_pycache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "module.py"; source.write_text("value = 1\n", encoding="utf-8")
            compile(source.read_text(encoding="utf-8"), str(source), "exec")
            self.assertFalse((root / "__pycache__").exists())

    def test_partial_prepare_prefix_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = runner.BUNDLE_DIR
            try:
                runner.BUNDLE_DIR = root
                for expected_length, name in enumerate(runner.PREPARED_FILES, 1):
                    (root / name).write_text("placeholder", encoding="utf-8")
                    self.assertEqual(runner._valid_prepare_prefix_length(), expected_length)
                for name in runner.PREPARED_FILES: (root / name).unlink()
                (root / "fold_assignments.json").write_text("orphan", encoding="utf-8")
                with self.assertRaises(core.AnalysisError):
                    runner._valid_prepare_prefix_length()
            finally:
                runner.BUNDLE_DIR = original

    def test_root_and_destination_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); real = parent / "real"; real.mkdir(); link = parent / "link"
            try:
                os.symlink(real, link, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            with self.assertRaises(core.AnalysisError):
                core.require_plain_directory(link, parent=parent)
            dangling = parent / "dangling"
            os.symlink(parent / "missing", dangling, target_is_directory=True)
            self.assertTrue(core.path_lexists(dangling))
            with self.assertRaises(core.AnalysisError):
                core.require_absent_or_plain_directory(dangling, parent=parent)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_is_rejected_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); target = parent / "target"; junction = parent / "junction"; target.mkdir(); (target / "child").mkdir()
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            if result.returncode != 0:
                self.skipTest("junction creation unavailable")
            try:
                self.assertTrue(core.is_reparse_or_link(junction))
                with self.assertRaises(core.AnalysisError):
                    core.require_plain_directory(junction, parent=parent)
                with self.assertRaises(core.AnalysisError):
                    core.require_plain_directory(junction / "child")
                with self.assertRaises(core.AnalysisError):
                    core.inspect_plain_tree(junction / "child")
            finally:
                os.rmdir(junction)

    def test_weighted_median_matches_integer_expansion(self) -> None:
        values = np.asarray([5.0, 1.0, 9.0, 3.0])
        weights = np.asarray([2, 3, 1, 4], dtype=np.int64)
        expected = float(np.median(np.repeat(values, weights)))
        self.assertEqual(core.weighted_median(values, weights), expected)

    def test_scientific_completion_rejects_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "checkpoints" / "oof").mkdir(parents=True)
            (root / "checkpoints" / "bootstrap").mkdir(parents=True)
            for name, content in (("code.py", b"pass\n"), ("RUNBOOK.md", b"test\n"), ("run_config.json", b"{}\n"), ("metrics.json", b"{}\n")):
                (root / name).write_bytes(content)
            checkpoint = core.payload_with_hash({
                "schema": "actual_incremental_sensitivity.checkpoint_index",
                "schema_version": 1, "config_sha256": core.sha256_file(root / "run_config.json"),
                "oof": [], "bootstrap": [],
            })
            core.atomic_write_json(root / "checkpoint_index.json", checkpoint)
            config_sha = core.sha256_file(root / "run_config.json")
            execution = core.payload_with_hash({
                "schema": "actual_incremental_sensitivity.execution", "schema_version": 1,
                "state": "scientific_outputs_complete", "config_sha256": config_sha,
                "elapsed_seconds": 1.0, "environment": core.environment_receipt(),
                "resources": {
                    "rss_backend": "psutil", "rss_baseline_bytes": 10, "rss_peak_bytes": 12,
                    "rss_incremental_peak_bytes": 2, "phase_rss_peaks_bytes": {"test": 12},
                    "tracemalloc_current_bytes": 1, "tracemalloc_peak_bytes": 2,
                    "rss_target_bytes": core.RSS_TARGET, "rss_hard_limit_bytes": core.RSS_HARD_LIMIT,
                    "rss_limit_semantics": "sampled_process_rss_hard_limit", "rss_sampling_interval_milliseconds": 50, "synchronous_exit_rss_sample": True,
                },
                "external_api_calls": 0, "network_access": False, "gpu": False,
                "model_generation": False, "text_regeneration": False, "recompression": False,
                "prompt_output_text_reads": 0, "counterfactual_fields_used": False,
                "authority_modified": False, "word_modified": False,
            })
            core.atomic_write_json(root / "execution.json", execution)
            formal = ("run_config.json", "checkpoint_index.json", "metrics.json", "execution.json")
            records = sorted([core.file_record(root / name, root) for name in formal], key=lambda row: row["path"])
            code = [core.file_record(root / "code.py", root)]
            completion = core.payload_with_hash({
                "schema": "actual_incremental_sensitivity.scientific_completion", "schema_version": 1,
                "state": "complete_pending_independent_audit", "bundle_id": runner.BUNDLE_ID,
                "config_sha256": core.sha256_file(root / "run_config.json"),
                "authority_ledger_sha256": core.EXPECTED_LEDGER_SHA256,
                "checkpoint_index_sha256": core.sha256_file(root / "checkpoint_index.json"),
                "artifacts": records,
                "artifact_inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(records)),
                "code_snapshot": {"files": code, "inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(code))},
            })
            core.atomic_write_json(root / "scientific_completion.json", completion)
            with mock.patch.multiple(runner, BUNDLE_DIR=root, CODE_FILES=("code.py",), FORMAL_SCIENTIFIC_FILES=formal), mock.patch.object(runner, "_expected_checkpoint_paths", return_value=(set(), set())):
                runner._validate_scientific_completion()
                bad_execution = dict(execution); bad_execution["environment"] = {}; bad_execution.pop("payload_sha256_excluding_this_field")
                core.replace_json(root / "execution.json", core.payload_with_hash(bad_execution))
                with self.assertRaises(core.AnalysisError): runner._validate_scientific_completion()
                core.replace_json(root / "execution.json", execution)
                (root / "metrics.json").write_bytes(b'{"tampered":true}\n')
                with self.assertRaises(core.AnalysisError):
                    runner._validate_scientific_completion()

    def test_manifest_schema_version_and_bindings_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "checkpoints" / "oof").mkdir(parents=True); (root / "checkpoints" / "bootstrap").mkdir()
            for name in ("run_config.json", "scientific_completion.json", "audit.json"): (root / name).write_text("{}\n", encoding="utf-8")
            artifacts = [core.file_record(root / name, root) for name in sorted(("run_config.json", "scientific_completion.json", "audit.json"))]
            base = {
                "schema": "actual_incremental_sensitivity.manifest", "schema_version": 1,
                "state": "complete", "bundle_id": runner.BUNDLE_ID, "created_at_utc": runner.CREATED_AT_UTC,
                "authority_bundle_id": runner.AUTHORITY_ID, "authority_manifest_sha256": core.EXPECTED_AUTHORITY_MANIFEST_SHA256,
                "ledger_sha256": core.EXPECTED_LEDGER_SHA256, "pair_set_sha256": core.EXPECTED_PAIR_SET_SHA256,
                "config_sha256": core.sha256_file(root / "run_config.json"), "scientific_completion_sha256": core.sha256_file(root / "scientific_completion.json"),
                "audit_sha256": core.sha256_file(root / "audit.json"), "artifacts": artifacts,
                "artifact_inventory_sha256": core.sha256_bytes(core.canonical_json_bytes(artifacts)),
                "claims": {"external_api_calls": 0, "network_access": False, "gpu": False, "model_generation": False, "recompression": False, "prompt_output_text_reads": 0, "counterfactual_fields_used": False, "authority_modified": False, "word_modified": False},
            }
            manifest = core.payload_with_hash(base, "manifest_payload_sha256_excluding_this_field"); core.atomic_write_json(root / "manifest.json", manifest)
            original = runner.BUNDLE_DIR
            try:
                runner.BUNDLE_DIR = root; runner._validate_existing_manifest(root / "manifest.json")
                tampered = dict(base); tampered["schema_version"] = 2
                core.replace_json(root / "manifest.json", core.payload_with_hash(tampered, "manifest_payload_sha256_excluding_this_field"))
                with self.assertRaises(core.AnalysisError): runner._validate_existing_manifest(root / "manifest.json")
            finally: runner.BUNDLE_DIR = original

    def test_audit_nested_error_and_resource_forgery_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); authority = {"frozen": True}; core.atomic_write_json(root / "run_config.json", {"authority": authority}); (root / "scientific_completion.json").write_text("{}\n", encoding="utf-8")
            completion = {"artifact_inventory_sha256": "a" * 64}
            resources = {"rss_backend": "psutil", "rss_baseline_bytes": 10, "rss_peak_bytes": 12, "rss_incremental_peak_bytes": 2, "phase_rss_peaks_bytes": {"audit": 12}, "tracemalloc_current_bytes": 1, "tracemalloc_peak_bytes": 2, "rss_target_bytes": core.RSS_TARGET, "rss_hard_limit_bytes": core.RSS_HARD_LIMIT, "rss_limit_semantics": "sampled_process_rss_hard_limit", "rss_sampling_interval_milliseconds": 50, "synchronous_exit_rss_sample": True}
            models = {"ridge_outer_models_refit": 170, "hgb_outer_models_refit": 70, "hgb_import_available": True, "exact_model_inventory": True, "all_model_fit_metadata_recomputed": True, "maximum_prediction_absolute_error": 1e-13, "maximum_prediction_tolerance_ratio": 0.1, "maximum_model_fit_metadata_absolute_error": 1e-13, "maximum_model_fit_metadata_allowed_absolute_error": 1e-10, "prediction_atol": 1e-12, "prediction_rtol": 1e-10, "fit_metadata_tolerance": 1e-10}
            replay = {"replicates": 2000, "metrics": 552, "expected_metric_inventory": True, "draw_sequence_sha256": core.EXPECTED_DRAW_SHA256, "maximum_replay_absolute_error": 1e-13, "replay_absolute_tolerance": 2e-12, "maximum_percentile_absolute_error": 1e-13, "percentile_absolute_tolerance": 3e-12, "all_effective_matrix_elements_recomputed": True, "all_effective_summary_fields_recomputed": True}
            scan = {"passed": True, "forbidden_identifier_occurrences": 0, "structured_artifacts_scanned": ["metrics.json", "bootstrap_summary.json", "model_fits.jsonl", "oof_predictions.jsonl", "metrics.csv", *runner.TABLE_FILES, "appendix_subgroups.md", "appendix_model_coefficients.md", "REPORT_ZH.md"], "narrative_prose_excluded_by_design": True}
            base = {"schema": "actual_incremental_sensitivity.independent_audit", "schema_version": 1, "state": "pass", "bundle_id": runner.BUNDLE_ID, "config_sha256": core.sha256_file(root / "run_config.json"), "scientific_completion_sha256": core.sha256_file(root / "scientific_completion.json"), "scientific_artifact_inventory_sha256": completion["artifact_inventory_sha256"], "authority": authority, "coverage": {"pairs": core.EXPECTED_PAIRS, "items": core.EXPECTED_ITEMS, "clusters": core.EXPECTED_CLUSTERS}, "auditor_independence": {"auditor_imports_production": False, "production_forbidden_import_scan": {"analysis_core.py": "pass", "run_analysis.py": "pass"}}, "folds": {"independently_rebuilt": True, "full_row_permutation_invariant": True, "zero_cluster_leakage": True, "all_cluster_counts_and_inner_outer_cells_recomputed": True}, "raw_algebra": {"independently_rebuilt": True, "ratio_identity_exact_within_frozen_tolerance": True}, "models": models, "point_statistics": {"all_recomputed": True, "maximum_absolute_error": 1e-13, "tolerance": 2e-12}, "bootstrap": replay, "checkpoints": {"model_outer_blocks": 240, "aggregate_outer_blocks": 5, "bootstrap_blocks": 80, "exact_inventory": True, "all_hashes_keys_rows_dtypes_shapes_and_payloads_valid": True, "all_oof_checkpoint_values_match_ledger": True}, "projection_byte_comparison": {name: True for name in sorted(runner.PROJECTION_FILES)}, "structured_output_scan": scan, "resources": resources, "execution": {"elapsed_seconds": 1.0, "external_api_calls": 0, "network_access": False, "gpu": False, "model_generation": False, "text_regeneration": False, "recompression": False, "prompt_output_text_reads": 0, "counterfactual_fields_used": False, "authority_modified": False, "word_modified": False}}
            core.atomic_write_json(root / "audit.json", core.payload_with_hash(base))
            original = runner.BUNDLE_DIR
            try:
                runner.BUNDLE_DIR = root
                with mock.patch.object(runner, "_hgb_available", return_value=True): runner._validate_audit_receipt(completion)
                forged = json.loads(json.dumps(base)); forged["bootstrap"]["maximum_replay_absolute_error"] = 1.0
                core.replace_json(root / "audit.json", core.payload_with_hash(forged))
                with mock.patch.object(runner, "_hgb_available", return_value=True), self.assertRaises(core.AnalysisError): runner._validate_audit_receipt(completion)
                forged = json.loads(json.dumps(base)); forged["models"]["maximum_prediction_tolerance_ratio"] = 1.000001
                core.replace_json(root / "audit.json", core.payload_with_hash(forged))
                with mock.patch.object(runner, "_hgb_available", return_value=True), self.assertRaises(core.AnalysisError): runner._validate_audit_receipt(completion)
                forged = json.loads(json.dumps(base)); forged["resources"]["rss_incremental_peak_bytes"] = 999
                core.replace_json(root / "audit.json", core.payload_with_hash(forged))
                with mock.patch.object(runner, "_hgb_available", return_value=True), self.assertRaises(core.AnalysisError): runner._validate_audit_receipt(completion)
            finally: runner.BUNDLE_DIR = original

    def test_hgb_fit_errors_are_fatal(self) -> None:
        data = synthetic_dataset(10)
        outer = core.assign_grouped_folds(data.cluster_keys, data.cluster_rows, data.domains, seed=core.OUTER_SEED)
        x, _ = core.predictor_matrix(data, "L")
        with mock.patch("sklearn.ensemble.HistGradientBoostingRegressor.fit", side_effect=RuntimeError("synthetic fit failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic fit failure"):
                core.hgb_oof(x, data.values["phi_actual_llama"], data, outer, model_label="synthetic")

    def test_percentile_support_boundary(self) -> None:
        exactly = np.arange(2000, dtype=float); exactly[:20] = np.nan
        below = exactly.copy(); below[20] = np.nan
        self.assertIsNotNone(core.percentile_summary(exactly, 1.0)["ci_95_percentile"]["lower"])
        cell = core.percentile_summary(below, 1.0)
        self.assertIsNone(cell["ci_95_percentile"]["lower"])
        self.assertEqual(cell["undefined_reason"], "insufficient_bootstrap_support")

    def test_hgb_unavailable_is_only_import_skip(self) -> None:
        original_import = builtins.__import__
        def blocked(name: str, *args: object, **kwargs: object) -> object:
            if name == "sklearn.ensemble":
                raise ImportError("synthetic")
            return original_import(name, *args, **kwargs)
        dummy = synthetic_dataset(10)
        outer = {key: index % 5 for index, key in enumerate(dummy.cluster_keys)}
        with mock.patch("builtins.__import__", side_effect=blocked):
            prediction, records, status = core.hgb_oof(
                np.arange(dummy.n, dtype=float)[:, None], dummy.values["phi_actual_llama"],
                dummy, outer, model_label="synthetic",
            )
        self.assertIsNone(prediction); self.assertEqual(records, []); self.assertEqual(status, "skipped_unavailable")


def synthetic_rows(items: int, *, bad_levels: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in range(items):
        levels = list(core.LEVELS)
        if bad_levels and item == 0:
            levels[3], levels[4] = levels[4], levels[3]
        for level_index, level in enumerate(levels):
            output_bytes = float(100 + item * 3 + level_index)
            ratio = float((5 - level_index) / 6.0)
            row: dict[str, object] = {
                "generation_model": "model-a", "domain": "news", "id": f"{item:05d}",
                "level": level, "scoring_input_sha256": hashlib.sha256(f"score-{item}".encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(f"prompt-{item}-{level}".encode()).hexdigest(),
                "output_sha256": hashlib.sha256(f"output-{item}-{level}".encode()).hexdigest(),
                "source_cluster_domain": "news", "source_cluster_id": f"cluster-{item:05d}",
                "source_cluster_fingerprint": hashlib.sha256(f"source-{item}".encode()).hexdigest(),
                "blackbox_actual_ratio": ratio,
                "prompt_bytes": float(80 + item), "output_bytes": output_bytes,
                "prompt_words": float(20 + item % 5), "output_words": float(30 + level_index),
                "prompt_to_output_byte_ratio": float((80 + item) / output_bytes),
                "word_type_coverage": ratio * .8, "word_token_coverage": ratio * .85,
                "word_bigram_coverage": ratio * .6, "char3_coverage": ratio * .82,
                "char5_coverage": ratio * .78, "char8_coverage": ratio * .7,
                "rouge_l_recall": ratio * .9, "output_type_token_ratio": .5 + level_index * .01,
                "output_bigram_repeat_fraction": .1 + item * .0001,
                "output_self_bits_per_byte": 4.0 + level_index * .02,
                "phi_actual_llama": ratio * .7 + item * .001,
                "phi_actual_mixtral": ratio * .65 + item * .0012,
            }
            rows.append(row)
    return rows


def write_synthetic(path: Path, items: int, *, bad_levels: bool = False, crlf: bool = False) -> None:
    separator = b"\r\n" if crlf else b"\n"
    with path.open("wb") as handle:
        for row in synthetic_rows(items, bad_levels=bad_levels):
            handle.write(core.canonical_json_bytes(row) + separator)


def synthetic_dataset(items: int) -> core.Dataset:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.jsonl"
        write_synthetic(path, items)
        return core.load_ledger(path, expected_pairs=items * 5)


class DummyMonitor:
    def set_phase(self, phase: str) -> None:
        return None

    def check(self) -> None:
        return None


def direct_support_value_and_n(
    data: core.Dataset, key: str, multiplicity: np.ndarray,
) -> tuple[float, int]:
    parts = key.split("|")
    output_bytes = data.values["output_bytes"].reshape(-1, 5)
    item_cluster = data.cluster_index[::5]
    fields = {"R": "R_actual", "G": "G_raw_bits", "Llama": "phi_actual_llama", "Mixtral": "phi_actual_mixtral"}
    if parts[0] == "support":
        _, caliper_text, pair_text, label, statistic = parts
        high, low = pair_text.split("-"); i = core.LEVELS.index(high); j = core.LEVELS.index(low)
        mask = np.maximum(output_bytes[:, i], output_bytes[:, j]) / np.minimum(output_bytes[:, i], output_bytes[:, j]) <= float(caliper_text)
        difference = data.values[fields[label]].reshape(-1, 5)[:, i] - data.values[fields[label]].reshape(-1, 5)[:, j]
        weights = multiplicity[item_cluster] * mask.astype(np.int64); effective_n = int(weights.sum())
        if effective_n == 0:
            return math.nan, 0
        if statistic == "mean":
            value = float(np.dot(weights, difference) / effective_n)
        elif statistic == "median":
            value = float(np.median(np.repeat(difference, weights)))
        elif statistic == "expected_rate":
            value = float(np.dot(weights, difference > 0) / effective_n)
        elif statistic == "reverse_rate":
            value = float(np.dot(weights, difference < 0) / effective_n)
        else:
            value = float(np.dot(weights, difference == 0) / effective_n)
        return value, effective_n
    if parts[0] != "support_treatment":
        raise AssertionError(f"not a support key: {key}")
    _, caliper_text, label, scope, metric = parts
    candidate_parts: list[np.ndarray] = []; label_parts: list[np.ndarray] = []; cluster_parts: list[np.ndarray] = []
    matrix = data.values[fields[label]].reshape(-1, 5)
    for high, low in core.ADJACENT_LEVEL_PAIRS:
        i = core.LEVELS.index(high); j = core.LEVELS.index(low)
        mask = np.maximum(output_bytes[:, i], output_bytes[:, j]) / np.minimum(output_bytes[:, i], output_bytes[:, j]) <= float(caliper_text)
        retained = np.flatnonzero(mask)
        candidate_parts.append(matrix[retained][:, [i, j]])
        label_parts.append(np.tile(np.asarray([core.LEVEL_VALUE[high], core.LEVEL_VALUE[low]], dtype=np.float64), (len(retained), 1)))
        cluster_parts.append(item_cluster[retained])
    candidates = np.concatenate(candidate_parts); labels = np.concatenate(label_parts); clusters = np.concatenate(cluster_parts)
    weights = multiplicity[clusters]; effective_n = int(2 * weights.sum())
    repeated = np.repeat(np.arange(len(weights), dtype=np.int64), weights)
    if len(repeated) == 0:
        return math.nan, 0
    candidates = candidates[repeated]; labels = labels[repeated]
    if scope == "adjacent_pair_centered":
        candidates = candidates - candidates.mean(axis=1, keepdims=True)
        labels = labels - labels.mean(axis=1, keepdims=True)
    cell = independent_audit.pair(candidates.reshape(-1), labels.reshape(-1))
    return (math.nan if cell[metric] is None else float(cell[metric])), effective_n


class LedgerAndSyntheticTests(unittest.TestCase):
    def test_prepare_recovers_every_missing_suffix_boundary(self) -> None:
        data = synthetic_dataset(10)
        config = {"kind": "synthetic-config"}; folds = {"kind": "synthetic-folds"}; derived = {"kind": "synthetic-derived"}
        class PrepareMonitor:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def set_phase(self, phase): return None
            def receipt(self):
                return {"rss_backend": "psutil", "rss_baseline_bytes": 10, "rss_peak_bytes": 12, "rss_incremental_peak_bytes": 2, "phase_rss_peaks_bytes": {"prepare": 12}, "tracemalloc_current_bytes": 1, "tracemalloc_peak_bytes": 2, "rss_target_bytes": core.RSS_TARGET, "rss_hard_limit_bytes": core.RSS_HARD_LIMIT, "rss_limit_semantics": "sampled_process_rss_hard_limit", "rss_sampling_interval_milliseconds": 50, "synchronous_exit_rss_sample": True}
        payloads = (config, folds, derived)
        for prefix_length in range(4):
            with self.subTest(prefix_length=prefix_length), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root / "checkpoints" / "oof").mkdir(parents=True); (root / "checkpoints" / "bootstrap").mkdir()
                (root / "code.py").write_text("pass\n", encoding="utf-8"); (root / "RUNBOOK.md").write_text("test\n", encoding="utf-8")
                for name, payload in zip(runner.PREPARED_FILES[:prefix_length], payloads[:prefix_length], strict=True): core.atomic_write_json(root / name, payload)
                with mock.patch.multiple(runner, BUNDLE_DIR=root, FINAL_DIR_UNRESOLVED=root.parent / "absent-final", CODE_FILES=("code.py",)), mock.patch.object(runner, "_ensure_stage", return_value=False), mock.patch.object(core, "validate_authority", return_value={"authority": True}), mock.patch.object(core, "load_ledger", return_value=data), mock.patch.object(core, "build_fold_plan", return_value=folds), mock.patch.object(core, "frozen_strongest", return_value={"strongest": True}), mock.patch.object(core, "bootstrap_draw_sequence_sha256", return_value=core.EXPECTED_DRAW_SHA256), mock.patch.object(core, "make_run_config", return_value=config), mock.patch.object(runner, "_expected_derived_receipt", return_value=derived), mock.patch.object(core, "ResourceMonitor", PrepareMonitor), mock.patch("builtins.print"):
                    runner.prepare()
                self.assertEqual(core.strict_json_load(root / "run_config.json"), config)
                self.assertEqual(core.strict_json_load(root / "fold_assignments.json"), folds)
                self.assertEqual(core.strict_json_load(root / "derived_features_receipt.json"), derived)
                receipt = core.strict_json_load(root / "prepare_receipt.json"); core.verify_payload_hash(receipt)
                self.assertEqual(set(core.inspect_plain_tree(root, allowed_directories=runner.ALLOWED_BUNDLE_DIRECTORIES)), {"code.py", "RUNBOOK.md", *runner.PREPARED_FILES})

    def test_preparation_semantic_tampering_is_rejected(self) -> None:
        data = synthetic_dataset(10); folds = {"outer_assignment_sha256": "a" * 64, "payload_sha256_excluding_this_field": "b" * 64}; authority = {"synthetic": True}
        selections = {"strongest_single_heuristic": {"selected": "rouge_l_recall", "selected_metric_id": "direct|rouge_l_recall|macro_within_level|rho"}}
        resources = {"rss_backend": "psutil", "rss_baseline_bytes": 10, "rss_peak_bytes": 12, "rss_incremental_peak_bytes": 2, "phase_rss_peaks_bytes": {"prepare": 12}, "tracemalloc_current_bytes": 1, "tracemalloc_peak_bytes": 2, "rss_target_bytes": core.RSS_TARGET, "rss_hard_limit_bytes": core.RSS_HARD_LIMIT, "rss_limit_semantics": "sampled_process_rss_hard_limit", "rss_sampling_interval_milliseconds": 50, "synchronous_exit_rss_sample": True}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in runner.CODE_FILES: (root / name).write_text(f"# {name}\n", encoding="utf-8")
            config = core.make_run_config(bundle_id=runner.BUNDLE_ID, authority_receipt=authority, selections=selections, fold_plan=folds, code_files=[root / name for name in runner.CODE_FILES], created_at_utc=runner.CREATED_AT_UTC)
            core.atomic_write_json(root / "run_config.json", config); core.atomic_write_json(root / "fold_assignments.json", folds)
            derived = runner._expected_derived_receipt(data, core.sha256_file(root / "run_config.json")); core.atomic_write_json(root / "derived_features_receipt.json", derived)
            prepare_base = {"schema": "actual_incremental_sensitivity.prepare_receipt", "schema_version": 1, "state": "prepared", "bundle_id": runner.BUNDLE_ID, "artifacts": {name: core.sha256_file(root / name) for name in ("run_config.json", "fold_assignments.json", "derived_features_receipt.json")}, "authority_manifest_sha256": core.EXPECTED_AUTHORITY_MANIFEST_SHA256, "ledger_sha256": core.EXPECTED_LEDGER_SHA256, "pair_set_sha256": core.EXPECTED_PAIR_SET_SHA256, "bootstrap_draw_sequence_sha256": core.EXPECTED_DRAW_SHA256, "elapsed_seconds": 1.0, "resources": resources, "formal_statistics_started": False, "external_api_calls": 0, "network_access": False, "gpu": False, "model_generation": False, "recompression": False, "prompt_output_text_reads": 0}
            prepare = core.payload_with_hash(prepare_base)
            original = runner.BUNDLE_DIR
            try:
                runner.BUNDLE_DIR = root
                patches = (mock.patch.object(core, "validate_authority", return_value=authority), mock.patch.object(core, "load_ledger", return_value=data), mock.patch.object(core, "build_fold_plan", return_value=folds), mock.patch.object(core, "frozen_strongest", return_value=selections))
                with patches[0], patches[1], patches[2], patches[3]: runner._rebuild_and_validate_preparation(config, folds, derived, prepare)
                bad_config = json.loads(json.dumps(config)); bad_config["common_support"]["all_five_caliper"] = 9.0; bad_config.pop("config_payload_sha256_excluding_this_field"); bad_config["config_payload_sha256_excluding_this_field"] = core.sha256_bytes(core.canonical_json_bytes(bad_config))
                with mock.patch.object(core, "validate_authority", return_value=authority), mock.patch.object(core, "load_ledger", return_value=data), mock.patch.object(core, "build_fold_plan", return_value=folds), mock.patch.object(core, "frozen_strongest", return_value=selections), self.assertRaises(core.AnalysisError): runner._rebuild_and_validate_preparation(bad_config, folds, derived, prepare)
                bad_derived = json.loads(json.dumps(derived)); bad_derived["consensus"]["constructed_once_over_rows"] += 1; bad_derived.pop("payload_sha256_excluding_this_field"); bad_derived = core.payload_with_hash(bad_derived)
                with mock.patch.object(core, "validate_authority", return_value=authority), mock.patch.object(core, "load_ledger", return_value=data), mock.patch.object(core, "build_fold_plan", return_value=folds), mock.patch.object(core, "frozen_strongest", return_value=selections), self.assertRaises(core.AnalysisError): runner._rebuild_and_validate_preparation(config, folds, bad_derived, prepare)
                bad_prepare = json.loads(json.dumps(prepare_base)); bad_prepare["resources"]["rss_incremental_peak_bytes"] = 999; bad_prepare = core.payload_with_hash(bad_prepare)
                with mock.patch.object(core, "validate_authority", return_value=authority), mock.patch.object(core, "load_ledger", return_value=data), mock.patch.object(core, "build_fold_plan", return_value=folds), mock.patch.object(core, "frozen_strongest", return_value=selections), self.assertRaises(core.AnalysisError): runner._rebuild_and_validate_preparation(config, folds, derived, bad_prepare)
            finally: runner.BUNDLE_DIR = original

    def test_ledger_missing_or_misordered_level_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            write_synthetic(path, 2, bad_levels=True)
            with self.assertRaises(core.CoverageError):
                core.load_ledger(path, expected_pairs=10)

    def test_item_cannot_span_source_cluster_triples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad_cluster.jsonl"; rows = synthetic_rows(2)
            rows[3]["source_cluster_id"] = "different-cluster"
            with path.open("wb") as handle:
                for row in rows: handle.write(core.canonical_json_bytes(row, newline=True))
            with self.assertRaises(core.CoverageError):
                core.load_ledger(path, expected_pairs=10)

    def test_ledger_crlf_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            write_synthetic(path, 1, crlf=True)
            with self.assertRaises(core.CoverageError):
                core.load_ledger(path, expected_pairs=5)

    def test_raw_algebra_and_consensus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            write_synthetic(path, 3)
            data = core.load_ledger(path, expected_pairs=15)
            self.assertTrue(np.allclose(data.values["G_raw_bits"] / data.values["C_y_bits"], data.values["R_actual"]))
            expected = ((core.rankdata(data.values["phi_actual_llama"], method="average") - .5) / data.n +
                        (core.rankdata(data.values["phi_actual_mixtral"], method="average") - .5) / data.n) / 2
            np.testing.assert_allclose(data.values["consensus_midrank_percentile"], expected)
            receipt = core.raw_algebra_receipt(data)
            self.assertEqual(receipt["D_conditional_role"], "audit_only_not_baseline")

    def test_treatment_within_level_is_declared_undefined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"; write_synthetic(path, 4)
            data = core.load_ledger(path, expected_pairs=20)
            result = core.treatment_scopes(data.values["R_actual"], data)
            self.assertEqual(result["macro_within_level"]["undefined_reason"], "reference_constant_within_level")
            self.assertTrue(all(cell["undefined_reason"] == "reference_constant_within_level" for cell in result["per_level"].values()))

    def test_evaluator_ordering_ties_inversions_and_strictness(self) -> None:
        data = synthetic_dataset(3)
        data.values["phi_actual_llama"][:] = np.tile(np.asarray([5., 4., 3., 2., 1.]), 3)
        data.values["phi_actual_mixtral"][:] = np.concatenate((
            np.asarray([5., 4., 3., 2., 1.]),
            np.asarray([1., 2., 3., 4., 5.]),
            np.asarray([3., 3., 3., 3., 3.]),
        ))
        result = core.evaluator_ordering(data)
        for cell in result["all_ten"].values():
            self.assertEqual((cell["concordant"], cell["discordant"], cell["tied_either_evaluator"]), (1, 1, 1))
            self.assertAlmostEqual(cell["inversion_rate_all"], 1 / 3)
            self.assertAlmostEqual(cell["inversion_rate_non_tie"], 1 / 2)
        self.assertEqual(result["strict_monotonicity"], {"llama_items": 3, "mixtral_items": 1, "both_items": 1, "denominator_items": 3})

    def test_consensus_ties_and_global_z_are_constructed_once(self) -> None:
        data = synthetic_dataset(4)
        data.values["phi_actual_llama"][:] = np.tile(np.asarray([0., 0., 1., 1., 2.]), 4) + np.repeat(np.arange(4, dtype=float) * .1, 5)
        data.values["phi_actual_mixtral"][:] = np.arange(data.n, dtype=float)
        core.derive_features(data)
        expected_rank = ((core.rankdata(data.values["phi_actual_llama"], method="average") - .5) / data.n + (core.rankdata(data.values["phi_actual_mixtral"], method="average") - .5) / data.n) / 2
        np.testing.assert_array_equal(data.values["consensus_midrank_percentile"], expected_rank)
        self.assertAlmostEqual(float(data.values["phi_actual_llama_global_z"].mean()), 0.0, places=14)
        self.assertAlmostEqual(float(data.values["phi_actual_llama_global_z"].std(ddof=1)), 1.0, places=14)
        global_subset = data.values["evaluator_absolute_global_z_difference"][data.levels == "L1"].mean()
        llama_local = data.values["phi_actual_llama"][data.levels == "L1"]
        mixtral_local = data.values["phi_actual_mixtral"][data.levels == "L1"]
        local_difference = np.abs((llama_local-llama_local.mean())/llama_local.std(ddof=1) - (mixtral_local-mixtral_local.mean())/mixtral_local.std(ddof=1)).mean()
        self.assertNotAlmostEqual(float(global_subset), float(local_difference), places=8)

    def test_common_support_inclusive_boundary_and_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"; write_synthetic(path, 10)
            data = core.load_ledger(path, expected_pairs=50)
            # Make L1/L2 exactly 1.10 for every item; inclusive threshold must retain all.
            matrix = data.values["output_bytes"].reshape(-1, 5)
            matrix[:, 0] = 110.0; matrix[:, 1] = 100.0
            result = core.common_support(data)
            self.assertEqual(result["adjacent_byte_calipers"]["1.10"]["L1-L2"]["retained_model_item_pairs"], 10)
            self.assertTrue(result["nesting_asserted"])
            self.assertTrue(result["all_five_byte_1.25"]["low_support"])

    def test_common_support_bootstrap_uses_cluster_multiplicity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"; rows = synthetic_rows(3)
            for offset in range(5, 10):
                rows[offset]["source_cluster_id"] = rows[offset-5]["source_cluster_id"]
                rows[offset]["source_cluster_fingerprint"] = rows[offset-5]["source_cluster_fingerprint"]
            for row in rows: row["output_bytes"] = 100.0
            for item, difference in enumerate((.1, .3, .8)):
                base = item * 5; rows[base]["blackbox_actual_ratio"] = .1 + difference; rows[base+1]["blackbox_actual_ratio"] = .1
            with path.open("wb") as handle:
                for row in rows: handle.write(core.canonical_json_bytes(row, newline=True))
            data = core.load_ledger(path, expected_pairs=15)
            predictions = {f"{learner}|{target}|{predictor}": data.values[target].copy() for learner in ("ridge", "hgb") for target in core.WHITEBOX_TARGETS for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET)}
            residuals = {f"{spec}|{target}": data.values[target] - data.values[target].mean() for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS}
            selections = {"strongest_word_overlap": {"selected": "word_token_coverage"}, "strongest_char_overlap": {"selected": "char5_coverage"}}
            keys, calculate, effective = runner._bootstrap_specifications(data, predictions, residuals, selections, core.common_support(data))
            multiplicity = np.ones(len(data.cluster_keys), dtype=np.int32); shared_cluster = int(data.cluster_index[0]); multiplicity[shared_cluster] = 2
            indices = core.bootstrap_cluster_indices(data, np.repeat(np.arange(len(data.cluster_keys), dtype=np.int32), multiplicity))
            values = calculate(indices, multiplicity); counts = effective(indices, multiplicity)
            position = keys.index("support|1.10|L1-L2|R|mean")
            item_weights = multiplicity[data.cluster_index[::5]]
            differences = data.values["R_actual"].reshape(-1, 5)[:, 0] - data.values["R_actual"].reshape(-1, 5)[:, 1]
            self.assertAlmostEqual(values[position], float(np.average(differences, weights=item_weights)))
            self.assertEqual(counts[position], int(item_weights.sum()))

    def test_synthetic_nested_cv_and_train_only_scaler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"; write_synthetic(path, 25)
            data = core.load_ledger(path, expected_pairs=125)
            outer = core.assign_grouped_folds(data.cluster_keys, data.cluster_rows, data.domains, seed=core.OUTER_SEED)
            inners = []
            for fold in range(5):
                selected = [i for i, key in enumerate(data.cluster_keys) if outer[key] != fold]
                inners.append(core.assign_grouped_folds(
                    tuple(data.cluster_keys[i] for i in selected),
                    tuple(data.cluster_rows[i] for i in selected), data.domains,
                    seed=core.inner_seed(fold),
                ))
            x, names = core.predictor_matrix(data, "L")
            from sklearn.preprocessing import StandardScaler
            original_fit = StandardScaler.fit; fit_row_counts: list[int] = []
            def fit_spy(instance: object, values: np.ndarray, *args: object, **kwargs: object) -> object:
                fit_row_counts.append(len(values))
                return original_fit(instance, values, *args, **kwargs)
            with mock.patch.object(StandardScaler, "fit", new=fit_spy):
                prediction, fits = core.nested_ridge_oof(
                    x, data.values["phi_actual_llama"], data, outer, inners,
                    feature_names=names, model_label="synthetic",
                )
            self.assertEqual(len(fit_row_counts), 5 * (5 + 1))
            self.assertEqual(sum(count == 100 for count in fit_row_counts), 5)
            self.assertTrue(all(count < data.n for count in fit_row_counts))
            self.assertTrue(np.isfinite(prediction).all())
            self.assertEqual(len(fits), 5)
            cluster_outer = np.asarray([outer[key] for key in data.cluster_keys])
            row_outer = cluster_outer[data.cluster_index]
            from sklearn.linear_model import Ridge
            fold = 0; train = row_outer != fold; inner_cluster = np.full(len(data.cluster_keys), -1, dtype=np.int8)
            for cluster_id in np.flatnonzero(cluster_outer != fold): inner_cluster[cluster_id] = inners[fold][data.cluster_keys[int(cluster_id)]]
            inner_rows = inner_cluster[data.cluster_index]; naive_scores = []
            for alpha in core.RIDGE_ALPHAS:
                sse = 0.0; count = 0
                for inner_fold in range(5):
                    valid = train & (inner_rows == inner_fold); inner_train = train & (inner_rows != inner_fold)
                    scaler = StandardScaler().fit(x[inner_train]); model = Ridge(alpha=alpha, fit_intercept=True, solver="svd").fit(scaler.transform(x[inner_train]), data.values["phi_actual_llama"][inner_train])
                    predicted = model.predict(scaler.transform(x[valid])); sse += float(np.square(data.values["phi_actual_llama"][valid] - predicted).sum()); count += int(valid.sum())
                naive_scores.append({"alpha": alpha, "mse": sse / count, "holdout_rows": count})
            self.assertEqual(fits[0]["inner_scores"], naive_scores)
            self.assertEqual(fits[0]["selected_alpha"], core.select_ridge_alpha(naive_scores))
            for record in fits:
                train = row_outer != record["outer_fold"]
                np.testing.assert_allclose(record["scaler_mean"], x[train].mean(axis=0), atol=1e-14, rtol=0)
                self.assertEqual(record["train_cluster_count"] + record["test_cluster_count"], len(data.cluster_keys))

    def test_oof_stream_rejects_missing_and_duplicate_rows(self) -> None:
        data = synthetic_dataset(10)
        outer = core.assign_grouped_folds(data.cluster_keys, data.cluster_rows, data.domains, seed=core.OUTER_SEED)
        plan = {"outer_assignments": [[*key, value] for key, value in sorted(outer.items())], "outer_folds": []}
        predictions = {f"{learner}|{target}|{predictor}": data.values[target].copy() for learner in ("ridge", "hgb") for target in core.WHITEBOX_TARGETS for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET)}
        length_predictions = {f"length_ridge|{spec}|{target}": data.values[target].copy() for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS}
        residuals = {f"{spec}|{target}": data.values[target] - length_predictions[f"length_ridge|{spec}|{target}"] for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = runner.BUNDLE_DIR
            try:
                runner.BUNDLE_DIR = root; core.atomic_write_json(root / "fold_assignments.json", plan)
                runner._write_oof(data, predictions, length_predictions, residuals, "c" * 64)
                runner._stream_validate_oof(data, predictions, length_predictions, residuals, plan)
                ledger = root / "oof_predictions.jsonl"; lines = ledger.read_bytes().splitlines(keepends=True)
                ledger.write_bytes(b"".join(lines[:-1]))
                with self.assertRaises(core.AnalysisError):
                    runner._stream_validate_oof(data, predictions, length_predictions, residuals, plan)
                ledger.write_bytes(b"".join([*lines[:-1], lines[0]]))
                with self.assertRaises(core.AnalysisError):
                    runner._stream_validate_oof(data, predictions, length_predictions, residuals, plan)
            finally:
                runner.BUNDLE_DIR = original

    def test_resumable_ridge_uses_validated_outer_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"; write_synthetic(ledger, 25)
            data = core.load_ledger(ledger, expected_pairs=125)
            outer = core.assign_grouped_folds(data.cluster_keys, data.cluster_rows, data.domains, seed=core.OUTER_SEED)
            inners = []
            for fold in range(5):
                selected = [i for i, key in enumerate(data.cluster_keys) if outer[key] != fold]
                inners.append(core.assign_grouped_folds(
                    tuple(data.cluster_keys[i] for i in selected),
                    tuple(data.cluster_rows[i] for i in selected), data.domains,
                    seed=core.inner_seed(fold),
                ))
            x, names = core.predictor_matrix(data, "L")
            original_bundle = runner.BUNDLE_DIR
            try:
                runner.BUNDLE_DIR = Path(directory)
                first, first_fits, first_blocks = runner._fit_ridge_resumable(
                    x, data.values["phi_actual_llama"], data, outer, inners,
                    feature_names=names, model_label="ridge|phi_actual_llama|L",
                    config_sha="a" * 64, monitor=DummyMonitor(),
                )
                with mock.patch.object(core, "nested_ridge_oof", side_effect=AssertionError("must resume")):
                    second, second_fits, second_blocks = runner._fit_ridge_resumable(
                        x, data.values["phi_actual_llama"], data, outer, inners,
                        feature_names=names, model_label="ridge|phi_actual_llama|L",
                        config_sha="a" * 64, monitor=DummyMonitor(),
                    )
            finally:
                runner.BUNDLE_DIR = original_bundle
            np.testing.assert_array_equal(first, second)
            self.assertEqual(first_fits, second_fits)
            self.assertEqual(first_blocks, second_blocks)
            self.assertEqual(len(first_blocks), 5)

    def test_length_predictions_are_not_routed_as_whitebox_targets(self) -> None:
        data = synthetic_dataset(10)
        predictive = {
            f"{learner}|{target}|{predictor}": data.values[target].copy()
            for learner in ("ridge", "hgb")
            for target in core.WHITEBOX_TARGETS
            for predictor in (*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET)
        }
        length_predictions = {
            f"length_ridge|{spec}|{target}": data.values[target].copy()
            for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS
        }
        residuals = {
            f"{spec}|{target}": data.values[target] - length_predictions[f"length_ridge|{spec}|{target}"]
            for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS
        }
        points = runner._point_metrics(data, predictive, residuals)
        self.assertEqual(set(points["incremental_validity"]), set(predictive))
        self.assertFalse(any(key.startswith("length_ridge|") for key in points["incremental_validity"]))

    def test_actual_fit_write_read_point_lifecycle(self) -> None:
        data = synthetic_dataset(10)
        outer = core.assign_grouped_folds(data.cluster_keys, data.cluster_rows, data.domains, seed=core.OUTER_SEED)
        inners = []
        for fold in range(5):
            chosen = [i for i, key in enumerate(data.cluster_keys) if outer[key] != fold]
            inners.append(core.assign_grouped_folds(tuple(data.cluster_keys[i] for i in chosen), tuple(data.cluster_rows[i] for i in chosen), data.domains, seed=core.inner_seed(fold)))
        plan = {"outer_assignments": [[*key, value] for key, value in sorted(outer.items())], "outer_folds": [{"inner_assignments": [[*key, value] for key, value in sorted(inner.items())]} for inner in inners]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); production_root = runner.BUNDLE_DIR; audit_root = independent_audit.HERE
            try:
                runner.BUNDLE_DIR = root; independent_audit.HERE = root
                core.atomic_write_json(root / "fold_assignments.json", plan)
                predictions, length_predictions, residuals, fits, model_blocks = runner._fit_all(data, plan, "d" * 64, DummyMonitor(), "rouge_l_recall")
                aggregate_blocks = runner._write_oof(data, predictions, length_predictions, residuals, "d" * 64)
                runner._stream_validate_oof(data, predictions, length_predictions, residuals, plan)
                runner._write_model_fits(fits); reloaded_fits = runner._load_model_fits(hgb_available=True)
                audit_data = {"n": data.n, "pair_keys": data.pair_keys, "clusters": data.cluster_keys, "cluster_index": data.cluster_index}
                audited_predictions, audited_residuals = independent_audit.read_oof(audit_data, outer)
                points = runner._point_metrics(data, predictions, residuals)
            finally:
                runner.BUNDLE_DIR = production_root; independent_audit.HERE = audit_root
            self.assertEqual((len(predictions), len(length_predictions), len(residuals)), (28, 20, 20))
            self.assertEqual((len(fits), len(reloaded_fits), len(model_blocks), len(aggregate_blocks)), (240, 240, 240, 5))
            self.assertEqual(len(points["incremental_validity"]), 28)
            for key, values in {**predictions, **length_predictions}.items(): np.testing.assert_array_equal(audited_predictions[key], values)
            for key, values in residuals.items(): np.testing.assert_array_equal(audited_residuals[key], values)

    def test_synthetic_point_and_bootstrap_inventory_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"; write_synthetic(path, 25)
            data = core.load_ledger(path, expected_pairs=125)
            predictions: dict[str, np.ndarray] = {}
            for learner in ("ridge", "hgb"):
                for target in core.WHITEBOX_TARGETS:
                    for index, predictor in enumerate((*core.PREDICTOR_SETS, core.AUXILIARY_PREDICTOR_SET)):
                        predictions[f"{learner}|{target}|{predictor}"] = (
                            data.values[target] + (index + 1) * 1e-4 * np.sin(np.arange(data.n))
                        )
            residuals = {
                f"{spec}|{target}": data.values[target] - np.mean(data.values[target])
                for spec in core.LENGTH_SPECS for target in core.LENGTH_TARGETS
            }
            byte_patterns = np.asarray([
                [100., 105., 115., 130., 150.],
                [100., 112., 120., 150., 180.],
                [100., 125., 130., 160., 170.],
                [100., 135., 140., 145., 190.],
            ])
            data.values["output_bytes"][:] = np.vstack([
                byte_patterns[item % len(byte_patterns)] for item in range(data.item_count)
            ]).reshape(-1)
            points = runner._point_metrics(data, predictions, residuals)
            self.assertIn("adjacent_treatment_concordance", points["common_support"])
            selections = {
                "strongest_word_overlap": {"selected": "word_token_coverage"},
                "strongest_char_overlap": {"selected": "char5_coverage"},
            }
            keys, calculator, effective_calculator = runner._bootstrap_specifications(
                data, predictions, residuals, selections, points["common_support"]
            )
            identity_indices = np.concatenate(data.cluster_rows)
            identity_multiplicity = np.ones(len(data.cluster_keys), dtype=np.int32)
            result = calculator(identity_indices, identity_multiplicity)
            effective = effective_calculator(identity_indices, identity_multiplicity)
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(keys, independent_audit.expected_bootstrap_keys({"frozen_strongest": selections}, True))
            self.assertEqual(len(keys), 552)
            self.assertEqual(result.shape, (len(keys),))
            self.assertEqual(effective.shape, result.shape)
            self.assertTrue(np.all(effective > 0))
            self.assertTrue(any("|treatment|pooled|rho" in key for key in keys))
            support_keys = [key for key in keys if key.startswith("support|") or key.startswith("support_treatment|")]
            self.assertEqual(len(support_keys), 288)
            self.assertEqual(sum(key.startswith("support|") for key in support_keys), 240)
            self.assertEqual(sum(key.startswith("support_treatment|") for key in support_keys), 48)
            draw = np.arange(len(data.cluster_keys), dtype=np.int32); draw[-1] = 0
            nontrivial_multiplicity = np.bincount(draw, minlength=len(data.cluster_keys)).astype(np.int32)
            nontrivial_indices = core.bootstrap_cluster_indices(data, draw)
            for draw_name, draw_indices, multiplicity in (
                ("identity", identity_indices, identity_multiplicity),
                ("nontrivial", nontrivial_indices, nontrivial_multiplicity),
            ):
                draw_values = calculator(draw_indices, multiplicity)
                draw_effective = effective_calculator(draw_indices, multiplicity)
                for key in support_keys:
                    position = keys.index(key)
                    expected_value, expected_n = direct_support_value_and_n(data, key, multiplicity)
                    self.assertEqual(int(draw_effective[position]), expected_n, f"{draw_name}:{key}:effective_n")
                    if math.isnan(expected_value):
                        self.assertTrue(math.isnan(float(draw_values[position])), f"{draw_name}:{key}:value")
                    else:
                        self.assertAlmostEqual(float(draw_values[position]), expected_value, places=13, msg=f"{draw_name}:{key}:value")
            manual_key = "direct_delta|R_actual-minus-G_raw_bits|llama|item_centered|rho"
            manual = core.agreement_scopes(data.values["R_actual"], data.values["phi_actual_llama"], data, include_subgroups=False)["item_centered"]["rho"] - core.agreement_scopes(data.values["G_raw_bits"], data.values["phi_actual_llama"], data, include_subgroups=False)["item_centered"]["rho"]
            self.assertAlmostEqual(result[keys.index(manual_key)], manual, places=14)
            self.assertEqual(int(effective[keys.index(manual_key)]), data.n)
            bootstrap_metrics = {}
            for key, value in zip(keys, result, strict=True):
                finite = bool(np.isfinite(value))
                bootstrap_metrics[key] = {
                    "point": float(value) if finite else None,
                    "ci_95_percentile": {
                        "lower": float(value) if finite else None,
                        "upper": float(value) if finite else None,
                    },
                    "finite_resamples": 2000 if finite else 0,
                    "undefined_resamples": 0 if finite else 2000,
                    "undefined_reason": None if finite else "insufficient_bootstrap_support",
                    "point_effective_n": int(effective[keys.index(key)]),
                    "resample_effective_n_all_min": int(effective[keys.index(key)]),
                    "resample_effective_n_all_max": int(effective[keys.index(key)]),
                    "resample_effective_n_finite_min": int(effective[keys.index(key)]) if finite else None,
                    "resample_effective_n_finite_max": int(effective[keys.index(key)]) if finite else None,
                }
            bootstrap = {"metrics": bootstrap_metrics}
            classification = runner._classification(bootstrap)
            negative_bootstrap = {"metrics": {key: {**cell, "ci_95_percentile": {"lower": -2.0, "upper": -1.0}} for key, cell in bootstrap_metrics.items()}}
            self.assertEqual(runner._classification(negative_bootstrap)["R_vs_G"]["overall"], "stable_negative")
            points["outcome_neutral_classification"] = classification
            config = {"frozen_strongest": selections}
            deliberately_unsorted_fits = [
                {"model_label": "z-model", "learner": "Ridge", "outer_fold": 4, "selected_alpha": 1.0},
                {"model_label": "a-model", "learner": "Ridge", "outer_fold": 0, "selected_alpha": 10.0},
            ]
            with tempfile.TemporaryDirectory() as production_dir, tempfile.TemporaryDirectory() as audit_dir:
                original_bundle = runner.BUNDLE_DIR
                try:
                    runner.BUNDLE_DIR = Path(production_dir)
                    runner._write_projections(points, bootstrap, deliberately_unsorted_fits, selections, classification)
                finally:
                    runner.BUNDLE_DIR = original_bundle
                independent_audit.regenerate_projections(
                    points, bootstrap, config, deliberately_unsorted_fits, Path(audit_dir)
                )
                header = (Path(production_dir) / "metrics.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
                self.assertEqual(header[-5:-1], ["resample_effective_n_all_min", "resample_effective_n_all_max", "resample_effective_n_finite_min", "resample_effective_n_finite_max"])
                for name in runner.PROJECTION_FILES:
                    self.assertEqual(
                        (Path(production_dir) / name).read_bytes(),
                        (Path(audit_dir) / name).read_bytes(),
                        name,
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
