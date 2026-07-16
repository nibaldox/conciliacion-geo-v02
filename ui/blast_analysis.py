"""Shared blast-correlation kernel and Plotly scatter builder.

Both ``ui/modulo_tronadura.py`` (módulo de tronadura) and
``ui/tabs/blast_correlation.py`` (results tab) compute the same per-section
projection + powder-factor aggregation when correlating blast holes with
geotechnical deviations. This module owns the pure kernel so the two
surfaces stay byte-identical.

Why this lives under ``ui/`` (not ``core/``): the scatter builder wraps
Plotly (``go.Figure``) and reads ``st.session_state``-bound inputs at the
caller; moving it into ``core/`` would re-introduce the GUI/domain split
the audit found. The kernel itself is dep-free (pandas, numpy, the two
``core`` modules) and is unit-testable on synthetic DataFrames.

Per-call differences (preserved via parameter or call-site glue):

| Behavior                         | modulo_tronadura           | tabs/blast_correlation  |
|----------------------------------|----------------------------|-------------------------|
| Signed split source              | inline pandas split        | compute_signed_deviations |
| OLS trendline on over            | yes                        | no (uses px.scatter)    |
| Fallback x to ``total_kg``       | yes (via local variable)   | n/a (always PF)         |
| x axis label                     | con-signo                  | absolute                |
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.blast_correlation import aggregate_powder_factor_by_group
from core.calculo_tronadura import proyectar_pozos_en_seccion


def _project_one(
    df: pd.DataFrame,
    pf_enriched: pd.DataFrame,
    *,
    origin,
    azimuth: float,
    length: float,
    kg_col: str | None,
    tolerance: float,
    fecha_corte: str | None,
    label_col: str,
    label_value: str,
) -> dict:
    """Project blast holes onto one plane + aggregate the powder factor.

    Single-loop kernel shared by both public projectors. Returns the
    canonical row dict with keys: ``section_name``, ``num_pozos``,
    ``total_kg``, ``pf_vol_avg_kgm3``, ``pf_area_avg_kgm2``,
    ``energy_total_mj``, ``n_pf_valid``, ``projected_df``.
    """
    proj = proyectar_pozos_en_seccion(
        df,
        origin=origin,
        azimuth=azimuth,
        length=length,
        tolerance=tolerance,
        fecha_corte=fecha_corte,
    )
    num_pozos = len(proj)
    if proj.empty:
        return {
            'section_name': label_value,
            'num_pozos': 0,
            'total_kg': 0.0,
            'pf_vol_avg_kgm3': float('nan'),
            'pf_area_avg_kgm2': float('nan'),
            'energy_total_mj': 0.0,
            'n_pf_valid': 0,
            'projected_df': proj,
        }
    total_kg = (
        float(proj[kg_col].fillna(0).sum())
        if kg_col and kg_col in proj.columns
        else 0.0
    )
    proj_labeled = proj.copy()
    proj_labeled[label_col] = label_value
    pf_row = aggregate_powder_factor_by_group(
        pf_enriched, label_col, label_value, proj_labeled,
    )
    return {
        'section_name': label_value,
        'num_pozos': num_pozos,
        'total_kg': total_kg,
        'pf_vol_avg_kgm3': pf_row.get('pf_vol_avg'),
        'pf_area_avg_kgm2': pf_row.get('pf_area_avg'),
        'energy_total_mj': pf_row.get('energy_total_mj', 0.0) or 0.0,
        'n_pf_valid': int(pf_row.get('n_pf_valid', 0) or 0),
        'projected_df': proj,
    }


def project_powder_factor_per_section(
    df_filtered: pd.DataFrame,
    pf_enriched: pd.DataFrame,
    sections: list,
    *,
    kg_col: str | None,
    tolerance: float,
    fecha_corte: str | None = None,
    label_col: str = 'section_name',
) -> list[dict]:
    """Per-section projection + PF aggregation (thin wrapper over ``_project_one``).

    Each section must expose ``name``, ``origin``, ``azimuth``, ``length``.
    """
    return [
        _project_one(
            df_filtered, pf_enriched,
            origin=getattr(sec, 'origin'),
            azimuth=float(getattr(sec, 'azimuth', 0.0)),
            length=float(getattr(sec, 'length', 200.0)),
            kg_col=kg_col,
            tolerance=tolerance,
            fecha_corte=fecha_corte,
            label_col=label_col,
            label_value=getattr(sec, 'name', str(sec)),
        )
        for sec in sections
    ]


def project_powder_factor_per_group(
    df_group: pd.DataFrame,
    pf_enriched: pd.DataFrame,
    *,
    kg_col: str | None,
    group_values: list,
    origin_getter: Callable,
    azimuth_getter: Callable,
    length_getter: Callable,
    tolerance: float,
    fecha_corte: str | None = None,
    label_col: str = 'group_label',
) -> list[dict]:
    """Generic per-group projection + PF aggregation (thin wrapper over ``_project_one``).

    Used by the bench / malla correlation helpers in
    ``ui/tabs/blast_correlation.py``. The caller supplies callables that
    map a group value to (origin, azimuth, length).
    """
    return [
        _project_one(
            df_group, pf_enriched,
            origin=origin_getter(group),
            azimuth=azimuth_getter(group),
            length=length_getter(group),
            kg_col=kg_col,
            tolerance=tolerance,
            fecha_corte=fecha_corte,
            label_col=label_col,
            label_value=str(group),
        )
        for group in group_values
    ]


def build_pf_deviation_scatter(
    df_corr: pd.DataFrame,
    *,
    x_col: str,
    x_label: str,
    over_label: str = 'Sobre-excavación (delta_crest > 0)',
    under_label: str = 'Deuda/Relleno (delta_crest < 0)',
    section_label_col: str = 'Sección',
    over_y_col: str = 'Sobre-excavación_Media_m',
    under_y_col: str = 'Deuda/Relleno_Media_m',
    radius_m: float,
    show_ols: bool = False,
    title: Optional[str] = None,
) -> go.Figure:
    """Build the Plotly scatter for the powder-factor / deviation view.

    Renders two traces (over / under) keyed on the signed deviation
    columns, optional OLS trendline on the over subset (only used by
    ``ui/modulo_tronadura.py``), zero line on the y axis, and the radius
    embedded in the title for traceability.
    """
    fig = go.Figure()
    df_over = df_corr[df_corr[over_y_col] > 0]
    df_under = df_corr[df_corr[under_y_col] < 0]

    if not df_over.empty:
        fig.add_trace(go.Scatter(
            x=df_over[x_col].values,
            y=df_over[over_y_col].values,
            mode='markers+text',
            text=df_over[section_label_col].values,
            textposition='top center',
            marker=dict(size=11, color='crimson', symbol='circle'),
            name=over_label,
        ))

    if not df_under.empty:
        fig.add_trace(go.Scatter(
            x=df_under[x_col].values,
            y=df_under[under_y_col].values,
            mode='markers+text',
            text=df_under[section_label_col].values,
            textposition='bottom center',
            marker=dict(size=11, color='steelblue', symbol='diamond'),
            name=under_label,
        ))

    if show_ols and not df_over.empty and len(df_over) > 1:
        xs = pd.to_numeric(df_over[x_col], errors='coerce').fillna(0).values.astype(float)
        ys = df_over[over_y_col].values.astype(float)
        if np.var(xs) > 0:
            m, b = np.polyfit(xs, ys, 1)
            trend_x = np.array([xs.min(), xs.max()])
            trend_y = m * trend_x + b
            fig.add_trace(go.Scatter(
                x=trend_x, y=trend_y,
                mode='lines',
                line=dict(color='darkred', dash='dash'),
                name=f'Tendencia Sobre-excavación (m={m:.4f})',
            ))

    if title is None:
        x_kind = 'Powder Factor' if 'PF' in x_col.upper() or 'POWDER' in x_col.upper() else 'Kg Explosivos'
        title = f"Correlación: {x_kind} (r={radius_m:.0f}m) vs Desviación con signo (delta_crest)"

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title='Desviación Media con signo (m)',
        height=450,
        margin=dict(l=40, r=20, t=40, b=40),
        yaxis=dict(zeroline=True, zerolinecolor='gray', zerolinewidth=1),
    )
    return fig


__all__ = [
    'project_powder_factor_per_section',
    'project_powder_factor_per_group',
    'build_pf_deviation_scatter',
]
