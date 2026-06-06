import { describe, it, expect } from 'vitest';
import {
  applyFilters,
  isFilterActive,
  toggleStatus,
  compareByStatusSeverity,
  DEFAULT_FILTER_STATE,
  ALL_STATUSES_FOR_FILTER,
} from '../filters';
import type { Bench, BenchStatus } from '../types';

// ─── Fixture ────────────────────────────────────────────────

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
    isRamp: false, designHeight: 15, designAngle: 65, designBerm: 8, heightStatus: 'UNKNOWN', angleStatus: 'UNKNOWN', bermStatus: 'UNKNOWN',
    status: 'CUMPLE',
    matched: true,
    ...overrides,
  };
}

const benches: readonly Bench[] = [
  makeBench({ benchNumber: 1, status: 'CUMPLE' }),
  makeBench({ benchNumber: 2, status: 'FUERA' }),
  makeBench({ benchNumber: 3, status: 'NO_CUMPLE' }),
  makeBench({ benchNumber: 4, status: 'UNKNOWN' }),
  makeBench({ benchNumber: 5, status: 'CUMPLE' }),
];

// ─── applyFilters ───────────────────────────────────────────

describe('applyFilters', () => {
  it('returns the input unchanged when statusFilter is empty', () => {
    expect(applyFilters(benches, { ...DEFAULT_FILTER_STATE, statusFilter: [] })).toEqual(benches);
  });

  it('keeps only benches whose status is in the filter', () => {
    const result = applyFilters(benches, { ...DEFAULT_FILTER_STATE, statusFilter: ['CUMPLE'] });
    expect(result.map((b) => b.benchNumber)).toEqual([1, 5]);
  });

  it('supports multiple statuses', () => {
    const result = applyFilters(benches, {
      ...DEFAULT_FILTER_STATE,
      statusFilter: ['CUMPLE', 'FUERA'],
    });
    expect(result.map((b) => b.benchNumber)).toEqual([1, 2, 5]);
  });

  it('returns an empty array if no status matches', () => {
    const result = applyFilters([], { ...DEFAULT_FILTER_STATE, statusFilter: ['NO_CUMPLE'] });
    expect(result).toEqual([]);
  });

  it('does not mutate the input array', () => {
    const input = [...benches];
    applyFilters(input, { ...DEFAULT_FILTER_STATE, statusFilter: ['CUMPLE'] });
    expect(input).toEqual(benches);
  });
});

// ─── isFilterActive ─────────────────────────────────────────

describe('isFilterActive', () => {
  it('returns false for the default state', () => {
    expect(isFilterActive(DEFAULT_FILTER_STATE)).toBe(false);
  });

  it('returns true when any overlay toggle differs from default', () => {
    expect(isFilterActive({ ...DEFAULT_FILTER_STATE, showAreas: true })).toBe(true);
    expect(isFilterActive({ ...DEFAULT_FILTER_STATE, showSpillAreas: false })).toBe(true);
    expect(isFilterActive({ ...DEFAULT_FILTER_STATE, showSemaphore: true })).toBe(true);
    expect(isFilterActive({ ...DEFAULT_FILTER_STATE, showBlastHoles: false })).toBe(true);
  });

  it('returns true when blastTolerance differs from default', () => {
    expect(isFilterActive({ ...DEFAULT_FILTER_STATE, blastTolerance: 5 })).toBe(true);
  });

  it('returns true when statusFilter is non-empty', () => {
    expect(isFilterActive({ ...DEFAULT_FILTER_STATE, statusFilter: ['CUMPLE'] })).toBe(true);
  });
});

// ─── toggleStatus ───────────────────────────────────────────

describe('toggleStatus', () => {
  it('adds a status that is not present', () => {
    expect(toggleStatus([], 'CUMPLE')).toEqual(['CUMPLE']);
    expect(toggleStatus(['FUERA'], 'CUMPLE')).toEqual(['FUERA', 'CUMPLE']);
  });

  it('removes a status that is present', () => {
    expect(toggleStatus(['CUMPLE'], 'CUMPLE')).toEqual([]);
    expect(toggleStatus(['CUMPLE', 'FUERA'], 'CUMPLE')).toEqual(['FUERA']);
  });

  it('does not mutate the input', () => {
    const input: readonly BenchStatus[] = ['CUMPLE'];
    const result = toggleStatus(input, 'FUERA');
    expect(input).toEqual(['CUMPLE']);
    expect(result).not.toBe(input);
  });

  it('handles toggle-twice roundtrip', () => {
    const start: readonly BenchStatus[] = ['CUMPLE', 'FUERA'];
    const after = toggleStatus(toggleStatus(start, 'NO_CUMPLE'), 'NO_CUMPLE');
    expect(after).toEqual(start);
  });
});

// ─── compareByStatusSeverity ────────────────────────────────

describe('compareByStatusSeverity', () => {
  it('orders worst (NO_CUMPLE) first by default (desc)', () => {
    const sorted = [...benches].sort(compareByStatusSeverity);
    expect(sorted[0]!.status).toBe('NO_CUMPLE');
  });

  it('orders least-severe (UNKNOWN) first when asc', () => {
    // UNKNOWN has the lowest severity (0), so asc puts it first.
    // The "best" of the three real statuses (CUMPLE) is second.
    const sorted = [...benches].sort((a, b) => compareByStatusSeverity(a, b, 'asc'));
    expect(sorted[0]!.status).toBe('UNKNOWN');
  });
});

// ─── ALL_STATUSES_FOR_FILTER ────────────────────────────────

describe('ALL_STATUSES_FOR_FILTER', () => {
  it('exposes every status exactly once', () => {
    expect(new Set(ALL_STATUSES_FOR_FILTER).size).toBe(4);
  });
});

// ─── DEFAULT_FILTER_STATE ───────────────────────────────────

describe('DEFAULT_FILTER_STATE', () => {
  it('is frozen so callers cannot mutate it', () => {
    expect(Object.isFrozen(DEFAULT_FILTER_STATE)).toBe(true);
  });
});
