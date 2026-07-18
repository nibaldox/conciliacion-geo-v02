/**
 * Bench status semantics: parsing, comparison, presentation tokens.
 *
 * Everything status-related lives here so the rest of the codebase
 * imports from a single place. If we add a new status (or rename
 * 'FUERA DE TOLERANCIA' to 'FUERA' on the backend), this is the
 * only file that needs to change.
 */

import { assertNever, type BenchStatus } from './types';

export type ComplianceStatus = 'CUMPLE' | 'NO_CUMPLE' | 'UNKNOWN';

// ─── Backend status strings ──────────────────────────────────

/** The seven strings the backend may return in `*_status` fields.
 *
 *  Note: 'FUERA DE TOLERANCIA' is intentionally absent. The presentation
 *  layer treats compliance as binary, so parseBenchStatus collapses
 *  every out-of-tolerance backend string (including the legacy
 *  "FUERA DE TOLERANCIA" / "FUERA" forms) into NO_CUMPLE before it
 *  reaches this type. Anything that still receives a raw FUERA literal
 *  is operating outside the canonical pipeline and should be migrated
 *  rather than whitelisted here. */
export const BACKEND_STATUS_STRINGS = [
  'CUMPLE',
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

/** Normalise any backend status string to one of our 4 buckets.
 *
 * The compliance system is now binary at the presentation layer
 * (CUMPLE / NO_CUMPLE). The legacy "FUERA DE TOLERANCIA" / "FUERA"
 * strings coming from the backend are collapsed into NO_CUMPLE so
 * downstream code never sees a FUERA value. The 'FUERA' literal
 * remains in the BenchStatus union purely as a defensive fallback
 * for any path that hasn't yet been migrated; it is never produced
 * by parseBenchStatus or by the API adapter. */
export function parseBenchStatus(raw: string | null | undefined): BenchStatus {
  if (raw == null) return 'UNKNOWN';
  const s = raw.trim().toUpperCase();
  if (s === 'CUMPLE') return 'CUMPLE';
  // "FUERA DE TOLERANCIA" and the shortened "FUERA" both collapse to
  // NO_CUMPLE — the presentation layer treats compliance as binary.
  if (s === 'FUERA DE TOLERANCIA' || s === 'FUERA') return 'NO_CUMPLE';
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
 *  the problem.
 *
 *  FUERA is intentionally absent: parseBenchStatus collapses all
 *  out-of-tolerance backend strings into NO_CUMPLE, so the
 *  presentation layer never needs to render a FUERA bucket. */
export const STATUS_PRESENTATION_ORDER: readonly ComplianceStatus[] = [
  'NO_CUMPLE',
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
