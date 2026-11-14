import { describe, expect, it } from 'vitest';
import { EMPTY_RESULT_FILTERS, filterResults, uniqueLevelOptions, type ResultFilterState } from '../resultFilters.utils';
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

const levelFilter = (level: string[]): ResultFilterState => ({ sector: [], section: [], level, bench: [] });

function realSessionLikeRows(): ComparisonResult[] {
  const out: ComparisonResult[] = [];
  for (let i = 0; i < 96; i += 1) {
    const section = `S-${String(i + 1).padStart(2, '0')}`;
    out.push(makeRow({ sector: 'Fase 1', section, bench_num: 1, level: String(3124 + (i % 3)), level_nominal: '3125' }));
    out.push(makeRow({ sector: 'Fase 1', section, bench_num: 2, level: String(3109 + (i % 3)), level_nominal: '3110' }));
    out.push(makeRow({ sector: 'Fase 1', section, bench_num: 3, type: 'MISSING', level: String(3095 + (i % 10)), level_nominal: '3104' }));
  }
  return out;
}

describe('cota nominal', () => {
  const session = realSessionLikeRows();

  it('agrupa la dispersión real del banco 3 (3095–3104) en una sola opción "3104"', () => {
    expect(new Set(session.filter((r) => r.bench_num === 3).map((r) => r.level)).size).toBe(10);
    expect(uniqueLevelOptions(session)).toEqual(['3125', '3110', '3104']);
  });

  it('ordena las opciones numéricas de mayor a menor y deja las no numéricas al final', () => {
    const mixed = [
      makeRow({ level: '85' }),
      makeRow({ level: '1000' }),
      makeRow({ level: '' }),
      makeRow({ level: '100', level_nominal: '100' }),
      makeRow({ level: 'rampa' }),
    ];
    expect(uniqueLevelOptions(mixed)).toEqual(['1000', '100', '85', '', 'rampa']);
    expect(uniqueLevelOptions(null)).toEqual([]);
  });

  it('seleccionar "3104" conserva las 96 filas del banco 3', () => {
    const kept = filterResults(session, levelFilter(['3104']));
    expect(kept).toHaveLength(96);
    expect(kept.every((r) => r.bench_num === 3)).toBe(true);
  });

  it('usa la cota exacta como respaldo cuando el valor no es una cota nominal del sector', () => {
    const kept = filterResults(session, levelFilter(['3099']));
    expect(kept.length).toBeGreaterThan(0);
    expect(kept.every((r) => r.level === '3099' && r.bench_num === 3)).toBe(true);
    expect(kept).toHaveLength(session.filter((r) => r.level === '3099').length);
    expect(filterResults(session, levelFilter(['3104', '3099']))).toHaveLength(96);
  });

  it('no aplica el respaldo exacto a un valor que sí es cota nominal del sector', () => {
    const shifted = [
      makeRow({ sector: 'A', section: 'S01', bench_num: 1, level: '3110', level_nominal: '3110' }),
      makeRow({ sector: 'A', section: 'S02', bench_num: 1, level: '3104', level_nominal: '3110' }),
      makeRow({ sector: 'A', section: 'S01', bench_num: 2, level: '3103', level_nominal: '3104' }),
      makeRow({ sector: 'B', section: 'S03', bench_num: 1, level: '3104', level_nominal: '3100' }),
    ];
    const kept = filterResults(shifted, levelFilter(['3104']));
    expect(kept.map((r) => `${r.sector}/${r.section}/${r.bench_num}`)).toEqual(['A/S01/2', 'B/S03/1']);
  });

  it('filtra por level cuando la API antigua no entrega level_nominal', () => {
    const legacy = [
      makeRow({ section: 'S01', level: '3104' }),
      makeRow({ section: 'S02', level: '3099' }),
      makeRow({ section: 'S03', level: '' }),
    ];
    expect(legacy.every((r) => !('level_nominal' in r))).toBe(true);
    expect(uniqueLevelOptions(legacy)).toEqual(['3104', '3099', '']);
    expect(filterResults(legacy, levelFilter(['3099'])).map((r) => r.section)).toEqual(['S02']);
    expect(filterResults(legacy, levelFilter([''])).map((r) => r.section)).toEqual(['S03']);
  });

  it('una fila con level_nominal nulo se ofrece y se filtra por su cota exacta', () => {
    const mixed = [
      makeRow({ section: 'S01', level: '100', level_nominal: '100' }),
      makeRow({ section: 'S02', level: '', level_nominal: null, type: 'EXTRA' }),
    ];
    expect(uniqueLevelOptions(mixed)).toEqual(['100', '']);
    expect(filterResults(mixed, levelFilter([''])).map((r) => r.section)).toEqual(['S02']);
  });
});
