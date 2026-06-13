"""
Results tab: detailed compliance table with sorting and filtering.
"""
import pandas as pd
import streamlit as st

from ui.filter_cache import _ensure_filter_values


def render_tab_table() -> None:
    if not st.session_state.comparison_results:
        return

    sort_option = st.radio(
        "Orden de la tabla:",
        ["Por Sección (Vertical)", "Por Nivel (Horizontal)"],
        horizontal=True, key="table_sort")

    df = pd.DataFrame(st.session_state.comparison_results)
    df = _apply_filters(df)
    df = _apply_sorting(df, sort_option)

    display_cols = {
        'sector': 'Sector', 'section': 'Sección', 'bench_num': 'Banco',
        'level': 'Nivel', 'height_design': 'H. Diseño', 'height_real': 'H. Real',
        'height_dev': 'Desv. H', 'height_status': 'Cumpl. H',
        'angle_design': 'Á. Diseño', 'angle_real': 'Á. Real',
        'angle_dev': 'Desv. Á', 'angle_status': 'Cumpl. Á',
        'berm_design': 'B. Diseño', 'berm_real': 'B. Real',
        'berm_min': 'B. Mínima', 'berm_status': 'Cumpl. B',
        'spill_width': 'B. Derrame', 'effective_berm': 'B. Efectiva',
        'delta_crest': 'Δ Cresta', 'delta_toe': 'Δ Pata',
    }
    cols_to_keep = [c for c in df.columns if c in display_cols]
    df_display = df[cols_to_keep].rename(columns=display_cols)
    df_display = _format_numeric(df_display)
    styled = df_display.style.map(
        _highlight_status, subset=['Cumpl. H', 'Cumpl. Á', 'Cumpl. B'])
    st.dataframe(styled, use_container_width=True, height=400)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    with st.expander("🔎 Filtros (Excel-style)", expanded=False):
        cols_filter = st.columns(4)
        fv = _ensure_filter_values()

        sel_sectors = cols_filter[0].multiselect(
            "Filtrar por Sector:", fv['sectors'], default=[], key="table_filter_sector")
        sel_levels = cols_filter[1].multiselect(
            "Filtrar por Nivel (Cota):", fv['levels'], default=[], key="table_filter_level")
        sel_sections = cols_filter[2].multiselect(
            "Filtrar por Sección:", fv['sections'], default=[], key="table_filter_section")
        sel_benches = cols_filter[3].multiselect(
            "Filtrar por Banco:", fv['benches'], default=[], key="table_filter_bench")

    if sel_sectors:
        df = df[df['sector'].isin(sel_sectors)]
    if sel_levels:
        df = df[df['level'].isin(sel_levels)]
    if sel_sections:
        df = df[df['section'].isin(sel_sections)]
    if sel_benches:
        df = df[df['bench_num'].isin(sel_benches)]
    return df


def _apply_sorting(df: pd.DataFrame, sort_option: str) -> pd.DataFrame:
    df['sort_level'] = pd.to_numeric(df['level'], errors='coerce').fillna(-9999)

    if "Por Nivel" in sort_option:
        df = df.sort_values(by=['sort_level', 'section'], ascending=[False, True])
        ordered = ['sector', 'level', 'section', 'bench_num']
    else:
        df = df.sort_values(by=['section', 'sort_level'], ascending=[True, False])
        ordered = ['sector', 'section', 'bench_num', 'level']

    rest = [c for c in df.columns if c not in ordered + ['sort_level', 'sort_bench']]
    return df[ordered + rest]


def _format_numeric(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        'H. Diseño', 'H. Real', 'Desv. H',
        'Á. Diseño', 'Á. Real', 'Desv. Á',
        'B. Diseño', 'B. Real', 'B. Mínima',
        'B. Derrame', 'B. Efectiva',
        'Δ Cresta', 'Δ Pata',
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: f"{x:.2f}" if isinstance(x, (int, float)) and x is not None else x)
    return df


def _highlight_status(val: str) -> str:
    val = str(val)
    if val == "CUMPLE" or "RAMPA OK" in val:
        return 'background-color: #C6EFCE; color: #006100'
    if val == "FUERA DE TOLERANCIA":
        return 'background-color: #FFEB9C; color: #9C5700'
    if val == "NO CUMPLE" or "FALTA" in val:
        return 'background-color: #FFC7CE; color: #9C0006'
    if val == "NO CONSTRUIDO":
        return 'background-color: #E0E0E0; color: #555555'
    if val == "EXTRA" or "ADICIONAL" in val or "RAMPA" in val:
        return 'background-color: #E6E6FA; color: #4B0082'
    return ''
