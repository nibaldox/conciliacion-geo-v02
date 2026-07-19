"""Orquestador de la pestaña Agente IA v2."""
from __future__ import annotations

import asyncio
import datetime
from collections.abc import AsyncIterator
from typing import Any

import streamlit as st

from core.ai_v2.config import AIConfig
from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage
from core.ai_v2.providers import PROVIDER_PRESETS, ProviderType
from core.ai_v2.service import stream_report
from ui.filters import (
    apply_comparison_filters,
    collect_active_filters_from_session_state,
    filters_summary,
)
from ui.state_keys import StateKey
from ui.tabs.ai_report.prompt import (
    build_metadata,
    build_prompt,
    compute_blast_trend_metadata,
)
from ui.tabs.ai_report.providers import provider_base_url
from ui.tabs.ai_report.usage import format_usage_summary
from ui.tabs.ai_report.widgets import (
    render_error_box,
    render_filter_caption,
    render_generate_button,
    render_no_data_message,
    render_partial_warning,
    render_post_stream_buttons,
    render_settings,
    render_streaming_placeholders,
    render_success_box,
    render_zero_filter_warning,
)


def _apply_table_filters(
    comparisons: list[dict],
) -> tuple[list[dict], dict[str, list]]:
    """Apply the same filters as ui/tabs/table.py to the comparisons list."""
    active = collect_active_filters_from_session_state()
    filtered = apply_comparison_filters(comparisons, active)
    return filtered, active


def _build_ai_request(
    comparisons: list[dict],
    ptype: ProviderType,
    model: str,
    use_cache: bool,
    filters_active: dict[str, list] | None,
    notes: str = "",
) -> AIRequest:
    """Build the AIRequest payload from session state and filters."""
    df_pozos = st.session_state.get(StateKey.BLAST_DF_CLEAN)
    sections = st.session_state.get(StateKey.SECTIONS) or []
    config = st.session_state.get("config", {})
    tolerances = config.get("tolerances", {})
    project_info = {
        "project": st.session_state.get(StateKey.PROJECT_NAME, "Sin nombre"),
        "operation": config.get("operation", "N/A"),
    }
    blast_trend = compute_blast_trend_metadata(df_pozos, sections, comparisons)
    metadata = build_metadata(
        comparisons=comparisons,
        filters_active=filters_active,
        blast_trend=blast_trend,
        project_name=project_info["project"],
        active_section=st.session_state.get(StateKey.ACTIVE_SECTION, "global"),
        notes=notes,
    )

    # ── Construir DataFrame unificado para el LLM ──
    from core.unified_dataframe import build_unified_dataframe, dataframe_to_markdown

    params_design = st.session_state.get("params_design") or []
    params_topo = st.session_state.get("params_topo") or []
    unified_df = build_unified_dataframe(
        comparisons=comparisons,
        params_design=params_design,
        params_topo=params_topo,
        df_pozos=df_pozos,
        sections=sections,
        tolerances=tolerances,
        project_info=project_info,
    )
    unified_markdown = dataframe_to_markdown(unified_df)

    prompt_text = build_prompt(
        notes=notes,
        sections=[str(s) for s in (filters_active or {}).get("section") or []],
        filters=filters_active or {},
        blast_trend=blast_trend,
    )
    # Inyectar la tabla unificada en el prompt
    prompt_text = (
        prompt_text
        + "\n\n---\n\n**DATOS COMPLETOS DEL PROYECTO (DataFrame unificado):**\n\n"
        + unified_markdown
    )
    return AIRequest(
        results={"comparisons": comparisons},
        sections=None,
        settings=None,
        provider=ptype.value,
        model=model,
        notes=prompt_text,
        stream=True,
        use_cache=use_cache,
        metadata=metadata,
    )


def _run_stream(
    request: AIRequest,
    config: AIConfig,
    provider: Any,
) -> AsyncIterator[AIResponseChunk]:
    """Stream report chunks from the AI service."""
    return stream_report(request, provider=provider, config=config)


def render_tab_ai(config: dict) -> None:
    """Pestaña IA con selector de provider + generación streaming."""
    st.subheader("🤖 Agente IA v2 — Informe Ejecutivo")

    comparisons: list[dict] = st.session_state.get(StateKey.COMPARISON_RESULTS) or []
    if not comparisons:
        render_no_data_message()
        return

    ptype, model, ai_config, provider = render_settings()

    filtered, active_filters = _apply_table_filters(comparisons)
    n_total = len(comparisons)
    n_filtered = len(filtered)
    filters_str = filters_summary(active_filters)

    render_filter_caption(
        n_total=n_total,
        n_filtered=n_filtered,
        filters_str=filters_str,
        provider_name=ptype.value,
        endpoint=provider_base_url(ptype.value),
        active_filters=active_filters,
    )

    if n_filtered == 0:
        render_zero_filter_warning()
        return

    # ── Preview del DataFrame unificado ──
    with st.expander("📊 DataFrame unificado (datos que se envían al LLM)", expanded=False):
        from core.unified_dataframe import build_unified_dataframe, dataframe_to_markdown
        df_pozos = st.session_state.get(StateKey.BLAST_DF_CLEAN)
        sections = st.session_state.get(StateKey.SECTIONS) or []
        params_design = st.session_state.get("params_design") or []
        params_topo = st.session_state.get("params_topo") or []
        tolerances = config.get("tolerances", {})
        project_info_df = {
            "project": st.session_state.get(StateKey.PROJECT_NAME, "Sin nombre"),
            "operation": config.get("operation", "N/A"),
        }
        try:
            unified_df = build_unified_dataframe(
                comparisons=filtered,
                params_design=params_design,
                params_topo=params_topo,
                df_pozos=df_pozos,
                sections=sections,
                tolerances=tolerances,
                project_info=project_info_df,
            )
            st.dataframe(unified_df, use_container_width=True, hide_index=True)
            st.caption(f"DataFrame con {len(unified_df)} filas y {len(unified_df.columns)} columnas")
        except Exception as exc:
            st.warning(f"No se pudo construir el DataFrame: {exc}")

    if not render_generate_button():
        return

    request = _build_ai_request(
        filtered,
        ptype,
        model,
        use_cache=bool(ai_config.enable_cache),
        filters_active=active_filters,
    )

    placeholder, duration_box, progress_bar = render_streaming_placeholders()
    full_report: str = ""
    usage: AIUsage | None = None
    start = datetime.datetime.now()
    max_tokens = int(ai_config.max_tokens)

    try:
        async def _consume() -> None:
            nonlocal full_report, usage
            async for chunk in _run_stream(request, ai_config, provider):
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.content:
                    full_report += chunk.content
                    st.session_state[StateKey.AI_V2_FULL_REPORT] = full_report
                    placeholder.markdown(full_report + "▌")
                    ratio = (
                        min(0.95, len(full_report.split()) / max_tokens)
                        if max_tokens
                        else 0.5
                    )
                    progress_bar.progress(ratio, text="Generando informe…")

        asyncio.run(_consume())

        placeholder.markdown(full_report)
        progress_bar.progress(1.0, text="✅ Listo")
        elapsed = (datetime.datetime.now() - start).total_seconds()
        usage_line = format_usage_summary(ptype.value, usage, elapsed)
        render_success_box(
            elapsed_s=elapsed,
            n_filtered=n_filtered,
            n_total=n_total,
            provider_name=ptype.value,
            model=model,
            usage_line=usage_line,
        )
        render_post_stream_buttons(full_report)
    except Exception as exc:
        progress_bar.empty()
        placeholder.empty()
        if full_report:
            render_partial_warning()
            render_post_stream_buttons(full_report)
        render_error_box(
            exc=exc,
            provider_name=ptype.value,
            model=model,
            endpoint=provider_base_url(ptype.value),
        )
