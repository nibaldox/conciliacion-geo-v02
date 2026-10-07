/**
 * Tests for the pure `buildTraces` function in ProfileChart.
 *
 * We export `buildTraces` for testability — it's the core of the
 * chart: view model + filter state + cross-link → Plotly Data[].
 * The React component is mostly a wrapper, so testing this pure
 * function gives us most of the value.
 */

import { describe, it, expect } from 'vitest';
import {
  buildHorizontalDeviationSampleAnnotations,
  buildHorizontalDeviationSampleTraces,
  buildTraces,
  computeAxisRanges,
  getBenchNumberFromPlotEvent,
  getBenchNumberFromPointerGlyph,
} from '../ProfileChart';
import type { Data } from 'plotly.js';
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
    deltaCrest: null,
    deltaToe: null,
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
    const terrain = traces.find((t) => (t as { name?: string }).name === 'Terreno') as {
      hoverinfo?: string;
      hovertemplate?: string;
    } | undefined;
    expect(topoTrace).toBeDefined();
    expect(terrain?.hoverinfo).toBe('skip');
    expect(terrain?.hovertemplate).toBeUndefined();
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
    expect((fill as { hoverinfo?: string }).hoverinfo).toBe('skip');
    expect((fill as { hovertemplate?: string }).hovertemplate).toBeUndefined();
    const overexcavation = traces.find((t) => (t as { name?: string }).name === 'Sobrexcavación');
    expect((overexcavation as { hovertemplate?: string } | undefined)?.hovertemplate).toBeUndefined();
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
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as { customdata?: unknown[][] } | undefined;
    expect(bench?.customdata).toEqual([[42, 85, 'N/A', 'N/A', '65.0°', '65.0°', '8.0 m', '8.0 m']]);
  });

  it('shows actual and planned angle and berm values in the hover popup', () => {
    const vm = makeViewModel({ benches: [makeBench({ faceAngle: 63.27, designAngle: 70, bermWidth: 4, designBerm: 6.5 })] });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as {
      customdata?: unknown[][];
      hovertemplate?: string | string[];
    } | undefined;

    expect(bench?.customdata?.[0]).toEqual([1, 85, 'N/A', 'N/A', '63.3°', '70.0°', '4.0 m', '6.5 m']);
    expect(bench?.hovertemplate?.toString()).toContain('Ángulo real: %{customdata[4]}');
    expect(bench?.hovertemplate?.toString()).toContain('Ángulo planificado: %{customdata[5]}');
    expect(bench?.hovertemplate?.toString()).toContain('Berma real: %{customdata[6]}');
    expect(bench?.hovertemplate?.toString()).toContain('Berma planificada: %{customdata[7]}');
  });

  it('explains unmatched benches in the hover and omits the explanation for matched benches', () => {
    const vm = makeViewModel({ benches: [
      makeBench({ benchNumber: 1, matched: true }),
      makeBench({ benchNumber: 2, matched: false, designAngle: null, designBerm: null }),
    ] });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as {
      hovertemplate?: string | string[];
    } | undefined;
    const templates = Array.isArray(bench?.hovertemplate)
      ? bench.hovertemplate
      : [bench?.hovertemplate ?? ''];

    expect(templates[0]).not.toContain('Sin banco de diseño asociado');
    expect(templates[1]).toContain('Sin banco de diseño asociado');
  });

  it('shows a dash for unavailable angle and berm measurements', () => {
    const vm = makeViewModel({ benches: [makeBench({ faceAngle: Number.NaN, designAngle: null, bermWidth: null, designBerm: null })] });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const bench = traces.find((t) => (t as { name?: string }).name === 'Bancos') as { customdata?: unknown[][] } | undefined;

    expect(bench?.customdata?.[0]?.slice(4)).toEqual(['—', '—', '—', '—']);
  });

  it('identifies visible topographic points only when exactly one bench contains them', () => {
    const vm = makeViewModel({
      lines: [{
        kind: 'topo',
        points: [
          { distance: 0, elevation: 100 },
          { distance: 10, elevation: 97 },
          { distance: 15, elevation: 92 },
          { distance: 20, elevation: 85 },
          { distance: 25, elevation: 80 },
        ],
      }],
      benches: [makeBench({ benchNumber: 42, crestDistance: 10, toeDistance: 20 })],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const topo = traces.find((trace) => (trace as { name?: string }).name === 'Topografía') as {
      meta?: { profileViewRole?: string };
      customdata?: unknown[][];
      x?: number[];
      y?: number[];
      text?: string[];
      hovertemplate?: string[];
    } | undefined;

    expect(topo?.meta?.profileViewRole).toBe('bench-face');
    expect(topo?.x).toEqual([0, 10, 15, 20, 25]);
    expect(topo?.y).toEqual([100, 97, 92, 85, 80]);
    expect(topo?.customdata).toEqual([
      [],
      [42, 85, 'N/A', 'N/A', '65.0°', '65.0°', '8.0 m', '8.0 m'],
      [42, 85, 'N/A', 'N/A', '65.0°', '65.0°', '8.0 m', '8.0 m'],
      [42, 85, 'N/A', 'N/A', '65.0°', '65.0°', '8.0 m', '8.0 m'],
      [],
    ]);
    expect(topo?.text?.[1]).toContain('42');
    expect(topo?.hovertemplate?.[0]).toContain('%{x:.1f} m, %{y:.1f} m');
    expect(topo?.hovertemplate?.[2]).toContain('Ángulo real: %{customdata[4]}');
    expect(topo?.hovertemplate?.[2]).toContain('Ángulo planificado: %{customdata[5]}');
    expect(topo?.hovertemplate?.[2]).toContain('Berma real: %{customdata[6]}');
    expect(topo?.hovertemplate?.[2]).toContain('Berma planificada: %{customdata[7]}');
  });

  it('ignores generic lines, overlapping bank boundaries, and ambiguous multi-bank events', () => {
    const vm = makeViewModel({
      lines: [
        { kind: 'design', points: [{ distance: 0, elevation: 101 }, { distance: 20, elevation: 76 }] },
        { kind: 'topo', points: [
          { distance: 0, elevation: 100 }, { distance: 10, elevation: 85 },
          { distance: 15, elevation: 90 }, { distance: 20, elevation: 75 },
        ] },
      ],
      benches: [
        makeBench({ benchNumber: 7, crestDistance: 0, toeDistance: 10 }),
        makeBench({ benchNumber: 8, crestDistance: 10, toeDistance: 20 }),
      ],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const topoIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Topografía');
    const designIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Diseño');
    const topo = traces[topoIndex] as { customdata?: unknown[][] };

    expect(topo.customdata?.[1]).toEqual([]);
    expect(getBenchNumberFromPlotEvent({ points: [{ curveNumber: topoIndex, customdata: topo.customdata?.[1] }] }, traces)).toBeNull();
    expect(getBenchNumberFromPlotEvent({ points: [{ curveNumber: designIndex, customdata: [7] }] }, traces)).toBeNull();
    expect(getBenchNumberFromPlotEvent({ points: [
      { curveNumber: topoIndex, customdata: [7, 85, 'N/A', 'N/A', '65.0°', '65.0°', '8.0 m', '8.0 m'] },
      { curveNumber: topoIndex, customdata: [8, 85, 'N/A', 'N/A', '65.0°', '65.0°', '8.0 m', '8.0 m'] },
    ] }, traces)).toBeNull();
  });

  it('prefers a clicked bench marker over an overlapping topographic face hit from another bench', () => {
    const vm = makeViewModel({
      lines: [{ kind: 'topo', points: [
        { distance: 0, elevation: 100 }, { distance: 10, elevation: 85 },
        { distance: 15, elevation: 90 }, { distance: 20, elevation: 75 },
      ] }],
      benches: [
        makeBench({ benchNumber: 7, crestDistance: 0, toeDistance: 10 }),
        makeBench({ benchNumber: 8, crestDistance: 10, toeDistance: 20 }),
      ],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const topoIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Topografía');
    const topo = traces[topoIndex] as { customdata?: unknown[][] };
    const markerIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Bancos');
    const marker = traces[markerIndex] as { customdata?: unknown[][] };

    expect(getBenchNumberFromPlotEvent({ points: [
      { curveNumber: topoIndex, customdata: topo.customdata?.[2] },
      { curveNumber: markerIndex, customdata: marker.customdata?.[1] },
    ] }, traces)).toBe(8);
  });

  it('selects only a unique marker glyph under an unresolved horizontal-deviation hit', () => {
    const traces = [
      { type: 'scatter', meta: { profileViewRole: 'bench-face', horizontalDeviation: true } },
      { type: 'scatter', meta: { profileViewRole: 'bench-marker' } },
    ] as Data[];
    const event = {
      event: { clientX: 20, clientY: 30 } as MouseEvent,
      points: [{ curveNumber: 0, customdata: [] }],
    };
    const marker = { benchNumber: 7, centerX: 20, centerY: 30, radius: 5 };

    expect(getBenchNumberFromPointerGlyph(event, traces, [marker])).toBe(7);
    expect(getBenchNumberFromPointerGlyph(event, traces, [marker, { ...marker, benchNumber: 8 }])).toBeNull();
    expect(getBenchNumberFromPointerGlyph({ ...event, event: { clientX: 26, clientY: 30 } as MouseEvent }, traces, [marker])).toBeNull();

    const genericTraces = [{ ...traces[0], meta: { profileViewRole: 'bench-face' } }, traces[1]] as Data[];
    expect(getBenchNumberFromPointerGlyph(event, genericTraces, [marker])).toBeNull();
    const blastTraces = [{ type: 'scatter', meta: { profileViewRole: 'blast-hole' } }, traces[1]] as Data[];
    expect(getBenchNumberFromPointerGlyph({ ...event, points: [{ curveNumber: 0, customdata: [7] }] }, blastTraces, [marker])).toBeNull();
  });

  it('selects an identified point among other trace hits and ignores blast-hole measurements', () => {
    const vm = makeViewModel({
      lines: [{ kind: 'topo', points: [{ distance: 0, elevation: 100 }, { distance: 10, elevation: 85 }] }],
      benches: [makeBench({ benchNumber: 7, crestDistance: 0, toeDistance: 10 })],
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false, [{
      hole_id: 'H1', distance: 5, elevation: 92, burden: 7, spacing: 8, is_within_tolerance: true,
    }]);
    const topoIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Topografía');
    const topo = traces[topoIndex] as { customdata?: unknown[][] };
    const markerIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Bancos');
    const holeIndex = traces.findIndex((trace) => (trace as { name?: string }).name === 'Pozos de tronadura');

    expect(getBenchNumberFromPlotEvent({ points: [
      { curveNumber: topoIndex, customdata: topo.customdata?.[1] },
      { curveNumber: markerIndex, customdata: [7, 85] },
    ] }, traces)).toBe(7);
    expect(getBenchNumberFromPlotEvent({ points: [
      { curveNumber: topoIndex, customdata: topo.customdata?.[1] },
      { curveNumber: holeIndex, customdata: [7, 8] },
    ] }, traces)).toBeNull();
    expect(getBenchNumberFromPlotEvent({ points: [
      { curveNumber: holeIndex, customdata: [7, 8] },
    ] }, traces)).toBeNull();
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

describe('horizontal deviation profile overlay', () => {
  it('colors raw topo points by dH category and preserves unique bench click routing', () => {
    const vm = makeViewModel({
      lines: [{ kind: 'topo', points: [
        { distance: 10, elevation: 95 },
        { distance: 15, elevation: 90 },
        { distance: 20, elevation: 85 },
      ] }],
      benches: [makeBench({ benchNumber: 42, crestDistance: 10, toeDistance: 20 })],
      horizontalDeviation: {
        unit: 'm',
        method: 'horizontal_at_equal_elevation',
        direction: 'positive_overbreak_negative_underbreak',
        thresholds: { within: 1, moderate: 1.8, severe: 3 },
        points: [
          { distance: 10, elevation: 95, deviation: -1.2, category: 'underbreak_minor', design_bench_num: 200, status: 'measured' },
          { distance: 15, elevation: 90, deviation: 2.2, category: 'overbreak_moderate', design_bench_num: 201, status: 'measured' },
          { distance: 20, elevation: 85, deviation: null, category: 'unmeasured', design_bench_num: null, status: 'missing' },
        ],
        samples: [],
        summary: { measured: 2, total: 3, within_percent: 0, max_abs_deviation: 2.2 },
        warnings: [],
      },
    });
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);
    const overlays = traces.filter((trace) => (trace.meta as { horizontalDeviation?: boolean } | undefined)?.horizontalDeviation);
    const overlayIndex = traces.findIndex((trace) => (trace.meta as { horizontalDeviation?: boolean } | undefined)?.horizontalDeviation);

    expect(overlays).toHaveLength(3);
    expect(String((overlays[0] as { hovertemplate?: string | string[] } | undefined)?.hovertemplate))
      .toContain('Banco de diseño 200');
    expect(getBenchNumberFromPlotEvent({ points: [{ curveNumber: overlayIndex, customdata: [42] }] }, traces)).toBe(42);
  });

  it('shows sample connectors and actual heights while safely skipping null elevations', () => {
    const vm = makeViewModel({
      horizontalDeviation: {
        unit: 'm',
        method: 'horizontal_at_equal_elevation',
        direction: 'positive_overbreak_negative_underbreak',
        thresholds: { within: 1, moderate: 1.8, severe: 3 },
        points: [],
        samples: [
          {
            design_bench_num: 7, height_above_toe: 3.5, toe_elevation: 86.5,
            elevation: 90, reference_elevation: 90, design_distance: 12, topo_distance: 14,
            deviation: 2.2, category: 'overbreak_moderate', status: 'measured',
          },
          {
            design_bench_num: 8, height_above_toe: null, toe_elevation: null,
            elevation: null, reference_elevation: null, design_distance: null, topo_distance: null,
            deviation: null, category: 'unmeasured', status: 'missing',
          },
          {
            design_bench_num: 9, height_above_toe: null, toe_elevation: 80,
            elevation: 82, reference_elevation: 82, design_distance: 22, topo_distance: null,
            deviation: null, category: 'unmeasured', status: 'missing',
          },
        ],
        summary: { measured: 1, total: 3, within_percent: 0, max_abs_deviation: 2.2 },
        warnings: [],
      },
    });
    const traces = buildHorizontalDeviationSampleTraces(vm);
    const annotations = buildHorizontalDeviationSampleAnnotations(vm);

    expect(traces).toHaveLength(1);
    expect(traces[0]?.x).toEqual([12, 14]);
    expect(traces[0]?.y).toEqual([90, 90]);
    expect(traces[0]?.hovertemplate).toContain('h desde pata 3.5 m');
    expect(traces[0]?.hovertemplate).toContain('Pata de diseño: 86.5 m');
    expect(annotations).toHaveLength(2);
    expect(annotations[0]?.text).toContain('D7');
    expect(annotations[0]?.text).toContain('3.5 m');
    expect(annotations[0]?.text).not.toContain('%');
    expect(annotations[0]?.font?.size).toBeGreaterThanOrEqual(10);
    expect(annotations[0]?.x).toBe(14);
    expect(annotations[0]?.xanchor).toBe('left');
    expect(annotations[0]?.yanchor).toBe('middle');
    expect(annotations[0]?.xshift).toBe(8);
    expect(annotations[0]?.yshift).toBe(0);
    expect(annotations[0]?.bgcolor).toBeTruthy();
    expect(annotations[0]?.borderpad).toBe(3);
    expect(annotations[1]?.text).toContain('D9');
    expect(annotations[1]?.text).toContain('h —');
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
