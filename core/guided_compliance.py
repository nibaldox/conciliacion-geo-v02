"""PROPOSED compliance rules (wave 9 user decisions) — additive side-channel.

Re-scores the comparison rows produced by
:func:`core.profile_compliance.compare_design_vs_asbuilt_guided` according to
the rules the user approved for the proposal, WITHOUT touching a single
official value: :func:`apply_proposed_rules` returns copies carrying the
``proposed_*`` / floor / excavation-debt fields of the wave 9 contract next
to the untouched legacy fields.

Rules (user decisions, definitive — wave 9 plus the wave 13 per-magnitude
source decision):

1. **Per-magnitude source (wave 13)**: every proposed magnitude (height,
   angle, delta crest, delta toe, berm) uses the GUIDED measurement when its
   ``guided_*_status`` is ``'measured'`` for that bench; the official value
   is only a fallback when the guided measurement did not measure that
   magnitude. The origin of each magnitude is registered additively in
   ``proposed_height_source`` / ``proposed_angle_source`` /
   ``proposed_crest_source`` / ``proposed_toe_source`` /
   ``proposed_berm_source`` (``'guided'`` | ``'current'`` | ``None``), and
   ``proposed_source`` aggregates them: ``'guided'`` when every used
   magnitude is guided, ``'current'`` when every used magnitude is official,
   ``'mixed'`` when they combine (``None`` when nothing was measured).
2. **``not_excavated``**: outside the score and the denominators; reported
   as excavation debt (mean/max remaining thickness and section-plane area).
3. **High floor** (``floor_offset_m`` measured): evaluated separately
   against the symmetric vertical tolerance ``floor_vertical`` (default
   ±0.5 m, FUERA up to 1.5x) and the remnant on the design berm is reported
   as ``berm_remnant_max_m`` / ``berm_remnant_area_m2``; neither alters the
   bench score (the height no longer double-penalizes a high floor).
4. **``section_truncated`` / ``unmeasured``**: explicitly not evaluable
   (score ``None``, never 0), outside the averages, with visible coverage.
   Split-bench / MISSING rows additionally need the guided crest AND toe to
   be measured, otherwise they are ``unmeasured``; ``split_bench`` stays
   informative and the EXTRA fragment (``split_of``) stays excluded.
5. Official values never change: everything here is a parallel proposal.

``guided_warnings`` (``incline_berm`` = inclined remnant on the design
berm, ``floor_below_design`` = the only local floor belongs to the next
bench down) travels on the rows as a diagnostic next to the side-by-side
official vs guided values.

Scoring reuses the private helpers of :mod:`core.profile_compliance`
(``_evaluate_status`` / ``_finite_or_none``) so the proposal applies
EXACTLY the official formula (berm 60/0 against the minimum berm, angle
10/0, height 30/0, ``bench_score`` only when every magnitude is measured)
to different input values. A missing magnitude propagates as ``None`` /
``'-'`` and never becomes 0.

EXTRA rows without ``split_of`` keep their current treatment: they remain
additional benches with ``proposed_bench_score`` 0 that do NOT enter the
compliance denominators (``proposed_evaluable`` is False), mirroring how
``compare_design_vs_asbuilt`` scores EXTRA rows 0 while averaging only
MATCH rows.
"""

from core.compliance_status import STATUS_CUMPLE, STATUS_NO_CUMPLE
from core.config import TOLERANCES as _CONFIG_TOLERANCES
from core.profile_compliance import _evaluate_status, _finite_or_none

EXCLUSION_NOT_EXCAVATED = 'not_excavated'
EXCLUSION_SECTION_TRUNCATED = 'section_truncated'
EXCLUSION_UNMEASURED = 'unmeasured'
EXCLUSION_SPLIT_FRAGMENT = 'split_fragment'

_SECTION_SCORE_THRESHOLD = 70.0

_STATE_EXCLUSION = {
    'excavated': None,
    'not_excavated': EXCLUSION_NOT_EXCAVATED,
    'section_truncated': EXCLUSION_SECTION_TRUNCATED,
}

_SOURCE_GUIDED = 'guided'
_SOURCE_CURRENT = 'current'
_SOURCE_MIXED = 'mixed'

_MAGNITUDES = (
    ('guided_height', 'guided_height_status', 'height_real',
     'proposed_height', 'proposed_height_source'),
    ('guided_angle', 'guided_angle_status', 'angle_real',
     'proposed_angle', 'proposed_angle_source'),
    ('guided_delta_crest', 'guided_delta_crest_status', 'delta_crest',
     'proposed_delta_crest', 'proposed_crest_source'),
    ('guided_delta_toe', 'guided_delta_toe_status', 'delta_toe',
     'proposed_delta_toe', 'proposed_toe_source'),
    ('guided_berm', 'guided_berm_status', 'berm_real',
     'proposed_berm', 'proposed_berm_source'),
)


def _floor_max(tolerances) -> float:
    tol = None
    if hasattr(tolerances, 'get'):
        tol = tolerances.get('floor_vertical')
    else:
        tol = getattr(tolerances, 'floor_vertical', None)
    if isinstance(tol, dict):
        value = _finite_or_none(tol.get('max'))
        if value is not None:
            return float(value)
    config_max = _CONFIG_TOLERANCES.floor_vertical.get('max')
    return float(config_max) if config_max is not None else 0.5


def _floor_status(offset, floor_max: float) -> str:
    value = _finite_or_none(offset)
    if value is None:
        return '-'
    return _evaluate_status(abs(value), floor_max, floor_max)


def _delta_status(delta, tolerances) -> str:
    value = _finite_or_none(delta)
    if value is None:
        return '-'
    tol = tolerances.get('crest_toe_deviation') if hasattr(tolerances, 'get') else None
    if not isinstance(tol, dict):
        tol = dict(_CONFIG_TOLERANCES.crest_toe_deviation)
    return _evaluate_status(value, tol.get('neg', 1.0), tol.get('pos', 1.0))


def _score_proposed(height, height_design, angle, angle_design, berm, tolerances) -> dict:
    """Mirror of the ``_build_match_row`` scoring block for proposed values."""
    tol_h = tolerances['bench_height']
    tol_a = tolerances['face_angle']
    tol_b = tolerances.get('berm_width', {}) if hasattr(tolerances, 'get') else {}
    min_berm = tol_b.get('min', 0.0)

    berm_real = _finite_or_none(berm)
    berm_complies = berm_real is not None and berm_real >= min_berm
    berm_status = '-' if berm_real is None else (
        STATUS_CUMPLE if berm_complies else STATUS_NO_CUMPLE)
    berm_score = None if berm_real is None else (60 if berm_complies else 0)

    angle_dev = None
    if angle is not None and angle_design is not None:
        angle_dev = float(angle) - float(angle_design)
    if angle_dev is None:
        angle_status, angle_score = '-', None
    else:
        angle_complies = abs(angle_dev) <= (tol_a['neg'] if angle_dev < 0 else tol_a['pos'])
        angle_status = _evaluate_status(angle_dev, tol_a['neg'], tol_a['pos'])
        angle_score = 10 if angle_complies else 0

    height_dev = None
    if height is not None and height_design is not None:
        height_dev = float(height) - float(height_design)
    if height_dev is None:
        height_status, height_score = '-', None
    else:
        height_complies = abs(height_dev) <= (tol_h['neg'] if height_dev < 0 else tol_h['pos'])
        height_status = _evaluate_status(height_dev, tol_h['neg'], tol_h['pos'])
        height_score = 30 if height_complies else 0

    if berm_score is None or angle_score is None or height_score is None:
        bench_score = None
    else:
        bench_score = float(berm_score + angle_score + height_score)
    return {
        'height_status': height_status,
        'angle_status': angle_status,
        'berm_status': berm_status,
        'bench_score': bench_score,
    }


def apply_proposed_rules(rows, tolerances) -> list[dict]:
    """Return copies of ``rows`` enriched with the proposed compliance fields.

    ``rows`` are the comparison rows of
    :func:`core.profile_compliance.compare_design_vs_asbuilt_guided`
    (legacy + guided fields). The input rows are never mutated and every
    legacy value stays identical in the copies; only the wave 9 contract
    fields are added.
    """
    floor_max = _floor_max(tolerances)
    out: list[dict] = []
    for row in rows:
        new = dict(row)
        new['proposed_source'] = None
        new['proposed_height'] = None
        new['proposed_angle'] = None
        new['proposed_delta_crest'] = None
        new['proposed_delta_toe'] = None
        new['proposed_berm'] = None
        new['proposed_height_source'] = None
        new['proposed_angle_source'] = None
        new['proposed_crest_source'] = None
        new['proposed_toe_source'] = None
        new['proposed_berm_source'] = None
        new['proposed_height_status'] = '-'
        new['proposed_angle_status'] = '-'
        new['proposed_crest_status'] = '-'
        new['proposed_toe_status'] = '-'
        new['proposed_berm_status'] = '-'
        new['proposed_bench_score'] = None
        new['proposed_evaluable'] = False
        new['proposed_exclusion_reason'] = None
        new['floor_offset_m'] = None
        new['floor_status'] = '-'
        new['berm_remnant_max_m'] = row.get('guided_berm_remnant_max_m')
        new['berm_remnant_area_m2'] = row.get('guided_berm_remnant_area_m2')
        new['excavation_debt_thickness_mean_m'] = row.get('guided_remaining_thickness_mean_m')
        new['excavation_debt_thickness_max_m'] = row.get('guided_remaining_thickness_max_m')
        new['excavation_debt_area_m2'] = row.get('guided_excavation_debt_area_m2')

        if row.get('type') == 'EXTRA':
            if row.get('split_of') is not None:
                new['proposed_exclusion_reason'] = EXCLUSION_SPLIT_FRAGMENT
            else:
                new['proposed_bench_score'] = 0.0
            out.append(new)
            continue

        floor_offset = _finite_or_none(row.get('guided_floor_offset_m'))
        if floor_offset is not None:
            new['floor_offset_m'] = row.get('guided_floor_offset_m')
            new['floor_status'] = _floor_status(floor_offset, floor_max)

        state = row.get('design_bench_state')
        if state != 'excavated':
            new['proposed_exclusion_reason'] = _STATE_EXCLUSION.get(
                state, EXCLUSION_UNMEASURED)
            out.append(new)
            continue

        is_missing = row.get('type') == 'MISSING'
        is_split = row.get('type') == 'MATCH' and bool(row.get('split_bench'))
        guided_complete = (
            _finite_or_none(row.get('guided_delta_crest')) is not None
            and _finite_or_none(row.get('guided_delta_toe')) is not None
        )

        if (is_split or is_missing) and not guided_complete:
            new['proposed_exclusion_reason'] = EXCLUSION_UNMEASURED
            out.append(new)
            continue

        used_sources = set()
        for guided_key, status_key, official_key, proposed_key, source_key in _MAGNITUDES:
            guided_value = _finite_or_none(row.get(guided_key))
            if guided_value is not None and row.get(status_key) == 'measured':
                new[proposed_key] = row.get(guided_key)
                new[source_key] = _SOURCE_GUIDED
            elif _finite_or_none(row.get(official_key)) is not None:
                new[proposed_key] = row.get(official_key)
                new[source_key] = _SOURCE_CURRENT
            if new[source_key] is not None:
                used_sources.add(new[source_key])
        if used_sources == {_SOURCE_GUIDED}:
            new['proposed_source'] = _SOURCE_GUIDED
        elif used_sources == {_SOURCE_CURRENT}:
            new['proposed_source'] = _SOURCE_CURRENT
        elif used_sources:
            new['proposed_source'] = _SOURCE_MIXED

        scores = _score_proposed(
            new['proposed_height'], row.get('height_design'),
            new['proposed_angle'], row.get('angle_design'),
            new['proposed_berm'], tolerances,
        )
        new['proposed_height_status'] = scores['height_status']
        new['proposed_angle_status'] = scores['angle_status']
        new['proposed_berm_status'] = scores['berm_status']
        new['proposed_bench_score'] = scores['bench_score']
        new['proposed_crest_status'] = _delta_status(new['proposed_delta_crest'], tolerances)
        new['proposed_toe_status'] = _delta_status(new['proposed_delta_toe'], tolerances)
        new['proposed_evaluable'] = True
        out.append(new)
    return out


def _finite_proposed_scores(rows) -> list[float]:
    return [
        score
        for score in (
            _finite_or_none(r.get('proposed_bench_score'))
            for r in rows
            if r.get('proposed_evaluable')
        )
        if score is not None
    ]


def _count_reason(rows, reason) -> int:
    return sum(1 for r in rows if r.get('proposed_exclusion_reason') == reason)


def _debt_total(rows) -> float:
    return round(
        sum(v for v in (_finite_or_none(r.get('excavation_debt_area_m2')) for r in rows)
            if v is not None),
        2,
    )


def _floor_counts(rows) -> dict:
    counts: dict = {}
    for r in rows:
        status = r.get('floor_status') or '-'
        counts[status] = counts.get(status, 0) + 1
    return counts


def summarize_proposed_section(rows) -> dict:
    """Summarize the proposal for the rows of one section."""
    scores = _finite_proposed_scores(rows)
    section_score = round(sum(scores) / len(scores), 1) if scores else None
    section_status = None
    if section_score is not None:
        section_status = (
            STATUS_CUMPLE if section_score >= _SECTION_SCORE_THRESHOLD
            else STATUS_NO_CUMPLE
        )
    return {
        'section': rows[0].get('section') if rows else None,
        'proposed_section_score': section_score,
        'proposed_section_status': section_status,
        'n_rows': len(rows),
        'n_evaluable': sum(1 for r in rows if r.get('proposed_evaluable')),
        'n_not_excavated': _count_reason(rows, EXCLUSION_NOT_EXCAVATED),
        'n_section_truncated': _count_reason(rows, EXCLUSION_SECTION_TRUNCATED),
        'n_unmeasured': _count_reason(rows, EXCLUSION_UNMEASURED),
        'n_split_fragments': _count_reason(rows, EXCLUSION_SPLIT_FRAGMENT),
        'n_split_benches': sum(
            1 for r in rows if r.get('type') == 'MATCH' and r.get('split_bench')),
        'excavation_debt_area_m2': _debt_total(rows),
        'floor_status_counts': _floor_counts(rows),
    }


def summarize_proposed(rows) -> dict:
    """Summarize the proposal across sections (same counts + global score/coverage)."""
    grouped: dict = {}
    for r in rows:
        grouped.setdefault(r.get('section'), []).append(r)
    by_section = {
        section: summarize_proposed_section(section_rows)
        for section, section_rows in grouped.items()
    }
    scores = _finite_proposed_scores(rows)
    n_evaluable = sum(1 for r in rows if r.get('proposed_evaluable'))
    n_design_benches = sum(1 for r in rows if r.get('type') != 'EXTRA')
    floor_counts: dict = {}
    for counts in (s['floor_status_counts'] for s in by_section.values()):
        for status, n in counts.items():
            floor_counts[status] = floor_counts.get(status, 0) + n
    return {
        'section': None,
        'proposed_global_score': round(sum(scores) / len(scores), 1) if scores else None,
        'n_rows': len(rows),
        'n_evaluable': n_evaluable,
        'n_not_excavated': sum(s['n_not_excavated'] for s in by_section.values()),
        'n_section_truncated': sum(s['n_section_truncated'] for s in by_section.values()),
        'n_unmeasured': sum(s['n_unmeasured'] for s in by_section.values()),
        'n_split_fragments': sum(s['n_split_fragments'] for s in by_section.values()),
        'n_split_benches': sum(s['n_split_benches'] for s in by_section.values()),
        'excavation_debt_area_m2': round(
            sum(s['excavation_debt_area_m2'] for s in by_section.values()), 2),
        'floor_status_counts': floor_counts,
        'coverage': {
            'n_evaluable': n_evaluable,
            'n_design_benches': n_design_benches,
            'ratio': round(n_evaluable / n_design_benches, 3) if n_design_benches else None,
        },
        'by_section': by_section,
    }
