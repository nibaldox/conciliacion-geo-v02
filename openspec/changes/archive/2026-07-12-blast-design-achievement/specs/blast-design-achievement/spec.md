# Capability: blast-design-achievement

> **Status**: draft | **Change**: `blast-design-achievement`
> **Scope override**: temporarily lifts `ui/` off-limits for the blast tab only (precedent: `2026-07-11-streamlit-audit-remediation`).

## Purpose

Close two closed-loop blast→design KPIs: (a) **stemming ↔ crest damage** per bench — symmetric to the pasadura↔toe correlation; (b) **per-malla design achievement score** (0–100%) with crest/toe/berm breakdown. Both consume existing fields; nothing existing changes.

## Requirements

### Requirement: stemming-crest correlation mirrors pasadura-toe

The system SHALL expose `core.blast_model.compute_stemming_crest_correlation(blast_df, comparisons, bench_height=15.0, tolerance=5.0)` whose signature and return shape are 1:1 with `compute_pasadura_toe_correlation` (`core/blast_model.py:172`). It SHALL group `blast_df` by floor `(Z_collar - bench_height).round(0)` → mean `Taco_m`, and mean `delta_crest` per `level` from `comparisons`; pair and compute Pearson r + p-value via a lazy `from scipy import stats` import. Thresholds: `r < -0.3` → gases venting up (catch bench blown off); `r > 0.3` → energía baja (stemming corta, sobre-excavación de cresta); else weak/null. The symbol SHALL NOT be re-exported from `core/__init__.py`.

#### Scenario: happy path — negative correlation

- GIVEN a `blast_df` with 4 floors and `Taco_m` decreasing floor-by-floor, paired with `comparisons` whose `delta_crest` rises on the same 4 `level`s
- WHEN `compute_stemming_crest_correlation(blast_df, comparisons)` is called
- THEN `r < -0.3`, `p_value` finite, `n_benches == 4`, and `interpretation` is the "gases venting up" Spanish string

#### Scenario: empty or insufficient data

- GIVEN `blast_df` empty OR `comparisons` empty OR `n_benches < 2` OR `Taco_m` / `delta_crest` missing
- WHEN the function is called
- THEN it returns the empty-shape dict with `r=0.0`, `p_value=nan`, `n_benches=0`, and a "Sin datos suficientes" interpretation — without raising

### Requirement: per-malla design achievement score (0–100%)

The system SHALL expose `core.blast_achievement.compute_design_achievement_score(comparisons, malla_column=None)`. Per-row partial credit: `CUMPLE → 1.0`, `FUERA DE TOLERANCIA → 0.5`, anything else (`NO CUMPLE`, `NO CONSTRUIDO`, missing) → `0.0`. The aggregate SHALL be a weighted mean: `0.4` crest (`delta_crest` within tolerance), `0.3` toe (`delta_toe` within tolerance), `0.3` berm (`berm_status == STATUS_CUMPLE`). Result SHALL be an integer 0–100 percentage plus a `breakdown` dict with `crest`, `toe`, `berm` (each 0–100), `n_passing_crest/toe/berm`, `n_total`. When `malla_column` is supplied and present, return `per_malla: dict[str, int]`; otherwise `per_malla=None`.

#### Scenario: all-CUMPLE section

- GIVEN 10 comparison rows where `delta_crest`, `delta_toe`, and `berm_status` all comply
- WHEN `compute_design_achievement_score(comparisons)` is called
- THEN `global == 100`, `breakdown["crest"] == 100`, `breakdown["toe"] == 100`, `breakdown["berm"] == 100`, `n_passing_crest == 10`

#### Scenario: mixed three-tier with per-malla breakdown

- GIVEN 12 rows across 2 mallas (`A`, `B`); `A` all CUMPLE, `B` has 4 CUMPLE + 2 FUERA on crest
- WHEN the function is called with `malla_column="malla"`
- THEN `per_malla["A"] == 100`, `per_malla["B"]` reflects its crest pass rate in the 0.4 component, and `global` is the whole-section weighted mean

#### Scenario: malla column missing

- GIVEN `malla_column=None` or the column absent in `comparisons`
- WHEN the function is called
- THEN `per_malla is None` and `global` reflects all rows; no exception

### Requirement: graceful empty-data handling

Both new functions SHALL return their empty-shape outputs (correlation dict with `n_benches=0`; score with `global=0`, `n_total=0`) — never raise — when inputs are `None`, empty, missing required columns, or only NaN.

#### Scenario: zero rows in comparisons

- GIVEN `comparisons == []`
- WHEN either function is called
- THEN no exception is raised and the result reflects zero data

### Requirement: legacy blast regressions unchanged

The system SHALL keep `compute_pf_damage_regression` and `compute_pasadura_toe_correlation` (and their Streamlit renderers) behavior-preserving. New code is purely additive: new functions in `core/blast_model.py`, new module `core/blast_achievement.py`, and `_render_stemming_crest_block`.

#### Scenario: existing tests still pass

- GIVEN the existing `tests/test_blast_model.py` corpus
- WHEN `pytest tests/test_blast_model.py -v` runs after the change
- THEN every pre-existing test passes (no regression in PF or pasadura paths)

### Requirement: legacy public API surface preserved

Per `openspec/config.yaml` (`core/__init__.py` off-limits), the new symbols SHALL be imported from their submodule directly (`from core.blast_model import compute_stemming_crest_correlation`; `from core.blast_achievement import compute_design_achievement_score`). `core/__init__.py` SHALL NOT be modified.

## Out of Scope

Gaps 0/1/3/4, stability analysis, M3.