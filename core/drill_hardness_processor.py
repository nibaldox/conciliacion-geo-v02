"""Drilling hardness processor: CSV load + spatial join to blast DataFrame.

Wraps the pure functions in core.drill_hardness with a pandas adapter.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from core.config import DRILL_HARDNESS
from core.drill_hardness import (
    DEFAULT_THRESHOLDS,
    classify_with_metric,
    hardness_index_with_metric,
    penetration_rate,
    rig_normalized_penetration,
)

_CANONICAL_COLUMNS = (
    "pozo",
    "tiempo_inicial",
    "tiempo_final",
    "profundidad_m",
    "x",
    "y",
    "rig",
    "duracion_min",
    "tasa_penetracion",
    "dureza",
    "indice_dureza",
)

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "pozo": ("pozo", "label_pozo", "id_pozo", "hole_id", "nombre_pozo"),
    "tiempo_inicial": (
        "tiempo inicial", "tiempo_inicial", "inicio", "start_time",
        "fecha inicio", "hora inicio",
    ),
    "tiempo_final": (
        "tiempo final", "tiempo_final", "fin", "end_time",
        "fecha final", "hora final",
    ),
    "profundidad_m": (
        "prof. por operador", "prof_por_operador", "profundidad_m",
        "profundidad", "depth", "depth_m", "longitud_perforacion",
    ),
    "x": ("coord. este [m]", "coord este [m]", "este", "x", "este_m", "x_collar"),
    "y": ("coord. norte [m]", "coord norte [m]", "norte", "y", "norte_m", "y_collar"),
    "rig": ("equipo", "perforadora", "rig", "maquina", "machine"),
}


def _empty_canonical_df() -> pd.DataFrame:
    df = pd.DataFrame({col: pd.Series(dtype=object) for col in _CANONICAL_COLUMNS})
    return df


def _normalize_column_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return (
        name.strip()
        .lower()
        .replace("\u00a0", " ")
        .replace("\u2013", "-")
    )


def _resolve_input_columns(df: pd.DataFrame) -> dict[str, str | None]:
    normalized = {_normalize_column_name(col): col for col in df.columns}
    resolved: dict[str, str | None] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        match: str | None = None
        for alias in aliases:
            if alias in normalized:
                match = normalized[alias]
                break
        resolved[canonical] = match
    return resolved


def _collapse_reperforados(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the last drilling event per Pozo (max Tiempo Final)."""
    if "pozo" not in df.columns or df["pozo"].isna().all():
        return df.copy()
    if "tiempo_final" not in df.columns:
        return df.copy()
    valid = df.dropna(subset=["pozo", "tiempo_final"])
    if valid.empty:
        return df.copy()
    idx = valid.groupby("pozo")["tiempo_final"].idxmax()
    return valid.loc[idx].copy()


def _classify_duration(row: pd.Series) -> tuple[Any, float | None]:
    duracion = row.get("duracion_min")
    if duracion is None or not np.isfinite(duracion):
        return (None, None)
    cat = classify_with_metric(float(duracion), DEFAULT_THRESHOLDS, "duration")
    idx_val = hardness_index_with_metric(float(duracion), DEFAULT_THRESHOLDS, "duration")
    return (cat, idx_val)


def _classify_rate(row: pd.Series) -> tuple[Any, float | None]:
    rate = row.get("tasa_penetracion")
    if rate is None or not np.isfinite(rate):
        return (None, None)
    cat = classify_with_metric(float(rate), DEFAULT_THRESHOLDS, "penetration_rate")
    idx_val = hardness_index_with_metric(float(rate), DEFAULT_THRESHOLDS, "penetration_rate")
    return (cat, idx_val)


def _safe_read_csv(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, engine="python", on_bad_lines="warn")
    except (FileNotFoundError, OSError, ValueError, pd.errors.EmptyDataError):
        return _empty_canonical_df()


def load_drilling_csv(file_path: str) -> pd.DataFrame:
    """Parse a drilling rig CSV and return a normalized DataFrame.

    Required canonical columns (lowercase, snake_case):
    ``pozo``, ``tiempo_inicial``, ``tiempo_final``, ``x``, ``y``.
    Optional: ``profundidad_m``, ``rig``.

    Returns an empty canonical-schema DataFrame on read failure.
    Never raises.
    """
    df = _safe_read_csv(file_path)
    if df.empty:
        return _empty_canonical_df()

    if "pozo" not in {_normalize_column_name(c) for c in df.columns}:
        return _empty_canonical_df()

    resolved = _resolve_input_columns(df)
    if resolved["x"] is None or resolved["y"] is None:
        return _empty_canonical_df()

    out = pd.DataFrame()
    out["pozo"] = df[resolved["pozo"]].astype(object) if resolved["pozo"] else np.nan

    def _parse_ts(col: str) -> pd.Series:
        if resolved.get(col) is None:
            return pd.Series([pd.NaT] * len(df), index=df.index)
        return pd.to_datetime(df[resolved[col]], errors="coerce", dayfirst=True)

    out["tiempo_inicial"] = _parse_ts("tiempo_inicial")
    out["tiempo_final"] = _parse_ts("tiempo_final")
    out["profundidad_m"] = (
        pd.to_numeric(df[resolved["profundidad_m"]], errors="coerce")
        if resolved["profundidad_m"]
        else pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    )
    out["x"] = (
        pd.to_numeric(df[resolved["x"]], errors="coerce")
        if resolved["x"]
        else pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    )
    out["y"] = (
        pd.to_numeric(df[resolved["y"]], errors="coerce")
        if resolved["y"]
        else pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    )
    out["rig"] = (
        df[resolved["rig"]].astype(object)
        if resolved["rig"]
        else pd.Series(["?"] * len(df), index=df.index, dtype=object)
    )

    out = _collapse_reperforados(out)
    if out.empty:
        return _empty_canonical_df()

    delta = (out["tiempo_final"] - out["tiempo_inicial"]).dt.total_seconds() / 60.0
    out["duracion_min"] = pd.to_numeric(delta, errors="coerce")

    rate = out.apply(
        lambda r: penetration_rate(
            float(r["profundidad_m"]) if np.isfinite(r["profundidad_m"]) else float("nan"),
            float(r["duracion_min"]) if np.isfinite(r["duracion_min"]) else float("nan"),
        ),
        axis=1,
    )
    out["tasa_penetracion"] = pd.to_numeric(rate, errors="coerce")

    use_rate = out["tasa_penetracion"].notna() & np.isfinite(out["tasa_penetracion"])
    cats: list[Any] = [None] * len(out)
    indices: list[float | None] = [None] * len(out)
    for i, row in enumerate(out.itertuples(index=False)):
        if use_rate.iloc[i]:
            cat, idx_val = _classify_rate(out.iloc[i])
        else:
            cat, idx_val = _classify_duration(out.iloc[i])
        cats[i] = cat
        indices[i] = idx_val
    out["dureza"] = pd.Series(cats, index=out.index, dtype=object)
    out["indice_dureza"] = pd.to_numeric(pd.Series(indices, index=out.index), errors="coerce")

    if "rig" in out.columns and out["rig"].notna().any():
        rig_groups = out.groupby("rig")["tasa_penetracion"]
        out["rig_avg_rate"] = out["rig"].map(rig_groups.transform("mean"))
        out["rig_std_rate"] = out["rig"].map(rig_groups.transform("std"))
    else:
        out["rig_avg_rate"] = np.nan
        out["rig_std_rate"] = np.nan

    def _zscore(row: pd.Series) -> float:
        rate = row.get("tasa_penetracion")
        avg = row.get("rig_avg_rate")
        std = row.get("rig_std_rate")
        return rig_normalized_penetration(rate, avg, std)

    out["rig_zscore"] = out.apply(_zscore, axis=1).astype(float)

    return out


def _resolve_blast_xy(blast_df: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    east_aliases = ("x", "este", "x_collar", "latitud_geo", "este_m")
    north_aliases = ("y", "norte", "y_collar", "longitud_geo", "norte_m")
    normalized = {_normalize_column_name(c): c for c in blast_df.columns}

    east = next((normalized[a] for a in east_aliases if a in normalized), None)
    north = next((normalized[a] for a in north_aliases if a in normalized), None)
    if east is None or north is None:
        return None
    return (
        pd.to_numeric(blast_df[east], errors="coerce"),
        pd.to_numeric(blast_df[north], errors="coerce"),
    )


def _resolve_drilling_xy(drilling_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    return (
        pd.to_numeric(drilling_df["x"], errors="coerce"),
        pd.to_numeric(drilling_df["y"], errors="coerce"),
    )


def enrich_blast_with_hardness(
    blast_df: pd.DataFrame,
    drilling_df: pd.DataFrame,
    radius: float = DRILL_HARDNESS.radius_m,
) -> pd.DataFrame:
    """Spatial-join drilling hardness onto blast holes via cKDTree.

    Parameters
    ----------
    blast_df : pd.DataFrame
        Output of ``procesar_pozos``. Must have X/East and Y/North cols.
    drilling_df : pd.DataFrame
        Output of ``load_drilling_csv``.
    radius : float, default 2.0
        Maximum spatial distance (m) for a match.

    Returns
    -------
    pd.DataFrame
        Copy of ``blast_df`` augmented with hardness columns. Holes beyond
        ``radius`` (or with no valid drilling event within range) receive
        NaN hardness fields.
    """
    hardness_columns = (
        "dureza",
        "indice_dureza",
        "tasa_penetracion",
        "duracion_min",
        "rig",
        "rig_zscore",
        "distancia_pozo_perf_m",
        "perforadora",
    )

    if blast_df is None:
        return blast_df
    if blast_df.empty:
        out = blast_df.copy()
        for col in hardness_columns:
            out[col] = np.nan
        return out
    if drilling_df is None or drilling_df.empty:
        out = blast_df.copy()
        for col in hardness_columns:
            out[col] = np.nan
        return out

    blast_xy = _resolve_blast_xy(blast_df)
    if blast_xy is None:
        out = blast_df.copy()
        for col in hardness_columns:
            out[col] = np.nan
        return out

    blast_x, blast_y = blast_xy
    drill_x, drill_y = _resolve_drilling_xy(drilling_df)

    valid_drill = drill_x.notna() & drill_y.notna()
    if not valid_drill.any():
        out = blast_df.copy()
        for col in hardness_columns:
            out[col] = np.nan
        return out

    drill_xy = np.column_stack([drill_x[valid_drill].to_numpy(), drill_y[valid_drill].to_numpy()])
    valid_drill_df = drilling_df.loc[valid_drill].reset_index(drop=True)

    tree = cKDTree(drill_xy)
    out = blast_df.copy()

    valid_blast = blast_x.notna() & blast_y.notna()
    matched_dureza = pd.Series([np.nan] * len(out), index=out.index, dtype=object)
    matched_indice = pd.Series([np.nan] * len(out), index=out.index, dtype=float)
    matched_tasa = pd.Series([np.nan] * len(out), index=out.index, dtype=float)
    matched_dur = pd.Series([np.nan] * len(out), index=out.index, dtype=float)
    matched_rig = pd.Series([np.nan] * len(out), index=out.index, dtype=object)
    matched_z = pd.Series([np.nan] * len(out), index=out.index, dtype=float)
    matched_dist = pd.Series([np.nan] * len(out), index=out.index, dtype=float)
    matched_perf = pd.Series([np.nan] * len(out), index=out.index, dtype=object)

    if valid_blast.any():
        query_pts = np.column_stack([
            blast_x[valid_blast].to_numpy(),
            blast_y[valid_blast].to_numpy(),
        ])
        distances, positions = tree.query(query_pts, k=1)
        blast_valid_index = out.index[valid_blast]
        for offset, (dist, pos) in enumerate(zip(distances, positions)):
            if dist <= radius and pos < len(valid_drill_df):
                drill_row = valid_drill_df.iloc[int(pos)]
                blast_idx = blast_valid_index[offset]
                matched_dureza.at[blast_idx] = drill_row.get("dureza")
                matched_indice.at[blast_idx] = drill_row.get("indice_dureza")
                matched_tasa.at[blast_idx] = drill_row.get("tasa_penetracion")
                matched_dur.at[blast_idx] = drill_row.get("duracion_min")
                matched_rig.at[blast_idx] = drill_row.get("rig")
                matched_z.at[blast_idx] = drill_row.get("rig_zscore")
                matched_dist.at[blast_idx] = float(dist)
                matched_perf.at[blast_idx] = drill_row.get("rig")

    out["dureza"] = matched_dureza
    out["indice_dureza"] = pd.to_numeric(matched_indice, errors="coerce")
    out["tasa_penetracion"] = pd.to_numeric(matched_tasa, errors="coerce")
    out["duracion_min"] = pd.to_numeric(matched_dur, errors="coerce")
    out["rig"] = matched_rig
    out["rig_zscore"] = pd.to_numeric(matched_z, errors="coerce")
    out["distancia_pozo_perf_m"] = pd.to_numeric(matched_dist, errors="coerce")
    out["perforadora"] = matched_perf

    return out
