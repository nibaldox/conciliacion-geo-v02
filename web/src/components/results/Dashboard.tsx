import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { BenchFilter } from './BenchFilter';
import { CompliancePlanView } from './CompliancePlanView';
import { ResultFilters } from './ResultFilters';
import { DesignAchievementPanel } from './DesignAchievementPanel';
import { ProposalSummaryCard } from './ProposalSummaryCard';
import { filterResults, type ResultFilterState } from './resultFilters.utils';
import { useTranslation } from 'react-i18next';
import Plot from '../charts/Plot';
import type { Data, Layout, Config, Shape } from 'plotly.js';
import { useResults, useSections, useSettings } from '../../api/hooks';
import type { PlanColorBy, PlanStatusKey } from './planColors';
import { ParameterBars, SelectedSectionPanel } from './dashboard/DashboardRail';
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
  const { data: sections } = useSections();
  const setSelectedProfile = useSession((s) => s.setSelectedSection);
  const setActiveWorkspaceView = useSession((s) => s.setActiveWorkspaceView);
  const [colorBy, setColorBy] = useState<PlanColorBy>('status');
  const [visibleStatuses, setVisibleStatuses] = useState<Set<PlanStatusKey>>(() => new Set(['CUMPLE', 'FUERA', 'NO_CUMPLE', 'UNKNOWN']));
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const filters = useSession((s) => s.filters);
  const setFilters = useSession((s) => s.setFilters);
  const [histogramKey, setHistogramKey] = useState<HistogramKey>('height');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [workspaceHeight, setWorkspaceHeight] = useState<number>();
  const filtersRef = useRef<HTMLDivElement>(null);
  const dashboardRef = useRef<HTMLDivElement>(null);
  const activeFilterCount = [filters.bench, filters.sector, filters.section, filters.level].filter((values) => values.length > 0).length;

  useEffect(() => {
    if (!filtersOpen) return;
    const outside = (event: PointerEvent) => {
      if (!filtersRef.current?.contains(event.target as Node)) setFiltersOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setFiltersOpen(false);
        filtersRef.current?.querySelector('button')?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [filtersOpen]);

  useEffect(() => {
    const workspace = dashboardRef.current?.closest('.overflow-auto');
    if (!workspace) return;
    const update = () => {
      const style = getComputedStyle(workspace);
      setWorkspaceHeight(workspace.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(workspace);
    return () => observer.disconnect();
  }, [results]);

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

  const selectedVisible = selectedSection != null && filteredResults.some((row) => row.section === selectedSection) && visibleStatuses.has(profileStatuses.get(selectedSection) ?? 'UNKNOWN');
  useEffect(() => {
    if (selectedSection && !selectedVisible) setSelectedSection(null);
  }, [selectedSection, selectedVisible]);
  const selectedMatches = sections?.filter((section) => section.name === selectedSection) ?? [];
  const selectedId = selectedMatches.length === 1 ? selectedMatches[0]!.id : null;

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

  const proposalSections = useMemo(
    () => [...new Set(filteredResults.map((row) => row.section))],
    [filteredResults],
  );
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
    <div ref={dashboardRef} className="flex min-w-0 flex-col gap-6">
      <div className="flex min-h-0 min-w-0 flex-col xl:h-[var(--workspace-height)]" style={{ '--workspace-height': workspaceHeight == null ? 'auto' : `${workspaceHeight}px` } as CSSProperties}>
      <div data-slot="dashboard-filters" className="relative flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border pb-2 xl:flex-nowrap xl:[&_[role=group]]:flex-nowrap">
        <span className="shrink-0 whitespace-nowrap text-xs text-text-muted">{t('dashboard.rail.color_by')}</span>
        <SegmentedControl label={t('dashboard.rail.color_by')} options={(['status', 'score', 'height', 'angle', 'berm'] as const).map((value) => ({ value, label: t(`dashboard.rail.color_${value}`) }))} value={colorBy} onChange={setColorBy} />
        <div role="group" aria-label={t('dashboard.rail.filter_status')} className="flex flex-nowrap gap-1">
          {(['CUMPLE', 'FUERA', 'NO_CUMPLE', 'UNKNOWN'] as const).map((status) => <button key={status} type="button" aria-pressed={visibleStatuses.has(status)} className="border border-border px-2 py-1 text-xs aria-pressed:text-text-primary text-text-muted" onClick={() => setVisibleStatuses((current) => { const next = new Set(current); if (next.has(status)) next.delete(status); else next.add(status); return next; })}>{t(`dashboard.rail.status_${status.toLowerCase()}`)}</button>)}
        </div>
        <div ref={filtersRef} className="relative">
          <button type="button" aria-expanded={filtersOpen} aria-controls="dashboard-filter-panel" className="h-8 whitespace-nowrap border border-border px-2 text-xs text-text-primary" onClick={() => setFiltersOpen((open) => !open)}>{t('dashboard.filters.label')}{activeFilterCount > 0 && ` · ${activeFilterCount}`}</button>
          {filtersOpen && <div id="dashboard-filter-panel" ref={(panel) => { if (panel) { const bounds = panel.closest('main')?.getBoundingClientRect(); const left = Math.max(8, (bounds?.left ?? 0) + 12); const right = Math.min(window.innerWidth - 8, (bounds?.right ?? window.innerWidth) - 12); panel.style.width = `${Math.min(352, right - left)}px`; panel.style.translate = '0 0'; const rect = panel.getBoundingClientRect(); panel.style.translate = `${Math.max(left - rect.left, Math.min(0, right - rect.right))}px 0`; } }} className="absolute right-0 top-full z-30 mt-1 w-[22rem] max-w-[calc(100vw-2rem)] space-y-3 border border-border bg-surface-raised p-3 shadow-lg">
            <BenchFilter available={benchNumbers} selected={filters.bench} onChange={(bench) => setFilters({ bench })} />
            <ResultFilters results={results} filters={filters} onChange={setScenarioFilters} compact />
          </div>}
        </div>
        <span className="ml-auto text-xs tabular-nums text-text-muted">{t('dashboard.rail.count', { benches: totalBenches, sections: nSections })}</span>
      </div>
      {filteredResults.length === 0 ? <p role="status" className="text-sm text-text-muted">{t('dashboard.filters.no_matching_results')}</p> :
        <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 pt-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] xl:grid-rows-[minmax(400px,1fr)]">
          <div data-slot="dashboard-plan" className="min-w-0 h-[60vh] min-h-[390px] xl:h-full xl:min-h-[400px]">
            <CompliancePlanView results={filteredResults} statuses={profileStatuses} variant="hero" colorBy={colorBy} visibleStatuses={visibleStatuses} selectedSection={selectedVisible ? selectedSection : null} onSelectSection={setSelectedSection} />
          </div>
          <aside data-slot="dashboard-rail" className="min-w-0 px-4 pt-5 [&_[class$=bubble]]:max-w-48! xl:min-h-0 xl:overflow-y-auto xl:border-l xl:border-border">
            <KpiHeader globalScore={globalScore} counts={profileCounts} t={t} />
            <ParameterBars rows={filteredResults} />
            <details className="border-t border-border py-4 [&_.overflow-x-auto]:overflow-visible [&_table]:table-fixed [&_table]:text-xs [&_th]:pr-1 [&_td]:pr-1 [&_span[aria-hidden]]:hidden [&_td_span]:w-auto [&_td_div]:gap-0" onToggle={(event) => { if (event.currentTarget.open) event.currentTarget.scrollIntoView?.({ block: 'nearest' }); }}><summary className="cursor-pointer text-sm">{t('dashboard.rail.parameter_detail')}</summary><ParameterTable breakdown={parameterBreakdown} t={t} /></details>
            <SelectedSectionPanel name={selectedVisible ? selectedSection : null} sectionId={selectedVisible ? selectedId : null} rows={filteredResults} statuses={profileStatuses} canOpen={selectedId != null} onClear={() => setSelectedSection(null)} onOpen={() => { if (selectedId != null) { setSelectedProfile(selectedId); setActiveWorkspaceView('profiles'); } }} />
          </aside>
        </div>}
      </div>
      {filteredResults.length > 0 && <>
        <div className="grid min-w-0 gap-6 border-t border-border pt-6 xl:grid-cols-2">
          <SummaryPanel slot="deviation-distribution" title={t('dashboard.section.deviation_distribution')} actions={<SegmentedControl label={t('dashboard.histogram.selector')} options={histogramOptions} value={histogramKey} onChange={setHistogramKey} />}>
            <p className="text-xs text-text-muted">{histogramTitle(histogramKey, t)}</p>
            <div className="h-[280px]">{histogramHasData ? <Plot data={themedHistogramData} layout={activeHistogram.layout} config={plotConfig} style={{ width: '100%' }} /> : <p className="flex h-full items-center justify-center text-xs text-text-muted">{t('dashboard.histogram.no_data')}</p>}</div>
          </SummaryPanel>
          <SummaryPanel slot="sector-compliance" title={t('dashboard.section.by_sector')}>
            {sectorCompliance.some((sector) => sector.sector?.trim()) ? <Plot data={sectorChartData} layout={sectorChartLayout} config={plotConfig} style={{ width: '100%' }} /> : <p className="text-xs text-text-muted">{t('dashboard.rail.no_sectors')}</p>}
          </SummaryPanel>
        </div>
        <div className="grid min-w-0 gap-6 xl:grid-cols-2">
          <DesignAchievementPanel filters={filters} />
          <ProposalSummaryCard filters={filters} sections={proposalSections} />
        </div>
      </>}
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
