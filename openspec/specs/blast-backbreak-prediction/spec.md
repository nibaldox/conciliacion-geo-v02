# Blast Back-Break Prediction Specification

## Purpose

Forward estimator of expected back-break (m behind the design crest) BEFORE drilling, derived from the multivariate regression trained on past blasts. Adds an empirical Holmberg-Persson cross-check when no fitted model is available. Closes Gap 4 without disturbing existing forensic fits or advisors.

## Requirements

### Requirement: Forward Prediction

`predict_backbreak(design_params, model=None, *, alpha=0.05)` SHALL return a `BackbreakPrediction` carrying `predicted_m` (m, ≥ 0), a `(1 - alpha)` confidence interval, `method ∈ {"multivariate", "empirical_fallback"}`, `confidence ∈ {"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"}`, and a `notes` list. Inputs are read from `design_params` keys (or kwargs) `burden_m`, `spacing_m`, `pf_kgm3`, `stemming_m`, `diameter_mm` (plus optional `rock_factor`).

#### Scenario: Multivariate path when model is fitted
- GIVEN a `model` dict from `core.blast_model.fit_multivariate_damage_model` with `confidence != "INSUFFICIENT"` and a complete design
- WHEN `predict_backbreak(design_params, model)` runs
- THEN `method == "multivariate"`, `predicted_m == beta0 + Σ beta_i · x_i`, and the CI uses `t_(1-α/2, dof) · pooled_SE`

#### Scenario: Empirical fallback when no model
- GIVEN `model=None` (or `model["confidence"] == "INSUFFICIENT"`)
- WHEN `predict_backbreak(design_params)` runs
- THEN `method == "empirical_fallback"` and `predicted_m == 0.3 · burden · (pf / 0.35)` where `0.35` is `BackbreakDefaults.pf_optimal_default_kgm3`

### Requirement: Always Emit Uncertainty

The result SHALL never be a bare point estimate. Multivariate CI uses `t · pooled_SE`; empirical CI defaults to a `±ci_band_pct` (default 15%) band around the point estimate; in both cases `ci_low_m ≤ predicted_m ≤ ci_high_m`.

#### Scenario: Empirical ±15% CI
- GIVEN the empirical path
- WHEN prediction runs
- THEN `ci_low_m == predicted_m · (1 - 0.15)` and `ci_high_m == predicted_m · (1 + 0.15)`

### Requirement: Graceful on Malformed Input

The function SHALL never raise on `None`, missing keys, non-finite values, or out-of-range numbers. Unusable inputs force `confidence == "INSUFFICIENT"`; otherwise defaults are substituted (e.g. PF ≤ 0 → `pf_optimal_default_kgm3`).

#### Scenario: None design
- GIVEN `design_params=None`
- WHEN the function runs
- THEN it returns `BackbreakPrediction(method="empirical_fallback", confidence="INSUFFICIENT", ...)` without raising

#### Scenario: Non-finite burden
- GIVEN `design_params={"burden_m": NaN, "pf_kgm3": 0.35}`
- WHEN the function runs
- THEN burden falls back to `default_burden_m` and `predicted_m` stays finite

### Requirement: Holmberg-Persson Cross-Check

The empirical fallback SHALL also compute `r_damage = hp_constant · sqrt(kg_per_hole)` where `kg_per_hole = pf · burden · spacing · bench_height_m`. The cross-check value (clamped to `[clamp_low_factor_b · B, clamp_high_factor_b · B]`) SHALL be appended to `notes` as a sanity number; it SHALL NOT replace the empirical point estimate.

#### Scenario: Cross-check agreement in calibrated band
- GIVEN a typical open-pit design (PF ≈ 0.35, burden ≈ 6, spacing ≈ 7, bench = 15, `hp_constant=0.6`)
- WHEN both estimates run
- THEN `|r_damage − predicted_m| / predicted_m ≤ 0.20`

### Requirement: Legacy Surface Unchanged

`fit_multivariate_damage_model`, `fit_powder_factor_damage_model`, `predict_damage_for_pf`, `BlastAdvisorDefaults.suggest_blast_recommendation`, and every symbol re-exported by `core/__init__.py` SHALL remain unchanged. The new module SHALL be imported as `core.backbreak_prediction` and MUST NOT be re-exported from `core/__init__.py`.

#### Scenario: No edits to core/__init__.py
- GIVEN the implementation lands
- WHEN `git diff main...HEAD -- core/__init__.py` runs
- THEN the diff is empty

#### Scenario: Old predictor still works
- GIVEN `predict_damage_for_pf(model, target_pf)` returning `{predicted_damage, delta_from_current, uncertainty_m}`
- WHEN back-break prediction lands
- THEN those return keys and shapes are unchanged

### Requirement: Monotonicity and Clamping

The empirical path SHALL be monotonic in `pf_kgm3` and `burden_m` (higher each → ≥ `predicted_m`). The multivariate path SHALL NOT enforce monotonicity (data-driven) but SHALL clamp `predicted_m < 0` to `0` and note the clamp.

#### Scenario: Higher PF → more back-break (empirical)
- GIVEN two designs differing only in `pf_kgm3` (0.30 vs 0.45)
- WHEN the empirical predictor runs on both
- THEN the higher PF yields ≥ `predicted_m`

## Legacy API Compatibility

This change is additive. `core/blast_model.py`, `core/blast_advisor.py`, and `core/__init__.py` re-exports stay intact. Optional addition in `core/config.py`: a frozen `BackbreakDefaults` dataclass + `BACKBREAK` singleton exposing `hp_constant=0.6`, `empirical_k=0.3`, `pf_optimal_default_kgm3=0.35`, `ci_band_pct=0.15`, `clamp_low_factor_b=0.5`, `clamp_high_factor_b=4.0`, `bench_height_m=15.0`, and per-parameter defaults for graceful substitution.

## Result Contract

```python
@dataclass(frozen=True)
class BackbreakPrediction:
    predicted_m: float        # expected back-break (m), >= 0
    ci_low_m: float           # (1 - alpha) lower bound
    ci_high_m: float          # (1 - alpha) upper bound
    method: str               # "multivariate" | "empirical_fallback"
    confidence: str           # "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT"
    notes: list[str]          # cross-check, clamps, extrapolation warnings

def predict_backbreak(
    design_params: dict | None,
    model: dict | None = None,
    *,
    alpha: float = 0.05,
    defaults: BackbreakDefaults | None = None,
) -> BackbreakPrediction: ...
```

The function SHALL never raise; malformed input → `confidence="INSUFFICIENT"`. A positional-args sibling (`predict_backbreak(burden_m, spacing_m, pf_kgm3, stemming_m, diameter_mm, model=None, ...)`) MAY be exposed as a thin wrapper over the same core to keep Streamlit slider bindings simple.
