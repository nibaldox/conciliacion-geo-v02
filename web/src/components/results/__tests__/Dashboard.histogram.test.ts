import { describe, it, expect } from 'vitest';
import { collectDeviations, filterByBench } from '../Dashboard';
import type { ComparisonResult } from '../../../../api/types';

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

describe('collectDeviations (G06)', () => {
  it('gathers every finite crest deviation (render data)', () => {
    const rows = [
      makeRow({ delta_crest: 0.5, bench_num: 1 }),
      makeRow({ delta_crest: -1.2, bench_num: 2 }),
      makeRow({ delta_crest: 3.0, bench_num: 3 }),
    ];
    expect(collectDeviations(rows, 'delta_crest')).toEqual([0.5, -1.2, 3.0]);
  });

  it('skips null and non-finite values', () => {
    const rows = [
      makeRow({ delta_crest: 1, bench_num: 1 }),
      makeRow({ delta_crest: null, bench_num: 2 }),
      makeRow({ delta_crest: NaN, bench_num: 3 }),
      makeRow({ delta_crest: 2, bench_num: 4 }),
    ];
    expect(collectDeviations(rows, 'delta_crest')).toEqual([1, 2]);
  });

  it('respects the bench filter (filter applied)', () => {
    const rows = [
      makeRow({ delta_crest: 1, bench_num: 1 }),
      makeRow({ delta_crest: 2, bench_num: 2 }),
      makeRow({ delta_crest: 3, bench_num: 3 }),
    ];
    const filtered = filterByBench(rows, [2, 3]);
    expect(collectDeviations(filtered, 'delta_crest')).toEqual([2, 3]);
  });
});
