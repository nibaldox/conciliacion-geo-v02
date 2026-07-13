# Tasks: Blast Multivariate Damage Model

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~380 (post-trim; nominal 440) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR with test boilerplate trim |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

### Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Multivariate OLS + burden advisor + UI expander + tests | PR 1 (single) | Test trim; legacy API untouched |

## Phase 1: Foundation

- [x] 1.1 Add `_MULTIVARIATE_PREDICTOR_CANDIDATES` lookup (pf_vol, burden, spacing_burden_ratio, stemming)
- [x] 1.2 Add `_MULTIVARIATE_INSUFFICIENT_RESULT` skeleton dict
- [x] 1.3 Add `_classify_multivariate_confidence(model)` helper (n, F p-value, cond; HIGH→CAUTION at cond ≥ 30)

## Phase 2: Core Multivariate Model

- [x] 2.1 Implement `fit_multivariate_damage_model(df, damage_col, min_samples=12)` via `first_present_column` + `np.linalg.lstsq` with intercept column
- [x] 2.2 Derive SE/t/p from `inv(XᵀX)`; R², adj-R², F-test via `scipy.stats.f.sf`; condition via `np.linalg.cond`
- [x] 2.3 Handle rank deficiency (`pinv`, `rank_deficient=True`) and non-finite condition, no raise
- [x] 2.4 Confirm `fit_powder_factor_damage_model` and `core/__init__.py` re-exports unchanged

## Phase 3: Advisor Burden Inversion

- [x] 3.1 Implement `recommend_burden_adjustment(model, current_burden, target_overbreak_m=None)` — solve burden, others at `model["feature_means"]`
- [x] 3.2 Reuse `_classify_feasibility` with bounds `[0.5·B, 2·B]`; CAUTION when target outside
- [x] 3.3 Add `_build_burden_message` (Spanish-neutral) and `_MULTIVARIATE_INSUFFICIENT` skeleton
- [x] 3.4 Add `recommend_multivariate` dispatcher: route when `n ≥ 12 AND ≥3 features AND != INSUFFICIENT`
- [x] 3.5 Confirm `recommend_pf_adjustment` + existing helpers unchanged

## Phase 4: UI Integration

- [x] 4.1 Add `st.expander("Modelo multivariado (PF + burden + stemming)")` in `ui/tabs/blast_correlation.py` under PF block (override approved)
- [x] 4.2 Render coefficients table (SE + p-values); show `collinearity_warning` when present
- [x] 4.3 Call `recommend_multivariate(model, current_burden)`; display feasibility + target burden + message

## Phase 5: Tests

- [x] 5.1 Truth recovery: `y = 0.3 + 1.2·PF − 0.5·B + 0.1·S/B − 0.2·T + ε` (n=40); `|β̂ − β| < 2·SE` (parametrized)
- [x] 5.2 R² lift vs mono: `r_squared ≥ mono + 0.05`
- [x] 5.3 Small-n: n=8 → INSUFFICIENT; n=12 strong → MEDIUM/HIGH
- [x] 5.4 Collinearity: PF = 1/B → cond ≥ 30 → CAUTION + warning
- [x] 5.5 Missing/constant cols: ≤2 features → INSUFFICIENT, no raise
- [x] 5.6 Advisor inversion: given true β, recovers burden within 5%
- [x] 5.7 Boundary: 2.1·B → CAUTION; zero/non-finite β_burden → INSUFFICIENT
- [x] 5.8 Dispatcher: n=15 + 3 feats → multi; n=5 → INSUFFICIENT
- [x] 5.9 Legacy regression: `recommend_pf_adjustment` byte-identical
- [x] 5.10 Trim boilerplate so test ≤ 180 LOC and PR ≤ 380 lines

## Phase 6: Verification

- [x] 6.1 `pytest tests/test_blast_multivariate_model.py -v` green; suite 768+ tests
- [x] 6.2 `git diff main...HEAD -- core/__init__.py` empty (legacy API preserved)
- [x] 6.3 `python cli.py --auto` smoke test on synthetic meshes; expander renders clean