import { useTranslation } from 'react-i18next';
import type { Bench, BenchStatus } from '../domain/types';
import { useComplianceStats } from '../application';
import { STATUS_FG_VAR, STATUS_PRESENTATION_ORDER } from '../domain/status';

export interface ComplianceSummaryProps {
  readonly benches: readonly Bench[];
  readonly statuses?: readonly BenchStatus[];
  readonly filtered?: boolean;
}

export function ComplianceSummary({ benches, statuses, filtered = false }: ComplianceSummaryProps) {
  const { t } = useTranslation();
  const stats = useComplianceStats(benches, statuses);
  const title = t(filtered ? 'profileView.summary.filtered_title' : 'profileView.summary.title', {
    defaultValue: filtered ? 'Cumplimiento de bancos seleccionados' : 'Cumplimiento de sección',
  });

  const pct = (n: number): string => (stats.total === 0 ? '—' : `${Math.round((n / stats.total) * 100)}%`);

  return (
    <section
      data-slot="compliance-summary"
      className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-2 border-t border-border px-4 py-2.5"
      aria-label={filtered ? title : t('profileView.summary.aria', { defaultValue: 'Cumplimiento de sección' })}
    >
      <header className="flex min-w-0 items-baseline gap-2">
        <h3 className="text-sm font-medium text-text-primary">{title}</h3>
        <span className="truncate text-xs tabular-nums text-text-muted">
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

      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
        {STATUS_PRESENTATION_ORDER.map((status) => {
          const n = stats.counts[status];
          return (
            <li key={status} data-summary-status={status} className="inline-flex items-center gap-1.5 tabular-nums">
              <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: STATUS_FG_VAR[status] }} />
              <span>{t('profileView.status.' + status)}</span>
              <span className="font-medium text-text-primary">{n}</span>
              <span>{pct(n)}</span>
            </li>
          );
        })}
      </ul>

      <div
        className="ml-auto flex h-1.5 w-32 overflow-hidden rounded-full bg-surface-muted"
        role="img"
        aria-label={t('profileView.summary.bar_aria', { defaultValue: 'Distribución de cumplimiento' })}
      >
        {STATUS_PRESENTATION_ORDER.map((status) => {
          const n = stats.counts[status];
          if (n === 0) return null;
          return (
            <div
              key={status}
              data-status={status}
              style={{ width: `${(n / stats.total) * 100}%`, backgroundColor: STATUS_FG_VAR[status] }}
              title={`${status}: ${n} (${pct(n)})`}
            />
          );
        })}
      </div>
    </section>
  );
}
