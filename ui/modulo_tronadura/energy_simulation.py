"""Energy simulation adapter — Streamlit presentation layer only.

This module is the documented H-10 exception: ``ui/modulo_tronadura/``
may host presentation/adapters but NO domain logic. Every formula lives
in :mod:`core.blast_simulation`; this file only:

* collects operator decisions via Streamlit widgets (every physical
  selector starts empty — no silent defaults);
* builds the canonical :class:`SimulationConfiguration`;
* validates it (raising structured errors the UI renders);
* invokes ``run_simulation`` on a worker thread;
* renders the canonical result with Plotly tables and the uncalibrated-
  model warning.

Confirmation invalidates by SHA-256 fingerprint exactly like the Fase 1
``upload.py`` geometry contract — any edit clears the checkbox unless
the edit IS the checkbox.
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from core.blast_simulation import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    KernelType,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SimulationConfiguration,
    SimulationConfigurationError,
    TemporalMode,
    export_simulation_xlsx,
    run_simulation,
    write_npz_artifact,
    write_summary_json,
)
from core.config import SIMULATION as SIM_DEFAULTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fingerprint + validation
# ---------------------------------------------------------------------------


def simulation_fingerprint(state: dict[str, Any]) -> str:
    """Stable SHA-256 over the operator-selected simulation parameters."""
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_config(state: dict[str, Any], geom_version: str) -> SimulationConfiguration:
    rock = RockMassConfiguration(
        rock_unit_id=state.get("rock_unit_id", ""),
        density_kg_m3=state.get("rock_density_kg_m3"),
        ucs_mpa=state.get("rock_ucs_mpa"),
        attenuation_coefficient_1_m=state.get("rock_attenuation"),
        wave_velocity_m_s=state.get("rock_velocity"),
        anisotropy_mode=state.get("anisotropy_mode", AnisotropyMode.ISOTROPIC),
        anisotropy_tensor=state.get("anisotropy_tensor"),
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
        anisotropy_mode=state["anisotropy_mode"],
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
    state = {
        "voxel_size_m": voxel_size,
        "x_min": x_min, "x_max": x_max,
        "y_min": y_min, "y_max": y_max,
        "z_min": z_min, "z_max": z_max,
        "energy_mode": energy_mode,
        "temporal_mode": temporal_mode,
        "anisotropy_mode": anisotropy_mode,
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
        and x_max > x_min and y_max > y_min and z_max > z_min
        and energy_mode and temporal_mode and anisotropy_mode
        and attenuation is not None and attenuation >= 0
        and regularization and regularization > 0
        and coupling is not None and 0.0 <= coupling <= 1.0
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
                # Persist artifacts.
                result, _, sha = write_npz_artifact(
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
        _render_summary(last)
    return last


def _render_summary(result_dict: dict[str, Any]) -> None:
    """Render the canonical result. No re-engineering of the engine."""
    ef = result_dict["energy_field"]
    summary = result_dict["processing_summary"]
    unit = result_dict["grid_metadata"]["energy_unit"]
    st.markdown("**Resumen de la simulación**")
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Energía representada", f"{ef['represented_energy_j']:.2e} {unit}")
    sc2.metric("Energía fuera del dominio", f"{ef['outside_domain_energy_j']:.2e} {unit}")
    sc3.metric("Fracción representada", f"{ef['fraction_represented'] * 100:.1f} %")
    sc4.metric("Vóxeles activos", f"{ef['active_voxels']} / {result_dict['grid_metadata']['voxel_count']}")

    if result_dict["blocking_errors"]:
        st.markdown("**Errores bloqueantes**")
        st.json(list(result_dict["blocking_errors"]))

    src = result_dict["source_summary"]
    df_summary = pd.DataFrame([
        {"Métrica": "Fuentes válidas", "Valor": src["valid_sources"]},
        {"Métrica": "Fuentes inválidas", "Valor": src["invalid_sources"]},
        {"Métrica": "Segmentos de carga", "Valor": src["charge_segments"]},
        {"Métrica": "Pozos aceptados", "Valor": src["accepted_holes"]},
        {"Métrica": "Estado temporal", "Valor": summary["temporal_status"]},
        {"Métrica": "Modo de energía", "Valor": summary["energy_mode"]},
    ])
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

    with st.expander("Procedencia"):
        st.json(result_dict["provenance"])
