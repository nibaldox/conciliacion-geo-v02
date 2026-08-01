# Geotechnical Decision-Support Improvements Implementation Plan

> **For Hermes:** Execute this plan task-by-task with one sequential writer per work package, test-first development, and a fresh review before each commit. This is a standalone implementation plan; do not create or use OpenSpec/SDD artifacts.

**Goal:** Upgrade the application from geometric reconciliation and screening to traceable geotechnical decision support, without presenting the outputs as certified slope design or allowing advisory dimensions to alter geometric compliance.

**Architecture:** Keep the existing geometric pipeline stable and add typed decision-support products around it. Each product must carry provenance, quality, method, limitations, and availability; it must survive the complete extraction → persistence → API → React → report/AI round trip. Implement vertical slices sequentially because `core`, `api/routers/process.py`, schemas, report builders, and frontend contracts are shared bottlenecks.

**Tech Stack:** Python 3.10+, NumPy/SciPy, trimesh, FastAPI/Pydantic, SQLite JSON persistence, React 19, TypeScript strict mode, TanStack Query, Zustand, Plotly/three.js, pytest, Vitest, Playwright.

---

## 1. Executive technical proposal

The recommended upgrade consists of nine sequential work packages:

| Priority | Work package | Outcome |
|---|---|---|
| P0 | Reliability contracts | Correct 60/20/20 score, truly local face angle, one functional hole-attribution implementation |
| P1 | QA/QC and provenance foundation | Mesh/profile diagnostics, data lineage, confidence inputs, versioned persistence |
| P1 | Signed area and volume | Per-bench overbreak/underbreak area and volume with verified orientation and explicit fallback uncertainty |
| P1 | Blast–bench association | Reproducible spatial/temporal hole association and evidence-based explanations without causal claims |
| P2 | Structural and water advisory | Markland-style kinematics and deterministic stability only when caller-supplied inputs are complete |
| P2 | Sector and temporal calibration | Versioned sector models with walk-forward validation and explicit fallback |
| P2 | Statistical monitoring | CUSUM/EWMA over ordered, quality-controlled observations |
| P3 | Optional probabilistic analysis | Reproducible uncertainty propagation using caller-supplied distributions and settings |
| P0–P3 | Product integration | Stable DB/API round trip, React panels, exports, and unified AI context |

### Why this order

1. Score, face angle, and hole attribution are active correctness defects; downstream analysis cannot be trusted until they are fixed.
2. QA/QC and provenance must exist before confidence labels, 3D volume, structural advice, or statistical calibration are published.
3. Area/volume and blast association create the per-bench observations required by calibration and monitoring.
4. Structural and water contracts must precede probabilistic stability.
5. Probabilistic outputs are optional and last because they amplify weak assumptions if introduced too early.

---

## 2. Non-negotiable product and engineering contracts

1. **Visible compliance remains binary.** When all three required geometric checks are available, the verdict is only `CUMPLE` or `NO CUMPLE`.
2. **Scoring is fixed:** berm 60, face angle 20, bench height 20; threshold 70.
3. **Metric availability is separate.** `INSUFFICIENT_DATA` describes an unavailable metric or advisory product; it is not a third compliance status. When a required geometric metric is unavailable, return `verdict: null` rather than fabricate a score.
4. **No `FUERA DE TOLERANCIA` in user-facing outputs.** Preserve compatibility constants only where old stored payloads require them.
5. **Advisory dimensions never alter compliance.** Confidence, QA/QC, structure, water, kinematics, stability, probability, and monitoring are separate objects and UI/report sections.
6. **No invented geotechnical defaults.** Friction, cohesion, unit weight, `r_u`, target FS, distributions, Monte Carlo iterations, monitoring limits, and sample sufficiency come from validated project configuration or the caller. Missing inputs return `INSUFFICIENT_DATA`.
7. **Association is not causation.** Blast outputs may say “associated with”, “consistent with”, or “hypothesis”; never “caused by” unless an external controlled study supports that claim.
8. **No certified-design claims.** Label stability and kinematic outputs as advisory/screening with assumptions and limitations.
9. **Unknown metadata remains unknown.** Do not infer CRS, datum, units, or scale from a bounding box. Emit `UNKNOWN`/`UNVERIFIED` warnings without blocking basic profile processing.
10. **Stable public API:** do not modify `core/__init__.py`; import new helpers from their submodules.
11. **Off-limits surfaces:** do not modify `app.py`, `ui/`, or `cli.py`. Streamlit parity is explicitly deferred.
12. **Additive wire format:** new Pydantic and TypeScript fields are optional; old saved analyses remain readable but must be marked stale when they cannot support a new product.
13. **Language:** code, symbols, tests, and technical comments in English; user-facing React and report text in Spanish with matching `es.json` and `en.json` entries.

---

## 3. Verified current defects and gaps

| Area | Verified current behavior | Technical consequence |
|---|---|---|
| Local angle | `core/profile_extract.py:_build_face_bench()` sets `idx_start = 0`, `idx_end = len(dx)` before `_weighted_face_angle()` | A bench can consume simplified segments from the full profile; another bench can change its reported angle |
| Score | `core/profile_compliance.py:_build_match_row()` uses 60/10/30; section threshold is 70 | Backend and frontend/report semantics can disagree |
| Section score | Only `MATCH` rows enter the average; `MISSING`/`EXTRA` rows receive zero but are ignored | A section with missing or extra benches can appear better than it is |
| Hole attribution | `core/blast_correlation.py` defines `attribute_failure_to_holes()` twice; the active copy calls the projector with the wrong signature and swallows `TypeError` | “No holes” is indistinguishable from an internal programming error |
| Signed deviation | Two 2D implementations use contradictory overbreak/underbreak sign semantics | Area and future volume cannot be compared safely |
| 3D volume | No per-bench 3D signed volume or formal section-prism fallback exists | Reconciliation cannot quantify material volume reliably |
| Mesh QA/QC | Section cutting densifies/interpolates without reporting coverage, gaps, non-manifold geometry, or partial edge cuts | Low-quality sections can look authoritative |
| Hazards | Wedge/toppling are geometric proxies; discontinuity orientations are not preserved end-to-end | Current results are screening, not structural kinematics |
| Water/FS | Existing stability helpers contain generic defaults and untraced water inputs | Numeric FS can be over-interpreted |
| Calibration | Sector recommendations reuse a global model; temporal analysis is descriptive | Sector recommendations are not calibrated out of sample |
| Monitoring | No CUSUM/EWMA implementation exists | No controlled detection of sustained process drift |
| Probability | No geotechnical Monte Carlo contract exists | Uncertainty is not propagated to FS or volume |
| Persistence | `bench_real`/`bench_design` are stripped before `db.save_results`; serializers must list every field symmetrically | Fields can disappear silently between Python, SQLite, API, and React |
| AI | `core/unified_dataframe.py` exists, but the API AI path does not consume it | React-generated AI reports lack the full per-bench/blast context |

---

## 4. Target architecture and data flow

```text
Mesh + metadata + blast + project inputs
                 │
                 ▼
      QA/QC and provenance contracts
                 │
                 ▼
Profile cutting → extraction → local bench metrics
                 │
                 ▼
Design/as-built matching + binary compliance
                 │
        ┌────────┼─────────┐
        ▼        ▼         ▼
Signed area/   Hole-bench  Structural/water
volume         association advisory
        └────────┼─────────┘
                 ▼
       Calibration and monitoring
                 │
                 ▼
Optional probabilistic advisory
                 │
                 ▼
Versioned persistence → FastAPI → React
                 ├──────────────→ Excel/Word/PDF
                 └──────────────→ Unified DataFrame → AI
```

### Shared domain contracts

Create frozen dataclasses in focused submodules; do not add re-exports to `core/__init__.py`:

- `ComplianceScore`
- `FaceAngleEstimate`
- `EvidenceProvenance`
- `QualityAssessment`
- `MeshQualityReport`
- `ProfileQualityReport`
- `BenchDeviationMeasurement`
- `HoleBenchAssociation`
- `AssociationExplanation`
- `DiscontinuitySet`
- `HydroCondition`
- `KinematicAssessment`
- `StabilityAdvisory`
- `CalibrationDataset` / `CalibrationModelVersion`
- `TrendSignal`
- `ProbabilisticStabilityResult`

Every product should expose, where applicable:

```text
value + units
method
availability
quality indicators
confidence category
provenance
warnings
limitations
schema/algorithm version
```

---

## 5. Work package 0 — Clean implementation baseline

**Objective:** Start implementation from a reproducible baseline without carrying the existing planning artifacts into code commits.

**Files:** No production edits. The current branch contains uncommitted `openspec/**` planning files; implementation commits must exclude them.

### Steps

1. Create a clean implementation branch from current `origin/main` or an isolated worktree after preserving the current branch exactly as-is.
2. Confirm `app.py`, `ui/`, `cli.py`, and `core/__init__.py` hashes before implementation.
3. Run the backend baseline with `PYTHONPATH=.`. The ambient Hermes `PYTHONPATH` points to Python 3.11 packages while the project `.venv` is Python 3.14; overriding it avoids the observed Pillow `_imaging` mismatch.
4. Run frontend domain tests, all Vitest tests, typecheck, and production build.
5. Save golden synthetic fixtures for:
   - two benches with different angles;
   - one missing and one extra bench;
   - one section with a known inside/outside blast-hole set;
   - two parallel surfaces with analytical signed offset;
   - one incomplete edge section.
6. Record the current public API payload shapes before adding optional fields.

### Baseline commands

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v --tb=short --ignore=tests/test_openblast.py
PYTHONPATH=. .venv/bin/python test_pipeline.py
cd web && npm run test:domain
cd web && npm run test
cd web && npx tsc --noEmit
cd web && npm run build
```

**Acceptance:** Baseline results are recorded; no production changes; no planning paths staged in implementation commits.

---

## 6. Work package 1 — Correct active reliability defects

### 1A. Centralize the 60/20/20 score

**Technical proposal**

Create `core/compliance_scoring.py` as the only backend definition of weights and threshold. Implement a pure scoring function that receives three explicit metric states and returns components, total, availability, and optional binary verdict.

Recommended policy:

- All three metric checks available → compute total and binary verdict.
- Any required metric unavailable → no invented component; `score=None`, `verdict=None`, metric availability explains why.
- `MISSING` and `EXTRA` comparison rows remain score `0` and `NO CUMPLE` because they are geometric non-compliance, not missing sensor data.
- Section score includes `MATCH`, `MISSING`, and `EXTRA` rows so geometry inventory defects cannot be hidden by averaging only matches.
- Advisory objects are not accepted as function inputs.

**Files**

- Create: `core/compliance_scoring.py`
- Modify: `core/profile_compliance.py::_build_match_row`, `_build_missing_row`, `_build_extra_row`, `compare_design_vs_asbuilt`
- Modify: `api/routers/process.py` only to propagate score-contract metadata if needed
- Modify: `web/src/components/results/Dashboard.tsx` and relevant domain mapping only to consume backend values instead of redefining them
- Test: `tests/test_compliance_scoring.py`
- Extend: `tests/test_profile_compliance.py`, `tests/test_process_reconciled_alignment.py`

**TDD evidence**

1. Write an exhaustive test for the eight Boolean combinations.
2. Assert all-pass = 100.
3. Assert berm-only = 60 and `NO CUMPLE`.
4. Assert berm + either other metric = 80 and `CUMPLE`.
5. Assert advisory data cannot change score or verdict.
6. Assert a section containing a missing bank cannot ignore that row in the section score.

### 1B. Make face angle truly local

**Technical proposal**

Introduce `FaceAngleEstimate` in `core/profile_metrics.py` or locally in `profile_extract.py`. Preserve the RDP index range for each detected face, or select only segments whose two endpoints belong to the current crest–toe span. Compute:

- robust local face fit;
- crest–toe endpoint angle as fallback;
- dispersion/residual;
- source point and segment count;
- method and availability.

The estimate must use only the current bench face. It must never inherit section azimuth as a face angle.

**Files**

- Create: `core/profile_metrics.py` if separation reduces complexity
- Modify: `core/profile_extract.py::_build_face_bench`, `_weighted_face_angle`, `_bench_from_points`
- Modify: `core/param_extractor.py` only if `BenchParams` gains additive estimate fields
- Test: `tests/test_profile_extract.py`, `tests/test_param_extractor.py`

**Acceptance**

- Changing a neighboring bench does not change the target bench angle.
- Synthetic local angle is recovered within the test tolerance under noise.
- Method, dispersion, and point count survive serialization.

### 1C. Remove the broken duplicate attribution function

**Technical proposal**

Keep exactly one public implementation. Move the domain result to `core/blast_attribution.py` if doing so avoids another oversized function; leave a compatibility wrapper in `blast_correlation.py` only if existing callers require it.

Call `proyectar_pozos_en_seccion()` with explicit `origin`, `azimuth`, and `length` keyword arguments. Replace `None` ambiguity with structured states:

- `INVALID_INPUT`
- `PROJECTION_ERROR`
- `NO_PROJECTED_HOLES`
- `NO_BENCH_MATCHES`
- `SUCCESS`

Do not catch broad `Exception` around programming errors. Preserve `uniqid`/`id_pozo`, which are already retained by the current loader.

**Files**

- Create: `core/blast_attribution.py` if selected
- Modify: `core/blast_correlation.py`
- Reuse: `core/calculo_tronadura.py::proyectar_pozos_en_seccion`
- Test: `tests/test_blast_hole_attribution.py`

**Acceptance**

- AST/import test proves only one active definition.
- A forcing fixture returns exactly the expected hole ID.
- A wrong projector call fails the test; it cannot masquerade as an empty result.
- Date, distance, and elevation exclusions are tested independently.

**Rollback:** One commit per subtask (`score`, `local-angle`, `attribution-fix`) so defects can be reverted independently.

---

## 7. Work package 2 — QA/QC, provenance, confidence, and persistence

### 2A. Mesh and profile QA/QC

**Technical proposal**

Create `core/mesh_quality.py` with two reports:

- `MeshQualityReport`: finite coordinates, bounds, duplicate vertices, degenerate faces, connected components, boundary/non-manifold edges, winding/normals, watertightness, and edge-length statistics.
- `ProfileQualityReport`: requested/observed coverage, raw intersection count, maximum raw gap before interpolation, duplicate-distance aggregation, interpolated fraction, discontinuities, and edge-section completeness.

Checks with objective truth may run without thresholds. Any severity threshold for coverage, gaps, or minimum samples must be caller/project supplied. A non-watertight topographic mesh is a warning and may disable closed-volume methods; it must not block all profile extraction.

**Files**

- Create: `core/mesh_quality.py`
- Modify: `core/section_cutter.py::ProfileResult`, `cut_mesh_with_section`, `cut_both_surfaces`
- Modify: `core/mesh_handler.py` only to attach source metadata/hash
- Test: `tests/test_mesh_quality.py`, `tests/test_section_cutter.py`

### 2B. Provenance and confidence contracts

**Technical proposal**

Create `core/quality_contracts.py` with frozen `EvidenceProvenance` and `QualityAssessment` dataclasses. Record raw quality indicators first; derive `HIGH/MEDIUM/LOW/INSUFFICIENT_DATA` only from an explicit policy supplied by validated project configuration.

Required provenance:

- source file ID and hash;
- declared CRS/datum/units and verification status;
- survey/blast timestamps;
- algorithm/schema version;
- effective parameters;
- measured, estimated, interpolated, or fallback origin;
- coverage and warnings.

### 2C. Close every serialization boundary

**Technical proposal**

Add `analysis_schema_version` to persisted results and keep serializer/deserializer symmetry. Choose one representation per domain object:

- Flatten only fields needed by comparison tables.
- Preserve reusable decision-support objects as nested JSON-safe dictionaries.
- Do not persist Python dataclass instances.

Whenever `BenchParams` changes, update all three functions together:

- `api/routers/process.py::_extraction_to_dict`
- `api/routers/process.py::_bench_to_dict`
- `api/routers/process.py::_dict_to_bench`

Old payloads remain readable. Analyses lacking required provenance/local-angle/volume fields are marked `reprocess_required: true`; values are not silently replaced with zero.

**Integration files**

- Modify: `api/database.py` for additive schema/version storage
- Modify: `api/schemas.py` with optional QA/provenance fields
- Modify: `web/src/api/types.ts`
- Modify: `web/src/components/results/ProfileView/domain/types.ts` and `mapping.ts`
- Create: `web/src/components/results/QualityPanel.tsx`
- Modify: `web/src/locales/es.json`, `web/src/locales/en.json`

**Tests**

- `tests/test_quality_contracts.py`
- `tests/test_mesh_quality.py`
- `tests/api/test_quality_roundtrip.py`
- `tests/test_reconciled_profile_serialization.py`
- `web/src/components/results/ProfileView/domain/__tests__/mapping.test.ts`

**Acceptance**

- Exact filesystem hash and metadata appear in API/report payloads.
- Unknown CRS/units render `UNVERIFIED` and do not block profile processing.
- Partial sections cannot receive high confidence.
- A save/read/rebuild round trip preserves every new field.
- Old cached analyses are readable and visibly require reprocessing when necessary.

---

## 8. Work package 3 — Signed overbreak/underbreak area and volume

### 3A. Define one signed-orientation convention

Define the design-surface normal toward the excavation void as `n_void`.

```text
signed_normal_offset = dot(asbuilt_point - design_point, n_void)
positive → material protrudes into the excavation void → underbreak
negative → excavation extends into the rock mass → overbreak
```

This label is valid only when wall-facing orientation is explicitly supplied or geometrically verified. If orientation is unknown, return signed magnitude with `orientation_status=UNVERIFIED` and do not label it overbreak/underbreak.

### 3B. Primary 3D method

Create `core/reconciliation_volume.py`.

1. Clip design and as-built surfaces to the design-bank domain.
2. Sample/integrate signed normal offsets over design triangles using area-weighted quadrature.
3. Compute separately:
   - `overbreak_area_m2`
   - `underbreak_area_m2`
   - `net_area_m2`
   - `overbreak_volume_m3`
   - `underbreak_volume_m3`
   - `net_volume_m3`
4. Report mesh coverage, normal-orientation status, sampling/resolution, unmatched area, and registration metadata.
5. Do not require a boolean closed-solid operation for open topographic surfaces; only use closed-volume methods when QA/QC proves they are valid.

### 3C. Section-prism fallback

When usable bank-clipped 3D coverage is unavailable:

1. Compute signed normal area per section.
2. Match homologous banks between adjacent sections.
3. Integrate over actual station spacing with the trapezoidal/prismatic rule.
4. Integrate overbreak and underbreak separately to avoid cancellation.
5. Expose section spacing, azimuth difference, open ends, coverage, and `method="section_prism"`.

**Files**

- Create: `core/reconciliation_volume.py`
- Modify: `core/geom_utils.py::calculate_area_between_profiles`
- Modify: `core/profile_compliance.py::SectorDeviation`, `compute_sector_deviations`
- Reuse: `core/section_cutter.py::SectionLine`
- Modify persistence/API/types through the WP2 contracts
- Create: `web/src/components/results/VolumePanel.tsx`
- Modify: `ProfileChart.tsx` only for optional signed-area overlays
- Modify: `core/excel_writer.py`, `core/report_generator.py`, `core/pdf_report.py`, `core/ai_v2/builder.py`

**Tests**

- Create: `tests/test_reconciliation_volume.py`
- Extend: `tests/test_geom_utils.py`, `tests/test_profile_compliance.py`
- Analytical fixtures: uniform offset planes, linear wedge, reversed facing orientation, unequal section spacing, incomplete mesh forcing fallback, and shuffled section order.

**Acceptance**

- Analytical fixtures recover expected area/volume within stated numerical tolerance.
- Reordering sections does not change total volume.
- Overbreak and underbreak do not cancel before separate totals are reported.
- Every output includes sign convention, method, coverage, and uncertainty indicators.

**Risk:** Wall-facing orientation is the dominant semantic risk. Never infer it from arbitrary triangle winding alone.

---

## 9. Work package 4 — Robust blast–bench association and explanation

### 4A. Spatial and temporal association

Extend `core/blast_attribution.py` from the repaired P0 implementation:

1. Represent each hole as the 3D collar-to-toe trajectory.
2. Build a per-bench 3D corridor from section geometry, design-bank span, elevation/floor, and caller-supplied tolerances.
3. Calculate minimum distance and trajectory fraction within the corridor.
4. Exclude holes that are temporally ineligible relative to the topographic survey.
5. Resolve multi-bench/multi-section conflicts with exclusive assignment or normalized weights; total weight for a hole must not exceed 1.
6. Return observed and estimated fields separately.

`HoleBenchAssociation` should include:

- `hole_id`, `section_id`, `bench_id`;
- `spatial_weight`, `intersection_fraction`, `distance_m`;
- `temporal_eligible` and timestamp evidence;
- `assignment_method`, `quality`, `provenance`;
- burden, spacing, stemming, charge, timing, and other available blast metrics.

### 4B. Evidence-based explanation

Create `core/association_explanation.py` or refactor `blast_advisor.explain_non_compliance()` behind a compatibility adapter.

Output sections:

- geometric observation;
- spatial/temporal association;
- statistical evidence;
- limitations and unobserved confounders;
- alternative explanations;
- recommended field checks.

Remove hardcoded PF/stemming/subdrill recommendations unless they are validated project configuration. No-data decreases confidence; it must not escalate severity.

### 4C. API and React

- Add additive endpoints to `api/routers/blast.py`:
  - `GET /api/v1/blast/attribution/{section_id}`
  - `GET /api/v1/blast/association-explanation/{section_id}/{bench_id}`
- Add optional models to `api/schemas.py`.
- Extend `web/src/components/results/BlastCorrelation.tsx` and `BlastCorrelationTable.tsx`.
- Create `web/src/components/results/BlastAssociationPanel.tsx`.
- Use Spanish labels “Asociación / Hipótesis”, “Evidencia”, “Limitaciones”, and “Verificaciones recomendadas”.
- Keep Streamlit untouched.

**Tests**

- `tests/test_blast_hole_attribution.py`
- `tests/test_association_explanation.py`
- `tests/test_blast_advisor.py`
- API endpoint tests under `tests/api/`
- `web/src/components/results/__tests__/BlastCorrelation.test.tsx`
- New `BlastAssociationPanel.test.tsx`

**Acceptance**

- Associations are deterministic under row permutation.
- Future holes are ineligible.
- Hole weights sum to at most 1.
- No output asserts proven causality or certification.
- A missing charge/timing field is marked unavailable rather than fabricated.

---

## 10. Work package 5 — Structural, kinematic, and water advisory

### 5A. Preserve structural observations

Extend `core/geology.py::RockMassEntry` and loaders so discontinuity fields survive ingestion. Create `DiscontinuitySet` with dip, dip direction, dispersion, source, timestamp, and verification state.

### 5B. Implement kinematic checks

Create `core/kinematic_analysis.py` for:

- planar daylighting;
- wedge intersection of two planes;
- toppling feasibility.

Use the project convention: azimuth/dip direction from north, clockwise. Derive face orientation from verified section and wall-facing orientation. Rotating the face 180° must change the kinematic result appropriately.

Existing `core/bench_hazards.py` outputs remain available but are renamed/labelled `GEOMETRIC_PROXY`. They must not be presented as structural results.

### 5C. Make water and deterministic FS explicit

Create `core/hydrogeology.py` with `HydroCondition` carrying value, representation (`r_u`, pressure, or water level), units, timestamp, instrument/source, and quality.

Refactor `core/stability_analysis.py` so numeric deterministic FS is returned only when geometry, cohesion, friction, unit weight, and water inputs are complete and verified. Remove or isolate generic internal defaults from the decision-support path. Existing simplified helpers may remain as clearly labelled proxies for compatibility.

**Files**

- Modify: `core/geology.py`, `core/bench_hazards.py`, `core/stability_analysis.py`
- Create: `core/kinematic_analysis.py`, `core/hydrogeology.py`
- Add optional schemas/endpoints in a new `api/routers/geotechnical.py`, mounted under `/api/v1/geotechnical`
- Create: `web/src/components/results/GeotechnicalAdvisoryPanel.tsx`
- Modify reports/AI with a separate “Evaluación geotécnica asesora” section

**Tests**

- Extend: `tests/test_geology.py`, `tests/test_bench_hazards.py`, `tests/test_stability_analysis.py`
- Create: `tests/test_kinematic_analysis.py`, `tests/test_hydrogeology.py`
- Add API and React component tests.

**Acceptance**

- Known planar/wedge/toppling synthetic cases match analytical orientation logic.
- Missing discontinuities or water/strength inputs return `INSUFFICIENT_DATA`, not `False` or a fabricated FS.
- Increased water pressure lowers FS in a controlled fixture.
- Advisory results never change the 60/20/20 verdict.

---

## 11. Work package 6 — Sector and temporal calibration

**Objective:** Replace global-model reuse with versioned out-of-sample evidence.

**Technical proposal**

Create `core/calibration.py`:

1. Build `CalibrationDataset` with one quality-controlled observation per campaign, section, and bench.
2. Use signed area/volume, blast metrics, geology/domain, survey time, and provenance.
3. Partition by sector and ordered temporal windows.
4. Fit sector models only when caller-supplied sufficiency and variability criteria pass.
5. Use global fallback only when explicitly enabled; label it and lower confidence.
6. Validate with walk-forward or train-on-prior/validate-on-current splits; never random split temporal campaigns.
7. Persist `CalibrationModelVersion` with training period, features, coefficients, metrics, population, provenance, and algorithm version.

Add an additive `calibration_models` SQLite table in `api/database.py` using `CREATE TABLE IF NOT EXISTS`. Document that Render free-tier storage remains ephemeral; do not claim cross-deployment durability.

**Files**

- Create: `core/calibration.py`
- Modify: `core/blast_advisor.py::recommend_by_sector`
- Reuse: `core/blast_model.py` and existing multivariate model code
- Modify: `api/database.py`
- Add endpoints under `api/routers/geotechnical.py`
- Create: `web/src/components/results/CalibrationPanel.tsx`

**Tests**

- Create: `tests/test_calibration.py`
- Extend: `tests/test_blast_multivariate_model.py`, `tests/test_blast_advisor.py`
- API database round-trip tests.
- Synthetic two-sector fixture with opposite slopes and a temporal regime shift.

**Acceptance**

- Each recommendation names the exact model version used.
- No future leakage.
- Out-of-sample metrics are stored and rendered.
- Global fallback is explicit, never silent.

---

## 12. Work package 7 — CUSUM/EWMA monitoring

**Technical proposal**

Create `core/statistical_monitoring.py` over ordered quality-controlled observations:

- signed overbreak/underbreak area and volume;
- blast-model residuals;
- PF/stemming residuals where appropriate;
- deterministic stability indicators only when comparable inputs exist.

Implement:

- bilateral CUSUM with caller-supplied/calibrated `k` and `h`;
- EWMA with caller-supplied/calibrated smoothing and limits;
- explicit baseline period, reset/campaign boundaries, gaps, and unavailable states;
- output containing date, center, statistic, limits, direction, signal, and provenance.

Do not duplicate `compute_monthly_trend()`; make it consume the new observations or retain it only as a descriptive adapter.

**Files**

- Create: `core/statistical_monitoring.py`
- Modify: `core/blast_correlation.py::compute_monthly_trend`
- Add API route/models under geotechnical router
- Create: `web/src/components/results/MonitoringTrendPanel.tsx`
- Add report and AI trend sections

**Tests**

- Create: `tests/test_statistical_monitoring.py`
- Stable sequence, positive shift, negative shift, NaN/gaps, baseline reset, and manual short-sequence calculation.

**Acceptance**

- Short fixtures match hand calculations.
- Signal direction and first signal date are reproducible.
- Output is labelled process-control evidence, not a certified geotechnical alarm or causal conclusion.

---

## 13. Work package 8 — Optional probabilistic stability and volume

**Technical proposal**

Create `core/probabilistic_stability.py` using `numpy.random.Generator` with an explicit seed. Inputs are caller-supplied distributions or empirical samples, units, correlations, iteration count, convergence settings, and a caller-supplied FS threshold.

Return:

- FS quantiles;
- `P(FS < caller_threshold)`;
- sensitivity indicators;
- convergence diagnostics;
- seed, iteration count, input definitions, and provenance.

No distributions, iteration count, target FS, or correlation defaults are allowed. Missing essential inputs return `INSUFFICIENT_DATA`.

Optionally reuse the same sampling infrastructure to propagate mesh registration/section-spacing uncertainty into volume, but keep stability and volume result types separate.

**Files**

- Create: `core/probabilistic_stability.py`
- Refactor a validated deterministic kernel from `core/stability_analysis.py` without changing legacy public imports
- Optional integration: `core/reconciliation_volume.py`
- Add opt-in `POST /api/v1/geotechnical/probabilistic-stability`
- Add an opt-in subsection to `GeotechnicalAdvisoryPanel.tsx`

**Tests**

- Create: `tests/test_probabilistic_stability.py`
- Degenerate distributions equal deterministic FS.
- Same seed and inputs produce identical output.
- Quantiles are monotonic.
- Greater input uncertainty widens output intervals.
- Missing distributions produce no probability.

**Acceptance:** Full assumptions are visible; probability remains advisory; no false precision or compliance override.

---

## 14. Work package 9 — Complete product integration

Integration should be performed incrementally with each work package, then audited end-to-end here.

### Persistence and FastAPI

1. Maintain symmetry between `_extraction_to_dict`, `_bench_to_dict`, and `_dict_to_bench`.
2. Stop stripping reusable decision-support data without flattening/serializing the required fields first.
3. Keep new schema fields optional in `api/schemas.py`.
4. Put new analytical endpoints in `api/routers/geotechnical.py`; attribution remains in `api/routers/blast.py`.
5. Include `analysis_schema_version`, `algorithm_version`, and `reprocess_required` in applicable payloads.
6. Reject NaN/Inf at the API boundary or serialize them as `null` with an availability warning.

### React

Use existing product surfaces rather than a second dashboard:

- `QualityPanel.tsx` near profile/section context.
- `VolumePanel.tsx` in results/profile context.
- `BlastAssociationPanel.tsx` within `BlastCorrelation.tsx`.
- `GeotechnicalAdvisoryPanel.tsx` as a separate advisory section.
- `CalibrationPanel.tsx` and `MonitoringTrendPanel.tsx` under results.

Add new domain fields as optional properties on the base `Bench` interface, not only `SpillBench`. Map using `Number.isFinite` and null guards. Update both locale files.

### Reports

Update all controlled outputs:

- `core/excel_writer.py`
- `core/report_generator.py`
- `core/pdf_report.py`
- `core/ai_v2/builder.py`

Recommended structure:

1. Binary compliance summary.
2. QA/QC and provenance.
3. Signed area/volume.
4. Blast association/hypotheses.
5. Structural/water advisory.
6. Calibration/monitoring.
7. Probabilistic advisory only when requested.
8. Assumptions, limitations, and reprocessing warnings.

### Unified AI context

The backend, not React, should construct the unified DataFrame from stored session results, extraction cache, and stored blast uploads. This avoids sending a large user-controlled DataFrame from the browser and keeps one source of truth.

- Extend `core/ai_v2/service.py` and `core/ai_v2/builder.py` to receive/build the unified context.
- Use `core/unified_dataframe.py` directly from its submodule.
- Add new decision-support columns and a compact metadata/provenance block.
- Include a hash of the unified context and schema version in `core/ai_v2/cache.py` cache keys.
- Keep prompt truncation deterministic and report row counts/omissions.
- The AI may summarize evidence but must retain association/advisory language.

### Integration tests

- Create `tests/api/test_decision_support_roundtrip.py`.
- Extend `tests/test_unified_dataframe.py` or create it if absent.
- Extend `tests/test_ai_v2_builder.py`, report tests, export endpoint tests.
- Extend ProfileView domain mapping tests and blast component tests.
- Add Playwright flows with representative STL + blast CSV/XLSX fixtures.

---

## 15. Commit and review strategy

Use conventional commits with no AI attribution. One sequential writer owns shared files. Read-only reviews may run in parallel.

Recommended commit boundaries:

1. `fix: centralize compliance score contract`
2. `fix: compute face angle from local bench segments`
3. `fix: repair blast hole attribution`
4. `feat: add mesh quality and provenance contracts`
5. `feat: add signed bench area and volume`
6. `feat: add blast bench association evidence`
7. `feat: add geotechnical kinematic and water advisory`
8. `feat: add sector temporal calibration`
9. `feat: add statistical monitoring`
10. `feat: add optional probabilistic stability`
11. `feat: expose decision support across api web and reports`

If any boundary exceeds approximately 400 changed lines, split it by vertical behavior, not by arbitrary file type. Each commit must have a complete test and rollback boundary.

### Review gates

- After score/local-angle/attribution: correctness and regression review.
- After QA/QC/provenance: serialization and backward-compatibility review.
- After volume: numerical/geometry review with analytical fixtures.
- After blast association: data lineage and non-causality language review.
- After structural/water: independent geotechnical-method review.
- After probabilistic: reproducibility and false-precision review.
- Before PR: security, resilience, reliability, and readability review because the expected diff exceeds 400 lines.

---

## 16. Test and validation matrix

### Focused backend cycle

```bash
# Always neutralize the ambient Hermes PYTHONPATH.
PYTHONPATH=. .venv/bin/python -m pytest tests/test_compliance_scoring.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_profile_extract.py tests/test_param_extractor.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_blast_hole_attribution.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_mesh_quality.py tests/test_quality_contracts.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_reconciliation_volume.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_kinematic_analysis.py tests/test_stability_analysis.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_calibration.py tests/test_statistical_monitoring.py -v
PYTHONPATH=. .venv/bin/python -m pytest tests/test_probabilistic_stability.py -v
```

### Backend release gate

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v --tb=short --ignore=tests/test_openblast.py
PYTHONPATH=. .venv/bin/python test_pipeline.py
```

Run `tests/test_openblast.py` separately only when the optional OpenBlast package is installed.

### Frontend gate

```bash
cd web && npm run test:domain
cd web && npm run test
cd web && npx tsc --noEmit
cd web && npm run build
VITE_PWA=false npm run build
```

The production build is mandatory even when `tsc --noEmit` passes. Do not use `npm run lint` as a release gate until the currently missing/broken ESLint setup is repaired in a separate tooling task.

### API and E2E gate

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/api/ -v --tb=short
bash dev.sh
cd web && npm run test:e2e
```

Manual/Playwright scenarios:

1. Load representative design and topography meshes.
2. Confirm QA/QC warnings and metadata.
3. Process a multi-bench section and verify local angles.
4. Confirm binary score parity in API, React, Excel, Word, PDF, and AI.
5. Upload blast data and select a non-compliant bench.
6. Verify associated holes, evidence, timestamps, and limitations.
7. Verify signed area/volume and fallback labels.
8. Submit complete and incomplete structural/water inputs.
9. Confirm `INSUFFICIENT_DATA` affects advisory availability only.
10. Run monitoring/probabilistic features only with explicit inputs.
11. Reopen saved results and verify the DB round trip.

### Final invariant checks

- `git diff --name-only -- app.py ui cli.py core/__init__.py` → empty.
- No user-facing `FUERA DE TOLERANCIA`.
- No new geotechnical magic numbers.
- No causal/certification language.
- No NaN/Inf in JSON.
- Every new field survives save → load → rebuild → API → React.
- Every report and AI prompt uses the same score and decision-support source data.

---

## 17. Primary risks and mitigations

| Risk | Mitigation |
|---|---|
| Wrong overbreak sign from mesh normals | Require verified wall-facing orientation; otherwise do not label sign |
| Hidden serializer drift | Round-trip contract test for every new dataclass/schema field |
| Score drift across Python and TypeScript | Backend source of truth + API metadata + cross-layer contract test |
| False confidence from incomplete sections | Publish raw quality indicators; partial coverage cannot be high confidence |
| Causal claims from correlation | Association-specific data model, forbidden-language tests, explicit confounders |
| Structural advice without sufficient inputs | Typed availability; no numeric result when required inputs are missing |
| Model overfit by sector | Caller sufficiency criteria, walk-forward validation, explicit global fallback |
| Statistical false alarms | Caller/calibrated limits, baseline/version metadata, residual monitoring |
| Monte Carlo false precision | Caller-supplied distributions/correlations, seed, convergence and sensitivity report |
| Old cached analyses silently using defaults | Schema version + `reprocess_required`; no silent zero substitution |
| Payload growth | Compact nested products, optional fields, lazy endpoint loading |
| Shared-file write races | One sequential writer; parallel read-only review only |

---

## 18. Definition of complete

The upgrade is complete only when:

- [ ] Score is 60/20/20 everywhere and section aggregation handles missing/extra benches explicitly.
- [ ] Each bench angle is independent of unrelated profile segments.
- [ ] One functional attribution implementation returns structured errors and real hole IDs.
- [ ] Mesh/profile QA/QC and provenance are visible without blocking ordinary processing.
- [ ] Signed area and volume pass analytical tests and expose orientation/method/coverage.
- [ ] Blast outputs present evidence and hypotheses, never proven causality.
- [ ] Kinematic, water, and stability outputs require complete caller-supplied inputs.
- [ ] Sector/temporal models are versioned and validated out of sample.
- [ ] CUSUM/EWMA outputs are reproducible and correctly labelled.
- [ ] Probabilistic analysis is opt-in, reproducible, and transparent about assumptions.
- [ ] SQLite/API/React/report/AI round trips preserve every field.
- [ ] Excel, Word, PDF, React, and AI agree on score and terminology.
- [ ] Streamlit and stable legacy interfaces remain untouched.
- [ ] Backend, frontend, builds, API, E2E, and representative operational flows pass.

## 19. Explicitly excluded from this plan

- Certified slope design or formal sign-off.
- Automatic interpretation of geological domains without supplied data.
- Inference of CRS/datum/units from bounding-box dimensions.
- Hidden/default geotechnical design parameters.
- Replacement of the binary geometric verdict by FS or risk probability.
- Streamlit changes (`app.py`, `ui/`).
- Changes to `cli.py` or `core/__init__.py`.
- PostgreSQL migration or durable cloud model registry until infrastructure is approved.
- OpenSpec/SDD artifacts or workflows.
