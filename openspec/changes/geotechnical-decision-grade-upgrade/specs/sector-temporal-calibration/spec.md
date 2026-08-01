# Capability: sector-temporal-calibration

## Purpose

Per-sector and temporal calibration of the blast-damage model with leave-
one-out (LOO) cross-validation. Caller/project configuration supplies
distributions, iterations, and minimum sample counts; the system SHALL
NOT invent numeric defaults.

## Requirements

### Requirement: Per-sector calibration

The system SHALL fit the multivariate damage model per sector using
caller-supplied sector labels and SHALL report per-sector coefficients,
R², sample count, and confidence.

#### Scenario: sector with sufficient samples

- GIVEN a sector with at least the caller-supplied `min_samples`
- WHEN calibration runs
- THEN per-sector coefficients, R², and sample count SHALL be reported
- AND confidence SHALL be derived from the fit

#### Scenario: sector below minimum

- GIVEN a sector with fewer than `min_samples` rows
- WHEN calibration runs
- THEN the sector SHALL be reported with `confidence = INSUFFICIENT`
- AND SHALL NOT emit actionable coefficients

### Requirement: Temporal calibration

The system SHALL train on prior sessions and validate on the current
session using caller-supplied session boundaries. Validation metrics
(RMSE, MAE, R²) and residuals SHALL be returned.

#### Scenario: train/validate split supplied

- GIVEN prior session IDs and a current session ID supplied by the caller
- WHEN temporal calibration runs
- THEN the model SHALL be fit on the prior sessions
- AND SHALL be evaluated on the current session

#### Scenario: missing prior sessions

- GIVEN no prior sessions supplied
- WHEN temporal calibration runs
- THEN it SHALL return `INSUFFICIENT_DATA` for the temporal component
- AND SHALL NOT fall back to the current session as both train and test

### Requirement: Leave-one-out cross-validation

The system SHALL perform LOO cross-validation per sector when the caller
requests it. LOO SHALL fold out one observation at a time, refit the
model on the remainder, and report aggregate metrics.

#### Scenario: LOO requested

- GIVEN `cv = "loo"` supplied by the caller
- WHEN calibration runs
- THEN LOO SHALL be performed
- AND aggregate RMSE, MAE, and R² SHALL be reported

#### Scenario: LOO on insufficient data

- GIVEN fewer than the caller-supplied `min_samples` rows
- WHEN LOO is requested
- THEN it SHALL return `INSUFFICIENT_DATA`
- AND SHALL NOT emit partial LOO metrics

### Requirement: Caller-supplied MC inputs

Monte Carlo distributions and `n_iterations` SHALL be supplied by the
caller/project. The system SHALL NOT invent distribution shapes, sample
counts, or convergence thresholds.

#### Scenario: caller supplies distribution

- GIVEN the caller supplies a normal distribution for one predictor
- WHEN calibration runs
- THEN that distribution SHALL be used as supplied
- AND SHALL be exposed in the response

#### Scenario: distribution absent

- GIVEN no distribution supplied for a predictor
- WHEN calibration runs
- THEN that predictor SHALL be omitted from the MC step
- AND the response SHALL flag it as `MC_SKIPPED`

### Requirement: No invented numeric defaults

`min_samples`, `n_iterations`, distribution shapes, convergence
thresholds, and CV strategy SHALL be supplied by the caller or exposed
as named constants — never applied silently.

#### Scenario: named constant inspection

- GIVEN the module is imported
- WHEN constants are inspected
- THEN they SHALL be present and clearly named
- AND SHALL NOT appear as magic numbers inside the algorithm body

#### Scenario: all values omitted

- GIVEN no caller-supplied values for any calibration parameter
- WHEN calibration runs
- THEN it SHALL return `INSUFFICIENT_DATA`
- AND SHALL NOT silently substitute defaults