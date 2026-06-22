"""Tests for STL mesh validation — Sprint 3 D5."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import trimesh

from core.mesh_handler import (
    DEFAULT_MAX_MESH_SIZE_MB,
    MeshValidationError,
    _validate_stl_magic_bytes,
    _validate_stl_path,
    load_mesh,
)


def _write_stl_bytes(path: Path, header: bytes, n_triangles: int = 0) -> None:
    """Write a binary STL with the given header bytes (padded to 80) and triangle count."""
    preamble = header.ljust(80, b"\x00")[:80]
    with open(path, "wb") as fh:
        fh.write(preamble)
        fh.write(n_triangles.to_bytes(4, "little"))
        # Each triangle = 50 bytes (12 floats normal/vertices + 2 bytes attr)
        for _ in range(n_triangles):
            fh.write(b"\x00" * 50)


def _valid_cube_stl(path: Path) -> None:
    """Write a valid binary STL of a unit cube (12 triangles, 36 floats)."""
    mesh = trimesh.creation.box((1, 1, 1))
    mesh.export(str(path))


class TestPathValidation:
    def test_empty_path_raises(self):
        with pytest.raises(MeshValidationError, match="vacía"):
            _validate_stl_path("")

    def test_nonexistent_path_raises(self, tmp_path):
        missing = tmp_path / "nope.stl"
        with pytest.raises(MeshValidationError, match="no existe"):
            _validate_stl_path(str(missing))

    def test_directory_raises(self, tmp_path):
        with pytest.raises(MeshValidationError, match="no apunta a un archivo"):
            _validate_stl_path(str(tmp_path))

    def test_empty_file_raises(self, tmp_path):
        empty = tmp_path / "empty.stl"
        empty.write_bytes(b"")
        with pytest.raises(MeshValidationError, match="0 bytes"):
            _validate_stl_path(str(empty))

    def test_oversize_raises(self, tmp_path, monkeypatch):
        # Use a small custom cap so we don't have to write 200MB.
        cap_mb = 1
        # Create a file just over the cap.
        big = tmp_path / "big.stl"
        big.write_bytes(b"solid\n" + b"\x00" * (cap_mb * 1024 * 1024 + 1))
        with pytest.raises(MeshValidationError, match="demasiado grande"):
            _validate_stl_path(str(big), max_size_mb=cap_mb)

    def test_under_cap_ok(self, tmp_path):
        small = tmp_path / "small.stl"
        small.write_bytes(b"solid\n" + b"\x00" * 100)
        # Should not raise
        _validate_stl_path(str(small), max_size_mb=1)


class TestMagicBytes:
    def test_ascii_solid_prefix_ok(self, tmp_path):
        f = tmp_path / "ascii.stl"
        f.write_bytes(b"solid\n  facet normal 0 0 0\n")
        # Should not raise
        _validate_stl_magic_bytes(str(f))

    def test_uppercase_solid_prefix_ok(self, tmp_path):
        f = tmp_path / "ascii.stl"
        f.write_bytes(b"SOLID\n")
        _validate_stl_magic_bytes(str(f))

    def test_short_binary_with_valid_size_ok(self, tmp_path):
        f = tmp_path / "binary.stl"
        # Just a header, no triangles. Size >= 84 so passes magic check.
        _write_stl_bytes(f, b"\x00", n_triangles=0)
        _validate_stl_magic_bytes(str(f))

    def test_short_file_with_bad_header_raises(self, tmp_path):
        f = tmp_path / "garbage.stl"
        f.write_bytes(b"NOTSTL")
        with pytest.raises(MeshValidationError, match="no parece un STL válido"):
            _validate_stl_magic_bytes(str(f))

    def test_unreadable_file_raises(self, tmp_path, monkeypatch):
        f = tmp_path / "fake.stl"
        f.write_bytes(b"solid\n")
        # Simulate OSError on open
        def bad_open(*args, **kwargs):
            raise OSError("Permission denied")
        monkeypatch.setattr("builtins.open", bad_open)
        with pytest.raises(MeshValidationError, match="No se pudo leer"):
            _validate_stl_magic_bytes(str(f))


class TestLoadMeshIntegration:
    def test_valid_cube_loads(self, tmp_path):
        cube = tmp_path / "cube.stl"
        _valid_cube_stl(cube)
        mesh = load_mesh(str(cube))
        assert len(mesh.vertices) > 0
        assert len(mesh.faces) > 0

    def test_missing_file_raises_validation(self, tmp_path):
        with pytest.raises(MeshValidationError):
            load_mesh(str(tmp_path / "nope.stl"))

    def test_garbage_stl_raises_validation(self, tmp_path):
        bad = tmp_path / "bad.stl"
        bad.write_bytes(b"NOTSTL")
        with pytest.raises(MeshValidationError, match="no parece un STL válido"):
            load_mesh(str(bad))

    def test_mesh_validation_error_is_value_error(self):
        # Subclass relationship preserves compatibility with legacy
        # `except ValueError` callers.
        assert issubclass(MeshValidationError, ValueError)

    def test_default_cap_is_200mb(self):
        assert DEFAULT_MAX_MESH_SIZE_MB == 200
