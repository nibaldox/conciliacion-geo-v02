"""Tests for core.alert_system — Phase 11 alert evaluation."""
import pytest

from core.alert_system import (
    Alert,
    SectionAlertReport,
    aggregate_section_alerts,
    evaluate_bench_health,
)
from core.param_extractor import BenchParams
from core.config import STABILITY


def _bench(
    bench_number=1,
    overhang_m=0.0,
    catch_bench_adequate=True,
    catch_bench_ratio=1.0,
    face_angle=70.0,
    bench_height=15.0,
    wedge_risk=False,
    toppling_risk=False,
    face_angle_inconsistent=False,
):
    return BenchParams(
        bench_number=bench_number,
        crest_elevation=100.0,
        crest_distance=20.0,
        toe_elevation=85.0,
        toe_distance=10.0,
        bench_height=bench_height,
        face_angle=face_angle,
        berm_width=9.0,
        overhang_m=overhang_m,
        catch_bench_adequate=catch_bench_adequate,
        catch_bench_ratio=catch_bench_ratio,
        wedge_risk=wedge_risk,
        toppling_risk=toppling_risk,
        face_angle_inconsistent=face_angle_inconsistent,
    )


class TestBenchAlerts:
    """Phase 11 — C.5 single-bench alert thresholds."""

    def test_overhang_critical_red(self):
        """overhang >= STABILITY.overhang_critical_m → RED OVERHANG_CRITICAL."""
        b = _bench(overhang_m=STABILITY.overhang_critical_m + 0.1)
        alerts = evaluate_bench_health(b)
        codes = [a.code for a in alerts]
        assert 'OVERHANG_CRITICAL' in codes
        red = [a for a in alerts if a.code == 'OVERHANG_CRITICAL'][0]
        assert red.level == 'RED'
        assert red.bench_number == b.bench_number
        assert red.metric_value == pytest.approx(STABILITY.overhang_critical_m + 0.1)

    def test_overhang_warning_yellow(self):
        """overhang in warning band → YELLOW OVERHANG_WARNING (not RED)."""
        b = _bench(overhang_m=STABILITY.overhang_warning_m + 0.1)
        alerts = evaluate_bench_health(b)
        codes = [a.code for a in alerts]
        assert 'OVERHANG_WARNING' in codes
        assert 'OVERHANG_CRITICAL' not in codes

    def test_catch_bench_inadequate_orange(self):
        """!catch_bench_adequate → ORANGE CATCH_BENCH_INADEQUATE."""
        b = _bench(catch_bench_adequate=False, catch_bench_ratio=0.4)
        alerts = evaluate_bench_health(b)
        orange = [a for a in alerts if a.code == 'CATCH_BENCH_INADEQUATE']
        assert len(orange) == 1
        assert orange[0].level == 'ORANGE'
        assert orange[0].metric_value == pytest.approx(0.4)

    def test_toppling_risk_orange(self):
        """toppling_risk=True → ORANGE TOPPLING_RISK."""
        b = _bench(toppling_risk=True, face_angle=80.0, bench_height=20.0)
        alerts = evaluate_bench_health(b)
        top = [a for a in alerts if a.code == 'TOPPLING_RISK']
        assert len(top) == 1
        assert top[0].level == 'ORANGE'

    def test_wedge_risk_yellow(self):
        """wedge_risk=True → YELLOW WEDGE_RISK."""
        b = _bench(wedge_risk=True)
        alerts = evaluate_bench_health(b)
        w = [a for a in alerts if a.code == 'WEDGE_RISK']
        assert len(w) == 1
        assert w[0].level == 'YELLOW'

    def test_angle_inconsistent_yellow(self):
        """face_angle_inconsistent=True → YELLOW ANGLE_INCONSISTENT."""
        b = _bench(face_angle_inconsistent=True, face_angle=72.0)
        alerts = evaluate_bench_health(b)
        a = [a for a in alerts if a.code == 'ANGLE_INCONSISTENT']
        assert len(a) == 1
        assert a[0].level == 'YELLOW'
        assert a[0].metric_value == pytest.approx(72.0)

    def test_no_alerts_for_clean_bench(self):
        """Healthy bench with all flags false → empty alert list."""
        b = _bench()
        alerts = evaluate_bench_health(b)
        assert alerts == []

    def test_multiple_alerts_per_bench(self):
        """A bench can trigger several alerts (overhang + toppling + wedge + ...)."""
        b = _bench(
            overhang_m=2.0,
            catch_bench_adequate=False,
            catch_bench_ratio=0.3,
            wedge_risk=True,
            toppling_risk=True,
            face_angle_inconsistent=True,
            face_angle=85.0,
            bench_height=25.0,
        )
        alerts = evaluate_bench_health(b)
        codes = sorted(a.code for a in alerts)
        assert codes == sorted([
            'OVERHANG_CRITICAL',
            'CATCH_BENCH_INADEQUATE',
            'TOPPLING_RISK',
            'WEDGE_RISK',
            'ANGLE_INCONSISTENT',
        ])


class TestSectionAlerts:
    """Phase 11 — C.5 aggregate per-section report."""

    def test_aggregate_overall_level_is_worst(self):
        """A section with mixed alerts returns the highest severity overall."""
        benches = [
            _bench(bench_number=1, overhang_m=0.0),  # GREEN
            _bench(bench_number=2, wedge_risk=True),  # YELLOW
            _bench(bench_number=3, overhang_m=2.0),  # RED
            _bench(bench_number=4, catch_bench_adequate=False, catch_bench_ratio=0.3),  # ORANGE
        ]
        rep = aggregate_section_alerts('S1', benches)
        assert isinstance(rep, SectionAlertReport)
        assert rep.section_name == 'S1'
        assert rep.overall_level == 'RED'
        assert len(rep.alerts) >= 3

    def test_empty_section_returns_green(self):
        """No benches → overall GREEN, no alerts, health_score present."""
        rep = aggregate_section_alerts('S-empty', [])
        assert rep.overall_level == 'GREEN'
        assert rep.alerts == []
        assert rep.health_score is not None

    def test_only_yellow_benches_section_yellow(self):
        """Section with only YELLOW triggers → overall YELLOW."""
        benches = [
            _bench(bench_number=1, wedge_risk=True),
            _bench(bench_number=2, face_angle_inconsistent=True, face_angle=75.0),
        ]
        rep = aggregate_section_alerts('S2', benches)
        assert rep.overall_level == 'YELLOW'

    def test_health_score_attached(self):
        """The aggregated report carries the SectionHealthScore."""
        benches = [_bench()]
        rep = aggregate_section_alerts('S3', benches)
        assert rep.health_score is not None
        assert rep.health_score.section_name == 'S3'

    def test_alert_dataclass_fields(self):
        """Alert dataclass exposes all documented fields."""
        a = Alert('RED', 'TEST', 1, 'msg', 'action', 1.5)
        assert a.level == 'RED'
        assert a.code == 'TEST'
        assert a.bench_number == 1
        assert a.message == 'msg'
        assert a.action == 'action'
        assert a.metric_value == pytest.approx(1.5)
