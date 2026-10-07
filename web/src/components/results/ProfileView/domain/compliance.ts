/**
 * Compliance statistics: pure counting over a bench array.
 *
 * Used by the ComplianceSummary card to show the 3-of-5-within-
 * tolerance headline and the stacked distribution bar.
 *
 * The counts retain the backend's three tolerance tiers plus
 * UNKNOWN for benches without a recognised status.
 */

import { STATUS_PRESENTATION_ORDER } from './status';
import type { Bench, BenchStatus } from './types';

// ─── Output shape ───────────────────────────────────────────

/** The three tolerance tiers and the unevaluated state. */
export type ComplianceStatus = 'CUMPLE' | 'FUERA' | 'NO_CUMPLE' | 'UNKNOWN';

/** Per-status count plus aggregate compliance ratio. */
export interface ComplianceStats {
  /** Ordered worst → best, with a count for every visible status. */
  readonly counts: Readonly<Record<ComplianceStatus, number>>;
  /** `counts.CUMPLE + counts.FUERA + counts.NO_CUMPLE + counts.UNKNOWN`.
   *  Cached so the renderer doesn't have to re-sum. */
  readonly total: number;
  /** Number of benches with a recognised tolerance tier. */
  readonly evaluated: number;
  /** Number with missing or unrecognised compliance data. */
  readonly unknown: number;
  /** `counts.CUMPLE / total` in [0, 1]. `0` when total is 0. */
  readonly complianceRatio: number;
  /** Convenience: the count of benches within tolerance. */
  readonly withinTolerance: number;
}

// ─── Computation ────────────────────────────────────────────

/** Compute compliance stats. Pure: no I/O, no mutation. */
export function computeCompliance(benches: readonly Bench[]): ComplianceStats {
  return computeComplianceStatuses(benches.map((bench) => bench.status));
}

export function computeComplianceStatuses(statuses: readonly BenchStatus[]): ComplianceStats {
  // Start every status at 0 — the renderer can rely on a complete
  // record even when no bench has that status.
  //
  const counts: Record<ComplianceStatus, number> = {
    CUMPLE: 0,
    FUERA: 0,
    NO_CUMPLE: 0,
    UNKNOWN: 0,
  };
  for (const status of statuses) {
    if (Object.hasOwn(counts, status)) counts[status] += 1;
    else counts.UNKNOWN += 1;
  }

  const total = statuses.length;
  const evaluated = total - counts.UNKNOWN;
  const complianceRatio = evaluated === 0 ? 0 : counts.CUMPLE / evaluated;
  const withinTolerance = counts.CUMPLE;
  const unknown = counts.UNKNOWN;

  return { counts, total, evaluated, unknown, complianceRatio, withinTolerance };
}

/** Returns a presentation-ready label like "3 of 5 within tolerance"
 *  given the stats. */
export function describeCompliance(
  stats: ComplianceStats,
  formatRatio: (n: number) => string,
): string {
  return `${stats.withinTolerance} of ${stats.evaluated} evaluated within tolerance (${formatRatio(
    stats.complianceRatio,
  )})`;
}

/** Iterate statuses in presentation order with their counts. */
export function* iterateCounts(
  stats: ComplianceStats,
): Generator<{ status: ComplianceStatus; count: number }> {
  for (const status of STATUS_PRESENTATION_ORDER) {
    yield { status, count: stats.counts[status] };
  }
}
