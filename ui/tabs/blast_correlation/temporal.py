"""Pure temporal-analysis helpers."""

import pandas as pd

from core.blast_correlation import (
    compute_monthly_trend,
    detect_pf_outliers_iqr,
    split_campaign,
)


def build_monthly_trend_data(blast_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute monthly PF/damage trend and IQR outliers.

    Returns ``(trend_df, outliers)``. Either may be empty on failure.
    """
    try:
        trend_df = compute_monthly_trend(blast_df)
    except Exception:
        trend_df = pd.DataFrame()

    try:
        outliers = detect_pf_outliers_iqr(blast_df)
    except Exception:
        outliers = pd.DataFrame()

    return trend_df, outliers


def build_temporal_figure(trend_df: pd.DataFrame) -> object:
    """Build the monthly trend Plotly figure."""
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend_df["mes"],
            y=trend_df["pf_promedio"],
            name="PF (kg/m³)",
            yaxis="y1",
            mode="lines+markers",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=trend_df["mes"],
            y=trend_df["damage_promedio"],
            name="Sobre-excavación (m)",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="crimson"),
        )
    )
    fig.update_layout(
        yaxis=dict(title="PF (kg/m³)", side="left"),
        yaxis2=dict(
            title="Sobre-excavación (m)", overlaying="y", side="right"
        ),
        height=400,
        margin=dict(l=40, r=40, t=30, b=30),
    )
    return fig


def split_campaign_data(blast_df: pd.DataFrame, campaign_date_str: str) -> dict:
    """Pure wrapper around :func:`core.blast_correlation.split_campaign`."""
    try:
        return split_campaign(blast_df, campaign_date_str)
    except Exception:
        return {
            "has_campaign": False,
            "before": pd.DataFrame(),
            "after": pd.DataFrame(),
        }
