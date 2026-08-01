# Delta for reconciled-profile-serialization

## MODIFIED Requirements

### Requirement: ReconciledProfile.summary

`ReconciledProfile` SHALL expose `summary(benches=None) -> dict` with keys `n_benches`, `n_ramps`, `n_overhangs`, `n_wedge_risks`, `n_toppling_risks`, `n_consensus_benches`, `height_range_m`, `total_berm_width_m`, `avg_face_angle_deg`, `max_overhang_m`, `source`, `local_angle_method`, `advisory`, `confidence`, `volume_m3`.

Without `benches`: hazards `0`, `n_consensus_benches = n_benches`, `avg_face_angle_deg = None`, width/overhang totals `0.0`. Values MUST NOT expose numpy scalars/dataclasses. `height_range_m` SHALL be a `(min, max)` tuple. `local_angle_method` SHALL be a per-bench face-fit from ONLY that bench's face points; MUST NOT inherit/derive from section azimuth; unavailable SHALL be `None` (`INSUFFICIENT_DATA`); no invented enum default. `advisory` SHALL be an advisory dict, MUST NEVER alter verdict; `None` when absent. `confidence` SHALL be `HIGH | MEDIUM | LOW | INSUFFICIENT`. `volume_m3` SHALL be signed area/volume from `bench-area-volume` when supplied, else `None`.

(Previously: those fields were not in the contract; local angle was not tied to a method label.)

#### Scenario: empty profile

- GIVEN `ReconciledProfile(distances=[], elevations=[], points=[])`
- WHEN `summary()` is called
- THEN numeric fields equal `0` or `None`; `local_angle_method` is `None`; `json.dumps` ok

#### Scenario: enriched benches

- GIVEN a profile with two unique bench numbers, one ramp point, benches with overhang/wedge/toppling
- WHEN `summary(benches=benches)` is called
- THEN bench/ramp/hazard/berm-width/face-angle/max-overhang, `local_angle_method`, `volume_m3` reflect supplied benches; verdict unchanged

#### Scenario: advisory never alters verdict

- GIVEN a bench with `score >= 70` and an `UNFAVORABLE` wedge advisory
- WHEN `summary(benches=benches)` is called
- THEN verdict stays `CUMPLE`; advisory under `advisory` only

### Requirement: ReconciledProfile.to_dataframe

`ReconciledProfile` SHALL expose `to_dataframe(benches=None) -> pandas.DataFrame` (one row per `ReconciledPoint`). Base columns SHALL be `bench_number`, `segment_type`, `distance_m`, `elevation_m`, `is_ramp`, `source`, `local_angle_method`, `volume_m3`. With `benches`, SHALL add `overhang_m`, `wedge_risk`, `toppling_risk`, `advisory`, `confidence` by bench number (`NaN`/`False` when absent). `is_ramp` SHALL mark ramp points.

(Previously: those columns were not in the dataframe.)

#### Scenario: empty profile dataframe

- GIVEN an empty profile
- WHEN `to_dataframe()` is called
- THEN it returns base columns; `0` rows.

#### Scenario: CSV round trip

- GIVEN a populated profile
- WHEN `to_dataframe().to_csv(index=False)` is read back
- THEN row count and base values match.

### Requirement: ReconciledProfile.to_dict round trip

`ReconciledProfile` SHALL expose `to_dict() -> dict` and `from_dict(d) -> ReconciledProfile`. Dict SHALL be JSON-serializable with `distances: list[float]`, `elevations: list[float]`, `points: list[dict]`, `source: str`. Each point SHALL include `bench_number`, `segment_type`, `distance_m`, `elevation_m`, `is_ramp`, `local_angle_method`, `source`; optional fields MAY be omitted. The pair SHALL round-trip new fields losslessly.

(Previously: those fields were not in the round-trip contract.)

#### Scenario: JSON round trip

- GIVEN a populated profile
- WHEN `from_dict(json.loads(json.dumps(profile.to_dict())))` runs
- THEN distances, elevations, points, source, `local_angle_method`, advisory, confidence, volume all survive

#### Scenario: optional fields omitted

- GIVEN a populated profile without advisory, confidence, volume
- WHEN `to_dict()` is called
- THEN the dict SHALL NOT contain them; `from_dict` restores an equivalent profile.

### Requirement: v2 import path and legacy import stability

`build_reconciled_profile_v2` SHALL be imported only from `core.param_extractor`; it SHALL NOT be re-exported from `core/__init__.py`. Legacy `from core import build_reconciled_profile` SHALL keep signature and tuple behavior byte-for-byte unchanged. Legacy MAY emit the existing `DeprecationWarning` (`stacklevel=2`) pointing to `build_reconciled_profile_v2`; no removal timeline, no promise to delete it. Legacy SHALL round-trip (`advisory`, `confidence`, `volume_m3`) losslessly via v2.

(Previously: legacy did not formally round-trip new optional fields; no removal timeline was implied.)

#### Scenario: imports remain compatible

- GIVEN the published `core` package
- WHEN `from core import build_reconciled_profile` and `from core.param_extractor import build_reconciled_profile_v2` are executed
- THEN both imports succeed; legacy equals `core.param_extractor.build_reconciled_profile`; v2 is NOT in `core.__init__`

#### Scenario: legacy warning without tuple drift

- GIVEN benches with optional advisory, confidence, volume fields
- WHEN `build_reconciled_profile(benches)` is called
- THEN `DeprecationWarning` is emitted, returned `(distances, elevations)` matches pre-change output, optional fields round-trip via v2

## Legacy API Compatibility

Additive-only. `web/`, `api/`, `app.py`, `ui/`, `cli.py`, tests, other `openspec/specs/` SHALL NOT change. `core/__init__.py` SHALL remain byte-unchanged (no v2 re-export, no signature changes, no removal of legacy re-export). `local_angle_method`, `advisory`, `confidence`, `volume_m3` are additive.

(Previously: covered additive-only changes; now pins `core/__init__.py` as untouched.)