#!/usr/bin/env python3
"""Independent full auditor for the actual incremental/sensitivity bundle.

Independence rule: this file must not import analysis_core.py or run_analysis.py.
All key normalization, folds, estimators, statistics, bootstrap draws, renderers,
and hashes below are separate audit implementations.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import math
import os
import platform
import stat
import sys
import tempfile
import threading
import time
import tracemalloc
import traceback
import unicodedata
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import numpy as np
from scipy.stats import kendalltau, rankdata

SCRIPT_UNRESOLVED=Path(os.path.abspath(__file__))
HERE_UNRESOLVED=SCRIPT_UNRESOLVED.parent
HERE = HERE_UNRESOLVED.resolve()
ROOT = HERE.parents[2]
PARENT_UNRESOLVED=HERE_UNRESOLVED.parent
PARENT = PARENT_UNRESOLVED.resolve()
MIGRATION = "phi_v2_20260822T180934_7d329704f7ab"
BUNDLE_ID = f"{MIGRATION}_actual_incremental_sensitivity_20260911T172319Z_v1"
AUTHORITY = PARENT / f"{MIGRATION}_actual_heuristic_20260911T035818Z_v1"
LEDGER = AUTHORITY / "actual_pair_features.jsonl"
LEVELS = ("L1", "L2", "L3", "L4", "L5")
LEVEL_VALUE = {"L1": 5.0, "L2": 4.0, "L3": 3.0, "L4": 2.0, "L5": 1.0}
ADJACENT = (("L1", "L2"), ("L2", "L3"), ("L3", "L4"), ("L4", "L5"))
ALL_PAIRS = tuple((LEVELS[i], LEVELS[j]) for i in range(5) for j in range(i + 1, 5))
HEURISTICS = (
    "prompt_bytes", "output_bytes", "prompt_words", "output_words",
    "prompt_to_output_byte_ratio", "word_type_coverage", "word_token_coverage",
    "word_bigram_coverage", "char3_coverage", "char5_coverage", "char8_coverage",
    "rouge_l_recall", "output_type_token_ratio", "output_bigram_repeat_fraction",
    "output_self_bits_per_byte",
)
LOG_H = {"prompt_bytes", "output_bytes", "prompt_words", "output_words", "prompt_to_output_byte_ratio"}
OVERLAP = ("rouge_l_recall", "word_type_coverage", "word_token_coverage", "word_bigram_coverage", "char3_coverage", "char5_coverage", "char8_coverage")
NUMERIC = ("blackbox_actual_ratio", *HEURISTICS, "phi_actual_llama", "phi_actual_mixtral")
IDENTITY = ("generation_model", "domain", "id", "level", "scoring_input_sha256", "prompt_sha256", "output_sha256", "source_cluster_domain", "source_cluster_id", "source_cluster_fingerprint")
FIELDS = frozenset((*IDENTITY, *NUMERIC))
DIRECT = ("R_actual", "G_raw_bits", "G_raw_bits_per_output_byte", "C_y_bits", *HEURISTICS)
TARGETS = ("phi_actual_llama", "phi_actual_mixtral")
SETS = ("L", "O", "H", "H+R", "R-only", "G-only")
AUX_SET = "AUX-strongest-single"
LENGTH_SPECS = ("byte_L_out", "byte_L_full", "word_L_out", "word_L_full")
LENGTH_TARGETS = ("R_actual", "G_raw_bits", "G_raw_bits_per_output_byte", "phi_actual_llama", "phi_actual_mixtral")
ALPHAS = tuple(float(10.0 ** exponent) for exponent in range(-6, 7))
PAIR_ALPHA = "pairwise_continuous_alpha_z"
JOINT_ALPHA = "joint_reference_continuous_alpha_z"
EXPECTED_LEDGER = "dbe012c59802518dea1ddb3a6b694f9446bf56fbc920578c3aae7df6ba9ec776"
EXPECTED_PAIR_SET = "02f9e08550b32ae6693676c3b71ab535c7a87b06a93f061587ddf10569a80037"
EXPECTED_MANIFEST = "30938906b58abc6dbaaddad72002d53915f20e50e6ea8d358e7d315002cf4e6a"
EXPECTED_DRAW = "f53da5c8fe317a3f3acbea472c5f35f6fdaba29c0d7284aefc18638e07566521"
MODEL_ITEMS = {"claude-opus-4-8": 1892, "claude-sonnet-5": 2320, "gemini-3.6-flash": 2240, "gpt-5.5": 2446, "gpt-5.6-sol": 2324}
DOMAIN_ITEMS = {"arxiv": 2937, "news": 2856, "patent": 2760, "poetry": 2669}
TABLE_FILES = (
    "table1_ratio_vs_raw_gain.md", "table2_incremental_validity.md",
    "table3_evaluator_sensitivity.md", "table4_length_residualized.md",
    "table5_length_common_support.md",
)
PROJECTION_FILES = (
    "metrics.csv", *TABLE_FILES, "appendix_subgroups.md",
    "appendix_model_coefficients.md", "REPORT_ZH.md",
)
PREPARED_FILES = ("run_config.json", "fold_assignments.json", "derived_features_receipt.json", "prepare_receipt.json")
FORMAL_SCIENTIFIC_FILES = (
    *PREPARED_FILES, "oof_predictions.jsonl", "model_fits.jsonl",
    "checkpoint_index.json", "bootstrap_summary.json", "metrics.json",
    *PROJECTION_FILES, "execution.json",
)
ALLOWED_DIRECTORIES = {"checkpoints", "checkpoints/oof", "checkpoints/bootstrap"}
RSS_HARD_LIMIT = 1610612736
RSS_TARGET = 1073741824
FORBIDDEN_IDENTIFIER_TOKENS = ("excess", "cf_baseline", "counterfactual_score", "1_minus_r", "d_over_c", "derived_score")


class AuditFailure(RuntimeError):
    pass


def lexists(path:Path)->bool:return os.path.lexists(os.fspath(path))


def reparse_or_link(path:Path)->bool:
    if not lexists(path):return False
    info=path.lstat();junction=getattr(path,"is_junction",None)
    return bool(path.is_symlink() or (callable(junction) and junction()) or int(getattr(info,"st_file_attributes",0))&0x400)


def component_snapshot(path:Path,*,include_leaf:bool=True)->list[tuple[Path,os.stat_result]]:
    unresolved=Path(os.path.abspath(os.fspath(path)));target=unresolved if include_leaf else unresolved.parent;parts=target.parts
    if not parts:raise AuditFailure("empty path")
    components=[Path(parts[0])]
    for part in parts[1:]:components.append(components[-1]/part)
    snapshot=[]
    for current in components:
        if not lexists(current):raise AuditFailure(f"missing path component {current}")
        info=current.lstat()
        if reparse_or_link(current):raise AuditFailure(f"reparse path component {current}")
        if current!=target and not stat.S_ISDIR(info.st_mode):raise AuditFailure(f"non-directory path component {current}")
        snapshot.append((current,info))
    return snapshot


def verify_component_snapshot(snapshot:Sequence[tuple[Path,os.stat_result]])->None:
    for path,expected in snapshot:
        if not lexists(path) or reparse_or_link(path) or not os.path.samestat(expected,path.lstat()):raise AuditFailure(f"path component identity changed {path}")


def plain_components(path:Path,*,include_leaf:bool=True)->Path:
    unresolved=Path(os.path.abspath(os.fspath(path)));component_snapshot(unresolved,include_leaf=include_leaf);return unresolved


@contextmanager
def open_plain(path:Path):
    unresolved=Path(os.path.abspath(os.fspath(path)));components=component_snapshot(unresolved);before=unresolved.lstat()
    if reparse_or_link(unresolved) or not stat.S_ISREG(before.st_mode):raise AuditFailure(f"nonplain file {unresolved}")
    flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)
    try:descriptor=os.open(unresolved,flags)
    except OSError as exc:raise AuditFailure(f"plain open failed {unresolved}: {exc}") from exc
    handle=os.fdopen(descriptor,"rb",closefd=True)
    try:
        opened=os.fstat(handle.fileno());verify_component_snapshot(components);after_open=unresolved.lstat()
        if not stat.S_ISREG(opened.st_mode) or reparse_or_link(unresolved) or not os.path.samestat(before,opened) or not os.path.samestat(after_open,opened):raise AuditFailure(f"file identity changed on open {unresolved}")
        yield handle
        after_read=os.fstat(handle.fileno());verify_component_snapshot(components);after_path=unresolved.lstat()
        if not os.path.samestat(opened,after_read) or not os.path.samestat(after_path,after_read) or after_read.st_size!=opened.st_size or after_read.st_mtime_ns!=opened.st_mtime_ns or reparse_or_link(unresolved):raise AuditFailure(f"file identity changed on read {unresolved}")
    finally:handle.close()


def read_plain_bytes(path:Path)->bytes:
    with open_plain(path) as handle:return handle.read()


def validate_root_path()->None:
    parent=plain_components(PARENT_UNRESOLVED);here=plain_components(HERE_UNRESOLVED)
    if not stat.S_ISDIR(parent.lstat().st_mode) or not stat.S_ISDIR(here.lstat().st_mode):raise AuditFailure("audit root path is not plain")
    if here.resolve(strict=True)!=HERE or HERE.parent!=parent.resolve(strict=True):raise AuditFailure("audit path containment differs")
    script=plain_components(SCRIPT_UNRESOLVED)
    if not stat.S_ISREG(script.lstat().st_mode):raise AuditFailure("audit script non-file")
    final=PARENT_UNRESOLVED/BUNDLE_ID;plain_components(final,include_leaf=False)
    if lexists(final) and (reparse_or_link(final) or not stat.S_ISDIR(final.lstat().st_mode)):raise AuditFailure("final destination link/reparse/non-directory")


def reject_constant(value: str) -> None:
    raise ValueError(value)


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out: raise ValueError(f"duplicate key {key}")
        out[key] = value
    return out


def loads(raw: bytes | str, label: str = "json") -> Any:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return json.loads(text, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    except Exception as exc:
        raise AuditFailure(f"{label}: strict JSON failure: {exc}") from exc


def load_record(path:Path)->tuple[Any,str,int]:
    digest=hashlib.sha256();chunks=[];size=0
    with open_plain(path) as handle:
        while True:
            block=handle.read(8*1024*1024)
            if not block:break
            digest.update(block);chunks.append(block);size+=len(block)
    return loads(b"".join(chunks),str(path)),digest.hexdigest(),size


def load(path: Path) -> Any:return load_record(path)[0]


def clean(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)): return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool): return int(value)
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if not math.isfinite(result): raise AuditFailure("non-finite serialization")
        return result
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value): raise AuditFailure("non-string key")
        return {key: clean(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)): return [clean(child) for child in value]
    raise AuditFailure(f"unsupported JSON type {type(value)}")


def canonical(value: Any, newline: bool = False) -> bytes:
    result = json.dumps(clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return result + (b"\n" if newline else b"")


def sha_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()


def fingerprint(path:Path)->tuple[str,int]:
    digest=hashlib.sha256()
    with open_plain(path) as handle:
        while block:=handle.read(8*1024*1024):digest.update(block)
        size=os.fstat(handle.fileno()).st_size
    return digest.hexdigest(),int(size)


def sha_file(path: Path) -> str:return fingerprint(path)[0]


def write_immutable(path:Path,payload:bytes)->None:
    path.parent.mkdir(parents=True,exist_ok=True);parents=component_snapshot(path,include_leaf=False)
    if lexists(path):
        digest,size=fingerprint(path)
        if (digest,size)==(sha_bytes(payload),len(payload)):return
        raise AuditFailure(f"refusing to overwrite immutable file {path}")
    descriptor,name=tempfile.mkstemp(prefix=f".{path.name}.{os.getpid()}.",suffix=".tmp",dir=path.parent);temporary=Path(name)
    try:
        with os.fdopen(descriptor,"wb",closefd=True) as handle:handle.write(payload);handle.flush();os.fsync(handle.fileno())
        verify_component_snapshot(parents)
        try:os.link(temporary,path,follow_symlinks=False)
        except FileExistsError:
            digest,size=fingerprint(path)
            if (digest,size)!=(sha_bytes(payload),len(payload)):raise AuditFailure(f"immutable destination race {path}")
    finally:
        if lexists(temporary):
            if reparse_or_link(temporary):raise AuditFailure(f"temporary path replaced {temporary}")
            temporary.unlink()


def self_hash(value: Mapping[str, Any], field: str = "payload_sha256_excluding_this_field") -> None:
    copy = dict(value); stored = copy.pop(field, None)
    if stored != sha_bytes(canonical(copy)): raise AuditFailure(f"self hash differs: {field}")


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AuditFailure(f"non-finite {label}")
    return float(value)


def validate_resources(resources:Any,label:str)->dict[str,Any]:
    fields={"rss_backend","rss_baseline_bytes","rss_peak_bytes","rss_incremental_peak_bytes","phase_rss_peaks_bytes","tracemalloc_current_bytes","tracemalloc_peak_bytes","rss_target_bytes","rss_hard_limit_bytes","rss_limit_semantics","rss_sampling_interval_milliseconds","synchronous_exit_rss_sample"}
    if not isinstance(resources,dict) or set(resources)!=fields or resources["rss_backend"] not in {"psutil","win32_ctypes"}:raise AuditFailure(f"{label} resource schema/backend")
    numeric=fields-{"rss_backend","phase_rss_peaks_bytes","rss_limit_semantics","synchronous_exit_rss_sample"}
    if any(isinstance(resources[key],bool) or not isinstance(resources[key],int) or resources[key]<0 for key in numeric):raise AuditFailure(f"{label} resource numeric values")
    phases=resources["phase_rss_peaks_bytes"]
    if not isinstance(phases,dict) or not phases or any(not isinstance(key,str) or not key or isinstance(value,bool) or not isinstance(value,int) or value<0 for key,value in phases.items()):raise AuditFailure(f"{label} phase RSS evidence")
    if resources["rss_target_bytes"]!=RSS_TARGET or resources["rss_hard_limit_bytes"]!=RSS_HARD_LIMIT or resources["rss_limit_semantics"]!="sampled_process_rss_hard_limit" or resources["rss_sampling_interval_milliseconds"]!=50 or resources["synchronous_exit_rss_sample"] is not True or resources["rss_peak_bytes"]<resources["rss_baseline_bytes"] or resources["rss_incremental_peak_bytes"]!=max(0,resources["rss_peak_bytes"]-resources["rss_baseline_bytes"]) or resources["rss_peak_bytes"]>RSS_HARD_LIMIT or max(phases.values())>resources["rss_peak_bytes"] or resources["tracemalloc_current_bytes"]>resources["tracemalloc_peak_bytes"]:raise AuditFailure(f"{label} resource policy/evidence")
    return resources


def expected_environment()->dict[str,Any]:
    import scipy
    answer={"python":platform.python_version(),"platform":platform.platform(),"numpy":np.__version__,"scipy":scipy.__version__}
    try:
        import sklearn
        answer["scikit_learn"]=sklearn.__version__
    except ImportError:answer["scikit_learn"]=None
    try:
        import pandas
        answer["pandas"]=pandas.__version__
    except ImportError:answer["pandas"]=None
    return answer


def norm_key(model: Any, domain: Any, item: Any) -> tuple[str, str, str]:
    if not all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in (model, domain, item)):
        raise AuditFailure("invalid key type")
    answer = (unicodedata.normalize("NFC", str(model).strip()), unicodedata.normalize("NFC", str(domain).strip()).lower(), unicodedata.normalize("NFC", str(item).strip()))
    if not all(answer): raise AuditFailure("empty key")
    return answer


def norm_cluster(domain: Any, item: Any, fingerprint: Any) -> tuple[str, str, str]:
    answer = (unicodedata.normalize("NFC", str(domain).strip()).lower(), unicodedata.normalize("NFC", str(item).strip()), unicodedata.normalize("NFC", str(fingerprint).strip()).lower())
    if not all(answer): raise AuditFailure("empty cluster key")
    return answer


def plain_files(root: Path, allowed_directories: set[str] | None = None) -> list[str]:
    root=plain_components(root)
    if not stat.S_ISDIR(root.lstat().st_mode):raise AuditFailure(f"inventory root non-directory {root}")
    allowed = set() if allowed_directories is None else set(allowed_directories)
    result: list[str] = []; seen_directories: set[str] = set()
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in dirs:
            child = current_path / name; info = child.lstat(); relative = child.relative_to(root).as_posix()
            if child.is_symlink() or int(getattr(info, "st_file_attributes", 0)) & 0x400 or not stat.S_ISDIR(info.st_mode): raise AuditFailure(f"reparse directory {child}")
            if name.startswith(".") or name == "__pycache__" or relative not in allowed: raise AuditFailure(f"undeclared directory {child}")
            seen_directories.add(relative)
        for name in files:
            child = current_path / name; info = child.lstat()
            if child.is_symlink() or int(getattr(info, "st_file_attributes", 0)) & 0x400 or not stat.S_ISREG(info.st_mode): raise AuditFailure(f"nonplain file {child}")
            if name.startswith(".") or name.endswith((".tmp", ".partial", ".lock")): raise AuditFailure(f"temporary file {child}")
            result.append(child.relative_to(root).as_posix())
    if seen_directories != allowed: raise AuditFailure(f"directory inventory differs: {seen_directories ^ allowed}")
    return sorted(result)


def verify_authority() -> dict[str, Any]:
    authority_path=plain_components(AUTHORITY);root_path=plain_components(ROOT)
    if not stat.S_ISDIR(authority_path.lstat().st_mode) or not stat.S_ISDIR(root_path.lstat().st_mode):raise AuditFailure("authority/root directory is not plain")
    expected = {
        "manifest.json": EXPECTED_MANIFEST,
        "actual_pair_features.jsonl": EXPECTED_LEDGER,
        "metrics.json": "894ef996c466a86920e1cf69af67d3bd53dec2a9e6defc411a9e6e09a9cf295e",
        "audit.json": "06d525867220f5ff5f57388e96b019434352a0da534c12a459af4d36e85a4e0d",
        "scientific_completion.json": "c9a887fc8e794bc9686877753bfa954baa78eda2ca93682c38b9a391b2e7a8d6",
    }
    for name, digest in expected.items():
        if sha_file(AUTHORITY / name) != digest: raise AuditFailure(f"authority drift {name}")
    manifest,manifest_sha,_ = load_record(AUTHORITY / "manifest.json")
    if manifest_sha!=EXPECTED_MANIFEST:raise AuditFailure("authority manifest changed between validation and parse")
    copy = dict(manifest); stored = copy.pop("manifest_payload_sha256_excluding_this_field", None)
    if stored != sha_bytes(canonical(copy)): raise AuditFailure("authority manifest self hash")
    declared = {entry["path"]: entry for entry in manifest["artifacts"]}
    if plain_files(AUTHORITY) != sorted([*declared, "manifest.json"]): raise AuditFailure("authority inventory")
    for name, entry in declared.items():
        path = AUTHORITY / name;digest,size=fingerprint(path)
        if size != entry["size"] or digest != entry["sha256"]: raise AuditFailure(f"authority file {name}")
    old_config,old_config_sha,old_config_size = load_record(AUTHORITY / "run_config.json")
    declared_config=declared.get("run_config.json")
    if not declared_config or (old_config_sha,old_config_size)!=(declared_config["sha256"],declared_config["size"]):raise AuditFailure("authority run_config parse binding")
    if len(old_config["input_artifacts"]) != 10: raise AuditFailure("protected input count")
    checked = {}
    for label, entry in old_config["input_artifacts"].items():
        relative=entry.get("path")
        if not isinstance(relative,str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:raise AuditFailure(f"protected input path {label}")
        path = ROOT / relative;digest,size=fingerprint(path)
        if size != entry["size"] or digest != entry["sha256"]: raise AuditFailure(f"protected input {label}")
        checked[label] = {"path": relative, "sha256": entry["sha256"], "size": entry["size"]}
    coverage={"actual_pairs":56110,"model_items":11222,"source_clusters":2551,"pairs_per_item":5,"pair_set_sha256":EXPECTED_PAIR_SET}
    if any(manifest["coverage"].get(key)!=value for key,value in coverage.items()) or manifest["coverage"].get("domain_items")!=DOMAIN_ITEMS or manifest["coverage"].get("generation_model_items")!=MODEL_ITEMS:raise AuditFailure("authority coverage")
    return {"authority_path":"${HC_DATA_ROOT}/experiment_baseline\\phi_v2_derived_results\\phi_v2_20260822T180934_7d329704f7ab_actual_heuristic_20260911T035818Z_v1","authority_bundle_id":manifest.get("bundle_id"),"known_hashes":expected,"internal_inventory_sha256":manifest["artifact_inventory_sha256"],"protected_inputs":dict(sorted(checked.items())),"coverage":coverage,"external_non_input_warning":"relocated_same_sha_not_consumed","word_path_followed":False}


def read_ledger() -> dict[str, Any]:
    ledger_digest=hashlib.sha256()
    models=[]; domains=[]; ids=[]; levels=[]; clusters=[]; pair_keys=[]; payload=[]
    values={name:[] for name in NUMERIC}; seen=set(); previous=None
    with open_plain(LEDGER) as handle:
        for line_number, raw in enumerate(handle, 1):
            ledger_digest.update(raw)
            if raw[-1:] != b"\n" or raw.endswith(b"\r\n"): raise AuditFailure("ledger newline")
            row=loads(raw, f"ledger {line_number}")
            if not isinstance(row,dict) or frozenset(row)!=FIELDS: raise AuditFailure("ledger schema")
            key3=norm_key(row["generation_model"],row["domain"],row["id"]); level=row["level"]
            if level not in LEVELS: raise AuditFailure("level")
            key=(*key3,level); sort=(*key3,LEVELS.index(level))
            if key in seen or (previous is not None and sort<=previous): raise AuditFailure("duplicate/order")
            seen.add(key); previous=sort
            for field in ("scoring_input_sha256","prompt_sha256","output_sha256"):
                if not isinstance(row[field],str) or len(row[field])!=64: raise AuditFailure("hash field")
            cluster=norm_cluster(row["source_cluster_domain"],row["source_cluster_id"],row["source_cluster_fingerprint"])
            models.append(key3[0]); domains.append(key3[1]); ids.append(key3[2]); levels.append(level); clusters.append(cluster); pair_keys.append(key)
            payload.append([*key3,level,row["scoring_input_sha256"]])
            for field in NUMERIC: values[field].append(finite(row[field],field))
    if ledger_digest.hexdigest()!=EXPECTED_LEDGER:raise AuditFailure("ledger hash differs from bytes parsed")
    if len(pair_keys)!=56110 or sha_bytes(canonical(payload))!=EXPECTED_PAIR_SET: raise AuditFailure("pair coverage/hash")
    for start in range(0,len(pair_keys),5):
        if len({key[:3] for key in pair_keys[start:start+5]})!=1 or tuple(key[3] for key in pair_keys[start:start+5])!=LEVELS: raise AuditFailure("item levels")
        if len(set(clusters[start:start+5]))!=1:raise AuditFailure("item source-cluster triple")
    cluster_keys=tuple(sorted(set(clusters)))
    if len(cluster_keys)!=2551: raise AuditFailure("cluster count")
    lookup={key:i for i,key in enumerate(cluster_keys)}
    cluster_index=np.asarray([lookup[key] for key in clusters],dtype=np.int32)
    cluster_rows=tuple(np.flatnonzero(cluster_index==i).astype(np.int32) for i in range(len(cluster_keys)))
    data={name:np.asarray(vector,dtype=np.float64) for name,vector in values.items()}
    r=data["blackbox_actual_ratio"]; c=data["output_self_bits_per_byte"]*data["output_bytes"]; g=r*c; d=c-g
    eps=np.finfo(np.float64).eps; tol=64*eps*np.maximum.reduce((np.ones(len(r)),np.abs(c),np.abs(g)))
    if np.any(data["output_bytes"]<=0) or np.any(c<=0) or np.any((r<0)|(r>1)) or np.any(g<0) or np.any(d < -tol): raise AuditFailure("algebra bounds")
    if not np.all(np.isclose(g/c,r,rtol=64*eps,atol=64*eps)): raise AuditFailure("algebra identity")
    data.update(R_actual=r.copy(),C_y_bits=c,G_raw_bits=g,G_raw_bits_per_output_byte=g/data["output_bytes"],D_conditional_bits_audit_only=d)
    treatment=np.tile(np.asarray([5,4,3,2,1],dtype=np.float64),11222); data["treatment_ordinal"]=treatment
    lr=rankdata(data["phi_actual_llama"],method="average"); mr=rankdata(data["phi_actual_mixtral"],method="average")
    data["consensus_midrank_percentile"]=((lr-.5)/56110+(mr-.5)/56110)/2
    lz=(data["phi_actual_llama"]-data["phi_actual_llama"].mean())/data["phi_actual_llama"].std(ddof=1)
    mz=(data["phi_actual_mixtral"]-data["phi_actual_mixtral"].mean())/data["phi_actual_mixtral"].std(ddof=1)
    data["phi_actual_llama_global_z"]=lz; data["phi_actual_mixtral_global_z"]=mz; data["consensus_global_z"]=(lz+mz)/2; data["evaluator_absolute_global_z_difference"]=np.abs(lz-mz)
    model_array=np.asarray(models,dtype="U32"); domain_array=np.asarray(domains,dtype="U16"); level_array=np.asarray(levels,dtype="U2")
    if dict(sorted(Counter(model_array[::5]).items())) != MODEL_ITEMS or dict(sorted(Counter(domain_array[::5]).items())) != DOMAIN_ITEMS: raise AuditFailure("item cells")
    for key,rows in zip(cluster_keys,cluster_rows,strict=True):
        if set(domain_array[rows])!={key[0]}: raise AuditFailure("cluster domain")
        item_ids=rows//5
        if len(rows)%5 or any(int(np.sum(item_ids==item))!=5 for item in np.unique(item_ids)):raise AuditFailure("cluster incomplete item block")
    return {"models":model_array,"domains":domain_array,"ids":np.asarray(ids,dtype=object),"levels":level_array,"clusters":cluster_keys,"cluster_index":cluster_index,"cluster_rows":cluster_rows,"values":data,"pair_keys":tuple(pair_keys),"n":56110,"items":11222}


def token(seed:int,purpose:str,key:tuple[str,str,str],fold:int|None=None)->str:
    parts=[str(seed),purpose,*key]
    if fold is not None: parts.append(str(fold))
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def assign(keys:Sequence[tuple[str,str,str]],rows:Sequence[np.ndarray],domains:np.ndarray,seed:int)->dict[tuple[str,str,str],int]:
    records=[]
    for key,index in zip(keys,rows,strict=True):
        if set(domains[index])!={key[0]}: raise AuditFailure("fold domain")
        records.append((key,key[0],len(index),token(seed,"sort",key)))
    records.sort(key=lambda x:(-x[2],x[3],x[0])); dr=defaultdict(lambda:[0]*5); total=[0]*5; counts=[0]*5; out={}
    for key,domain,n,_ in records:
        selected=min(range(5),key=lambda fold:(dr[domain][fold],total[fold],counts[fold],token(seed,"fold-priority",key,fold),fold))
        out[key]=selected;dr[domain][selected]+=n;total[selected]+=n;counts[selected]+=1
    return out


def fold_cell(data:Mapping[str,Any],rows:np.ndarray,fold:int)->dict[str,Any]:
    row_ids=np.asarray(rows,dtype=np.int64)
    return {"fold":int(fold),"rows":int(len(row_ids)),"clusters":int(len(np.unique(data["cluster_index"][row_ids]))),"items":int(len(np.unique(row_ids//5))),"domain_rows":dict(sorted(Counter(data["domains"][row_ids]).items())),"model_rows":dict(sorted(Counter(data["models"][row_ids]).items()))}


def independent_folds(data:Mapping[str,Any])->tuple[dict[tuple[str,str,str],int],list[dict[tuple[str,str,str],int]],dict[str,Any]]:
    outer=assign(data["clusters"],data["cluster_rows"],data["domains"],20260824)
    if outer!=assign(tuple(reversed(data["clusters"])),tuple(reversed(data["cluster_rows"])),data["domains"],20260824): raise AuditFailure("outer cluster-order invariance")
    permutation=np.random.default_rng(20260824).permutation(data["n"]);permuted_domains=data["domains"][permutation];permuted_ci=data["cluster_index"][permutation];permuted_rows=tuple(np.flatnonzero(permuted_ci==index).astype(np.int32) for index in range(len(data["clusters"])))
    if outer!=assign(data["clusters"],permuted_rows,permuted_domains,20260824):raise AuditFailure("full-row permutation invariance")
    inners=[];outer_details=[]
    for fold in range(5):
        indices=[i for i,key in enumerate(data["clusters"]) if outer[key]!=fold]
        keys=tuple(data["clusters"][i] for i in indices);rows=tuple(data["cluster_rows"][i] for i in indices)
        seed=int.from_bytes(hashlib.sha256(f"20260825\0outer={fold}".encode("ascii")).digest()[:8],"big")
        inner=assign(keys,rows,data["domains"],seed)
        if inner!=assign(tuple(reversed(keys)),tuple(reversed(rows)),data["domains"],seed): raise AuditFailure("inner order invariance")
        cells=[]
        for inner_fold in range(5):
            validation_ids=[i for i,key in enumerate(data["clusters"]) if key in inner and inner[key]==inner_fold]
            training_ids=[i for i,key in enumerate(data["clusters"]) if key in inner and inner[key]!=inner_fold]
            validation=np.concatenate([data["cluster_rows"][i] for i in validation_ids]);training=np.concatenate([data["cluster_rows"][i] for i in training_ids])
            if set(data["domains"][validation])!=set(DOMAIN_ITEMS) or set(data["models"][validation])!=set(MODEL_ITEMS):raise AuditFailure("inner empty domain/model cell")
            vc=fold_cell(data,validation,inner_fold);vc["role"]="validation";tc=fold_cell(data,training,inner_fold);tc["role"]="training";cells.append({"inner_fold":inner_fold,"validation":vc,"training":tc})
        inners.append(inner);test_keys={key for key,value in outer.items() if value==fold};train_keys=set(outer)-test_keys;payload=[[*key,int(inner[key])] for key in sorted(inner)]
        outer_details.append({"outer_fold":fold,"inner_seed_uint64":seed,"train_cluster_count":len(train_keys),"test_cluster_count":len(test_keys),"train_cluster_key_sha256":sha_bytes(canonical([list(k) for k in sorted(train_keys)])),"test_cluster_key_sha256":sha_bytes(canonical([list(k) for k in sorted(test_keys)])),"inner_assignment_sha256":sha_bytes(canonical(payload)),"inner_assignments":payload,"inner_fold_cells":cells})
    outer_payload=[[*key,int(outer[key])] for key in sorted(outer)];row_counts=[[*key,int(len(data["cluster_rows"][index]))] for index,key in enumerate(data["clusters"])]
    outer_cells=[]
    for fold in range(5):
        ids=[i for i,key in enumerate(data["clusters"]) if outer[key]==fold];rows=np.concatenate([data["cluster_rows"][i] for i in ids]);outer_cells.append(fold_cell(data,rows,fold))
    base={"schema":"actual_incremental_sensitivity.fold_assignments","schema_version":1,"outer_seed":20260824,"inner_master_seed":20260825,"algorithm":{"sort":"(-row_count, seeded_sha256_tie_token, canonical_cluster_key)","assignment_minimum":"(domain_rows, total_rows, cluster_count, seeded_fold_priority, fold)","cluster_key":["source_cluster_domain","source_cluster_id","source_cluster_fingerprint"]},"row_order_invariant":True,"row_permutation_test":{"seed":20260824,"method":"full row permutation followed by cluster-row reconstruction","passed":True},"cluster_row_counts":row_counts,"cluster_row_count_sha256":sha_bytes(canonical(row_counts)),"outer_assignments":outer_payload,"outer_assignment_sha256":sha_bytes(canonical(outer_payload)),"outer_folds":outer_details,"outer_fold_cells":outer_cells,"coverage":{"rows":data["n"],"items":data["items"],"clusters":len(data["clusters"])}}
    expected={**base,"payload_sha256_excluding_this_field":sha_bytes(canonical(base))};frozen=load(HERE/"fold_assignments.json");self_hash(frozen)
    if expected!=frozen:raise AuditFailure("complete fold receipt differs from independent rebuild")
    return outer,inners,frozen


def alpha_exact(matrix:np.ndarray)->float|None:
    x=np.asarray(matrix,dtype=np.float64)
    if x.ndim!=2 or not np.isfinite(x).all(): raise AuditFailure("alpha input")
    n,k=x.shape
    if n<2 or k<2:return None
    rs=x.sum(1);rq=np.square(x).sum(1);m=n*k;gs=float(rs.sum());gq=float(rq.sum())
    num=2*(gq-float(np.sum((np.square(rs)-rq)/(k-1))));den=(2/(m-1))*(m*gq-gs*gs);tol=np.finfo(float).eps*max(1,abs(num),abs(den))*64
    if abs(den)<=tol:return 1.0 if abs(num)<=tol else None
    value=1-num/den;return float(value) if math.isfinite(value) else None


def pair_alpha(x:np.ndarray,y:np.ndarray)->float|None:
    z=np.column_stack((x,y)).astype(float)
    if len(z)<2 or not np.isfinite(z).all():return None
    sd=z.std(0,ddof=1)
    if np.any(sd==0) or not np.isfinite(sd).all():return None
    return alpha_exact((z-z.mean(0))/sd)


def joint_alpha(x:np.ndarray,y:np.ndarray,z:np.ndarray)->float|None:
    m=np.column_stack((x,y,z)).astype(float);sd=m.std(0,ddof=1)
    if len(m)<2 or np.any(sd==0) or not np.isfinite(m).all():return None
    return alpha_exact((m-m.mean(0))/sd)


def rho(x:np.ndarray,y:np.ndarray)->float|None:
    if len(x)<2 or not np.isfinite(x).all() or not np.isfinite(y).all():return None
    a=rankdata(x,method="average");b=rankdata(y,method="average");sa=a.std();sb=b.std()
    if sa==0 or sb==0:return None
    return float(np.mean((a-a.mean())*(b-b.mean()))/(sa*sb))


def pair(x:np.ndarray,y:np.ndarray)->dict[str,Any]:
    reason=None
    if len(x)<2:reason="insufficient_observations"
    elif not np.isfinite(x).all() or not np.isfinite(y).all():reason="nonfinite_input"
    elif np.ptp(x)==0:reason="candidate_constant"
    elif np.ptp(y)==0:reason="reference_constant"
    r=None if reason else rho(x,y);a=None if reason else pair_alpha(x,y)
    return {"n":int(len(x)),"rho":r,PAIR_ALPHA:a,"undefined_reason":reason if r is None or a is None else None}


def centered(x:np.ndarray)->np.ndarray:return (x.reshape(-1,5)-x.reshape(-1,5).mean(1,keepdims=True)).reshape(-1)


def scopes(x:np.ndarray,y:np.ndarray,data:Mapping[str,Any],subgroups:bool=True)->dict[str,Any]:
    out={"pooled":pair(x,y)};per={level:pair(x[data["levels"]==level],y[data["levels"]==level]) for level in LEVELS};out["per_level"]=per
    if any(per[level]["rho"] is None or per[level][PAIR_ALPHA] is None for level in LEVELS):out["macro_within_level"]={"n":data["items"],"rho":None,PAIR_ALPHA:None,"undefined_reason":"one_or_more_level_metrics_undefined"}
    else:out["macro_within_level"]={"n":data["items"],"rho":float(np.mean([per[l]["rho"] for l in LEVELS])),PAIR_ALPHA:float(np.mean([per[l][PAIR_ALPHA] for l in LEVELS])),"undefined_reason":None}
    out["item_centered"]=pair(centered(x),centered(y))
    if subgroups:
        out["by_domain"]={d:pair(x[data["domains"]==d],y[data["domains"]==d]) for d in sorted(set(data["domains"]))}
        out["by_generation_model"]={m:pair(x[data["models"]==m],y[data["models"]==m]) for m in sorted(set(data["models"]))}
    return out


def joint_scopes(candidate:np.ndarray,llama:np.ndarray,mixtral:np.ndarray,data:Mapping[str,Any])->dict[str,Any]:
    def cell(mask:Any)->dict[str,Any]:
        x=candidate[mask];value=joint_alpha(x,llama[mask],mixtral[mask]);return {"n":int(len(x)),JOINT_ALPHA:value,"undefined_reason":None if value is not None else "constant_or_insufficient_column"}
    out={"pooled":cell(slice(None)),"per_level":{level:cell(data["levels"]==level) for level in LEVELS}}
    vals=[out["per_level"][level][JOINT_ALPHA] for level in LEVELS];out["macro_within_level"]={"n":data["items"],JOINT_ALPHA:float(np.mean(vals)) if all(v is not None for v in vals) else None,"undefined_reason":None if all(v is not None for v in vals) else "one_or_more_level_metrics_undefined"}
    value=joint_alpha(centered(candidate),centered(llama),centered(mixtral));out["item_centered"]={"n":data["n"],JOINT_ALPHA:value,"undefined_reason":None if value is not None else "constant_or_insufficient_column"}
    out["by_domain"]={domain:cell(data["domains"]==domain) for domain in sorted(set(data["domains"]))};out["by_generation_model"]={model:cell(data["models"]==model) for model in sorted(set(data["models"]))};return out


def treatment(x:np.ndarray,data:Mapping[str,Any])->dict[str,Any]:
    out=scopes(x,data["values"]["treatment_ordinal"],data)
    for level in LEVELS:out["per_level"][level]={"n":data["items"],"rho":None,PAIR_ALPHA:None,"undefined_reason":"reference_constant_within_level"}
    out["macro_within_level"]={"n":data["items"],"rho":None,PAIR_ALPHA:None,"undefined_reason":"reference_constant_within_level"}
    matrix=x.reshape(-1,5);label=np.asarray([5,4,3,2,1.]);rhos=[];taus=[];strict=0;nonstrict=0
    for row in matrix:
        r=rho(row,label);t=kendalltau(row,label,variant="b").statistic
        if r is not None:rhos.append(r)
        if t is not None and math.isfinite(float(t)):taus.append(float(t))
        strict+=int(np.all(row[:-1]>row[1:]));nonstrict+=int(np.all(row[:-1]>=row[1:]))
    out["per_item_ordinal"]={"items":data["items"],"mean_per_item_spearman":float(np.mean(rhos)) if rhos else None,"finite_spearman_items":len(rhos),"mean_per_item_kendall_tau_b":float(np.mean(taus)) if taus else None,"finite_tau_b_items":len(taus),"strict_monotonic_items":strict,"strict_monotonic_rate":strict/data["items"],"nonstrict_monotonic_items":nonstrict,"nonstrict_monotonic_rate":nonstrict/data["items"]}
    return out


def xmatrix(data:Mapping[str,Any],name:str,strongest_single:str|None=None)->tuple[np.ndarray,list[str]]:
    v=data["values"];p=np.log1p(v["prompt_bytes"]);o=np.log1p(v["output_bytes"])
    if name==AUX_SET:
        if strongest_single not in HEURISTICS:raise AuditFailure("invalid auxiliary strongest-single feature")
        return v[strongest_single][:,None],[strongest_single]
    if name=="L":return np.column_stack((p,o,p*p,p*o,o*o)),["log1p_prompt_bytes","log1p_output_bytes","p2","p_x_o","o2"]
    if name=="O":return np.column_stack([v[f] for f in OVERLAP]),list(OVERLAP)
    if name in {"H","H+R"}:
        columns=[np.log1p(v[f]) if f in LOG_H else v[f] for f in HEURISTICS];names=[f"log1p_{f}" if f in LOG_H else f for f in HEURISTICS]
        if name=="H+R":columns.append(v["R_actual"]);names.append("R_actual")
        return np.column_stack(columns),names
    if name=="R-only":return v["R_actual"][:,None],["R_actual"]
    if name=="G-only":return v["G_raw_bits"][:,None],["G_raw_bits"]
    raise AuditFailure(name)


def lmatrix(data:Mapping[str,Any],spec:str)->tuple[np.ndarray,list[str]]:
    v=data["values"]
    if spec.startswith("byte_"):p=np.log1p(v["prompt_bytes"]);o=np.log1p(v["output_bytes"]);prefix="bytes"
    else:p=np.log1p(v["prompt_words"]);o=np.log1p(v["output_words"]);prefix="words"
    if spec.endswith("L_out"):return np.column_stack((o,o*o,o*o*o)),[f"log1p_output_{prefix}","o2","o3"]
    return np.column_stack((p,o,p*p,p*o,o*o)),[f"log1p_prompt_{prefix}",f"log1p_output_{prefix}","p2","p_x_o","o2"]


def independent_ridge(x:np.ndarray,y:np.ndarray,data:Mapping[str,Any],outer:Mapping[tuple[str,str,str],int],inners:Sequence[Mapping[tuple[str,str,str],int]],*,feature_names:Sequence[str],model_label:str)->tuple[np.ndarray,list[dict[str,Any]]]:
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error,r2_score
    from sklearn.preprocessing import StandardScaler
    out=np.full(data["n"],np.nan);cluster_outer=np.asarray([outer[k] for k in data["clusters"]],dtype=np.int8);row_outer=cluster_outer[data["cluster_index"]];records=[]
    for fold in range(5):
        test=row_outer==fold;train=~test;inner_cluster=np.full(len(data["clusters"]),-1,dtype=np.int8)
        for ci,key in enumerate(data["clusters"]):
            if cluster_outer[ci]!=fold:inner_cluster[ci]=inners[fold][key]
        inner_rows=inner_cluster[data["cluster_index"]];splits=[]
        for iv in range(5):
            valid=train&(inner_rows==iv);tr=train&(inner_rows!=iv);scaler=StandardScaler().fit(x[tr]);splits.append((valid,tr,scaler.transform(x[tr]),scaler.transform(x[valid])))
        scores=[]
        for alpha in ALPHAS:
            sse=0.;n=0
            for valid,tr,scaled_train,scaled_valid in splits:
                model=Ridge(alpha=alpha,fit_intercept=True,solver="svd").fit(scaled_train,y[tr]);pred=model.predict(scaled_valid);sse+=float(np.square(y[valid]-pred).sum());n+=int(valid.sum())
            scores.append({"alpha":alpha,"mse":sse/n,"holdout_rows":n})
        best=min(entry["mse"] for entry in scores);tol=1e-12+1e-10*abs(best);alpha=max(entry["alpha"] for entry in scores if entry["mse"]<=best+tol)
        scaler=StandardScaler().fit(x[train]);model=Ridge(alpha=alpha,fit_intercept=True,solver="svd").fit(scaler.transform(x[train]),y[train]);prediction=model.predict(scaler.transform(x[test]));out[test]=prediction
        train_clusters=sorted(set(data["cluster_index"][train].tolist()));test_clusters=sorted(set(data["cluster_index"][test].tolist()))
        records.append({"model_label":model_label,"learner":"Ridge","outer_fold":fold,"feature_names":list(feature_names),"selected_alpha":alpha,"inner_scores":scores,"scaler_mean":scaler.mean_.tolist(),"scaler_scale":scaler.scale_.tolist(),"coefficients_standardized":model.coef_.tolist(),"intercept":float(model.intercept_),"train_rows":int(train.sum()),"test_rows":int(test.sum()),"train_cluster_count":len(train_clusters),"test_cluster_count":len(test_clusters),"train_cluster_sha256":sha_bytes(canonical([list(data["clusters"][i]) for i in train_clusters])),"test_cluster_sha256":sha_bytes(canonical([list(data["clusters"][i]) for i in test_clusters])),"test_r2_auxiliary":float(r2_score(y[test],prediction)),"test_mae_auxiliary":float(mean_absolute_error(y[test],prediction))})
    return out,records


def independent_hgb(x:np.ndarray,y:np.ndarray,data:Mapping[str,Any],outer:Mapping[tuple[str,str,str],int],*,model_label:str)->tuple[np.ndarray,list[dict[str,Any]]]:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error,r2_score
    out=np.full(data["n"],np.nan);co=np.asarray([outer[k] for k in data["clusters"]],dtype=np.int8);ro=co[data["cluster_index"]]
    params=dict(loss="squared_error",learning_rate=.05,max_iter=200,max_leaf_nodes=15,max_depth=None,min_samples_leaf=50,l2_regularization=1.,max_bins=255,early_stopping=False,random_state=20260826);records=[]
    for fold in range(5):
        test=ro==fold;train=~test;prediction=HistGradientBoostingRegressor(**params).fit(x[train],y[train]).predict(x[test]);out[test]=prediction;train_clusters=sorted(set(data["cluster_index"][train].tolist()));test_clusters=sorted(set(data["cluster_index"][test].tolist()))
        records.append({"model_label":model_label,"learner":"HistGradientBoostingRegressor","outer_fold":fold,"parameters":params,"train_rows":int(train.sum()),"test_rows":int(test.sum()),"train_cluster_count":len(train_clusters),"test_cluster_count":len(test_clusters),"train_cluster_sha256":sha_bytes(canonical([list(data["clusters"][i]) for i in train_clusters])),"test_cluster_sha256":sha_bytes(canonical([list(data["clusters"][i]) for i in test_clusters])),"test_r2_auxiliary":float(r2_score(y[test],prediction)),"test_mae_auxiliary":float(mean_absolute_error(y[test],prediction))})
    return out,records


def hgb_import_available()->bool:
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: F401
    except ImportError:
        return False
    return True


def expected_prediction_keys(include_hgb:bool)->list[str]:
    keys=[f"ridge|{target}|{name}" for target in TARGETS for name in (*SETS,AUX_SET)]
    if include_hgb:keys.extend(f"hgb|{target}|{name}" for target in TARGETS for name in (*SETS,AUX_SET))
    keys.extend(f"length_ridge|{spec}|{target}" for spec in LENGTH_SPECS for target in LENGTH_TARGETS)
    return sorted(keys)


def expected_residual_keys()->list[str]:
    return sorted(f"{spec}|{target}" for spec in LENGTH_SPECS for target in LENGTH_TARGETS)


def read_oof(data:Mapping[str,Any],outer:Mapping[tuple[str,str,str],int])->tuple[dict[str,np.ndarray],dict[str,np.ndarray]]:
    expected_predictions=expected_prediction_keys(hgb_import_available());expected_residuals=expected_residual_keys()
    expected_fields=tuple(sorted([
        "generation_model","domain","id","level","outer_fold",
        *(f"prediction|{key}" for key in expected_predictions),
        *(f"residual|{key}" for key in expected_residuals),
    ]))
    predictions={key:np.empty(data["n"],dtype=np.float64) for key in expected_predictions};residuals={key:np.empty(data["n"],dtype=np.float64) for key in expected_residuals};seen=set();count=0
    with open_plain(HERE/"oof_predictions.jsonl") as handle:
        for i,raw in enumerate(handle):
            if raw[-1:]!=b"\n" or raw.endswith(b"\r\n"):raise AuditFailure("OOF canonical LF")
            row=loads(raw,"oof")
            if not isinstance(row,dict) or tuple(sorted(row))!=expected_fields:raise AuditFailure("OOF exact schema")
            key=(row.pop("generation_model"),row.pop("domain"),row.pop("id"),row.pop("level"));stored_outer=row.pop("outer_fold")
            if key!=data["pair_keys"][i] or key in seen:raise AuditFailure("OOF key/order")
            expected_outer=outer[data["clusters"][int(data["cluster_index"][i])]]
            if isinstance(stored_outer,bool) or stored_outer!=expected_outer:raise AuditFailure("OOF outer_fold differs")
            seen.add(key);count+=1
            for name in predictions:predictions[name][i]=finite(row[f"prediction|{name}"],name)
            for name in residuals:residuals[name][i]=finite(row[f"residual|{name}"],name)
    if count!=data["n"] or len(seen)!=data["n"]:raise AuditFailure("OOF coverage")
    return predictions,residuals


def read_fit_records()->list[dict[str,Any]]:
    records=[];previous=None
    ridge_fields={"model_label","learner","outer_fold","feature_names","selected_alpha","inner_scores","scaler_mean","scaler_scale","coefficients_standardized","intercept","train_rows","test_rows","train_cluster_count","test_cluster_count","train_cluster_sha256","test_cluster_sha256","test_r2_auxiliary","test_mae_auxiliary"}
    hgb_fields={"model_label","learner","outer_fold","parameters","train_rows","test_rows","train_cluster_count","test_cluster_count","train_cluster_sha256","test_cluster_sha256","test_r2_auxiliary","test_mae_auxiliary"}
    skip_fields={"model_label","learner","status"}
    with open_plain(HERE/"model_fits.jsonl") as handle:
        for line_number,raw in enumerate(handle,1):
            if raw[-1:]!=b"\n" or raw.endswith(b"\r\n"):raise AuditFailure("model fits LF")
            record=loads(raw,"fits");learner=record.get("learner")
            expected=ridge_fields if learner=="Ridge" else skip_fields if record.get("status")=="skipped_unavailable" else hgb_fields if learner=="HistGradientBoostingRegressor" else set()
            if set(record)!=expected:raise AuditFailure(f"model-fit schema line {line_number}")
            order=(str(record["model_label"]),int(record.get("outer_fold",-1)))
            if previous is not None and order<=previous:raise AuditFailure("model-fit order/duplicate")
            previous=order;records.append(record)
    return records


def refit_all(data:Mapping[str,Any],outer:Mapping[tuple[str,str,str],int],inners:Sequence[Mapping[tuple[str,str,str],int]],stored_p:Mapping[str,np.ndarray],stored_r:Mapping[str,np.ndarray],fit_records:Sequence[Mapping[str,Any]],strongest_single:str)->dict[str,Any]:
    max_prediction=0.;max_prediction_ratio=0.;max_fit_error=0.;ridge_models=0;hgb_models=0;expected_records={};available=hgb_import_available()
    actual_lookup={(r["model_label"],int(r.get("outer_fold",-1))):r for r in fit_records}
    if len(actual_lookup)!=len(fit_records):raise AuditFailure("duplicate model-fit keys")
    for target in TARGETS:
        for name in (*SETS,AUX_SET):
            key=f"ridge|{target}|{name}";x,names=xmatrix(data,name,strongest_single);pred,records=independent_ridge(x,data["values"][target],data,outer,inners,feature_names=names,model_label=key)
            error=np.abs(pred-stored_p[key]);max_prediction=max(max_prediction,float(np.max(error)));max_prediction_ratio=max(max_prediction_ratio,float(np.max(error/(1e-12+1e-10*np.abs(stored_p[key])))));ridge_models+=5
            if not np.allclose(pred,stored_p[key],atol=1e-12,rtol=1e-10):raise AuditFailure(f"ridge prediction {key}")
            for record in records:expected_records[(key,record["outer_fold"])]=record
            hkey=f"hgb|{target}|{name}"
            if available:
                hp,hrecords=independent_hgb(x,data["values"][target],data,outer,model_label=hkey);error=np.abs(hp-stored_p[hkey]);max_prediction=max(max_prediction,float(np.max(error)));max_prediction_ratio=max(max_prediction_ratio,float(np.max(error/(1e-12+1e-10*np.abs(stored_p[hkey])))));hgb_models+=5
                if not np.allclose(hp,stored_p[hkey],atol=1e-12,rtol=1e-10):raise AuditFailure(f"HGB prediction {hkey}")
                for record in hrecords:expected_records[(hkey,record["outer_fold"])]=record
            else:
                expected_records[(hkey,-1)]={"model_label":hkey,"learner":"HistGradientBoostingRegressor","status":"skipped_unavailable"}
    for spec in LENGTH_SPECS:
        x,names=lmatrix(data,spec)
        for target in LENGTH_TARGETS:
            key=f"length_ridge|{spec}|{target}";pred,records=independent_ridge(x,data["values"][target],data,outer,inners,feature_names=names,model_label=key)
            error=np.abs(pred-stored_p[key]);max_prediction=max(max_prediction,float(np.max(error)));max_prediction_ratio=max(max_prediction_ratio,float(np.max(error/(1e-12+1e-10*np.abs(stored_p[key])))));ridge_models+=5
            if not np.allclose(pred,stored_p[key],atol=1e-12,rtol=1e-10):raise AuditFailure(f"length prediction {key}")
            residual=data["values"][target]-pred
            if not np.allclose(residual,stored_r[f"{spec}|{target}"],atol=1e-12,rtol=1e-10):raise AuditFailure(f"residual {key}")
            for record in records:expected_records[(key,record["outer_fold"])]=record
    if set(actual_lookup)!=set(expected_records):raise AuditFailure(f"model-fit exact inventory differs; missing={len(set(expected_records)-set(actual_lookup))}, unknown={len(set(actual_lookup)-set(expected_records))}")
    for key,expected in expected_records.items():max_fit_error=max(max_fit_error,compare_recursive(expected,actual_lookup[key],path=f"model_fit.{key}",tolerance=1e-10))
    return {"ridge_outer_models_refit":ridge_models,"hgb_outer_models_refit":hgb_models,"hgb_import_available":available,"exact_model_inventory":True,"all_model_fit_metadata_recomputed":True,"maximum_prediction_absolute_error":max_prediction,"maximum_prediction_tolerance_ratio":max_prediction_ratio,"maximum_model_fit_metadata_absolute_error":max_fit_error,"maximum_model_fit_metadata_allowed_absolute_error":1e-10,"prediction_atol":1e-12,"prediction_rtol":1e-10,"fit_metadata_tolerance":1e-10}


def ordering(data:Mapping[str,Any])->dict[str,Any]:
    l=data["values"]["phi_actual_llama"].reshape(-1,5);m=data["values"]["phi_actual_mixtral"].reshape(-1,5);r=data["values"]["R_actual"].reshape(-1,5);out={}
    for family,pairs in (("all_ten",ALL_PAIRS),("adjacent_four",ADJACENT)):
        records={}
        for high,low in pairs:
            i=LEVELS.index(high);j=LEVELS.index(low);dl=np.sign(l[:,i]-l[:,j]);dm=np.sign(m[:,i]-m[:,j]);dr=np.sign(r[:,i]-r[:,j]);tied=(dl==0)|(dm==0);con=(~tied)&(dl==dm);dis=(~tied)&(dl==-dm);match=con&(dr==dl);reverse=con&(dr==-dl);rtie=con&(dr==0);nt=int((~tied).sum());cn=int(con.sum())
            records[f"{high}-{low}"]={"items":data["items"],"concordant":int(con.sum()),"discordant":int(dis.sum()),"tied_either_evaluator":int(tied.sum()),"inversion_rate_all":float(dis.sum()/data["items"]),"inversion_rate_non_tie":float(dis.sum()/nt) if nt else None,"R_on_evaluator_concordant_non_tied":{"n":cn,"same_sign":int(match.sum()),"opposite_sign":int(reverse.sum()),"tied":int(rtie.sum()),"same_sign_rate":float(match.sum()/cn) if cn else None}}
        out[family]=records
    sl=np.all(l[:,:-1]>l[:,1:],axis=1);sm=np.all(m[:,:-1]>m[:,1:],axis=1);out["strict_monotonicity"]={"llama_items":int(sl.sum()),"mixtral_items":int(sm.sum()),"both_items":int((sl&sm).sum()),"denominator_items":data["items"]}
    d=data["values"]["evaluator_absolute_global_z_difference"];qs=[0.,.1,.25,.5,.75,.9,.95,.99,1.]
    out["absolute_global_z_difference"]={"definition":"abs(z_llama_global-z_mixtral_global)","mean":float(d.mean()),"sd_ddof1":float(d.std(ddof=1)),"quantiles_linear":{format(q,".2f"):float(np.quantile(d,q,method="linear")) for q in qs},"by_level":{level:float(d[data["levels"]==level].mean()) for level in LEVELS},"by_domain":{domain:float(d[data["domains"]==domain].mean()) for domain in sorted(set(data["domains"]))},"by_generation_model":{model:float(d[data["models"]==model].mean()) for model in sorted(set(data["models"]))},"subgroups_use_global_z_not_restandardized":True}
    return out


def support(data:Mapping[str,Any])->dict[str,Any]:
    b=data["values"]["output_bytes"].reshape(-1,5);records={};concordance={};previous={};method_fields=(("R","R_actual"),("G","G_raw_bits"),("Llama","phi_actual_llama"),("Mixtral","phi_actual_mixtral"))
    for cal in (1.10,1.20,1.30):
        ck=format(cal,".2f");records[ck]={};pooled={label:[] for label,_ in method_fields};centered_values={label:[] for label,_ in method_fields};pooled_labels=[];centered_labels=[]
        for high,low in ADJACENT:
            i=LEVELS.index(high);j=LEVELS.index(low);ratio=np.maximum(b[:,i],b[:,j])/np.minimum(b[:,i],b[:,j]);mask=ratio<=cal;key=f"{high}-{low}"
            if key in previous and np.any(previous[key]&~mask):raise AuditFailure("caliper nesting")
            previous[key]=mask;items=np.flatnonzero(mask);rows=np.concatenate((items*5+i,items*5+j)) if len(items) else np.empty(0,dtype=int);clusters=np.unique(data["cluster_index"][rows]);methods={};labels=np.tile(np.asarray([LEVEL_VALUE[high],LEVEL_VALUE[low]],dtype=float),(len(items),1));pooled_labels.append(labels.reshape(-1));centered_labels.append((labels-labels.mean(1,keepdims=True)).reshape(-1))
            for label,field in method_fields:
                matrix=data["values"][field].reshape(-1,5);pair_matrix=matrix[items][:,[i,j]];diff=pair_matrix[:,0]-pair_matrix[:,1];pooled[label].append(pair_matrix.reshape(-1));centered_values[label].append((pair_matrix-pair_matrix.mean(1,keepdims=True)).reshape(-1))
                methods[label]={"n":int(len(diff)),"mean_higher_minus_lower":float(diff.mean()) if len(diff) else None,"median_higher_minus_lower":float(np.median(diff)) if len(diff) else None,"expected":int((diff>0).sum()),"reverse":int((diff<0).sum()),"tie":int((diff==0).sum()),"expected_rate":float((diff>0).mean()) if len(diff) else None,"reverse_rate":float((diff<0).mean()) if len(diff) else None,"tie_rate":float((diff==0).mean()) if len(diff) else None}
            records[ck][key]={"retained_model_item_pairs":int(len(items)),"source_clusters":int(len(clusters)),"domain_items":dict(sorted(Counter(data["domains"][items*5]).items())),"generation_model_items":dict(sorted(Counter(data["models"][items*5]).items())),"methods":methods}
        pt=np.concatenate(pooled_labels);ct=np.concatenate(centered_labels);concordance[ck]={label:{"pooled":pair(np.concatenate(pooled[label]),pt),"adjacent_pair_centered":pair(np.concatenate(centered_values[label]),ct)} for label,_ in method_fields}
    ratio=b.max(1)/b.min(1);mask=ratio<=1.25;items=np.flatnonzero(mask);rows=items*5;allrows=np.concatenate([items*5+i for i in range(5)]) if mask.any() else np.empty(0,dtype=int);clusters=np.unique(data["cluster_index"][allrows]);domains=Counter(data["domains"][rows]);models=Counter(data["models"][rows]);reasons=[]
    if mask.sum()<1123:reasons.append("items_below_1123")
    if len(clusters)<256:reasons.append("clusters_below_256")
    if set(domains)!=set(DOMAIN_ITEMS):reasons.append("domain_absent")
    if set(models)!=set(MODEL_ITEMS):reasons.append("generation_model_absent")
    inference=None
    if not reasons:
        labels=np.tile(np.asarray([5,4,3,2,1.]),len(items));inference={}
        for label,field in method_fields:
            candidate=data["values"][field].reshape(-1,5)[items].reshape(-1);inference[label]={"pooled":pair(candidate,labels),"item_centered":pair(centered(candidate),centered(labels))}
    return {"adjacent_byte_calipers":records,"adjacent_treatment_concordance":concordance,"nesting_asserted":True,"all_five_byte_1.25":{"items":int(mask.sum()),"clusters":int(len(clusters)),"domain_items":dict(sorted(domains.items())),"generation_model_items":dict(sorted(models.items())),"low_support":bool(reasons),"low_support_reasons":reasons,"inference_policy":"coverage_only" if reasons else "full_exploratory_inference","inference":inference}}


def rebuilt_metrics(data:Mapping[str,Any],predictions:Mapping[str,np.ndarray],residuals:Mapping[str,np.ndarray])->dict[str,Any]:
    refs={"treatment_ordinal":data["values"]["treatment_ordinal"],"phi_actual_llama":data["values"]["phi_actual_llama"],"phi_actual_mixtral":data["values"]["phi_actual_mixtral"],"consensus_midrank_percentile":data["values"]["consensus_midrank_percentile"],"consensus_global_z":data["values"]["consensus_global_z"]};direct={}
    for candidate in DIRECT:
        vector=data["values"][candidate];record={}
        for name,reference in refs.items():record[name]=treatment(vector,data) if name=="treatment_ordinal" else scopes(vector,reference,data)
        record[JOINT_ALPHA]=joint_scopes(vector,refs["phi_actual_llama"],refs["phi_actual_mixtral"],data);direct[candidate]=record
    incremental={}
    for key,pred in sorted(predictions.items()):
        learner,target,predictor=key.split("|",2)
        if learner=="length_ridge":continue
        if learner not in {"ridge","hgb"} or target not in TARGETS or predictor not in {*SETS,AUX_SET}:raise AuditFailure(f"invalid predictive key {key}")
        reference=data["values"][target];incremental[key]={"agreement":scopes(pred,reference,data),"auxiliary":{"r2":float(1-np.square(reference-pred).sum()/np.square(reference-reference.mean()).sum()),"mae":float(np.abs(reference-pred).mean())}}
    length={}
    for spec in LENGTH_SPECS:
        result={}
        for evaluator in TARGETS:
            ref=residuals[f"{spec}|{evaluator}"]
            for candidate in ("R_actual","G_raw_bits","G_raw_bits_per_output_byte"):result[f"{candidate}_vs_{evaluator}"]=scopes(residuals[f"{spec}|{candidate}"],ref,data)
        result["residual_candidate_vs_raw_treatment_ordinal"]=treatment(residuals[f"{spec}|R_actual"],data);length[spec]=result
    return {"schema":"actual_incremental_sensitivity.metrics","schema_version":1,"estimand":"aggregate R_actual on real pairs only","coverage":{"pairs":data["n"],"items":data["items"],"source_clusters":len(data["clusters"])},"metric_namespaces":{"rho":"Spearman average midranks","alpha":PAIR_ALPHA,"joint":JOINT_ALPHA},"direct":direct,"incremental_validity":incremental,"evaluator_sensitivity":{"llama_vs_mixtral":scopes(data["values"]["phi_actual_llama"],data["values"]["phi_actual_mixtral"],data),"ordering":ordering(data)},"length_residualized":length,"common_support":support(data),"treatment_terminology":"investigator-specified ordinal treatment labels","scientific_limits":["agreement and predictive convergence do not establish criterion truth","treatment levels are designed ordinal treatments, not independent human annotations","cross-fitted predictive CIs are conditional on frozen OOF predictions","residual_candidate_vs_raw_treatment_ordinal is one-sided nuisance residualization, not a two-sided partial correlation","no counterfactual-derived quantity is analyzed"]}


def compare_recursive(expected:Any,actual:Any,path:str="root",tolerance:float=2e-12)->float:
    maximum=0.
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or set(expected)!=set(actual):raise AuditFailure(f"keys differ {path}: {set(expected)^set(actual) if isinstance(actual,dict) else type(actual)}")
        for key in expected:maximum=max(maximum,compare_recursive(expected[key],actual[key],f"{path}.{key}",tolerance))
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(expected)!=len(actual):raise AuditFailure(f"list differs {path}")
        for i,(a,b) in enumerate(zip(expected,actual,strict=True)):maximum=max(maximum,compare_recursive(a,b,f"{path}[{i}]",tolerance))
    elif isinstance(expected,(int,float)) and not isinstance(expected,bool):
        if not isinstance(actual,(int,float)) or isinstance(actual,bool):raise AuditFailure(f"numeric type {path}")
        error=abs(float(expected)-float(actual));maximum=max(maximum,error)
        if error>tolerance:raise AuditFailure(f"numeric difference {path}: {error}")
    elif expected!=actual:raise AuditFailure(f"value differs {path}")
    return maximum


def expected_bootstrap_keys(config:Mapping[str,Any],include_hgb:bool)->list[str]:
    selections=config["frozen_strongest"]
    baselines=tuple(dict.fromkeys(("G_raw_bits","G_raw_bits_per_output_byte","prompt_to_output_byte_ratio","rouge_l_recall",selections["strongest_word_overlap"]["selected"],selections["strongest_char_overlap"]["selected"])))
    keys=[]
    for baseline in baselines:
        for reference in ("llama","mixtral","consensus_rank","consensus_z","treatment"):
            scopes_=("pooled","item_centered") if reference=="treatment" else ("macro_within_level","item_centered")
            for scope_ in scopes_:
                for metric in ("rho",PAIR_ALPHA):keys.append(f"direct_delta|R_actual-minus-{baseline}|{reference}|{scope_}|{metric}")
    for learner in (("ridge","hgb") if include_hgb else ("ridge",)):
        for target in TARGETS:
            for left,right in (("H+R","H"),("H","L"),("H","O"),("R-only","G-only"),("R-only",AUX_SET)):
                for scope_ in ("macro_within_level","item_centered"):
                    for metric in ("rho",PAIR_ALPHA):keys.append(f"incremental_delta|{learner}|{target}|{left}-minus-{right}|{scope_}|{metric}")
    for spec in LENGTH_SPECS:
        for target in TARGETS:
            for baseline in ("G_raw_bits","G_raw_bits_per_output_byte"):
                for scope_ in ("macro_within_level","item_centered"):
                    for metric in ("rho",PAIR_ALPHA):keys.append(f"length_delta|{spec}|{target}|R_actual-minus-{baseline}|{scope_}|{metric}")
    for cal in (1.10,1.20,1.30):
        for high,low in ADJACENT:
            for label in ("R","G","Llama","Mixtral"):
                for statistic in ("mean","median","expected_rate","reverse_rate","tie_rate"):keys.append(f"support|{cal:.2f}|{high}-{low}|{label}|{statistic}")
        for label in ("R","G","Llama","Mixtral"):
            for scope_ in ("pooled","adjacent_pair_centered"):
                for metric in ("rho",PAIR_ALPHA):keys.append(f"support_treatment|{cal:.2f}|{label}|{scope_}|{metric}")
    if len(keys)!=len(set(keys)):raise AuditFailure("independent expected bootstrap keys duplicate")
    return keys


def checkpoint_descriptor(arrays:Mapping[str,np.ndarray])->dict[str,dict[str,Any]]:
    return {key:{"dtype":np.asarray(value).dtype.str,"shape":list(np.asarray(value).shape)} for key,value in sorted(arrays.items())}


def checkpoint_payload(arrays:Mapping[str,np.ndarray])->str:
    return sha_bytes(canonical({key:array_sha(np.asarray(value)) for key,value in sorted(arrays.items())}))


def deterministic_npz(arrays:Mapping[str,np.ndarray],metadata:Mapping[str,Any])->bytes:
    payload={key:np.asarray(value) for key,value in arrays.items()};payload["metadata_json"]=np.asarray(canonical(metadata).decode("utf-8"));output=io.BytesIO()
    with zipfile.ZipFile(output,mode="w",compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
        for key in sorted(payload):
            buffer=io.BytesIO();np.lib.format.write_array(buffer,payload[key],allow_pickle=False);info=zipfile.ZipInfo(f"{key}.npy",date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED;info.create_system=3;info.external_attr=0o600<<16;archive.writestr(info,buffer.getvalue())
    return output.getvalue()


def require_deterministic_npz(path:Path,arrays:Mapping[str,np.ndarray],metadata:Mapping[str,Any])->None:
    expected=deterministic_npz(arrays,metadata);digest,size=fingerprint(path)
    if size!=len(expected) or digest!=sha_bytes(expected):raise AuditFailure(f"non-deterministic/tampered NPZ bytes {path}")


def read_checkpoint_matrix(keys:Sequence[str],config_sha:str)->tuple[np.ndarray,np.ndarray]:
    value_blocks=[];effective_blocks=[];expected_start=0;paths=sorted((HERE/"checkpoints"/"bootstrap").glob("*.npz"));expected_paths=[HERE/"checkpoints"/"bootstrap"/f"block_{start:04d}_{start+25:04d}.npz" for start in range(0,2000,25)]
    if paths!=expected_paths:raise AuditFailure("bootstrap checkpoint exact file inventory")
    for path in paths:
        with open_plain(path) as handle:
            with np.load(handle,allow_pickle=False) as stored:
                if set(stored.files)!={"values","effective","keys","metadata_json"}:raise AuditFailure("bootstrap checkpoint arrays")
                metadata=loads(str(stored["metadata_json"].item()),"checkpoint metadata");arrays={name:np.asarray(stored[name]) for name in ("values","effective","keys")}
        values=arrays["values"];effective=arrays["effective"];stored_keys=[str(x) for x in arrays["keys"]]
        expected_metadata={"schema":"actual_incremental_sensitivity.bootstrap_checkpoint","schema_version":1,"config_sha256":config_sha,"metric_key_sha256":sha_bytes(canonical(list(keys))),"replicate_start_inclusive":expected_start,"replicate_end_exclusive":expected_start+len(values),"arrays":checkpoint_descriptor(arrays),"payload_sha256":checkpoint_payload(arrays)}
        if metadata!=expected_metadata or stored_keys!=list(keys):raise AuditFailure("bootstrap checkpoint binding")
        require_deterministic_npz(path,arrays,metadata)
        if values.dtype!=np.dtype("float64") or effective.dtype!=np.dtype("int32") or arrays["keys"].dtype.kind!="U" or arrays["keys"].shape!=(len(keys),) or values.shape!=(25,len(keys)) or effective.shape!=values.shape:raise AuditFailure("bootstrap checkpoint dtype/shape")
        expected_start+=len(values);value_blocks.append(values);effective_blocks.append(effective)
    if expected_start!=2000:raise AuditFailure("bootstrap block coverage")
    return np.concatenate(value_blocks),np.concatenate(effective_blocks)


def array_sha(array:np.ndarray)->str:
    x=np.ascontiguousarray(array);return sha_bytes(canonical({"dtype":x.dtype.str,"shape":list(x.shape)})+x.tobytes())


def sampled_metrics(x:np.ndarray,y:np.ndarray,indices:np.ndarray,levels:np.ndarray,cx:np.ndarray,cy:np.ndarray,scope:str)->dict[str,float]:
    metrics=("rho",PAIR_ALPHA)
    if scope=="item_centered":
        cell=pair(cx[indices],cy[indices]);return {metric:math.nan if cell[metric] is None else float(cell[metric]) for metric in metrics}
    if scope=="pooled":
        cell=pair(x[indices],y[indices]);return {metric:math.nan if cell[metric] is None else float(cell[metric]) for metric in metrics}
    values={metric:[] for metric in metrics};sample_levels=levels[indices]
    for level in LEVELS:
        subset=indices[sample_levels==level];cell=pair(x[subset],y[subset])
        for metric in metrics:values[metric].append(math.nan if cell[metric] is None else float(cell[metric]))
    return {metric:float(np.mean(series)) if np.isfinite(series).all() else math.nan for metric,series in values.items()}


def weighted_median(values:np.ndarray,weights:np.ndarray)->float|None:
    total=int(weights.sum())
    if total==0:return None
    order=np.argsort(values,kind="mergesort");ordered=values[order];cumulative=np.cumsum(weights[order],dtype=np.int64);lower=(total-1)//2;upper=total//2
    return float((ordered[int(np.searchsorted(cumulative,lower+1,side="left"))]+ordered[int(np.searchsorted(cumulative,upper+1,side="left"))])/2)


def bootstrap_replay(data:Mapping[str,Any],predictions:Mapping[str,np.ndarray],residuals:Mapping[str,np.ndarray],summary:Mapping[str,Any],config:Mapping[str,Any],config_sha:str)->dict[str,Any]:
    expected_summary_fields={"schema","schema_version","method","replicates","seed","cluster_count","block_size","draw_sequence_sha256","metric_key_sha256","metric_keys","conditional_on_frozen_cross_fitted_predictions","metrics"}
    if set(summary)!=expected_summary_fields or summary.get("schema")!="actual_incremental_sensitivity.bootstrap_summary" or summary.get("replicates")!=2000 or summary.get("seed")!=20260823 or summary.get("cluster_count")!=2551 or summary.get("block_size")!=25:raise AuditFailure("bootstrap summary exact schema/frozen values")
    keys=list(summary["metric_keys"]);expected_keys=expected_bootstrap_keys(config,hgb_import_available())
    if keys!=expected_keys or set(summary["metrics"])!=set(keys) or summary.get("metric_key_sha256")!=sha_bytes(canonical(keys)):
        raise AuditFailure("bootstrap exact metric inventory/order")
    center_cache={}
    for vector in [*data["values"].values(),*predictions.values(),*residuals.values()]:
        if isinstance(vector,np.ndarray) and vector.shape==(data["n"],):center_cache[id(vector)]=centered(vector)
    support_cache={};support_treatment_cache={};bytes_=data["values"]["output_bytes"].reshape(-1,5);item_cluster=data["cluster_index"][::5]
    def cached_score(x:np.ndarray,y:np.ndarray,indices:np.ndarray,scope:str,metric:str,agreement_cache:dict[tuple[int,int,str],dict[str,float]])->float:
        cache_key=(id(x),id(y),scope)
        if cache_key not in agreement_cache:agreement_cache[cache_key]=sampled_metrics(x,y,indices,data["levels"],center_cache[id(x)],center_cache[id(y)],scope)
        return agreement_cache[cache_key][metric]
    def calculate(key:str,indices:np.ndarray,multiplicity:np.ndarray,agreement_cache:dict[tuple[int,int,str],dict[str,float]])->float:
        parts=key.split("|")
        if parts[0]=="direct_delta":
            baseline=parts[1].removeprefix("R_actual-minus-");reference={"llama":data["values"]["phi_actual_llama"],"mixtral":data["values"]["phi_actual_mixtral"],"consensus_rank":data["values"]["consensus_midrank_percentile"],"consensus_z":data["values"]["consensus_global_z"],"treatment":data["values"]["treatment_ordinal"]}[parts[2]];left=data["values"]["R_actual"];right=data["values"][baseline];scope,metric=parts[3],parts[4]
            return cached_score(left,reference,indices,scope,metric,agreement_cache)-cached_score(right,reference,indices,scope,metric,agreement_cache)
        if parts[0]=="incremental_delta":
            _,learner,target,contrast,scope,metric=parts;left_name,right_name=contrast.split("-minus-");left=predictions[f"{learner}|{target}|{left_name}"];right=predictions[f"{learner}|{target}|{right_name}"];reference=data["values"][target]
            return cached_score(left,reference,indices,scope,metric,agreement_cache)-cached_score(right,reference,indices,scope,metric,agreement_cache)
        if parts[0]=="length_delta":
            _,spec,target,contrast,scope,metric=parts;baseline=contrast.removeprefix("R_actual-minus-");left=residuals[f"{spec}|R_actual"];right=residuals[f"{spec}|{baseline}"];reference=residuals[f"{spec}|{target}"]
            return cached_score(left,reference,indices,scope,metric,agreement_cache)-cached_score(right,reference,indices,scope,metric,agreement_cache)
        if parts[0]=="support":
            _,cal_text,pair_text,label,statistic=parts;high,low=pair_text.split("-");i=LEVELS.index(high);j=LEVELS.index(low);cache_key=(cal_text,pair_text,label)
            if cache_key not in support_cache:
                cal=float(cal_text);mask=np.maximum(bytes_[:,i],bytes_[:,j])/np.minimum(bytes_[:,i],bytes_[:,j])<=cal;field={"R":"R_actual","G":"G_raw_bits","Llama":"phi_actual_llama","Mixtral":"phi_actual_mixtral"}[label];diff=data["values"][field].reshape(-1,5)[:,i]-data["values"][field].reshape(-1,5)[:,j];support_cache[cache_key]=(mask,diff)
            mask,diff=support_cache[cache_key];weights=multiplicity[item_cluster]*mask;total=weights.sum()
            if total==0:return math.nan
            if statistic=="mean":return float(np.dot(weights,diff)/total)
            if statistic=="median":
                value=weighted_median(diff,weights);return math.nan if value is None else value
            if statistic=="expected_rate":return float(np.dot(weights,diff>0)/total)
            if statistic=="reverse_rate":return float(np.dot(weights,diff<0)/total)
            return float(np.dot(weights,diff==0)/total)
        if parts[0]=="support_treatment":
            _,cal_text,label,scope,metric=parts;cache_key=(cal_text,label)
            if cache_key not in support_treatment_cache:
                cal=float(cal_text);field={"R":"R_actual","G":"G_raw_bits","Llama":"phi_actual_llama","Mixtral":"phi_actual_mixtral"}[label];candidate_parts=[];label_parts=[];cluster_parts=[]
                for high,low in ADJACENT:
                    i=LEVELS.index(high);j=LEVELS.index(low);mask=np.maximum(bytes_[:,i],bytes_[:,j])/np.minimum(bytes_[:,i],bytes_[:,j])<=cal;retained=np.flatnonzero(mask);candidate_parts.append(data["values"][field].reshape(-1,5)[retained][:,[i,j]]);label_parts.append(np.tile(np.asarray([LEVEL_VALUE[high],LEVEL_VALUE[low]],dtype=float),(len(retained),1)));cluster_parts.append(item_cluster[retained])
                support_treatment_cache[cache_key]=(np.concatenate(candidate_parts),np.concatenate(label_parts),np.concatenate(cluster_parts))
            candidate,labels,clusters=support_treatment_cache[cache_key];weights=multiplicity[clusters];repeated=np.repeat(np.arange(len(weights),dtype=np.int64),weights)
            if len(repeated)==0:return math.nan
            x=candidate[repeated];y=labels[repeated]
            if scope=="adjacent_pair_centered":x=x-x.mean(1,keepdims=True);y=y-y.mean(1,keepdims=True)
            cell=pair(x.reshape(-1),y.reshape(-1));return math.nan if cell[metric] is None else float(cell[metric])
        raise AuditFailure(f"unknown bootstrap key {key}")
    def effective_count(key:str,indices:np.ndarray,multiplicity:np.ndarray)->int:
        parts=key.split("|")
        if parts[0] in {"direct_delta","incremental_delta","length_delta"}:
            scope_=parts[-2]
            return int(len(indices)//5 if scope_=="macro_within_level" else len(indices))
        if parts[0]=="support":
            _,cal_text,pair_text,_,_=parts;high,low=pair_text.split("-");i=LEVELS.index(high);j=LEVELS.index(low);mask=np.maximum(bytes_[:,i],bytes_[:,j])/np.minimum(bytes_[:,i],bytes_[:,j])<=float(cal_text)
            return int(np.sum(multiplicity[item_cluster]*mask.astype(np.int64)))
        if parts[0]=="support_treatment":
            _,cal_text,_,_,_=parts;total=0
            for high,low in ADJACENT:
                i=LEVELS.index(high);j=LEVELS.index(low);mask=np.maximum(bytes_[:,i],bytes_[:,j])/np.minimum(bytes_[:,i],bytes_[:,j])<=float(cal_text);total+=int(np.sum(multiplicity[item_cluster]*mask.astype(np.int64)))
            return 2*total
        raise AuditFailure(f"unknown effective-count key {key}")
    matrix,effective_matrix=read_checkpoint_matrix(keys,config_sha);replayed=np.full_like(matrix,np.nan);replayed_effective=np.zeros_like(effective_matrix,dtype=np.int32);digest=hashlib.sha256();max_error=0.
    for replicate in range(2000):
        seed=int.from_bytes(hashlib.sha256(f"20260823\0{replicate}".encode("ascii")).digest()[:8],"big");draw=np.random.default_rng(seed).integers(0,2551,size=2551,dtype=np.int32);digest.update(draw.tobytes());mult=np.bincount(draw,minlength=2551).astype(np.int32);indices=np.concatenate([data["cluster_rows"][int(i)] for i in draw]);agreement_cache={}
        for column,key in enumerate(keys):
            replayed[replicate,column]=calculate(key,indices,mult,agreement_cache)
            replayed_effective[replicate,column]=effective_count(key,indices,mult)
        finite=np.isfinite(replayed[replicate])&np.isfinite(matrix[replicate])
        if finite.any():max_error=max(max_error,float(np.max(np.abs(replayed[replicate,finite]-matrix[replicate,finite]))))
        if not np.array_equal(replayed_effective[replicate],effective_matrix[replicate]):raise AuditFailure(f"bootstrap effective counts {replicate}")
        if not np.array_equal(np.isnan(replayed[replicate]),np.isnan(matrix[replicate])) or not np.allclose(replayed[replicate,finite],matrix[replicate,finite],atol=2e-12,rtol=0):raise AuditFailure(f"bootstrap replay {replicate}")
        if (replicate+1)%100==0:print(f"independent bootstrap replay {replicate+1}/2000",flush=True)
    if digest.hexdigest()!=EXPECTED_DRAW or summary["draw_sequence_sha256"]!=EXPECTED_DRAW:raise AuditFailure("draw digest")
    max_percentile=0.;point_agreement_cache={}
    identity=np.arange(2551,dtype=np.int32);point_indices=np.concatenate([data["cluster_rows"][i] for i in identity]);ones=np.ones(2551,dtype=np.int32)
    for column,key in enumerate(keys):
        point=calculate(key,point_indices,ones,point_agreement_cache);point_effective=effective_count(key,point_indices,ones);cell=summary["metrics"][key];stored=cell["point"]
        expected_cell_fields={"point","ci_95_percentile","finite_resamples","undefined_resamples","undefined_reason","point_effective_n","resample_effective_n_all_min","resample_effective_n_all_max","resample_effective_n_finite_min","resample_effective_n_finite_max"}
        if set(cell)!=expected_cell_fields or set(cell["ci_95_percentile"])!={"lower","upper"}:raise AuditFailure(f"bootstrap cell schema {key}")
        if stored is None:
            if math.isfinite(point):raise AuditFailure(f"bootstrap point {key}")
        elif abs(point-stored)>2e-12:raise AuditFailure(f"bootstrap point {key}")
        finite_mask=np.isfinite(replayed[:,column]);finite=replayed[:,column][finite_mask]
        expected_ci=(float(np.percentile(finite,2.5,method="linear")),float(np.percentile(finite,97.5,method="linear"))) if len(finite)>=1980 else (None,None)
        actual_ci=(cell["ci_95_percentile"]["lower"],cell["ci_95_percentile"]["upper"])
        for a,b in zip(expected_ci,actual_ci,strict=True):
            if a is None:
                if b is not None:raise AuditFailure("CI null")
            else:
                error=abs(a-b);max_percentile=max(max_percentile,error)
                if error>3e-12:raise AuditFailure(f"CI {key}")
        finite_effective=replayed_effective[:,column][finite_mask]
        expected_effective={"point_effective_n":point_effective,"resample_effective_n_all_min":int(replayed_effective[:,column].min()),"resample_effective_n_all_max":int(replayed_effective[:,column].max()),"resample_effective_n_finite_min":int(finite_effective.min()) if len(finite_effective) else None,"resample_effective_n_finite_max":int(finite_effective.max()) if len(finite_effective) else None}
        if any(cell[name]!=value for name,value in expected_effective.items()):raise AuditFailure(f"effective summary {key}")
        if cell["finite_resamples"]!=len(finite) or cell["undefined_resamples"]!=2000-len(finite) or cell["undefined_reason"]!=(None if len(finite)>=1980 else "insufficient_bootstrap_support"):raise AuditFailure(f"bootstrap finite/undefined summary {key}")
    return {"replicates":2000,"metrics":len(keys),"expected_metric_inventory":True,"draw_sequence_sha256":digest.hexdigest(),"maximum_replay_absolute_error":max_error,"replay_absolute_tolerance":2e-12,"maximum_percentile_absolute_error":max_percentile,"percentile_absolute_tolerance":3e-12,"all_effective_matrix_elements_recomputed":True,"all_effective_summary_fields_recomputed":True}


def fmt(value:Any)->str:
    if value is None:return "NA"
    if isinstance(value,(int,np.integer)):return f"{int(value):,}"
    if isinstance(value,(float,np.floating)):return f"{float(value):.6f}"
    return str(value)


def ci_text(cell:Mapping[str,Any])->str:return f"[{fmt(cell['ci_95_percentile'].get('lower'))}, {fmt(cell['ci_95_percentile'].get('upper'))}]"


def regenerate_projections(metrics:Mapping[str,Any],bootstrap:Mapping[str,Any],config:Mapping[str,Any],fit_rows:Sequence[Mapping[str,Any]],destination:Path)->dict[str,str]:
    selections=config["frozen_strongest"]
    candidates=["R_actual","G_raw_bits","G_raw_bits_per_output_byte","C_y_bits","prompt_to_output_byte_ratio","rouge_l_recall",selections["strongest_word_overlap"]["selected"],selections["strongest_char_overlap"]["selected"]]
    lines=["# Table 1. Normalized R_actual versus raw gain and frozen simple heuristics","","All cells pair Spearman rho with `pairwise_continuous_alpha_z`.","","| Candidate | Llama macro rho / alpha_z | Mixtral macro rho / alpha_z | Llama item-centered rho / alpha_z | Mixtral item-centered rho / alpha_z |","|---|---:|---:|---:|---:|"]
    for candidate in dict.fromkeys(candidates):
        cells=[]
        for reference,scope_ in (("phi_actual_llama","macro_within_level"),("phi_actual_mixtral","macro_within_level"),("phi_actual_llama","item_centered"),("phi_actual_mixtral","item_centered")):
            cell=metrics["direct"][candidate][reference][scope_];cells.append(f"{fmt(cell['rho'])} / {fmt(cell[PAIR_ALPHA])}")
        lines.append(f"| {candidate} | "+" | ".join(cells)+" |")
    lines.extend(["","## Direct paired R-minus-baseline bootstrap contrasts","","| Contrast | Reference | Scope | Metric | Point | 95% paired cluster-bootstrap CI |","|---|---|---|---|---:|---:|"])
    for key,cell in sorted(bootstrap["metrics"].items()):
        if key.startswith("direct_delta|"):
            _,contrast,reference,scope_,metric=key.split("|");lines.append(f"| {contrast} | {reference} | {scope_} | {metric} | {fmt(cell['point'])} | {ci_text(cell)} |")
    outputs={"table1_ratio_vs_raw_gain.md":"\n".join(lines)+"\n"}
    lines=["# Table 2. Cross-fitted incremental validity","","Primary rows use source-grouped nested-CV OOF predictions. All agreement cells pair rho with `pairwise_continuous_alpha_z`.","","| Learner | Target | Predictor set | Status | Macro rho / alpha_z | Item-centered rho / alpha_z | OOF R2 / MAE (auxiliary) |","|---|---|---|---|---:|---:|---:|"]
    for key,record in sorted(metrics["incremental_validity"].items()):
        learner,target,predictor=key.split("|",2);macro=record["agreement"]["macro_within_level"];center=record["agreement"]["item_centered"];aux=record["auxiliary"];status="auxiliary frozen strongest-single" if predictor==AUX_SET else "primary";lines.append(f"| {learner} | {target} | {predictor} | {status} | {fmt(macro['rho'])} / {fmt(macro[PAIR_ALPHA])} | {fmt(center['rho'])} / {fmt(center[PAIR_ALPHA])} | {fmt(aux['r2'])} / {fmt(aux['mae'])} |")
    lines.extend(["","## Direct paired OOF contrasts","","| Contrast ID | Point | 95% paired cluster-bootstrap CI |","|---|---:|---:|"])
    for key,cell in sorted(bootstrap["metrics"].items()):
        if key.startswith("incremental_delta|"):lines.append(f"| {key} | {fmt(cell['point'])} | {ci_text(cell)} |")
    outputs["table2_incremental_validity.md"]="\n".join(lines)+"\n"
    ag=metrics["evaluator_sensitivity"]["llama_vs_mixtral"];order=metrics["evaluator_sensitivity"]["ordering"];lines=["# Table 3. White-box evaluator sensitivity and consensus","","| Scope | Spearman rho | pairwise_continuous_alpha_z | N |","|---|---:|---:|---:|"]
    for scope_ in ("pooled","macro_within_level","item_centered"):
        cell=ag[scope_];lines.append(f"| {scope_} | {fmt(cell['rho'])} | {fmt(cell[PAIR_ALPHA])} | {fmt(cell['n'])} |")
    for level,cell in ag["per_level"].items():lines.append(f"| level:{level} | {fmt(cell['rho'])} | {fmt(cell[PAIR_ALPHA])} | {fmt(cell['n'])} |")
    for family in ("by_domain","by_generation_model"):
        for label,cell in ag[family].items():lines.append(f"| {family}:{label} | {fmt(cell['rho'])} | {fmt(cell[PAIR_ALPHA])} | {fmt(cell['n'])} |")
    lines.extend(["","## Exact evaluator ordering","","| Pair | Concordant | Discordant | Tied either | Inversion rate (all / non-tie) | R same-sign on concordant non-ties |","|---|---:|---:|---:|---:|---:|"])
    for family_key in ("all_ten","adjacent_four"):
        for pair_name,cell in order[family_key].items():
            r=cell["R_on_evaluator_concordant_non_tied"];lines.append(f"| {family_key}:{pair_name} | {cell['concordant']:,} | {cell['discordant']:,} | {cell['tied_either_evaluator']:,} | {fmt(cell['inversion_rate_all'])} / {fmt(cell['inversion_rate_non_tie'])} | {fmt(r['same_sign_rate'])} |")
    strict=order["strict_monotonicity"]
    lines.extend(["","## Strict L1>L2>L3>L4>L5 monotonicity","","| Evaluator condition | Strictly monotonic items | Denominator | Rate |","|---|---:|---:|---:|",f"| Llama | {strict['llama_items']:,} | {strict['denominator_items']:,} | {fmt(strict['llama_items']/strict['denominator_items'])} |",f"| Mixtral | {strict['mixtral_items']:,} | {strict['denominator_items']:,} | {fmt(strict['mixtral_items']/strict['denominator_items'])} |",f"| Both | {strict['both_items']:,} | {strict['denominator_items']:,} | {fmt(strict['both_items']/strict['denominator_items'])} |"])
    difference=order["absolute_global_z_difference"];quantiles=difference["quantiles_linear"]
    lines.extend(["","## Standardized evaluator disagreement","",f"Global-z absolute difference: mean={fmt(difference['mean'])}; sample SD={fmt(difference['sd_ddof1'])}. All subgroups reuse the one global z-standardization (`subgroups_use_global_z_not_restandardized={difference['subgroups_use_global_z_not_restandardized']}`).","","Quantiles (`method=linear`): "+", ".join(f"q={key}: {fmt(value)}" for key,value in quantiles.items()),"","| Subgroup | Mean absolute global-z difference |","|---|---:|"])
    for level,value in difference["by_level"].items():lines.append(f"| level:{level} | {fmt(value)} |")
    for domain,value in difference["by_domain"].items():lines.append(f"| domain:{domain} | {fmt(value)} |")
    for model,value in difference["by_generation_model"].items():lines.append(f"| generation_model:{model} | {fmt(value)} |")
    lines.extend(["","## R_actual against the two frozen evaluator consensuses","","| Consensus | Scope | rho | pairwise_continuous_alpha_z |","|---|---|---:|---:|"])
    for reference in ("consensus_midrank_percentile","consensus_global_z"):
        for scope_name in ("macro_within_level","item_centered"):
            cell=metrics["direct"]["R_actual"][reference][scope_name];lines.append(f"| {reference} | {scope_name} | {fmt(cell['rho'])} | {fmt(cell[PAIR_ALPHA])} |")
    outputs["table3_evaluator_sensitivity.md"]="\n".join(lines)+"\n"
    lines=["# Table 4. Cross-fitted length-residualized robustness","","Evaluator comparisons residualize candidate and evaluator independently using the same source-grouped folds. `residual_candidate_vs_raw_treatment_ordinal` instead compares residualized R to the unchanged designed ordinal labels, as frozen; it is not a two-sided partial correlation.","","| Length specification | Candidate vs evaluator | Macro rho / alpha_z | Item-centered rho / alpha_z |","|---|---|---:|---:|"]
    for spec,records in metrics["length_residualized"].items():
        if not spec.startswith("byte_"):continue
        for label,record in records.items():
            macro=record["macro_within_level"];center=record["item_centered"];lines.append(f"| {spec} | {label} | {fmt(macro['rho'])} / {fmt(macro[PAIR_ALPHA])} | {fmt(center['rho'])} / {fmt(center[PAIR_ALPHA])} |")
    lines.extend(["","## Direct paired residual R-minus-raw-gain contrasts","","| Contrast ID | Point | 95% paired cluster-bootstrap CI |","|---|---:|---:|"])
    for key,cell in sorted(bootstrap["metrics"].items()):
        if key.startswith("length_delta|byte_"):lines.append(f"| {key} | {fmt(cell['point'])} | {ci_text(cell)} |")
    lines.extend(["","## Persistence after length control","","| Length specification | Baseline | Classification | Relative to unadjusted |","|---|---|---|---|"])
    for spec,baselines in metrics["outcome_neutral_classification"]["length_R_vs_baselines"].items():
        if not spec.startswith("byte_"):continue
        for baseline,result in baselines.items():lines.append(f"| {spec} | {baseline} | {result['classification']} | {result['relative_to_unadjusted']} |")
    outputs["table4_length_residualized.md"]="\n".join(lines)+"\n"
    sup=metrics["common_support"];lines=["# Table 5. Common output-length support","","Inclusive adjacent-level output-byte calipers are nested by construction.","","| Caliper | Adjacent pair | Method | Retained item-pairs / clusters | Mean / median higher-minus-lower | Mean / median 95% CIs | Expected / reverse / tie rates | Expected / reverse / tie 95% CIs |","|---|---|---|---:|---:|---:|---:|---:|"]
    for caliper,pairs in sup["adjacent_byte_calipers"].items():
        for pair_name,cell in pairs.items():
            for method,result in cell["methods"].items():
                mean_key=f"support|{caliper}|{pair_name}|{method}|mean";median_key=f"support|{caliper}|{pair_name}|{method}|median";expected_key=f"support|{caliper}|{pair_name}|{method}|expected_rate";reverse_key=f"support|{caliper}|{pair_name}|{method}|reverse_rate";tie_key=f"support|{caliper}|{pair_name}|{method}|tie_rate";lines.append(f"| {caliper} | {pair_name} | {method} | {cell['retained_model_item_pairs']:,} / {cell['source_clusters']:,} | {fmt(result['mean_higher_minus_lower'])} / {fmt(result['median_higher_minus_lower'])} | {ci_text(bootstrap['metrics'][mean_key])} / {ci_text(bootstrap['metrics'][median_key])} | {fmt(result['expected_rate'])} / {fmt(result['reverse_rate'])} / {fmt(result['tie_rate'])} | {ci_text(bootstrap['metrics'][expected_key])} / {ci_text(bootstrap['metrics'][reverse_key])} / {ci_text(bootstrap['metrics'][tie_key])} |")
    lines.extend(["","## Retained adjacent-pair treatment concordance","","| Caliper | Method | Scope | rho | pairwise_continuous_alpha_z | rho 95% CI | alpha_z 95% CI |","|---|---|---|---:|---:|---:|---:|"])
    for caliper,methods in sup["adjacent_treatment_concordance"].items():
        for method,scope_records in methods.items():
            for scope_name,cell in scope_records.items():
                rho_key=f"support_treatment|{caliper}|{method}|{scope_name}|rho";alpha_key=f"support_treatment|{caliper}|{method}|{scope_name}|{PAIR_ALPHA}";lines.append(f"| {caliper} | {method} | {scope_name} | {fmt(cell['rho'])} | {fmt(cell[PAIR_ALPHA])} | {ci_text(bootstrap['metrics'][rho_key])} | {ci_text(bootstrap['metrics'][alpha_key])} |")
    af=sup["all_five_byte_1.25"];lines.extend(["",f"All-five 1.25 support: {af['items']:,} items, {af['clusters']:,} clusters; policy = `{af['inference_policy']}`; low-support reasons = {af['low_support_reasons']}.",""])
    if af["inference"] is not None:
        lines.extend(["## All-five 1.25 exploratory inference","","| Method | Scope | rho | pairwise_continuous_alpha_z | N |","|---|---|---:|---:|---:|"])
        for method,scope_records in af["inference"].items():
            for scope_name,cell in scope_records.items():lines.append(f"| {method} | {scope_name} | {fmt(cell['rho'])} | {fmt(cell[PAIR_ALPHA])} | {fmt(cell['n'])} |")
        lines.append("")
    outputs["table5_length_common_support.md"]="\n".join(lines)+"\n"
    lines=["# Appendix: complete subgroup and secondary inventory",""]
    for candidate,references in metrics["direct"].items():
        lines.extend([f"## {candidate}",""])
        for reference,sc in references.items():
            if reference==JOINT_ALPHA:
                lines.append(f"- `{JOINT_ALPHA}`:")
                for joint_scope in ("pooled","macro_within_level","item_centered"):
                    cell=sc[joint_scope];lines.append(f"  - {joint_scope}: {fmt(cell[JOINT_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
                for level,cell in sc["per_level"].items():lines.append(f"  - level:{level}: {fmt(cell[JOINT_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
                for family in ("by_domain","by_generation_model"):
                    for label,cell in sc[family].items():lines.append(f"  - {family}:{label}: {fmt(cell[JOINT_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
                continue
            lines.append(f"### Reference: {reference}")
            lines.append("- per_level:")
            for level,cell in sc["per_level"].items():lines.append(f"  - {level}: rho={fmt(cell['rho'])}; {PAIR_ALPHA}={fmt(cell[PAIR_ALPHA])}; n={cell['n']}; reason={cell.get('undefined_reason')}")
            for family in ("by_domain","by_generation_model"):
                lines.append(f"- {family}:")
                for label,cell in sc[family].items():lines.append(f"  - {label}: rho={fmt(cell['rho'])}; {PAIR_ALPHA}={fmt(cell[PAIR_ALPHA])}; n={cell['n']}")
            if reference=="treatment_ordinal":
                ordinal=sc["per_item_ordinal"];lines.append(f"- per-item ordinal: mean Spearman={fmt(ordinal['mean_per_item_spearman'])}; finite Spearman items={ordinal['finite_spearman_items']}; mean Kendall tau-b={fmt(ordinal['mean_per_item_kendall_tau_b'])}; finite tau-b items={ordinal['finite_tau_b_items']}; strict monotonic={ordinal['strict_monotonic_items']}/{ordinal['items']} ({fmt(ordinal['strict_monotonic_rate'])}); nonstrict monotonic={ordinal['nonstrict_monotonic_items']}/{ordinal['items']} ({fmt(ordinal['nonstrict_monotonic_rate'])})")
            lines.append("")
    lines.extend(["## Compact word-length residualization sensitivity",""])
    classifications=metrics["outcome_neutral_classification"]["length_R_vs_baselines"]
    for spec in ("word_L_out","word_L_full"):
        lines.append(f"### {spec}")
        for baseline,result in classifications[spec].items():
            lines.append(f"- {baseline}: classification={result['classification']}; relative_to_unadjusted={result['relative_to_unadjusted']}")
            for metric_id in result["metric_ids"]:
                cell=bootstrap["metrics"][metric_id];lines.append(f"  - `{metric_id}`: point={fmt(cell['point'])}; CI={ci_text(cell)}")
        lines.append("")
    lines.extend(["## Common-support coverage cells","","```json",json.dumps(metrics["common_support"],ensure_ascii=False,sort_keys=True,indent=2),"```",""]);outputs["appendix_subgroups.md"]="\n".join(lines)
    lines=["# Appendix: nested-CV model fits and coefficients","","This appendix records every outer-fold fit. Ridge entries include the complete inner-alpha score grid, training-only scaler mean/scale, standardized coefficients, intercept, auxiliary test metrics, and exact train/test cluster hashes. HGB entries include the frozen parameters and fold hashes.",""]
    for record in sorted(fit_rows,key=lambda r:(str(r.get("model_label")),int(r.get("outer_fold",-1)))):
        label=str(record["model_label"]);fold=record.get("outer_fold","unavailable");lines.extend([f"## {label} — outer {fold}","","```json",json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2),"```",""])
    outputs["appendix_model_coefficients.md"]="\n".join(lines)
    classification=metrics["outcome_neutral_classification"];ag=metrics["evaluator_sensitivity"]["llama_vs_mixtral"];lines=["# Actual-only 增量与敏感性分析报告","","## 冻结的主要分析","",f"- Llama↔Mixtral 的五层宏平均：Spearman rho={fmt(ag['macro_within_level']['rho'])}，`{PAIR_ALPHA}`={fmt(ag['macro_within_level'][PAIR_ALPHA])}。",f"- Llama↔Mixtral 的item-centered结果：Spearman rho={fmt(ag['item_centered']['rho'])}，`{PAIR_ALPHA}`={fmt(ag['item_centered'][PAIR_ALPHA])}。",f"- Ridge中H+R相对H的冻结分类：`{classification['H+R_vs_H_ridge']['classification']}`。",f"- R相对raw G的总体分类：`{classification['R_vs_G']['overall']}`（white-box convergence：`{classification['R_vs_G']['white_box_convergence']}`；treatment construct：`{classification['R_vs_G']['treatment_construct']}`）。","","## 次要分析","","归一化R、raw gain、冻结heuristics、evaluator ordering、pooled结果和预声明subgroup均完整报告，不按结果筛选。","strongest-single模型明确属于辅助分析，不是六个冻结primary predictor sets之一；其R-only差值也使用同一paired source-cluster bootstrap。","","## 稳健性分析","",f"- 固定HGB中H+R相对H的分类：`{classification['H+R_vs_H_hgb']['classification']}`。","- byte output-only长度残差化是主要稳健性规格；full-byte以及word-length规格是敏感性检查。`residual_candidate_vs_raw_treatment_ordinal`保持treatment labels不变，仅残差化R；它不是双侧partial correlation。",f"- byte L_out下R相对raw G：`{classification['length_R_vs_baselines']['byte_L_out']['G_raw_bits']['classification']}`，相对未调整结论为`{classification['length_R_vs_baselines']['byte_L_out']['G_raw_bits']['relative_to_unadjusted']}`。","","## 探索性分析","",f"- all-five 1.25 common-support推断策略：`{metrics['common_support']['all_five_byte_1.25']['inference_policy']}`。","","## 不支持的主张","","这些结果不建立criterion truth、语义效度、因果效度、普遍优越性，也不代表相对于独立人工标注ground truth的可靠性。L1–L5是investigator-specified ordinal treatment labels。","","本分析未调用API、未联网、未使用GPU、未生成或重生成文本、未读取完整prompt/output正文、未重新压缩、未使用counterfactual字段，也未修改Word。资源约束为`sampled_process_rss_hard_limit`（50 ms采样并在退出时同步复测），不声称捕获采样间隔内所有瞬时峰值。",""];outputs["REPORT_ZH.md"]="\n".join(lines)
    rows=[]
    for candidate,references in metrics["direct"].items():
        for reference,sc in references.items():
            if reference==JOINT_ALPHA:
                for scope_ in ("pooled","macro_within_level","item_centered"):
                    cell=sc[scope_];rows.append({"family":"direct_joint","candidate":candidate,"reference":"llama+mixtral","scope":scope_,"metric":JOINT_ALPHA,"point":cell[JOINT_ALPHA],"ci_lower":None,"ci_upper":None,"n":cell["n"],"finite_resamples":None,"undefined_resamples":None,"undefined_reason":cell.get("undefined_reason")})
                for level,cell in sc["per_level"].items():rows.append({"family":"direct_joint","candidate":candidate,"reference":"llama+mixtral","scope":f"level:{level}","metric":JOINT_ALPHA,"point":cell[JOINT_ALPHA],"ci_lower":None,"ci_upper":None,"n":cell["n"],"finite_resamples":None,"undefined_resamples":None,"undefined_reason":cell.get("undefined_reason")})
                for family in ("by_domain","by_generation_model"):
                    for label,cell in sc[family].items():rows.append({"family":"direct_joint","candidate":candidate,"reference":"llama+mixtral","scope":f"{family}:{label}","metric":JOINT_ALPHA,"point":cell[JOINT_ALPHA],"ci_lower":None,"ci_upper":None,"n":cell["n"],"finite_resamples":None,"undefined_resamples":None,"undefined_reason":cell.get("undefined_reason")})
                continue
            for scope_ in ("pooled","macro_within_level","item_centered"):
                cell=sc[scope_]
                for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"direct","candidate":candidate,"reference":reference,"scope":scope_,"metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
            for level,cell in sc["per_level"].items():
                for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"direct","candidate":candidate,"reference":reference,"scope":f"level:{level}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
            for subgroup_family in ("by_domain","by_generation_model"):
                for subgroup,cell in sc[subgroup_family].items():
                    for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"direct","candidate":candidate,"reference":reference,"scope":f"{subgroup_family}:{subgroup}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
            if reference=="treatment_ordinal":
                ordinal=sc["per_item_ordinal"]
                for metric_name in ("mean_per_item_spearman","finite_spearman_items","mean_per_item_kendall_tau_b","finite_tau_b_items","strict_monotonic_items","strict_monotonic_rate","nonstrict_monotonic_items","nonstrict_monotonic_rate"):
                    rows.append({"family":"treatment_per_item_ordinal","candidate":candidate,"reference":reference,"scope":"per_item_ordinal","metric":metric_name,"point":ordinal[metric_name],"ci_lower":None,"ci_upper":None,"n":ordinal["items"],"undefined_reason":None})
    for model_id,record in metrics["incremental_validity"].items():
        for scope_ in ("pooled","macro_within_level","item_centered"):
            cell=record["agreement"][scope_]
            for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"incremental_validity","candidate":model_id,"reference":model_id.split("|")[1],"scope":scope_,"metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
        for level,cell in record["agreement"]["per_level"].items():
            for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"incremental_validity","candidate":model_id,"reference":model_id.split("|")[1],"scope":f"level:{level}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
        for subgroup_family in ("by_domain","by_generation_model"):
            for subgroup,cell in record["agreement"][subgroup_family].items():
                for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"incremental_validity","candidate":model_id,"reference":model_id.split("|")[1],"scope":f"{subgroup_family}:{subgroup}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
        for metric_name in ("r2","mae"):rows.append({"family":"incremental_auxiliary","candidate":model_id,"reference":model_id.split("|")[1],"scope":"pooled","metric":metric_name,"point":record["auxiliary"][metric_name],"ci_lower":None,"ci_upper":None,"n":metrics["coverage"]["pairs"],"undefined_reason":None})
    evaluator=metrics["evaluator_sensitivity"]["llama_vs_mixtral"]
    for scope_ in ("pooled","macro_within_level","item_centered"):
        for metric_name in ("rho",PAIR_ALPHA):
            cell=evaluator[scope_];rows.append({"family":"evaluator_sensitivity","candidate":"phi_actual_llama","reference":"phi_actual_mixtral","scope":scope_,"metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
    for level,cell in evaluator["per_level"].items():
        for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"evaluator_sensitivity","candidate":"phi_actual_llama","reference":"phi_actual_mixtral","scope":f"level:{level}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
    for subgroup_family in ("by_domain","by_generation_model"):
        for subgroup,cell in evaluator[subgroup_family].items():
            for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"evaluator_sensitivity","candidate":"phi_actual_llama","reference":"phi_actual_mixtral","scope":f"{subgroup_family}:{subgroup}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
    for spec,comparisons in metrics["length_residualized"].items():
        for comparison,scope_records in comparisons.items():
            for scope_ in ("pooled","macro_within_level","item_centered"):
                cell=scope_records[scope_]
                for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"length_residualized","candidate":f"{spec}|{comparison}","reference":None,"scope":scope_,"metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
    for caliper,methods in metrics["common_support"]["adjacent_treatment_concordance"].items():
        for method,scope_records in methods.items():
            for scope_,cell in scope_records.items():
                for metric_name in ("rho",PAIR_ALPHA):rows.append({"family":"common_support_treatment","candidate":method,"reference":"treatment_ordinal","scope":f"{caliper}|{scope_}","metric":metric_name,"point":cell[metric_name],"ci_lower":None,"ci_upper":None,"n":cell["n"],"undefined_reason":cell.get("undefined_reason")})
    for key,cell in bootstrap["metrics"].items():
        ci=cell["ci_95_percentile"];rows.append({"family":"bootstrap_contrast","candidate":key,"reference":None,"scope":None,"metric":"paired_difference","point":cell["point"],"ci_lower":ci["lower"],"ci_upper":ci["upper"],"n":cell["point_effective_n"],"finite_resamples":cell["finite_resamples"],"undefined_resamples":cell["undefined_resamples"],"resample_effective_n_all_min":cell["resample_effective_n_all_min"],"resample_effective_n_all_max":cell["resample_effective_n_all_max"],"resample_effective_n_finite_min":cell["resample_effective_n_finite_min"],"resample_effective_n_finite_max":cell["resample_effective_n_finite_max"],"undefined_reason":cell.get("undefined_reason")})
    csv_path=destination/"metrics.csv";fields=["family","candidate","reference","scope","metric","point","ci_lower","ci_upper","n","finite_resamples","undefined_resamples","resample_effective_n_all_min","resample_effective_n_all_max","resample_effective_n_finite_min","resample_effective_n_finite_max","undefined_reason"]
    with csv_path.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator="\n");writer.writeheader();writer.writerows(rows)
    for name,text in outputs.items():(destination/name).write_text(text,encoding="utf-8",newline="")
    outputs["metrics.csv"]=""
    return {name:sha_file(destination/name) for name in sorted(outputs)}


def audit_checkpoints(config_sha:str,data:Mapping[str,Any],outer:Mapping[tuple[str,str,str],int],predictions:Mapping[str,np.ndarray],residuals:Mapping[str,np.ndarray],fit_rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    index=load(HERE/"checkpoint_index.json");self_hash(index)
    if set(index)!={"schema","schema_version","config_sha256","oof","bootstrap","payload_sha256_excluding_this_field"} or index["schema"]!="actual_incremental_sensitivity.checkpoint_index" or index["schema_version"]!=1 or index["config_sha256"]!=config_sha:raise AuditFailure("checkpoint index exact schema/config")
    indexed={}
    for family in ("oof","bootstrap"):
        records=index[family]
        if not isinstance(records,list) or records!=sorted(records,key=lambda record:record["path"]):raise AuditFailure("checkpoint index order")
        for record in records:
            if not isinstance(record,dict) or set(record)!={"path","sha256","size"} or record["path"] in indexed:raise AuditFailure("checkpoint index record")
            relative=record["path"]
            if not isinstance(relative,str) or Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative:raise AuditFailure("checkpoint index unsafe path")
            path=HERE/relative;digest,size=fingerprint(path)
            if size!=record["size"] or digest!=record["sha256"]:raise AuditFailure(f"checkpoint hash {path}")
            indexed[relative]=family
    labels=expected_prediction_keys(hgb_import_available())
    expected_models={f"checkpoints/oof/model_{hashlib.sha256(label.encode('utf-8')).hexdigest()[:24]}_outer_{fold}.npz":(label,fold) for label in labels for fold in range(5)}
    expected_aggregates={f"checkpoints/oof/outer_{fold}.npz":fold for fold in range(5)}
    expected_oof={*expected_models,*expected_aggregates}
    expected_boot={f"checkpoints/bootstrap/block_{start:04d}_{start+25:04d}.npz":(start,start+25) for start in range(0,2000,25)}
    actual_oof={path.relative_to(HERE).as_posix() for path in (HERE/"checkpoints"/"oof").glob("*.npz")};actual_boot={path.relative_to(HERE).as_posix() for path in (HERE/"checkpoints"/"bootstrap").glob("*.npz")}
    if actual_oof!=expected_oof or actual_boot!=set(expected_boot):raise AuditFailure(f"checkpoint exact path inventory differs; missing_oof={len(expected_oof-actual_oof)}, unknown_oof={len(actual_oof-expected_oof)}, missing_boot={len(set(expected_boot)-actual_boot)}, unknown_boot={len(actual_boot-set(expected_boot))}")
    if {record["path"] for record in index["oof"]}!=expected_oof or {record["path"] for record in index["bootstrap"]}!=set(expected_boot):raise AuditFailure("checkpoint index logical inventory differs")
    row_outer=np.asarray([outer[data["clusters"][int(index_)]] for index_ in data["cluster_index"]],dtype=np.int8);aggregate_keys=sorted([*predictions,*(f"residual|{key}" for key in residuals)]);checkpoint_fit_rows=[record for record in fit_rows if int(record.get("outer_fold",-1))>=0];fit_lookup={(record["model_label"],int(record["outer_fold"])):record for record in checkpoint_fit_rows}
    if len(fit_lookup)!=len(checkpoint_fit_rows) or set(fit_lookup)!={(label,fold) for label in labels for fold in range(5)}:raise AuditFailure("checkpoint fit-record logical inventory")
    seen_models=set();seen_aggregates=set()
    for relative in sorted(expected_oof):
        path=HERE/relative
        with open_plain(path) as handle:
            with np.load(handle,allow_pickle=False) as stored:
                metadata=loads(str(stored["metadata_json"].item()),"oof metadata");arrays={name:np.asarray(stored[name]) for name in stored.files if name!="metadata_json"}
        if metadata.get("config_sha256")!=config_sha or metadata.get("arrays")!=checkpoint_descriptor(arrays) or metadata.get("payload_sha256")!=checkpoint_payload(arrays):raise AuditFailure("OOF checkpoint metadata/payload")
        require_deterministic_npz(path,arrays,metadata)
        if relative in expected_models:
            label,fold=expected_models[relative];expected_rows=np.flatnonzero(row_outer==fold).astype(np.int32);metadata_fields={"schema","schema_version","config_sha256","model_label","outer_fold","metric_key_sha256","row_count","arrays","payload_sha256"}
            if set(metadata)!=metadata_fields or metadata["schema"]!="actual_incremental_sensitivity.model_oof_checkpoint" or metadata["schema_version"]!=1 or metadata["model_label"]!=label or metadata["outer_fold"]!=fold or metadata["row_count"]!=len(expected_rows):raise AuditFailure("model checkpoint exact metadata/path binding")
            if set(arrays)!={"keys","rows","values","fit_json"}:raise AuditFailure("model block arrays")
            if arrays["keys"].dtype.kind!="U" or arrays["keys"].shape!=(1,) or arrays["rows"].dtype!=np.dtype("int32") or arrays["values"].dtype!=np.dtype("float64") or arrays["values"].shape!=(len(expected_rows),) or arrays["fit_json"].dtype.kind!="U" or arrays["fit_json"].shape!=() or arrays["keys"].tolist()!=[label] or metadata["metric_key_sha256"]!=sha_bytes(canonical([label])) or not np.array_equal(arrays["rows"],expected_rows) or not np.array_equal(arrays["values"],predictions[label][expected_rows]):raise AuditFailure("model block key/row/value")
            fit=loads(str(arrays["fit_json"].item()),"model block fit")
            if fit!=fit_lookup[(label,fold)]:raise AuditFailure("model block fit binding")
            logical=(label,fold)
            if logical in seen_models:raise AuditFailure("duplicate model checkpoint logical key")
            seen_models.add(logical)
        else:
            fold=expected_aggregates[relative];expected_rows=np.flatnonzero(row_outer==fold).astype(np.int32);metadata_fields={"schema","schema_version","config_sha256","outer_fold","metric_key_sha256","row_count","arrays","payload_sha256"}
            if set(metadata)!=metadata_fields or metadata["schema"]!="actual_incremental_sensitivity.oof_checkpoint" or metadata["schema_version"]!=1 or metadata["outer_fold"]!=fold or metadata["row_count"]!=len(expected_rows):raise AuditFailure("aggregate checkpoint exact metadata/path binding")
            if set(arrays)!={"keys","rows","values"}:raise AuditFailure("aggregate OOF arrays")
            expected_matrix=np.column_stack([predictions[key][expected_rows] if key in predictions else residuals[key.removeprefix("residual|")][expected_rows] for key in aggregate_keys])
            if arrays["keys"].dtype.kind!="U" or arrays["keys"].shape!=(len(aggregate_keys),) or arrays["rows"].dtype!=np.dtype("int32") or arrays["keys"].tolist()!=aggregate_keys or metadata["metric_key_sha256"]!=sha_bytes(canonical(aggregate_keys)) or not np.array_equal(arrays["rows"],expected_rows) or arrays["values"].dtype!=np.dtype("float64") or arrays["values"].shape!=expected_matrix.shape or not np.array_equal(arrays["values"],expected_matrix):raise AuditFailure("aggregate OOF block key/row/value")
            if fold in seen_aggregates:raise AuditFailure("duplicate aggregate checkpoint fold")
            seen_aggregates.add(fold)
    boot_keys=list(load(HERE/"bootstrap_summary.json")["metric_keys"]);boot_key_sha=sha_bytes(canonical(boot_keys))
    for relative,(start,end) in sorted(expected_boot.items()):
        path=HERE/relative
        with open_plain(path) as handle:
            with np.load(handle,allow_pickle=False) as stored:
                if set(stored.files)!={"values","effective","keys","metadata_json"}:raise AuditFailure("bootstrap checkpoint arrays")
                metadata=loads(str(stored["metadata_json"].item()),"bootstrap metadata");arrays={name:np.asarray(stored[name]) for name in ("values","effective","keys")}
        expected_metadata={"schema":"actual_incremental_sensitivity.bootstrap_checkpoint","schema_version":1,"config_sha256":config_sha,"metric_key_sha256":boot_key_sha,"replicate_start_inclusive":start,"replicate_end_exclusive":end,"arrays":checkpoint_descriptor(arrays),"payload_sha256":checkpoint_payload(arrays)}
        if metadata!=expected_metadata or arrays["keys"].tolist()!=boot_keys or arrays["keys"].dtype.kind!="U" or arrays["keys"].shape!=(len(boot_keys),) or arrays["values"].dtype!=np.dtype("float64") or arrays["effective"].dtype!=np.dtype("int32") or arrays["values"].shape!=(25,len(boot_keys)) or arrays["effective"].shape!=arrays["values"].shape:raise AuditFailure("bootstrap checkpoint exact metadata/path binding")
        require_deterministic_npz(path,arrays,metadata)
    if seen_models!={(label,fold) for label in labels for fold in range(5)} or seen_aggregates!=set(range(5)):raise AuditFailure("checkpoint logical coverage")
    return {"model_outer_blocks":len(seen_models),"aggregate_outer_blocks":len(seen_aggregates),"bootstrap_blocks":len(expected_boot),"exact_inventory":True,"all_hashes_keys_rows_dtypes_shapes_and_payloads_valid":True,"all_oof_checkpoint_values_match_ledger":True}


def ast_independence()->dict[str,Any]:
    tree=ast.parse(read_plain_bytes(SCRIPT_UNRESOLVED).decode("utf-8",errors="strict"));imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom):imports.append(node.module or "")
    forbidden=[name for name in imports if name in {"analysis_core","run_analysis"} or name.endswith(".analysis_core") or name.endswith(".run_analysis")]
    if forbidden:raise AuditFailure(f"auditor forbidden imports {forbidden}")
    production={}
    for name in ("analysis_core.py","run_analysis.py"):
        p=HERE/name;tree=ast.parse(read_plain_bytes(p).decode("utf-8",errors="strict"));bad=[]
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ""]
                bad.extend(x for x in names if x.split(".")[0] in {"requests","httpx","urllib","socket","openai","anthropic","torch"})
        if bad:raise AuditFailure(f"forbidden production import {name}: {bad}")
        production[name]="pass"
    return {"auditor_imports_production":False,"production_forbidden_import_scan":production}


def scan_forbidden_structured(metrics:Mapping[str,Any],bootstrap:Mapping[str,Any],fit_rows:Sequence[Mapping[str,Any]],oof_fields:Sequence[str])->dict[str,Any]:
    findings=[];identifier_fields={"path","schema","family","candidate","reference","scope","metric","model_label","feature_names","metric_keys","direct_candidates","predictor","target","comparison","estimand"}
    def check(text:str,path:str)->None:
        normalized=text.casefold().replace("-","_")
        for token in FORBIDDEN_IDENTIFIER_TOKENS:
            if token in normalized:findings.append(f"{path}:{token}")
    def visit(value:Any,path:str,scan_string:bool=False)->None:
        if isinstance(value,dict):
            for key,child in value.items():check(str(key),f"{path}.<key>");visit(child,f"{path}.{key}",str(key) in identifier_fields)
        elif isinstance(value,list):
            for index,child in enumerate(value):visit(child,f"{path}[{index}]",scan_string)
        elif scan_string and isinstance(value,str):check(value,path)
    visit(metrics,"metrics");visit(bootstrap,"bootstrap");visit(list(fit_rows),"model_fits")
    for field in oof_fields:check(field,"oof")
    with io.StringIO(read_plain_bytes(HERE/"metrics.csv").decode("utf-8",errors="strict"),newline="") as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames!="family candidate reference scope metric point ci_lower ci_upper n finite_resamples undefined_resamples resample_effective_n_all_min resample_effective_n_all_max resample_effective_n_finite_min resample_effective_n_finite_max undefined_reason".split():raise AuditFailure("metrics CSV schema")
        for row_number,row in enumerate(reader,2):
            for field in ("family","candidate","reference","scope","metric"):check(row[field] or "",f"metrics.csv:{row_number}.{field}")
    import re
    for name in (*TABLE_FILES,"appendix_subgroups.md","appendix_model_coefficients.md","REPORT_ZH.md"):
        text=read_plain_bytes(HERE/name).decode("utf-8",errors="strict");candidates=re.findall(r"`([^`]+)`",text)
        for line in text.splitlines():
            if line.startswith("|"):candidates.extend(cell.strip() for cell in line.strip("|").split("|"))
        for value in candidates:check(value,name)
    if findings:raise AuditFailure(f"forbidden structured labels: {findings[:20]}")
    return {"passed":True,"forbidden_identifier_occurrences":0,"structured_artifacts_scanned":["metrics.json","bootstrap_summary.json","model_fits.jsonl","oof_predictions.jsonl","metrics.csv",*TABLE_FILES,"appendix_subgroups.md","appendix_model_coefficients.md","REPORT_ZH.md"],"narrative_prose_excluded_by_design":True}


def rebuild_classification(bootstrap:Mapping[str,Any])->dict[str,Any]:
    records=bootstrap["metrics"]
    def classify(keys:Sequence[str])->str:
        cells=[records[key] for key in keys if key in records]
        if len(cells)!=len(keys):return "skipped_unavailable"
        bounds=[(cell["ci_95_percentile"]["lower"],cell["ci_95_percentile"]["upper"]) for cell in cells]
        if all(lower is not None and lower>0 for lower,_ in bounds):return "stable_positive"
        if all(upper is not None and upper<0 for _,upper in bounds):return "stable_negative"
        return "mixed_or_inconclusive"
    out={}
    for learner in ("ridge","hgb"):
        keys=[f"incremental_delta|{learner}|{target}|H+R-minus-H|{scope_}|{metric}" for target in TARGETS for scope_ in ("macro_within_level","item_centered") for metric in ("rho",PAIR_ALPHA)]
        out[f"H+R_vs_H_{learner}"]={"classification":classify(keys),"required_cells":8,"available_cells":sum(key in records for key in keys),"metric_ids":keys}
    white=[f"direct_delta|R_actual-minus-G_raw_bits|{reference}|{scope_}|{metric}" for reference in ("llama","mixtral") for scope_ in ("macro_within_level","item_centered") for metric in ("rho",PAIR_ALPHA)]
    treatment_keys=[f"direct_delta|R_actual-minus-G_raw_bits|treatment|{scope_}|{metric}" for scope_ in ("pooled","item_centered") for metric in ("rho",PAIR_ALPHA)]
    wc=classify(white);tc=classify(treatment_keys);out["R_vs_G"]={"white_box_convergence":wc,"treatment_construct":tc,"overall":wc if wc==tc and wc in {"stable_positive","stable_negative"} else "mixed_or_inconclusive","white_box_metric_ids":white,"treatment_metric_ids":treatment_keys}
    length_results={}
    for spec in LENGTH_SPECS:
        length_results[spec]={}
        for baseline in ("G_raw_bits","G_raw_bits_per_output_byte"):
            keys=[f"length_delta|{spec}|{target}|R_actual-minus-{baseline}|{scope_}|{metric}" for target in TARGETS for scope_ in ("macro_within_level","item_centered") for metric in ("rho",PAIR_ALPHA)];category=classify(keys)
            direct_category=wc if baseline=="G_raw_bits" else classify([f"direct_delta|R_actual-minus-{baseline}|{reference}|{scope_}|{metric}" for reference in ("llama","mixtral") for scope_ in ("macro_within_level","item_centered") for metric in ("rho",PAIR_ALPHA)])
            if category==direct_category and category in {"stable_positive","stable_negative"}:persistence="persists"
            elif category in {"stable_positive","stable_negative"} and direct_category in {"stable_positive","stable_negative"} and category!=direct_category:persistence="reverses"
            elif direct_category in {"stable_positive","stable_negative"}:persistence="attenuates_or_disappears"
            else:persistence="inconclusive_primary_baseline"
            length_results[spec][baseline]={"classification":category,"relative_to_unadjusted":persistence,"unadjusted_classification":direct_category,"metric_ids":keys}
    out["length_R_vs_baselines"]=length_results
    return out


def derive_strongest()->dict[str,Any]:
    metrics=load(AUTHORITY/"metrics.json");records=metrics.get("records")
    if not isinstance(records,dict):raise AuditFailure("authority selection records absent")
    sets={"strongest_word_overlap":("word_type_coverage","word_token_coverage","word_bigram_coverage"),"strongest_char_overlap":("char3_coverage","char5_coverage","char8_coverage"),"strongest_single_heuristic":HEURISTICS};answer={}
    for label,candidates in sets.items():
        inspected=[]
        for order,candidate in enumerate(candidates):
            metric_id=f"direct|{candidate}|macro_within_level|rho";record=records.get(metric_id)
            if not isinstance(record,dict):raise AuditFailure(f"selection record absent {metric_id}")
            point=finite(record.get("point"),metric_id);inspected.append({"candidate":candidate,"declared_order":order,"metric_id":metric_id,"point":point})
        winner=max(inspected,key=lambda item:(item["point"],-item["declared_order"]));answer[label]={"criterion":"largest signed point estimate","tie_break":"earlier declared candidate order","candidates":inspected,"selected":winner["candidate"],"selected_metric_id":winner["metric_id"],"selected_point":winner["point"]}
    if {key:value["selected"] for key,value in answer.items()}!={"strongest_word_overlap":"word_token_coverage","strongest_char_overlap":"char5_coverage","strongest_single_heuristic":"rouge_l_recall"}:raise AuditFailure("authority-derived strongest selections")
    return answer


def expected_run_config(authority_receipt:Mapping[str,Any],folds:Mapping[str,Any],selections:Mapping[str,Any])->dict[str,Any]:
    code=[]
    for name in sorted(("analysis_core.py","audit_analysis.py","run_analysis.py","test_analysis.py")):
        path=HERE/name;digest,size=fingerprint(path);code.append({"path":name,"sha256":digest,"size":size})
    base={
        "schema":"actual_incremental_sensitivity.run_config","schema_version":1,"state":"frozen_before_formal_statistics","bundle_id":BUNDLE_ID,"created_at_utc":"2026-09-11T17:23:19Z","estimand":"aggregate R_actual on real prompt-output pairs only","authority":dict(authority_receipt),
        "coverage":{"pairs":56110,"items":11222,"source_clusters":2551,"levels":list(LEVELS)},
        "keys":{"model_item":["generation_model","NFC/lower(domain)","NFC(id)"],"pair":["generation_model","NFC/lower(domain)","NFC(id)","level"],"source_cluster":["source_cluster_domain","source_cluster_id","source_cluster_fingerprint"]},
        "raw_algebra":{"C_y_bits":"output_self_bits_per_byte * output_bytes","G_raw_bits":"R_actual * C_y_bits","D_conditional_bits":"C_y_bits - G_raw_bits; audit only","G_raw_bits_per_output_byte":"G_raw_bits / output_bytes","rtol":"64*float64_eps","atol":"64*float64_eps"},
        "direct_candidates":list(DIRECT),"frozen_strongest":dict(selections),
        "folds":{"outer":5,"inner":5,"outer_seed":20260824,"inner_master_seed":20260825,"outer_assignment_sha256":folds["outer_assignment_sha256"],"fold_plan_payload_sha256":folds["payload_sha256_excluding_this_field"]},
        "learners":{"ridge":{"scaler":"StandardScaler fit only on current training fold","fit_intercept":True,"solver":"svd","alphas":list(ALPHAS),"selection":"concatenated inner-holdout row-weighted MSE; within 1e-12+1e-10*abs(best), choose larger alpha"},"hist_gradient_boosting":{"loss":"squared_error","learning_rate":.05,"max_iter":200,"max_leaf_nodes":15,"max_depth":None,"min_samples_leaf":50,"l2_regularization":1.,"max_bins":255,"early_stopping":False,"random_state":20260826,"tuning":False}},
        "predictor_sets":{"primary_sets":list(SETS),"L":["p","o","p^2","p*o","o^2"],"O":list(OVERLAP),"H":list(HEURISTICS),"H_log1p":sorted(LOG_H),"H+R":["H","R_actual"],"R-only":["R_actual"],"G-only":["G_raw_bits"],"auxiliary_strongest_single":{"set_name":AUX_SET,"status":"auxiliary_not_one_of_six_primary_sets","feature":selections["strongest_single_heuristic"]["selected"],"selection_source":selections["strongest_single_heuristic"]["selected_metric_id"]},"white_box_predictors_forbidden":True},
        "length_residualization":{"targets":list(LENGTH_TARGETS),"specifications":list(LENGTH_SPECS),"byte_L_out":["o","o^2","o^3"],"byte_L_full":["p","o","p^2","p*o","o^2"],"word_L_out":["w","w^2","w^3"],"word_L_full":["pw","ow","pw^2","pw*ow","ow^2"],"treatment_estimand":"residual_candidate_vs_raw_treatment_ordinal; not two-sided partial correlation"},
        "consensus":{"primary":"equal mean of evaluator global average-midrank percentiles (rank-.5)/N","sensitivity":"equal mean of evaluator global sample-z scores ddof=1","constructed_once_globally":True,"joint_reference_statistic":JOINT_ALPHA},
        "agreement":{"rank":"Spearman rho with average midranks","primary_alpha":PAIR_ALPHA,"alpha_protocol":"independent sample-z ddof=1 then exact interval Krippendorff alpha O(m)","primary_scopes":["macro_within_level","item_centered"],"treatment_labels":{level:int(value) for level,value in LEVEL_VALUE.items()},"constant_columns":"undefined_with_reason_not_zero"},
        "evaluator_sensitivity":{"difference":"abs(global-z llama - global-z mixtral)","quantiles":[0.,.1,.25,.5,.75,.9,.95,.99,1.],"level_pairs":[list(pair_) for pair_ in ALL_PAIRS],"adjacent_pairs":[list(pair_) for pair_ in ADJACENT],"strict_monotonicity":"L1>L2>L3>L4>L5"},
        "common_support":{"adjacent_output_byte_ratio_calipers":[1.1,1.2,1.3],"inclusive":True,"all_five_caliper":1.25,"low_support":{"items_less_than":1123,"clusters_less_than":256,"any_domain_absent":True,"any_model_absent":True}},
        "bootstrap":{"replicates":2000,"seed":20260823,"block_size":25,"cluster_count":2551,"draw_sequence_sha256":EXPECTED_DRAW,"percentiles":[2.5,97.5],"method":"linear","minimum_finite_replicates":1980,"conditional_on_frozen_cross_fitted_predictions":True,"refit_inside_bootstrap":False},
        "classification":{"stable_positive":"all predeclared paired CI lower bounds > 0","stable_negative":"all predeclared paired CI upper bounds < 0","otherwise":"mixed_or_inconclusive"},
        "resources":{"single_process":True,"blas_openmp_threads":1,"rss_target_bytes":RSS_TARGET,"rss_hard_limit_bytes":RSS_HARD_LIMIT,"rss_limit_semantics":"sampled_process_rss_hard_limit","rss_sampling_interval_milliseconds":50,"synchronous_exit_rss_sample":True,"gpu":False,"network":False},
        "prohibitions":{"api_calls":0,"model_generation":False,"network":False,"gpu":False,"text_regeneration":False,"recompression":False,"prompt_or_output_text_reads":0,"counterfactual_fields":False,"authority_modified":False,"word_modified":False},
        "code_snapshot":{"files":code,"inventory_sha256":sha_bytes(canonical(code))},
    }
    return {**base,"config_payload_sha256_excluding_this_field":sha_bytes(canonical(base))}


def validate_config(config:Mapping[str,Any],authority_receipt:Mapping[str,Any],folds:Mapping[str,Any],selections:Mapping[str,Any])->None:
    expected=expected_run_config(authority_receipt,folds,selections)
    if config!=expected:raise AuditFailure("run_config differs from complete independent reconstruction")


def validate_prepared_receipts(data:Mapping[str,Any],config_sha:str)->None:
    derived,derived_sha,_=load_record(HERE/"derived_features_receipt.json");prepare,_,_=load_record(HERE/"prepare_receipt.json");_,folds_sha,_=load_record(HERE/"fold_assignments.json");self_hash(derived);self_hash(prepare)
    v=data["values"];conditional=v["D_conditional_bits_audit_only"];ratio_error=np.abs(v["G_raw_bits"]/v["C_y_bits"]-v["R_actual"])
    algebra={"formulae":{"C_y_bits":"output_self_bits_per_byte * output_bytes","G_raw_bits":"R_actual * C_y_bits","D_conditional_bits_audit_only":"C_y_bits - G_raw_bits","G_raw_bits_per_output_byte":"G_raw_bits / output_bytes"},"rows":data["n"],"all_output_bytes_positive":bool(np.all(v["output_bytes"]>0)),"all_C_y_bits_positive":bool(np.all(v["C_y_bits"]>0)),"all_R_actual_in_unit_interval":bool(np.all((v["R_actual"]>=0)&(v["R_actual"]<=1))),"all_G_raw_bits_nonnegative":bool(np.all(v["G_raw_bits"]>=0)),"minimum_D_conditional_bits":float(conditional.min()),"maximum_ratio_reconstruction_absolute_error":float(ratio_error.max()),"float_tolerance":"64*float64_eps with rowwise max scale; np.isclose rtol=atol=64*eps","array_sha256":{name:array_sha(v[name]) for name in ("C_y_bits","G_raw_bits","D_conditional_bits_audit_only","G_raw_bits_per_output_byte")},"D_conditional_role":"audit_only_not_baseline","redundant_1_minus_R_or_D_over_C_constructed":False}
    derived_base={"schema":"actual_incremental_sensitivity.derived_features_receipt","schema_version":1,"state":"complete","config_sha256":config_sha,"authority_ledger_sha256":EXPECTED_LEDGER,"pair_set_sha256":EXPECTED_PAIR_SET,"coverage":{"pairs":56110,"items":11222,"source_clusters":2551},"raw_algebra":algebra,"consensus":{"primary_array_sha256":array_sha(v["consensus_midrank_percentile"]),"sensitivity_array_sha256":array_sha(v["consensus_global_z"]),"llama_global_z_array_sha256":array_sha(v["phi_actual_llama_global_z"]),"mixtral_global_z_array_sha256":array_sha(v["phi_actual_mixtral_global_z"]),"constructed_once_over_rows":56110},"forbidden_derived_fields_constructed":False,"prompt_output_text_reads":0,"recompression_operations":0};expected_derived={**derived_base,"payload_sha256_excluding_this_field":sha_bytes(canonical(derived_base))}
    if derived!=expected_derived:raise AuditFailure("derived_features_receipt differs from complete independent reconstruction")
    expected_artifacts={"run_config.json":config_sha,"fold_assignments.json":folds_sha,"derived_features_receipt.json":derived_sha}
    prepare_fields={"schema","schema_version","state","bundle_id","artifacts","authority_manifest_sha256","ledger_sha256","pair_set_sha256","bootstrap_draw_sequence_sha256","elapsed_seconds","resources","formal_statistics_started","external_api_calls","network_access","gpu","model_generation","recompression","prompt_output_text_reads","payload_sha256_excluding_this_field"}
    static={"schema":"actual_incremental_sensitivity.prepare_receipt","schema_version":1,"state":"prepared","bundle_id":BUNDLE_ID,"artifacts":expected_artifacts,"authority_manifest_sha256":EXPECTED_MANIFEST,"ledger_sha256":EXPECTED_LEDGER,"pair_set_sha256":EXPECTED_PAIR_SET,"bootstrap_draw_sequence_sha256":EXPECTED_DRAW,"formal_statistics_started":False,"external_api_calls":0,"network_access":False,"gpu":False,"model_generation":False,"recompression":False,"prompt_output_text_reads":0}
    if set(prepare)!=prepare_fields or any(prepare.get(key)!=value for key,value in static.items()):raise AuditFailure("prepare receipt static field differs")
    elapsed=prepare["elapsed_seconds"];resources=prepare["resources"]
    if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or not math.isfinite(float(elapsed)) or elapsed<0:raise AuditFailure("prepare elapsed")
    validate_resources(resources,"prepare")


def file_record(path:Path)->dict[str,Any]:
    digest,size=fingerprint(path);return {"path":path.relative_to(HERE).as_posix(),"sha256":digest,"size":size}


def validate_completion(config_sha:str,*,expect_audit:bool)->dict[str,Any]:
    completion,completion_sha,_=load_record(HERE/"scientific_completion.json");expected_keys={"schema","schema_version","state","bundle_id","config_sha256","authority_ledger_sha256","checkpoint_index_sha256","artifacts","artifact_inventory_sha256","code_snapshot","payload_sha256_excluding_this_field"}
    if set(completion)!=expected_keys:raise AuditFailure("scientific completion exact schema")
    self_hash(completion)
    if completion["schema"]!="actual_incremental_sensitivity.scientific_completion" or completion["schema_version"]!=1 or completion["state"]!="complete_pending_independent_audit" or completion["bundle_id"]!=BUNDLE_ID or completion["config_sha256"]!=config_sha or completion["authority_ledger_sha256"]!=EXPECTED_LEDGER:raise AuditFailure("scientific completion identity/binding")
    checkpoint,checkpoint_sha,_=load_record(HERE/"checkpoint_index.json");self_hash(checkpoint)
    if completion["checkpoint_index_sha256"]!=checkpoint_sha:raise AuditFailure("completion checkpoint binding")
    artifacts=completion["artifacts"]
    if [entry.get("path") for entry in artifacts]!=sorted(FORMAL_SCIENTIFIC_FILES) or completion["artifact_inventory_sha256"]!=sha_bytes(canonical(artifacts)):raise AuditFailure("completion artifact inventory")
    for entry in artifacts:
        if set(entry)!={"path","sha256","size"}:raise AuditFailure("completion artifact record")
        path=HERE/entry["path"];digest,size=fingerprint(path)
        if size!=entry["size"] or digest!=entry["sha256"]:raise AuditFailure(f"scientific artifact drift {entry['path']}")
    code=[file_record(HERE/name) for name in sorted(("analysis_core.py","audit_analysis.py","run_analysis.py","test_analysis.py"))]
    if completion["code_snapshot"]!={"files":code,"inventory_sha256":sha_bytes(canonical(code))}:raise AuditFailure("completion code snapshot")
    execution,execution_sha,execution_size=load_record(HERE/"execution.json");self_hash(execution);execution_entry=next((entry for entry in artifacts if entry["path"]=="execution.json"),None)
    if execution_entry is None or (execution_sha,execution_size)!=(execution_entry["sha256"],execution_entry["size"]):raise AuditFailure("execution parse/artifact binding")
    execution_fields={"schema","schema_version","state","config_sha256","elapsed_seconds","environment","resources","external_api_calls","network_access","gpu","model_generation","text_regeneration","recompression","prompt_output_text_reads","counterfactual_fields_used","authority_modified","word_modified","payload_sha256_excluding_this_field"}
    if set(execution)!=execution_fields or execution["schema"]!="actual_incremental_sensitivity.execution" or execution["schema_version"]!=1 or execution["state"]!="scientific_outputs_complete" or execution["config_sha256"]!=config_sha or any((execution["external_api_calls"]!=0,execution["network_access"] is not False,execution["gpu"] is not False,execution["model_generation"] is not False,execution["text_regeneration"] is not False,execution["recompression"] is not False,execution["prompt_output_text_reads"]!=0,execution["counterfactual_fields_used"] is not False,execution["authority_modified"] is not False,execution["word_modified"] is not False)):raise AuditFailure("execution receipt exact schema/claims")
    if finite(execution["elapsed_seconds"],"execution elapsed")<0 or execution["environment"]!=expected_environment():raise AuditFailure("execution timing/environment")
    validate_resources(execution["resources"],"execution")
    self_hash(checkpoint)
    if set(checkpoint)!={"schema","schema_version","config_sha256","oof","bootstrap","payload_sha256_excluding_this_field"} or checkpoint["schema"]!="actual_incremental_sensitivity.checkpoint_index" or checkpoint["schema_version"]!=1 or checkpoint["config_sha256"]!=config_sha:raise AuditFailure("checkpoint index exact schema")
    checkpoint_paths={record["path"] for family in ("oof","bootstrap") for record in checkpoint[family]}
    expected={"analysis_core.py","audit_analysis.py","run_analysis.py","test_analysis.py","RUNBOOK.md",*FORMAL_SCIENTIFIC_FILES,"scientific_completion.json",*checkpoint_paths}
    if expect_audit:expected.add("audit.json")
    if (HERE/"manifest.json").exists():expected.add("manifest.json")
    actual=set(plain_files(HERE,ALLOWED_DIRECTORIES))
    if actual!=expected:raise AuditFailure(f"formal recursive inventory differs; missing={sorted(expected-actual)}, unknown={sorted(actual-expected)}")
    return completion


class AuditResourceMonitor:
    def __init__(self)->None:
        self.baseline=0;self.peak=0;self.phase="initial";self.phase_peaks={};self.backend="unknown";self._stop=threading.Event();self._failure=threading.Event();self._thread=None;self._heap_current=0;self._heap_peak=0;self._closed=False
    def _rss(self)->int:
        try:
            import psutil
            self.backend="psutil";return int(psutil.Process().memory_info().rss)
        except ImportError:
            if os.name!="nt":return 0
            import ctypes
            from ctypes import wintypes
            class PMC(ctypes.Structure):_fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD),("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t)]
            counters=PMC();counters.cb=ctypes.sizeof(counters);handle=ctypes.windll.kernel32.GetCurrentProcess()
            if not ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):return 0
            self.backend="win32_ctypes";return int(counters.WorkingSetSize)
    def _sample(self)->None:
        rss=self._rss();self.peak=max(self.peak,rss);self.phase_peaks[self.phase]=max(self.phase_peaks.get(self.phase,0),rss)
        if rss>RSS_HARD_LIMIT:self._failure.set()
    def _run(self)->None:
        while not self._stop.wait(.05):self._sample()
    def __enter__(self)->"AuditResourceMonitor":
        self.baseline=self._rss();self.peak=self.baseline;tracemalloc.start();self._thread=threading.Thread(target=self._run,daemon=True);self._thread.start();return self
    def set_phase(self,phase:str)->None:self.check();self.phase=phase
    def check(self)->None:
        if self._failure.is_set():raise AuditFailure("audit RSS hard limit exceeded")
    def __exit__(self,exc_type:Any,exc:Any,tb:Any)->None:
        self._stop.set();self._thread.join(timeout=1.0)
        if self._thread.is_alive():self._failure.set()
        self._sample();self._heap_current,self._heap_peak=tracemalloc.get_traced_memory();tracemalloc.stop();self._closed=True
        if self._failure.is_set():raise AuditFailure("audit RSS hard limit exceeded")
    def receipt(self)->dict[str,Any]:
        if not self._closed:raise AuditFailure("audit resource receipt before close")
        return {"rss_backend":self.backend,"rss_baseline_bytes":self.baseline,"rss_peak_bytes":self.peak,"rss_incremental_peak_bytes":max(0,self.peak-self.baseline),"phase_rss_peaks_bytes":dict(sorted(self.phase_peaks.items())),"tracemalloc_current_bytes":self._heap_current,"tracemalloc_peak_bytes":self._heap_peak,"rss_target_bytes":RSS_TARGET,"rss_hard_limit_bytes":RSS_HARD_LIMIT,"rss_limit_semantics":"sampled_process_rss_hard_limit","rss_sampling_interval_milliseconds":50,"synchronous_exit_rss_sample":True}


def validate_existing_audit(completion:Mapping[str,Any],config_sha:str,authority_receipt:Mapping[str,Any])->dict[str,Any]:
    audit,audit_sha,_=load_record(HERE/"audit.json");_,completion_sha,_=load_record(HERE/"scientific_completion.json");expected={"schema","schema_version","state","bundle_id","config_sha256","scientific_completion_sha256","scientific_artifact_inventory_sha256","authority","coverage","auditor_independence","folds","raw_algebra","models","point_statistics","bootstrap","checkpoints","projection_byte_comparison","structured_output_scan","resources","execution","payload_sha256_excluding_this_field"}
    if set(audit)!=expected:raise AuditFailure("audit exact schema")
    self_hash(audit)
    if audit["schema"]!="actual_incremental_sensitivity.independent_audit" or audit["schema_version"]!=1 or audit["state"]!="pass" or audit["bundle_id"]!=BUNDLE_ID or audit["config_sha256"]!=config_sha or audit["scientific_completion_sha256"]!=completion_sha or audit["scientific_artifact_inventory_sha256"]!=completion["artifact_inventory_sha256"]:raise AuditFailure("audit identity/binding")
    if audit["authority"]!=authority_receipt or audit["coverage"]!={"pairs":56110,"items":11222,"clusters":2551}:raise AuditFailure("audit authority/coverage")
    if audit["auditor_independence"]!={"auditor_imports_production":False,"production_forbidden_import_scan":{"analysis_core.py":"pass","run_analysis.py":"pass"}} or audit["folds"]!={"independently_rebuilt":True,"full_row_permutation_invariant":True,"zero_cluster_leakage":True,"all_cluster_counts_and_inner_outer_cells_recomputed":True} or audit["raw_algebra"]!={"independently_rebuilt":True,"ratio_identity_exact_within_frozen_tolerance":True}:raise AuditFailure("audit mandatory pass claims")
    models=audit["models"];expected_hgb=70 if hgb_import_available() else 0
    model_fields={"ridge_outer_models_refit","hgb_outer_models_refit","hgb_import_available","exact_model_inventory","all_model_fit_metadata_recomputed","maximum_prediction_absolute_error","maximum_prediction_tolerance_ratio","maximum_model_fit_metadata_absolute_error","maximum_model_fit_metadata_allowed_absolute_error","prediction_atol","prediction_rtol","fit_metadata_tolerance"}
    if set(models)!=model_fields or models["ridge_outer_models_refit"]!=170 or models["hgb_outer_models_refit"]!=expected_hgb or models["hgb_import_available"] is not hgb_import_available() or models["exact_model_inventory"] is not True or models["all_model_fit_metadata_recomputed"] is not True or models["prediction_atol"]!=1e-12 or models["prediction_rtol"]!=1e-10 or models["fit_metadata_tolerance"]!=1e-10 or models["maximum_model_fit_metadata_allowed_absolute_error"]!=1e-10:raise AuditFailure("audit model claims")
    for key in ("maximum_prediction_absolute_error","maximum_prediction_tolerance_ratio","maximum_model_fit_metadata_absolute_error"):finite(models[key],f"audit models {key}")
    if any(models[key]<0 for key in ("maximum_prediction_absolute_error","maximum_prediction_tolerance_ratio","maximum_model_fit_metadata_absolute_error")) or models["maximum_prediction_tolerance_ratio"]>1.0 or models["maximum_model_fit_metadata_absolute_error"]>models["maximum_model_fit_metadata_allowed_absolute_error"]:raise AuditFailure("audit model error bounds")
    point=audit["point_statistics"]
    if set(point)!={"all_recomputed","maximum_absolute_error","tolerance"} or point["all_recomputed"] is not True or point["tolerance"]!=2e-12 or finite(point["maximum_absolute_error"],"audit point error")<0 or point["maximum_absolute_error"]>point["tolerance"]:raise AuditFailure("audit point claims")
    replay=audit["bootstrap"]
    replay_fields={"replicates","metrics","expected_metric_inventory","draw_sequence_sha256","maximum_replay_absolute_error","replay_absolute_tolerance","maximum_percentile_absolute_error","percentile_absolute_tolerance","all_effective_matrix_elements_recomputed","all_effective_summary_fields_recomputed"}
    if set(replay)!=replay_fields or replay["replicates"]!=2000 or replay["metrics"]!=(552 if hgb_import_available() else 512) or replay["expected_metric_inventory"] is not True or replay["draw_sequence_sha256"]!=EXPECTED_DRAW or replay["replay_absolute_tolerance"]!=2e-12 or replay["percentile_absolute_tolerance"]!=3e-12 or replay["all_effective_matrix_elements_recomputed"] is not True or replay["all_effective_summary_fields_recomputed"] is not True:raise AuditFailure("audit bootstrap claims")
    if finite(replay["maximum_replay_absolute_error"],"audit replay error")<0 or replay["maximum_replay_absolute_error"]>replay["replay_absolute_tolerance"] or finite(replay["maximum_percentile_absolute_error"],"audit percentile error")<0 or replay["maximum_percentile_absolute_error"]>replay["percentile_absolute_tolerance"]:raise AuditFailure("audit bootstrap error bounds")
    checkpoints=audit["checkpoints"]
    if checkpoints!={"model_outer_blocks":240 if hgb_import_available() else 170,"aggregate_outer_blocks":5,"bootstrap_blocks":80,"exact_inventory":True,"all_hashes_keys_rows_dtypes_shapes_and_payloads_valid":True,"all_oof_checkpoint_values_match_ledger":True}:raise AuditFailure("audit checkpoint claims")
    expected_scan={"passed":True,"forbidden_identifier_occurrences":0,"structured_artifacts_scanned":["metrics.json","bootstrap_summary.json","model_fits.jsonl","oof_predictions.jsonl","metrics.csv",*TABLE_FILES,"appendix_subgroups.md","appendix_model_coefficients.md","REPORT_ZH.md"],"narrative_prose_excluded_by_design":True}
    if audit["projection_byte_comparison"]!={name:True for name in sorted(PROJECTION_FILES)} or audit["structured_output_scan"]!=expected_scan:raise AuditFailure("audit projection/scan claims")
    validate_resources(audit["resources"],"audit")
    execution=audit["execution"];execution_fields={"elapsed_seconds","external_api_calls","network_access","gpu","model_generation","text_regeneration","recompression","prompt_output_text_reads","counterfactual_fields_used","authority_modified","word_modified"}
    if set(execution)!=execution_fields or finite(execution["elapsed_seconds"],"audit execution elapsed")<0 or any((execution["external_api_calls"]!=0,execution["network_access"] is not False,execution["gpu"] is not False,execution["model_generation"] is not False,execution["text_regeneration"] is not False,execution["recompression"] is not False,execution["prompt_output_text_reads"]!=0,execution["counterfactual_fields_used"] is not False,execution["authority_modified"] is not False,execution["word_modified"] is not False)):raise AuditFailure("audit execution claims")
    return audit


def validate_manifest(config_sha:str)->None:
    path=HERE/"manifest.json"
    if not path.exists():return
    manifest,manifest_sha,_=load_record(path);expected={"schema","schema_version","state","bundle_id","created_at_utc","authority_bundle_id","authority_manifest_sha256","ledger_sha256","pair_set_sha256","config_sha256","scientific_completion_sha256","audit_sha256","artifacts","artifact_inventory_sha256","claims","manifest_payload_sha256_excluding_this_field"}
    if set(manifest)!=expected:raise AuditFailure("manifest exact schema")
    self_hash(manifest,"manifest_payload_sha256_excluding_this_field")
    expected_claims={"external_api_calls":0,"network_access":False,"gpu":False,"model_generation":False,"recompression":False,"prompt_output_text_reads":0,"counterfactual_fields_used":False,"authority_modified":False,"word_modified":False}
    if manifest["schema"]!="actual_incremental_sensitivity.manifest" or manifest["schema_version"]!=1 or manifest["state"]!="complete" or manifest["bundle_id"]!=BUNDLE_ID or manifest["created_at_utc"]!="2026-09-11T17:23:19Z" or manifest["authority_bundle_id"]!=f"{MIGRATION}_actual_heuristic_20260911T035818Z_v1" or manifest["authority_manifest_sha256"]!=EXPECTED_MANIFEST or manifest["ledger_sha256"]!=EXPECTED_LEDGER or manifest["pair_set_sha256"]!=EXPECTED_PAIR_SET or manifest["config_sha256"]!=config_sha or manifest["scientific_completion_sha256"]!=sha_file(HERE/"scientific_completion.json") or manifest["audit_sha256"]!=sha_file(HERE/"audit.json") or manifest["claims"]!=expected_claims:raise AuditFailure("manifest frozen binding")
    artifacts=manifest["artifacts"]
    if manifest["artifact_inventory_sha256"]!=sha_bytes(canonical(artifacts)):raise AuditFailure("manifest inventory digest")
    declared=[]
    for entry in artifacts:
        if not isinstance(entry,dict) or set(entry)!={"path","sha256","size"}:raise AuditFailure("manifest record")
        relative=entry["path"]
        if not isinstance(relative,str) or Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative:raise AuditFailure("manifest unsafe path")
        target=HERE/relative;digest,size=fingerprint(target)
        if size!=entry["size"] or digest!=entry["sha256"]:raise AuditFailure(f"manifest artifact {relative}")
        declared.append(relative)
    if sorted([*declared,"manifest.json"])!=plain_files(HERE,ALLOWED_DIRECTORIES):raise AuditFailure("manifest recursive inventory")


def validate_recomputed_audit_evidence(existing:Mapping[str,Any],rebuilt:Mapping[str,Any])->None:
    fields=("authority","coverage","auditor_independence","folds","raw_algebra","models","point_statistics","bootstrap","checkpoints","projection_byte_comparison","structured_output_scan")
    for field in fields:
        if existing.get(field)!=rebuilt.get(field):raise AuditFailure(f"existing audit differs from full fresh recomputation: {field}")


def main()->None:
    validate_root_path();start=time.perf_counter();existing_audit=None
    with AuditResourceMonitor() as monitor:
        monitor.set_phase("authority_config_and_folds")
        authority_receipt=verify_authority();data=read_ledger();outer,inners,fold_receipt=independent_folds(data);selections=derive_strongest()
        config,config_sha,_=load_record(HERE/"run_config.json");validate_config(config,authority_receipt,fold_receipt,selections);validate_prepared_receipts(data,config_sha)
        audit_exists=lexists(HERE/"audit.json")
        completion=validate_completion(config_sha,expect_audit=audit_exists)
        if audit_exists:
            existing_audit=validate_existing_audit(completion,config_sha,authority_receipt);validate_manifest(config_sha)
        monitor.set_phase("independence_and_oof")
        independence=ast_independence();predictions,residuals=read_oof(data,outer);fit_rows=read_fit_records()
        monitor.set_phase("independent_model_refits")
        refit=refit_all(data,outer,inners,predictions,residuals,fit_rows,selections["strongest_single_heuristic"]["selected"])
        monitor.set_phase("point_statistics")
        rebuilt=rebuilt_metrics(data,predictions,residuals);stored=load(HERE/"metrics.json");self_hash(stored)
        expected_metric_fields={"schema","schema_version","estimand","coverage","metric_namespaces","direct","incremental_validity","evaluator_sensitivity","length_residualized","common_support","treatment_terminology","scientific_limits","bootstrap_summary_sha256","outcome_neutral_classification","config_sha256","payload_sha256_excluding_this_field"}
        if set(stored)!=expected_metric_fields or stored["config_sha256"]!=config_sha or stored["bootstrap_summary_sha256"]!=sha_file(HERE/"bootstrap_summary.json"):raise AuditFailure("metrics exact schema/bindings")
        compare_target={key:value for key,value in stored.items() if key not in {"bootstrap_summary_sha256","outcome_neutral_classification","config_sha256","payload_sha256_excluding_this_field"}}
        point_error=compare_recursive(rebuilt,compare_target,tolerance=2e-12)
        monitor.set_phase("bootstrap_replay")
        bootstrap=load(HERE/"bootstrap_summary.json");replay=bootstrap_replay(data,predictions,residuals,bootstrap,config,config_sha)
        rebuilt_classification=rebuild_classification(bootstrap)
        if rebuilt_classification!=stored["outcome_neutral_classification"]:raise AuditFailure("outcome-neutral classification differs")
        monitor.set_phase("checkpoint_validation")
        checkpoints=audit_checkpoints(config_sha,data,outer,predictions,residuals,fit_rows)
        monitor.set_phase("projection_rebuild")
        with tempfile.TemporaryDirectory(prefix="actual-sensitivity-audit-") as directory:
            regenerated=regenerate_projections(stored,bootstrap,config,fit_rows,Path(directory));byte_compare={}
            for name,digest in regenerated.items():
                actual=sha_file(HERE/name);byte_compare[name]=actual==digest
                if actual!=digest:raise AuditFailure(f"projection differs {name}")
        oof_fields=[*(f"prediction|{key}" for key in predictions),*(f"residual|{key}" for key in residuals)]
        structured=scan_forbidden_structured(stored,bootstrap,fit_rows,oof_fields)
        monitor.check()
    resources=monitor.receipt()
    receipt_base={"schema":"actual_incremental_sensitivity.independent_audit","schema_version":1,"state":"pass","bundle_id":BUNDLE_ID,"config_sha256":config_sha,"scientific_completion_sha256":sha_file(HERE/"scientific_completion.json"),"scientific_artifact_inventory_sha256":completion["artifact_inventory_sha256"],"authority":authority_receipt,"coverage":{"pairs":data["n"],"items":data["items"],"clusters":len(data["clusters"])},"auditor_independence":independence,"folds":{"independently_rebuilt":True,"full_row_permutation_invariant":True,"zero_cluster_leakage":True,"all_cluster_counts_and_inner_outer_cells_recomputed":True},"raw_algebra":{"independently_rebuilt":True,"ratio_identity_exact_within_frozen_tolerance":True},"models":refit,"point_statistics":{"all_recomputed":True,"maximum_absolute_error":point_error,"tolerance":2e-12},"bootstrap":replay,"checkpoints":checkpoints,"projection_byte_comparison":byte_compare,"structured_output_scan":structured,"resources":resources,"execution":{"elapsed_seconds":time.perf_counter()-start,"external_api_calls":0,"network_access":False,"gpu":False,"model_generation":False,"text_regeneration":False,"recompression":False,"prompt_output_text_reads":0,"counterfactual_fields_used":False,"authority_modified":False,"word_modified":False}}
    if existing_audit is not None:
        validate_recomputed_audit_evidence(existing_audit,receipt_base)
        print("independent audit existing PASS; full refits/replay/checkpoints/projections revalidated; no-op",flush=True);return
    receipt={**receipt_base,"payload_sha256_excluding_this_field":sha_bytes(canonical(receipt_base))};payload=canonical(receipt,True);path=HERE/"audit.json"
    write_immutable(path,payload)
    validate_completion(config_sha,expect_audit=True);validate_existing_audit(completion,config_sha,authority_receipt)
    print(f"independent audit PASS -> {path}",flush=True)


if __name__=="__main__":
    failure_path=PARENT/f".{BUNDLE_ID}.independent-audit.FAILED.json"
    try:
        main()
    except Exception as exc:
        base={"schema":"actual_incremental_sensitivity.failure","schema_version":1,"state":"failed","bundle_id":BUNDLE_ID,"command":"independent-audit","recorded_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"exception_type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc(),"staging_path":str(HERE),"final_published":(PARENT/BUNDLE_ID).exists()};receipt={**base,"payload_sha256_excluding_this_field":sha_bytes(canonical(base))};temporary=failure_path.with_name(f".{failure_path.name}.{os.getpid()}.tmp")
        with temporary.open("wb") as handle:handle.write(canonical(receipt,True));handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,failure_path)
        raise
    else:
        if lexists(failure_path):
            prior=load(failure_path);self_hash(prior)
            if prior.get("command")=="independent-audit":failure_path.unlink()
