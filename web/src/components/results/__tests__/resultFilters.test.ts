import { describe, expect, it } from 'vitest';
import { EMPTY_RESULT_FILTERS, filterResults, type ResultFilterState } from '../resultFilters';
import type { ComparisonResult } from '../../../api/types';

function makeRow(overrides: Partial<ComparisonResult>): ComparisonResult {
  return {
    sector: 'Norte',
    section: 'S01',
    bench_num: 1,
    type: 'MATCH',
    level: '2960',
    height_design: 15,
    height_real: 15.2,
    height_dev: 0.2,
    height_status: 'CUMPLE',
    angle_design: 70,
    angle_real: 70,
    angle_dev: 0,
    angle_status: 'CUMPLE',
    berm_design: 7,
    berm_real: 7,
    berm_min: 7,
    berm_status: 'CUMPLE',
    delta_crest: null,
    delta_toe: null,
    ...overrides,
  };
}

const rows: ComparisonResult[] = [
  makeRow({ section: 'S01', bench_num: 1, sector: '', delta_crest: 0, delta_toe: 0 }),
  makeRow({ section: 'S02', bench_num: 1, sector: 'Norte' }),
  makeRow({ section: 'S02', bench_num: 2, sector: 'Sur', type: 'MISSING', delta_crest: 1.25, delta_toe: -0.5 }),
  makeRow({ section: 'S03', bench_num: 3, sector: 'Sur', level: '', type: 'EXTRA' }),
];

describe('filterResults', () => {
  it('devuelve todas las filas con filtros vacíos, conservando ceros, sector vacío y MISSING/EXTRA', () => {
    expect(filterResults(rows, EMPTY_RESULT_FILTERS)).toEqual(rows);
  });

  it('EMPTY_RESULT_FILTERS declara el estado vacío del contrato de filtros', () => {
    expect(EMPTY_RESULT_FILTERS).toEqual({ sector: [], section: [], level: [], bench: [] });
  });

  it('filtra por una dimensión seleccionada (OR implícito dentro de la dimensión)', () => {
    let filtered = filterResults(rows, { sector: [], section: [], level: [], bench: [1, 2] });
    expect(filtered.map((r) => r.bench_num).sort()).toEqual([1, 1, 2]);

    filtered = filterResults(rows, { sector: [], section: [], level: [], bench: [] });
    expect(filtered).toEqual(rows);
  });

  it('filtra por sector incluyendo el sector vacío "" como valor seleccionable', () => {
    const filtered = filterResults(rows, { sector: ['Sur'], section: [], level: [], bench: [] });
    expect(filtered.map((r) => r.sector)).toEqual(['Sur', 'Sur']);

    const emptySector = filterResults(rows, { sector: [''], section: [], level: [], bench: [] });
    expect(emptySector.length).toBe(1);
    expect(emptySector[0].section).toBe('S01');
  });

  it('aplica AND entre dimensiones y OR dentro de cada una', () => {
    const filtered = filterResults(rows, { sector: ['Sur', 'Norte'], section: ['S02'], level: [], bench: [] });
    expect(filtered.map((r) => r.section).sort()).toEqual(['S02', 'S02']);
  });

  it('filtra por nivel conservando filas con level vacío solo si "" fue seleccionada', () => {
    const level = filterResults(rows, { sector: [], section: [], level: ['2960'], bench: [] });
    expect(level.every((r) => r.level === '2960')).toBe(true);

    const none = filterResults(rows, { sector: [], section: [], level: ['2900'], bench: [] });
    expect(none).toEqual([]);
  });

  it('retorna arreglo vacío para resultados nulos o indefinidos', () => {
    expect(filterResults(null, EMPTY_RESULT_FILTERS)).toEqual([]);
    expect(filterResults(undefined, EMPTY_RESULT_FILTERS)).toEqual([]);
  });

  it('no muta las filas de entrada ni el estado de filtros', () => {
    const snapshot = rows.map((r) => ({ ...r }));
    const filters: ResultFilterState = { sector: ['Sur'], section: [], level: [], bench: [] };
    filterResults(rows, filters);
    expect(rows).toEqual(snapshot);
    expect(filters).toEqual({ sector: ['Sur'], section: [], level: [], bench: [] });
  });
});
