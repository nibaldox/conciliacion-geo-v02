"""Per-feature blast-hole attribution to measured crest and toe deviations.

Additive helper that links individual blast holes to non-zero crest/toe
deviations found in ``comparison_results``. The scoring mirrors the IDW
energy density used in :func:`core.blast_model.compute_energy_density_along_profile`
(``kg / d^2`` with a 1e-4 m^2 floor) so per-feature attributions stay
consistent with the energy model already shipped.

The module is intentionally narrow and additive:
  - reads ``blast_df`` (with ``X``, ``Y``, optional ``Kilos_*``) and the
    matched ``comparison_results`` from the existing pipeline;
  - uses the canonical ``azimuth_to_direction`` transform so along-profile
    distances land in the same world XY plane as
    :func:`core.calculo_tronadura.proyectar_pozos_en_seccion`;
  - returns plain ``list[dict]`` so the Streamlit renderer can iterate
    without additional imports.

The function MUST never raise on missing data — empty ``blast_df``,
missing ``X``/``Y``, no ``MATCH`` rows, or unknown section names all
return ``[]``.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from core.geom_utils import find_df_column
from core.section_cutter import SectionLine, azimuth_to_direction


_KG_CANDIDATES: Sequence[str] = (
    "Kilos_Cargados_real",
    "Kilos_Cargados",
    "Carga_kg",
    "Explosivo_kg",
    "kg",
)

_LABEL_CANDIDATES: Sequence[str] = (
    "label_pozo",
    "pozo_id",
    "id_pozo",
    "numero",
)

_MALLA_CANDIDATES: Sequence[str] = (
    "holes_polygon",
    "Nombre_Malla_Original",
    "Malla",
    "Poligono",
    "Polígono",
)

_DISTANCE_FLOOR_M2: float = 1e-4


def _resolve_kg_column(blast_df: pd.DataFrame) -> Optional[str]:
    """Return the first present kg column or ``None`` to signal fallback."""
    for cand in _KG_CANDIDATES:
        if cand in blast_df.columns:
            return cand
    return None


def _feature_world_xy(section: SectionLine, distance_m: float) -> np.ndarray:
    """Project an along-profile distance to world XY using section azimuth."""
    origin = np.asarray(section.origin, dtype=float)[:2]
    direction = azimuth_to_direction(float(section.azimuth))
    return origin + direction * float(distance_m)


def _extract_benches(
    comparison_results: Iterable[dict],
    sections_by_name: dict,
    min_delta_m: float,
) -> List[dict]:
    """Filter and shape MATCH rows into per-feature attribution candidates."""
    bench_feature_rows: List[dict] = []
    for comp in comparison_results or []:
        if not isinstance(comp, dict):
            continue
        if comp.get("type") != "MATCH":
            continue
        bench_real = comp.get("bench_real")
        if bench_real is None:
            continue
        section_name = comp.get("section")
        section = sections_by_name.get(section_name)
        if section is None:
            continue

        bench_num = comp.get("bench_num")
        delta_crest = comp.get("delta_crest")
        delta_toe = comp.get("delta_toe")

        for feature, delta in (("crest", delta_crest), ("toe", delta_toe)):
            if delta is None:
                continue
            try:
                delta_f = float(delta)
            except (TypeError, ValueError):
                continue
            if abs(delta_f) <= float(min_delta_m):
                continue
            distance_m = float(
                getattr(bench_real, "crest_distance", 0.0)
                if feature == "crest"
                else getattr(bench_real, "toe_distance", 0.0)
            )
            bench_feature_rows.append(
                {
                    "section": section,
                    "section_name": section_name,
                    "bench_num": bench_num,
                    "feature": feature,
                    "delta_m": round(delta_f, 3),
                    "distance_m": distance_m,
                }
            )
    return bench_feature_rows


def _select_top_holes(
    feature_xy: np.ndarray,
    well_x: np.ndarray,
    well_y: np.ndarray,
    well_q: np.ndarray,
    well_labels: Sequence[str],
    well_mallas: Sequence[Optional[str]],
    tolerance: float,
    top_n: int,
) -> tuple[list[dict], int]:
    """Return (top_holes, n_candidates) for one feature point."""
    if well_x.size == 0:
        return [], 0

    dx = feature_xy[0] - well_x
    dy = feature_xy[1] - well_y
    d2 = dx * dx + dy * dy
    radius2 = float(tolerance) ** 2
    within_mask = d2 <= radius2
    n_candidates = int(np.count_nonzero(within_mask))
    if n_candidates == 0:
        return [], 0

    safe_d2 = np.where(d2 < _DISTANCE_FLOOR_M2, _DISTANCE_FLOOR_M2, d2)
    scores = well_q / safe_d2

    eligible_idx = np.flatnonzero(within_mask)
    eligible_scores = scores[eligible_idx]
    if eligible_scores.size == 0:
        return [], 0

    order = np.argsort(-eligible_scores, kind="stable")[: int(top_n)]
    total = float(np.sum(eligible_scores)) if eligible_scores.size else 0.0

    top_holes: list[dict] = []
    for pos in order:
        idx = int(eligible_idx[int(pos)])
        score = float(eligible_scores[int(pos)])
        distance_m = float(np.sqrt(d2[idx]))
        pct = (score / total * 100.0) if total > 0.0 else 0.0
        top_holes.append(
            {
                "label_pozo": well_labels[idx],
                "malla": well_mallas[idx],
                "kg": float(well_q[idx]),
                "distance_m": round(distance_m, 3),
                "contribution_pct": round(pct, 2),
            }
        )
    return top_holes, n_candidates


def attribute_holes_to_benches(
    blast_df: Optional[pd.DataFrame],
    comparison_results: Optional[Iterable[dict]],
    sections: Optional[Iterable[SectionLine]],
    tolerance: float = 15.0,
    top_n: int = 5,
    min_delta_m: float = 0.5,
) -> List[dict]:
    """Return one entry per deviated MATCH crest/toe with top-N contributing holes.

    Parameters
    ----------
    blast_df : pandas.DataFrame or None
        Processed blast holes. Must include ``X`` and ``Y``; a kg column
        is auto-resolved from ``Kilos_Cargados_real`` /
        ``Kilos_Cargados`` / ``Carga_kg`` / ``Explosivo_kg`` / ``kg``
        and falls back to 1 kg per hole when none is present.
    comparison_results : iterable of dict or None
        Output of the reconciliation pipeline. Only ``type == 'MATCH'``
        rows with non-null ``bench_real`` are considered.
    sections : iterable of SectionLine or None
        Section definitions keyed by ``section.name``. Unknown sections
        are silently skipped.
    tolerance : float
        Search radius (m) for holes around the measured feature XY.
    top_n : int
        Maximum holes returned per feature, ranked by ``kg / d^2``.
    min_delta_m : float
        Minimum absolute crest/toe deviation (m) required to produce a
        result entry. Rows within tolerance are skipped to avoid noise.

    Returns
    -------
    list of dict
        One entry per deviated feature with shape::

            {
                "section": str,
                "bench_num": int | None,
                "feature": "crest" | "toe",
                "delta_m": float,
                "n_candidates": int,
                "top_holes": [
                    {"label_pozo", "malla", "kg",
                     "distance_m", "contribution_pct"}, ...
                ],
            }
    """
    if (
        blast_df is None
        or not isinstance(blast_df, pd.DataFrame)
        or blast_df.empty
        or "X" not in blast_df.columns
        or "Y" not in blast_df.columns
    ):
        return []

    if not comparison_results or not sections:
        return []

    try:
        tolerance_f = float(tolerance)
    except (TypeError, ValueError):
        return []
    if tolerance_f <= 0:
        return []
    try:
        top_n_int = max(1, int(top_n))
    except (TypeError, ValueError):
        return []

    sections_by_name = {s.name: s for s in sections if getattr(s, "name", None) is not None}
    if not sections_by_name:
        return []

    feature_rows = _extract_benches(comparison_results, sections_by_name, min_delta_m)
    if not feature_rows:
        return []

    well_x = pd.to_numeric(blast_df["X"], errors="coerce").to_numpy(dtype=float)
    well_y = pd.to_numeric(blast_df["Y"], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(well_x) & np.isfinite(well_y)
    well_x = well_x[valid]
    well_y = well_y[valid]
    if well_x.size == 0:
        return []

    kg_col = _resolve_kg_column(blast_df)
    if kg_col is not None:
        well_q = (
            pd.to_numeric(blast_df[kg_col], errors="coerce")
            .fillna(0.0)
            .to_numpy(dtype=float)[valid]
        )
    else:
        well_q = np.ones(well_x.size, dtype=float)

    label_col = find_df_column(blast_df, list(_LABEL_CANDIDATES), raise_error=False)
    if label_col is not None:
        well_labels = blast_df[label_col].astype(object).fillna("").tolist()
    else:
        well_labels = ["" for _ in range(well_x.size)]
    well_labels = [well_labels[i] for i in np.flatnonzero(valid)]

    malla_col = find_df_column(blast_df, list(_MALLA_CANDIDATES), raise_error=False)
    if malla_col is not None:
        raw_mallas = blast_df[malla_col].tolist()
    else:
        raw_mallas = [None] * well_x.size
    well_mallas: list[Optional[str]] = []
    for raw in raw_mallas:
        if raw is None:
            well_mallas.append(None)
        elif isinstance(raw, float) and np.isnan(raw):
            well_mallas.append(None)
        else:
            well_mallas.append(str(raw))
    well_mallas = [well_mallas[i] for i in np.flatnonzero(valid)]

    results: list[dict] = []
    for row in feature_rows:
        feature_xy = _feature_world_xy(row["section"], row["distance_m"])
        top_holes, n_candidates = _select_top_holes(
            feature_xy,
            well_x,
            well_y,
            well_q,
            well_labels,
            well_mallas,
            tolerance_f,
            top_n_int,
        )
        if not top_holes:
            continue
        results.append(
            {
                "section": row["section_name"],
                "bench_num": row["bench_num"],
                "feature": row["feature"],
                "delta_m": row["delta_m"],
                "n_candidates": n_candidates,
                "top_holes": top_holes,
            }
        )

    return results


__all__ = ["attribute_holes_to_benches"]