/**
 * Compliance statistics: pure counting over a bench array.
 *
 * Used by the ComplianceSummary card to show the 3-of-5-within-
 * tolerance headline and the stacked distribution bar.
 *
 * The compliance system is now binary (CUMPLE / NO_CUMPLE). FUERA
 * is no longer a separate bucket — `parseBenchStatus` collapses the
 * legacy "FUERA DE TOLERANCIA" / "FUERA" backend strings into
 * NO_CUMPLE, so by the time benches reach `computeCompliance` the
 * status set is already binary. The `counts` shape therefore only
 * needs the three presentational statuses.
 */

import { STATUS_PRESENTATION_ORDER } from './status';
import type { Bench } from './types';

// ─── Output shape ───────────────────────────────────────────

/** The three statuses rendered in the compliance summary.
 *
 *  FUERA is excluded: it has been collapsed into NO_CUMPLE by the
 *  domain parsing layer. */
export type ComplianceStatus = 'CUMPLE' | 'NO_CUMPLE' | 'UNKNOWN';

/** Per-status count plus aggregate compliance ratio. */
export interface ComplianceStats {
  /** Ordered worst → best, with a count for every visible status.
   *  No FUERA bucket — the binary CUMPLE/NO_CUMPLE model means
   *  out-of-tolerance benches already land in NO_CUMPLE. */
  readonly counts: Readonly<Record<ComplianceStatus, number>>;
  /** `counts.CUMPLE + counts.NO_CUMPLE + counts.UNKNOWN`.
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
  //
  // FUERA intentionally absent: benches with a legacy out-of-
  // tolerance status arrive here already collapsed into NO_CUMPLE
  // by `parseBenchStatus`, so no merge step is needed.
  const counts: Record<ComplianceStatus, number> = {
    CUMPLE: 0,
    NO_CUMPLE: 0,
    UNKNOWN: 0,
  };
  for (const b of benches) {
    // Defensive: if any bench somehow carries a legacy 'FUERA' status
    // (e.g. constructed directly in tests or fixtures), merge it into
    // NO_CUMPLE so the binary model is preserved end-to-end.
    const status = b.status === 'FUERA' ? 'NO_CUMPLE' : b.status;
    if (status in counts) counts[status] += 1;
  }

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
): Generator<{ status: ComplianceStatus; count: number }> {
  for (const status of STATUS_PRESENTATION_ORDER) {
    // FUERA is no longer in STATUS_PRESENTATION_ORDER, so the indexed
    // access is guaranteed to hit a defined key in stats.counts.
    yield { status: status as ComplianceStatus, count: stats.counts[status as ComplianceStatus] };
  }
}
