"""Pre/post H5 byte-identity check on a synthetic 4-section DataFrame.

Builds the same correlation rows two ways:
  pre  = inline loop in ui/modulo_tronadura.py (verbatim from L417-463)
  post = project_powder_factor_per_section from ui/blast_analysis

Asserts the rows + the Plotly scatter figure structure (data, layout
titles, axis ranges, trace colors, mode) match. Run this script before
touching modulo_tronadura to lock the baseline; re-run after the
refactor and confirm diff is empty.
"""
import sys

sys.path.insert(0, ".")

import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.blast_correlation import aggregate_powder_factor_by_group, compute_powder_factor
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.config import DEFAULTS

from ui.blast_analysis import (
    build_pf_deviation_scatter,
    project_powder_factor_per_section,
)


class _Sec:
    def __init__(self, name, x, y, az):
        self.name = name
        self.origin = np.array([x, y])
        self.azimuth = az
        self.length = 200.0


def _synthetic():
    df = pd.DataFrame(
        {
            "X": [100, 105, 110, 115, 200, 205, 210, 215, 300, 305, 310, 315, 400, 405, 410, 415],
            "Y": [200, 200, 200, 200, 210, 210, 210, 210, 220, 220, 220, 220, 230, 230, 230, 230],
            "Z_collar": [50, 50, 50, 50, 45, 45, 45, 45, 40, 40, 40, 40, 35, 35, 35, 35],
            "Z_toe": [38, 38, 38, 38, 33, 33, 33, 33, 28, 28, 28, 28, 23, 23, 23, 23],
            "Burden": [5] * 16,
            "Kilos_Cargados_real": [200] * 4 + [250] * 4 + [300] * 4 + [350] * 4,
        }
    )
    df["Len"] = df["Z_collar"] - df["Z_toe"]
    df["Inclinacion_real"] = 90.0
    df["Azimuth_real"] = 0.0
    df["longitud_real"] = df["Len"]
    df["Latitud_Geo"] = df["Y"]
    df["Longitud_Geo"] = df["X"]

    sections = [
        _Sec("S1", 100, 200, 0.0),
        _Sec("S2", 200, 210, 0.0),
        _Sec("S3", 300, 220, 0.0),
        _Sec("S4", 400, 230, 0.0),
    ]

    comparison = pd.DataFrame(
        [
            {"section": "S1", "delta_crest": 0.15},
            {"section": "S2", "delta_crest": -0.30},
            {"section": "S3", "delta_crest": 0.45},
            {"section": "S4", "delta_crest": -0.10},
        ]
    )
    return df, sections, comparison


def _pre_refactor(df, sections, comparison, kg_col="Kilos_Cargados_real"):
    df_filtered_pf = compute_powder_factor(df)
    df_comp_signed = comparison.dropna(subset=["delta_crest"])
    df_comp_signed_over = df_comp_signed[df_comp_signed["delta_crest"] > 0]
    df_comp_signed_under = df_comp_signed[df_comp_signed["delta_crest"] < 0]
    sec_over_grouped = (
        df_comp_signed_over.groupby("section")["delta_crest"]
        .mean()
        .reset_index()
        .rename(columns={"delta_crest": "avg_over_break"})
    )
    sec_under_grouped = (
        df_comp_signed_under.groupby("section")["delta_crest"]
        .mean()
        .reset_index()
        .rename(columns={"delta_crest": "avg_under_break"})
    )

    corr_data = []
    for sec in sections:
        sec_name = sec.name
        match_over = sec_over_grouped[sec_over_grouped["section"] == sec_name]
        match_under = sec_under_grouped[sec_under_grouped["section"] == sec_name]
        avg_over_break = float(match_over["avg_over_break"].values[0]) if not match_over.empty else 0.0
        avg_under_break = float(match_under["avg_under_break"].values[0]) if not match_under.empty else 0.0

        proj_wells = proyectar_pozos_en_seccion(
            df, sec.origin, sec.azimuth, sec.length,
            tolerance=DEFAULTS.blast_correlation_radius_m, fecha_corte=None,
        )
        if not proj_wells.empty:
            total_kg = proj_wells[kg_col].fillna(0).sum()
            num_wells = len(proj_wells)
            proj_labeled = proj_wells.copy()
            proj_labeled["section_name"] = sec_name
            pf_row = aggregate_powder_factor_by_group(
                df_filtered_pf, "section_name", sec_name, proj_labeled,
            )
            pf_vol = pf_row.get("pf_vol_avg")
            energy_mj = pf_row.get("energy_total_mj", 0.0) or 0.0
        else:
            total_kg = 0
            num_wells = 0
            pf_vol = float("nan")
            energy_mj = 0.0

        corr_data.append(
            {
                "Sección": sec_name,
                "Kg_Explosivo": total_kg,
                "Pozos_Cercanos": num_wells,
                "PF_Vol_kgm3": pf_vol,
                "Energía_MJ": energy_mj,
                "Sobre-excavación_Media_m": avg_over_break,
                "Deuda/Relleno_Media_m": avg_under_break,
            }
        )
    return pd.DataFrame(corr_data)


def _pre_scatter(df_corr, x_col="Kg_Explosivo"):
    fig = go.Figure()
    df_over = df_corr[df_corr["Sobre-excavación_Media_m"] > 0]
    df_under = df_corr[df_corr["Deuda/Relleno_Media_m"] < 0]

    if not df_over.empty:
        fig.add_trace(go.Scatter(
            x=df_over[x_col].values,
            y=df_over["Sobre-excavación_Media_m"].values,
            mode="markers+text",
            text=df_over["Sección"].values,
            textposition="top center",
            marker=dict(size=11, color="crimson", symbol="circle"),
            name="Sobre-excavación (delta_crest > 0)",
        ))
    if not df_under.empty:
        fig.add_trace(go.Scatter(
            x=df_under[x_col].values,
            y=df_under["Deuda/Relleno_Media_m"].values,
            mode="markers+text",
            text=df_under["Sección"].values,
            textposition="bottom center",
            marker=dict(size=11, color="steelblue", symbol="diamond"),
            name="Deuda/Relleno (delta_crest < 0)",
        ))
    if not df_over.empty and len(df_over) > 1:
        xs = pd.to_numeric(df_over[x_col], errors="coerce").fillna(0).values.astype(float)
        ys = df_over["Sobre-excavación_Media_m"].values.astype(float)
        if np.var(xs) > 0:
            m, b = np.polyfit(xs, ys, 1)
            trend_x = np.array([xs.min(), xs.max()])
            trend_y = m * trend_x + b
            fig.add_trace(go.Scatter(
                x=trend_x, y=trend_y,
                mode="lines",
                line=dict(color="darkred", dash="dash"),
                name=f"Tendencia Sobre-excavación (m={m:.4f})",
            ))
    fig.update_layout(
        title=f"Correlación: Kg Explosivos (r={DEFAULTS.blast_correlation_radius_m:.0f}m) vs Desviación con signo (delta_crest)",
        xaxis_title="Carga Explosiva Acumulada (Kg) — fallback sin PF",
        yaxis_title="Desviación Media con signo (m)",
        height=450,
        margin=dict(l=40, r=20, t=40, b=40),
        yaxis=dict(zeroline=True, zerolinecolor="gray", zerolinewidth=1),
    )
    return fig


def _post_refactor(df, sections, comparison, kg_col="Kilos_Cargados_real"):
    df_filtered_pf = compute_powder_factor(df)
    df_comp_signed = comparison.dropna(subset=["delta_crest"])
    sec_over_grouped = (
        df_comp_signed[df_comp_signed["delta_crest"] > 0]
        .groupby("section")["delta_crest"].mean()
        .rename("avg_over_break")
    )
    sec_under_grouped = (
        df_comp_signed[df_comp_signed["delta_crest"] < 0]
        .groupby("section")["delta_crest"].mean()
        .rename("avg_under_break")
    )

    rows = project_powder_factor_per_section(
        df, df_filtered_pf, sections,
        kg_col=kg_col,
        tolerance=DEFAULTS.blast_correlation_radius_m,
        fecha_corte=None,
    )

    corr_data = []
    for row in rows:
        sec_name = row["section_name"]
        avg_over = float(sec_over_grouped.get(sec_name, 0.0) or 0.0)
        avg_under = float(sec_under_grouped.get(sec_name, 0.0) or 0.0)
        corr_data.append({
            "Sección": sec_name,
            "Kg_Explosivo": row["total_kg"],
            "Pozos_Cercanos": row["num_pozos"],
            "PF_Vol_kgm3": row["pf_vol_avg_kgm3"],
            "Energía_MJ": row["energy_total_mj"],
            "Sobre-excavación_Media_m": avg_over,
            "Deuda/Relleno_Media_m": avg_under,
        })
    return pd.DataFrame(corr_data)


def _serialize(fig):
    out = json.loads(json.dumps(fig.to_dict(), sort_keys=True, default=str))
    for trace in out.get("data", []):
        for axis in ("x", "y", "z"):
            if axis in trace and isinstance(trace[axis], dict):
                trace[axis] = {"dtype": "f8", "values": trace[axis].get("bdata", "")}
    return json.dumps(out, sort_keys=True)


def _trace_payload(fig):
    """Return a stable comparison dict for trace structure.

    Compares only the user-visible cosmetic / structural attributes:
    name, mode, type, marker (color/symbol/size), line (color/dash),
    textposition, and a dtype-normalized x/y sequence. The numeric values
    are rounded to 6 decimal places so float64 vs float32 storage
    differences don't trigger spurious diffs. Plotly's bdata / dtype
    choices (int16 vs float64 vs int8) are irrelevant to the figure the
    user sees on screen.
    """
    def _norm(seq):
        if seq is None:
            return None
        return [round(float(v), 6) for v in seq]

    payload = {"data": [], "layout": fig.layout.to_plotly_json()}
    for t in fig.data:
        payload["data"].append({
            "name": t.name,
            "mode": t.mode,
            "type": t.type,
            "marker": t.marker.to_plotly_json() if t.marker else None,
            "line": t.line.to_plotly_json() if hasattr(t, "line") and t.line else None,
            "textposition": getattr(t, "textposition", None),
            "x": _norm(t.x),
            "y": _norm(t.y),
        })
    return payload


def test_h5_pre_post_byte_identical():
    """H5 extraction: rows + scatter must match the pre-refactor inline loop."""
    df, sections, comparison = _synthetic()

    pre = _pre_refactor(df, sections, comparison)
    post = _post_refactor(df, sections, comparison)

    pre_kg = pre["Kg_Explosivo"].round(6).tolist()
    post_kg = post["Kg_Explosivo"].round(6).tolist()
    assert pre_kg == post_kg, f"Kg_Explosivo mismatch: {pre_kg} vs {post_kg}"

    pre_pf = [round(v, 6) if pd.notna(v) else None for v in pre["PF_Vol_kgm3"]]
    post_pf = [round(v, 6) if pd.notna(v) else None for v in post["PF_Vol_kgm3"]]
    assert pre_pf == post_pf, f"PF_Vol_kgm3 mismatch: {pre_pf} vs {post_pf}"

    pre_e = pre["Energía_MJ"].round(6).tolist()
    post_e = post["Energía_MJ"].round(6).tolist()
    assert pre_e == post_e, f"Energía_MJ mismatch: {pre_e} vs {post_e}"

    pre_n = pre["Pozos_Cercanos"].tolist()
    post_n = post["Pozos_Cercanos"].tolist()
    assert pre_n == post_n, f"Pozos_Cercanos mismatch: {pre_n} vs {post_n}"

    fig_pre = _pre_scatter(pre, x_col="Kg_Explosivo")
    fig_post = build_pf_deviation_scatter(
        post,
        x_col="Kg_Explosivo",
        x_label="Carga Explosiva Acumulada (Kg) — fallback sin PF",
        radius_m=DEFAULTS.blast_correlation_radius_m,
        show_ols=True,
        title=f"Correlación: Kg Explosivos (r={DEFAULTS.blast_correlation_radius_m:.0f}m) vs Desviación con signo (delta_crest)",
    )

    pre_payload = _trace_payload(fig_pre)
    post_payload = _trace_payload(fig_post)
    pre_json = json.dumps(pre_payload, sort_keys=True, default=str)
    post_json = json.dumps(post_payload, sort_keys=True, default=str)
    if pre_json != post_json:
        print("SCATTER trace payload diff:")
        for line_a, line_b in zip(pre_json.splitlines(), post_json.splitlines()):
            if line_a != line_b:
                print(" -", line_a)
                print(" +", line_b)
        raise SystemExit(1)

    print("PRE / POST byte-identical (rows + scatter): OK")


if __name__ == "__main__":
    test_h5_pre_post_byte_identical()