"""Widgets Streamlit reutilizables para la pestaña IA v2."""
from __future__ import annotations

import datetime
from typing import Any

import streamlit as st
import streamlit.components.v2 as components

from core.ai_v2.config import AIConfig
from core.ai_v2.providers import ProviderType
from ui.state_keys import (
    StateKey,
    ai_v2_key_for,
    ai_v2_key_input_for,
)
from ui.tabs.ai_report.providers import (
    PROVIDER_ENV_VAR,
    PROVIDER_LABELS,
    PROVIDERS_NEEDING_KEY,
    get_default_model,
    get_provider,
    resolve_api_key,
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


def render_copy_button(markdown: str) -> None:
    """Inject a browser-side copy-to-clipboard button."""
    _COPY_BTN_COMPONENT(
        data={"markdown": markdown},
        key=f"ai_copy_btn_{hash(markdown) & 0xffffffff}",
        height=42,
    )


def render_settings() -> tuple[ProviderType, str, AIConfig, Any]:
    """Render provider/model/config widgets and return the selected values."""
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
    default_model = get_default_model(ptype)
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
        if not resolve_api_key(ptype, dict(st.session_state)):
            st.warning(
                f"⚠️ No se detectó API key para {ptype.value}. "
                f"Configúrala arriba o exporta `{PROVIDER_ENV_VAR[ptype.value]}` "
                f"antes de lanzar Streamlit."
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
    api_key = resolve_api_key(ptype, dict(st.session_state))
    provider = get_provider(ptype, api_key) if api_key else get_provider(ptype)
    return ptype, model, config, provider


def render_no_data_message() -> None:
    """Info box shown when there are no comparison results yet."""
    st.info(
        "Carga STL de diseño + topografía y ejecuta la conciliación "
        "para tener datos disponibles para el informe."
    )


def render_filter_caption(
    n_total: int,
    n_filtered: int,
    filters_str: str,
    provider_name: str,
    endpoint: str,
    active_filters: dict[str, list],
) -> None:
    """Show the active filter / count caption below settings."""
    if active_filters and n_filtered != n_total:
        st.caption(
            f"**Filtros activos**: {filters_str} · "
            f"**{n_filtered}**/{n_total} comparaciones después del filtro · "
            f"Provider={provider_name}"
        )
    else:
        st.caption(
            f"**{n_total}** comparaciones (sin filtros) · "
            f"Provider={provider_name} · Endpoint={endpoint}"
        )


def render_zero_filter_warning() -> None:
    """Warning shown when filters leave zero comparisons."""
    st.warning(
        "⚠️ El filtro de la pestaña 'Tabla Detallada' dejó 0 bancos. "
        "Ajustá los filtros (o quítalos) antes de generar el informe."
    )


def render_generate_button() -> bool:
    """Render the primary generate-report button."""
    return st.button(
        "📝 Generar Informe Ejecutivo",
        type="primary",
        key=StateKey.AI_V2_GENERATE,
    )


def render_streaming_placeholders() -> tuple[Any, Any, Any]:
    """Return the placeholder, duration box and progress bar widgets."""
    return st.empty(), st.empty(), st.progress(0.0, text="Generando informe…")


def render_success_box(
    elapsed_s: float,
    n_filtered: int,
    n_total: int,
    provider_name: str,
    model: str,
    usage_line: str,
) -> None:
    """Show the success box with timing and usage info."""
    st.success(
        f"✅ Informe generado en {elapsed_s:.2f}s · "
        f"{n_filtered}/{n_total} bancos · "
        f"provider={provider_name}, model={model}\n\n{usage_line}"
    )


def render_partial_warning() -> None:
    """Caption shown when streaming failed but partial content is kept."""
    st.caption("⚠️ Streaming falló — se conservó el contenido parcial.")


def render_error_box(exc: Exception, provider_name: str, model: str, endpoint: str) -> None:
    """Show the error box after a failed generation attempt."""
    st.error(
        f"❌ No se pudo generar el informe con {provider_name}/{model}.\n\n"
        f"**Error**: {type(exc).__name__}: {exc}\n\n"
        f"Verifica que el provider esté disponible ({endpoint}) "
        f"o prueba con otro provider."
    )


def render_post_stream_buttons(report_text: str) -> None:
    """Render copy + download buttons for the generated report."""
    st.session_state[StateKey.AI_V2_FULL_REPORT] = report_text
    date_str = datetime.date.today().isoformat()
    project_name = st.session_state.get("project_name", "informe")
    file_name = f"informe_{project_name}_{date_str}.md"
    btn_cols = st.columns([1, 1, 4])
    with btn_cols[0]:
        render_copy_button(report_text)
    with btn_cols[1]:
        st.download_button(
            "💾 Descargar .md",
            data=report_text,
            file_name=file_name,
            mime="text/markdown",
            key="ai_v2_download_md",
        )
