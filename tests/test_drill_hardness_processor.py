"""Tests for core.drill_hardness_processor."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.config import DRILL_HARDNESS
from core.drill_hardness_processor import (
    enrich_blast_with_hardness,
    load_drilling_csv,
)


def _write_csv(tmp_path: Path, content: str, name: str = "drill.csv") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_drilling_csv_column_normalization(tmp_path: Path):
    csv = """Pozo,Tiempo Inicial,Tiempo Final,Prof. por Operador,Coord. Norte [m],Coord. Este [m],Equipo
H-1,2026-07-10 08:00,2026-07-10 08:20,17.0,2000.0,1000.0,R-1
H-2,2026-07-10 08:05,2026-07-10 08:45,28.0,2050.0,1010.0,R-2
"""
    path = _write_csv(tmp_path, csv)
    df = load_drilling_csv(str(path))
    assert not df.empty
    assert "pozo" in df.columns
    assert "x" in df.columns
    assert "y" in df.columns
    assert "profundidad_m" in df.columns
    assert "rig" in df.columns
    assert df["duracion_min"].iloc[0] == pytest.approx(20.0)
    assert df["tasa_penetracion"].iloc[0] == pytest.approx(17.0 / 20.0)
    assert df["dureza"].iloc[0] == "roca media"


def test_load_drilling_csv_reperforado_collapse_keeps_last_event(tmp_path: Path):
    csv = """Pozo,Tiempo Inicial,Tiempo Final,Prof. por Operador,Coord. Norte [m],Coord. Este [m],Equipo
H-1,2026-07-10 08:00,2026-07-10 08:10,10.0,2000.0,1000.0,R-1
H-1,2026-07-10 09:00,2026-07-10 09:45,15.0,2000.0,1000.0,R-1
H-1,2026-07-10 10:30,2026-07-10 11:30,18.0,2000.0,1000.0,R-1
"""
    path = _write_csv(tmp_path, csv)
    df = load_drilling_csv(str(path))
    assert len(df) == 1
    assert df["duracion_min"].iloc[0] == pytest.approx(60.0)
    assert df["profundidad_m"].iloc[0] == pytest.approx(18.0)
    assert df["tasa_penetracion"].iloc[0] == pytest.approx(0.3)


def test_load_drilling_csv_missing_pozo_column_returns_empty(tmp_path: Path):
    csv = """Tiempo Inicial,Tiempo Final,Coord. Norte [m],Coord. Este [m]
2026-07-10 08:00,2026-07-10 08:20,2000.0,1000.0
"""
    path = _write_csv(tmp_path, csv)
    df = load_drilling_csv(str(path))
    assert df.empty
    assert "pozo" in df.columns


def test_load_drilling_csv_nonexistent_file_returns_empty(tmp_path: Path):
    df = load_drilling_csv(str(tmp_path / "does_not_exist.csv"))
    assert df.empty


def test_load_drilling_csv_missing_depth_classifies_by_duration(tmp_path: Path):
    csv = """Pozo,Tiempo Inicial,Tiempo Final,Coord. Norte [m],Coord. Este [m],Equipo
H-1,2026-07-10 08:00,2026-07-10 09:00,2000.0,1000.0,R-1
"""
    path = _write_csv(tmp_path, csv)
    df = load_drilling_csv(str(path))
    assert df["tasa_penetracion"].isna().all()
    assert df["dureza"].iloc[0] == "roca muy dura"
    assert df["indice_dureza"].iloc[0] == pytest.approx(100.0)


def test_load_drilling_csv_bad_lines_do_not_crash(tmp_path: Path):
    csv = """Pozo,Tiempo Inicial,Tiempo Final,Prof. por Operador,Coord. Norte [m],Coord. Este [m],Equipo
H-1,2026-07-10 08:00,2026-07-10 08:20,17.0,2000.0,1000.0,R-1
THIS_IS,GARBAGE,LINE,WITH,NO,COMMAS,AT,ALL
H-2,2026-07-10 08:05,2026-07-10 08:25,18.0,2050.0,1010.0,R-1
"""
    path = _write_csv(tmp_path, csv)
    df = load_drilling_csv(str(path))
    assert not df.empty


def test_enrich_blast_with_hardness_within_radius():
    blast = pd.DataFrame({
        "X": [100.0, 200.0],
        "Y": [200.0, 300.0],
    })
    drill = pd.DataFrame({
        "pozo": ["H-1", "H-2"],
        "x": [100.5, 200.3],
        "y": [200.3, 300.0],
        "duracion_min": [15.0, 25.0],
        "tasa_penetracion": [1.2, 0.6],
        "dureza": ["roca suave", "roca dura"],
        "indice_dureza": [10.0, 70.0],
        "rig": ["R-1", "R-2"],
        "rig_zscore": [0.0, 0.0],
    })
    out = enrich_blast_with_hardness(blast, drill, radius=2.0)
    assert out["dureza"].iloc[0] == "roca suave"
    assert out["dureza"].iloc[1] == "roca dura"
    assert out["indice_dureza"].iloc[0] == pytest.approx(10.0)
    assert out["distancia_pozo_perf_m"].iloc[0] < 2.0


def test_enrich_blast_with_hardness_beyond_radius_nan():
    blast = pd.DataFrame({
        "X": [100.0, 200.0],
        "Y": [200.0, 300.0],
    })
    drill = pd.DataFrame({
        "pozo": ["H-far", "H-2"],
        "x": [105.0, 200.3],
        "y": [200.0, 300.0],
        "duracion_min": [15.0, 25.0],
        "tasa_penetracion": [1.2, 0.6],
        "dureza": ["roca suave", "roca dura"],
        "indice_dureza": [10.0, 70.0],
        "rig": ["R-1", "R-2"],
        "rig_zscore": [0.0, 0.0],
    })
    out = enrich_blast_with_hardness(blast, drill, radius=2.0)
    assert pd.isna(out["dureza"].iloc[0])
    assert out["dureza"].iloc[1] == "roca dura"


def test_enrich_blast_with_hardness_configurable_radius():
    blast = pd.DataFrame({"X": [100.0], "Y": [200.0]})
    drill = pd.DataFrame({
        "pozo": ["H-1"],
        "x": [105.0],
        "y": [200.0],
        "duracion_min": [25.0],
        "tasa_penetracion": [0.6],
        "dureza": ["roca dura"],
        "indice_dureza": [70.0],
        "rig": ["R-1"],
        "rig_zscore": [0.0],
    })
    out2 = enrich_blast_with_hardness(blast, drill, radius=2.0)
    out6 = enrich_blast_with_hardness(blast, drill, radius=6.0)
    assert pd.isna(out2["dureza"].iloc[0])
    assert out6["dureza"].iloc[0] == "roca dura"


def test_enrich_blast_with_hardness_empty_drilling_returns_blast_with_nan():
    blast = pd.DataFrame({"X": [100.0], "Y": [200.0]})
    drill = pd.DataFrame(columns=[
        "pozo", "x", "y", "duracion_min", "tasa_penetracion",
        "dureza", "indice_dureza", "rig", "rig_zscore",
    ])
    out = enrich_blast_with_hardness(blast, drill)
    assert len(out) == 1
    assert out["dureza"].isna().all()
    assert "dureza" in out.columns


def test_enrich_blast_with_hardness_empty_blast_passthrough():
    drill = pd.DataFrame({
        "pozo": ["H-1"],
        "x": [100.0],
        "y": [200.0],
        "dureza": ["roca media"],
    })
    blast = pd.DataFrame({"X": [], "Y": []})
    out = enrich_blast_with_hardness(blast, drill)
    assert out.empty
    assert "dureza" in out.columns


def test_enrich_blast_with_hardness_alt_xy_column_names():
    blast = pd.DataFrame({"Este": [100.0], "Norte": [200.0]})
    drill = pd.DataFrame({
        "pozo": ["H-1"],
        "x": [100.5],
        "y": [200.5],
        "duracion_min": [15.0],
        "tasa_penetracion": [1.2],
        "dureza": ["roca suave"],
        "indice_dureza": [10.0],
        "rig": ["R-1"],
        "rig_zscore": [0.0],
    })
    out = enrich_blast_with_hardness(blast, drill, radius=2.0)
    assert out["dureza"].iloc[0] == "roca suave"


def test_enrich_default_radius_uses_config():
    assert DRILL_HARDNESS.radius_m == 2.0
    blast = pd.DataFrame({"X": [100.0], "Y": [200.0]})
    drill = pd.DataFrame({
        "pozo": ["H-1"],
        "x": [101.0],
        "y": [200.0],
        "duracion_min": [15.0],
        "tasa_penetracion": [1.2],
        "dureza": ["roca suave"],
        "indice_dureza": [10.0],
        "rig": ["R-1"],
        "rig_zscore": [0.0],
    })
    out = enrich_blast_with_hardness(blast, drill)
    assert out["dureza"].iloc[0] == "roca suave"


def test_load_drilling_csv_rig_zscore_zero_variance():
    csv = """Pozo,Tiempo Inicial,Tiempo Final,Prof. por Operador,Coord. Norte [m],Coord. Este [m],Equipo
H-1,2026-07-10 08:00,2026-07-10 08:20,17.0,2000.0,1000.0,R-1
"""
    path = _write_csv(Path("/tmp"), csv)
    df = load_drilling_csv(str(path))
    assert df["rig_zscore"].iloc[0] == 0.0
    Path("/tmp").joinpath(path.name).unlink(missing_ok=True)
