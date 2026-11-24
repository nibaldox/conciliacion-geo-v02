import { describe, expect, it } from 'vitest';
import {
  formatDegrees,
  formatDeviation,
  formatFileSize,
  formatLocaleNumber,
  formatLocalePercent,
  formatLocaleSigned,
  formatMeters,
  formatPct,
  getMatchClass,
  getStatusClass,
  resolveNumberLocale,
} from '../format';

describe('resolveNumberLocale', () => {
  it('resolves English languages to en-US and defaults everything else to es-CL', () => {
    expect(resolveNumberLocale('en')).toBe('en-US');
    expect(resolveNumberLocale('en-GB')).toBe('en-US');
    expect(resolveNumberLocale('EN-us')).toBe('en-US');
    expect(resolveNumberLocale('es')).toBe('es-CL');
    expect(resolveNumberLocale('es-CL')).toBe('es-CL');
    expect(resolveNumberLocale(undefined)).toBe('es-CL');
    expect(resolveNumberLocale('')).toBe('es-CL');
  });
});

describe('formatLocaleNumber', () => {
  it('formats numbers according to locale and decimal precision', () => {
    expect(formatLocaleNumber(1234.56, 'es')).toBe('1.234,6');
    expect(formatLocaleNumber(1234.56, 'en')).toBe('1,234.6');
    expect(formatLocaleNumber(48.5, 'es-CL', 2)).toBe('48,50');
    expect(formatLocaleNumber(48.5, 'en-US', 0)).toBe('49');
    expect(formatLocaleNumber(-0, 'es', 1)).toBe('0,0');
  });

  it('returns an em dash for null, undefined, and non-finite inputs', () => {
    expect(formatLocaleNumber(null, 'es')).toBe('—');
    expect(formatLocaleNumber(undefined, 'en')).toBe('—');
    expect(formatLocaleNumber(Number.NaN, 'es')).toBe('—');
    expect(formatLocaleNumber(Number.POSITIVE_INFINITY, 'es')).toBe('—');
    expect(formatLocaleNumber(Number.NEGATIVE_INFINITY, 'en')).toBe('—');
  });
});

describe('formatLocaleSigned', () => {
  it('adds an explicit plus sign for non-negative numbers and preserves minus sign', () => {
    expect(formatLocaleSigned(2.34, 'es')).toBe('+2,3');
    expect(formatLocaleSigned(2.34, 'en', 2, ' m')).toBe('+2.34 m');
    expect(formatLocaleSigned(-1.5, 'es', 1, '°')).toBe('-1,5°');
    expect(formatLocaleSigned(0, 'es', 1, ' m')).toBe('+0,0 m');
    expect(formatLocaleSigned(-0, 'en', 1)).toBe('+0.0');
  });

  it('returns an em dash for nullish or non-finite inputs', () => {
    expect(formatLocaleSigned(null, 'es', 1, ' m')).toBe('—');
    expect(formatLocaleSigned(undefined, 'en', 1, ' m')).toBe('—');
    expect(formatLocaleSigned(Number.NaN, 'es', 1, ' m')).toBe('—');
  });
});

describe('formatLocalePercent', () => {
  it('formats 0–100 percentages with locale decimal separator and spaced percent sign', () => {
    expect(formatLocalePercent(48.5, 'es')).toBe('48,5 %');
    expect(formatLocalePercent(48.5, 'en')).toBe('48.5 %');
    expect(formatLocalePercent(100, 'es', 0)).toBe('100 %');
    expect(formatLocalePercent(null, 'es')).toBe('—');
    expect(formatLocalePercent(Number.POSITIVE_INFINITY, 'en')).toBe('—');
  });
});

describe('legacy formatting exports', () => {
  it('keeps existing helpers backwards-compatible', () => {
    expect(formatDeviation(1.2)).toBe('+1.20');
    expect(formatDeviation(-0.5)).toBe('-0.50');
    expect(formatDeviation(null)).toBe('—');
    expect(formatMeters(15)).toBe('15.00m');
    expect(formatDegrees(70.25)).toBe('70.3°');
    expect(getStatusClass('CUMPLE')).toBe('badge-ok');
    expect(getMatchClass('MATCH')).toBe('badge-ok');
    expect(formatPct(0.485)).toBe('48.5%');
    expect(formatFileSize(2048)).toBe('2.0 KB');
  });
});
