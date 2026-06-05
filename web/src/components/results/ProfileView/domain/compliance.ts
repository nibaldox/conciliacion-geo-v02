/**
 * Compliance statistics: pure counting over a bench array.
 *
 * Used by the ComplianceSummary card to show the 3-of-5-within-
 * tolerance headline and the stacked distribution bar.
 */

import { STATUS_PRESENTATION_ORDER } from './status';
import type { Bench, BenchStatus } from './types';

// ─── Output shape ───────────────────────────────────────────

/** Per-status count plus aggregate compliance ratio. */
export interface ComplianceStats {
  /** Ordered worst → best, with a count for every status. */
  readonly counts: Readonly<Record<BenchStatus, number>>;
  /** `counts.CUMPLE + counts.FUERA + counts.NO_CUMPLE + counts.UNKNOWN`.
   *  Cached so the renderer doesn't have to re-sum. */
  readonly total: number;
  /** `counts.CUMPLE / total` in [0, 1]. `0` when total is 0. */
  readonly complianceRatio: number;
  /** Convenience: the count of benches within tolerance. */
  readonly withinTolerance: number;
}

// ─── Computation ────────────────────────────────────────────

/** Compute compliance stats. Pure: no I/O, no mutation. */
export function computeCompliance(benches: readonly Bench[]): ComplianceStats {
  // Start every status at 0 — the renderer can rely on a complete
  // record even when no bench has that status.
  const counts: Record<BenchStatus, number> = {
    CUMPLE: 0,
    FUERA: 0,
    NO_CUMPLE: 0,
    UNKNOWN: 0,
  };
  for (const b of benches) counts[b.status] += 1;

  const total = benches.length;
  const complianceRatio = total === 0 ? 0 : counts.CUMPLE / total;
  const withinTolerance = counts.CUMPLE;

  return { counts, total, complianceRatio, withinTolerance };
}

/** Returns a presentation-ready label like "3 of 5 within tolerance"
 *  given the stats. */
export function describeCompliance(
  stats: ComplianceStats,
  formatRatio: (n: number) => string,
): string {
  return `${stats.withinTolerance} of ${stats.total} within tolerance (${formatRatio(
    stats.complianceRatio,
  )})`;
}

/** Iterate statuses in presentation order with their counts. */
export function* iterateCounts(
  stats: ComplianceStats,
): Generator<{ status: BenchStatus; count: number }> {
  for (const status of STATUS_PRESENTATION_ORDER) {
    yield { status, count: stats.counts[status] };
  }
}
