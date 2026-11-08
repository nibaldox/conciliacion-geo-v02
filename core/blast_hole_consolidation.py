from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import pandas as pd


BLAST_ALGORITHM_VERSION = 'blast-auditable.v1'

_GEOMETRY = ('X', 'Y', 'Z_collar', 'Len', 'Incl', 'Az')
_DATE = ('fecha_tronadura',)
_CHARGE = ('Kilos_Cargados_real', 'Tipo_Explosivo', 'Taco_m')
_PATTERN = ('Nombre_Malla_Original', 'Blast')


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())
    except (TypeError, ValueError):
        return False


def _text(value: Any) -> str | None:
    return None if _missing(value) else str(value)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _user_source_row(value: Any) -> int | None:
    if _missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def consolidate_blast_holes(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Consolidate source rows by event and literal hole ID without mutating input."""
    if 'decks' in df.columns and all(isinstance(v, list) for v in df['decks']):
        previous = df.attrs.get('consolidation_report')
        if previous is not None:
            return df.copy(deep=True), previous.copy()
    from core.column_utils import KILOS_CANDIDATES, first_present_column

    df = df.copy()
    kilos_column = first_present_column(df, KILOS_CANDIDATES)
    if kilos_column is not None:
        df['Kilos_Cargados_real'] = pd.to_numeric(df[kilos_column], errors='coerce')
    report: dict[str, Any] = {
        'key_columns': ['uniqid', 'Nombre_Malla_Original', 'Blast', 'id_pozo'],
        'rows_in': len(df), 'holes_out': 0, 'exact_copies_removed': 0,
        'copies_by_malla': {}, 'holes_with_decks': 0, 'deck_rows_merged': 0,
        'conflicts': [], 'unmerged_missing_identity': 0,
        'version': 'hole-consolidation.v1', 'warnings': [],
    }
    columns = set(df.columns)
    geometry = [c for c in _GEOMETRY + ('Incl_original',) + _DATE if c in columns]
    compared = [c for c in _GEOMETRY + _CHARGE + _DATE + _PATTERN if c in columns]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    entries = []
    for position, (index, values) in enumerate(zip(df.index, df.to_dict('records'))):
        source = values.get('source_row_index', index)
        if not isinstance(source, int):
            try:
                source = int(source)
            except (TypeError, ValueError):
                source = position
        event = next((_text(values.get(c)) for c in ('uniqid', 'Nombre_Malla_Original', 'Blast') if _text(values.get(c)) is not None), None)
        hole = _text(values.get('id_pozo'))
        malla = next((_text(values.get(c)) for c in ('Nombre_Malla_Original', 'Blast', 'uniqid') if _text(values.get(c)) is not None), '')
        entry = {'row': values, 'index': index, 'source': source, 'event': event, 'hole': hole, 'malla': malla, 'position': position}
        entries.append(entry)
        if event is None or hole is None:
            report['unmerged_missing_identity'] += 1
            report['warnings'].append({'reason': 'missing_identity', 'source_row_indices': [source]})
        else:
            groups[(event, hole)].append(entry)
    output = []

    def emit(items: list[dict], removed: int = 0, sources: list[int] | None = None) -> None:
        first = items[0]
        row = first['row'].copy()
        decks = [{'kg': _number(e['row'].get('Kilos_Cargados_real')),
                  'explosive': _text(e['row'].get('Tipo_Explosivo')),
                  'taco_m': _number(e['row'].get('Taco_m')),
                  'source_row_index': e['source']} for e in items]
        mix: dict[str, float] = {}
        products = set()
        for deck in decks:
            if deck['explosive'] is not None:
                products.add(deck['explosive'])
                if deck['kg'] is not None:
                    mix[deck['explosive']] = mix.get(deck['explosive'], 0.0) + deck['kg']
        row['hole_key'] = f"{first['event']}|{first['hole']}" if first['event'] is not None and first['hole'] is not None else None
        row['decks'] = decks
        row['n_decks'] = len(decks)
        row['explosive_mix'] = mix
        row['explosive_mixed'] = len(products) > 1
        row['duplicate_rows_removed'] = removed
        row['source_row_indices'] = sorted(sources if sources is not None else [e['source'] for e in items])
        user_sources = [_user_source_row(e['row'].get('source_row_index_user')) for e in items]
        user_sources = [value for value in user_sources if value is not None]
        row['source_row_indices_user'] = user_sources or None
        row['Kilos_Cargados_real'] = sum(d['kg'] for d in decks) if all(d['kg'] is not None for d in decks) else None
        row['Tipo_Explosivo'] = min(mix, key=lambda key: (-mix[key], key)) if mix else None
        output.append((first['position'], first['index'], row))

    for entry in entries:
        if entry['event'] is None or entry['hole'] is None:
            emit([entry])
    for (event, hole), group in groups.items():
        group.sort(key=lambda e: (e['source'], e['position']))
        if len(group) == 1:
            emit(group)
            continue
        identity_mismatch = any(
            len({_text(e['row'].get(col)) for e in group if not _missing(e['row'].get(col))}) > 1
            for col in _PATTERN
        )
        taco_mismatch = len({_number(e['row'].get('Taco_m')) for e in group
                             if _number(e['row'].get('Taco_m')) is not None}) > 1
        if identity_mismatch or taco_mismatch:
            report['conflicts'].append({'malla': group[0]['malla'], 'id_pozo': hole,
                                        'source_row_indices': [e['source'] for e in group],
                                        'reason': 'event_identity_mismatch' if identity_mismatch else 'non_charge_attribute_mismatch'})
            for entry in group:
                emit([entry])
            continue
        signatures = [tuple(e['row'].get(c) for c in geometry) for e in group]
        comparable = all(not _missing(value) for signature in signatures for value in signature)
        mismatch = any(len({e['row'].get(col) for e in group if not _missing(e['row'].get(col))}) > 1 for col in geometry)
        if mismatch:
            report['conflicts'].append({'malla': group[0]['malla'], 'id_pozo': hole,
                                        'source_row_indices': [e['source'] for e in group],
                                        'reason': 'geometry_or_date_mismatch'})
            for entry in group:
                emit([entry])
            continue
        if not comparable:
            report['warnings'].append({'reason': 'missing_geometry_or_date', 'source_row_indices': [e['source'] for e in group]})
            for entry in group:
                emit([entry])
            continue
        unique = []
        seen = {}
        removed = 0
        copies: dict[int, list[int]] = defaultdict(list)
        for entry in group:
            values = tuple(entry['row'].get(c) for c in compared)
            if any(_missing(value) for value in values):
                unique.append(entry)
                report['warnings'].append({'reason': 'missing_comparison_value', 'source_row_indices': [entry['source']]})
                continue
            if values in seen:
                removed += 1
                copies[seen[values]['position']].append(entry['source'])
            else:
                seen[values] = entry
                unique.append(entry)
        if len(unique) > 1:
            charge_values = [tuple(e['row'].get(c) for c in _CHARGE[:2] if c in columns) for e in unique]
            if any(not any(not _missing(a) and not _missing(b) and a != b for a, b in zip(left, right)) for pos, left in enumerate(charge_values) for right in charge_values[pos + 1:]):
                report['warnings'].append({'reason': 'indistinguishable_decks', 'source_row_indices': [e['source'] for e in unique]})
                report['exact_copies_removed'] += removed
                if removed:
                    name = group[0]['malla']
                    report['copies_by_malla'][name] = report['copies_by_malla'].get(name, 0) + removed
                for entry in unique:
                    duplicate_sources = copies[entry['position']]
                    emit([entry], len(duplicate_sources), [entry['source'], *duplicate_sources])
                continue
        report['exact_copies_removed'] += removed
        if removed:
            name = group[0]['malla']
            report['copies_by_malla'][name] = report['copies_by_malla'].get(name, 0) + removed
        if len(unique) > 1:
            report['holes_with_decks'] += 1
            report['deck_rows_merged'] += len(unique) - 1
        emit(unique, removed, [e['source'] for e in group])
    output.sort(key=lambda item: item[0])
    if output:
        result = pd.DataFrame([item[2] for item in output], index=[item[1] for item in output])
    else:
        result = df.copy()
        for col in ('hole_key', 'decks', 'n_decks', 'explosive_mix', 'explosive_mixed', 'duplicate_rows_removed', 'source_row_indices', 'source_row_indices_user'):
            result[col] = pd.Series(dtype=object)
    report['holes_out'] = len(result)
    result.attrs['consolidation_report'] = report
    return result, report
