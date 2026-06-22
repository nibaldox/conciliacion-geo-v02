"""Tests for cache LRU eviction — Sprint 3 A3."""
from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path

import pytest

from core.ai_v2.cache import DiskCache


@pytest.fixture
def cache(tmp_path):
    return DiskCache(cache_dir=str(tmp_path), ttl_s=3600, max_files=3)


class TestLRUEviction:
    def test_enforces_max_files(self, cache, tmp_path):
        """Put 5 files with max_files=3, verify only 3 remain."""
        for i in range(5):
            asyncio.run(cache.put(f"k{i}", [f"chunk-{i}"]))
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 3

    def test_keeps_newest(self, cache, tmp_path):
        """The 3 most recently written files should survive."""
        for i in range(5):
            asyncio.run(cache.put(f"k{i}", [f"chunk-{i}"]))
            time.sleep(0.01)  # ensure mtime ordering
        remaining = sorted(p.stem for p in tmp_path.glob("*.json"))
        assert remaining == ["k2", "k3", "k4"]

    def test_unbounded_when_max_files_none(self, tmp_path):
        cache = DiskCache(cache_dir=str(tmp_path), max_files=None)
        for i in range(10):
            asyncio.run(cache.put(f"k{i}", [f"chunk-{i}"]))
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 10

    def test_default_max_files_is_1000(self, tmp_path):
        cache = DiskCache(cache_dir=str(tmp_path))
        assert cache._max_files == 1000

    def test_empty_dir_no_error(self, cache, tmp_path):
        # No puts at all — just instantiate and call _enforce_lru_cap.
        # Should not raise even though directory is empty.
        cache._enforce_lru_cap()
        assert list(tmp_path.glob("*.json")) == []

    def test_under_cap_no_eviction(self, cache, tmp_path):
        """When file count is below cap, no files are removed."""
        for i in range(2):
            asyncio.run(cache.put(f"k{i}", [f"chunk-{i}"]))
        files = sorted(p.stem for p in tmp_path.glob("*.json"))
        assert files == ["k0", "k1"]


class TestLRUConcurrent:
    def test_concurrent_writes_with_lru(self, cache, tmp_path):
        """N threads writing concurrently with LRU enabled should leave
        the cache in a consistent state (max_files entries, all valid)."""
        N = 8
        barrier = threading.Barrier(N)
        errors: list = []
        payloads = [[f"chunk-{i}-{j}" for j in range(2)] for i in range(N)]

        def writer(i: int, payload: list):
            try:
                barrier.wait(timeout=5)
                asyncio.run(cache.put(f"k{i}", payload))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(i, payloads[i]))
            for i in range(N)
        ]
        for t in threads: t.start()
        for t in threads: t.join()

        assert errors == []
        # Cap is 3, so exactly 3 files survive.
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 3
        # Every surviving file is valid JSON with the expected chunks.
        import json
        for p in files:
            data = json.loads(p.read_text())
            assert "chunks" in data
            assert isinstance(data["chunks"], list)
