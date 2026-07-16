"""Centralized session_state access for the tronadura module."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.state_keys import StateKey


def _get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def _set(key: str, value: Any) -> None:
    st.session_state[key] = value


# Reference lines (shared with sidebar)
def get_ref_line_traces() -> dict:
    return _get("ref_line_traces", {})


# Cached file name used to invalidate processed state on reload
def get_blast_cached_name() -> str | None:
    return _get("blast_cached_name")


def set_blast_cached_name(name: str) -> None:
    _set("blast_cached_name", name)


# Processed blast dataframe
def get_blast_df() -> pd.DataFrame | None:
    return _get(StateKey.BLAST_DF_CLEAN)


def set_blast_df(df: pd.DataFrame | None) -> None:
    _set(StateKey.BLAST_DF_CLEAN, df)


# 3D line arrays built from collar-toe segments
def get_blast_lines() -> tuple[Any, Any, Any]:
    return _get("blast_x_lines"), _get("blast_y_lines"), _get("blast_z_lines")


def set_blast_lines(x_lines, y_lines, z_lines) -> None:
    _set("blast_x_lines", x_lines)
    _set("blast_y_lines", y_lines)
    _set("blast_z_lines", z_lines)


def clear_blast_lines() -> None:
    _set("blast_x_lines", None)
    _set("blast_y_lines", None)
    _set("blast_z_lines", None)


# Processing flag
def get_blast_processed() -> bool:
    return _get("blast_processed", False)


def set_blast_processed(value: bool) -> None:
    _set("blast_processed", value)


def reset_blast_processed_state() -> None:
    set_blast_cached_name("")
    set_blast_df(None)
    clear_blast_lines()
    set_blast_processed(False)


# Meshes (shared with conciliación module)
def get_mesh_design():
    return _get("mesh_design")


def get_mesh_topo():
    return _get("mesh_topo")


def get_decimated_mesh_design():
    return _get("decimated_mesh_design")


def set_decimated_mesh_design(mesh) -> None:
    _set("decimated_mesh_design", mesh)


def get_decimated_mesh_topo():
    return _get("decimated_mesh_topo")


def set_decimated_mesh_topo(mesh) -> None:
    _set("decimated_mesh_topo", mesh)


# IDW energy grid
def get_last_idw_grid() -> dict | None:
    return _get("last_idw_grid")


def set_last_idw_grid(grid: dict) -> None:
    _set("last_idw_grid", grid)


def get_idw_grid_params() -> tuple[int, int, int, float]:
    nx = int(_get("idw_nx", 25))
    ny = int(_get("idw_ny", 25))
    nz = int(_get("idw_nz", 5))
    radius = float(_get("idw_radius", 30.0))
    return nx, ny, nz, radius


def set_idw_grid_params(nx: int, ny: int, nz: int, radius: float) -> None:
    _set("idw_nx", nx)
    _set("idw_ny", ny)
    _set("idw_nz", nz)
    _set("idw_radius", radius)


# Conciliation results / sections (shared)
def get_comparison_results() -> list:
    return _get(StateKey.COMPARISON_RESULTS, [])


def get_sections() -> list:
    return _get(StateKey.SECTIONS, [])


def get_profiles_design() -> list:
    return _get(StateKey.PROFILES_DESIGN, [])


def get_profiles_topo() -> list:
    return _get(StateKey.PROFILES_TOPO, [])


def get_processed_sections() -> list:
    return _get("processed_sections", [])


# Sector deviation widget state
def get_sector_deviation_section_name(section_names: list[str]) -> str | None:
    return _get("sector_dev_section", section_names[0] if section_names else None)


def set_sector_deviation_section_name(name: str) -> None:
    _set("sector_dev_section", name)


def get_sector_tolerance() -> float:
    from core.config import SECTOR_DEVIATION
    return float(_get("sector_dev_tolerance", SECTOR_DEVIATION.tolerance_m))


def set_sector_tolerance(value: float) -> None:
    _set("sector_dev_tolerance", value)


# Face angle suggestion widget state
def get_sector_fs_target() -> float:
    return float(_get("sector_fs_target", 1.3))


def get_sector_rmr() -> int:
    return int(_get("sector_rmr", 60))


def get_sector_bench_h() -> int:
    return int(_get("sector_bench_h", 15))
