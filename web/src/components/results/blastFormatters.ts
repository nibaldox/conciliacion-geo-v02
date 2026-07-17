/**
 * Pure formatting helpers for the blast-correlation table (exported for
 * testing). Kept React- and i18n-free so unit tests can assert on the
 * numeric rendering without rendering the component. Mirrors the
 * Dashboard.tsx helper-export pattern.
 */

/** Format a kilograms value with 1 decimal (e.g. "1234.5 kg"). */
export function formatKg(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toFixed(1)} kg`;
}

/** Format an energy value in megajoules with 0 decimals (e.g. "8421 MJ"). */
export function formatMJ(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${Math.round(value).toLocaleString('es-CL')} MJ`;
}

/** Format the highlighted powder factor g/ton with 2 decimals. */
export function formatGramsPerTon(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(2);
}

/** Format a generic powder-factor term (kg/m³ or kg/m²) with 3 decimals. */
export function formatPowderFactor(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(3);
}

/** Format an over/under-break length in metres with 2 decimals. */
export function formatBreakMeters(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(2);
}

/** Format the effective rock density (ρ, ton/m³) with 2 decimals (e.g. "2.70"). */
export function formatDensityShort(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(2);
}