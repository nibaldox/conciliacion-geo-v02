# Change: blast-design-achievement

> **Status**: proposal | **Risk**: additive, low | **Scope override**: temporarily lifts `ui/` off-limits (precedent: `2026-07-11-streamlit-audit-remediation`); blast tab only.

## Why

Two closed-loop blast→design KPIs missing:

- **Stemming ↔ crest damage** — symmetric to `compute_pasadura_toe_correlation` (`core/blast_model.py:172`). Short stemming vents gases upward → catch bench blown off (safety-critical). `Taco_m` enriched; `delta_crest` on every comparison row.
- **Per-malla design achievement score** — `_compute_malla_correlation` (`ui/tabs/blast_correlation.py:580`) aggregates per-malla deviations/PF/energy but no single 0-100% KPI. Ops needs "Malla A achieved 85% of design" for upward reporting.

Both behavior-preserving; consume existing fields.

## Scope

**In**: `compute_stemming_crest_correlation` (mirrors pasadura) in `core/blast_model.py`; new `core/blast_achievement.py` with `compute_design_achievement_score`; `_render_stemming_crest_block` next to `_render_pasadura_toe_block` (line 330); extra column in per-malla dataframe (line 342); `tests/test_blast_model.py` +4 tests; new `tests/test_blast_achievement.py` (4 tests).

**Out**: Gaps 0/1/3/4 (separate). Stability analysis — deferred. M3 — unrelated. `web/`, `api/` — no changes. Permanent lift of `ui/` off-limits.

## Capabilities

**New** — `blast-design-achievement`: (a) stemming→crest Pearson correlation; (b) per-malla 0-100% achievement score with crest/toe/berm breakdown; (c) existing PF→damage regression + pasadura→toe unchanged; (d) graceful empty/missing-data.

**Modified**: None.

## Approach

**Gap 2** — `compute_stemming_crest_correlation(blast_df, comparisons, bench_height=15.0, tolerance=5.0)` in `core/blast_model.py`. Group `blast_df` by `(Z_collar - bench_height).round(0)` → mean `Taco_m` per floor; mean `delta_crest` per `level` from comparisons; pair → Pearson r + p-value (lazy `scipy.stats.pearsonr`). Interpret: `r < -0.3` → gases venting up; `r > 0.3` → energía baja; else weak/null. Same shape + guards as pasadura. Not in `core/__init__.py`.

**Gap 5** — `compute_design_achievement_score(comparisons, malla_column=None)` in new `core/blast_achievement.py` (matches `core/blast_advisor.py` pattern). Returns `{global, breakdown, per_malla, n_total, n_passing_crest/toe/berm}`. Weights: 0.4/0.3/0.3. Partial credit: `CUMPLE=1.0`, `FUERA=0.5`, else `0.0`. Reuses `height_status`/`angle_status`/`berm_status`. No `malla_column` → `per_malla=None`.

**UI** (`ui/tabs/blast_correlation.py`): `_render_stemming_crest_block` mirroring lines 864-903 (same layout, Spanish); append `score_pct` (`'Logro Diseño (%)'`) to `df_malla_corr` + `display_map_m` at lines 342-355; global-score `st.metric` above the per-malla dataframe.

## Affected Areas

| Path | Δ |
|---|---|
| `core/blast_model.py` | +`compute_stemming_crest_correlation` |
| `core/blast_achievement.py` | new |
| `tests/test_blast_model.py` | +4 tests |
| `tests/test_blast_achievement.py` | new (4 tests) |
| `ui/tabs/blast_correlation.py` | +renderer + column (scope override) |
| `openspec/specs/blast-design-achievement/spec.md` | new (sdd-spec) |
| `openspec/changes/ACTIVE.md` | append row |

## Risks

| Risk | Mit |
|---|---|
| `ui/` edit rejected | Orchestrator authorization + blast-tab-only, additive. |
| `Taco_m` missing | Empty-shape dict + Spanish guard, no crash. |
| Weights disagree | Module constants, refactor-free tuning in sdd-spec. |
| Malla col missing | `per_malla=None`, global score only. |

## Rollback

Revert PR (3 modified + 2 new files). No DB/schema/flags. Pasadura→toe + PF→damage render unchanged (additive).

## Dependencies

`scipy.stats.pearsonr` (`core/blast_model.py:298`), `core.compliance_status`, `DEFAULTS.blast_default_bench_height`.

## Success Criteria

- [ ] `compute_stemming_crest_correlation` mirrors pasadura.
- [ ] `_render_stemming_crest_block` renders with Spanish strings, no crash on empty.
- [ ] Per-malla table gains `Logro Diseño (%)` column (0-100).
- [ ] Pasadura→toe + PF→damage regression render unchanged.
- [ ] `pytest tests/test_blast_model.py tests/test_blast_achievement.py -v` passes (≥8 new tests).

## Forecast (400-line budget)

`core/blast_model.py` +~80 + `core/blast_achievement.py` ~90 + tests ~140 + UI +~50 ≈ **~360 LOC**. Single PR, no chaining.