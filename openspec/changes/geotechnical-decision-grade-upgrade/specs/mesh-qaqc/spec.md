# Capability: mesh-qaqc

## Purpose

Additive provenance, CRS/datum/units, and warning-quality-assurance pass
for input meshes. Unknown metadata surfaces as `UNVERIFIED` warning, not
as a blocker, and the system MUST NOT infer CRS or units from bounding
box heuristics.

## Requirements

### Requirement: Provenance record per mesh

The system SHALL record, per loaded mesh, the source path, file hash,
mesh vertex/face counts, declared CRS (if any), declared datum (if any),
and declared units (if any). Each field SHALL be marked `VERIFIED` or
`UNVERIFIED` depending on whether it was supplied explicitly.

#### Scenario: fully declared mesh

- GIVEN a mesh with CRS, datum, and units declared in sidecar or filename
- WHEN QA/QC runs
- THEN all fields SHALL be `VERIFIED` and exposed in the provenance record

#### Scenario: missing metadata

- GIVEN a mesh without CRS or units metadata
- WHEN QA/QC runs
- THEN the affected fields SHALL be `UNVERIFIED`
- AND the warning SHALL be surfaced, not raised as an error

### Requirement: No bbox CRS/unit inference

The system SHALL NOT infer CRS or units from bounding box dimensions,
area, or aspect ratio. Inference is permitted ONLY from explicit `.prj`
sidecars, declared fields, or unambiguous filename hints.

#### Scenario: explicit `.prj`

- GIVEN a mesh with a sibling `.prj` file
- WHEN QA/QC runs
- THEN the CRS SHALL be read from the sidecar and marked `VERIFIED`

#### Scenario: ambiguous filename

- GIVEN a filename with no recognized CRS or units token
- WHEN QA/QC runs
- THEN CRS SHALL remain `UNVERIFIED`
- AND no inference SHALL be performed

#### Scenario: bbox heuristic forbidden

- GIVEN a mesh with no declared CRS but with a small bounding box
- WHEN QA/QC runs
- THEN the system SHALL NOT infer CRS from the bounding box
- AND SHALL leave CRS as `UNVERIFIED`

### Requirement: Warning, not blocker

QA/QC findings MUST be surfaced as warnings surfaced through the API,
the web app, and the Excel/Word reports. They MUST NOT prevent
downstream processing or block the visible verdict.

#### Scenario: warning surfaced in API

- GIVEN a mesh with `UNVERIFIED` units
- WHEN the QA/QC report is requested
- THEN the response SHALL include the warning with severity `WARNING`
- AND the verdict endpoint SHALL still respond with the binary verdict

#### Scenario: warning surfaced in reports

- GIVEN a mesh with `UNVERIFIED` CRS
- WHEN the Excel or Word report is generated
- THEN a `QA/QC` section SHALL appear with the warning text

### Requirement: Hash-based change detection

The system SHALL compute a deterministic hash for each loaded mesh and
SHALL compare it to a stored hash when available. Mismatches SHALL be
surfaced as warnings, not errors.

#### Scenario: first-load

- GIVEN a mesh loaded for the first time
- WHEN QA/QC runs
- THEN the hash SHALL be recorded and no mismatch warning SHALL be emitted

#### Scenario: hash mismatch

- GIVEN a stored hash and a different current hash
- WHEN QA/QC runs
- THEN a `HASH_MISMATCH` warning SHALL be emitted
- AND downstream processing SHALL continue

### Requirement: Additive output channel

QA/QC results SHALL be exposed through an additive endpoint, an additive
report section, and an additive web panel. They MUST NOT replace
existing payload fields or alter the binary verdict.

#### Scenario: additive API endpoint

- GIVEN the QA/QC module is mounted
- WHEN `/api/v1/mesh/qaqc` is called
- THEN the response SHALL include the provenance record and any warnings

#### Scenario: existing payload untouched

- GIVEN the existing mesh response shape
- WHEN QA/QC is enabled
- THEN existing fields SHALL be unchanged
- AND QA/QC data SHALL be returned under a separate `qaqc` key