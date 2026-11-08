"""Pure helpers for the PROPOSED compliance view (Oficial vs Propuesta).

Reads the ``guided_*`` / ``proposed_*`` fields added by
``core.compare_design_vs_asbuilt_guided`` and builds presentation-only
tables and Plotly traces. Official values are read, never modified.
"""
import math

import plotly.graph_objects as go

PROPOSAL_UNAVAILABLE_MESSAGE = (
    "Esta sesión se procesó antes de la medición guiada: "
    "Reprocese (Paso 3 → Ejecutar Análisis) para ver la propuesta."
)

_BENCH_STATE_LABELS = {
    'excavated': 'Excavado',
    'not_excavated': 'No excavado',
    'section_truncated': 'Truncado por la sección',
    'unmeasured': 'Sin medir',
}
_SOURCE_LABELS = {'current': 'Actual', 'guided': 'Guiada', 'mixed': 'Mixta'}
_SOURCE_SUFFIXES = {'guided': ' (g)', 'current': ' (o)'}
_DEFAULT_FLOOR_SPAN_M = 8.0


def has_proposal(rows) -> bool:
    """True when at least one row carries the ``proposed_*`` fields."""
    return any('proposed_source' in r for r in rows)


def _fmt(value) -> str:
    if value is None:
        return '—'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return '—'
    return f"{number:g}"


def _pair(official, proposed, source=None) -> str:
    suffix = _SOURCE_SUFFIXES.get(source, '')
    return f"{_fmt(official)} → {_fmt(proposed)}{suffix}"


def _bench_state_label(row) -> str:
    reason = row.get('proposed_exclusion_reason')
    if reason == 'split_fragment':
        return 'Fragmento de banco partido'
    if row.get('type') == 'MATCH' and row.get('split_bench'):
        return 'Banco partido'
    if reason in _BENCH_STATE_LABELS:
        label = _BENCH_STATE_LABELS[reason]
        if reason == 'not_excavated':
            debt = row.get('excavation_debt_area_m2')
            if debt is not None:
                try:
                    label += f" · deuda {float(debt):.1f} m²"
                except (TypeError, ValueError):
                    pass
        return label
    return _BENCH_STATE_LABELS.get(row.get('design_bench_state'), '—')


def _floor_label(row) -> str:
    offset = row.get('floor_offset_m')
    if offset is None:
        offset = row.get('guided_floor_offset_m')
    if offset is None:
        return '—'
    status = row.get('floor_status') or '-'
    return f"{_fmt(offset)} m · {status}"


def build_proposed_rows(rows, include_section: bool = False) -> list[dict]:
    """Compact Oficial → Propuesta table rows, one per comparison row."""
    table = []
    for row in rows:
        entry: dict = {}
        if include_section:
            entry['Sección'] = str(row.get('section') or '—')
        bench = row.get('bench_num')
        if row.get('type') == 'EXTRA':
            entry['Banco'] = f"+{row.get('bench_num_topo', '—')} (adicional)"
        else:
            entry['Banco'] = f"B{bench}" if bench is not None else '—'
        entry['Estado banco'] = _bench_state_label(row)
        entry['Origen'] = _SOURCE_LABELS.get(row.get('proposed_source'), '—')
        entry['Altura'] = _pair(row.get('height_real'), row.get('proposed_height'), row.get('proposed_height_source'))
        entry['Ángulo'] = _pair(row.get('angle_real'), row.get('proposed_angle'), row.get('proposed_angle_source'))
        entry['Δ Cresta'] = _pair(row.get('delta_crest'), row.get('proposed_delta_crest'), row.get('proposed_crest_source'))
        entry['Δ Pata'] = _pair(row.get('delta_toe'), row.get('proposed_delta_toe'), row.get('proposed_toe_source'))
        entry['Berma'] = _pair(row.get('berm_real'), row.get('proposed_berm'), row.get('proposed_berm_source'))
        entry['Puntaje'] = _pair(row.get('bench_score'), row.get('proposed_bench_score'))
        entry['Piso (±0,5 m)'] = _floor_label(row)
        table.append(entry)
    return table


def _profile_range_from_fig(fig):
    xs = []
    for trace in fig.data:
        mode = str(getattr(trace, "mode", "") or "")
        if "line" not in mode:
            continue
        for value in (getattr(trace, "x", None) or []):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                xs.append(number)
    if not xs:
        return None
    return (min(xs), max(xs))


def add_proposal_traces(fig, sec_rows, design_benches, profile_range=None) -> None:
    """Overlay the guided solid toe and the local floor on a profile figure.

    ``design_benches`` are the design benches of the section (positions of
    the design toe/crest); guided absolute positions are reconstructed from
    the design toe plus the signed guided delta. ``profile_range`` is the
    ``(x_min, x_max)`` extent of the profile; when absent it is derived from
    the line traces already drawn on ``fig``.
    """
    if not sec_rows or not design_benches:
        return
    if profile_range is None:
        profile_range = _profile_range_from_fig(fig)
    by_number = {}
    for bench in design_benches:
        try:
            by_number[int(bench.bench_number)] = bench
        except (TypeError, ValueError):
            continue
    row_by_number = {}
    for row in sec_rows:
        if row.get('type') != 'EXTRA' and row.get('bench_num') is not None:
            try:
                row_by_number[int(row['bench_num'])] = row
            except (TypeError, ValueError):
                continue

    toe_x: list[float] = []
    toe_y: list[float] = []
    floor_segments: list[tuple[float, float, float]] = []

    for row in sec_rows:
        if row.get('type') == 'EXTRA':
            continue
        bench = by_number.get(row.get('bench_num'))
        if bench is None:
            continue
        crest_d = float(bench.crest_distance)
        toe_d = float(bench.toe_distance)
        toe_e = float(bench.toe_elevation)
        sign = 1.0 if crest_d >= toe_d else -1.0

        floor_offset = row.get('floor_offset_m')
        if floor_offset is None:
            floor_offset = row.get('guided_floor_offset_m')
        floor_e = None
        if floor_offset is not None:
            try:
                floor_e = toe_e + float(floor_offset)
            except (TypeError, ValueError):
                floor_e = None

        guided_toe = None
        delta_toe = row.get('guided_delta_toe')
        if delta_toe is not None:
            try:
                guided_toe = toe_d + float(delta_toe) * sign
            except (TypeError, ValueError):
                guided_toe = None
        if guided_toe is not None:
            toe_x.append(guided_toe)
            toe_y.append(floor_e if floor_e is not None else toe_e)

        if floor_e is not None:
            span = _DEFAULT_FLOOR_SPAN_M
            berm = row.get('berm_design')
            if berm is not None:
                try:
                    span = float(berm)
                except (TypeError, ValueError):
                    span = _DEFAULT_FLOOR_SPAN_M
            start = guided_toe if guided_toe is not None else toe_d
            x1 = start - sign * span
            anchored = False
            lower = by_number.get(int(bench.bench_number) + 1)
            if lower is not None:
                lower_crest_d = float(lower.crest_distance)
                lower_sign = 1.0 if lower_crest_d >= float(lower.toe_distance) else -1.0
                lower_crest = lower_crest_d
                lower_row = row_by_number.get(int(lower.bench_number))
                delta_crest = lower_row.get('guided_delta_crest') if lower_row is not None else None
                if delta_crest is not None:
                    try:
                        lower_crest += float(delta_crest) * lower_sign
                    except (TypeError, ValueError):
                        pass
                if (sign > 0 and lower_crest < start) or (sign < 0 and lower_crest > start):
                    x1 = lower_crest
                    anchored = True
            if not anchored and profile_range is not None:
                x1 = float(profile_range[0]) if sign > 0 else float(profile_range[1])
            if profile_range is not None:
                lo, hi = float(profile_range[0]), float(profile_range[1])
                x1 = min(max(x1, lo), hi)
                start = min(max(start, lo), hi)
            floor_segments.append((start, x1, floor_e))

    if toe_x:
        fig.add_trace(go.Scatter(
            x=toe_x, y=toe_y, mode='markers', name='Pata sólida guiada',
            marker=dict(symbol='triangle-up', size=11, color='#7B1FA2',
                        line=dict(width=1, color='white')),
            legendgroup='propuesta',
        ))
    for idx, (x0, x1, z) in enumerate(floor_segments):
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[z, z], mode='lines',
            name='Piso local (propuesta)' if idx == 0 else None,
            line=dict(color='#7B1FA2', width=2, dash='dot'),
            legendgroup='propuesta piso', showlegend=idx == 0,
        ))
