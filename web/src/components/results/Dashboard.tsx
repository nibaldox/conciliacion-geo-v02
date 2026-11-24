import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { BenchFilter } from './BenchFilter';
import { CompliancePlanView } from './CompliancePlanView';
import { buildActiveFilterChips, ResultFilters } from './ResultFilters';
import { DesignAchievementPanel } from './DesignAchievementPanel';
import { ProposalSummaryCard } from './ProposalSummaryCard';
import { filterResults, toggleDimensionValue, type ResultFilterState } from './resultFilters.utils';
import { useTranslation } from 'react-i18next';
import Plot from '../charts/Plot';
import type { Data, Layout, Config, Shape } from 'plotly.js';
import { useMeshInfo, useResults, useSections, useSettings } from '../../api/hooks';
import type { PlanColorBy } from './planColors';
import { SelectedSectionPanel } from './dashboard/DashboardRail';
import { DashboardContextBar } from './dashboard/DashboardContextBar';
import { CoverageBanner } from './dashboard/CoverageBanner';
import { DirectionalSummary } from './dashboard/DirectionalSummary';
import { LevelComplianceTable } from './dashboard/LevelComplianceTable';
import { PriorityReviewList } from './dashboard/PriorityReviewList';
import { DeviationHistogramsGrid } from './dashboard/DeviationHistogramsGrid';
import { computeDashboardCoverage } from './dashboard/coverageSelectors';
import {
  computeDirectionalStats,
  computeLevelCompliance,
  computePriorityReviewList,
} from './dashboard/geotechSelectors';
import { DEFAULT_TOLERANCES } from '../../utils/constants';
import { formatLocaleNumber, formatLocalePercent } from '../../utils/format';
import { useSession } from '../../stores/session';
import { useBenchFocus } from '../../stores/benchFocus';
import type { ComparisonResult } from '../../api/types';
import {
  BENCH_SCORE_MAX,
  SCORE_WEIGHTS,
  classifyProfileStatusFromRows,
  resolveBenchScore,
} from './ProfileView/domain/status';
import type { BenchStatus } from './ProfileView/domain/types';
import { useTheme } from '../../stores/theme';
import { resolveThemeVariables } from '../../utils/theme';
import { InfoTip, SegmentedControl, StatusDot, SummaryPanel, statusToneColor, type StatusTone } from './SummaryControls';

export function filterByBench(
  rows: readonly ComparisonResult[],
  benchNumbers: readonly number[],
): readonly ComparisonResult[] {
  if (benchNumbers.length === 0) return rows;
  const allowed = new Set<number>(benchNumbers);
  return rows.filter((r) => allowed.has(r.bench_num));
}

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

export { BENCH_SCORE_MAX, SCORE_WEIGHTS };

export function benchScore(row: ComparisonResult): number | null {
  return resolveBenchScore(row);
}

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

export function computeProfileStatuses(rows: readonly ComparisonResult[]): Map<string, BenchStatus> {
  const bySection = new Map<string, ComparisonResult[]>();
  for (const row of rows) {
    const list = bySection.get(row.section);
    if (list) list.push(row);
    else bySection.set(row.section, [row]);
  }
  const statuses = new Map<string, BenchStatus>();
  for (const [section, sectionRows] of bySection) {
    statuses.set(section, classifyProfileStatusFromRows(sectionRows));
  }
  return statuses;
}

export function computeGlobalScore(
  rows: readonly ComparisonResult[],
): number {
  const profiles = computeProfileScores(rows);
  if (profiles.size === 0) return 0;
  let total = 0;
  for (const v of profiles.values()) total += v;
  return total / profiles.size;
}

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

export interface ParameterBreakdown {
  parameter: 'height' | 'angle' | 'berm';
  cumple: number;
  noCumple: number;
  nEvaluated: number;
  nNotCompared: number;
  realSum: number;
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
  const nNotCompared = rows.filter((r) => r.type === 'MISSING' || r.type === 'EXTRA').length;
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
      if (r.type === 'MATCH') {
        if (status === 'CUMPLE') cumple += 1;
        else noCumple += 1;
        const real = realFor(r, parameter);
        if (real != null && Number.isFinite(real)) {
          realSum += real;
          realCount += 1;
        }
      }
    }
    out.push({ parameter, cumple, noCumple, nEvaluated: cumple + noCumple, nNotCompared, realSum, realCount });
  }
  return out;
}

export interface SectorCompliance {
  sector: string;
  pct: number | null;
  total: number;
  nNotCompared: number;
}

export function computeSectorCompliance(
  rows: readonly ComparisonResult[],
): SectorCompliance[] {
  const map = new Map<string, { cumple: number; total: number; nNotCompared: number }>();
  for (const r of rows) {
    const entry = map.get(r.sector) ?? { cumple: 0, total: 0, nNotCompared: 0 };
    map.set(r.sector, entry);
    if (r.type === 'MISSING' || r.type === 'EXTRA') entry.nNotCompared += 1;
    if (r.type !== 'MATCH') continue;
    for (const status of [r.height_status, r.angle_status, r.berm_status]) {
      if (!status || status === '-') continue;
      entry.total += 1;
      if (status === 'CUMPLE') entry.cumple += 1;
    }
  }
  return [...map.entries()]
    .map(([sector, { cumple, total, nNotCompared }]) => ({
      sector,
      pct: total === 0 ? null : (cumple / total) * 100,
      total,
      nNotCompared,
    }))
    .sort((a, b) => a.sector.localeCompare(b.sector));
}

export function complianceTone(pct: number): StatusTone {
  if (pct >= 70) return 'ok';
  if (pct >= 50) return 'warn';
  return 'nok';
}

export function sectorComplianceColor(pct: number | null): string {
  return statusToneColor(pct == null ? 'muted' : complianceTone(pct));
}

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

function binaryBucket(
  raw: string | null | undefined,
): 'CUMPLE' | 'NO_CUMPLE' {
  if (raw == null) return 'NO_CUMPLE';
  const s = raw.trim().toUpperCase();
  if (s === 'CUMPLE') return 'CUMPLE';
  return 'NO_CUMPLE';
}

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

type Translate = (key: string, options?: Record<string, unknown>) => string;

function percentOf(part: number, total: number): number {
  return total === 0 ? 0 : (part / total) * 100;
}

function KpiHeader({
  globalScore,
  counts,
  unknownCount,
  language,
  t,
}: {
  globalScore: number;
  counts: ProfileComplianceCounts;
  unknownCount: number;
  language?: string;
  t: Translate;
}) {
  const total = counts.cumple + counts.noCumple + unknownCount;
  const counters: { key: string; tone: StatusTone; label: string; value: number }[] = [
    { key: 'ok', tone: 'ok', label: t('dashboard.kpi.count_ok', { defaultValue: 'Cumple' }), value: counts.cumple },
    { key: 'nok', tone: 'nok', label: t('dashboard.kpi.count_no', { defaultValue: 'No cumple' }), value: counts.noCumple },
  ];
  if (unknownCount > 0) {
    counters.push({
      key: 'unknown',
      tone: 'muted',
      label: t('dashboard.rail.status_unknown', { defaultValue: 'Sin dato' }),
      value: unknownCount,
    });
  }
  return (
    <div data-slot="dashboard-kpis" className="flex flex-wrap items-end gap-x-8 gap-y-4 pb-4">
      <dl className="m-0">
        <div className="flex items-baseline gap-2">
          <dt className="order-last flex items-center gap-1.5 text-xs text-text-muted">
            {t('dashboard.kpi.global_score')}
            <InfoTip align="end" label={t('dashboard.kpi.how_calculated', { defaultValue: '¿Cómo se calcula?' })}>
              {t('dashboard.kpi.global_score_help')}
            </InfoTip>
          </dt>
          <dd
            className="m-0 text-4xl font-semibold leading-none tabular-nums"
            style={{ color: statusToneColor(complianceTone(globalScore)) }}
          >
            {formatLocaleNumber(globalScore, language, 1)}
          </dd>
          <dd className="m-0 text-sm tabular-nums text-text-muted">/100</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
        <span className="flex items-center gap-1.5 text-xs text-text-muted">
          {t('dashboard.kpi.profiles_label', { defaultValue: 'Perfiles' })}
          <InfoTip align="start" label={t('dashboard.kpi.how_classified', { defaultValue: '¿Cómo se clasifican los perfiles?' })}>
            {t('dashboard.kpi.profile_classification_help')}
          </InfoTip>
        </span>
        <dl className="m-0 flex flex-wrap items-baseline gap-x-5 gap-y-2">
          {counters.map((counter) => (
            <div key={counter.key} data-tone={counter.tone} className="flex items-baseline gap-1.5">
              <dt className="flex items-center gap-1.5 text-sm text-text-secondary">
                <StatusDot tone={counter.tone} />
                {counter.label}
              </dt>
              <dd className="m-0 text-xl font-semibold tabular-nums text-text-primary">
                {formatLocaleNumber(counter.value, language, 0)}
              </dd>
              <dd className="m-0 text-xs tabular-nums text-text-muted">
                {Math.round(percentOf(counter.value, total))}%
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

function ParameterTable({
  breakdown,
  language,
  t,
}: {
  breakdown: readonly ParameterBreakdown[];
  language?: string;
  t: Translate;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border text-text-muted">
            <th scope="col" className="whitespace-nowrap py-1.5 pr-3 text-left font-medium">
              {t('dashboard.table.parameter')}
            </th>
            <th scope="col" className="whitespace-nowrap px-2 py-1.5 text-right font-medium">
              {t('dashboard.table.pct_ok', { defaultValue: '% cumple' })}
            </th>
            <th scope="col" className="whitespace-nowrap px-2 py-1.5 text-right font-medium">
              {t('dashboard.kpi.count_ok', { defaultValue: 'Cumple' })}
            </th>
            <th scope="col" className="whitespace-nowrap px-2 py-1.5 text-right font-medium">
              {t('dashboard.kpi.count_no', { defaultValue: 'No cumple' })}
            </th>
            <th scope="col" className="whitespace-nowrap py-1.5 pl-2 text-right font-medium">
              {t('dashboard.table.real_avg', { defaultValue: 'Promedio real' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {breakdown.map((p) => {
            const total = p.nEvaluated;
            const pct = percentOf(p.cumple, total);
            const avgReal = p.realCount === 0 ? null : p.realSum / p.realCount;
            return (
              <tr key={p.parameter} data-parameter={p.parameter} className="border-b border-border last:border-b-0">
                <th scope="row" className="whitespace-nowrap py-2 pr-3 text-left font-medium text-text-primary">
                  {parameterLabel(p.parameter, t)}
                </th>
                <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-text-primary">
                  {total === 0 ? '—' : formatLocalePercent(pct, language, 1)}
                </td>
                <td data-col="cumple" className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-text-secondary">
                  {formatLocaleNumber(p.cumple, language, 0)}
                </td>
                <td data-col="no-cumple" className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-text-secondary">
                  {formatLocaleNumber(p.noCumple, language, 0)}
                </td>
                <td className="whitespace-nowrap py-2 pl-2 text-right tabular-nums text-text-secondary">
                  {avgReal == null ? '—' : formatReal(p.parameter, avgReal, language)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const PLAN_COLOR_OPTIONS: readonly PlanColorBy[] = ['berm', 'score', 'status', 'height', 'angle'];

export function Dashboard() {
  const { t, i18n } = useTranslation();
  const language = i18n?.resolvedLanguage ?? i18n?.language;
  const isDark = useTheme((s) => s.isDark);
  const { data: results } = useResults();
  const { data: settings } = useSettings();
  const { data: sections } = useSections();
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const { data: designMeshInfo } = useMeshInfo(designMeshId ?? null);
  const { data: topoMeshInfo } = useMeshInfo(topoMeshId ?? null);
  const setSelectedProfile = useSession((s) => s.setSelectedSection);
  const setProfilesMode = useSession((s) => s.setProfilesMode);
  const setActiveWorkspaceView = useSession((s) => s.setActiveWorkspaceView);
  const [colorBy, setColorBy] = useState<PlanColorBy>('berm');
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const filters = useSession((s) => s.filters);
  const setFilters = useSession((s) => s.setFilters);
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
  const bermTol = tolerances.berm_width;
  const bermMin = Number(bermTol.min ?? DEFAULT_TOLERANCES.berm_width.min);

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

  const unknownProfileCount = useMemo(() => {
    let count = 0;
    for (const status of profileStatuses.values()) {
      if (status === 'UNKNOWN') count += 1;
    }
    return count;
  }, [profileStatuses]);

  const selectedVisible = selectedSection != null && filteredResults.some((row) => row.section === selectedSection);
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

  const hasSectors = useMemo(
    () => sectorCompliance.some((sector) => Boolean(sector.sector?.trim())),
    [sectorCompliance],
  );

  const coverage = useMemo(
    () => computeDashboardCoverage(filteredResults, results ?? [], sections, bermMin),
    [filteredResults, results, sections, bermMin],
  );

  const directionalStats = useMemo(
    () =>
      computeDirectionalStats(filteredResults, {
        heightPos: Number(heightTol.pos ?? DEFAULT_TOLERANCES.bench_height.pos),
        heightNeg: Number(heightTol.neg ?? DEFAULT_TOLERANCES.bench_height.neg),
        bermMin,
      }),
    [filteredResults, heightTol.pos, heightTol.neg, bermMin],
  );

  const levelRows = useMemo(
    () => computeLevelCompliance(filteredResults),
    [filteredResults],
  );

  const priorityItems = useMemo(
    () => computePriorityReviewList(filteredResults, sections, bermMin),
    [filteredResults, sections, bermMin],
  );

  const activeFilterChips = useMemo(
    () =>
      buildActiveFilterChips(
        filters,
        {
          bench: t('table.col_bench', { defaultValue: 'Banco' }),
          sector: t('dashboard.sector', { defaultValue: 'Sector' }),
          section: t('table.col_section', { defaultValue: 'Sección' }),
          level: t('results.filters.level_nominal', { defaultValue: 'Cota nominal' }),
          noSector: t('results.filters.no_sector', { defaultValue: '(sin sector)' }),
        },
        setScenarioFilters,
      ),
    [filters, t],
  );

  const proposalSections = useMemo(
    () => [...new Set(filteredResults.map((row) => row.section))],
    [filteredResults],
  );

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
        text: sectorCompliance.map((s) => (s.pct == null ? '—' : formatLocalePercent(s.pct, language, 1))),
        textposition: 'outside',
        cliponaxis: false,
        hovertemplate: `<b>%{x}</b><br>${hoverLabel}: %{y:.1f}%<extra></extra>`,
      },
    ]) as Data[];
  }, [sectorCompliance, t, isDark, language]);

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

  if (!results || results.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-text-muted">
        {t('dashboard.empty_state')}
      </div>
    );
  }

  const sectionLengthM = sections?.[0]?.length ?? null;

  const filterTrigger = (
    <div ref={filtersRef} className="relative">
      <button
        type="button"
        aria-expanded={filtersOpen}
        aria-controls="dashboard-filter-panel"
        className="h-8 whitespace-nowrap rounded-md border border-border bg-surface-sunken px-2.5 text-xs font-medium text-text-primary hover:bg-surface-muted"
        onClick={() => setFiltersOpen((open) => !open)}
      >
        {t('dashboard.filters.label')}{activeFilterCount > 0 && ` · ${activeFilterCount}`}
      </button>
      {filtersOpen && (
        <div
          id="dashboard-filter-panel"
          ref={(panel) => {
            if (panel) {
              const bounds = panel.closest('main')?.getBoundingClientRect();
              const left = Math.max(8, (bounds?.left ?? 0) + 12);
              const right = Math.min(window.innerWidth - 8, (bounds?.right ?? window.innerWidth) - 12);
              panel.style.width = `${Math.min(352, right - left)}px`;
              panel.style.translate = '0 0';
              const rect = panel.getBoundingClientRect();
              panel.style.translate = `${Math.max(left - rect.left, Math.min(0, right - rect.right))}px 0`;
            }
          }}
          className="absolute right-0 top-full z-40 mt-1 w-[22rem] max-w-[calc(100vw-2rem)] space-y-3 rounded-lg border border-border bg-surface-raised p-3 shadow-lg"
        >
          <BenchFilter available={benchNumbers} selected={filters.bench} onChange={(bench) => setFilters({ bench })} />
          <ResultFilters results={results} filters={filters} onChange={setScenarioFilters} compact />
        </div>
      )}
    </div>
  );

  return (
    <div ref={dashboardRef} className="flex min-w-0 flex-col gap-6">
      <DashboardContextBar
        designName={designMeshInfo?.filename ?? null}
        topoName={topoMeshInfo?.filename ?? null}
        sectionLengthM={sectionLengthM}
        tolerances={tolerances}
        activeChips={activeFilterChips}
        onClearAllFilters={() => setFilters({ sector: [], section: [], level: [], bench: [] })}
        filterTrigger={filterTrigger}
      />
      <CoverageBanner coverage={coverage} defaultBermMin={bermMin} />
      <div
        className="flex min-h-0 min-w-0 flex-col xl:h-[var(--workspace-height)]"
        style={{ '--workspace-height': workspaceHeight == null ? 'auto' : `${workspaceHeight}px` } as CSSProperties}
      >
        <div
          data-slot="dashboard-filters"
          className="relative flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border pb-2 xl:flex-nowrap xl:[&_[role=group]]:flex-nowrap"
        >
          <span className="shrink-0 whitespace-nowrap text-xs text-text-muted">{t('dashboard.rail.color_by')}</span>
          <SegmentedControl
            label={t('dashboard.rail.color_by')}
            options={PLAN_COLOR_OPTIONS.map((value) => ({ value, label: t(`dashboard.rail.color_${value}`) }))}
            value={colorBy}
            onChange={setColorBy}
          />
          <span data-slot="dashboard-coverage-count" className="ml-auto text-xs tabular-nums text-text-muted">
            {t('dashboard.coverage.sections_of', {
              evaluated: formatLocaleNumber(coverage.evaluatedFilteredSections, language, 0),
              total: formatLocaleNumber(coverage.totalSectionsDefined, language, 0),
            })}
            {' · '}
            {formatLocaleNumber(coverage.comparedBenches, language, 0)}{' '}
            {t('dashboard.byLevel.compared').toLowerCase()}
          </span>
        </div>
        {filteredResults.length === 0 ? (
          <p role="status" className="py-4 text-sm text-text-muted">
            {t('dashboard.filters.no_matching_results')}
          </p>
        ) : (
          <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 pt-4 xl:grid-cols-[minmax(0,1fr)_minmax(340px,400px)] xl:grid-rows-[minmax(400px,1fr)]">
            <div data-slot="dashboard-plan" className="h-[60vh] min-h-[390px] min-w-0 xl:h-full xl:min-h-[400px]">
              <CompliancePlanView
                results={filteredResults}
                frameResults={results}
                statuses={profileStatuses}
                variant="hero"
                colorBy={colorBy}
                visibleStatuses={undefined}
                selectedSection={selectedVisible ? selectedSection : null}
                onSelectSection={setSelectedSection}
              />
            </div>
            <aside
              data-slot="dashboard-rail"
              className="min-w-0 px-4 pt-5 xl:min-h-0 xl:overflow-y-auto xl:border-l xl:border-border"
            >
              <KpiHeader
                globalScore={globalScore}
                counts={profileCounts}
                unknownCount={unknownProfileCount}
                language={language}
                t={t}
              />
              <DirectionalSummary stats={directionalStats} rows={filteredResults} />
              <details
                data-slot="parameter-detail"
                className="border-t border-border py-4"
                onToggle={(event) => {
                  if (event.currentTarget.open) event.currentTarget.scrollIntoView?.({ block: 'nearest' });
                }}
              >
                <summary className="cursor-pointer select-none text-sm font-medium text-text-primary">
                  {t('dashboard.rail.parameter_detail')}
                </summary>
                <div className="mt-2">
                  <ParameterTable breakdown={parameterBreakdown} language={language} t={t} />
                </div>
              </details>
              <SelectedSectionPanel
                name={selectedVisible ? selectedSection : null}
                sectionId={selectedVisible ? selectedId : null}
                rows={filteredResults}
                statuses={profileStatuses}
                canOpen={selectedId != null}
                onClear={() => setSelectedSection(null)}
                onOpen={() => {
                  if (selectedId != null) {
                    setSelectedProfile(selectedId);
                    setActiveWorkspaceView('profiles');
                  }
                }}
              />
            </aside>
          </div>
        )}
      </div>
      {filteredResults.length > 0 && (
        <>
          <div className="grid min-w-0 grid-cols-1 gap-6 border-t border-border pt-6 xl:grid-cols-2">
            <LevelComplianceTable
              levels={levelRows}
              activeLevels={filters.level}
              onToggleLevel={(level) => setFilters({ level: toggleDimensionValue(filters.level, level) })}
            />
            <PriorityReviewList
              items={priorityItems}
              onOpenBench={(item) => {
                if (item.sectionId == null) return;
                setSelectedProfile(item.sectionId);
                setProfilesMode('detail');
                setActiveWorkspaceView('profiles');
                useBenchFocus.getState().requestBench(item.sectionId, item.benchNum);
              }}
            />
          </div>
          <SummaryPanel
            slot="deviation-distribution"
            title={t('dashboard.histograms.title')}
            className="border-t border-border pt-6"
          >
            <DeviationHistogramsGrid rows={filteredResults} tolerances={tolerances} isDark={isDark} />
          </SummaryPanel>
          {hasSectors && (
            <SummaryPanel
              slot="sector-compliance"
              title={t('dashboard.section.by_sector')}
              className="border-t border-border pt-6"
            >
              <Plot data={sectorChartData} layout={sectorChartLayout} config={plotConfig} style={{ width: '100%' }} />
            </SummaryPanel>
          )}
          <details
            data-slot="complementary-metrics"
            className="border-t border-border pt-4"
          >
            <summary className="cursor-pointer select-none">
              <span className="text-sm font-medium text-text-primary">
                {t('dashboard.complementary.title')}
              </span>
              <span className="ml-2 text-xs text-text-muted">
                {t('dashboard.complementary.summary_hint')}
              </span>
            </summary>
            <div className="mt-4 grid min-w-0 gap-6 xl:grid-cols-2">
              <DesignAchievementPanel filters={filters} />
              <ProposalSummaryCard filters={filters} sections={proposalSections} />
            </div>
          </details>
        </>
      )}
    </div>
  );
}

function parameterLabel(p: 'height' | 'angle' | 'berm', t: Translate): string {
  switch (p) {
    case 'height': return t('dashboard.parameter.height');
    case 'angle': return t('dashboard.parameter.angle');
    case 'berm': return t('dashboard.parameter.berm');
  }
}

function formatReal(p: 'height' | 'angle' | 'berm', v: number, language?: string): string {
  if (p === 'angle') return `${formatLocaleNumber(v, language, 1)}°`;
  return `${formatLocaleNumber(v, language, 2)} m`;
}
