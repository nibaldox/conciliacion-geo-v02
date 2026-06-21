# Changelog

All notable changes to OpenBlast are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project adheres to [Semantic Versioning 2.0.0](https://semver.org/).

## [1.0.0] — 2026-06-20

### Added
- Initial public release of the OpenBlast CSV format.
- 17 mandatory fields across 5 blocks (Identification, Location, Geometry, Charge, Stemming, Metadata) and 17 optional fields in a 7th block.
- JSON Schema (Draft-07) at `schema/openblast-1.0.0.schema.json`.
- Frictionless Data Table Schema equivalent at `schema/openblast-1.0.0.table-schema.json`.
- Three example files:
  - `examples/minimal.csv` (5 wells, only mandatory fields)
  - `examples/complete.csv` (5 wells, all fields populated)
  - `examples/datapackage.json` (Frictionless metadata wrapper)
- Vendor mappings (machine-readable) for ENAEX, Datamine/MinePlan, and Surpac.
- Documentation: `docs/field-reference.md`, `docs/versioning.md`, `docs/migrations/1.0.0-initial.md`.
- Schema is extensible via `additionalProperties: true` so vendor-specific columns are preserved on round-trip.

### Notes
- This release was driven by the [conciliacion-geo-v02](https://github.com/nibaldox/conciliacion-geo-v02) project to enable community adoption of geotechnical reconciliation without ENAEX vendor lock-in.
- See `docs/../OPENBLAST_DESIGN.md` for the full design rationale and survey of prior art.

[1.0.0]: https://github.com/nibaldox/conciliacion-geo-v02/releases/tag/openblast-v1.0.0