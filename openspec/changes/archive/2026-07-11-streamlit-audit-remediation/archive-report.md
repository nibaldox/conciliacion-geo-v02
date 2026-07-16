# Archive Report: `streamlit-audit-remediation`

> **Archiver**: `sdd-archive` (sub-agent)
> **Project**: `conciliacion-geo-v02`
> **Mode**: openspec
> **Archived on**: 2026-07-11
> **Source**: [`openspec/changes/streamlit-audit-remediation/`](../streamlit-audit-remediation/) (now at `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/`)

---

## Final Status

**Status**: `success` — change fully closed
**Recommendation**: `ready-to-archive` (from verify pass — PASS)

### Verify tally

| Severity | Count | Notes |
|---|---|---|
| CRITICAL | 0 | All invariants zero-hit (M1, H3, M2, C2, H2-bonus). |
| WARNING  | 0 | No blocker. |
| SUGGESTION | 1 | S1 (cosmetic) — `_get_filtered_comparisons` in `ui/tabs/export.py:51-61` is a thin delegation wrapper instead of a full deletion. The H2 SSOT invariant holds (no inline filter loop, all callers route through `apply_comparison_filters`). Optional follow-up: inline body at L116/L202 and remove function. |

All 13 spec requirements satisfied. 755 pytest tests pass. Pipeline smoke (`python test_pipeline.py`) green. H5 pre/post byte-identity test passes on synthetic 4-section DataFrame.

---

## Spec Sync Confirmation

| Field | Value |
|---|---|
| Source (delta) | `openspec/changes/streamlit-audit-remediation/specs/streamlit-legacy-surface-integrity/spec.md` |
| Destination (main spec) | `openspec/specs/streamlit-legacy-surface-integrity/spec.md` |
| Mode | New capability — full spec created from delta, not merged |
| Header conversion | Top-level `### Capability: streamlit-legacy-surface-integrity` promoted to `# Capability: streamlit-legacy-surface-integrity` (canonical for spec store). Delta title `# Spec: streamlit-audit-remediation` replaced with the capability name. Metadata block augmented with `**Archived on**: 2026-07-11` and `**Status**: archived, source of truth` (matches `reconciled-profile-serialization` archive-report template). |
| Verified | File present at `openspec/specs/streamlit-legacy-surface-integrity/spec.md` (the canonical source of truth for this capability). |

All 13 ADDED Requirements preserved with their scenarios:

| # | Requirement | Scenarios |
|---|---|---|
| **C1** | Contour cache invalidation on surface reset | same-grid re-upload, clear precedes rerun |
| **C2** | Production code MUST NOT import from `tests/` | no tests-imports, helpers resolve, tests pass |
| **H1** | cached helper purity in section building | cache safe across sessions |
| **H2** | single source of truth for comparison filtering | no inline filter loops, ai_report delegates |
| **H3** | dead highlight helper removed | only one highlight helper |
| **H4** | berm threshold slider reads detection default | slider default matches config |
| **H5** | shared blast-correlation helper | single definition, both consumers delegate |
| **M4** | section-definition tabs append consistently | manual tab appends, auto tab appends, duplicate name gets suffix, explicit clear preserved |
| **M1** | no `use_container_width` in `ui/` or `app.py` | zero residual hits |
| **M2** | streamlit.components.v2 import | zero v1 hits, v2 resolves |
| **L1–L4** | mechanical cleanups | cleanup invariants hold |

Legacy API Compatibility section and Scope override notice preserved verbatim.

---

## ACTIVE.md Cleanup

| Field | Value |
|---|---|
| Before | Row present: `streamlit-audit-remediation` in `proposal` phase |
| After | Row removed. Placeholder text `_(No active changes.)_` inserted in the table body. |
| File | `openspec/changes/ACTIVE.md` |
| Footer | "Off-limits reminders" section preserved (project convention). |

---

## Archive INDEX Entry

`openspec/changes/archive/INDEX.md` updated with a new entry for this change. Newer-on-top ordering; links to all six archived artifacts (proposal / specs / design / tasks / verify-report / archive-report).

---

## Files Changed (Final Tally)

Source-of-truth artifacts (read-only history):

| Path | Role |
|---|---|
| `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/proposal.md` | 136 lines |
| `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/specs/streamlit-legacy-surface-integrity/spec.md` | delta spec, 166 lines |
| `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/design.md` | 210 lines |
| `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/tasks.md` | 54 lines (19 tasks, all `[x]`) |
| `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/verify-report.md` | 328 lines |
| `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/archive-report.md` | this file |

Implementation artifacts produced by `sdd-apply` (per `git diff --stat 91c5aa2..2b25176 --` scoped to this change's files, 7 commits on branch `sdd/streamlit-audit-remediation`):

| Path | Δ lines | Notes |
|---|---|---|
| `ui/_blast_correlation_shared.py` | new (+322) | New shared module per H5. |
| `tests/test_h5_blast_correlation_shared.py` | new (+310) | Pre/post byte-identity test for H5. |
| `core/blast_correlation.py` | +118 | Additive: 3 top-level helpers (compute_monthly_trend, detect_pf_outliers_iqr, split_campaign) + `__all__`. No signature changes. |
| `ui/modulo_tronadura.py` | +107/-171 | H5 dedup (replace inline kernel with shared import). |
| `ui/tabs/blast_correlation.py` | +25/-49 | H5 dedup + drop try/except for C2. |
| `ui/tabs/ai_report.py` | +52/-66 | M2 (components.v2) + H2 (delegate filter loop, drop local `_filters_summary`). |
| `ui/tabs/export.py` | +9/-16 | H2 — `_get_filtered_comparisons` becomes 3-line delegation wrapper (SUGGESTION S1). |
| `ui/tabs/dashboard.py` | +16/-20 | H2 — delegate filter loop to `apply_comparison_filters`. |
| `ui/tabs/table.py` | +2/-15 | H3 — delete `_highlight_status`. |
| `ui/step2_sections.py` | +31/-23 | H1 (drop cached helper) + M1 (width="stretch") + M4 (append+suffix) + L2 (pop `_profile_figs`) + L4 (drop `import os`). |
| `ui/step1_upload.py` | +4/-2 | C1 — insert `st.cache_resource.clear()` + `st.cache_data.clear()` before mesh-null + `st.rerun()`. |
| `ui/tabs/profiles.py` | +1/-1 | L2 hook (handler in `step2_sections.py`). |
| `ui/filters.py` | +17/-4 | H2a — add `_collect_active_filters_from_session_state()` to `__all__`. |
| `ui/plots.py` | +7/-0 | C1 doc — document `_mesh` (underscore) contract. |
| `ui/sidebar.py` | +1/-1 | H4 — `berm_threshold` slider default from `DETECTION.berm_threshold`. |
| `ui/ref_lines.py` | +1/-1 | L3 — `z_value: float \| None = None` (PEP 604). |
| `ui/modulo_conciliacion.py` | +1/-1 | M1 — width="stretch". |
| `tests/test_ai_service_enrich.py` | +0/-111 | C2b — replace module defs with `from core.blast_correlation import (...)` (signatures preserved exactly). |

Total implementation Δ: **+1,044 / -461 ≈ +583 net** across 18 files (15 modified + 2 new + 1 net-shrink-only). Forecast was ~260 LOC — insertion forecast exceeded by ~4×, but **net LOC after dedup deletions is +583**, in line with the proposal's expectation for H5 (~200 LOC extraction → matches the modulo_tronadura + blast_correlation dedup). The forecast underestimated the volume of new test code (310 lines for H5 byte-identity + 118 lines for C2 helper additions).

Commits (in tasks.md order — CRITICAL → HIGH → MEDIUM → LOW, H5 last of HIGH for bisect):

```
5d667d0 fix(ui): invalidate contour cache on surface reset + relocate trend helpers [C1,C2]
ec1ba02 refactor(ui): drop cached helper, dedupe filter loops, drop dead code [H1,H2,H3,H4]
b35fbd6 refactor(ui): extract shared blast-correlation kernel + scatter builder [H5]
be2a1ce refactor(ui): stretch width, components.v2, append sections with suffix [M1,M2,M4,L4]
7c07ee4 refactor(ui): drop redundant imports + evict profile fig cache + PEP604 type [L1-L4]
2b25176 refactor(ui): dashboard delegates filter loop to apply_comparison_filters [H2]
ec523e6 chore(sdd): mark all tasks complete in streamlit-audit-remediation tasks.md
```

---

## Verification Cross-Reference

| Spec requirement | Verify evidence | Status |
|---|---|---|
| **C1** cache invalidation | `ui/step1_upload.py:45-59` confirmed: `st.cache_resource.clear()` + `st.cache_data.clear()` precede mesh-null + `st.rerun()` | ✅ |
| **C2** no tests-imports | `rg 'from tests\.' ui/` returns 0; `from core.blast_correlation import compute_monthly_trend, detect_pf_outliers_iqr, split_campaign` resolves | ✅ |
| **H1** cached helper purity | `_cached_local_azimuth` removed (0 hits in `ui/`); direct `compute_local_azimuth(mesh, np.array([ox, oy]))` calls at L254, L320, L398 | ✅ |
| **H2** filter SSOT | `rg 'df\["'\'']sector["'\'']\]\.isin' ui/` returns 0; all 4 callers route through `apply_comparison_filters` (one is a 3-line wrapper, see S1) | ✅ |
| **H3** dead code | `rg '_highlight_status' ui/tabs/table.py` returns 0 (the 1 hit in `ui/labels.py:60` is a docstring reference, intentional) | ✅ |
| **H4** berm threshold slider | `ui/sidebar.py:38` = `st.slider("Ángulo máximo berma (°)", 0, 30, int(DETECTION.berm_threshold))` | ✅ |
| **H5** shared helper | `ui/_blast_correlation_shared.py` exports `project_powder_factor_per_section` + `build_pf_deviation_scatter`; both consumers import; pre/post byte-identical on synthetic DataFrame | ✅ |
| **M1** no `use_container_width` | `rg 'use_container_width' ui/ app.py` returns 0 | ✅ |
| **M2** components.v2 | `rg 'streamlit\.components\.v1' ui/` returns 0; `import streamlit.components.v2` resolves; `_html_button` wrapper at L146; `components.component(html=..., js=...)` registered once | ✅ |
| **M4** section append | All 4 tabs (file L115-127, manual L333-351, auto L383-417, interactive L263-264) append; `_N` suffix on collision; "Total acumulado" banner at L438-440 | ✅ |
| **L1–L4** mechanical | L1: only 1 `import pandas as pd` (module-top); no `import numpy as np`. L2: `pop('_profile_figs', None)` at L127/L265/L350/L416. L3: `z_value: float \| None = None` (PEP 604). L4: `import os` kept at L10 because still used at L102/L145 (spec scenario permits this) | ✅ |

Test counts at archive time: **755 passed / 15 pre-existing failures (test_ai_v2_cache.py + test_ai_v2_service.py async + test_api_auth.py sqlite — confirmed pre-existing on clean checkout at HEAD) / 2 skipped**. Pipeline smoke: green (Excel + Word export).

---

## SDD Cycle Complete

The change has been fully planned (`explore` → `propose` → `spec` → `design` → `tasks`), implemented (`apply` — 19 tasks completed, 7 conventional commits in tasks.md order), verified (`verify` — 0 CRITICAL, 0 WARNING, 1 cosmetic SUGGESTION, PASS), and now archived. The capability `streamlit-legacy-surface-integrity` is now part of the canonical specs source of truth.

The temporary lift of the `off_limits` rule for `ui/` (per proposal §Scope override) was used exclusively by this change and does **not** establish precedent. Subsequent changes touching `ui/`, `app.py`, or `cli.py` must re-justify access in their own proposal.

Ready for the next change.

---

## Return Envelope

- **status**: `success`
- **executive_summary**: Change `streamlit-audit-remediation` archived. Delta spec synced to canonical `openspec/specs/streamlit-legacy-surface-integrity/spec.md` (new capability, 13 requirements preserved with all scenarios). Change folder moved to `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/`. `ACTIVE.md` row removed. `archive/INDEX.md` updated (newest on top). Archive report persisted to Engram (topic_key `sdd/streamlit-audit-remediation/archive-report`, project `conciliacion-geo-v02`, capture_prompt=false) and written to disk. SDD cycle closed.
- **artifacts**:
  - `openspec/specs/streamlit-legacy-surface-integrity/spec.md` (new, canonical source of truth)
  - `openspec/changes/archive/2026-07-11-streamlit-audit-remediation/` (new, contains proposal/specs/design/tasks/verify-report/archive-report)
  - `openspec/changes/ACTIVE.md` (modified — row removed)
  - `openspec/changes/archive/INDEX.md` (modified — new entry appended on top)
  - Engram observation `sdd/streamlit-audit-remediation/archive-report` (type=architecture, capture_prompt=false)
- **next_recommended**: `none` — change fully closed. Orchestrator may start the next change. Optional cosmetic follow-up tracked in SUGGESTION S1 (delete `_get_filtered_comparisons` wrapper in `ui/tabs/export.py:51-61`) — non-blocking, can be picked up as a one-line cleanup in any future change.
- **risks**: None blocking. SUGGESTION S1 is cosmetic and explicitly accepted per preflight status ("PASS with 1 non-blocking SUGGESTION"). The `ui/` scope override is one-off per proposal §Scope override; any future `ui/` work must re-justify.
- **skill_resolution**: `paths-injected` — orchestrator provided the explicit skill path `developing-with-streamlit`. Loaded; the v2 component pattern in the implementation (`components.component(html=..., js=...)` registered once + `_html_button` wrapper) matches the skill's `references/custom-components-v2.md` CRITICAL guidance. No skill recommendation issued from `sdd-archive` itself beyond what `sdd-verify` already validated.
