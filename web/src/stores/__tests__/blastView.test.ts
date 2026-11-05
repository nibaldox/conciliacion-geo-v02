import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createBlastViewContextKey, useBlastView } from '../blastView';

const REV_A = 'a'.repeat(64);
const REV_B = 'b'.repeat(64);
const DEFAULT_FILTERS = {
  query: '', bench: '', grid: [], polygon: [], originalBench: [], phase: [],
  depthMin: '', depthMax: '', chargeMin: '', chargeMax: '', date: '', datePresence: '',
  geometryStatus: '', provenance: '', surfaceSampleStatus: '', sectionRelation: '', corridorM: 10,
};
const DEFAULT_COLOR = { kind: 'variable', variable: 'charge', category: 'grid', palette: 'Turbo', rangeMode: 'data' };

const key1 = createBlastViewContextKey('session-1', 'design-1', 'topo-1', REV_A) as string;
const key2 = createBlastViewContextKey('session-1', 'design-1', 'topo-1', REV_B) as string;
const keySession2 = createBlastViewContextKey('session-2', 'design-1', 'topo-1', REV_A) as string;
const keyMesh2 = createBlastViewContextKey('session-1', 'design-2', 'topo-1', REV_A) as string;

beforeEach(() => {
  useBlastView.getState().reset();
});

describe('blastView store defaults and reset', () => {
  it('starts with explicit presentation defaults and no confirmation', () => {
    const state = useBlastView.getState();
    expect(state.contextKey).toBeNull();
    expect(state.confirmedSpatialContext).toBeNull();
    expect(state.filters).toEqual(DEFAULT_FILTERS);
    expect(state.colorConfig).toEqual(DEFAULT_COLOR);
    expect(state.colorTarget).toBe('both');
    expect(state.showBlastHoles).toBe(false);
    expect(state.workspaceTab).toBe('explore');
    expect(state.surveyDate).toBe('');
  });

  it('reset restores every default including context and confirmation', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.confirmSpatial(key1);
    store.setShowBlastHoles(true);
    store.setWorkspaceTab('data');
    store.setSurveyDate('2026-11-01');
    store.setColorTarget('collars');
    store.setFilters({ query: 'P-1' });
    useBlastView.getState().reset();
    const state = useBlastView.getState();
    expect(state.contextKey).toBeNull();
    expect(state.confirmedSpatialContext).toBeNull();
    expect(state.showBlastHoles).toBe(false);
    expect(state.workspaceTab).toBe('explore');
    expect(state.surveyDate).toBe('');
    expect(state.colorTarget).toBe('both');
    expect(state.filters).toEqual(DEFAULT_FILTERS);
    expect(state.colorConfig).toEqual(DEFAULT_COLOR);
  });
});

describe('createBlastViewContextKey', () => {
  it('serializes the exact context tuple with literal nullable mesh ids', () => {
    expect(createBlastViewContextKey('s', null, null, REV_A)).toBe(JSON.stringify(['s', null, null, REV_A]));
  });

  it('returns null when the revision is absent or not a 64-hex digest', () => {
    expect(createBlastViewContextKey('s', 'd', 't', null)).toBeNull();
    expect(createBlastViewContextKey('s', 'd', 't', undefined)).toBeNull();
    expect(createBlastViewContextKey('s', 'd', 't', '')).toBeNull();
    expect(createBlastViewContextKey('s', 'd', 't', 'abc')).toBeNull();
    expect(createBlastViewContextKey('s', 'd', 't', 'g'.repeat(64))).toBeNull();
  });

  it('returns null when the session is missing', () => {
    expect(createBlastViewContextKey(null, 'd', 't', REV_A)).toBeNull();
    expect(createBlastViewContextKey('', 'd', 't', REV_A)).toBeNull();
  });
});

describe('navigation preserves presentation state', () => {
  it('keeps preferences across unmount and remount-style reads within the same context', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.setFilters({ query: 'P-7', grid: ['G1'] });
    store.setColorConfig({ variable: 'powderFactorGeometry', palette: 'Viridis' });
    store.setColorTarget('trajectories');
    store.setShowBlastHoles(true);
    store.setWorkspaceTab('analysis');
    store.setSurveyDate('2026-11-02');
    const snapshot = useBlastView.getState();
    expect(useBlastView.getState()).toBe(snapshot);
    expect(snapshot.filters.query).toBe('P-7');
    expect(snapshot.colorConfig.variable).toBe('powderFactorGeometry');
    expect(snapshot.colorConfig.palette).toBe('Viridis');
    expect(snapshot.colorTarget).toBe('trajectories');
    expect(snapshot.showBlastHoles).toBe(true);
    expect(snapshot.workspaceTab).toBe('analysis');
    expect(snapshot.surveyDate).toBe('2026-11-02');
  });

  it('treats re-activating the same context as a no-op with no notification', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.setFilters({ query: 'keep' });
    store.confirmSpatial(key1);
    const before = useBlastView.getState();
    const listener = vi.fn();
    const unsubscribe = useBlastView.subscribe(listener);
    try {
      expect(store.activateContext(key1)).toBe(true);
      expect(useBlastView.getState()).toBe(before);
      expect(listener).not.toHaveBeenCalled();
      expect(useBlastView.getState().confirmedSpatialContext).toBe(key1);
      expect(useBlastView.getState().filters.query).toBe('keep');
    } finally {
      unsubscribe();
    }
  });

  it('does not notify when the same tab or survey date is set again', () => {
    useBlastView.getState().setWorkspaceTab('data');
    const before = useBlastView.getState();
    const listener = vi.fn();
    const unsubscribe = useBlastView.subscribe(listener);
    try {
      useBlastView.getState().setWorkspaceTab('data');
      useBlastView.getState().setSurveyDate('');
      expect(useBlastView.getState()).toBe(before);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });
});

describe('spatial confirmation is not transferable', () => {
  it('confirms only the exact active context', () => {
    useBlastView.getState().activateContext(key1);
    expect(useBlastView.getState().confirmSpatial(key2)).toBe(false);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
    expect(useBlastView.getState().confirmSpatial(key1)).toBe(true);
    expect(useBlastView.getState().confirmedSpatialContext).toBe(key1);
  });

  it('rejects confirmation for null without touching the current confirmation', () => {
    useBlastView.getState().activateContext(key1);
    useBlastView.getState().confirmSpatial(key1);
    expect(useBlastView.getState().confirmSpatial(null)).toBe(false);
    expect(useBlastView.getState().confirmedSpatialContext).toBe(key1);
  });

  it('clears confirmation when the session changes', () => {
    useBlastView.getState().activateContext(key1);
    useBlastView.getState().confirmSpatial(key1);
    useBlastView.getState().activateContext(keySession2);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
    expect(useBlastView.getState().confirmSpatial(key1)).toBe(false);
    expect(useBlastView.getState().confirmSpatial(keySession2)).toBe(true);
  });

  it('clears confirmation when the design mesh changes', () => {
    useBlastView.getState().activateContext(key1);
    useBlastView.getState().confirmSpatial(key1);
    useBlastView.getState().activateContext(keyMesh2);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
  });

  it('clears confirmation when the data revision changes with the same ids', () => {
    useBlastView.getState().activateContext(key1);
    useBlastView.getState().confirmSpatial(key1);
    useBlastView.getState().activateContext(key2);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
    expect(useBlastView.getState().confirmSpatial(key1)).toBe(false);
  });

  it('never authorizes a context whose revision is null or malformed in JSON', () => {
    const nullRevision = JSON.stringify(['session-1', 'design-1', 'topo-1', null]);
    const malformed = JSON.stringify(['session-1', 'design-1', 'topo-1', 'abc']);
    const store = useBlastView.getState();
    expect(store.activateContext(nullRevision)).toBe(false);
    expect(useBlastView.getState().contextKey).toBeNull();
    expect(useBlastView.getState().confirmSpatial(nullRevision)).toBe(false);
    expect(store.activateContext(malformed)).toBe(false);
    expect(useBlastView.getState().confirmSpatial(malformed)).toBe(false);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
  });

  it('rejects non-canonical or non-array context strings', () => {
    expect(useBlastView.getState().activateContext('not json')).toBe(false);
    expect(useBlastView.getState().activateContext(JSON.stringify({ a: 1 }))).toBe(false);
    expect(useBlastView.getState().contextKey).toBeNull();
  });
});

describe('null context does not break queries or visibility', () => {
  it('clears authorization but keeps showBlastHoles and workspaceTab', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.confirmSpatial(key1);
    store.setShowBlastHoles(true);
    store.setWorkspaceTab('analysis');
    expect(store.activateContext(null)).toBe(true);
    const state = useBlastView.getState();
    expect(state.contextKey).toBeNull();
    expect(state.confirmedSpatialContext).toBeNull();
    expect(state.showBlastHoles).toBe(true);
    expect(state.workspaceTab).toBe('analysis');
  });
});

describe('new source resets incompatible state', () => {
  it('resets filters and variable/category while keeping visibility, palette and tab', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.setFilters({ query: 'old', corridorM: 25 });
    store.setColorConfig({ variable: 'hardness', palette: 'Viridis', rangeMode: 'manual', rangeMin: 1, rangeMax: 9 });
    store.setShowBlastHoles(true);
    store.setWorkspaceTab('analysis');
    store.activateContext(key2);
    const state = useBlastView.getState();
    expect(state.filters).toEqual(DEFAULT_FILTERS);
    expect(state.colorConfig).toEqual({ ...DEFAULT_COLOR, palette: 'Viridis' });
    expect(state.colorConfig.rangeMin).toBeUndefined();
    expect(state.showBlastHoles).toBe(true);
    expect(state.workspaceTab).toBe('analysis');
  });
});

describe('color configuration validation', () => {
  it('accepts a valid manual range', () => {
    expect(useBlastView.getState().setColorConfig({ rangeMode: 'manual', rangeMin: 0, rangeMax: 200 })).toBe(true);
    expect(useBlastView.getState().colorConfig).toMatchObject({ rangeMode: 'manual', rangeMin: 0, rangeMax: 200 });
  });

  it('rejects manual ranges with min >= max without changing the stored config', () => {
    useBlastView.getState().setColorConfig({ variable: 'depth' });
    const before = useBlastView.getState().colorConfig;
    expect(useBlastView.getState().setColorConfig({ rangeMode: 'manual', rangeMin: 5, rangeMax: 5 })).toBe(false);
    expect(useBlastView.getState().setColorConfig({ rangeMode: 'manual', rangeMin: 9, rangeMax: 1 })).toBe(false);
    expect(useBlastView.getState().colorConfig).toBe(before);
  });

  it('rejects non-finite manual limits', () => {
    const before = useBlastView.getState().colorConfig;
    expect(useBlastView.getState().setColorConfig({ rangeMode: 'manual', rangeMin: Number.NaN, rangeMax: 3 })).toBe(false);
    expect(useBlastView.getState().setColorConfig({ rangeMode: 'manual', rangeMin: 0, rangeMax: Number.POSITIVE_INFINITY })).toBe(false);
    expect(useBlastView.getState().colorConfig).toBe(before);
  });

  it('rejects a partial limit patch that makes an existing manual range invalid', () => {
    useBlastView.getState().setColorConfig({ rangeMode: 'manual', rangeMin: 0, rangeMax: 10 });
    const before = useBlastView.getState().colorConfig;
    expect(useBlastView.getState().setColorConfig({ rangeMin: 10 })).toBe(false);
    expect(useBlastView.getState().colorConfig).toBe(before);
  });

  it('rejects an invalid colour target or workspace tab', () => {
    const before = useBlastView.getState();
    useBlastView.getState().setColorTarget('bogus' as never);
    useBlastView.getState().setWorkspaceTab('bogus' as never);
    expect(useBlastView.getState().colorTarget).toBe(before.colorTarget);
    expect(useBlastView.getState().workspaceTab).toBe(before.workspaceTab);
  });
});

describe('revoke spatial confirmation', () => {
  it('revoke-clears confirmation while keeping context, filters, palette, range, toggle and tab', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.setFilters({ query: 'P-9', grid: ['G2'] });
    store.setColorConfig({ variable: 'hardness', palette: 'Viridis', rangeMode: 'manual', rangeMin: 1, rangeMax: 9 });
    store.setShowBlastHoles(true);
    store.setWorkspaceTab('analysis');
    store.confirmSpatial(key1);
    store.clearSpatialConfirmation();
    const state = useBlastView.getState();
    expect(state.confirmedSpatialContext).toBeNull();
    expect(state.contextKey).toBe(key1);
    expect(state.filters).toMatchObject({ query: 'P-9', grid: ['G2'] });
    expect(state.colorConfig).toEqual({ kind: 'variable', variable: 'hardness', category: 'grid', palette: 'Viridis', rangeMode: 'manual', rangeMin: 1, rangeMax: 9 });
    expect(state.showBlastHoles).toBe(true);
    expect(state.workspaceTab).toBe('analysis');
  });

  it('revoke-is-idempotent and does not notify when already unconfirmed', () => {
    useBlastView.getState().activateContext(key1);
    const before = useBlastView.getState();
    const listener = vi.fn();
    const unsubscribe = useBlastView.subscribe(listener);
    try {
      useBlastView.getState().clearSpatialConfirmation();
      useBlastView.getState().clearSpatialConfirmation();
      expect(useBlastView.getState()).toBe(before);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it('revoke-then-confirm restores authorization for the same active context', () => {
    useBlastView.getState().activateContext(key1);
    useBlastView.getState().confirmSpatial(key1);
    useBlastView.getState().clearSpatialConfirmation();
    expect(useBlastView.getState().confirmSpatial(key1)).toBe(true);
    expect(useBlastView.getState().confirmedSpatialContext).toBe(key1);
  });

  it('revoke-does-not-reset-preferences when the context is later reactivated with the same key', () => {
    const store = useBlastView.getState();
    store.activateContext(key1);
    store.setFilters({ query: 'keep' });
    store.confirmSpatial(key1);
    store.clearSpatialConfirmation();
    expect(useBlastView.getState().activateContext(key1)).toBe(true);
    expect(useBlastView.getState().filters.query).toBe('keep');
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
  });
});
