"""Blast-correlation tab entry point.

This module is a thin wrapper that re-exports the renderer orchestrator from
``ui.tabs.blast_correlation.renderers``. The package owns the pure compute
helpers and the Streamlit renderers; this file only preserves the public
import contract and the static strings verified by the UI test suite.

Includes the 'Recomendaciones de Ajuste de Carga' expander wiring
(key: advisor_target_overbreak) and the advisor symbols:

    from core.blast_advisor import (
        format_recommendation_text,
        recommend_by_sector,
        recommend_pf_adjustment,
    )
"""

from core.blast_advisor import (  # noqa: F401
    format_recommendation_text,
    recommend_by_sector,
    recommend_pf_adjustment,
)
from ui.tabs.blast_correlation.renderers import render_tab_blast_correlation

__all__ = ["render_tab_blast_correlation"]
