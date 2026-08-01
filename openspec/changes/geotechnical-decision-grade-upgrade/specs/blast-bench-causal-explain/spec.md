# Capability: blast-bench-causal-explain

## Purpose

Generate additive, human-readable causal explanations for blast-induced
bench deviations. Outputs complement (never replace) the existing
`blast-hole-attribution` results by surfacing a per-bench narrative that
links deviation patterns to plausible blast drivers with confidence and
evidence references.

## Requirements

### Requirement: Per-bench explanation payload

The system SHALL produce a structured payload per deviated bench containing:
`bench_number`, `deviation_summary`, `candidate_causes` (ranked list with
`driver`, `evidence_refs`, `confidence`, `direction`), and
`inconclusive_notes` (list of unresolved signals).

#### Scenario: explanation produced

- GIVEN a deviated bench with at least one contributing hole and at least one
  profile metric available
- WHEN explanation is requested
- THEN the payload SHALL include all required fields with at least one
  ranked candidate cause

#### Scenario: empty payload

- GIVEN a bench with no contributing holes and no metrics
- WHEN explanation is requested
- THEN the payload SHALL be returned with empty `candidate_causes` and a
  note that the bench is inconclusive

### Requirement: Evidence-based attribution only

Each candidate cause MUST reference at least one observable: hole distance,
hole-to-feature orientation, hole charge, hole timing, or pattern metric.
The system SHALL NOT state association or hypothesis as proven causality.

#### Scenario: causal hypothesis labelled

- GIVEN a candidate cause is "excessive burden → overbreak on crest"
- WHEN the payload is rendered
- THEN it SHALL appear under a "Hypothesis" header, NOT a "Conclusion" header
- AND SHALL list at least one evidence reference

#### Scenario: no invented evidence

- GIVEN no observable supports a candidate cause
- WHEN the candidate is generated
- THEN it SHALL NOT be emitted and SHALL NOT appear in the payload

### Requirement: Confidence per cause

Each candidate cause SHALL include a `confidence` field with values drawn
from the existing confidence vocabulary (`HIGH | MEDIUM | LOW`). Confidence
MUST be derived from sample sufficiency, signal consistency, and blast-data
quality — never from narrative heuristics.

#### Scenario: confidence degrades with sparse data

- GIVEN only one contributing hole within tolerance
- WHEN the cause is scored
- THEN confidence SHALL be `LOW`

#### Scenario: confidence improves with consistent signals

- GIVEN multiple contributing holes and consistent stem/burden signals
- WHEN the cause is scored
- THEN confidence SHALL be at least `MEDIUM`

### Requirement: Distance, orientation and time evidence

For every contributing hole, the payload SHALL expose `distance_m`,
`orientation_to_feature_deg`, and (when available) `timing_ms` alongside
blast attributes (`charge_kg`, `burden_m`, `stemming_m`).

#### Scenario: orientation computed

- GIVEN a contributing hole and a deviated feature
- WHEN the evidence block is generated
- THEN `orientation_to_feature_deg` SHALL be finite and within `[0, 360)`

#### Scenario: timing omitted when unavailable

- GIVEN no timing column is present in the blast data
- WHEN the evidence block is generated
- THEN `timing_ms` SHALL be `null` and SHALL NOT be fabricated

### Requirement: Additive rendering surface

The API and web layers SHALL expose the payload under an additive endpoint
and component. They MUST NOT alter existing `blast-hole-attribution`
output, the binary verdict, or the score formula.

#### Scenario: additive API endpoint

- GIVEN the API server is running
- WHEN `/api/v1/blast/causal-explain` is called for a session
- THEN it SHALL return the per-bench payload
- AND existing `/api/v1/blast/*` endpoints SHALL remain unchanged

#### Scenario: additive web surface

- GIVEN the web app is loaded
- WHEN a bench is selected on the blast tab
- THEN the causal-explain block SHALL render beside existing attribution
- AND existing attribution blocks SHALL remain unchanged