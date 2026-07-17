import { Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';
import { useBlastCorrelation, useSections } from '../../api/hooks';
import { getSessionId } from '../../api/client';
import { BlastUploader } from './BlastUploader';
import { BlastHoles3DViewer } from './BlastHoles3DViewer';
import { PowderFactorDamagePanel } from './PowderFactorDamagePanel';
import { BlastSectorDensityEditor } from './BlastSectorDensityEditor';
import { BlastCorrelationTable } from './BlastCorrelationTable';
import { useBlastSettings } from './useBlastSettings';
// Re-exports below kept for backwards-compat with existing tests:
//   - damage test suite imports `buildDamageTraces` / `DAMAGE_MODEL_MIN_SAMPLES`
//     (canonical home: PowderFactorDamagePanel.tsx)
//   - main / formatting tests import the `format*` helpers (canonical home:
//     blastFormatters.ts)
export {
  buildDamageTraces,
  DAMAGE_MODEL_MIN_SAMPLES,
} from './PowderFactorDamagePanel';
export {
  formatKg,
  formatMJ,
  formatGramsPerTon,
  formatPowderFactor,
  formatBreakMeters,
  formatDensityShort,
} from './blastFormatters';
import type { BlastCorrelationRow } from '../../api/types';

// ─── Histogram overlay helpers (G18) ────────────────────────

export interface HistogramBins {
  carga: number[];
  descarga: number[];
  binEdges: number[];
  binMidpoints: number[];
  countsCarga: number[];
  countsDescarga: number[];
}

function countIntoBins(values: number[], edges: number[]): number[] {
  const counts: number[] = new Array(Math.max(0, edges.length - 1)).fill(0);
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    let placed = false;
    for (let i = 0; i < edges.length - 1; i++) {
      if (v >= edges[i] && v < edges[i + 1]) {
        counts[i]++;
        placed = true;
        break;
      }
    }
    if (!placed && v === edges[edges.length - 1]) {
      counts[counts.length - 1]++;
    }
  }
  return counts;
}

export function buildOverlayHistogram(
  carga: number[],
  descarga: number[],
  binCount: number = 20,
): HistogramBins {
  const all = [...carga, ...descarga].filter(Number.isFinite);
  const min = all.length > 0 ? Math.min(...all) : 0;
  const max = all.length > 0 ? Math.max(...all) : 0;
  const range = max === min ? 1 : max - min;
  const binWidth = range / binCount;

  const binEdges: number[] = [];
  for (let i = 0; i <= binCount; i++) {
    binEdges.push(min + i * binWidth);
  }

  const binMidpoints: number[] = [];
  for (let i = 0; i < binCount; i++) {
    binMidpoints.push((binEdges[i] + binEdges[i + 1]) / 2);
  }

  return {
    carga,
    descarga,
    binEdges,
    binMidpoints,
    countsCarga: countIntoBins(carga, binEdges),
    countsDescarga: countIntoBins(descarga, binEdges),
  };
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
  const qc = useQueryClient();
  const { data, isLoading, error } = useBlastCorrelation();

  const rows: BlastCorrelationRow[] = data?.rows ?? [];
  const carga: number[] = data?.carga ?? [];
  const descarga: number[] = data?.descarga ?? [];

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
        className="flex flex-col items-center justify-center h-auto min-h-48 gap-3 text-center px-6 py-6"
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
        <div className="w-full max-w-md">
          <BlastUploader
            onUploaded={() => qc.invalidateQueries({ queryKey: ['blast-correlation'] })}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <BlastUploader
        onUploaded={() => qc.invalidateQueries({ queryKey: ['blast-correlation'] })}
      />
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
      <BlastCorrelationTable rows={rows} />

      {/* G13 visual: PF↔damage scatter with OLS regression overlay */}
      <PowderFactorDamagePanel />

      {/* G18 visual: histogram overlay of charge vs discharge */}
      <BlastHistogramChart carga={carga} descarga={descarga} />

      {/* G11 phase 3: 3D viewer of blast holes */}
      <Suspense
        fallback={
          <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
            {t('common.loading', { defaultValue: 'Cargando…' })}
          </p>
        }
      >
        <BlastHoles3DViewer sessionId={getSessionId()} />
      </Suspense>
    </div>
  );
}

// ─── Histogram overlay chart (G18) ──────────────────────────

function BlastHistogramChart({ carga, descarga }: { carga: number[]; descarga: number[] }) {
  const { t } = useTranslation();
  const hasData = carga.length > 0 || descarga.length > 0;
  if (!hasData) return null;

  const bins = buildOverlayHistogram(carga, descarga, 20);
  const binSize = bins.binEdges.length > 1 ? bins.binEdges[1] - bins.binEdges[0] : 1;
  const xbins = {
    start: bins.binEdges[0],
    end: bins.binEdges[bins.binEdges.length - 1],
    size: binSize,
  };

  return (
    <div
      className="glass-panel rounded-xl p-5 space-y-3"
      data-testid="blast-histogram-chart"
    >
      <p
        className="text-xs font-bold uppercase tracking-wider"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {t('blast.histogram_title', { defaultValue: 'Carga vs Descarga' })}
      </p>
      <Plot
        data={[
          {
            x: carga,
            type: 'histogram',
            name: t('blast.carga', { defaultValue: 'Carga' }),
            marker: { color: '#3b82f6' },
            opacity: 0.7,
            xbins,
          },
          {
            x: descarga,
            type: 'histogram',
            name: t('blast.descarga', { defaultValue: 'Descarga' }),
            marker: { color: '#ef4444' },
            opacity: 0.7,
            xbins,
          },
        ] as Data[]}
        layout={{
          height: 340,
          barmode: 'overlay',
          margin: { l: 55, r: 20, t: 24, b: 50 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: 'var(--color-text-secondary)', size: 11 },
          xaxis: {
            title: {
              text: t('blast.histogram_x_axis', { defaultValue: 'Carga (kg)' }),
              font: { size: 11 },
            },
            gridcolor: 'var(--color-border)',
            zeroline: false,
          },
          yaxis: {
            title: {
              text: t('blast.histogram_y_axis', { defaultValue: 'Frecuencia' }),
              font: { size: 11 },
            },
            gridcolor: 'var(--color-border)',
            zeroline: false,
          },
          legend: { orientation: 'h', y: -0.22, font: { size: 10 } },
        } as Partial<Layout>}
        config={{ displayModeBar: false, responsive: true } as Partial<Config>}
        style={{ width: '100%' }}
      />
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
// All settings state, sync, and save-side-effect wiring is owned by
// the ``useBlastSettings`` hook so this component stays purely
// presentational.

export function BlastDensityControl() {
  const { t } = useTranslation();
  const { data: sectionsData } = useSections();

  const {
    density,
    setDensity,
    height,
    setHeight,
    sectorDensity,
    setSectorDensity,
    invalid,
    isPending,
    isError,
    saveSettings,
  } = useBlastSettings();

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
        onClick={saveSettings}
        disabled={isPending || invalid}
        className="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors disabled:opacity-50"
        style={{
          backgroundColor: 'var(--color-accent, #f97316)',
          color: 'white',
        }}
        aria-label={t('blast.apply_aria', { defaultValue: 'Aplicar' })}
        data-testid="blast-apply-btn"
      >
        {isPending
          ? t('common.loading', { defaultValue: 'Cargando…' })
          : t('blast.apply', { defaultValue: 'Aplicar' })}
      </button>
      {isError && (
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
      <BlastSectorDensityEditor
        sectors={sectors}
        density={density}
        sectorDensity={sectorDensity}
        setSectorDensity={setSectorDensity}
      />
    </div>
  );
}

