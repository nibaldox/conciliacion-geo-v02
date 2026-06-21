"""Agente IA v2 — Tab de UI Streamlit.

Reemplaza el stub del Phase 2. Permite al usuario elegir un provider,
configurar el modelo, y generar un informe ejecutivo streaming
del estado de la conciliación.
"""
from __future__ import annotations

import asyncio
import datetime
import os
from collections.abc import AsyncIterator
from typing import Any

import streamlit as st

from core.ai_v2.config import AIConfig
from core.ai_v2.models import AIRequest, AIResponseChunk
from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ProviderType,
)
from core.ai_v2.service import stream_report


PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local)",
    "lmstudio": "LM Studio (local)",
    "openai": "OpenAI",
    "openrouter": "OpenRouter (cloud)",
    "minimax": "MiniMax",
    "glm": "GLM",
    "grok": "Grok",
}


PROVIDERS_NEEDING_KEY: frozenset[str] = frozenset(
    {"openai", "openrouter", "minimax", "glm", "grok"}
)

PROVIDER_ENV_VAR: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "glm": "GLM_API_KEY",
    "grok": "GROK_API_KEY",
}


def _resolve_api_key(ptype: ProviderType) -> str:
    env_var = PROVIDER_ENV_VAR.get(ptype.value, "")
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val
    return st.session_state.get(f"ai_v2_key_{ptype.value}", "")


def _render_settings() -> tuple[ProviderType, str, AIConfig, OpenAICompatibleProvider]:
    st.markdown("#### Configuración del agente")
    cols = st.columns(3)
    provider_name = cols[0].selectbox(
        "Provider",
        options=[p.value for p in ProviderType],
        index=0,
        format_func=lambda n: PROVIDER_LABELS.get(n or "", n or ""),
        key="ai_v2_provider",
    )
    ptype = ProviderType(provider_name)
    default_model = ProviderRegistry.get_default_model(ptype)
    model = cols[1].text_input(
        "Modelo", value=default_model, key="ai_v2_model"
    )
    temperature = cols[2].slider(
        "Temperatura", 0.0, 2.0, 0.3, 0.05, key="ai_v2_temperature"
    )

    if ptype.value in PROVIDERS_NEEDING_KEY:
        st.session_state.setdefault(f"ai_v2_key_{ptype.value}", "")
        api_key = st.text_input(
            f"🔑 {PROVIDER_ENV_VAR[ptype.value]}",
            value=st.session_state[f"ai_v2_key_{ptype.value}"],
            type="password",
            key=f"ai_v2_key_input_{ptype.value}",
            help=(
                f"Puedes dejar vacío si ya configuraste la variable "
                f"de entorno {PROVIDER_ENV_VAR[ptype.value]} en tu shell."
            ),
        )
        st.session_state[f"ai_v2_key_{ptype.value}"] = api_key
        if not _resolve_api_key(ptype):
            st.warning(
                f"⚠️ No se detectó API key para {ptype.value}. "
                f"Configúrala arriba o exporta `{PROVIDER_ENV_VAR[ptype.value]}` antes de lanzar Streamlit."
            )

    with st.expander("Avanzado", expanded=False):
        adv = st.columns(3)
        max_tokens = adv[0].number_input(
            "Max tokens", min_value=64, max_value=16384, value=4096, step=64,
            key="ai_v2_max_tokens",
        )
        timeout_s = adv[1].number_input(
            "Timeout (s)", min_value=5.0, max_value=600.0, value=120.0, step=5.0,
            key="ai_v2_timeout",
        )
        enable_cache = adv[2].checkbox(
            "Usar caché", value=False, key="ai_v2_cache",
        )

    config = AIConfig(
        temperature=float(temperature),
        max_tokens=int(max_tokens),
        timeout_s=float(timeout_s),
        enable_cache=bool(enable_cache),
    )
    api_key = _resolve_api_key(ptype)
    if api_key:
        provider = ProviderRegistry.get(ptype, api_key=api_key)
    else:
        provider = ProviderRegistry.get(ptype)
    return ptype, model, config, provider


def _apply_table_filters(
    comparisons: list[dict],
) -> tuple[list[dict], dict[str, list]]:
    """Apply the same filters as ui/tabs/table.py to the comparisons list.

    Reads st.session_state.table_filter_{sector,level,section,bench} and
    returns (filtered_list, active_filters_dict). Returns the input list
    untouched if no filter is active.
    """
    sel_sectors: list = st.session_state.get("table_filter_sector") or []
    sel_levels: list = st.session_state.get("table_filter_level") or []
    sel_sections: list = st.session_state.get("table_filter_section") or []
    sel_benches: list = st.session_state.get("table_filter_bench") or []

    active = {
        "sector": list(sel_sectors),
        "level": list(sel_levels),
        "section": list(sel_sections),
        "bench": list(sel_benches),
    }
    if not any(active.values()):
        return comparisons, active

    out: list[dict] = []
    for r in comparisons:
        if sel_sectors and r.get("sector") not in sel_sectors:
            continue
        if sel_levels and r.get("level") not in sel_levels:
            continue
        if sel_sections and r.get("section") not in sel_sections:
            continue
        if sel_benches and r.get("bench_num") not in sel_benches:
            continue
        out.append(r)
    return out, active


def _filters_summary(active: dict[str, list]) -> str:
    parts: list[str] = []
    if active["sector"]:
        parts.append(f"sector={','.join(map(str, active['sector']))}")
    if active["section"]:
        parts.append(f"sección={','.join(map(str, active['section']))}")
    if active["level"]:
        parts.append(f"cota={','.join(map(str, active['level']))}")
    if active["bench"]:
        parts.append(f"banco={','.join(map(str, active['bench']))}")
    return "; ".join(parts) if parts else "ninguno"


def _build_ai_request(
    comparisons: list[dict], ptype: ProviderType, model: str,
    use_cache: bool,
    filters_active: dict[str, list] | None = None,
) -> AIRequest:
    metadata: dict = {
        "project_name": st.session_state.get("project_name", "Sin nombre"),
        "fecha_informe": datetime.date.today().isoformat(),
        "seccion": ", ".join(str(s) for s in (filters_active or {}).get("section") or [])
                if (filters_active and (filters_active.get("section") or [])) else
                st.session_state.get("active_section", "global"),
        "banco": ", ".join(str(b) for b in (filters_active or {}).get("bench") or [])
                if (filters_active and (filters_active.get("bench") or [])) else "N/A",
    }
    return AIRequest(
        results={"comparisons": comparisons},
        sections=None,
        settings=None,
        provider=ptype.value,
        model=model,
        stream=True,
        use_cache=use_cache,
        metadata=metadata,
    )


def _run_stream(
    request: AIRequest, config: AIConfig, provider: OpenAICompatibleProvider
) -> AsyncIterator[AIResponseChunk]:
    return stream_report(request, provider=provider, config=config)


def render_tab_ai(config: dict) -> None:
    """Pestaña IA con selector de provider + generación streaming."""
    st.subheader("🤖 Agente IA v2 — Informe Ejecutivo")

    comparisons: list[dict] = st.session_state.get("comparison_results") or []
    if not comparisons:
        st.info(
            "Carga STL de diseño + topografía y ejecuta la conciliación "
            "para tener datos disponibles para el informe."
        )
        return

    ptype, model, ai_config, provider = _render_settings()

    filtered, active_filters = _apply_table_filters(comparisons)
    n_total = len(comparisons)
    n_filtered = len(filtered)
    filters_str = _filters_summary(active_filters)

    if active_filters and n_filtered != n_total:
        st.caption(
            f"**Filtros activos**: {filters_str} · "
            f"**{n_filtered}**/{n_total} comparaciones después del filtro · "
            f"Provider={ptype.value}"
        )
    else:
        st.caption(
            f"**{n_total}** comparaciones (sin filtros) · "
            f"Provider={ptype.value} · Endpoint={PROVIDER_PRESETS[ptype]['base_url']}"
        )

    if n_filtered == 0:
        st.warning(
            "⚠️ El filtro de la pestaña 'Tabla Detallada' dejó 0 bancos. "
            "Ajustá los filtros (o quítalos) antes de generar el informe."
        )
        return

    if not st.button(
        "📝 Generar Informe Ejecutivo", type="primary", key="ai_v2_generate"
    ):
        return

    request = _build_ai_request(
        filtered, ptype, model,
        use_cache=bool(ai_config.enable_cache),
        filters_active=active_filters,
    )

    placeholder = st.empty()
    full_report = ""
    duration_box = st.empty()
    start = datetime.datetime.now()

    try:
        async def _consume() -> None:
            nonlocal full_report
            async for chunk in _run_stream(request, ai_config, provider):
                if chunk.content:
                    full_report += chunk.content
                    placeholder.markdown(full_report + "▌")

        asyncio.run(_consume())

        placeholder.markdown(full_report)
        elapsed = (datetime.datetime.now() - start).total_seconds()
        duration_box.success(
            f"✅ Informe generado en {elapsed:.2f}s · "
            f"{n_filtered}/{n_total} bancos · "
            f"provider={ptype.value}, model={model}"
        )
    except Exception as exc:
        placeholder.empty()
        st.error(
            f"❌ No se pudo generar el informe con {ptype.value}/{model}.\n\n"
            f"**Error**: {type(exc).__name__}: {exc}\n\n"
            f"Verifica que el provider esté disponible "
            f"({PROVIDER_PRESETS[ptype]['base_url']}) "
            f"o prueba con otro provider."
        )