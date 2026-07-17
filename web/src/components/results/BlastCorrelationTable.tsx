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
    <div
      className="overflow-x-auto rounded-lg border"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <table className="w-full text-xs">
        <thead>
          <tr
            style={{
              backgroundColor: 'var(--color-surface-raised)',
              color: 'var(--color-text-secondary)',
            }}
          >
            <th className="text-left font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_section', { defaultValue: 'Sección' })}
            </th>
            <th className="text-left font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_sector', { defaultValue: 'Sector' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_wells', { defaultValue: 'Pozos' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_total_kg', { defaultValue: 'Carga total' })}
            </th>
            {/* Highlighted primary column */}
            <th
              className="text-right font-mono font-bold uppercase tracking-wider px-3 py-2"
              style={{
                backgroundColor: 'var(--color-accent-bg, rgba(249,115,22,0.12))',
                color: 'var(--color-accent-bright, #f97316)',
              }}
            >
              {t('blast.col_pf_g_per_ton', { defaultValue: 'Factor de carga (g/ton)' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_pf_g_per_ton_net', { defaultValue: 'PF s/pasadura (g/ton)' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_pf_vol', { defaultValue: 'PF vol. (kg/m³)' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_pf_area', { defaultValue: 'PF área (kg/m²)' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_energy', { defaultValue: 'Energía (MJ)' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_over_break', { defaultValue: 'Over-break (m)' })}
            </th>
            <th className="text-right font-mono font-semibold uppercase tracking-wider px-3 py-2">
              {t('blast.col_under_break', { defaultValue: 'Under-break (m)' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.section_name}
              className="border-t"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <td
                className="px-3 py-2 font-mono"
                style={{ color: 'var(--color-text-primary)' }}
              >
                {row.section_name}
              </td>
              <td
                className="px-3 py-2 font-mono"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {row.sector ? (
                  <span>
                    {row.sector}
                    <span
                      className="ml-1 text-[10px] opacity-70"
                      data-testid={`row-sector-rho-${row.section_name}`}
                    >
                      ({formatDensityShort(row.rock_density_used)})
                    </span>
                  </span>
                ) : (
                  <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                )}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {row.num_wells}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {formatKg(row.total_kg)}
              </td>
              {/* Highlighted primary value */}
              <td
                className="px-3 py-2 text-right tabular-nums font-extrabold text-sm"
                style={{
                  backgroundColor: 'var(--color-accent-bg, rgba(249,115,22,0.08))',
                  color: 'var(--color-accent-bright, #f97316)',
                }}
              >
                {formatGramsPerTon(row.pf_g_per_ton_avg)}
              </td>
              {/* Additive net metric (bench height excluding sub-drill) */}
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {formatGramsPerTon(row.pf_g_per_ton_net_avg)}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {formatPowderFactor(row.pf_vol_avg_kgm3)}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {formatPowderFactor(row.pf_area_avg_kgm2)}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {formatMJ(row.energy_total_mj)}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-status-error, #ef4444)' }}
              >
                {formatBreakMeters(row.avg_over_break)}
              </td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                style={{ color: 'var(--color-status-warning, #f59e0b)' }}
              >
                {formatBreakMeters(row.avg_under_break)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}