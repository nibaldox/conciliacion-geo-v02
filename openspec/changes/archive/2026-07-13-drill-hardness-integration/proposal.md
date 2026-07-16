# Proposal: drill-hardness-integration

> **Status**: proposal | **Risk**: additive, medium | **Scope override**: temporarily lifts `ui/` off-limits for `ui/modulo_tronadura.py` (drilling-hardness uploader only) per explicit user authorization (precedent: `blast-drill-compliance`, `blast-design-achievement`).

## Intent

`core/drill_compliance` (Gap 3) reports geometric deviation of as-drilled holes vs design. It does NOT report rock resistance to the bit. The standalone `dureza_relativa/` app already classifies drilling CSVs into `dureza` (suave/media/dura/muy dura), `indice_dureza` (0–100), `tasa_penetracion` (m/min), and a per-rig z-score — but its data lives in a separate tool. Fold these signals into the blast DataFrame so engineers correlate hardness against PF, stemming, and overbreak in the same 3D view.

## Scope

### In Scope
- Port `dureza_relativa/classification.py` → `core/drill_hardness.py` (verbatim pure functions, no pandas/numpy, <400 LOC trimmed).
- New `core/drill_hardness_processor.py`: load rig CSV, normalize columns, parse timestamps, compute metrics, handle reperforados (last event per `Pozo`), cKDTree join to blast DF at 2 m default (configurable).
- Optional third uploader "Datos de Perforación (CSV)" in `ui/modulo_tronadura.py` below line 57.
- New color options (Dureza / Índice de Dureza / Tasa de Penetración) + hovertemplate enrichment in the 3D view.
- New `tests/test_drill_hardness.py` (ported parity cases + join cases).

### Out of Scope
- Replacing the standalone `dureza_relativa/` app — it stays the source of the pure module.
- Modifying `core/__init__.py` re-exports; modifying `procesar_pozos`; any existing blast computation.
- Re-deriving hardness thresholds — defaults travel verbatim from `classification.py`.
- Gaps 0/1/2/4/5 — already closed.
- Permanent lift of `ui/` off-limits.

## Capabilities

### New Capabilities
- `blast-drill-hardness`: load rig CSV with column normalization; compute `duracion`, `tasa_penetracion`, `dureza` (categorical), `indice_dureza` (0–100), per-rig z-score; collapse reperforados; cKDTree join to blast DataFrame on (X, Y) within 2 m default; gracefully degrade when rig CSV absent or columns missing.

### Modified Capabilities
- None. `blast-drill-compliance` stays as-is (geometric deviation, 5 m radius, design↔actual).

## Approach

Two additive modules. `core/drill_hardness.py` is a verbatim port of `classification.py` trimmed to <400 LOC (TypedDicts, `DEFAULT_THRESHOLDS`, `STD_EPSILON` unchanged). `core/drill_hardness_processor.py` wraps it: `load_drilling_csv(path)`, `compute_hardness_metrics(df)`, `join_hardness_to_blast(blast_df, hardness_df, radius_m=2.0)` using the `cKDTree` pattern from `core/drill_compliance.py:116` but with a tighter default (same holes, different systems). Reperforados: `df.loc[df.groupby("pozo")["tiempo_final"].idxmax()]`. UI: `st.file_uploader(..., key="drill_hardness_file")` after line 57; absent → app unchanged; present → `_render_hardness_block()` color selector feeding existing 3D `Scatter3d` traces. `DrillHardnessDefaults` dataclass in `core/config.py` (radius_m=2.0); NOT re-exported from `core/__init__.py`.

## Affected Areas

| Path | Δ |
|---|---|
| `core/drill_hardness.py` | new (~330 LOC) |
| `core/drill_hardness_processor.py` | new (~180 LOC) |
| `core/config.py` | +`DrillHardnessDefaults` |
| `tests/test_drill_hardness.py` | new (~8 tests) |
| `ui/modulo_tronadura.py` | +uploader + selector (override) |
| `openspec/specs/blast-drill-hardness/spec.md` | new |
| `openspec/changes/ACTIVE.md` | append row |

## Risks

| Risk | Lik | Mit |
|---|---|---|
| `ui/` edit rejected | Med | Explicit authorization + blast-module-only; blast-drill-compliance precedent |
| Mis-join across rigs | Low | 2 m is tight; unmatched dropped, never mis-attributed |
| Reperforados overwrite | Med | Group by `Pozo`, `idxmax("tiempo_final")` — documented + tested |
| `Prof. por Operador` missing | Med | Fallback to duration-only hardness; pipeline continues |
| `core/__init__.py` drift | Low | Not re-exported; imported from submodule |
| Radius overlap (5 m vs 2 m) | Low | Distinct module + distinct defaults; coexist |

## Rollback Plan

Revert PR (2 new modules, 1 config addition, 1 UI additive block, 1 new test file). No DB migrations, no flags, no `core/__init__.py` changes. Drilling CSV uploader is opt-in: removing the file returns the app to its pre-change state.

## Dependencies

`scipy.spatial.cKDTree` (already in `core/drill_compliance.py`), `pandas`, `numpy`, stdlib `math` + `datetime`. No new packages.

## Success Criteria

- [ ] `core/drill_hardness.py` ports all six pure functions with identical numerical output (parity tests pass).
- [ ] `compute_hardness_metrics` + `join_hardness_to_blast` end-to-end on synthetic CSV with ≥8 pytest cases.
- [ ] Drilling CSV optional: app runs identically when uploader empty.
- [ ] 3D view accepts Dureza, Índice de Dureza, Tasa de Penetración as color axes; hovertemplate shows new fields.
- [ ] `core/__init__.py` byte-identical (no new re-exports).
- [ ] Reperforado logic: 3 duplicate `Pozo` rows collapse to 1 keyed by max `Tiempo Final`.