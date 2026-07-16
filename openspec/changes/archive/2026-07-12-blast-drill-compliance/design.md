# Design: blast-drill-compliance

## Technical Approach

Pure-Python compliance checker (`core/drill_compliance.py`) joining a planned blast design CSV with the as-built frame from `procesar_pozos`, computing per-hole deltas and a compliance score. Optional second uploader into `ui/modulo_tronadura.py` (scoped override). No re-export from `core/__init__.py`, no env vars, no schema changes.

## Architecture Decisions

| Decision | Choice | Alternative | Why |
|---|---|---|---|
| File format | CSV with `_CANONICAL_COLUMN_ALIASES`-style alias dict | xlsx-only | Matches existing uploaders; zero mapping for typical ENAEX |
| Required cols | `Pozo`, `X`, `Y`, `Z_collar` | Force all 7 dims | Real exports omit Incl/Az/Len/Kilos; skip-dim safer than reject |
| Matching | Primary label (`Pozo`/`label_pozo`/`id_pozo`); fallback `cKDTree` (X,Y) radius 5 m | Always nearest | Label is documented link; `PipelineDefaults.match_threshold=5.0` exists |
| Azimuth Δ | `((az_a − az_d + 180) mod 360) − 180` | Naive subtract | Wraps at 360° — naive returns 350° instead of 10° |
| Inclination Δ | Signed (`incl_a − incl_d`) | Absolute | Direction matters: over- vs under-inclined damage toe geometry differently |
| Tolerances | Frozen `DrillComplianceDefaults` + `DRILL_COMPLIANCE` singleton | Module constants | Matches `Tolerances`/`SectorDeviationDefaults`; env-overridable later |
| Score | Global = % holes where ALL dims within tol; per-dim = % holes where that dim within tol | Weighted index | Operators reason in "how many complied", not weighted scores |
| Grouping | Optional `group_by=["malla","banco"]` → per-group score + per-dim | Global only | Surfaces bad sectors without masking them in a global number |
| UI location | Second `st.file_uploader` below line 51, after `procesar_pozos` | New tab | Same screen, less nav; absent file → `st.info` skip |

## Data Flow

```
Design CSV ─→ pd.read_csv ─→ _resolve_design_columns (alias detect)
                                          │
   df_clean (post procesar_pozos) ───────┤
                                          ▼
                              compute_drill_compliance(...)
                                          ▼
                  ┌───────────────┬───────┴───────┬───────────────┐
                  ▼               ▼               ▼               ▼
              per_hole Δ     aggregates    compliance_score   unmatched lists
              (DataFrame)   (dict[float])      (0–1)
                                          └→ _render_drill_compliance_block
                                             (Spanish expander + table + metrics)
```

## File Changes

| File | Action | LOC | Why |
|---|---|---|---|
| `core/drill_compliance.py` | Create | ~150 | Pure: alias resolve, match, deviation, score, group |
| `core/config.py` | Modify | +15 | `DrillComplianceDefaults` + singleton |
| `tests/test_drill_compliance.py` | Create | ~180 | 8 tests: label, nearest fallback, azimuth wrap, empty, missing cols, per-dim score, group, tol edge |
| `ui/modulo_tronadura.py` | Modify | +40 | Uploader + `_render_drill_compliance_block` (scoped override) |
| `openspec/changes/ACTIVE.md` | Modify | +1 | Append entry per AGENTS.md |

Total ≈ **386 LOC** — single PR, under 400-line budget.

## Interfaces / Contracts

```python
def compute_drill_compliance(
    design_df: pd.DataFrame,
    actual_df: pd.DataFrame,
    match_by: Literal["label", "nearest"] = "label",
    tolerances: DrillComplianceDefaults | None = None,
    group_by: list[str] | None = None,
) -> dict[str, Any]:
    # Returns: {per_hole: DataFrame, aggregates: dict, compliance_score: float,
    #           per_group: dict | None, unmatched_design: list, unmatched_actual: list}
```

Per-hole cols: `label, dX, dY, dZ, dIncl, dAz, dLen, dKg_pct, all_within_tol`.

## Schema Auto-Detection

Mirror `_TACO_CANDIDATES`: a small alias dict resolved via `find_df_column(..., raise_error=required)`. Required = `Pozo, X, Y, Z_collar`; optional dims become NaN and skip scoring. Aliases: `Pozo`→`Pozo|label_pozo|id_pozo|Hole_ID`, `X`→`X|X_Diseno|Este|Latitud_Geo`, `Y`→`Y|Y_Diseno|Norte|Longitud_Geo`, `Z_collar`→`Z_collar|Z_Diseno`, `Incl`→`Incl_Diseno|Design_Dip`, `Az`→`Az_Diseno|Design_Azimuth`, `Len`→`Len_Diseno`, `Kilos`→`Kilos_Diseno|Carga_kg`.

## Matching

- **`label`**: inner join on `Pozo`. Unmatched rows returned for warning.
- **`nearest`**: `cKDTree(actual[[X,Y]].values)`, query each design row; reject > 5 m (reuses `PipelineDefaults.match_threshold`).

## Deviation & Tolerances

| Field | Formula | Default tol |
|---|---|---|
| dX | X_a − X_d | 0.5 m |
| dY | Y_a − Y_d | 0.5 m |
| dZ | Z_collar_a − Z_collar_d | 0.3 m |
| dIncl | Incl_a − Incl_d (signed) | 3° |
| dAz | `((Az_a − Az_d + 180) mod 360) − 180` | 5° |
| dLen | Len_a − Len_d | 0.5 m |
| dKg_pct | (Kilos_a − Kilos_d) / Kilos_d × 100 | 10 % |

```python
@dataclass(frozen=True)
class DrillComplianceDefaults:
    dx_m: float = 0.5
    dy_m: float = 0.5
    dz_m: float = 0.3
    dincl_deg: float = 3.0
    daz_deg: float = 5.0
    dlen_m: float = 0.5
    dkg_pct: float = 10.0
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | Label match, nearest fallback, azimuth wrap (179°↔181°), empty design, missing cols, per-dim score, group score, tol edge (±0.01 m) | `pytest tests/test_drill_compliance.py` (≥6 required, 8 proposed) |
| Integration | `_read_uploaded → procesar_pozos → compute_drill_compliance` on synthetic ENAEX + design | Extend `test_pipeline.py` |
| UI | Manual (`ui/` off-limits in CI) | Streamlit local |

## Migration / Rollout

No migration. Absent design file → `st.info("Sin diseño cargado — omitiendo verificación")`. No schema/flags/env. Revert PR is rollback.

## Open Questions

- `dIncl` tolerance: proposal says 3°, user-prompt example suggested 2°. Going with **3° per proposal** — confirm if tighter is needed.
- `group_by` keys resolve via `find_df_column` against actual df (`Nombre_Malla_Original`, `Banco_Original` per modulo_tronadura.py:118-122), so canonical `["malla","banco"]` work transparently.
