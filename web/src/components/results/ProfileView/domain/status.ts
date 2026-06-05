/**
 * Bench status semantics: parsing, comparison, presentation tokens.
 *
 * Everything status-related lives here so the rest of the codebase
 * imports from a single place. If we add a new status (or rename
 * 'FUERA DE TOLERANCIA' to 'FUERA' on the backend), this is the
 * only file that needs to change.
 */

import { assertNever, type BenchStatus } from './types';

// ─── Backend status strings ──────────────────────────────────

/** The seven strings the backend may return in `*_status` fields. */
export const BACKEND_STATUS_STRINGS = [
  'CUMPLE',
  'FUERA DE TOLERANCIA',
  'NO CUMPLE',
  'NO CONSTRUIDO',
  'FALTA BANCO',
  'EXTRA',
  'BANCO ADICIONAL',
] as const;

export type BackendStatusString = (typeof BACKEND_STATUS_STRINGS)[number];

/** Returns true if the string is one we know how to handle. */
export function isBackendStatusString(s: string): s is BackendStatusString {
  return (BACKEND_STATUS_STRINGS as readonly string[]).includes(s);
}

// ─── Parsing ────────────────────────────────────────────────

/** Normalise any backend status string to one of our 4 buckets. */
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
  ) {
    return 'NO_CUMPLE';
  }
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
 *  the problem. */
export const STATUS_PRESENTATION_ORDER: readonly BenchStatus[] = [
  'NO_CUMPLE',
  'FUERA',
  'CUMPLE',
  'UNKNOWN',
] as const;

/** Exhaustiveness check helper. */
export function forEachStatus(fn: (status: BenchStatus) => void): void {
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
