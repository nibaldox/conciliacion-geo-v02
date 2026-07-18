import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config, Shape } from 'plotly.js';
import { useResults, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { ComparisonResult } from '../../api/types';

// ─── Module-level icons (M3: hoisted to avoid per-render allocation) ──

const GlobalIcon = (
  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10" />
    <path d="m9 12 2 2 4-4" />
  </svg>
);

const ProfilesOkIcon = (
  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

const ProfilesNoIcon = (
  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </svg>
);

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
export function uniqueBenchNumbers(
  rows: readonly ComparisonResult[],
): number[] {
  const set = new Set<number>();
  for (const r of rows) set.add(r.bench_num);
  return [...set].sort((a, b) => a - b);
}

// ─── Binary compliance scoring (Track 1-WEB) ─────────────────
//
// The Streamlit dashboard was redesigned around binary compliance:
// every bench is either CUMPLE or NO CUMPLE (any "FUERA DE TOLERANCIA"
// is merged into NO CUMPLE). A per-bench score weights the three
// parameters (berma=60, ángulo=20, altura=20, max 100). A profile
// (i.e. a section) CUMPLEs when its average bench score ≥ 70. The
// global score is the mean of per-profile scores.

/** Maximum bench score when all three parameters CUMPLE. */
export const BENCH_SCORE_MAX = 100;

/** Per-parameter weights (sum = 100). */
export const SCORE_WEIGHTS = {
  berm: 60,
  angle: 20,
  height: 20,
} as const;

/** Threshold above which a profile is considered CUMPLE. */
export const PROFILE_CUMPLE_THRESHOLD = 70;

/**
 * Score for a single bench row. Each parameter contributes its
 * weight if it CUMPLES, 0 otherwise.
 */
export function benchScore(row: ComparisonResult): number {
  let score = 0;
  if (row.berm_status === 'CUMPLE') score += SCORE_WEIGHTS.berm;
  if (row.angle_status === 'CUMPLE') score += SCORE_WEIGHTS.angle;
  if (row.height_status === 'CUMPLE') score += SCORE_WEIGHTS.height;
  return score;
}

/** True if a profile (section) meets the CUMPLE threshold. */
export function profileCumple(score: number): boolean {
  return score >= PROFILE_CUMPLE_THRESHOLD;
}

/**
 * Mean score across all benches of a section. Returns 0 when the
 * section has no benches.
 */
export function profileScore(
  rows: readonly ComparisonResult[],
): number {
  if (rows.length === 0) return 0;
  let total = 0;
  for (const r of rows) total += benchScore(r);
  return total / rows.length;
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
    const list = map.get(r.section) ?? [];
    list.push(benchScore(r));
    map.set(r.section, list);
  }
  const out = new Map<string, number>();
  for (const [section, scores] of map) {
    const sum = scores.reduce((a, b) => a + b, 0);
    out.set(section, scores.length === 0 ? 0 : sum / scores.length);
  }
  return out;
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

/**
 * Counts of CUMPLE vs NO CUMPLE profiles (binary — FUERA is folded
 * into NO CUMPLE). Used by the global KPI cards.
 */
export interface ProfileComplianceCounts {
  cumple: number;
  noCumple: number;
}

export function computeProfileComplianceCounts(
  rows: readonly ComparisonResult[],
): ProfileComplianceCounts {
  const profiles = computeProfileScores(rows);
  let cumple = 0;
  let noCumple = 0;
  for (const score of profiles.values()) {
    if (profileCumple(score)) cumple += 1;
    else noCumple += 1;
  }
  return { cumple, noCumple };
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
  /** Percentage of benches CUMPLE on the sector (0-100). */
  pct: number;
  total: number;
}

export function computeSectorCompliance(
  rows: readonly ComparisonResult[],
): SectorCompliance[] {
  const map = new Map<string, { cumple: number; total: number }>();
  for (const r of rows) {
    const entry = map.get(r.sector) ?? { cumple: 0, total: 0 };
    entry.total += 1;
    if (r.height_status === 'CUMPLE' &&
        r.angle_status === 'CUMPLE' &&
        r.berm_status === 'CUMPLE') {
      entry.cumple += 1;
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

/**
 * Colour for a sector compliance percentage. Matches the
 * Streamlit thresholds (green ≥70, orange 50-70, red <50).
 */
export function sectorComplianceColor(pct: number): string {
  if (pct >= 70) return '#10b981'; // emerald
  if (pct >= 50) return '#f59e0b'; // amber
  return '#ef4444';                // red
}

// ─── Deviation histograms ─────────────────────────────────────

/** Numeric deviation/real-value fields used by the histograms. */
export type HistogramField = 'height_dev' | 'angle_dev' | 'delta_crest';

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

interface KPICardProps {
  title: string;
  value: string;
  valueColor: string;
  pct: number;
  icon: React.ReactNode;
}

function KPICard({ title, value, valueColor, pct, icon }: KPICardProps) {
  const safePct = Number.isFinite(pct) ? pct : 0;
  return (
    <dl className="glass-card rounded-xl p-5 flex flex-col gap-4 relative overflow-hidden group">
      <div
        className="absolute -right-6 -bottom-6 w-24 h-24 rounded-full blur-2xl opacity-10 group-hover:opacity-20 transition-opacity duration-500 pointer-events-none"
        style={{ backgroundColor: valueColor }}
      />

      <div className="flex items-center justify-between">
        <dt className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
          {title}
        </dt>
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center transition-transform group-hover:scale-105 duration-300"
          style={{ backgroundColor: `${valueColor}15`, color: valueColor }}
        >
          {icon}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <dd className="text-3xl font-extrabold tracking-tight m-0" style={{ color: 'var(--color-text-primary)' }}>
          {value}
        </dd>

        <dd className="w-full h-1.5 rounded-full overflow-hidden m-0" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div
            className="h-full rounded-full transition-all duration-1000 ease-out"
            style={{ width: `${Math.round(safePct * 100)}%`, backgroundColor: valueColor }}
          />
        </dd>
      </div>
    </dl>
  );
}

/** Threshold colour mapping (green ≥70, orange 50-70, red <50). */
function getValueColor(pct: number): string {
  if (pct >= 70) return '#10b981';
  if (pct >= 50) return '#f59e0b';
  return '#ef4444';
}

export function Dashboard() {
  const { t } = useTranslation();
  const { data: results } = useResults();
  const { data: sections } = useSections();
  const filters = useSession((s) => s.filters);
  const setFilters = useSession((s) => s.setFilters);

  // G10: bench filter propagates to every Dashboard visualization.
  const filteredResults = useMemo(
    () => filterByBench(results ?? [], filters.bench),
    [results, filters.bench],
  );

  const benchNumbers = useMemo(
    () => uniqueBenchNumbers(results ?? []),
    [results],
  );

  // Binary compliance aggregates
  const globalScore = useMemo(
    () => computeGlobalScore(filteredResults),
    [filteredResults],
  );

  const profileCounts = useMemo(
    () => computeProfileComplianceCounts(filteredResults),
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

  // Per-deviation histograms
  const heightDevs = useMemo(
    () => collectField(filteredResults, 'height_dev'),
    [filteredResults],
  );
  const angleDevs = useMemo(
    () => collectField(filteredResults, 'angle_dev'),
    [filteredResults],
  );
  const crestDevs = useMemo(
    () => collectField(filteredResults, 'delta_crest'),
    [filteredResults],
  );

  const totalBenches = filteredResults.length;
  const nSections = sections?.length ?? 0;
  const filterActive = filters.bench.length > 0;

  const plotConfig = useMemo<Partial<Config>>(
    () => ({ displayModeBar: false, responsive: true }),
    [],
  );

  // ── Plotly data ──
  const parameterChartData = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        name: t('status.cumple'),
        x: parameterBreakdown.map((p) => parameterLabel(p.parameter, t)),
        y: parameterBreakdown.map((p) => p.cumple),
        marker: { color: '#10b981' },
      },
      {
        type: 'bar',
        name: t('status.no_cumple'),
        x: parameterBreakdown.map((p) => parameterLabel(p.parameter, t)),
        y: parameterBreakdown.map((p) => p.noCumple),
        marker: { color: '#ef4444' },
      },
    ],
    [parameterBreakdown, t],
  );

  const parameterLayout = useMemo<Partial<Layout>>(
    () => ({
      barmode: 'stack',
      height: 320,
      margin: { l: 50, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: 'var(--color-text-secondary)' },
      xaxis: { title: { text: t('dashboard.plot.axis.parameter') } },
      yaxis: { title: { text: t('dashboard.plot.axis.bench_count') } },
      legend: { orientation: 'h', y: -0.2 },
    }),
    [t],
  );

  const sectorChartData = useMemo<Data[]>(() => {
    const sectors = sectorCompliance.map((s) => s.sector);
    const colors = sectorCompliance.map((s) => sectorComplianceColor(s.pct));
    const hoverLabel = t('dashboard.plot.hover.compliance_label');
    return [
      {
        type: 'bar',
        x: sectors,
        y: sectorCompliance.map((s) => s.pct),
        marker: { color: colors },
        text: sectorCompliance.map((s) => `${s.pct.toFixed(1)}%`),
        textposition: 'outside',
        hovertemplate: `<b>%{x}</b><br>${hoverLabel}: %{y:.1f}%<extra></extra>`,
      },
    ] as unknown as Data[];
  }, [sectorCompliance, t]);

  const sectorChartLayout = useMemo<Partial<Layout>>(
    () => ({
      height: 320,
      margin: { l: 50, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: 'var(--color-text-secondary)' },
      xaxis: { title: { text: t('dashboard.plot.axis.sector') } },
      yaxis: { title: { text: t('dashboard.plot.axis.pct_compliance') }, range: [0, 105] },
    }),
    [t],
  );

  const histogramLayoutBase = useMemo<Partial<Layout>>(
    () => ({
      height: 260,
      margin: { l: 50, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: 'var(--color-text-secondary)' },
    }),
    [],
  );

  function buildHistogram(
    values: readonly number[],
    title: string,
    xLabel: string,
    tolerance: number,
  ): { data: Data[]; layout: Partial<Layout> } {
    const shape: Partial<Shape> = {
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: -tolerance,
      x1: tolerance,
      y0: 0,
      y1: 1,
      fillcolor: 'rgba(16, 185, 129, 0.15)',
      line: { color: 'rgba(16, 185, 129, 0.6)', width: 1 },
      layer: 'below',
    };
    return {
      data: [
        {
          type: 'histogram',
          x: [...values],
          nbinsx: 15,
          marker: { color: '#3b82f6' },
          name: title,
        },
      ] as unknown as Data[],
      layout: {
        ...histogramLayoutBase,
        xaxis: { title: { text: xLabel } },
        yaxis: { title: { text: t('dashboard.plot.axis.frequency') } },
        shapes: [shape],
        showlegend: false,
      },
    };
  }

  const heightHist = useMemo(
    () => buildHistogram(
      heightDevs,
      t('dashboard.parameter.height'),
      t('dashboard.plot.axis.delta_height'),
      1.0,
    ),
    [heightDevs, histogramLayoutBase, t],
  );
  const angleHist = useMemo(
    () => buildHistogram(
      angleDevs,
      t('dashboard.parameter.angle'),
      t('dashboard.plot.axis.delta_angle'),
      3.0,
    ),
    [angleDevs, histogramLayoutBase, t],
  );
  const crestHist = useMemo(
    () => buildHistogram(
      crestDevs,
      t('dashboard.parameter.berm'),
      t('dashboard.plot.axis.delta_crest'),
      1.0,
    ),
    [crestDevs, histogramLayoutBase, t],
  );

  if (!results || results.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        {t('dashboard.empty_state')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary text */}
      <div className="flex items-center justify-between border-b pb-3 shrink-0" style={{ borderColor: 'var(--color-border)' }}>
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          {t('dashboard.title')}
        </p>
        <span className="text-xs px-2.5 py-1 rounded-full font-semibold" style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-secondary)' }}>
          {t('dashboard.summary.bench_section', { benches: totalBenches, sections: nSections })}
        </span>
      </div>

      {/* G10: bench filter */}
      <div className="glass-panel rounded-xl p-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider mr-1" style={{ color: 'var(--color-text-muted)' }}>
          {t('dashboard.bench_filter.label')}
        </span>
        <button
          type="button"
          onClick={() => setFilters({ bench: [] })}
          className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${
            !filterActive ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]'
          }`}
          aria-pressed={!filterActive}
          aria-label={`${t('dashboard.bench_filter.all')}, ${!filterActive ? 'activado' : 'desactivado'}`}
        >
          {t('dashboard.bench_filter.all')}
        </button>
        {benchNumbers.map((n) => {
          const selected = filters.bench.includes(n);
          return (
            <button
              key={n}
              type="button"
              onClick={() => {
                const next = selected
                  ? filters.bench.filter((b) => b !== n)
                  : [...filters.bench, n];
                setFilters({ bench: next });
              }}
              className={`text-xs px-2.5 py-1 rounded-full font-medium tabular-nums transition-colors ${
                selected ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]'
              }`}
              aria-pressed={selected}
              aria-label={`Banco ${n}, ${selected ? 'activado' : 'desactivado'}`}
            >
              B{n}
            </button>
          );
        })}
      </div>

      {/* Section 1: Global KPI */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          title={t('dashboard.kpi.global_score')}
          value={globalScore.toFixed(1)}
          valueColor={getValueColor(globalScore)}
          pct={globalScore / 100}
          icon={GlobalIcon}
        />
        <KPICard
          title={t('dashboard.kpi.profiles_ok')}
          value={String(profileCounts.cumple)}
          valueColor="#10b981"
          pct={profileCounts.cumple + profileCounts.noCumple === 0
            ? 0
            : profileCounts.cumple / (profileCounts.cumple + profileCounts.noCumple)}
          icon={ProfilesOkIcon}
        />
        <KPICard
          title={t('dashboard.kpi.profiles_no')}
          value={String(profileCounts.noCumple)}
          valueColor="#ef4444"
          pct={profileCounts.cumple + profileCounts.noCumple === 0
            ? 0
            : profileCounts.noCumple / (profileCounts.cumple + profileCounts.noCumple)}
          icon={ProfilesNoIcon}
        />
      </div>

      {/* Section 2: Parameter breakdown */}
      <div className="glass-panel rounded-xl p-5 space-y-4">
        <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
          {t('dashboard.section.parameter_breakdown')}
        </p>

        {parameterBreakdown.some((p) => p.cumple + p.noCumple > 0) && (
          <Plot
            data={parameterChartData}
            layout={parameterLayout}
            config={plotConfig}
            style={{ width: '100%' }}
          />
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left" style={{ color: 'var(--color-text-muted)' }}>
                <th className="py-2 pr-4 font-semibold uppercase tracking-wider">{t('dashboard.table.parameter')}</th>
                <th className="py-2 pr-4 font-semibold uppercase tracking-wider text-right">{t('dashboard.table.pct_cumple')}</th>
                <th className="py-2 pr-4 font-semibold uppercase tracking-wider text-right">{t('status.cumple')}</th>
                <th className="py-2 pr-4 font-semibold uppercase tracking-wider text-right">{t('status.no_cumple')}</th>
                <th className="py-2 pr-4 font-semibold uppercase tracking-wider text-right">{t('dashboard.table.value_avg')}</th>
              </tr>
            </thead>
            <tbody>
              {parameterBreakdown.map((p) => {
                const total = p.cumple + p.noCumple;
                const pct = total === 0 ? 0 : (p.cumple / total) * 100;
                const avgReal = p.realCount === 0 ? null : p.realSum / p.realCount;
                return (
                  <tr key={p.parameter} className="border-t" style={{ borderColor: 'var(--color-border)' }}>
                    <td className="py-2 pr-4 font-medium" style={{ color: 'var(--color-text-primary)' }}>
                      {parameterLabel(p.parameter, t)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums" style={{ color: getValueColor(pct) }}>
                      {pct.toFixed(1)}%
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums" style={{ color: '#10b981' }}>
                      {p.cumple}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums" style={{ color: '#ef4444' }}>
                      {p.noCumple}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>
                      {avgReal == null ? '—' : formatReal(p.parameter, avgReal)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Section 3: Sector compliance */}
      {sectorCompliance.length > 0 && (
        <div className="glass-panel rounded-xl p-5 space-y-3">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
            {t('dashboard.section.sector_compliance')}
          </p>
          <Plot
            data={sectorChartData}
            layout={sectorChartLayout}
            config={plotConfig}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* Section 4: Deviation histograms with tolerance bands */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <HistogramPanel
          title={t('dashboard.section.deviation_height')}
          chart={heightHist}
          config={plotConfig}
          emptyText={t('dashboard.histogram.no_data')}
        />
        <HistogramPanel
          title={t('dashboard.section.deviation_angle')}
          chart={angleHist}
          config={plotConfig}
          emptyText={t('dashboard.histogram.no_data')}
        />
        <HistogramPanel
          title={t('dashboard.section.deviation_crest')}
          chart={crestHist}
          config={plotConfig}
          emptyText={t('dashboard.histogram.no_data')}
        />
      </div>
    </div>
  );
}

// ─── Small UI helpers ────────────────────────────────────────

function parameterLabel(
  p: 'height' | 'angle' | 'berm',
  t: (key: string) => string,
): string {
  switch (p) {
    case 'height': return t('dashboard.parameter.height');
    case 'angle':  return t('dashboard.parameter.angle');
    case 'berm':   return t('dashboard.parameter.berm');
  }
}

function formatReal(p: 'height' | 'angle' | 'berm', v: number): string {
  if (p === 'height') return `${v.toFixed(2)} m`;
  if (p === 'angle')  return `${v.toFixed(1)}°`;
  return `${v.toFixed(2)} m`;
}

interface HistogramPanelProps {
  title: string;
  chart: { data: Data[]; layout: Partial<Layout> };
  config: Partial<Config>;
  emptyText: string;
}

function HistogramPanel({ title, chart, config, emptyText }: HistogramPanelProps) {
  const hasData = chart.data.some((d) => {
    const x = (d as { x?: unknown }).x;
    return Array.isArray(x) && x.length > 0;
  });
  return (
    <div className="glass-panel rounded-xl p-5 space-y-3">
      <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
        {title}
      </p>
      {hasData ? (
        <Plot
          data={chart.data}
          layout={chart.layout}
          config={config}
          style={{ width: '100%' }}
        />
      ) : (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {emptyText}
        </p>
      )}
    </div>
  );
}
