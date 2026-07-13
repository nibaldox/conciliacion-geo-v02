# Blast Drill Hardness Specification

## Purpose

Fold the standalone `dureza_relativa/` rock-resistance signals into the blast pipeline so engineers correlate per-hole hardness (`dureza`, `indice_dureza`, `tasa_penetracion`, rig-normalized z-score) against PF, stemming, and overbreak in the same 3D view. The drilling CSV uploader is OPTIONAL — the blast workflow MUST keep working when absent or malformed. Closes the gap between geometric deviation (`blast-drill-compliance`, 5 m radius) and rock-strength feedback.

## Requirements

### Requirement: Pure Classification Module

`core/drill_hardness.py` SHALL port the seven parity-critical symbols from `dureza_relativa/classification.py` byte-for-byte: `DEFAULT_DURATION_THRESHOLDS`, `DEFAULT_RATE_THRESHOLDS`, `DEFAULT_THRESHOLDS`, `DURATION_INDEX_UPPER_SATURATION`, `RATE_INDEX_UPPER_SATURATION`, `STD_EPSILON`, `MetricThresholds`, `Thresholds`, `Metric`, `classify_duracion`, `hardness_index`, `penetration_rate`, `classify_with_metric`, `hardness_index_with_metric`, `rig_mean_penetration`, `rig_normalized_penetration`. The module SHALL NOT import `pandas`, `numpy`, `streamlit`, `plotly`, or `logging`; only `typing` + `math` are permitted.

#### Scenario: Numerical parity with source

- GIVEN the parity fixture cases from `dureza_relativa/tests`
- WHEN each ported function runs with the same inputs
- THEN the outputs match the source values to float64 precision

#### Scenario: Classify with strict `<` boundaries (duration)

- GIVEN `value=16.0` and `DEFAULT_THRESHOLDS`
- WHEN `classify_with_metric(16.0, DEFAULT_THRESHOLDS, "duration")` runs
- THEN it returns `"roca media"` (exact cutoff falls into harder bucket)

#### Scenario: Rate metric returns 0.0 above upper saturation

- GIVEN `value=2.5` and `DEFAULT_THRESHOLDS`
- WHEN `hardness_index_with_metric(2.5, DEFAULT_THRESHOLDS, "penetration_rate")` runs
- THEN it returns `0.0` (above `RATE_INDEX_UPPER_SATURATION=2.0`)

#### Scenario: Zero-variance rig returns z-score 0.0

- GIVEN `rig_std <= STD_EPSILON`
- WHEN `rig_normalized_penetration(0.8, rig_avg=1.0, rig_std=1e-12)` runs
- THEN it returns `0.0` and SHALL NOT raise `ZeroDivisionError`

### Requirement: Processor Module

`core/drill_hardness_processor.py` SHALL expose `load_drilling_csv(path) -> pd.DataFrame`, `compute_hardness_metrics(df) -> pd.DataFrame`, and `join_hardness_to_blast(blast_df, hardness_df, *, radius_m=2.0) -> pd.DataFrame`. The processor SHALL NOT be re-exported from `core/__init__.py`; callers import from `core.drill_hardness_processor`.

#### Scenario: Load drilling CSV with column normalization

- GIVEN a CSV with columns `["Pozo", "Tiempo Inicial", "Tiempo Final", "Prof. por Operador", "Coord. Norte [m]", "Coord. Este [m]", "Equipo"]`
- WHEN `load_drilling_csv(path)` runs
- THEN the returned DataFrame has canonical columns `pozo`, `tiempo_inicial`, `tiempo_final`, `profundidad_m`, `x`, `y`, `rig`, `duracion_min` computed as `tiempo_final - tiempo_inicial`

#### Scenario: Reperforados collapse by last event

- GIVEN three rows for `Pozo="H-1"` with `Tiempo Final` 10:00, 10:45, 11:30
- WHEN `compute_hardness_metrics(df)` runs
- THEN only the 11:30 row survives for `H-1` (collapse via `df.loc[df.groupby("pozo")["tiempo_final"].idxmax()]`) and `tasa_penetracion`, `dureza`, `indice_dureza` are computed on that row only

### Requirement: Hardness Metrics Computation

`compute_hardness_metrics(df)` SHALL add per-row columns: `duracion_min` (float, minutes), `tasa_penetracion` (float m/min or NaN), `dureza` (one of `roca suave|roca media|roca dura|roca muy dura`), `indice_dureza` (float in `[0, 100]`), `rig_avg_rate`, `rig_std_rate`, `rig_zscore`. Classification SHALL use `classify_with_metric` against `DEFAULT_THRESHOLDS` on the `duracion_min` metric when `profundidad_m` is missing or non-finite, and on `tasa_penetracion` otherwise.

#### Scenario: Missing depth → duration-only classification

- GIVEN a row with `profundidad_m` absent (NaN)
- WHEN `compute_hardness_metrics(df)` runs
- THEN `tasa_penetracion` is NaN, `dureza` and `indice_dureza` are computed via `classify_with_metric` / `hardness_index_with_metric` on `duracion_min` using `DEFAULT_THRESHOLDS["duration"]`

#### Scenario: Rig z-score collapses zero-variance rigs

- GIVEN a single hole under rig `"R-1"`
- WHEN `compute_hardness_metrics(df)` runs
- THEN `rig_zscore == 0.0` (single-sample rig has `rig_std <= STD_EPSILON`)

### Requirement: Spatial Join to Blast DataFrame

`join_hardness_to_blast(blast_df, hardness_df, *, radius_m=2.0)` SHALL use `scipy.spatial.cKDTree` on `(x, y)` to match each blast hole to the nearest drilling event within `radius_m`. Hardness columns (`dureza`, `indice_dureza`, `tasa_penetracion`, `rig_zscore`, `rig`) SHALL be added via `merge(..., how="left", on="pozo")` ONLY for matched holes; unmatched blast holes SHALL keep all original columns and receive NaN hardness fields. Holes beyond `radius_m` SHALL be reported as `unmatched_blast_holes` in the result metadata, NEVER silently mis-attributed.

#### Scenario: Default 2 m radius

- GIVEN a blast hole at (100.0, 200.0) and a drilling event at (100.5, 200.3)
- WHEN `join_hardness_to_blast(blast_df, hardness_df)` runs (default `radius_m=2.0`)
- THEN the blast hole inherits the drilling event's hardness fields

#### Scenario: Hole beyond radius stays unmatched

- GIVEN a blast hole at (100.0, 200.0) and the nearest drilling event at (105.0, 200.0) (5 m away)
- WHEN the join runs
- THEN the blast row survives with NaN hardness columns and is recorded in `unmatched_blast_holes`

#### Scenario: Configurable radius

- GIVEN the same pair 5 m apart and `radius_m=6.0`
- WHEN the join runs
- THEN the pair matches

### Requirement: Optional Uploader — Graceful Degradation

`core/drill_hardness_processor.load_drilling_csv(path)` SHALL return an empty DataFrame (with the canonical schema) when the file is missing, empty, or unreadable, instead of raising. `join_hardness_to_blast` SHALL accept an empty `hardness_df` and return `blast_df` unchanged. The blast pipeline SHALL detect absence via `len(hardness_df) == 0` and skip the join; no exceptions propagate to the Streamlit or API layers.

#### Scenario: Empty CSV

- GIVEN a 0-row CSV with the canonical header
- WHEN `load_drilling_csv(path)` runs
- THEN it returns an empty DataFrame with the canonical schema, not an error

#### Scenario: Missing required columns

- GIVEN a CSV with no `Pozo` column
- WHEN `load_drilling_csv(path)` runs
- THEN it returns an empty DataFrame and the blast pipeline continues without enrichment

#### Scenario: No matching drilling events

- GIVEN a blast DataFrame with 50 holes and a `hardness_df` whose `(x, y)` points are all > 2 m from any blast collar
- WHEN the join runs
- THEN all 50 blast rows survive with NaN hardness fields; no rows are dropped

### Requirement: Required Hardness Columns

`DrillHardnessResult` columns SHALL include at minimum: `pozo`, `x`, `y`, `rig`, `duracion_min`, `tasa_penetracion`, `dureza`, `indice_dureza`, `rig_avg_rate`, `rig_std_rate`, `rig_zscore`. All columns MUST use snake_case; Pozo IDs SHALL round-trip through the join unchanged.

#### Scenario: Schema round-trip

- GIVEN a drill event with `Pozo="H-1"` and `Tiempo Final` 11:30
- WHEN the full pipeline runs
- THEN the joined blast row carries `pozo="H-1"` and `tasa_penetracion` matches the float64 value from `penetration_rate`

### Requirement: Configuration Defaults

`core/config.py` SHALL expose a frozen `DrillHardnessDefaults` dataclass with a module-level singleton `DRILL_HARDNESS`:

| Field | Default | Unit |
|---|---|---|
| `radius_m` | 2.0 | m |
| `radius_min_m` | 0.5 | m |
| `radius_max_m` | 10.0 | m |
| `duration_soft_min` | 16.0 | min |
| `duration_medium_min` | 24.0 | min |
| `duration_hard_min` | 40.0 | min |
| `index_upper_saturation_min` | 60.0 | min |
| `std_epsilon` | 1e-9 | — |
| `strict_parity` | `True` | bool |

`DRILL_HARDNESS` SHALL NOT be re-exported from `core/__init__.py`. Callers import as `from core.config import DRILL_HARDNESS`.

#### Scenario: Singleton is importable from core.config

- GIVEN the implementation lands
- WHEN `from core.config import DRILL_HARDNESS` runs
- THEN the singleton is available with `DRILL_HARDNESS.radius_m == 2.0`

### Requirement: Legacy Surface Unchanged

`core/drill_compliance`, `core.calculo_tronadura.procesar_pozos`, the `blast-drill-compliance` join (5 m radius), every symbol re-exported by `core/__init__.py`, and the Streamlit blast module SHALL remain unchanged in behaviour. The new `drill_hardness` and `drill_hardness_processor` modules are additive. `core/__init__.py` SHALL stay byte-identical (no new re-exports).

#### Scenario: No edits to core/__init__.py

- GIVEN the implementation lands
- WHEN `git diff main...HEAD -- core/__init__.py` runs
- THEN the diff is empty

#### Scenario: Old drill compliance still works

- GIVEN `compute_drill_compliance(design_df, actual_df, match_by="label")` returning its existing shape
- WHEN the hardness integration lands
- THEN return shape, tolerances, and fields are unchanged

#### Scenario: Existing blast workflow runs when CSV absent

- GIVEN a Streamlit session with no drilling file uploaded
- WHEN the user runs the existing blast pipeline
- THEN the pipeline produces the same output as before; no `KeyError`, no traceback, no new mandatory widget

### Requirement: Test Surface

`tests/test_drill_hardness.py` SHALL cover, at minimum: 4 parity cases for `classify_with_metric` / `hardness_index_with_metric` against the source `classification.py` outputs, 2 cases each for `rig_mean_penetration` / `rig_normalized_penetration` (zero-variance, finite), 3 cases for `compute_hardness_metrics` (missing depth, reperforado collapse, rig z-score), 3 cases for `join_hardness_to_blast` (within radius, beyond radius, empty `hardness_df`), and 2 cases for `load_drilling_csv` (missing columns, empty file). All tests SHALL run under `pytest tests/test_drill_hardness.py -v` with `pythonpath="."`.

#### Scenario: Parity test against source

- GIVEN the canonical fixture `inputs=(depth, duration) → expected_rate`
- WHEN `penetration_rate(depth, duration)` runs in the new module
- THEN it returns the same float64 as the source classification module

## Legacy API Compatibility

This change is additive. `core/__init__.py` re-exports stay intact. New modules are `core/drill_hardness.py` and `core/drill_hardness_processor.py`. The `DrillHardnessDefaults` frozen dataclass adds to `core/config.py` without replacing existing singletons. The Streamlit blast module gains ONE optional `st.file_uploader` and ONE color selector only when `drill_hardness_file` is provided; absent → app renders identically to pre-change.
