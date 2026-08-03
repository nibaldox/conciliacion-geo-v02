"""Charge-segment builder — transforms accepted rows into discrete
explosive-charge segments along each hole cylinder.

Pipeline (spec §2, §4.1, §4.2):

    accepted_row (Fase 1 ProcessingResult)
      → oriented cylinder collar→toe
      → taco (stemming) sliced off
      → explosive column discretized into N linear segments
      → per-segment mass (kg) and energy (J) with provenance
      → domain membership flagged

Each segment is a :class:`ChargeSegment`. The engine later turns the
list of valid segments into the voxel energy field.

Hard rules (spec §4.1):

* Unknown explosive → status ``UNKNOWN``; never an ANFO fallback.
* Missing specific energy → ``energy_j=None``; ABSOLUTE mode blocked.
* Missing kg → ``mass_kg=0.0`` + ``invalid`` flag; the segment is
  reported but excluded from the energy sum.
* Charge length incompatible with the real hole length
  (``taco + charge > Len``) → segment truncated to ``Len - taco`` with
  a structured warning; never a negative length.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from core.blast_simulation.contracts import (
    AnisotropyMode,
    ChargeSegment,
    DomainBounds,
    EnergyMode,
    SimulationConfiguration,
)
from core.blast_simulation.grid import point_in_domain_mask
from core.explosive_properties import (
    ExplosiveProduct,
    get_explosive_status,
    resolve_explosive,
)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def hole_axis_unit_vector(
    collar: tuple[float, float, float],
    toe: tuple[float, float, float],
) -> np.ndarray:
    """Unit vector along collar→toe. Raises if the hole has zero length."""
    c = np.asarray(collar, dtype=float)
    t = np.asarray(toe, dtype=float)
    v = t - c
    norm = float(np.linalg.norm(v))
    if norm <= 0.0:
        raise ValueError(f"Hole has zero or negative length (norm={norm})")
    return v / norm


def _segment_centre(
    collar: np.ndarray,
    unit: np.ndarray,
    distance_from_collar: float,
    half_length: float,
) -> np.ndarray:
    """Centre of a segment located at ``distance_from_collar`` along the axis."""
    return collar + unit * (distance_from_collar + half_length)


def _coerce_float(value: Any) -> Optional[float]:
    """Best-effort float coercion; None/NaN/inf → None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


# ---------------------------------------------------------------------------
# Domain membership
# ---------------------------------------------------------------------------


def _point_in_bounds(p: np.ndarray, bounds: DomainBounds) -> bool:
    return (
        bounds.x_min <= p[0] <= bounds.x_max
        and bounds.y_min <= p[1] <= bounds.y_max
        and bounds.z_min <= p[2] <= bounds.z_max
    )


# ---------------------------------------------------------------------------
# Single-hole segmentation
# ---------------------------------------------------------------------------


def _segment_single_hole(
    row: dict[str, Any],
    *,
    config: SimulationConfiguration,
    segments_per_hole: int,
) -> list[ChargeSegment]:
    """Build the charge segments for one accepted row.

    The explosive column runs from ``collar + taco`` to ``toe``. If the
    declared ``Len`` / ``descarga`` disagree with the geometric toe, the
    shorter of the two is used and a structured warning is attached.
    """
    hole_id = str(row.get("hole_id") or row.get("pozo") or row.get("id_pozo") or "?")
    source_idx = row.get("source_row_index")

    collar_x = _coerce_float(row.get("X"))
    collar_y = _coerce_float(row.get("Y"))
    collar_z = _coerce_float(row.get("Z_collar"))
    toe_x = _coerce_float(row.get("X_toe"))
    toe_y = _coerce_float(row.get("Y_toe"))
    toe_z = _coerce_float(row.get("Z_toe"))
    if None in (collar_x, collar_y, collar_z, toe_x, toe_y, toe_z):
        # Fase 1 should have rejected this row, but be defensive.
        return [_invalid_segment(hole_id, source_idx, "missing collar/toe coordinates")]

    collar = np.asarray([collar_x, collar_y, collar_z], dtype=float)
    toe = np.asarray([toe_x, toe_y, toe_z], dtype=float)
    try:
        unit = hole_axis_unit_vector(tuple(collar), tuple(toe))
    except ValueError as exc:
        return [_invalid_segment(hole_id, source_idx, str(exc))]

    geom_len = float(np.linalg.norm(toe - collar))
    declared_len = _coerce_float(row.get("Len")) or geom_len
    taco_m = _coerce_float(row.get("Taco_m")) or 0.0
    descarga_m = _coerce_float(row.get("descarga"))
    diameter_mm = _coerce_float(row.get("Diam_mm")) or 0.0
    kilos = _coerce_float(row.get("Kilos_Cargados_real"))
    explosive_name = str(row.get("Tipo_Explosivo") or "").strip()
    delay_ms = _coerce_float(row.get("Retardo_ms") or row.get("delay_ms") or row.get("Tiempo_Retardo"))

    warnings: list[str] = []

    # Resolve the effective charge length: prefer the declared descarga
    # (Len - Taco) when consistent, otherwise fall back to the geometric
    # length minus the taco. Never accept a negative charge length.
    candidate_charge = descarga_m if descarga_m is not None else (declared_len - taco_m)
    if candidate_charge is None or not math.isfinite(candidate_charge):
        candidate_charge = geom_len - taco_m
    # If the taco alone is longer than (or equal to) the hole, there is
    # no explosive column — clamp to zero with a warning (never negative).
    if taco_m >= declared_len:
        warnings.append(
            f"taco_m ({taco_m:.3f} m) >= hole length ({declared_len:.3f} m); "
            "charge length clamped to 0"
        )
        candidate_charge = 0.0
    elif candidate_charge < 0.0:
        warnings.append("taco_m longer than hole length; charge length clamped to 0")
        candidate_charge = 0.0
    if candidate_charge > geom_len:
        warnings.append(
            f"declared charge length {candidate_charge:.3f} m exceeds geometric "
            f"length {geom_len:.3f} m; truncated"
        )
        candidate_charge = geom_len
    charge_length_m = float(candidate_charge)

    # Explosive resolution — never ANFO fallback.
    product: Optional[ExplosiveProduct] = resolve_explosive(explosive_name) if explosive_name else None
    explosive_status = get_explosive_status(explosive_name) if explosive_name else "MISSING"
    energy_mj_kg = product.energy_mj_kg if product else None

    # Energy mode policy.
    energy_mode = config.energy_mode or EnergyMode.RELATIVE
    if (
        energy_mode == EnergyMode.ABSOLUTE
        and (product is None or energy_mj_kg is None)
    ):
        # ABSOLUTE mode is blocked — surface a structured warning. The
        # engine will refuse to run; we still emit the segments so the
        # diagnostics can show why.
        warnings.append(
            "ABSOLUTE mode blocked: explosive product or specific energy unavailable"
        )

    # Discretize the explosive column.
    n_segs = max(1, int(segments_per_hole))
    if charge_length_m <= 0.0 or kilos is None or kilos <= 0.0:
        # Hole has no explosive column (pure stemming or unloaded) or no
        # mass declared — emit ONE marker segment so it appears in the
        # source summary without contributing energy.
        marker = ChargeSegment(
            hole_id=hole_id,
            segment_type="taco" if charge_length_m <= 0.0 else "charge",
            cx=float(collar[0]),
            cy=float(collar[1]),
            cz=float(collar[2]),
            length_m=0.0,
            diameter_mm=diameter_mm,
            mass_kg=0.0,
            energy_j=None,
            explosive_name=explosive_name or "UNKNOWN",
            explosive_status=explosive_status,
            detonation_time_s=(delay_ms / 1000.0) if delay_ms is not None else None,
            in_domain=_point_in_bounds(collar, config.domain_bounds),
            source_row_index=source_idx,
            warnings=tuple(warnings) if warnings else (),
        )
        return [marker]

    seg_len = charge_length_m / n_segs
    seg_mass = kilos / n_segs
    seg_energy: Optional[float] = None
    if product is not None and energy_mj_kg is not None:
        # E_acoplada per segment = (kg × MJ/kg × 1e6 J/MJ) × η / n_segs
        # η applied later by the engine; here we store the chemical energy.
        seg_energy = (seg_mass * energy_mj_kg * 1.0e6)

    bounds = config.domain_bounds
    segments: list[ChargeSegment] = []
    # Segment k starts at distance (taco + k*seg_len) from collar.
    for k in range(n_segs):
        start_d = taco_m + k * seg_len
        centre = _segment_centre(collar, unit, start_d, seg_len / 2.0)
        in_domain = _point_in_bounds(centre, bounds)
        seg = ChargeSegment(
            hole_id=hole_id,
            segment_type="charge",
            cx=float(centre[0]),
            cy=float(centre[1]),
            cz=float(centre[2]),
            length_m=seg_len,
            diameter_mm=diameter_mm,
            mass_kg=seg_mass,
            energy_j=seg_energy,
            explosive_name=product.normalized_name if product else (explosive_name or "UNKNOWN"),
            explosive_status=explosive_status,
            detonation_time_s=(delay_ms / 1000.0) if delay_ms is not None else None,
            in_domain=in_domain,
            source_row_index=source_idx,
            warnings=tuple(warnings) if warnings else (),
        )
        segments.append(seg)

    return segments


def _invalid_segment(hole_id: str, source_idx: Any, reason: str) -> ChargeSegment:
    return ChargeSegment(
        hole_id=hole_id,
        segment_type="charge",
        cx=float("nan"),
        cy=float("nan"),
        cz=float("nan"),
        length_m=0.0,
        diameter_mm=0.0,
        mass_kg=0.0,
        energy_j=None,
        explosive_name="UNKNOWN",
        explosive_status="INVALID",
        detonation_time_s=None,
        in_domain=False,
        source_row_index=source_idx,
        warnings=(reason,),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_charge_segments(
    accepted_rows: list[dict[str, Any]],
    *,
    config: SimulationConfiguration,
    segments_per_hole: int = 8,
) -> list[ChargeSegment]:
    """Build the full list of charge segments from accepted rows.

    Each row produces ``segments_per_hole`` explosive-charge segments
    along its collar→toe axis (after the taco is sliced off). Rows with
    no explosive column or no declared mass produce a single marker
    segment so they still appear in the source summary.

    The function NEVER silently substitutes ANFO for an unknown
    explosive, NEVER invents a mass, and NEVER extends a charge beyond
    the geometric collar→toe segment.
    """
    if segments_per_hole < 1:
        raise ValueError("segments_per_hole must be >= 1")
    out: list[ChargeSegment] = []
    for row in accepted_rows:
        out.extend(_segment_single_hole(row, config=config, segments_per_hole=segments_per_hole))
    return out


def classify_segments(
    segments: list[ChargeSegment],
    *,
    energy_mode: str,
) -> tuple[list[ChargeSegment], list[ChargeSegment], dict[str, Any]]:
    """Split segments into (valid, invalid, diagnostics).

    A segment is **valid** when:

    * it is of type ``charge`` (not ``taco`` / ``deck_gap`` marker);
    * it carries a positive mass;
    * for ``ABSOLUTE`` mode, it carries a finite ``energy_j``.

    Invalid segments are reported but excluded from the energy sum.
    """
    valid: list[ChargeSegment] = []
    invalid: list[ChargeSegment] = []
    n_total = len(segments)
    n_no_mass = 0
    n_no_energy_abs = 0
    n_nan_centre = 0

    for s in segments:
        if s.segment_type != "charge":
            invalid.append(s)
            continue
        if not all(math.isfinite(v) for v in (s.cx, s.cy, s.cz)):
            n_nan_centre += 1
            invalid.append(s)
            continue
        if s.mass_kg <= 0.0:
            n_no_mass += 1
            invalid.append(s)
            continue
        if energy_mode == EnergyMode.ABSOLUTE and (
            s.energy_j is None or not math.isfinite(s.energy_j) or s.energy_j <= 0.0
        ):
            n_no_energy_abs += 1
            invalid.append(s)
            continue
        valid.append(s)

    diagnostics = {
        "total_segments": n_total,
        "valid_segments": len(valid),
        "invalid_segments": len(invalid),
        "invalid_no_mass": n_no_mass,
        "invalid_no_energy_absolute": n_no_energy_abs,
        "invalid_nan_centre": n_nan_centre,
    }
    return valid, invalid, diagnostics
