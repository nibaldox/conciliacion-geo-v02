"""Byte-bounded LRU cache shared by the mesh router payloads.

The mesh endpoints memoise large JSON-ready payloads (vertex arrays, contour
polylines, breakline segments, horizontal-deviation patches). Bounding those
caches by *entry count* is useless when a single entry can weigh hundreds of
megabytes, so :class:`ByteLruCache` tracks an estimated size per entry and
evicts least-recently-used entries until the shared :class:`ByteBudget` fits.

Size estimation (:func:`estimate_size`) walks containers recursively but stays
cheap on the structures these payloads actually use:

* ``numpy`` arrays report ``nbytes``.
* Numeric sequences are sampled (first 64 items); if every sample is a number
  the whole sequence is charged ``56 + 32 * len`` bytes (list header + pointer
  slot + boxed float), without visiting the remaining items.
* Containers nested deeper than ``_MAX_NODES`` (200k nodes) are not expanded:
  their children are sampled (first 16) and the average child size — itself
  sampled one level down — is scaled by ``len``. This keeps a
  multi-million-object payload from costing seconds.
* Unknown objects are charged a flat 64 bytes.

The estimate is intentionally conservative for scalars and strings; it is an
approximation used for eviction accounting, never for allocation decisions.
"""
from __future__ import annotations

import functools
import itertools
import os
import threading
from collections import OrderedDict, namedtuple
from collections.abc import Hashable, Mapping
from typing import Any, Callable

import numpy as np

DEFAULT_BUDGET_MB = 512
ENV_VAR = "CONCILIACION_MESH_CACHE_MB"
_MIB = 1024 * 1024
_MAX_NODES = 200_000
_SAMPLE_CHILDREN = 16
_SAMPLE_SEQUENCE = 64
_FALLBACK_CHILD_BYTES = 56
_UNKNOWN_OBJECT_BYTES = 64

CacheInfo = namedtuple(
    "CacheInfo", "hits misses currsize maxsize bytes limit_bytes"
)


def budget_bytes_from_env(env: Mapping[str, str] | None = None) -> int:
    """Return the mesh cache budget in bytes from ``CONCILIACION_MESH_CACHE_MB``.

    Invalid values (non-integer, zero, negative, empty) fall back to
    :data:`DEFAULT_BUDGET_MB` megabytes.
    """
    default = DEFAULT_BUDGET_MB * _MIB
    raw = (os.environ if env is None else env).get(ENV_VAR)
    if raw is None:
        return default
    try:
        megabytes = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if megabytes <= 0:
        return default
    return megabytes * _MIB


def _is_numeric_sequence(items) -> bool:
    seen_any = False
    for item in itertools.islice(items, _SAMPLE_SEQUENCE):
        seen_any = True
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return False
    return seen_any


def _shallow_size(value: Any) -> int:
    """Estimate one object without descending into its grandchildren."""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, np.ndarray):
        return int(value.nbytes) + 112
    if isinstance(value, str):
        return 49 + len(value)
    if isinstance(value, (bytes, bytearray)):
        return 33 + len(value)
    if isinstance(value, float):
        return 24
    if isinstance(value, complex):
        return 32
    if isinstance(value, int):
        return 28
    if isinstance(value, dict):
        return 232 + 100 * len(value) + _FALLBACK_CHILD_BYTES * len(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        base = 56 + 8 * len(value)
        if _is_numeric_sequence(value):
            return base + 32 * len(value)
        return base + _FALLBACK_CHILD_BYTES * len(value)
    return _UNKNOWN_OBJECT_BYTES


def _sampled_container_size(container) -> int:
    """Estimate a container whose children are not walked individually."""
    if isinstance(container, dict):
        base = 232 + 100 * len(container)
        children = list(itertools.islice(container.values(), _SAMPLE_CHILDREN))
    else:
        base = 56 + 8 * len(container)
        children = list(itertools.islice(container, _SAMPLE_CHILDREN))
    length = len(container)
    if not children or not length:
        return base
    per_child = sum(_sample_child_size(child) for child in children) / len(children)
    return base + int(per_child * length)


def _sample_child_size(child: Any) -> int:
    if isinstance(child, (dict, list, tuple, set, frozenset)):
        return _sampled_container_size(child)
    return _shallow_size(child)


def estimate_size(value: Any) -> int:
    """Approximate the bytes retained by a cached payload (see module docstring)."""
    total = 0
    nodes = 0
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        nodes += 1
        deep = nodes <= _MAX_NODES
        if item is None or isinstance(item, bool):
            continue
        if isinstance(item, np.ndarray):
            total += int(item.nbytes) + 112
            continue
        if isinstance(item, str):
            total += 49 + len(item)
            continue
        if isinstance(item, (bytes, bytearray)):
            total += 33 + len(item)
            continue
        if isinstance(item, float):
            total += 24
            continue
        if isinstance(item, complex):
            total += 32
            continue
        if isinstance(item, int):
            total += 28
            continue
        if isinstance(item, dict):
            if not deep:
                total += _sampled_container_size(item)
                continue
            total += 232 + 100 * len(item)
            for key, child in item.items():
                stack.append(key)
                stack.append(child)
            continue
        if isinstance(item, (list, tuple, set, frozenset)):
            base = 56 + 8 * len(item)
            if _is_numeric_sequence(item):
                total += base + 32 * len(item)
                continue
            if not deep:
                total += _sampled_container_size(item)
                continue
            total += base
            stack.extend(item)
            continue
        total += _UNKNOWN_OBJECT_BYTES
    return total


class ByteBudget:
    """Shared byte accounting for one or more :class:`ByteLruCache` instances."""

    def __init__(self, limit_bytes: int) -> None:
        if int(limit_bytes) <= 0:
            raise ValueError("limit_bytes must be a positive integer")
        self._limit = int(limit_bytes)
        self._used = 0
        self._lock = threading.Lock()

    @property
    def limit_bytes(self) -> int:
        return self._limit

    @property
    def used_bytes(self) -> int:
        with self._lock:
            return self._used

    def reserve(self, size: int) -> bool:
        with self._lock:
            if size > self._limit or self._used + size > self._limit:
                return False
            self._used += size
            return True

    def release(self, size: int) -> None:
        with self._lock:
            self._used = max(0, self._used - size)


def _make_key(args: tuple, kwargs: dict) -> Hashable:
    if kwargs:
        return (args, tuple(sorted(kwargs.items())))
    return args


class ByteLruCache:
    """LRU cache of ``fn`` results bounded by a shared :class:`ByteBudget`.

    The decorator exposes ``cache_clear()``, ``cache_info()`` and ``cache`` so
    callers written against :func:`functools.lru_cache` keep working. Entries
    larger than the budget are returned but never stored. The internal lock is
    never held while ``fn`` runs; concurrent callers of the same key wait for
    the first one to finish instead of recomputing.
    """

    def __init__(self, budget: ByteBudget, *, name: str = "byte_cache") -> None:
        self.budget = budget
        self.name = name
        self._entries: "OrderedDict[Hashable, tuple[Any, int]]" = OrderedDict()
        self._pending: "dict[Hashable, threading.Event]" = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(args, kwargs)
            hit, value = self._lookup(key)
            if hit:
                return value
            event, owner = self._claim(key)
            if not owner:
                event.wait()
                hit, value = self._lookup(key)
                if hit:
                    return value
            try:
                value = fn(*args, **kwargs)
            finally:
                if owner:
                    self._release_claim(key, event)
            self._store(key, value)
            return value

        setattr(wrapper, "cache_clear", self.clear)
        setattr(wrapper, "cache_info", self.info)
        setattr(wrapper, "cache", self)
        return wrapper

    def _lookup(self, key: Hashable) -> tuple[bool, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return False, None
            self._entries.move_to_end(key)
            self._hits += 1
            return True, entry[0]

    def _claim(self, key: Hashable) -> tuple[threading.Event, bool]:
        with self._lock:
            pending = self._pending.get(key)
            if pending is not None:
                return pending, False
            event = threading.Event()
            self._pending[key] = event
            return event, True

    def _release_claim(self, key: Hashable, event: threading.Event) -> None:
        with self._lock:
            self._pending.pop(key, None)
        event.set()

    def _store(self, key: Hashable, value: Any) -> None:
        size = estimate_size(value)
        with self._lock:
            self._discard(key)
            while True:
                if self.budget.reserve(size):
                    self._entries[key] = (value, size)
                    return
                if not self._entries:
                    return
                _, (_, evicted_size) = self._entries.popitem(last=False)
                self.budget.release(evicted_size)

    def _discard(self, key: Hashable) -> None:
        entry = self._entries.pop(key, None)
        if entry is not None:
            self.budget.release(entry[1])

    def clear(self) -> None:
        with self._lock:
            for _, size in self._entries.values():
                self.budget.release(size)
            self._entries.clear()

    def info(self) -> CacheInfo:
        with self._lock:
            return CacheInfo(
                self._hits,
                self._misses,
                len(self._entries),
                None,
                sum(size for _, size in self._entries.values()),
                self.budget.limit_bytes,
            )


_global_lock = threading.Lock()
_global_budget: ByteBudget | None = None


def global_budget() -> ByteBudget:
    """Return the process-wide budget read from the environment on first use."""
    global _global_budget
    with _global_lock:
        if _global_budget is None:
            _global_budget = ByteBudget(budget_bytes_from_env())
        return _global_budget


def mesh_cache(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Memoise ``fn`` under the shared mesh-payload byte budget."""
    return ByteLruCache(global_budget(), name=fn.__name__)(fn)
