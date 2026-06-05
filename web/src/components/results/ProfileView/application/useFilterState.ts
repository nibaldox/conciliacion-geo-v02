/**
 * useFilterState — single source of truth for the FilterState.
 *
 * URL is the primary persistence (so /conciliacion-geo-v02/?f.a=1
 * deep-links to a specific filter config). localStorage is the
 * fallback when there's no URL state.
 *
 * Returns a setter that:
 *  - updates state in React (so the UI re-renders)
 *  - replaces the URL (via history.replaceState, no navigation)
 *  - mirrors to localStorage (survives reload)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { BenchStatus } from '../domain/types';
import type { FilterState } from '../domain/filters';
import {
  DEFAULT_FILTER_STATE,
  toggleStatus,
} from '../domain/filters';
import {
  readFiltersFromUrl,
  writeFiltersToUrl,
  readFiltersFromStorage,
  writeFiltersToStorage,
} from '../infrastructure/persistenceAdapter';

function loadInitialState(): FilterState {
  if (typeof window === 'undefined') return DEFAULT_FILTER_STATE;
  const fromUrl = readFiltersFromUrl(window.location.search);
  // If the URL has ANY filter params, URL wins. Otherwise fall back
  // to the user's last-saved session.
  const urlHasAny = window.location.search.length > 0 &&
    Array.from(new URLSearchParams(window.location.search).keys()).some((k) => k.startsWith('f.'));
  if (urlHasAny) return fromUrl;
  return readFiltersFromStorage() ?? fromUrl;
}

export interface UseFilterStateApi {
  readonly state: FilterState;
  setField: <K extends keyof Omit<FilterState, 'statusFilter'>>(field: K, value: FilterState[K]) => void;
  toggleStatusInFilter: (status: BenchStatus) => void;
  reset: () => void;
}

export function useFilterState(): UseFilterStateApi {
  const [state, setState] = useState<FilterState>(loadInitialState);

  // Persist on every change. We use a single effect (rather than
  // a debounce) because the operations are cheap (string encoding
  // + a single history.replaceState call).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const qs = writeFiltersToUrl(state);
    const url = qs.length > 0 ? `${window.location.pathname}?${qs}` : window.location.pathname;
    window.history.replaceState(null, '', url);
    writeFiltersToStorage(state);
  }, [state]);

  const setField = useCallback(
    <K extends keyof Omit<FilterState, 'statusFilter'>>(field: K, value: FilterState[K]) => {
      setState((prev: FilterState) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const toggleStatusInFilter = useCallback((status: BenchStatus) => {
    setState((prev: FilterState) => ({ ...prev, statusFilter: toggleStatus(prev.statusFilter, status) }));
  }, []);

  const reset = useCallback(() => {
    setState(DEFAULT_FILTER_STATE);
  }, []);

  return useMemo(
    () => ({ state, setField, toggleStatusInFilter, reset }),
    [state, setField, toggleStatusInFilter, reset],
  );
}
