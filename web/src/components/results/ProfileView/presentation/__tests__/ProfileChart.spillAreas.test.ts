/**
 * Tests for the spill-area ("Derrame") traces emitted by `buildTraces`.
 *
 * These cover the G02 parity gap: the "Mostrar Área de Derrame" toggle
 * must actually produce filled rectangle traces when benches carry
 * spill data, and must stay silent otherwise.
 */

import { describe, it, expect } from 'vitest';
import { buildTraces } from '../ProfileChart';
import type { ProfileViewModel } from '../../domain/types';
import type { SpillBench } from '../../domain/mapping';
import type { FilterState } from '../../domain/filters';
import { DEFAULT_FILTER_STATE } from '../../domain/filters';
import type { UseCrossLinkStateApi } from '../../application';

// ─── Test fixtures ──────────────────────────────────────────

function makeViewModel(overrides: Partial<ProfileViewModel> = {}): ProfileViewModel {
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
    benches: [],
    ...overrides,
  };
}

/** A bench with spill data by default (matches the brief's test data). */
function makeSpillBench(overrides: Partial<SpillBench> = {}): SpillBench {
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
    spillWidth: 5,
    spillStartDistance: 10,
    spillStartElevation: 3145,
    ...overrides,
  };
}

const stubCrossLink: UseCrossLinkStateApi = {
  hovered: null,
  selected: null,
  setHovered: () => {},
  setSelected: () => {},
  clear: () => {},
};

function makeFilterState(overrides: Partial<FilterState> = {}): FilterState {
  return { ...DEFAULT_FILTER_STATE, ...overrides };
}

/** Count traces that are closed polygons (the spill fill mode). */
function countSpillTraces(traces: ReturnType<typeof buildTraces>): number {
  return traces.filter((t) => (t as { fill?: string }).fill === 'toself').length;
}

// ─── Tests ──────────────────────────────────────────────────

describe('buildTraces — spill areas', () => {
  it('emits a spill trace when showSpillAreas=true and the bench has spill data', () => {
    const vm = makeViewModel({ benches: [makeSpillBench()] });
    const traces = buildTraces(vm, makeFilterState({ showSpillAreas: true }), stubCrossLink, false);

    expect(countSpillTraces(traces)).toBe(1);
    const spill = traces.find((t) => (t as { fill?: string }).fill === 'toself') as
      | { x?: number[]; y?: number[]; fillcolor?: string }
      | undefined;
    // Rectangle: x [10..15], y [3125..3145]
    expect(spill?.x).toEqual([10, 15, 15, 10]);
    expect(spill?.y).toEqual([3145, 3145, 3125, 3125]);
    expect(spill?.fillcolor).toBe('rgba(255, 100, 100, 0.3)');
  });

  it('hides spill traces when showSpillAreas=false', () => {
    const vm = makeViewModel({ benches: [makeSpillBench()] });
    const traces = buildTraces(vm, makeFilterState({ showSpillAreas: false }), stubCrossLink, false);

    expect(countSpillTraces(traces)).toBe(0);
  });

  it('skips benches without spill data', () => {
    const withSpill = makeSpillBench({ benchNumber: 1 });
    const withoutSpill = makeSpillBench({
      benchNumber: 2,
      spillWidth: null,
      spillStartDistance: null,
      spillStartElevation: null,
    });
    const vm = makeViewModel({ benches: [withSpill, withoutSpill] });
    const traces = buildTraces(vm, makeFilterState({ showSpillAreas: true }), stubCrossLink, false);

    expect(countSpillTraces(traces)).toBe(1);
  });

  it('does not crash and emits no spill traces when benches is empty', () => {
    const vm = makeViewModel({ benches: [] });
    const traces = buildTraces(vm, makeFilterState({ showSpillAreas: true }), stubCrossLink, false);

    expect(countSpillTraces(traces)).toBe(0);
    expect(traces).toEqual([]);
  });
});
