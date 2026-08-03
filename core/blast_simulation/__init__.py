"""Phase 2 — deterministic 3D voxel energy engine.

This package implements an engineering-grade, auditable energy model that
transforms the accepted rows of the Fase 1 ``ProcessingResult`` into a
spatial and temporal energy field over a voxelized rock mass.

The results are RELATIVE comparative indicators for analysis and
calibration. They are NOT high-fidelity FEM/DEM/SPH predictions of
fragmentation, damage, PPV or stability. See
``docs/BLAST_ENERGY_SIMULATION_PHASE_2.md`` for the full scientific scope
and limits.

Public API (re-exported here):

    SimulationConfiguration
    SimulationResult
    VoxelEnergyField
    run_simulation

All physics, math and persistence live in :mod:`core.blast_simulation`.
Routers, React and Streamlit are presentation layers — they MUST NOT
reimplement the engine.
"""
from __future__ import annotations

from core.blast_simulation.charges import (
    build_charge_segments,
    classify_segments,
)
from core.blast_simulation.contracts import (
    AnisotropyMode,
    ChargeSegment,
    DomainBounds,
    EnergyMode,
    EnergyPropagationConfiguration,
    GridMetadata,
    KernelType,
    PlanSlice,
    ProcessingSummary,
    RockMassConfiguration,
    SectionSlice,
    SimulationConfiguration,
    SimulationConfigurationError,
    SimulationDiagnostics,
    SimulationProvenance,
    SimulationResult,
    SimulationSourceSummary,
    SIMULATION_CONFIGURATION_VERSION,
    TemporalMode,
    TemporalSimulationConfiguration,
    VoxelEnergyField,
    VoxelGridSpecification,
)
from core.blast_simulation.diagnostics import (
    DEFAULT_BAND_EDGES,
    classify_energy_bands,
    coverage_report,
    statistical_summary,
)
from core.blast_simulation.engine import (
    ENGINE_VERSION,
    export_field_arrays,
    run_simulation,
)
from core.blast_simulation.slicing import (
    attach_slices_to_result,
    compute_slices,
    plan_slice,
    section_slice,
)

__all__ = [
    "SIMULATION_CONFIGURATION_VERSION",
    "ENGINE_VERSION",
    "AnisotropyMode",
    "ChargeSegment",
    "DEFAULT_BAND_EDGES",
    "DomainBounds",
    "EnergyMode",
    "EnergyPropagationConfiguration",
    "GridMetadata",
    "KernelType",
    "PlanSlice",
    "ProcessingSummary",
    "RockMassConfiguration",
    "SectionSlice",
    "SimulationConfiguration",
    "SimulationConfigurationError",
    "SimulationDiagnostics",
    "SimulationProvenance",
    "SimulationResult",
    "SimulationSourceSummary",
    "TemporalMode",
    "TemporalSimulationConfiguration",
    "VoxelEnergyField",
    "VoxelGridSpecification",
    "attach_slices_to_result",
    "build_charge_segments",
    "classify_energy_bands",
    "classify_segments",
    "compute_slices",
    "coverage_report",
    "export_field_arrays",
    "plan_slice",
    "run_simulation",
    "section_slice",
    "statistical_summary",
]
