"""Pestaña IA — Agente IA v2 (stub en reconstrucción).

Esta pestaña reemplazaba ``ui/tabs/ai_report.py`` legacy que dependía
de ``core.ai_reporter``. Mientras se implementa el agente v2 completo
(ver ``docs/AI_AGENT_V2_BLUEPRINT.md``), mostramos:

1. El motor local determinista (sin LLM) que sigue activo debajo.
2. Un mensaje claro de que el LLM está en reconstrucción.
"""
from __future__ import annotations

import streamlit as st


def render_tab_ai(config: dict) -> None:
    """Stub del tab IA. Mantiene compat con la firma legacy."""
    st.subheader("🤖 Agente IA v2 — En reconstrucción")

    st.warning(
        "El agente IA está siendo rediseñado (Fase 2 de reescritura, "
        "junio 2026). El módulo `core/ai_v2/` reemplazará tanto el camino "
        "moderno (FastAPI + React) como el legacy (Streamlit) que estaban "
        "acoplados a un solo SDK con providers hardcodeados."
    )

    st.markdown("### Roadmap del agente IA v2")
    st.markdown(
        """
        - [ ] **Fase 1** — Diseño arquitectónico (blueprint en `docs/AI_AGENT_V2_BLUEPRINT.md`)
        - [x] **Fase 2** — Stub funcional (este tab) ← *aquí*
        - [ ] **Fase 3** — Core: providers, prompts, builder, service
        - [ ] **Fase 4** — Integración UI (Streamlit + opcional FastAPI)
        - [ ] **Fase 5** — Tests (target 95% cobertura)
        - [ ] **Fase 6** — Documentación (AI_AGENT.md, MIGRATION.md)
        """
    )

    st.markdown("### Mientras tanto")
    st.info(
        "El motor local determinista de recomendaciones de tronadura "
        "(basado en OLS PF→daño y RMR/GSI) sigue activo en la pestaña "
        "anterior. No requiere LLM ni conexión externa."
    )

    if st.session_state.get("comparison_results"):
        st.success(
            f"Tienes {len(st.session_state.comparison_results)} resultados "
            "de conciliación cargados. Cuando el agente v2 esté listo, "
            "se generará automáticamente el informe ejecutivo aquí."
        )