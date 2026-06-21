"""Disk-based async cache for AI agent v2 responses."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def _cache_key(prompt: str, provider: str, model: str) -> str:
    raw = f"{provider}|{model}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DiskCache:
    def __init__(self, cache_dir: str = ".ai_v2_cache", ttl_s: int = 86400) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(exist_ok=True)
        self._ttl_s = ttl_s

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
        payload = {"ts": time.time(), "chunks": chunks, "ttl": ttl or self._ttl_s}
        self._path(key).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )