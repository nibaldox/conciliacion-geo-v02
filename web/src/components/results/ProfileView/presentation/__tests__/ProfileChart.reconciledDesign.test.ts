/**
 * Tests for the `reconciled_design` trace in ProfileChart.
 *
 * Regression coverage for the G01 fix: `buildTraces` previously skipped
 * the `reconciled_design` line (the comment literally said "no dashed
 * reconciled design"). It now emits a dashed royalblue polyline that
 * mirrors Streamlit's `go.Scatter(line=dict(color='royalblue', dash='dash'))`.
 */

import { describe, it, expect } from 'vitest';
import { buildTraces } from '../ProfileChart';
import type { ProfileViewModel, ProfileLine } from '../../domain/types';
import type { FilterState } from '../../domain/filters';
import { DEFAULT_FILTER_STATE } from '../../domain/filters';
import type { UseCrossLinkStateApi } from '../../application';

// ─── Fixtures ───────────────────────────────────────────────

function makeViewModel(lines: readonly ProfileLine[]): ProfileViewModel {
  return {
    section: {
      id: 'sec-1',
      name: 'S-001',
      sector: 'Norte',
      azimuth: 45,
      length: 200,
      origin: [0, 0],
    },
    lines,
    benches: [],
  };
}

function makeFilterState(overrides: Partial<FilterState> = {}): FilterState {
  return { ...DEFAULT_FILTER_STATE, ...overrides };
}

const stubCrossLink: UseCrossLinkStateApi = {
  hovered: null,
  selected: null,
  setHovered: () => {},
  setSelected: () => {},
  clear: () => {},
};

type TraceLine = { color?: string; dash?: string; width?: number };
type NamedTrace = { name?: string; line?: TraceLine };

function findTrace(traces: readonly NamedTrace[], name: string): NamedTrace | undefined {
  return traces.find((t) => t.name === name);
}

const RECONCILED_DESIGN_POINTS: readonly { distance: number; elevation: number }[] = [
  { distance: 0, elevation: 3140 },
  { distance: 10, elevation: 3140 },
];

// ─── Tests ──────────────────────────────────────────────────

describe('buildTraces — reconciled_design', () => {
  it('emits a dashed royalblue trace when showReconciledDesign=true and data is present', () => {
    const vm = makeViewModel([
      { kind: 'reconciled_design', points: RECONCILED_DESIGN_POINTS },
    ]);
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);

    const trace = findTrace(traces as unknown as readonly NamedTrace[], 'Diseño (reconciliado)');
    expect(trace).toBeDefined();
    expect(trace?.line?.color).toBe('royalblue');
    expect(trace?.line?.dash).toBe('dash');
  });

  it('hides the reconciled_design trace when showReconciledDesign=false', () => {
    const vm = makeViewModel([
      { kind: 'reconciled_design', points: RECONCILED_DESIGN_POINTS },
    ]);
    const traces = buildTraces(
      vm,
      makeFilterState({ showReconciledDesign: false }),
      stubCrossLink,
      false,
    );

    const trace = findTrace(traces as unknown as readonly NamedTrace[], 'Diseño (reconciliado)');
    expect(trace).toBeUndefined();
  });

  it('does not crash and emits no trace when reconciled_design data is absent', () => {
    const vm = makeViewModel([
      { kind: 'design', points: RECONCILED_DESIGN_POINTS },
    ]);
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);

    const trace = findTrace(traces as unknown as readonly NamedTrace[], 'Diseño (reconciliado)');
    expect(trace).toBeUndefined();
  });

  it('still renders reconciled_topo (solid amber) as a regression guard', () => {
    const vm = makeViewModel([
      { kind: 'reconciled_design', points: RECONCILED_DESIGN_POINTS },
      { kind: 'reconciled_topo', points: RECONCILED_DESIGN_POINTS },
    ]);
    const traces = buildTraces(vm, makeFilterState(), stubCrossLink, false);

    const topo = findTrace(traces as unknown as readonly NamedTrace[], 'Topografía (reconciliada)');
    expect(topo).toBeDefined();
    expect(topo?.line?.color).toBe('#f59e0b');
    expect(topo?.line?.dash).toBeUndefined();
  });
});
