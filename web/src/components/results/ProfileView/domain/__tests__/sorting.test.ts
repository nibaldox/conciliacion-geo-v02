import { describe, it, expect } from 'vitest';
import { comparator, applySort, cycleSort, SORT_FIELDS, DEFAULT_SORT } from '../sorting';
import type { Bench } from '../types';

function makeBench(overrides: Partial<Bench> = {}): Bench {
  return {
    benchNumber: 1,
    crestElevation: 100,
    crestDistance: 0,
    toeElevation: 95,
    toeDistance: 5,
    height: 15,
    faceAngle: 65,
    bermWidth: 8,
    isRamp: false,
    status: 'CUMPLE',
    matched: true,
    ...overrides,
  };
}

const benches: readonly Bench[] = [
  makeBench({ benchNumber: 3, height: 12, faceAngle: 70, status: 'FUERA' }),
  makeBench({ benchNumber: 1, height: 15, faceAngle: 65, status: 'CUMPLE' }),
  makeBench({ benchNumber: 5, height: 18, faceAngle: 80, status: 'NO_CUMPLE' }),
  makeBench({ benchNumber: 2, height: 14, faceAngle: 60, status: 'CUMPLE' }),
  makeBench({ benchNumber: 4, height: 16, faceAngle: 75, status: 'FUERA', bermWidth: null }),
];

describe('comparator', () => {
  it('sorts by benchNumber asc', () => {
    const sorted = [...benches].sort(comparator('benchNumber', 'asc'));
    expect(sorted.map((b) => b.benchNumber)).toEqual([1, 2, 3, 4, 5]);
  });

  it('sorts by benchNumber desc', () => {
    const sorted = [...benches].sort(comparator('benchNumber', 'desc'));
    expect(sorted.map((b) => b.benchNumber)).toEqual([5, 4, 3, 2, 1]);
  });

  it('sorts by height asc', () => {
    const sorted = [...benches].sort(comparator('height', 'asc'));
    expect(sorted.map((b) => b.height)).toEqual([12, 14, 15, 16, 18]);
  });

  it('sorts by faceAngle desc', () => {
    const sorted = [...benches].sort(comparator('faceAngle', 'desc'));
    expect(sorted.map((b) => b.faceAngle)).toEqual([80, 75, 70, 65, 60]);
  });

  it('sorts by crestElevation asc', () => {
    const sorted = [...benches].sort(comparator('crestElevation', 'asc'));
    expect(sorted[0]!.crestElevation).toBeLessThanOrEqual(sorted[sorted.length - 1]!.crestElevation);
  });

  it('sorts by status: NO_CUMPLE first, then FUERA, then CUMPLE', () => {
    const sorted = [...benches].sort(comparator('status', 'asc'));
    // First by status rank (presentation order), stable within rank.
    expect(sorted[0]!.status).toBe('NO_CUMPLE');
    expect(sorted[1]!.status).toBe('FUERA');
    // Among CUMPLE, the original order is preserved (stable sort).
  });

  it('pushes null bermWidth to the end regardless of direction', () => {
    const asc = [...benches].sort(comparator('bermWidth', 'asc'));
    expect(asc[asc.length - 1]!.bermWidth).toBeNull();

    const desc = [...benches].sort(comparator('bermWidth', 'desc'));
    expect(desc[desc.length - 1]!.bermWidth).toBeNull();
  });

  it('places a non-null bench BEFORE a null one (a=non-null, b=null)', () => {
    const cmp = comparator('bermWidth', 'asc');
    const nonNull = makeBench({ benchNumber: 1, bermWidth: 8 });
    const nullBench = makeBench({ benchNumber: 2, bermWidth: null });
    expect(cmp(nonNull, nullBench)).toBe(-1);
  });

  it('places a null bench AFTER a non-null one (a=null, b=non-null)', () => {
    const cmp = comparator('bermWidth', 'asc');
    const nullBench = makeBench({ benchNumber: 2, bermWidth: null });
    const nonNull = makeBench({ benchNumber: 1, bermWidth: 8 });
    expect(cmp(nullBench, nonNull)).toBe(1);
  });

  it('treats two null bermWidth benches as equal', () => {
    const cmp = comparator('bermWidth', 'asc');
    const a = makeBench({ benchNumber: 1, bermWidth: null });
    const b = makeBench({ benchNumber: 2, bermWidth: null });
    expect(cmp(a, b)).toBe(0);
  });

  it('throws on unknown field (exhaustiveness guard)', () => {
    const badComparator = comparator('notAField' as never, 'asc');
    expect(() => badComparator(makeBench(), makeBench())).toThrow(/Unhandled sort field/);
  });
});

describe('applySort', () => {
  it('returns a new array (does not mutate)', () => {
    const original = [...benches];
    applySort(benches, 'benchNumber', 'asc');
    expect(benches).toEqual(original);
  });

  it('returns the sorted benches', () => {
    const sorted = applySort(benches, 'height', 'desc');
    expect(sorted.map((b) => b.height)).toEqual([18, 16, 15, 14, 12]);
  });

  it('accepts the default sort', () => {
    const sorted = applySort(benches, DEFAULT_SORT.field, DEFAULT_SORT.direction);
    expect(sorted.map((b) => b.benchNumber)).toEqual([1, 2, 3, 4, 5]);
  });
});

describe('cycleSort', () => {
  it('returns asc when there is no current sort', () => {
    expect(cycleSort(null, 'height')).toEqual({ field: 'height', direction: 'asc' });
  });

  it('returns asc when the clicked field differs from current', () => {
    const next = cycleSort({ field: 'height', direction: 'desc' }, 'faceAngle');
    expect(next).toEqual({ field: 'faceAngle', direction: 'asc' });
  });

  it('cycles asc → desc when the same field is clicked', () => {
    const next = cycleSort({ field: 'height', direction: 'asc' }, 'height');
    expect(next).toEqual({ field: 'height', direction: 'desc' });
  });

  it('cycles desc → null when the same field is clicked again', () => {
    const next = cycleSort({ field: 'height', direction: 'desc' }, 'height');
    expect(next).toBeNull();
  });
});

describe('SORT_FIELDS', () => {
  it('lists the expected fields', () => {
    expect([...SORT_FIELDS].sort()).toEqual(
      ['benchNumber', 'bermWidth', 'crestElevation', 'faceAngle', 'height', 'status'].sort(),
    );
  });
});
