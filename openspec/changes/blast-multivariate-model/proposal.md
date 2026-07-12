# Proposal: Blast Multivariate Damage Model

## Intent

fit_powder_factor_damage_model regresses mono-variable PF on mean overbreak; the advisor's _invert_pf inverts that line. PF is volumetric kg/m3 and conflates burden, S/B, stemming, diameter. Equal PF with different burden yields different overbreak, suppressing R² and thrashing recommendations. Add a multivariate model so the advisor can invert the burden coefficient, keeping PF and stemming separable.

## Scope

In: fit_multivariate_damage_model in core/blast_model.py (additive, no signature change to fit_powder_factor_damage_model). OLS via numpy.linalg.lstsq with intercept; SE/t-stats via manual covariance on XᵀX; two-sided p-values via scipy.stats.t.sf; overall F via scipy.stats.f.sf. Returns betas, std-errors, p-values, R², adjusted R², n, condition number, confidence, features used. Feature auto-resolution via core.column_utils.first_present_column for PF, burden, S/B, stemming. recommend_burden_adjustment in core/blast_advisor.py (additive) solves for burden with others at section means, reusing _classify_feasibility with burden bounds (0.5·B to 2·B). recommend_multivariate picks multivariate when n ≥ 12 and ≥3 valid predictors, else delegates. Tests cover synthetic truth recovery, R² lift vs mono, n<12 guard, advisor inversion, multicollinearity flag.

Out: drill-pattern compliance (Gap 3), PF prediction (Gap 4); touching fit_powder_factor_damage_model or recommend_pf_adjustment; sklearn; core/__init__.py re-exports.

## Capabilities

New: blast-multivariate-correlation — multivariate damage regression plus burden-aware advisor inversion, additive alongside the mono-variable PF correlation. Modified: none — blast-design-achievement and blast-hole-attribution stay untouched.

## Approach

OLS via np.linalg.lstsq with intercept; adjusted R² guards small-n overfit. np.linalg.cond(X) ≥ 30 downgrades confidence to surface PF↔burden collinearity. Advisor inverts one feature at a time, fixing others at section means. UI goes in the spec phase: a "Modelo multivariado" expander under the PF block.

## Affected Areas

- core/blast_model.py — additive new function.
- core/blast_advisor.py — additive new functions.
- tests/test_blast_multivariate_model.py — new, ~12 tests.
- ui/tabs/blast_correlation.py — additive expander; maintainer override required.

## Risks

- PF↔burden multicollinearity (high): condition-number flag, prefer S/B over S.
- Small-n over-fit (medium): min_samples=12, adjusted R², tightened classifier.
- Real data missing burden/S/B (high): column-utils fallback, expose features_used.
- UI override for the blast correlation tab (low — precedent set by blast-design-achievement).

## Rollback Plan

Drop the new function, advisor additions, and test file. git revert works cleanly — zero edits to existing signatures, so the test suite stays green on main after revert. The UI expander is fully isolated; deleting it restores the prior tab.

## Dependencies

- numpy + scipy.stats (already imported lazily in core/blast_model.py); core.column_utils.first_present_column and core.compliance_status (existing). Maintainer scope override for the blast correlation UI tab.

## Success Criteria

- pytest tests/ -v --tb=short passes 768+ existing tests.
- Synthesized 3-feature data recovers true coefficients within 2·SE; R² lifts vs mono; n < 12 → INSUFFICIENT; condition ≥ 30 downgrades confidence.
- recommend_burden_adjustment recovers input burden within 5%; recommend_pf_adjustment byte-identical on existing fixtures.
- git diff main...HEAD -- core/__init__.py is empty.
