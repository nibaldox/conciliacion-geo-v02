import { create } from 'zustand';
import type { BlastHoleFilterState } from '../components/mesh/BlastHoleFilters';
import type { BlastHoleCategory, BlastHoleColorScale, BlastHoleRangeMode, BlastHoleVariable } from '../components/mesh/blastHoleColors';

export interface BlastViewColorConfig {
  kind: 'variable' | 'category';
  variable: BlastHoleVariable;
  category: BlastHoleCategory;
  palette: BlastHoleColorScale;
  rangeMode: BlastHoleRangeMode;
  rangeMin?: number;
  rangeMax?: number;
}

export type BlastWorkspaceTab = 'explore' | 'analysis' | 'simulation' | 'data';
export type BlastColorTarget = 'both' | 'collars' | 'trajectories';

const WORKSPACE_TABS: readonly BlastWorkspaceTab[] = ['explore', 'analysis', 'simulation', 'data'];
const COLOR_TARGETS: readonly BlastColorTarget[] = ['both', 'collars', 'trajectories'];
const RANGE_MODES: readonly BlastHoleRangeMode[] = ['legacy', 'data', 'manual'];
const COLOR_KINDS: readonly BlastViewColorConfig['kind'][] = ['variable', 'category'];
const REVISION_PATTERN = /^[0-9a-f]{64}$/;

interface BlastViewState {
  contextKey: string | null;
  filters: BlastHoleFilterState;
  colorConfig: BlastViewColorConfig;
  colorTarget: BlastColorTarget;
  showBlastHoles: boolean;
  confirmedSpatialContext: string | null;
  workspaceTab: BlastWorkspaceTab;
  surveyDate: string;
  activateContext: (contextKey: string | null) => boolean;
  setFilters: (partial: Partial<BlastHoleFilterState>) => void;
  setColorConfig: (partial: Partial<BlastViewColorConfig>) => boolean;
  setColorTarget: (target: BlastColorTarget) => void;
  setShowBlastHoles: (value: boolean) => void;
  confirmSpatial: (contextKey: string | null) => boolean;
  clearSpatialConfirmation: () => void;
  setWorkspaceTab: (tab: BlastWorkspaceTab) => void;
  setSurveyDate: (value: string) => void;
  reset: () => void;
}

type PresentationFields = Pick<
  BlastViewState,
  | 'contextKey'
  | 'filters'
  | 'colorConfig'
  | 'colorTarget'
  | 'showBlastHoles'
  | 'confirmedSpatialContext'
  | 'workspaceTab'
  | 'surveyDate'
>;

function defaultFilters(): BlastHoleFilterState {
  return {
    query: '',
    bench: '',
    grid: [],
    polygon: [],
    originalBench: [],
    phase: [],
    depthMin: '',
    depthMax: '',
    chargeMin: '',
    chargeMax: '',
    date: '',
    datePresence: '',
    geometryStatus: '',
    provenance: '',
    surfaceSampleStatus: '',
    sectionRelation: '',
    corridorM: 10,
  };
}

function defaultColorConfig(): BlastViewColorConfig {
  return {
    kind: 'variable',
    variable: 'charge',
    category: 'grid',
    palette: 'Turbo',
    rangeMode: 'data',
  };
}

function defaultPresentation(): PresentationFields {
  return {
    contextKey: null,
    filters: defaultFilters(),
    colorConfig: defaultColorConfig(),
    colorTarget: 'both',
    showBlastHoles: false,
    confirmedSpatialContext: null,
    workspaceTab: 'explore',
    surveyDate: '',
  };
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function parseContextKey(contextKey: string): unknown[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(contextKey);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed) || parsed.length !== 4) return null;
  const [sessionId, designMeshId, topoMeshId, dataRevision] = parsed;
  if (typeof sessionId !== 'string' || sessionId.length === 0) return null;
  if (!isNullableString(designMeshId) || !isNullableString(topoMeshId)) return null;
  if (typeof dataRevision !== 'string' || !REVISION_PATTERN.test(dataRevision)) return null;
  if (JSON.stringify(parsed) !== contextKey) return null;
  return parsed;
}

function isValidContextKey(contextKey: string | null): contextKey is string {
  return typeof contextKey === 'string' && parseContextKey(contextKey) !== null;
}

function valueEquals(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  return a.every((item, index) => Object.is(item, b[index]));
}

function patchChanges<T extends object>(current: T, partial: Partial<T>): boolean {
  return (Object.keys(partial) as Array<keyof T>).some((key) => !valueEquals(current[key], partial[key]));
}

function isFiniteRange(min: number | undefined, max: number | undefined): boolean {
  return typeof min === 'number' && typeof max === 'number'
    && Number.isFinite(min) && Number.isFinite(max) && min < max;
}

export function createBlastViewContextKey(
  sessionId: string | null,
  designMeshId: string | null,
  topoMeshId: string | null,
  dataRevision: string | null | undefined,
): string | null {
  if (typeof sessionId !== 'string' || sessionId.length === 0) return null;
  if (typeof dataRevision !== 'string' || !REVISION_PATTERN.test(dataRevision)) return null;
  return JSON.stringify([sessionId, designMeshId, topoMeshId, dataRevision]);
}

export const useBlastView = create<BlastViewState>()((set, get) => ({
  ...defaultPresentation(),

  activateContext: (contextKey) => {
    if (contextKey === null) {
      const current = get();
      if (current.contextKey === null && current.confirmedSpatialContext === null) return true;
      set({ contextKey: null, confirmedSpatialContext: null });
      return true;
    }
    if (!isValidContextKey(contextKey)) return false;
    const current = get();
    if (current.contextKey === contextKey) return true;
    const reset = defaultPresentation();
    set({
      contextKey,
      confirmedSpatialContext: null,
      filters: reset.filters,
      colorConfig: { ...reset.colorConfig, palette: current.colorConfig.palette },
    });
    return true;
  },

  setFilters: (partial) => {
    const current = get();
    if (!patchChanges(current.filters, partial)) return;
    set({ filters: { ...current.filters, ...partial } });
  },

  setColorConfig: (partial) => {
    const current = get();
    if (!patchChanges(current.colorConfig, partial)) return true;
    const next = { ...current.colorConfig, ...partial };
    if (!COLOR_KINDS.includes(next.kind) || !RANGE_MODES.includes(next.rangeMode)) return false;
    if (next.rangeMode === 'manual' && !isFiniteRange(next.rangeMin, next.rangeMax)) return false;
    set({ colorConfig: next });
    return true;
  },

  setColorTarget: (target) => {
    if (!COLOR_TARGETS.includes(target) || get().colorTarget === target) return;
    set({ colorTarget: target });
  },

  setShowBlastHoles: (value) => {
    if (get().showBlastHoles === value) return;
    set({ showBlastHoles: value });
  },

  confirmSpatial: (contextKey) => {
    const current = get();
    if (contextKey === null || contextKey !== current.contextKey) return false;
    if (current.confirmedSpatialContext === contextKey) return true;
    set({ confirmedSpatialContext: contextKey });
    return true;
  },

  clearSpatialConfirmation: () => {
    if (get().confirmedSpatialContext === null) return;
    set({ confirmedSpatialContext: null });
  },

  setWorkspaceTab: (tab) => {
    if (!WORKSPACE_TABS.includes(tab) || get().workspaceTab === tab) return;
    set({ workspaceTab: tab });
  },

  setSurveyDate: (value) => {
    if (get().surveyDate === value) return;
    set({ surveyDate: value });
  },

  reset: () => set(defaultPresentation()),
}));
