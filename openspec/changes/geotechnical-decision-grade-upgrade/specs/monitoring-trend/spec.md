# Capability: monitoring-trend

## Purpose

Additive monitoring layer providing CUSUM and EWMA trend detection for
per-bench compliance signals across successive sessions. Caller/project
configuration supplies thresholds, sample sufficiency, and run-length
limits; the system SHALL NOT invent numeric defaults.

## Requirements

### Requirement: Caller-supplied thresholds

The system SHALL accept per-metric thresholds (target value, slack,
decision interval) for CUSUM and EWMA from caller/project configuration.
Defaults MUST be exposed as named constants in `core/monitoring_trend.py`
and SHALL NOT be silently applied.

#### Scenario: thresholds supplied

- GIVEN the caller supplies CUSUM `k` and `h` values
- WHEN monitoring runs
- THEN the algorithm SHALL use those values exactly
- AND SHALL expose them in the response

#### Scenario: thresholds missing

- GIVEN no thresholds supplied
- WHEN monitoring runs
- THEN the system SHALL return `INSUFFICIENT_DATA` for the affected
  metric
- AND SHALL NOT fall back to internal defaults

### Requirement: CUSUM trend detection

The system SHALL compute one-sided or two-sided CUSUM on the supplied
series and SHALL emit a `TREND` signal when the cumulative sum crosses
the caller-supplied decision interval. Signal SHALL include the
crossing index and the contributing values.

#### Scenario: positive shift detected

- GIVEN a stable series followed by a sustained positive shift
- WHEN CUSUM runs
- THEN a `TREND` signal SHALL be emitted with the first crossing index

#### Scenario: stable series

- GIVEN a series with no sustained shift
- WHEN CUSUM runs
- THEN no `TREND` signal SHALL be emitted
- AND the run SHALL be reported as `NO_TREND`

### Requirement: EWMA smoothing and detection

The system SHALL compute EWMA with caller-supplied smoothing constant
`lambda` and decision interval `L`. Detection SHALL trigger when EWMA
exceeds the supplied control limits.

#### Scenario: lambda supplied

- GIVEN the caller supplies `lambda = 0.2` and `L = 3.0`
- WHEN EWMA runs
- THEN the algorithm SHALL use those values
- AND SHALL expose them in the response

#### Scenario: short series

- GIVEN fewer observations than the caller-supplied minimum
- WHEN EWMA runs
- THEN it SHALL return `INSUFFICIENT_DATA`
- AND SHALL NOT emit a partial signal

### Requirement: Sample sufficiency

The system SHALL accept a `min_samples` from caller configuration and
SHALL return `INSUFFICIENT_DATA` when the supplied series is shorter.
`min_samples` SHALL be exposed as a named constant.

#### Scenario: enough samples

- GIVEN a series of `n = min_samples` observations
- WHEN monitoring runs
- THEN it SHALL proceed and SHALL emit a verdict

#### Scenario: too few samples

- GIVEN a series shorter than `min_samples`
- WHEN monitoring runs
- THEN it SHALL return `INSUFFICIENT_DATA`
- AND SHALL NOT emit a verdict

### Requirement: No invented numeric defaults

The system SHALL NOT invent numeric defaults for `k`, `h`, `lambda`, `L`,
or `min_samples`. All such values SHALL be supplied by the caller or
exposed as named constants — never applied silently inside the algorithm.

#### Scenario: named constant inspection

- GIVEN the module is imported
- WHEN named constants are inspected
- THEN they SHALL be present and clearly named
- AND SHALL NOT be referenced inside the algorithm body as magic numbers

#### Scenario: caller omits all values

- GIVEN no caller-supplied values for any parameter
- WHEN monitoring runs
- THEN it SHALL return `INSUFFICIENT_DATA` for the run
- AND SHALL NOT silently substitute defaults