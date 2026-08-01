# Capability: bench-area-volume

## Purpose

Compute signed area and signed volume for each reconciled bench using
3D bank-clipped surfaces as the primary source and a section-prism
fallback when only cross-sections are available.

## Requirements

### Requirement: Signed normal-distance area on 3D bank-clipped surfaces

The system SHALL compute signed area per bench on the 3D bank-clipped
surface using signed normal distance, prioritizing the topographic
surface over any design/as-built difference mesh.

#### Scenario: 3D surface primary path

- GIVEN a reconciled bench with a bank-clipped 3D surface patch
- WHEN signed area is computed
- THEN the result SHALL be the integral of the signed normal distance
  over the patch
- AND SHALL be reported in square meters with sign

#### Scenario: empty patch returns zero

- GIVEN a bench whose bank-clipped patch is empty
- WHEN signed area is computed
- THEN the result SHALL be `0.0` with sign `0`

### Requirement: Section-prism fallback exposes uncertainty

When the 3D surface patch is unavailable, the system SHALL fall back to a
section-prism estimate built from the available cross-sections. The
fallback MUST expose the spacing and orientation of contributing
sections so callers can reason about uncertainty.

#### Scenario: fallback invoked

- GIVEN no 3D bank-clipped surface for a bench
- WHEN signed area is computed
- THEN the system SHALL compute a section-prism estimate
- AND SHALL expose `section_spacing_m`, `section_orientation_deg`,
  and `n_sections` alongside the area

#### Scenario: section spacing above threshold

- GIVEN `section_spacing_m` exceeds a caller-supplied maximum
- WHEN the fallback is returned
- THEN the result SHALL carry `uncertainty = HIGH`
- AND SHALL NOT be promoted to the primary path

### Requirement: Signed volume from bank-clipped surfaces

The system SHALL compute signed volume per bench by integrating the signed
area along the bench's vertical extent using the 3D bank-clipped surface
when available. The section-prism fallback SHALL produce a triangular-prism
volume approximation.

#### Scenario: 3D volume primary

- GIVEN a bench with a bank-clipped 3D surface
- WHEN signed volume is computed
- THEN the result SHALL be the integral of signed area over the bench
  height in cubic meters with sign

#### Scenario: fallback volume approximation

- GIVEN no 3D surface and two contributing sections
- WHEN signed volume is computed
- THEN the result SHALL be a triangular-prism approximation
- AND SHALL be flagged with `method = "section_prism_fallback"`

### Requirement: No invented sample thresholds

The system SHALL NOT introduce hidden tolerances for minimum samples,
minimum area, or sign-detection stability. Callers SHALL supply any
thresholds via configuration; defaults SHALL be exposed as constants in
`core/bench_metrics_volume.py`.

#### Scenario: caller-supplied threshold

- GIVEN a caller supplies `min_section_count = 4`
- WHEN the fallback is evaluated
- THEN benches with fewer than 4 sections SHALL be returned with
  `uncertainty = HIGH` regardless of internal heuristics

#### Scenario: no silent defaults

- GIVEN the module is imported
- WHEN default thresholds are inspected
- THEN they SHALL be named constants, not magic numbers inside the body
  of the computation

### Requirement: Additive outputs and surface

Area and volume results SHALL be returned as additive fields on the
existing bench payload. They MUST NOT replace any current field and MUST
NOT alter the binary verdict or the score formula.

#### Scenario: additive fields

- GIVEN a bench payload with the existing fields
- WHEN area and volume are computed
- THEN the response SHALL include `signed_area_m2`, `signed_volume_m3`,
  `method`, and `uncertainty` alongside the existing fields

#### Scenario: verdict independent

- GIVEN any bench with a known score
- WHEN area and volume are added to the payload
- THEN the visible verdict SHALL remain unchanged