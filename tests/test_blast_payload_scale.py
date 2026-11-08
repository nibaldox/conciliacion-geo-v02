import json
import math
import tracemalloc
from datetime import date, datetime

import numpy as np
import pandas as pd

from core.calculo_tronadura import _collect_spatial_diagnostics, _df_to_accepted_records
from core.processing_result import ProcessingResult


def _iterrows_accepted_records_reference(frame):
    from core.calculo_tronadura import _EVENT_LEVEL_RECORD_COLUMNS

    columns = [col for col in frame.columns if col not in _EVENT_LEVEL_RECORD_COLUMNS]
    carga = pd.to_numeric(frame["kg_per_meter"], errors="coerce")
    descarga = pd.to_numeric(frame["altura_carga_m"], errors="coerce")
    records = []
    for idx, row in frame[columns].iterrows():
        record = {}
        for col in columns:
            value = row[col]
            if value is pd.NaT or value is pd.NA:
                value = None
            elif isinstance(value, (date, datetime, np.datetime64)):
                if pd.isna(value):
                    value = None
                elif isinstance(value, np.datetime64):
                    value = pd.Timestamp(value).isoformat()
                else:
                    value = value.isoformat()
            elif isinstance(value, np.bool_):
                value = bool(value)
            elif isinstance(value, np.integer):
                value = int(value)
            elif isinstance(value, np.floating):
                number = float(value)
                value = number if math.isfinite(number) else None
            elif isinstance(value, float):
                value = value if math.isfinite(value) else None
            record[col] = value
        load = carga.loc[idx] if idx in carga.index else float("nan")
        height = descarga.loc[idx] if idx in descarga.index else float("nan")
        record["carga"] = float(load) if pd.notna(load) else None
        record["descarga"] = float(height) if pd.notna(height) else None
        record["source_row_index"] = int(idx) if isinstance(idx, (np.integer, int)) else str(idx)
        record["row_processing_status"] = "accepted"
        records.append(record)
    return records


def test_accepted_records_matches_iterrows_for_mixed_values_and_indices():
    frame = pd.DataFrame({
        "npy_int": pd.Series([np.int64(3), np.int64(4)], dtype="int64"),
        "npy_float": pd.Series([np.float64(2.5), np.float64(np.inf)], dtype="float64"),
        "npy_bool": pd.Series([np.bool_(True), np.bool_(False)], dtype="bool"),
        "date": [date(2026, 1, 2), None],
        "datetime": [datetime(2026, 1, 2, 3, 4), pd.NaT],
        "timestamp": pd.to_datetime(["2026-01-02T03:04:05", None]),
        "missing": pd.Series([pd.NA, "ok"], dtype="object"),
        "kg_per_meter": [4.0, np.nan],
        "altura_carga_m": [7.0, 0.0],
    }, index=pd.Index([np.int64(17), "row-X"], dtype="object"))

    expected = _iterrows_accepted_records_reference(frame)
    actual = _df_to_accepted_records(frame)

    assert actual == expected
    assert actual[0]["source_row_index"] == 17
    assert actual[1]["source_row_index"] == "row-X"


def test_accepted_records_scale_without_repeating_event_summaries():
    row_count = 20_939
    rejected_ids = ",".join(f"BAD-{index}" for index in range(2_469))
    rejected_reasons = " | ".join(f"fila {index}: coordenada inválida" for index in range(2_469))
    outside_ids = "|".join(f"OUT-{index}" for index in range(2_469))
    frame = pd.DataFrame({
        "X": np.arange(row_count, dtype=float),
        "Y": np.arange(row_count, dtype=float),
        "Z_collar": np.full(row_count, 100.0),
        "Incl": np.full(row_count, 15.0),
        "Az": np.full(row_count, 90.0),
        "Len": np.full(row_count, 12.0),
        "hole_id": [f"H-{index}" for index in range(row_count)],
        "processing_rows_received": np.full(row_count, row_count),
        "processing_rows_accepted": np.full(row_count, row_count),
        "processing_rows_rejected": np.zeros(row_count, dtype=int),
        "processing_rejected_ids": [rejected_ids] * row_count,
        "processing_rejected_reasons": [rejected_reasons] * row_count,
        "voronoi_method": ["global_bbox"] * row_count,
        "voronoi_validation_messages": [[]] * row_count,
        "assigned_area_m2": np.full(row_count, 123.0),
        "area_residual_m2": np.full(row_count, 0.0),
        "area_residual_pct": np.full(row_count, 0.0),
        "voronoi_conservation_ok": np.ones(row_count, dtype=bool),
        "outside_domain_hole_count": np.full(row_count, 2_469),
        "outside_domain_hole_ids": [outside_ids] * row_count,
        "outside_domain_assigned_area_m2": np.full(row_count, 0.0),
        "invalid_coordinate_hole_count": np.zeros(row_count, dtype=int),
    })

    tracemalloc.start()
    records = _df_to_accepted_records(frame)
    serialized_size = len(json.dumps(records, separators=(",", ":")).encode("utf-8"))
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(records) == row_count
    assert records[0]["hole_id"] == "H-0"
    assert records[-1]["source_row_index"] == row_count - 1
    assert not set(frame.columns).intersection(records[0]) & {
        "processing_rows_received",
        "processing_rows_accepted",
        "processing_rows_rejected",
        "processing_rejected_ids",
        "processing_rejected_reasons",
        "voronoi_method",
        "voronoi_validation_messages",
        "assigned_area_m2",
        "area_residual_m2",
        "area_residual_pct",
        "voronoi_conservation_ok",
        "outside_domain_hole_count",
        "outside_domain_hole_ids",
        "outside_domain_assigned_area_m2",
        "invalid_coordinate_hole_count",
    }
    assert serialized_size < 10_000_000
    assert peak_bytes < 128 * 1024 * 1024

    diagnostics = _collect_spatial_diagnostics(frame)
    assert diagnostics["outside_domain_hole_count"] == 2_469
    assert diagnostics["outside_domain_hole_ids"] == outside_ids
    assert diagnostics["voronoi_method"] == "global_bbox"

    result = ProcessingResult.from_rejections(
        accepted_dataframe=frame,
        accepted_rows=records,
        rejected_rows=[],
        event_warnings=[],
        spatial_diagnostics=diagnostics,
        geometry_configuration={},
        rows_received=row_count,
        scatter_lines=((), (), ()),
    )
    assert result.processing_summary()["legacy_rejection_summary"] == {
        "processing_rejected_ids": rejected_ids,
        "processing_rejected_reasons": rejected_reasons,
    }
