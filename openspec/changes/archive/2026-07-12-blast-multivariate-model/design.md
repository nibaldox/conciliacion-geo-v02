# Design: Blast Multivariate Damage Model

## Technical Approach

Additive multivariate OLS alongside the existing mono
`fit_powder_factor_damage_model`. Same return-dict shape so UI and advisor
consume mono or multi interchangeably. Pure numpy + `scipy.stats`, no
sklearn. Advisor gains per-feature inversion holding other predictors at
section means, isolating burden from PF.

## Architecture Decisions

### Decision: OLS via `np.linalg.lstsq` + manual covariance

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `stats.linregress` (current) | mono only | keep for mono path |
| `np.linalg.lstsq` + manual cov | vectorized, no sklearn, full SE/t/p/F | **chosen** |
| sklearn `LinearRegression` | no SE/t/p without extra code | rejected |

`X = [1, x₁, …, xₚ]`. `beta, *_ = np.linalg.lstsq(X, y, rcond=None)`. `XtX_inv = inv(XᵀX)`; `pinv` fallback → `rank_deficient=True`. `sigma2 = Σ(y − Xβ)² / max(n−p, 1)`. `SE = sqrt(sigma2 · diag(XtX_inv))`. `t = β/SE`. `p = 2·stats.t.sf(|t|, df=n−p)`. `F = (SSR/(p−1))/(SSE/(n−p))`, `f_pvalue = stats.f.sf(F, p−1, n−p)`. `R² = 1 − SSE/SST`, `R²_adj = 1 − (1−R²)(n−1)/(n−p)`. `condition_number = np.linalg.cond(X)`. Lazy `from scipy import stats`.

### Decision: Confidence downgrades on collinearity

`cond(X) ≥ 30` → cap CAUTION + `collinearity_warning: "Posible colinealidad entre predictores (típicamente PF↔burden)"`. Rationale: PF = kilos/(B·S·h); when B/S vary little, PF and burden are linearly dependent (Belsley gate). Otherwise reuse existing n + p-value thresholds with F-test gate on `f_pvalue`.

### Decision: Predictor auto-resolution

| Predictor | Candidates (first match wins) |
|-----------|-------------------------------|
| `pf_vol` | `pf_vol_kgm3`, `pf_vol_avg_kgm3`, `PF_vol` |
| `burden` | `Burden`, `Burden_Real`, `Burden_diseno`, `B` (`_BURDEN_CANDIDATES`) |
| `spacing_burden_ratio` | `spacing_burden_ratio` (from `enrich_blast_dataframe`); else `Esp/Burden` if both present |
| `stemming` | `Taco_m`, `Taco`, `Stemming` (`_TACO_CANDIDATES`) |

Min 2 predictors required → else INSUFFICIENT. Means stored in `feature_means` so the advisor holds them fixed.

### Decision: Return shape mirrors mono dict

Additive keys: `coefficients`, `std_errors`, `t_stats`, `p_values` (`dict[str, float]` keyed by predictor), `r_squared_adj`, `f_statistic`, `f_pvalue`, `dof`, `condition_number`, `features_used`, `feature_means`, `collinearity_warning`. Legacy `beta0`, `r_squared`, `p_value` (now F-test), `n`, `confidence`, `is_significant` preserved.

### Decision: Advisor burden inversion

`recommend_burden_adjustment(model, current_burden, target_overbreak_m=None)` solves `target = β0 + Σᵢ βᵢ·x̄ᵢ + β_burden·target_burden` for `target_burden`; others fixed at `model["feature_means"]`. Reuses `_classify_feasibility` with burden bounds `[0.5·B, 2·B]`. New `_build_burden_message` keeps Spanish-neutral tone.

### Decision: Dispatcher `recommend_multivariate`

Picks burden-aware path when `n ≥ 12` AND `len(features_used) ≥ 3` AND `confidence != "INSUFFICIENT"`. Otherwise returns INSUFFICIENT.

## Data Flow

```
ui/tabs/blast_correlation.py
   df_filtered_sections
        │
        ▼
fit_multivariate_damage_model(df, damage_col)
   X via first_present_column; OLS via np.linalg.lstsq; SE/t/p/F/R²
        │
        ▼
model dict (mono-shape + multi extras)
   ├─► ui expander: coefficients table + collinearity warning
   └─► recommend_multivariate(model, current_burden)
            └─► recommend_burden_adjustment
                  solve linear eqn → _classify_feasibility([0.5B, 2B])
```

## File Changes

| File | Action | LOC | Description |
|------|--------|-----|-------------|
| `core/blast_model.py` | Modify | +95 | `fit_multivariate_damage_model`, `_classify_multivariate_confidence`, `_MULTIVARIATE_INSUFFICIENT_RESULT` |
| `core/blast_advisor.py` | Modify | +75 | `_MULTIVARIATE_INSUFFICIENT`, `recommend_burden_adjustment`, `recommend_multivariate`, `_build_burden_message`; no edits to existing helpers |
| `tests/test_blast_multivariate_model.py` | Create | +210 | 12 tests (parametrized) |
| `ui/tabs/blast_correlation.py` | Modify | +60 | New expander "Modelo multivariado (PF + burden + stemming)" — maintainer override |

**Total ≈ 440 LOC**, slightly over the 400-line budget; absorb by trimming test boilerplate toward 380. Zero edits to `core/__init__.py`, `fit_powder_factor_damage_model`, or `recommend_pf_adjustment`.

## Interfaces / Contracts

```python
def fit_multivariate_damage_model(
    df: pd.DataFrame, damage_col: str = "avg_over_break", min_samples: int = 12,
) -> Dict[str, Any]:
    """Multivariate OLS: damage ~ intercept + {pf_vol, burden, S/B, stemming}.
    Empty/insufficient returns INSUFFICIENT skeleton (confidence='INSUFFICIENT')."""

def recommend_burden_adjustment(
    model: Dict[str, Any], current_burden: float, target_overbreak_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Invert for burden, others held at model['feature_means']. Bounds [0.5B, 2B]."""

def recommend_multivariate(
    model: Dict[str, Any], current_burden: float, target_overbreak_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Dispatch to recommend_burden_adjustment when n≥12 AND ≥3 features AND !=INSUFFICIENT."""
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | truth recovery | `y = 0.3 + 1.2·PF − 0.5·B + 0.1·S/B − 0.2·T + ε` (n=40); assert `|β̂ − β| < 2·SE` per coef |
| Unit | R² lift vs mono | same data → `r_squared` ≥ `linregress` R² + 0.05 |
| Unit | small-n guard | n=8 → INSUFFICIENT; n=12 strong signal → MEDIUM/HIGH |
| Unit | collinearity flag | PF = 1/B exactly → cond ≥ 30 → CAUTION + warning |
| Unit | missing cols / rank def | df without Burden/S/B → 2 feats; constant col → INSUFFICIENT |
| Unit | advisor inversion | given true β, recovers input burden within 5%; boundary [0.5B, 2B] → CAUTION |
| Unit | dispatcher | n=15+3 feats → multi path; n=5 → INSUFFICIENT |
| Regression | `recommend_pf_adjustment` | existing fixtures produce identical bytes |

## Migration / Rollout

No migration. All additive; `core/__init__.py` re-exports stay unchanged. Rollback = `git revert` of the four files.

## Open Questions

None. Proposal already settled the collinearity threshold, predictor list, and per-feature inversion math.