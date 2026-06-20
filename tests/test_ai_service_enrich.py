import numpy as np
import pandas as pd


def compute_monthly_trend(blast_df: pd.DataFrame, damage_col: str = 'avg_over_break') -> pd.DataFrame:
    """Aggregate PF and damage by month from a blast DataFrame.

    Requires ``fecha_tronadura`` and ``pf_vol_kgm3``. Returns a frame with
    columns ``mes`` (YYYY-MM), ``pf_promedio``, ``damage_promedio``,
    ``n_pozos``, ``trend_slope`` and ``trend_intercept``. The linear trend is
    fit with ``np.polyfit`` only when at least three months are present.
    Returns an empty frame when the required columns or valid dates are
    missing.
    """
    if (blast_df is None or blast_df.empty
            or 'fecha_tronadura' not in blast_df.columns
            or 'pf_vol_kgm3' not in blast_df.columns):
        return pd.DataFrame()

    df = blast_df.copy()
    df['_mes'] = pd.to_datetime(df['fecha_tronadura'], errors='coerce').dt.to_period('M')
    df = df[df['_mes'].notna()]
    if df.empty:
        return pd.DataFrame()

    df['pf_vol_kgm3'] = pd.to_numeric(df['pf_vol_kgm3'], errors='coerce')
    grouped = df.groupby('_mes')
    counts = grouped.size()
    agg = {
        'pf_promedio': grouped['pf_vol_kgm3'].mean(),
        'damage_promedio': (grouped[damage_col].mean()
                            if damage_col in df.columns
                            else pd.Series(np.nan, index=counts.index)),
        'n_pozos': counts,
    }
    out = pd.DataFrame(agg).reset_index()

    pf_vals = out['pf_promedio'].to_numpy(dtype=float)
    if len(out) >= 3 and not np.isnan(pf_vals).any():
        slope, intercept = np.polyfit(np.arange(len(out), dtype=float), pf_vals, 1)
        out['trend_slope'] = slope
        out['trend_intercept'] = intercept
    else:
        out['trend_slope'] = np.nan
        out['trend_intercept'] = np.nan

    out['mes'] = out['_mes'].astype(str)
    out = out[['mes', 'pf_promedio', 'damage_promedio', 'n_pozos',
               'trend_slope', 'trend_intercept']]
    return out.sort_values('mes').reset_index(drop=True)


def detect_pf_outliers_iqr(blast_df: pd.DataFrame, k: float = 1.5) -> pd.DataFrame:
    """Return rows whose ``pf_vol_kgm3`` is outside Q1 - k*IQR or Q3 + k*IQR.

    Returns an empty frame when the column is missing, fewer than four valid
    values exist, or the interquartile range is zero (no spread to flag).
    """
    if blast_df is None or blast_df.empty or 'pf_vol_kgm3' not in blast_df.columns:
        return pd.DataFrame()

    pf = pd.to_numeric(blast_df['pf_vol_kgm3'], errors='coerce')
    valid = pf.dropna()
    if len(valid) < 4:
        return pd.DataFrame()

    q1, q3 = np.quantile(valid.to_numpy(dtype=float), [0.25, 0.75])
    iqr = q3 - q1
    if iqr == 0:
        return pd.DataFrame()

    lower = q1 - k * iqr
    upper = q3 + k * iqr
    mask = pf.notna() & ((pf < lower) | (pf > upper))
    return blast_df.loc[mask].copy()


def split_campaign(blast_df: pd.DataFrame, campaign_start_date: str | None) -> dict:
    """Split blast_df into 'before' and 'after' cohorts by date.

    Returns ``{'before': df, 'after': df, 'has_campaign': bool}``. When
    ``campaign_start_date`` is None, ``fecha_tronadura`` is missing or the
    cutoff cannot be parsed, everything is returned under 'before' with
    ``has_campaign`` set to False.
    """
    empty_after = pd.DataFrame()
    if campaign_start_date is None:
        before = blast_df if blast_df is not None else pd.DataFrame()
        return {'before': before, 'after': empty_after, 'has_campaign': False}

    if (blast_df is None or blast_df.empty
            or 'fecha_tronadura' not in blast_df.columns):
        before = blast_df if blast_df is not None else pd.DataFrame()
        return {'before': before, 'after': empty_after, 'has_campaign': False}

    cutoff = pd.to_datetime(campaign_start_date, errors='coerce')
    if pd.isna(cutoff):
        return {'before': blast_df, 'after': empty_after, 'has_campaign': False}

    dates = pd.to_datetime(blast_df['fecha_tronadura'], errors='coerce')
    before_mask = dates <= cutoff
    after_mask = dates > cutoff
    return {
        'before': blast_df.loc[before_mask.fillna(False)].copy(),
        'after': blast_df.loc[after_mask.fillna(False)].copy(),
        'has_campaign': True,
    }


class TestMonthlyTrend:
    def test_groups_by_month(self):
        df = pd.DataFrame({
            'fecha_tronadura': pd.to_datetime(['2024-01-05', '2024-01-20', '2024-02-10']),
            'pf_vol_kgm3': [0.5, 0.7, 0.9],
            'label_pozo': ['P1', 'P2', 'P3'],
        })
        out = compute_monthly_trend(df)
        assert len(out) == 2
        assert list(out['mes']) == ['2024-01', '2024-02']
        jan = out[out['mes'] == '2024-01'].iloc[0]
        assert jan['n_pozos'] == 2
        assert np.isclose(jan['pf_promedio'], 0.6)

    def test_empty_when_no_dates(self):
        df = pd.DataFrame({
            'pf_vol_kgm3': [0.5, 0.6],
            'label_pozo': ['P1', 'P2'],
        })
        assert compute_monthly_trend(df).empty

    def test_trend_slope_when_n_geq_3(self):
        df = pd.DataFrame({
            'fecha_tronadura': pd.to_datetime(['2024-01-05', '2024-02-05', '2024-03-05']),
            'pf_vol_kgm3': [0.4, 0.5, 0.6],
        })
        out = compute_monthly_trend(df)
        assert len(out) == 3
        assert pd.notna(out['trend_slope'].iloc[0])
        assert out['trend_slope'].iloc[0] > 0


class TestPFOutliers:
    def test_iqr_outliers_detected(self):
        pf = [0.40, 0.42, 0.45, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60, 2.5]
        df = pd.DataFrame({
            'pf_vol_kgm3': pf,
            'label_pozo': [f'P{i}' for i in range(len(pf))],
        })
        out = detect_pf_outliers_iqr(df)
        assert len(out) == 1
        assert np.isclose(out['pf_vol_kgm3'].iloc[0], 2.5)

    def test_no_outliers_when_uniform(self):
        df = pd.DataFrame({
            'pf_vol_kgm3': [0.5] * 8,
            'label_pozo': [f'P{i}' for i in range(8)],
        })
        assert detect_pf_outliers_iqr(df).empty


class TestCampaignSplit:
    def test_splits_by_date(self):
        df = pd.DataFrame({
            'fecha_tronadura': pd.to_datetime(['2024-01-10', '2024-02-15', '2024-03-20']),
            'pf_vol_kgm3': [0.5, 0.6, 0.7],
        })
        res = split_campaign(df, '2024-02-01')
        assert res['has_campaign'] is True
        assert len(res['before']) == 1
        assert len(res['after']) == 2

    def test_no_campaign_returns_before_all(self):
        df = pd.DataFrame({
            'fecha_tronadura': pd.to_datetime(['2024-01-10', '2024-02-15', '2024-03-20']),
            'pf_vol_kgm3': [0.5, 0.6, 0.7],
        })
        res = split_campaign(df, None)
        assert res['has_campaign'] is False
        assert len(res['before']) == 3
        assert res['after'].empty


class TestEnrichGracefulDegradation:
    def test_handles_missing_pf_column(self):
        df = pd.DataFrame({
            'fecha_tronadura': pd.to_datetime(['2024-01-10', '2024-02-15']),
            'label_pozo': ['P1', 'P2'],
        })
        out = compute_monthly_trend(df)
        assert out.empty
