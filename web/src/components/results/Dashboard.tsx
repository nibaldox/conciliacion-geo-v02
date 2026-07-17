import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';
import { useResults, useSections } from '../../api/hooks';
import { formatPct } from '../../utils/format';
import { useSession } from '../../stores/session';
import { worstOfThree } from './ProfileView/domain/status';
import type { ComparisonResult } from '../../api/types';

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

// ─── G05: over-excavation / debt area by sector ──────────────
//
// Cross-section area proxy (m²) computed client-side from the
// crest deviation: a positive `delta_crest` means the real crest
// sits beyond the design face (over-excavation / overbreak); a
// negative value means material is missing (debt / underbreak).
// We scale the horizontal offset by the real bench height to get
// an approximate face area. Rows with null delta or null height
// contribute zero. Aggregated per sector.

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

// ─── G06: deviation distribution ────────────────────────────

/** Numeric deviation fields available on a comparison row. */
export type DeviationField =
  | 'delta_crest'
  | 'delta_toe'
  | 'height_dev'
  | 'angle_dev';

/** Collect finite, non-null values of a deviation field across rows. */
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

// ─── G07: status counts by sector ───────────────────────────
//
// Each comparison row resolves to a single worst-case status
// (worstOfThree over height/angle/berm). We count benches per
// sector and stack CUMPLE / FUERA / NO_CUMPLE. Rows that parse
// to UNKNOWN (no usable status) are folded into NO_CUMPLE so the
// stacked totals always equal the number of rows.

export interface SectorStatusCounts {
  sector: string;
  CUMPLE: number;
  FUERA: number;
  NO_CUMPLE: number;
}

export function computeStatusCountsBySector(
  rows: readonly ComparisonResult[],
): SectorStatusCounts[] {
  const map = new Map<string, SectorStatusCounts>();
  for (const r of rows) {
    const entry =
      map.get(r.sector) ?? { sector: r.sector, CUMPLE: 0, FUERA: 0, NO_CUMPLE: 0 };
    const status = worstOfThree(r.height_status, r.angle_status, r.berm_status);
    if (status === 'CUMPLE') entry.CUMPLE += 1;
    else if (status === 'FUERA') entry.FUERA += 1;
    else entry.NO_CUMPLE += 1;
    map.set(r.sector, entry);
  }
  return [...map.values()].sort((a, b) => a.sector.localeCompare(b.sector));
}

interface KPICardProps {
  title: string;
  value: string;
  valueColor: string;
  pct: number;
  icon: React.ReactNode;
}

function KPICard({ title, value, valueColor, pct, icon }: KPICardProps) {
  return (
    <div className="glass-card rounded-xl p-5 flex flex-col gap-4 relative overflow-hidden group">
      {/* Glow Effect */}
      <div 
        className="absolute -right-6 -bottom-6 w-24 h-24 rounded-full blur-2xl opacity-10 group-hover:opacity-20 transition-opacity duration-500 pointer-events-none"
        style={{ backgroundColor: valueColor }}
      />
      
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
          {title}
        </span>
        <div 
          className="w-9 h-9 rounded-lg flex items-center justify-center transition-transform group-hover:scale-105 duration-300"
          style={{ backgroundColor: `${valueColor}15`, color: valueColor }}
        >
          {icon}
        </div>
      </div>
      
      <div className="flex flex-col gap-2">
        <span className="text-3xl font-extrabold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
          {value}
        </span>
        
        {/* Dynamic ambient progress bar */}
        <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div 
            className="h-full rounded-full transition-all duration-1000 ease-out"
            style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: valueColor }}
          />
        </div>
      </div>
    </div>
  );
}

function getValueColor(pct: number): string {
  if (pct > 0.8) return '#10b981'; // Vivid emerald
  if (pct > 0.6) return '#f59e0b'; // Vivid amber
  return '#ef4444'; // Vivid red
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

  const areasBySector = useMemo(
    () => computeAreasBySector(filteredResults),
    [filteredResults],
  );

  const crestDeviations = useMemo(
    () => collectDeviations(filteredResults, 'delta_crest'),
    [filteredResults],
  );

  const statusBySector = useMemo(
    () => computeStatusCountsBySector(filteredResults),
    [filteredResults],
  );

  const stats = useMemo(() => {
    if (filteredResults.length === 0) {
      return {
        total: 0,
        globalPct: 0,
        heightPct: 0,
        anglePct: 0,
        bermPct: 0,
        nSections: 0,
      };
    }

    const total = filteredResults.length;

    // Global compliance: all three statuses are CUMPLE
    const globalOk = filteredResults.filter(
      (r) =>
        r.height_status === 'CUMPLE' &&
        r.angle_status === 'CUMPLE' &&
        r.berm_status === 'CUMPLE',
    ).length;

    // Per-parameter compliance
    const heightOk = filteredResults.filter((r) => r.height_status === 'CUMPLE').length;
    const angleOk = filteredResults.filter((r) => r.angle_status === 'CUMPLE').length;
    const bermOk = filteredResults.filter((r) => r.berm_status === 'CUMPLE').length;

    return {
      total,
      globalPct: globalOk / total,
      heightPct: heightOk / total,
      anglePct: angleOk / total,
      bermPct: bermOk / total,
      nSections: sections?.length ?? 0,
    };
  }, [filteredResults, sections]);

  // Memoized Plotly data/layout for the 3 charts so Plotly.react
  // diffing only fires when the underlying memoized inputs change,
  // not on every render (e.g. on each bench-filter keystroke).
  const areasData = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        name: t('dashboard.over_excavation'),
        x: areasBySector.map((a) => a.sector),
        y: areasBySector.map((a) => a.overExcavation),
        marker: { color: '#ef4444' },
      },
      {
        type: 'bar',
        name: t('dashboard.debt'),
        x: areasBySector.map((a) => a.sector),
        y: areasBySector.map((a) => a.debt),
        marker: { color: '#f59e0b' },
      },
    ],
    [areasBySector, t],
  );
  const areasLayout = useMemo<Partial<Layout>>(
    () => ({
      barmode: 'stack',
      height: 320,
      margin: { l: 50, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: 'var(--color-text-secondary)' },
      xaxis: { title: t('dashboard.sector') },
      yaxis: { title: t('dashboard.area_m2') },
      legend: { orientation: 'h', y: -0.2 },
    }),
    [t],
  );

  const crestData = useMemo<Data[]>(
    () => [
      {
        type: 'histogram',
        x: crestDeviations,
        nbinsx: 15,
        marker: { color: '#3b82f6' },
      },
    ] as unknown as Data[],
    [crestDeviations],
  );
  const crestLayout = useMemo<Partial<Layout>>(
    () => ({
      height: 300,
      margin: { l: 50, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: 'var(--color-text-secondary)' },
      xaxis: { title: t('dashboard.crest_delta_m') },
      yaxis: { title: t('dashboard.frequency') },
    }),
    [t],
  );

  const statusData = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        name: t('status.cumple'),
        x: statusBySector.map((s) => s.sector),
        y: statusBySector.map((s) => s.CUMPLE),
        marker: { color: '#10b981' },
      },
      {
        type: 'bar',
        name: t('status.fuera'),
        x: statusBySector.map((s) => s.sector),
        y: statusBySector.map((s) => s.FUERA),
        marker: { color: '#f59e0b' },
      },
      {
        type: 'bar',
        name: t('status.no_cumple'),
        x: statusBySector.map((s) => s.sector),
        y: statusBySector.map((s) => s.NO_CUMPLE),
        marker: { color: '#ef4444' },
      },
    ],
    [statusBySector, t],
  );
  const statusLayout = useMemo<Partial<Layout>>(
    () => ({
      barmode: 'stack',
      height: 320,
      margin: { l: 50, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: 'var(--color-text-secondary)' },
      xaxis: { title: t('dashboard.sector') },
      yaxis: { title: t('dashboard.bench_count') },
      legend: { orientation: 'h', y: -0.2 },
    }),
    [t],
  );
  const plotConfig = useMemo<Partial<Config>>(
    () => ({ displayModeBar: false, responsive: true }),
    [],
  );

  if (!results || results.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        {t('dashboard.empty_state')}
      </div>
    );
  }

  // Beautiful SVG Icons
  const GlobalIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );

  const HeightIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="m8 3 4-4 4 4" />
      <path d="m8 21 4 4 4-4" />
      <line x1="12" y1="1" x2="12" y2="23" />
    </svg>
  );

  const AngleIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 21H3V3" />
      <path d="M3 21c7.5-7.5 10.5-12 18-18" />
    </svg>
  );

  const BermIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 17h6l4-10h10" />
      <path d="m18 3 4 4-4 4" />
      <line x1="22" y1="7" x2="12" y2="7" />
    </svg>
  );

  const filterActive = filters.bench.length > 0;

  return (
    <div className="space-y-6">
      {/* Summary text */}
      <div className="flex items-center justify-between border-b pb-3 shrink-0" style={{ borderColor: 'var(--color-border)' }}>
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Resumen General de Conciliación
        </p>
        <span className="text-xs px-2.5 py-1 rounded-full font-semibold" style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-secondary)' }}>
          {stats.total} Bancos / {stats.nSections} Secciones
        </span>
      </div>

      {/* G10: bench filter — pills that propagate to every chart below */}
      <div className="glass-panel rounded-xl p-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider mr-1" style={{ color: 'var(--color-text-muted)' }}>
          Banco:
        </span>
        <button
          type="button"
          onClick={() => setFilters({ bench: [] })}
          className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${
            !filterActive ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]'
          }`}
          aria-pressed={!filterActive}
        >
          Todos
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
            >
              B{n}
            </button>
          );
        })}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPICard
          title={t('dashboard.kpi_global')}
          value={formatPct(stats.globalPct)}
          valueColor={getValueColor(stats.globalPct)}
          pct={stats.globalPct}
          icon={GlobalIcon}
        />
        <KPICard
          title={t('dashboard.kpi_height')}
          value={formatPct(stats.heightPct)}
          valueColor={getValueColor(stats.heightPct)}
          pct={stats.heightPct}
          icon={HeightIcon}
        />
        <KPICard
          title={t('dashboard.kpi_angle')}
          value={formatPct(stats.anglePct)}
          valueColor={getValueColor(stats.anglePct)}
          pct={stats.anglePct}
          icon={AngleIcon}
        />
        <KPICard
          title={t('dashboard.kpi_berm')}
          value={formatPct(stats.bermPct)}
          valueColor={getValueColor(stats.bermPct)}
          pct={stats.bermPct}
          icon={BermIcon}
        />
      </div>

      {/* G05: over-excavation / debt area by sector */}
      {areasBySector.length > 0 && (
        <div className="glass-panel rounded-xl p-5 space-y-3">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
            {t('dashboard.areas_title')}
          </p>
          <Plot
            data={areasData}
            layout={areasLayout}
            config={plotConfig}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* G06: deviation distribution (crest) */}
      <div className="glass-panel rounded-xl p-5 space-y-3">
        <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
          {t('dashboard.crest_dev_title')}
        </p>
        {crestDeviations.length > 0 ? (
          <Plot
            data={crestData}
            layout={crestLayout}
            config={plotConfig}
            style={{ width: '100%' }}
          />
        ) : (
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {t('dashboard.no_deviation_data')}
          </p>
        )}
      </div>

      {/* G07: status counts stacked by sector */}
      {statusBySector.length > 0 && (
        <div className="glass-panel rounded-xl p-5 space-y-3">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
            {t('dashboard.compliance_title')}
          </p>
          <Plot
            data={statusData}
            layout={statusLayout}
            config={plotConfig}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* Visual bars & detail statistics */}
      <div className="glass-panel rounded-xl p-5 space-y-4">
        <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
          {t('dashboard.breakdown_title')}
        </p>
        <div className="space-y-4">
          {([
            [t('dashboard.kpi_global'), stats.globalPct, GlobalIcon],
            [t('dashboard.kpi_height'), stats.heightPct, HeightIcon],
            [t('dashboard.kpi_angle'), stats.anglePct, AngleIcon],
            [t('dashboard.kpi_berm'), stats.bermPct, BermIcon],
          ] as const).map(([label, pct, icon]) => (
            <div key={label} className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <div className="flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
                  <span className="w-4 h-4 opacity-70">{icon}</span>
                  <span className="font-medium">{label}</span>
                </div>
                <span className="font-bold" style={{ color: getValueColor(pct) }}>
                  {formatPct(pct)}
                </span>
              </div>
              <div className="w-full rounded-full h-2 relative overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
                {/* Ambient glow behind progress bar */}
                <div 
                  className="absolute h-full rounded-full blur-[1px] opacity-40 transition-all duration-1000"
                  style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: getValueColor(pct) }}
                />
                <div
                  className="absolute h-full rounded-full transition-all duration-1000 ease-out"
                  style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: getValueColor(pct) }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
