import { Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import Plot from '../charts/Plot';
import type { Data, Layout, Config } from 'plotly.js';
import { useBlastCorrelation, useSections } from '../../api/hooks';
import { getSessionId } from '../../api/client';
import { BlastUploader } from './BlastUploader';
import { BlastHoles3DViewer } from './BlastHoles3DViewer';
import { BlastSimulationPanel } from './BlastSimulationPanel';
import { PowderFactorDamagePanel } from './PowderFactorDamagePanel';
import { BlastSectorDensityEditor } from './BlastSectorDensityEditor';
import { BlastCorrelationTable } from './BlastCorrelationTable';
import { GEOMETRY_CONFIGURATION_VERSION } from '../../api/types';
import { useBlastSettings } from './useBlastSettings';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import { Button } from '../ui/Button';
import {
  BlastSectionHeader,
  BLAST_PLOT_AXIS_BASE,
  BLAST_PLOT_LAYOUT_BASE,
  useBlastChartColors,
} from './blastLayout';
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

export function BlastCorrelation() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { designMeshId, topoMeshId } = useSession();
  const hasVirtualMesh = designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo;
  const { data, isLoading, error } = useBlastCorrelation();

  const rows: BlastCorrelationRow[] = data?.rows ?? [];
  const carga: number[] = data?.carga ?? [];
  const descarga: number[] = data?.descarga ?? [];

  if (isLoading) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-text-muted">
        {t('blast.loading', { defaultValue: 'Cargando…' })}
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="flex h-48 items-center justify-center gap-2 text-sm text-text-secondary">
        <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full bg-[var(--status-nok-text)]" />
        {t('blast.error', { defaultValue: 'Error al cargar datos de tronadura.' })}
      </div>
    );
  }

  const invalidateCorrelation = () => qc.invalidateQueries({ queryKey: ['blast-correlation'] });

  if (rows.length === 0) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 py-6">
        <div className="flex flex-col gap-1">
          <h2 className="ui-section-title">
            {t('blast.empty_title', { defaultValue: 'Sin datos de tronadura' })}
          </h2>
          <p className="text-xs leading-relaxed text-text-muted">
            {hasVirtualMesh
              ? t('blast.empty_demo_desc', {
                  defaultValue: 'La demo usa mallas virtuales y no incluye datos de tronadura.',
                })
              : t('blast.empty_desc', {
                  defaultValue:
                    'Cargue un archivo de pozos/tronadura y ejecute el análisis para ver el factor de carga por sección.',
                })}
          </p>
        </div>
        <BlastUploader onUploaded={invalidateCorrelation} />
      </div>
    );
  }

  const loadingFallback = (
    <p className="text-sm text-text-muted">
      {t('common.loading', { defaultValue: 'Cargando…' })}
    </p>
  );

  return (
    <div className="flex flex-col gap-6" data-slot="blast-correlation">
      <BlastSectionHeader
        as="h2"
        title={t('blast.summary_title', { defaultValue: 'Correlación de Tronadura' })}
        aside={
          <span className="ui-chip tabular-nums">
            {t('blast.n_sections', {
              defaultValue: '{{count}} secciones',
              count: rows.length,
            })}
          </span>
        }
      />

      <BlastUploader collapsible onUploaded={invalidateCorrelation} />

      <BlastDensityControl />

      <section className="flex flex-col gap-3">
        <BlastSectionHeader
          title={t('blast.table_title', { defaultValue: 'Factor de carga por sección' })}
        />
        <BlastCorrelationTable rows={rows} />
      </section>

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <PowderFactorDamagePanel />
        <BlastHistogramChart carga={carga} descarga={descarga} />
      </div>

      <Suspense fallback={loadingFallback}>
        <BlastHoles3DViewer sessionId={getSessionId()} />
      </Suspense>

      <Suspense fallback={loadingFallback}>
        <BlastSimulationPanel
          sessionId={getSessionId()}
          geometryConfigurationVersion={GEOMETRY_CONFIGURATION_VERSION}
        />
      </Suspense>
    </div>
  );
}

function BlastHistogramChart({ carga, descarga }: { carga: number[]; descarga: number[] }) {
  const { t } = useTranslation();
  const colors = useBlastChartColors();
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
    <section
      className="flex min-w-0 flex-col gap-3"
      data-testid="blast-histogram-chart"
    >
      <BlastSectionHeader
        title={t('blast.histogram_title', { defaultValue: 'Carga vs Descarga' })}
      />
      <Plot
        data={[
          {
            x: carga,
            type: 'histogram',
            name: t('blast.carga', { defaultValue: 'Carga' }),
            marker: { color: colors.primary },
            opacity: 0.7,
            xbins,
          },
          {
            x: descarga,
            type: 'histogram',
            name: t('blast.descarga', { defaultValue: 'Descarga' }),
            marker: { color: colors.secondary },
            opacity: 0.7,
            xbins,
          },
        ] as Data[]}
        layout={{
          ...BLAST_PLOT_LAYOUT_BASE,
          height: 320,
          barmode: 'overlay',
          margin: { l: 50, r: 12, t: 8, b: 48 },
          xaxis: {
            ...BLAST_PLOT_AXIS_BASE,
            title: {
              text: t('blast.histogram_x_axis', { defaultValue: 'Carga (kg)' }),
              font: { size: 11 },
            },
          },
          yaxis: {
            ...BLAST_PLOT_AXIS_BASE,
            title: {
              text: t('blast.histogram_y_axis', { defaultValue: 'Frecuencia' }),
              font: { size: 11 },
            },
          },
        } as Partial<Layout>}
        config={{ displayModeBar: false, responsive: true } as Partial<Config>}
        style={{ width: '100%' }}
      />
    </section>
  );
}

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

  const sectors = Array.from(
    new Set(
      (sectionsData ?? [])
        .map((s) => s.sector)
        .filter((sec) => typeof sec === 'string' && sec.trim() !== ''),
    ),
  ).sort();

  const inputCls =
    'w-24 rounded-md border border-border bg-surface px-2 py-1 text-xs tabular-nums text-text-primary outline-none focus:border-accent';

  return (
    <section className="flex flex-col gap-3" data-slot="blast-density-control">
      <BlastSectionHeader
        title={t('blast.density_section_title', { defaultValue: 'Parámetros de cálculo' })}
        info={t('blast.density_help', {
          defaultValue:
            'Ajusta el factor de carga (g/ton) por sección. Valor por defecto: 2,7 ton/m³.',
        })}
      />
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="blast-rock-density" className="text-xs text-text-muted">
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
            data-testid="blast-rock-density"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="blast-height-fallback" className="text-xs text-text-muted">
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
            data-testid="blast-height-fallback"
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={saveSettings}
          disabled={isPending || invalid}
          aria-label={t('blast.apply_aria', { defaultValue: 'Aplicar' })}
          data-testid="blast-apply-btn"
        >
          {isPending
            ? t('common.loading', { defaultValue: 'Cargando…' })
            : t('blast.apply', { defaultValue: 'Aplicar' })}
        </Button>
        {isError && (
          <span
            className="flex items-center gap-1.5 self-center text-xs text-text-secondary"
            role="alert"
            data-testid="blast-settings-error"
          >
            <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full bg-[var(--status-nok-text)]" />
            {t('blast.error', { defaultValue: 'Error al cargar los datos' })}
          </span>
        )}
      </div>
      <BlastSectorDensityEditor
        sectors={sectors}
        density={density}
        sectorDensity={sectorDensity}
        setSectorDensity={setSectorDensity}
      />
    </section>
  );
}
