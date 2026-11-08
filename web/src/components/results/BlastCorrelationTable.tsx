import { useTranslation } from 'react-i18next';
import type { BlastCorrelationRow, BlastDefinitions } from '../../api/types';
import {
  formatKg,
  formatMJ,
  formatGramsPerTon,
  formatPowderFactor,
  formatBreakMeters,
  formatDensityShort,
} from './blastFormatters';

const TH_LEFT = 'px-3 py-2 text-left text-xs font-medium text-text-muted whitespace-nowrap';
const TH_RIGHT = 'px-3 py-2 text-right text-xs font-medium text-text-muted whitespace-nowrap';
const TD_NUM = 'px-3 py-2 text-right tabular-nums text-text-secondary';

/**
 * Per-section blast-correlation table.
 *
 * Pure presentational: receives the row list and renders the full
 * 11-column table with the highlighted g/ton column styled as the
 * primary KPI. No data fetching, no state. The parent
 * ``BlastCorrelation`` is responsible for the loading/empty/error
 * states.
 */
export function BlastCorrelationTable({ rows, definitions }: { rows: BlastCorrelationRow[]; definitions?: BlastDefinitions }) {
  const { t } = useTranslation();

  const show = (value: number | null | undefined, formatter: (value: number | null | undefined) => string) => value == null || !Number.isFinite(value) ? t('blast.missing_value') : formatter(value);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            <th className={TH_LEFT}>{t('blast.col_section', { defaultValue: 'Sección' })}</th>
            <th className={TH_LEFT}>{t('blast.col_sector', { defaultValue: 'Sector' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_wells', { defaultValue: 'Pozos' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_total_kg', { defaultValue: 'Carga total' })}</th>
            <th className={`${TH_RIGHT} !text-text-primary`} data-primary="true" title={definitions?.pf_voronoi_bench_g_per_ton?.formula}>
              {t('blast.col_pf_primary')}
            </th>
            <th className={TH_RIGHT} title={definitions?.pf_g_per_ton?.formula}>{t('blast.col_pf_secondary')}</th>
            <th className={TH_RIGHT} title={definitions?.pf_g_per_ton_net?.formula}>{t('blast.col_pf_net_corrective')}</th>
            <th className={TH_RIGHT} title={definitions?.pf_vol_kgm3?.formula}>{t('blast.col_pf_vol', { defaultValue: 'PF vol. (kg/m³)' })}</th>
            <th className={TH_RIGHT} title={definitions?.pf_area_kgm2?.formula}>{t('blast.col_pf_area', { defaultValue: 'PF área (kg/m²)' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_energy', { defaultValue: 'Energía (MJ)' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_over_break', { defaultValue: 'Over-break (m)' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_under_break', { defaultValue: 'Under-break (m)' })}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.section_name}>
              <td className="px-3 py-2 font-mono text-text-primary">{row.section_name}</td>
              <td className="px-3 py-2 text-text-secondary">
                {row.sector ? (
                  <span>
                    {row.sector}
                    <span
                      className="ml-1 tabular-nums text-text-muted"
                      data-testid={`row-sector-rho-${row.section_name}`}
                    >
                      ({formatDensityShort(row.rock_density_used)})
                    </span>
                  </span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>
              <td className={TD_NUM}>{row.num_wells}</td>
              <td className={TD_NUM}>{show(row.total_kg, formatKg)}{row.total_kg == null && row.n_kg_known != null && row.n_kg_missing != null && <div>{t('blast.mass_coverage', { known: row.n_kg_known, missing: row.n_kg_missing })}</div>}</td>
              <td className="px-3 py-2 text-right text-sm font-semibold tabular-nums text-text-primary">
                {show(row.pf_voronoi_bench_g_per_ton_section, formatGramsPerTon)}
                {row.pf_voronoi_bench_g_per_ton_section == null && Object.entries(row.pf_voronoi_bench_status_counts ?? {}).map(([status, count]) => <div key={status} className="text-xs font-normal text-text-secondary">{t(`blast.pf_status.${status}`, { defaultValue: status })} ({t('blast.hole_count', { count })})</div>)}
                {row.pf_voronoi_bench_source_dominant?.startsWith('footprint:') && (
                  <div
                    className="text-xs font-normal text-text-secondary"
                    data-testid={`pf-footprint-source-${row.section_name}`}
                    title={definitions?.pf_voronoi_bench_g_per_ton?.footprint ?? t('blast.pf_footprint_estimated_tooltip')}
                  >
                    {row.pf_voronoi_bench_source_dominant === 'footprint:user_polygon'
                      ? t('blast.pf_footprint_user')
                      : t('blast.pf_footprint_estimated')}
                  </div>
                )}
              </td>
              <td className={TD_NUM}>{show(row.pf_g_per_ton_avg, formatGramsPerTon)}</td>
              <td className={TD_NUM}>{show(row.pf_g_per_ton_net_avg, formatGramsPerTon)}</td>
              <td className={TD_NUM}>{show(row.pf_vol_avg_kgm3, formatPowderFactor)}</td>
              <td className={TD_NUM}>{show(row.pf_area_avg_kgm2, formatPowderFactor)}</td>
              <td className={TD_NUM}>{row.energy_total_mj == null && row.energy_known_mj != null && Number.isFinite(row.energy_known_mj) ? t('blast.energy_partial', { value: row.energy_known_mj.toFixed(2), coverage: row.energy_coverage_kg_fraction != null ? (row.energy_coverage_kg_fraction * 100).toFixed(0) + ' %' : t('blast.missing_value') }) : <>{show(row.energy_total_mj, formatMJ)}{row.energy_coverage_kg_fraction != null && row.energy_coverage_kg_fraction < 1 && <div>{t('blast.energy_coverage_corrective', { value: (row.energy_coverage_kg_fraction * 100).toFixed(0) })}</div>}</>}</td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--status-nok-text)]">
                {show(row.avg_over_break, formatBreakMeters)} <span>n = {row.n_over}</span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--status-warn-text)]">
                {show(row.avg_under_break, formatBreakMeters)} <span>n = {row.n_under}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
