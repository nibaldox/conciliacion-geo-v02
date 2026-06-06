/**
 * Tests for the pure `buildTraces` function in ProfileChart.
 *
 * We export `buildTraces` for testability — it's the core of the
 * chart: view model + filter state + cross-link → Plotly Data[].
 * The React component is mostly a wrapper, so testing this pure
 * function gives us most of the value.
 */

import { describe, it, expect } from 'vitest';
import { buildTraces, computeAxisRanges } from '../ProfileChart';
import type { ProfileViewModel } from '../../domain/types';
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

function makeBench(overrides: Partial<ProfileViewModel['benches'][number]> = {}): ProfileViewModel['benches'][number] {
  return {
    benchNumber: 1,
    crestElevation: 100,
    crestDistance: 10,
    toeElevation: 85,
    toeDistance: 20,
    height: 15,
    faceAngle: 65,
    bermWidth: 8,
    isRamp: false, designHeight: 15, designAngle: 65, designBerm: 8, heightStatus: 'UNKNOWN', angleStatus: 'UNKNOWN', bermStatus: 'UNKNOWN',
    status: 'CUMPLE',
    matched: true,
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

// ─── Tests ──────────────────────────────────────────────────

describe('buildTraces', () => {
  it('emits a design polyline when design line is present', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'design', points: [{ distance: 0, elevation: 100 }, { distance: 10, elevation: 90 }] },
      ],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const designTrace = traces.find((t) => (t as { name?: string }).name === 'Diseño');
    expect(designTrace).toBeDefined();
  });

  it('emits a topo polyline when topo line is present', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'topo', points: [{ distance: 0, elevation: 99 }, { distance: 10, elevation: 89 }] },
      ],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const topoTrace = traces.find((t) => (t as { name?: string }).name === 'Topografía');
    expect(topoTrace).toBeDefined();
  });

  it('emits reconciled polylines by default (matches Streamlit)', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'reconciled_design', points: [{ distance: 0, elevation: 100 }] },
        { kind: 'reconciled_topo', points: [{ distance: 0, elevation: 99 }] },
      ],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const names = traces.map((t) => (t as { name?: string }).name);
    expect(names).toContain('Topografía (reconciliada)');
  });

  it('does NOT emit reconciled polylines when both toggles are off', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'reconciled_design', points: [{ distance: 0, elevation: 100 }] },
        { kind: 'reconciled_topo', points: [{ distance: 0, elevation: 99 }] },
      ],
    });
    const traces = buildTraces(
      vm,
      makeFilterState({ showReconciledDesign: false, showReconciledTopo: false }),
      stubCrossLink,
      false,
    );
    const names = traces.map((t) => (t as { name?: string }).name);
    expect(names).not.toContain('Topografía (reconciliada)');
  });

  it('emits a fill trace when showAreas is on and both polylines exist', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'design', points: [{ distance: 0, elevation: 100 }, { distance: 10, elevation: 90 }] },
        { kind: 'topo', points: [{ distance: 0, elevation: 99 }, { distance: 10, elevation: 89 }] },
      ],
    });
    const traces = buildTraces(vm, makeFilterState({ showAreas: true }), stubCrossLink, false);
    const fill = traces.find((t) => (t as { name?: string }).name === 'Deuda');
    expect(fill).toBeDefined();
    expect((fill as { fill?: string }).fill).toBe('tonexty');
  });

  it('does NOT emit a fill trace when only one of design/topo is present', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'topo', points: [{ distance: 0, elevation: 99 }, { distance: 10, elevation: 89 }] },
      ],
    });
    const traces = buildTraces(vm, makeFilterState({ showAreas: true }), stubCrossLink, false);
    const fill = traces.find((t) => (t as { name?: string }).name === 'Deuda');
    expect(fill).toBeUndefined();
  });

  it('emits one bench-markers trace by default (semaphore off)', () => {
    const vm = makeViewModel({ benches: [makeBench({ benchNumber: 1, status: 'CUMPLE' })] });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const benchTraces = traces.filter((t) => (t as { name?: string }).name === 'Bancos');
    expect(benchTraces).toHaveLength(1);
  });

  it('emits one trace per status when showSemaphore is on', () => {
    const vm = makeViewModel({
      benches: [
        makeBench({ benchNumber: 1, status: 'CUMPLE' }),
        makeBench({ benchNumber: 2, status: 'FUERA' }),
        makeBench({ benchNumber: 3, status: 'NO_CUMPLE' }),
      ],
    });
    const traces = buildTraces(vm, makeFilterState({ showSemaphore: true }), stubCrossLink, false);
    const names = traces.map((t) => (t as { name?: string }).name);
    expect(names).toContain('Cumple');
    expect(names).toContain('Fuera');
    expect(names).toContain('No cumple');
  });

  it('encodes the bench number in customdata for cross-link routing', () => {
    const vm = makeViewModel({ benches: [makeBench({ benchNumber: 42, status: 'CUMPLE' })] });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as { customdata?: number[][] } | undefined;
    expect(bench?.customdata).toEqual([[42, 85, 'N/A', 'N/A']]);
  });

  it('grows the marker for the hovered bench', () => {
    const vm = makeViewModel({ benches: [makeBench({ benchNumber: 1 })] });
    const crossLink: UseCrossLinkStateApi = { ...stubCrossLink, hovered: 1 };
    const traces = buildTraces(vm, makeFilterState(), crossLink, false);
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as { marker?: { size?: number[] } } | undefined;
    expect(bench?.marker?.size).toEqual([14]);
  });

  it('grows the marker even more for the selected bench', () => {
    const vm = makeViewModel({ benches: [makeBench({ benchNumber: 1 })] });
    const crossLink: UseCrossLinkStateApi = { ...stubCrossLink, selected: 1 };
    const traces = buildTraces(vm, makeFilterState(), crossLink, false);
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as { marker?: { size?: number[] } } | undefined;
    expect(bench?.marker?.size).toEqual([16]);
  });

  it('handles an empty view model (no lines, no benches)', () => {
    const traces = buildTraces(makeViewModel(), makeFilterState(), stubCrossLink, false);
    expect(traces).toEqual([]);
  });
});

describe('computeAxisRanges', () => {
  it('returns tight x and y ranges with 8% padding by default', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'design', points: [
          { distance: 0, elevation: 100 },
          { distance: 100, elevation: 80 },
        ] },
      ],
      benches: [makeBench({ crestDistance: 50, toeDistance: 70, crestElevation: 90, toeElevation: 85 })],
    });
    const { xRange, yRange } = computeAxisRanges(vm, 480);
    // x: data 0-100, +8% padding on each side = -8 to 108
    expect(xRange[0]).toBeCloseTo(-8, 5);
    expect(xRange[1]).toBeCloseTo(108, 5);
    // y: data 80-100, span 20. Mid 90, ±10. + 8% padding.
    expect(yRange[0]).toBeLessThanOrEqual(80);
    expect(yRange[1]).toBeGreaterThanOrEqual(100);
  });

  it('enforces a minimum y-axis span of 20m so flat benches are visible', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'design', points: [
          { distance: 0, elevation: 100 },
          { distance: 50, elevation: 101 },
        ] },
      ],
    });
    const { yRange } = computeAxisRanges(vm, 480);
    expect(yRange[1] - yRange[0]).toBeGreaterThanOrEqual(20);
  });

  it('falls back to a sensible default when there is no data', () => {
    const vm = makeViewModel();
    const { xRange, yRange } = computeAxisRanges(vm, 480);
    expect(xRange[1] - xRange[0]).toBeGreaterThan(0);
    expect(yRange[1] - yRange[0]).toBeGreaterThan(0);
  });

  it('honors a custom padding percentage', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'design', points: [
          { distance: 0, elevation: 100 },
          { distance: 100, elevation: 80 },
        ] },
      ],
    });
    const { xRange } = computeAxisRanges(vm, 480, 0.25);
    // 25% padding on each side → -25 to 125
    expect(xRange[0]).toBeCloseTo(-25, 5);
    expect(xRange[1]).toBeCloseTo(125, 5);
  });
});
