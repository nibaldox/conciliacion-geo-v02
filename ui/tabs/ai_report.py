"""Agente IA v2 — Tab de UI Streamlit.

Reemplaza el stub del Phase 2. Permite al usuario elegir un provider,
configurar el modelo, y generar un informe ejecutivo streaming
del estado de la conciliación.
"""
from __future__ import annotations

import asyncio
import datetime
from collections.abc import AsyncIterator
from typing import Any

import streamlit as st

from core.ai_v2.config import AIConfig
from core.ai_v2.models import AIRequest, AIResponseChunk
from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    ProviderRegistry,
    ProviderType,
)
from core.ai_v2.service import stream_report


PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local)",
    "lmstudio": "LM Studio (local)",
    "openai": "OpenAI",
    "minimax": "MiniMax",
    "glm": "GLM",
    "grok": "Grok",
}


def _render_settings() -> tuple[ProviderType, str, AIConfig]:
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
    return ptype, model, config


def _build_ai_request(
    comparisons: list[dict], ptype: ProviderType, model: str
) -> AIRequest:
    return AIRequest(
        results={"comparisons": comparisons},
        sections=None,
        settings=None,
        provider=ptype.value,
        model=model,
        stream=True,
        use_cache=False,
        metadata={
            "project_name": st.session_state.get("project_name", "Sin nombre"),
            "fecha_informe": datetime.date.today().isoformat(),
            "seccion": st.session_state.get("active_section", "global"),
            "banco": "N/A",
        },
    )


def _run_stream(request: AIRequest, config: AIConfig) -> AsyncIterator[AIResponseChunk]:
    return stream_report(request, config=config)


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

    ptype, model, ai_config = _render_settings()

    st.caption(f"{len(comparisons)} comparaciones disponibles.")
    if not st.button(
        "📝 Generar Informe Ejecutivo", type="primary", key="ai_v2_generate"
    ):
        return

    request = _build_ai_request(comparisons, ptype, model)

    placeholder = st.empty()
    full_report = ""
    duration_box = st.empty()
    start = datetime.datetime.now()

    try:
        async def _consume() -> None:
            nonlocal full_report
            async for chunk in _run_stream(request, ai_config):
                if chunk.content:
                    full_report += chunk.content
                    placeholder.markdown(full_report + "▌")

        asyncio.run(_consume())

        placeholder.markdown(full_report)
        elapsed = (datetime.datetime.now() - start).total_seconds()
        duration_box.success(
            f"✅ Informe generado en {elapsed:.2f}s "
            f"(provider={ptype.value}, model={model})"
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