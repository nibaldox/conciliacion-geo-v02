import { describe, it, expect } from 'vitest';
import { filterByBench, uniqueBenchNumbers } from '../Dashboard';
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

const rows: ComparisonResult[] = [
  makeRow({ sector: 'Norte', bench_num: 1 }),
  makeRow({ sector: 'Norte', bench_num: 2 }),
  makeRow({ sector: 'Sur', bench_num: 3 }),
  makeRow({ sector: 'Sur', bench_num: 1 }),
];

describe('filterByBench (G10)', () => {
  it('returns every row when the selection is empty (empty = all)', () => {
    expect(filterByBench(rows, [])).toEqual(rows);
  });

  it('keeps only rows whose bench_num is selected (filter applied)', () => {
    const out = filterByBench(rows, [3]);
    expect(out.map((r) => r.bench_num)).toEqual([3]);
  });

  it('supports multi-select across benches', () => {
    const out = filterByBench(rows, [1, 3]);
    // benches 1 (Norte), 3 (Sur), 1 (Sur) — order preserved
    expect(out.map((r) => `${r.sector}-${r.bench_num}`)).toEqual([
      'Norte-1',
      'Sur-3',
      'Sur-1',
    ]);
  });

  it('clearing the filter restores the full dataset', () => {
    const restricted = filterByBench(rows, [2]);
    expect(restricted).toHaveLength(1);
    const cleared = filterByBench(rows, []);
    expect(cleared).toEqual(rows);
  });

  it('does not mutate the input array', () => {
    const snapshot = [...rows];
    filterByBench(rows, [1]);
    expect(rows).toEqual(snapshot);
  });
});

describe('uniqueBenchNumbers', () => {
  it('returns sorted unique bench numbers', () => {
    expect(uniqueBenchNumbers(rows)).toEqual([1, 2, 3]);
  });

  it('returns an empty list for no data', () => {
    expect(uniqueBenchNumbers([])).toEqual([]);
  });
});
