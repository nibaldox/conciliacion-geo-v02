# Blast Multivariate Correlation Specification

## Purpose

Define additive multivariate blast-damage regression and burden-aware recommendations while preserving the existing powder-factor workflow.

## Requirements

### Requirement: Multivariate Damage Model Result

`fit_multivariate_damage_model` SHALL accept a DataFrame with damage, PF, burden, spacing-to-burden ratio, and stemming columns. It SHALL return the intercept, feature-keyed coefficients, standard errors, t-statistics, p-values, R², adjusted R², sample count, condition number, overall p-value, confidence, and `features_used`.

#### Scenario: Recover a multivariate relationship

- GIVEN at least `min_samples` finite rows generated from three independent blast predictors
- WHEN the model is fitted
- THEN each recovered coefficient SHALL be within two standard errors of its generating value
- AND the result SHALL report all fitted diagnostics and a higher R² than the PF-only fit

### Requirement: OLS Statistical Method

The model SHALL use intercept-inclusive `numpy.linalg.lstsq`, derive inference from residual covariance, and use `scipy.stats` for two-sided t and overall F probabilities. It MUST NOT require scikit-learn.

#### Scenario: Fit without scikit-learn

- GIVEN NumPy, SciPy, and valid observations are available but scikit-learn is unavailable
- WHEN fitting is requested
- THEN the model SHALL produce coefficients and inferential statistics without an import or dependency failure

### Requirement: Collinearity Diagnostics

The model SHALL calculate the design-matrix condition number. A condition number of at least 30 SHALL downgrade confidence by at least one level, and rank deficiency or a non-finite condition number SHALL prevent high confidence.

#### Scenario: Correlated predictors

- GIVEN valid predictors whose design matrix has condition number at least 30
- WHEN the model is fitted
- THEN the reported condition number SHALL expose the collinearity
- AND confidence SHALL be lower than the equivalent well-conditioned fit

#### Scenario: Perfect collinearity

- GIVEN two valid predictors are exact linear combinations
- WHEN the model is fitted
- THEN the function SHALL return a structured result without raising an exception
- AND confidence SHALL NOT be `HIGH`

### Requirement: Insufficient and Malformed Input

The function SHALL return `confidence="INSUFFICIENT"` when fewer than `min_samples` complete rows or fewer than two finite, non-constant predictors remain. It SHALL omit missing and all-NaN predictors; a missing damage column SHALL yield `INSUFFICIENT` without raising.

#### Scenario: Too few observations

- GIVEN fewer than `min_samples` complete rows
- WHEN fitting is requested
- THEN confidence SHALL be `INSUFFICIENT`
- AND no actionable coefficients SHALL be reported

#### Scenario: Unusable predictor columns

- GIVEN candidate columns are missing, all-NaN, or constant so fewer than two predictors remain
- WHEN fitting is requested
- THEN confidence SHALL be `INSUFFICIENT`
- AND `features_used` SHALL contain only predictors that passed validation

### Requirement: Burden Adjustment Recommendation

`recommend_burden_adjustment` SHALL invert the burden coefficient for target damage while holding other predictors at supplied values or section means. It SHALL return current/target burden, absolute/percentage change, predicted current/target damage, feasibility, confidence, and message. Targets outside 0.5–2.0 times current burden SHALL be cautionary.

#### Scenario: Recover target burden

- GIVEN a sufficient model with a finite non-zero burden coefficient and representative values for other predictors
- WHEN a reachable target damage is requested
- THEN target burden SHALL satisfy the fitted equation within numeric tolerance
- AND the returned change and feasibility SHALL be consistent with that target

#### Scenario: Burden cannot be inverted

- GIVEN an insufficient model or a zero, missing, or non-finite burden coefficient
- WHEN a recommendation is requested
- THEN feasibility SHALL be `INSUFFICIENT`
- AND the function SHALL NOT emit an actionable burden change

## Legacy API Compatibility

### Requirement: Preserve Mono-variable Behavior

This capability SHALL be additive. `fit_powder_factor_damage_model` and `recommend_pf_adjustment` SHALL retain their signatures, return contracts, numerical behavior, and existing import paths; `core/__init__.py` MUST remain unchanged.

#### Scenario: Existing regression fixtures

- GIVEN any existing PF-model and PF-advisor fixture
- WHEN the legacy functions run after this capability is added
- THEN their outputs SHALL equal the pre-change outputs
- AND existing callers SHALL require no modifications
