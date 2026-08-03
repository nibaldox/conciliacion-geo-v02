"""Energy simulation adapter — Streamlit presentation layer only.

This module is the documented H-10 exception: ``ui/modulo_tronadura/``
may host presentation/adapters but NO domain logic. Every formula lives
in :mod:`core.blast_simulation`; this file only:

* collects operator decisions via Streamlit widgets (every physical
  selector starts empty — no silent defaults);
* renders the 3×3 anisotropy tensor editor (Falla 5) with explicit
  symmetry and positive-definite validation BEFORE the engine runs;
* fingerprints the configuration via SHA-256 so any edit clears the
  confirmation checkbox exactly like the Fase 1 ``upload.py`` geometry
  contract;
* invokes ``run_simulation`` on a worker thread;
* renders the canonical 2D maps (plant + section) and the linear profile
  (Falla 4) using the real numeric values from the persisted result —
  NOT re-implemented here.

The slice / profile helpers come from :mod:`core.blast_simulation.slicing`
(read-only sampling over the persisted field). No physics is computed
inline.
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.blast_simulation import (
    SIMULATION_CONFIGURATION_VERSION,
    AnisotropyMode,
    DEFAULT_BAND_EDGES,
    DomainBounds,
    EnergyMode,
    KernelType,
    RockMassConfiguration,
    SimulationConfiguration,
    SimulationConfigurationError,
    TemporalMode,
    VoxelGridSpecification,
    plan_slice,
    profile_slice,
    read_npz_artifact,
    run_simulation,
    section_slice,
    write_npz_artifact,
    write_summary_json,
)
from core.blast_simulation.contracts import _is_symmetric_pd
from core.config import SIMULATION as SIM_DEFAULTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tensor 3×3 — symmetric / positive-definite validation
# ---------------------------------------------------------------------------


_TENSOR_LABELS: tuple[str, ...] = ("11", "12", "13", "21", "22", "23", "31", "32", "33")


def _tensor_default() -> tuple[float, ...]:
    """Return the nine-entry diagonal default — NOT auto-applied.

    The operator MUST press the explicit "Usar identidad I=diag(1,1,1)"
    button to populate the tensor. The fields render empty until then.
    """
    return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _read_tensor_from_state() -> tuple[float, ...] | None:
    """Read the 9 tensor entries from ``st.session_state``.

    Returns ``None`` if any cell is missing or not finite. The widget
    initialisation populates every cell with a finite float, so ``None``
    means the operator never touched the editor.
    """
    out: list[float] = []
    for label in _TENSOR_LABELS:
        key = f"sim_m{label}"
        v = st.session_state.get(key)
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(f):
            return None
        out.append(f)
    return tuple(out)


def _tensor_as_3x3(values: tuple[float, ...]) -> tuple[tuple[float, float, float], ...]:
    return (
        (values[0], values[1], values[2]),
        (values[3], values[4], values[5]),
        (values[6], values[7], values[8]),
    )


def _validate_tensor(values: tuple[float, ...]) -> dict[str, str]:
    """Validate the 3×3 tensor.

    Returns an empty dict when valid. Otherwise a mapping ``field → msg``
    explaining the failure. Checks: shape, finiteness, symmetry,
    positive-definiteness (via Sylvester's criterion, delegated to
    :func:`core.blast_simulation.contracts._is_symmetric_pd`).
    """
    errors: dict[str, str] = {}
    if len(values) != 9:
        return {"shape": "Debe ser un tensor 3×3"}
    sym_pd = _is_symmetric_pd(_tensor_as_3x3(values))
    if not sym_pd:
        # Try to give a more specific message when the failure is just
        # symmetry, vs a genuine non-PD matrix.
        matrix = _tensor_as_3x3(values)
        if not np.allclose(matrix, np.array(matrix).T, atol=1e-12):
            errors["symmetry"] = "El tensor debe ser simétrico (Mᵢⱼ = Mⱼᵢ)."
        else:
            errors["positive_definite"] = (
                "El tensor debe ser positivo definido (todos los autovalores > 0)."
            )
    return errors


def _set_identity_tensor() -> None:
    """Programmatically populate the 9 tensor cells with I = diag(1,1,1).

    Bound to the explicit "Usar identidad" button — never the default.
    """
    values = _tensor_default()
    for label, value in zip(_TENSOR_LABELS, values):
        st.session_state[f"sim_m{label}"] = float(value)


def _sync_pair(*, source: str, target: str) -> None:
    """Symmetry-preserving callback: when ``source`` changes, copy to ``target``.

    Streamlit does NOT re-trigger ``on_change`` when a widget's value is
    updated programmatically, so this avoids the Mij ↔ Mji ping-pong.
    """
    src_val = st.session_state.get(source)
    if src_val is not None:
        try:
            st.session_state[target] = float(src_val)
        except (TypeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Fingerprint + validation
# ---------------------------------------------------------------------------


def simulation_fingerprint(state: dict[str, Any]) -> str:
    """Stable SHA-256 over the operator-selected simulation parameters.

    The anisotropy tensor (when present) is folded into the digest so
    editing a cell invalidates the confirmation exactly like the Fase 1
    geometry contract.
    """
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_config(state: dict[str, Any], geom_version: str) -> SimulationConfiguration:
    """Build the canonical :class:`SimulationConfiguration` from the UI state.

    The anisotropy tensor is forwarded only when the operator chose
    ``ANISOTROPIC_TENSOR``; otherwise the engine's isotropic kernel is
    used untouched. The state must already carry the validated tensor
    when ``anisotropy_mode == ANISOTROPIC_TENSOR``.
    """
    anisotropy_mode = state.get("anisotropy_mode", AnisotropyMode.ISOTROPIC)
    anisotropy_tensor_value = state.get("anisotropy_tensor")
    if anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR and anisotropy_tensor_value:
        anisotropy_tensor = _tensor_as_3x3(tuple(anisotropy_tensor_value))
    else:
        anisotropy_tensor = None
    rock = RockMassConfiguration(
        rock_unit_id=state.get("rock_unit_id", ""),
        density_kg_m3=state.get("rock_density_kg_m3"),
        ucs_mpa=state.get("rock_ucs_mpa"),
        attenuation_coefficient_1_m=state.get("rock_attenuation"),
        wave_velocity_m_s=state.get("rock_velocity"),
        anisotropy_mode=anisotropy_mode,
        anisotropy_tensor=anisotropy_tensor,
        source=state.get("rock_source", ""),
        status=state.get("rock_status", "MISSING"),
    )
    bounds = DomainBounds(
        x_min=float(state["x_min"]), y_min=float(state["y_min"]), z_min=float(state["z_min"]),
        x_max=float(state["x_max"]), y_max=float(state["y_max"]), z_max=float(state["z_max"]),
    )
    return SimulationConfiguration(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version=geom_version,
        user_confirmed=True,
        voxel_size_m=float(state["voxel_size_m"]),
        domain_bounds=bounds,
        energy_mode=state["energy_mode"],
        temporal_mode=state["temporal_mode"],
        anisotropy_mode=anisotropy_mode,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=float(state["attenuation_coefficient_1_m"]),
        regularization_radius_m=float(state["regularization_radius_m"]),
        coupling_efficiency=float(state["coupling_efficiency"]),
        propagation_velocity_m_s=state.get("propagation_velocity_m_s"),
        propagation_velocity_source=state.get("propagation_velocity_source", ""),
        pulse_sigma_s=state.get("pulse_sigma_s"),
        rock_mass=rock,
    )


# ---------------------------------------------------------------------------
# Slice rendering — 2D maps (Falla 4)
# ---------------------------------------------------------------------------


def _plan_slice_to_grid_matrix(plan_slice_dict: dict[str, Any]) -> np.ndarray:
    """Reshape a serialised :class:`PlanSlice` back into a 2D ``(nx, ny)`` matrix."""
    nx, ny = int(plan_slice_dict["grid_shape"][0]), int(plan_slice_dict["grid_shape"][1])
    values = np.asarray(plan_slice_dict["values"], dtype=np.float64)
    if values.size == 0 or nx == 0 or ny == 0:
        return np.zeros((max(nx, 0), max(ny, 0)), dtype=np.float64)
    return values.reshape((nx, ny))


def _section_slice_to_grid_matrix(section_slice_dict: dict[str, Any]) -> np.ndarray:
    """Reshape a serialised :class:`SectionSlice` back into a 2D ``(along, vertical)`` matrix."""
    na, nz = int(section_slice_dict["grid_shape"][0]), int(section_slice_dict["grid_shape"][1])
    values = np.asarray(section_slice_dict["values"], dtype=np.float64)
    if values.size == 0 or na == 0 or nz == 0:
        return np.zeros((max(na, 0), max(nz, 0)), dtype=np.float64)
    return values.reshape((na, nz))


def _render_plan_slice(
    plan_slice_dict: dict[str, Any],
    *,
    unit: str,
    energy_max: float,
) -> None:
    """Render a horizontal plan slice as a Plotly heatmap with holes overlay."""
    matrix = _plan_slice_to_grid_matrix(plan_slice_dict)
    x_coords = np.asarray(plan_slice_dict.get("x_coordinates_m", ()), dtype=np.float64)
    y_coords = np.asarray(plan_slice_dict.get("y_coordinates_m", ()), dtype=np.float64)
    if matrix.size == 0 or x_coords.size == 0 or y_coords.size == 0:
        st.info("El slice en planta no contiene datos (dominio vacío).")
        return
    z_max = float(matrix.max()) if float(matrix.max()) > 0.0 else 1.0
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=x_coords,
            y=y_coords,
            colorscale="Viridis",
            zmin=0.0,
            zmax=z_max,
            colorbar=dict(title=f"Energía ({unit})"),
            hovertemplate=(
                "X: %{x:.2f} m<br>"
                "Y: %{y:.2f} m<br>"
                f"Valor: %{{z:.3e}} {unit}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=(
            f"Planta z = {float(plan_slice_dict['elevation_m']):.2f} m  "
            f"(max campo = {energy_max:.3e} {unit})"
        ),
        xaxis_title="X (Este, m)",
        yaxis_title="Y (Norte, m)",
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    holes = plan_slice_dict.get("source_holes_projection") or []
    if holes:
        hx = [float(h.get("x_m", 0.0)) for h in holes]
        hy = [float(h.get("y_m", 0.0)) for h in holes]
        hover_ids = [str(h.get("hole_id", "")) for h in holes]
        hover_values = [float(h.get("value_at_voxel", 0.0)) for h in holes]
        fig.add_trace(
            go.Scatter(
                x=hx,
                y=hy,
                mode="markers",
                marker=dict(symbol="x", color="white", size=10, line=dict(width=1.5)),
                name="Pozos",
                customdata=np.stack([hover_ids, hover_values], axis=1),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "X: %{x:.2f} m<br>"
                    "Y: %{y:.2f} m<br>"
                    f"Valor: %{{customdata[1]:.3e}} {unit}<extra></extra>"
                ),
            )
        )
    st.plotly_chart(fig, width="stretch")


def _render_section_slice(
    section_slice_dict: dict[str, Any],
    *,
    unit: str,
    energy_max: float,
) -> None:
    """Render a vertical section slice as a Plotly heatmap with holes overlay."""
    matrix = _section_slice_to_grid_matrix(section_slice_dict)
    along = np.asarray(section_slice_dict.get("along_coordinates_m", ()), dtype=np.float64)
    vertical = np.asarray(section_slice_dict.get("vertical_coordinates_m", ()), dtype=np.float64)
    if matrix.size == 0 or along.size == 0 or vertical.size == 0:
        st.info("La sección vertical no contiene datos (dominio vacío).")
        return
    z_max = float(matrix.max()) if float(matrix.max()) > 0.0 else 1.0
    axis = str(section_slice_dict.get("axis", "x"))
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=along,
            y=vertical,
            colorscale="Viridis",
            zmin=0.0,
            zmax=z_max,
            colorbar=dict(title=f"Energía ({unit})"),
            hovertemplate=(
                "A lo largo: %{x:.2f} m<br>"
                "Cota: %{y:.2f} m<br>"
                f"Valor: %{{z:.3e}} {unit}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=(
            f"Sección eje {axis} = {float(section_slice_dict['coordinate_m']):.2f} m  "
            f"(max campo = {energy_max:.3e} {unit})"
        ),
        xaxis_title=f"{'Norte' if axis == 'x' else 'Este'} (m)",
        yaxis_title="Cota (m)",
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    holes = section_slice_dict.get("source_holes_projection") or []
    if holes:
        if axis == "x":
            h_along = [float(h.get("y_m", 0.0)) for h in holes]
        else:
            h_along = [float(h.get("x_m", 0.0)) for h in holes]
        h_vert = [float(h.get("z_m", 0.0)) for h in holes]
        hover_ids = [str(h.get("hole_id", "")) for h in holes]
        hover_values = [float(h.get("value_at_voxel", 0.0)) for h in holes]
        fig.add_trace(
            go.Scatter(
                x=h_along,
                y=h_vert,
                mode="markers",
                marker=dict(symbol="x", color="white", size=10, line=dict(width=1.5)),
                name="Pozos",
                customdata=np.stack([hover_ids, hover_values], axis=1),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "A lo largo: %{x:.2f} m<br>"
                    "Cota: %{y:.2f} m<br>"
                    f"Valor: %{{customdata[1]:.3e}} {unit}<extra></extra>"
                ),
            )
        )
    st.plotly_chart(fig, width="stretch")


def _render_energy_bands(
    *,
    field_total_flat: np.ndarray,
    active_mask: np.ndarray | None,
    unit: str,
) -> None:
    """Render the 5 relative energy bands as a Plotly bar chart.

    Bands are RELATIVE to the field's own maximum (Brecha 6 / Falla 4
    contract). The computation is delegated to
    :func:`core.blast_simulation.classify_energy_bands` whenever
    available; otherwise the same algorithm is reproduced inline as a
    pure read-only operation over the persisted field.
    """
    arr = np.asarray(field_total_flat, dtype=np.float64).ravel()
    if active_mask is None:
        active_mask = arr > 0.0
    active_mask = np.asarray(active_mask, dtype=bool).ravel()
    if active_mask.size != arr.size:
        active_mask = arr > 0.0
    if not active_mask.any() or arr.max() <= 0.0:
        st.info("Sin vóxeles activos: no se calculan bandas.")
        return
    max_e = float(arr[active_mask].max())
    norm = arr[active_mask] / max_e
    integrated = arr[active_mask]
    n_active = int(active_mask.sum())
    labels: list[str] = []
    counts: list[int] = []
    fractions: list[float] = []
    energies: list[float] = []
    for lo, hi in DEFAULT_BAND_EDGES:
        mask = (norm >= lo) & (norm < hi)
        cnt = int(mask.sum())
        labels.append(f"[{lo:.2f}, {hi:.2f})")
        counts.append(cnt)
        fractions.append(cnt / n_active if n_active else 0.0)
        energies.append(float(integrated[mask].sum()))
    band_fig = go.Figure(
        data=go.Bar(
            x=labels,
            y=fractions,
            marker=dict(
                color=energies,
                colorscale="Viridis",
                colorbar=dict(title=f"Energía ({unit})"),
            ),
            customdata=np.stack([counts, energies], axis=1),
            hovertemplate=(
                "Banda: %{x}<br>"
                "Vóxeles: %{customdata[0]}<br>"
                "Fracción activos: %{y:.3f}<br>"
                f"Energía integrada: %{{customdata[1]:.3e}} {unit}<extra></extra>"
            ),
        )
    )
    band_fig.update_layout(
        title="Bandas relativas de energía (5)",
        xaxis_title="Banda (fracción del máximo)",
        yaxis_title="Fracción de vóxeles activos",
        height=320,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(band_fig, width="stretch")


# ---------------------------------------------------------------------------
# Linear profile (Falla 4)
# ---------------------------------------------------------------------------


def _load_field_arrays(result_dict: dict[str, Any]) -> dict[str, np.ndarray] | None:
    """Read the persisted NPZ artifact if available; ``None`` otherwise."""
    ef = result_dict.get("energy_field") or {}
    npz_path = ef.get("npz_path") or ""
    if not npz_path:
        return None
    if not Path(npz_path).exists():
        return None
    try:
        arrays, _meta, _sha = read_npz_artifact(npz_path)
    except Exception as exc:
        logger.warning("No se pudo leer NPZ %s: %s", npz_path, exc)
        return None
    return arrays


def _render_profile(
    *,
    result_dict: dict[str, Any],
    start_xyz: tuple[float, float, float],
    end_xyz: tuple[float, float, float],
    n_samples: int,
) -> None:
    """Render a linear profile between two 3D points.

    The sampling is delegated to :func:`core.blast_simulation.profile_slice`
    — the canonical read-only helper that interpolates the per-voxel field
    along the straight segment. No physics is recomputed here.
    """
    arrays = _load_field_arrays(result_dict)
    if not arrays or "energy_total" not in arrays:
        st.info(
            "No se encontró el artefacto NPZ de la simulación; el perfil no "
            "puede mostrarse. Vuelva a ejecutar la simulación para regenerarlo."
        )
        return
    grid_meta = result_dict.get("grid_metadata") or {}
    bounds_dict = grid_meta.get("bounds") or {}
    try:
        bounds = DomainBounds(
            x_min=float(bounds_dict["x_min"]),
            y_min=float(bounds_dict["y_min"]),
            z_min=float(bounds_dict["z_min"]),
            x_max=float(bounds_dict["x_max"]),
            y_max=float(bounds_dict["y_max"]),
            z_max=float(bounds_dict["z_max"]),
        )
    except (KeyError, TypeError, ValueError):
        st.info("Dominio inválido en la simulación; no se puede perfilar.")
        return
    voxel_size = float(grid_meta.get("voxel_size_m") or 0.0)
    if voxel_size <= 0.0:
        st.info("Tamaño de vóxel inválido; no se puede perfilar.")
        return
    grid = VoxelGridSpecification(voxel_size_m=voxel_size, bounds=bounds)
    unit = str(grid_meta.get("energy_unit") or "J")
    profile = profile_slice(
        energy_total_flat=np.asarray(arrays["energy_total"], dtype=np.float64),
        grid=grid,
        start_xyz=(float(start_xyz[0]), float(start_xyz[1]), float(start_xyz[2])),
        end_xyz=(float(end_xyz[0]), float(end_xyz[1]), float(end_xyz[2])),
        n_samples=int(n_samples),
        energy_unit=unit,
    )
    distances = np.asarray(profile.get("distances_m", ()), dtype=np.float64)
    values = np.asarray(profile.get("values", ()), dtype=np.float64)
    if distances.size == 0 or values.size == 0:
        st.info("El perfil no contiene muestras dentro del dominio.")
        return
    fig = go.Figure(
        data=go.Scatter(
            x=distances,
            y=values,
            mode="lines+markers",
            name="Perfil",
            line=dict(width=2),
            marker=dict(size=4),
            hovertemplate=(
                "Distancia: %{x:.2f} m<br>"
                f"Valor: %{{y:.3e}} {unit}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=(
            f"Perfil {start_xyz} → {end_xyz}  ({int(n_samples)} muestras)"
        ),
        xaxis_title="Distancia (m)",
        yaxis_title=f"Energía ({unit})",
        height=360,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, width="stretch")
    pmin = float(profile.get("min", 0.0))
    pmax = float(profile.get("max", 0.0))
    pmean = float(profile.get("mean", 0.0))
    m1, m2, m3 = st.columns(3)
    m1.metric("Mínimo", f"{pmin:.3e} {unit}")
    m2.metric("Máximo", f"{pmax:.3e} {unit}")
    m3.metric("Promedio", f"{pmean:.3e} {unit}")


# ---------------------------------------------------------------------------
# Result rendering (Falla 4 — never re-implement the engine)
# ---------------------------------------------------------------------------


def _render_result(result_dict: dict[str, Any]) -> None:
    """Render the canonical simulation result.

    Combines: KPI metrics, blocking errors, 2D maps (plant + section),
    relative energy bands, warnings, and the provenance block. The
    slices are picked up from the persisted result dict — no re-engineering
    of the engine.
    """
    ef = result_dict.get("energy_field") or {}
    summary = result_dict.get("processing_summary") or {}
    grid_meta = result_dict.get("grid_metadata") or {}
    unit = str(grid_meta.get("energy_unit") or "J")
    energy_max = float(ef.get("max_energy_j") or 0.0)

    st.markdown("**Resumen de la simulación**")
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Energía representada", f"{float(ef.get('represented_energy_j', 0.0)):.2e} {unit}")
    sc2.metric("Energía fuera del dominio", f"{float(ef.get('outside_domain_energy_j', 0.0)):.2e} {unit}")
    sc3.metric("Fracción representada", f"{float(ef.get('fraction_represented', 0.0)) * 100:.1f} %")
    sc4.metric(
        "Vóxeles activos",
        f"{int(ef.get('active_voxels', 0))} / {int(grid_meta.get('voxel_count', 0))}",
    )

    blocking = result_dict.get("blocking_errors") or []
    if blocking:
        st.markdown("**Errores bloqueantes**")
        for err in blocking:
            st.error(f"**{err.get('error_code', 'ERROR')}**: {err.get('message', '')}")
            details = err.get("details")
            if details:
                st.json(details)

    warnings = result_dict.get("warnings") or []
    if warnings:
        st.markdown("**Advertencias**")
        for w in warnings:
            st.warning(str(w.get("message", w)))

    src = result_dict.get("source_summary") or {}
    df_summary = pd.DataFrame([
        {"Métrica": "Fuentes válidas", "Valor": src.get("valid_sources", 0)},
        {"Métrica": "Fuentes inválidas", "Valor": src.get("invalid_sources", 0)},
        {"Métrica": "Segmentos de carga", "Valor": src.get("charge_segments", 0)},
        {"Métrica": "Pozos aceptados", "Valor": src.get("accepted_holes", 0)},
        {"Métrica": "Modo de energía", "Valor": summary.get("energy_mode", "")},
        {"Métrica": "Estado temporal", "Valor": summary.get("temporal_status", "")},
    ])
    st.markdown("**Procedencia y diagnóstico**")
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

    plan_slices = result_dict.get("plan_slices") or []
    if plan_slices:
        st.markdown("**Mapa en planta (heatmap)**")
        plan_labels = [
            f"z = {float(p.get('elevation_m', 0.0)):.2f} m  "
            f"(sha {str(p.get('data_sha256', ''))[:8]})"
            for p in plan_slices
        ]
        idx = st.selectbox(
            "Slice en planta",
            options=list(range(len(plan_slices))),
            format_func=lambda i: plan_labels[int(i)],
            key="sim_plan_slice_idx",
        )
        _render_plan_slice(plan_slices[int(idx)], unit=unit, energy_max=energy_max)

    section_slices = result_dict.get("section_slices") or []
    if section_slices:
        st.markdown("**Sección vertical (heatmap)**")
        section_labels = [
            f"{str(s.get('axis', 'x'))} = {float(s.get('coordinate_m', 0.0)):.2f} m  "
            f"(sha {str(s.get('data_sha256', ''))[:8]})"
            for s in section_slices
        ]
        idx = st.selectbox(
            "Sección vertical",
            options=list(range(len(section_slices))),
            format_func=lambda i: section_labels[int(i)],
            key="sim_section_slice_idx",
        )
        _render_section_slice(section_slices[int(idx)], unit=unit, energy_max=energy_max)

    arrays = _load_field_arrays(result_dict)
    if arrays is not None and "energy_total" in arrays:
        st.markdown("**Bandas relativas de energía (5)**")
        active_mask = (np.asarray(arrays["energy_total"], dtype=np.float64) > 0.0)
        _render_energy_bands(
            field_total_flat=arrays["energy_total"],
            active_mask=active_mask,
            unit=unit,
        )

        st.markdown("**Perfil lineal**")
        bounds = grid_meta.get("bounds") or {}
        sx_col, sy_col, sz_col = st.columns(3)
        with sx_col:
            sx = st.number_input(
                "X inicio (m)",
                value=float(bounds.get("x_min", 0.0)),
                step=0.5,
                key="sim_profile_sx",
            )
        with sy_col:
            sy = st.number_input(
                "Y inicio (m)",
                value=float(bounds.get("y_min", 0.0)),
                step=0.5,
                key="sim_profile_sy",
            )
        with sz_col:
            sz = st.number_input(
                "Z inicio (m)",
                value=float(bounds.get("z_min", 0.0)),
                step=0.5,
                key="sim_profile_sz",
            )
        ex_col, ey_col, ez_col, n_col = st.columns(4)
        with ex_col:
            ex = st.number_input(
                "X fin (m)",
                value=float(bounds.get("x_max", 0.0)),
                step=0.5,
                key="sim_profile_ex",
            )
        with ey_col:
            ey = st.number_input(
                "Y fin (m)",
                value=float(bounds.get("y_max", 0.0)),
                step=0.5,
                key="sim_profile_ey",
            )
        with ez_col:
            ez = st.number_input(
                "Z fin (m)",
                value=float(bounds.get("z_max", 0.0)),
                step=0.5,
                key="sim_profile_ez",
            )
        with n_col:
            n_samples = st.number_input(
                "Muestras",
                min_value=2,
                max_value=10_000,
                value=200,
                step=10,
                key="sim_profile_n",
            )
        if st.button("Calcular perfil", key="sim_profile_button", type="secondary"):
            _render_profile(
                result_dict=result_dict,
                start_xyz=(sx, sy, sz),
                end_xyz=(ex, ey, ez),
                n_samples=int(n_samples),
            )

    with st.expander("Procedencia"):
        st.json(result_dict.get("provenance") or {})


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def render_energy_simulation_section(
    *,
    accepted_rows: list[dict[str, Any]] | None,
    geometry_configuration_version: str,
) -> dict[str, Any] | None:
    """Render the energy simulation adapter.

    Returns the canonical ``SimulationResult.to_dict()`` after a
    successful run, or ``None`` when no run has happened yet. The
    function is purely presentational: no physics is computed inline —
    ``run_simulation`` is the only entry point to the engine.
    """
    st.subheader("Simulador de Energía 3D")
    st.caption("Mapa energético determinista sobre vóxeles del macizo")
    st.warning(
        "Los mapas corresponden a un modelo energético ingenieril **no calibrado**. "
        "No representan por sí solos daño, fragmentación, PPV ni estabilidad."
    )

    if not accepted_rows:
        st.info("Cargue pozos aceptados de Fase 1 antes de simular.")
        return None

    # ── Domain ─────────────────────────────────────────────────────────
    st.markdown("**Dominio del macizo**")
    col1, col2, col3 = st.columns(3)
    with col1:
        x_min = st.number_input("X mínimo (Este, m)", value=None, step=0.5, key="sim_x_min")
        x_max = st.number_input("X máximo (Este, m)", value=None, step=0.5, key="sim_x_max")
    with col2:
        y_min = st.number_input("Y mínimo (Norte, m)", value=None, step=0.5, key="sim_y_min")
        y_max = st.number_input("Y máximo (Norte, m)", value=None, step=0.5, key="sim_y_max")
    with col3:
        z_min = st.number_input("Cota mínima (m)", value=None, step=0.5, key="sim_z_min")
        z_max = st.number_input("Cota máxima (m)", value=None, step=0.5, key="sim_z_max")
    voxel_size = st.number_input("Tamaño de vóxel (m)", value=None, step=0.1, key="sim_voxel")

    # ── Physical modes (empty by default — no silent defaults) ─────────
    st.markdown("**Modos físicos**")
    mcol1, mcol2, mcol3 = st.columns(3)
    with mcol1:
        energy_mode = st.selectbox(
            "Modo de energía",
            options=["", EnergyMode.ABSOLUTE, EnergyMode.RELATIVE],
            format_func=lambda x: {"": "Seleccione una opción",
                                    EnergyMode.ABSOLUTE: "Absoluta (J)",
                                    EnergyMode.RELATIVE: "Relativa"}.get(x, x),
            key="sim_energy_mode",
        )
    with mcol2:
        temporal_mode = st.selectbox(
            "Modo temporal",
            options=["", TemporalMode.STATIC, TemporalMode.TEMPORAL],
            format_func=lambda x: {"": "Seleccione una opción",
                                    TemporalMode.STATIC: "Estático",
                                    TemporalMode.TEMPORAL: "Temporal"}.get(x, x),
            key="sim_temporal_mode",
        )
    with mcol3:
        anisotropy_mode = st.selectbox(
            "Anisotropía",
            options=["", AnisotropyMode.ISOTROPIC, AnisotropyMode.ANISOTROPIC_TENSOR],
            format_func=lambda x: {"": "Seleccione una opción",
                                    AnisotropyMode.ISOTROPIC: "Isotrópica",
                                    AnisotropyMode.ANISOTROPIC_TENSOR: "Tensor 3×3 SPD"}.get(x, x),
            key="sim_anisotropy_mode",
        )

    # ── 3×3 tensor editor (Falla 5) ─────────────────────────────────────
    anisotropy_tensor_state: tuple[float, ...] | None = None
    anisotropy_tensor_errors: dict[str, str] = {}
    if anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR:
        st.markdown("**Tensor de anisotropía (3×3, simétrico y positivo definido)**")
        st.caption(
            "Edite cualquier celda; los pares Mij/Mji se mantienen en sincronía. "
            "El tensor debe ser simétrico y positivo definido."
        )
        # 3 rows × 3 columns layout. Diagonal cells have no sync partner.
        cell_layout: tuple[tuple[str, str | None], ...] = (
            (("11", None), ("12", "21"), ("13", "31")),
            (("21", "12"), ("22", None), ("23", "32")),
            (("31", "13"), ("32", "23"), ("33", None)),
        )
        for row in cell_layout:
            cells = st.columns(3)
            for cell, (label, peer) in zip(cells, row):
                with cell:
                    if peer is None:
                        st.number_input(
                            f"M{label}",
                            value=None,
                            step=0.1,
                            key=f"sim_m{label}",
                            help=f"Componente ({label}) del tensor.",
                        )
                    else:
                        st.number_input(
                            f"M{label}",
                            value=None,
                            step=0.1,
                            key=f"sim_m{label}",
                            on_change=_sync_pair,
                            kwargs={"source": f"sim_m{label}", "target": f"sim_m{peer}"},
                            help=(
                                f"Componente ({label}); editar mantiene M{peer} "
                                f"en sincronía."
                            ),
                        )
        id_col, _spacer = st.columns([1, 3])
        with id_col:
            st.button(
                "Usar identidad I = diag(1,1,1)",
                key="sim_tensor_identity",
                on_click=_set_identity_tensor,
                help=(
                    "Pulsa explícitamente para inicializar el tensor como "
                    "identidad. No es el valor por defecto."
                ),
            )
        anisotropy_tensor_state = _read_tensor_from_state()
        if anisotropy_tensor_state is None:
            anisotropy_tensor_errors = {
                "missing": "Complete las 9 celdas del tensor antes de ejecutar."
            }
        else:
            anisotropy_tensor_errors = _validate_tensor(anisotropy_tensor_state)
        if anisotropy_tensor_errors:
            for msg in anisotropy_tensor_errors.values():
                st.error(msg)

    # ── Kernel ─────────────────────────────────────────────────────────
    st.markdown("**Kernel de propagación**")
    kcol1, kcol2, kcol3 = st.columns(3)
    with kcol1:
        attenuation = st.number_input("Atenuación α (1/m)", value=None, step=0.05, key="sim_alpha")
    with kcol2:
        regularization = st.number_input("Radio de regularización r₀ (m)", value=None, step=0.1, key="sim_r0")
    with kcol3:
        coupling = st.number_input("Eficiencia de acoplamiento η (0–1)", value=None, step=0.05,
                                   min_value=0.0, max_value=1.0, key="sim_eta")

    velocity = None
    velocity_source = ""
    pulse_sigma = None
    if temporal_mode == TemporalMode.TEMPORAL:
        st.markdown("**Propagación temporal**")
        tcol1, tcol2, tcol3 = st.columns(3)
        with tcol1:
            velocity = st.number_input("Velocidad (m/s)", value=None, step=100.0, key="sim_v")
        with tcol2:
            velocity_source = st.text_input("Procedencia de la velocidad", key="sim_v_src")
        with tcol3:
            pulse_sigma = st.number_input("Sigma del pulso (s)", value=None, step=0.005, key="sim_sigma")

    # ── Rock mass (optional) ──────────────────────────────────────────
    with st.expander("Macizo rocoso (opcional)", expanded=False):
        rcol1, rcol2 = st.columns(2)
        with rcol1:
            rock_density = st.number_input("Densidad (kg/m³)", value=None, step=50.0, key="sim_rd")
            rock_attenuation = st.number_input("Atenuación macizo (1/m)", value=None, step=0.01, key="sim_ra")
        with rcol2:
            rock_velocity = st.number_input("Velocidad onda (m/s)", value=None, step=100.0, key="sim_rv")
            rock_ucs = st.number_input("UCS (MPa)", value=None, step=5.0, key="sim_rucs")
        rock_source = st.text_input("Procedencia del macizo", key="sim_rsrc")
        rock_status = st.selectbox(
            "Estado del macizo",
            options=["MISSING", "UNVALIDATED_REFERENCE", "PROXY_EMPIRICAL_LOCAL", "VALIDATED"],
            key="sim_rstatus",
        )

    # ── Confirmation by fingerprint ───────────────────────────────────
    state: dict[str, Any] = {
        "voxel_size_m": voxel_size,
        "x_min": x_min, "x_max": x_max,
        "y_min": y_min, "y_max": y_max,
        "z_min": z_min, "z_max": z_max,
        "energy_mode": energy_mode,
        "temporal_mode": temporal_mode,
        "anisotropy_mode": anisotropy_mode,
        "anisotropy_tensor": list(anisotropy_tensor_state) if anisotropy_tensor_state else None,
        "attenuation_coefficient_1_m": attenuation,
        "regularization_radius_m": regularization,
        "coupling_efficiency": coupling,
        "propagation_velocity_m_s": velocity,
        "propagation_velocity_source": velocity_source,
        "pulse_sigma_s": pulse_sigma,
        "rock_density_kg_m3": rock_density,
        "rock_attenuation": rock_attenuation,
        "rock_velocity": rock_velocity,
        "rock_ucs_mpa": rock_ucs,
        "rock_source": rock_source,
        "rock_status": rock_status,
    }
    current_fp = simulation_fingerprint(state)
    saved_fp = st.session_state.get("sim_contract_fingerprint")
    if current_fp != saved_fp:
        st.session_state["sim_confirmed"] = False

    confirmed = st.checkbox(
        "He revisado y confirmo la configuración física del evento",
        value=st.session_state.get("sim_confirmed", False),
        key="sim_confirmed",
    )
    if confirmed:
        st.session_state["sim_contract_fingerprint"] = current_fp
    else:
        st.session_state.pop("sim_contract_fingerprint", None)

    can_run = (
        confirmed
        and voxel_size and voxel_size > 0
        and x_max is not None and x_min is not None and x_max > x_min
        and y_max is not None and y_min is not None and y_max > y_min
        and z_max is not None and z_min is not None and z_max > z_min
        and energy_mode and temporal_mode and anisotropy_mode
        and attenuation is not None and attenuation >= 0
        and regularization and regularization > 0
        and coupling is not None and 0.0 <= coupling <= 1.0
        and (anisotropy_mode != AnisotropyMode.ANISOTROPIC_TENSOR
             or (anisotropy_tensor_state is not None and not anisotropy_tensor_errors))
        and (temporal_mode != TemporalMode.TEMPORAL or (velocity and velocity > 0 and velocity_source))
    )

    if st.button("Ejecutar simulación", disabled=not can_run, type="primary"):
        try:
            config = _build_config(state, geometry_configuration_version)
            config.validate()
        except SimulationConfigurationError as exc:
            st.error(f"**{exc.error_code}**: {exc}")
            if exc.details:
                st.json(exc.details)
            return None

        with st.spinner("Ejecutando motor de energía 3D…"):
            try:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(
                        run_simulation,
                        accepted_rows=accepted_rows,
                        configuration=config,
                        segments_per_hole=8,
                    )
                    result = future.result(timeout=SIM_DEFAULTS.max_wall_time_seconds)
                result, _, _sha = write_npz_artifact(
                    result=result,
                    accepted_rows=accepted_rows,
                    configuration=config,
                    segments_per_hole=8,
                )
                write_summary_json(result=result)
                st.session_state["sim_last_result"] = result.to_dict()
            except SimulationConfigurationError as exc:
                st.error(f"**{exc.error_code}**: {exc}")
                if exc.details:
                    st.json(exc.details)
                return None
            except Exception as exc:
                logger.exception("Energy simulation failed")
                st.error(f"Error inesperado: {exc}")
                return None

    last = st.session_state.get("sim_last_result")
    if last:
        _render_result(last)
    return last
