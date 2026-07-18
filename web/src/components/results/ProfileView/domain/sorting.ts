/**
 * Pure sorting operations for the bench table.
 *
 * Sort field enum + a factory that returns a `Comparator<Bench>` for
 * the chosen field+direction. Centralised so every sort UI (column
 * header, default order, URL-saved order) goes through one place.
 *
 * Status ordering is now binary at the presentation layer
 * (NO_CUMPLE worst → CUMPLE best → UNKNOWN last). FUERA has been
 * removed from the status index because parseBenchStatus collapses
 * the legacy "FUERA DE TOLERANCIA" / "FUERA" backend strings into
 * NO_CUMPLE before benches reach the sort layer.
 */

import type { Bench, BenchStatus } from './types';
import { STATUS_PRESENTATION_ORDER } from './status';

// ─── Field enum ─────────────────────────────────────────────

export const SORT_FIELDS = [
  'benchNumber',
  'crestElevation',
  'designHeight',
  'height',
  'designAngle',
  'faceAngle',
  'designBerm',
  'bermWidth',
  'status',
] as const;

export type SortField = (typeof SORT_FIELDS)[number];

/** Direction: `asc` = smallest first, `desc` = largest first. */
export type SortDirection = 'asc' | 'desc';

export const DEFAULT_SORT: { field: SortField; direction: SortDirection } = {
  field: 'benchNumber',
  direction: 'asc',
};

// ─── Comparators ────────────────────────────────────────────

const STATUS_INDEX: Record<BenchStatus, number> = (() => {
  // Seed every variant of BenchStatus with a high "unknown" rank so
  // any legacy FUERA value (which should never reach the sorter
  // because parseBenchStatus collapses it) still sorts to the end
  // rather than crashing.
  const map = {
    CUMPLE: 0,
    NO_CUMPLE: 0,
    UNKNOWN: 0,
    FUERA: Number.MAX_SAFE_INTEGER,
  } as Record<BenchStatus, number>;
  STATUS_PRESENTATION_ORDER.forEach((s, i) => {
    map[s] = i;
  });
  return map;
})();

/** Status index in the *presentation* order: NO_CUMPLE=0, CUMPLE=1,
 *  UNKNOWN=2. FUERA is not in the presentation order — it has been
 *  collapsed into NO_CUMPLE by parseBenchStatus — but it remains in
 *  STATUS_INDEX with a sentinel rank so any stray value sorts last
 *  instead of producing NaN. */
function statusRank(s: BenchStatus): number {
  return STATUS_INDEX[s];
}

/** Build a comparator for the given field + direction. */
export function comparator(
  field: SortField,
  direction: SortDirection,
): (a: Bench, b: Bench) => number {
  const sign = direction === 'asc' ? 1 : -1;

  return (a, b) => {
    let cmp = 0;
    switch (field) {
      case 'benchNumber':
        cmp = a.benchNumber - b.benchNumber;
        break;
      case 'crestElevation':
        cmp = a.crestElevation - b.crestElevation;
        break;
      case 'designHeight':
        cmp = (a.designHeight ?? 0) - (b.designHeight ?? 0);
        break;
      case 'height':
        cmp = a.height - b.height;
        break;
      case 'designAngle':
        cmp = (a.designAngle ?? 0) - (b.designAngle ?? 0);
        break;
      case 'faceAngle':
        cmp = a.faceAngle - b.faceAngle;
        break;
      case 'designBerm':
        cmp = (a.designBerm ?? 0) - (b.designBerm ?? 0);
        break;
      case 'bermWidth':
        if (a.bermWidth === null && b.bermWidth === null) cmp = 0;
        else if (a.bermWidth === null) return 1;
        else if (b.bermWidth === null) return -1;
        else cmp = a.bermWidth - b.bermWidth;
        break;
      case 'status':
        cmp = statusRank(a.status) - statusRank(b.status);
        break;
      default:
        // Exhaustiveness — TypeScript will complain here if a new
        // field is added to SortField but not handled above.
        throw new Error(`Unhandled sort field: ${String(field)}`);
    }
    return cmp * sign;
  };
}

/** Apply a comparator to a bench array. Pure, returns a new array. */
export function applySort(
  benches: readonly Bench[],
  field: SortField,
  direction: SortDirection,
): readonly Bench[] {
  // Copy before sorting — Array#sort mutates.
  return [...benches].sort(comparator(field, direction));
}

/** Cycle: `asc → desc → none → asc`. Returns the next state. */
export function cycleSort(
  current: { field: SortField; direction: SortDirection } | null,
  clickedField: SortField,
): { field: SortField; direction: SortDirection } | null {
  if (current === null || current.field !== clickedField) {
    return { field: clickedField, direction: 'asc' };
  }
  if (current.direction === 'asc') {
    return { field: clickedField, direction: 'desc' };
  }
  return null; // back to default order
}
