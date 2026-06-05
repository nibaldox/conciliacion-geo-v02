/**
 * useFilteredBenches — applies the FilterState.statusFilter to a
 * bench list. Pure derivation, memoised by inputs.
 */

import { useMemo } from 'react';
import type { Bench } from '../domain/types';
import type { FilterState } from '../domain/filters';
import { applyFilters } from '../domain/filters';

export function useFilteredBenches(
  benches: readonly Bench[],
  filterState: FilterState,
): readonly Bench[] {
  return useMemo(() => applyFilters(benches, filterState), [benches, filterState]);
}
