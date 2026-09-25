"""Cross-process concurrency slots for calls to the local Copilot router.

The pool deliberately uses only filesystem primitives available in the Python
standard library.  A slot is claimed with ``O_CREAT | O_EXCL`` and can only be
released by the process holding the random owner token written into that slot.
"""

from __future__ import annotations

import errno
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

POOL_VERSION = 1
DEFAULT_CAPACITY = 4
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_POLL_SECONDS = 0.05
DEFAULT_MALFORMED_STALE_SECONDS = 60.0
CAPACITY_ENV = "COPILOT_GLOBAL_SLOT_CAPACITY"
ROOT_ENV = "COPILOT_GLOBAL_SLOT_ROOT"


class SlotPoolError(RuntimeError):
    """Base error for the global slot pool."""


class CapacityMismatchError(SlotPoolError):
    """The requested capacity differs from the capacity pinned on disk."""


class SlotOwnershipError(SlotPoolError):
    """A release was attempted with a token that does not own the slot."""


class SlotTimeoutError(TimeoutError, SlotPoolError):
    """No slot became available before the acquisition timeout."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_slot_root() -> Path:
    """Return the versioned default pool root without creating it."""

    configured = os.environ.get(ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Local"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "HumanContribution" / "local_slot-slots" / "v1"


def _parse_capacity(value: Optional[Union[int, str]]) -> int:
    if value is None:
        value = os.environ.get(CAPACITY_ENV, str(DEFAULT_CAPACITY))
    try:
        capacity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"slot capacity must be a positive integer, got {value!r}") from exc
    if capacity <= 0:
        raise ValueError(f"slot capacity must be positive, got {capacity}")
    return capacity


def pid_is_alive(pid: int) -> bool:
    """Return whether *pid* currently exists on Windows or POSIX.

    Permission errors mean that the process exists but is owned by another
    user.  Invalid/non-positive PIDs are never considered live.
    """

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            open_process.restype = wintypes.HANDLE
            get_exit_code = kernel32.GetExitCodeProcess
            get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_exit_code.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL

            handle = open_process(process_query_limited_information, False, pid)
            if not handle:
                error = ctypes.get_last_error()
                # Access denied means the process exists.
                return error == 5
            try:
                exit_code = wintypes.DWORD()
                if not get_exit_code(handle, ctypes.byref(exit_code)):
                    return True
                return exit_code.value == still_active
            finally:
                close_handle(handle)
        except (AttributeError, OSError):
            # os.kill(pid, 0) is a suitable fallback on supported Python builds.
            pass

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        return False
    return True


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _write_exclusive_json(path: Path, value: Dict[str, Any]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


@dataclass(frozen=True)
class SlotAcquisition:
    """Information yielded by a slot context manager."""

    slot_index: int
    wait_seconds: float

    def __iter__(self) -> Iterator[Union[int, float]]:
        yield self.slot_index
        yield self.wait_seconds


class SlotLease:
    """A context manager representing one claimed slot."""

    def __init__(
        self,
        pool: "CopilotGlobalSlotPool",
        slot_index: int,
        owner_token: str,
        wait_seconds: float,
    ) -> None:
        self._pool = pool
        self.slot_index = slot_index
        self.owner_token = owner_token
        self.wait_seconds = wait_seconds
        self._released = False

    def __enter__(self) -> SlotAcquisition:
        return SlotAcquisition(self.slot_index, self.wait_seconds)

    def release(self) -> bool:
        """Release this lease once; a repeated call is a harmless no-op."""

        if self._released:
            return False
        released = self._pool.release(self.slot_index, self.owner_token)
        self._released = True
        return released

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


class CopilotGlobalSlotPool:
    """A filesystem-backed, machine-wide concurrency pool.

    Capacity is permanently pinned by ``pool.json`` at a given root.  Pointing
    another process at the same root with a different capacity is an error,
    rather than silently creating incompatible views of the pool.
    """

    def __init__(
        self,
        root: Optional[Union[str, os.PathLike[str]]] = None,
        capacity: Optional[Union[int, str]] = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        malformed_stale_seconds: float = DEFAULT_MALFORMED_STALE_SECONDS,
    ) -> None:
        self.root = Path(root).expanduser() if root is not None else default_slot_root()
        self.capacity = _parse_capacity(capacity)
        self.timeout_seconds = float(timeout_seconds)
        self.poll_seconds = float(poll_seconds)
        self.malformed_stale_seconds = float(malformed_stale_seconds)
        if self.timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self.malformed_stale_seconds < 0:
            raise ValueError("malformed_stale_seconds must be non-negative")
        self.root.mkdir(parents=True, exist_ok=True)
        self._metadata_path = self.root / "pool.json"
        self._ensure_metadata()

    def _ensure_metadata(self) -> None:
        metadata = {
            "version": POOL_VERSION,
            "capacity": self.capacity,
            "created_at": _utc_now(),
        }
        try:
            _write_exclusive_json(self._metadata_path, metadata)
        except FileExistsError:
            # A competing creator may have made the directory entry but not yet
            # completed its tiny write.  Briefly wait before declaring it bad.
            deadline = time.monotonic() + 2.0
            while True:
                try:
                    existing = _read_json(self._metadata_path)
                    break
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    if time.monotonic() >= deadline:
                        raise SlotPoolError(
                            f"cannot read slot-pool metadata {self._metadata_path}: {exc}"
                        ) from exc
                    time.sleep(min(self.poll_seconds, 0.02))
            if existing.get("version") != POOL_VERSION:
                raise SlotPoolError(
                    f"slot-pool version mismatch at {self.root}: "
                    f"found {existing.get('version')!r}, expected {POOL_VERSION}"
                )
            pinned = existing.get("capacity")
            if pinned != self.capacity:
                raise CapacityMismatchError(
                    f"slot-pool capacity mismatch at {self.root}: "
                    f"pinned={pinned!r}, requested={self.capacity}"
                )

    def _slot_path(self, slot_index: int) -> Path:
        if not isinstance(slot_index, int) or isinstance(slot_index, bool):
            raise ValueError("slot_index must be an integer")
        if not 0 <= slot_index < self.capacity:
            raise ValueError(
                f"slot_index must be in [0, {self.capacity - 1}], got {slot_index}"
            )
        return self.root / f"slot_{slot_index}.json"

    @staticmethod
    def _record_is_valid(record: Dict[str, Any]) -> bool:
        return (
            record.get("version") == POOL_VERSION
            and isinstance(record.get("pid"), int)
            and not isinstance(record.get("pid"), bool)
            and record.get("pid") > 0
            and isinstance(record.get("owner_token"), str)
            and bool(record.get("owner_token"))
            and isinstance(record.get("created_unix"), (int, float))
            and not isinstance(record.get("created_unix"), bool)
        )

    def _remove_if_unchanged(self, path: Path, expected_bytes: bytes) -> bool:
        """Best-effort compare-before-unlink for stale or owned records.

        Windows can reject ``unlink`` while another process is briefly reading
        the file to check liveness.  Retry sharing violations for a bounded
        interval; never treat them as proof that a live slot is stale.
        """

        deadline = time.monotonic() + 1.0
        while True:
            try:
                if path.read_bytes() != expected_bytes:
                    return False
                path.unlink()
                return True
            except FileNotFoundError:
                return False
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(self.poll_seconds, 0.01))

    def _clean_one_if_stale(self, path: Path) -> bool:
        try:
            raw = path.read_bytes()
            stat = path.stat()
        except FileNotFoundError:
            return False
        except PermissionError:
            # Most commonly the exclusive creator is still writing, or a
            # Windows peer has the file open for its own liveness check.
            return False

        try:
            decoded = json.loads(raw.decode("utf-8"))
            record = decoded if isinstance(decoded, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            record = {}

        if self._record_is_valid(record):
            if pid_is_alive(record["pid"]):
                return False
            return self._remove_if_unchanged(path, raw)

        age = max(0.0, time.time() - stat.st_mtime)
        if age < self.malformed_stale_seconds:
            return False
        return self._remove_if_unchanged(path, raw)

    def cleanup_stale(self) -> List[int]:
        """Remove dead-owner (or sufficiently old malformed) slot files."""

        removed: List[int] = []
        for slot_index in range(self.capacity):
            if self._clean_one_if_stale(self._slot_path(slot_index)):
                removed.append(slot_index)
        return removed

    def acquire(
        self,
        label: str = "",
        *,
        timeout_seconds: Optional[float] = None,
        poll_seconds: Optional[float] = None,
    ) -> SlotLease:
        """Wait for and claim one slot.

        Use as ``with pool.acquire(label) as (slot_index, wait_seconds):``.
        Every call generates a fresh ownership token and starts scanning at a
        random index to avoid all processes contending on slot zero.
        """

        timeout = self.timeout_seconds if timeout_seconds is None else float(timeout_seconds)
        poll = self.poll_seconds if poll_seconds is None else float(poll_seconds)
        if timeout < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if poll <= 0:
            raise ValueError("poll_seconds must be positive")
        if not isinstance(label, str):
            raise TypeError("label must be a string")

        started = time.monotonic()
        deadline = started + timeout
        start_index = secrets.randbelow(self.capacity)
        owner_token = secrets.token_hex(32)
        pid = os.getpid()

        while True:
            for offset in range(self.capacity):
                slot_index = (start_index + offset) % self.capacity
                path = self._slot_path(slot_index)
                now_unix = time.time()
                record = {
                    "version": POOL_VERSION,
                    "slot_index": slot_index,
                    "pid": pid,
                    "owner_token": owner_token,
                    "label": label,
                    "created_at": _utc_now(),
                    "created_unix": now_unix,
                }
                try:
                    _write_exclusive_json(path, record)
                except FileExistsError:
                    if self._clean_one_if_stale(path):
                        try:
                            _write_exclusive_json(path, record)
                        except FileExistsError:
                            continue
                        waited = max(0.0, time.monotonic() - started)
                        return SlotLease(self, slot_index, owner_token, waited)
                    continue
                waited = max(0.0, time.monotonic() - started)
                return SlotLease(self, slot_index, owner_token, waited)

            now = time.monotonic()
            if now >= deadline:
                raise SlotTimeoutError(
                    f"timed out after {now - started:.3f}s waiting for one of "
                    f"{self.capacity} Copilot global slots at {self.root}"
                )
            time.sleep(min(poll, max(0.0, deadline - now)))

    def release(self, slot_index: int, owner_token: str) -> bool:
        """Release a slot only when *owner_token* exactly matches its record."""

        if not isinstance(owner_token, str) or not owner_token:
            raise SlotOwnershipError("a non-empty owner token is required")
        path = self._slot_path(slot_index)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return False
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SlotOwnershipError(f"slot {slot_index} has an unreadable owner record") from exc
        if not isinstance(record, dict) or not secrets.compare_digest(
            str(record.get("owner_token", "")), owner_token
        ):
            raise SlotOwnershipError(f"owner token does not match slot {slot_index}")
        return self._remove_if_unchanged(path, raw)

    def snapshot(self, *, clean_stale: bool = True) -> Dict[str, Any]:
        """Return a sanitized pool snapshot; ownership tokens are never exposed."""

        cleaned = self.cleanup_stale() if clean_stale else []
        slots: List[Dict[str, Any]] = []
        for slot_index in range(self.capacity):
            path = self._slot_path(slot_index)
            try:
                record = _read_json(path)
                stat = path.stat()
            except FileNotFoundError:
                continue
            except (OSError, ValueError, json.JSONDecodeError):
                try:
                    stat = path.stat()
                    age_seconds = max(0.0, time.time() - stat.st_mtime)
                except FileNotFoundError:
                    continue
                slots.append(
                    {
                        "slot_index": slot_index,
                        "state": "malformed",
                        "age_seconds": age_seconds,
                    }
                )
                continue
            slots.append(
                {
                    "slot_index": slot_index,
                    "state": "occupied",
                    "pid": record.get("pid"),
                    "label": record.get("label", ""),
                    "created_at": record.get("created_at"),
                    "created_unix": record.get("created_unix"),
                    "age_seconds": max(0.0, time.time() - stat.st_mtime),
                }
            )
        return {
            "version": POOL_VERSION,
            "root": str(self.root),
            "capacity": self.capacity,
            "occupied": len(slots),
            "available": self.capacity - len(slots),
            "cleaned_stale_slots": cleaned,
            "slots": slots,
            "snapshot_at": _utc_now(),
        }


# Short alias for callers that do not need the provider-specific name.
GlobalSlotPool = CopilotGlobalSlotPool


def acquire_global_slot(
    label: str = "",
    *,
    root: Optional[Union[str, os.PathLike[str]]] = None,
    capacity: Optional[Union[int, str]] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> SlotLease:
    """Convenience wrapper that constructs the shared pool and acquires once."""

    pool = CopilotGlobalSlotPool(
        root=root,
        capacity=capacity,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    return pool.acquire(label)


__all__ = [
    "CAPACITY_ENV",
    "ROOT_ENV",
    "DEFAULT_CAPACITY",
    "CapacityMismatchError",
    "CopilotGlobalSlotPool",
    "GlobalSlotPool",
    "SlotAcquisition",
    "SlotLease",
    "SlotOwnershipError",
    "SlotPoolError",
    "SlotTimeoutError",
    "acquire_global_slot",
    "default_slot_root",
    "pid_is_alive",
]
