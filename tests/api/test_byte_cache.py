"""Tests for the byte-bounded LRU cache shared by the mesh router."""
from __future__ import annotations

import os
import threading
import time

import numpy as np
import pytest

import api.routers.meshes as meshes_router
from api.byte_cache import (
    DEFAULT_BUDGET_MB,
    ENV_VAR,
    ByteBudget,
    ByteLruCache,
    budget_bytes_from_env,
    estimate_size,
)


def _value(n: int = 100) -> list[float]:
    return [float(i) for i in range(n)]


class TestEstimateSize:
    def test_numbers_and_strings_are_counted(self):
        assert estimate_size([1.0] * 1000) > 8 * 1000
        assert estimate_size("x" * 1000) >= 1000
        assert estimate_size(b"x" * 1000) >= 1000
        assert estimate_size(1.0) < estimate_size([1.0] * 10)
        assert estimate_size(None) == 0

    def test_numpy_uses_nbytes(self):
        array = np.zeros((100, 3), dtype=np.float64)
        assert estimate_size(array) >= array.nbytes

    def test_nested_payload_is_counted_recursively(self):
        flat = [1.0] * 100
        nested = {"a": [flat, flat, flat]}
        assert estimate_size(nested) >= 3 * estimate_size(flat)


class TestBudget:
    def test_budget_respected_after_many_inserts(self):
        budget = ByteBudget(50_000)
        cache = ByteLruCache(budget)

        @cache
        def load(key: int) -> list[float]:
            return _value(500)

        for key in range(50):
            load(key)
        info = load.cache_info()
        assert info.bytes <= 50_000
        assert budget.used_bytes <= 50_000
        assert info.currsize < 50
        assert info.currsize >= 1

    def test_lru_eviction_order(self):
        size = estimate_size(_value(100))
        budget = ByteBudget(2 * size)
        cache = ByteLruCache(budget)
        calls: list[int] = []

        @cache
        def load(key: int) -> list[float]:
            calls.append(key)
            return _value(100)

        load(1)
        load(2)
        load(1)
        assert load.cache_info().hits == 1
        assert load.cache_info().currsize == 2

        load(3)
        assert load.cache_info().currsize == 2
        assert load.cache_info().bytes <= budget.limit_bytes

        load(1)
        assert calls.count(1) == 1
        load(2)
        assert calls.count(2) == 2

    def test_entry_larger_than_budget_is_not_stored(self):
        value = _value(1000)
        budget = ByteBudget(estimate_size(value) // 2)
        cache = ByteLruCache(budget)
        calls: list[int] = []

        @cache
        def load(key: int) -> list[float]:
            calls.append(key)
            return value

        first = load(1)
        second = load(1)
        assert first is second
        assert calls == [1, 1]
        info = load.cache_info()
        assert info.currsize == 0
        assert info.bytes == 0
        assert budget.used_bytes == 0

    def test_cache_clear_releases_bytes(self):
        budget = ByteBudget(1_000_000)
        cache = ByteLruCache(budget)

        @cache
        def load(key: int) -> list[float]:
            return _value(100)

        load(1)
        load(2)
        assert load.cache_info().currsize == 2
        load.cache_clear()
        assert load.cache_info().currsize == 0
        assert load.cache_info().bytes == 0
        assert budget.used_bytes == 0
        load(1)
        assert load.cache_info().currsize == 1

    def test_budget_shared_between_two_cached_functions(self):
        size = estimate_size(_value(100))
        budget = ByteBudget(2 * size)
        first_cache = ByteLruCache(budget)
        second_cache = ByteLruCache(budget)

        @first_cache
        def first(key: int) -> list[float]:
            return _value(100)

        @second_cache
        def second(key: int) -> list[float]:
            return _value(100)

        first(1)
        second(1)
        assert budget.used_bytes == 2 * size
        assert budget.used_bytes <= budget.limit_bytes

        first(2)
        assert budget.used_bytes <= budget.limit_bytes
        assert second.cache_info().hits == 0
        assert second.cache_info().currsize == 1
        second(1)
        assert second.cache_info().hits == 1

    def test_concurrent_access_is_correct_and_safe(self):
        budget = ByteBudget(5_000_000)
        cache = ByteLruCache(budget)
        calls: list[int] = []
        failures: list[BaseException] = []

        @cache
        def load(key: int) -> tuple[int, int]:
            calls.append(key)
            time.sleep(0.01)
            return key, key * 2

        results: dict[int, list[tuple[int, int]]] = {}
        guard = threading.Lock()

        def worker(worker_id: int) -> None:
            try:
                for key in range(8):
                    result = load(key)
                    with guard:
                        results.setdefault(worker_id, []).append(result)
            except BaseException as exc:  # pragma: no cover - reported below
                failures.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not failures
        assert all(not thread.is_alive() for thread in threads)
        for worker_id, values in results.items():
            assert values == [(key, key * 2) for key in range(8)]
        assert load.cache_info().currsize == 8
        assert load.cache_info().hits > 0
        assert len(calls) >= 8
        assert budget.used_bytes <= budget.limit_bytes


class TestBudgetFromEnv:
    def test_default_when_env_absent(self):
        assert budget_bytes_from_env({}) == DEFAULT_BUDGET_MB * 1024 * 1024

    @pytest.mark.parametrize("raw", ["abc", "", "0", "-5", "1.5", "  ", "12MB"])
    def test_invalid_values_fall_back_to_default(self, raw):
        assert budget_bytes_from_env({ENV_VAR: raw}) == DEFAULT_BUDGET_MB * 1024 * 1024

    def test_valid_value_is_honoured(self):
        assert budget_bytes_from_env({ENV_VAR: "64"}) == 64 * 1024 * 1024
        assert budget_bytes_from_env({ENV_VAR: " 1 "}) == 1 * 1024 * 1024


class TestMeshRouterIntegration:
    def test_decorated_helpers_share_one_budget(self):
        budget = budget_bytes_from_env(os.environ)
        helpers = (
            meshes_router._get_decimated_vertices_cached,
            meshes_router._get_roi_vertices_cached,
            meshes_router._get_contours_cached,
            meshes_router._get_breaklines_cached,
            meshes_router._build_horizontal_deviation_cached,
        )
        for helper in helpers:
            assert helper.cache_info().limit_bytes == budget
            assert helper.cache.budget is helpers[0].cache.budget

    def test_cached_helper_matches_uncached_result(self, monkeypatch):
        import trimesh

        mesh = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
        get_mesh = lambda _mesh_id: mesh
        get_mesh.cache_clear = meshes_router.db.get_trimesh_by_id.cache_clear
        monkeypatch.setattr(meshes_router.db, "get_trimesh_by_id", get_mesh)

        meshes_router._get_decimated_vertices_cached.cache_clear()
        cached = meshes_router._get_decimated_vertices_cached("mesh-1", 8)
        raw = meshes_router._get_decimated_vertices_cached.__wrapped__("mesh-1", 8)
        again = meshes_router._get_decimated_vertices_cached("mesh-1", 8)

        assert set(cached) == set(raw) == {"x", "y", "z", "faces"}
        for axis in ("x", "y", "z"):
            assert len(cached[axis]) == len(raw[axis])
            np.testing.assert_allclose(cached[axis], raw[axis])
        assert len(cached["faces"]) == len(raw["faces"])
        assert again is cached
        meshes_router._get_decimated_vertices_cached.cache_clear()
