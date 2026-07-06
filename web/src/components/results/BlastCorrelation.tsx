import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { useBlastCorrelation, useSettings, useUpdateSettings } from '../../api/hooks';
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
 *
 * A small controls panel (`BlastDensityControl`) at the top lets the
 * user tune the per-session rock density (ρ, ton/m³) and height
 * fallback (m). On "Aplicar" the values are PUT to `/settings` under
 * the `blast` block and the `['blast-correlation', ...]` query is
 * invalidated so the table refetches with the new ρ.
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
      <BlastDensityControl />
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

// ─── Per-session blast density / height control ─────────────
//
// Renders a compact control panel that lets the user override the
// session's rock density (ρ, ton/m³) and height fallback (m). Both
// values feed the per-mass powder factor (pf_g_per_ton). On "Aplicar"
// the values are PUT to /settings under the `blast` block, then the
// ['blast-correlation', ...] query is invalidated so the table above
// refetches with the new ρ.
//
// The inputs are initialised from the current settings (useSettings)
// and resync whenever the settings query data changes (e.g. after a
// successful PUT or an external update). We do NOT PUT on every
// keystroke — only when the user clicks "Aplicar", matching the
// Sidebar's explicit-save pattern for process settings.

const BLAST_DEFAULTS = { rock_density_tm3: 2.7, height_fallback_m: 15.0 };

export function BlastDensityControl() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();

  const [density, setDensity] = useState<number>(BLAST_DEFAULTS.rock_density_tm3);
  const [height, setHeight] = useState<number>(BLAST_DEFAULTS.height_fallback_m);

  // Resync local state whenever the settings query data changes.
  useEffect(() => {
    const b = settings?.blast;
    if (b) {
      setDensity(Number(b.rock_density_tm3 ?? BLAST_DEFAULTS.rock_density_tm3));
      setHeight(Number(b.height_fallback_m ?? BLAST_DEFAULTS.height_fallback_m));
    }
  }, [settings]);

  const invalid =
    !Number.isFinite(density) ||
    !Number.isFinite(height) ||
    density <= 0 ||
    height <= 0;

  const handleApply = () => {
    if (invalid) return;
    // Send only the blast block — the PUT router merges it into stored
    // settings without touching process/tolerances (exclude_unset merge).
    updateSettings.mutate({
      blast: {
        rock_density_tm3: density,
        height_fallback_m: height,
      },
    });
    // Refetch the correlation table so pf_g_per_ton recomputes with ρ.
    qc.invalidateQueries({ queryKey: ['blast-correlation'] });
  };

  const inputStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-surface)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-text-primary)',
  };
  const inputCls =
    'w-24 px-2 py-1 border rounded-md text-xs outline-none transition-colors focus:ring-2 focus:ring-accent/30 font-mono';

  return (
    <div
      className="flex flex-wrap items-end gap-3 rounded-lg border p-3 shrink-0"
      style={{
        borderColor: 'var(--color-border)',
        backgroundColor: 'var(--color-surface-muted)',
      }}
    >
      <div className="flex flex-col gap-1">
        <label
          htmlFor="blast-rock-density"
          className="text-xs font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('blast.rock_density', { defaultValue: 'Densidad de roca (ton/m³)' })}
        </label>
        <input
          id="blast-rock-density"
          type="number"
          inputMode="decimal"
          step="0.1"
          min="0"
          value={density}
          onChange={(e) => setDensity(Number(e.target.value))}
          className={inputCls}
          style={inputStyle}
          data-testid="blast-rock-density"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label
          htmlFor="blast-height-fallback"
          className="text-xs font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('blast.height_fallback', { defaultValue: 'Altura fallback (m)' })}
        </label>
        <input
          id="blast-height-fallback"
          type="number"
          inputMode="decimal"
          step="0.5"
          min="0"
          value={height}
          onChange={(e) => setHeight(Number(e.target.value))}
          className={inputCls}
          style={inputStyle}
          data-testid="blast-height-fallback"
        />
      </div>
      <button
        type="button"
        onClick={handleApply}
        disabled={updateSettings.isPending || invalid}
        className="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors disabled:opacity-50"
        style={{
          backgroundColor: 'var(--color-accent, #f97316)',
          color: 'white',
        }}
        aria-label={t('blast.apply_aria', { defaultValue: 'Aplicar' })}
        data-testid="blast-apply-btn"
      >
        {updateSettings.isPending
          ? t('common.loading', { defaultValue: 'Cargando…' })
          : t('blast.apply', { defaultValue: 'Aplicar' })}
      </button>
      {updateSettings.isError && (
        <span
          className="text-xs"
          style={{ color: 'var(--color-danger, #ef4444)' }}
          data-testid="blast-settings-error"
        >
          {t('blast.error', { defaultValue: 'Error al cargar los datos' })}
        </span>
      )}
      <p
        className="text-xs leading-relaxed"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t('blast.density_help', {
          defaultValue:
            'Ajusta el factor de carga (g/ton) por sección. Valor por defecto: 2,7 ton/m³.',
        })}
      </p>
    </div>
  );
}
