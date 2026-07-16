# Capability: reconciled-profile-serialization

> **Source change**: `reconciled-profile-v2-default` (archived)
> **Archived on**: 2026-07-10
> **Status**: archived, source of truth

This capability defines the canonical serialization surface of the
reconciled profile (`ReconciledProfile`) in `core/`. It exposes:

1. The canonical `from core import build_reconciled_profile_v2` re-export,
   paired with a hardened deprecation horizon for the legacy
   `build_reconciled_profile` builder.
2. Three serialization methods on `ReconciledProfile`:
   `summary()`, `to_dataframe()`, and a `to_dict()` / `from_dict()`
   JSON round-trip pair.

Hazard enrichment is method-level: callers pass an optional
`benches: list[BenchParams] | None = None` argument to the relevant
methods. No persistent `ReconciledProfile.benches` field is required.

## Requirements

### Requirement: ReconciledProfile.summary

`ReconciledProfile` SHALL expose `summary(benches=None) -> dict`. The dict SHALL be flat, accepted by `json.dumps`, and contain at least: `n_benches`, `n_ramps`, `n_overhangs`, `n_wedge_risks`, `n_toppling_risks`, `n_consensus_benches`, `height_range_m`, `total_berm_width_m`, `avg_face_angle_deg`, `max_overhang_m`, and `source`.

Counts SHALL use typed points. Bench/hazard metrics SHALL use the optional `benches` argument when supplied. Without benches, hazard counts SHALL be `0`, `n_consensus_benches` SHALL equal `n_benches`, `avg_face_angle_deg` SHALL be `None`, and width/overhang totals SHALL be `0.0`. Values MUST NOT expose numpy scalars or dataclasses. `height_range_m` SHALL be a `(min, max)` tuple before JSON serialization.

#### Scenario: empty profile

- GIVEN `ReconciledProfile(distances=[], elevations=[], points=[])`
- WHEN `summary()` is called
- THEN `n_benches=0`, `n_ramps=0`, hazard counts are `0`, and `height_range_m=(0, 0)`
- AND `json.dumps(summary)` succeeds.

#### Scenario: enriched benches

- GIVEN a profile with two unique bench numbers, one ramp point, and benches with overhang/wedge/toppling fields
- WHEN `summary(benches=benches)` is called
- THEN bench, ramp, hazard, berm-width, face-angle, and max-overhang values reflect those benches.

### Requirement: ReconciledProfile.to_dataframe

`ReconciledProfile` SHALL expose `to_dataframe(benches=None) -> pandas.DataFrame` with one row per `ReconciledPoint`. Base columns SHALL be English snake_case: `bench_number`, `segment_type`, `distance_m`, `elevation_m`, `is_ramp`, `source`. `is_ramp` SHALL be true for ramp points. When `benches` is supplied, the dataframe SHALL add `overhang_m`, `wedge_risk`, and `toppling_risk` by bench number, using `NaN`/`False` when a value is absent.

#### Scenario: empty profile dataframe

- GIVEN an empty profile
- WHEN `to_dataframe()` is called
- THEN it returns the documented base columns and `0` rows.

#### Scenario: CSV round trip

- GIVEN a populated profile
- WHEN `to_dataframe().to_csv(index=False)` is read back
- THEN row count and base column values match the original dataframe.

### Requirement: ReconciledProfile.to_dict round trip

`ReconciledProfile` SHALL expose `to_dict() -> dict` and `from_dict(d) -> ReconciledProfile`. The dict SHALL be JSON-serializable and include `distances: list[float]`, `elevations: list[float]`, `points: list[dict]`, and `source: str`. Each point dict SHALL include `bench_number`, `segment_type`, `distance_m`, `elevation_m`, `is_ramp`, and `source`; optional hazard fields MAY be omitted when absent.

#### Scenario: JSON round trip

- GIVEN a populated profile
- WHEN `from_dict(json.loads(json.dumps(profile.to_dict())))` is called
- THEN distances, elevations, points, and source are preserved.

### Requirement: Canonical v2 import and legacy deprecation

`core/__init__.py` SHALL export `build_reconciled_profile_v2` while preserving the legacy `build_reconciled_profile` export, signature, and tuple output. The legacy builder SHALL emit `DeprecationWarning` with `stacklevel=2` on legacy calls, and the warning/docstring SHALL mention `build_reconciled_profile_v2` and `scheduled for removal in 2 release cycles`.

#### Scenario: imports remain compatible

- GIVEN the published `core` package
- WHEN `from core import build_reconciled_profile, build_reconciled_profile_v2` is executed
- THEN both imports succeed, and the legacy import is the same object as `core.param_extractor.build_reconciled_profile`.

#### Scenario: legacy warning without tuple drift

- GIVEN benches accepted by the legacy builder
- WHEN `build_reconciled_profile(benches)` is called
- THEN a matching `DeprecationWarning` is emitted
- AND the returned `(distances, elevations)` tuple is byte-for-byte identical to the pre-change legacy output.

## Legacy API Compatibility

This capability SHALL be additive-only. `web/`, `api/`, `app.py`, `ui/`, `cli.py`, tests, and `openspec/specs/` (other than this domain) SHALL NOT be modified by changes touching this capability. `core/__init__.py` changes SHALL only add the v2 re-export and SHALL NOT remove legacy exports.

## Design Note

`core.ai_v2.builder.py` does not consume `ReconciledProfile`; it consumes `BenchParams` from comparison rows. Therefore this spec does not require a persistent optional `ReconciledProfile.benches` field. Hazard enrichment is specified through method-level `benches` arguments and can be revisited in a future change if a stored field is still desired.