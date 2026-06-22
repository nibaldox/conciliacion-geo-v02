"""Disk-based async cache for AI agent v2 responses.

Atomic writes via tempfile + os.replace (POSIX-guaranteed atomic rename)
and a module-level threading.Lock protect against two failure modes
addressed in docs/BARRIDO_2026-06-21.md (A2 + D4):

1. **Truncated file on crash**: a partial write previously left a
   corrupted ``<key>.json`` on disk. Now we write to a sibling temp
   file and rename atomically; readers either see the previous good
   payload or the new one, never a half-written one.
2. **Race on concurrent writes**: two threads calling ``put`` with the
   same key could interleave ``write_text`` calls and produce a
   truncated or scrambled payload. A module-level Lock serializes the
   write path; reads are lock-free.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path


# Module-level lock — shared by all DiskCache instances so concurrent
# callers from any process (Streamlit worker thread, FastAPI request,
# pytest parallel) serialize on the same critical section.
_CACHE_LOCK = threading.Lock()


def _cache_key(prompt: str, provider: str, model: str) -> str:
    raw = f"{provider}|{model}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DiskCache:
    def __init__(
        self,
        cache_dir: str = ".ai_v2_cache",
        ttl_s: int = 86400,
        max_files: int | None = 1000,
    ) -> None:
        """Disk cache for AI agent v2 responses.

        Parameters
        ----------
        cache_dir : str
            Directory for cache files. Created on init if missing.
        ttl_s : int
            Default time-to-live in seconds.
        max_files : int | None
            Maximum number of files to keep in the cache. When the
            directory exceeds this count, the oldest files (by mtime)
            are removed after each ``put``. Pass ``None`` to disable
            eviction (unbounded mode). Default 1000 — covers ~1 year
            of moderate use without touching the disk.
        """
        self._dir = Path(cache_dir)
        self._dir.mkdir(exist_ok=True)
        self._ttl_s = ttl_s
        self._max_files = max_files

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    async def get(self, key: str) -> list[str] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        ts = data.get("ts", 0)
        if time.time() - ts > self._ttl_s:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        chunks = data.get("chunks")
        if not isinstance(chunks, list):
            return None
        return [str(c) for c in chunks]

    async def put(
        self, key: str, chunks: list[str], ttl: int | None = None
    ) -> None:
        """Persist ``chunks`` for ``key`` atomically.

        Write path:
        1. Acquire ``_CACHE_LOCK`` so no two threads race on the same key.
        2. Serialize payload to a sibling ``.tmp`` file with ``O_EXCL``.
        3. ``os.replace(tmp, final)`` — POSIX-atomic; readers see either
           the old payload or the new one, never a partial write.
        4. Best-effort cleanup of leftover ``.tmp`` from previous crashes.
        """
        payload = {"ts": time.time(), "chunks": chunks, "ttl": ttl or self._ttl_s}
        serialized = json.dumps(payload, ensure_ascii=False)
        final = self._path(key)
        # Sibling temp file in the SAME directory (required so os.replace
        # is atomic on POSIX; cross-filesystem rename is not atomic).
        tmp_path = final.with_suffix(final.suffix + ".tmp")
        with _CACHE_LOCK:
            # Best-effort cleanup of stale temp from previous crash.
            # Inside the lock so we don't race with another writer.
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
            try:
                fd = os.open(
                    str(tmp_path),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(serialized)
                except Exception:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    raise
                os.replace(tmp_path, final)
            except OSError:
                # Don't leak .tmp on disk full / permission errors.
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
                raise
            if self._max_files is not None:
                self._enforce_lru_cap()

    def _enforce_lru_cap(self) -> None:
        """Evict the oldest files (by mtime) until under the cap.

        MUST be called inside ``_CACHE_LOCK`` (caller's responsibility)
        to prevent racing with concurrent writers that might have just
        added a new file. Files whose mtime cannot be read (broken
        symlinks, deleted, etc.) are evicted first.
        """
        try:
            paths = list(self._dir.glob("*.json"))
        except OSError:
            return
        # Defensive: include any .tmp leftovers in the count so they get cleaned up.
        all_paths = paths + list(self._dir.glob("*.tmp"))
        if len(all_paths) <= self._max_files:
            return

        def mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return -1.0  # broken paths sort to the front → evicted first

        all_paths.sort(key=mtime)
        excess = len(all_paths) - self._max_files
        for p in all_paths[:excess]:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
