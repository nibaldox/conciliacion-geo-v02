import { useMemo, useState } from 'react';
import { BenchFilter } from './BenchFilter';
import { CompliancePlanView } from './CompliancePlanView';
import { ResultFilters } from './ResultFilters';
import { DesignAchievementPanel } from './DesignAchievementPanel';
import { filterResults, type ResultFilterState } from './resultFilters.utils';
import { useTranslation } from 'react-i18next';
import Plot from '../charts/Plot';
import type { Data, Layout, Config, Shape } from 'plotly.js';
import { useResults, useSettings } from '../../api/hooks';
import { DEFAULT_TOLERANCES } from '../../utils/constants';
import { useSession } from '../../stores/session';
import type { ComparisonResult } from '../../api/types';
import { BENCH_SCORE_MAX, SCORE_WEIGHTS, compareStatus, resolveBenchScore } from './ProfileView/domain/status';
import type { BenchStatus } from './ProfileView/domain/types';
import { toComparisonBenchStatuses } from './ProfileView/domain/mapping';
import { useTheme } from '../../stores/theme';
import { resolveThemeVariables } from '../../utils/theme';
import { InfoTip, SegmentedControl, StatusDot, SummaryPanel, statusToneColor, type StatusTone } from './SummaryControls';

// ─── Pure helpers (exported for testing) ─────────────────────
//
// The Dashboard's logic is pure: ComparisonResult[] + filter →
// derived values. We keep it out of React so tests don't need to
// render Plotly or mock hooks (same pattern as ProfileChart).

/**
 * Restrict comparison rows to the selected bench numbers.
 * Empty selection = all rows (matches Streamlit's `sel_benches`).
 * Pure: does not mutate the input.
 */
export function filterByBench(
  rows: readonly ComparisonResult[],
  benchNumbers: readonly number[],
): readonly ComparisonResult[] {
  if (benchNumbers.length === 0) return rows;
  const allowed = new Set<number>(benchNumbers);
  return rows.filter((r) => allowed.has(r.bench_num));
}

/** Unique bench numbers present in the data, ascending. */
export interface DesignBenchOption {
  readonly number: number;
  readonly minElevation: number | null;
  readonly maxElevation: number | null;
}

export function designBenchOptions(
  rows: readonly ComparisonResult[],
): DesignBenchOption[] {
  const elevations = new Map<number, Set<number>>();
  for (const row of rows) {
    if (row.type === 'EXTRA') continue;
    if (!Number.isInteger(row.bench_num)) continue;
    const values = elevations.get(row.bench_num) ?? new Set<number>();
    const elevation = Number(row.level);
    if (Number.isFinite(elevation)) values.add(elevation);
    elevations.set(row.bench_num, values);
  }
  return [...elevations.entries()].sort(([a], [b]) => a - b).map(([number, values]) => {
    const ordered = [...values].sort((a, b) => a - b);
    return {
      number,
      minElevation: ordered.length ? ordered[0]! : null,
      maxElevation: ordered.length ? ordered[ordered.length - 1]! : null,
    };
  });
}

// ─── Binary compliance scoring (Track 1-WEB) ─────────────────
//
export { BENCH_SCORE_MAX, SCORE_WEIGHTS };

/** Threshold above which a profile is considered CUMPLE. */
/** Score for a single bench row. Kept for the explicitly numeric KPI. */
export function benchScore(row: ComparisonResult): number | null {
  return resolveBenchScore(row);
}

/**
 * Mean score across all benches of a section. Returns 0 when the
 * section has no benches.
 */
export function profileScore(
  rows: readonly ComparisonResult[],
): number {
  let total = 0;
  let count = 0;
  for (const r of rows) {
    const score = benchScore(r);
    if (score == null) continue;
    total += score;
    count += 1;
  }
  return count === 0 ? 0 : total / count;
}

/**
 * Per-section (profile) scores keyed by section name. Sections
 * with zero benches are omitted so the global average only
 * reflects profiles we actually evaluated.
 */
export function computeProfileScores(
  rows: readonly ComparisonResult[],
): Map<string, number> {
  const map = new Map<string, number[]>();
  for (const r of rows) {
    const score = benchScore(r);
    if (score == null) continue;
    const list = map.get(r.section) ?? [];
    list.push(score);
    map.set(r.section, list);
  }
  const out = new Map<string, number>();
  for (const [section, scores] of map) {
    const sum = scores.reduce((a, b) => a + b, 0);
    out.set(section, sum / scores.length);
  }
  return out;
}

/** Worst evaluated tier across the matched design benches in each section. */
export function computeProfileStatuses(rows: readonly ComparisonResult[]): Map<string, BenchStatus> {
  const statuses = new Map<string, BenchStatus>();
  for (const bench of toComparisonBenchStatuses(rows)) {
    const previous = statuses.get(bench.sectionName);
    statuses.set(bench.sectionName, previous == null || compareStatus(bench.status, previous) > 0 ? bench.status : previous);
  }
  return statuses;
}

/**
 * Global compliance score: average of per-profile scores.
 * Mirrors Streamlit's `score_global = mean(per-section scores)`.
 */
export function computeGlobalScore(
  rows: readonly ComparisonResult[],
): number {
  const profiles = computeProfileScores(rows);
  if (profiles.size === 0) return 0;
  let total = 0;
  for (const v of profiles.values()) total += v;
  return total / profiles.size;
}

/** Counts each profile by its worst evaluated backend tolerance tier. */
export interface ProfileComplianceCounts {
  cumple: number;
  fuera: number;
  noCumple: number;
}

export function computeProfileComplianceCounts(
  rows: readonly ComparisonResult[],
): ProfileComplianceCounts {
  const profiles = computeProfileStatuses(rows);
  const counts: ProfileComplianceCounts = { cumple: 0, fuera: 0, noCumple: 0 };
  for (const status of profiles.values()) {
    if (status === 'CUMPLE') counts.cumple += 1;
    else if (status === 'FUERA') counts.fuera += 1;
    else if (status === 'NO_CUMPLE') counts.noCumple += 1;
  }
  return counts;
}

// ─── Per-parameter breakdown (binary) ────────────────────────

/**
 * Per-parameter compliance breakdown: how many benches CUMPLE /
 * NO CUMPLE on each parameter (height, angle, berm). FUERA and
 * NO CUMPLE are merged.
 */
export interface ParameterBreakdown {
  parameter: 'height' | 'angle' | 'berm';
  cumple: number;
  noCumple: number;
  /** Sum of real values for CUMPLE benches (null-safe). */
  realSum: number;
  /** Count of finite real values contributed (nulls excluded). */
  realCount: number;
}

function realFor(
  row: ComparisonResult,
  parameter: 'height' | 'angle' | 'berm',
): number | null {
  if (parameter === 'height') return row.height_real;
  if (parameter === 'angle') return row.angle_real;
  return row.berm_real;
}

export function computeParameterBreakdown(
  rows: readonly ComparisonResult[],
): ParameterBreakdown[] {
  const out: ParameterBreakdown[] = [];
  const parameters = ['height', 'angle', 'berm'] as const;
  for (const parameter of parameters) {
    let cumple = 0;
    let noCumple = 0;
    let realSum = 0;
    let realCount = 0;
    for (const r of rows) {
      const status = parameter === 'height'
        ? r.height_status
        : parameter === 'angle'
          ? r.angle_status
          : r.berm_status;
      if (!status || status === '-') continue;
      const isCumple = status === 'CUMPLE';
      if (isCumple) cumple += 1;
      else noCumple += 1;
      const real = realFor(r, parameter);
      if (real != null && Number.isFinite(real)) {
        realSum += real;
        realCount += 1;
      }
    }
    out.push({ parameter, cumple, noCumple, realSum, realCount });
  }
  return out;
}

// ─── Sector compliance (% CUMPLE per sector, binary) ─────────

export interface SectorCompliance {
  sector: string;
  pct: number;
  total: number;
}

export function computeSectorCompliance(
  rows: readonly ComparisonResult[],
): SectorCompliance[] {
  const map = new Map<string, { cumple: number; total: number }>();
  for (const r of rows) {
    const entry = map.get(r.sector) ?? { cumple: 0, total: 0 };
    for (const status of [r.height_status, r.angle_status, r.berm_status]) {
      if (!status || status === '-') continue;
      entry.total += 1;
      if (status === 'CUMPLE') entry.cumple += 1;
    }
    map.set(r.sector, entry);
  }
  return [...map.entries()]
    .map(([sector, { cumple, total }]) => ({
      sector,
      total,
      pct: total === 0 ? 0 : (cumple / total) * 100,
    }))
    .sort((a, b) => a.sector.localeCompare(b.sector));
}

export function complianceTone(pct: number): StatusTone {
  if (pct >= 70) return 'ok';
  if (pct >= 50) return 'warn';
  return 'nok';
}

export function sectorComplianceColor(pct: number): string {
  return statusToneColor(complianceTone(pct));
}

// ─── Deviation histograms ─────────────────────────────────────

/** Numeric deviation/real-value fields used by the histograms. */
export type HistogramField = 'height_dev' | 'angle_dev' | 'delta_crest' | 'delta_toe' | 'berm_real';

export function collectField(
  rows: readonly ComparisonResult[],
  field: HistogramField,
): number[] {
  const out: number[] = [];
  for (const r of rows) {
    const v = r[field];
    if (v != null && Number.isFinite(v)) out.push(v);
  }
  return out;
}

export type HistogramBand =
  | { readonly neg: number; readonly pos: number }
  | { readonly min: number };

const CHART_LAYOUT_BASE: Partial<Layout> = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: 'var(--color-text-secondary)', size: 11 },
};

const HISTOGRAM_LAYOUT_BASE: Partial<Layout> = {
  ...CHART_LAYOUT_BASE,
  height: 280,
  margin: { l: 48, r: 16, t: 8, b: 40 },
  bargap: 0.08,
};

const TOLERANCE_BAND_STYLE: Partial<Shape> = {
  fillcolor: 'var(--status-ok-bg)',
  line: { width: 0 },
  layer: 'below',
};

export function buildHistogram(
  values: readonly number[],
  title: string,
  xLabel: string,
  band: HistogramBand,
  frequencyLabel: string,
): { data: Data[]; layout: Partial<Layout> } {
  const shape: Partial<Shape> = 'min' in band
    ? {
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: band.min,
        x1: values.length === 0 ? band.min : Math.max(band.min, ...values),
        y0: 0,
        y1: 1,
        ...TOLERANCE_BAND_STYLE,
      }
    : {
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: -band.neg,
        x1: band.pos,
        y0: 0,
        y1: 1,
        ...TOLERANCE_BAND_STYLE,
      };
  return {
    data: [
      {
        type: 'histogram',
        x: [...values],
        nbinsx: 15,
        marker: { color: 'var(--color-accent)' },
        name: title,
      },
    ] as unknown as Data[],
    layout: {
      ...HISTOGRAM_LAYOUT_BASE,
      xaxis: { title: { text: xLabel }, zeroline: false },
      yaxis: { title: { text: frequencyLabel }, zeroline: false },
      shapes: [shape],
      showlegend: false,
    },
  };
}

// ─── Legacy helpers (kept for back-compat with tests) ────────
//
// `computeAreasBySector`, `collectDeviations`, and
// `computeStatusCountsBySector` were introduced for the previous
// stacked-area / FUERA-included dashboard. The current redesign
// doesn't render them, but the test files still import them, so
// we keep them exported with their original 3-bucket semantics.

export interface SectorArea {
  sector: string;
  overExcavation: number;
  debt: number;
}

export function computeAreasBySector(
  rows: readonly ComparisonResult[],
): SectorArea[] {
  const map = new Map<string, SectorArea>();
  for (const r of rows) {
    const entry =
      map.get(r.sector) ?? { sector: r.sector, overExcavation: 0, debt: 0 };
    const h = r.height_real ?? 0;
    const d = r.delta_crest ?? 0;
    if (d > 0) entry.overExcavation += d * h;
    else if (d < 0) entry.debt += -d * h;
    map.set(r.sector, entry);
  }
  return [...map.values()].sort((a, b) => a.sector.localeCompare(b.sector));
}

export type DeviationField =
  | 'delta_crest'
  | 'delta_toe'
  | 'height_dev'
  | 'angle_dev';

export function collectDeviations(
  rows: readonly ComparisonResult[],
  field: DeviationField,
): number[] {
  const out: number[] = [];
  for (const r of rows) {
    const v = r[field];
    if (v != null && Number.isFinite(v)) out.push(v);
  }
  return out;
}

export interface SectorStatusCounts {
  sector: string;
  CUMPLE: number;
  NO_CUMPLE: number;
}

/** Map a single raw backend status string to its binary bucket.
 *  FUERA DE TOLERANCIA is folded into NO_CUMPLE. */
function binaryBucket(
  raw: string | null | undefined,
): 'CUMPLE' | 'NO_CUMPLE' {
  if (raw == null) return 'NO_CUMPLE';
  const s = raw.trim().toUpperCase();
  if (s === 'CUMPLE') return 'CUMPLE';
  // All non-CUMPLE values (FUERA, NO CUMPLE, NO CONSTRUIDO, etc.)
  // collapse to NO_CUMPLE — the presentation layer is binary.
  return 'NO_CUMPLE';
}

/** Pick the worst binary status among the three. NO_CUMPLE wins
 *  over CUMPLE (strict). Equal → tie. */
function worstBinary(
  a: 'CUMPLE' | 'NO_CUMPLE',
  b: 'CUMPLE' | 'NO_CUMPLE',
  c: 'CUMPLE' | 'NO_CUMPLE',
): 'CUMPLE' | 'NO_CUMPLE' {
  if (a === 'NO_CUMPLE' || b === 'NO_CUMPLE' || c === 'NO_CUMPLE') {
    return 'NO_CUMPLE';
  }
  return 'CUMPLE';
}

export function computeStatusCountsBySector(
  rows: readonly ComparisonResult[],
): SectorStatusCounts[] {
  const map = new Map<string, SectorStatusCounts>();
  for (const r of rows) {
    const entry =
      map.get(r.sector) ?? { sector: r.sector, CUMPLE: 0, NO_CUMPLE: 0 };
    const status = worstBinary(
      binaryBucket(r.height_status),
      binaryBucket(r.angle_status),
      binaryBucket(r.berm_status),
    );
    if (status === 'CUMPLE') entry.CUMPLE += 1;
    else entry.NO_CUMPLE += 1;
    map.set(r.sector, entry);
  }
  return [...map.values()].sort((a, b) => a.sector.localeCompare(b.sector));
}

// ─── UI ──────────────────────────────────────────────────────

type HistogramKey = 'height' | 'angle' | 'crest' | 'toe' | 'berm';

const HISTOGRAM_KEYS: readonly HistogramKey[] = ['height', 'angle', 'crest', 'toe', 'berm'];

type Translate = (key: string, options?: Record<string, unknown>) => string;

function percentOf(part: number, total: number): number {
  return total === 0 ? 0 : (part / total) * 100;
}

function KpiHeader({ globalScore, counts, t }: { globalScore: number; counts: ProfileComplianceCounts; t: Translate }) {
  const total = counts.cumple + counts.fuera + counts.noCumple;
  const counters: { key: string; tone: StatusTone; label: string; value: number }[] = [
    { key: 'ok', tone: 'ok', label: t('dashboard.kpi.count_ok', { defaultValue: 'Cumple' }), value: counts.cumple },
    { key: 'warn', tone: 'warn', label: t('dashboard.kpi.count_outside', { defaultValue: 'Fuera de tolerancia' }), value: counts.fuera },
    { key: 'nok', tone: 'nok', label: t('dashboard.kpi.count_no', { defaultValue: 'No cumple' }), value: counts.noCumple },
  ];
  return (
    <div data-slot="dashboard-kpis" className="flex flex-wrap items-end gap-x-10 gap-y-4">
      <dl className="m-0">
        <div className="flex items-baseline gap-2">
          <dt className="order-last flex items-center gap-1.5 text-xs text-text-muted">
            {t('dashboard.kpi.global_score')}
            <InfoTip label={t('dashboard.kpi.how_calculated', { defaultValue: '¿Cómo se calcula?' })}>
              {t('dashboard.kpi.global_score_help')}
            </InfoTip>
          </dt>
          <dd className="m-0 text-4xl font-semibold leading-none tabular-nums" style={{ color: statusToneColor(complianceTone(globalScore)) }}>
            {globalScore.toFixed(1)}
          </dd>
          <dd className="m-0 text-sm tabular-nums text-text-muted">/100</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <span className="flex items-center gap-1.5 text-xs text-text-muted">
          {t('dashboard.kpi.profiles_label', { defaultValue: 'Perfiles' })}
          <InfoTip label={t('dashboard.kpi.how_classified', { defaultValue: '¿Cómo se clasifican los perfiles?' })}>
            {t('dashboard.kpi.profile_classification_help')}
          </InfoTip>
        </span>
        <dl className="m-0 flex flex-wrap items-baseline gap-x-6 gap-y-2">
          {counters.map((counter) => (
            <div key={counter.key} data-tone={counter.tone} className="flex items-baseline gap-2">
              <dt className="flex items-center gap-1.5 text-sm text-text-secondary">
                <StatusDot tone={counter.tone} />
                {counter.label}
              </dt>
              <dd className="m-0 text-xl font-semibold tabular-nums text-text-primary">{counter.value}</dd>
              <dd className="m-0 text-xs tabular-nums text-text-muted">{Math.round(percentOf(counter.value, total))}%</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

function ParameterTable({ breakdown, t }: { breakdown: readonly ParameterBreakdown[]; t: Translate }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-text-muted">
            <th scope="col" className="py-2 pr-4 text-left font-medium">{t('dashboard.table.parameter')}</th>
            <th scope="col" className="py-2 pr-4 text-left font-medium">{t('dashboard.table.pct_ok', { defaultValue: '% cumple' })}</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">{t('dashboard.kpi.count_ok', { defaultValue: 'Cumple' })}</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">{t('dashboard.kpi.count_no', { defaultValue: 'No cumple' })}</th>
            <th scope="col" className="py-2 text-right font-medium">{t('dashboard.table.real_avg', { defaultValue: 'Promedio real' })}</th>
          </tr>
        </thead>
        <tbody>
          {breakdown.map((p) => {
            const total = p.cumple + p.noCumple;
            const pct = percentOf(p.cumple, total);
            const avgReal = p.realCount === 0 ? null : p.realSum / p.realCount;
            return (
              <tr key={p.parameter} data-parameter={p.parameter} className="border-b border-border last:border-b-0">
                <th scope="row" className="py-2 pr-4 text-left font-medium text-text-primary">{parameterLabel(p.parameter, t)}</th>
                <td className="py-2 pr-4">
                  <div className="flex items-center gap-3">
                    <span className="w-14 text-right tabular-nums text-text-primary">{total === 0 ? '—' : `${pct.toFixed(1)}%`}</span>
                    <span aria-hidden="true" className="h-1.5 w-full max-w-40 overflow-hidden rounded-full bg-surface-muted">
                      <span className="block h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: statusToneColor(complianceTone(pct)) }} />
                    </span>
                  </div>
                </td>
                <td data-col="cumple" className="py-2 pr-4 text-right tabular-nums text-text-secondary">{p.cumple}</td>
                <td data-col="no-cumple" className="py-2 pr-4 text-right tabular-nums text-text-secondary">{p.noCumple}</td>
                <td className="py-2 text-right tabular-nums text-text-secondary">{avgReal == null ? '—' : formatReal(p.parameter, avgReal)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard() {
  const { t } = useTranslation();
  const isDark = useTheme((s) => s.isDark);
  const { data: results } = useResults();
  const { data: settings } = useSettings();
  const filters = useSession((s) => s.filters);
  const setFilters = useSession((s) => s.setFilters);
  const [histogramKey, setHistogramKey] = useState<HistogramKey>('height');

  const tolerances = settings?.tolerances ?? DEFAULT_TOLERANCES;
  const heightTol = tolerances.bench_height;
  const angleTol = tolerances.face_angle;
  const crestTol = tolerances.crest_toe_deviation ?? DEFAULT_TOLERANCES.crest_toe_deviation;
  const bermTol = tolerances.berm_width;

  const setScenarioFilters = (next: ResultFilterState) => setFilters(next);

  const filteredResults = useMemo(
    () => filterResults(results, filters),
    [results, filters],
  );

  const benchNumbers = useMemo(
    () => designBenchOptions(results ?? []),
    [results],
  );

  const globalScore = useMemo(
    () => computeGlobalScore(filteredResults),
    [filteredResults],
  );

  const profileCounts = useMemo(
    () => computeProfileComplianceCounts(filteredResults),
    [filteredResults],
  );

  const profileStatuses = useMemo(
    () => computeProfileStatuses(filteredResults),
    [filteredResults],
  );

  const parameterBreakdown = useMemo(
    () => computeParameterBreakdown(filteredResults),
    [filteredResults],
  );

  const sectorCompliance = useMemo(
    () => computeSectorCompliance(filteredResults),
    [filteredResults],
  );

  const heightDevs = useMemo(() => collectField(filteredResults, 'height_dev'), [filteredResults]);
  const angleDevs = useMemo(() => collectField(filteredResults, 'angle_dev'), [filteredResults]);
  const crestDevs = useMemo(() => collectField(filteredResults, 'delta_crest'), [filteredResults]);
  const toeDevs = useMemo(() => collectField(filteredResults, 'delta_toe'), [filteredResults]);
  const bermWidths = useMemo(() => collectField(filteredResults, 'berm_real'), [filteredResults]);

  const totalBenches = filteredResults.length;
  const nSections = new Set(filteredResults.map((row) => row.section)).size;

  const plotConfig = useMemo<Partial<Config>>(
    () => ({ displayModeBar: false, responsive: true }),
    [],
  );

  const sectorChartData = useMemo<Data[]>(() => {
    const hoverLabel = t('dashboard.plot.hover.compliance_label');
    return resolveThemeVariables([
      {
        type: 'bar',
        x: sectorCompliance.map((s) => s.sector),
        y: sectorCompliance.map((s) => s.pct),
        marker: { color: sectorCompliance.map((s) => sectorComplianceColor(s.pct)) },
        text: sectorCompliance.map((s) => `${s.pct.toFixed(1)}%`),
        textposition: 'outside',
        cliponaxis: false,
        hovertemplate: `<b>%{x}</b><br>${hoverLabel}: %{y:.1f}%<extra></extra>`,
      },
    ]) as Data[];
  }, [sectorCompliance, t, isDark]);

  const sectorChartLayout = useMemo<Partial<Layout>>(
    () => ({
      ...CHART_LAYOUT_BASE,
      height: 300,
      margin: { l: 48, r: 16, t: 16, b: 40 },
      bargap: 0.35,
      xaxis: { showgrid: false },
      yaxis: { title: { text: t('dashboard.plot.axis.pct_compliance') }, range: [0, 110], ticksuffix: '%', zeroline: false },
    }),
    [t],
  );

  const frequencyLabel = t('dashboard.plot.axis.frequency');
  const crestBand = useMemo(
    () => ({
      neg: Number(crestTol.neg ?? DEFAULT_TOLERANCES.crest_toe_deviation.neg),
      pos: Number(crestTol.pos ?? DEFAULT_TOLERANCES.crest_toe_deviation.pos),
    }),
    [crestTol],
  );

  const activeHistogram = useMemo(() => {
    switch (histogramKey) {
      case 'height':
        return buildHistogram(heightDevs, t('dashboard.parameter.height'), t('dashboard.plot.axis.delta_height'), { neg: Number(heightTol.neg), pos: Number(heightTol.pos) }, frequencyLabel);
      case 'angle':
        return buildHistogram(angleDevs, t('dashboard.parameter.angle'), t('dashboard.plot.axis.delta_angle'), { neg: Number(angleTol.neg), pos: Number(angleTol.pos) }, frequencyLabel);
      case 'crest':
        return buildHistogram(crestDevs, t('dashboard.plot.axis.delta_crest'), t('dashboard.plot.axis.delta_crest'), crestBand, frequencyLabel);
      case 'toe':
        return buildHistogram(toeDevs, t('dashboard.plot.axis.delta_toe', { defaultValue: 'Δ Pata (m)' }), t('dashboard.plot.axis.delta_toe', { defaultValue: 'Δ Pata (m)' }), crestBand, frequencyLabel);
      case 'berm':
        return buildHistogram(bermWidths, t('dashboard.plot.axis.berm_width', { defaultValue: 'Ancho de berma real (m)' }), t('dashboard.plot.axis.berm_width', { defaultValue: 'Ancho de berma real (m)' }), { min: Number(bermTol.min) }, frequencyLabel);
    }
  }, [histogramKey, heightDevs, angleDevs, crestDevs, toeDevs, bermWidths, heightTol, angleTol, crestBand, bermTol, frequencyLabel, t]);

  const themedHistogramData = useMemo(
    () => resolveThemeVariables(activeHistogram.data) as Data[],
    [activeHistogram, isDark],
  );

  const histogramHasData = activeHistogram.data.some((d) => {
    const x = (d as { x?: unknown }).x;
    return Array.isArray(x) && x.length > 0;
  });

  const histogramOptions = HISTOGRAM_KEYS.map((key) => ({ value: key, label: histogramLabel(key, t) }));

  if (!results || results.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-text-muted">
        {t('dashboard.empty_state')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {filteredResults.length > 0 ? (
        <KpiHeader globalScore={globalScore} counts={profileCounts} t={t} />
      ) : (
        <p role="status" className="text-sm text-text-muted">{t('dashboard.filters.no_matching_results')}</p>
      )}

      <div data-slot="dashboard-filters" className="flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-border py-2">
        <BenchFilter available={benchNumbers} selected={filters.bench} onChange={(bench) => setFilters({ bench })} />
        <ResultFilters results={results} filters={filters} onChange={setScenarioFilters} />
        <span className="ml-auto text-xs tabular-nums text-text-muted">
          {t('dashboard.summary.bench_section', { benches: totalBenches, sections: nSections })}
        </span>
      </div>

      {filteredResults.length > 0 && (
        <>
          <SummaryPanel slot="parameter-breakdown" title={t('dashboard.section.parameters', { defaultValue: 'Desglose por parámetro' })}>
            <ParameterTable breakdown={parameterBreakdown} t={t} />
          </SummaryPanel>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            {sectorCompliance.length > 0 && (
              <SummaryPanel slot="sector-compliance" title={t('dashboard.section.by_sector', { defaultValue: 'Cumplimiento por sector' })}>
                <Plot data={sectorChartData} layout={sectorChartLayout} config={plotConfig} style={{ width: '100%' }} />
              </SummaryPanel>
            )}
            <CompliancePlanView results={filteredResults} statuses={profileStatuses} />
          </div>

          <SummaryPanel
            slot="deviation-distribution"
            title={t('dashboard.section.deviation_distribution', { defaultValue: 'Distribución de desviaciones' })}
            actions={(
              <SegmentedControl
                label={t('dashboard.histogram.selector', { defaultValue: 'Variable del histograma' })}
                options={histogramOptions}
                value={histogramKey}
                onChange={setHistogramKey}
              />
            )}
          >
            <p className="text-xs text-text-muted">{histogramTitle(histogramKey, t)}</p>
            <div className="h-[280px]">
              {histogramHasData ? (
                <Plot data={themedHistogramData} layout={activeHistogram.layout} config={plotConfig} style={{ width: '100%' }} />
              ) : (
                <p className="flex h-full items-center justify-center text-xs text-text-muted">{t('dashboard.histogram.no_data')}</p>
              )}
            </div>
          </SummaryPanel>

          <DesignAchievementPanel filters={filters} />
        </>
      )}
    </div>
  );
}

// ─── Small UI helpers ────────────────────────────────────────

function parameterLabel(p: 'height' | 'angle' | 'berm', t: Translate): string {
  switch (p) {
    case 'height': return t('dashboard.parameter.height');
    case 'angle':  return t('dashboard.parameter.angle');
    case 'berm':   return t('dashboard.parameter.berm');
  }
}

function histogramLabel(key: HistogramKey, t: Translate): string {
  switch (key) {
    case 'height': return t('dashboard.parameter.height');
    case 'angle':  return t('dashboard.parameter.angle');
    case 'crest':  return t('dashboard.parameter.crest', { defaultValue: 'Cresta' });
    case 'toe':    return t('dashboard.parameter.toe', { defaultValue: 'Pata' });
    case 'berm':   return t('dashboard.parameter.berm');
  }
}

function histogramTitle(key: HistogramKey, t: Translate): string {
  switch (key) {
    case 'height': return t('dashboard.section.deviation_height');
    case 'angle':  return t('dashboard.section.deviation_angle');
    case 'crest':  return t('dashboard.section.deviation_crest');
    case 'toe':    return t('dashboard.section.deviation_toe', { defaultValue: 'Desviación de Pata (m)' });
    case 'berm':   return t('dashboard.section.deviation_berm', { defaultValue: 'Ancho de berma (m)' });
  }
}

function formatReal(p: 'height' | 'angle' | 'berm', v: number): string {
  if (p === 'height') return `${v.toFixed(2)} m`;
  if (p === 'angle')  return `${v.toFixed(1)}°`;
  return `${v.toFixed(2)} m`;
}
