# Blast Drill Compliance Specification

## Purpose

Compute per-hole deviation between a planned blast design and the as-drilled report. Surfaces collar offset, inclination error, azimuth drift, length, and charge deviation BEFORE topo confirms overbreak. Consumes the canonical columns produced by `core.calculo_tronadura.procesar_pozos` so a single source of truth feeds downstream correlation.

## Requirements

### Requirement: Per-Hole Deviation

`compute_drill_compliance(design_df, actual_df)` SHALL produce one row per matched pair with signed deviations: `delta_x`, `delta_y`, `delta_z_collar` (metres), `delta_incl`, `delta_az` (degrees), `delta_len` (metres), `delta_kg_pct` = `abs(kg_actual - kg_design) / max(kg_design, 1) * 100`.

#### Scenario: Matched by label
- GIVEN design and actual rows sharing `Pozo="H-1"`
- WHEN `compute_drill_compliance(design_df, actual_df, match_by="label")` runs
- THEN `per_hole` has one row with the seven Δ fields populated and `match_method="label"`

#### Scenario: Unmatched label dropped
- GIVEN an actual row whose `Pozo` has no design counterpart
- WHEN matching runs
- THEN the row is dropped from `per_hole` and appended to `unmatched["actual"]`

### Requirement: Match Strategy

The system SHALL support `match_by ∈ {"label", "nearest"}`. The `"nearest"` strategy SHALL use `scipy.spatial.cKDTree` on (X, Y) within `nearest_radius_m` (default 5.0 m). When `match_by="label"` is requested but the design lacks a `Pozo` column, the system SHALL warn and fall back to `match_by="nearest"`.

#### Scenario: Nearest fallback within radius
- GIVEN actual at (100, 200) and a design point at (101, 199)
- WHEN `match_by="nearest"` runs
- THEN the pair is matched and tagged `match_method="nearest"`

#### Scenario: Nearest beyond radius
- GIVEN the closest design point is > 5 m from the actual collar
- WHEN matching runs
- THEN the actual row is reported as `unmatched`; the system SHALL NEVER silently mis-pair

#### Scenario: Auto-fallback when design lacks label column
- GIVEN design_df has no `Pozo` column
- WHEN `match_by="label"` is requested
- THEN the system emits a warning and proceeds with `match_by="nearest"`

### Requirement: Group Aggregation

When `group_by` is provided (e.g. `"malla"` or `"sector"`), `per_group` SHALL list each group with `n`, `mean_abs` per dimension, and `within_tol_pct` per dimension.

#### Scenario: Group by malla
- GIVEN 30 matched holes tagged `malla ∈ {M-1, M-2}`
- WHEN `group_by="malla"` is requested
- THEN `per_group` has two rows, each with seven `mean_abs` and seven `within_tol_pct` values

### Requirement: Compliance Score

`compliance_score` SHALL equal the mean across the seven dimensions of `(abs(Δ) <= tol).mean()`. Range `[0.0, 1.0]`; `None` on empty input.

#### Scenario: All in tolerance
- GIVEN every matched hole satisfies all seven tolerances
- WHEN the score is computed
- THEN `compliance_score == 1.0`

#### Scenario: Mixed compliance
- GIVEN per-dim pass rates 80%, 60%, ...
- WHEN the score is computed
- THEN `compliance_score` is the mean of those seven rates

### Requirement: Tolerances

The system SHALL expose a frozen `DrillComplianceDefaults` dataclass in `core/config.py` with a module-level singleton `DRILL_COMPLIANCE`:

| Field | Default | Unit |
|---|---|---|
| `delta_x_m` | 0.5 | m |
| `delta_y_m` | 0.5 | m |
| `delta_z_m` | 0.3 | m |
| `delta_incl_deg` | 3.0 | deg |
| `delta_az_deg` | 5.0 | deg |
| `delta_len_m` | 0.5 | m |
| `delta_kg_pct` | 10.0 | % |
| `nearest_radius_m` | 5.0 | m |

Callers MAY pass a custom dataclass instance via `tolerances=` to override any field.

#### Scenario: Override tolerance
- GIVEN `tolerances=DrillComplianceDefaults(delta_x_m=1.0)`
- WHEN `compute_drill_compliance(...)` runs
- THEN `within_tol_pct` for ΔX uses 1.0 m; ΔY, ΔZ, etc. use defaults

### Requirement: Graceful Empty Inputs

The system SHALL return an empty result (never raise) when `design_df` is `None` or empty, when `actual_df` is `None` or empty, when no matches exist, or when required columns (X, Y) are missing from one side. Empty results SHALL populate `per_hole = []`, `aggregates = {}`, `compliance_score = None`, `per_group = None`, `unmatched = {"design": [], "actual": []}`, `warnings = [...]`.

#### Scenario: No design file
- GIVEN `design_df=None`
- WHEN the function is called
- THEN it returns an empty result dict, emits one info-level warning, and does not raise

#### Scenario: No actual rows
- GIVEN `actual_df` is empty but a valid design exists
- WHEN the function is called
- THEN it returns an empty result dict; no exception

#### Scenario: Missing X/Y on design
- GIVEN `design_df` has no X and Y columns
- WHEN the function is called
- THEN it returns an empty result with warning `"spatial matching impossible"`

### Requirement: Legacy Blast Processing Unchanged

The system SHALL NOT modify the public surface of `core.calculo_tronadura.procesar_pozos`, `proyectar_pozos_en_seccion`, or any symbol re-exported by `core/__init__.py`. The new module SHALL be imported as `core.drill_compliance` (NOT re-exported from `core/__init__.py`).

#### Scenario: Existing tuple signature
- GIVEN `procesar_pozos(df)` returns `(df_clean, x_lines, y_lines, z_lines)`
- WHEN drill compliance is added
- THEN that signature and every output column remain unchanged

## Legacy API Compatibility

This change is additive. `core/__init__.py` re-exports stay intact. Only addition in `core/config.py`: `DrillComplianceDefaults` dataclass + `DRILL_COMPLIANCE` singleton (opt-in for callers).

## Result Contract

Function signature:

```python
def compute_drill_compliance(
    design_df: pd.DataFrame | None,
    actual_df: pd.DataFrame,
    match_by: Literal["label", "nearest"] = "label",
    tolerances: DrillComplianceDefaults | None = None,
    group_by: str | None = None,
) -> DrillComplianceResult: ...
```

Return shape (per proposal):

```python
{
    "per_hole":          pd.DataFrame,         # one row per matched pair
    "aggregates":        dict[str, float],     # global mean|Δ| per dim
    "compliance_score":  float | None,         # 0.0..1.0; None on empty
    "per_group":         pd.DataFrame | None,  # present when group_by given
    "unmatched":         {"design": [...], "actual": [...]},
    "warnings":          list[str],            # human-readable caveats
}
```

Implementation MAY use a frozen dataclass (`DrillComplianceResult`) for type safety; the contract above is the shape, not the wire format.