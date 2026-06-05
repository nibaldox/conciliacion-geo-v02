/**
 * Pure filter operations for the ProfileView.
 *
 * The `FilterState` is plain data; `applyFilters` is a pure function.
 * No React, no I/O, no `useEffect`. Tests don't need jsdom.
 */

import type { Bench, BenchStatus } from './types';
import { compareStatus, STATUS_PRESENTATION_ORDER } from './status';

// ─── Filter state ───────────────────────────────────────────

/** Which view-overlay toggles are currently enabled. */
export interface FilterState {
  /** Show the reconciled design polyline (dashed blue). */
  readonly showReconciledDesign: boolean;
  /** Show the reconciled topo polyline (dashed green). */
  readonly showReconciledTopo: boolean;
  /** Show shaded deviation areas between design and topo. */
  readonly showAreas: boolean;
  /** Show spill material at the base of each bench. */
  readonly showSpillAreas: boolean;
  /** Color the bench markers by compliance (overrides the default
   *  design-blue / topo-green split). */
  readonly showSemaphore: boolean;
  /** Overlay blast-hole projections. */
  readonly showBlastHoles: boolean;
  /** Maximum distance (m) from the section line for a blast hole
   *  to be considered "on" this section. Only meaningful when
   *  `showBlastHoles` is true. */
  readonly blastTolerance: number;
  /** Restrict the bench table to these statuses. Empty = all. */
  readonly statusFilter: readonly BenchStatus[];
}

/** The default filter state — mirrors Streamlit's defaults. */
export const DEFAULT_FILTER_STATE: FilterState = Object.freeze({
  showReconciledDesign: true,
  showReconciledTopo: true,
  showAreas: false,
  showSpillAreas: true,
  showSemaphore: false,
  showBlastHoles: true,
  blastTolerance: 10,
  statusFilter: [],
});

// ─── Pure operations ────────────────────────────────────────

/** Returns true if the state is different from DEFAULT_FILTER_STATE.
 *  Used to decide whether to show a "Reset filters" button. */
export function isFilterActive(state: FilterState): boolean {
  const d = DEFAULT_FILTER_STATE;
  return (
    state.showReconciledDesign !== d.showReconciledDesign ||
    state.showReconciledTopo !== d.showReconciledTopo ||
    state.showAreas !== d.showAreas ||
    state.showSpillAreas !== d.showSpillAreas ||
    state.showSemaphore !== d.showSemaphore ||
    state.showBlastHoles !== d.showBlastHoles ||
    state.blastTolerance !== d.blastTolerance ||
    state.statusFilter.length > 0
  );
}

/** Filter an array of benches by `FilterState.statusFilter`. Pure:
 *  does not mutate the input. */
export function applyFilters(
  benches: readonly Bench[],
  state: FilterState,
): readonly Bench[] {
  if (state.statusFilter.length === 0) return benches;
  const allowed = new Set<BenchStatus>(state.statusFilter);
  return benches.filter((b) => allowed.has(b.status));
}

/** All possible values for `statusFilter`, in presentation order.
 *  Useful for rendering filter chips. */
export const ALL_STATUSES_FOR_FILTER: readonly BenchStatus[] =
  STATUS_PRESENTATION_ORDER;

/** Toggle a single status in the filter set. Returns a new array
 *  (immutability for React state updates). */
export function toggleStatus(
  current: readonly BenchStatus[],
  status: BenchStatus,
): readonly BenchStatus[] {
  if (current.includes(status)) {
    return current.filter((s) => s !== status);
  }
  return [...current, status];
}

/** Returns a sort comparator that orders by status severity
 *  (worst first). Useful for the "errors at top" default. */
export function compareByStatusSeverity(
  a: Bench,
  b: Bench,
  direction: 'asc' | 'desc' = 'desc',
): number {
  const cmp = compareStatus(b.status, a.status); // b first → worst first
  return direction === 'desc' ? cmp : -cmp;
}
