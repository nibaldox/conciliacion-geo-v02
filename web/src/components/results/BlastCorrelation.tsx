import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';
import { useBlastCorrelation, useBlastDamageModel, useSections, useSettings, useUpdateSettings } from '../../api/hooks';
import type {
  BlastCorrelationRow,
  BlastDamagePoint,
  BlastDamageModelFit,
} from '../../api/types';

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

/** Format the effective rock density (ρ, ton/m³) with 2 decimals (e.g. "2.70"). */
export function formatDensityShort(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(2);
}

// ─── PF↔damage chart helpers (exported for testing) ─────────
//
// Pure (no React, no i18n) mapping from the damage-model payload to
// Plotly traces, so vitest can assert on the regression overlay and
// the scatter shape without rendering Plotly. Mirrors the formatting-
// helper export pattern above and the Dashboard's pure-helper style.

/** Minimum number of valid points required to fit the OLS model. */
export const DAMAGE_MODEL_MIN_SAMPLES = 5;

/**
 * Build the Plotly traces for the PF↔damage scatter chart.
 *
 * Always emits the scatter trace (one marker per section). When a non-null
 * ``fit`` with at least ``DAMAGE_MODEL_MIN_SAMPLES`` points is supplied,
 * also emits a regression line trace spanning the x-range of the points
 * (y = beta0 + beta1 * x evaluated at min/max x). Returns an empty array
 * when there are no points.
 */
export function buildDamageTraces(
  points: BlastDamagePoint[],
  fit: BlastDamageModelFit | null,
): Partial<Data>[] {
  if (!points || points.length === 0) return [];

  const xs = points.map((p) => p.pf_g_per_ton);
  const ys = points.map((p) => p.over_break);
  const names = points.map((p) => p.section_name);

  const scatter: Partial<Data> = {
    type: 'scatter',
    mode: 'markers',
    x: xs,
    y: ys,
    text: names,
    hovertemplate: '<b>%{text}</b><br>PF: %{x:.2f} g/ton<br>Over-break: %{y:.2f} m<extra></extra>',
    marker: { color: '#f97316', size: 10, line: { color: '#ffffff', width: 1 } },
    name: 'Secciones',
  };

  const traces: Partial<Data>[] = [scatter];

  if (fit && points.length >= DAMAGE_MODEL_MIN_SAMPLES) {
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    const yMin = fit.beta0 + fit.beta1 * xMin;
    const yMax = fit.beta0 + fit.beta1 * xMax;
    const line: Partial<Data> = {
      type: 'scatter',
      mode: 'lines',
      x: [xMin, xMax],
      y: [yMin, yMax],
      hoverinfo: 'skip',
      line: { color: '#ef4444', width: 2, dash: 'solid' },
      name: 'Ajuste OLS',
    };
    traces.push(line);
  }

  return traces;
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
              <th className="text-left font-mono font-semibold uppercase tracking-wider px-3 py-2">
                {t('blast.col_sector', { defaultValue: 'Sector' })}
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
                {t('blast.col_pf_g_per_ton_net', { defaultValue: 'PF s/pasadura (g/ton)' })}
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
                  className="px-3 py-2 font-mono"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {row.sector ? (
                    <span>
                      {row.sector}
                      <span
                        className="ml-1 text-[10px] opacity-70"
                        data-testid={`row-sector-rho-${row.section_name}`}
                      >
                        ({formatDensityShort(row.rock_density_used)})
                      </span>
                    </span>
                  ) : (
                    <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                  )}
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
                {/* Additive net metric (bench height excluding sub-drill) */}
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {formatGramsPerTon(row.pf_g_per_ton_net_avg)}
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

      {/* G13 visual: PF↔damage scatter with OLS regression overlay */}
      <BlastDamageChart />
    </div>
  );
}

// ─── PF↔damage scatter chart (G13 visual parity) ────────────
//
// Renders one Plotly marker per section (x = pf_g_per_ton, y = over_break)
// with the fitted OLS line overlaid when the backend reports a non-null
// fit. Mirrors the Streamlit reference's scatter + fitted damage line.
// The trace mapping lives in the pure `buildDamageTraces` helper above so
// it is unit-testable without rendering Plotly. The dark-theme layout
// matches the established Dashboard Plotly pattern (transparent bg, CSS
// variable font color, compact margins).

function BlastDamageChart() {
  const { t } = useTranslation();
  const { data } = useBlastDamageModel();

  const points = data?.points ?? [];
  const fit = data?.fit ?? null;

  // Empty state: no points at all → nothing to draw. The table's own
  // empty state already covers the "no blast data" message; we only
  // render the chart once rows exist.
  if (points.length === 0) return null;

  const traces = buildDamageTraces(points, fit);
  const showFit = Boolean(fit) && points.length >= DAMAGE_MODEL_MIN_SAMPLES;
  const insufficient =
    points.length < DAMAGE_MODEL_MIN_SAMPLES || !fit;

  const r2Text = fit
    ? `R² = ${fit.r_squared.toFixed(2)} · ${fit.confidence} · n = ${fit.n}`
    : '';

  return (
    <div
      className="glass-panel rounded-xl p-5 space-y-3"
      data-testid="blast-damage-chart"
    >
      <p
        className="text-xs font-bold uppercase tracking-wider"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {t('blast.damage_title', {
          defaultValue: 'Factor de carga vs Sobre-excavación',
        })}
      </p>
      <Plot
        data={traces as Data[]}
        layout={{
          height: 340,
          margin: { l: 55, r: 20, t: 24, b: 50 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: 'var(--color-text-secondary)', size: 11 },
          xaxis: {
            title: {
              text: t('blast.damage_x_axis', {
                defaultValue: 'Factor de carga (g/ton)',
              }),
              font: { size: 11 },
            },
            gridcolor: 'var(--color-border)',
            zeroline: false,
          },
          yaxis: {
            title: {
              text: t('blast.damage_y_axis', {
                defaultValue: 'Over-break (m)',
              }),
              font: { size: 11 },
            },
            gridcolor: 'var(--color-border)',
            zeroline: false,
          },
          legend: { orientation: 'h', y: -0.22, font: { size: 10 } },
          annotations: showFit && r2Text
            ? [
                {
                  text: r2Text,
                  showarrow: false,
                  x: 0.99,
                  xanchor: 'right',
                  y: 0.99,
                  yanchor: 'top',
                  font: { size: 10, color: 'var(--color-text-muted)' },
                  bgcolor: 'rgba(0,0,0,0)',
                },
              ]
            : [],
        } as Partial<Layout>}
        config={{ displayModeBar: false, responsive: true } as Partial<Config>}
        style={{ width: '100%' }}
      />
      {insufficient && (
        <p
          className="text-xs"
          style={{ color: 'var(--color-text-muted)' }}
          data-testid="blast-damage-insufficient"
        >
          {t('blast.damage_insufficient', {
            defaultValue:
              'Insuficientes secciones para ajustar el modelo (mínimo 5).',
          })}
        </p>
      )}
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
  const { data: sectionsData } = useSections();
  const updateSettings = useUpdateSettings();

  const [density, setDensity] = useState<number>(BLAST_DEFAULTS.rock_density_tm3);
  const [height, setHeight] = useState<number>(BLAST_DEFAULTS.height_fallback_m);
  // Per-sector ρ overrides. Local edits are staged here and committed on
  // "Aplicar" alongside the global density / height. ``sectorDensity`` is a
  // sparse map: a sector present in the map overrides the global ρ for that
  // sector; absent sectors fall back to the global ``rock_density_tm3``.
  const [sectorDensity, setSectorDensity] = useState<Record<string, number>>({});

  // Distinct sectors present across the session's sections. The editor lists
  // one ρ input per sector so the user can tune each geotechnical domain.
  // An empty list (all sections carry sector="") renders a hint instead.
  const sectors = Array.from(
    new Set(
      (sectionsData ?? [])
        .map((s) => s.sector)
        .filter((sec) => typeof sec === 'string' && sec.trim() !== ''),
    ),
  ).sort();

  // Resync local state whenever the settings query data changes.
  useEffect(() => {
    const b = settings?.blast;
    if (b) {
      setDensity(Number(b.rock_density_tm3 ?? BLAST_DEFAULTS.rock_density_tm3));
      setHeight(Number(b.height_fallback_m ?? BLAST_DEFAULTS.height_fallback_m));
      // Merge stored sector densities into local state without dropping any
      // sector the user is actively editing. Stored values win on reload.
      const stored = b.sector_density ?? {};
      setSectorDensity((prev) => {
        const merged: Record<string, number> = {};
        for (const sec of Object.keys({ ...prev, ...stored })) {
          const sv = Number(stored[sec]);
          merged[sec] = Number.isFinite(sv) ? sv : Number(prev[sec]);
        }
        return merged;
      });
    }
  }, [settings]);

  const invalid =
    !Number.isFinite(density) ||
    !Number.isFinite(height) ||
    density <= 0 ||
    height <= 0 ||
    // Every sector override must be a positive finite number when present.
    Object.values(sectorDensity).some(
      (v) => !Number.isFinite(v) || v <= 0,
    );

  const handleApply = () => {
    if (invalid) return;
    // Send only the blast block — the PUT router merges it into stored
    // settings without touching process/tolerances (exclude_unset merge).
    // ``sector_density`` is sent in full (the router overwrites the stored
    // map wholesale, which is the intended apply semantics).
    updateSettings.mutate({
      blast: {
        rock_density_tm3: density,
        height_fallback_m: height,
        sector_density: { ...sectorDensity },
      },
    });
    // Refetch the correlation table + damage model so pf_g_per_ton and the
    // OLS fit recompute with the new per-sector ρ.
    qc.invalidateQueries({ queryKey: ['blast-correlation'] });
    qc.invalidateQueries({ queryKey: ['blast-damage-model'] });
  };

  const inputStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-surface)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-text-primary)',
  };
  const inputCls =
    'w-24 px-2 py-1 border rounded-md text-xs outline-none transition-colors focus:ring-2 focus:ring-accent/30 font-mono';
  const sectorInputCls =
    'w-20 px-2 py-1 border rounded-md text-xs outline-none transition-colors focus:ring-2 focus:ring-accent/30 font-mono';

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
        className="text-xs leading-relaxed basis-full"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t('blast.density_help', {
          defaultValue:
            'Ajusta el factor de carga (g/ton) por sección. Valor por defecto: 2,7 ton/m³.',
        })}
      </p>
      {/* Per-sector ρ editor */}
      <div
        className="flex flex-col gap-2 basis-full pt-2 border-t"
        style={{ borderColor: 'var(--color-border)' }}
        data-testid="blast-sector-density-editor"
      >
        <p
          className="text-xs font-semibold"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('blast.sector_density_title', { defaultValue: 'Densidad por sector' })}
        </p>
        {sectors.length === 0 ? (
          <p
            className="text-xs"
            style={{ color: 'var(--color-text-muted)' }}
            data-testid="blast-sector-density-empty"
          >
            {t('blast.sector_density_empty', {
              defaultValue:
                'Asigne un sector a cada sección para definir una densidad específica.',
            })}
          </p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {sectors.map((sec) => (
              <div key={sec} className="flex flex-col gap-1">
                <label
                  htmlFor={`blast-sector-rho-${sec}`}
                  className="text-xs font-mono"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {sec}
                </label>
                <input
                  id={`blast-sector-rho-${sec}`}
                  type="number"
                  inputMode="decimal"
                  step="0.1"
                  min="0"
                  placeholder={String(density)}
                  value={sectorDensity[sec] ?? ''}
                  onChange={(e) => {
                    const v = e.target.value;
                    setSectorDensity((prev) => {
                      const next = { ...prev };
                      if (v === '') {
                        delete next[sec];
                      } else {
                        const num = Number(v);
                        if (Number.isFinite(num)) next[sec] = num;
                      }
                      return next;
                    });
                  }}
                  className={sectorInputCls}
                  style={inputStyle}
                  data-testid={`blast-sector-rho-${sec}`}
                />
              </div>
            ))}
            <p
              className="text-xs leading-relaxed self-center"
              style={{ color: 'var(--color-text-muted)' }}
            >
              {t('blast.sector_density_help', {
                defaultValue:
                  'Vacío = usar densidad global. Cada sector anula la densidad solo en sus secciones.',
              })}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
