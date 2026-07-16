"""Blast-correlation tab package.

Re-exports the public entry point used by ``ui.step4_results``.
"""

from ui.tabs.blast_correlation.renderers import render_tab_blast_correlation

__all__ = ["render_tab_blast_correlation"]
