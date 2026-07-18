import { describe, it, expect } from 'vitest';
import { computeStatusCountsBySector, filterByBench } from '../Dashboard';
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

describe('computeStatusCountsBySector (G07)', () => {
  it('stacks CUMPLE / NO_CUMPLE per sector (render data)', () => {
    const rows = [
      makeRow({ sector: 'Norte', bench_num: 1, height_status: 'CUMPLE' }),
      makeRow({
        sector: 'Norte',
        bench_num: 2,
        height_status: 'FUERA DE TOLERANCIA',
      }),
      makeRow({ sector: 'Norte', bench_num: 3, height_status: 'NO CUMPLE' }),
      makeRow({ sector: 'Sur', bench_num: 1, angle_status: 'CUMPLE' }),
    ];
    const out = computeStatusCountsBySector(rows);
    expect(out).toEqual([
      { sector: 'Norte', CUMPLE: 1, NO_CUMPLE: 2 },
      { sector: 'Sur', CUMPLE: 1, NO_CUMPLE: 0 },
    ]);
  });

  it('respects the bench filter (filter applied)', () => {
    const rows = [
      makeRow({ sector: 'Norte', bench_num: 1, height_status: 'CUMPLE' }),
      makeRow({
        sector: 'Norte',
        bench_num: 2,
        height_status: 'NO CUMPLE',
      }),
      makeRow({ sector: 'Sur', bench_num: 3, height_status: 'CUMPLE' }),
    ];
    const filtered = filterByBench(rows, [2]);
    const out = computeStatusCountsBySector(filtered);
    expect(out).toEqual([
      { sector: 'Norte', CUMPLE: 0, NO_CUMPLE: 1 },
    ]);
  });
});
