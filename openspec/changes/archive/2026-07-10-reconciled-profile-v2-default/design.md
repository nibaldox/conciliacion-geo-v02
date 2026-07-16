# Design: reconciled-profile-v2-default

## 1. Goals and non-goals

Three outcomes: (a) `from core import build_reconciled_profile_v2` resolves; (b) the legacy `build_reconciled_profile(...)` keeps emitting `DeprecationWarning` whose message hardcodes the v2 successor and `scheduled for removal in 2 release cycles`; (c) `ReconciledProfile` gains `summary()`, `to_dataframe()`, and a `to_dict()` / `from_dict()` round-trip pair.

Non-goals: no removal of the legacy builder; no signature or return-value change; no new field on `ReconciledProfile`; no edits in `web/`, `api/`, `app.py`, `ui/`, `cli.py`, `tests/`, `docs/`; no wiring of `summary()` into `excel_writer` / `report_generator`. Hazard enrichment is method-level — the spec's design note intentionally drops the persistent field.

## 2. Current architecture

```
load_mesh → cut_mesh_with_section → extract_parameters
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
   build_reconciled_profile(benches,  build_reconciled_profile_v2(
      return_v2=False)                      benches, source, profile)
      → DeprecationWarning                  → ReconciledProfile
      → (np.array, np.array)                  (rich)
```

`core/__init__.py` exposes the legacy builder only; `core/param_extractor.py` re-exports both. `ReconciledProfile` lives at `core/profile_extract.py:77-88` with zero serialization helpers.

## 3. Proposed changes

### 3.1 `core/__init__.py`

Add `build_reconciled_profile_v2` to the existing `from core.param_extractor import (...)` block and to `__all__` (alphabetical, before `compare_design_vs_asbuilt`). Nothing removed.

### 3.2 `core/profile_compliance.py::build_reconciled_profile`

Function lives here (lines 56-130); `core/param_extractor.py` only re-exports. Edits:

- **Keep warning conditional on `return_v2=False`** — internal `build_reconciled_profile_v2(benches)` calls this with `return_v2=True`; unconditional would falsely flag v2.
- **Update warning text** (lines 99-101) — hardcode v2 successor + 2-cycle horizon. Category + `stacklevel=2` unchanged (tests assert category: `tests/test_param_extractor.py:144-158`, `tests/test_process_reconciled_alignment.py:324`).
- **Update docstring** (lines 59-96) — add `.. deprecated::` block; refresh "Notes" with horizon.
- **Return value unchanged** — byte-for-byte identity: empty input → `(np.array([]), np.array([]))`; otherwise sorted-by-distance.

New `warnings.warn(...)` body:

> "build_reconciled_profile(return_v2=False) is deprecated and
> scheduled for removal in 2 release cycles. Use
> build_reconciled_profile_v2(benches, source, profile), now
> re-exported from `core`, instead."

### 3.3 `core/profile_extract.py::ReconciledProfile`

Dataclass frozen. Add `import json, math` at module top; append four methods + 1 classmethod after line 88.

- **`summary(self, benches=None) -> dict`** — flat JSON-safe; `.item()` / `float(...)` coerce numpy scalars. With `benches=None`: `n_benches`, `n_ramps`, `n_overhangs=0`, `n_wedge_risks=0`, `n_toppling_risks=0`, `n_consensus_benches=n_benches`, `height_range_m=[0.0,0.0]` (or `[min,max]`), `total_berm_width_m=0.0`, `avg_face_angle_deg=None`, `max_overhang_m=0.0`, `source`. The `None` (not `math.nan`) for `avg_face_angle_deg` is required by the spec for strict-JSON consumers — `json.dumps(s, allow_nan=False)` MUST succeed. With `benches`: hazards read `overhang_m` / `wedge_risk` / `toppling_risk` (confirmed on `BenchParams`, `core/profile_extract.py:110-117`).
- **`to_dataframe(self) -> pd.DataFrame`** — one row per `ReconciledPoint`. Fixed columns: `bench_number`, `segment_type`, `distance_m`, `elevation_m`, `is_ramp`, `source`. `is_ramp = (segment_type == "ramp")`.
- **`to_dict(self) -> dict`** — `distances: list[float]`, `elevations: list[float]`, `points: list[{bench_number, segment_type, distance_m, elevation_m, is_ramp, source}]`, `source: str`; passes `json.dumps`.
- **`from_dict(cls, d)`** — classmethod; inverse of `to_dict`; unknown fields silently dropped.

## 4. Data flow

```
extract_parameters → list[BenchParams] → build_reconciled_profile_v2(...) → ReconciledProfile
                                                            │
                         ┌──────────────────┬────────────────┴───────────────────┐
                         ▼                  ▼                  ▼                  ▼
                     summary()         to_dataframe()       to_dict()    .distances/.elevations
                         │                  │                  │                  │
                         ▼                  ▼                  ▼                  ▼
                       dict            pd.DataFrame      dict (json-safe)    np.ndarray
```

Legacy `(np.array, np.array)` path is a sibling — untouched.

## 5. File-by-file diff

| File | Action | Δ | Risk |
|---|---|---|---|
| `core/__init__.py` | add re-export + `__all__` entry | +2 | none |
| `core/profile_compliance.py` | warn text + docstring | +5 | very low (conditional) |
| `core/profile_extract.py` | 4 methods + 2 imports | +85 | low (dataclass body) |
| `tests/test_reconciled_profile_serialization.py` | new | +250 | none |
| `openspec/changes/ACTIVE.md` | tick row | ±1 | none |
| **Total** | | **~345** | within 400-line budget |

## 6. Test strategy

New `tests/test_reconciled_profile_serialization.py` (~250 lines). Reuses `_bench(...)` from `tests/test_reconciled_berm_top_descent.py:22-45`. Six test classes:

- **`Summary`** — empty + populated counts; JSON-safe (including `json.dumps(s, allow_nan=False)` for the no-benches path); no numpy scalars leak; `avg_face_angle_deg is None` without benches (per spec).
- **`ToDataframe`** — empty + populated English snake_case columns; CSV round-trip via `pd.read_csv(io.StringIO(df.to_csv(index=False)))` matches.
- **`ToFromDict`** — exact key shape; `json.dumps` clean; full round-trip preserves fields; `from_dict({})` empty.
- **`LegacyDeprecationWarning`** — `return_v2=False` emits `DeprecationWarning` containing both `build_reconciled_profile_v2` AND `2 release cycles`; `return_v2=True` emits none.
- **`CoreReExportsV2`** — both names importable from `core`; both in `core.__all__`; identity match vs `core.param_extractor`.
- **`LegacyTupleContractPreserved`** — 3-bench fixture returns `(np.array, np.array)` with `dtype == float`; `np.allclose` against frozen snapshot.

## 7. Risk and mitigations

- **numpy scalar leakage** → `.item()` / `float(...)` in every helper; `test_summary_dict_is_json_serializable` enforces.
- **Warning on v2 path** → guarded by `if not return_v2:`; new test asserts no emission when `return_v2=True`.
- **Existing test callers** → `tests/test_process_reconciled_alignment.py:28` already uses `filterwarnings("ignore::DeprecationWarning")`; `pyproject.toml:37-39` does NOT set `-W error::DeprecationWarning`.
- **`ReconciledProfile.benches` not stored** → hazard counters default to `0`/`0.0`; documented in `summary()` docstring.
- **Pandas import** → hard dep (`pyproject.toml:19`); already in 6 sibling modules.


## 8. Rollback

Single-commit revert. Re-export + four new methods are additive; only the deprecation text changes. Callers can `warnings.simplefilter("ignore", DeprecationWarning)` locally. No migrations, schema, or fixture edits.


## 9. Out of scope

Removing `build_reconciled_profile` (future); persisting `ReconciledProfile.benches` (spec dropped); wiring `summary()` into `excel_writer` / `report_generator` / `api/`; Streamlit / React / CLI / FastAPI surface; mesh-edge warnings, Excel "Rampas" sheet, design↔as-built matching by elevation, max-berm per sector.


## 10. Open questions

None — spec resolvable from source. `BenchParams` fields confirmed (`core/profile_extract.py:96-122`); pandas dep confirmed; warning strategy compatible with existing pytest markers.


