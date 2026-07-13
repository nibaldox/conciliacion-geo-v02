# Archive Report: `reconciled-profile-v2-default`

> **Archiver**: `sdd-archive` (sub-agent)
> **Project**: `conciliacion-geo-v02`
> **Mode**: openspec
> **Archived on**: 2026-07-10
> **Source**: [`openspec/changes/reconciled-profile-v2-default/`](../reconciled-profile-v2-default/) (now at `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/`)

---

## Final Status

**Status**: `success` — change fully closed
**Recommendation**: `ready-to-archive` (from verify-pass-2)

### Verify pass 2 tally

| Severity | Count | Notes |
|---|---|---|
| CRITICAL | 0 | CRITICAL-1 (`avg_face_angle_deg` NaN vs None) resolved by Phase 4 surgical fix. |
| WARNING | 1 | WARNING-1 (LOC budget overrun: ~636 actual vs ~345 forecast, ~+91%) — advisory process guardrail breach; not a spec violation. |
| SUGGESTION | 1 | SUGGESTION-2 (stale `math.nan` text in `tasks.md:39` Phase 1.3 description, superseded by Phase 4) — internal artifact inconsistency; runtime, design, and tests confirm `None`. |

The orchestrator explicitly approved archiving with these non-blocking advisories (per preflight status: *"0 CRITICAL, 1 advisory WARNING (LOC budget overrun, not blocking), 1 advisory SUGGESTION (stale text in tasks.md:39, non-blocking)"*).

---

## Spec Sync Confirmation

| Field | Value |
|---|---|
| Source (delta) | `openspec/changes/reconciled-profile-v2-default/specs/reconciled-profile-serialization/spec.md` |
| Destination (main spec) | `openspec/specs/reconciled-profile-serialization/spec.md` |
| Mode | New capability — full spec created from delta, not merged |
| Header conversion | `## ADDED Requirements` → `## Requirements` (canonical). Top-level `### Capability: reconciled-profile-serialization` promoted to `# Capability: reconciled-profile-serialization`. Delta title `# Spec: reconciled-profile-v2-default` replaced with the capability name. |
| Verified | File present at `openspec/specs/reconciled-profile-serialization/spec.md` (5,399 bytes). |

All four ADDED Requirements preserved with their scenarios:

| Requirement | Scenarios |
|---|---|
| `ReconciledProfile.summary` | empty profile, enriched benches |
| `ReconciledProfile.to_dataframe` | empty profile dataframe, CSV round trip |
| `ReconciledProfile.to_dict round trip` | JSON round trip |
| `Canonical v2 import and legacy deprecation` | imports remain compatible, legacy warning without tuple drift |

Legacy API Compatibility section and Design Note preserved verbatim.

---

## ACTIVE.md Cleanup

| Field | Value |
|---|---|
| Before | Row present: `reconciled-profile-v2-default` in `apply`/`verify` phase |
| After | Row removed. Placeholder text "(No active changes.)" inserted in the table body. |
| File | `openspec/changes/ACTIVE.md` |
| Footer | "Off-limits reminders" section preserved (project convention). |

---

## Archive INDEX Entry

`openspec/changes/archive/INDEX.md` created with a single entry for this change. Newer-on-top ordering; links to all six archived artifacts (proposal / specs / design / tasks / verify-report / archive-report).

---

## Files Changed (Final Tally)

Source-of-truth artifacts (read-only history):

| Path | Role |
|---|---|
| `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/proposal.md` | 245 lines |
| `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/specs/reconciled-profile-serialization/spec.md` | delta spec, 68 lines |
| `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/design.md` | 114 lines |
| `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/tasks.md` | 77 lines (12 tasks, all `[x]`) |
| `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/verify-report.md` | 314 lines (pass-1 + pass-2 sections) |
| `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/archive-report.md` | this file |

Implementation artifacts produced by `sdd-apply` (per `git diff --stat HEAD` at archive time, excluding pre-existing `AGENTS.md` churn and `openspec/` artifacts):

| Path | Δ lines | Notes |
|---|---|---|
| `core/__init__.py` | +7 | Additive re-export of `build_reconciled_profile_v2`; entry in `__all__`. |
| `core/profile_compliance.py` | ±16 | Deprecation warning text + docstring hardened (2-cycle horizon, v2 successor named). |
| `core/profile_extract.py` | +178 | Four methods (`summary`, `to_dataframe`, `to_dict`, `from_dict`) appended to `ReconciledProfile`. Imports for `json` and `math` added. |
| `tests/test_reconciled_profile_serialization.py` | new (454 lines) | 6 test classes, 27 tests, 100% green. |
| `openspec/specs/reconciled-profile-serialization/spec.md` | new (canonical, 5,399 bytes) | Synced from delta by this archive pass. |

Total implementation Δ (excluding pre-existing `AGENTS.md`): **+637 / -42 ≈ +595 net** (matches verify-pass-2 WARNING-1 LOC figure). Forecast was ~345 LOC — over budget by ~91% but within the `size-exception` delivery strategy resolved during `sdd-tasks`.

---

## Verification Cross-Reference

| Spec requirement | Test(s) | Status |
|---|---|---|
| `summary()` flat JSON-safe dict (11 keys, strict-JSON compatible) | `TestSummary.test_empty_profile_returns_zero_counts`, `test_no_benches_arg_avg_face_is_none`, `test_summary_is_json_serializable_no_benches` (uses `allow_nan=False`) | ✅ |
| `summary()` no numpy scalars/dataclasses leak | `TestSummary.test_summary_has_no_numpy_scalar_leak` | ✅ |
| `summary(benches=...)` hazard enrichment | `TestSummary.test_enriched_with_benches` | ✅ |
| `to_dataframe()` English snake_case columns | `TestToDataframe.test_populated_columns_and_dtypes`, `test_empty_profile_dataframe_shape` | ✅ |
| Hazard columns added when `benches` supplied | `TestToDataframe.test_to_dataframe_with_benches_adds_hazard_columns`, `test_to_dataframe_benches_missing_bench_number_yields_defaults` | ✅ |
| CSV round-trip | `TestToDataframe.test_csv_round_trip_preserves_rows_and_columns` | ✅ |
| `to_dict()` / `from_dict()` round trip | `TestToFromDict.test_round_trip_preserves_fields`, `test_from_dict_drops_unknown_fields`, `test_from_dict_empty` | ✅ |
| Canonical v2 import + `__all__` membership | `TestCoreReExportsV2.test_both_importable_from_core`, `test_both_in_core_all`, `test_legacy_identity_match_vs_param_extractor` | ✅ |
| Legacy deprecation warning content | `TestLegacyDeprecationWarning.test_warning_emitted_on_legacy_call`, `test_no_warning_when_return_v2_true`, `test_warning_stacklevel_is_two` | ✅ |
| Legacy `(np.array, np.array)` byte-for-byte identity | `TestLegacyTupleContractPreserved.test_three_bench_tuple_shape_and_dtype`, `test_three_bench_frozen_snapshot`, `test_empty_input_returns_empty_float_arrays` | ✅ |
| Additive-only (no `web/`, `api/`, `app.py`, `ui/`, `cli.py` edits) | `git diff --stat` | ✅ |

Test counts at archive time: **27/27 new tests pass**; full suite **795 passed / 2 pre-existing `test_api_auth` failures (out of scope — sqlite3 "no such table: sessions", confirmed on clean checkout at HEAD `877feed`)**.

---

## SDD Cycle Complete

The change has been fully planned (`explore` → `propose` → `spec` → `design` → `tasks`), implemented (`apply` — 12 tasks completed), verified (`verify` — 0 CRITICAL, pass-with-warnings, ready-to-archive), and now archived. The capability `reconciled-profile-serialization` is now part of the canonical specs source of truth.

Ready for the next change.

---

## Return Envelope

- **status**: `success`
- **executive_summary**: Change `reconciled-profile-v2-default` archived. Delta spec synced to canonical `openspec/specs/reconciled-profile-serialization/spec.md` (new capability, headers converted from `## ADDED Requirements` to `## Requirements`). Change folder moved to `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/`. `ACTIVE.md` row removed. `archive/INDEX.md` created with one entry. Archive report persisted to Engram and written to disk. SDD cycle closed.
- **artifacts**: `openspec/specs/reconciled-profile-serialization/spec.md` (new, canonical), `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/archive-report.md` (new), `openspec/changes/ACTIVE.md` (modified — row removed), `openspec/changes/archive/INDEX.md` (new). Engram observation `sdd/reconciled-profile-v2-default/archive-report` (type=architecture, capture_prompt=false).
- **next_recommended**: `none` — change fully closed. Orchestrator may start the next change.
- **risks**: None blocking. WARNING-1 (LOC budget overrun ~91%) and SUGGESTION-2 (`tasks.md:39` stale `math.nan` text) are advisory and explicitly accepted by the orchestrator per preflight status.
- **skill_resolution**: `paths-injected` — orchestrator provided exact skill paths (`sdd-archive`, `_shared/sdd-phase-common.md`, `_shared/openspec-convention.md`); all three loaded.