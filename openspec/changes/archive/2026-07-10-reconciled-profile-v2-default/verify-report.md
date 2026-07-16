# Verify Report: `reconciled-profile-v2-default`

> **Verifier**: `sdd-verify` (sdd-verify sub-agent)
> **Project**: `conciliacion-geo-v02`
> **Mode**: standard (Strict TDD OFF)
> **Persistence**: openspec + engram
> **Date**: 2026-07-10

---

## TL;DR

**Status**: `fail`
**Recommendation**: `needs-fix-then-archive`
**CRITICAL**: 1 — spec violation on `avg_face_angle_deg` value when `benches` is absent (spec requires `None`, implementation returns `math.nan`)
**WARNING**: 2 — LOC budget overrun (~636 vs ~345 forecast, +91% over); design-vs-spec inconsistency on `avg_face_angle_deg` semantic choice
**SUGGESTION**: 1 — test name/assertion should mirror spec contract
**Pre-existing failures** (out of scope, confirmed unrelated): `tests/test_api_auth.py::test_no_auth_when_env_var_unset`, `tests/test_api_auth.py::test_auth_with_correct_key` (sqlite3 "no such table: sessions")

---

## Test Execution Summary

| Suite | Passed | Failed | Skipped | Notes |
|---|---|---|---|---|
| `tests/test_reconciled_profile_serialization.py` (new) | **27/27** | 0 | 0 | All six test classes green. |
| Targeted legacy subset (`test_param_extractor`, `test_profile_compliance`, `test_process_reconciled_alignment`, `test_reconciled_berm_top_descent`) | **100/100** | 0 | 0 | Legacy tuple byte-for-byte identity preserved. |
| Full suite `pytest tests/ --ignore=tests/test_openblast.py` | **795/797** | 2 | 2 | Two `test_api_auth` failures pre-existing (sqlite "no such table: sessions" — confirmed on clean checkout via `git stash`). |
| `python test_pipeline.py` (E2E smoke) | OK | — | — | Generates `/tmp/test_conciliacion.xlsx` + `/tmp/test_report.docx`. |

---

## Completeness Table

| Artifact | Status | Notes |
|---|---|---|
| `proposal.md` | present | 245 lines, scope/budget/risks/rollback complete. |
| `specs/reconciled-profile-serialization/spec.md` | present | 4 ADDED Requirements with 8 Scenarios. |
| `design.md` | present | 114 lines, 10 sections. |
| `tasks.md` | present | All 5 implementation task checkboxes ticked `[x]`. |
| `core/__init__.py` | modified (additive) | `build_reconciled_profile_v2` added to import block and `__all__`. |
| `core/profile_compliance.py` | modified (additive) | Docstring + warning text updated. Warning conditional on `return_v2=False`. |
| `core/profile_extract.py` | modified (additive) | `summary()`, `to_dataframe()`, `to_dict()`, `from_dict()` added. No dataclass field added (per spec design note). |
| `tests/test_reconciled_profile_serialization.py` | new | 454 lines, 6 test classes, 27 tests. |
| `openspec/changes/ACTIVE.md` | updated | Phase column shows `apply`, Apply cell ticked ✓. |

---

## Spec Compliance Matrix

| Spec requirement / scenario | Implementation evidence | Test coverage | Status |
|---|---|---|---|
| `ReconciledProfile.summary(benches=None)` flat JSON-safe dict | `core/profile_extract.py:93-164` returns 11 required keys | `TestSummary.test_empty_profile_returns_zero_counts`, `test_no_benches_arg_avg_face_is_nan` | **PARTIAL** — `avg_face_angle_deg` returns `math.nan` instead of spec-required `None` (see CRITICAL-1) |
| `summary()` JSON-serializable | `json.dumps` succeeds on returned dict | `test_summary_is_json_serializable_no_benches`, `test_summary_is_json_serializable_with_benches` | pass |
| `summary()` no numpy scalars/dataclasses leak | All values coerced with `int(...)`, `float(...)`, `bool(...)` | `test_summary_has_no_numpy_scalar_leak` | pass |
| `height_range_m` is `(min, max)` tuple before JSON | Tuple of `float`s returned | `test_summary_is_json_serializable_no_benches` | pass |
| `summary(benches=...)` enriches hazards | Reads `overhang_m` / `wedge_risk` / `toppling_risk` / `n_detection_methods_agreeing` / `berm_width` / `face_angle` from `BenchParams` | `test_enriched_with_benches` | pass |
| `to_dataframe()` English snake_case base columns | `core/profile_extract.py:190-194` returns exactly `[bench_number, segment_type, distance_m, elevation_m, is_ramp, source]` | `test_empty_profile_dataframe_shape`, `test_populated_columns_and_dtypes` | pass |
| `is_ramp` true for ramp points | `is_ramp = (segment_type == "ramp")` | `test_populated_columns_and_dtypes` | pass |
| Hazard columns added when `benches` supplied | `to_dataframe.py:196-213` adds `overhang_m` / `wedge_risk` / `toppling_risk` | `test_to_dataframe_with_benches_adds_hazard_columns` | pass |
| Missing bench number → NaN/False defaults | `math.nan` for `overhang_m`, `False` for risks | `test_to_dataframe_benches_missing_bench_number_yields_defaults` | pass |
| CSV round-trip via `pd.read_csv(io.StringIO(df.to_csv(index=False)))` | Frame-equal after round-trip | `test_csv_round_trip_preserves_rows_and_columns` | pass |
| `to_dict()` keys `distances, elevations, points, source` | `core/profile_extract.py:217-243` | `test_to_dict_key_shape` | pass |
| `from_dict()` inverse of `to_dict()`; drops unknown fields | `core/profile_extract.py:245-265`; uses `.get(..., default)` | `test_from_dict_empty`, `test_from_dict_drops_unknown_fields`, `test_round_trip_preserves_fields` | pass |
| `from core import build_reconciled_profile_v2` works | `core/__init__.py:11` + `__all__:20` | `TestCoreReExportsV2.test_both_importable_from_core`, `test_both_in_core_all` | pass |
| Legacy `build_reconciled_profile` export preserved + identity match | Same object as `core.param_extractor.build_reconciled_profile` | `test_legacy_identity_match_vs_param_extractor`, `test_param_extractor_module_reexports_v2` | pass |
| Legacy deprecation warning emitted with v2 successor + 2-cycle horizon | `core/profile_compliance.py:101-108` message contains both substrings | `TestLegacyDeprecationWarning.test_warning_emitted_on_legacy_call` | pass |
| No DeprecationWarning when `return_v2=True` | Warning guarded by `if not return_v2:` | `test_no_warning_when_return_v2_true` | pass |
| `stacklevel=2` (warning attribution to caller) | `stacklevel=2` literal in warn call; test asserts filename ends with test file | `test_warning_stacklevel_is_two` | pass |
| Legacy `(np.array, np.array)` tuple byte-for-byte identity | `core/profile_compliance.py:109-119` unchanged | `test_three_bench_tuple_shape_and_dtype`, `test_three_bench_frozen_snapshot`, `test_empty_input_returns_empty_float_arrays` | pass |
| Additive-only: no edits in `web/`, `api/`, `app.py`, `ui/`, `cli.py` | `git diff --stat` confirms only `core/`, `AGENTS.md` (pre-existing uncommitted), `tests/test_reconciled_profile_serialization.py` (new), `openspec/` | n/a | pass |

---

## Issues

### CRITICAL — blocks archive readiness

#### CRITICAL-1: Spec violation — `avg_face_angle_deg` returns `math.nan` instead of `None`

- **Spec** (`openspec/changes/reconciled-profile-v2-default/specs/reconciled-profile-serialization/spec.md` line 11):
  > Without benches, hazard counts SHALL be `0`, `n_consensus_benches` SHALL equal `n_benches`, **`avg_face_angle_deg` SHALL be `None`**, and width/overhang totals SHALL be `0.0`.
- **Design** (`openspec/changes/reconciled-profile-v2-default/design.md` section 3.3): `avg_face_angle_deg=math.nan`
- **Implementation** (`core/profile_extract.py:132`): `"avg_face_angle_deg": math.nan,`
- **Test** (`tests/test_reconciled_profile_serialization.py:109-117`): `assert math.isnan(s["avg_face_angle_deg"])` — test name `test_no_benches_arg_avg_face_is_nan` also asserts the design choice
- **Runtime evidence**:
  ```
  >>> prof.summary()
  {... 'avg_face_angle_deg': nan, ...}
  >>> json.loads(json.dumps(prof.summary()))['avg_face_angle_deg']
  nan  # ← Python's lenient encoder accepted NaN as 'NaN' literal; non-standard JSON
  ```

**Why critical**: RFC 2119 SHALL is normative. The spec is the authoritative contract per `sdd-verify` hard rules ("Compare specs first, design second, task completion third"). Implementation silently diverged from the contract. Side effect: `json.dumps` produces non-standard JSON (`"NaN"` literal) instead of `"null"`, breaking strict-JSON consumers (the spec says "Values MUST NOT expose numpy scalars or dataclasses" — implying standards-compliant JSON).

**Required fix**:
1. In `core/profile_extract.py:132`, replace `"avg_face_angle_deg": math.nan,` with `"avg_face_angle_deg": None,`.
2. In `tests/test_reconciled_profile_serialization.py:109-117`, rename `test_no_benches_arg_avg_face_is_nan` → `test_no_benches_arg_avg_face_is_none` and replace:
   ```python
   assert isinstance(s["avg_face_angle_deg"], float)
   assert math.isnan(s["avg_face_angle_deg"])
   ```
   with:
   ```python
   assert s["avg_face_angle_deg"] is None
   ```
3. Add a strict-JSON assertion to `test_summary_is_json_serializable_no_benches`:
   ```python
   encoded = json.dumps(s, allow_nan=False)  # MUST succeed under strict mode
   ```
4. Update design.md section 3.3 to match the corrected spec interpretation (or amend the spec if `math.nan` was intended — but spec is the contract; fix the design and code, not the spec).

### WARNING — reviewer concerns, do not block

#### WARNING-1: Total LOC budget overrun (~636 vs ~345 forecast, +91%)

- Design forecast: ~345 LOC additions (section 5).
- Actual (excluding pre-existing uncommitted `AGENTS.md` changes — `git diff --stat`):
  - `core/__init__.py`: +3 lines (forecast +2)
  - `core/profile_compliance.py`: +4 lines net (forecast +5)
  - `core/profile_extract.py`: +177 lines (forecast +85)
  - `tests/test_reconciled_profile_serialization.py`: 454 lines new (forecast ~250, **+204**)
- 400-line review budget was breached by ~60%. Apply-progress observation id 49 self-disclosed this as a "review-burden concern" but justified the size as comprehensive edge-case coverage.
- **Classification**: WARNING (not CRITICAL) — 400-line budget is a process guardrail, not a spec requirement. Code changes are still additive and tightly scoped.

#### WARNING-2: Design-vs-spec inconsistency on `avg_face_angle_deg` semantic choice

- **Design** (section 3.3) chose `math.nan`; **Spec** (line 11) requires `None`. Both were authored in the same change. The conflict was not flagged at design time.
- **Classification**: WARNING — surfaces the same root cause as CRITICAL-1 but at the artifact-quality level. Either the design rationale should be written into the spec (`.. note:: rationale for NaN vs None`) or the implementation should follow the spec. CRITICAL-1 above resolves it; this warning captures the upstream authoring process gap.

### SUGGESTION — improvement

#### SUGGESTION-1: Test naming/assertion asymmetry

- The test `test_no_benches_arg_avg_face_is_nan` couples the test name to the implementation choice rather than the spec contract. Tests should be named after the contract they verify (`..._is_none_per_spec` or simply `..._returns_none_when_no_benches`). Same root cause as CRITICAL-1; flagging separately because future test additions in this file should follow the spec contract, not mirror the implementation.
- **Classification**: SUGGESTION — resolves itself when CRITICAL-1 is fixed.

---

## Pre-existing failures (out of scope — confirmed unrelated)

```
tests/test_api_auth.py::test_no_auth_when_env_var_unset — sqlite3.OperationalError: no such table: sessions
tests/test_api_auth.py::test_auth_with_correct_key       — sqlite3.OperationalError: no such table: sessions
```

- Verified via `git stash --keep-index --include-untracked` (clean working tree at HEAD `877feed`) — both failures reproduce.
- Failure occurs in `api/routers/sections.py:181` → `api/database.py:105` — files not touched by this change.
- Triage in a separate change.

---

## Design Coherence Notes

- **Field ordering in `to_dataframe()`**: Implementation correctly puts hazard columns **after** the base six columns (lines 211-213), preserving the documented base shape. ✓
- **`ReconciledProfile.benches` field absent**: Spec design note explicitly drops the persistent field; implementation correctly uses method-level `benches` parameter. ✓
- **Pandas hard dependency**: Imported at module top (`core/profile_extract.py:22`). Confirmed hard dep via existing usage in 8 sibling `core/` modules. ✓
- **JSON strictness**: `json.dumps` accepts `math.nan` by default (Python leniency) but produces non-standard JSON. This compounds CRITICAL-1. Should be tested with `allow_nan=False` after fix.

---

## Files Changed by This Verification (none — read-only)

This was a read-only verification pass. No edits performed.

---

## Final Verdict

**FAIL** — 1 CRITICAL spec violation must be fixed before archive.

**Recommendation**: `needs-fix-then-archive`. After CRITICAL-1 is remediated (two-line code change + test update + design.md alignment), this change becomes archive-ready. WARNING-1 (LOC overrun) and WARNING-2 (design-vs-spec inconsistency) are advisory and resolve as side effects of the CRITICAL-1 fix.

---

## Return Envelope

- **status**: `partial`
- **executive_summary**: Verification surfaced one CRITICAL spec violation: `ReconciledProfile.summary()` returns `math.nan` for `avg_face_angle_deg` when `benches` is absent, but the spec (line 11) requires `None`. All 27 new tests pass and the full pytest suite is green except for two pre-existing `test_api_auth` failures (unrelated, confirmed on clean checkout). Implementation otherwise matches spec, design, and tasks across all 8 scenarios.
- **artifacts**: `openspec/changes/reconciled-profile-v2-default/verify-report.md` (this file)
- **next_recommended**: `sdd-apply` (or `sdd-spec` amendment) to fix CRITICAL-1, then re-run `sdd-verify`; after green, `sdd-archive`.
- **risks**: One spec-authoritative normative violation (CRITICAL-1); one process guardrail breach (WARNING-1, ~60% over 400-line budget).
- **skill_resolution**: `paths-injected` — orchestrator provided exact skill paths; `sdd-verify` + `_shared/sdd-phase-common.md` loaded.

---

# Re-Verification Pass — 2026-07-10 (CRITICAL-1 surgical fix batch)

> **Verifier**: `sdd-verify` (re-running after surgical fix batch)
> **Mode**: standard (Strict TDD OFF)
> **Persistence**: openspec + engram
> **Trigger**: `apply` reported a 5-sub-task fix batch addressing CRITICAL-1

## TL;DR (re-verify)

**Status**: `pass-with-warnings`
**Recommendation**: `ready-to-archive`
**CRITICAL**: **0** (CRITICAL-1 resolved)
**WARNING**: **1 retained** (WARNING-1, LOC budget overrun — process note, not spec violation)
**SUGGESTION**: **1 new** (`tasks.md` Phase 1.3 description still has stale `math.nan` text, superseded by Phase 4 — minor artifact-internal inconsistency)

---

## CRITICAL-1 resolution evidence

### Code (`core/profile_extract.py`)

- Line 133: `"avg_face_angle_deg": None,` — was `math.nan` before fix. ✅
- Lines 104–110 (docstring): documents `avg_face_angle_deg` to `None` with explicit strict-JSON contract note. ✅
- Runtime probe:
  ```
  >>> from core.profile_extract import ReconciledProfile
  >>> prof = ReconciledProfile(distances=np.array([]), elevations=np.array([]), points=[])
  >>> s = prof.summary()
  >>> s['avg_face_angle_deg']
  None
  >>> json.dumps(s, allow_nan=False)
  '{"n_benches": 0, ..., "avg_face_angle_deg": null, ...}'   # ← strict JSON OK
  ```

### Tests (`tests/test_reconciled_profile_serialization.py`)

- Line 109: test renamed `test_no_benches_arg_avg_face_is_nan` → **`test_no_benches_arg_avg_face_is_none`**. ✅
- Line 112: `assert s["avg_face_angle_deg"] is None`. ✅
- Lines 144–153 (`test_summary_is_json_serializable_no_benches`): now uses `json.dumps(s, allow_nan=False)` (strict mode) and asserts `decoded["avg_face_angle_deg"] is None`. ✅
- Result: **`27/27` passed** in `tests/test_reconciled_profile_serialization.py`.

### Design (`openspec/changes/reconciled-profile-v2-default/design.md`)

- §3.3 (line 49): now states `avg_face_angle_deg=None` with explicit rationale: *"The `None` (not `math.nan`) for `avg_face_angle_deg` is required by the spec for strict-JSON consumers — `json.dumps(s, allow_nan=False)` MUST succeed."* ✅
- §6 (line 84): test description updated to "`avg_face_angle_deg is None` without benches (per spec)". ✅

### Tasks (`openspec/changes/reconciled-profile-v2-default/tasks.md`)

- New Phase 4 ("Post-verify CRITICAL-1 remediation") added with 5 sub-tasks (4.1–4.5), all `[x]`. ✅

---

## Test execution (re-verify)

| Suite | Passed | Failed | Skipped | Notes |
|---|---|---|---|---|
| `tests/test_reconciled_profile_serialization.py` (new, **after fix**) | **27/27** | 0 | 0 | First test in class is now `test_no_benches_arg_avg_face_is_none`. |
| Full suite `pytest tests/ --ignore=tests/test_openblast.py` | **795 passed** | **2 (pre-existing)** | 2 | Identical pre-existing failures (`test_api_auth.py::test_no_auth_when_env_var_unset`, `test_api_auth.py::test_auth_with_correct_key` — sqlite3 "no such table: sessions"). Out-of-scope, confirmed on clean checkout via `git stash` during original verify. |
| `python test_pipeline.py` (E2E smoke) | OK | — | — | Generates `/tmp/test_conciliacion.xlsx` + `/tmp/test_report.docx`. |

Total tests collected: **799** (vs. ~772 in AGENTS.md — drift noted, not a regression).

---

## Spec compliance matrix — first-table row updated

The row previously marked `**PARTIAL**` is now **`✅ COMPLIANT`**:

| Spec requirement / scenario | Implementation evidence | Test coverage | Status (re-verify) |
|---|---|---|---|
| `avg_face_angle_deg is None` without benches (spec line 11) | `core/profile_extract.py:133` | `TestSummary.test_no_benches_arg_avg_face_is_none`, `test_summary_is_json_serializable_no_benches` (strict JSON) | **✅ COMPLIANT** |

Other compliance rows from the original report remain `✅ COMPLIANT` — re-verify did not regress them.

---

## Warnings retained

### WARNING-1 (retained) — LOC budget overrun (~636 vs ~345 forecast, +91%)

- **Classification**: WARNING (process guardrail, not a spec violation). Apply-progress self-disclosed; justified as comprehensive edge-case coverage. Carrying forward as an advisory.
- Code changes are still additive and tightly scoped; no scope creep.

---

## Warnings resolved (side effects of CRITICAL-1 fix)

| ID | Resolution | Mechanism |
|---|---|---|
| **WARNING-2** (design-vs-spec inconsistency) | ✅ RESOLVED | `design.md` §3.3 and §6 both now state `avg_face_angle_deg=None`. Spec and design are aligned. |
| **SUGGESTION-1** (test naming/assertion asymmetry) | ✅ RESOLVED | Test renamed to `test_no_benches_arg_avg_face_is_none`; assertion now uses `is None`. |

---

## New SUGGESTION (artifact-internal, non-blocking)

### SUGGESTION-2: `tasks.md` Phase 1.3 description retains stale `math.nan` text (now superseded by Phase 4)

- **Where**: `openspec/changes/reconciled-profile-v2-default/tasks.md:39`
- **Content**: `> summary(self, benches=None) -> dict ... With benches=None: ... avg_face_angle_deg = math.nan. ...`
- **Reality**: Phase 4 (line 60) corrected this. The Phase 1.3 row was not retroactively amended, so readers who scan only Phase 1 (which is the canonical task description) will see the stale `math.nan` instruction.
- **Severity**: SUGGESTION — internal artifact inconsistency. Runtime and all tests confirm `None`. Do NOT block archive.
- **Optional remediation**: amend `tasks.md:39` to match `avg_face_angle_deg = None` (single-token edit) and tick a Phase 4.6 task; or leave as-is and rely on Phase 4 overwriting it functionally. I'll flag it; the orchestrator/user can decide.

---

## Files changed by this verification (none — read-only)

Re-verification was a read-only pass. No edits performed; the fix batch is what I'm verifying, not what I'm writing.

---

## Final verdict (re-verify)

**PASS WITH WARNINGS** — CRITICAL-1 is fully resolved. Code (`core/profile_extract.py:133` = `None`), test (`tests/test_reconciled_profile_serialization.py:109-153` renamed + `is None` + strict-JSON), design (`design.md:49,84` rationale aligned), tasks (`tasks.md:54-64` Phase 4 complete). Strict-JSON probe (`json.dumps(s, allow_nan=False)`) succeeds and emits standards-compliant `"avg_face_angle_deg": null`. **27/27** new tests pass; full suite is **795 passed / 2 pre-existing `test_api_auth` failures (out of scope)**.

**Recommendation**: **ready-to-archive**. WARNING-1 and the new SUGGESTION-2 are advisory and do not block the archive step.

---

## Return Envelope (re-verify)

- **status**: `success`
- **executive_summary**: Re-verification after CRITICAL-1 surgical fix batch confirms 0 CRITICAL / 1 retained WARNING / 1 new SUGGESTION. `avg_face_angle_deg` returns `None` per spec, strict-JSON serialization passes, all 27 new tests pass, full suite is 795/797 (2 pre-existing auth failures still unrelated). Change is **archive-ready**.
- **artifacts**: `openspec/changes/reconciled-profile-v2-default/verify-report.md` (this section appended after the original pass)
- **next_recommended**: `sdd-archive`
- **risks**: none blocking; WARNING-1 (LOC overrun, ~60%) and SUGGESTION-2 (tasks.md Phase 1.3 stale `math.nan` text) are advisory only.
- **skill_resolution**: `paths-injected` — orchestrator provided `sdd-verify` + `_shared/sdd-phase-common.md`; both loaded.