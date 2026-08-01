# Exploration: `geotechnical-decision-grade-upgrade`

**Change name**: `geotechnical-decision-grade-upgrade`
**Phase**: `sdd-explore`
**Fingerprint**: `sdd-explore|geotechnical-decision-grade-upgrade|resume-gatefix1`
**Persistence**: hybrid (filesystem + Engram)
**Artifact language**: English (technical artifact)
**Date**: 2026-07-30
**Status**: ready for `sdd-propose`

| Continuation and explicit verification of audit Engram `#189`
| (`geotechnical gaps`) and sdd-init Engram `#190` (`conciliacion-geo-v02`).
| This artifact is the corrected re-run after the prior exploration was
| rejected by the automatic gate for factual and geotechnical-policy drift,
| and applies the **gate-fix #1** corrections for citation accuracy,
| worktree state, `core/__init__.py` policy, verdict separation, and
| concurrent-writer policy.

### Prior corrections preserved verbatim

The following corrections from the previous accepted re-run are kept in
full force and are re-affirmed here; the gate-fix #1 changes only add
precision, never weaken them:

1. The line-980 mask `(Z_toe <= z_lo) & (Z_toe >= z_hi)` with
   `crest > toe` is mathematically the interval `[z_hi, z_lo]`
   (confusing variable names but not empty). The empty-result behaviour
   of `attribute_failure_to_holes` comes from the **broad
   `except Exception`** that swallows the `TypeError` raised by Python
   argument binding before `proyectar_pozos_en_seccion` executes, because
   the line-980 caller passes `(df_pozos, section)` instead of `(df_pozos,
   origin, azimuth, length, ...)`. **Gate-fix #1 additionally corrects
   the projector citation**: the real signature is at
   `core/calculo_tronadura.py:246-253`, not `core/blast_correlation.py`,
   and the `TypeError` occurs at argument binding, not from invented
   `section[0]` indexing.
2. **Eight sequential work units** (Sprint 0 through Sprint 7).
3. **No invented `r_u`, friction angle (`phi`), FS target, or Monte Carlo
   distribution / sample count.** Missing inputs produce
   `INSUFFICIENT_DATA`.
4. **Binary `CUMPLE / NO CUMPLE` verdict** with `60 / 20 / 20` and
   threshold `70`; **confidence** is a separate axis that never breaks
   the binary. **Gate-fix #1 additionally enforces**: structural,
   water, kinematic, probabilistic, and confidence outputs are
   **separate advisory dimensions** and MUST NEVER combine with,
   override, or replace the binary verdict. `INSUFFICIENT_DATA` is a
   metric-availability state, **never** a third conformity state.
5. Volume method: signed normal distance on **3D bank-clipped design vs
   as-built surfaces**; section-prism fallback with explicit
   spacing / orientation uncertainty when 3D inputs are unavailable.
6. Structural kinematics: Markland test requires face orientation
   **plus** explicit discontinuity sets; geometry-only wedge / toppling
   remains a proxy.
7. QA/QC: the system MUST NOT infer reliable CRS / units from bbox
   heuristics alone; unknown metadata stays `UNKNOWN / UNVERIFIED` as a
   **warning**, not a blocker.
8. `core/__init__.py` is the legacy stable public API and is kept
   untouched. **Gate-fix #1 additionally enforces**: no new re-exports
   may be added and no existing re-exports may be removed; new helpers
   are imported from their submodules directly
   (`from core.<submodule> import <name>`).
9. **No concurrent writer subagents**, even on disjoint file sets,
   because no isolated worktrees have been approved for this change.
   Each work unit has exactly one sequential writer subagent.
   Parallelism is allowed only for read-only review / research.
   **Eight sequential work units total.**

---

## Executive Summary

The project has a robust geometric core (RDP simplification, Hungarian
matching, tripartite tolerances, reconciled profile, FS proxy, blast
correlation). However, viewed through a slope-geotechnical lens, it is **not
yet decision-grade**: several critical decisions are still taken with geometric
proxies or with hardcoded constants that do not reflect the real rock-mass
state. This exploration continues the audit (`#189`) and proposes a
**stratified, additive, non-monolithic** architecture that delivers, in
decreasing order of expected return, the seven improvement groups already
detected: (P0) per-bench local-angle bug + 60/20/20 score contract;
(P0) operative cause→hole→bench traceability; (P0) screen-vs-design
semantics so screening never bleeds into design verdict; (P1) signed
area/volume per bench with explicit uncertainty; (P1) structural model +
water + FS **only when inputs are explicit**; (P2) per-sector calibration,
probabilistic monitoring, mesh QA/QC.

**All deliverables are additive**, respect `off_limits`
(`app.py`, `ui/`, `cli.py` strictly untouched; `core/__init__.py` is the
legacy stable public API and is **kept untouched** — new helpers are
imported from their submodules directly, e.g.
`from core.score_weights import BERM, ANGLE, HEIGHT, PASS_THRESHOLD`),
and run as **eight sequential work units (Sprint 0 through Sprint 7)** with
shared-file conflicts handled by serialising dependent sprints. Where two
work units both need the same file (notably `core/profile_compliance.py`,
`core/stability_analysis.py`), they are split into separate sprints with an
explicit dependency arrow so no concurrent writers collide.

**Hard rules carried over from the audit and the task contract,
strengthened by the gate-fix #1 corrections:**

- No invented `r_u`, friction angle (`phi`), FS target, or Monte Carlo
  distributions / sample counts. Where such inputs are required, the system
  MUST demand explicit traceable inputs and return `INSUFFICIENT_DATA` (with
  the affected metric flagged as screening-only) when the inputs are absent.
- The user-facing compliance verdict stays binary `CUMPLE / NO CUMPLE` with
  `60 / 20 / 20` and threshold `70`; **confidence** is a separate axis that
  never breaks the binary. **Gate-fix #1 additionally**:
  structural, water, kinematic, probabilistic, and confidence outputs are
  **separate advisory dimensions** and MUST NEVER combine with, override,
  or replace the binary verdict. `INSUFFICIENT_DATA` is a metric-
  availability state, **never** a third conformity state.
- Volume method: signed normal distance on **3D bank-clipped design vs
  as-built surfaces**; if 3D inputs are unavailable, fall back to a
  section-prism method whose spacing and orientation uncertainty are
  reported explicitly.
- Structural kinematics: Markland test requires face orientation **plus**
  explicit discontinuity sets; geometry-only wedge/toppling remains a
  proxy.
- QA/QC: the system MUST NOT infer reliable CRS / units from bbox
  heuristics alone; unknown metadata stays `UNKNOWN / UNVERIFIED` and is a
  **warning**, not a blocker.
- `app.py`, `ui/`, `cli.py` are off-limits.
- `core/__init__.py` is the legacy stable public API and is **kept
  untouched** (no new re-exports, no removals). New helpers are imported
  from their submodules directly (see AGENTS.md "Import rules — gotcha").
- **Eight sequential work units** (Sprint 0 through Sprint 7); each
  work unit has exactly **one sequential writer** subagent — no
  concurrent writer subagents, even over disjoint file sets, because
  no isolated worktrees have been approved for this change.
  Parallelism is allowed only for read-only review / research.

**Recommendation**: eight sequential sprints (Sprint 0 through Sprint 7).
Each sprint has its own commit and push. Each sprint has **one
sequential writer** subagent — no concurrent writer subagents are
permitted, even over disjoint file sets, because no isolated worktrees
have been approved for this change. Parallelism is permitted only for
**read-only review and research** (e.g. multiple reviewers reading the
same artifacts, or read-only research sweeps across
documentation/git history), never for file writes. Within a sprint,
all file writes are sequential.

---

## 1. Verification of the prior audit (Engram `#189`)

Continuation of `#189` (audit/geotechnical-gaps) and `#190`
(sdd-init/conciliacion-geo-v02). Verified line-by-line against the current
codebase on `main`. **Production code (`core/`, `api/`, `web/`) is
unchanged** in the working tree; only the SDD artifacts under
`openspec/` (`openspec/config.yaml`, `openspec/sdd-init/...`,
`openspec/changes/geotechnical-decision-grade-upgrade/`) are
modified or untracked. No new helper modules, no API endpoints, no UI
components have been added by this exploration.

| Audit claim | Code verification (current) | Status |
|---|---|---|
| Per-bench angle biased by whole profile | `core/profile_extract.py:697-701` — `idx_start=0; idx_end=len(dx)` uses the **entire** mesh sample, not the bench's local span | ✅ Confirmed (P0) |
| Executed score 60/10/30, visible contract 60/20/20 | `core/profile_compliance.py:239,243,247` hardcodes `60`, `10`, `30`; `web/src/components/results/Dashboard.tsx:73` declares `SCORE_WEIGHTS = { berm:60, angle:20, height:20 }` | ✅ Confirmed (P0 drift) |
| `attribute_failure_to_holes` duplicated | `core/blast_correlation.py:320` (correct signature, correct mask); `core/blast_correlation.py:980` (re-declared: same `def attribute_failure_to_holes(...)` overrides the earlier binding, so the runtime symbol comes from line 980) | ✅ Confirmed (P0 — the line-980 version is the *active* one) |
| `explain_non_compliance` orphan | `core/blast_advisor.py:760-823` exists; zero references in `api/`, `web/src/`, `ui/`, or `core/ai_v2/` | ✅ Confirmed |
| FS / wedge / toppling without structural model, water, uncertainty | `core/stability_analysis.py:204-307` (`compute_section_health_score` weights 0.30 / 0.20 / 0.20 / 0.15 / 0.10 / 0.05), `core/bench_hazards.py:126-167` (`_detect_wedge_shape_in_face`), `core/bench_hazards.py:170-209` (`_detect_toppling_potential`) — all **purely geometric**, no discontinuity sets, no `r_u`, no Monte Carlo | ✅ Confirmed (proxies only) |
| `attribute_failure_to_holes` line 980 — wrong projector signature is swallowed by `except Exception` | The real signature of `proyectar_pozos_en_seccion` lives at `core/calculo_tronadura.py:246-253` and requires `(df_pozos, origin: np.ndarray, azimuth: float, length: float, tolerance: float = 10.0, fecha_corte: "str | None" = None)`. The line-980 caller in `core/blast_correlation.py` passes only `(df_pozos, section)` where `section` is a `SectionLine` dataclass (`core/section_cutter.py:9-22` with attributes `.origin`, `.azimuth`, `.length`). Python raises `TypeError` during argument binding, before the projector body executes, because required arguments `azimuth` and `length` are missing. The `try: ... except Exception: return None` at line 1009-1010 **swallows the TypeError** and returns `None`, so the function never reaches the mask logic when called this way. No invented `section[0]` indexing exists in `proyectar_pozos_en_seccion`. | ✅ Confirmed (P0 — the active definition silently returns `None`) |
| `attribute_failure_to_holes` line 980 — bad variable names do **not** make the mask empty | Local reading: `crest > toe` is the normal case. `z_lo = max(crest, toe) + tol = crest + tol` (upper bound) and `z_hi = min(crest, toe) - tol = toe - tol` (lower bound). With `crest > toe` we get `z_lo > z_hi` numerically, but the mask is `(Z_toe <= z_lo) & (Z_toe >= z_hi)`, which is the standard "between-with-lower-and-upper" pattern `[z_hi, z_lo]`. The variable names are confusing but the test **does** select the interval `[toe - tol, crest + tol]` — i.e. the intended interval, just with reversed naming. The empty-result behaviour is caused by the `try/except` short-circuit on the wrong projector signature, **not** by the inequality itself. | ✅ Confirmed (correction to prior claim — mask selects the interval despite confusing names) |
| `attribute_failure_to_holes` not wired to UI/API/reports | `grep -r "attribute_failure_to_holes"` finds only definitions in `core/blast_correlation.py` and one docstring in `core/blast_advisor.py:777`; **zero** call sites in `api/`, `web/src/`, `ui/`, `core/ai_v2/` | ✅ Confirmed (dormant) |
| `compute_section_health_score` not exposed via API nor UI | `grep -r "compute_section_health"` finds only `core/ai_v2/builder.py:44` (LLM context) and `core/alert_system.py:14` (internal); **zero** HTTP endpoints | ✅ Confirmed |
| Score weights centralised only in TS — backend duplicates the formula in `_build_match_row` with different weights | `core/profile_compliance.py:239/243/247` uses hardcoded literals; no Python module re-exports `SCORE_WEIGHTS`. Drift is silent. | ✅ Confirmed |
| Mesh QA/QC absent | `core/mesh_handler.py` only loads bbox + face count + volume; **no** CRS / datum / epoch / units / provenance capture | ✅ Confirmed |

The audit is fully reproducible; every row matches an actual grep or file
read. The prior exploration overstated two points, however:

1. The line-980 mask was claimed to be "always empty". That is wrong: the
   inequality `(Z_toe <= z_lo) & (Z_toe >= z_hi)` with `z_lo > z_hi`
   *mathematically* describes the interval `[z_hi, z_lo]` — confusingly
   named but not empty. The real reason the function always returns `None`
   is the **broad `except Exception`** that swallows the `TypeError`
   raised by Python argument binding before the projector body executes.
   The signature at `core/calculo_tronadura.py:246-253` requires
   `(df_pozos, origin, azimuth, length, ...)`; the call
   `(df_pozos, section)` omits `azimuth` and `length`.
2. `compute_section_health_score` weights (`0.30 / 0.20 / 0.20 / 0.15 / 0.10
   / 0.05`) and `STABILITY.rockfall_catch_factor = 0.6` are real, in-code
   defaults. Other "defaults" found in the prior exploration (`r_u =
   0.15 / 0.05`, `phi = 35°`, `FS > 1.3`, `toppling_dip_threshold_deg =
   75.0`, Monte Carlo `n_iter = 1000`, distribution shapes
   `N(c_nominal, 0.2·c_nominal)` etc.) are **not** in the current code and
   must not be invented here.

---

## 2. Current state (what the system does today)

### 2.1 Geometric core (`core/`)

- `param_extractor.py` → RDP → angle classification → merge → Hungarian
  matching for design vs topography.
- `profile_extract.py:677-736` (`_build_face_bench`) — P0 bug:
  `idx_start = 0; idx_end = len(dx)` (line 697-698) so `local_len /
  local_ang` covers the **whole** mesh sample, not the bench's span.
- `profile_extract.py:739-746` (`_weighted_face_angle`) — correctly weights
  by `local_len` under the `local_ang > face_threshold - margin` mask, but
  receives the global arrays.
- `profile_compliance.py:223-281` (`_build_match_row`) — score 60 / 10 / 30
  hardcoded (line 239, 243, 247).
- `bench_classify.py` — berm/ramp classifier with
  `RampDetection(min_width=15.0, max_width=42.0)`.

### 2.2 Stability / kinematic (`core/stability_analysis.py`,
`core/bench_hazards.py`)

- `compute_section_health_score` (0–100) combines: FS (0.30), berm (0.20),
  overhang (0.20), wedge (0.15), toppling (0.10), anisotropy (0.05).
  Weights are hardcoded in the docstring and body, **not** exposed in
  `core/config.py`.
- `compute_planar_factor_of_safety` (Hoek & Bray 1981 form) accepts
  `water_pressure_ratio=0.0`; callers pass `0.0` by default and no seasonal
  / piezometer logic exists.
- `_detect_wedge_shape_in_face` and `_detect_toppling_potential` are
  **purely geometric** proxies; they never read structural data. Thresholds
  in the existing code: wedge dihedral `< 60°` or fallback
  `face_angle > 65° AND bench_height > 12 m`; toppling `> 80°`, or
  `> 75° AND h > 15 m`, or `> 65° AND h > 12 m AND upper face > 75°`.
- `core/geology.py` exposes `estimate_rock_strength_from_gsi` and
  `rmr_to_gsi` (Phase 21), invoked from `_resolve_face_angle_strength`
  **only when callers pass GSI explicitly**. There is no automatic GSI
  catalog.

### 2.3 Blast → bench traceability (`core/blast_correlation.py`)

- `attribute_failure_to_holes` is **defined twice**:
  - Line 320 — `section` is used with `getattr(section, "origin"/"azimuth"/"length")`, calls `proyectar_pozos_en_seccion(df_pozos, origin=..., azimuth=..., length=...)` (correct), uses `between(z_min, z_max, inclusive="both")` (correct).
  - Line 980 — passes `(df_pozos, section)` to `proyectar_pozos_en_seccion` (wrong signature → `TypeError` inside the projector, swallowed by `except Exception: return None`). Local variable names (`z_lo`, `z_hi`) are reversed relative to their values, but the mask `(Z_toe <= z_lo) & (Z_toe >= z_hi)` is the standard interval form `[z_hi, z_lo]` — it selects the interval, it is not empty.
  - Because Python binds `attribute_failure_to_holes` to the **last** `def` at module scope, the line-980 version is the runtime symbol; the line-320 version is dead code.
- `explain_non_compliance` (`core/blast_advisor.py:760`) is implemented but
  has **no consumers** in `api/`, `web/src/`, `ui/`, or `core/ai_v2/`.
- `uniqid` / `id_pozo` join keys preserved since commit `80418ca`.
- Temporal filter `fecha_tronadura ≤ fecha_corte - 7 days` is active in
  `core/calculo_tronadura.py:288-301`.

### 2.4 API / web / reports

- `api/routers/process.py` (1226 LOC), `api/routers/blast.py` (395 LOC).
  **No endpoint exposes** `compute_section_health_score`,
  `attribute_failure_to_holes`, `explain_non_compliance`, or signed
  area/volume per bench.
- `web/src/components/results/Dashboard.tsx:73` `SCORE_WEIGHTS = { berm:60,
  angle:20, height:20 }` — the **only** place the visible contract lives.
- `web/src/components/results/ProfileView/domain/` — TS domain layer with
  100 % vitest coverage enforced. Has no health-score or attribution types
  today.
- `core/excel_writer.py`, `core/report_generator.py` — render
  `comparison_results` but do not call `attribute_failure_to_holes` or
  `explain_non_compliance`.

### 2.5 Configuration central (`core/config.py`)

Frozen dataclasses in `core/config.py`:
`Tolerances`, `DetectionDefaults`, `PipelineDefaults`,
`VisualizationDefaults`, `RampDetection`, `DeployDefaults`,
`ExplosiveEnergy`, `PowderFactor`, `BlastAdvisorDefaults`,
`StabilityDefaults`, `BlastDefaults`, `SectorDeviationDefaults`,
`DrillComplianceDefaults`, `DrillHardnessDefaults`, `BackbreakDefaults`.
**Missing** (would have to be added additively):
`ScoreWeights`, `StructuralDefaults`, `WaterDefaults`, `QAQCDefaults`,
`ProbabilisticDefaults`, `MonitoringDefaults`,
`SectorCalibrationDefaults`.

### 2.6 Active specs (`openspec/specs/`)

- Preserved: `reconciled-profile-serialization/spec.md`,
  `streamlit-legacy-surface-integrity/spec.md`, six blast specs (Phase 12-13).
- **Missing**: `score-contract`, `blast-bench-causal-explain`,
  `blast-bench-attribution-api`, `bench-area-volume`,
  `structural-discontinuity-model`, `mesh-qaqc`,
  `monitoring-probabilistic`, `sector-calibration`.

### 2.7 Off-limits (do not modify)

- `app.py`, `ui/` — Streamlit legacy surface used daily.
- `cli.py` — legacy CLI in production.
- `core/__init__.py` — legacy stable public API; **kept untouched**.
  No new re-exports may be added and no existing re-exports may be
  removed. New helpers (e.g. `core.score_weights`,
  `core.structural_model`, `core.bench_metrics_volume`,
  `core.mesh_qaqc`, `core.confidence_propagation`,
  `core.probabilistic_stability`, `core.calibration_by_sector`,
  `core.monitoring_trend`) are imported from their submodules directly:
  `from core.<submodule> import <name>`. Canonical example for the
  consumer pattern is `api/routers/process.py` and
  `core/report_generator.py`.

---

## 3. Affected areas (potential scope)

### Backend (`core/` and `api/` — additive)

- `core/profile_extract.py` — P0: bound the slice to `[crest_x, toe_x]` in
  `_build_face_bench`. ~10 LOC + 2-3 tests.
- `core/score_weights.py` (**NEW**) — single source of truth:
  `BERM=60`, `ANGLE=20`, `HEIGHT=20`, `PASS_THRESHOLD=70`. **Imported
  directly from the submodule** in production modules:
  `from core.score_weights import BERM, ANGLE, HEIGHT, PASS_THRESHOLD`.
  No re-export is added to `core/__init__.py` (legacy stable API stays
  untouched per AGENTS.md).
- `core/profile_compliance.py` — replace literals `60 / 10 / 30` with
  `score_weights.BERM / ANGLE / HEIGHT`. Public signature unchanged.
- `core/blast_correlation.py` — **delete** the line-980 duplicate (the
  active broken definition); keep the line-320 correct version as the
  canonical `attribute_failure_to_holes`. Update `__all__` accordingly.
  ~5 LOC + a regression test that exercises a `SectionLine`.
- `core/blast_advisor.py:760` (`explain_non_compliance`) — formalise the
  contract (Pydantic schema in `api/schemas.py`); add fields
  `blast_correlation_id`, `mesh_qaqc_passed`, `confidence_propagation`.
- `core/stability_analysis.py` — add `compute_discontinuity_kinematics(
  face_orientation, joint_sets, friction_angle_deg, toppling_dip_threshold_deg
  )` (Markland-style test). This function returns `INSUFFICIENT_DATA`
  whenever `joint_sets` is empty.
- `core/structural_model.py` (**NEW**) — `StructuralDefaults` dataclass
  (joint_sets, friction_angle_deg, toppling_dip_threshold_deg), `WaterDefaults`
  (seasonal_factor, piezometer_id, observed_head_m, r_u_computed), and a
  helper to read GSI / RQD / Jn / Ja from a user-provided catalogue. **All
  fields are required to be supplied by the caller; the dataclass carries no
  defaults for design parameters (friction, cohesion, r_u) — defaults would
  be unsafe policy.**
- `core/bench_metrics_volume.py` (**NEW**) — signed-area/volume per bench
  via **signed normal distance on 3D bank-clipped design vs as-built
  surfaces**; section-prism fallback with explicit spacing / orientation
  uncertainty when 3D inputs are unavailable.
- `core/mesh_qaqc.py` (**NEW**) — `validate_mesh_metadata(mesh_path) ->
  QAQCReport`: detect `.prj` companion file (preferred), filename EPSG
  hints, and survey timestamp; surface `crs: UNKNOWN | EPSG:...`,
  `units: UNKNOWN | m | ft`, `datum`, `epoch`, `provenance_hash`. **No
  bbox-based CRS or units inference** — those are unreliable.
- `core/confidence_propagation.py` (**NEW**) — propagate
  `confidence_score` and `n_detection_methods_agreeing` from `BenchParams`
  to per-bench score and then to section health score (variance-weighted).
- `core/probabilistic_stability.py` (**NEW**) — Monte Carlo on FS **only
  when the caller passes an explicit distribution spec** (`cohesion_*`,
  `friction_*`, `r_u_*`); if absent, return `INSUFFICIENT_DATA`.
- `core/calibration_by_sector.py` (**NEW**) — re-fit
  `fit_powder_factor_damage_model` per sector (`sector` column) with
  leave-one-out and temporal validation (train on `t-1`, validate on `t`).
- `core/monitoring_trend.py` (**NEW**) — control chart (CUSUM or EWMA) on
  `bench_score` and `health_score`; alerts when sustained degradation is
  detected.
- `api/routers/process.py` — `GET /process/{section_id}/explain`,
  `GET /process/{section_id}/health`, `GET /process/{section_id}/areas-volumes`,
  `GET /process/qaqc/{mesh_id}`.
- `api/routers/blast.py` — `POST /blast/attribute`,
  `GET /blast/calibration/{sector_id}`.
- `api/routers/meshes.py` — `GET /meshes/{mesh_id}/qaqc`.
- `api/schemas.py` — Pydantic schemas for the new payloads.

### Frontend (`web/` — additive, α-surface via `ui/` is off-limits)

- `web/src/components/results/ProfileView/domain/`:
  - `scoreWeights.ts` (TS mirror, test-friendly).
  - `causalExplain.ts` (types for `explain_non_compliance`).
  - `blastAttribution.ts` (types for `attribute_failure_to_holes`).
  - `healthScore.ts` (types for `SectionHealthScore`).
  - `areaVolume.ts` (types for signed areas / volumes).
  - `meshQAQC.ts` (types for `QAQCReport`).
- `web/src/components/results/Dashboard.tsx` — panel "Por qué NO CUMPLE"
  (consumer of `/process/{section_id}/explain`).
- `web/src/components/results/CausalExplanation.tsx` (**NEW**) — per-bench
  geometry / blast / recommendation / severity.
- `web/src/components/results/BlastAttribution.tsx` (**NEW**) — table of
  blast holes attributed to each failing bench.
- `web/src/components/results/AreasVolumes.tsx` (**NEW**) — breakdown of
  signed area / volume per bench with uncertainty bars.
- `web/src/components/results/MeshQAQCBadge.tsx` (**NEW**) — small badge
  showing `UNVERIFIED` when metadata is unknown.
- `web/src/components/results/SectorCalibration.tsx` (**NEW**) —
  per-sector calibration curves + MAPE.
- `web/src/components/results/MonitoringTrend.tsx` (**NEW**) — control
  chart view.
- `web/src/components/export/ExportPanel.tsx` — buttons "Explicación
  causal", "Áreas / volúmenes firmados", "Calibración por sector".
- `web/src/locales/es.json` + `en.json` — new i18n keys (Spanish +
  English parity required).

### Reports (`core/excel_writer.py`, `core/report_generator.py` — additive)

- New sheet "Por qué NO CUMPLE" (Excel).
- New section "Trazabilidad causal" (Word).
- New sheet "Salud de sección" with `compute_section_health_score`.
- New sheet "Áreas / volúmenes firmados" with explicit uncertainty column.
- New sheet "QA/QC de malla" with `UNKNOWN / UNVERIFIED` badge.

### Specs (`openspec/specs/` — new files)

- `score-contract/spec.md`
- `blast-bench-causal-explain/spec.md`
- `blast-bench-attribution-api/spec.md`
- `bench-area-volume/spec.md`
- `structural-discontinuity-model/spec.md`
- `mesh-qaqc/spec.md`
- `monitoring-probabilistic/spec.md`
- `sector-calibration/spec.md`

### Off-limits (do not touch)

- `app.py`, `ui/`, `cli.py`, and signatures inside `core/__init__.py`
  (no new re-exports, no removals — `core/__init__.py` is kept
  untouched; new helpers are imported from their submodules directly).

---

## 4. Architectural options (compare & decide)

| # | Approach | Pros | Cons | Effort | Decision-grade gain |
|---|----------|------|------|--------|---------------------|
| **A** | **Monolithic rewrite** — refactor `core/` so the whole stack is FS-based | Theoretical coherence | Very high risk (breaks legacy stable API); single sprint >40 h; no concurrent subagents allowed; would require modifying `core/__init__.py` signatures (forbidden) | **XL** (>60 h) | High but undeliverable |
| **B** | **Stratified decision layer (recommended)** — keep geometry as input; add a geotechnical decision layer on top (health score, causal attribution, signed area/volume, structural model, calibration) consuming existing `BenchParams` and `comparison_results` | Additive; eight sequential sprints with shared-file dependencies serialised; respects off-limits; each sprint is a self-contained commit + push; `core/__init__.py` is kept untouched (legacy stable API); new helpers are imported from their submodules directly | Eight sequential sprints | **L** |
| **C** | **P0-only** (fix angle bug + 60/20/20 contract + wire `explain_non_compliance`) | Minimum viable; lowest risk | Does not address P1/P2 (signed area/volume, structural model, calibration, monitoring) | **M** (~6-8 h) | Low-medium |
| **D** | **Rewrite the score layer with ML** (random forest on `comparison_results` + blast features) | Potentially more accurate | Requires labelled dataset (not available); not interpretable (worse for decisions); does not augment human judgement | **XL** + MLOps | Uncertain |

**Recommendation**: **Option B**, delivered as eight sequential sprints
(Sprint 0-7). Each sprint has exactly **one sequential writer**
subagent (no concurrent writers, even over disjoint file sets, because
no isolated worktrees have been approved). Parallelism is allowed only
for read-only review / research. Shared-file edits (notably
`core/profile_compliance.py` and `core/stability_analysis.py`) are split
across sprints with explicit dependencies.

---

## 5. Detailed architectural recommendation

### 5.1 Layering

```
┌─────────────────────────────────────────────────────────────┐
│ Decision Layer (NEW)                                        │
│  - score_weights.SCORES (60 / 20 / 20, threshold 70)        │
│  - structural_model.STRUCT  (joint_sets, friction)          │
│  - water.WATER              (piezometer, seasonal_factor)    │
│  - mesh_qaqc.QAQC           (CRS, datum, epoch, provenance) │
│  - probabilistic.MC_PARAMS  (caller-supplied distributions) │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ consumes
┌─────────────────────────────────────────────────────────────┐
│ Existing Geotechnical Layer (PRESERVE)                      │
│  - stability_analysis (FS proxy + health score)             │
│  - bench_hazards (wedge / toppling proxies)                 │
│  - bench_classify (berma / rampa)                           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ consumes
┌─────────────────────────────────────────────────────────────┐
│ Geometric Layer (P0 fix)                                    │
│  - profile_extract._build_face_bench (bounded slice)        │
│  - profile_compliance._build_match_row (uses SCORES)        │
│  - blast_correlation.attribute_failure_to_holes (canonical) │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ produces
┌─────────────────────────────────────────────────────────────┐
│ Reporting Layer (ADDITIVE)                                  │
│  - excel_writer (new sheets)                                │
│  - report_generator (new sections)                          │
│  - ai_v2/builder (consumes explain_non_compliance + health) │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ consumed by
┌─────────────────────────────────────────────────────────────┐
│ API / Web Layer (ADDITIVE)                                  │
│  - api/routers/process.py  (new endpoints)                  │
│  - api/routers/blast.py    (new endpoints)                  │
│  - api/routers/meshes.py   (new endpoint)                   │
│  - web/src/components/results/ProfileView/domain/*          │
│    + new top-level components                               │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Stratification rules

1. **Legacy stable API preserved.** `core/__init__.py` is **kept
   untouched** — no new re-exports may be added and no existing
   re-exports may be removed. `DeprecationWarning` on
   `build_reconciled_profile` (tuple) is kept. New helpers (e.g.
   `core.score_weights`, `core.structural_model`,
   `core.bench_metrics_volume`, `core.mesh_qaqc`,
   `core.confidence_propagation`, `core.probabilistic_stability`,
   `core.calibration_by_sector`, `core.monitoring_trend`) are imported
   from their submodules directly:
   `from core.<submodule> import <name>`.
2. **No public signatures rewritten.** `compare_design_vs_asbuilt`,
   `extract_parameters`, `build_reconciled_profile_v2`,
   `compute_section_health_score`, `attribute_failure_to_holes`,
   `explain_non_compliance` keep their existing contracts.
3. **Score weights single source of truth.** `core/score_weights.py`
   declares `BERM=60`, `ANGLE=20`, `HEIGHT=20`, `PASS_THRESHOLD=70` as
   frozen module constants. The frontend `SCORE_WEIGHTS` becomes a
   type-only mirror consumed via the API.
4. **Defaults are caller-supplied, not invented.** `StructuralDefaults`,
   `WaterDefaults`, `QAQCDefaults`, `ProbabilisticDefaults`,
   `MonitoringDefaults`, `SectorCalibrationDefaults` are added to
   `core/config.py` **without numerical defaults for design parameters**
   (friction angle, cohesion, `r_u`, FS target, Monte Carlo sample count,
   distribution shapes). They declare the *shape* of the data; the values
   must come from the caller. The few parameters that already have
   defensible geometric defaults (`STABILITY.rockfall_catch_factor = 0.6`,
   `STABILITY.overhang_warning_m = 0.5`,
   `STABILITY.overhang_critical_m = 1.5`,
   `SECTOR_DEVIATION.tolerance_m = 0.3`) remain as they are.
5. **No silent zero defaults for water / FS.** If `r_u` is missing, the
   affected FS is flagged `INSUFFICIENT_DATA` and excluded from the
   `health_score` aggregate with a warning. The verdict stays binary.

### 5.3 Per-bench angle bug (P0)

- Diagnosis: `_build_face_bench` receives `dx`, `dy`, `dists`, `angles`
  for the **entire** profile; line 697-698 set `idx_start=0; idx_end=
  len(dx)` so `local_len / local_ang` covers everything. `_weighted_face_angle`
  then weights the whole mesh sample. For an isolated tall bench with a wide
  berm or ramp adjacent, the angle averages down incorrectly.
- Fix: compute `idx_start = int(np.argmin(np.abs(dists - min(crest[0],
  toe[0]))))`, `idx_end = int(np.argmin(np.abs(dists - max(crest[0],
  toe[0])))) + 1` so `local_len` is bounded to the bench's span.
- Risk: `_face_span_mask` (line 766) already provides tolerance; reuse
  it. Add a 0.1 m edge-tolerance guard.

### 5.4 Score 60 / 20 / 20 contract (P0)

- New module `core/score_weights.py` with frozen module constants
  `BERM=60`, `ANGLE=20`, `HEIGHT=20`, `PASS_THRESHOLD=70`.
- `core/profile_compliance.py:239,243,247` import the constants instead of
  using literals.
- `core/report_generator.py` and `core/excel_writer.py` consume the same
  constants in their score rendering by importing from the submodule:
  `from core.score_weights import BERM, ANGLE, HEIGHT, PASS_THRESHOLD`.
- `web/src/components/results/Dashboard.tsx:73` keeps its `SCORE_WEIGHTS`
  for typing; a vitest unit test asserts the Python sum is 60 + 20 + 20 =
  100 when all three parameters CUMPLEN.
- The user-facing verdict remains binary `CUMPLE / NO CUMPLE` at threshold
  70. **Confidence** (low / medium / high) is propagated separately and
  never breaks the binary.

### 5.5 `attribute_failure_to_holes` (P0)

- Diagnosis (corrected): the line-980 definition is the active one because
  Python re-binds the name. It calls
  `proyectar_pozos_en_seccion(df_pozos, section)` but the real signature
  (`core/calculo_tronadura.py:246-253`) requires `(df_pozos, origin:
  np.ndarray, azimuth: float, length: float, tolerance: float = 10.0,
  fecha_corte: "str | None" = None)`. The `try / except
  Exception: return None` (line 1009-1010) swallows the resulting
  `TypeError`, raised by Python argument binding before the projector body
  executes because `azimuth` and `length` are missing. The function therefore
  returns `None` when called this way. The
  variable-name confusion (`z_lo = max + tol`, `z_hi = min - tol`,
  `z_lo > z_hi` numerically) is misleading but the mask
  `(Z_toe <= z_lo) & (Z_toe >= z_hi)` is mathematically the interval form
  `[z_hi, z_lo]` — i.e. it selects the interval `[toe - tol, crest + tol]`,
  not an empty set.
- Fix: **delete** the line-980 duplicate (the active broken binding) and
  keep the line-320 version (correct signature, correct mask, correct
  error handling) as the canonical `attribute_failure_to_holes`. Update
  `__all__` to keep one entry.
- The original failure mode at line 980 is a `TypeError` raised by Python
  argument binding before `proyectar_pozos_en_seccion` executes: the call
  `(df_pozos, section)` omits the required positional arguments `azimuth`
  and `length` from the signature in `core/calculo_tronadura.py:246-253`.
  No invented `section[0]` indexing occurs in the projector.
- New endpoint `POST /blast/attribute` (`api/routers/blast.py`) consumes
  the canonical function and returns a list per bench
  (`section_name`, `bench_num`, `n_holes`, `holes`, `pf_avg`,
  `stemming_ratio_avg`, `burden_avg`, `spacing_avg`, `subdrill_avg`,
  `kg_total`, `kg_per_meter_avg`).
- Consumers: `core/ai_v2/builder.py` (replace the placeholder "Sin
  contexto de tronadura..." that `explain_non_compliance` emits when
  `blast_context` is missing), `core/report_generator.py`,
  `core/excel_writer.py`, and the new `BlastAttribution.tsx` React
  component.
- The new function returns `None` only for the genuine empty-input cases
  (no `comp_row`, no `bench_real`, missing `SectionLine`). The
  `try/except` is narrowed to `(KeyError, AttributeError, TypeError,
  ValueError)` matching the line-320 implementation; **never** a bare
  `except Exception` for control flow.

### 5.6 `explain_non_compliance` consumer chain

- Function exists (`core/blast_advisor.py:760`); no consumer.
- New endpoint `GET /process/{section_id}/explain`
  (`api/routers/process.py`).
- Pydantic schema `ExplainResponse` in `api/schemas.py` (with `geometry_issues`,
  `blast_causes`, `recommendations`, `severity`, plus the new fields
  `blast_correlation_id`, `mesh_qaqc_passed`, `confidence_propagation`).
- New TS domain module `web/src/components/results/ProfileView/domain/causalExplain.ts`.
- New component `web/src/components/results/CausalExplanation.tsx`.
- New i18n keys (Spanish + English).

### 5.7 Screen-vs-design semantics

- Today `_build_match_row` produces independent `angle_status`,
  `height_status`, `berm_status`. Aggregation is binary at the Dashboard
  level (FUERA collapses to NO_CUMPLE), but the LLM receives the raw
  table and may misinterpret it.
- Solution: add `aggregate_status(statuses) -> 'CUMPLE' | 'NO_CUMPLE'`
  with worst-of-three semantics in `core/score_weights.py` (port of the
  existing TS `worstOfThree`).
- Document explicitly: the 70 threshold is **deterministic weighted
  aggregation**, not a probabilistic screen, and is the **sole
  determinant of the visible compliance verdict**. The visible verdict
  is and remains a **binary `CUMPLE / NO CUMPLE`** derived from the
  weighted 60 / 20 / 20 score and threshold 70 — nothing else.
- **Hard rule (verdict separation):** structural, water, kinematic
  (wedge / toppling), probabilistic (`FS_p05/p50/p95`,
  `P(FS < target)`), and confidence outputs are **separate advisory /
  geotechnical assessment dimensions**. They are surfaced alongside the
  verdict as additional rows, badges, or sections in the API response,
  the web UI, the Excel sheet, and the Word report — but they MUST
  NEVER combine with, override, or replace the binary verdict.
  `INSUFFICIENT_DATA` is a metric-availability state, **never** a third
  conformity state. `CUMPLE / NO CUMPLE` are the only two states the
  user can see for compliance.
- Confidence (`low / medium / high`) is propagated separately (see
  § 5.10) and only changes the confidence badge on the per-bench score
  and on the section health score — it never breaks the binary.

### 5.8 Signed area / volume per bench

- Method (preferred): **signed normal distance on 3D bank-clipped design
  vs as-built surfaces**. Bank-clip is the prism `[crest_x, toe_x] ×
  [min(Z_crest, Z_toe), max(Z_crest, Z_toe)]` per bench. Signed distance
  is the per-vertex perpendicular distance from the design surface to the
  as-built surface; positive = over-excavation, negative =
  sub-excavation. Aggregate per bench:
  - `backbreak_area_m2`, `backbreak_volume_m3` (positive distance behind
    the design crest).
  - `face_overbreak_area_m2` (positive distance above the design face
    angle).
  - `face_underbreak_area_m2` (negative distance below the design face
    angle).
  - `berm_loss_area_m2`, `berm_loss_volume_m3` (`berm_real < berm_design`).
  - `residual_toe_volume_m3` (positive distance beyond the design toe).
  - `floor_overdig_volume_m3`, `floor_underbreak_volume_m3`.
- **Fallback**: section-prism method when 3D meshes are unavailable.
  Inputs are `crest_x`, `toe_x`, `crest_z`, `toe_z`, `design_crest_x`,
  `design_toe_x`, `design_crest_z`, `design_toe_z`, plus `spacing_m`
  (between consecutive sections) and `orientation_deg` (azimuth of the
  section). The fallback **explicitly reports** `spacing_uncertainty_m`
  and `orientation_uncertainty_deg` as inputs to the volume integral so
  downstream users see the noise floor.
- Uncertainty: when ≥ 3 profiles per section exist, compute a **non-
  parametric bootstrap** (no fixed `n`) over the per-bench signed distances
  to obtain a CI95 % per metric. When fewer profiles exist, report
  `INSUFFICIENT_DATA` for the uncertainty column and keep the point
  estimate.
- Module: `core/bench_metrics_volume.py`.
- Tests: fixtures with 1, 3, and 10 profiles per section (boundary at
  `n=3`).

### 5.9 Mesh QA / QC

- Today `core/mesh_handler.py` only loads bbox, face count, volume. No
  CRS / datum / epoch / units / provenance capture.
- New module `core/mesh_qaqc.py`. Detection order:
  1. **CRS**: scan for a companion `.prj` file (WKT preferred). If absent,
     look for `EPSG:XXXX` in the filename. If absent, return
     `crs: UNKNOWN`. **Do not** infer CRS from bbox — bbox is unreliable
     for CRS identification.
  2. **Datum**: extract from the `.prj` WKT (e.g. `DATUM["WGS_1984"]`).
     If absent, `datum: UNKNOWN`.
  3. **Epoch**: read file mtime and any `survey_id` / `epoch` token in
     the filename. If absent, `epoch: UNKNOWN`.
  4. **Units**: read from the `.prj` WKT (`LENGTHUNIT["Meter", 1]`). If
     absent, **do not** infer from bbox — declare `units: UNKNOWN` and a
     warning. (The prior exploration suggested a bbox heuristic
     `max(|x|,|y|) < 360`; this is rejected as unreliable and can mislead
     on UTM-extent projects.)
  5. **Source precision**: tag `drone / rover / total_station` from
     filename hints if present; otherwise `UNKNOWN`.
  6. **Provenance**: `sha256` of the file + `mtime` + filename.
- Result: `QAQCReport` dataclass with `crs`, `datum`, `epoch`, `units`,
  `precision_class`, `provenance_hash`, `provenance_mtime`, and a list of
  warnings.
- **Behaviour**: when any of `crs`, `datum`, `epoch`, `units` is
  `UNKNOWN`, the report is surfaced as `UNVERIFIED` with a badge. This
  is a **warning**, not a blocker — the pipeline continues. The badge
  also appears in the Excel report and the Word PDF.

### 5.10 Confidence propagation

- `BenchParams.confidence_score ∈ [0, 1]` and
  `n_detection_methods_agreeing ∈ [0, N]` are already computed and stored
  but never propagate.
- New module `core/confidence_propagation.py`. Function
  `propagate_confidence(bench, score) -> WeightedScore`. Aggregates
  per-section with variance-weighted pooling.
- UI: when `n_detection_methods_agreeing == 1`, the per-bench score carries
  a `low` confidence badge. The binary verdict (CUMPLE / NO CUMPLE) does
  not change; only the badge changes.

### 5.11 Structural discontinuity model + kinematic

- Today: `_detect_wedge_shape_in_face` and `_detect_toppling_potential`
  are purely geometric. The audit calls this out: structural decisions
  require **face orientation plus explicit discontinuity sets**.
- New module `core/structural_model.py`. `compute_discontinuity_kinematics(
  face_orientation, joint_sets, friction_angle_deg, toppling_dip_threshold_deg
  )`:
  - `joint_sets`: list of `{dip, dip_direction, spacing, persistence,
    roughness, JRC, JCS, water_condition}`. **If empty, the function
    returns `INSUFFICIENT_DATA` immediately** and emits a warning that
    the geometric proxy (`_detect_wedge_shape_in_face` /
    `_detect_toppling_potential`) is being used instead.
  - Planar failure: Markland test (Markland 1972) — plane fails when
    `dip < friction_angle_deg` AND `dip < face_dip` AND plane daylights
    in the face.
  - Wedge: intersection line of two planes; failure when
    `dip(line) < friction_angle_deg` and the line daylights.
  - Toppling: plane steeper than `toppling_dip_threshold_deg` with dip
    direction opposite the face (`|dip_dir - face_dip_dir| > 90°`).
- Caller responsibility: `friction_angle_deg` and
  `toppling_dip_threshold_deg` must come from a user-supplied catalogue;
  the function refuses to run with no `joint_sets`.

### 5.12 Water-aware stability

- Today: `compute_planar_factor_of_safety` accepts
  `water_pressure_ratio=0.0` but is never called with `r_u > 0` from the
  UI.
- New module: schema for `WaterPressure`:
  `{seasonal_factor, piezometer_id, observed_head_m, r_u_computed}`. All
  fields are caller-supplied.
- **No silent `r_u = 0`**. If the caller does not supply piezometer or
  seasonal data, the FS is tagged `INSUFFICIENT_DATA` and excluded from
  `health_score` with a warning. The binary compliance verdict
  (`CUMPLE / NO CUMPLE`) is **unchanged** by missing water / structural
  inputs — it is computed deterministically from the 60 / 20 / 20
  weighted score and threshold 70. The FS contribution shows as `N/A`
  or `INSUFFICIENT_DATA` in the section health breakdown and the
  geotechnical advisory panel; it does **not** alter the verdict.
- UI: sidebar "Condiciones de agua" with explicit seasonal selector +
  optional piezometer ID input.

### 5.13 Catch-bench capacity

- Today: `BenchParams.catch_bench_ratio ∈ [0, 1]` exists;
  `compute_section_health_score` uses it with weight 0.20.
- New function `compute_catch_bench_capacity(berm_width, berm_height,
  block_volume_m3) -> float` returning m³ of catchable rockfall volume.
  Formula: `V_capacity = berm_width × berm_height × catch_factor` with
  `catch_factor = STABILITY.rockfall_catch_factor = 0.6` (existing
  default, already in code).

### 5.14 Calibrated blast-damage models per sector

- Today: `fit_powder_factor_damage_model` fits a single model over the
  whole mine.
- New module `core/calibration_by_sector.py`:
  - Re-fit per sector (`sector` column). Falls back to the global model
    with a badge when `n < 5` per sector (existing threshold from
    `BlastAdvisorDefaults.min_samples_for_advice`).
  - **Leave-one-out cross-validation** per sector.
  - **Temporal validation**: train on `t-1`, validate on `t`. Report
    MAPE and bias.
- No new distribution defaults are invented; the regression remains a
  regularised linear / GLM as in the current implementation.

### 5.15 Monitoring / trend / probabilistic extensions

- Today: `compute_monthly_trend` aggregates PF monthly. No control chart.
- New module `core/monitoring_trend.py`:
  - CUSUM or EWMA on `bench_score` and `health_score` per section.
  - Alerts when `health_score < threshold` AND `n_consecutive_below >=
    N` (thresholds and `N` are caller-supplied).
- New module `core/probabilistic_stability.py`:
  - Monte Carlo FS **only when the caller supplies an explicit
    distribution spec** (`cohesion_mean`, `cohesion_std`,
    `friction_mean`, `friction_std`, `r_u_min`, `r_u_max`,
    `n_iterations`, `ci_level`). Default values for these are **not**
    provided — the function returns `INSUFFICIENT_DATA` otherwise.
  - When invoked, output: `FS_mean`, `FS_p05`, `FS_p95`, CI95 band, and
    the probability that `FS < 1.0`.
- Acceptance criterion: when the caller passes an explicit `FS_target`
  (e.g. `1.3`), report `P(FS < target)`; otherwise just report the
  distribution summary. **No default `FS_target` is invented.**

---

## 6. Eight sequential work units (Sprint 0-7)

The project requires **eight** sequential sprints. The prior exploration
said "seven" — that was an off-by-one (counting `Sprint 0` as setup
rather than a sprint). Here the numbering is `Sprint 0` through
`Sprint 7`, all with their own commit + push cycle.

> **Acknowledgement of recurring shared files.** Three files recur across
> sprints: `core/profile_compliance.py` (Sprints 0 and 6),
> `core/stability_analysis.py` (Sprint 4), and `core/excel_writer.py`
> (Sprints 0, 1, 3). The dependency arrow is:
> `Sprint 0 → Sprint 1 → Sprint 2 → Sprint 3 → Sprint 4 → Sprint 5 →
> Sprint 6 → Sprint 7`. Each sprint runs **one sequential writer**
> subagent — no concurrent writer subagents are ever launched, even over
> disjoint file sets, because no isolated worktrees have been approved
> for this change. Within a sprint that touches a shared file, the
> sub-items (e.g. `S0.1 / S0.2 / S0.3` in Sprint 0,
> `S6.1 / S6.2 / S6.3` in Sprint 6) are **sequential commits by the
> same single subagent**, not parallel writers. The brief for each sprint
> explicitly lists the shared-file dependency so the writer waits for
> the previous sprint's commit before touching the shared file.

### Sprint 0 — P0 bug fixes (three sequential commits on shared files)

- **S0.1**: `core/profile_extract.py` — bound the slice to the bench's
  span (`_build_face_bench`, line 697-698). Commit
  `fix(profile-extract): acotar slice local por banco en _build_face_bench`.
  Tests: three new cases (tall isolated bench, bench adjacent to ramp,
  bench with wide berm).
- **S0.2**: `core/score_weights.py` (**NEW**) +
  `core/profile_compliance.py` (use `score_weights`) +
  `core/report_generator.py` +
  `core/excel_writer.py`. Production modules import from the new
  submodule directly (`from core.score_weights import ...`); no edits
  to `core/__init__.py`. Commit
  `feat(score): single source of truth para pesos 60/20/20`. Tests:
  backend 60 / 20 / 20 contract; integration with `excel_writer`;
  integration with `report_generator`.
- **S0.3**: `core/blast_correlation.py` — **delete** the line-980
  duplicate (the active broken binding); keep the line-320 canonical
  version. Commit
  `fix(blast): eliminar duplicación rota de attribute_failure_to_holes`.
  Tests: add a regression that calls `attribute_failure_to_holes` with a
  real `SectionLine` and a 3-hole fixture and asserts `n_holes > 0`.

### Sprint 1 — `explain_non_compliance` consumer chain
(one sequential writer subagent — all edits and sub-items are
sequential within this single work unit)

- **S1.A** (`api/schemas.py` + `api/routers/process.py`) — new endpoint
  `GET /process/{section_id}/explain`. Pydantic `ExplainResponse`.
  Sequential commit within Sprint 1 by the same subagent.
- **S1.B** (`core/excel_writer.py` + `core/report_generator.py`) — new
  Excel sheet "Por qué NO CUMPLE"; new Word section "Trazabilidad
  causal". Sequential commit within Sprint 1 by the same subagent
  (depends on S1.A, runs after).
- **S1.C** (`web/src/components/results/CausalExplanation.tsx` +
  `web/src/components/results/ProfileView/domain/causalExplain.ts` +
  i18n) — new React component + TS types + new i18n keys (es + en).
  Sequential commit within Sprint 1 by the same subagent (depends on
  S1.A + S1.B, runs last).

### Sprint 2 — `attribute_failure_to_holes` operative
(one sequential writer subagent — all edits and sub-items are
sequential within this single work unit)

- **S2.A** (`api/routers/blast.py` + `api/schemas.py`) — new endpoint
  `POST /blast/attribute`. Sequential commit within Sprint 2 by the
  same subagent.
- **S2.B** (`web/src/components/results/BlastAttribution.tsx` +
  `web/src/components/results/ProfileView/domain/blastAttribution.ts` +
  i18n + vitest 100 % coverage). Sequential commit within Sprint 2 by
  the same subagent (depends on S2.A, runs after).

### Sprint 3 — Signed area / volume per bench
(one subagent, sequential)

- `core/bench_metrics_volume.py` (**NEW**) — pure functions.
- `api/routers/process.py` — new endpoint
  `GET /process/{section_id}/areas-volumes`.
- `web/src/components/results/AreasVolumes.tsx` + domain TS.
- `core/excel_writer.py` — new sheet "Áreas / volúmenes firmados".

### Sprint 4 — Structural model + water + discontinuity kinematics
(one sequential writer subagent — all edits and sub-items are
sequential within this single work unit)

- **S4.A** (`core/structural_model.py` (**NEW**) + `core/config.py`
  adding `StructuralDefaults`, `WaterDefaults`) — Markland test, GSI /
  RQD lookup, water pressure schema. Sequential commit within Sprint 4
  by the same subagent.
- **S4.B** (`core/stability_analysis.py` — extend
  `compute_section_health_score` to consume `StructuralDefaults` and
  `WaterDefaults`; wire `compute_discontinuity_kinematics`). Sequential
  commit within Sprint 4 by the same subagent (depends on S4.A, runs
  after).

### Sprint 5 — Mesh QA / QC + provenance (one subagent)

- `core/mesh_qaqc.py` (**NEW**) + `api/routers/meshes.py` — new
  endpoint `GET /meshes/{mesh_id}/qaqc` + Pydantic schema.
- `web/src/components/results/MeshQAQCBadge.tsx` + i18n.

### Sprint 6 — Confidence propagation + probabilistic + monitoring
(three sequential commits on shared `core/profile_compliance.py` and
`core/stability_analysis.py`)

- **S6.1**: `core/confidence_propagation.py` (**NEW**) + integration
  into `core/profile_compliance.py` and `core/stability_analysis.py`.
- **S6.2**: `core/probabilistic_stability.py` (**NEW**) — Monte Carlo FS
  with caller-supplied distributions and `n_iterations`; returns
  `INSUFFICIENT_DATA` when no spec is provided.
- **S6.3**: `core/monitoring_trend.py` (**NEW**) — control chart +
  alerts + integration with `core/alert_system.py`.

### Sprint 7 — Calibration per sector + temporal validation
(one subagent)

- `core/calibration_by_sector.py` (**NEW**) — re-fit + LOO + temporal
  validation.
- `api/routers/blast.py` — new endpoint
  `GET /blast/calibration/{sector_id}`.
- `web/src/components/results/SectorCalibration.tsx` + i18n.

**Total**: 8 sequential work units (Sprint 0 through Sprint 7). Each
sprint is **one sequential writer subagent**, and may emit 1-3
sequential commits to a shared file. Each sprint fits in a 1-4 h
session. Parallelism is not permitted within a sprint — all file writes
are sequential; concurrency is allowed only for read-only review /
research.

---

## 7. Staged vs full-scope

**Recommendation**: **staged delivery across 8 sprints**. Reasons:

1. **Audit drift**: each sprint has its own tests that block silent
   regressions. Without staging, the risk of merge conflict between
   `core/profile_compliance.py`, `core/blast_correlation.py`,
   `core/stability_analysis.py`, and `core/config.py` is very high.
2. **Reviewability**: the maintainer can accept or reject sprint by
   sprint. If signed area/volume turns out not to be a priority, Sprint 3
   is skipped without affecting the rest.
3. **Per-sprint commit + push**: the cycle
   `write brief → launch subagent → verify on disk → commit → push → next`
   is the proven pattern from `multi-sprint-plan-execution/SKILL.md` for
   this repo.
4. **Early drift detection**: the score-weights bug (60 / 10 / 30 backend
   vs 60 / 20 / 20 frontend) is exactly the regression that staging
   prevents — Sprint 0.2 closes it atomically with a contract test in
   every layer.
5. **Off-limits respected**: no sprint touches `app.py`, `ui/`, `cli.py`,
   and `core/__init__.py` is kept untouched (legacy stable API; new
   helpers are imported from their submodules directly).
6. **No invented defaults**: each Sprint that introduces a defaults-
   carrying dataclass (`StructuralDefaults`, `WaterDefaults`,
   `ProbabilisticDefaults`) declares the *shape* only; values are
   caller-supplied.

**Caveat**: all detected gaps (P0, P1, P2) must be delivered, not
suppressed. Staging ≠ skipping. If the maintainer cancels a sprint, it
must be an explicit decision.

---

## 8. Explicit trade-offs

| Decision | Alternative | Why recommended |
|----------|-------------|-----------------|
| Score weights centralised in Python (`core/score_weights.py`) | Keep TS ↔ Py duplication | Single source of truth avoids drift (60 / 10 / 30 already diverged). TS consumes via the API response. |
| Delete the broken line-980 `attribute_failure_to_holes` | Keep both + feature flag | The duplicate was the **active** binding because Python re-binds names; keeping both is ambiguous and the bug is functional (always returns `None`), not cosmetic. |
| FS / kinematic / water / probabilistic are **advisory dimensions, never inputs to the verdict** | Replace 60 / 20 / 20 with FS | The visible compliance verdict is and remains the deterministic weighted aggregation with threshold 70. Structural, water, kinematic, probabilistic, and confidence outputs are surfaced as **separate advisory dimensions** and never combine with, override, or replace the binary verdict. The geotechnical layer **adds** new information; it does not modify the verdict logic. |
| No invented `r_u`, `phi`, FS target, or Monte Carlo distribution / sample count | Default values | Defaults would be unsafe policy. The system refuses to compute when inputs are missing and returns `INSUFFICIENT_DATA`. |
| QA/QC as a **warning**, not a blocker | QA/QC as blocker | The maintainer loads meshes with unknown CRS from legacy providers; blocking blocks operations. The `UNVERIFIED` badge is surfaced in API, web, Excel, and Word. |
| No CRS / units inference from bbox | Bbox heuristic | Bbox heuristics fail on UTM-extent projects and on large-coordinate local grids; they mislead. `UNKNOWN` is honest. |
| Markland test with user-supplied joint sets | Auto-detect from point cloud | No measurable discontinuity stream in the current flow; auto-detection requires LIDAR + clustering that is not implemented. |
| Temporal validation: train on `t-1`, validate on `t` | Walk-forward with fixed window | Walk-forward requires years of data; for a decision-grade-upgrade it is overkill. |
| Monte Carlo with caller-supplied `n_iterations` | Hard-coded `n = 1000` | The hard-coded value invented a sample count without traceable justification. |
| 8 sequential sprints (Sprint 0-7) | 7 sprints | The prior exploration said "7" but counted `Sprint 0` as setup; Sprint 0 carries real P0 bug fixes that warrant their own sprint. |

---

## 9. Autonomous work-unit boundary (subagent brief skeleton)

Each sprint produces a brief following `delegated-module-implementation/SKILL.md`:

```markdown
# Brief: geotechnical-decision-grade-upgrade / Sprint N

## TASK
<1 paragraph: what to deliver>

Following commit <sha-of-sprint-N-1> which did <what>, this phase is needed
because <dependency reason>.

## READ FIRST
- AGENTS.md (full repo conventions)
- openspec/changes/geotechnical-decision-grade-upgrade/exploration.md
- openspec/changes/geotechnical-decision-grade-upgrade/specs/* (if any)
- core/config.py (frozen dataclass pattern)
- <sprint-specific files>

## HARD CONSTRAINTS
- DO NOT modify app.py, ui/, cli.py, core/__init__.py.
- DO NOT modify shared files from other sprints unless this sprint's
  dependency arrow explicitly allows it.
- File allowlist: <exact list>.
- No invented design defaults (r_u, friction, FS target, MC sample count,
  distribution shape). If absent, return INSUFFICIENT_DATA.
- Conventional commit message (no AI attribution).

## STEP-BY-STEP
1. <step 1 with path>
2. <step 2 with path>
...
N. <step N with path>

## ACCEPTANCE CRITERIA
- [ ] Test command 1 passes
- [ ] Test command 2 passes
- [ ] No new lint warnings
- [ ] No new circular imports
- [ ] Legacy API still works (smoke test)
- [ ] i18n keys added to BOTH es.json + en.json (when applicable)
- [ ] No invented design defaults — missing inputs produce
      INSUFFICIENT_DATA / screening-only

## OUTPUT
- List of files created
- List of files modified
- Test count delta
- Deviations from brief (if any)
```

---

## 10. Ready for Proposal

**Yes — proceed to `sdd-propose`** with the following scope:

- **P0**: per-bench angle slice, 60 / 20 / 20 contract, blast-bench
  traceability (delete line-980 duplicate), screen-vs-design semantics.
- **P1**: signed area / volume per bench (3D bank-clipped surfaces +
  section-prism fallback + explicit uncertainty), mesh QA/QC with
  caller-supplied provenance, confidence propagation, structural model +
  water + FS (caller-supplied inputs only), catch-bench capacity.
- **P2**: per-sector calibration, monitoring/trend, probabilistic FS
  (caller-supplied distributions and `n_iterations`).

**Staging**: eight sequential sprints (Sprint 0-7) with shared-file
dependencies serialised. Each sprint is its own commit + push +
verification cycle.

**Off-limits**: `app.py`, `ui/`, `cli.py`; `core/__init__.py` is the
legacy stable API and is kept untouched (no new re-exports, no
removals). New helpers are imported from their submodules directly.

**Test strategy**: 100 % domain coverage for new TS modules under
`web/src/components/results/ProfileView/domain/{causalExplain,
blastAttribution, healthScore, areaVolume, scoreWeights, meshQAQC}.ts`
(vitest); pytest coverage ≥ baseline (~772 tests, +~30 tests per
sprint); no Python linter configured (PEP 8 by convention).

**Verification** (per `openspec/config.yaml`):

```bash
pytest tests/ -v --tb=short --ignore=tests/test_openblast.py
python test_pipeline.py
npm --prefix web run test:domain
npx --prefix web tsc --noEmit
npm --prefix web run build
```

---

## Risks

1. **Drift between backend 60 / 20 / 20 and frontend 60 / 20 / 20 during
   Sprint 0**. The brief for S0.2 includes an explicit test that
   `berm_score + angle_score + height_score = 100` when all three
   parameters CUMPLEN.
2. **Deleting the broken `attribute_failure_to_holes` may break tests
   that assume `n_holes = 0`**. Mitigated by: before deleting, `grep -rn
   "attribute_failure_to_holes" tests/` shows zero call sites in tests
   today, so the deletion is safe.
3. **Markland test is dead-on-arrival without `joint_sets`**. Mitigated
   by: `compute_discontinuity_kinematics` returns `INSUFFICIENT_DATA`
   immediately when `joint_sets` is empty and surfaces a warning;
   `_detect_wedge_shape_in_face` and `_detect_toppling_potential`
   remain as the geometry-only proxy with badge "structural proxy, not
   full Markland".
4. **Monte Carlo FS may be slow on large projects**. Mitigated by:
   caller-supplied `n_iterations`; cache results by `(section_id,
   input_hash)`; invalidate when inputs change.
5. **Per-sector calibration needs `n ≥ 5` holes per sector**. Mitigated
   by: fall back to the global model with badge "modelo global, no
   calibrado localmente" when `n < 5`
   (`BlastAdvisorDefaults.min_samples_for_advice = 5`).
6. **`core/mesh_qaqc.py` may surface `UNVERIFIED` too often**. Mitigated
   by: only the **missing-metadata** paths declare `UNKNOWN`; the
   `.prj`-present path returns the parsed CRS without inference.
7. **`UNVERIFIED` QA/QC may be ignored**. Mitigated by: badge appears in
   API response, web UI, Excel sheet, and Word section.
8. **Off-limits respected but maintainer may request touching `app.py`
   or `ui/`**. Mitigated by: brief explicitly forbids it; any exception
   requires an explicit maintainer decision.

---

## Skill Resolution

Skills loaded for this exploration:

- `sdd-explore` (mandated by task) — followed the hybrid persistence
  contract, Section D envelope, and the `topic_key = sdd/{change-name}/
  explore` convention.
- `workflow/codebase-coordination` — applied the "sibling subagent file
  write race" guard: shared files are split across sprints with explicit
  dependency arrows; within a sprint, **no concurrent writer
  subagents** are launched (only sequential commits by one subagent).
  Parallelism is restricted to read-only review / research.
- `software-development/multi-sprint-plan-execution` — applied the
  "write the next brief only after the previous commit" discipline.
- `software-development/swarm-brainstorm` — applied the
  "Disjoint file paths for parallel implementation fan-outs" rule as a
  **read-only review / research pattern only**; for this change, no
  isolated worktrees have been approved, so concurrent writer fan-out
  is not used.

Skills NOT loaded (and why):

- `sdd-spec`, `sdd-design`, `sdd-tasks` — these are the next phases;
  they will be loaded by the orchestrator or by future subagents.
- `swarm-brainstorm/references/*` — not needed; the eight-sprint
  sequence was designed directly.

No skill patches required: all loaded skills (`sdd-explore`,
`workflow/codebase-coordination`,
`software-development/multi-sprint-plan-execution`,
`software-development/swarm-brainstorm`) were accurate.

---

## Appendix A — Concrete file inventory (proposed)

**NEW files** (8 Python modules + 6 TS domain modules + 6 React
components):

```
core/score_weights.py
core/structural_model.py
core/bench_metrics_volume.py
core/mesh_qaqc.py
core/confidence_propagation.py
core/probabilistic_stability.py
core/calibration_by_sector.py
core/monitoring_trend.py

web/src/components/results/ProfileView/domain/scoreWeights.ts
web/src/components/results/ProfileView/domain/causalExplain.ts
web/src/components/results/ProfileView/domain/blastAttribution.ts
web/src/components/results/ProfileView/domain/healthScore.ts
web/src/components/results/ProfileView/domain/areaVolume.ts
web/src/components/results/ProfileView/domain/meshQAQC.ts

web/src/components/results/CausalExplanation.tsx
web/src/components/results/BlastAttribution.tsx
web/src/components/results/AreasVolumes.tsx
web/src/components/results/MeshQAQCBadge.tsx
web/src/components/results/SectorCalibration.tsx
web/src/components/results/MonitoringTrend.tsx
```

**MODIFIED files** (existing):

```
# core/__init__.py is NOT modified — kept untouched (legacy stable API)
core/config.py                                      # add ScoreWeights, StructuralDefaults, WaterDefaults, QAQCDefaults, ProbabilisticDefaults, MonitoringDefaults, SectorCalibrationDefaults
core/profile_extract.py                             # Sprint 0.1 (bound slice)
core/profile_compliance.py                          # Sprints 0.2, 6.1
core/blast_correlation.py                           # Sprint 0.3 (delete duplicate)
core/stability_analysis.py                          # Sprints 4.B, 6.1
core/blast_advisor.py                               # Sprint 1 (formalise contract)
core/ai_v2/builder.py                               # Sprint 1 (consume explain_non_compliance)
core/excel_writer.py                                # Sprints 0.2, 1.B, 3
core/report_generator.py                            # Sprints 0.2, 1.B
api/schemas.py                                      # Sprints 1, 2, 3, 5, 7
api/routers/process.py                              # Sprints 1, 3
api/routers/blast.py                                # Sprints 2, 7
api/routers/meshes.py                               # Sprint 5
web/src/components/results/Dashboard.tsx            # Sprint 1
web/src/components/results/ComplianceSummary.tsx    # Sprint 3
web/src/components/export/ExportPanel.tsx           # Sprints 1, 3
web/src/locales/es.json + en.json                   # all sprints with UI
```

**NEW specs** (8):

```
openspec/specs/score-contract/spec.md
openspec/specs/blast-bench-causal-explain/spec.md
openspec/specs/blast-bench-attribution-api/spec.md
openspec/specs/bench-area-volume/spec.md
openspec/specs/structural-discontinuity-model/spec.md
openspec/specs/mesh-qaqc/spec.md
openspec/specs/monitoring-probabilistic/spec.md
openspec/specs/sector-calibration/spec.md
```

**Total**: 20 new files + 19 modified files + 8 new specs = ~47 files
touched across 8 sequential sprints.

---

## Appendix B — Verification commands

Per sprint (each runs in < 60 s):

```bash
# Backend
pytest tests/ -v --tb=short --ignore=tests/test_openblast.py

# Frontend (domain coverage gate)
npm --prefix web run test:domain

# Frontend typecheck
npx --prefix web tsc --noEmit

# Frontend build (catches strict-config errors tsc --noEmit misses)
npm --prefix web run build

# Pipeline smoke
python test_pipeline.py

# i18n parity (manual grep)
grep -c '"' web/src/locales/es.json web/src/locales/en.json
# Should be equal (or off by ≤ 2 for ICU plural-only keys).
```

---

End of exploration.