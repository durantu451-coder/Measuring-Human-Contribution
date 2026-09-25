# -*- coding: utf-8 -*-
"""Strictly assemble baseline-v2 timing artifacts into JSON and long CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_b.storage import atomic_replace_json, canonical_row_sha256, sha256_bytes
from experiment_baseline import whitebox_core

SCALING_MODELS = (
    ("llama3.2-3b", 3.21),
    ("llama3.1-8b", 8.03),
    ("qwen2.5-14b", 14.77),
    ("internlm2.5-20b", 19.86),
    ("qwen2.5-32b", 32.76),
    ("llama3-42b", 43.17),
)
PRODUCTION_EVALUATORS = ("llama", "mixtral")
EXPECTED_BINS = tuple(str(index) for index in range(6))


def _load(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing timing artifact: {path}")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"timing artifact is not an object: {path}")
    value["_input_artifact"] = {
        "path": str(path.resolve()),
        "sha256": sha256_bytes(raw),
        "size": len(raw),
    }
    return value


def _expected_code_sha256(filename: str) -> str:
    return hashlib.sha256((HERE / filename).read_bytes()).hexdigest()


def _validate_code_hash(artifact: dict, filename: str, *, label: str) -> None:
    expected = _expected_code_sha256(filename)
    if artifact.get("benchmark_code_sha256") != expected:
        raise RuntimeError(f"{label}: benchmark code hash mismatch")


def _validate_protocol(artifact: dict, *, label: str) -> None:
    protocol = artifact.get("protocol")
    if not isinstance(protocol, dict):
        raise RuntimeError(f"{label}: missing protocol object")
    expected = canonical_row_sha256(protocol)
    if artifact.get("protocol_sha256") != expected:
        raise RuntimeError(f"{label}: protocol hash mismatch")


def _validate_pair_rows(
    rows: object,
    bins_by_scope: dict,
    *,
    scopes: tuple[str, ...],
    label: str,
    expected_n: int,
) -> set[str]:
    if not isinstance(rows, list) or len(rows) != expected_n * len(EXPECTED_BINS):
        raise RuntimeError(f"{label}: unexpected row count")
    pair_hashes = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("pair_sha256"), str):
            raise RuntimeError(f"{label}.rows[{index}]: missing pair_sha256")
        pair_hashes.append(row["pair_sha256"])
    if len(set(pair_hashes)) != len(pair_hashes):
        raise RuntimeError(f"{label}: duplicate pair_sha256")

    for scope in scopes:
        values = bins_by_scope[scope]
        field = f"{scope}_s" if scope != "cpu_wall" else "wall_time_s"
        for bin_index in EXPECTED_BINS:
            selected = [row[field] for row in rows if str(row["bin"]) == bin_index]
            if len(selected) != expected_n:
                raise RuntimeError(f"{label}/{scope}/bin{bin_index}: row-count mismatch")
            stored = values[bin_index]
            checks = {
                "mean": st.fmean(selected),
                "median": st.median(selected),
                "std": st.pstdev(selected),
            }
            prefix = "" if scope != "cpu_wall" else "wall_"
            for name, calculated in checks.items():
                stored_field = f"{name}_{'s' if not prefix else prefix + 's'}"
                if not math.isclose(
                    float(stored[stored_field]), calculated, rel_tol=0.0, abs_tol=1e-15
                ):
                    raise RuntimeError(
                        f"{label}/{scope}/bin{bin_index}: {stored_field} mismatch"
                    )
    return set(pair_hashes)


def _validate_bins(
    values: dict,
    *,
    label: str,
    expected_n: int,
    fields: tuple[str, str, str] = ("mean_s", "median_s", "std_s"),
) -> None:
    if tuple(sorted(values, key=int)) != EXPECTED_BINS:
        raise RuntimeError(f"{label}: expected bins {EXPECTED_BINS}, got {sorted(values)}")
    for key in EXPECTED_BINS:
        row = values[key]
        if row.get("n") != expected_n:
            raise RuntimeError(f"{label}.bin{key}: n={row.get('n')} != {expected_n}")
        for field in fields:
            number = row.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise RuntimeError(f"{label}.bin{key}.{field} is not finite")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fields = (
        "family", "method", "scope", "role", "params_B", "bin",
        "ref_tokens", "n", "mean_ms", "median_ms", "std_ms",
        "sample_file_sha256", "protocol_sha256",
    )
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--expected-per-bin", type=int, default=100)
    args = parser.parse_args()

    artifacts: list[tuple[str, str, dict, float | None]] = []
    for tag, params_b in SCALING_MODELS:
        artifact = _load(args.timing_dir / f"whitebox_scaling_{tag}_v2.json")
        if artifact.get("schema") != "whitebox_scaling_timing_v2" or artifact.get("tag") != tag:
            raise RuntimeError(f"invalid scaling artifact for {tag}")
        _validate_protocol(artifact, label=f"whitebox_scaling/{tag}")
        _validate_code_hash(
            artifact, "bench_whitebox_time.py", label=f"whitebox_scaling/{tag}"
        )
        artifacts.append(("whitebox_scaling", tag, artifact, params_b))
    for evaluator in PRODUCTION_EVALUATORS:
        artifact = _load(args.timing_dir / f"whitebox_production_{evaluator}_v2.json")
        if artifact.get("schema") != "whitebox_production_timing_v2" or artifact.get("evaluator") != evaluator:
            raise RuntimeError(f"invalid production artifact for {evaluator}")
        _validate_protocol(artifact, label=f"whitebox_production/{evaluator}")
        _validate_code_hash(
            artifact,
            "bench_whitebox_production_time.py",
            label=f"whitebox_production/{evaluator}",
        )
        if artifact.get("evaluator_sha256") != whitebox_core.evaluator_sha256(evaluator):
            raise RuntimeError(f"evaluator fingerprint mismatch for {evaluator}")
        artifacts.append(("whitebox_production", evaluator, artifact, None))
    blackbox = _load(args.timing_dir / "blackbox_binned_v2.json")
    if blackbox.get("schema") != "blackbox_timing_v2":
        raise RuntimeError("invalid black-box timing artifact")
    _validate_protocol(blackbox, label="blackbox")
    _validate_code_hash(
        blackbox, "bench_blackbox_time_binned.py", label="blackbox"
    )
    blackbox_full_item = _load(args.timing_dir / "blackbox_full_item_v2.json")
    if blackbox_full_item.get("schema") != "blackbox_full_item_timing_v2":
        raise RuntimeError("invalid full-item black-box timing artifact")
    _validate_protocol(blackbox_full_item, label="blackbox_full_item")
    _validate_code_hash(
        blackbox_full_item,
        "bench_blackbox_time.py",
        label="blackbox_full_item",
    )

    sample_hashes = {artifact.get("sample_file_sha256") for _, _, artifact, _ in artifacts}
    sample_hashes.add(blackbox.get("sample_file_sha256"))
    if None in sample_hashes or len(sample_hashes) != 1:
        raise RuntimeError(f"timing artifacts use different sample hashes: {sample_hashes}")
    sample_hash = next(iter(sample_hashes))
    declared_hashes = {
        artifact.get("sample_declared_sha256") for _, _, artifact, _ in artifacts
    }
    declared_hashes.add(blackbox.get("sample_declared_sha256"))
    if None in declared_hashes or len(declared_hashes) != 1:
        raise RuntimeError(
            f"timing artifacts use different declared sample payload hashes: {declared_hashes}"
        )
    declared_sample_hash = next(iter(declared_hashes))

    rows: list[dict] = []
    structured = {
        "schema": "combined_timing_v2",
        "sample_file_sha256": sample_hash,
        "sample_payload_sha256": declared_sample_hash,
        "expected_per_bin": args.expected_per_bin,
        "whitebox_production": {},
        "whitebox_scaling": {},
        "blackbox": {},
        "blackbox_full_item": blackbox_full_item,
        "input_artifacts": {
            "blackbox_full_item": blackbox_full_item["_input_artifact"],
            "blackbox_pair": blackbox["_input_artifact"],
        },
    }
    pair_sets: list[tuple[str, set[str]]] = []
    for family, method, artifact, params_b in artifacts:
        scopes = artifact.get("per_bin")
        if not isinstance(scopes, dict):
            raise RuntimeError(f"{family}/{method}: missing per_bin scopes")
        for scope, bins in scopes.items():
            _validate_bins(
                bins,
                label=f"{family}/{method}/{scope}",
                expected_n=args.expected_per_bin,
            )
        pair_sets.append(
            (
                f"{family}/{method}",
                _validate_pair_rows(
                    artifact.get("rows"),
                    scopes,
                    scopes=tuple(scopes),
                    label=f"{family}/{method}",
                    expected_n=args.expected_per_bin,
                ),
            )
        )
        structured[family][method] = {
            "input_artifact": artifact["_input_artifact"],
            "protocol": artifact.get("protocol"),
            "protocol_sha256": artifact.get("protocol_sha256"),
            "evaluator_descriptor": artifact.get("evaluator_descriptor"),
            "evaluator_sha256": artifact.get("evaluator_sha256"),
            "n_params": artifact.get("n_params"),
            "load_s": artifact.get("load_s"),
            "cuda_visible_devices": artifact.get("cuda_visible_devices"),
            "participating_devices": artifact.get("participating_devices"),
            "hf_device_map": artifact.get("hf_device_map"),
            "environment": artifact.get("environment"),
            "scopes": scopes,
        }
        for scope, bins in scopes.items():
            for bin_index in EXPECTED_BINS:
                value = bins[bin_index]
                rows.append(
                    {
                        "family": family,
                        "method": method,
                        "scope": scope,
                        "role": "primary" if family == "whitebox_production" else "scaling_appendix",
                        "params_B": params_b,
                        "bin": int(bin_index),
                        "ref_tokens": value["mean_ref_tokens"],
                        "n": value["n"],
                        "mean_ms": value["mean_s"] * 1000,
                        "median_ms": value["median_s"] * 1000,
                        "std_ms": value["std_s"] * 1000,
                        "sample_file_sha256": sample_hash,
                        "protocol_sha256": artifact.get("protocol_sha256"),
                    }
                )

    variants = blackbox.get("variants")
    if not isinstance(variants, dict):
        raise RuntimeError("black-box artifact has no variants")
    for method, value in variants.items():
        bins = value.get("per_bin")
        _validate_bins(
            bins,
            label=f"blackbox/{method}",
            expected_n=args.expected_per_bin,
            fields=("mean_wall_s", "median_wall_s", "std_wall_s"),
        )
        pair_sets.append(
            (
                f"blackbox/{method}",
                _validate_pair_rows(
                    value.get("rows"),
                    {"cpu_wall": bins},
                    scopes=("cpu_wall",),
                    label=f"blackbox/{method}",
                    expected_n=args.expected_per_bin,
                ),
            )
        )
        structured["blackbox"][method] = {
            "input_artifact": blackbox["_input_artifact"],
            "role": value.get("role"),
            "compressors": value.get("compressors"),
            "protocol_sha256": blackbox.get("protocol_sha256"),
            "per_bin": bins,
        }
        for bin_index in EXPECTED_BINS:
            entry = bins[bin_index]
            rows.append(
                {
                    "family": "blackbox",
                    "method": method,
                    "scope": "cpu_wall",
                    "role": value.get("role"),
                    "params_B": 0,
                    "bin": int(bin_index),
                    "ref_tokens": entry["mean_ref_tokens"],
                    "n": entry["n"],
                    "mean_ms": entry["mean_wall_s"] * 1000,
                    "median_ms": entry["median_wall_s"] * 1000,
                    "std_ms": entry["std_wall_s"] * 1000,
                    "sample_file_sha256": sample_hash,
                    "protocol_sha256": blackbox.get("protocol_sha256"),
                }
            )

    reference_label, reference_pairs = pair_sets[0]
    for label, pair_set in pair_sets[1:]:
        if pair_set != reference_pairs:
            raise RuntimeError(
                f"pair set mismatch: {label} differs from {reference_label}"
            )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(args.out_json, structured)
    _write_csv(args.out_csv, rows)
    print(f"assembled {len(rows)} rows -> {args.out_json} and {args.out_csv}")


if __name__ == "__main__":
    main()
