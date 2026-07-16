# Design: Blast Back-Break Prediction

## Technical Approach

Additive pure-Python module `core/backbreak_prediction.py` exposing `predict_backbreak` plus a frozen `BackbreakPrediction` dataclass. No sklearn: reuses `numpy` and `scipy.stats` already imported lazily by `core/blast_model`. The empirical fallback consumes `POWDER_FACTOR.pf_optimal_kgm3` (already 0.35 kg/m³) and a new `BackbreakDefaults` singleton in `core/config.py`. UI lives in `ui/tabs/blast_correlation.py` (needs the maintainer scope-override precedent from prior cycles).

The change is single-PR, ~340 LOC nominal (~120 prod + ~180 tests + ~20 config + ~20 UI). Under the 400 budget.

## Public Signature

```python
from dataclasses import dataclass
from typing import List, Literal, Optional

@dataclass(frozen=True)
class BackbreakPrediction:
    predicted_m: float
    ci_low_m: float
    ci_high_m: float
    method: Literal["multivariate", "empirical_fallback"]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    notes: List[str]


def predict_backbreak(
    burden_m: float,
    spacing_m: float,
    pf_kgm3: float,
    stemming_m: float,
    diameter_mm: float,
    model: Optional[dict] = None,
    rock_factor: float = 1.0,
    *,
    alpha: float = 0.05,
    bench_height_m: float = 15.0,
    defaults: Optional["BackbreakDefaults"] = None,
) -> BackbreakPrediction: ...
```

The spec's `design_params` dict form is exposed via the thin wrapper `_design_dict_to_kwargs(design_params)` invoked at the top of `predict_backbreak`; both share the same core, Streamlit sliders bind directly to the positional form.

## Multivariate Path

1. Read `model["coefficients"]`, `model["std_errors"]`, `model["beta0"]`, `model["dof"]`, `model["feature_means"]`, `model["confidence"]`.
2. Build the design row aligned with the model's `features_used`:

| feature name in model | input field | mapping |
|---|---|---|
| `pf_vol` | `pf_kgm3` | direct |
| `burden` | `burden_m` | direct |
| `spacing_burden_ratio` | `spacing_m / burden_m` | compute ratio |
| `stemming` | `stemming_m` | direct |

3. Compute `predicted_m = model["beta0"] + Σ coefficients[f] · x_f`.
4. CI: pooled SE from the diagonal covariance `diag(xtx_inv) · sigma2` already returned in `model["std_errors"]`. Approximate `pooled_var = Σ std_errors[f]^2 · x_f^2` (acceptable because the existing model stores diagonal-only covariance and the design sits near the training centroid). SE_pred = `sqrt(pooled_var + sigma2)`. CI half-width = `t_(1-α/2, dof) · SE_pred`.
5. Clamp `predicted_m < 0` to `0` and push `"clamped_nonnegative"` to `notes`.
6. If `model["confidence"] in {"INSUFFICIENT"}` OR `len(features_used) < 1`, fall through to the empirical path; tag the transition `"multivariate_not_available, using empirical_fallback"` in notes.

## Empirical Fallback

```python
defaults = defaults or BACKBREAK
PF_OPT    = defaults.pf_optimal_default_kgm3   # 0.35
K_BURDEN  = defaults.empirical_k                # 0.3
HP_K      = defaults.hp_constant                # 0.6
BAND      = defaults.ci_band_pct                # 0.15
B_LOW     = defaults.clamp_low_factor_b         # 0.5
B_HIGH    = defaults.clamp_high_factor_b        # 4.0

ratio     = pf_kgm3 / PF_OPT if pf_kgm3 > 0 else 1.0
predicted = max(K_BURDEN * burden_m * ratio * rock_factor, 0.0)
ci_low    = predicted * (1 - BAND)
ci_high   = predicted * (1 + BAND)

# Holmberg-Persson cross-check
kg_per_hole = max(pf_kgm3, 0.0) * max(burden_m, 0.0) * max(spacing_m, 0.0) * bench_height_m
r_damage    = HP_K * math.sqrt(kg_per_hole)
r_damage    = max(min(r_damage, B_HIGH * burden_m), B_LOW * burden_m)
notes.append(f"Holmberg-Persson cross-check (clamped to [{B_LOW}·B, {B_HIGH}·B]): {r_damage:.2f} m")
```

Confidence ladder: `HIGH` if the parent model reported `HIGH` AND input passes the `[0.5·mean, 2·mean]` extrapolation check; `MEDIUM` for typical inputs on the empirical path; `LOW` if any default substitution kicked in; `INSUFFICIENT` if the design is empty AND substitution cannot produce a finite value.

## Robustness Rules

- `None` / `NaN` / negative / non-finite numbers → substitute defaults from `BackbreakDefaults` and append `"substituted:<field>"` to `notes`. Defaults: burden=6.0 m, spacing=7.0 m, pf=0.35, stemming=burden, diameter=250 mm.
- `rock_factor` clamped to `[rock_factor_min, rock_factor_max] = [0.7, 1.3]`.
- Never raise; always return a `BackbreakPrediction`.
- Empirical monotonicity in `pf_kgm3` and `burden_m` is intrinsic (`max(K_BURDEN · x · ratio, 0)`); the multivariate path does NOT guarantee it.
- `core/__init__.py` MUST NOT be touched; import the new module as `from core.backbreak_prediction import predict_backbreak, BackbreakPrediction`.

## Config Additions (`core/config.py`)

Append a new frozen dataclass + singleton next to `DrillComplianceDefaults` (no edits to existing fields):

```python
@dataclass(frozen=True)
class BackbreakDefaults:
    empirical_k: float = 0.3
    hp_constant: float = 0.6
    pf_optimal_default_kgm3: float = 0.35
    ci_band_pct: float = 0.15
    clamp_low_factor_b: float = 0.5
    clamp_high_factor_b: float = 4.0
    bench_height_m: float = 15.0
    default_burden_m: float = 6.0
    default_spacing_m: float = 7.0
    default_stemming_m: float = 6.0
    default_diameter_mm: float = 250.0
    rock_factor_min: float = 0.7
    rock_factor_max: float = 1.3

BACKBREAK = BackbreakDefaults()
```

## UI Addition (`ui/tabs/blast_correlation.py`)

New `with st.expander("Predictor de Back-Break")` rendered below the multivariate regression block. Five number inputs bound to session state:

| Slider (es label) | min | max | default | step |
|---|---|---|---|---|
| Burden (m) | 3.0 | 12.0 | 6.0 | 0.1 |
| Spacing (m) | 4.0 | 14.0 | 7.0 | 0.1 |
| PF (kg/m³) | 0.10 | 1.20 | 0.35 | 0.05 |
| Stemming (m) | 1.0 | 12.0 | 6.0 | 0.1 |
| Diameter (mm) | 100 | 400 | 250 | 25 |
| Rock factor | 0.7 | 1.3 | 1.0 | 0.05 |

Render via `st.metric("Back-break predicho", f"{p.predicted_m:.2f} m", delta=f"IC 95% [{p.ci_low_m:.2f}, {p.ci_high_m:.2f}]")` plus `st.caption` showing `method` and `confidence`. Reuses the existing fitted model dict (kept in session state by the multivariate block) so the call threads `model=` automatically. Needs maintainer scope override (`ui/tabs/blast_correlation.py` and the existing `core.blast_model` consumer patterns).

## Tests (`tests/test_backbreak_prediction.py`)

~10 pytest cases, all pure (no Streamlit, no fixtures outside numpy seeds):

| # | Test | Asserts |
|---|---|---|
| 1 | Multivariate roundtrip on synthetic 3-feature data | `|predicted - truth| ≤ 2·SE` |
| 2 | CI coverage on 200 Monte-Carlo draws | truth ∈ CI ≥ 90% |
| 3 | Empirical fallback for typical inputs | `predicted_m ∈ [0.5, 2.5]` |
| 4 | Holmberg-Persson within ±20% (calibrated band) | `|r_damage - predicted|/predicted ≤ 0.20` |
| 5 | `design_params=None` | no raise, `confidence="INSUFFICIENT"` |
| 6 | `NaN`/negative parameters | defaults substituted, finite output |
| 7 | Damage radius clamp | `r_damage ∈ [0.5·B, 4·B]` |
| 8 | Monotonicity (empirical) on (pf, burden) grid | `predicted_m` non-decreasing |
| 9 | Multivariate negative prediction clamp | `predicted_m ≥ 0`, note present |
| 10 | Legacy `predict_damage_for_pf` signature untouched | import + smoke test |

## File Touch List

| File | Change | LOC |
|---|---|---|
| `core/backbreak_prediction.py` | new | ~140 |
| `core/config.py` | new dataclass + singleton | ~20 |
| `tests/test_backbreak_prediction.py` | new | ~180 |
| `ui/tabs/blast_correlation.py` | new expander | ~30 |
| `openspec/changes/blast-backbreak-prediction/specs/.../spec.md` | delta spec | n/a |

Total ~370 LOC nominal (under 400 budget; chained PRs not required).

## Result Contract

```python
@dataclass(frozen=True)
class BackbreakPrediction:
    predicted_m: float           # expected back-break, m, >= 0
    ci_low_m: float              # (1 - alpha) CI lower bound, m
    ci_high_m: float             # (1 - alpha) CI upper bound, m
    method: str                  # "multivariate" | "empirical_fallback"
    confidence: str              # "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT"
    notes: list[str]             # cross-check, clamps, extrapolation notes

def predict_backbreak(
    burden_m: float, spacing_m: float, pf_kgm3: float,
    stemming_m: float, diameter_mm: float,
    model: dict | None = None, rock_factor: float = 1.0,
    *, alpha: float = 0.05, bench_height_m: float = 15.0,
    defaults: BackbreakDefaults | None = None,
) -> BackbreakPrediction: ...
```

The function never raises. Malformed input downgrades `confidence`. The empirical path is monotonic in `pf_kgm3` and `burden_m`; the multivariate path follows fitted coefficients and clamps `predicted_m >= 0`. Holmberg-Persson cross-check is recorded in `notes` for sanity, never as the primary estimate.
