"""Pure helpers for pasadura/toe, stemming/crest and attribution blocks."""

import pandas as pd

from core.blast_attribution import attribute_holes_to_benches
from core.blast_model import (
    compute_pasadura_toe_correlation,
    compute_stemming_crest_correlation,
)
from core.config import DEFAULTS


def build_pasadura_toe_data(blast_df: pd.DataFrame, comparison_results: list) -> dict:
    """Pure wrapper around :func:`core.blast_model.compute_pasadura_toe_correlation`."""
    return compute_pasadura_toe_correlation(
        blast_df,
        comparison_results,
        bench_height=DEFAULTS.blast_default_bench_height,
    )


def build_pasadura_toe_table(pas_corr: dict) -> pd.DataFrame:
    """Build a display DataFrame for the pasadura/toe correlation."""
    if pas_corr["n_benches"] < 2:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "Nivel (cota)": list(pas_corr["pasadura_per_bench"].keys()),
            "Pasadura media (m)": list(pas_corr["pasadura_per_bench"].values()),
            "delta_toe (m)": list(pas_corr["toe_per_bench"].values()),
        }
    ).sort_values("Nivel (cota)", ascending=False)


def build_stemming_crest_data(blast_df: pd.DataFrame, comparison_results: list) -> dict:
    """Pure wrapper around :func:`core.blast_model.compute_stemming_crest_correlation`."""
    return compute_stemming_crest_correlation(
        blast_df,
        comparison_results,
        bench_height=DEFAULTS.blast_default_bench_height,
    )


def build_stemming_crest_table(st_corr: dict) -> pd.DataFrame:
    """Build a display DataFrame for the stemming/crest correlation."""
    if st_corr["n_benches"] < 2:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "Nivel (cota)": list(st_corr["stemming_per_bench"].keys()),
            "Taco medio (m)": list(st_corr["stemming_per_bench"].values()),
            "delta_crest (m)": list(st_corr["crest_per_bench"].values()),
        }
    ).sort_values("Nivel (cota)", ascending=False)


def build_attribution_data(
    blast_df: pd.DataFrame,
    comparison_results: list,
    sections: list,
    tolerance: float,
) -> list:
    """Pure wrapper around :func:`core.blast_attribution.attribute_holes_to_benches`."""
    return attribute_holes_to_benches(
        blast_df,
        comparison_results,
        sections,
        tolerance,
    )
