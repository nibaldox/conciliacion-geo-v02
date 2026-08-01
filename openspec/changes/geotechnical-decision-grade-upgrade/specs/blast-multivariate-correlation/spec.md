# Delta for blast-multivariate-correlation

## MODIFIED Requirements

### Requirement: Damage

`fit_multivariate_damage_model` SHALL accept damage, PF, burden, spacing-to-burden, stemming columns and return intercept, coefficients, SEs, t/p stats, R², adj. R², count, condition number, p-value, confidence, `features_used`. It MUST accept `sector`/`session_id` for per-group sub-results.

(Previously: per-sector/temporal fields absent from return contract.)

#### Scenario: Recover

- GIVEN ≥ `min_samples` rows, 3 predictors
- WHEN fitting
- THEN coefficients within 2 SEs of true value
- AND R² exceeds PF-only fit

#### Scenario: Sub

- GIVEN `sector` with ≥2 sectors at `min_samples`
- WHEN fitting
- THEN per-sector coefficients/R²/count/confidence reported
- AND SHALL NOT replace global fit

### Requirement: OLS

The model SHALL use `numpy.linalg.lstsq` (intercept) and `scipy.stats` for t/F; MUST NOT require scikit-learn. With sector/session data, it SHALL fit per-group using OLS.

(Previously: OLS only; per-group unspecified.)

#### Scenario: Fit

- GIVEN NumPy/SciPy, no scikit-learn
- WHEN fitting
- THEN model produces coefficients/stats

#### Scenario: OLS

- GIVEN two sectors with sufficient rows, `sector`
- WHEN fitting
- THEN each sector fits with OLS
- AND global fit is primary

### Requirement: Collinearity

The model SHALL compute the design-matrix condition number; ≥30 SHALL downgrade confidence by one level; rank deficiency or non-finite value SHALL prevent `HIGH`. The number SHALL be reported per-sector.

(Previously: condition number was global.)

#### Scenario: Correlated

- GIVEN design matrix condition number ≥30
- WHEN fitting
- THEN number exposes collinearity
- AND confidence < well-conditioned

#### Scenario: Collinear

- GIVEN two predictors are linear combinations
- WHEN fitting
- THEN returns result, no raise
- AND confidence SHALL NOT be `HIGH`

### Requirement: Insufficient

The function SHALL return `confidence = "INSUFFICIENT"` below `min_samples` rows or with fewer than two finite, non-constant predictors. It SHALL omit missing/all-NaN predictors; missing damage SHALL yield `INSUFFICIENT` without raising. When a sector/session is below caller `min_samples`, the per-group result SHALL be `INSUFFICIENT`; global fit continues.

(Previously: per-group sufficiency unspecified.)

#### Scenario: Few

- GIVEN < `min_samples` rows
- WHEN fitting
- THEN confidence is `INSUFFICIENT`
- AND no actionable coefficients

#### Scenario: Unusable

- GIVEN cols missing/NaN/constant; <2 predictors
- WHEN fitting
- THEN confidence is `INSUFFICIENT`
- AND `features_used` lists validated predictors

#### Scenario: Sector min

- GIVEN one sector below `min_samples`
- WHEN fitting with `sector`
- THEN that sector is `INSUFFICIENT`
- AND other sectors fit

### Requirement: Burden

`recommend_burden_adjustment` SHALL invert the burden coefficient for target damage. It SHALL return current/target burden, change, predicted damage, feasibility, confidence, message. Targets outside 0.5–2.0× current SHALL be cautionary. With `sector`, it SHALL use the sector fit, falling back to global on opt-in when sector is `INSUFFICIENT`.

(Previously: sector-aware burden recommendation absent.)

#### Scenario: Target

- GIVEN sufficient model, finite non-zero burden, representative predictors
- WHEN a reachable target damage is requested
- THEN target burden satisfies equation within tolerance
- AND change/feasibility match target

#### Scenario: Invert

- GIVEN insufficient model or non-finite/missing burden
- WHEN a recommendation is requested
- THEN feasibility is `INSUFFICIENT`
- AND SHALL NOT emit a change

#### Scenario: Sector

- GIVEN a sector fit with sufficient data
- WHEN a sector recommendation is requested
- THEN uses sector fit
- AND falls back to global on caller opt-in

## Legacy API Compatibility

### Requirement: Mono-var

This capability SHALL be additive. `fit_powder_factor_damage_model` and `recommend_pf_adjustment` SHALL retain signatures, return contracts, and import paths; `core/__init__.py` MUST remain unchanged. New sector/temporal fields SHALL be optional, defaulting to legacy.

(Previously: legacy behaviour preserved; adds sector/temporal.)

#### Scenario: Fixt.

- GIVEN any PF fixture
- WHEN legacy functions run after the change
- THEN outputs equal pre-change values
- AND callers need no changes

#### Scenario: Omitted

- GIVEN legacy callers omitting `sector`/`session_id`
- WHEN fitting
- THEN behavior matches pre-change