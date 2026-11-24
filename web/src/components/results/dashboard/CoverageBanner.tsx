import { useTranslation } from 'react-i18next';
import { formatLocaleNumber } from '../../../utils/format';
import type { DashboardCoverage } from './coverageSelectors';

export interface CoverageBannerProps {
  readonly coverage: DashboardCoverage;
  readonly defaultBermMin: number;
}

interface FunnelSegment {
  readonly key: string;
  readonly count: number;
  readonly colorVar: string;
}

interface BreakdownItem {
  readonly key: string;
  readonly label: string;
  readonly count: number;
  readonly dotColor: string;
}

export function CoverageBanner({ coverage, defaultBermMin }: CoverageBannerProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;

  const missingCount = coverage.missingSections.length;
  const hasDesignStates =
    coverage.truncatedStateBenches + coverage.notExcavatedStateBenches + coverage.unmeasuredStateBenches > 0;
  const completeCount = Math.max(0, coverage.evaluableCompleteBenches);
  const truncatedCount = hasDesignStates
    ? coverage.truncatedStateBenches
    : coverage.truncatedBermDesignCount;
  const notExcavatedCount = hasDesignStates
    ? coverage.notExcavatedStateBenches
    : coverage.notBuiltBenches;
  const unmeasuredCount = hasDesignStates ? coverage.unmeasuredStateBenches : 0;

  const segments: readonly FunnelSegment[] = [
    { key: 'complete', count: completeCount, colorVar: 'var(--status-ok-text)' },
    { key: 'truncated', count: truncatedCount, colorVar: 'var(--status-warn-text)' },
    { key: 'not_excavated', count: notExcavatedCount, colorVar: 'var(--status-missing-text)' },
    { key: 'unmeasured', count: unmeasuredCount, colorVar: 'var(--status-nok-text)' },
  ];
  const segmentTotal = segments.reduce((sum, segment) => sum + segment.count, 0);

  const breakdownItems: readonly BreakdownItem[] = [
    {
      key: 'truncated',
      label: t('dashboard.coverage.truncated_count'),
      count: truncatedCount,
      dotColor: 'var(--status-warn-text)',
    },
    {
      key: 'not_excavated',
      label: t('dashboard.coverage.not_excavated_count'),
      count: notExcavatedCount,
      dotColor: 'var(--status-missing-text)',
    },
    {
      key: 'unmeasured',
      label: t('dashboard.coverage.unmeasured_count'),
      count: unmeasuredCount,
      dotColor: 'var(--status-nok-text)',
    },
    {
      key: 'extra',
      label: t('dashboard.coverage.extra_count'),
      count: coverage.extraBenches,
      dotColor: 'var(--color-accent-bright)',
    },
  ].filter((item) => item.count > 0);

  return (
    <section
      data-slot="dashboard-coverage"
      className="space-y-3 border-b border-border pb-4 text-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="ui-section-title">{t('dashboard.coverage.title')}</h3>
          <span className="tabular-nums font-medium text-text-secondary">
            {t('dashboard.coverage.sections_of', {
              evaluated: formatLocaleNumber(coverage.evaluatedSections, language, 0),
              total: formatLocaleNumber(coverage.totalSectionsDefined, language, 0),
            })}
          </span>
        </div>

        {missingCount > 0 ? (
          <span className="ui-chip" data-tone="warn">
            {t('dashboard.coverage.sections_missing', { count: missingCount })}
          </span>
        ) : (
          <span className="ui-chip" data-tone="ok">
            {t('dashboard.coverage.all_sections_ok')}
          </span>
        )}
      </div>

      {missingCount > 0 ? (
        <details data-slot="missing-sections-details" className="text-xs text-text-secondary">
          <summary className="cursor-pointer select-none font-medium text-text-muted hover:text-text-primary">
            {t('dashboard.coverage.sections_missing_list_toggle')}
          </summary>
          <p className="mt-1.5 rounded border border-border bg-surface-muted px-2.5 py-1.5 font-mono text-text-primary">
            {coverage.missingSections.join(', ')}
          </p>
        </details>
      ) : null}

      <div className="space-y-1.5">
        <p className="tabular-nums text-text-secondary">
          {t('dashboard.coverage.benches_funnel', {
            design: formatLocaleNumber(coverage.designBenches, language, 0),
            compared: formatLocaleNumber(coverage.comparedBenches, language, 0),
            evaluable: formatLocaleNumber(coverage.evaluableCompleteBenches, language, 0),
          })}
        </p>

        {segmentTotal > 0 ? (
          <div
            data-slot="coverage-funnel-bar"
            className="flex h-2 w-full overflow-hidden rounded-full bg-surface-muted"
            aria-hidden="true"
          >
            {segments.map((segment) =>
              segment.count > 0 ? (
                <span
                  key={segment.key}
                  data-segment={segment.key}
                  style={{
                    width: `${(segment.count / segmentTotal) * 100}%`,
                    backgroundColor: segment.colorVar,
                  }}
                />
              ) : null,
            )}
          </div>
        ) : null}

        {breakdownItems.length > 0 ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5 text-text-secondary">
            {breakdownItems.map((item) => (
              <span key={item.key} className="inline-flex items-center gap-1.5 tabular-nums">
                <span
                  aria-hidden="true"
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: item.dotColor }}
                />
                <span className="text-text-muted">{item.label}:</span>
                <strong className="font-medium text-text-primary">
                  {formatLocaleNumber(item.count, language, 0)}
                </strong>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {coverage.truncatedBermDesignCount > 0 ? (
        <div
          role="status"
          data-slot="truncated-berm-warning"
          className="rounded-md border border-[var(--status-warn-border)] bg-[var(--status-warn-bg)] px-3 py-2 text-xs text-text-primary"
        >
          {t('dashboard.coverage.truncated_berm_warning', {
            count: formatLocaleNumber(coverage.truncatedBermDesignCount, language, 0),
            pct: formatLocaleNumber(coverage.truncatedBermDesignPct, language, 1),
            min: formatLocaleNumber(defaultBermMin, language, 1),
          })}
        </div>
      ) : null}
    </section>
  );
}
