"""Unified DataFrame builder for LLM consumption.

Consolida toda la información del proyecto (superficies, secciones,
bancos, comparaciones, pozos de tronadura, tolerancias) en un único
DataFrame tabular que el LLM puede inspeccionar para responder
preguntas específicas como:

- "¿Por qué el perfil S-01 no cumple?"
- "¿Qué pozos afectaron el banco B3?"
- "¿Cuál es el PF promedio del sector Norte?"

El DataFrame se serializa a markdown y se inyecta en el prompt del
LLM como contexto estructurado.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def build_unified_dataframe(
    comparisons: list[dict],
    params_design: list | None = None,
    params_topo: list | None = None,
    df_pozos: pd.DataFrame | None = None,
    sections: list | None = None,
    tolerances: dict | None = None,
    project_info: dict | None = None,
) -> pd.DataFrame:
    """Construye un DataFrame unificado con toda la info del proyecto.

    Cada fila representa un banco emparejado (design vs as-built) con
    todas sus métricas geométricas, de cumplimiento, y de tronadura
    cuando hay datos disponibles.

    Parameters
    ----------
    comparisons : list[dict]
        Resultados de ``compare_design_vs_asbuilt``.
    params_design / params_topo : list[ExtractionResult] | None
        Parámetros extraídos de diseño y topografía.
    df_pozos : pd.DataFrame | None
        DataFrame enriquecido de pozos de tronadura.
    sections : list | None
        Lista de SectionLine cargadas.
    tolerances : dict | None
        Tolerancias geotécnicas activas.
    project_info : dict | None
        Metadatos del proyecto (nombre, operación, fase).

    Returns
    -------
    pd.DataFrame
        DataFrame tabular con una fila por banco.
    """
    project_info = project_info or {}
    tolerances = tolerances or {}

    # ── 1. Construir filas base desde comparisons ──
    rows: list[dict] = []
    for c in comparisons:
        row: dict[str, Any] = {
            "proyecto": project_info.get("project", "N/A"),
            "operacion": project_info.get("operation", "N/A"),
            "seccion": c.get("section", ""),
            "sector": c.get("sector", ""),
            "banco_num": c.get("bench_num", ""),
            "nivel": c.get("level", ""),
            "tipo": c.get("type", ""),
            # Geometría diseño
            "altura_design_m": c.get("height_design"),
            "angulo_design_deg": c.get("angle_design"),
            "berma_design_m": c.get("berm_design"),
            # Geometría real (as-built)
            "altura_real_m": c.get("height_real"),
            "angulo_real_deg": c.get("angle_real"),
            "berma_real_m": c.get("berm_real"),
            # Desviaciones
            "delta_altura_m": c.get("height_dev"),
            "delta_angulo_deg": c.get("angle_dev"),
            "delta_crest_m": c.get("delta_crest"),
            "delta_toe_m": c.get("delta_toe"),
            # Cumplimiento (binario)
            "estado_altura": c.get("height_status", ""),
            "estado_angulo": c.get("angle_status", ""),
            "estado_berma": c.get("berm_status", ""),
            # Score ponderado
            "bench_score": c.get("bench_score"),
            "section_score": c.get("section_score"),
        }

        # Floor elevation del banco real (si existe)
        bt = c.get("bench_real")
        if bt is not None:
            row["cota_crest_real"] = round(float(bt.crest_elevation), 1)
            row["cota_toe_real"] = round(float(bt.toe_elevation), 1)
            row["cota_piso"] = round(float(getattr(bt, "floor_elevation", 0)), 1)
            row["berm_width_real"] = round(float(bt.berm_width), 2)
            row["effective_berm"] = round(float(bt.effective_berm_width), 2)
            row["is_ramp"] = bool(bt.is_ramp)

        # Tolerancias
        tol_h = tolerances.get("bench_height", {})
        tol_a = tolerances.get("face_angle", {})
        tol_b = tolerances.get("berm_width", {})
        row["tol_altura_pos"] = tol_h.get("pos") if isinstance(tol_h, dict) else None
        row["tol_altura_neg"] = tol_h.get("neg") if isinstance(tol_h, dict) else None
        row["tol_angulo_pos"] = tol_a.get("pos") if isinstance(tol_a, dict) else None
        row["tol_angulo_neg"] = tol_a.get("neg") if isinstance(tol_a, dict) else None
        row["berma_minima"] = tol_b.get("min") if isinstance(tol_b, dict) else None

        rows.append(row)

    df = pd.DataFrame(rows)

    # ── 2. Enriquecer con datos de tronadura por sección ──
    if df_pozos is not None and len(df_pozos) > 0 and sections:
        try:
            from core.blast_correlation import compute_blast_geotech_correlation
            blast_rows = compute_blast_geotech_correlation(df_pozos, sections, comparisons)
            # Crear mapa sección → métricas de tronadura
            blast_map: dict[str, dict] = {}
            for br in blast_rows:
                blast_map[br.section_name] = {
                    "n_pozos": br.num_wells,
                    "pf_vol_kgm3": round(br.pf_vol_avg_kgm3, 3) if br.pf_vol_avg_kgm3 else None,
                    "pf_g_ton": round(br.pf_g_per_ton_avg, 1) if br.pf_g_per_ton_avg else None,
                    "kg_total": round(br.total_kg, 0) if br.total_kg else None,
                    "over_break_m": round(br.avg_over_break, 2) if br.avg_over_break else None,
                    "under_break_m": round(br.avg_under_break, 2) if br.avg_under_break else None,
                }
            # Mergear al DataFrame por sección
            for sec_name, blast_data in blast_map.items():
                mask = df["seccion"] == sec_name
                for key, val in blast_data.items():
                    df.loc[mask, key] = val
        except Exception:
            pass  # Sin datos de tronadura, el DF queda sin esas columnas

    # ── 3. Métricas agregadas de pozos (por sección) ──
    if df_pozos is not None and len(df_pozos) > 0:
        try:
            # PF promedio global
            if "pf_vol_kgm3" in df_pozos.columns:
                pf_vals = pd.to_numeric(df_pozos["pf_vol_kgm3"], errors="coerce").dropna()
                if len(pf_vals) > 0:
                    df.attrs["pf_promedio_global"] = round(float(pf_vals.mean()), 3)
            # Stemming ratio promedio
            if "stemming_ratio" in df_pozos.columns:
                sr_vals = pd.to_numeric(df_pozos["stemming_ratio"], errors="coerce").dropna()
                if len(sr_vals) > 0:
                    df.attrs["stemming_ratio_promedio"] = round(float(sr_vals.mean()), 3)
            df.attrs["n_pozos_total"] = int(len(df_pozos))
        except Exception:
            pass

    return df


def dataframe_to_markdown(df: pd.DataFrame, max_rows: int = 60) -> str:
    """Convierte el DataFrame unificado a una tabla markdown para el LLM.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame unificado de ``build_unified_dataframe``.
    max_rows : int
        Número máximo de filas a incluir (para no exceder el contexto
        del LLM). Si hay más, se resume.

    Returns
    -------
    str
        Tabla en formato markdown.
    """
    if df.empty:
        return "(Sin datos disponibles para el análisis)"

    parts: list[str] = []

    # Metadatos del DataFrame (attrs)
    attrs = df.attrs
    if attrs:
        meta_lines = [f"- {k}: {v}" for k, v in attrs.items()]
        parts.append("**Métricas globales del proyecto:**\n" + "\n".join(meta_lines))

    # Tabla principal
    if len(df) > max_rows:
        # Resumir: mostrar las primeras y últimas filas
        head = df.head(max_rows // 2)
        tail = df.tail(max_rows // 2)
        parts.append(
            f"**Tabla de bancos** ({len(df)} filas, mostrando "
            f"{max_rows // 2} primeras + {max_rows // 2} últimas):\n"
        )
        parts.append(head.to_markdown(index=False, floatfmt=".1f"))
        parts.append("...\n")
        parts.append(tail.to_markdown(index=False, floatfmt=".1f"))
    else:
        parts.append(f"**Tabla de bancos** ({len(df)} filas):\n")
        parts.append(df.to_markdown(index=False, floatfmt=".1f"))

    return "\n\n".join(parts)
