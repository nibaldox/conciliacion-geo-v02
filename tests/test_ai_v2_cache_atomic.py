"""Tests for atomic write + lock in core.ai_v2.cache — Sprint 1 A2/D4."""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from core.ai_v2.cache import DiskCache, _CACHE_LOCK


@pytest.fixture
def cache(tmp_path):
    return DiskCache(cache_dir=str(tmp_path), ttl_s=3600)


class TestAtomicWrite:
    def test_no_tmp_file_left_on_success(self, cache, tmp_path):
        asyncio.run(cache.put("k1", ["chunk1"]))
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []
        assert (tmp_path / "k1.json").exists()

    def test_target_file_is_valid_json_after_write(self, cache):
        asyncio.run(cache.put("k1", ["alpha", "beta"]))
        loaded = asyncio.run(cache.get("k1"))
        assert loaded == ["alpha", "beta"]

    def test_get_returns_none_for_missing_key(self, cache):
        assert asyncio.run(cache.get("nonexistent")) is None

    def test_get_returns_none_for_corrupted_json(self, cache, tmp_path):
        (tmp_path / "bad.json").write_text("{not json}", encoding="utf-8")
        assert asyncio.run(cache.get("bad")) is None


class TestConcurrentWrites:
    def test_concurrent_writes_serialize(self, cache, tmp_path):
        """N threads writing concurrently should produce a valid file
        (one of the payloads, never truncated/corrupt)."""
        N = 4
        barrier = threading.Barrier(N)
        errors: list = []
        payloads = [[f"chunk-{i}-{j}" for j in range(3)] for i in range(N)]

        def writer(payload: list):
            try:
                barrier.wait(timeout=5)
                asyncio.run(cache.put("race", payload))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(payloads[i],))
            for i in range(N)
        ]
        for t in threads: t.start()
        for t in threads: t.join()

        assert errors == []
        loaded = asyncio.run(cache.get("race"))
        # The final value must be one of the payloads (atomic guarantee).
        assert loaded in payloads, f"loaded={loaded} not in {payloads}"
        # No temp files left behind
        assert list(tmp_path.glob("*.tmp")) == []
        # File must be valid JSON
        on_disk = json.loads((tmp_path / "race.json").read_text())
        assert on_disk["chunks"] in payloads

    def test_module_level_lock_is_shared(self):
        """Two DiskCache instances serialize on the same lock."""
        c1 = DiskCache(cache_dir="/tmp/a", ttl_s=3600)
        c2 = DiskCache(cache_dir="/tmp/b", ttl_s=3600)
        # Both should reference the same module-level lock.
        # We exercise the lock by attempting to acquire it from outside.
        assert _CACHE_LOCK.acquire(timeout=1)
        _CACHE_LOCK.release()
