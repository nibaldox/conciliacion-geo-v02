import { useTranslation } from 'react-i18next';
import type { HorizontalDeviationSummary } from '../../api/types';

export interface HorizontalDeviationOverviewProps {
  readonly summary: HorizontalDeviationSummary;
  readonly compact?: boolean;
}

export function HorizontalDeviationOverview({ summary, compact = false }: HorizontalDeviationOverviewProps) {
  const { t } = useTranslation();
  const valueClass = compact ? 'text-xs' : 'text-sm';

  return (
    <div data-slot="horizontal-deviation-overview" className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
      <Metric label={t('horizontalDeviation.summary.measured')} value={`${summary.measured} / ${summary.total}`} valueClass={valueClass} />
      <Metric
        label={t('horizontalDeviation.summary.within')}
        value={summary.within_percent == null ? '—' : `${summary.within_percent.toFixed(1)}%`}
        valueClass={valueClass}
      />
      <Metric
        label={t('horizontalDeviation.summary.max_abs')}
        value={summary.max_abs_deviation == null ? '—' : `${summary.max_abs_deviation.toFixed(2)} m`}
        valueClass={valueClass}
      />
    </div>
  );
}

function Metric({ label, value, valueClass }: { label: string; value: string; valueClass: string }) {
  return (
    <div className="flex min-w-0 flex-col">
      <span className="text-[9px] uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>{label}</span>
      <span className={`${valueClass} font-mono font-semibold tabular-nums`} style={{ color: 'var(--color-text-primary)' }}>{value}</span>
    </div>
  );
}
