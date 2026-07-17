/**
 * Tests for the G08 parity gap: bench toe annotations (`B1'`, `B2'`)
 * and berm shape indicators (dashed horizontal lines connecting each
 * bench toe to the next bench crest).
 *
 * `buildAnnotations` and `buildBermShapes` are pure helpers extracted
 * from the layout derivation in `ProfileChart` so they can be tested
 * independently of React / Plotly rendering.
 */

import { describe, it, expect } from 'vitest';
import { buildAnnotations, buildBermShapes } from '../ProfileChart';
import type { Bench, ProfileViewModel } from '../../domain/types';

// ─── Test fixtures ──────────────────────────────────────────

function makeBench(overrides: Partial<Bench> = {}): Bench {
  return {
    benchNumber: 1,
    crestElevation: 3150,
    crestDistance: 5,
    toeElevation: 3125,
    toeDistance: 12,
    height: 25,
    faceAngle: 65,
    bermWidth: 8,
    designHeight: 25,
    designAngle: 65,
    designBerm: 8,
    isRamp: false,
    status: 'CUMPLE',
    heightStatus: 'UNKNOWN',
    angleStatus: 'UNKNOWN',
    bermStatus: 'UNKNOWN',
    matched: true,
    deltaCrest: null,
    deltaToe: null,
    ...overrides,
  };
}

function makeViewModel(benches: readonly Bench[]): ProfileViewModel {
  return {
    section: {
      id: 'sec-1',
      name: 'S-001',
      sector: 'Norte',
      azimuth: 45,
      length: 200,
      origin: [0, 0],
    },
    lines: [],
    benches,
  };
}

// ─── buildBermShapes ───────────────────────────────────────

describe('buildBermShapes', () => {
  it('returns N-1 shapes for N benches, each spanning toe→next-crest at the toe elevation', () => {
    const vm = makeViewModel([
      makeBench({ benchNumber: 1, toeDistance: 12, toeElevation: 3125 }),
      makeBench({ benchNumber: 2, toeDistance: 30, toeElevation: 3100, crestDistance: 22 }),
      makeBench({ benchNumber: 3, toeDistance: 48, toeElevation: 3075, crestDistance: 40 }),
    ]);

    const shapes = buildBermShapes(vm);

    // 3 benches → 2 berms (the last bench has no successor).
    expect(shapes).toHaveLength(2);

    // First berm: from bench 1's toe (12, 3125) to bench 2's crest (22, 3125).
    const [first] = shapes;
    expect(first?.type).toBe('line');
    expect(first?.x0).toBe(12);
    expect(first?.x1).toBe(22);
    expect(first?.y0).toBe(3125);
    expect(first?.y1).toBe(3125);
    expect(first?.line).toEqual({ color: '#888', width: 2, dash: 'dot' });

    // Second berm: from bench 2's toe (30, 3100) to bench 3's crest (40, 3100).
    const [, second] = shapes;
    expect(second?.x0).toBe(30);
    expect(second?.x1).toBe(40);
    expect(second?.y0).toBe(3100);
    expect(second?.y1).toBe(3100);
  });

  it('returns 0 shapes for a single bench (no successor to connect)', () => {
    const vm = makeViewModel([makeBench({ benchNumber: 1 })]);

    expect(buildBermShapes(vm)).toHaveLength(0);
  });
});

// ─── buildAnnotations ──────────────────────────────────────

describe('buildAnnotations', () => {
  it('returns N annotations when showAnnotations=true', () => {
    const vm = makeViewModel([
      makeBench({ benchNumber: 1 }),
      makeBench({ benchNumber: 2 }),
      makeBench({ benchNumber: 3 }),
    ]);

    expect(buildAnnotations(vm, true)).toHaveLength(3);
  });

  it('returns 0 annotations when showAnnotations=false', () => {
    const vm = makeViewModel([
      makeBench({ benchNumber: 1 }),
      makeBench({ benchNumber: 2 }),
    ]);

    expect(buildAnnotations(vm, false)).toHaveLength(0);
  });

  it("formats toe labels as B{number}' anchored at the toe point with no arrow", () => {
    const vm = makeViewModel([
      makeBench({ benchNumber: 7, toeDistance: 42, toeElevation: 3099 }),
    ]);

    const [annotation] = buildAnnotations(vm, true);

    // Prime symbol distinguishes the toe (pie) label from the crest
    // label `B7` already rendered by the bench-marker trace.
    // Includes the toe elevation for geotechnical context.
    expect(annotation?.text).toContain("B7'");
    expect(annotation?.text).toContain("3099");
    expect(annotation?.x).toBe(42);
    expect(annotation?.y).toBe(3099);
    expect(annotation?.showarrow).toBe(false);
    expect(annotation?.font).toEqual({ size: 10, color: '#888' });
  });
});
