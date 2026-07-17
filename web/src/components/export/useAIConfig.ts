import { useReducer, useMemo, type Dispatch } from 'react';
import type { ComparisonResult } from '../../api/types';

export type StreamMode = 'single' | 'stream';

export type AIErrorKind = 'rate_limited' | 'server' | 'network';

export interface AIErrorState {
  kind: AIErrorKind;
  detail: string;
  retryAfter?: number;
}

export interface AIConfigState {
  provider: string;
  model: string;
  notes: string;
  showAdvanced: boolean;
  showFilters: boolean;
  temperature: number;
  maxTokens: number;
  timeoutS: number;
  useCache: boolean;
  streamMode: StreamMode;
}

export const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  ollama: 'llama3.1:8b',
  lmstudio: 'loaded-model',
  openai: 'gpt-4o-mini',
  openrouter: 'nvidia/nemotron-3-ultra-550b-a55b:free',
  minimax: 'MiniMax-M3',
  glm: 'glm-5.2',
  grok: 'grok-4.20',
};

export const DEFAULT_TEMPERATURE = 0.7;
export const DEFAULT_MAX_TOKENS = 2000;
export const DEFAULT_TIMEOUT_S = 60;

export const initialAIConfigState: AIConfigState = {
  provider: '',
  model: '',
  notes: '',
  showAdvanced: false,
  showFilters: false,
  temperature: DEFAULT_TEMPERATURE,
  maxTokens: DEFAULT_MAX_TOKENS,
  timeoutS: DEFAULT_TIMEOUT_S,
  useCache: true,
  streamMode: 'single',
};

export type AIConfigAction =
  | { type: 'SET_PROVIDER'; value: string }
  | { type: 'SET_MODEL'; value: string }
  | { type: 'SET_NOTES'; value: string }
  | { type: 'SET_TEMPERATURE'; value: number }
  | { type: 'SET_MAX_TOKENS'; value: number }
  | { type: 'SET_TIMEOUT_S'; value: number }
  | { type: 'SET_USE_CACHE'; value: boolean }
  | { type: 'SET_STREAM_MODE'; value: StreamMode }
  | { type: 'TOGGLE_ADVANCED' }
  | { type: 'TOGGLE_FILTERS' };

export function aiConfigReducer(
  state: AIConfigState,
  action: AIConfigAction,
): AIConfigState {
  switch (action.type) {
    case 'SET_PROVIDER': {
      const next = action.value;
      const modelDefault = PROVIDER_DEFAULT_MODELS[next] ?? '';
      return { ...state, provider: next, model: modelDefault };
    }
    case 'SET_MODEL':
      return { ...state, model: action.value };
    case 'SET_NOTES':
      return { ...state, notes: action.value };
    case 'SET_TEMPERATURE':
      return { ...state, temperature: action.value };
    case 'SET_MAX_TOKENS':
      return { ...state, maxTokens: action.value };
    case 'SET_TIMEOUT_S':
      return { ...state, timeoutS: action.value };
    case 'SET_USE_CACHE':
      return { ...state, useCache: action.value };
    case 'SET_STREAM_MODE':
      return { ...state, streamMode: action.value };
    case 'TOGGLE_ADVANCED':
      return { ...state, showAdvanced: !state.showAdvanced };
    case 'TOGGLE_FILTERS':
      return { ...state, showFilters: !state.showFilters };
    default:
      return state;
  }
}

export interface AIConfigActions {
  setProvider: (value: string) => void;
  setModel: (value: string) => void;
  setNotes: (value: string) => void;
  setTemperature: (value: number) => void;
  setMaxTokens: (value: number) => void;
  setTimeoutS: (value: number) => void;
  setUseCache: (value: boolean) => void;
  setStreamMode: (value: StreamMode) => void;
  toggleAdvanced: () => void;
  toggleFilters: () => void;
}

export interface UseAIConfigResult {
  state: AIConfigState;
  dispatch: Dispatch<AIConfigAction>;
  actions: AIConfigActions;
}

export function useAIConfig(
  initial?: Partial<AIConfigState>,
): UseAIConfigResult {
  const [state, dispatch] = useReducer(
    aiConfigReducer,
    initial ? { ...initialAIConfigState, ...initial } : initialAIConfigState,
  );

  const actions = useMemo<AIConfigActions>(
    () => ({
      setProvider: (value) => dispatch({ type: 'SET_PROVIDER', value }),
      setModel: (value) => dispatch({ type: 'SET_MODEL', value }),
      setNotes: (value) => dispatch({ type: 'SET_NOTES', value }),
      setTemperature: (value) => dispatch({ type: 'SET_TEMPERATURE', value }),
      setMaxTokens: (value) => dispatch({ type: 'SET_MAX_TOKENS', value }),
      setTimeoutS: (value) => dispatch({ type: 'SET_TIMEOUT_S', value }),
      setUseCache: (value) => dispatch({ type: 'SET_USE_CACHE', value }),
      setStreamMode: (value) => dispatch({ type: 'SET_STREAM_MODE', value }),
      toggleAdvanced: () => dispatch({ type: 'TOGGLE_ADVANCED' }),
      toggleFilters: () => dispatch({ type: 'TOGGLE_FILTERS' }),
    }),
    [],
  );

  return { state, dispatch, actions };
}

/**
 * Auto-pick the first available provider when none is selected yet.
 * Returns the next provider (or empty string if nothing to pick).
 */
export function pickFirstAvailableProvider(
  currentProvider: string,
  availableProviders: string[] | undefined,
): string | null {
  if (currentProvider) return null;
  if (!availableProviders || availableProviders.length === 0) return null;
  return availableProviders[0];
}

/**
 * Build the set of distinct filter options from a list of comparison rows.
 * Pure helper, exported for reuse and easy testing.
 */
export function buildFilterOptions(rows: ComparisonResult[] | undefined): {
  sectors: string[];
  sections: string[];
  benches: number[];
} {
  const rowsArr: ComparisonResult[] = Array.isArray(rows) ? rows : [];
  const sectors = new Set<string>();
  const sections = new Set<string>();
  const benches = new Set<number>();
  rowsArr.forEach((r) => {
    if (r.sector) sectors.add(r.sector);
    if (r.section) sections.add(r.section);
    if (typeof r.bench_num === 'number') benches.add(r.bench_num);
  });
  return {
    sectors: Array.from(sectors).sort(),
    sections: Array.from(sections).sort(),
    benches: Array.from(benches).sort((a, b) => a - b),
  };
}