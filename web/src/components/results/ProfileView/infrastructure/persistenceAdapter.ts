/**
 * Persistence adapter for UI state.
 *
 * Two storage channels:
 *  - URL search params: for state that should survive navigation
 *    and be shareable (filter toggles).
 *  - localStorage: for state that should survive reloads but is
 *    per-device (cross-link selection).
 *
 * The domain/application layers never touch these directly. Hooks
 * wrap them and handle the JSON encode/decode.
 */

import type { FilterState } from '../domain/filters';
import { DEFAULT_FILTER_STATE } from '../domain/filters';

// ─── URL search params ──────────────────────────────────────

/** All FilterState fields except `statusFilter`, mapped to short URL keys. */
const FILTER_PARAM_KEYS = {
  showReconciledDesign: 'f.rd',
  showReconciledTopo: 'f.rt',
  showAreas: 'f.a',
  showSpillAreas: 'f.sa',
  showSemaphore: 'f.sm',
  showBlastHoles: 'f.bh',
  blastTolerance: 'f.bt',
} as const satisfies Record<keyof Omit<FilterState, 'statusFilter'>, string>;

type FilterParamField = keyof typeof FILTER_PARAM_KEYS;

/** Serialise the filter state into the URL. */
export function writeFiltersToUrl(state: FilterState): string {
  const params = new URLSearchParams();
  for (const field of Object.keys(FILTER_PARAM_KEYS) as FilterParamField[]) {
    const key = FILTER_PARAM_KEYS[field];
    const value = state[field];
    const defaultValue = DEFAULT_FILTER_STATE[field];
    if (value !== defaultValue) {
      params.set(key, String(value));
    }
  }
  if (state.statusFilter.length > 0) {
    params.set('f.sf', state.statusFilter.join(','));
  }
  return params.toString();
}

/** Read the filter state from the URL, falling back to defaults. */
export function readFiltersFromUrl(search: string): FilterState {
  const params = new URLSearchParams(search);
  let out: FilterState = { ...DEFAULT_FILTER_STATE };
  for (const field of Object.keys(FILTER_PARAM_KEYS) as FilterParamField[]) {
    const key = FILTER_PARAM_KEYS[field];
    const raw = params.get(key);
    if (raw === null) continue;
    const def = DEFAULT_FILTER_STATE[field];
    if (typeof def === 'number') {
      const n = parseFloat(raw);
      if (Number.isFinite(n)) out = { ...out, [field]: n };
    } else if (typeof def === 'boolean') {
      out = { ...out, [field]: raw === 'true' || raw === '1' };
    }
  }
  const sf = params.get('f.sf');
  if (sf) {
    out = { ...out, statusFilter: sf.split(',').filter(Boolean) as FilterState['statusFilter'] };
  }
  return out;
}

// ─── localStorage ───────────────────────────────────────────

const CROSS_LINK_KEY = 'profileView.crossLink';
const FILTER_LS_KEY = 'profileView.filters';

export interface CrossLinkPersisted {
  hoveredBench: number | null;
  selectedBench: number | null;
}

/** Read the cross-link state from localStorage. SSR-safe. */
export function readCrossLink(): CrossLinkPersisted {
  const fallback: CrossLinkPersisted = { hoveredBench: null, selectedBench: null };
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(CROSS_LINK_KEY);
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'hoveredBench' in parsed &&
      'selectedBench' in parsed
    ) {
      const obj = parsed as Record<string, unknown>;
      return {
        hoveredBench: typeof obj.hoveredBench === 'number' ? obj.hoveredBench : null,
        selectedBench: typeof obj.selectedBench === 'number' ? obj.selectedBench : null,
      };
    }
    return fallback;
  } catch {
    return fallback;
  }
}

/** Write the cross-link state to localStorage. */
export function writeCrossLink(state: CrossLinkPersisted): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CROSS_LINK_KEY, JSON.stringify(state));
  } catch {
    // localStorage may be full or disabled (private mode) — fail
    // silently. The state still works for the current session.
  }
}

/** Read the filter state from localStorage as a fallback. */
export function readFiltersFromStorage(): FilterState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(FILTER_LS_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === 'object' && parsed !== null) {
      return { ...DEFAULT_FILTER_STATE, ...(parsed as Partial<FilterState>) };
    }
    return null;
  } catch {
    return null;
  }
}

/** Write the filter state to localStorage. */
export function writeFiltersToStorage(state: FilterState): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(FILTER_LS_KEY, JSON.stringify(state));
  } catch {
    // see writeCrossLink
  }
}
