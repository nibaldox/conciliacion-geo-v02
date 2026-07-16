# Proposal: Blast Back-Break Prediction (Gap 4)

## Intent

`fit_multivariate_damage_model` and the mono PF fit describe past damage — the tool is **forensic**. Mining engineers want forward prediction: given a NEW design (burden, spacing, PF, stemming, hole diameter), estimate back-break BEFORE drilling. The advisor inverts for a *target* damage, not an *unobserved* design. Add a predictor that turns the historical regression into a forward estimator with uncertainty. Closes Gap 4 without disturbing regression or advisor.

## Scope

**In**: new module `core/backbreak_prediction.py` exposing `predict_backbreak(design, model=None, *, alpha=0.05)` and `@dataclass BackbreakPrediction {predicted_m, ci_low_m, ci_high_m, method, confidence, notes}`. Two paths: (a) multivariate — apply fitted coefficients, CI via residual SE × t_(1-α/2, n-k); (b) empirical fallback — Holmberg-Persson `r_d ≈ k·(Q/R)^0.5` with `k` from fit residual std, else `BlastAdvisorDefaults`; clamp `r_d` to `[0.5·B, 4·B]`. Malformed input → `confidence="INSUFFICIENT"`, no raise. Tests `tests/test_backbreak_prediction.py` (~10): recovery, both paths, CI coverage, guards, clamping, monotonicity.

**Out**: changes to existing fits/advisors; `core/__init__.py`; UI outside override; new blast-correlation / drill logic; sklearn.

## Capabilities

### New Capabilities
- `blast-backbreak-prediction`: forward estimation of expected back-break (m) from a design dict, with CI and empirical fallback.

### Modified Capabilities
- None. `blast-multivariate-correlation` and `blast-design-achievement` stay untouched; the predictor only **reads** via public return contracts.

## Approach

Additive module; single function + frozen dataclass. UI in spec phase — a "Predictor de Back-Break" expander under the multivariate block, covered by the maintainer override.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `core/backbreak_prediction.py` | New | `predict_backbreak`, `BackbreakPrediction`, Holmberg-Persson helper. ~120 LOC. |
| `tests/test_backbreak_prediction.py` | New | ~10 tests, both paths + guards. |
| `ui/tabs/blast_correlation.py` | New expander | `_render_backbreak_predictor`. Needs scope override. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Extrapolation beyond training range | High | CI via SE × t; clamp `r_d` to `[0.5·B, 4·B]`; `confidence="LOW"` outside 0.5–2× feature mean. |
| Empirical fallback weak constant | Medium | Document `k` provenance; treat as calibration hint. |
| Multivariate model not fitted | Medium | Pass-through to empirical; `method="empirical_fallback"`. |
| UI override rejected | Low | Precedent set; defer UI if rejected. |

## Rollback Plan

Delete `core/backbreak_prediction.py` and its test file; revert the single UI commit. No edits to existing signatures — main stays green after revert. `core/__init__.py` MUST stay untouched.

## Dependencies

`numpy`, `scipy.stats` (env-present, lazy-imported in `core/blast_model.py`); optional `BlastAdvisorDefaults`; maintainer scope override.

## Success Criteria

- `pytest tests/ -v --tb=short` passes all ~772 tests.
- 3-feature synthetic: prediction within 2·SE; 95% CI covers truth ≥90% of 200 draws.
- Empirical fallback recovers Holmberg-Persson truth within ±15% in the calibrated band.
- Malformed input → `confidence="INSUFFICIENT"`, no raise.
- `git diff main...HEAD -- core/__init__.py` is empty.
