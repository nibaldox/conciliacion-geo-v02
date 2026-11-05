import { useTranslation } from 'react-i18next';
import type { BlastCorrelationRow } from '../../api/types';
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
export function BlastCorrelationTable({ rows }: { rows: BlastCorrelationRow[] }) {
  const { t } = useTranslation();

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            <th className={TH_LEFT}>{t('blast.col_section', { defaultValue: 'Sección' })}</th>
            <th className={TH_LEFT}>{t('blast.col_sector', { defaultValue: 'Sector' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_wells', { defaultValue: 'Pozos' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_total_kg', { defaultValue: 'Carga total' })}</th>
            <th className={`${TH_RIGHT} !text-text-primary`} data-primary="true">
              {t('blast.col_pf_g_per_ton', { defaultValue: 'Factor de carga (g/ton)' })}
            </th>
            <th className={TH_RIGHT}>{t('blast.col_pf_g_per_ton_net', { defaultValue: 'PF s/pasadura (g/ton)' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_pf_vol', { defaultValue: 'PF vol. (kg/m³)' })}</th>
            <th className={TH_RIGHT}>{t('blast.col_pf_area', { defaultValue: 'PF área (kg/m²)' })}</th>
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
              <td className={TD_NUM}>{formatKg(row.total_kg)}</td>
              <td className="px-3 py-2 text-right text-sm font-semibold tabular-nums text-text-primary">
                {formatGramsPerTon(row.pf_g_per_ton_avg)}
              </td>
              <td className={TD_NUM}>{formatGramsPerTon(row.pf_g_per_ton_net_avg)}</td>
              <td className={TD_NUM}>{formatPowderFactor(row.pf_vol_avg_kgm3)}</td>
              <td className={TD_NUM}>{formatPowderFactor(row.pf_area_avg_kgm2)}</td>
              <td className={TD_NUM}>{formatMJ(row.energy_total_mj)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--status-nok-text)]">
                {formatBreakMeters(row.avg_over_break)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--status-warn-text)]">
                {formatBreakMeters(row.avg_under_break)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
