# Blast Hole Attribution Specification

## Purpose

Define individual blast-hole attribution to measured crest and toe deviations without changing existing blast analysis.

## Requirements

### Requirement: Feature-level attribution

The system SHALL attribute holes to every non-zero crest or toe deviation in matched benches. It MUST use the measured feature's world position and only collar locations within the horizontal tolerance.

#### Scenario: Attribute a nearby hole

- GIVEN a matched bench has a non-zero crest deviation and a hole collar within tolerance
- WHEN attribution is requested
- THEN the result SHALL link the hole to that section, bench, crest, and signed deviation

#### Scenario: Isolate features

- GIVEN one hole is within tolerance of multiple features
- WHEN attribution is requested
- THEN it MAY appear once per applicable section-bench-feature result
- AND contributions SHALL NOT be aggregated across features

### Requirement: Charge-distance ranking

The system MUST score eligible holes as charge in kilograms divided by squared horizontal distance, using the energy-density inverse-distance floor. It SHALL rank descending and return at most `top_n` holes per feature.

#### Scenario: Rank by charge and distance

- GIVEN two eligible holes have different charges and distances
- WHEN their scores are calculated
- THEN each score SHALL equal charge divided by floored squared distance
- AND the higher score SHALL rank first

#### Scenario: Enforce result limit

- GIVEN eligible holes exceed `top_n`
- WHEN attribution is requested
- THEN only the `top_n` highest-scoring holes SHALL be returned

### Requirement: Auditable result fields

Each ranked hole MUST include label, `malla`, `distance_m`, `kg`, and `contribution_pct`. Each feature result MUST include section, bench number, feature, and signed `delta_m`. Percentages SHALL use total eligible contribution for that feature.

#### Scenario: Return hole details

- GIVEN eligible holes exist for a deviated feature
- WHEN attribution results are returned
- THEN every feature and ranked hole SHALL contain all required fields

#### Scenario: Missing charge column

- GIVEN valid blast coordinates have no recognized charge column
- WHEN attribution is requested
- THEN the system SHALL use 1 kg per hole, matching energy-density fallback behavior
- AND SHALL still return ranked results

### Requirement: Graceful absence handling

The system MUST return an empty list without raising when blast data is `None` or empty, coordinates are missing, benches or sections are absent, or no matched non-zero deviation exists.

#### Scenario: No usable blast data

- GIVEN blast data is `None`, empty, or lacks `X` or `Y`
- WHEN attribution is requested
- THEN the result SHALL be an empty list without an exception

#### Scenario: No attributable deviation

- GIVEN comparisons are absent or contain no matched non-zero crest or toe deviation
- WHEN attribution is requested
- THEN the result SHALL be an empty list

### Requirement: Attribution presentation

The Streamlit blast-correlation view SHALL provide an additive Spanish-language attribution block. It SHALL allow feature selection, display ranked holes and required fields, and remain safe when empty.

#### Scenario: Inspect a feature

- GIVEN results contain multiple deviated features
- WHEN the user selects one feature
- THEN the view SHALL display its ranked-hole table with Spanish labels

#### Scenario: Empty attribution view

- GIVEN attribution returns no results
- WHEN the view renders
- THEN it SHALL NOT raise or display a misleading ranked-hole table

## Legacy API Compatibility

### Requirement: Preserve existing blast analysis

Attribution MUST be additive. Powder-factor, energy-density, `malla`, pasadura, and stemming-to-crest calculations and outputs SHALL remain unchanged. `core/__init__.py` SHALL remain unchanged.

#### Scenario: Existing regression suite

- GIVEN attribution is installed
- WHEN existing blast tests run without requesting attribution
- THEN prior blast-analysis results SHALL remain unchanged
