# Proposal: geotechnical-decision-grade-upgrade

> Status: proposal | Risk: additive, medium | Scope: core/, api/, web/, reports | 8 sequential single-writer work units S0→S7.

## Intent

Project is not yet decision-grade for slope geotechnics: P0 per-bench slice bug, score drift (60/10/30 vs 60/20/20), dormant bank-hole attribution, geometric-only FS/wedge/toppling proxies, no signed area/volume, no mesh QA/QC, no per-sector calibration, no monitoring. Add an additive decision layer over the existing geometric core.

## Scope

**In** — eight sprints: S0 P0 fixes (60/20/20 + threshold 70; `attribute_failure_to_holes` repair); S1 causal explain; S2 blast attribution; S3 signed area/volume; S4 structural + water (Markland); S5 mesh QA/QC; S6 confidence + probabilistic + monitoring (Monte Carlo needs caller-supplied distributions + `n_iterations`; CUSUM/EWMA); S7 sector + temporal calibration (LOO + train-on-prior/validate-on-current).

**Out**: modify `app.py`, `ui/`, `cli.py`, `core/__init__.py`; invent defaults (`r_u`, friction, FS target, MC sample count, distribution shape); replace binary `CUMPLE/NO CUMPLE`; QA/QC as a hard blocker.

## Capabilities

**Modified**: `blast-hole-attribution` (repair dormant projector binding); `blast-multivariate-correlation` (sector + temporal fields); `reconciled-profile-serialization` (local-angle semantics plus advisory/confidence/volume fields; preserve `ReconciledProfile`).

**New**: `score-contract`; `blast-bench-causal-explain`; `blast-bench-attribution-api`; `bench-area-volume`; `geotechnical-advisory-assessment` (Markland + water + kinematic, separate from verdict); `mesh-qaqc` (provenance + CRS/datum/units + `UNVERIFIED` warning); `monitoring-trend` (CUSUM/EWMA); `sector-temporal-calibration` (per-sector + temporal fit with LOO).

## Approach

Stratified decision layer over the geometric core. New `core/` helpers imported from submodules directly. Additive `api/` on `/api/v1/*`.

**Verdict separation rule.** Visible verdict = deterministic 60/20/20 score at threshold 70 → binary `CUMPLE/NO CUMPLE`. Structural, water, kinematic, probabilistic, and confidence are advisory only; they MUST NEVER combine with, override, or replace the binary verdict. Caller/project configuration supplies thresholds; missing data yields `INSUFFICIENT_DATA`.

## Affected Areas

New `core/`: score_weights, structural_model, bench_metrics_volume, mesh_qaqc, confidence_propagation, probabilistic_stability, monitoring_trend, calibration_by_sector. Modified `core/`: profile_extract, profile_compliance, blast_correlation, calculo_tronadura, stability_analysis, config, excel_writer, report_generator, ai_v2/builder. Additive `api/` + `web/`. Off-limits: `app.py`, `ui/`, `cli.py`, `core/__init__.py`.

## Risks

Write races; TS↔Python score drift; Markland/MC inventing numbers; `UNVERIFIED` QA/QC ignored; bbox-heuristic CRS inference. Mitigations: sequential writer per sprint; `core/score_weights.py` sole source + weights-sum-to-100 contract test; mandatory caller-supplied inputs (else `INSUFFICIENT_DATA`); surfaces as warning in API/web/Excel/Word; forbidden (only `.prj` + filename hints).

## Rollback

Each sprint = own commit + push on `feature/geotechnical-decision-grade-upgrade`. `git revert <sha>` per sprint. All changes additive; no production signature breaks. `core/__init__.py`, `app.py`, `ui/`, `cli.py` untouched.

## Dependencies

Strict order S0→S1→S2→S3→S4→S5→S6→S7. CI deps unchanged.

## Success Criteria

- [ ] Eight sequential sprints, each with own commit + push; CI green.
- [ ] Binary `CUMPLE/NO CUMPLE` preserved at threshold 70 / 60/20/20; `INSUFFICIENT_DATA` is metric-availability only.
- [ ] `attribute_failure_to_holes` regression test passes with real `SectionLine` and asserts `n_holes > 0`; `core/score_weights.py` sole source of truth.
- [ ] `app.py`, `ui/`, `cli.py`, `core/__init__.py` unchanged; missing inputs → `INSUFFICIENT_DATA`; QA/QC unknown → `UNVERIFIED` warning.