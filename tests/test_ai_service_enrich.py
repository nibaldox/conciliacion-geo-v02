import numpy as np
import pandas as pd

from core.blast_correlation import (
    compute_monthly_trend,
    detect_pf_outliers_iqr,
    split_campaign,
)


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