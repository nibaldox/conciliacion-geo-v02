from __future__ import annotations

import warnings as python_warnings
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from core.config import DRILL_COMPLIANCE, DrillComplianceDefaults
from core.geom_utils import find_df_column

_DRILL_COL_ALIASES = {
    "Pozo": ["Pozo", "label_pozo", "id_pozo", "Hole_ID", "Nombre_Pozo"],
    "X": ["X", "X_Diseno", "Este", "Latitud_Geo", "Latitud"],
    "Y": ["Y", "Y_Diseno", "Norte", "Longitud_Geo", "Longitud"],
    "Z_collar": ["Z_collar", "Z_Diseno", "Cota_Collar", "Z"],
    "Incl": ["Incl", "Incl_Diseno", "Inclinacion_real", "Design_Dip"],
    "Az": ["Az", "Az_Diseno", "Azimuth_real", "Design_Azimuth"],
    "Len": ["Len", "Len_Diseno", "longitud_real", "Length"],
    "Kilos": ["Kilos", "Kilos_Diseno", "Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg"],
}

_DELTAS = (
    ("delta_x", "X", "delta_x_m"),
    ("delta_y", "Y", "delta_y_m"),
    ("delta_z_collar", "Z_collar", "delta_z_m"),
    ("delta_incl", "Incl", "delta_incl_deg"),
    ("delta_az", "Az", "delta_az_deg"),
    ("delta_len", "Len", "delta_len_m"),
    ("delta_kg_pct", "Kilos", "delta_kg_pct"),
)


def _empty_result(messages: list[str] | None = None) -> dict[str, Any]:
    return {
        "per_hole": pd.DataFrame(),
        "aggregates": {},
        "compliance_score": None,
        "per_group": None,
        "unmatched": {"design": [], "actual": []},
        "warnings": messages or [],
    }


def _resolve_columns(
    df: pd.DataFrame, required: set[str]
) -> tuple[pd.DataFrame, dict[str, str | None]]:
    resolved: dict[str, str | None] = {}
    normalized = df.copy()
    for canonical, aliases in _DRILL_COL_ALIASES.items():
        column = find_df_column(df, aliases, raise_error=canonical in required)
        resolved[canonical] = column
        normalized[canonical] = df[column] if column else np.nan
    for column in ("X", "Y", "Z_collar", "Incl", "Az", "Len", "Kilos"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized, resolved


def _identity_values(df: pd.DataFrame, label_column: str | None, indexes: list[Any]) -> list[Any]:
    if label_column:
        return df.loc[indexes, label_column].tolist()
    return indexes


def compute_drill_compliance(
    design_df: pd.DataFrame | None,
    actual_df: pd.DataFrame | None,
    match_by: Literal["label", "nearest"] = "label",
    tolerances: DrillComplianceDefaults | None = None,
    group_by: str | list[str] | None = None,
) -> dict[str, Any]:
    messages: list[str] = []

    def warn(message: str) -> None:
        messages.append(message)
        python_warnings.warn(message, UserWarning, stacklevel=2)

    if design_df is None or design_df.empty:
        warn("No design data provided; drill compliance analysis skipped.")
        return _empty_result(messages)
    if actual_df is None or actual_df.empty:
        warn("No actual drill data provided; drill compliance analysis skipped.")
        return _empty_result(messages)
    if match_by not in {"label", "nearest"}:
        raise ValueError("match_by must be 'label' or 'nearest'")

    try:
        design, design_columns = _resolve_columns(design_df, {"X", "Y"})
        actual, actual_columns = _resolve_columns(actual_df, {"X", "Y"})
    except KeyError:
        warn("spatial matching impossible: required X/Y columns are missing.")
        return _empty_result(messages)

    effective_match = match_by
    if match_by == "label" and (not design_columns["Pozo"] or not actual_columns["Pozo"]):
        warn("Hole label missing; falling back to nearest spatial matching.")
        effective_match = "nearest"

    pairs: list[tuple[Any, Any]] = []
    if effective_match == "label":
        design_labels = design["Pozo"].dropna()
        actual_labels = actual["Pozo"].dropna()
        design_lookup: dict[Any, Any] = {}
        for index, label in design_labels.items():
            design_lookup.setdefault(label, index)
        pairs = [
            (design_lookup[label], index)
            for index, label in actual_labels.items()
            if label in design_lookup
        ]
    else:
        valid_design = design.dropna(subset=["X", "Y"])
        valid_actual = actual.dropna(subset=["X", "Y"])
        if not valid_design.empty and not valid_actual.empty:
            tree = cKDTree(valid_design[["X", "Y"]].to_numpy())
            distances, positions = tree.query(valid_actual[["X", "Y"]].to_numpy(), k=1)
            design_indexes = valid_design.index.to_numpy()
            actual_indexes = valid_actual.index.to_numpy()
            pairs = [
                (design_indexes[position], actual_indexes[offset])
                for offset, (distance, position) in enumerate(zip(distances, positions))
                if distance <= (tolerances or DRILL_COMPLIANCE).nearest_radius_m
            ]

    matched_design = {design_index for design_index, _ in pairs}
    matched_actual = {actual_index for _, actual_index in pairs}
    unmatched_design_indexes = [index for index in design.index if index not in matched_design]
    unmatched_actual_indexes = [index for index in actual.index if index not in matched_actual]
    unmatched = {
        "design": _identity_values(design_df, design_columns["Pozo"], unmatched_design_indexes),
        "actual": _identity_values(actual_df, actual_columns["Pozo"], unmatched_actual_indexes),
    }
    if not pairs:
        result = _empty_result(messages)
        result["unmatched"] = unmatched
        return result

    rows: list[dict[str, Any]] = []
    group_columns = [group_by] if isinstance(group_by, str) else (group_by or [])
    for design_index, actual_index in pairs:
        design_row = design.loc[design_index]
        actual_row = actual.loc[actual_index]
        row: dict[str, Any] = {
            "label": actual_row["Pozo"] if pd.notna(actual_row["Pozo"]) else design_row["Pozo"],
            "match_method": effective_match,
        }
        for output, source, _ in _DELTAS:
            design_value = design_row[source]
            actual_value = actual_row[source]
            if pd.isna(design_value) or pd.isna(actual_value):
                row[output] = np.nan
            elif output == "delta_az":
                row[output] = ((actual_value - design_value + 180.0) % 360.0) - 180.0
            elif output == "delta_kg_pct":
                row[output] = abs(actual_value - design_value) / max(design_value, 1.0) * 100.0
            else:
                row[output] = actual_value - design_value
        for column in group_columns:
            resolved_group = find_df_column(actual_df, [column], raise_error=False)
            row[column] = actual_df.loc[actual_index, resolved_group] if resolved_group else np.nan
        rows.append(row)

    per_hole = pd.DataFrame(rows)
    active_tolerances = tolerances or DRILL_COMPLIANCE
    pass_columns: list[str] = []
    aggregates: dict[str, float] = {}
    for delta, _, tolerance_field in _DELTAS:
        pass_column = f"{delta}_within_tol"
        per_hole[pass_column] = per_hole[delta].notna() & (
            per_hole[delta].abs() <= getattr(active_tolerances, tolerance_field)
        )
        pass_columns.append(pass_column)
        aggregates[delta] = float(per_hole[delta].abs().mean())
    per_hole["all_within_tol"] = per_hole[pass_columns].all(axis=1)
    compliance_score = float(per_hole["all_within_tol"].mean())

    per_group = None
    if group_columns:
        group_rows: list[dict[str, Any]] = []
        grouper: str | list[str] = group_columns[0] if len(group_columns) == 1 else group_columns
        for keys, group in per_hole.groupby(grouper, dropna=False):
            key_values = (keys,) if len(group_columns) == 1 else keys
            group_row = dict(zip(group_columns, key_values))
            group_row["n"] = len(group)
            group_row["compliance_score"] = float(group["all_within_tol"].mean())
            for delta, _, _ in _DELTAS:
                group_row[f"mean_abs_{delta}"] = float(group[delta].abs().mean())
                group_row[f"within_tol_pct_{delta}"] = float(group[f"{delta}_within_tol"].mean() * 100.0)
            group_rows.append(group_row)
        per_group = pd.DataFrame(group_rows)

    return {
        "per_hole": per_hole,
        "aggregates": aggregates,
        "compliance_score": compliance_score,
        "per_group": per_group,
        "unmatched": unmatched,
        "warnings": messages,
    }
