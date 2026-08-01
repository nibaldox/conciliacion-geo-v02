# Capability: blast-bench-attribution-api

## Purpose

Provide a public, additive FastAPI surface for blast-to-bench attribution
so the existing dormant `attribute_failure_to_holes` projector can be
consumed by external clients and the web frontend without coupling to
internal helpers.

## Requirements

### Requirement: Real SectionLine projector binding

The system SHALL invoke `attribute_failure_to_holes` with the actual
`SectionLine` instances produced for the current session and SHALL return
results only when at least one hole was projected (`n_holes > 0`).

#### Scenario: live projection succeeds

- GIVEN a session with at least one section and blast data with X/Y/Z
- WHEN `/api/v1/blast/attribution` is called
- THEN the response SHALL contain per-section entries
- AND `n_holes` SHALL be greater than zero

#### Scenario: dormant projector returns nothing

- GIVEN the projector is invoked but no holes match
- WHEN the endpoint is called
- THEN the response SHALL be `{"results": []}`
- AND the endpoint SHALL NOT raise

### Requirement: Evidence-rich result contract

Each attribution entry MUST include `section_id`, `bench_number`,
`feature` (`crest` | `toe`), `signed_delta_m`, and per-hole evidence
(`hole_id`, `distance_m`, `orientation_deg`, `timing_ms`,
`charge_kg`, `burden_m`, `stemming_m`, `contribution_pct`).

#### Scenario: required fields present

- GIVEN a matched bench with one contributing hole
- WHEN the response is rendered
- THEN every required field SHALL be present and JSON-serializable

#### Scenario: timing null when absent

- GIVEN the blast data lacks timing columns
- WHEN the response is rendered
- THEN `timing_ms` SHALL be `null` and SHALL NOT be fabricated

### Requirement: Confidence exposure

The endpoint SHALL return a per-entry `confidence` field using the existing
vocabulary. Confidence MUST degrade when `n_holes` is low or when signals
are inconsistent; it SHALL NOT be set heuristically by the projector.

#### Scenario: low sample confidence

- GIVEN only one contributing hole within tolerance
- WHEN the endpoint responds
- THEN `confidence` SHALL be `LOW`

#### Scenario: medium confidence with multiple signals

- GIVEN three contributing holes with consistent distance/charge
- WHEN the endpoint responds
- THEN `confidence` SHALL be `MEDIUM` or `HIGH`

### Requirement: Association, not proven causality

The endpoint MUST label entries as "association" or "hypothesis" and MUST
NOT emit text asserting proven causality between any hole and the
deviation.

#### Scenario: association labelling

- GIVEN any returned entry
- WHEN the payload is rendered
- THEN the label SHALL be "association" or "hypothesis", never
  "cause" or "caused by"

#### Scenario: inconclusive entry

- GIVEN a feature with no contributing holes but a non-zero deviation
- WHEN the endpoint responds
- THEN the entry SHALL include `inconclusive: true`
- AND SHALL NOT assign a hole to it

### Requirement: Additive, non-breaking surface

The endpoint SHALL be additive. It MUST NOT modify existing
`/api/v1/blast/*` responses, MUST NOT touch `app.py`, `ui/`, `cli.py`, or
`core/__init__.py`.

#### Scenario: existing endpoints unaffected

- GIVEN the new endpoint is mounted
- WHEN pre-existing `/api/v1/blast/*` regression tests run
- THEN they SHALL pass without modification

#### Scenario: legacy imports unaffected

- GIVEN `core/__init__.py` is unchanged
- WHEN `from core import …` is executed by any caller
- THEN no new symbols SHALL be introduced in that re-export