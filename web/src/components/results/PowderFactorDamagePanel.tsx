import Plot from '../charts/Plot';
import type { Data, Layout, Config } from 'plotly.js';
import { useTranslation } from 'react-i18next';
import { useBlastDamageModel } from '../../api/hooks';
import {
  BlastSectionHeader,
  BLAST_PLOT_AXIS_BASE,
  BLAST_PLOT_LAYOUT_BASE,
  readBlastChartColors,
  useBlastChartColors,
  type BlastChartColors,
} from './blastLayout';
import type {
  BlastDamagePoint,
  BlastDamageModelFit,
} from '../../api/types';

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
 *
 * Pure (no React, no i18n) mapping so vitest can assert on the regression
 * overlay and the scatter shape without rendering Plotly. Mirrors the
 * formatting-helper export pattern in BlastCorrelation.tsx.
 */
export function buildDamageTraces(
  points: BlastDamagePoint[],
  fit: BlastDamageModelFit | null,
  colors: BlastChartColors = readBlastChartColors(),
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
    marker: { color: colors.secondary, size: 9, line: { color: colors.outline, width: 1 } },
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
      line: { color: colors.fit, width: 1.5, dash: 'solid' },
      name: 'Ajuste OLS',
    };
    traces.push(line);
  }

  return traces;
}

/**
 * PF↔damage scatter panel (G13 visual parity).
 *
 * Renders one Plotly marker per section (x = pf_g_per_ton, y = over_break)
 * with the fitted OLS line overlaid when the backend reports a non-null
 * fit. Mirrors the Streamlit reference's scatter + fitted damage line.
 *
 * The trace mapping lives in the pure ``buildDamageTraces`` helper above so
 * it is unit-testable without rendering Plotly. The dark-theme layout
 * matches the established Dashboard Plotly pattern (transparent bg, CSS
 * variable font color, compact margins).
 */
export function PowderFactorDamagePanel() {
  const { t } = useTranslation();
  const { data } = useBlastDamageModel();
  const colors = useBlastChartColors();

  const points = data?.points ?? [];
  const fit = data?.fit ?? null;

  if (points.length === 0) return null;

  const traces = buildDamageTraces(points, fit, colors);
  const showFit = Boolean(fit) && points.length >= DAMAGE_MODEL_MIN_SAMPLES;
  const insufficient =
    points.length < DAMAGE_MODEL_MIN_SAMPLES || !fit;

  const r2Text = fit
    ? `R² = ${fit.r_squared.toFixed(2)} · ${fit.confidence} · n = ${fit.n}`
    : '';

  return (
    <section
      className="flex min-w-0 flex-col gap-3"
      data-testid="blast-damage-chart"
    >
      <BlastSectionHeader
        title={t('blast.damage_title', {
          defaultValue: 'Factor de carga vs Sobre-excavación',
        })}
        aside={showFit && r2Text ? (
          <span className="font-mono text-xs tabular-nums text-text-muted" data-testid="blast-damage-fit">
            {r2Text}
          </span>
        ) : undefined}
      />
      <Plot
        data={traces as Data[]}
        layout={{
          ...BLAST_PLOT_LAYOUT_BASE,
          height: 320,
          margin: { l: 50, r: 12, t: 8, b: 48 },
          xaxis: {
            ...BLAST_PLOT_AXIS_BASE,
            title: {
              text: t('blast.damage_x_axis', {
                defaultValue: 'Factor de carga (g/ton)',
              }),
              font: { size: 11 },
            },
          },
          yaxis: {
            ...BLAST_PLOT_AXIS_BASE,
            title: {
              text: t('blast.damage_y_axis', {
                defaultValue: 'Over-break (m)',
              }),
              font: { size: 11 },
            },
          },
        } as Partial<Layout>}
        config={{ displayModeBar: false, responsive: true } as Partial<Config>}
        style={{ width: '100%' }}
      />
      {insufficient && (
        <p className="text-xs text-text-muted" data-testid="blast-damage-insufficient">
          {t('blast.damage_insufficient', {
            defaultValue:
              'Insuficientes secciones para ajustar el modelo (mínimo 5).',
          })}
        </p>
      )}
    </section>
  );
}
