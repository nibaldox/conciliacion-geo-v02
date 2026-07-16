# Tasks: reconciled-profile-v2-default

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~345 (additions only) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-always |
| Chain strategy | pending |
| Decision needed before apply | No |
| Chained PRs recommended | No |
| Chain strategy | size-exception |
| 400-line budget risk | Low |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

> Forecast is ~345 LOC additions, ~15% margin under the 400-line budget. Single
> PR with the orchestrator-accepted additive scope is appropriate. Delivery
> strategy is `ask-always`, but since the budget is **not** exceeded, no
> pre-apply decision is required.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | canonical import + deprecation text + serialization methods + tests | PR 1 | single PR to `main`; tests committed alongside code (work-unit-commits) |

## Phase 1: Backend Core (`core/` additive mod)

- [x] 1.1 In `core/__init__.py`, add `build_reconciled_profile_v2` to the existing `from core.param_extractor import (...)` block and to `__all__`. Alphabetical position: before `compare_design_vs_asbuilt`. Nothing removed.
- [x] 1.2 In `core/profile_compliance.py`, harden `build_reconciled_profile`: replace the `"... preserved for one release cycle ..."` docstring tail with `.. deprecated:: 2 release cycles; use ``build_reconciled_profile_v2`` instead`, and replace the `warnings.warn(...)` body (lines 99-101) with `"build_reconciled_profile(return_v2=False) is deprecated and scheduled for removal in 2 release cycles. Use build_reconciled_profile_v2(benches, source, profile), now re-exported from core, instead."`. Keep category `DeprecationWarning`, keep `stacklevel=2`, keep the warning conditional on `return_v2=False`.
- [x] 1.3 In `core/profile_extract.py`, append four methods to `ReconciledProfile` (no new dataclass field per spec design note) and add `import json, math` at module top:
  - `summary(self, benches=None) -> dict` — flat JSON-safe; coerce numpy scalars with `.item()` / `float(...)`. With `benches=None`: `n_consensus_benches == n_benches`, `avg_face_angle_deg = math.nan`. With `benches`: enrich from `overhang_m` / `wedge_risk` / `toppling_risk` / `n_detection_methods_agreeing` / `is_ramp` / `face_angle` / `berm_width`.
  - `to_dataframe(self, benches=None) -> pd.DataFrame` — columns `bench_number, segment_type, distance_m, elevation_m, is_ramp, source`; `is_ramp = (segment_type == "ramp")`. With `benches`: append `overhang_m, wedge_risk, toppling_risk` by bench-number match (NaN/False when absent).
  - `to_dict(self) -> dict` — keys `distances, elevations, points, source`; JSON-serializable.
  - `from_dict(cls, d) -> ReconciledProfile` — inverse of `to_dict`; silently drops unknown fields.
- [x] 1.4 Run `pytest tests/test_reconciled_profile_serialization.py tests/test_param_extractor.py tests/test_profile_compliance.py tests/test_process_reconciled_alignment.py -v --tb=short` after each sub-step to confirm legacy behavior is byte-for-byte unchanged.

## Phase 2: Backend Tests (`tests/` new file)

- [x] 2.1 Create `tests/test_reconciled_profile_serialization.py`. Six test classes following design §6: `Summary`, `ToDataframe`, `ToFromDict`, `LegacyDeprecationWarning`, `CoreReExportsV2`, `LegacyTupleContractPreserved`. Reuse the `_bench(...)` fixture pattern from `tests/test_reconciled_berm_top_descent.py:22-45`. Cover: empty profile, populated profile, JSON safety (no numpy scalars), CSV round-trip via `pd.read_csv(io.StringIO(df.to_csv(index=False)))`, `json.loads(json.dumps(d))` round-trip, `from_dict({})` empty, `DeprecationWarning` on `return_v2=False` carrying both `build_reconciled_profile_v2` and `2 release cycles`, no warning on `return_v2=True`, `core.__all__` membership, identity match vs `core.param_extractor`, and `np.allclose` against frozen legacy tuple fixtures.
- [x] 2.2 Run `pytest tests/ -v --tb=short` (full suite, exclude `tests/test_openblast.py` if openblast missing) and `python test_pipeline.py` (synthetic E2E smoke). Both MUST pass before declaring phase done.

## Phase 3: Orchestration / Tracking

- [x] 3.1 In `openspec/changes/ACTIVE.md`, tick the `Tasks` cell for `reconciled-profile-v2-default` and advance the `Phase` column from `design` to `tasks`. Do not touch the broken `spec.md` link cell — that is the orchestrator's responsibility.

## Phase 4: Post-verify CRITICAL-1 remediation

> Triggered by `verify-report.md` CRITICAL-1 (spec violation on
> `avg_face_angle_deg`). Surgical fix; no behavior change beyond the
> no-benches branch of `ReconciledProfile.summary`.

- [x] 4.1 In `core/profile_extract.py`, replace `"avg_face_angle_deg": math.nan,` with `"avg_face_angle_deg": None,` in the `benches is None` branch of `ReconciledProfile.summary()` (line 133). Update the method docstring (lines 104-110) to document the spec-correct `None` value and the strict-JSON contract.
- [x] 4.2 In `tests/test_reconciled_profile_serialization.py`, rename `test_no_benches_arg_avg_face_is_nan` to `test_no_benches_arg_avg_face_is_none` and replace the `isinstance(..., float)` + `math.isnan(...)` pair with `assert s["avg_face_angle_deg"] is None`.
- [x] 4.3 In `tests/test_reconciled_profile_serialization.py::test_summary_is_json_serializable_no_benches`, change `json.dumps(s)` to `json.dumps(s, allow_nan=False)` so the no-benches path is exercised under strict-JSON mode (catches any future `NaN`/`Infinity` leak), and add `assert decoded["avg_face_angle_deg"] is None`.
- [x] 4.4 In `openspec/changes/reconciled-profile-v2-default/design.md` section 3.3, replace `avg_face_angle_deg=math.nan` with `avg_face_angle_deg=None` (spec-authoritative value). Section 6 ("Summary" test description) updated likewise. No other artifact changes.
- [x] 4.5 Re-run `pytest tests/test_reconciled_profile_serialization.py -v --tb=short` (expect 27/27) and the full suite `pytest tests/ --ignore=tests/test_openblast.py` (expect 795 passed / 2 skipped / 2 pre-existing `test_api_auth` failures — confirmed unrelated). Update `apply-progress` observation id 49 with the merged batch.

## Out-of-scope guardrails (do NOT touch)

- `app.py`, `ui/`, `cli.py`, `web/`, `api/`, `docs/`, `excel_writer`, `report_generator`, `tests/test_openblast.py`, `core/param_extractor.py`.
- No removal of `build_reconciled_profile` legacy. No signature change. No behavior change to the legacy `(np.array, np.array)` tuple.

## Verification commands

```bash
pytest tests/ -v --tb=short          # full backend suite (~772+ collected)
python test_pipeline.py              # synthetic E2E smoke
pytest tests/test_reconciled_profile_serialization.py -v --tb=short   # new file only
```