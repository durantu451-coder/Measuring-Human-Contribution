# -*- coding: utf-8 -*-
"""Durable storage primitives for Experiment B.

The module is deliberately independent of the experiment runners so migration can
be staged without weakening their current resume rules.  All writes use canonical
UTF-8 JSON, binary newlines, file ``fsync``, and (where applicable) atomic replace.
JSONL recovery is intentionally conservative: only one malformed, unterminated
final fragment may be quarantined; every other defect aborts the scan.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping


PathLike = str | os.PathLike[str]
Validator = Callable[[Any], Any]
IdGetter = Callable[[Any], Any]

PAUSE_SENTINEL_NAME = "PAUSED"
MIGRATION_SENTINEL_NAME = "MIGRATION_IN_PROGRESS"
LOCK_DIR_NAME = ".locks"
MAINTENANCE_LOCK_NAME = "maintenance.lock"
_SCOPE_LOCK_SUFFIX = ".scope.lock"


# ═══════════════════════════════════════════════════════════════════════════════
# Errors
# ═══════════════════════════════════════════════════════════════════════════════

class StorageError(RuntimeError):
    """Base class for Experiment B storage failures."""


class CanonicalJsonError(ValueError):
    """A value cannot be represented as strict canonical JSON."""


class JsonlError(StorageError):
    """Base class for strict JSONL scan failures."""


class InvalidUtf8Error(JsonlError):
    """A JSONL file is not strict UTF-8."""


class BlankJsonlLineError(JsonlError):
    """A JSONL file contains a blank physical row."""


class MalformedJsonlError(JsonlError):
    """A JSONL row is not strict JSON."""


class DuplicateJsonKeyError(MalformedJsonlError):
    """A JSON object repeats a key."""


class JsonlValidationError(JsonlError):
    """A parsed row fails the caller-supplied validator."""


class MissingRowIdError(JsonlError):
    """A JSONL row has no valid unique identifier."""


class DuplicateRowIdError(JsonlError):
    """An identical row identifier appears more than once."""


class ConflictingRowIdError(JsonlError):
    """One row identifier maps to different canonical row content."""


class UnterminatedJsonlError(JsonlError):
    """A JSONL file does not end at a newline boundary."""


class AtomicWriteError(StorageError):
    """An atomic replacement could not be completed."""


class BackupVerificationError(StorageError):
    """A backup does not exactly match its stable source."""


class LockError(StorageError):
    """Base class for process-lock failures."""


class LockHeldError(LockError):
    """A live process already owns a lock."""


class InvalidLockError(LockError):
    """A lock file has no trustworthy owner record."""


class LockOwnershipError(LockError):
    """The releasing process no longer owns the on-disk lock token."""


class SentinelError(StorageError):
    """A storage sentinel prevents ordinary writes."""


class ExperimentPausedError(SentinelError):
    """The Experiment B PAUSED sentinel is present."""


class MigrationInProgressError(SentinelError):
    """A migration sentinel or maintenance lock is active."""


class ScopeLocksActiveError(LockError):
    """Maintenance cannot start while one or more scopes are active."""


# ═══════════════════════════════════════════════════════════════════════════════
# Canonical JSON and hashes
# ═══════════════════════════════════════════════════════════════════════════════

def canonical_json_text(value: Any) -> str:
    """Return deterministic compact JSON with Unicode preserved and NaN banned."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalJsonError(f"value is not strict canonical JSON: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical JSON encoded as strict UTF-8 (without a newline)."""
    return canonical_json_text(value).encode("utf-8")


def canonical_jsonl_row_bytes(value: Any) -> bytes:
    """Return one canonical UTF-8 JSONL row, including exactly one LF."""
    return canonical_json_bytes(value) + b"\n"


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_row_sha256(value: Any) -> str:
    """Hash a row's canonical JSON bytes (the JSONL delimiter is excluded)."""
    return sha256_bytes(canonical_json_bytes(value))


def file_sha256(path: PathLike, *, chunk_size: int = 1024 * 1024) -> str:
    """Stream a file and return its SHA-256 hex digest."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Familiar aliases for callers that prefer noun-first names.
canonical_dumps = canonical_json_text
row_sha256 = canonical_row_sha256
sha256_file = file_sha256


# ═══════════════════════════════════════════════════════════════════════════════
# Atomic durable replacement
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AtomicWriteResult:
    path: Path
    sha256: str
    size: int


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        try:
            count = os.write(fd, view[written:])
        except InterruptedError:
            continue
        if count <= 0:
            raise OSError("zero-byte write before payload completion")
        written += count


def fsync_directory(directory: PathLike) -> bool:
    """Best-effort directory fsync; return whether it was supported and worked.

    Windows normally refuses opening directories through ``os.open``.  The file
    itself and the replacement are still durable there; inability to sync the
    directory entry is intentionally non-fatal.
    """
    directory = Path(directory)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(directory, flags)
    except (OSError, TypeError):
        return False
    try:
        os.fsync(fd)
    except OSError:
        return False
    finally:
        os.close(fd)
    return True


def _atomic_replace_chunks(
    path: PathLike,
    chunks: Iterable[bytes],
) -> AtomicWriteResult:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = -1
    temporary: Path | None = None
    digest = hashlib.sha256()
    size = 0
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        for chunk in chunks:
            if not isinstance(chunk, bytes):
                raise TypeError("atomic replacement chunks must be bytes")
            if not chunk:
                continue
            _write_all(fd, chunk)
            digest.update(chunk)
            size += len(chunk)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, destination)
        temporary = None
        fsync_directory(destination.parent)
    except Exception as exc:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, (CanonicalJsonError, TypeError)):
            raise
        raise AtomicWriteError(f"could not atomically replace {destination}: {exc}") from exc
    return AtomicWriteResult(destination, digest.hexdigest(), size)


def atomic_replace_bytes(path: PathLike, data: bytes) -> AtomicWriteResult:
    """Durably replace a file with bytes through a unique sibling temp file."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return _atomic_replace_chunks(path, (data,))


def atomic_replace_json(path: PathLike, value: Any) -> AtomicWriteResult:
    """Durably replace a file with canonical compact JSON (no trailing LF)."""
    return atomic_replace_bytes(path, canonical_json_bytes(value))


def atomic_replace_jsonl(
    path: PathLike,
    rows: Iterable[Any],
) -> AtomicWriteResult:
    """Durably replace a file with canonical JSONL rows and final LF."""
    return _atomic_replace_chunks(
        path,
        (canonical_jsonl_row_bytes(row) for row in rows),
    )


atomic_write_bytes = atomic_replace_bytes
atomic_write_json = atomic_replace_json
atomic_write_jsonl = atomic_replace_jsonl


# ═══════════════════════════════════════════════════════════════════════════════
# Fsynced JSONL append
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AppendResult:
    path: Path
    row_sha256: str
    bytes_written: int
    file_size: int


def append_jsonl_row(path: PathLike, row: Any) -> AppendResult:
    """Append one canonical row, refusing a non-newline-aligned existing file.

    The boundary check and append happen on the same descriptor.  Cross-process
    callers must additionally hold the appropriate :class:`ProcessLock`.
    """
    destination = Path(path)
    payload = canonical_jsonl_row_bytes(row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    fd = os.open(destination, flags, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size:
            os.lseek(fd, -1, os.SEEK_END)
            if os.read(fd, 1) != b"\n":
                raise UnterminatedJsonlError(
                    f"refusing append: {destination} does not end with LF"
                )
        _write_all(fd, payload)
        os.fsync(fd)
        final_size = os.fstat(fd).st_size
    finally:
        os.close(fd)
    return AppendResult(
        destination,
        sha256_bytes(payload[:-1]),
        len(payload),
        final_size,
    )


append_jsonl = append_jsonl_row


# ═══════════════════════════════════════════════════════════════════════════════
# Strict JSONL scanning and conservative tail repair
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class JsonlRow:
    line_number: int
    byte_offset: int
    value: Any
    row_sha256: str
    item_id: str | None


@dataclass(frozen=True)
class TailQuarantine:
    path: Path
    manifest_path: Path
    sha256: str
    size: int
    byte_offset: int
    original_file_sha256: str


@dataclass(frozen=True)
class JsonlScanResult:
    path: Path
    entries: tuple[JsonlRow, ...]
    ids: frozenset[str]
    id_hashes: Mapping[str, str]
    file_sha256: str
    normalized_final_newline: bool = False
    quarantine: TailQuarantine | None = None

    @property
    def rows(self) -> tuple[Any, ...]:
        """Parsed row values, in file order."""
        return tuple(entry.value for entry in self.entries)

    @property
    def records(self) -> tuple[Any, ...]:
        """Alias for :attr:`rows`."""
        return self.rows

    @property
    def repaired_tail(self) -> bool:
        return self.quarantine is not None

    def __len__(self) -> int:
        return len(self.entries)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r} is forbidden")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJsonKeyError(f"duplicate JSON object key {key!r}")
        value[key] = item
    return value


def _strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_json_constant,
    )


def _utc_stamp(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _unique_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    while candidate.exists():
        candidate = directory / f"{name}.{secrets.token_hex(4)}"
    return candidate


def _quarantine_tail(
    source: Path,
    fragment: bytes,
    byte_offset: int,
    original_hash: str,
    quarantine_dir: Path | None,
) -> TailQuarantine:
    directory = quarantine_dir or source.parent / "quarantine"
    directory.mkdir(parents=True, exist_ok=True)
    fragment_hash = sha256_bytes(fragment)
    stamp = _utc_stamp()
    name = (
        f"{source.name}.tail-{stamp}-{fragment_hash[:16]}.quarantine.bin"
    )
    quarantine_path = _unique_path(directory, name)
    atomic_replace_bytes(quarantine_path, fragment)
    if file_sha256(quarantine_path) != fragment_hash:
        quarantine_path.unlink(missing_ok=True)
        raise BackupVerificationError(
            f"tail quarantine verification failed for {quarantine_path}"
        )

    manifest_path = Path(str(quarantine_path) + ".json")
    manifest = {
        "byte_offset": byte_offset,
        "fragment_sha256": fragment_hash,
        "fragment_size": len(fragment),
        "original_file_sha256": original_hash,
        "quarantined_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source.resolve()),
    }
    atomic_replace_json(manifest_path, manifest)
    return TailQuarantine(
        quarantine_path,
        manifest_path,
        fragment_hash,
        len(fragment),
        byte_offset,
        original_hash,
    )


def _extract_row_id(
    value: Any,
    *,
    id_getter: IdGetter | None,
    id_field: str,
    require_ids: bool,
    path: Path,
    line_number: int,
) -> str | None:
    if id_getter is not None:
        try:
            item_id = id_getter(value)
        except Exception as exc:
            raise MissingRowIdError(
                f"could not extract row ID at {path}:{line_number}: {exc}"
            ) from exc
    elif isinstance(value, dict):
        item_id = value.get(id_field)
    else:
        item_id = None

    if item_id is None and not require_ids:
        return None
    if not isinstance(item_id, str) or not item_id:
        raise MissingRowIdError(
            f"missing non-empty string {id_field!r} at {path}:{line_number}"
        )
    return item_id


def scan_jsonl(
    path: PathLike,
    *,
    validator: Validator | None = None,
    id_getter: IdGetter | None = None,
    id_field: str = "id",
    require_ids: bool = True,
    repair: bool = True,
    quarantine_dir: PathLike | None = None,
) -> JsonlScanResult:
    """Strictly scan JSONL, validate rows, and enforce unique IDs.

    ``validator`` is called once with each parsed row; it may raise or return
    ``False`` to reject the row.  With ``repair=True`` (the default), a valid
    final row lacking LF is normalized, while a malformed unterminated final
    fragment is saved byte-for-byte with a SHA-256 manifest and removed.  Blank
    rows, malformed middle rows, newline-terminated malformed rows, semantic
    validation errors, duplicate/conflicting IDs, and invalid UTF-8 are never
    repaired.
    """
    source = Path(path)
    if not source.exists():
        empty_hash = sha256_bytes(b"")
        return JsonlScanResult(source, (), frozenset(), {}, empty_hash)

    data = source.read_bytes()
    original_hash = sha256_bytes(data)
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidUtf8Error(
            f"invalid UTF-8 at {source}, byte {exc.start}: {exc.reason}"
        ) from exc

    terminated = data.endswith(b"\n")
    physical_lines = data.split(b"\n")
    if terminated:
        physical_lines.pop()  # delimiter after the final row, not a blank row
    if not data:
        physical_lines = []

    entries: list[JsonlRow] = []
    id_hashes: dict[str, str] = {}
    offset = 0
    quarantine: TailQuarantine | None = None

    for index, raw_line in enumerate(physical_lines):
        line_number = index + 1
        is_unterminated_tail = not terminated and index == len(physical_lines) - 1
        if not raw_line.strip():
            raise BlankJsonlLineError(f"blank JSONL row at {source}:{line_number}")

        text = raw_line.decode("utf-8")
        try:
            value = _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError, DuplicateJsonKeyError) as exc:
            if is_unterminated_tail and repair:
                quarantine = _quarantine_tail(
                    source,
                    raw_line,
                    offset,
                    original_hash,
                    Path(quarantine_dir) if quarantine_dir is not None else None,
                )
                atomic_replace_bytes(source, data[:offset])
                break
            location = "unterminated final" if is_unterminated_tail else ""
            qualifier = f" {location}" if location else ""
            raise MalformedJsonlError(
                f"malformed{qualifier} JSONL row at {source}:{line_number}: {exc}"
            ) from exc

        if validator is not None:
            try:
                validation_result = validator(value)
            except Exception as exc:
                raise JsonlValidationError(
                    f"row validation failed at {source}:{line_number}: {exc}"
                ) from exc
            if validation_result is False:
                raise JsonlValidationError(
                    f"row validation returned False at {source}:{line_number}"
                )

        item_id = _extract_row_id(
            value,
            id_getter=id_getter,
            id_field=id_field,
            require_ids=require_ids,
            path=source,
            line_number=line_number,
        )
        digest = canonical_row_sha256(value)
        if item_id is not None and item_id in id_hashes:
            first_hash = id_hashes[item_id]
            if first_hash == digest:
                raise DuplicateRowIdError(
                    f"duplicate ID {item_id!r} at {source}:{line_number}"
                )
            raise ConflictingRowIdError(
                f"conflicting ID {item_id!r} at {source}:{line_number}: "
                f"{first_hash} != {digest}"
            )
        if item_id is not None:
            id_hashes[item_id] = digest
        entries.append(JsonlRow(line_number, offset, value, digest, item_id))
        offset += len(raw_line) + 1

    normalized = False
    if quarantine is None and data and not terminated:
        if not repair:
            raise UnterminatedJsonlError(
                f"valid final JSONL row lacks LF at {source}:{len(physical_lines)}"
            )
        atomic_replace_bytes(source, data + b"\n")
        normalized = True

    return JsonlScanResult(
        source,
        tuple(entries),
        frozenset(id_hashes),
        dict(id_hashes),
        file_sha256(source),
        normalized,
        quarantine,
    )


strict_scan_jsonl = scan_jsonl


# ═══════════════════════════════════════════════════════════════════════════════
# Verified timestamped backups
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BackupResult:
    source: Path
    backup_path: Path
    sha256: str
    size: int
    timestamp_utc: str


def verify_backup(
    source: PathLike,
    backup: PathLike,
    *,
    expected_sha256: str | None = None,
) -> str:
    """Verify that source and backup have the same expected SHA-256."""
    source_hash = file_sha256(source)
    backup_hash = file_sha256(backup)
    expected = expected_sha256 or source_hash
    if source_hash != expected or backup_hash != expected:
        raise BackupVerificationError(
            f"backup hash mismatch: source={source_hash}, backup={backup_hash}, "
            f"expected={expected}"
        )
    return expected


def create_verified_backup(
    path: PathLike,
    *,
    backup_dir: PathLike | None = None,
    timestamp: datetime | None = None,
    chunk_size: int = 1024 * 1024,
) -> BackupResult:
    """Create and verify a timestamped byte-for-byte backup of a stable file."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    directory = Path(backup_dir) if backup_dir is not None else source.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)

    stamp = _utc_stamp(timestamp)
    before_hash = file_sha256(source, chunk_size=chunk_size)
    target = _unique_path(
        directory,
        f"{source.name}.backup-{stamp}-{before_hash[:16]}",
    )
    fd = -1
    temporary: Path | None = None
    copied_hash = hashlib.sha256()
    copied_size = 0
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=directory
        )
        temporary = Path(temporary_name)
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                _write_all(fd, chunk)
                copied_hash.update(chunk)
                copied_size += len(chunk)
        os.fsync(fd)
        os.close(fd)
        fd = -1

        after_hash = file_sha256(source, chunk_size=chunk_size)
        if copied_hash.hexdigest() != before_hash or after_hash != before_hash:
            raise BackupVerificationError(
                f"source changed while backing up {source}: "
                f"before={before_hash}, copied={copied_hash.hexdigest()}, "
                f"after={after_hash}"
            )
        os.replace(temporary, target)
        temporary = None
        fsync_directory(directory)
        verify_backup(source, target, expected_sha256=before_hash)
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if target.exists():
            target.unlink(missing_ok=True)
            fsync_directory(directory)
        raise

    return BackupResult(source, target, before_hash, copied_size, stamp)


verified_backup = create_verified_backup


# ═══════════════════════════════════════════════════════════════════════════════
# PID + owner-token process locks
# ═══════════════════════════════════════════════════════════════════════════════

def pid_is_running(pid: int) -> bool:
    """Return whether a PID currently exists, on Windows and POSIX."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Access denied means the process exists but cannot be queried.
        return ctypes.windll.kernel32.GetLastError() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _parse_lock_bytes(path: Path, raw: bytes) -> dict[str, Any]:
    if len(raw) > 64 * 1024:
        raise InvalidLockError(f"oversized lock file: {path}")
    try:
        text = raw.decode("utf-8", errors="strict")
        owner = _strict_json_loads(text)
    except Exception as exc:
        raise InvalidLockError(f"invalid lock file {path}: {exc}") from exc
    if not isinstance(owner, dict):
        raise InvalidLockError(f"lock owner is not an object: {path}")
    pid = owner.get("pid")
    token = owner.get("owner_token")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise InvalidLockError(f"lock has invalid PID: {path}")
    if not isinstance(token, str) or not token:
        raise InvalidLockError(f"lock has invalid owner token: {path}")
    return owner


def read_lock_owner(path: PathLike) -> dict[str, Any]:
    lock_path = Path(path)
    try:
        raw = lock_path.read_bytes()
    except FileNotFoundError:
        raise
    return _parse_lock_bytes(lock_path, raw)


def _unlink_if_unchanged(path: Path, observed: bytes) -> bool:
    try:
        current = path.read_bytes()
    except FileNotFoundError:
        return False
    if current != observed:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    fsync_directory(path.parent)
    return True


class ProcessLock:
    """An exclusive O_EXCL lock containing a PID and random owner token.

    A lock owned by a dead PID is removed and acquisition retried.  Release reads
    the lock back and verifies both this process's PID and its unguessable token;
    an old owner can therefore never remove a replacement lock.
    """

    def __init__(
        self,
        path: PathLike,
        *,
        scope: str | None = None,
        timeout: float | None = 0.0,
        poll_interval: float = 0.05,
    ) -> None:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.path = Path(path)
        self.scope = scope
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.owner_token = secrets.token_hex(24)
        self._owner: dict[str, Any] | None = None
        self._payload: bytes | None = None
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    @property
    def owner(self) -> Mapping[str, Any] | None:
        return dict(self._owner) if self._owner is not None else None

    def _new_owner(self) -> dict[str, Any]:
        return {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "owner_token": self.owner_token,
            "pid": os.getpid(),
            "scope": self.scope,
        }

    def acquire(self) -> "ProcessLock":
        if self._acquired:
            raise LockError(f"lock is already acquired by this object: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()

        while True:
            owner = self._new_owner()
            payload = canonical_json_bytes(owner)
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            try:
                fd = os.open(self.path, flags, 0o600)
            except FileExistsError:
                try:
                    observed = self.path.read_bytes()
                except FileNotFoundError:
                    continue
                existing = _parse_lock_bytes(self.path, observed)
                existing_pid = existing["pid"]
                if not pid_is_running(existing_pid):
                    if _unlink_if_unchanged(self.path, observed):
                        continue
                    continue

                if self.timeout is not None:
                    elapsed = time.monotonic() - started
                    if elapsed >= self.timeout:
                        raise LockHeldError(
                            f"lock {self.path} is held by live PID {existing_pid} "
                            f"(scope={existing.get('scope')!r})"
                        )
                    remaining = self.timeout - elapsed
                    time.sleep(min(self.poll_interval, max(0.0, remaining)))
                else:
                    time.sleep(self.poll_interval)
                continue

            try:
                _write_all(fd, payload)
                os.fsync(fd)
            except Exception:
                os.close(fd)
                _unlink_if_unchanged(self.path, payload)
                raise
            else:
                os.close(fd)
            fsync_directory(self.path.parent)
            self._owner = owner
            self._payload = payload
            self._acquired = True
            return self

    def release(self) -> None:
        if not self._acquired or self._owner is None:
            return
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError as exc:
            raise LockOwnershipError(
                f"owned lock disappeared before release: {self.path}"
            ) from exc
        try:
            current = _parse_lock_bytes(self.path, raw)
        except InvalidLockError as exc:
            raise LockOwnershipError(
                f"cannot verify lock ownership before release: {self.path}"
            ) from exc
        if (
            current.get("pid") != os.getpid()
            or current.get("owner_token") != self.owner_token
        ):
            raise LockOwnershipError(
                f"lock owner changed; refusing to remove {self.path}"
            )
        try:
            self.path.unlink()
        except FileNotFoundError as exc:
            raise LockOwnershipError(
                f"owned lock disappeared during release: {self.path}"
            ) from exc
        fsync_directory(self.path.parent)
        self._acquired = False
        self._owner = None
        self._payload = None

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def lock_is_active(path: PathLike, *, clean_stale: bool = False) -> bool:
    """Check a lock owner; optionally remove a byte-identical stale lock."""
    lock_path = Path(path)
    try:
        observed = lock_path.read_bytes()
    except FileNotFoundError:
        return False
    owner = _parse_lock_bytes(lock_path, observed)
    if pid_is_running(owner["pid"]):
        return True
    if clean_stale:
        _unlink_if_unchanged(lock_path, observed)
    return False


ProcessFileLock = ProcessLock


# ═══════════════════════════════════════════════════════════════════════════════
# Pause/migration sentinels and coordinated lock helpers
# ═══════════════════════════════════════════════════════════════════════════════

def pause_sentinel_path(root: PathLike) -> Path:
    return Path(root) / PAUSE_SENTINEL_NAME


def migration_sentinel_path(root: PathLike) -> Path:
    return Path(root) / MIGRATION_SENTINEL_NAME


def is_paused(root: PathLike) -> bool:
    return pause_sentinel_path(root).exists()


def migration_in_progress(root: PathLike) -> bool:
    return migration_sentinel_path(root).exists()


def _sentinel_detail(path: Path) -> str:
    try:
        detail = path.read_text(encoding="utf-8", errors="replace").strip()[:500]
    except OSError:
        detail = ""
    return f" ({detail})" if detail else ""


def check_pause_sentinel(root: PathLike) -> None:
    path = pause_sentinel_path(root)
    if path.exists():
        raise ExperimentPausedError(
            f"Experiment B is paused by {path}{_sentinel_detail(path)}"
        )


def check_migration_sentinel(root: PathLike) -> None:
    path = migration_sentinel_path(root)
    if path.exists():
        raise MigrationInProgressError(
            f"Experiment B migration is active via {path}{_sentinel_detail(path)}"
        )


def check_storage_sentinels(root: PathLike) -> None:
    """Reject ordinary storage work while paused or migrating."""
    check_pause_sentinel(root)
    check_migration_sentinel(root)


assert_not_paused = check_pause_sentinel
assert_no_migration = check_migration_sentinel
assert_storage_writable = check_storage_sentinels


def _lock_directory(root: PathLike) -> Path:
    return Path(root) / LOCK_DIR_NAME


def maintenance_lock_path(root: PathLike) -> Path:
    return _lock_directory(root) / MAINTENANCE_LOCK_NAME


def _scope_slug(scope: str) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("scope must be a non-empty string")
    normalized = scope.strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized).strip(" ._") or "scope"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:64]}-{digest}"


def scope_lock_path(root: PathLike, scope: str) -> Path:
    return _lock_directory(root) / f"{_scope_slug(scope)}{_SCOPE_LOCK_SUFFIX}"


@contextmanager
def scope_lock(
    root: PathLike,
    scope: str,
    *,
    timeout: float | None = 0.0,
    poll_interval: float = 0.05,
) -> Iterator[ProcessLock]:
    """Hold one write scope unless sentinels or maintenance forbid work.

    The scope lock is created before checking the maintenance lock.  A racing
    maintenance process creates its global lock first and then scans scopes, so
    the two helpers cannot both enter their protected regions.
    """
    root_path = Path(root)
    lock = ProcessLock(
        scope_lock_path(root_path, scope),
        scope=scope,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    with lock:
        check_storage_sentinels(root_path)
        if lock_is_active(maintenance_lock_path(root_path), clean_stale=True):
            raise MigrationInProgressError(
                f"maintenance lock is active: {maintenance_lock_path(root_path)}"
            )
        yield lock


@contextmanager
def maintenance_lock(
    root: PathLike,
    *,
    timeout: float | None = 0.0,
    poll_interval: float = 0.05,
) -> Iterator[ProcessLock]:
    """Hold the global maintenance lock only when no live scope lock exists."""
    root_path = Path(root)
    lock = ProcessLock(
        maintenance_lock_path(root_path),
        scope="maintenance",
        timeout=timeout,
        poll_interval=poll_interval,
    )
    with lock:
        active: list[Path] = []
        lock_dir = _lock_directory(root_path)
        for candidate in sorted(lock_dir.glob(f"*{_SCOPE_LOCK_SUFFIX}")):
            if lock_is_active(candidate, clean_stale=True):
                active.append(candidate)
        if active:
            names = ", ".join(path.name for path in active)
            raise ScopeLocksActiveError(
                f"cannot enter maintenance while scope locks are active: {names}"
            )
        yield lock


acquire_scope_lock = scope_lock
acquire_maintenance_lock = maintenance_lock


__all__ = [
    "AppendResult",
    "AtomicWriteError",
    "AtomicWriteResult",
    "BackupResult",
    "BackupVerificationError",
    "BlankJsonlLineError",
    "CanonicalJsonError",
    "ConflictingRowIdError",
    "DuplicateJsonKeyError",
    "DuplicateRowIdError",
    "ExperimentPausedError",
    "InvalidLockError",
    "InvalidUtf8Error",
    "JsonlError",
    "JsonlRow",
    "JsonlScanResult",
    "JsonlValidationError",
    "LockError",
    "LockHeldError",
    "LockOwnershipError",
    "MAINTENANCE_LOCK_NAME",
    "MIGRATION_SENTINEL_NAME",
    "MalformedJsonlError",
    "MigrationInProgressError",
    "MissingRowIdError",
    "PAUSE_SENTINEL_NAME",
    "ProcessFileLock",
    "ProcessLock",
    "ScopeLocksActiveError",
    "SentinelError",
    "StorageError",
    "TailQuarantine",
    "UnterminatedJsonlError",
    "acquire_maintenance_lock",
    "acquire_scope_lock",
    "append_jsonl",
    "append_jsonl_row",
    "assert_no_migration",
    "assert_not_paused",
    "assert_storage_writable",
    "atomic_replace_bytes",
    "atomic_replace_json",
    "atomic_replace_jsonl",
    "atomic_write_bytes",
    "atomic_write_json",
    "atomic_write_jsonl",
    "canonical_dumps",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_jsonl_row_bytes",
    "canonical_row_sha256",
    "check_migration_sentinel",
    "check_pause_sentinel",
    "check_storage_sentinels",
    "create_verified_backup",
    "file_sha256",
    "fsync_directory",
    "is_paused",
    "lock_is_active",
    "maintenance_lock",
    "maintenance_lock_path",
    "migration_in_progress",
    "migration_sentinel_path",
    "pause_sentinel_path",
    "pid_is_running",
    "read_lock_owner",
    "row_sha256",
    "scan_jsonl",
    "scope_lock",
    "scope_lock_path",
    "sha256_bytes",
    "sha256_file",
    "strict_scan_jsonl",
    "verified_backup",
    "verify_backup",
]
