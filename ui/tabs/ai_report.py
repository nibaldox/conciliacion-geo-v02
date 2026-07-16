"""Agente IA v2 — Tab de UI Streamlit.

Thin tab delegado al paquete ui/tabs/ai_report/.
La implementación usa core.ai_v2.service.stream_report, ProviderType y render_tab_ai.
"""
from __future__ import annotations

from ui.tabs.ai_report import render_tab_ai

__all__ = ["render_tab_ai"]
