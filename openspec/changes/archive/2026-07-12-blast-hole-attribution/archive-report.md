# Archive Report: `blast-hole-attribution`

> **Archiver**: `sdd-archive` (sub-agent)
> **Project**: `conciliacion-geo-v02`
> **Mode**: openspec with Engram report persistence
> **Archived on**: 2026-07-12
> **Source**: [`openspec/changes/blast-hole-attribution/`](../archive/2026-07-12-blast-hole-attribution/) (moved from `openspec/changes/blast-hole-attribution/`)
> **Overwrites**: prior blocked archive-report (observation #102) emitted earlier the same day before task checkboxes were reconciled.

---

## Final Status

**Status**: `success` — change fully closed
**Recommendation**: `ready-for-archive` (from verify pass — PASS with 0 CRITICAL / 0 WARNING / 3 SUGGESTION)

### Verify tally

| Severity | Count | Notes |
|---|---:|---|
| CRITICAL | 0 | All invariants zero-hit (reqs 1-5 + 7 scenarios satisfied). |
| WARNING | 0 | No blocker. |
| SUGGESTION | 3 | S1 (cosmetic) — `🎯` emoji in subheader violates AGENTS.md default (legacy UI uses emojis so this matches the maintainer's precedent); S2 (forward-only) — no `st.download_button` CSV export (legacy renderer pattern matches); S3 (defensive, very low priority) — selectbox label uniqueness on collision (impossible in practice). |

All 6 spec requirements + all 7 scenarios satisfied. 23/23 new tests pass in `tests/test_blast_attribution.py` (TestGracefulAbsence × 7, TestMinDeviationGate × 3, TestKgFallback × 2, TestTopNLimit × 3, TestMultiFeatureIsolation × 2, TestCoordinateTransform × 2, TestTolerance × 2, TestResultShape × 2). Full suite: 790 passed, 2 skipped, 15 pre-existing async+sqlite failures (test_ai_v2_* / test_api_auth.py — confirmed unrelated to blast files via grep on imports, identical to baseline before this change). Pipeline smoke (`python test_pipeline.py`) green. Scope-clean: only `ui/tabs/blast_correlation.py` touched inside `ui/`, `core/__init__.py` untouched, `app.py` untouched, `cli.py`/`web/`/`api/` untouched.

---

## Task Completion Gate

| Field | Value |
|---|---|
| Task artifact | `openspec/changes/blast-hole-attribution/tasks.md` (now archived at `archive/2026-07-12-blast-hole-attribution/tasks.md`) |
| Total implementation tasks | 23 (4 phases: 7 domain + 7 tests + 4 UI + 5 verify) |
| Checked `[x]` | 23 |
| Unchecked `[ ]` | 0 |
| Gate result | **PASS** |

A prior `sdd-archive` invocation earlier the same day (observation #102) returned `blocked` because the persisted `tasks.md` still showed 23 unchecked items even though the verify report was passing. The orchestrator reconciled `tasks.md` against the apply-progress evidence (commits `9904432` + `4174ef8` carry all the work) and explicitly authorized this archive run. Every previously unchecked task now shows `[x]` in the archived `tasks.md`, and verify report §3 (spec ↔ test traceability) provides the same proof for every task — so the audit trail is internally consistent.

---

## Spec Sync Confirmation

| Field | Value |
|---|---|
| Source (delta) | `openspec/changes/blast-hole-attribution/specs/blast-hole-attribution/spec.md` |
| Destination (main spec) | `openspec/specs/blast-hole-attribution/spec.md` |
| Mode | New capability — full spec created from delta, not merged (no prior spec at this domain) |
| Header conversion | Delta `# Blast Hole Attribution Specification` replaced with canonical `# Capability: blast-hole-attribution`. Added metadata: `**Source change**`, `**Archived on**: 2026-07-12`, `**Status**: archived, source of truth`, `**Scope override**` (blast tab only, one-off, not precedent — same pattern as `2026-07-12-blast-design-achievement`). |
| Verified | File present at `openspec/specs/blast-hole-attribution/spec.md` (canonical source of truth for this capability). |

All 6 ADDED Requirements preserved with their 7 scenarios:

| # | Requirement | Scenarios |
|---|---|---|
| **1** | Feature-level attribution | S1 attribute a nearby hole, S2 isolate features |
| **2** | Charge-distance ranking (`kg / d²`) | S1 rank by charge and distance, S2 enforce result limit |
| **3** | Auditable result fields | S1 return hole details, S2 missing charge column |
| **4** | Graceful absence handling | S1 no usable blast data, S2 no attributable deviation |
| **5** | Attribution presentation (Streamlit) | S1 inspect a feature, S2 empty attribution view |
| **6** | Legacy API Compatibility | S1 existing regression suite |

`Legacy API Compatibility` section preserved verbatim.

---

## ACTIVE.md Cleanup

| Field | Value |
|---|---|
| Before | Row present: `blast-hole-attribution` in `proposal` phase |
| After | Row removed. Placeholder text `_(No active changes.)_` inserted in the table body. |
| File | `openspec/changes/ACTIVE.md` |
| Footer | "Off-limits reminders" section preserved (project convention). |

## Archive INDEX Entry

`openspec/changes/archive/INDEX.md` updated with a new entry for this change. Newer-on-top ordering maintained (this change above `2026-07-12-blast-design-achievement`); links to all six archived artifacts (proposal / specs / design / tasks / verify-report / archive-report).

---

## Files Changed (Final Tally)

Source-of-truth artifacts (read-only history):

| Path | Role |
|---|---|
| `openspec/changes/archive/2026-07-12-blast-hole-attribution/proposal.md` | 74 lines |
| `openspec/changes/archive/2026-07-12-blast-hole-attribution/specs/blast-hole-attribution/spec.md` | delta spec, 102 lines |
| `openspec/changes/archive/2026-07-12-blast-hole-attribution/design.md` | 92 lines |
| `openspec/changes/archive/2026-07-12-blast-hole-attribution/tasks.md` | 61 lines (23 tasks, all `[x]`) |
| `openspec/changes/archive/2026-07-12-blast-hole-attribution/verify-report.md` | 137 lines |
| `openspec/changes/archive/2026-07-12-blast-hole-attribution/archive-report.md` | this file |

Implementation artifacts produced by `sdd-apply` (per `git diff --numstat main..HEAD`, 2 conventional commits on branch `sdd/blast-design-achievement`):

| Path | Δ lines | Notes |
|---|---|---|
| `core/blast_attribution.py` | new (+326) | New module per Gap 1: `attribute_holes_to_benches()` + private helpers (`_resolve_kg_column`, `_feature_world_xy`, `_extract_benches`, `_select_top_holes`). `__all__ = ["attribute_holes_to_benches"]` — narrow. |
| `ui/tabs/blast_correlation.py` | +58/-0 | Imports (1 LOC) + `tab_bnc` call after `_render_stemming_crest_block` (~4 LOC) + `_render_attribution_block` (~53 LOC). Spanish copy. |
| `tests/test_blast_attribution.py` | new (+395) | 23 tests in 8 `TestCase` classes. Synthetic 4-hole 30×30 m fixture, MATCH-row builder, SectionLine stub. |
| `openspec/changes/blast-hole-attribution/tasks.md` | new (+61) | Task breakdown, all 23 implementation tasks ticked in `apply`. |

Total implementation Δ: **+779/-0 ≈ +779 net** across 4 files (3 new + 1 modified). Exceeds the design forecast (~330 LOC) by ~136% because the test suite is larger than forecast (23 tests vs. ≥5) and the source module grew with stricter helper decomposition. No 400-line budget overflow on any single file; the `core/blast_attribution.py` module at 326 LOC remains under the design ceiling. The verify report explicitly accepts this growth (matrix check #2 + #5 PASS).

Commits (per verify report §1):

```
9904432 feat(blast): add per-feature hole attribution domain module
4174ef8 feat(ui): wire blast-hole attribution block into blast-correlation tab
```

NOTE: branch name is `sdd/blast-design-achievement` (carryover from the prior change on the same worktree); both commits under that branch carry `blast-hole-attribution` files only.

---

## Spec ↔ Test Traceability (Verify §3 cross-reference)

| Spec requirement | Verify evidence | Status |
|---|---|---|
| **1** Feature-level attribution | `core/blast_attribution.py` `_extract_benches` (lines 75-123) + `_feature_world_xy` exercised by `test_top_n_limits_results`, `test_outside_tolerance_excluded`, `test_hole_near_two_features_appears_in_both`, `test_no_cross_feature_aggregation`. | ✅ |
| **1.a** `bench_real` measured coords | `_feature_world_xy` uses `bench_real["x|y"]` (lines 89-94); not `bench_design`. Per design §Architecture Decisions row 2. | ✅ |
| **2** Charge-distance ranking | Line 142 `d2 = dx*dx + dy*dy`; line 149 `safe_d2 = np.where(d2 < 1e-4, 1e-4, d2)`; line 150 `scores = well_q / safe_d2`; line 144 `within_mask = d2 <= tolerance**2`. Tested by `test_score_uses_floored_inverse_distance_squared` and `test_d2_floor_prevents_div_by_zero`. | ✅ |
| **3** Auditable result fields | `test_required_fields_present` asserts every entry has `section, bench_num, feature, delta_m, top_holes[label_pozo, malla, kg, distance_m, contribution_pct], n_candidates`. | ✅ |
| **4** Graceful absence | 7 tests in `TestGracefulAbsence`: `None`, empty df, missing X, missing Y, no comparisons, no sections, unknown section, non-MATCH rows all return `[]` without raising. | ✅ |
| **5** Streamlit presentation | `ui/tabs/blast_correlation.py:995-1044` provides `selectbox` per feature, dataframe with Spanish labels (`Pozo / Malla / Carga (kg) / Distancia (m) / Contribución (%)`), n_candidates caption. Empty path: `st.info("Sin desviaciones atribuibles")` at line 1008-1010. | ✅ |
| **6** Legacy API Compatibility | `git show HEAD:core/__init__.py \| grep blast_attribution` → no match. HEAD~2..HEAD diff: only `blast_attribution.py` + `test_blast_attribution.py` + `blast_correlation.py`. `pytest tests/test_blast_*.py` → 172 passed, 2 skipped (no regression). | ✅ |

---

## Artifact Traceability

### OpenSpec

- `openspec/specs/blast-hole-attribution/spec.md` (new canonical source of truth, 87 lines)
- `openspec/changes/archive/2026-07-12-blast-hole-attribution/` (moved from `openspec/changes/blast-hole-attribution/`, contains proposal/specs/design/tasks/verify-report/archive-report)
- `openspec/changes/ACTIVE.md` (modified — row removed)
- `openspec/changes/archive/INDEX.md` (modified — new entry appended on top)

### Engram observations

- Spec: observation `#97`, topic `sdd/blast-hole-attribution/spec`
- Design: observation `#96`, topic `sdd/blast-hole-attribution/design`
- Tasks: observation `#98`, topic `sdd/blast-hole-attribution/tasks`
- Verify report: observation `#101`, topic `sdd/blast-hole-attribution/verify-report`
- Archive report: observation `#102` (prior blocked entry, overwritten via same `topic_key` upsert → new `sync_id`, see Engram envelope returned with this report)
- Proposal: no matching Engram observation found; OpenSpec proposal was read directly

---

## SDD Cycle Complete

The change has been fully planned (`propose` → `spec` → `design` → `tasks`), implemented (`apply` — 23 tasks completed, 2 conventional commits in tasks.md order), verified (`verify` — 0 CRITICAL, 0 WARNING, 3 cosmetic SUGGESTION, PASS), and now archived. The capability `blast-hole-attribution` is now part of the canonical specs source of truth.

The temporary lift of the `off_limits` rule for `ui/` (per proposal §Scope override) was used exclusively by this change and does **not** establish precedent. The blast-tab-only edit in `ui/tabs/blast_correlation.py` is the sole UI modification; `app.py` and all other `ui/*` files remain untouched. Subsequent changes touching `ui/`, `app.py`, or `cli.py` must re-justify access in their own proposal.

The three SUGGESTIONs are all cosmetic and explicitly accepted per preflight status ("PASS with 3 non-blocking SUGGESTIONs"):

- S1: `🎯` emoji in subheader — legacy UI uses emojis throughout (maintainer precedent); AGENTS.md default would forbid, but matches codebase reality.
- S2: No CSV `st.download_button` — matches the legacy `_render_stemming_crest_block` pattern; can be added as a one-line follow-up if blast engineers request export.
- S3: Selectbox label uniqueness — defensive only; impossible in practice because each MATCH row yields exactly one crest + one toe (no duplicates possible).

Ready for the next change.

---

## Return Envelope

- **status**: `success`
- **executive_summary**: Change `blast-hole-attribution` archived. Delta spec synced to canonical `openspec/specs/blast-hole-attribution/spec.md` (new capability, 6 requirements preserved with all 7 scenarios). Change folder moved to `openspec/changes/archive/2026-07-12-blast-hole-attribution/`. `ACTIVE.md` row removed (placeholder `_(No active changes.)_` inserted). `archive/INDEX.md` updated (newest on top). Archive report persisted to Engram (topic_key `sdd/blast-hole-attribution/archive-report`, project `conciliacion-geo-v02`, capture_prompt=false) and overwrites the prior blocked observation (#102). SDD cycle closed.
- **artifacts**:
  - `openspec/specs/blast-hole-attribution/spec.md` (new, canonical source of truth, 87 lines)
  - `openspec/changes/archive/2026-07-12-blast-hole-attribution/` (moved from `openspec/changes/blast-hole-attribution/`, contains proposal/specs/design/tasks/verify-report/archive-report)
  - `openspec/changes/ACTIVE.md` (modified — row removed)
  - `openspec/changes/archive/INDEX.md` (modified — new entry appended on top)
  - Engram observation `sdd/blast-hole-attribution/archive-report` (upsert over prior blocked entry #102, type=architecture, capture_prompt=false)
- **next_recommended**: `none` — change fully closed. Orchestrator may start the next change. Three non-blocking SUGGESTIONs from verify report (S1: `🎯` emoji — matches maintainer's emoji convention; S2: CSV download button — matches legacy renderer; S3: selectbox label uniqueness — defensive, impossible in practice) can be picked up as one-line cleanups in any future change.
- **risks**: None blocking. SUGGESTIONs are cosmetic and explicitly accepted per preflight status ("PASS with 3 non-blocking SUGGESTIONs"). The `ui/` scope override is one-off per proposal §Scope override; any future `ui/` work must re-justify. The 15 pre-existing test failures (async + sqlite) are unrelated and were confirmed via grep on imports before archive. Working-tree shows leftover modifications from a prior `blast-design-achievement` change (AGENTS.md, core/__init__.py, core/profile_*.py, deletion of blast-design-achievement/tasks.md) — these are out of scope for this archive and do not touch blast-hole-attribution files.
- **skill_resolution**: `none` — no additional task-specific skills were injected or required beyond the executor's `sdd-archive` instructions. The implementation's `_render_attribution_block` is consistent with `developing-with-streamlit` patterns (`st.expander`, `st.selectbox`, `st.dataframe`, `st.info` early-return) but no new Streamlit API surface was introduced and the verify report already validated it.