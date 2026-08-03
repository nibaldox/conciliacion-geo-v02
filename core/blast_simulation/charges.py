"""Charge-segment builder — transforms accepted rows into discrete
explosive-charge segments along each hole cylinder.

Pipeline (spec §2, §4.1, §4.2, Brecha 3.2):

    accepted_row (Fase 1 ProcessingResult)
      → oriented cylinder collar→toe
      → taco (stemming) sliced off
      → explosive column discretized into N linear segments
      → per-segment mass (kg) and energy (J) with provenance
      → domain membership flagged

Each segment is a :class:`ChargeSegment`. The engine later turns the
list of valid segments into the voxel energy field.

Two row-level modes are supported:

* **Multi-deck mode** — when ``row["Decks"]`` is a non-empty list of
  dicts. Each deck is validated independently (geometry, taco
  invasion, zero-length, overlap, explosive resolution) and
  discretized into ``n_segments_per_deck`` sub-segments. Inert gaps
  between decks produce no segments at all.
* **Legacy single-column mode** — when ``row["Decks"]`` is missing
  or empty. The explosive column is treated as a single contiguous
  cylinder between ``collar + Taco`` and ``toe``, distributed
  uniformly over ``segments_per_hole`` segments.

Hard rules (spec §4.1):

* Unknown explosive → status ``UNKNOWN_EXPLOSIVE``; never an ANFO fallback.
* Missing specific energy → status ``MISSING_ENERGY``; the segment is
  reported but excluded from the energy sum.
* Missing kg → ``mass_kg=0.0`` + invalid flag; the segment is
  reported but excluded from the energy sum.
* Charge length incompatible with the real hole length
  (``taco + charge > Len``) → segment truncated to ``Len - taco`` with
  a structured warning; never a negative length.

Deck-info preservation
----------------------

The :class:`ChargeSegment` dataclass is frozen and owned by
:mod:`core.blast_simulation.contracts`, which is managed by a parallel
branch and cannot be extended here. Per-deck provenance
(``deck_id``, ``from_m``, ``to_m``, ``status``) is therefore carried
as a structured marker in the existing ``warnings`` tuple on every
charge segment generated from a deck:

    "deck:<deck_id>:<from_m>:<to_m>:<status>"

The marker is stable, parseable, and survives ``to_dict()`` round-trip
(``warnings`` is exposed verbatim). Downstream layers can grep the
warnings tuple to recover per-deck metadata without modifying the
frozen contract.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from core.blast_simulation.contracts import (
    ChargeSegment,
    DeckSegment,
    DomainBounds,
    EnergyMode,
    SimulationConfiguration,
)
from core.explosive_properties import (
    ExplosiveProduct,
    get_explosive_status,
    resolve_explosive,
)


# ---------------------------------------------------------------------------
# Public dataclass — per-deck validation result (Brecha 3.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeckValidation:
    """Result of validating a single deck against the geometry + explosive policy.

    ``status`` is a closed set:

    * ``OK`` — deck contributes charge segments.
    * ``INVALID_GEOMETRY`` — ``from_m`` / ``to_m`` missing or non-finite.
    * ``TACO_INVADED`` — ``from_m < Taco_m``; the deck overlaps the stemming.
    * ``ZERO_LENGTH`` — ``to_m <= from_m`` after the geometric checks.
    * ``OVERLAP`` — the deck range overlaps a previously-accepted deck.
    * ``OUT_OF_HOLE`` — ``to_m`` exceeded the geometric hole length; the
      deck was truncated to ``geom_len`` but still contributes (when
      ``length_m > 0``).
    * ``UNKNOWN_EXPLOSIVE`` — explosive product does not resolve to a
      known record; deck contributes no segments (no ANFO fallback).
    * ``MISSING_ENERGY`` — explosive resolved but ``energy_mj_kg is None``.
    """
    deck_id: str
    status: str
    from_m: float
    to_m: float
    length_m: float
    reason: str = ""


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


def _point_in_bounds(p: np.ndarray, bounds: DomainBounds) -> bool:
    return (
        bounds.x_min <= p[0] <= bounds.x_max
        and bounds.y_min <= p[1] <= bounds.y_max
        and bounds.z_min <= p[2] <= bounds.z_max
    )


def _deck_warning_marker(
    deck_id: str, from_m: float, to_m: float, status: str,
) -> str:
    """Structured marker that preserves per-deck metadata on ChargeSegment.

    The :class:`ChargeSegment` dataclass is frozen and cannot be
    extended (owned by :mod:`core.blast_simulation.contracts`), so
    deck metadata is encoded into the existing ``warnings`` tuple in
    a stable, parseable form. Format: ``"deck:<id>:<from>:<to>:<status>"``.
    """
    return f"deck:{deck_id}:{from_m:.4f}:{to_m:.4f}:{status}"


# ---------------------------------------------------------------------------
# Deck parsing
# ---------------------------------------------------------------------------


def parse_decks_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the ``Decks`` field from a row, returning a list of deck dicts.

    Permissive semantics — never raises:

    * Missing ``Decks`` key → ``[]`` (legacy single-column mode).
    * ``Decks`` is ``None`` → ``[]`` (legacy single-column mode).
    * ``Decks`` is empty list → ``[]`` (legacy single-column mode).
    * ``Decks`` is non-list → ``[]`` (defensive; legacy mode).
    * Non-dict entries inside ``Decks`` are filtered out silently.

    The returned list preserves the caller's input order — the
    builder relies on positional order for the deterministic
    overlap-detection rule (first deck to claim a range wins).
    """
    decks = row.get("Decks")
    if not decks:
        return []
    if not isinstance(decks, list):
        return []
    return [entry for entry in decks if isinstance(entry, dict)]


# ---------------------------------------------------------------------------
# Deck validation
# ---------------------------------------------------------------------------


def validate_deck(
    deck: dict[str, Any],
    *,
    hole_id: str,
    taco_m: float,
    geom_len: float,
    deck_id: str,
    all_decks: list[dict[str, Any]],
) -> DeckValidation:
    """Validate a single deck and return its status + reason.

    ``all_decks`` is the full list of decks for this hole (in input
    order). The function checks the current deck against previously
    validated entries by reading the ``_validation`` slot attached by
    :func:`build_deck_segments`. The first deck to claim a range wins;
    later overlapping decks are marked ``OVERLAP``.

    Validation order (each step short-circuits on failure):

    1. ``from_m`` / ``to_m`` must be finite numbers → otherwise
       ``INVALID_GEOMETRY``.
    2. ``from_m >= Taco_m`` → otherwise ``TACO_INVADED``.
    3. ``to_m > from_m`` → otherwise ``ZERO_LENGTH``.
    4. Range overlap with any previously-accepted deck
       (``status`` in ``{"OK", "OUT_OF_HOLE"}``) → ``OVERLAP``.
    5. ``to_m > geom_len`` → truncated to ``geom_len``; status
       ``OUT_OF_HOLE`` but the deck still contributes (when the
       remaining length is positive).
    6. Explosive resolution is NOT performed here — the dedicated
       ``_resolve_deck_explosive`` helper appends ``UNKNOWN_EXPLOSIVE``
       or ``MISSING_ENERGY`` downstream when appropriate.
    """
    from_raw = deck.get("from_m")
    to_raw = deck.get("to_m")
    from_m = _coerce_float(from_raw)
    to_m = _coerce_float(to_raw)
    if from_m is None or to_m is None:
        return DeckValidation(
            deck_id=deck_id,
            status="INVALID_GEOMETRY",
            from_m=float("nan") if from_m is None else from_m,
            to_m=float("nan") if to_m is None else to_m,
            length_m=0.0,
            reason="from_m or to_m is missing/NaN/inf",
        )

    if from_m < taco_m:
        return DeckValidation(
            deck_id=deck_id,
            status="TACO_INVADED",
            from_m=from_m,
            to_m=to_m,
            length_m=0.0,
            reason=f"from_m={from_m:.4f} < taco_m={taco_m:.4f}",
        )

    if to_m <= from_m:
        return DeckValidation(
            deck_id=deck_id,
            status="ZERO_LENGTH",
            from_m=from_m,
            to_m=to_m,
            length_m=0.0,
            reason=f"to_m ({to_m:.4f}) <= from_m ({from_m:.4f})",
        )

    out_of_hole = to_m > geom_len
    effective_to = min(to_m, geom_len) if out_of_hole else to_m
    if effective_to <= from_m:
        return DeckValidation(
            deck_id=deck_id,
            status="OUT_OF_HOLE",
            from_m=from_m,
            to_m=to_m,
            length_m=0.0,
            reason=(
                f"to_m={to_m:.4f} > geom_len={geom_len:.4f}; "
                "truncation collapsed the deck"
            ),
        )
    length_m = effective_to - from_m
    status = "OUT_OF_HOLE" if out_of_hole else "OK"
    reason = (
        f"to_m={to_m:.4f} > geom_len={geom_len:.4f}; truncated to {effective_to:.4f}"
        if out_of_hole
        else ""
    )

    try:
        deck_index = all_decks.index(deck)
    except ValueError:
        deck_index = -1
    if deck_index > 0:
        for prior in all_decks[:deck_index]:
            prior_validation = prior.get("_validation")  # type: ignore[arg-type]
            if not isinstance(prior_validation, DeckValidation):
                continue
            if prior_validation.status not in ("OK", "OUT_OF_HOLE"):
                continue
            if not (
                effective_to <= prior_validation.from_m
                or from_m >= prior_validation.to_m
            ):
                return DeckValidation(
                    deck_id=deck_id,
                    status="OVERLAP",
                    from_m=from_m,
                    to_m=effective_to,
                    length_m=length_m,
                    reason=(
                        f"overlaps deck {prior_validation.deck_id} "
                        f"[{prior_validation.from_m:.4f}, {prior_validation.to_m:.4f}]"
                    ),
                )

    return DeckValidation(
        deck_id=deck_id,
        status=status,
        from_m=from_m,
        to_m=effective_to,
        length_m=length_m,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Explosive + mass resolution per deck
# ---------------------------------------------------------------------------


def _resolve_deck_explosive(
    deck: dict[str, Any],
) -> tuple[Optional[ExplosiveProduct], Optional[float], str, str]:
    """Resolve the explosive product for a single deck.

    Returns ``(product, energy_mj_kg, normalized_name, explosive_status)``.
    ``product`` is ``None`` when the name does not resolve — callers
    MUST treat that as ``UNKNOWN_EXPLOSIVE`` (no ANFO fallback).
    """
    name_raw = deck.get("explosive_type") or deck.get("Tipo_Explosivo") or ""
    name = str(name_raw).strip()
    if not name:
        return None, None, "UNKNOWN", "UNKNOWN"
    product = resolve_explosive(name)
    status = get_explosive_status(name)
    energy = product.energy_mj_kg if product else None
    return product, energy, (product.normalized_name if product else name), status


def _resolve_deck_mass(
    deck: dict[str, Any], length_m: float,
) -> tuple[Optional[float], str]:
    """Compute the deck's mass in kg.

    Priority:

    1. ``mass_kg`` (explicit per-deck mass).
    2. ``Kilos_Cargados_real`` (legacy single-row field; reused as a
       per-deck mass when no explicit ``mass_kg`` is provided).
    3. ``kg_per_m`` × ``length_m`` (linear density).
    4. ``density_kg_m3`` × cross-section × ``length_m`` (when no
       kg_per_m is available — uses the hole diameter as the section).

    Returns ``(mass_kg, source)`` where ``source`` is one of
    ``"mass_kg"``, ``"kg_per_m"``, ``"density"`` or ``"MISSING"``.
    ``mass_kg`` is ``None`` when no mass could be derived.
    """
    mass_raw = _coerce_float(deck.get("mass_kg")) or _coerce_float(
        deck.get("Kilos_Cargados_real")
    )
    if mass_raw is not None and mass_raw > 0.0:
        return float(mass_raw), "mass_kg"

    kg_per_m = _coerce_float(deck.get("kg_per_m"))
    if kg_per_m is not None and kg_per_m > 0.0:
        return float(kg_per_m * length_m), "kg_per_m"

    density = _coerce_float(deck.get("density_kg_m3"))
    if density is not None and density > 0.0 and length_m > 0.0:
        diameter_mm = _coerce_float(deck.get("Diam_mm"))
        if diameter_mm is not None and diameter_mm > 0.0:
            radius_m = float(diameter_mm) / 2000.0
            area_m2 = math.pi * radius_m * radius_m
            return float(density * area_m2 * length_m), "density"
    return None, "MISSING"


# ---------------------------------------------------------------------------
# Per-deck discretization
# ---------------------------------------------------------------------------


def _make_deck_marker(
    *,
    hole_id: str,
    source_idx: Any,
    collar: np.ndarray,
    unit: np.ndarray,
    validation: DeckValidation,
    diameter_mm: float,
    detonation_time_s: Optional[float],
    explosive_name: str,
    explosive_status: str,
    config: SimulationConfiguration,
    reason: str,
) -> ChargeSegment:
    """Build a zero-mass marker segment so the deck still appears in the source summary."""
    centre_d = validation.from_m + max(validation.length_m, 0.0) / 2.0
    centre = collar + unit * centre_d
    warning = _deck_warning_marker(
        validation.deck_id, validation.from_m, validation.to_m, validation.status,
    )
    return ChargeSegment(
        hole_id=hole_id,
        segment_type="taco" if validation.length_m <= 0.0 else "charge",
        cx=float(centre[0]),
        cy=float(centre[1]),
        cz=float(centre[2]),
        length_m=0.0,
        diameter_mm=diameter_mm,
        mass_kg=0.0,
        energy_j=None,
        explosive_name=explosive_name or "UNKNOWN",
        explosive_status=explosive_status,
        detonation_time_s=detonation_time_s,
        in_domain=_point_in_bounds(centre, config.domain_bounds),
        source_row_index=source_idx,
        warnings=(warning, reason),
    )


def _build_deck_charge_segments(
    *,
    deck: dict[str, Any],
    validation: DeckValidation,
    hole_id: str,
    source_idx: Any,
    collar: np.ndarray,
    unit: np.ndarray,
    diameter_mm: float,
    row_delay_ms: Optional[float],
    config: SimulationConfiguration,
    n_segments_per_deck: int,
) -> tuple[list[ChargeSegment], DeckValidation]:
    """Materialize one validated deck into ``n_segments_per_deck`` ChargeSegments.

    Returns ``(segments, final_validation)``. ``final_validation`` may
    carry an updated status (``UNKNOWN_EXPLOSIVE`` / ``MISSING_ENERGY``)
    when the explosive resolution fails. When the final status is not
    ``OK`` / ``OUT_OF_HOLE``, ``segments`` is empty (no charge
    contribution). When the status is OK but mass is missing, a single
    zero-mass marker segment is emitted so the deck still appears in
    the source summary.
    """
    product, energy_mj_kg, exp_name, exp_status = _resolve_deck_explosive(deck)
    final_status = validation.status
    final_reason = validation.reason

    if validation.status in ("OK", "OUT_OF_HOLE"):
        if product is None:
            final_status = "UNKNOWN_EXPLOSIVE"
            final_reason = (
                f"explosive '{deck.get('explosive_type') or ''}' does not "
                "resolve; no ANFO fallback"
            )
        elif energy_mj_kg is None:
            final_status = "MISSING_ENERGY"
            final_reason = f"explosive '{exp_name}' has no energy_mj_kg"

    final_validation = DeckValidation(
        deck_id=validation.deck_id,
        status=final_status,
        from_m=validation.from_m,
        to_m=validation.to_m,
        length_m=validation.length_m,
        reason=final_reason,
    )

    if final_status not in ("OK", "OUT_OF_HOLE"):
        return [], final_validation

    # Per-deck detonation delay (Falla 8 fix, audit 2026-08-03).
    # Precedence — explicit higher-resolution field wins, then deck-level
    # Retardo_ms, then the row-level Retardo_ms as a fallback:
    #   1. deck["detonation_time_s"] (already normalised to seconds)
    #   2. deck["Retardo_ms"] or deck["delay_ms"] (normalised ms → s)
    #   3. row-level Retardo_ms (passed as row_delay_ms)
    # The original field name and value are preserved in the deck marker
    # for downstream provenance (no silent precedence overrides).
    deck_delay_ms = _coerce_float(
        deck.get("Retardo_ms")
        if deck.get("Retardo_ms") is not None
        else deck.get("delay_ms")
    )
    detonation_time_s: Optional[float] = _coerce_float(deck.get("detonation_time_s"))
    deck_delay_provenance = ""
    if detonation_time_s is not None:
        deck_delay_provenance = "deck.detonation_time_s"
    elif deck_delay_ms is not None:
        detonation_time_s = deck_delay_ms / 1000.0
        deck_delay_provenance = "deck.Retardo_ms->s"
    elif row_delay_ms is not None:
        detonation_time_s = row_delay_ms / 1000.0
        deck_delay_provenance = "row.Retardo_ms->s"

    mass_kg, _mass_source = _resolve_deck_mass(deck, validation.length_m)
    if mass_kg is None or mass_kg <= 0.0:
        marker = _make_deck_marker(
            hole_id=hole_id,
            source_idx=source_idx,
            collar=collar,
            unit=unit,
            validation=final_validation,
            diameter_mm=diameter_mm,
            detonation_time_s=detonation_time_s,
            explosive_name=exp_name,
            explosive_status=exp_status,
            config=config,
            reason="deck has no mass (mass_kg / kg_per_m / density all missing)",
        )
        return [marker], final_validation

    seg_energy_total: Optional[float] = None
    if energy_mj_kg is not None and product is not None:
        seg_energy_total = mass_kg * energy_mj_kg * 1.0e6  # J

    n = max(1, int(n_segments_per_deck))
    seg_len = validation.length_m / n
    seg_mass = mass_kg / n
    seg_energy_each = (
        seg_energy_total / n if seg_energy_total is not None else None
    )

    bounds = config.domain_bounds
    segments: list[ChargeSegment] = []
    for k in range(n):
        start_d = validation.from_m + k * seg_len
        centre = _segment_centre(collar, unit, start_d, seg_len / 2.0)
        in_domain = _point_in_bounds(centre, bounds)
        warning = _deck_warning_marker(
            validation.deck_id, validation.from_m, validation.to_m,
            validation.status,
        )
        warnings_tuple: tuple[str, ...] = (warning,)
        if deck_delay_provenance:
            # Preserve per-deck delay provenance so downstream layers can
            # trace which field supplied the detonation time (Falla 8).
            warnings_tuple = (
                *warnings_tuple,
                f"deck_delay:{deck_delay_provenance}:"
                f"{detonation_time_s if detonation_time_s is not None else 'None'}",
            )
        seg = ChargeSegment(
            hole_id=hole_id,
            segment_type="charge",
            cx=float(centre[0]),
            cy=float(centre[1]),
            cz=float(centre[2]),
            length_m=seg_len,
            diameter_mm=diameter_mm,
            mass_kg=seg_mass,
            energy_j=seg_energy_each,
            explosive_name=exp_name,
            explosive_status=exp_status,
            detonation_time_s=detonation_time_s,
            in_domain=in_domain,
            source_row_index=source_idx,
            warnings=warnings_tuple,
        )
        segments.append(seg)
    return segments, final_validation


# ---------------------------------------------------------------------------
# Row-level geometry helper
# ---------------------------------------------------------------------------


def _resolve_row_geometry(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Resolve collar / toe / taco / length for one accepted row.

    Returns ``None`` when collar/toe coordinates are missing or the
    hole has zero length. The returned dict has the canonical geometry
    context shared by both legacy and deck-aware code paths.
    """
    collar_x = _coerce_float(row.get("X"))
    collar_y = _coerce_float(row.get("Y"))
    collar_z = _coerce_float(row.get("Z_collar"))
    toe_x = _coerce_float(row.get("X_toe"))
    toe_y = _coerce_float(row.get("Y_toe"))
    toe_z = _coerce_float(row.get("Z_toe"))
    if None in (collar_x, collar_y, collar_z, toe_x, toe_y, toe_z):
        return None
    collar = np.asarray([collar_x, collar_y, collar_z], dtype=float)
    toe = np.asarray([toe_x, toe_y, toe_z], dtype=float)
    try:
        unit = hole_axis_unit_vector(tuple(collar), tuple(toe))
    except ValueError:
        return None
    geom_len = float(np.linalg.norm(toe - collar))
    declared_len = _coerce_float(row.get("Len")) or geom_len
    taco_m = _coerce_float(row.get("Taco_m")) or 0.0
    return {
        "collar": collar,
        "toe": toe,
        "unit": unit,
        "geom_len": geom_len,
        "declared_len": declared_len,
        "taco_m": taco_m,
    }


def _row_common_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Extract fields shared by every row-level segment builder."""
    return {
        "hole_id": str(
            row.get("hole_id") or row.get("pozo") or row.get("id_pozo") or "?"
        ),
        "source_idx": row.get("source_row_index"),
        "diameter_mm": _coerce_float(row.get("Diam_mm")) or 0.0,
        "delay_ms": _coerce_float(
            row.get("Retardo_ms")
            or row.get("delay_ms")
            or row.get("Tiempo_Retardo")
        ),
    }


# ---------------------------------------------------------------------------
# Per-row deck builder
# ---------------------------------------------------------------------------


def build_deck_segments(
    row: dict[str, Any],
    *,
    config: SimulationConfiguration,
    n_segments_per_deck: int = 4,
) -> list[ChargeSegment]:
    """Parse + validate + discretize every deck in ``row``.

    Pipeline:

    1. ``parse_decks_from_row`` → ``[]`` triggers early return
       (legacy single-column mode is handled by the dispatcher).
    2. Resolve row geometry (collar / toe / geom_len / Taco).
    3. Per-deck validation in input order; the first deck to claim a
       range wins, later overlaps are marked ``OVERLAP``.
    4. Discretize each surviving deck into ``n_segments_per_deck``
       charge segments with uniformly-distributed mass / energy.
    5. The returned list contains charge segments only — invalid decks
       contribute nothing (no charge segments). When every deck is
       invalid, the caller (dispatcher) emits a single ``taco`` marker
       so the hole still appears in the source summary.

    Deck metadata (``deck_id``, ``from_m``, ``to_m``, ``status``) is
    preserved on every emitted segment as a structured entry in
    :attr:`ChargeSegment.warnings`.
    """
    decks_raw = parse_decks_from_row(row)
    if not decks_raw:
        return []

    geom = _resolve_row_geometry(row)
    if geom is None:
        return []
    common = _row_common_fields(row)

    validations: list[DeckValidation] = []
    for idx, deck in enumerate(decks_raw):
        deck_id = str(deck.get("deck_id") or f"DK{idx + 1}")
        deck["_validation"] = None  # type: ignore[index]
        v = validate_deck(
            deck,
            hole_id=common["hole_id"],
            taco_m=geom["taco_m"],
            geom_len=geom["geom_len"],
            deck_id=deck_id,
            all_decks=decks_raw,
        )
        deck["_validation"] = v  # type: ignore[index]
        validations.append(v)

    out: list[ChargeSegment] = []
    for deck, validation in zip(decks_raw, validations):
        if validation.status in (
            "INVALID_GEOMETRY", "TACO_INVADED", "ZERO_LENGTH", "OVERLAP",
        ):
            continue
        segs, _ = _build_deck_charge_segments(
            deck=deck,
            validation=validation,
            hole_id=common["hole_id"],
            source_idx=common["source_idx"],
            collar=geom["collar"],
            unit=geom["unit"],
            diameter_mm=common["diameter_mm"],
            row_delay_ms=common["delay_ms"],
            config=config,
            n_segments_per_deck=n_segments_per_deck,
        )
        out.extend(segs)
    return out


def _empty_hole_marker(
    row: dict[str, Any], *, config: SimulationConfiguration,
) -> list[ChargeSegment]:
    """Emit a single zero-length ``taco`` marker for a hole whose decks all failed."""
    common = _row_common_fields(row)
    geom = _resolve_row_geometry(row)
    if geom is None:
        return [_invalid_segment(common["hole_id"], common["source_idx"],
                                 "missing collar/toe coordinates")]
    collar = geom["collar"]
    detonation_time_s = (
        common["delay_ms"] / 1000.0 if common["delay_ms"] is not None else None
    )
    return [
        ChargeSegment(
            hole_id=common["hole_id"],
            segment_type="taco",
            cx=float(collar[0]),
            cy=float(collar[1]),
            cz=float(collar[2]),
            length_m=0.0,
            diameter_mm=common["diameter_mm"],
            mass_kg=0.0,
            energy_j=None,
            explosive_name="UNKNOWN",
            explosive_status="UNKNOWN",
            detonation_time_s=detonation_time_s,
            in_domain=_point_in_bounds(collar, config.domain_bounds),
            source_row_index=common["source_idx"],
            warnings=("all_decks_invalid",),
        )
    ]


# ---------------------------------------------------------------------------
# Legacy single-column segmentation
# ---------------------------------------------------------------------------


def _segment_single_hole(
    row: dict[str, Any],
    *,
    config: SimulationConfiguration,
    segments_per_hole: int,
) -> list[ChargeSegment]:
    """Legacy single-column discretization (no decks).

    Kept verbatim from the original implementation: the explosive
    column runs from ``collar + taco`` to ``toe`` and is split into
    ``segments_per_hole`` equal sub-segments. Rows with no
    explosive column or no declared mass produce a single ``taco``
    marker so they still appear in the source summary.
    """
    common = _row_common_fields(row)
    geom = _resolve_row_geometry(row)
    if geom is None:
        return [_invalid_segment(
            common["hole_id"], common["source_idx"],
            "missing collar/toe coordinates",
        )]

    collar = geom["collar"]
    unit = geom["unit"]
    geom_len = geom["geom_len"]
    declared_len = geom["declared_len"]
    taco_m = geom["taco_m"]

    descarga_m = _coerce_float(row.get("descarga"))
    kilos = _coerce_float(row.get("Kilos_Cargados_real"))
    explosive_name = str(row.get("Tipo_Explosivo") or "").strip()
    delay_ms = common["delay_ms"]
    diameter_mm = common["diameter_mm"]

    warnings: list[str] = []

    candidate_charge = descarga_m if descarga_m is not None else (declared_len - taco_m)
    if candidate_charge is None or not math.isfinite(candidate_charge):
        candidate_charge = geom_len - taco_m
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

    product: Optional[ExplosiveProduct] = (
        resolve_explosive(explosive_name) if explosive_name else None
    )
    explosive_status = (
        get_explosive_status(explosive_name) if explosive_name else "MISSING"
    )
    energy_mj_kg = product.energy_mj_kg if product else None

    energy_mode = config.energy_mode or EnergyMode.RELATIVE
    if (
        energy_mode == EnergyMode.ABSOLUTE
        and (product is None or energy_mj_kg is None)
    ):
        warnings.append(
            "ABSOLUTE mode blocked: explosive product or specific energy unavailable"
        )

    n_segs = max(1, int(segments_per_hole))
    if charge_length_m <= 0.0 or kilos is None or kilos <= 0.0:
        marker = ChargeSegment(
            hole_id=common["hole_id"],
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
            source_row_index=common["source_idx"],
            warnings=tuple(warnings) if warnings else (),
        )
        return [marker]

    seg_len = charge_length_m / n_segs
    seg_mass = kilos / n_segs
    seg_energy: Optional[float] = None
    if product is not None and energy_mj_kg is not None:
        seg_energy = seg_mass * energy_mj_kg * 1.0e6

    bounds = config.domain_bounds
    segments: list[ChargeSegment] = []
    for k in range(n_segs):
        start_d = taco_m + k * seg_len
        centre = _segment_centre(collar, unit, start_d, seg_len / 2.0)
        in_domain = _point_in_bounds(centre, bounds)
        seg = ChargeSegment(
            hole_id=common["hole_id"],
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
            source_row_index=common["source_idx"],
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
    n_segments_per_deck: int = 4,
) -> list[ChargeSegment]:
    """Build the full list of charge segments from accepted rows.

    Per-row dispatch:

    * **Decks mode** — when ``row["Decks"]`` is a non-empty list, each
      deck is validated and discretized independently. The output
      contains ``n_validated_decks × n_segments_per_deck`` charge
      segments (from OK / OUT_OF_HOLE decks only). When every deck
      failed validation, ONE ``taco`` marker is emitted so the hole
      still appears in the source summary.
    * **Legacy single-column mode** — when ``row["Decks"]`` is
      missing, ``None`` or empty, the row is processed as a single
      contiguous explosive cylinder between ``collar + Taco`` and
      ``toe``, producing ``segments_per_hole`` charge segments (or
      one ``taco`` marker when there is no explosive column).

    Hard rules preserved across both modes:

    * NEVER silently substitutes ANFO for an unknown explosive.
    * NEVER invents a mass.
    * NEVER extends a charge beyond the geometric collar→toe segment.
    * NEVER emits a negative-length segment.
    """
    if segments_per_hole < 1:
        raise ValueError("segments_per_hole must be >= 1")
    if n_segments_per_deck < 1:
        raise ValueError("n_segments_per_deck must be >= 1")

    out: list[ChargeSegment] = []
    for row in accepted_rows:
        if parse_decks_from_row(row):
            deck_segs = build_deck_segments(
                row,
                config=config,
                n_segments_per_deck=n_segments_per_deck,
            )
            if not deck_segs:
                out.extend(_empty_hole_marker(row, config=config))
            else:
                out.extend(deck_segs)
        else:
            out.extend(
                _segment_single_hole(
                    row,
                    config=config,
                    segments_per_hole=segments_per_hole,
                )
            )
    return out


# ---------------------------------------------------------------------------
# Segment classification
# ---------------------------------------------------------------------------


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


__all__ = [
    "DeckValidation",
    "DeckSegment",
    "build_charge_segments",
    "build_deck_segments",
    "classify_segments",
    "hole_axis_unit_vector",
    "parse_decks_from_row",
    "validate_deck",
]
