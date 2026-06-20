"""Alert system for slope stability monitoring.

Evaluates a section against critical thresholds and produces
categorized alerts with recommended actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.param_extractor import BenchParams
from core.stability_analysis import (
    SectionHealthScore,
    compute_section_health_score,
)
from core.config import STABILITY


@dataclass
class Alert:
    level: str
    code: str
    bench_number: int
    message: str
    action: str
    metric_value: float


@dataclass
class SectionAlertReport:
    section_name: str
    overall_level: str
    alerts: List[Alert] = field(default_factory=list)
    health_score: Optional[SectionHealthScore] = None


def evaluate_bench_health(bench: BenchParams) -> List[Alert]:
    """Produce alerts for a single bench against critical thresholds."""
    alerts: List[Alert] = []
    if bench.overhang_m >= STABILITY.overhang_critical_m:
        alerts.append(Alert(
            'RED', 'OVERHANG_CRITICAL', bench.bench_number,
            f'Overhang crítico de {bench.overhang_m:.2f} m en cresta.',
            'Detener trabajo en zona. Instrumentar con prismas.',
            float(bench.overhang_m),
        ))
    elif bench.overhang_m >= STABILITY.overhang_warning_m:
        alerts.append(Alert(
            'YELLOW', 'OVERHANG_WARNING', bench.bench_number,
            f'Overhang de {bench.overhang_m:.2f} m. Riesgo de falla planar.',
            'Inspeccionar cara del banco en próximo turno.',
            float(bench.overhang_m),
        ))
    if not bench.catch_bench_adequate:
        alerts.append(Alert(
            'ORANGE', 'CATCH_BENCH_INADEQUATE', bench.bench_number,
            f'Catch bench insuficiente (ratio {bench.catch_bench_ratio:.2f}).',
            'Reprofile catch bench en próximo ciclo de perforación.',
            float(bench.catch_bench_ratio),
        ))
    if bench.toppling_risk:
        alerts.append(Alert(
            'ORANGE', 'TOPPLING_RISK', bench.bench_number,
            f'Toppling potential: cara {bench.face_angle:.1f}°, altura {bench.bench_height:.1f} m.',
            'Evaluar sostenimiento con pernos o malla.',
            float(bench.face_angle),
        ))
    if bench.wedge_risk:
        alerts.append(Alert(
            'YELLOW', 'WEDGE_RISK', bench.bench_number,
            'Posible cuña en cara del banco.',
            'Solicitar mapeo de discontinuidades.',
            0.0,
        ))
    if bench.face_angle_inconsistent:
        alerts.append(Alert(
            'YELLOW', 'ANGLE_INCONSISTENT', bench.bench_number,
            f'Ángulo de cara {bench.face_angle:.1f}° inconsistente con inter-ramp.',
            'Verificar patrón de tronadura aplicado.',
            float(bench.face_angle),
        ))
    return alerts


def aggregate_section_alerts(
    section_name: str,
    benches: List[BenchParams],
) -> SectionAlertReport:
    """Aggregate alerts from all benches in a section."""
    all_alerts: List[Alert] = []
    for b in benches:
        all_alerts.extend(evaluate_bench_health(b))
    level_priority = {'GREEN': 0, 'YELLOW': 1, 'ORANGE': 2, 'RED': 3}
    if all_alerts:
        overall = max(all_alerts, key=lambda a: level_priority.get(a.level, 0)).level
    else:
        overall = 'GREEN'
    health = compute_section_health_score(section_name, benches)
    return SectionAlertReport(
        section_name=section_name,
        overall_level=overall,
        alerts=all_alerts,
        health_score=health,
    )
