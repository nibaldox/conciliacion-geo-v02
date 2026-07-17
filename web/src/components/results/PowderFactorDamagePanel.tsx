import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';
import { useTranslation } from 'react-i18next';
import { useBlastDamageModel } from '../../api/hooks';
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