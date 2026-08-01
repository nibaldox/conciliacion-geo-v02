# Capability: geotechnical-advisory-assessment

## Purpose

Provide an advisory geotechnical assessment (kinematic, Markland-style
planar/wedge/toppling, and water/strength inputs) that augments the
existing geometric compliance verdict without ever altering it. Stability
outputs are NEVER certified and MUST NOT be combined into the binary
`CUMPLE/NO CUMPLE` verdict.

## Requirements

### Requirement: Face orientation and discontinuity sets required

The system SHALL refuse to emit a stability advisory unless it has been
supplied with: face orientation, at least one discontinuity set, water
inputs, and strength inputs — each with explicit provenance.

#### Scenario: missing face orientation

- GIVEN no face orientation supplied
- WHEN assessment is requested
- THEN it SHALL return `INSUFFICIENT_DATA` for stability
- AND SHALL NOT emit a stability advisory

#### Scenario: provenance missing

- GIVEN all inputs supplied but provenance missing on any of them
- WHEN assessment is requested
- THEN the affected input SHALL be reported as `UNVERIFIED`
- AND the stability advisory SHALL be downgraded to `LOW` confidence

### Requirement: Markland-style kinematic output

The system SHALL evaluate planar, wedge, and toppling modes using the
supplied face and discontinuity orientations. Each mode SHALL be
reported as one of `FAVORABLE | UNFAVORABLE | MARGINAL | INSUFFICIENT_DATA`.

#### Scenario: planar mode reported

- GIVEN a face and one discontinuity set
- WHEN kinematic assessment runs
- THEN planar mode SHALL be reported using the supplied friction
  angle with provenance

#### Scenario: friction angle caller-supplied

- GIVEN no friction angle is supplied
- WHEN kinematic assessment runs
- THEN it SHALL return `INSUFFICIENT_DATA` for the affected modes
- AND SHALL NOT invent a default friction angle

### Requirement: Water and strength inputs propagate

The system SHALL accept water conditions (`dry | damp | wet | flowing`)
and a strength input set (`cohesion_kpa`, `friction_deg`,
`unit_weight_kn_m3`). When any of these are absent, the affected
advisory components SHALL return `INSUFFICIENT_DATA`.

#### Scenario: water supplied

- GIVEN `water = "wet"` and full strength inputs
- WHEN assessment is requested
- THEN water SHALL be propagated to all affected components with
  provenance attached

#### Scenario: strength missing

- GIVEN water supplied but `cohesion_kpa` absent
- WHEN assessment is requested
- THEN the components requiring cohesion SHALL return
  `INSUFFICIENT_DATA`
- AND SHALL NOT silently substitute a default

### Requirement: Advisory never alters verdict

The advisory assessment SHALL be exposed as a separate payload. It MUST
NEVER combine with, override, or replace the binary `CUMPLE/NO CUMPLE`
verdict or the score formula.

#### Scenario: unfavorable wedge keeps verdict

- GIVEN a bench with score 80 and an `UNFAVORABLE` wedge advisory
- WHEN the merged payload is rendered
- THEN the verdict SHALL remain `CUMPLE`
- AND the advisory SHALL be reported under a separate header

#### Scenario: no certified-stability claims

- GIVEN any advisory output
- WHEN rendered
- THEN it SHALL be labelled "advisory" and SHALL NOT contain the words
  "certified", "approved", or "guaranteed"

### Requirement: No silent defaults

The system SHALL NOT apply silent defaults for `r_u`, friction angle,
factor-of-safety target, or any other geotechnical constant. Missing
inputs SHALL yield `INSUFFICIENT_DATA`.

#### Scenario: r_u missing

- GIVEN water supplied but no `r_u`
- WHEN the assessment runs
- THEN the affected components SHALL return `INSUFFICIENT_DATA`
- AND no constant SHALL be invented

#### Scenario: caller supplies all constants

- GIVEN the caller supplies all required constants with provenance
- WHEN the assessment runs
- THEN all components SHALL use the caller values
- AND the provenance SHALL be exposed per input