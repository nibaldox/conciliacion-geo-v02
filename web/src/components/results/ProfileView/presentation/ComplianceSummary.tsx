/**
 * ComplianceSummary — tolerance-tier counts and a horizontal stacked
 * bar showing evaluated and unevaluated design banks.
 *
 * "X of Y within tolerance" headline, then a 3-segment bar in
 * semantic colors, then a small legend.
 *
 * When a design-bank filter is active, both the counts and table use
 * that same design-bank identity.
 */

import { useTranslation } from 'react-i18next';
import type { Bench, BenchStatus } from '../domain/types';
import { useComplianceStats } from '../application';
import { STATUS_FG_VAR, STATUS_PRESENTATION_ORDER, STATUS_ICON } from '../domain/status';

export interface ComplianceSummaryProps {
  readonly benches: readonly Bench[];
  readonly statuses?: readonly BenchStatus[];
  readonly filtered?: boolean;
}

export function ComplianceSummary({ benches, statuses, filtered = false }: ComplianceSummaryProps) {
  const { t } = useTranslation();
  const stats = useComplianceStats(benches, statuses);

  const pct = (n: number): string => (stats.total === 0 ? '—' : `${Math.round((n / stats.total) * 100)}%`);

  return (
    <section
      data-slot="compliance-summary"
      className="rounded-lg p-3 flex flex-col gap-2.5"
      style={{
        backgroundColor: 'var(--color-surface-raised)',
        border: '1px solid var(--color-border)',
      }}
      aria-label={t(filtered ? 'profileView.summary.filtered_title' : 'profileView.summary.aria', { defaultValue: filtered ? 'Cumplimiento de bancos seleccionados' : 'Cumplimiento de sección' })}
    >
      {/* Headline */}
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center justify-center w-6 h-6 rounded"
            style={{
              backgroundColor: 'var(--color-accent-bg)',
              color: 'var(--color-accent-bright)',
              fontSize: '12px',
            }}
            aria-hidden="true"
          >
            ✓
          </span>
          <h3
            className="text-sm font-semibold"
            style={{
              color: 'var(--color-text-muted)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {t(filtered ? 'profileView.summary.filtered_title' : 'profileView.summary.title', { defaultValue: filtered ? 'Cumplimiento de bancos seleccionados' : 'Cumplimiento de sección' })}
          </h3>
        </div>
        <span
          className="text-sm tabular-nums"
          style={{
            color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {stats.total === 0
            ? t('profileView.summary.no_benches', { defaultValue: 'Sin bancos' })
            : stats.evaluated === 0
              ? t('profileView.summary.no_evaluated', { defaultValue: '{{count}} bancos sin datos evaluables', count: stats.unknown })
            : t('profileView.summary.headline', {
                defaultValue: '{{within}} de {{total}} bancos evaluados dentro de tolerancia',
                within: stats.withinTolerance,
                total: stats.evaluated,
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
                backgroundColor: STATUS_FG_VAR[status],
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
              <span>{t('profileView.status.' + status)}</span><span className="font-semibold">{n}</span>
              <span style={{ color: 'var(--color-text-muted)' }}>{pct(n)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
