/**
 * useCrossLinkState — coordinates the chart↔table hover/click.
 *
 * `hoveredBench` is ephemeral: set on mouseenter, cleared on mouseleave.
 * `selectedBench` is sticky: persists until the user clicks elsewhere
 * or selects a different bench. Stored in localStorage so a reload
 * (or navigating away and back) keeps the selection.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  readCrossLink,
  writeCrossLink,
  type CrossLinkPersisted,
} from '../infrastructure/persistenceAdapter';

export interface UseCrossLinkStateApi {
  readonly hovered: number | null;
  readonly selected: number | null;
  setHovered: (n: number | null) => void;
  setSelected: (n: number | null) => void;
  clear: () => void;
}

export function useCrossLinkState(): UseCrossLinkStateApi {
  // `selected` survives reloads; `hovered` is per-session only.
  const [persisted, setPersisted] = useState<CrossLinkPersisted>(() => readCrossLink());
  const [hovered, setHovered] = useState<number | null>(null);

  useEffect(() => {
    writeCrossLink(persisted);
  }, [persisted]);

  const setSelected = useCallback((n: number | null) => {
    setPersisted((p) => ({ ...p, selectedBench: n }));
  }, []);

  const clear = useCallback(() => {
    setPersisted({ hoveredBench: null, selectedBench: null });
    setHovered(null);
  }, []);

  return useMemo(
    () => ({
      hovered,
      selected: persisted.selectedBench,
      setHovered,
      setSelected,
      clear,
    }),
    [hovered, persisted.selectedBench, setSelected, clear],
  );
}
