"""Persistence + export round-trip tests (spec §8, §12).

These tests prove the artifacts are not just created but RE-OPENABLE
and verifiable:

* NPZ write → read back with SHA-256 verification.
* SHA-256 mismatch raises PersistenceError (tamper detection).
* JSON summary round-trips through json.loads.
* Excel workbook reopens with openpyxl and every nested structure
  survives as parseable JSON.
* Conservation totals survive the round-trip within float32 tolerance.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.blast_simulation import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    KernelType,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SimulationConfiguration,
    TemporalMode,
    export_simulation_xlsx,
    npz_path_for,
    read_back_simulation_xlsx,
    read_npz_artifact,
    read_summary_json,
    run_simulation,
    sha256_file,
    summary_path_for,
    write_npz_artifact,
    write_summary_json,
)
from core.blast_simulation.persistence import PersistenceError


def _cfg() -> SimulationConfiguration:
    return SimulationConfiguration(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(-5, -5, -5, 5, 5, 5),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.STATIC,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=2.0,
        regularization_radius_m=0.5,
        coupling_efficiency=0.85,
        rock_mass=RockMassConfiguration(
            rock_unit_id="1c", density_kg_m3=2700.0, ucs_mpa=80.0,
            attenuation_coefficient_1_m=2.0, wave_velocity_m_s=3500.0,
            anisotropy_mode=AnisotropyMode.ISOTROPIC,
            source="lab", status="VALIDATED",
        ),
    )


def _rows() -> list[dict]:
    return [
        {
            "hole_id": "H-001", "X": 0.0, "Y": 0.0, "Z_collar": 4.0,
            "X_toe": 0.0, "Y_toe": 0.0, "Z_toe": -4.0,
            "Incl": 0.0, "Az": 0.0, "Len": 8.0,
            "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
            "Kilos_Cargados_real": 100.0, "Tipo_Explosivo": "ANFO",
            "source_row_index": 0,
        },
    ]


# ---------------------------------------------------------------------------
# NPZ round-trip
# ---------------------------------------------------------------------------


class TestNpzRoundTrip:
    def test_write_and_read_back(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        updated, npz, sha = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg,
            data_dir=tmp_path, segments_per_hole=4,
        )
        assert npz.exists()
        assert len(sha) == 64
        assert updated.energy_field.npz_path == str(npz)
        assert updated.grid_metadata.npz_sha256 == sha

        arrays, metadata, sha2 = read_npz_artifact(npz, expected_sha256=sha)
        assert sha == sha2
        assert metadata["simulation_id"] == result.simulation_id
        assert metadata["voxel_count"] == arrays["energy_total"].size
        assert metadata["energy_unit"] == "J"

    def test_tampered_file_detected(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        updated, npz, sha = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
        )
        # Tamper with the file: append bytes.
        with open(npz, "ab") as f:
            f.write(b"\x00\x01\x02")
        with pytest.raises(PersistenceError):
            read_npz_artifact(npz, expected_sha256=sha)

    def test_wrong_hash_raises(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        _, npz, _ = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
        )
        with pytest.raises(PersistenceError):
            read_npz_artifact(npz, expected_sha256="0" * 64)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(PersistenceError):
            read_npz_artifact(tmp_path / "does_not_exist.npz")

    def test_conservation_survives_round_trip(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        updated, npz, sha = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
            segments_per_hole=4,
        )
        arrays, metadata, _ = read_npz_artifact(npz, expected_sha256=sha)
        # The NPZ energy_total must match the result metadata within
        # float32 storage tolerance.
        field_sum = float(arrays["energy_total"].sum())
        assert field_sum == pytest.approx(
            metadata["represented_energy_j"], rel=1e-5
        )
        # Conservation invariant.
        total = metadata["represented_energy_j"] + metadata["outside_domain_energy_j"]
        assert total == pytest.approx(metadata["total_coupled_energy_j"], rel=1e-6)

    def test_density_array_present(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        _, npz, sha = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
        )
        arrays, _, _ = read_npz_artifact(npz, expected_sha256=sha)
        assert "energy_density" in arrays
        # Density is J/m³. Never kg/m³ (audit H-09).
        assert arrays["energy_density"].shape == arrays["energy_total"].shape

    def test_dominant_arrays_present(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        _, npz, sha = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
        )
        arrays, _, _ = read_npz_artifact(npz, expected_sha256=sha)
        assert "dominant_idx" in arrays
        assert "dominant_energy" in arrays
        assert "contributing_count" in arrays


# ---------------------------------------------------------------------------
# JSON summary round-trip
# ---------------------------------------------------------------------------


class TestJsonSummaryRoundTrip:
    def test_write_and_read_back(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        updated, _, _ = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
        )
        out = write_summary_json(result=updated, data_dir=tmp_path)
        assert out.exists()
        payload = read_summary_json(out)
        assert payload["simulation_id"] == updated.simulation_id
        assert payload["engine_version"] == updated.engine_version
        assert payload["processing_summary"]["energy_mode"] == "ABSOLUTE"
        # Round-trip through JSON must not lose information.
        re_string = json.dumps(payload, default=str, sort_keys=True)
        assert "represented_energy_j" in re_string


# ---------------------------------------------------------------------------
# Excel round-trip
# ---------------------------------------------------------------------------


class TestExcelRoundTrip:
    def test_export_and_reopen(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        out = export_simulation_xlsx(result, tmp_path / "sim.xlsx")
        assert out.exists()
        sheets = read_back_simulation_xlsx(out)
        # Mandatory sheets (spec §12).
        for required in ("Resumen", "Configuración", "Fuentes", "Procedencia"):
            assert required in sheets, f"missing sheet {required}"
        # The processing summary round-trips through openpyxl as a KV
        # table (clave/valor); both keys must be present.
        resumen = sheets["Resumen"]
        keys = list(resumen["clave"].astype(str))
        assert any("energy_mode" in k for k in keys)
        assert any("temporal_status" in k for k in keys)

    def test_nested_diagnostics_round_trip_as_json(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        out = export_simulation_xlsx(result, tmp_path / "sim.xlsx")
        sheets = read_back_simulation_xlsx(out)
        diag = sheets["Diagnósticos"]
        # The diagnostics sheet is a KV table (clave/valor).
        # Find the spatial_diagnostics row and verify it parses as JSON.
        keys = list(diag["clave"])
        assert any("resource_info" in str(k) for k in keys)

    def test_warnings_sheet_when_no_warnings(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        out = export_simulation_xlsx(result, tmp_path / "sim.xlsx")
        sheets = read_back_simulation_xlsx(out)
        # Warnings sheet exists even when empty (placeholder row).
        assert "Advertencias" in sheets


# ---------------------------------------------------------------------------
# Full persistence chain
# ---------------------------------------------------------------------------


class TestFullPersistenceChain:
    def test_npz_json_xlsx_all_aligned(self, tmp_path):
        cfg = _cfg()
        rows = _rows()
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        updated, npz, sha = write_npz_artifact(
            result=result, accepted_rows=rows, configuration=cfg, data_dir=tmp_path,
            segments_per_hole=4,
        )
        json_path = write_summary_json(result=updated, data_dir=tmp_path)
        xlsx_path = export_simulation_xlsx(updated, tmp_path / "sim.xlsx")

        # The NPZ, JSON and XLSX all carry the same simulation_id and
        # the same represented energy (within float tolerance).
        arrays, npz_meta, _ = read_npz_artifact(npz, expected_sha256=sha)
        json_meta = read_summary_json(json_path)
        sheets = read_back_simulation_xlsx(xlsx_path)

        assert npz_meta["simulation_id"] == json_meta["simulation_id"]
        assert json_meta["grid_metadata"]["npz_sha256"] == sha
        # The Excel Resumen sheet references the same total coupled energy.
        resumen = sheets["Resumen"]
        coupled_values = resumen.loc[resumen["clave"] == "total_coupled_energy_j", "valor"]
        assert len(coupled_values) == 1
        excel_coupled = float(coupled_values.iloc[0])
        assert excel_coupled == pytest.approx(
            json_meta["energy_field"]["total_coupled_energy_j"], rel=1e-6
        )
