"""Agente IA v2 — Tab de UI Streamlit.

Reemplaza el stub del Phase 2. Permite al usuario elegir un provider,
configurar el modelo, y generar un informe ejecutivo streaming
del estado de la conciliación.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import streamlit as st
import streamlit.components.v2 as components

from core.ai_v2.config import AIConfig
from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage
from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ProviderType,
)
from core.ai_v2.service import stream_report
from ui.filters import apply_comparison_filters, filters_summary
from ui.state_keys import (
    StateKey,
    ai_v2_key_for,
    ai_v2_key_input_for,
)


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


LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "lmstudio"})
CLOUD_PROMPT_RATE_USD_PER_TOKEN: float = 0.10 / 1_000_000.0
CLOUD_COMPLETION_RATE_USD_PER_TOKEN: float = 0.30 / 1_000_000.0


def _estimate_cost(provider_name: str, usage: AIUsage | None) -> float:
    """USD cost estimate — uses usage.cost_usd if populated, else a flat cloud
    rate ($0.10/1M prompt + $0.30/1M completion); $0.00 for local providers."""
    if usage is None:
        return 0.0
    if usage.cost_usd is not None:
        return usage.cost_usd
    if provider_name in LOCAL_PROVIDERS:
        return 0.0
    return round(
        usage.prompt_tokens * CLOUD_PROMPT_RATE_USD_PER_TOKEN
        + usage.completion_tokens * CLOUD_COMPLETION_RATE_USD_PER_TOKEN,
        4,
    )


def _format_usage_line(
    provider_name: str, usage: AIUsage | None, elapsed_s: float
) -> str:
    """One-line token + cost summary appended to the success box."""
    if usage is None:
        return f"⏱️ {elapsed_s:.2f}s · sin métricas de uso"
    tps = (usage.completion_tokens / elapsed_s) if elapsed_s > 0 else 0.0
    if provider_name in LOCAL_PROVIDERS:
        cost_str = "$0.0000 (local)"
    else:
        cost_str = f"${_estimate_cost(provider_name, usage):.4f}"
    # Mark estimated counts so the user knows not to bill against them.
    suffix = " (estimado)" if usage.is_synthetic else ""
    return (
        f"⏱️ {elapsed_s:.2f}s · "
        f"Tokens: {usage.prompt_tokens:,} in / "
        f"{usage.completion_tokens:,} out / "
        f"{usage.total_tokens:,} total · "
        f"{tps:.1f} tok/s · 💰 {cost_str}{suffix}"
    )


_COPY_BTN_HTML = (
    '<div id="ai_copy_root">'
    '<button id="ai_copy_btn" type="button" '
    'style="background:#f63366;color:white;border:none;'
    'padding:6px 12px;border-radius:6px;cursor:pointer;font-size:0.9rem;">'
    "📋 Copiar al portapapeles"
    "</button></div>"
)

_COPY_BTN_JS = (
    "export default function(component) {\n"
    "  const { data, parentElement } = component;\n"
    "  const root = parentElement.querySelector('#ai_copy_root') || parentElement;\n"
    "  const btn = root.querySelector('#ai_copy_btn');\n"
    "  if (!btn) return;\n"
    "  btn.addEventListener('click', async () => {\n"
    "    const md = (data && data.markdown) ? data.markdown : '';\n"
    "    try {\n"
    "      await navigator.clipboard.writeText(md);\n"
    "      const original = btn.textContent;\n"
    "      btn.textContent = '✅ Copiado';\n"
    "      setTimeout(() => { btn.textContent = original; }, 1500);\n"
    "    } catch (e) {\n"
    "      const ta = document.createElement('textarea');\n"
    "      ta.value = md; ta.style.position = 'fixed'; ta.style.opacity = '0';\n"
    "      document.body.appendChild(ta); ta.select();\n"
    "      try { document.execCommand('copy'); btn.textContent = '✅ Copiado'; }\n"
    "      catch (_) { btn.textContent = '❌ Falló'; }\n"
    "      document.body.removeChild(ta);\n"
    "      setTimeout(() => { btn.textContent = '📋 Copiar al portapapeles'; }, 1500);\n"
    "    }\n"
    "  });\n"
    "}\n"
)

_COPY_BTN_COMPONENT = components.component(
    "ai_copy_button",
    html=_COPY_BTN_HTML,
    js=_COPY_BTN_JS,
    isolate_styles=False,
)


def _html_button(payload: str, key: str | None = None) -> None:
    """Mount the v2 components button with the markdown body to copy."""
    _COPY_BTN_COMPONENT(data={"markdown": payload}, key=key, height=42)


def _render_copy_button(markdown: str) -> None:
    """Inject a browser-side copy-to-clipboard button via the Clipboard API,
    with a textarea+execCommand fallback for sandboxed iframes."""
    _html_button(markdown, key=f"ai_copy_btn_{hash(markdown) & 0xffffffff}")


def _resolve_api_key(ptype: ProviderType) -> str:
    env_var = PROVIDER_ENV_VAR.get(ptype.value, "")
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val
    return st.session_state.get(ai_v2_key_for(ptype.value), "")


def _render_settings() -> tuple[ProviderType, str, AIConfig, OpenAICompatibleProvider]:
    st.markdown("#### Configuración del agente")
    cols = st.columns(3)
    provider_name = cols[0].selectbox(
        "Provider",
        options=[p.value for p in ProviderType],
        index=0,
        format_func=lambda n: PROVIDER_LABELS.get(n or "", n or ""),
        key=StateKey.AI_V2_PROVIDER,
    )
    ptype = ProviderType(provider_name)
    default_model = ProviderRegistry.get_default_model(ptype)
    model = cols[1].text_input(
        "Modelo", value=default_model, key=StateKey.AI_V2_MODEL
    )
    temperature = cols[2].slider(
        "Temperatura", 0.0, 2.0, 0.3, 0.05, key=StateKey.AI_V2_TEMPERATURE
    )

    if ptype.value in PROVIDERS_NEEDING_KEY:
        st.session_state.setdefault(ai_v2_key_for(ptype.value), "")
        api_key = st.text_input(
            f"🔑 {PROVIDER_ENV_VAR[ptype.value]}",
            value=st.session_state[ai_v2_key_for(ptype.value)],
            type="password",
            key=ai_v2_key_input_for(ptype.value),
            help=(
                f"Puedes dejar vacío si ya configuraste la variable "
                f"de entorno {PROVIDER_ENV_VAR[ptype.value]} en tu shell."
            ),
        )
        st.session_state[ai_v2_key_for(ptype.value)] = api_key
        if not _resolve_api_key(ptype):
            st.warning(
                f"⚠️ No se detectó API key para {ptype.value}. "
                f"Configúrala arriba o exporta `{PROVIDER_ENV_VAR[ptype.value]}` antes de lanzar Streamlit."
            )

    with st.expander("Avanzado", expanded=False):
        adv = st.columns(3)
        max_tokens = adv[0].number_input(
            "Max tokens", min_value=64, max_value=16384, value=4096, step=64,
            key=StateKey.AI_V2_MAX_TOKENS,
        )
        timeout_s = adv[1].number_input(
            "Timeout (s)", min_value=5.0, max_value=600.0, value=120.0, step=5.0,
            key=StateKey.AI_V2_TIMEOUT,
        )
        enable_cache = adv[2].checkbox(
            "Usar caché", value=False, key=StateKey.AI_V2_CACHE,
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

    Delegates to ui.filters._collect_active_filters_from_session_state +
    apply_comparison_filters so the AI tab, dashboard, and export share
    one source of truth.
    """
    from ui.filters import _collect_active_filters_from_session_state

    active = _collect_active_filters_from_session_state()
    filtered = apply_comparison_filters(comparisons, active)
    return filtered, active


def _compute_blast_trend_metadata() -> dict | None:
    """Compute ``blast_trend`` metadata for the AI prompt (Idea 11).

    Pulls the enriched blast-hole DataFrame from ``st.session_state`` and
    runs :func:`compute_blast_geotech_correlation` against the active
    sections + comparisons. Returns ``None`` when there is no blast data
    (the builder will then render its "No hay datos de tronadura"
    fallback). The returned dict matches the shape expected by the
    ``blast_enrichment.md`` prompt template.
    """
    import numpy as np

    df_pozos = st.session_state.get("blast_df_clean")
    sections = st.session_state.get("sections") or []
    comparisons = st.session_state.get(StateKey.COMPARISON_RESULTS) or []  # noqa: E501
    if df_pozos is None or len(df_pozos) == 0 or not sections:
        return None

    try:
        from core.blast_correlation import compute_blast_geotech_correlation
        from core.blast_metrics import compute_spacing_burden_ratio

        rows = compute_blast_geotech_correlation(df_pozos, sections, comparisons)
    except Exception:
        return None

    if not rows:
        return None

    pf_values = [
        r.pf_vol_avg_kgm3 for r in rows
        if r.pf_vol_avg_kgm3 and r.pf_vol_avg_kgm3 > 0
    ]
    n_pozos_total = sum(r.num_wells for r in rows)
    if not pf_values:
        return None

    pf_mean = float(sum(pf_values) / len(pf_values))
    pf_std = (
        float(np.std(pf_values, ddof=0)) if len(pf_values) > 1 else 0.0
    )

    # Outliers via Tukey's IQR rule on the per-section PF averages.
    if len(pf_values) >= 4:
        q1, q3 = np.percentile(pf_values, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = [f"{v:.2f} kg/m³" for v in pf_values if v < lo or v > hi]
    else:
        outliers = []

    # Operational ratios (mean across holes). Falls back to "N/A" when
    # the source columns are not present in the DataFrame.
    ratios: dict[str, str] = {}
    try:
        sb = compute_spacing_burden_ratio(df_pozos)
        if sb.notna().any():
            ratios["S/B"] = f"{float(sb.mean()):.2f}"
    except Exception:
        pass

    return {
        "pf_promedio": round(pf_mean, 3),
        "pf_desviacion": round(pf_std, 3),
        "n_pozos_total": int(n_pozos_total),
        # We only have a snapshot — no time series to fit a real slope.
        "trend_slope_pf_per_month": 0.0,
        "trend_direction": "estable",
        "ratios": ratios,
        "outliers": outliers,
    }


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
    blast_trend = _compute_blast_trend_metadata()
    if blast_trend is not None:
        metadata["blast_trend"] = blast_trend
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

    comparisons: list[dict] = st.session_state.get(StateKey.COMPARISON_RESULTS) or []  # noqa: E501
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
    filters_str = filters_summary(active_filters)

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
        "📝 Generar Informe Ejecutivo", type="primary", key=StateKey.AI_V2_GENERATE
    ):
        return

    request = _build_ai_request(
        filtered, ptype, model,
        use_cache=bool(ai_config.enable_cache),
        filters_active=active_filters,
    )

    placeholder = st.empty()
    full_report: str = ""
    usage: AIUsage | None = None
    duration_box = st.empty()
    progress_bar = st.progress(0.0, text="Generando informe…")
    start = datetime.datetime.now()
    max_tokens = int(ai_config.max_tokens)

    def _post_stream_buttons(report_text: str) -> None:
        """Render copy + download buttons (works for full or partial report)."""
        st.session_state[StateKey.AI_V2_FULL_REPORT] = report_text
        date_str = datetime.date.today().isoformat()
        project_name = st.session_state.get("project_name", "informe")
        file_name = f"informe_{project_name}_{date_str}.md"
        btn_cols = st.columns([1, 1, 4])
        with btn_cols[0]:
            _render_copy_button(report_text)
        with btn_cols[1]:
            st.download_button(
                "💾 Descargar .md",
                data=report_text,
                file_name=file_name,
                mime="text/markdown",
                key="ai_v2_download_md",
            )

    try:
        async def _consume() -> None:
            nonlocal full_report, usage
            async for chunk in _run_stream(request, ai_config, provider):
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.content:
                    full_report += chunk.content
                    st.session_state["ai_v2_full_report"] = full_report
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
        usage_line = _format_usage_line(ptype.value, usage, elapsed)
        duration_box.success(
            f"✅ Informe generado en {elapsed:.2f}s · "
            f"{n_filtered}/{n_total} bancos · "
            f"provider={ptype.value}, model={model}\n\n{usage_line}"
        )
        _post_stream_buttons(full_report)
    except Exception as exc:
        progress_bar.empty()
        placeholder.empty()
        if full_report:
            st.caption("⚠️ Streaming falló — se conservó el contenido parcial.")
            _post_stream_buttons(full_report)
        st.error(
            f"❌ No se pudo generar el informe con {ptype.value}/{model}.\n\n"
            f"**Error**: {type(exc).__name__}: {exc}\n\n"
            f"Verifica que el provider esté disponible "
            f"({PROVIDER_PRESETS[ptype]['base_url']}) "
            f"o prueba con otro provider."
        )