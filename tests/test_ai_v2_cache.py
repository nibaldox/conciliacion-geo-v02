"""Tests for core.ai_v2 DiskCache."""
from __future__ import annotations

import json

import pytest

from core.ai_v2.cache import DiskCache, _cache_key


def test_cache_key_is_sha256_hex():
    k = _cache_key("prompt", "ollama", "llama3.1")
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)


def test_cache_key_deterministic():
    a = _cache_key("hello", "ollama", "llama3.1")
    b = _cache_key("hello", "ollama", "llama3.1")
    assert a == b


def test_cache_key_differs_on_prompt():
    a = _cache_key("hello", "ollama", "llama3.1")
    b = _cache_key("world", "ollama", "llama3.1")
    assert a != b


def test_cache_key_differs_on_provider():
    a = _cache_key("hello", "ollama", "llama3.1")
    b = _cache_key("hello", "openai", "llama3.1")
    assert a != b


def test_cache_key_differs_on_model():
    a = _cache_key("hello", "ollama", "llama3.1")
    b = _cache_key("hello", "ollama", "gpt-4o")
    assert a != b


def test_disk_cache_creates_dir(tmp_path):
    cache_dir = tmp_path / "new_cache"
    DiskCache(cache_dir=str(cache_dir), ttl_s=3600)
    assert cache_dir.exists()
    assert cache_dir.is_dir()


@pytest.mark.asyncio
async def test_disk_cache_get_missing(tmp_path):
    cache = DiskCache(cache_dir=str(tmp_path), ttl_s=3600)
    result = await cache.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_disk_cache_put_and_get(tmp_path):
    cache = DiskCache(cache_dir=str(tmp_path), ttl_s=3600)
    await cache.put("k1", ["chunk1", "chunk2", "chunk3"])
    result = await cache.get("k1")
    assert result == ["chunk1", "chunk2", "chunk3"]


@pytest.mark.asyncio
async def test_disk_cache_get_corrupt_file(tmp_path):
    cache = DiskCache(cache_dir=str(tmp_path), ttl_s=3600)
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {{{", encoding="utf-8")
    result = await cache.get("bad")
    assert result is None


@pytest.mark.asyncio
async def test_disk_cache_get_expired(tmp_path):
    cache = DiskCache(cache_dir=str(tmp_path), ttl_s=1)
    await cache.put("k1", ["x"])
    import asyncio
    await asyncio.sleep(1.5)
    result = await cache.get("k1")
    assert result is None
    assert not (tmp_path / "k1.json").exists()


@pytest.mark.asyncio
async def test_disk_cache_put_with_explicit_ttl(tmp_path):
    cache = DiskCache(cache_dir=str(tmp_path), ttl_s=3600)
    await cache.put("k1", ["x"], ttl=60)
    payload = json.loads((tmp_path / "k1.json").read_text())
    assert payload["ttl"] == 60