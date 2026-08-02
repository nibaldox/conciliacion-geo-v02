"""Visible data-quality warnings for the tronadura UI (cierre final §2.3).

``collect_data_warnings`` is a PURE function: it reads the processed
DataFrame and returns a list of structured warnings that the UI renders
with visible components (st.error / st.warning / st.info). Warnings are
never hidden in logs, tooltips or closed expanders; ``attach=True``
persists them into the result frame so the output stays reproducible.

Each warning: level ("error" | "warning" | "info"), message (what is
missing/invalid), affected (which calculation), fix (how to correct).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"


def _bench_height_warnings(df: pd.DataFrame) -> list[dict]:
    if "bench_height_status" not in df.columns:
        return []
    status = df["bench_height_status"].iloc[0]
    confirmed = bool(df["bench_height_user_confirmed"].iloc[0]) if "bench_height_user_confirmed" in df.columns else False
    message = str(df["bench_height_validation_message"].iloc[0]) if "bench_height_validation_message" in df.columns else ""
    if status in ("MISSING", "INVALID"):
        return [{
            "level": LEVEL_WARNING,
            "message": (
                f"Altura de banco {'inválida' if status == 'INVALID' else 'ausente'}: "
                f"{message or 'sin valor válido'}"
            ),
            "affected": "pf_vol, pf_g_per_ton_net, pasadura, altura neta, volumen de influencia, tonelaje",
            "fix": "Declare la altura de banco del evento (bench_height_m) antes de procesar.",
        }]
    if status == "EXPLICIT_ASSUMPTION":
        return [{
            "level": LEVEL_INFO,
            "message": f"Altura de banco por supuesto explícito {('confirmado' if confirmed else 'PENDIENTE DE CONFIRMACIÓN')}: {message}",
            "affected": "pf_vol, pf_g_per_ton_net, pasadura",
            "fix": "Declare la altura real del evento para limpiar el supuesto.",
        }]
    return []


def _angular_warnings(df: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    if "inclination_validation_status" in df.columns:
        status = df["inclination_validation_status"].iloc[0]
        if status == "OUT_OF_RANGE":
            out.append({
                "level": LEVEL_WARNING,
                "message": "Inclinación fuera de rango (|inclinación| > 90°): filas descartadas de la geometría.",
                "affected": "toe, altura real, trayectorias 3D",
                "fix": "Revise los valores de la columna de inclinación del evento.",
            })
        elif status == "NOT_CONFIRMED":
            out.append({
                "level": LEVEL_ERROR,
                "message": "Convención de inclinación no confirmada: la geometría no se calculó.",
                "affected": "toe, desplazamientos, geometría 3D",
                "fix": "Seleccione y confirme la convención en 'Convención geométrica del evento'.",
            })
    if "inclination_user_confirmed" in df.columns and bool(df["inclination_user_confirmed"].iloc[0]) is False:
        if not any("convenci" in w["message"].lower() for w in out):
            out.append({
                "level": LEVEL_ERROR,
                "message": "Convención angular sin confirmación explícita.",
                "affected": "geometría dependiente",
                "fix": "Confirme la convención en la interfaz o declare Incl_convention en el evento.",
            })
    return out


def _voronoi_warnings(df: pd.DataFrame) -> list[dict]:
    if "voronoi_conservation_ok" not in df.columns:
        return []
    ok = bool(df["voronoi_conservation_ok"].iloc[0])
    if ok:
        return []
    residual = df["area_residual_pct"].iloc[0]
    return [{
        "level": LEVEL_ERROR,
        "message": (
            f"Conservación Voronoi fallida (residual {residual:+.2f}%): el PF por "
            "área de influencia quedó bloqueado."
        ),
        "affected": "pf_g_per_ton_inf",
        "fix": "Proporcione el polígono real de la tronadura o revise los collares duplicados/fuera de dominio.",
    }]


def _explosive_warnings(df: pd.DataFrame) -> list[dict]:
    if "explosive_status" not in df.columns:
        return []
    counts = df["explosive_status"].value_counts().to_dict()
    out: list[dict] = []
    unknown = int(counts.get("UNKNOWN", 0))
    if unknown:
        out.append({
            "level": LEVEL_WARNING,
            "message": f"{unknown} pozos con explosivo DESCONOCIDO: energía y RWS = NaN (sin fallback).",
            "affected": "energy_mj, RWS, kuznetsov_x50",
            "fix": "Corrija el nombre del producto en el evento o regístrelo en el catálogo.",
        })
    unvalidated = int(counts.get("UNVALIDATED_REFERENCE", 0))
    if unvalidated:
        out.append({
            "level": LEVEL_INFO,
            "message": f"{unvalidated} pozos con producto de referencia sin validación oficial (falta ficha técnica; RWS estimado).",
            "affected": "energía específica, RWS, kuznetsov_x50",
            "fix": "Entregue la ficha técnica oficial para validar las propiedades.",
        })
    return out


def _blocked_indicator_warnings(df: pd.DataFrame) -> list[dict]:
    """Indicators that came out NaN because their physical inputs were blocked."""
    out: list[dict] = []
    if "pf_vol_kgm3" in df.columns and df["pf_vol_kgm3"].isna().all():
        out.append({
            "level": LEVEL_WARNING,
            "message": "Factor de carga volumétrico bloqueado (sin altura de banco válida o sin carga).",
            "affected": "pf_vol_kgm3",
            "fix": "Declare la altura de banco y verifique la carga por pozo.",
        })
    if "pf_g_per_ton_inf" in df.columns and df["pf_g_per_ton_inf"].isna().all():
        out.append({
            "level": LEVEL_WARNING,
            "message": "Factor de carga por área de influencia bloqueado (conservación Voronoi o altura).",
            "affected": "pf_g_per_ton_inf",
            "fix": "Revise el polígono del evento y la altura de banco.",
        })
    return out


def collect_data_warnings(
    df: pd.DataFrame | None,
    attach: bool = False,
) -> list[dict]:
    """Collect visible data-quality warnings from a processed blast frame.

    Returns a list of dicts with level/message/affected/fix, ordered by
    severity (error first). With ``attach=True`` the warnings are joined
    into a ``data_warnings`` column of the (copied) frame so they
    persist in the reproducible output.
    """
    if df is None or df.empty:
        return []
    warnings = (
        _angular_warnings(df)
        + _bench_height_warnings(df)
        + _voronoi_warnings(df)
        + _explosive_warnings(df)
        + _blocked_indicator_warnings(df)
    )
    if attach:
        joined = " | ".join(f"[{w['level']}] {w['message']}" for w in warnings)
        out = df.copy()
        out["data_warnings"] = joined
        return out
    return warnings


def render_warnings(warnings: list[dict]) -> None:
    """Render warnings with visible Streamlit components (cierre §2.3).

    Errors are blocking (st.error), warnings are st.warning and
    informational notes are st.info. Never hidden in closed expanders.
    """
    import streamlit as st

    for w in warnings:
        level = w.get("level", "info")
        text = f"**{w.get('message', '')}**"
        if w.get("affected"):
            text += f"\n\nCálculo afectado: `{w['affected']}`"
        if w.get("fix"):
            text += f"\n\nCómo corregirlo: {w['fix']}"
        if level == "error":
            st.error(text)
        elif level == "warning":
            st.warning(text)
        else:
            st.info(text)
