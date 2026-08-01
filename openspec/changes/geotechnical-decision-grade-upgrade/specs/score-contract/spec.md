# Capability: score-contract

## Purpose

Single, authoritative contract for the per-bench compliance score used by the
visible verdict. Eliminates score drift (60/10/30 vs 60/20/20) and gives all
interfaces one place to import weights and thresholds from.

## Requirements

### Requirement: Authoritative score formula

The system SHALL compute the per-bench compliance score as
`score = 60·berm + 20·angle + 20·height` (weights MUST sum to 100), exposed
only by `core/score_weights.py`. No other module SHALL redefine the weights.

#### Scenario: weights sum to 100

- GIVEN `core/score_weights.py` exports berm, angle, height weights
- WHEN the sum is computed at import time
- THEN the sum SHALL equal 100 and SHALL be verified by a contract test

#### Scenario: drift guard

- GIVEN any import of the three weights from a path other than `core/score_weights.py`
- WHEN the import is executed
- THEN it SHALL raise `ImportError` to prevent duplicate definitions

### Requirement: Visible verdict is binary

The system SHALL derive the visible verdict from the score using a threshold
of 70. Below 70 SHALL emit `NO CUMPLE`; at or above 70 SHALL emit `CUMPLE`.
Verdict SHALL be exposed as binary `CUMPLE/NO CUMPLE` only.

#### Scenario: at threshold

- GIVEN a bench score of exactly 70
- WHEN verdict is computed
- THEN the result SHALL be `CUMPLE`

#### Scenario: below threshold

- GIVEN a bench score of 69.99
- WHEN verdict is computed
- THEN the result SHALL be `NO CUMPLE`

### Requirement: Advisory outputs never alter verdict

The system SHALL treat structural, water, kinematic, probabilistic and
confidence outputs as advisory only. These outputs MUST NEVER combine with,
override, or replace the binary `CUMPLE/NO CUMPLE` verdict.

#### Scenario: low confidence keeps verdict

- GIVEN a bench score of 80 with `confidence = LOW`
- WHEN the verdict is computed
- THEN it SHALL remain `CUMPLE` and confidence SHALL be exposed separately

#### Scenario: probabilistic warning keeps verdict

- GIVEN a bench score of 72 with a probabilistic advisory flag
- WHEN the verdict is computed
- THEN it SHALL remain `CUMPLE` and the flag SHALL be reported as advisory

### Requirement: Insufficient data fallback

When a per-bench metric is missing, the system SHALL return `INSUFFICIENT_DATA`
for that bench only. The verdict SHALL be computed from the available metrics
of that bench without inventing values.

#### Scenario: missing height metric

- GIVEN berm and angle metrics are present, height is absent
- WHEN the bench is evaluated
- THEN it SHALL return `INSUFFICIENT_DATA` for height
- AND SHALL NOT emit a verdict until height is supplied

#### Scenario: all metrics missing

- GIVEN a bench has none of berm, angle, height
- WHEN the bench is evaluated
- THEN it SHALL return `INSUFFICIENT_DATA` for the bench with no verdict

### Requirement: TS↔Python weight parity

The TypeScript layer SHALL import weights from a generated JSON mirror of
`core/score_weights.py` (build-time) and SHALL compare them at test time.
Mismatches SHALL fail the build.

#### Scenario: build-time mirror

- GIVEN a build invocation
- WHEN the mirror is regenerated
- THEN the TS values SHALL equal the Python values exactly

#### Scenario: drift detection

- GIVEN the TS values diverge from the Python values
- WHEN the parity test runs
- THEN the test SHALL fail with a message naming the diverging field