"""Agente IA v2 — en reconstrucción.

Este módulo reemplaza a:
- ``core.ai_service`` (moderno FastAPI, 261 líneas)
- ``core.ai_reporter`` (legacy Streamlit, 90 líneas)

Estado actual (2026-06-21): STUB. Funcionalidad disponible:
- Motor local determinista (sin LLM) sigue activo en ``ui/tabs/blast_correlation.py``
- En las próximas sesiones se implementará el v2 completo

Arquitectura planeada (ver ``docs/AI_AGENT_V2_BLUEPRINT.md``):
- providers/  : abstracción Ollama / LM Studio / OpenAI / MiniMax / GLM / Grok
- prompts/    : plantillas en Markdown separadas del código
- builder.py  : build_analysis_prompt() con Pydantic input
- service.py  : stream_report() async con timeout / temp / max_tokens / cache
- cache.py    : DiskCache opcional (sha256(prompt + model))
- errors.py   : jerarquía de errores del agente
"""
from __future__ import annotations

__version__ = "0.1.0-stub"
__status__ = "stub"

__all__: list[str] = [
    "__version__",
    "__status__",
]