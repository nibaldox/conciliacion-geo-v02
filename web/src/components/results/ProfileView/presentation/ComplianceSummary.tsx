/**
 * ComplianceSummary — compact card with the 3-status counts and a
 * horizontal stacked bar showing the distribution.
 *
 * "X of Y within tolerance" headline, then a 3-segment bar in
 * semantic colors, then a small legend.
 *
 * Computed from the full bench list (not the filtered view) so it
 * always reflects the section's actual compliance.
 */

import { useTranslation } from 'react-i18next';
import type { Bench } from '../domain/types';
import { useComplianceStats } from '../application';
import { STATUS_BG_VAR, STATUS_FG_VAR, STATUS_PRESENTATION_ORDER, STATUS_ICON } from '../domain/status';

export interface ComplianceSummaryProps {
  readonly benches: readonly Bench[];
}

export function ComplianceSummary({ benches }: ComplianceSummaryProps) {
  const { t } = useTranslation();
  const stats = useComplianceStats(benches);

  const pct = (n: number): string => (stats.total === 0 ? '—' : `${Math.round((n / stats.total) * 100)}%`);

  return (
    <section
      data-slot="compliance-summary"
      className="rounded-lg p-4 flex flex-col gap-3"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
      }}
      aria-label={t('profileView.summary.aria', { defaultValue: 'Resumen de cumplimiento' })}
    >
      {/* Headline */}
      <header className="flex items-baseline justify-between gap-4">
        <h3
          className="text-[11px] uppercase tracking-wider font-semibold"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('profileView.summary.title', { defaultValue: 'Cumplimiento' })}
        </h3>
        <span className="text-xs tabular-nums" style={{ color: 'var(--color-text-muted)' }}>
          {stats.total === 0
            ? t('profileView.summary.no_benches', { defaultValue: 'Sin bancos' })
            : t('profileView.summary.headline', {
                defaultValue: '{{within}} de {{total}} dentro de tolerancia',
                within: stats.withinTolerance,
                total: stats.total,
              })}
        </span>
      </header>

      {/* Stacked bar */}
      <div
        className="h-2 w-full rounded-full overflow-hidden flex"
        role="img"
        aria-label={t('profileView.summary.bar_aria', {
          defaultValue: 'Distribución de cumplimiento',
        })}
        style={{ backgroundColor: 'var(--color-surface-muted)' }}
      >
        {STATUS_PRESENTATION_ORDER.map((status) => {
          const n = stats.counts[status];
          if (n === 0) return null;
          const widthPct = (n / stats.total) * 100;
          return (
            <div
              key={status}
              data-status={status}
              style={{
                width: `${widthPct}%`,
                backgroundColor: STATUS_BG_VAR[status],
              }}
              title={`${status}: ${n} (${pct(n)})`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {STATUS_PRESENTATION_ORDER.map((status) => {
          const n = stats.counts[status];
          return (
            <li
              key={status}
              className="inline-flex items-center gap-1.5 tabular-nums"
              style={{ color: STATUS_FG_VAR[status] }}
            >
              <span aria-hidden="true">{STATUS_ICON[status]}</span>
              <span className="font-semibold">{n}</span>
              <span style={{ color: 'var(--color-text-muted)' }}>{pct(n)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
