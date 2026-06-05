/**
 * useSortedBenches — applies sort field + direction to a bench list.
 * Default: sort by benchNumber asc. Pure derivation, memoised.
 */

import { useMemo } from 'react';
import type { Bench } from '../domain/types';
import type { SortField, SortDirection } from '../domain/sorting';
import { applySort, DEFAULT_SORT } from '../domain/sorting';

export function useSortedBenches(
  benches: readonly Bench[],
  field: SortField = DEFAULT_SORT.field,
  direction: SortDirection = DEFAULT_SORT.direction,
): readonly Bench[] {
  return useMemo(() => applySort(benches, field, direction), [benches, field, direction]);
}
