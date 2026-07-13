# Tasks: Blast Back-Break Prediction

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~370 (120 prod + 180 tests + 20 config + 30 UI) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | BackbreakDefaults + predict_backbreak + tests + UI expander | PR 1 | additive, no core/__init__.py edits |

## Phase 1: Foundation (Config)

- [x] 1.1 Append `BackbreakDefaults` frozen dataclass to `core/config.py` (k, hp_constant, pf_optimal, ci_band_pct, clamps, defaults, rock_factor bounds)
- [x] 1.2 Add `BACKBREAK = BackbreakDefaults()` singleton next to `DRILL_COMPLIANCE`

## Phase 2: Core Implementation (Domain)

- [x] 2.1 Create `core/backbreak_prediction.py` with `BackbreakPrediction` frozen dataclass and `predict_backbreak(burden_m, spacing_m, pf_kgm3, stemming_m, diameter_mm, model=None, rock_factor=1.0, *, alpha=0.05, bench_height_m=15.0, defaults=None)` signature
- [x] 2.2 Implement multivariate path: read model coefficients + std_errors, build feature row aligned with `features_used`, compute `predicted_m = beta0 + Σ beta_i·x_i`, CI via `t·sqrt(Σ se_i²·x_i² + σ²)`, clamp negative to 0
- [x] 2.3 Implement empirical fallback: `predicted = K·burden·(pf/0.35)·rock_factor` clamped >=0, CI ±15%, Holmberg-Persson cross-check `r = 0.6·sqrt(pf·B·S·H)` clamped to `[0.5·B, 4·B]` appended to `notes`
- [x] 2.4 Robustness: None/NaN/negative/non-finite → substitute defaults from `BackbreakDefaults`, append `substituted:<field>` notes, never raise
- [x] 2.5 Confidence ladder: HIGH (multivariate + within extrapolation), MEDIUM (typical empirical), LOW (any substitution), INSUFFICIENT (empty design + no finite substitute)

## Phase 3: Tests (Verification)

- [x] 3.1 Add `tests/test_backbreak_prediction.py`: synthetic 3-feature recovery, CI coverage 200 MC draws, empirical typical inputs, Holmberg-Persson ±20% agreement
- [x] 3.2 Add guards tests: `None` design, NaN/negative parameters, damage-radius clamp, empirical monotonicity on (pf, burden) grid
- [x] 3.3 Add multivariate clamp-to-zero + legacy `predict_damage_for_pf` smoke test (no signature drift)

## Phase 4: UI (Streamlit override)

- [x] 4.1 In `ui/tabs/blast_correlation.py` append `_render_backbreak_predictor(df_filtered_sections, multivariate_model)` after the multivariate expander; reuse fitted model dict, render `st.expander("Predictor de Back-Break")` with 6 sliders + `st.metric` for predicted_m and CI caption
- [x] 4.2 Wire call site in `render_tab_blast_correlation` so predictor sees the same dataframe + multivariate model as the advisor block

## Phase 5: Verify

- [x] 5.1 `pytest tests/test_backbreak_prediction.py -v` (new file only)
- [x] 5.2 `pytest tests/ --tb=short -q --ignore=tests/test_openblast.py --ignore=tests/test_reconciled_profile_serialization.py`
- [x] 5.3 `python -c "from core.backbreak_prediction import predict_backbreak; print(predict_backbreak(4.0, 4.5, 0.35, 3.0, 165))"`
- [x] 5.4 `python test_pipeline.py`
- [x] 5.5 `git diff main...HEAD -- core/__init__.py` empty
