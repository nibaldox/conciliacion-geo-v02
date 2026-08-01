# Delta for blast-hole-attribution

## MODIFIED Requirements

### Requirement: Feature-level attribution

The system SHALL attribute holes to every non-zero crest or toe deviation in matched benches using the feature's world position and only within-tolerance collars. With `SectionLine` bound, the system MUST invoke the projector; results SHALL return only when ≥1 hole projects onto active sections.

(Previously: no live binding verification.)

#### Scenario: Attribute a hole

- GIVEN a matched bench with non-zero crest deviation and within-tolerance collar
- WHEN attribution is requested with a live `SectionLine`
- THEN the hole links to section, bench, crest, signed deviation; `n_holes > 0`

#### Scenario: Isolate features

- GIVEN one hole within tolerance of many features
- WHEN attribution is requested
- THEN it MAY appear once per section-bench-feature result without aggregation

### Requirement: Charge-distance rank

The system MUST score eligible holes as `kg/max(d, d_min)^2`, rank descending, return ≤ `top_n`/feature. Each ranked hole exposes `orientation_to_feature_deg`, `timing_ms` (or null), `confidence`.

(Previously: only distance+charge exposed.)

#### Scenario: Rank by charge/distance

- GIVEN two eligible holes with distinct charges/distances
- WHEN scores are calculated
- THEN each equals charge/floored squared distance; the higher score ranks first

#### Scenario: Enforce result limit

- GIVEN eligible holes exceed `top_n`
- WHEN attribution is requested
- THEN only `top_n` top-scoring holes return

#### Scenario: Orientation and confidence

- GIVEN an eligible hole with finite orientation
- WHEN the ranked hole is returned
- THEN it includes `orientation_to_feature_deg`, `timing_ms` (or `null`), `confidence`

### Requirement: Auditable fields

Ranked holes MUST include label, `malla`, `distance_m`, `orientation_to_feature_deg`, `timing_ms`, `kg`, `burden_m`, `stemming_m`, `contribution_pct`, `confidence`. Features MUST include section, bench, feature, signed `delta_m`. Percentages SHALL use total eligible contribution. Entries SHALL be labelled `association`/`hypothesis`, never proven causality.

(Previously: those fields were not required.)

#### Scenario: Hole details

- GIVEN holes exist for a deviated feature
- WHEN results are returned
- THEN every feature and ranked hole has all required fields, labelled `association` or `hypothesis`

#### Scenario: Missing charge

- GIVEN blast coords lack a recognized charge column
- WHEN attribution is requested
- THEN it uses 1 kg/hole (fallback) and returns ranked results

### Requirement: Graceful absence

The system MUST return an empty list without raising when blast data is None/empty, coords missing, benches/sections absent, or no non-zero deviation matches. Without `SectionLine` bound, entries SHALL carry `association = "unbound"`.

(Previously: no `unbound` label.)

#### Scenario: No blast data

- GIVEN blast data None/empty or lacks X/Y
- WHEN attribution is requested
- THEN the result is an empty list; entries carry `association = "unbound"`

#### Scenario: No deviation

- GIVEN no non-zero deviation matches
- WHEN attribution is requested
- THEN the result is an empty list

### Requirement: Presentation (additive React/web + report/export)

The contract SHALL expose a React/web block AND a report/export block displaying ranked holes for a feature using `Asociación / Hipótesis`. Empty results SHALL render a safe empty state. `app.py`, `ui/`, `cli.py`, `core/__init__.py` SHALL remain untouched. Renderers SHALL NOT display the causal label.

(Previously: entry labels not enforced; moved off Streamlit to additive React/web + report/export.)

#### Scenario: Inspect feature

- GIVEN many deviated features
- WHEN the user selects one feature
- THEN both show the table under `Asociación / Hipótesis`

#### Scenario: Empty view

- GIVEN attribution returns empty
- WHEN renderers run
- THEN no raise; safe empty state shown

## Legacy API Compatibility

### Requirement: Preserve analysis

Attribution MUST be additive. Powder-factor, energy-density, `malla`, pasadura, stemming-to-crest outputs remain unchanged. `app.py`, `ui/`, `cli.py`, `core/__init__.py` SHALL remain untouched. Existing blast tests SHALL pass without attribution.

(Previously: legacy API preserved.)

#### Scenario: Regression suite

- GIVEN attribution is installed
- WHEN existing blast tests run without requesting attribution
- THEN prior results remain unchanged