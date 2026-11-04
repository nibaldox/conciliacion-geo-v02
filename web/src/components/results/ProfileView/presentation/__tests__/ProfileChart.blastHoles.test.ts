/**
 * Tests for the blast-hole markers trace emitted by `buildTraces`.
 *
 * Regression coverage for the G03b parity gap: the
 * "Mostrar Pozos de Tronadura" toggle and `blastTolerance` filter
 * existed in the UI but `buildTraces` ignored them. Now the
 * (optional) `blastHoles` parameter drives a single diamond-marker
 * trace, coloured green when the hole is within tolerance and red
 * otherwise. Undefined / empty inputs must stay silent.
 */

import { describe, it, expect } from 'vitest';
import { buildTraces } from '../ProfileChart';
import type { ProfileViewModel } from '../../domain/types';
import type { FilterState } from '../../domain/filters';
import { DEFAULT_FILTER_STATE } from '../../domain/filters';
import type { UseCrossLinkStateApi } from '../../application';
import type { BlastHoleOnProfile } from '../../../../../api/types';

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

function makeBlastHole(overrides: Partial<BlastHoleOnProfile> & { row_id?: string | null } = {}): BlastHoleOnProfile {
  return {
    hole_id: 'P-001',
    distance: 10,
    elevation: 3140,
    burden: 3.5,
    spacing: 4.0,
    is_within_tolerance: true,
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

type MarkerTrace = {
  name?: string;
  type?: string;
  mode?: string;
  x?: number[];
  y?: number[];
  marker?: { color?: string | string[]; size?: number | number[]; symbol?: string; line?: { color?: string | string[]; width?: number } };
  text?: string[];
  customdata?: unknown[][];
  hovertemplate?: string;
  meta?: { profileViewRole?: string; profilePointKind?: string };
};

function findBlastTrace(traces: ReturnType<typeof buildTraces>): MarkerTrace | undefined {
  return traces.find((t) => (t as MarkerTrace).meta?.profilePointKind === 'projected_collar') as
    | MarkerTrace
    | undefined;
}

function findIntersectionTrace(traces: ReturnType<typeof buildTraces>): MarkerTrace | undefined {
  return traces.find((t) => (t as MarkerTrace).meta?.profilePointKind === 'intersection') as MarkerTrace | undefined;
}

// ─── Tests ──────────────────────────────────────────────────

describe('buildTraces — blast holes', () => {
  it('emits a single markers trace with one diamond per hole, coloured by tolerance', () => {
    const vm = makeViewModel();
    const blastHoles: BlastHoleOnProfile[] = [
      makeBlastHole({ hole_id: 'P-1', distance: 5, elevation: 3140, is_within_tolerance: true }),
      makeBlastHole({ hole_id: 'P-2', distance: 10, elevation: 3135, is_within_tolerance: false }),
      makeBlastHole({ hole_id: 'P-3', distance: 15, elevation: 3150, is_within_tolerance: true }),
    ];

    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false, blastHoles);

    const trace = findBlastTrace(traces);
    expect(trace).toBeDefined();
    expect(trace?.type).toBe('scatter');
    expect(trace?.mode).toBe('markers');
    // One point per hole, in order.
    expect(trace?.x).toEqual([5, 10, 15]);
    expect(trace?.y).toEqual([3140, 3135, 3150]);
    // Per-hole colour: green for within tolerance, red otherwise.
    expect(trace?.marker?.color).toEqual(['#22c55e', '#ef4444', '#22c55e']);
    expect(trace?.marker?.size).toBe(8);
    expect(trace?.marker?.symbol).toBe('diamond');
    // customdata carries [burden, spacing] for the hovertemplate.
    expect(trace?.customdata).toEqual([
      [3.5, 4.0, 'Collar proyectado'],
      [3.5, 4.0, 'Collar proyectado'],
      [3.5, 4.0, 'Collar proyectado'],
    ]);
    expect(trace?.text).toEqual(['Pozo P-1', 'Pozo P-2', 'Pozo P-3']);
  });

  it('emits no markers trace when blastHoles is an empty array', () => {
    const vm = makeViewModel();
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false, []);

    expect(findBlastTrace(traces)).toBeUndefined();
  });

  it('emits no markers trace and does not crash when blastHoles is undefined', () => {
    const vm = makeViewModel();
    // Explicitly pass undefined to verify the optional-parameter guard.
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false, undefined);

    expect(findBlastTrace(traces)).toBeUndefined();
    // Sanity: existing traces (none in this empty vm) are still returned
    // without throwing.
    expect(traces).toEqual([]);
  });

  it('keeps emitting other traces (bench markers) alongside blast holes', () => {
    // Regression guard: adding the blastHoles parameter must not
    // suppress the bench-marker trace path.
    const vm = makeViewModel({
      benches: [
        {
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
        },
      ],
    });
    const blastHoles: BlastHoleOnProfile[] = [
      makeBlastHole({ hole_id: 'P-1', is_within_tolerance: true }),
    ];

    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false, blastHoles);

    // Both the bench trace (named "Bancos" in the non-semaphore path)
    // and the blast-hole trace must be present.
    const benchTrace = traces.find((t) => (t as MarkerTrace).name === 'Bancos');
    expect(benchTrace).toBeDefined();
    expect(findBlastTrace(traces)).toBeDefined();
  });

  it('highlights only the matching row_id when hole IDs are duplicated', () => {
    const holes = [
      makeBlastHole({ hole_id: 'DUP', row_id: 'row-a', distance: 5 }),
      makeBlastHole({ hole_id: 'DUP', row_id: 'row-b', distance: 10, is_within_tolerance: false }),
    ] as BlastHoleOnProfile[];

    const trace = findBlastTrace(buildTraces(makeViewModel(), makeFilterState(), stubCrossLink, false, holes,
      undefined, undefined, undefined, 'row-b'));

    expect(trace?.marker?.color).toEqual(['#22c55e', '#fde047']);
    expect(trace?.marker?.size).toEqual([8, 13]);
    expect(trace?.marker?.line?.color).toEqual(['rgba(0,0,0,0)', '#7c2d12']);
  });

  it('does not highlight a matching hole_id when row_id is missing', () => {
    const holes = [makeBlastHole({ hole_id: 'DUP', distance: 5 })];
    const trace = findBlastTrace(buildTraces(makeViewModel(), makeFilterState(), stubCrossLink, false, holes,
      undefined, undefined, undefined, 'row-a'));

    expect(trace?.marker?.color).toEqual(['#22c55e']);
    expect(trace?.marker?.size).toBe(8);
  });

  it('separates projected collars and intersections in legend and hover, highlighting by row_id', () => {
    const holes = [
      makeBlastHole({ hole_id: 'DUP', row_id: 'row-collar' }),
      makeBlastHole({ hole_id: 'DUP', row_id: 'row-cross', profile_point_kind: 'intersection', distance: 25 }),
    ];
    const traces = buildTraces(makeViewModel(), makeFilterState(), stubCrossLink, false, holes,
      undefined, undefined, undefined, 'row-cross');
    const collarTrace = findBlastTrace(traces);
    const intersectionTrace = findIntersectionTrace(traces);

    expect(collarTrace?.name).toBe('Collares de pozos proyectados');
    expect(collarTrace?.customdata?.[0]?.[2]).toBe('Collar proyectado');
    expect(intersectionTrace?.name).toBe('Intersecciones pozo-sección');
    expect(intersectionTrace?.hovertemplate).toContain('Tipo de punto=%{customdata[2]}');
    expect(intersectionTrace?.marker?.size).toEqual([13]);
    expect(intersectionTrace?.customdata?.[0]?.[2]).toBe('Intersección segmento-sección');
  });

  it('keeps legacy records without profile_point_kind in the projected-collar trace', () => {
    const trace = findBlastTrace(buildTraces(makeViewModel(), makeFilterState(), stubCrossLink, false,
      [makeBlastHole({ row_id: 'legacy-row' })]));

    expect(trace?.name).toBe('Collares de pozos proyectados');
    expect(findIntersectionTrace(buildTraces(makeViewModel(), makeFilterState(), stubCrossLink, false,
      [makeBlastHole({ row_id: 'legacy-row' })]))).toBeUndefined();
  });
});
