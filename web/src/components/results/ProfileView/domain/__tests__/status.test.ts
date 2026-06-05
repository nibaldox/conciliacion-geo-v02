import { describe, it, expect } from 'vitest';
import {
  parseBenchStatus,
  worstOfThree,
  compareStatus,
  isBackendStatusString,
  STATUS_SEVERITY,
  STATUS_PRESENTATION_ORDER,
  forEachStatus,
  formatStatus,
} from '../status';
import { assertNever } from '../types';
import type { BenchStatus } from '../types';

describe('parseBenchStatus', () => {
  it('parses known compliance strings to their canonical bucket', () => {
    expect(parseBenchStatus('CUMPLE')).toBe('CUMPLE');
    expect(parseBenchStatus('FUERA DE TOLERANCIA')).toBe('FUERA');
    expect(parseBenchStatus('NO CUMPLE')).toBe('NO_CUMPLE');
    expect(parseBenchStatus('NO CONSTRUIDO')).toBe('NO_CUMPLE');
    expect(parseBenchStatus('FALTA BANCO')).toBe('NO_CUMPLE');
    expect(parseBenchStatus('EXTRA')).toBe('NO_CUMPLE');
    expect(parseBenchStatus('BANCO ADICIONAL')).toBe('NO_CUMPLE');
  });

  it('accepts the shortened "FUERA" form', () => {
    expect(parseBenchStatus('FUERA')).toBe('FUERA');
  });

  it('normalises whitespace and case', () => {
    expect(parseBenchStatus('  cumple  ')).toBe('CUMPLE');
    expect(parseBenchStatus('fuera de tolerancia')).toBe('FUERA');
  });

  it('returns UNKNOWN for null, undefined, and empty string', () => {
    expect(parseBenchStatus(null)).toBe('UNKNOWN');
    expect(parseBenchStatus(undefined)).toBe('UNKNOWN');
    expect(parseBenchStatus('')).toBe('UNKNOWN');
  });

  it('returns UNKNOWN for unrecognised strings', () => {
    expect(parseBenchStatus('TODO BIEN')).toBe('UNKNOWN');
    expect(parseBenchStatus('???')).toBe('UNKNOWN');
  });

  it('does not throw on any input', () => {
    expect(() => parseBenchStatus('garbage')).not.toThrow();
  });
});

describe('worstOfThree', () => {
  it('returns CUMPLE when all three are CUMPLE', () => {
    expect(worstOfThree('CUMPLE', 'CUMPLE', 'CUMPLE')).toBe('CUMPLE');
  });

  it('returns the most severe when they differ', () => {
    expect(worstOfThree('CUMPLE', 'CUMPLE', 'NO CUMPLE')).toBe('NO_CUMPLE');
    expect(worstOfThree('CUMPLE', 'FUERA DE TOLERANCIA', 'CUMPLE')).toBe('FUERA');
    expect(worstOfThree('NO CUMPLE', 'FUERA DE TOLERANCIA', 'CUMPLE')).toBe('NO_CUMPLE');
  });

  it('treats null/undefined as UNKNOWN (least severe)', () => {
    expect(worstOfThree(null, null, null)).toBe('UNKNOWN');
    expect(worstOfThree('CUMPLE', null, null)).toBe('CUMPLE');
  });

  it('UNKNOWN is never worse than a real status', () => {
    expect(worstOfThree('UNKNOWN', 'CUMPLE', 'UNKNOWN')).toBe('CUMPLE');
  });
});

describe('compareStatus', () => {
  it('returns negative when a is less severe than b', () => {
    expect(compareStatus('CUMPLE', 'FUERA')).toBeLessThan(0);
    expect(compareStatus('CUMPLE', 'NO_CUMPLE')).toBeLessThan(0);
  });

  it('returns positive when a is more severe than b', () => {
    expect(compareStatus('NO_CUMPLE', 'CUMPLE')).toBeGreaterThan(0);
  });

  it('returns 0 when equal', () => {
    expect(compareStatus('CUMPLE', 'CUMPLE')).toBe(0);
  });
});

describe('isBackendStatusString', () => {
  it('returns true for known strings', () => {
    for (const s of ['CUMPLE', 'FUERA DE TOLERANCIA', 'NO CUMPLE'] as const) {
      expect(isBackendStatusString(s)).toBe(true);
    }
  });

  it('returns false for unknown strings', () => {
    expect(isBackendStatusString('UNKNOWN')).toBe(false);
    expect(isBackendStatusString('whatever')).toBe(false);
  });
});

describe('STATUS_SEVERITY', () => {
  it('has a strictly increasing severity across the four statuses', () => {
    expect(STATUS_SEVERITY.UNKNOWN).toBeLessThan(STATUS_SEVERITY.CUMPLE);
    expect(STATUS_SEVERITY.CUMPLE).toBeLessThan(STATUS_SEVERITY.FUERA);
    expect(STATUS_SEVERITY.FUERA).toBeLessThan(STATUS_SEVERITY.NO_CUMPLE);
  });

  it('exposes exactly the four canonical statuses', () => {
    expect(Object.keys(STATUS_SEVERITY).sort()).toEqual(
      ['CUMPLE', 'FUERA', 'NO_CUMPLE', 'UNKNOWN'].sort(),
    );
  });
});

describe('STATUS_PRESENTATION_ORDER', () => {
  it('orders worst first', () => {
    expect(STATUS_PRESENTATION_ORDER[0]).toBe('NO_CUMPLE');
  });

  it('puts CUMPLE (best of the three real statuses) before UNKNOWN', () => {
    const cumpleIdx = STATUS_PRESENTATION_ORDER.indexOf('CUMPLE');
    const unknownIdx = STATUS_PRESENTATION_ORDER.indexOf('UNKNOWN');
    expect(cumpleIdx).toBeLessThan(unknownIdx);
  });

  it('exhausts all four statuses', () => {
    expect(new Set(STATUS_PRESENTATION_ORDER).size).toBe(4);
  });
});

describe('forEachStatus', () => {
  it('visits every status exactly once in presentation order', () => {
    const seen: BenchStatus[] = [];
    forEachStatus((s) => seen.push(s));
    expect(seen).toEqual([...STATUS_PRESENTATION_ORDER]);
  });
});

describe('formatStatus', () => {
  it('returns the canonical name', () => {
    expect(formatStatus('CUMPLE')).toBe('CUMPLE');
    expect(formatStatus('FUERA')).toBe('FUERA');
    expect(formatStatus('NO_CUMPLE')).toBe('NO_CUMPLE');
    expect(formatStatus('UNKNOWN')).toBe('UNKNOWN');
  });

  it('throws on an unknown status (exhaustiveness guard)', () => {
    // @ts-expect-error - testing runtime, not type
    expect(() => formatStatus('BOGUS')).toThrow();
  });
});

describe('assertNever', () => {
  it('throws when called with a value', () => {
    expect(() => assertNever('nope' as never)).toThrow(/Unhandled/);
  });
});
