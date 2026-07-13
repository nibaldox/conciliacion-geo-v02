# Design: drill-hardness-integration

## Technical Approach

Port the parity-critical pure functions from `dureza_relativa/classification.py` verbatim into `core/drill_hardness.py`. Wrap them with a pandas adapter (`core/drill_hardness_processor.py`) that normalizes rig CSVs, collapses reperforados, and joins hardness signals onto the blast DataFrame via `cKDTree` (2 m default — tighter than the 5 m `drill_compliance` radius, same physical hole, different measurement system). Wire an optional third uploader into `ui/modulo_tronadura.py` that enriches `session_state.blast_df_clean` only when present; the app is byte-identical when the file is absent.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Port scope | All 7 pure functions from `classification.py` (incl. 2 legacy) + TypedDicts + `DEFAULT_THRESHOLDS` | "All 6" as stated in proposal | Source has 7 functions; legacy `classify_duracion`/`hardness_index` are called by the default classification path. Proposal count is off-by-one — port all 7 for true parity. |
| Hardness columns on blast | New columns: `dureza`, `indice_dureza`, `tasa_penetracion`, `duracion_min`, `distancia_pozo_perf_m`, `tasa_pen_norm` | Side-dict metadata | Existing `find_df_column` / hover / colorscale paths work unchanged |
| Join key | `cKDTree` on drilling `(Este, Norte)`, query with blast `(X, Y)`, filter `dist ≤ radius_m` | Label match on `Pozo` | Drilling CSV rarely shares `Pozo` naming with blast CSV; spatial is robust |
| Join radius default | 2.0 m (`DRILL_HARDNESS.radius_m`, configurable) | 5 m (matches `drill_compliance`) | Same physical hole, two systems — tighter radius avoids cross-rig attribution |
| Reperforado rule | `df.loc[df.groupby("pozo")["tiempo_final"].idxmax()]` after parsing timestamps | Keep all / last row | Matches domain semantics ("last drilling event = final hole state"); proposal-mandated |
| UI integration | 3rd uploader + 3 new color options + 3 new hover lines (additive) | New Streamlit tab | Proposal scope override; additive changes only |
| Re-export from `core/__init__.py` | **No** | Yes | Keeps the legacy stable API frozen; consistent with `drill_compliance`, `blast_metrics` |

## Data Flow

```
drill_hardness_file (CSV/Excel, optional)
    └─→ load_drilling_csv(buf)
          ├─ lower/strip columns; parse tiempo inicio/final → datetime
          ├─ duracion = (final − inicio).total_seconds()/60
          ├─ resolve depth col → tasa_penetracion (NaN if missing)
          ├─ dureza (cat) + indice_dureza (0-100) via pure funcs
          ├─ if perforadora col: per-rig z-score (tasa_pen_norm)
          └─ collapse_reperforados: idxmax(tiempo_final) per Pozo
                └─→ hardness_df
                       └─→ join_hardness_to_blast(blast_df, hardness_df, radius_m)
                              ├─ cKDTree(hardness_df[[este, norte]])
                              ├─ query(blast_df[[x, y]], k=1)
                              ├─ filter dist ≤ radius_m
                              └─ merge by blast index → enriched blast_df
                                     └─→ st.session_state.blast_df_clean
```

## File Changes

| File | Action | LOC | Description |
|------|--------|-----|-------------|
| `core/drill_hardness.py` | Create | ~330 | 7 pure functions + TypedDicts + `DEFAULT_THRESHOLDS` + `STD_EPSILON` |
| `core/drill_hardness_processor.py` | Create | ~180 | `load_drilling_csv`, `_resolve_columns`, `_collapse_reperforados`, `join_hardness_to_blast` |
| `core/config.py` | Modify | +10 | `DrillHardnessDefaults` dataclass + `DRILL_HARDNESS` singleton |
| `tests/test_drill_hardness.py` | Create | ~150 | 8 cases (parity + join + radius + reperforados + edge) |
| `ui/modulo_tronadura.py` | Modify | +50 | Uploader (after L57), color options, hover enrichment (scope override) |
| `openspec/specs/blast-drill-hardness/spec.md` | Create | ~80 | New capability spec (delta + requirements) |
| `openspec/changes/ACTIVE.md` | Modify | +1 | Append row |

## Interfaces / Contracts

```python
# core/drill_hardness.py — verbatim port, docstrings trimmed
class MetricThresholds(TypedDict): soft: float; medium: float; hard: float
class Thresholds(TypedDict): duration: MetricThresholds; rate: MetricThresholds
Metric = Literal["duration", "penetration_rate", "rig_normalized_penetration"]
DEFAULT_THRESHOLDS: Thresholds = {...}                   # 16/24/40 min, 1.0/0.7/0.4 m/min
STD_EPSILON: float = 1e-9
DURATION_INDEX_UPPER_SATURATION: float = 60.0
RATE_INDEX_UPPER_SATURATION: float = 2.0

def classify_duracion(minutos: float) -> str: ...       # legacy, parity-critical
def hardness_index(T: float) -> float: ...              # legacy, parity-critical
def penetration_rate(depth_m, duration_min) -> float | None: ...
def classify_with_metric(value, thresholds, metric) -> str | None: ...
def hardness_index_with_metric(value, thresholds, metric) -> float | None: ...
def rig_mean_penetration(rates: list[float]) -> float | None: ...
def rig_normalized_penetration(rate, rig_avg, rig_std) -> float: ...

# core/drill_hardness_processor.py
def load_drilling_csv(source, thresholds=DEFAULT_THRESHOLDS) -> pd.DataFrame:
    """Parse rig CSV/Excel (path or buffer); normalize; compute duracion,
    tasa_penetracion, dureza, indice_dureza; per-rig z-score if perforadora
    col present. Collapses reperforados via idxmax(tiempo_final) per Pozo.
    Never mutates input. Missing required cols → raises ValueError."""

def join_hardness_to_blast(
    blast_df: pd.DataFrame,
    hardness_df: pd.DataFrame,
    radius_m: float = DRILL_HARDNESS.radius_m,
) -> pd.DataFrame:
    """cKDTree join on (X,Y). Adds dureza, indice_dureza, tasa_penetracion,
    duracion_min, distancia_pozo_perf_m, tasa_pen_norm to blast_df by index.
    Unmatched holes → NaN. Returns a copy."""

# core/config.py
@dataclass(frozen=True)
class DrillHardnessDefaults:
    radius_m: float = 2.0
    soft_duration_min: float = 16.0
    medium_duration_min: float = 24.0
    hard_duration_min: float = 40.0
    soft_rate_m_min: float = 1.0
    medium_rate_m_min: float = 0.7
    hard_rate_m_min: float = 0.4

DRILL_HARDNESS = DrillHardnessDefaults()
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | All 7 pure functions: parity vs `classification.py` reference outputs (golden cases, boundaries 16/24/40, 1.0/0.7/0.4) | `pytest.mark.parametrize` |
| Unit | `join_hardness_to_blast`: matched / unmatched / radius boundary (1.99 vs 2.01) / empty inputs | pytest fixtures with 4-hole blast + 5-hole drilling |
| Unit | Reperforados: 3 duplicate `Pozo` rows collapse to 1 keyed by max `tiempo_final` | pytest, fixture + assert |
| Unit | Missing `Prof. por Operador` → `tasa_penetracion` all NaN, hardness uses duration only | pytest |
| Integration | `load_drilling_csv` end-to-end on synthetic rig CSV (3 rigs, 12 wells, 2 reperforados) | `pd.testing.assert_frame_equal` |

## Migration / Rollout

No data migration. No feature flags. The drilling CSV uploader is opt-in — the app is byte-identical when absent. Revert path: delete the 2 new modules, revert `config.py` +12 LOC, revert `ui/` additive block, delete `test_drill_hardness.py`. Nothing persists in `core/__init__.py`.

## 400-Line Budget Forecast

- New code: `drill_hardness.py` (330) + `drill_hardness_processor.py` (180) + `test_drill_hardness.py` (150) = **660 LOC**
- Modifications: `config.py` (+10) + `ui/modulo_tronadura.py` (+50) = **60 LOC**
- **Total addition: ~720 LOC** — exceeds the 400-line review budget.

| Guard | Value |
|---|---|
| Decision needed before apply | **Yes** (chained vs single PR) |
| Chained PRs recommended | **Yes** |
| 400-line budget risk | **High** |

Recommended slicing: **PR #1** = `core/drill_hardness.py` + parity tests only (~480 LOC, parity-first, no UI). **PR #2** = `core/drill_hardness_processor.py` + join tests + `core/config.py` (~340 LOC). **PR #3** = `ui/modulo_tronadura.py` additive block (~50 LOC) + spec. Each PR keeps review under 500 LOC and the uploader stays disabled until PR #2 merges.

## Open Questions

- None blocking. The `Prof. por Operador` fallback (NaN `tasa_penetracion`, duration-only hardness) is documented in the proposal and tested as a case.