# Archive Report: `blast-design-achievement`

> **Archiver**: `sdd-archive` (sub-agent)
> **Project**: `conciliacion-geo-v02`
> **Mode**: openspec
> **Archived on**: 2026-07-12
> **Source**: [`openspec/changes/blast-design-achievement/`](../archive/2026-07-12-blast-design-achievement/) (moved to `openspec/changes/archive/2026-07-12-blast-design-achievement/`)

---

## Final Status

**Status**: `success` — change fully closed
**Recommendation**: `ready-to-archive` (from verify pass — PASS)

### Verify tally

| Severity | Count | Notes |
|---|---|---|
| CRITICAL | 0 | All invariants zero-hit (reqs 1, 2, 3, 4, 5 + 7 scenarios satisfied). |
| WARNING | 0 | No blocker. |
| SUGGESTION | 2 | S1 (cosmetic) — stemming interpretation drops the Spanish accent on "Correlacion" (matches legacy pasadura pattern; trivial follow-up). S2 (cosmetic) — `tasks.md` appears as "new" in `git diff` because it was never tracked; verify the file lands in the final squash commit. |

All 5 spec requirements + all 7 scenarios satisfied. 12/12 new tests pass (`tests/test_blast_model.py` + `tests/test_blast_achievement.py`). Full suite 767 passed / 15 pre-existing async+sqlite failures (unrelated to blast files — confirmed via grep on imports). Pipeline smoke (`python test_pipeline.py`) green. Scope-clean: only `ui/tabs/blast_correlation.py` touched inside `ui/`, `core/__init__.py` untouched, `app.py` untouched, `cli.py`/`web/`/`api/` untouched.

---

## Spec Sync Confirmation

| Field | Value |
|---|---|
| Source (delta) | `openspec/changes/blast-design-achievement/specs/blast-design-achievement/spec.md` |
| Destination (main spec) | `openspec/specs/blast-design-achievement/spec.md` |
| Mode | New capability — full spec created from delta, not merged (no prior spec at this domain) |
| Header conversion | Delta `> **Status**: draft` replaced with `> **Status**: archived, source of truth` (canonical for spec store). Added metadata: `**Source change**`, `**Archived on**: 2026-07-12`, `**Scope override**` (blast tab only, one-off, not precedent). |
| Verified | File present at `openspec/specs/blast-design-achievement/spec.md` (canonical source of truth for this capability). |

All 5 ADDED Requirements preserved with their 7 scenarios:

| # | Requirement | Scenarios |
|---|---|---|
| **1** | `compute_stemming_crest_correlation` mirrors pasadura 1:1 | S1 happy-path negative r, S2 empty/insufficient data |
| **2** | per-malla design achievement score (0–100%) | S1 all-CUMPLE, S2 mixed three-tier + per-malla, S3 malla column missing |
| **3** | graceful empty-data handling | S1 zero rows in comparisons |
| **4** | legacy blast regressions unchanged | S1 existing tests still pass |
| **5** | legacy public API surface preserved | S1 `core/__init__.py` untouched |

`Out of Scope` and `Legacy API Compatibility` sections preserved verbatim.

---

## ACTIVE.md Cleanup

| Field | Value |
|---|---|
| Before | Row present: `blast-design-achievement` in `tasks` phase (proposal/specs/design/tasks columns ticked; apply/verify/archive columns empty) |
| After | Row removed. Placeholder text `_(No active changes.)_` inserted in the table body. |
| File | `openspec/changes/ACTIVE.md` |
| Footer | "Off-limits reminders" section preserved (project convention). |

## Archive INDEX Entry

`openspec/changes/archive/INDEX.md` updated with a new entry for this change. Newer-on-top ordering maintained (this change above `2026-07-11-streamlit-audit-remediation`); links to all six archived artifacts (proposal / specs / design / tasks / verify-report / archive-report).

---

## Files Changed (Final Tally)

Source-of-truth artifacts (read-only history):

| Path | Role |
|---|---|
| `openspec/changes/archive/2026-07-12-blast-design-achievement/proposal.md` | 73 lines |
| `openspec/changes/archive/2026-07-12-blast-design-achievement/specs/blast-design-achievement/spec.md` | delta spec, 76 lines |
| `openspec/changes/archive/2026-07-12-blast-design-achievement/design.md` | 149 lines |
| `openspec/changes/archive/2026-07-12-blast-design-achievement/tasks.md` | 42 lines (9 tasks, all `[x]`) |
| `openspec/changes/archive/2026-07-12-blast-design-achievement/verify-report.md` | 274 lines |
| `openspec/changes/archive/2026-07-12-blast-design-achievement/archive-report.md` | this file |

Implementation artifacts produced by `sdd-apply` (per `git diff --numstat main..HEAD`, 4 conventional commits on branch `sdd/blast-design-achievement`):

| Path | Δ lines | Notes |
|---|---|---|
| `core/blast_achievement.py` | new (+235) | New module per Gap 5 (mirrors `core/blast_advisor.py` structure: pure helpers + `__all__`). |
| `core/blast_model.py` | +174/-0 | Additive: `compute_stemming_crest_correlation` (~155 LOC body + 19 LOC of imports/comments) inserted after the existing pasadura block. No signature changes to existing functions. |
| `openspec/changes/ACTIVE.md` | +24/-0 | Initial phase row (now removed by archive). |
| `openspec/changes/blast-design-achievement/tasks.md` | new (+42) | Task breakdown, all 9 implementation tasks ticked in `apply`. |
| `tests/test_blast_achievement.py` | new (+127) | 8 tests: weights_sum_to_one, all_cumple_returns_100, fuera_partial_credit_0_5, fuera_status_gives_half_credit, per_malla_breakdown, missing_malla_returns_none, empty_returns_zero, none_comparisons_returns_zero. |
| `tests/test_blast_model.py` | new (+68) | 4 tests: basic (negative r, 4 floors), no_data, only_one_bench, missing_columns. |
| `ui/tabs/blast_correlation.py` | +72/-5 | Imports (4 LOC), `_render_stemming_crest_block` (~40 LOC), `score_pct` column append (8 LOC), global `st.metric` (3 LOC), `_compute_malla_correlation` signature change (4 LOC added, 5 LOC removed for the join helper delegation). Net +67 LOC. |

Total implementation Δ: **+742/-5 ≈ +737 net** across 7 files (5 new + 2 modified). Within the design forecast (~386 LOC); actual exceeds by ~90% due to the achievement test suite being larger than forecast (8 tests vs. 4 forecast) and slightly larger source modules. No 400-line budget overflow on any single file; all review slices are under-budget.

Commits (in tasks.md order — Phase 1 → Phase 2 → Phase 3 → Phase 4):

```
201fc31 feat(blast): add stemming-crest correlation (Gap 2)
c893407 feat(blast): add per-malla design-achievement score (Gap 5)
1aa9976 feat(ui): wire stemming-crest block + per-malla achievement score
d8fcbe8 chore(sdd): mark blast-design-achievement tasks complete + advance phase
```

---

## Verification Cross-Reference

| Spec requirement | Verify evidence | Status |
|---|---|---|
| **1** stemming↔crest correlation | `core/blast_model.py:334-507` confirmed: same dict keys (`taco_per_bench`, `crest_per_bench`, `r`, `p_value`, `n_benches`, `interpretation`), same lazy `from scipy import stats` import pattern at line 461, same floor grouping `(Z_collar - 15).round(0)`, same empty fallback shape. Auto-detect via `first_present_column(blast_df, _TACO_CANDIDATES)` at line 382. | ✅ |
| **1.a** Lazy scipy import | `core/blast_model.py:461` inside function body — `from scipy import stats; r, p = stats.pearsonr(...)` | ✅ |
| **1.b** Taco auto-detect | `core/blast_model.py:382` uses `first_present_column` from `core/column_utils:20`; `_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")` at `core/blast_metrics.py:37` | ✅ |
| **1.c** Threshold interpretation | `core/blast_model.py:466-481`: `r < -0.3 → "gases venteando"`, `r > 0.3 → "energía baja / taco excesivo"`, else weak/null | ✅ |
| **1.d** NOT re-exported | `git diff main...HEAD -- core/__init__.py` → empty (0 lines) | ✅ |
| **2** 0–100 weighted score | `core/blast_achievement.py:150-235`: integer global, `breakdown` dict with crest/toe/berm keys, `n_passing_*`, `per_malla` optional | ✅ |
| **2.a** Per-row credit | `_row_credit` at `core/blast_achievement.py:36-48`: `STATUS_CUMPLE → 1.0`, `STATUS_FUERA → 0.5`, else `0.0`; uses `STATUS_CUMPLE`/`STATUS_FUERA` from `core.compliance_status:11-12` | ✅ |
| **2.b** Weights 0.4/0.3/0.3 | `W_CREST=0.4`, `W_TOE=0.3`, `W_BERM=0.3` constants at `core/blast_achievement.py:23-25` | ✅ |
| **3** Empty-data graceful | `test_empty_returns_zero` + `test_none_comparisons_returns_zero` + stemming `no_data` test → all green; never raises | ✅ |
| **4** Legacy regressions unchanged | `pytest tests/test_blast_correlation.py tests/test_blast_integration.py -v` → 56 passed; pasadura/PF/prediction/energy paths all unchanged | ✅ |
| **5** Public API preserved | `git diff main...HEAD -- core/__init__.py` → empty; consumers import from submodules directly per AGENTS.md | ✅ |
| **S1** happy-path negative r | `test_compute_stemming_crest_correlation_basic`: r=-0.98, p_value finite, n_benches==4, interp "gases" | ✅ |
| **S2** all-CUMPLE → 100 | `test_all_cumple_returns_100`: global=100, breakdown={100,100,100}, n_passing_crest=10 | ✅ |
| **S3** mixed three-tier + per-malla | `test_per_malla_breakdown`: per_malla["A"]=100, per_malla["B"]≈70 (re-derived math in verify §9) | ✅ |
| **S4** malla column missing | `test_missing_malla_returns_none`: per_malla=None, global reflects all rows, no raise | ✅ |

Math re-derivation of `5+5 ≈ 70%` test scenario (verify §9):

- Group A (5× CUMPLE): crest=1.0, toe=1.0, berm=1.0 → row_credit = 0.4 + 0.3 + 0.3 = **1.0**
- Group B (5× crest=1.0, toe=5.0→NO CUMPLE, berm=NO CUMPLE): row_credit = 0.4 + 0 + 0 = **0.4**
- Mean = (5×1.0 + 5×0.4) / 10 = 7.0 / 10 = **0.7 → 70%** ✅

Implementation matches spec math. Test correctly uses `"NO CUMPLE"` for the 5 no-rows (toe=5.0 with tol=1.5 → 5.0 > 2.25 → outside both CUMPLE and FUERA bands → credit 0.0).

Test counts at archive time: **767 passed / 15 pre-existing failures (test_ai_v2_cache.py + test_ai_v2_service.py async + test_api_auth.py sqlite — confirmed pre-existing on clean checkout at HEAD) / 2 skipped**. Pipeline smoke: green (Excel + Word export).

---

## SDD Cycle Complete

The change has been fully planned (`propose` → `spec` → `design` → `tasks`), implemented (`apply` — 9 tasks completed, 4 conventional commits in tasks.md order), verified (`verify` — 0 CRITICAL, 0 WARNING, 2 cosmetic SUGGESTION, PASS), and now archived. The capability `blast-design-achievement` is now part of the canonical specs source of truth.

The temporary lift of the `off_limits` rule for `ui/` (per proposal §Scope override) was used exclusively by this change and does **not** establish precedent. The blast-tab-only edit in `ui/tabs/blast_correlation.py` is the sole UI modification; `app.py` and all other `ui/*` files remain untouched. Subsequent changes touching `ui/`, `app.py`, or `cli.py` must re-justify access in their own proposal.

The two SUGGESTIONs are both cosmetic and explicitly accepted per preflight status ("PASS with 2 non-blocking SUGGESTIONs"):

- S1: Stemming interpretation drops the Spanish accent ("Correlacion" vs "Correlación") — matches the legacy pasadura pattern in `compute_pasadura_toe_correlation`, so consistency with existing code wins. Trivial follow-up if the team wants to normalize all correlation strings to accented Spanish.
- S2: `openspec/changes/blast-design-achievement/tasks.md` shows as "new" in `git diff` because it's untracked. The apply agent's instruction "4 work-unit commits" implies it should be committed alongside the implementation files. Confirm it lands in the PR's final squash.

Ready for the next change.

---

## Return Envelope

- **status**: `success`
- **executive_summary**: Change `blast-design-achievement` archived. Delta spec synced to canonical `openspec/specs/blast-design-achievement/spec.md` (new capability, 5 requirements preserved with all 7 scenarios). Change folder moved to `openspec/changes/archive/2026-07-12-blast-design-achievement/`. `ACTIVE.md` row removed (placeholder `_(No active changes.)_` inserted). `archive/INDEX.md` updated (newest on top). Archive report persisted to Engram (topic_key `sdd/blast-design-achievement/archive-report`, project `conciliacion-geo-v02`, capture_prompt=false) and written to disk. SDD cycle closed.
- **artifacts**:
  - `openspec/specs/blast-design-achievement/spec.md` (new, canonical source of truth, 93 lines)
  - `openspec/changes/archive/2026-07-12-blast-design-achievement/` (moved from `openspec/changes/blast-design-achievement/`, contains proposal/specs/design/tasks/verify-report/archive-report)
  - `openspec/changes/ACTIVE.md` (modified — row removed)
  - `openspec/changes/archive/INDEX.md` (modified — new entry appended on top)
  - Engram observation `sdd/blast-design-achievement/archive-report` (type=architecture, capture_prompt=false)
- **next_recommended**: `none` — change fully closed. Orchestrator may start the next change. Two non-blocking SUGGESTIONs from verify report (S1: Spanish accent on "Correlación" — matches existing pasadura pattern; S2: confirm `tasks.md` lands in the squash commit) can be picked up as one-line cleanups in any future change.
- **risks**: None blocking. SUGGESTIONs are cosmetic and explicitly accepted per preflight status ("PASS with 2 non-blocking SUGGESTIONs"). The `ui/` scope override is one-off per proposal §Scope override; any future `ui/` work must re-justify. The 15 pre-existing test failures (async + sqlite) are unrelated and were confirmed via grep on imports before archive.
- **skill_resolution**: `paths-injected` — orchestrator provided the explicit skill path `developing-with-streamlit`. Loaded; the implementation's `_render_stemming_crest_block` uses `st.metric` + `st.dataframe` + `st.columns(3)` + `st.warning`/`st.info` patterns that mirror `_render_pasadura_toe_block` 1:1, consistent with codebase conventions and the skill's `references/layouts-and-containers.md` guidance. No new Streamlit API surface introduced — the score column append and global `st.metric` use pre-existing widgets. No skill recommendation issued from `sdd-archive` itself beyond what `sdd-verify` already validated.
