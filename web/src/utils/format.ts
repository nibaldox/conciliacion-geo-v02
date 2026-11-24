/** Format a deviation value with sign */
export function formatDeviation(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}`;
}

/** Format elevation/height in meters */
export function formatMeters(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—';
  return `${value.toFixed(decimals)}m`;
}

/** Format angle in degrees */
export function formatDegrees(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—';
  return `${value.toFixed(decimals)}°`;
}

/** Get status color class from status text */
export function getStatusClass(status: string): string {
  if (!status) return '';
  const s = status.toUpperCase();
  if (s === 'CUMPLE') return 'badge-ok';
  if (s.includes('FUERA')) return 'badge-warn';
  if (s.includes('NO CUMPLE')) return 'badge-nok';
  if (s === 'EXTRA') return 'badge-extra';
  if (s === 'MISSING') return 'badge-missing';
  return '';
}

/** Get match type badge class */
export function getMatchClass(type: string): string {
  switch (type) {
    case 'MATCH': return 'badge-ok';
    case 'MISSING': return 'badge-missing';
    case 'EXTRA': return 'badge-extra';
    default: return '';
  }
}

/** Format percentage */
export function formatPct(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Format file size */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const numberFormatCache = new Map<string, Intl.NumberFormat>();

export function resolveNumberLocale(language?: string): string {
  return language?.toLowerCase().startsWith('en') ? 'en-US' : 'es-CL';
}

function getNumberFormatter(language: string | undefined, decimals: number): Intl.NumberFormat {
  const locale = resolveNumberLocale(language);
  const digits = Math.max(0, Math.floor(decimals));
  const key = `${locale}:${digits}`;
  let formatter = numberFormatCache.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    numberFormatCache.set(key, formatter);
  }
  return formatter;
}

export function formatLocaleNumber(
  value: number | null | undefined,
  language?: string,
  decimals = 1,
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const normalized = Object.is(value, -0) ? 0 : value;
  return getNumberFormatter(language, decimals).format(normalized);
}

export function formatLocaleSigned(
  value: number | null | undefined,
  language?: string,
  decimals = 1,
  unit = '',
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const normalized = Object.is(value, -0) ? 0 : value;
  const sign = normalized >= 0 ? '+' : '';
  return `${sign}${getNumberFormatter(language, decimals).format(normalized)}${unit}`;
}

export function formatLocalePercent(
  value: number | null | undefined,
  language?: string,
  decimals = 1,
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${formatLocaleNumber(value, language, decimals)} %`;
}
