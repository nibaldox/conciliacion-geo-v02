# Tasks: Drill Hardness Integration

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~720 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes (per design) |
| Delivery strategy | exception-ok (single PR this session) |
| Chain strategy | size:exception |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Commit | Notes |
|------|------|--------|-------|
| 1 | Pure parity port | `feat(core): port drill hardness classification` | `core/drill_hardness.py` + tests, no UI |
| 2 | Processor + join + config | `feat(core): drill hardness CSV processor + cKDTree join` | processor + tests + `config.py` |
| 3 | UI integration | `feat(ui): wire drilling CSV into blast module` | `ui/modulo_tronadura.py` additive block |

## Phase 1: Pure Classification Module

- [x] 1.1 Create `core/drill_hardness.py` with TypedDicts (`MetricThresholds`, `Thresholds`, `Metric`) + constants (`DEFAULT_DURATION_THRESHOLDS`, `DEFAULT_RATE_THRESHOLDS`, `DEFAULT_THRESHOLDS`, `DURATION_INDEX_UPPER_SATURATION`, `RATE_INDEX_UPPER_SATURATION`, `STD_EPSILON`). No pandas/numpy/streamlit imports.
- [x] 1.2 Port 7 pure functions from `dureza_relativa/classification.py`: `classify_duracion`, `hardness_index`, `penetration_rate`, `classify_with_metric`, `hardness_index_with_metric`, `rig_mean_penetration`, `rig_normalized_penetration`.
- [x] 1.3 Trim docstrings aggressively — keep signatures and behavioural parity; drop prose.

## Phase 2: Processor + Spatial Join

- [x] 2.1 Add `DrillHardnessDefaults` frozen dataclass + `DRILL_HARDNESS` singleton to `core/config.py`. Do NOT export from `core/__init__.py`.
- [x] 2.2 Create `core/drill_hardness_processor.py` with `load_drilling_csv(path)`, `enrich_blast_with_hardness(blast_df, drilling_df, radius=2.0)`. Build tree from drilling `(Este, Norte)`, query blast `(X, Y)`, filter `dist ≤ radius`. Unmatched → NaN.
- [x] 2.3 Collapse reperforados: group drilling by `Pozo` (or coords if `Pozo` missing), keep row with max `Tiempo Final`.
- [x] 2.4 Computed columns on drilling_df: `duracion_min`, `tasa_penetracion`, `dureza`, `indice_dureza`, `perforadora`.

## Phase 3: Tests

- [x] 3.1 Create `tests/test_drill_hardness.py`: parity cases for `classify_with_metric` / `hardness_index_with_metric` boundaries (16/24/40, 1.0/0.7/0.4, 2.5 rate → 0.0), `rig_normalized_penetration` zero-variance, `classify_duracion(30)`.
- [x] 3.2 Create `tests/test_drill_hardness_processor.py`: load_csv (column normalization, missing `Pozo`), `enrich_blast_with_hardness` within radius / beyond radius / unmatched, empty df passthrough.

## Phase 4: UI Integration

- [x] 4.1 Add 3rd uploader in `ui/modulo_tronadura.py` after drill design uploader (`key="blast_drill_hardness_file"`). On load → process → enrich `blast_df_clean` in session_state. Absent → app unchanged.
- [x] 4.2 Add color options: `"Dureza"`, `"Índice de Dureza"`, `"Tasa de Penetración"`. Add `_COLLAR_HOVERTEMPLATE` line for hardness (customdata column or annotation).
- [x] 4.3 Verify all tests pass; `core/__init__.py` unchanged.

## Phase 5: Verification

- [x] 5.1 `pytest tests/test_drill_hardness.py tests/test_drill_hardness_processor.py -v` passes
- [x] 5.2 `pytest tests/ --tb=short -q --ignore=tests/test_openblast.py --ignore=tests/test_reconciled_profile_serialization.py` passes
- [x] 5.3 `python -c "from core.drill_hardness import classify_duracion, penetration_rate, hardness_index; print(...)"` succeeds
- [x] 5.4 `python -c "from core.drill_hardness_processor import load_drilling_csv, enrich_blast_with_hardness; print('OK')"` succeeds
- [x] 5.5 `python test_pipeline.py` succeeds
- [x] 5.6 `git diff main...HEAD -- core/__init__.py` empty
