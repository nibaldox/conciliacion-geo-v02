import { describe, it, expect } from 'vitest';
import { computeAreasBySector } from '../Dashboard';
import type { ComparisonResult } from '../../../api/types';

function makeRow(overrides: Partial<ComparisonResult> = {}): ComparisonResult {
  return {
    sector: 'Norte',
    section: 'S-001',
    bench_num: 1,
    type: 'MATCH',
    level: '3150',
    height_design: 15,
    height_real: 15,
    height_dev: 0,
    height_status: 'CUMPLE',
    angle_design: 65,
    angle_real: 65,
    angle_dev: 0,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 8,
    berm_min: 5,
    berm_status: 'CUMPLE',
    delta_crest: 0,
    delta_toe: 0,
    ...overrides,
  };
}

describe('computeAreasBySector (G05)', () => {
  it('splits crest deviation into over-excavation and debt per sector', () => {
    const rows = [
      // Norte: +2 m crest × 10 m height = 20 m² over-excavation
      makeRow({ sector: 'Norte', delta_crest: 2, height_real: 10 }),
      // Norte: -1 m crest × 10 m height = 10 m² debt
      makeRow({ sector: 'Norte', delta_crest: -1, height_real: 10, bench_num: 2 }),
      // Sur: -3 m crest × 5 m height = 15 m² debt
      makeRow({ sector: 'Sur', delta_crest: -3, height_real: 5, bench_num: 3 }),
    ];
    const out = computeAreasBySector(rows);
    expect(out).toEqual([
      { sector: 'Norte', overExcavation: 20, debt: 10 },
      { sector: 'Sur', overExcavation: 0, debt: 15 },
    ]);
  });

  it('returns an empty array for empty data', () => {
    expect(computeAreasBySector([])).toEqual([]);
  });

  it('isolates a single sector when all rows belong to it', () => {
    const rows = [
      makeRow({ sector: 'Este', delta_crest: 1, height_real: 12 }),
      makeRow({ sector: 'Este', delta_crest: 4, height_real: 12, bench_num: 2 }),
    ];
    const out = computeAreasBySector(rows);
    expect(out).toHaveLength(1);
    expect(out[0]!.sector).toBe('Este');
    // (1 + 4) × 12 = 60
    expect(out[0]!.overExcavation).toBe(60);
    expect(out[0]!.debt).toBe(0);
  });

  it('treats null delta / height as zero contribution', () => {
    const rows = [
      makeRow({ delta_crest: null, height_real: 10 }),
      makeRow({ delta_crest: 5, height_real: null, bench_num: 2 }),
    ];
    const out = computeAreasBySector(rows);
    expect(out).toEqual([{ sector: 'Norte', overExcavation: 0, debt: 0 }]);
  });
});
