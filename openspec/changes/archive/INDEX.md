# Archived Changes

> Audit trail of completed SDD changes. Each entry is dated and links to
> the archived change folder under `archive/`. Entries are append-only;
> archived changes are immutable historical records.

## Index

| Archived on | Change | Status | Verify result | Artifacts |
|---|---|---|---|---|
| 2026-07-13 | [`blast-backbreak-prediction`](./2026-07-13-blast-backbreak-prediction/) | archived (pass) | 0 CRITICAL / 0 WARNING / 14/14 tests pass — empirical + multivariate paths, Holmberg-Persson cross-check | [proposal](./2026-07-13-blast-backbreak-prediction/proposal.md) · [specs](./2026-07-13-blast-backbreak-prediction/specs/blast-backbreak-prediction/spec.md) · [design](./2026-07-13-blast-backbreak-prediction/design.md) · [tasks](./2026-07-13-blast-backbreak-prediction/tasks.md) |
| 2026-07-12 | [`blast-drill-compliance`](./2026-07-12-blast-drill-compliance/) | archived (pass) | 0 CRITICAL / 0 WARNING / 0 SUGGESTION — 10/10 tests, 817 suite green | [proposal](./2026-07-12-blast-drill-compliance/proposal.md) · [specs](./2026-07-12-blast-drill-compliance/specs/blast-drill-compliance/spec.md) · [design](./2026-07-12-blast-drill-compliance/design.md) · [tasks](./2026-07-12-blast-drill-compliance/tasks.md) |
| 2026-07-12 | [`blast-multivariate-model`](./2026-07-12-blast-multivariate-model/) | archived (pass-with-warnings) | 0 CRITICAL / 1 WARNING (collinearity scale-sensitivity, fixed inline) / 0 SUGGESTION | [proposal](./2026-07-12-blast-multivariate-model/proposal.md) · [specs](./2026-07-12-blast-multivariate-model/specs/blast-multivariate-correlation/spec.md) · [design](./2026-07-12-blast-multivariate-model/design.md) · [tasks](./2026-07-12-blast-multivariate-model/tasks.md) · [verify-report](./2026-07-12-blast-multivariate-model/verify-report.md) |
| 2026-07-12 | [`blast-hole-attribution`](./2026-07-12-blast-hole-attribution/) | archived (pass-with-suggestions) | 0 CRITICAL / 0 WARNING / 3 SUGGESTION (cosmetic — 🎯 emoji, no CSV export, selectbox uniqueness) | [proposal](./2026-07-12-blast-hole-attribution/proposal.md) · [specs](./2026-07-12-blast-hole-attribution/specs/blast-hole-attribution/spec.md) · [design](./2026-07-12-blast-hole-attribution/design.md) · [tasks](./2026-07-12-blast-hole-attribution/tasks.md) · [verify-report](./2026-07-12-blast-hole-attribution/verify-report.md) · [archive-report](./2026-07-12-blast-hole-attribution/archive-report.md) |
| 2026-07-12 | [`blast-design-achievement`](./2026-07-12-blast-design-achievement/) | archived (pass-with-suggestions) | 0 CRITICAL / 0 WARNING / 2 SUGGESTION (cosmetic — accent on "Correlación", tasks.md untracked) | [proposal](./2026-07-12-blast-design-achievement/proposal.md) · [specs](./2026-07-12-blast-design-achievement/specs/blast-design-achievement/spec.md) · [design](./2026-07-12-blast-design-achievement/design.md) · [tasks](./2026-07-12-blast-design-achievement/tasks.md) · [verify-report](./2026-07-12-blast-design-achievement/verify-report.md) · [archive-report](./2026-07-12-blast-design-achievement/archive-report.md) |
| 2026-07-11 | [`streamlit-audit-remediation`](./2026-07-11-streamlit-audit-remediation/) | archived (pass-with-suggestion) | 0 CRITICAL / 0 WARNING / 1 SUGGESTION (cosmetic wrapper) | [proposal](./2026-07-11-streamlit-audit-remediation/proposal.md) · [specs](./2026-07-11-streamlit-audit-remediation/specs/streamlit-legacy-surface-integrity/spec.md) · [design](./2026-07-11-streamlit-audit-remediation/design.md) · [tasks](./2026-07-11-streamlit-audit-remediation/tasks.md) · [verify-report](./2026-07-11-streamlit-audit-remediation/verify-report.md) · [archive-report](./2026-07-11-streamlit-audit-remediation/archive-report.md) |
| 2026-07-10 | [`reconciled-profile-v2-default`](./2026-07-10-reconciled-profile-v2-default/) | archived (pass-with-warnings) | 0 CRITICAL / 1 WARNING (LOC budget) / 1 SUGGESTION (tasks.md stale text) | [proposal](./2026-07-10-reconciled-profile-v2-default/proposal.md) · [specs](./2026-07-10-reconciled-profile-v2-default/specs/reconciled-profile-serialization/spec.md) · [design](./2026-07-10-reconciled-profile-v2-default/design.md) · [tasks](./2026-07-10-reconciled-profile-v2-default/tasks.md) · [verify-report](./2026-07-10-reconciled-profile-v2-default/verify-report.md) · [archive-report](./2026-07-10-reconciled-profile-v2-default/archive-report.md) |

## Conventions

- One row per archived change.
- Newest entries on top.
- Archive folder name is `YYYY-MM-DD-{change-name}/`.
- The archive is an audit trail — never modify or delete archived
  changes. Corrections go in a new change.