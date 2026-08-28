"""Tests for the step1 mesh decimation cache and surface state cleanup.

``ui.step1_upload._cached_decimate`` is a ``st.cache_resource`` function
whose ``_mesh`` argument is excluded from the cache hash. Design and topo
share the same target face count, so the cache must also be keyed by an
explicit hashable identity key (role + source + file) or the second mesh
may receive the first mesh's decimation. These tests exercise that keying
without a running Streamlit server: the module is reloaded against a fake
``streamlit`` whose ``cache_resource`` hashes exactly the non-underscore
arguments, mirroring the real behaviour.
"""
import contextlib
import functools
import importlib
import inspect
import sys

import numpy as np
import pytest
import trimesh

import ui.step1_upload as step1

TARGET = 30000


def _box():
    return trimesh.creation.box(extents=[10.0, 10.0, 5.0])


def _sphere():
    return trimesh.creation.icosphere(subdivisions=2, radius=7.0)


# ---------------------------------------------------------------------------
# Fake Streamlit runtime
# ---------------------------------------------------------------------------

class _FakeCacheResource:
    """Mimic ``st.cache_resource``: hash only non-underscore arguments.

    Usable both as ``cache_resource(**options)`` returning a decorator and
    as ``cache_resource.clear()``.
    """

    def __init__(self):
        self.entries = {}

    def __call__(self, func=None, **kwargs):
        if func is None:
            def deco(f):
                return self._wrap(f)
            return deco
        return self._wrap(func)

    def _wrap(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            params = list(inspect.signature(func).parameters)
            public = tuple(
                (params[i], value)
                for i, value in enumerate(args)
                if i < len(params) and not params[i].startswith("_")
            )
            extra = tuple(args[len(params):])
            key = (public, tuple(sorted(kwargs.items())), extra)
            if key not in self.entries:
                self.entries[key] = func(*args, **kwargs)
            return self.entries[key]
        return wrapper

    def clear(self):
        self.entries.clear()


class _FakeSession:
    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None


class _FakeStreamlitModule:
    def __init__(self):
        self.session_state = _FakeSession()
        self.cache_resource = _FakeCacheResource()
        self.cache_data = _FakeCacheResource()
        self.spinners = []

    @contextlib.contextmanager
    def spinner(self, text=""):
        self.spinners.append(text)
        yield

    def fragment(self, func):
        return func

    def error(self, msg):
        pass

    def rerun(self):
        pass


def _fresh_step1(monkeypatch):
    """Reload ``ui.step1_upload`` against a fresh fake Streamlit module."""
    fake = _FakeStreamlitModule()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return importlib.reload(step1)


def _tagged_decimate(calls):
    def fake_decimate(mesh, target_faces=None):
        calls.append(id(mesh))
        out = trimesh.Trimesh(vertices=np.asarray(mesh.vertices).copy(),
                              faces=np.asarray(mesh.faces).copy(), process=False)
        out._source_id = id(mesh)
        return out
    return fake_decimate


def _cache_roles(cache):
    roles = set()
    for key in cache.entries:
        for name, value in key[0]:
            if name == 'mesh_cache_key':
                roles.add(value[0])
    return roles


# ---------------------------------------------------------------------------
# build_mesh_cache_key: explicit hashable identity/source key
# ---------------------------------------------------------------------------

class TestMeshCacheKey:
    def test_is_a_hashable_tuple(self):
        key = step1.build_mesh_cache_key("topo", _box(), "t.stl", 200)
        assert isinstance(key, tuple)
        hash(key)

    def test_distinct_for_design_and_topo(self):
        mesh = _box()
        design = step1.build_mesh_cache_key("design", mesh, "d.stl", 100)
        topo = step1.build_mesh_cache_key("topo", mesh, "d.stl", 100)
        assert design != topo

    def test_changes_when_object_file_or_size_changes(self):
        mesh = _box()
        base = step1.build_mesh_cache_key("topo", mesh, "t.stl", 200)
        assert step1.build_mesh_cache_key("topo", _box(), "t.stl", 200) != base
        assert step1.build_mesh_cache_key("topo", mesh, "t2.stl", 200) != base
        assert step1.build_mesh_cache_key("topo", mesh, "t.stl", 999) != base

    def test_deterministic_for_same_inputs(self):
        mesh = _box()
        a = step1.build_mesh_cache_key("topo", mesh, "t.stl", 200)
        b = step1.build_mesh_cache_key("topo", mesh, "t.stl", 200)
        assert a == b


# ---------------------------------------------------------------------------
# _cached_decimate: no cross-mesh collision under the same target
# ---------------------------------------------------------------------------

class TestCachedDecimate:
    def test_two_meshes_same_target_do_not_collide(self, monkeypatch):
        mod = _fresh_step1(monkeypatch)
        calls = []
        monkeypatch.setattr(mod, "decimate_mesh", _tagged_decimate(calls))

        design = _box()
        topo = _sphere()
        key_design = mod.build_mesh_cache_key("design", design, "d.stl", 100)
        key_topo = mod.build_mesh_cache_key("topo", topo, "t.stl", 200)

        out_design = mod._cached_decimate(key_design, design, TARGET)
        out_topo = mod._cached_decimate(key_topo, topo, TARGET)

        assert out_design._source_id == id(design)
        assert out_topo._source_id == id(topo)
        assert out_design is not out_topo
        assert calls == [id(design), id(topo)]

    def test_same_key_and_target_reuses_cache(self, monkeypatch):
        mod = _fresh_step1(monkeypatch)
        calls = []
        monkeypatch.setattr(mod, "decimate_mesh", _tagged_decimate(calls))

        topo = _sphere()
        key = mod.build_mesh_cache_key("topo", topo, "t.stl", 200)
        first = mod._cached_decimate(key, topo, TARGET)
        second = mod._cached_decimate(key, topo, TARGET)

        assert first is second
        assert calls == [id(topo)]

    def test_different_targets_are_distinct(self, monkeypatch):
        mod = _fresh_step1(monkeypatch)
        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            out = trimesh.Trimesh(vertices=np.asarray(mesh.vertices).copy(),
                                  faces=np.asarray(mesh.faces).copy(), process=False)
            out._target = target_faces
            return out

        monkeypatch.setattr(mod, "decimate_mesh", fake_decimate)

        topo = _sphere()
        key = mod.build_mesh_cache_key("topo", topo, "t.stl", 200)
        out_10k = mod._cached_decimate(key, topo, 10000)
        out_30k = mod._cached_decimate(key, topo, 30000)

        assert out_10k._target == 10000
        assert out_30k._target == 30000
        assert calls == [10000, 30000]

    def test_cache_clear_rebuilds(self, monkeypatch):
        mod = _fresh_step1(monkeypatch)
        calls = []
        monkeypatch.setattr(mod, "decimate_mesh", _tagged_decimate(calls))

        topo = _sphere()
        key = mod.build_mesh_cache_key("topo", topo, "t.stl", 200)
        first = mod._cached_decimate(key, topo, TARGET)

        mod.st.cache_resource.clear()
        second = mod._cached_decimate(key, topo, TARGET)

        assert second is not first
        assert calls == [id(topo), id(topo)]


# ---------------------------------------------------------------------------
# Surface state cleanup: high-res plan mesh is wiped too
# ---------------------------------------------------------------------------

class TestSurfaceStateCleanup:
    def test_clear_surface_state_resets_plan_mesh(self, monkeypatch):
        mod = _fresh_step1(monkeypatch)
        ss = mod.st.session_state
        ss.plan_mesh_topo = _box()
        ss.plan_mesh_topo_token = ("stale", 1, 2)
        ss.decimated_mesh_topo = _box()
        ss.mesh_topo = _box()
        ss.mesh_design = _box()

        mod._clear_surface_state()

        assert ss.get('plan_mesh_topo') is None
        assert ss.get('plan_mesh_topo_token') is None
        assert ss.get('decimated_mesh_topo') is None
        assert ss.get('mesh_topo') is None
        assert ss.get('mesh_design') is None
        assert ss.get('decimated_mesh_design') is None

    def test_load_meshes_clears_plan_and_uses_distinct_keys(self, monkeypatch):
        mod = _fresh_step1(monkeypatch)
        mod.st.session_state.step = 1

        def fake_load_mesh(path):
            return _box() if "design" in path else _sphere()

        monkeypatch.setattr(mod, "load_mesh", fake_load_mesh)
        monkeypatch.setattr(mod, "decimate_mesh", lambda mesh, target_faces=None: mesh)

        class FakeFile:
            def __init__(self, name, size):
                self.name = name
                self.size = size

            def read(self):
                return b""

        mod._load_meshes(FakeFile("design.stl", 100), FakeFile("topo.stl", 200))

        ss = mod.st.session_state
        assert ss.get('plan_mesh_topo') is None
        assert ss.get('plan_mesh_topo_token') is None
        assert ss.decimated_mesh_design is not None
        assert ss.decimated_mesh_topo is not None
        assert _cache_roles(mod.st.cache_resource) == {"design", "topo"}
