import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { Annotation, Config, Data, Layout, Shape } from 'plotly.js';
import type { ComparisonResult, Tolerances } from '../../../api/types';
import { DEFAULT_TOLERANCES } from '../../../utils/constants';
import { formatLocaleNumber, formatLocaleSigned } from '../../../utils/format';
import { resolveThemeVariables } from '../../../utils/theme';
import Plot from '../../charts/Plot';
import { statusToneColor } from '../SummaryControls';
import { computeMedian } from './geotechSelectors';

export interface DeviationHistogramsGridProps {
  readonly rows: readonly ComparisonResult[];
  readonly tolerances: Tolerances;
  readonly isDark: boolean;
}

export type MiniHistogramBand =
  | { readonly neg: number; readonly pos: number }
  | { readonly min: number; readonly max?: number };

export interface BuildMiniHistogramSpecParams {
  readonly values: readonly number[];
  readonly title: string;
  readonly xLabel: string;
  readonly frequencyLabel: string;
  readonly band: MiniHistogramBand;
  readonly bandLabel: string;
  readonly isDark: boolean;
}

export interface MiniHistogramSpec {
  readonly n: number;
  readonly median: number | null;
  readonly outOfTolCount: number;
  readonly outOfTolPct: number | null;
  readonly data: Data[];
  readonly layout: Partial<Layout>;
}

type MatchNumericField = 'height_dev' | 'angle_dev' | 'delta_crest' | 'delta_toe' | 'berm_real';

const PLOT_CONFIG: Partial<Config> = {
  displayModeBar: false,
  responsive: true,
};

const DARK_BAND_FILL = 'rgba(57, 171, 96, 0.20)';
const LIGHT_BAND_FILL = 'rgba(29, 107, 63, 0.16)';

function isWithinBand(value: number, band: MiniHistogramBand): boolean {
  if ('min' in band) {
    if (band.max != null && Number.isFinite(band.max)) {
      return value >= band.min && value <= band.max;
    }
    return value >= band.min;
  }
  return value >= -Math.abs(band.neg) && value <= Math.abs(band.pos);
}

function computeSharedBins(
  values: readonly number[],
  band: MiniHistogramBand,
): { start: number; end: number; size: number } {
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const span = maxVal - minVal;
  if (span === 0) {
    const size = 'min' in band
      ? 1
      : Math.max(0.5, (Math.abs(band.neg) + Math.abs(band.pos)) / 4);
    return {
      start: minVal - size / 2,
      end: minVal + size / 2,
      size,
    };
  }
  const size = span / 14;
  const anchor = 'min' in band ? band.min : -Math.abs(band.neg);
  const start = anchor + Math.floor((minVal - anchor) / size) * size;
  const end = anchor + (Math.floor((maxVal - anchor) / size) + 1) * size + size * 1e-6;
  return { start, end, size };
}

function boundaryLineShape(x: number): Partial<Shape> {
  return {
    type: 'line',
    xref: 'x',
    yref: 'paper',
    x0: x,
    x1: x,
    y0: 0,
    y1: 1,
    line: {
      color: 'var(--status-ok-border)',
      width: 1,
      dash: 'dash',
    },
    layer: 'above',
  };
}

export function buildMiniHistogramSpec({
  values,
  title,
  xLabel,
  frequencyLabel,
  band,
  bandLabel,
  isDark,
}: BuildMiniHistogramSpecParams): MiniHistogramSpec {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  const n = finiteValues.length;
  const median = computeMedian(finiteValues);

  const withinValues: number[] = [];
  const outsideValues: number[] = [];
  for (const value of finiteValues) {
    if (isWithinBand(value, band)) {
      withinValues.push(value);
    } else {
      outsideValues.push(value);
    }
  }

  const outOfTolCount = outsideValues.length;
  const outOfTolPct = n > 0 ? (outOfTolCount / n) * 100 : null;

  const bandFill = isDark ? DARK_BAND_FILL : LIGHT_BAND_FILL;
  const shapes: Partial<Shape>[] = [];
  const annotations: Partial<Annotation>[] = [];

  if ('min' in band) {
    const hasFiniteMax = band.max != null && Number.isFinite(band.max) && band.max > band.min;
    const maxValue = n > 0 ? Math.max(...finiteValues) : band.min;
    const bandStart = band.min;
    const bandEnd = hasFiniteMax ? band.max! : (maxValue > band.min ? maxValue : band.min + 2);

    shapes.push({
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: bandStart,
      x1: bandEnd,
      y0: 0,
      y1: 1,
      fillcolor: bandFill,
      line: { width: 0 },
      layer: 'below',
    });
    shapes.push(boundaryLineShape(bandStart));
    if (hasFiniteMax) {
      shapes.push(boundaryLineShape(bandEnd));
    }

    annotations.push({
      xref: 'x',
      yref: 'paper',
      x: bandStart,
      y: 0.96,
      xanchor: 'left',
      xshift: 4,
      yanchor: 'top',
      text: bandLabel,
      showarrow: false,
      font: {
        size: 10,
        color: 'var(--status-ok-text)',
      },
    });
  } else {
    const bandStart = -Math.abs(band.neg);
    const bandEnd = Math.abs(band.pos);

    shapes.push({
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: bandStart,
      x1: bandEnd,
      y0: 0,
      y1: 1,
      fillcolor: bandFill,
      line: { width: 0 },
      layer: 'below',
    });
    shapes.push(boundaryLineShape(bandStart));
    shapes.push(boundaryLineShape(bandEnd));

    annotations.push({
      xref: 'x',
      yref: 'paper',
      x: (bandStart + bandEnd) / 2,
      y: 0.96,
      xanchor: 'center',
      yanchor: 'top',
      text: bandLabel,
      showarrow: false,
      font: {
        size: 10,
        color: 'var(--status-ok-text)',
      },
    });
  }

  const traces: Record<string, unknown>[] = [];
  if (n > 0) {
    const xbins = computeSharedBins(finiteValues, band);
    if (withinValues.length > 0) {
      traces.push({
        type: 'histogram',
        x: withinValues,
        xbins,
        marker: { color: 'var(--color-accent)' },
        name: title,
      });
    }
    if (outsideValues.length > 0) {
      traces.push({
        type: 'histogram',
        x: outsideValues,
        xbins,
        marker: { color: 'var(--status-nok-text)' },
        name: title,
      });
    }
  }

  const layout: Partial<Layout> = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { color: 'var(--color-text-secondary)', size: 11 },
    height: 190,
    margin: { l: 38, r: 10, t: 8, b: 34 },
    bargap: 0.08,
    barmode: 'stack',
    xaxis: { title: { text: xLabel, font: { size: 10 } }, zeroline: false },
    yaxis: { title: { text: frequencyLabel, font: { size: 10 } }, zeroline: false },
    shapes,
    annotations,
    showlegend: false,
  };

  return {
    n,
    median,
    outOfTolCount,
    outOfTolPct,
    data: traces as unknown as Data[],
    layout,
  };
}

function collectMatchField(
  rows: readonly ComparisonResult[],
  field: MatchNumericField,
): number[] {
  const out: number[] = [];
  for (const row of rows) {
    if (row.type !== 'MATCH') continue;
    const value = row[field];
    if (value != null && Number.isFinite(value)) {
      out.push(value);
    }
  }
  return out;
}

interface HistogramCardItem {
  readonly key: 'height' | 'angle' | 'crest' | 'toe' | 'berm';
  readonly title: string;
  readonly caption: string | null;
  readonly bermZeroCount: number;
  readonly formattedMedian: string;
  readonly spec: MiniHistogramSpec;
  readonly themedData: Data[];
}

export function DeviationHistogramsGrid({
  rows,
  tolerances,
  isDark,
}: DeviationHistogramsGridProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;

  const cards = useMemo<readonly HistogramCardItem[]>(() => {
    const heightNeg = Number(tolerances.bench_height?.neg ?? DEFAULT_TOLERANCES.bench_height.neg);
    const heightPos = Number(tolerances.bench_height?.pos ?? DEFAULT_TOLERANCES.bench_height.pos);
    const angleNeg = Number(tolerances.face_angle?.neg ?? DEFAULT_TOLERANCES.face_angle.neg);
    const anglePos = Number(tolerances.face_angle?.pos ?? DEFAULT_TOLERANCES.face_angle.pos);
    const crestNeg = Number(
      tolerances.crest_toe_deviation?.neg ?? DEFAULT_TOLERANCES.crest_toe_deviation.neg,
    );
    const crestPos = Number(
      tolerances.crest_toe_deviation?.pos ?? DEFAULT_TOLERANCES.crest_toe_deviation.pos,
    );
    const bermMin = Number(tolerances.berm_width?.min ?? DEFAULT_TOLERANCES.berm_width.min);
    const rawBermMax = tolerances.berm_width?.max;
    const bermMax =
      typeof rawBermMax === 'number' && Number.isFinite(rawBermMax) ? rawBermMax : undefined;

    const frequencyLabel = t('dashboard.plot.axis.frequency');
    const passLabel = t('dashboard.histograms.band_pass');
    const bermMinFormatted = formatLocaleNumber(bermMin, language, Number.isInteger(bermMin) ? 0 : 1);
    const bermBandLabel = t('dashboard.histograms.band_min', { min: bermMinFormatted });

    const heightValues = collectMatchField(rows, 'height_dev');
    const angleValues = collectMatchField(rows, 'angle_dev');
    const crestValues = collectMatchField(rows, 'delta_crest');
    const toeValues = collectMatchField(rows, 'delta_toe');
    const bermValues = collectMatchField(rows, 'berm_real');
    const bermZeroCount = bermValues.filter((value) => value === 0).length;

    const definitions: Array<{
      key: HistogramCardItem['key'];
      title: string;
      caption: string | null;
      values: number[];
      band: MiniHistogramBand;
      bandLabel: string;
      signed: boolean;
      unit: string;
      bermZeroCount: number;
    }> = [
      {
        key: 'height',
        title: t('dashboard.plot.axis.delta_height'),
        caption: t('dashboard.histograms.sign_height'),
        values: heightValues,
        band: { neg: heightNeg, pos: heightPos },
        bandLabel: passLabel,
        signed: true,
        unit: ' m',
        bermZeroCount: 0,
      },
      {
        key: 'angle',
        title: t('dashboard.plot.axis.delta_angle'),
        caption: t('dashboard.histograms.sign_angle'),
        values: angleValues,
        band: { neg: angleNeg, pos: anglePos },
        bandLabel: passLabel,
        signed: true,
        unit: '°',
        bermZeroCount: 0,
      },
      {
        key: 'crest',
        title: t('dashboard.plot.axis.delta_crest'),
        caption: t('dashboard.histograms.sign_crest'),
        values: crestValues,
        band: { neg: crestNeg, pos: crestPos },
        bandLabel: passLabel,
        signed: true,
        unit: ' m',
        bermZeroCount: 0,
      },
      {
        key: 'toe',
        title: t('dashboard.plot.axis.delta_toe'),
        caption: t('dashboard.histograms.sign_toe'),
        values: toeValues,
        band: { neg: crestNeg, pos: crestPos },
        bandLabel: passLabel,
        signed: true,
        unit: ' m',
        bermZeroCount: 0,
      },
      {
        key: 'berm',
        title: t('dashboard.histograms.berm_title'),
        caption: null,
        values: bermValues,
        band: bermMax != null ? { min: bermMin, max: bermMax } : { min: bermMin },
        bandLabel: bermBandLabel,
        signed: false,
        unit: ' m',
        bermZeroCount,
      },
    ];

    return definitions.map((item) => {
      const spec = buildMiniHistogramSpec({
        values: item.values,
        title: item.title,
        xLabel: item.title,
        frequencyLabel,
        band: item.band,
        bandLabel: item.bandLabel,
        isDark,
      });

      const formattedMedian = item.signed
        ? formatLocaleSigned(spec.median, language, 1, item.unit)
        : spec.median == null
          ? '—'
          : `${formatLocaleNumber(spec.median, language, 1)}${item.unit}`;

      return {
        key: item.key,
        title: item.title,
        caption: item.caption,
        bermZeroCount: item.bermZeroCount,
        formattedMedian,
        spec,
        themedData: resolveThemeVariables(spec.data) as Data[],
      };
    });
  }, [rows, tolerances, isDark, t, language]);

  return (
    <div
      data-slot="deviation-histograms-grid"
      className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      {cards.map((card) => (
        <article
          key={card.key}
          data-slot={`histogram-card-${card.key}`}
          className="flex min-w-0 flex-col border-t border-border pt-3"
        >
          <h4 className="text-xs font-semibold text-text-primary">{card.title}</h4>
          <div
            data-slot="histogram-stats"
            className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] tabular-nums text-text-secondary"
          >
            <span>
              {t('dashboard.histograms.n_label', {
                n: formatLocaleNumber(card.spec.n, language, 0),
              })}
            </span>
            {card.spec.n > 0 && (
              <>
                <span aria-hidden="true" className="text-text-dim">
                  ·
                </span>
                <span>
                  {t('dashboard.histograms.median_label', {
                    value: card.formattedMedian,
                  })}
                </span>
                <span aria-hidden="true" className="text-text-dim">
                  ·
                </span>
                <span
                  style={
                    card.spec.outOfTolCount > 0
                      ? { color: statusToneColor('nok') }
                      : undefined
                  }
                >
                  {t('dashboard.histograms.out_of_tol_label', {
                    pct: formatLocaleNumber(card.spec.outOfTolPct, language, 1),
                  })}
                </span>
              </>
            )}
          </div>
          {card.caption && (
            <p data-slot="histogram-caption" className="mt-1 text-[11px] text-text-muted">
              {card.caption}
            </p>
          )}
          {card.bermZeroCount > 0 && (
            <p
              data-slot="histogram-berm-zeros"
              className="mt-1 text-[11px]"
              style={{ color: statusToneColor('warn') }}
            >
              {t('dashboard.histograms.berm_zeros_note', { count: card.bermZeroCount })}
            </p>
          )}
          <div className="mt-2 h-[190px] w-full">
            {card.spec.n > 0 ? (
              <Plot
                data={card.themedData}
                layout={card.spec.layout}
                config={PLOT_CONFIG}
                style={{ width: '100%', height: '190px' }}
              />
            ) : (
              <p
                data-slot="histogram-empty"
                className="flex h-full items-center justify-center text-xs text-text-muted"
              >
                {t('dashboard.histogram.no_data')}
              </p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
