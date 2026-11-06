/**
 * Bench status semantics: parsing, comparison, presentation tokens.
 *
 * Everything status-related lives here so the rest of the codebase
 * imports from a single place. If we add a new status (or rename
 * 'FUERA DE TOLERANCIA' to 'FUERA' on the backend), this is the
 * only file that needs to change.
 */

import { assertNever, type BenchScoreInput, type BenchStatus } from './types';

export type ComplianceStatus = 'CUMPLE' | 'FUERA' | 'NO_CUMPLE' | 'UNKNOWN';

export const BENCH_SCORE_MAX = 100;

export const BENCH_PASSING_SCORE = 70;

export const SCORE_WEIGHTS = {
  berm: 60,
  angle: 10,
  height: 30,
} as const;

// ─── Backend status strings ──────────────────────────────────

/** The status strings the backend may return in `*_status` fields.
 *
 *  Out-of-tolerance is a distinct status because the backend evaluates
 *  signed deviations against asymmetric tolerances in three tiers. */
export const BACKEND_STATUS_STRINGS = [
  'CUMPLE',
  'FUERA DE TOLERANCIA',
  'FUERA',
  'NO CUMPLE',
  'NO CONSTRUIDO',
  'FALTA BANCO',
  'EXTRA',
  'BANCO ADICIONAL',
] as const;

export type BackendStatusString = (typeof BACKEND_STATUS_STRINGS)[number];

const BACKEND_STATUS_SET: ReadonlySet<string> = new Set(BACKEND_STATUS_STRINGS);

/** Returns true if the string is one we know how to handle. */
export function isBackendStatusString(s: string): s is BackendStatusString {
  return BACKEND_STATUS_SET.has(s);
}

// ─── Parsing ────────────────────────────────────────────────

/** Normalise backend strings to the three compliance tiers and UNKNOWN. */
export function parseBenchStatus(raw: string | null | undefined): BenchStatus {
  if (raw == null) return 'UNKNOWN';
  const s = raw.trim().toUpperCase();
  if (s === 'CUMPLE') return 'CUMPLE';
  if (s === 'FUERA DE TOLERANCIA' || s === 'FUERA') return 'FUERA';
  if (
    s === 'NO CUMPLE' ||
    s === 'NO_CONSTRUIDO' ||
    s === 'NO CONSTRUIDO' ||
    s === 'FALTA BANCO' ||
    s === 'BANCO ADICIONAL' ||
    s === 'EXTRA'
  ) return 'NO_CUMPLE';
  return 'UNKNOWN';
}

/** Given the three status fields of a comparison, return the
 *  worst (most severe) one. This is what we display in the UI
 *  when there's no other signal. */
export function worstOfThree(
  height: string | null | undefined,
  angle: string | null | undefined,
  berm: string | null | undefined,
): BenchStatus {
  const a = parseBenchStatus(height);
  const b = parseBenchStatus(angle);
  const c = parseBenchStatus(berm);
  const rank = STATUS_SEVERITY;
  let worst: BenchStatus = 'UNKNOWN';
  for (const s of [a, b, c]) {
    if (rank[s] > rank[worst]) worst = s;
  }
  return worst;
}

export function isValidBenchScore(score: unknown): score is number {
  return typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= BENCH_SCORE_MAX;
}

export function classifyBenchScore(score: number | null | undefined): BenchStatus {
  if (!isValidBenchScore(score)) return 'UNKNOWN';
  return score >= BENCH_PASSING_SCORE ? 'CUMPLE' : 'NO_CUMPLE';
}

export function resolveBenchScore(
  comparison: BenchScoreInput | null | undefined,
): number | null {
  if (comparison == null || comparison.type !== 'MATCH') return null;
  if (comparison.bench_score !== undefined && comparison.bench_score !== null) {
    return isValidBenchScore(comparison.bench_score) ? comparison.bench_score : null;
  }
  const height = parseMatchScoreStatus(comparison.height_status);
  const angle = parseMatchScoreStatus(comparison.angle_status);
  const berm = parseMatchScoreStatus(comparison.berm_status);
  if (height === 'UNKNOWN' || angle === 'UNKNOWN' || berm === 'UNKNOWN') return null;
  return (
    (berm === 'CUMPLE' ? SCORE_WEIGHTS.berm : 0) +
    (angle === 'CUMPLE' ? SCORE_WEIGHTS.angle : 0) +
    (height === 'CUMPLE' ? SCORE_WEIGHTS.height : 0)
  );
}

function parseMatchScoreStatus(raw: string | null | undefined): BenchStatus {
  if (raw == null) return 'UNKNOWN';
  const s = raw.trim().toUpperCase();
  if (s === 'CUMPLE') return 'CUMPLE';
  if (s === 'FUERA DE TOLERANCIA' || s === 'FUERA') return 'FUERA';
  if (s === 'NO CUMPLE') return 'NO_CUMPLE';
  return 'UNKNOWN';
}

export function classifyComparisonBenchStatus(
  comparison: BenchScoreInput | null | undefined,
): BenchStatus {
  if (comparison == null) return 'UNKNOWN';
  if (comparison.type === 'MISSING' || comparison.type === 'EXTRA') return 'NO_CUMPLE';
  return classifyBenchScore(resolveBenchScore(comparison));
}

// ─── Severity ordering ──────────────────────────────────────

/** Numeric severity for ordering/comparison. Higher = worse. */
export const STATUS_SEVERITY: Record<BenchStatus, number> = {
  UNKNOWN: 0,
  CUMPLE: 1,
  FUERA: 2,
  NO_CUMPLE: 3,
};

/** Returns -1, 0, or 1 for use in Array#sort. */
export function compareStatus(a: BenchStatus, b: BenchStatus): number {
  return STATUS_SEVERITY[a] - STATUS_SEVERITY[b];
}

// ─── Visual tokens (CSS variable names — never hex values) ──

/** Semantic status → CSS variable mapping. Components use these
 *  via `var(...)` so the design system owns the colours. */
export const STATUS_BG_VAR: Record<BenchStatus, string> = {
  CUMPLE: 'var(--status-ok-bg)',
  FUERA: 'var(--status-warn-bg)',
  NO_CUMPLE: 'var(--status-nok-bg)',
  UNKNOWN: 'var(--color-surface-muted)',
};

export const STATUS_FG_VAR: Record<BenchStatus, string> = {
  CUMPLE: 'var(--status-ok-text)',
  FUERA: 'var(--status-warn-text)',
  NO_CUMPLE: 'var(--status-nok-text)',
  UNKNOWN: 'var(--color-text-muted)',
};

export const STATUS_BORDER_VAR: Record<BenchStatus, string> = {
  CUMPLE: 'var(--status-ok-border)',
  FUERA: 'var(--status-warn-border)',
  NO_CUMPLE: 'var(--status-nok-border)',
  UNKNOWN: 'var(--color-border)',
};

export const STATUS_ICON: Record<BenchStatus, string> = {
  CUMPLE: '✓',
  FUERA: '⚠',
  NO_CUMPLE: '✗',
  UNKNOWN: '·',
};

/** Order in which statuses should be presented in legends, filters,
 *  and compliance summary cards. Worst first so the eye lands on
 *  the problem.
 *
 *  Includes all three evaluated tiers plus unknown data. */
export const STATUS_PRESENTATION_ORDER: readonly ComplianceStatus[] = [
  'NO_CUMPLE',
  'FUERA',
  'CUMPLE',
  'UNKNOWN',
] as const;

/** Exhaustiveness check helper. */
export function forEachStatus(fn: (status: ComplianceStatus) => void): void {
  for (const s of STATUS_PRESENTATION_ORDER) fn(s);
}

/** Pretty print for logs / dev tools. */
export function formatStatus(s: BenchStatus): string {
  switch (s) {
    case 'CUMPLE': return 'CUMPLE';
    case 'FUERA': return 'FUERA';
    case 'NO_CUMPLE': return 'NO_CUMPLE';
    case 'UNKNOWN': return 'UNKNOWN';
    default: return assertNever(s);
  }
}
