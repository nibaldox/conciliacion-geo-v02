import { useTranslation } from 'react-i18next';
import { useBlastCorrelation } from '../../api/hooks';
import type { BlastCorrelationRow } from '../../api/types';

// ─── Pure formatting helpers (exported for testing) ─────────
//
// Kept pure (no React, no i18n) so unit tests can assert on the
// numeric rendering without rendering the component. Mirrors the
// Dashboard.tsx helper-export pattern.

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

// ─── Component ──────────────────────────────────────────────

/**
 * Per-section blast-correlation table.
 *
 * Renders one row per section with powder-factor metrics. The
 * `pf_g_per_ton_avg` (g/ton) column is visually emphasized as the
 * primary KPI. Empty / loading / error states mirror sibling
 * results components.
 */
export function BlastCorrelation() {
  const { t } = useTranslation();
  const { data, isLoading, error } = useBlastCorrelation();

  const rows: BlastCorrelationRow[] = data?.rows ?? [];

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center h-48 text-sm"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t('blast.loading', { defaultValue: 'Cargando…' })}
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="flex items-center justify-center h-48 text-sm"
        style={{ color: 'var(--color-status-error, #ef4444)' }}
      >
        {t('blast.error', { defaultValue: 'Error al cargar datos de tronadura.' })}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center h-48 gap-2 text-center px-6"
      >
        <div className="text-4xl" aria-hidden="true">⚗️</div>
        <p
          className="text-sm font-semibold"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('blast.empty_title', { defaultValue: 'Sin datos de tronadura' })}
        </p>
        <p
          className="text-xs leading-relaxed max-w-md"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('blast.empty_desc', {
            defaultValue:
              'Cargue un archivo de pozos/tronadura y ejecute el análisis para ver el factor de carga por sección.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary header */}
      <div
        className="flex items-center justify-between border-b pb-3 shrink-0"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <p
          className="text-sm font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('blast.summary_title', { defaultValue: 'Correlación de Tronadura' })}
        </p>
        <span
          className="text-xs px-2.5 py-1 rounded-full font-semibold"
          style={{
            backgroundColor: 'var(--color-surface-muted)',
            color: 'var(--color-text-secondary)',
          }}
        >
          {t('blast.n_sections', {
            defaultValue: '{{count}} secciones',
            count: rows.length,
          })}
        </span>
      </div>

      {/* Table */}
      <div
        className="overflow-x-auto rounded-lg border"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <table className="w-full text-xs">
          <thead>
            <tr
              style={{
                backgroundColor: 'var(--color-surface-raised)',
                color: 'var(--color-text-secondary)',
              }}
            >
              <th className="text-left font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_section', { defaultValue: 'Sección' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_wells', { defaultValue: 'Pozos' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_total_kg', { defaultValue: 'Carga total' })}
              </th>
              {/* Highlighted primary column */}
              <th
                className="text-right font-mono font-bold uppercase tracking-wider px-3 py-2"
                style={{
                  backgroundColor: 'var(--color-accent-bg, rgba(249,115,22,0.12))',
                  color: 'var(--color-accent-bright, #f97316)',
                }}
              >
                {t('blast.col_pf_g_per_ton', { defaultValue: 'Factor de carga (g/ton)' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_pf_vol', { defaultValue: 'PF vol. (kg/m³)' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_pf_area', { defaultValue: 'PF área (kg/m²)' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_energy', { defaultValue: 'Energía (MJ)' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_over_break', { defaultValue: 'Over-break (m)' })}
              </th>
              <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_under_break', { defaultValue: 'Under-break (m)' })}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.section_name}
                className="border-t"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <td
                  className="px-3 py-2 font-mono"
                  style={{ color: 'var(--color-text-primary)' }}
                >
                  {row.section_name}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {row.num_wells}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {formatKg(row.total_kg)}
                </td>
                {/* Highlighted primary value */}
                <td
                  className="px-3 py-2 text-right tabular-nums font-extrabold text-sm"
                  style={{
                    backgroundColor: 'var(--color-accent-bg, rgba(249,115,22,0.08))',
                    color: 'var(--color-accent-bright, #f97316)',
                  }}
                >
                  {formatGramsPerTon(row.pf_g_per_ton_avg)}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {formatPowderFactor(row.pf_vol_avg_kgm3)}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {formatPowderFactor(row.pf_area_avg_kgm2)}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {formatMJ(row.energy_total_mj)}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-status-error, #ef4444)' }}
                >
                  {formatBreakMeters(row.avg_over_break)}
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-status-warning, #f59e0b)' }}
                >
                  {formatBreakMeters(row.avg_under_break)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
