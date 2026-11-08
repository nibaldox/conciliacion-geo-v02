import { Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import Plot from '../charts/Plot';
import type { Data, Layout, Config } from 'plotly.js';
import { useBlastCorrelation, useBlastDefinitions, useSections } from '../../api/hooks';
import { getSessionId } from '../../api/client';
import { BlastUploader } from './BlastUploader';
import { BlastHoles3DViewer } from './BlastHoles3DViewer';
import { BlastSimulationPanel } from './BlastSimulationPanel';
import { PowderFactorDamagePanel } from './PowderFactorDamagePanel';
import { BlastSectorDensityEditor } from './BlastSectorDensityEditor';
import { BlastCorrelationTable } from './BlastCorrelationTable';
import { BlastLegacyNotice } from './BlastLegacyNotice';
import { GEOMETRY_CONFIGURATION_VERSION } from '../../api/types';
import { useBlastSettings } from './useBlastSettings';
import { BlastTemporalFilter } from './BlastTemporalFilter';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import { Button } from '../ui/Button';
import {
  BlastSectionHeader,
  BLAST_PLOT_AXIS_BASE,
  BLAST_PLOT_LAYOUT_BASE,
  useBlastChartColors,
} from './blastLayout';
import { useBlastView } from '../../stores/blastView';
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
import type { BlastCorrelationRow, BlastDefinitions } from '../../api/types';

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

export interface BlastCorrelationProps {
  presentation?: 'legacy' | 'analysis';
  onData?: () => void;
}

export function BlastCorrelation({ presentation = 'legacy', onData }: BlastCorrelationProps = {}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { designMeshId, topoMeshId } = useSession();
  const hasVirtualMesh = designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo;
  const isAnalysis = presentation === 'analysis';
  const [localSurveyDate, setLocalSurveyDate] = useState('');
  const storeSurveyDate = useBlastView((s) => s.surveyDate);
  const setWorkspaceTab = useBlastView((s) => s.setWorkspaceTab);
  const openData = onData ?? (() => { setWorkspaceTab('data'); document.querySelector<HTMLDetailsElement>('[data-testid="blast-uploader"] details')?.setAttribute('open', ''); document.querySelector('[data-testid="blast-uploader"]')?.scrollIntoView?.(); });
  const setStoreSurveyDate = useBlastView((s) => s.setSurveyDate);
  const surveyDate = isAnalysis ? storeSurveyDate : localSurveyDate;
  const setSurveyDate = isAnalysis ? setStoreSurveyDate : setLocalSurveyDate;
  const { data: definitions } = useBlastDefinitions();
  const { data, isLoading, error } = useBlastCorrelation(surveyDate || undefined);
  const legacyNotice = data?.data_status === 'legacy_reimport_required' ? <BlastLegacyNotice onData={openData} /> : null;
  const temporalControl = <BlastTemporalFilter surveyDate={surveyDate} onApply={setSurveyDate} metadata={data?.temporal_filter} />;
  const refreshAnalysis = () => Promise.all([
    qc.invalidateQueries({ queryKey: ['blast-correlation'] }),
    qc.invalidateQueries({ queryKey: ['blast-damage-model'] }),
  ]);

  const rows: BlastCorrelationRow[] = data?.rows ?? [];
  const emptyAfterCutoff = Boolean(surveyDate && data?.temporal_filter?.enabled && data.temporal_filter.included === 0 && data.temporal_filter.excluded + data.temporal_filter.missing > 0);
  const carga: number[] = data?.carga ?? [];
  const descarga: number[] = data?.descarga ?? [];

  if (isLoading) {
    return (
      <div className="space-y-4">{temporalControl}<div className="flex h-48 items-center justify-center text-sm text-text-muted">
        {t('blast.loading', { defaultValue: 'Cargando…' })}
      </div></div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">{temporalControl}<div role="alert" className="flex h-48 items-center justify-center gap-2 text-sm text-text-secondary">
        <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full bg-[var(--status-nok-text)]" />
        {t('blast.error', { defaultValue: 'Error al cargar datos de tronadura.' })}
      </div></div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="space-y-4">{temporalControl}{legacyNotice}<div className="mx-auto flex w-full max-w-2xl flex-col gap-6 py-6">
        <div className="flex flex-col gap-1">
          <h2 className="ui-section-title">
            {emptyAfterCutoff ? t('blast.temporal.emptyTitle') : t('blast.empty_title', { defaultValue: 'Sin datos de tronadura' })}
          </h2>
          <p className="text-xs leading-relaxed text-text-muted">
            {emptyAfterCutoff ? t('blast.temporal.emptyDescription') : hasVirtualMesh
              ? t('blast.empty_demo_desc', {
                  defaultValue: 'La demo usa mallas virtuales y no incluye datos de tronadura.',
                })
              : t('blast.empty_desc', {
                  defaultValue:
                    'Cargue un archivo de pozos/tronadura y ejecute el análisis para ver el factor de carga por sección.',
                })}
          </p>
        </div>
        {!isAnalysis && <BlastUploader onUploaded={refreshAnalysis} />}
      </div></div>
    );
  }

  const loadingFallback = (
    <p className="text-sm text-text-muted">
      {t('common.loading', { defaultValue: 'Cargando…' })}
    </p>
  );

  return (
    <div className="flex flex-col gap-6" data-slot="blast-correlation">
      {temporalControl}
      {legacyNotice}
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

      {!isAnalysis && <BlastUploader collapsible onUploaded={refreshAnalysis} />}

      <BlastDensityControl />

      <section className="flex flex-col gap-3">
        <BlastSectionHeader
          title={t('blast.table_title', { defaultValue: 'Factor de carga por sección' })}
        />
        <BlastCorrelationTable rows={rows} definitions={definitions} />
      </section>

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <PowderFactorDamagePanel surveyDate={surveyDate || undefined} totalSections={rows.length} onData={openData} />
        <BlastHistogramChart carga={data?.kg_per_meter ?? carga} loadedColumn={data?.kg_per_meter_loaded_column ?? []} descarga={descarga} definitions={definitions} />
      </div>

      {!isAnalysis && (
        <>
          <Suspense fallback={loadingFallback}>
            <BlastHoles3DViewer sessionId={getSessionId()} />
          </Suspense>
          <Suspense fallback={loadingFallback}>
            <BlastSimulationPanel sessionId={getSessionId()} geometryConfigurationVersion={GEOMETRY_CONFIGURATION_VERSION} />
          </Suspense>
        </>
      )}
    </div>
  );
}

function BlastHistogramChart({ carga, loadedColumn, descarga, definitions }: { carga: number[]; loadedColumn: number[]; descarga: number[]; definitions?: BlastDefinitions }) {
  const { t } = useTranslation();
  const colors = useBlastChartColors();
  const [metric, setMetric] = useState<'kg_per_meter' | 'kg_per_meter_loaded_column'>('kg_per_meter');
  const values = metric === 'kg_per_meter' ? carga : loadedColumn;
  const label = t(metric === 'kg_per_meter' ? 'blast.charge_density_histogram_title' : 'blast.loaded_column_density');
  if (carga.length === 0 && loadedColumn.length === 0 && descarga.length === 0) return null;

  return (
    <section className="flex min-w-0 flex-col gap-3" data-testid="blast-histogram-chart">
      <BlastSectionHeader title={t('blast.histograms_title')} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="min-w-0" data-testid="blast-charge-density-histogram">
          <label htmlFor="charge-density-metric" className="text-xs text-text-secondary">{t('blast.charge_metric_selector')}</label>
          <select id="charge-density-metric" value={metric} onChange={(event) => setMetric(event.target.value as typeof metric)} className="block max-w-full rounded border border-border bg-surface text-text-primary">
            <option value="kg_per_meter">{t('blast.charge_density_histogram_title')}</option>
            <option value="kg_per_meter_loaded_column">{t('blast.loaded_column_density')}</option>
          </select>
          <p className="text-xs text-text-secondary">{t('blast.hole_count', { count: values.length })}</p>
          {definitions?.[metric]?.formula && <p className="text-xs text-text-secondary">{definitions[metric].formula}</p>}
          {values.length > 0 && <HistogramPlot values={values} title={label} xAxisTitle={label} color={colors.primary} testId="blast-charge-density-plot" />}
        </div>
        {descarga.length > 0 && <HistogramPlot values={descarga} title={t('blast.loaded_length_histogram_title')} xAxisTitle={t('blast.loaded_length_histogram_x_axis')} color={colors.secondary} testId="blast-loaded-length-histogram" />}
      </div>
    </section>
  );
}

function buildHistogramSeries(values: number[], binCount = 20) {
  const finite = values.filter(Number.isFinite);
  let min = finite[0] ?? 0;
  let max = finite[0] ?? 0;
  for (const value of finite) {
    min = Math.min(min, value);
    max = Math.max(max, value);
  }
  const width = max === min ? 1 : (max - min) / binCount;
  const midpoints = Array.from({ length: binCount }, (_, index) => min + (index + 0.5) * width);
  const counts = new Array<number>(binCount).fill(0);
  for (const value of finite) {
    const index = Math.min(binCount - 1, Math.floor((value - min) / width));
    counts[index] += 1;
  }
  return { midpoints, counts };
}

function HistogramPlot({
  values,
  title,
  xAxisTitle,
  color,
  testId,
}: {
  values: number[];
  title: string;
  xAxisTitle: string;
  color: string;
  testId: string;
}) {
  const { t } = useTranslation();
  const series = buildHistogramSeries(values);
  return (
    <div className="min-w-0" data-testid={testId}>
      <p className="text-xs font-semibold mb-1" style={{ color: 'var(--color-text-secondary)' }}>{title}</p>
      <Plot
        data={[{
          x: series.midpoints,
          y: series.counts,
          type: 'bar',
          name: title,
          marker: { color },
        }] as Data[]}
        layout={{
          ...BLAST_PLOT_LAYOUT_BASE,
          height: 280,
          margin: { l: 55, r: 20, t: 12, b: 50 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: 'var(--color-text-secondary)', size: 11 },
          xaxis: {
            ...BLAST_PLOT_AXIS_BASE,
            title: { text: xAxisTitle, font: { size: 11 } },
            gridcolor: 'var(--color-border)',
            zeroline: false,
          },
          yaxis: {
            ...BLAST_PLOT_AXIS_BASE,
            title: { text: t('blast.histogram_y_axis_wells', { defaultValue: 'Pozos por intervalo' }), font: { size: 11 } },
            gridcolor: 'var(--color-border)',
            zeroline: false,
          },
          showlegend: false,
        } as Partial<Layout>}
        config={{ displayModeBar: false, responsive: true } as Partial<Config>}
        style={{ width: '100%' }}
      />
    </div>
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
