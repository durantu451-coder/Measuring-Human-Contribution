#!/usr/bin/env python3
"""Frozen-data core for the actual-only incremental/sensitivity analysis.

This module never reads prompt/output text, calls a network API, invokes a GPU,
or recomputes compression.  Its only scientific row source is the independently
audited numeric ledger in the completed actual-heuristic authority bundle.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import stat
import sys
import tempfile
import threading
import time
import tracemalloc
import unicodedata
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import numpy as np
from scipy.stats import kendalltau, rankdata


class AnalysisError(RuntimeError):
    """Fail-closed analysis error."""


class AuthorityError(AnalysisError):
    """The immutable authority differs from its declared state."""


class CoverageError(AnalysisError):
    """The fixed cohort or grouping contract is not exact."""


class ResourceLimitError(AnalysisError):
    """The process exceeded the frozen memory ceiling."""


LEVELS = ("L1", "L2", "L3", "L4", "L5")
LEVEL_VALUE = {"L1": 5.0, "L2": 4.0, "L3": 3.0, "L4": 2.0, "L5": 1.0}
ADJACENT_LEVEL_PAIRS = (("L1", "L2"), ("L2", "L3"), ("L3", "L4"), ("L4", "L5"))
ALL_LEVEL_PAIRS = tuple((LEVELS[i], LEVELS[j]) for i in range(5) for j in range(i + 1, 5))
HEURISTICS = (
    "prompt_bytes", "output_bytes", "prompt_words", "output_words",
    "prompt_to_output_byte_ratio", "word_type_coverage", "word_token_coverage",
    "word_bigram_coverage", "char3_coverage", "char5_coverage", "char8_coverage",
    "rouge_l_recall", "output_type_token_ratio", "output_bigram_repeat_fraction",
    "output_self_bits_per_byte",
)
LOG_HEURISTICS = {
    "prompt_bytes", "output_bytes", "prompt_words", "output_words",
    "prompt_to_output_byte_ratio",
}
OVERLAP_FEATURES = (
    "rouge_l_recall", "word_type_coverage", "word_token_coverage",
    "word_bigram_coverage", "char3_coverage", "char5_coverage", "char8_coverage",
)
NUMERIC_FIELDS = ("blackbox_actual_ratio", *HEURISTICS, "phi_actual_llama", "phi_actual_mixtral")
IDENTITY_FIELDS = (
    "generation_model", "domain", "id", "level", "scoring_input_sha256",
    "prompt_sha256", "output_sha256", "source_cluster_domain",
    "source_cluster_id", "source_cluster_fingerprint",
)
LEDGER_FIELDS = frozenset((*IDENTITY_FIELDS, *NUMERIC_FIELDS))
DIRECT_CANDIDATES = (
    "R_actual", "G_raw_bits", "G_raw_bits_per_output_byte", "C_y_bits", *HEURISTICS,
)
WHITEBOX_TARGETS = ("phi_actual_llama", "phi_actual_mixtral")
PREDICTOR_SETS = ("L", "O", "H", "H+R", "R-only", "G-only")
AUXILIARY_PREDICTOR_SET = "AUX-strongest-single"
LENGTH_SPECS = ("byte_L_out", "byte_L_full", "word_L_out", "word_L_full")
LENGTH_TARGETS = (
    "R_actual", "G_raw_bits", "G_raw_bits_per_output_byte",
    "phi_actual_llama", "phi_actual_mixtral",
)
RIDGE_ALPHAS = tuple(float(10.0 ** exponent) for exponent in range(-6, 7))
OUTER_SEED = 20260824
INNER_MASTER_SEED = 20260825
HGB_RANDOM_STATE = 20260826
BOOTSTRAP_SEED = 20260823
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_BLOCK_SIZE = 25
EXPECTED_DRAW_SHA256 = "f53da5c8fe317a3f3acbea472c5f35f6fdaba29c0d7284aefc18638e07566521"
EXPECTED_PAIRS = 56110
EXPECTED_ITEMS = 11222
EXPECTED_CLUSTERS = 2551
EXPECTED_LEDGER_SHA256 = "dbe012c59802518dea1ddb3a6b694f9446bf56fbc920578c3aae7df6ba9ec776"
EXPECTED_PAIR_SET_SHA256 = "02f9e08550b32ae6693676c3b71ab535c7a87b06a93f061587ddf10569a80037"
EXPECTED_AUTHORITY_MANIFEST_SHA256 = "30938906b58abc6dbaaddad72002d53915f20e50e6ea8d358e7d315002cf4e6a"
EXPECTED_AUTHORITY_METRICS_SHA256 = "894ef996c466a86920e1cf69af67d3bd53dec2a9e6defc411a9e6e09a9cf295e"
EXPECTED_AUTHORITY_AUDIT_SHA256 = "06d525867220f5ff5f57388e96b019434352a0da534c12a459af4d36e85a4e0d"
EXPECTED_AUTHORITY_COMPLETION_SHA256 = "c9a887fc8e794bc9686877753bfa954baa78eda2ca93682c38b9a391b2e7a8d6"
EXPECTED_MODEL_ITEMS = {
    "claude-opus-4-8": 1892, "claude-sonnet-5": 2320,
    "gemini-3.6-flash": 2240, "gpt-5.5": 2446, "gpt-5.6-sol": 2324,
}
EXPECTED_DOMAIN_ITEMS = {"arxiv": 2937, "news": 2856, "patent": 2760, "poetry": 2669}
PAIRWISE_ALPHA = "pairwise_continuous_alpha_z"
JOINT_ALPHA = "joint_reference_continuous_alpha_z"
RSS_HARD_LIMIT = 1610612736
RSS_TARGET = 1073741824
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
FORBIDDEN_IDENTIFIER_TOKENS = (
    "excess", "cf_baseline", "counterfactual_score", "1_minus_r", "d_over_c",
    "derived_score",
)
CHECKPOINT_SCHEMAS = frozenset({
    "actual_incremental_sensitivity.model_oof_checkpoint",
    "actual_incremental_sensitivity.oof_checkpoint",
    "actual_incremental_sensitivity.bootstrap_checkpoint",
})


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: bytes | str, label: str = "JSON") -> Any:
    try:
        text = raw.decode("utf-8", errors="strict") if isinstance(raw, bytes) else raw
        return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AnalysisError(f"{label}: invalid strict JSON: {exc}") from exc


def strict_json_load(path: str | Path) -> Any:
    return strict_json_load_record(path)[0]


def strict_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if not math.isfinite(result):
            raise AnalysisError("attempted to serialize non-finite number")
        return result
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise AnalysisError(f"non-string JSON key: {key!r}")
            out[key] = strict_json_value(child)
        return out
    if isinstance(value, (list, tuple)):
        return [strict_json_value(child) for child in value]
    raise AnalysisError(f"unsupported strict JSON type: {type(value).__name__}")


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    payload = json.dumps(
        strict_json_value(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def path_lexists(path: str | Path) -> bool:
    return os.path.lexists(os.fspath(path))


def is_reparse_or_link(path: str | Path) -> bool:
    target = Path(path)
    if not path_lexists(target):
        return False
    info = target.lstat()
    is_junction = getattr(target, "is_junction", None)
    junction = bool(is_junction()) if callable(is_junction) else False
    return bool(target.is_symlink() or junction or int(getattr(info, "st_file_attributes", 0)) & 0x400)


def _plain_component_snapshot(path: str | Path, *, include_leaf: bool = True) -> list[tuple[Path, os.stat_result]]:
    unresolved = Path(os.path.abspath(os.fspath(path)))
    target = unresolved if include_leaf else unresolved.parent
    parts = target.parts
    if not parts:
        raise AnalysisError(f"empty path rejected: {unresolved}")
    components = [Path(parts[0])]
    for part in parts[1:]:
        components.append(components[-1] / part)
    snapshot: list[tuple[Path, os.stat_result]] = []
    for current in components:
        if not path_lexists(current):
            raise AnalysisError(f"path component does not exist: {current}")
        info = current.lstat()
        if is_reparse_or_link(current):
            raise AnalysisError(f"symlink/junction/reparse path component rejected: {current}")
        if current != target and not stat.S_ISDIR(info.st_mode):
            raise AnalysisError(f"non-directory path component rejected: {current}")
        snapshot.append((current, info))
    return snapshot


def verify_plain_component_snapshot(snapshot: Sequence[tuple[Path, os.stat_result]]) -> None:
    for path, expected in snapshot:
        if not path_lexists(path) or is_reparse_or_link(path):
            raise AnalysisError(f"path component changed or became reparse: {path}")
        actual = path.lstat()
        if not _same_open_file(expected, actual):
            raise AnalysisError(f"path component identity changed: {path}")


def require_plain_components(path: str | Path, *, include_leaf: bool = True) -> Path:
    """Reject a reparse/symlink or non-directory in every existing path component."""
    unresolved = Path(os.path.abspath(os.fspath(path)))
    _plain_component_snapshot(unresolved, include_leaf=include_leaf)
    return unresolved


def _same_open_file(left: os.stat_result, right: os.stat_result) -> bool:
    try:
        return bool(os.path.samestat(left, right))
    except (AttributeError, OSError):
        return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


@contextmanager
def open_plain_binary(path: str | Path) -> Iterator[Any]:
    """Open one ordinary file and fail if its path or identity changes while read."""
    unresolved = Path(os.path.abspath(os.fspath(path)))
    component_snapshot = _plain_component_snapshot(unresolved)
    before = unresolved.lstat()
    if not stat.S_ISREG(before.st_mode) or is_reparse_or_link(unresolved):
        raise AnalysisError(f"non-plain file rejected: {unresolved}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(unresolved, flags)
    except OSError as exc:
        raise AnalysisError(f"unable to open plain file: {unresolved}: {exc}") from exc
    handle = os.fdopen(descriptor, "rb", closefd=True)
    try:
        opened = os.fstat(handle.fileno())
        verify_plain_component_snapshot(component_snapshot)
        after_open = unresolved.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or is_reparse_or_link(unresolved)
            or not _same_open_file(before, opened)
            or not _same_open_file(after_open, opened)
        ):
            raise AnalysisError(f"file identity changed while opening: {unresolved}")
        yield handle
        after_read = os.fstat(handle.fileno())
        verify_plain_component_snapshot(component_snapshot)
        after_path = unresolved.lstat()
        if (
            not _same_open_file(opened, after_read)
            or not _same_open_file(after_path, after_read)
            or after_read.st_size != opened.st_size
            or after_read.st_mtime_ns != opened.st_mtime_ns
            or is_reparse_or_link(unresolved)
        ):
            raise AnalysisError(f"file identity/content changed while reading: {unresolved}")
    finally:
        handle.close()


def read_plain_bytes(path: str | Path) -> bytes:
    with open_plain_binary(path) as handle:
        return handle.read()


def strict_json_load_record(path: str | Path) -> tuple[Any, str, int]:
    """Parse strict JSON and hash/count exactly the same protected bytes."""
    target = Path(path)
    digest = hashlib.sha256(); chunks: list[bytes] = []; size = 0
    with open_plain_binary(target) as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block); chunks.append(block); size += len(block)
    return strict_json_loads(b"".join(chunks), str(target)), digest.hexdigest(), size


def file_fingerprint(path: str | Path, block_size: int = 8 * 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    with open_plain_binary(path) as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
        size = os.fstat(handle.fileno()).st_size
    return digest.hexdigest(), int(size)


def sha256_file(path: str | Path, block_size: int = 8 * 1024 * 1024) -> str:
    return file_fingerprint(path, block_size)[0]


def require_plain_directory(path: str | Path, *, parent: str | Path | None = None) -> Path:
    """Validate every unresolved component before returning its canonical path."""
    unresolved = require_plain_components(path)
    info = unresolved.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise AnalysisError(f"not a directory: {unresolved}")
    resolved = unresolved.resolve(strict=True)
    if parent is not None:
        parent_unresolved = require_plain_components(parent)
        parent_info = parent_unresolved.lstat()
        if not stat.S_ISDIR(parent_info.st_mode):
            raise AnalysisError(f"not a parent directory: {parent_unresolved}")
        parent_resolved = parent_unresolved.resolve(strict=True)
        if resolved.parent != parent_resolved:
            raise AnalysisError(f"directory escapes required parent: {unresolved}")
    return resolved


def require_absent_or_plain_directory(path: str | Path, *, parent: str | Path) -> Path:
    unresolved = Path(os.path.abspath(os.fspath(path)))
    parent_resolved = require_plain_directory(parent)
    require_plain_components(unresolved, include_leaf=False)
    if unresolved.parent.resolve(strict=True) != parent_resolved:
        raise AnalysisError(f"destination escapes required parent: {unresolved}")
    if path_lexists(unresolved):
        return require_plain_directory(unresolved, parent=parent)
    return unresolved


def publish_directory_no_replace(source: str | Path, destination: str | Path) -> None:
    """Atomically rename a directory while refusing a concurrently-created target."""
    source_path = Path(os.path.abspath(os.fspath(source)))
    destination_path = Path(os.path.abspath(os.fspath(destination)))
    require_plain_directory(source_path)
    require_plain_directory(destination_path.parent)
    source_snapshot = _plain_component_snapshot(source_path)
    parent_snapshot = _plain_component_snapshot(destination_path.parent)
    if path_lexists(destination_path):
        raise AnalysisError(f"publication destination already exists: {destination_path}")
    verify_plain_component_snapshot(source_snapshot); verify_plain_component_snapshot(parent_snapshot)
    if os.name == "nt":
        try:
            os.rename(source_path, destination_path)
        except FileExistsError as exc:
            raise AnalysisError(f"publication destination raced into existence: {destination_path}") from exc
    elif sys.platform.startswith("linux"):
        import ctypes
        import errno
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise AnalysisError("atomic no-replace directory publication unavailable")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            -100, os.fsencode(source_path), -100, os.fsencode(destination_path), 1,
        )
        if result != 0:
            code = ctypes.get_errno()
            if code in (errno.EEXIST, errno.ENOTEMPTY):
                raise AnalysisError(f"publication destination raced into existence: {destination_path}")
            raise AnalysisError(f"atomic no-replace publication failed: errno={code}")
    else:
        raise AnalysisError("atomic no-replace directory publication unavailable on this platform")
    require_plain_directory(destination_path, parent=destination_path.parent)


def file_record(path: str | Path, root: str | Path | None = None) -> dict[str, Any]:
    target = Path(path)
    name = target.name if root is None else target.relative_to(Path(root)).as_posix()
    digest, size = file_fingerprint(target)
    return {"path": name, "sha256": digest, "size": size}


def payload_with_hash(payload: Mapping[str, Any], field: str = "payload_sha256_excluding_this_field") -> dict[str, Any]:
    base = dict(payload)
    if field in base:
        raise AnalysisError(f"self-hash field already present: {field}")
    return {**base, field: sha256_bytes(canonical_json_bytes(base))}


def verify_payload_hash(payload: Mapping[str, Any], field: str = "payload_sha256_excluding_this_field") -> None:
    copy = dict(payload)
    stored = copy.pop(field, None)
    if not isinstance(stored, str) or stored != sha256_bytes(canonical_json_bytes(copy)):
        raise AnalysisError(f"self-hash mismatch: {field}")


def commit_plain_file_create_or_identical(
    temporary: str | Path, destination: str | Path, *, identical_ok: bool = True,
) -> None:
    """Publish a completed temporary file without any overwrite race."""
    source = Path(temporary)
    target = Path(destination)
    source_sha, source_size = file_fingerprint(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    require_plain_directory(target.parent)
    parent_snapshot = _plain_component_snapshot(target.parent)

    def accept_existing() -> bool:
        if not path_lexists(target):
            return False
        if is_reparse_or_link(target):
            raise AnalysisError(f"existing destination is a link/reparse: {target}")
        target_sha, target_size = file_fingerprint(target)
        if identical_ok and (target_sha, target_size) == (source_sha, source_size):
            return True
        raise AnalysisError(f"refusing to overwrite existing different file: {target}")

    if accept_existing():
        verify_plain_component_snapshot(parent_snapshot)
        return
    verify_plain_component_snapshot(parent_snapshot)
    try:
        os.link(source, target, follow_symlinks=False)
    except FileExistsError:
        if accept_existing():
            verify_plain_component_snapshot(parent_snapshot)
            return
        raise
    target_sha, target_size = file_fingerprint(target)
    verify_plain_component_snapshot(parent_snapshot)
    if (target_sha, target_size) != (source_sha, source_size):
        raise AnalysisError(f"new immutable file failed verification: {target}")


def atomic_write_bytes(path: str | Path, payload: bytes, *, identical_ok: bool = True) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    require_plain_directory(destination.parent)
    parent_snapshot = _plain_component_snapshot(destination.parent)
    expected_sha = sha256_bytes(payload)

    def accept_existing() -> bool:
        if not path_lexists(destination):
            return False
        if is_reparse_or_link(destination):
            raise AnalysisError(f"existing destination is a link/reparse: {destination}")
        actual_sha, actual_size = file_fingerprint(destination)
        if identical_ok and actual_size == len(payload) and actual_sha == expected_sha:
            return True
        raise AnalysisError(f"refusing to overwrite existing different file: {destination}")

    if accept_existing():
        verify_plain_component_snapshot(parent_snapshot)
        return
    verify_plain_component_snapshot(parent_snapshot)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.{os.getpid()}.", suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            verify_plain_component_snapshot(parent_snapshot)
            # Hard-link publication is atomic and fails if another writer created
            # the immutable destination; unlike replace(), it can never clobber it.
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            if accept_existing():
                return
            raise
        actual_sha, actual_size = file_fingerprint(destination)
        verify_plain_component_snapshot(parent_snapshot)
        if actual_size != len(payload) or actual_sha != expected_sha:
            raise AnalysisError(f"new immutable file failed verification: {destination}")
    finally:
        if path_lexists(temporary):
            temporary.unlink()


def atomic_write_json(path: str | Path, value: Any, *, identical_ok: bool = True) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value, newline=True), identical_ok=identical_ok)


def atomic_write_text(path: str | Path, value: str, *, identical_ok: bool = True) -> None:
    atomic_write_bytes(path, value.encode("utf-8"), identical_ok=identical_ok)


def replace_json(path: str | Path, value: Any) -> None:
    """Atomically replace a resumable checkpoint/working artifact only."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value, newline=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise AnalysisError(f"{label}: lowercase SHA-256 required")
    return value


def finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisError(f"{label}: finite number required")
    result = float(value)
    if not math.isfinite(result):
        raise AnalysisError(f"{label}: finite number required")
    return result


def normalize_semantic_key(generation_model: Any, domain: Any, item_id: Any) -> tuple[str, str, str]:
    if not all(isinstance(v, (str, int)) and not isinstance(v, bool)
               for v in (generation_model, domain, item_id)):
        raise CoverageError("semantic key components must be strings or integers")
    model = unicodedata.normalize("NFC", str(generation_model).strip())
    domain_value = unicodedata.normalize("NFC", str(domain).strip()).lower()
    identifier = unicodedata.normalize("NFC", str(item_id).strip())
    if not model or not domain_value or not identifier:
        raise CoverageError("semantic key components must be non-empty")
    return model, domain_value, identifier


def normalize_cluster_key(domain: Any, cluster_id: Any, fingerprint: Any) -> tuple[str, str, str]:
    if not all(isinstance(v, (str, int)) and not isinstance(v, bool)
               for v in (domain, cluster_id, fingerprint)):
        raise CoverageError("cluster key components must be strings or integers")
    result = (
        unicodedata.normalize("NFC", str(domain).strip()).lower(),
        unicodedata.normalize("NFC", str(cluster_id).strip()),
        unicodedata.normalize("NFC", str(fingerprint).strip()).lower(),
    )
    if not all(result):
        raise CoverageError("cluster key components must be non-empty")
    return result


def cluster_key_text(key: tuple[str, str, str]) -> str:
    return canonical_json_bytes(list(key)).decode("utf-8")


def array_sha256(array: np.ndarray) -> str:
    values = np.ascontiguousarray(array)
    descriptor = canonical_json_bytes({"dtype": values.dtype.str, "shape": list(values.shape)})
    return sha256_bytes(descriptor + values.tobytes(order="C"))


def inspect_plain_tree(
    root: str | Path, *, allowed_directories: Iterable[str] = (),
) -> list[str]:
    """Return exact regular-file inventory and reject every undeclared directory.

    The hidden name of the staging *root* is irrelevant: descendants are always
    checked.  This prevents empty or hidden directories from evading a file-only
    manifest inventory.
    """
    base = require_plain_directory(root)
    allowed = {Path(value).as_posix().rstrip("/") for value in allowed_directories}
    paths: list[str] = []
    seen_directories: set[str] = set()
    for current, directory_names, file_names in os.walk(base, followlinks=False):
        current_path = Path(current)
        for name in list(directory_names):
            child = current_path / name
            info = child.lstat()
            attrs = int(getattr(info, "st_file_attributes", 0))
            relative = child.relative_to(base).as_posix()
            if child.is_symlink() or attrs & 0x400 or not stat.S_ISDIR(info.st_mode):
                raise AnalysisError(f"reparse/symlink directory rejected: {child}")
            if name.startswith(".") or name == "__pycache__":
                raise AnalysisError(f"hidden/cache directory rejected: {child}")
            if relative not in allowed:
                raise AnalysisError(f"undeclared directory rejected: {child}")
            seen_directories.add(relative)
        for name in file_names:
            child = current_path / name
            info = child.lstat()
            attrs = int(getattr(info, "st_file_attributes", 0))
            if child.is_symlink() or attrs & 0x400 or not stat.S_ISREG(info.st_mode):
                raise AnalysisError(f"non-plain file rejected: {child}")
            if name.startswith(".") or name.endswith((".tmp", ".partial", ".lock")):
                raise AnalysisError(f"hidden/temporary file rejected: {child}")
            relative = child.relative_to(base).as_posix()
            if relative.startswith("../") or "/../" in relative:
                raise AnalysisError(f"path escape rejected: {child}")
            paths.append(relative)
    if seen_directories != allowed:
        raise AnalysisError(
            f"directory inventory differs; missing={sorted(allowed-seen_directories)}, "
            f"unknown={sorted(seen_directories-allowed)}"
        )
    return sorted(paths)


def validate_authority(authority: str | Path, project_root: str | Path) -> dict[str, Any]:
    authority_unresolved = Path(os.path.abspath(os.fspath(authority)))
    root_unresolved = Path(os.path.abspath(os.fspath(project_root)))
    authority_path = require_plain_directory(authority_unresolved)
    root = require_plain_directory(root_unresolved)
    if authority_path.parent.name != "phi_v2_derived_results":
        raise AuthorityError("authority location differs")
    known = {
        "manifest.json": EXPECTED_AUTHORITY_MANIFEST_SHA256,
        "metrics.json": EXPECTED_AUTHORITY_METRICS_SHA256,
        "audit.json": EXPECTED_AUTHORITY_AUDIT_SHA256,
        "scientific_completion.json": EXPECTED_AUTHORITY_COMPLETION_SHA256,
        "actual_pair_features.jsonl": EXPECTED_LEDGER_SHA256,
    }
    actual_known: dict[str, str] = {}
    for name, expected in known.items():
        target = authority_path / name
        try:
            actual, _ = file_fingerprint(target)
        except AnalysisError as exc:
            raise AuthorityError(f"authority artifact absent/non-plain: {name}") from exc
        actual_known[name] = actual
        if actual != expected:
            raise AuthorityError(f"authority artifact drift: {name}")

    manifest, manifest_sha, _ = strict_json_load_record(authority_path / "manifest.json")
    if manifest_sha != EXPECTED_AUTHORITY_MANIFEST_SHA256:
        raise AuthorityError("authority manifest changed between validation and parse")
    if not isinstance(manifest, dict):
        raise AuthorityError("authority manifest must be an object")
    copy = dict(manifest)
    stored = copy.pop("manifest_payload_sha256_excluding_this_field", None)
    if stored != sha256_bytes(canonical_json_bytes(copy)):
        raise AuthorityError("authority manifest self-hash differs")
    if manifest.get("state") != "complete" or manifest.get("schema") != "actual_heuristic.manifest":
        raise AuthorityError("authority manifest is not complete")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise AuthorityError("authority manifest inventory absent")
    declared: dict[str, dict[str, Any]] = {}
    for entry in artifacts:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise AuthorityError("authority inventory entry schema differs")
        relative = entry["path"]
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise AuthorityError("unsafe authority inventory path")
        if relative in declared:
            raise AuthorityError("duplicate authority inventory path")
        declared[relative] = entry
    actual_inventory = inspect_plain_tree(authority_path)
    expected_inventory = sorted([*declared, "manifest.json"])
    if actual_inventory != expected_inventory:
        raise AuthorityError("authority recursive inventory differs")
    for relative, entry in declared.items():
        target = authority_path / relative
        actual_hash, actual_size = file_fingerprint(target)
        if actual_size != entry["size"] or actual_hash != entry["sha256"]:
            raise AuthorityError(f"authority inventory hash differs: {relative}")
    if manifest.get("artifact_inventory_sha256") != sha256_bytes(canonical_json_bytes(artifacts)):
        raise AuthorityError("authority inventory digest differs")

    completion, completion_sha, _ = strict_json_load_record(authority_path / "scientific_completion.json")
    audit, audit_sha, _ = strict_json_load_record(authority_path / "audit.json")
    old_config, old_config_sha, old_config_size = strict_json_load_record(authority_path / "run_config.json")
    if completion_sha != EXPECTED_AUTHORITY_COMPLETION_SHA256 or audit_sha != EXPECTED_AUTHORITY_AUDIT_SHA256:
        raise AuthorityError("authority receipt changed between validation and parse")
    declared_old_config = declared.get("run_config.json")
    if not declared_old_config or (old_config_sha, old_config_size) != (declared_old_config["sha256"], declared_old_config["size"]):
        raise AuthorityError("authority run_config changed between inventory and parse")
    if completion.get("state") != "complete" or audit.get("state") != "pass":
        raise AuthorityError("authority completion/audit state differs")
    verify_payload_hash(completion, "receipt_payload_sha256_excluding_this_field")
    if audit.get("auditor_independence") != "does not import benchmark_core.py or run_benchmark.py":
        raise AuthorityError("authority audit independence differs")
    coverage = manifest.get("coverage", {})
    exact_coverage = {
        "actual_pairs": EXPECTED_PAIRS, "model_items": EXPECTED_ITEMS,
        "source_clusters": EXPECTED_CLUSTERS, "pairs_per_item": 5,
        "pair_set_sha256": EXPECTED_PAIR_SET_SHA256,
    }
    for key, expected in exact_coverage.items():
        if coverage.get(key) != expected:
            raise AuthorityError(f"authority coverage differs: {key}")
    if coverage.get("domain_items") != EXPECTED_DOMAIN_ITEMS or coverage.get("generation_model_items") != EXPECTED_MODEL_ITEMS:
        raise AuthorityError("authority item-cell counts differ")

    protected = old_config.get("input_artifacts")
    # The immutable authority enumerates ten entries: five canonical sources,
    # two raw-authority receipts, and three frozen pilot artifacts.
    if not isinstance(protected, dict) or len(protected) != 10:
        raise AuthorityError("authority protected-input inventory differs")
    input_snapshot: dict[str, dict[str, Any]] = {}
    for label, entry in sorted(protected.items()):
        if not isinstance(entry, dict) or not {"path", "sha256", "size"}.issubset(entry):
            raise AuthorityError(f"protected input schema differs: {label}")
        relative = entry["path"]
        if (
            not isinstance(relative, str) or not relative
            or Path(relative).is_absolute() or ".." in Path(relative).parts
        ):
            raise AuthorityError(f"unsafe protected input path: {label}")
        target = root / Path(relative)
        try:
            actual_hash, actual_size = file_fingerprint(target)
        except AnalysisError as exc:
            raise AuthorityError(f"protected input absent/non-plain: {label}") from exc
        if actual_hash != entry["sha256"] or actual_size != entry["size"]:
            raise AuthorityError(f"protected input drift: {label}")
        input_snapshot[label] = {
            "path": relative, "sha256": actual_hash, "size": actual_size,
        }

    return {
        "authority_path": "${HC_DATA_ROOT}/experiment_baseline\\phi_v2_derived_results\\phi_v2_20260822T180934_7d329704f7ab_actual_heuristic_20260911T035818Z_v1",
        "authority_bundle_id": manifest.get("bundle_id"),
        "known_hashes": actual_known,
        "internal_inventory_sha256": manifest["artifact_inventory_sha256"],
        "protected_inputs": input_snapshot,
        "coverage": exact_coverage,
        "external_non_input_warning": "relocated_same_sha_not_consumed",
        "word_path_followed": False,
    }


@dataclass(slots=True)
class Dataset:
    n: int
    models: np.ndarray
    domains: np.ndarray
    ids: np.ndarray
    levels: np.ndarray
    level_index: np.ndarray
    item_index: np.ndarray
    cluster_index: np.ndarray
    cluster_keys: tuple[tuple[str, str, str], ...]
    cluster_rows: tuple[np.ndarray, ...]
    scoring_hashes: np.ndarray
    prompt_hashes: np.ndarray
    output_hashes: np.ndarray
    values: dict[str, np.ndarray]
    pair_set_sha256: str
    ledger_sha256: str
    pair_keys: tuple[tuple[str, str, str, str], ...]

    @property
    def item_count(self) -> int:
        return self.n // 5


def load_ledger(path: str | Path, *, expected_pairs: int = EXPECTED_PAIRS) -> Dataset:
    ledger_path = Path(path)
    ledger_digest = hashlib.sha256()
    models: list[str] = []
    domains: list[str] = []
    ids: list[str] = []
    levels: list[str] = []
    scoring_hashes: list[str] = []
    prompt_hashes: list[str] = []
    output_hashes: list[str] = []
    raw_cluster_keys: list[tuple[str, str, str]] = []
    numeric: dict[str, list[float]] = {name: [] for name in NUMERIC_FIELDS}
    pair_keys: list[tuple[str, str, str, str]] = []
    pair_hash_payload: list[list[str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    previous_sort_key: tuple[str, str, str, int] | None = None
    with open_plain_binary(ledger_path) as handle:
        for line_number, raw in enumerate(handle, 1):
            ledger_digest.update(raw)
            if not raw or raw[-1:] != b"\n" or raw.endswith(b"\r\n"):
                raise CoverageError(f"ledger line {line_number}: canonical LF terminator required")
            if not raw.strip():
                raise CoverageError(f"ledger line {line_number}: blank line")
            row = strict_json_loads(raw, f"ledger line {line_number}")
            if not isinstance(row, dict) or frozenset(row) != LEDGER_FIELDS:
                raise CoverageError(f"ledger line {line_number}: exact schema differs")
            model, domain, item_id = normalize_semantic_key(
                row["generation_model"], row["domain"], row["id"]
            )
            if (model, domain, item_id) != (
                row["generation_model"], row["domain"], str(row["id"])
            ):
                raise CoverageError(f"ledger line {line_number}: key not canonical")
            level = row["level"]
            if level not in LEVELS:
                raise CoverageError(f"ledger line {line_number}: invalid level")
            key = (model, domain, item_id, level)
            if key in seen:
                raise CoverageError(f"duplicate pair key: {key!r}")
            seen.add(key)
            sort_key = (model, domain, item_id, LEVELS.index(level))
            if previous_sort_key is not None and sort_key <= previous_sort_key:
                raise CoverageError("ledger is not in unique canonical pair order")
            previous_sort_key = sort_key
            for name in ("scoring_input_sha256", "prompt_sha256", "output_sha256"):
                require_sha256(row[name], f"ledger line {line_number}.{name}")
            cluster = normalize_cluster_key(
                row["source_cluster_domain"], row["source_cluster_id"],
                row["source_cluster_fingerprint"],
            )
            models.append(model); domains.append(domain); ids.append(item_id); levels.append(level)
            scoring_hashes.append(row["scoring_input_sha256"])
            prompt_hashes.append(row["prompt_sha256"]); output_hashes.append(row["output_sha256"])
            raw_cluster_keys.append(cluster); pair_keys.append(key)
            pair_hash_payload.append([model, domain, item_id, level, row["scoring_input_sha256"]])
            for name in NUMERIC_FIELDS:
                numeric[name].append(finite_float(row[name], f"ledger line {line_number}.{name}"))
    ledger_sha = ledger_digest.hexdigest()
    if expected_pairs == EXPECTED_PAIRS and ledger_sha != EXPECTED_LEDGER_SHA256:
        raise AuthorityError("ledger SHA-256 differs from bytes parsed")
    if len(pair_keys) != expected_pairs:
        raise CoverageError(f"ledger pair count {len(pair_keys)} != {expected_pairs}")
    if len(pair_keys) % 5:
        raise CoverageError("ledger pair count is not divisible by five")

    item_index = np.repeat(np.arange(len(pair_keys) // 5, dtype=np.int32), 5)
    level_index = np.tile(np.arange(5, dtype=np.int8), len(pair_keys) // 5)
    for start in range(0, len(pair_keys), 5):
        group_keys = pair_keys[start:start + 5]
        if len({key[:3] for key in group_keys}) != 1 or tuple(key[3] for key in group_keys) != LEVELS:
            raise CoverageError(f"five-level item contract failed near row {start}")
        if len(set(scoring_hashes[start:start + 5])) != 1:
            raise CoverageError(f"scoring hash differs within item near row {start}")
        if len(set(raw_cluster_keys[start:start + 5])) != 1:
            raise CoverageError(f"source-cluster triple differs within item near row {start}")

    cluster_keys = tuple(sorted(set(raw_cluster_keys)))
    if len(cluster_keys) != (EXPECTED_CLUSTERS if expected_pairs == EXPECTED_PAIRS else len(cluster_keys)):
        raise CoverageError(f"source-cluster count {len(cluster_keys)} != {EXPECTED_CLUSTERS}")
    cluster_lookup = {key: index for index, key in enumerate(cluster_keys)}
    cluster_index = np.fromiter((cluster_lookup[key] for key in raw_cluster_keys), dtype=np.int32)
    cluster_rows = tuple(np.flatnonzero(cluster_index == index).astype(np.int32)
                         for index in range(len(cluster_keys)))
    model_array = np.asarray(models, dtype="U32")
    domain_array = np.asarray(domains, dtype="U16")
    for index, rows in enumerate(cluster_rows):
        if len(set(domain_array[rows].tolist())) != 1:
            raise CoverageError(f"cluster spans domains: {cluster_keys[index]!r}")
        if cluster_keys[index][0] != domain_array[rows[0]]:
            raise CoverageError(f"cluster domain differs from pair domain: {cluster_keys[index]!r}")
        if len(rows) % 5 or any(int(np.sum(item_index[rows] == item)) != 5 for item in np.unique(item_index[rows])):
            raise CoverageError(f"cluster does not contain complete five-row item blocks: {cluster_keys[index]!r}")

    pair_set_hash = sha256_bytes(canonical_json_bytes(pair_hash_payload))
    if expected_pairs == EXPECTED_PAIRS and pair_set_hash != EXPECTED_PAIR_SET_SHA256:
        raise CoverageError("pair-set SHA-256 differs")
    value_arrays = {name: np.asarray(values, dtype=np.float64) for name, values in numeric.items()}
    if not all(np.isfinite(values).all() for values in value_arrays.values()):
        raise CoverageError("non-finite numeric ledger value")
    dataset = Dataset(
        n=len(pair_keys), models=model_array, domains=domain_array,
        ids=np.asarray(ids, dtype=object), levels=np.asarray(levels, dtype="U2"),
        level_index=level_index, item_index=item_index, cluster_index=cluster_index,
        cluster_keys=cluster_keys, cluster_rows=cluster_rows,
        scoring_hashes=np.asarray(scoring_hashes, dtype="U64"),
        prompt_hashes=np.asarray(prompt_hashes, dtype="U64"),
        output_hashes=np.asarray(output_hashes, dtype="U64"),
        values=value_arrays, pair_set_sha256=pair_set_hash,
        ledger_sha256=ledger_sha, pair_keys=tuple(pair_keys),
    )
    validate_dataset_coverage(dataset, expected_pairs=expected_pairs)
    derive_features(dataset)
    return dataset


def validate_dataset_coverage(dataset: Dataset, *, expected_pairs: int = EXPECTED_PAIRS) -> None:
    if dataset.n != expected_pairs or dataset.item_count * 5 != dataset.n:
        raise CoverageError("dataset coverage differs")
    item_model = dataset.models[::5]
    item_domain = dataset.domains[::5]
    for offset in range(1, 5):
        if not np.array_equal(dataset.models[offset::5], item_model):
            raise CoverageError("generation model changes within item")
        if not np.array_equal(dataset.domains[offset::5], item_domain):
            raise CoverageError("domain changes within item")
    if expected_pairs == EXPECTED_PAIRS:
        model_counts = dict(sorted(Counter(item_model.tolist()).items()))
        domain_counts = dict(sorted(Counter(item_domain.tolist()).items()))
        if model_counts != EXPECTED_MODEL_ITEMS or domain_counts != EXPECTED_DOMAIN_ITEMS:
            raise CoverageError("model/domain item coverage differs")


def derive_features(dataset: Dataset) -> dict[str, np.ndarray]:
    values = dataset.values
    output_bytes = values["output_bytes"]
    ratio = values["blackbox_actual_ratio"]
    self_bpb = values["output_self_bits_per_byte"]
    c_bits = self_bpb * output_bytes
    gain = ratio * c_bits
    conditional = c_bits - gain
    gain_per_byte = gain / output_bytes
    eps = np.finfo(np.float64).eps
    tolerance = 64.0 * eps * np.maximum.reduce((
        np.ones(dataset.n), np.abs(c_bits), np.abs(gain),
    ))
    if np.any(output_bytes <= 0.0):
        raise CoverageError("output_bytes must be positive")
    if np.any(c_bits <= 0.0):
        raise CoverageError("C_y_bits must be positive")
    if np.any((ratio < 0.0) | (ratio > 1.0)):
        raise CoverageError("R_actual must be in [0,1]")
    if np.any(gain < 0.0) or np.any(conditional < -tolerance):
        raise CoverageError("raw-gain algebra bound failed")
    reconstructed = gain / c_bits
    if not np.all(np.isclose(reconstructed, ratio, rtol=64.0 * eps, atol=64.0 * eps)):
        raise CoverageError("raw-gain ratio reconstruction failed")
    values["R_actual"] = ratio.copy()
    values["C_y_bits"] = c_bits
    values["G_raw_bits"] = gain
    values["D_conditional_bits_audit_only"] = conditional
    values["G_raw_bits_per_output_byte"] = gain_per_byte
    treatment = np.asarray([LEVEL_VALUE[level] for level in dataset.levels], dtype=np.float64)
    values["treatment_ordinal"] = treatment
    llama = values["phi_actual_llama"]
    mixtral = values["phi_actual_mixtral"]
    llama_rank = rankdata(llama, method="average")
    mixtral_rank = rankdata(mixtral, method="average")
    values["consensus_midrank_percentile"] = (
        (llama_rank - 0.5) / dataset.n + (mixtral_rank - 0.5) / dataset.n
    ) / 2.0
    llama_z = (llama - llama.mean()) / llama.std(ddof=1)
    mixtral_z = (mixtral - mixtral.mean()) / mixtral.std(ddof=1)
    values["phi_actual_llama_global_z"] = llama_z
    values["phi_actual_mixtral_global_z"] = mixtral_z
    values["consensus_global_z"] = (llama_z + mixtral_z) / 2.0
    values["evaluator_absolute_global_z_difference"] = np.abs(llama_z - mixtral_z)
    return values


def raw_algebra_receipt(dataset: Dataset) -> dict[str, Any]:
    values = dataset.values
    conditional = values["D_conditional_bits_audit_only"]
    ratio_error = np.abs(values["G_raw_bits"] / values["C_y_bits"] - values["R_actual"])
    return {
        "formulae": {
            "C_y_bits": "output_self_bits_per_byte * output_bytes",
            "G_raw_bits": "R_actual * C_y_bits",
            "D_conditional_bits_audit_only": "C_y_bits - G_raw_bits",
            "G_raw_bits_per_output_byte": "G_raw_bits / output_bytes",
        },
        "rows": dataset.n,
        "all_output_bytes_positive": bool(np.all(values["output_bytes"] > 0.0)),
        "all_C_y_bits_positive": bool(np.all(values["C_y_bits"] > 0.0)),
        "all_R_actual_in_unit_interval": bool(np.all((values["R_actual"] >= 0.0) & (values["R_actual"] <= 1.0))),
        "all_G_raw_bits_nonnegative": bool(np.all(values["G_raw_bits"] >= 0.0)),
        "minimum_D_conditional_bits": float(conditional.min()),
        "maximum_ratio_reconstruction_absolute_error": float(ratio_error.max()),
        "float_tolerance": "64*float64_eps with rowwise max scale; np.isclose rtol=atol=64*eps",
        "array_sha256": {
            name: array_sha256(values[name]) for name in (
                "C_y_bits", "G_raw_bits", "D_conditional_bits_audit_only",
                "G_raw_bits_per_output_byte",
            )
        },
        "D_conditional_role": "audit_only_not_baseline",
        "redundant_1_minus_R_or_D_over_C_constructed": False,
    }


def _seed_token(seed: int, purpose: str, key: tuple[str, str, str], fold: int | None = None) -> str:
    parts = [str(seed), purpose, *key]
    if fold is not None:
        parts.append(str(fold))
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def inner_seed(outer_fold: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{INNER_MASTER_SEED}\0outer={outer_fold}".encode("ascii")).digest()[:8],
        "big",
    )


def assign_grouped_folds(
    cluster_keys: Sequence[tuple[str, str, str]],
    cluster_rows: Sequence[np.ndarray],
    domains: np.ndarray,
    *, seed: int, n_folds: int = 5,
) -> dict[tuple[str, str, str], int]:
    records: list[tuple[tuple[str, str, str], str, int, str]] = []
    for key, rows in zip(cluster_keys, cluster_rows, strict=True):
        row_domains = set(domains[np.asarray(rows, dtype=np.int64)].tolist())
        if len(row_domains) != 1 or key[0] not in row_domains:
            raise CoverageError(f"fold cluster domain contract failed: {key!r}")
        records.append((key, key[0], int(len(rows)), _seed_token(seed, "sort", key)))
    records.sort(key=lambda record: (-record[2], record[3], record[0]))
    domain_rows: dict[str, list[int]] = defaultdict(lambda: [0] * n_folds)
    total_rows = [0] * n_folds
    cluster_counts = [0] * n_folds
    assignment: dict[tuple[str, str, str], int] = {}
    for key, domain, row_count, _ in records:
        fold_priorities = {
            fold: _seed_token(seed, "fold-priority", key, fold) for fold in range(n_folds)
        }
        selected = min(
            range(n_folds),
            key=lambda fold: (
                domain_rows[domain][fold], total_rows[fold], cluster_counts[fold],
                fold_priorities[fold], fold,
            ),
        )
        assignment[key] = selected
        domain_rows[domain][selected] += row_count
        total_rows[selected] += row_count
        cluster_counts[selected] += 1
    return assignment


def _assignment_sha(assignment: Mapping[tuple[str, str, str], int]) -> str:
    payload = [[*key, int(assignment[key])] for key in sorted(assignment)]
    return sha256_bytes(canonical_json_bytes(payload))


def _fold_cell(dataset: Dataset, rows: np.ndarray, *, fold: int) -> dict[str, Any]:
    row_ids = np.asarray(rows, dtype=np.int64)
    return {
        "fold": int(fold),
        "rows": int(len(row_ids)),
        "clusters": int(len(np.unique(dataset.cluster_index[row_ids]))),
        "items": int(len(np.unique(dataset.item_index[row_ids]))),
        "domain_rows": dict(sorted(Counter(dataset.domains[row_ids].tolist()).items())),
        "model_rows": dict(sorted(Counter(dataset.models[row_ids].tolist()).items())),
    }


def _row_permuted_assignment(dataset: Dataset, seed: int) -> dict[tuple[str, str, str], int]:
    """Reconstruct grouping after a deterministic full-row permutation."""
    permutation = np.random.default_rng(seed).permutation(dataset.n)
    permuted_domains = dataset.domains[permutation]
    permuted_cluster_index = dataset.cluster_index[permutation]
    permuted_rows = tuple(
        np.flatnonzero(permuted_cluster_index == index).astype(np.int32)
        for index in range(len(dataset.cluster_keys))
    )
    return assign_grouped_folds(
        dataset.cluster_keys, permuted_rows, permuted_domains, seed=seed,
    )


def build_fold_plan(dataset: Dataset) -> dict[str, Any]:
    outer = assign_grouped_folds(
        dataset.cluster_keys, dataset.cluster_rows, dataset.domains, seed=OUTER_SEED,
    )
    reversed_outer = assign_grouped_folds(
        tuple(reversed(dataset.cluster_keys)), tuple(reversed(dataset.cluster_rows)),
        dataset.domains, seed=OUTER_SEED,
    )
    if outer != reversed_outer or outer != _row_permuted_assignment(dataset, OUTER_SEED):
        raise CoverageError("outer fold assignment is row-order sensitive")
    cluster_model_sets = [set(dataset.models[rows].tolist()) for rows in dataset.cluster_rows]
    cluster_domain = [dataset.cluster_keys[index][0] for index in range(len(dataset.cluster_keys))]
    outer_details: list[dict[str, Any]] = []
    all_outer_test: set[tuple[str, str, str]] = set()
    for outer_fold in range(5):
        test_keys = {key for key, fold in outer.items() if fold == outer_fold}
        train_keys = set(outer) - test_keys
        if train_keys & test_keys or not train_keys or not test_keys:
            raise CoverageError(f"outer fold {outer_fold}: leakage/empty split")
        if all_outer_test & test_keys:
            raise CoverageError("outer test cluster repeated")
        all_outer_test.update(test_keys)
        train_indices = [index for index, key in enumerate(dataset.cluster_keys) if key in train_keys]
        train_cluster_keys = tuple(dataset.cluster_keys[index] for index in train_indices)
        train_cluster_rows = tuple(dataset.cluster_rows[index] for index in train_indices)
        seed = inner_seed(outer_fold)
        inner = assign_grouped_folds(
            train_cluster_keys, train_cluster_rows, dataset.domains, seed=seed,
        )
        reverse_inner = assign_grouped_folds(
            tuple(reversed(train_cluster_keys)), tuple(reversed(train_cluster_rows)),
            dataset.domains, seed=seed,
        )
        if inner != reverse_inner:
            raise CoverageError(f"inner fold {outer_fold}: row-order sensitivity")
        if set(inner) != train_keys:
            raise CoverageError(f"inner fold {outer_fold}: universe differs")
        inner_counts = Counter(inner.values())
        if set(inner_counts) != set(range(5)):
            raise CoverageError(f"inner fold {outer_fold}: empty validation fold")
        inner_cells: list[dict[str, Any]] = []
        for inner_fold in range(5):
            validation_cluster_ids = [
                index for index, key in enumerate(dataset.cluster_keys)
                if key in inner and inner[key] == inner_fold
            ]
            training_cluster_ids = [
                index for index, key in enumerate(dataset.cluster_keys)
                if key in inner and inner[key] != inner_fold
            ]
            validation_rows = np.concatenate([
                dataset.cluster_rows[index] for index in validation_cluster_ids
            ])
            training_rows = np.concatenate([
                dataset.cluster_rows[index] for index in training_cluster_ids
            ])
            if (
                set(dataset.domains[validation_rows].tolist()) != set(EXPECTED_DOMAIN_ITEMS)
                or set(dataset.models[validation_rows].tolist()) != set(EXPECTED_MODEL_ITEMS)
            ):
                raise CoverageError(
                    f"inner fold {outer_fold}/{inner_fold}: empty domain/model cell"
                )
            validation_cell = _fold_cell(dataset, validation_rows, fold=inner_fold)
            validation_cell["role"] = "validation"
            training_cell = _fold_cell(dataset, training_rows, fold=inner_fold)
            training_cell["role"] = "training"
            inner_cells.append({"inner_fold": inner_fold, "validation": validation_cell, "training": training_cell})
        inner_payload = [[*key, int(inner[key])] for key in sorted(inner)]
        outer_details.append({
            "outer_fold": outer_fold,
            "inner_seed_uint64": seed,
            "train_cluster_count": len(train_keys),
            "test_cluster_count": len(test_keys),
            "train_cluster_key_sha256": sha256_bytes(canonical_json_bytes([list(k) for k in sorted(train_keys)])),
            "test_cluster_key_sha256": sha256_bytes(canonical_json_bytes([list(k) for k in sorted(test_keys)])),
            "inner_assignment_sha256": sha256_bytes(canonical_json_bytes(inner_payload)),
            "inner_assignments": inner_payload,
            "inner_fold_cells": inner_cells,
        })
    if all_outer_test != set(dataset.cluster_keys):
        raise CoverageError("not every cluster appears in outer test exactly once")

    fold_cells: list[dict[str, Any]] = []
    for fold in range(5):
        cluster_ids = [index for index, key in enumerate(dataset.cluster_keys) if outer[key] == fold]
        rows = np.concatenate([dataset.cluster_rows[index] for index in cluster_ids])
        cell = _fold_cell(dataset, rows, fold=fold)
        if set(cell["domain_rows"]) != set(EXPECTED_DOMAIN_ITEMS) or set(cell["model_rows"]) != set(EXPECTED_MODEL_ITEMS):
            raise CoverageError(f"outer fold {fold}: empty domain/model cell")
        fold_cells.append(cell)
    outer_payload = [[*key, int(outer[key])] for key in sorted(outer)]
    cluster_row_counts = [
        [*key, int(len(dataset.cluster_rows[index]))]
        for index, key in enumerate(dataset.cluster_keys)
    ]
    base = {
        "schema": "actual_incremental_sensitivity.fold_assignments",
        "schema_version": 1,
        "outer_seed": OUTER_SEED,
        "inner_master_seed": INNER_MASTER_SEED,
        "algorithm": {
            "sort": "(-row_count, seeded_sha256_tie_token, canonical_cluster_key)",
            "assignment_minimum": "(domain_rows, total_rows, cluster_count, seeded_fold_priority, fold)",
            "cluster_key": ["source_cluster_domain", "source_cluster_id", "source_cluster_fingerprint"],
        },
        "row_order_invariant": True,
        "row_permutation_test": {
            "seed": OUTER_SEED,
            "method": "full row permutation followed by cluster-row reconstruction",
            "passed": True,
        },
        "cluster_row_counts": cluster_row_counts,
        "cluster_row_count_sha256": sha256_bytes(canonical_json_bytes(cluster_row_counts)),
        "outer_assignments": outer_payload,
        "outer_assignment_sha256": sha256_bytes(canonical_json_bytes(outer_payload)),
        "outer_folds": outer_details,
        "outer_fold_cells": fold_cells,
        "coverage": {"rows": dataset.n, "items": dataset.item_count, "clusters": len(dataset.cluster_keys)},
    }
    return payload_with_hash(base)


def fold_maps(fold_plan: Mapping[str, Any]) -> tuple[dict[tuple[str, str, str], int], list[dict[tuple[str, str, str], int]]]:
    outer = {tuple(entry[:3]): int(entry[3]) for entry in fold_plan["outer_assignments"]}
    inner: list[dict[tuple[str, str, str], int]] = []
    for detail in fold_plan["outer_folds"]:
        inner.append({tuple(entry[:3]): int(entry[3]) for entry in detail["inner_assignments"]})
    return outer, inner


def frozen_strongest(authority_metrics_path: str | Path) -> dict[str, Any]:
    metrics = strict_json_load(authority_metrics_path)
    records = metrics.get("records")
    if not isinstance(records, dict):
        raise AuthorityError("authority metrics record mapping absent")
    sets = {
        "strongest_word_overlap": ("word_type_coverage", "word_token_coverage", "word_bigram_coverage"),
        "strongest_char_overlap": ("char3_coverage", "char5_coverage", "char8_coverage"),
        "strongest_single_heuristic": HEURISTICS,
    }
    selections: dict[str, Any] = {}
    for label, candidates in sets.items():
        inspected: list[dict[str, Any]] = []
        for order, candidate in enumerate(candidates):
            metric_id = f"direct|{candidate}|macro_within_level|rho"
            record = records.get(metric_id)
            if not isinstance(record, dict) or not isinstance(record.get("point"), (int, float)):
                raise AuthorityError(f"selection metric absent: {metric_id}")
            point = finite_float(record["point"], metric_id)
            inspected.append({"candidate": candidate, "declared_order": order, "metric_id": metric_id, "point": point})
        winner = max(inspected, key=lambda item: (item["point"], -item["declared_order"]))
        selections[label] = {
            "criterion": "largest signed point estimate",
            "tie_break": "earlier declared candidate order",
            "candidates": inspected,
            "selected": winner["candidate"],
            "selected_metric_id": winner["metric_id"],
            "selected_point": winner["point"],
        }
    expected = {
        "strongest_word_overlap": "word_token_coverage",
        "strongest_char_overlap": "char5_coverage",
        "strongest_single_heuristic": "rouge_l_recall",
    }
    if {key: value["selected"] for key, value in selections.items()} != expected:
        raise AuthorityError("frozen strongest selections differ from expected authority outcome")
    return selections


def make_run_config(
    *, bundle_id: str, authority_receipt: Mapping[str, Any], selections: Mapping[str, Any],
    fold_plan: Mapping[str, Any], code_files: Sequence[Path], created_at_utc: str,
) -> dict[str, Any]:
    code = [file_record(path, path.parent) for path in sorted(code_files, key=lambda p: p.name)]
    base = {
        "schema": "actual_incremental_sensitivity.run_config",
        "schema_version": 1,
        "state": "frozen_before_formal_statistics",
        "bundle_id": bundle_id,
        "created_at_utc": created_at_utc,
        "estimand": "aggregate R_actual on real prompt-output pairs only",
        "authority": dict(authority_receipt),
        "coverage": {"pairs": EXPECTED_PAIRS, "items": EXPECTED_ITEMS, "source_clusters": EXPECTED_CLUSTERS, "levels": list(LEVELS)},
        "keys": {
            "model_item": ["generation_model", "NFC/lower(domain)", "NFC(id)"],
            "pair": ["generation_model", "NFC/lower(domain)", "NFC(id)", "level"],
            "source_cluster": ["source_cluster_domain", "source_cluster_id", "source_cluster_fingerprint"],
        },
        "raw_algebra": {
            "C_y_bits": "output_self_bits_per_byte * output_bytes",
            "G_raw_bits": "R_actual * C_y_bits",
            "D_conditional_bits": "C_y_bits - G_raw_bits; audit only",
            "G_raw_bits_per_output_byte": "G_raw_bits / output_bytes",
            "rtol": "64*float64_eps", "atol": "64*float64_eps",
        },
        "direct_candidates": list(DIRECT_CANDIDATES),
        "frozen_strongest": dict(selections),
        "folds": {
            "outer": 5, "inner": 5, "outer_seed": OUTER_SEED,
            "inner_master_seed": INNER_MASTER_SEED,
            "outer_assignment_sha256": fold_plan["outer_assignment_sha256"],
            "fold_plan_payload_sha256": fold_plan["payload_sha256_excluding_this_field"],
        },
        "learners": {
            "ridge": {
                "scaler": "StandardScaler fit only on current training fold",
                "fit_intercept": True, "solver": "svd", "alphas": list(RIDGE_ALPHAS),
                "selection": "concatenated inner-holdout row-weighted MSE; within 1e-12+1e-10*abs(best), choose larger alpha",
            },
            "hist_gradient_boosting": {
                "loss": "squared_error", "learning_rate": 0.05, "max_iter": 200,
                "max_leaf_nodes": 15, "max_depth": None, "min_samples_leaf": 50,
                "l2_regularization": 1.0, "max_bins": 255, "early_stopping": False,
                "random_state": HGB_RANDOM_STATE, "tuning": False,
            },
        },
        "predictor_sets": {
            "primary_sets": list(PREDICTOR_SETS),
            "L": ["p", "o", "p^2", "p*o", "o^2"],
            "O": list(OVERLAP_FEATURES), "H": list(HEURISTICS),
            "H_log1p": sorted(LOG_HEURISTICS), "H+R": ["H", "R_actual"],
            "R-only": ["R_actual"], "G-only": ["G_raw_bits"],
            "auxiliary_strongest_single": {
                "set_name": AUXILIARY_PREDICTOR_SET,
                "status": "auxiliary_not_one_of_six_primary_sets",
                "feature": selections["strongest_single_heuristic"]["selected"],
                "selection_source": selections["strongest_single_heuristic"]["selected_metric_id"],
            },
            "white_box_predictors_forbidden": True,
        },
        "length_residualization": {
            "targets": list(LENGTH_TARGETS), "specifications": list(LENGTH_SPECS),
            "byte_L_out": ["o", "o^2", "o^3"],
            "byte_L_full": ["p", "o", "p^2", "p*o", "o^2"],
            "word_L_out": ["w", "w^2", "w^3"],
            "word_L_full": ["pw", "ow", "pw^2", "pw*ow", "ow^2"],
            "treatment_estimand": "residual_candidate_vs_raw_treatment_ordinal; not two-sided partial correlation",
        },
        "consensus": {
            "primary": "equal mean of evaluator global average-midrank percentiles (rank-.5)/N",
            "sensitivity": "equal mean of evaluator global sample-z scores ddof=1",
            "constructed_once_globally": True,
            "joint_reference_statistic": JOINT_ALPHA,
        },
        "agreement": {
            "rank": "Spearman rho with average midranks",
            "primary_alpha": PAIRWISE_ALPHA,
            "alpha_protocol": "independent sample-z ddof=1 then exact interval Krippendorff alpha O(m)",
            "primary_scopes": ["macro_within_level", "item_centered"],
            "treatment_labels": {level: int(value) for level, value in LEVEL_VALUE.items()},
            "constant_columns": "undefined_with_reason_not_zero",
        },
        "evaluator_sensitivity": {
            "difference": "abs(global-z llama - global-z mixtral)",
            "quantiles": [0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0],
            "level_pairs": [list(pair) for pair in ALL_LEVEL_PAIRS],
            "adjacent_pairs": [list(pair) for pair in ADJACENT_LEVEL_PAIRS],
            "strict_monotonicity": "L1>L2>L3>L4>L5",
        },
        "common_support": {
            "adjacent_output_byte_ratio_calipers": [1.10, 1.20, 1.30],
            "inclusive": True, "all_five_caliper": 1.25,
            "low_support": {"items_less_than": 1123, "clusters_less_than": 256, "any_domain_absent": True, "any_model_absent": True},
        },
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
            "block_size": BOOTSTRAP_BLOCK_SIZE, "cluster_count": EXPECTED_CLUSTERS,
            "draw_sequence_sha256": EXPECTED_DRAW_SHA256,
            "percentiles": [2.5, 97.5], "method": "linear",
            "minimum_finite_replicates": 1980,
            "conditional_on_frozen_cross_fitted_predictions": True,
            "refit_inside_bootstrap": False,
        },
        "classification": {
            "stable_positive": "all predeclared paired CI lower bounds > 0",
            "stable_negative": "all predeclared paired CI upper bounds < 0",
            "otherwise": "mixed_or_inconclusive",
        },
        "resources": {
            "single_process": True, "blas_openmp_threads": 1,
            "rss_target_bytes": RSS_TARGET, "rss_hard_limit_bytes": RSS_HARD_LIMIT,
            "rss_limit_semantics": "sampled_process_rss_hard_limit",
            "rss_sampling_interval_milliseconds": 50,
            "synchronous_exit_rss_sample": True,
            "gpu": False, "network": False,
        },
        "prohibitions": {
            "api_calls": 0, "model_generation": False, "network": False,
            "gpu": False, "text_regeneration": False, "recompression": False,
            "prompt_or_output_text_reads": 0, "counterfactual_fields": False,
            "authority_modified": False, "word_modified": False,
        },
        "code_snapshot": {"files": code, "inventory_sha256": sha256_bytes(canonical_json_bytes(code))},
    }
    return payload_with_hash(base, "config_payload_sha256_excluding_this_field")


def predictor_matrix(dataset: Dataset, set_name: str) -> tuple[np.ndarray, list[str]]:
    v = dataset.values
    p = np.log1p(v["prompt_bytes"]); o = np.log1p(v["output_bytes"])
    if set_name == "L":
        return np.column_stack((p, o, p * p, p * o, o * o)), ["log1p_prompt_bytes", "log1p_output_bytes", "p2", "p_x_o", "o2"]
    if set_name == "O":
        return np.column_stack([v[name] for name in OVERLAP_FEATURES]), list(OVERLAP_FEATURES)
    if set_name in {"H", "H+R"}:
        columns = [np.log1p(v[name]) if name in LOG_HEURISTICS else v[name] for name in HEURISTICS]
        names = [f"log1p_{name}" if name in LOG_HEURISTICS else name for name in HEURISTICS]
        if set_name == "H+R":
            columns.append(v["R_actual"]); names.append("R_actual")
        return np.column_stack(columns), names
    if set_name == "R-only":
        return v["R_actual"][:, None], ["R_actual"]
    if set_name == "G-only":
        return v["G_raw_bits"][:, None], ["G_raw_bits"]
    raise AnalysisError(f"unknown predictor set: {set_name}")


def length_matrix(dataset: Dataset, spec: str) -> tuple[np.ndarray, list[str]]:
    v = dataset.values
    if spec.startswith("byte_"):
        p = np.log1p(v["prompt_bytes"]); o = np.log1p(v["output_bytes"])
        prefix = "bytes"
    elif spec.startswith("word_"):
        p = np.log1p(v["prompt_words"]); o = np.log1p(v["output_words"])
        prefix = "words"
    else:
        raise AnalysisError(f"unknown length specification: {spec}")
    if spec.endswith("L_out"):
        return np.column_stack((o, o * o, o * o * o)), [f"log1p_output_{prefix}", "o2", "o3"]
    if spec.endswith("L_full"):
        return np.column_stack((p, o, p * p, p * o, o * o)), [f"log1p_prompt_{prefix}", f"log1p_output_{prefix}", "p2", "p_x_o", "o2"]
    raise AnalysisError(f"unknown length specification: {spec}")


def krippendorff_interval_exact(ratings: Sequence[Sequence[float]] | np.ndarray) -> float | None:
    matrix = np.asarray(ratings, dtype=np.float64)
    if matrix.ndim != 2:
        raise AnalysisError("ratings must be two-dimensional")
    if not np.isfinite(matrix).all():
        raise AnalysisError("ratings contain non-finite values")
    unit_count, rater_count = matrix.shape
    if unit_count < 2 or rater_count < 2:
        return None
    row_sums = matrix.sum(axis=1)
    row_square_sums = np.square(matrix).sum(axis=1)
    observation_count = unit_count * rater_count
    grand_sum = float(row_sums.sum())
    grand_square_sum = float(row_square_sums.sum())
    numerator = 2.0 * (
        grand_square_sum - float(np.sum((np.square(row_sums) - row_square_sums) / (rater_count - 1)))
    )
    denominator = (2.0 / (observation_count - 1)) * (
        observation_count * grand_square_sum - grand_sum * grand_sum
    )
    tolerance = np.finfo(float).eps * max(1.0, abs(denominator), abs(numerator)) * 64.0
    if abs(denominator) <= tolerance:
        return 1.0 if abs(numerator) <= tolerance else None
    result = 1.0 - numerator / denominator
    return float(result) if math.isfinite(result) else None


def pairwise_continuous_alpha_z(left: Sequence[float], right: Sequence[float]) -> float | None:
    matrix = np.column_stack((left, right)).astype(np.float64, copy=False)
    if matrix.shape[0] < 2 or not np.isfinite(matrix).all():
        return None
    std = matrix.std(axis=0, ddof=1)
    if not np.isfinite(std).all() or np.any(std == 0.0):
        return None
    return krippendorff_interval_exact((matrix - matrix.mean(axis=0)) / std)


def joint_reference_continuous_alpha_z(candidate: Sequence[float], llama: Sequence[float], mixtral: Sequence[float]) -> float | None:
    matrix = np.column_stack((candidate, llama, mixtral)).astype(np.float64, copy=False)
    if matrix.shape[0] < 2 or not np.isfinite(matrix).all():
        return None
    std = matrix.std(axis=0, ddof=1)
    if not np.isfinite(std).all() or np.any(std == 0.0):
        return None
    return krippendorff_interval_exact((matrix - matrix.mean(axis=0)) / std)


def spearman_rho(left: Sequence[float], right: Sequence[float]) -> float | None:
    x = np.asarray(left, dtype=np.float64); y = np.asarray(right, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all() or not np.isfinite(y).all():
        return None
    rx = rankdata(x, method="average"); ry = rankdata(y, method="average")
    sx = rx.std(ddof=0); sy = ry.std(ddof=0)
    if sx == 0.0 or sy == 0.0:
        return None
    return float(np.mean((rx - rx.mean()) * (ry - ry.mean())) / (sx * sy))


def paired_agreement(left: Sequence[float], right: Sequence[float]) -> dict[str, Any]:
    x = np.asarray(left, dtype=np.float64); y = np.asarray(right, dtype=np.float64)
    reason = None
    if len(x) < 2:
        reason = "insufficient_observations"
    elif not np.isfinite(x).all() or not np.isfinite(y).all():
        reason = "nonfinite_input"
    elif np.ptp(x) == 0.0:
        reason = "candidate_constant"
    elif np.ptp(y) == 0.0:
        reason = "reference_constant"
    rho = None if reason else spearman_rho(x, y)
    alpha = None if reason else pairwise_continuous_alpha_z(x, y)
    return {
        "n": int(len(x)), "rho": rho,
        PAIRWISE_ALPHA: alpha,
        "undefined_reason": reason if rho is None or alpha is None else None,
    }


def center_within_items(vector: Sequence[float], item_index: np.ndarray | None = None) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float64)
    if item_index is None:
        if len(values) % 5:
            raise CoverageError("item-centering requires five-level blocks")
        return (values.reshape(-1, 5) - values.reshape(-1, 5).mean(axis=1, keepdims=True)).reshape(-1)
    result = np.empty_like(values)
    for item in np.unique(item_index):
        mask = item_index == item
        result[mask] = values[mask] - values[mask].mean()
    return result


def agreement_scopes(left: np.ndarray, right: np.ndarray, dataset: Dataset, *, include_subgroups: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {"pooled": paired_agreement(left, right)}
    per_level: dict[str, Any] = {}
    for level in LEVELS:
        mask = dataset.levels == level
        per_level[level] = paired_agreement(left[mask], right[mask])
    result["per_level"] = per_level
    if any(per_level[level]["rho"] is None or per_level[level][PAIRWISE_ALPHA] is None for level in LEVELS):
        result["macro_within_level"] = {
            "n": dataset.item_count, "rho": None, PAIRWISE_ALPHA: None,
            "undefined_reason": "one_or_more_level_metrics_undefined",
        }
    else:
        result["macro_within_level"] = {
            "n": dataset.item_count,
            "rho": float(np.mean([per_level[level]["rho"] for level in LEVELS])),
            PAIRWISE_ALPHA: float(np.mean([per_level[level][PAIRWISE_ALPHA] for level in LEVELS])),
            "undefined_reason": None,
        }
    result["item_centered"] = paired_agreement(
        center_within_items(left), center_within_items(right)
    )
    if include_subgroups:
        result["by_domain"] = {
            domain: paired_agreement(left[dataset.domains == domain], right[dataset.domains == domain])
            for domain in sorted(set(dataset.domains.tolist()))
        }
        result["by_generation_model"] = {
            model: paired_agreement(left[dataset.models == model], right[dataset.models == model])
            for model in sorted(set(dataset.models.tolist()))
        }
    return result


def joint_reference_scopes(
    candidate: np.ndarray, llama: np.ndarray, mixtral: np.ndarray, dataset: Dataset
) -> dict[str, Any]:
    def cell(mask: np.ndarray | slice) -> dict[str, Any]:
        left = candidate[mask]; first = llama[mask]; second = mixtral[mask]
        value = joint_reference_continuous_alpha_z(left, first, second)
        return {
            "n": int(len(left)), JOINT_ALPHA: value,
            "undefined_reason": None if value is not None else "constant_or_insufficient_column",
        }
    result: dict[str, Any] = {"pooled": cell(slice(None))}
    result["per_level"] = {
        level: cell(dataset.levels == level) for level in LEVELS
    }
    level_values = [result["per_level"][level][JOINT_ALPHA] for level in LEVELS]
    result["macro_within_level"] = {
        "n": dataset.item_count,
        JOINT_ALPHA: (
            float(np.mean(level_values)) if all(value is not None for value in level_values)
            else None
        ),
        "undefined_reason": (
            None if all(value is not None for value in level_values)
            else "one_or_more_level_metrics_undefined"
        ),
    }
    centered_value = joint_reference_continuous_alpha_z(
        center_within_items(candidate), center_within_items(llama), center_within_items(mixtral)
    )
    result["item_centered"] = {
        "n": dataset.n, JOINT_ALPHA: centered_value,
        "undefined_reason": None if centered_value is not None else "constant_or_insufficient_column",
    }
    result["by_domain"] = {
        domain: cell(dataset.domains == domain)
        for domain in sorted(set(dataset.domains.tolist()))
    }
    result["by_generation_model"] = {
        model: cell(dataset.models == model)
        for model in sorted(set(dataset.models.tolist()))
    }
    return result


def treatment_scopes(candidate: np.ndarray, dataset: Dataset) -> dict[str, Any]:
    treatment = dataset.values["treatment_ordinal"]
    result = agreement_scopes(candidate, treatment, dataset)
    for level in LEVELS:
        result["per_level"][level] = {
            "n": dataset.item_count, "rho": None, PAIRWISE_ALPHA: None,
            "undefined_reason": "reference_constant_within_level",
        }
    result["macro_within_level"] = {
        "n": dataset.item_count, "rho": None, PAIRWISE_ALPHA: None,
        "undefined_reason": "reference_constant_within_level",
    }
    candidate_items = candidate.reshape(-1, 5)
    label = np.asarray([5, 4, 3, 2, 1], dtype=np.float64)
    rhos: list[float] = []; taus: list[float] = []
    strict = 0; nonstrict = 0
    for row in candidate_items:
        rho = spearman_rho(row, label)
        tau = kendalltau(row, label, variant="b").statistic
        if rho is not None: rhos.append(rho)
        if tau is not None and math.isfinite(float(tau)): taus.append(float(tau))
        strict += int(bool(np.all(row[:-1] > row[1:])))
        nonstrict += int(bool(np.all(row[:-1] >= row[1:])))
    result["per_item_ordinal"] = {
        "items": dataset.item_count,
        "mean_per_item_spearman": float(np.mean(rhos)) if rhos else None,
        "finite_spearman_items": len(rhos),
        "mean_per_item_kendall_tau_b": float(np.mean(taus)) if taus else None,
        "finite_tau_b_items": len(taus),
        "strict_monotonic_items": strict,
        "strict_monotonic_rate": strict / dataset.item_count,
        "nonstrict_monotonic_items": nonstrict,
        "nonstrict_monotonic_rate": nonstrict / dataset.item_count,
    }
    return result


def select_ridge_alpha(scores: Sequence[Mapping[str, Any]]) -> float:
    if len(scores) != len(RIDGE_ALPHAS):
        raise AnalysisError("Ridge inner-score inventory differs")
    normalized: list[tuple[float, float]] = []
    for expected_alpha, entry in zip(RIDGE_ALPHAS, scores, strict=True):
        if set(entry) != {"alpha", "mse", "holdout_rows"}:
            raise AnalysisError("Ridge inner-score schema differs")
        alpha = finite_float(entry["alpha"], "Ridge alpha")
        mse = finite_float(entry["mse"], "Ridge MSE")
        holdout = entry["holdout_rows"]
        if alpha != expected_alpha or isinstance(holdout, bool) or not isinstance(holdout, int) or holdout <= 0:
            raise AnalysisError("Ridge inner-score value differs")
        normalized.append((alpha, mse))
    best_score = min(mse for _, mse in normalized)
    tolerance = 1e-12 + 1e-10 * abs(best_score)
    return max(alpha for alpha, mse in normalized if mse <= best_score + tolerance)


def nested_ridge_oof(
    x: np.ndarray, y: np.ndarray, dataset: Dataset,
    outer_map: Mapping[tuple[str, str, str], int],
    inner_maps: Sequence[Mapping[tuple[str, str, str], int]],
    *, feature_names: Sequence[str], model_label: str,
    outer_folds: Sequence[int] | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    try:
        from sklearn.linear_model import Ridge
        from sklearn.metrics import mean_absolute_error, r2_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise AnalysisError("scikit-learn Ridge/StandardScaler unavailable") from exc
    x = np.asarray(x, dtype=np.float64); y = np.asarray(y, dtype=np.float64)
    if x.ndim != 2 or y.shape != (dataset.n,) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise AnalysisError(f"{model_label}: invalid model arrays")
    oof = np.full(dataset.n, np.nan, dtype=np.float64)
    fits: list[dict[str, Any]] = []
    cluster_outer = np.asarray([outer_map[key] for key in dataset.cluster_keys], dtype=np.int8)
    row_outer = cluster_outer[dataset.cluster_index]
    requested_folds = tuple(range(5)) if outer_folds is None else tuple(int(value) for value in outer_folds)
    if not requested_folds or len(set(requested_folds)) != len(requested_folds) or any(value not in range(5) for value in requested_folds):
        raise AnalysisError(f"{model_label}: invalid requested outer folds")
    for outer_fold in requested_folds:
        test = row_outer == outer_fold; train = ~test
        inner_map = inner_maps[outer_fold]
        train_cluster_ids = np.flatnonzero(cluster_outer != outer_fold)
        inner_cluster_fold = np.full(len(dataset.cluster_keys), -1, dtype=np.int8)
        for cluster_id in train_cluster_ids:
            inner_cluster_fold[cluster_id] = inner_map[dataset.cluster_keys[int(cluster_id)]]
        inner_row_fold = inner_cluster_fold[dataset.cluster_index]
        inner_splits: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        for inner_fold in range(5):
            validation = train & (inner_row_fold == inner_fold)
            inner_train = train & (inner_row_fold != inner_fold)
            if not validation.any() or not inner_train.any():
                raise CoverageError(f"{model_label}: empty inner split")
            if set(dataset.cluster_index[validation].tolist()) & set(dataset.cluster_index[inner_train].tolist()):
                raise CoverageError(f"{model_label}: inner cluster leakage")
            inner_scaler = StandardScaler().fit(x[inner_train])
            inner_splits.append((
                inner_train, validation,
                inner_scaler.transform(x[inner_train]), inner_scaler.transform(x[validation]),
            ))
        scores: list[dict[str, Any]] = []
        for alpha in RIDGE_ALPHAS:
            squared_error_sum = 0.0; holdout_n = 0
            for inner_train, validation, scaled_train, scaled_validation in inner_splits:
                learner = Ridge(alpha=alpha, fit_intercept=True, solver="svd")
                learner.fit(scaled_train, y[inner_train])
                prediction = learner.predict(scaled_validation)
                squared_error_sum += float(np.square(y[validation] - prediction).sum())
                holdout_n += int(validation.sum())
            scores.append({"alpha": alpha, "mse": squared_error_sum / holdout_n, "holdout_rows": holdout_n})
        selected_alpha = select_ridge_alpha(scores)
        scaler = StandardScaler().fit(x[train])
        learner = Ridge(alpha=selected_alpha, fit_intercept=True, solver="svd")
        learner.fit(scaler.transform(x[train]), y[train])
        prediction = learner.predict(scaler.transform(x[test]))
        if not np.isfinite(prediction).all() or np.isfinite(oof[test]).any():
            raise AnalysisError(f"{model_label}: OOF coverage/finite failure")
        oof[test] = prediction
        fits.append({
            "model_label": model_label, "learner": "Ridge", "outer_fold": outer_fold,
            "feature_names": list(feature_names), "selected_alpha": selected_alpha,
            "inner_scores": scores,
            "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
            "coefficients_standardized": learner.coef_.tolist(), "intercept": float(learner.intercept_),
            "train_rows": int(train.sum()), "test_rows": int(test.sum()),
            "train_cluster_count": int(len(np.unique(dataset.cluster_index[train]))),
            "test_cluster_count": int(len(np.unique(dataset.cluster_index[test]))),
            "train_cluster_sha256": sha256_bytes(canonical_json_bytes([list(dataset.cluster_keys[i]) for i in sorted(set(dataset.cluster_index[train].tolist()))])),
            "test_cluster_sha256": sha256_bytes(canonical_json_bytes([list(dataset.cluster_keys[i]) for i in sorted(set(dataset.cluster_index[test].tolist()))])),
            "test_r2_auxiliary": float(r2_score(y[test], prediction)),
            "test_mae_auxiliary": float(mean_absolute_error(y[test], prediction)),
        })
    expected_rows = np.isin(row_outer, np.asarray(requested_folds, dtype=np.int8))
    if not np.isfinite(oof[expected_rows]).all() or np.isfinite(oof[~expected_rows]).any():
        raise AnalysisError(f"{model_label}: incomplete or out-of-scope OOF prediction")
    return oof, fits


def hgb_oof(
    x: np.ndarray, y: np.ndarray, dataset: Dataset,
    outer_map: Mapping[tuple[str, str, str], int], *, model_label: str,
    outer_folds: Sequence[int] | None = None,
) -> tuple[np.ndarray | None, list[dict[str, Any]], str]:
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
    except ImportError:
        return None, [], "skipped_unavailable"
    x = np.asarray(x, dtype=np.float64); y = np.asarray(y, dtype=np.float64)
    oof = np.full(dataset.n, np.nan, dtype=np.float64)
    fits: list[dict[str, Any]] = []
    cluster_outer = np.asarray([outer_map[key] for key in dataset.cluster_keys], dtype=np.int8)
    row_outer = cluster_outer[dataset.cluster_index]
    parameters = dict(
        loss="squared_error", learning_rate=0.05, max_iter=200,
        max_leaf_nodes=15, max_depth=None, min_samples_leaf=50,
        l2_regularization=1.0, max_bins=255, early_stopping=False,
        random_state=HGB_RANDOM_STATE,
    )
    requested_folds = tuple(range(5)) if outer_folds is None else tuple(int(value) for value in outer_folds)
    if not requested_folds or len(set(requested_folds)) != len(requested_folds) or any(value not in range(5) for value in requested_folds):
        raise AnalysisError(f"{model_label}: invalid requested outer folds")
    for fold in requested_folds:
        test = row_outer == fold; train = ~test
        learner = HistGradientBoostingRegressor(**parameters)
        learner.fit(x[train], y[train])
        prediction = learner.predict(x[test])
        if not np.isfinite(prediction).all():
            raise AnalysisError(f"{model_label}: HGB non-finite prediction")
        oof[test] = prediction
        train_clusters = sorted(set(dataset.cluster_index[train].tolist()))
        test_clusters = sorted(set(dataset.cluster_index[test].tolist()))
        fits.append({
            "model_label": model_label, "learner": "HistGradientBoostingRegressor",
            "outer_fold": fold, "parameters": parameters,
            "train_rows": int(train.sum()), "test_rows": int(test.sum()),
            "train_cluster_count": len(train_clusters), "test_cluster_count": len(test_clusters),
            "train_cluster_sha256": sha256_bytes(canonical_json_bytes([list(dataset.cluster_keys[i]) for i in train_clusters])),
            "test_cluster_sha256": sha256_bytes(canonical_json_bytes([list(dataset.cluster_keys[i]) for i in test_clusters])),
            "test_r2_auxiliary": float(r2_score(y[test], prediction)),
            "test_mae_auxiliary": float(mean_absolute_error(y[test], prediction)),
        })
    expected_rows = np.isin(row_outer, np.asarray(requested_folds, dtype=np.int8))
    if not np.isfinite(oof[expected_rows]).all() or np.isfinite(oof[~expected_rows]).any():
        raise AnalysisError(f"{model_label}: incomplete or out-of-scope HGB OOF prediction")
    return oof, fits, "complete"


def evaluator_ordering(dataset: Dataset) -> dict[str, Any]:
    llama = dataset.values["phi_actual_llama"].reshape(-1, 5)
    mixtral = dataset.values["phi_actual_mixtral"].reshape(-1, 5)
    ratio = dataset.values["R_actual"].reshape(-1, 5)
    output: dict[str, Any] = {}
    for family, pairs in (("all_ten", ALL_LEVEL_PAIRS), ("adjacent_four", ADJACENT_LEVEL_PAIRS)):
        records: dict[str, Any] = {}
        for high, low in pairs:
            i = LEVELS.index(high); j = LEVELS.index(low)
            dl = np.sign(llama[:, i] - llama[:, j])
            dm = np.sign(mixtral[:, i] - mixtral[:, j])
            dr = np.sign(ratio[:, i] - ratio[:, j])
            tied = (dl == 0) | (dm == 0)
            concordant = (~tied) & (dl == dm)
            discordant = (~tied) & (dl == -dm)
            consensus = concordant
            ratio_match = consensus & (dr == dl)
            ratio_reverse = consensus & (dr == -dl)
            ratio_tie = consensus & (dr == 0)
            non_tied = int((~tied).sum())
            consensus_n = int(consensus.sum())
            records[f"{high}-{low}"] = {
                "items": dataset.item_count,
                "concordant": int(concordant.sum()), "discordant": int(discordant.sum()),
                "tied_either_evaluator": int(tied.sum()),
                "inversion_rate_all": float(discordant.sum() / dataset.item_count),
                "inversion_rate_non_tie": float(discordant.sum() / non_tied) if non_tied else None,
                "R_on_evaluator_concordant_non_tied": {
                    "n": consensus_n, "same_sign": int(ratio_match.sum()),
                    "opposite_sign": int(ratio_reverse.sum()), "tied": int(ratio_tie.sum()),
                    "same_sign_rate": float(ratio_match.sum() / consensus_n) if consensus_n else None,
                },
            }
        output[family] = records
    output["strict_monotonicity"] = {
        "llama_items": int(np.all(llama[:, :-1] > llama[:, 1:], axis=1).sum()),
        "mixtral_items": int(np.all(mixtral[:, :-1] > mixtral[:, 1:], axis=1).sum()),
        "both_items": int((np.all(llama[:, :-1] > llama[:, 1:], axis=1) & np.all(mixtral[:, :-1] > mixtral[:, 1:], axis=1)).sum()),
        "denominator_items": dataset.item_count,
    }
    differences = dataset.values["evaluator_absolute_global_z_difference"]
    quantiles = [0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0]
    output["absolute_global_z_difference"] = {
        "definition": "abs(z_llama_global-z_mixtral_global)",
        "mean": float(differences.mean()), "sd_ddof1": float(differences.std(ddof=1)),
        "quantiles_linear": {format(q, ".2f"): float(np.quantile(differences, q, method="linear")) for q in quantiles},
        "by_level": {level: float(differences[dataset.levels == level].mean()) for level in LEVELS},
        "by_domain": {domain: float(differences[dataset.domains == domain].mean()) for domain in sorted(set(dataset.domains.tolist()))},
        "by_generation_model": {model: float(differences[dataset.models == model].mean()) for model in sorted(set(dataset.models.tolist()))},
        "subgroups_use_global_z_not_restandardized": True,
    }
    return output


def common_support(dataset: Dataset) -> dict[str, Any]:
    output_bytes = dataset.values["output_bytes"].reshape(-1, 5)
    records: dict[str, Any] = {}
    concordance: dict[str, Any] = {}
    previous_masks: dict[str, np.ndarray] = {}
    method_fields = (("R", "R_actual"), ("G", "G_raw_bits"),
                     ("Llama", "phi_actual_llama"), ("Mixtral", "phi_actual_mixtral"))
    for caliper in (1.10, 1.20, 1.30):
        caliper_key = format(caliper, ".2f")
        records[caliper_key] = {}
        pooled_candidates: dict[str, list[np.ndarray]] = {label: [] for label, _ in method_fields}
        pooled_labels: list[np.ndarray] = []
        centered_candidates: dict[str, list[np.ndarray]] = {label: [] for label, _ in method_fields}
        centered_labels: list[np.ndarray] = []
        for high, low in ADJACENT_LEVEL_PAIRS:
            i = LEVELS.index(high); j = LEVELS.index(low)
            ratio = np.maximum(output_bytes[:, i], output_bytes[:, j]) / np.minimum(output_bytes[:, i], output_bytes[:, j])
            mask = ratio <= caliper
            key = f"{high}-{low}"
            if key in previous_masks and np.any(previous_masks[key] & ~mask):
                raise CoverageError("common-support calipers are not nested")
            previous_masks[key] = mask
            item_rows = np.flatnonzero(mask)
            pair_rows = np.concatenate((item_rows * 5 + i, item_rows * 5 + j)) if len(item_rows) else np.empty(0, dtype=np.int64)
            clusters = np.unique(dataset.cluster_index[pair_rows]) if len(pair_rows) else np.empty(0, dtype=np.int32)
            domains = Counter(dataset.domains[item_rows * 5].tolist())
            models = Counter(dataset.models[item_rows * 5].tolist())
            methods: dict[str, Any] = {}
            pair_label_matrix = np.tile(
                np.asarray([LEVEL_VALUE[high], LEVEL_VALUE[low]], dtype=np.float64),
                (len(item_rows), 1),
            )
            pooled_labels.append(pair_label_matrix.reshape(-1))
            centered_labels.append(
                (pair_label_matrix - pair_label_matrix.mean(axis=1, keepdims=True)).reshape(-1)
            )
            for label, field in method_fields:
                matrix = dataset.values[field].reshape(-1, 5)
                pair_matrix = matrix[item_rows][:, [i, j]]
                difference = pair_matrix[:, 0] - pair_matrix[:, 1]
                pooled_candidates[label].append(pair_matrix.reshape(-1))
                centered_candidates[label].append(
                    (pair_matrix - pair_matrix.mean(axis=1, keepdims=True)).reshape(-1)
                )
                methods[label] = {
                    "n": int(len(difference)), "mean_higher_minus_lower": float(difference.mean()) if len(difference) else None,
                    "median_higher_minus_lower": float(np.median(difference)) if len(difference) else None,
                    "expected": int((difference > 0).sum()), "reverse": int((difference < 0).sum()), "tie": int((difference == 0).sum()),
                    "expected_rate": float((difference > 0).mean()) if len(difference) else None,
                    "reverse_rate": float((difference < 0).mean()) if len(difference) else None,
                    "tie_rate": float((difference == 0).mean()) if len(difference) else None,
                }
            records[caliper_key][key] = {
                "retained_model_item_pairs": int(len(item_rows)),
                "source_clusters": int(len(clusters)),
                "domain_items": dict(sorted(domains.items())),
                "generation_model_items": dict(sorted(models.items())),
                "methods": methods,
            }
        pooled_treatment = np.concatenate(pooled_labels)
        centered_treatment = np.concatenate(centered_labels)
        concordance[caliper_key] = {}
        for label, _ in method_fields:
            concordance[caliper_key][label] = {
                "pooled": paired_agreement(
                    np.concatenate(pooled_candidates[label]), pooled_treatment
                ),
                "adjacent_pair_centered": paired_agreement(
                    np.concatenate(centered_candidates[label]), centered_treatment
                ),
            }
    all_ratio = output_bytes.max(axis=1) / output_bytes.min(axis=1)
    all_mask = all_ratio <= 1.25
    item_rows = np.flatnonzero(all_mask)
    rows = item_rows * 5
    all_pair_rows = (
        np.concatenate([item_rows * 5 + i for i in range(5)])
        if all_mask.any() else np.empty(0, dtype=np.int64)
    )
    clusters = np.unique(dataset.cluster_index[all_pair_rows]) if len(all_pair_rows) else np.empty(0, dtype=np.int32)
    domains = Counter(dataset.domains[rows].tolist()); models = Counter(dataset.models[rows].tolist())
    low_reasons: list[str] = []
    if int(all_mask.sum()) < 1123: low_reasons.append("items_below_1123")
    if len(clusters) < 256: low_reasons.append("clusters_below_256")
    if set(domains) != set(EXPECTED_DOMAIN_ITEMS): low_reasons.append("domain_absent")
    if set(models) != set(EXPECTED_MODEL_ITEMS): low_reasons.append("generation_model_absent")
    all_five_inference: dict[str, Any] | None = None
    if not low_reasons:
        treatment_labels = np.tile(np.asarray([5, 4, 3, 2, 1], dtype=np.float64), len(item_rows))
        all_five_inference = {}
        for label, field in method_fields:
            candidate = dataset.values[field].reshape(-1, 5)[item_rows].reshape(-1)
            all_five_inference[label] = {
                "pooled": paired_agreement(candidate, treatment_labels),
                "item_centered": paired_agreement(
                    center_within_items(candidate), center_within_items(treatment_labels)
                ),
            }
    return {
        "adjacent_byte_calipers": records,
        "adjacent_treatment_concordance": concordance,
        "nesting_asserted": True,
        "all_five_byte_1.25": {
            "items": int(all_mask.sum()), "clusters": int(len(clusters)),
            "domain_items": dict(sorted(domains.items())), "generation_model_items": dict(sorted(models.items())),
            "low_support": bool(low_reasons), "low_support_reasons": low_reasons,
            "inference_policy": "coverage_only" if low_reasons else "full_exploratory_inference",
            "inference": all_five_inference,
        },
    }


def replicate_seed(replicate: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{BOOTSTRAP_SEED}\0{replicate}".encode("ascii")).digest()[:8], "big"
    )


def bootstrap_draw(replicate: int, cluster_count: int = EXPECTED_CLUSTERS) -> np.ndarray:
    rng = np.random.default_rng(replicate_seed(replicate))
    return rng.integers(0, cluster_count, size=cluster_count, dtype=np.int32)


def bootstrap_draw_sequence_sha256(cluster_count: int = EXPECTED_CLUSTERS, replicates: int = BOOTSTRAP_REPLICATES) -> str:
    digest = hashlib.sha256()
    for replicate in range(replicates):
        digest.update(bootstrap_draw(replicate, cluster_count).tobytes())
    return digest.hexdigest()


def bootstrap_cluster_indices(dataset: Dataset, draw: np.ndarray) -> np.ndarray:
    return np.concatenate([dataset.cluster_rows[int(index)] for index in draw])


def percentile_summary(values: np.ndarray, point: float | None, *, minimum_finite: int = 1980) -> dict[str, Any]:
    series = np.asarray(values, dtype=np.float64)
    finite = series[np.isfinite(series)]
    if len(finite) < minimum_finite:
        interval = {"lower": None, "upper": None}
        reason = "insufficient_bootstrap_support"
    else:
        interval = {
            "lower": float(np.percentile(finite, 2.5, method="linear")),
            "upper": float(np.percentile(finite, 97.5, method="linear")),
        }
        reason = None
    return {
        "point": point, "ci_95_percentile": interval,
        "finite_resamples": int(len(finite)), "undefined_resamples": int(len(series) - len(finite)),
        "undefined_reason": reason,
    }


def classify_intervals(cells: Sequence[Mapping[str, Any]]) -> str:
    bounds = [(cell.get("ci_95_percentile", {}).get("lower"), cell.get("ci_95_percentile", {}).get("upper")) for cell in cells]
    if bounds and all(lower is not None and lower > 0.0 for lower, _ in bounds):
        return "stable_positive"
    if bounds and all(upper is not None and upper < 0.0 for _, upper in bounds):
        return "stable_negative"
    return "mixed_or_inconclusive"


def checkpoint_array_descriptor(arrays: Mapping[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    return {
        key: {"dtype": np.asarray(value).dtype.str, "shape": list(np.asarray(value).shape)}
        for key, value in sorted(arrays.items())
    }


def checkpoint_payload_sha256(arrays: Mapping[str, np.ndarray]) -> str:
    return sha256_bytes(canonical_json_bytes({
        key: array_sha256(np.asarray(value)) for key, value in sorted(arrays.items())
    }))


def deterministic_npz_bytes(arrays: Mapping[str, np.ndarray], metadata: Mapping[str, Any]) -> bytes:
    payload = {key: np.asarray(value) for key, value in arrays.items()}
    if "metadata_json" in payload:
        raise AnalysisError("metadata_json is reserved")
    payload["metadata_json"] = np.asarray(canonical_json_bytes(metadata).decode("utf-8"))
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for key in sorted(payload):
            array_buffer = io.BytesIO()
            np.lib.format.write_array(array_buffer, payload[key], allow_pickle=False)
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, array_buffer.getvalue())
    return output.getvalue()


def validate_deterministic_npz_file(
    path: str | Path, arrays: Mapping[str, np.ndarray], metadata: Mapping[str, Any],
) -> None:
    target = Path(path)
    expected = deterministic_npz_bytes(arrays, metadata)
    digest, size = file_fingerprint(target)
    if size != len(expected) or digest != sha256_bytes(expected):
        raise AnalysisError(f"checkpoint is not byte-identical deterministic NPZ: {target}")


def write_npz_atomic(path: str | Path, arrays: Mapping[str, np.ndarray], metadata: Mapping[str, Any]) -> dict[str, Any]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload_arrays = {key: np.asarray(value) for key, value in arrays.items()}
    if "metadata_json" in payload_arrays or not payload_arrays:
        raise AnalysisError("invalid checkpoint array inventory")
    expected_descriptor = checkpoint_array_descriptor(payload_arrays)
    expected_payload = checkpoint_payload_sha256(payload_arrays)
    if metadata.get("schema") not in CHECKPOINT_SCHEMAS:
        raise AnalysisError(f"unknown checkpoint schema: {metadata.get('schema')}")
    if metadata.get("arrays") != expected_descriptor or metadata.get("payload_sha256") != expected_payload:
        raise AnalysisError("checkpoint metadata does not bind exact arrays")
    if path_lexists(destination):
        receipt = file_record(destination, destination.parent)
        with open_plain_binary(destination) as checkpoint_handle:
            with np.load(checkpoint_handle, allow_pickle=False) as stored:
                if set(stored.files) != {*payload_arrays, "metadata_json"}:
                    raise AnalysisError(f"checkpoint array inventory differs: {destination}")
                stored_metadata = strict_json_loads(str(stored["metadata_json"].item()), f"{destination}.metadata")
                if stored_metadata != dict(metadata):
                    raise AnalysisError(f"checkpoint metadata differs: {destination}")
                stored_arrays = {key: np.asarray(stored[key]) for key in payload_arrays}
                if checkpoint_array_descriptor(stored_arrays) != expected_descriptor:
                    raise AnalysisError(f"checkpoint array descriptors differ: {destination}")
                if checkpoint_payload_sha256(stored_arrays) != expected_payload:
                    raise AnalysisError(f"checkpoint payload differs: {destination}")
                for key, expected in payload_arrays.items():
                    actual = stored_arrays[key]
                    same_values = (
                        np.array_equal(actual, expected, equal_nan=True)
                        if actual.dtype.kind in "fc" else np.array_equal(actual, expected)
                    )
                    if actual.dtype != expected.dtype or actual.shape != expected.shape or not same_values:
                        raise AnalysisError(f"checkpoint array differs: {destination}:{key}")
        validate_deterministic_npz_file(destination, stored_arrays, stored_metadata)
        return receipt
    atomic_write_bytes(destination, deterministic_npz_bytes(payload_arrays, metadata), identical_ok=False)
    return file_record(destination, destination.parent)


class ResourceMonitor:
    def __init__(self, hard_limit: int = RSS_HARD_LIMIT, interval_seconds: float = 0.05):
        self.hard_limit = hard_limit
        self.interval_seconds = interval_seconds
        self.baseline = 0; self.peak = 0; self.phase = "initial"; self.phase_peaks: dict[str, int] = {}
        self._stop = threading.Event(); self._failure = threading.Event(); self._thread: threading.Thread | None = None
        self.backend = "unknown"; self._closed = False
        self._heap_current = 0; self._heap_peak = 0

    def _rss(self) -> int:
        try:
            import psutil
            self.backend = "psutil"
            return int(psutil.Process().memory_info().rss)
        except ImportError:
            if os.name != "nt":
                return 0
            import ctypes
            from ctypes import wintypes
            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            counters = PMC(); counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return 0
            self.backend = "win32_ctypes"
            return int(counters.WorkingSetSize)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            rss = self._rss(); self.peak = max(self.peak, rss)
            self.phase_peaks[self.phase] = max(self.phase_peaks.get(self.phase, 0), rss)
            if rss > self.hard_limit:
                self._failure.set(); return

    def __enter__(self) -> "ResourceMonitor":
        self.baseline = self._rss(); self.peak = self.baseline
        tracemalloc.start(); self._thread = threading.Thread(target=self._run, daemon=True); self._thread.start()
        return self

    def set_phase(self, phase: str) -> None:
        self.check(); self.phase = phase

    def check(self) -> None:
        if self._failure.is_set():
            raise ResourceLimitError(f"RSS exceeded hard limit {self.hard_limit}")

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                self._failure.set()
        # A final synchronous sample closes the race between the sampling thread
        # and receipt/publication creation.
        rss = self._rss()
        self.peak = max(self.peak, rss)
        self.phase_peaks[self.phase] = max(self.phase_peaks.get(self.phase, 0), rss)
        if rss > self.hard_limit:
            self._failure.set()
        if tracemalloc.is_tracing():
            self._heap_current, self._heap_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        self._closed = True
        if self._failure.is_set():
            raise ResourceLimitError(f"RSS exceeded hard limit {self.hard_limit}")

    def receipt(self) -> dict[str, Any]:
        if not self._closed:
            raise AnalysisError("resource receipt requested before monitor closed")
        return {
            "rss_backend": self.backend, "rss_baseline_bytes": self.baseline,
            "rss_peak_bytes": self.peak, "rss_incremental_peak_bytes": max(0, self.peak - self.baseline),
            "phase_rss_peaks_bytes": dict(sorted(self.phase_peaks.items())),
            "tracemalloc_current_bytes": self._heap_current, "tracemalloc_peak_bytes": self._heap_peak,
            "rss_target_bytes": RSS_TARGET, "rss_hard_limit_bytes": self.hard_limit,
            "rss_limit_semantics": "sampled_process_rss_hard_limit",
            "rss_sampling_interval_milliseconds": int(round(self.interval_seconds * 1000.0)),
            "synchronous_exit_rss_sample": True,
        }


def environment_receipt() -> dict[str, Any]:
    import scipy
    receipt: dict[str, Any] = {
        "python": platform.python_version(), "platform": platform.platform(),
        "numpy": np.__version__, "scipy": scipy.__version__,
    }
    try:
        import sklearn
        receipt["scikit_learn"] = sklearn.__version__
    except ImportError:
        receipt["scikit_learn"] = None
    try:
        import pandas
        receipt["pandas"] = pandas.__version__
    except ImportError:
        receipt["pandas"] = None
    return receipt


def forbidden_identifier_findings(value: Any, *, path: str = "root") -> list[str]:
    """Scan structured identifiers, never narrative prose values.

    Mapping keys are identifiers.  String list elements and scalar values are
    scanned only under fields that explicitly carry identifiers.  This permits
    required limitation prose such as "no counterfactual-derived quantity" while
    rejecting forbidden analytic columns/metrics.
    """
    findings: list[str] = []
    identifier_fields = {
        "path", "schema", "family", "candidate", "reference", "scope", "metric",
        "model_label", "feature_names", "metric_keys", "direct_candidates",
        "predictor", "target", "comparison", "estimand",
    }

    def check(text: str, location: str) -> None:
        lowered = text.casefold().replace("-", "_")
        for token in FORBIDDEN_IDENTIFIER_TOKENS:
            if token in lowered:
                findings.append(f"{location}: {token}")

    def visit(child: Any, location: str, scan_string: bool = False) -> None:
        if isinstance(child, Mapping):
            for key, grandchild in child.items():
                check(str(key), f"{location}.<key>")
                visit(grandchild, f"{location}.{key}", str(key) in identifier_fields)
        elif isinstance(child, (list, tuple)):
            for index, grandchild in enumerate(child):
                visit(grandchild, f"{location}[{index}]", scan_string)
        elif scan_string and isinstance(child, str):
            check(child, location)

    visit(value, path)
    return findings


def forbidden_text_identifier_findings(text: str, *, path: str) -> list[str]:
    """Scan table cells and backtick identifiers, excluding prose sentences."""
    findings: list[str] = []
    candidates: list[str] = re.findall(r"`([^`]+)`", text)
    for line in text.splitlines():
        if line.startswith("|"):
            candidates.extend(cell.strip() for cell in line.strip("|").split("|"))
    for value in candidates:
        normalized = value.casefold().replace("-", "_")
        for token in FORBIDDEN_IDENTIFIER_TOKENS:
            if token in normalized:
                findings.append(f"{path}: {token}: {value}")
    return findings


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    x = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.int64)
    if x.shape != w.shape or x.ndim != 1 or np.any(w < 0) or not np.isfinite(x).all():
        raise AnalysisError("invalid weighted-median input")
    total = int(w.sum())
    if total == 0:
        return None
    order = np.argsort(x, kind="mergesort")
    ordered = x[order]; cumulative = np.cumsum(w[order], dtype=np.int64)
    # Exact NumPy median semantics for an integer-frequency expansion.
    lower_rank = (total - 1) // 2
    upper_rank = total // 2
    lower = ordered[int(np.searchsorted(cumulative, lower_rank + 1, side="left"))]
    upper = ordered[int(np.searchsorted(cumulative, upper_rank + 1, side="left"))]
    return float((lower + upper) / 2.0)


def validate_frozen_run_config(config: Mapping[str, Any], *, bundle_id: str) -> None:
    expected_top = {
        "schema", "schema_version", "state", "bundle_id", "created_at_utc", "estimand",
        "authority", "coverage", "keys", "raw_algebra", "direct_candidates",
        "frozen_strongest", "folds", "learners", "predictor_sets",
        "length_residualization", "consensus", "agreement", "evaluator_sensitivity",
        "common_support", "bootstrap", "classification", "resources", "prohibitions",
        "code_snapshot", "config_payload_sha256_excluding_this_field",
    }
    if set(config) != expected_top:
        raise AnalysisError(f"run_config exact schema differs: {sorted(set(config) ^ expected_top)}")
    verify_payload_hash(config, "config_payload_sha256_excluding_this_field")
    if (
        config.get("schema") != "actual_incremental_sensitivity.run_config"
        or config.get("schema_version") != 1
        or config.get("state") != "frozen_before_formal_statistics"
        or config.get("bundle_id") != bundle_id
        or config.get("coverage") != {
            "pairs": EXPECTED_PAIRS, "items": EXPECTED_ITEMS,
            "source_clusters": EXPECTED_CLUSTERS, "levels": list(LEVELS),
        }
        or config.get("direct_candidates") != list(DIRECT_CANDIDATES)
    ):
        raise AnalysisError("run_config frozen identity/coverage differs")
    folds = config.get("folds", {})
    bootstrap = config.get("bootstrap", {})
    resources = config.get("resources", {})
    if (
        folds.get("outer") != 5 or folds.get("inner") != 5
        or folds.get("outer_seed") != OUTER_SEED
        or folds.get("inner_master_seed") != INNER_MASTER_SEED
        or bootstrap.get("replicates") != BOOTSTRAP_REPLICATES
        or bootstrap.get("seed") != BOOTSTRAP_SEED
        or bootstrap.get("block_size") != BOOTSTRAP_BLOCK_SIZE
        or bootstrap.get("draw_sequence_sha256") != EXPECTED_DRAW_SHA256
        or resources.get("rss_hard_limit_bytes") != RSS_HARD_LIMIT
        or config.get("length_residualization", {}).get("targets") != list(LENGTH_TARGETS)
        or config.get("length_residualization", {}).get("specifications") != list(LENGTH_SPECS)
    ):
        raise AnalysisError("run_config frozen design differs")
    predictors = config.get("predictor_sets", {})
    auxiliary = predictors.get("auxiliary_strongest_single", {})
    selected_single = config.get("frozen_strongest", {}).get("strongest_single_heuristic", {})
    if (
        predictors.get("primary_sets") != list(PREDICTOR_SETS)
        or auxiliary.get("set_name") != AUXILIARY_PREDICTOR_SET
        or auxiliary.get("status") != "auxiliary_not_one_of_six_primary_sets"
        or auxiliary.get("feature") != selected_single.get("selected")
        or auxiliary.get("selection_source") != selected_single.get("selected_metric_id")
    ):
        raise AnalysisError("run_config predictor inventory differs")
    ridge = config.get("learners", {}).get("ridge", {})
    hgb = config.get("learners", {}).get("hist_gradient_boosting", {})
    if ridge.get("alphas") != list(RIDGE_ALPHAS) or ridge.get("solver") != "svd" or ridge.get("fit_intercept") is not True:
        raise AnalysisError("run_config Ridge specification differs")
    expected_hgb = {
        "loss": "squared_error", "learning_rate": 0.05, "max_iter": 200,
        "max_leaf_nodes": 15, "max_depth": None, "min_samples_leaf": 50,
        "l2_regularization": 1.0, "max_bins": 255, "early_stopping": False,
        "random_state": HGB_RANDOM_STATE, "tuning": False,
    }
    if hgb != expected_hgb:
        raise AnalysisError("run_config HGB specification differs")


__all__ = [name for name in globals() if not name.startswith("_")]
