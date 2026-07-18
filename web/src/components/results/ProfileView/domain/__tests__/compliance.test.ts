import { describe, it, expect } from 'vitest';
import { computeCompliance, describeCompliance, iterateCounts } from '../compliance';
import type { Bench, BenchStatus } from '../types';

function makeBench(status: BenchStatus, n: number): Bench {
  return {
    benchNumber: n,
    crestElevation: 100,
    crestDistance: 0,
    toeElevation: 95,
    toeDistance: 5,
    height: 15,
    faceAngle: 65,
    bermWidth: 8,
    isRamp: false, designHeight: 15, designAngle: 65, designBerm: 8, heightStatus: 'UNKNOWN', angleStatus: 'UNKNOWN', bermStatus: 'UNKNOWN',
    status,
    matched: true,
    deltaCrest: null,
    deltaToe: null,
  };
}

describe('computeCompliance', () => {
  it('returns zero counts for an empty input', () => {
    const stats = computeCompliance([]);
    expect(stats.total).toBe(0);
    // FUERA no longer appears in the counts shape — the binary
    // CUMPLE/NO_CUMPLE model means any legacy FUERA bench has
    // already collapsed into NO_CUMPLE by parseBenchStatus.
    expect(stats.counts).toEqual({ CUMPLE: 0, NO_CUMPLE: 0, UNKNOWN: 0 });
    expect(stats.complianceRatio).toBe(0);
    expect(stats.withinTolerance).toBe(0);
  });

  it('counts each status correctly', () => {
    const benches: Bench[] = [
      makeBench('CUMPLE', 1),
      makeBench('CUMPLE', 2),
      makeBench('NO_CUMPLE', 3),
      makeBench('NO_CUMPLE', 4),
      makeBench('UNKNOWN', 5),
    ];
    const stats = computeCompliance(benches);
    expect(stats.counts).toEqual({ CUMPLE: 2, NO_CUMPLE: 2, UNKNOWN: 1 });
    expect(stats.total).toBe(5);
  });

  it('merges legacy FUERA benches into NO_CUMPLE', () => {
    // Defensive: a Bench constructed directly with status='FUERA'
    // (e.g. a fixture or test that bypasses the parsing layer) must
    // still be counted under NO_CUMPLE so the binary model holds
    // end-to-end.
    const benches: Bench[] = [
      makeBench('CUMPLE', 1),
      makeBench('FUERA', 2),
    ];
    const stats = computeCompliance(benches);
    expect(stats.counts).toEqual({ CUMPLE: 1, NO_CUMPLE: 1, UNKNOWN: 0 });
    expect(stats.total).toBe(2);
  });

  it('computes the compliance ratio in [0, 1]', () => {
    const benches: Bench[] = [
      makeBench('CUMPLE', 1),
      makeBench('CUMPLE', 2),
      makeBench('CUMPLE', 3),
      makeBench('NO_CUMPLE', 4),
    ];
    const stats = computeCompliance(benches);
    expect(stats.complianceRatio).toBe(0.75);
  });

  it('returns 0 ratio when nothing complies', () => {
    const benches: Bench[] = [
      makeBench('NO_CUMPLE', 1),
      makeBench('NO_CUMPLE', 2),
    ];
    const stats = computeCompliance(benches);
    expect(stats.complianceRatio).toBe(0);
  });

  it('does not mutate the input', () => {
    const input: Bench[] = [
      makeBench('CUMPLE', 1),
      makeBench('NO_CUMPLE', 2),
    ];
    const snapshot = JSON.parse(JSON.stringify(input));
    computeCompliance(input);
    expect(input).toEqual(snapshot);
  });
});

describe('describeCompliance', () => {
  it('formats "X of Y within tolerance (P%)"', () => {
    const stats = computeCompliance([
      makeBench('CUMPLE', 1),
      makeBench('CUMPLE', 2),
      makeBench('CUMPLE', 3),
      makeBench('NO_CUMPLE', 4),
    ]);
    expect(describeCompliance(stats, (n) => `${Math.round(n * 100)}%`)).toBe(
      '3 of 4 within tolerance (75%)',
    );
  });
});

describe('iterateCounts', () => {
  it('yields every status in presentation order with its count', () => {
    const stats = computeCompliance([
      makeBench('CUMPLE', 1),
      makeBench('NO_CUMPLE', 2),
    ]);
    const out = Array.from(iterateCounts(stats));
    // FUERA has been removed from the presentation order — the
    // compliance summary now only renders the three binary buckets.
    expect(out).toEqual([
      { status: 'NO_CUMPLE', count: 1 },
      { status: 'CUMPLE', count: 1 },
      { status: 'UNKNOWN', count: 0 },
    ]);
  });
});
