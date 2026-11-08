import { useTranslation } from 'react-i18next';
import { useMemo } from 'react';
import { useProposedCompliance } from '../../api/proposedCompliance';
import { EMPTY_RESULT_FILTERS, type ResultFilterState } from './resultFilters.utils';
import { formatFloorStatusCounts, toProposalSessionNotice } from './ProfileView/domain';

function fmt(value: number | null | undefined, locale: string): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toLocaleString(locale, { maximumFractionDigits: 1 });
}

function scoreColorVar(score: number | null): string | undefined {
  if (score == null) return undefined;
  if (score >= 70) return 'var(--status-ok-text)';
  if (score >= 50) return 'var(--status-warn-text)';
  return 'var(--status-nok-text)';
}

export function ProposalSummaryCard({
  filters,
  sections,
}: {
  filters?: ResultFilterState;
  sections?: readonly string[];
}) {
  const { t, i18n } = useTranslation();
  const activeFilters = filters ?? EMPTY_RESULT_FILTERS;
  const { data, isPending, isFetching, isError, error, isDemo, refetch } =
    useProposedCompliance(activeFilters);
  const locale = i18n.resolvedLanguage?.toLowerCase().startsWith('en') ? 'en-US' : 'es-AR';

  const notice = useMemo(
    () => toProposalSessionNotice(data, sections ?? []),
    [data, sections],
  );
  const summary = data?.summary ?? null;
  const floorTol = data?.floor_tolerance.max ?? 0.5;
  const floorCounts = formatFloorStatusCounts(summary?.floor_status_counts ?? {});

  if (isDemo) {
    return (
      <section role="status" className="text-sm text-text-muted">
        {t('proposal.demoUnavailable')}
      </section>
    );
  }

  return (
    <section
      data-slot="proposal-summary"
      aria-labelledby="proposal-summary-title"
      aria-busy={isPending || (isFetching && !data) || undefined}
      className="min-w-0 space-y-4 text-sm"
    >
      <h3 id="proposal-summary-title" className="ui-section-title m-0">
        🧪 {t('proposal.cardTitle')}
      </h3>

      {isPending ? <p role="status" className="m-0 text-text-muted">{t('proposal.loading')}</p> : null}

      {!isPending && isError ? (
        <div role="alert" className="space-y-2">
          <p className="m-0" style={{ color: 'var(--status-nok-text)' }}>
            {t('proposal.loadError')}
            {error instanceof Error && error.message ? `: ${error.message}` : ''}
          </p>
          <button
            type="button"
            onClick={refetch}
            className="rounded-md border border-border px-2.5 py-1 text-xs text-text-primary hover:bg-surface-muted"
          >
            {t('proposal.retry', { defaultValue: t('common.retry') })}
          </button>
        </div>
      ) : null}

      {!isPending && !isError && notice.kind === 'not_computed' ? (
        <p role="status" className="m-0 rounded-md border border-border px-3 py-2 text-text-secondary">
          {t('proposal.notComputedNotice')}
        </p>
      ) : null}

      {!isPending && !isError && notice.kind === 'partial' ? (
        <p
          role="status"
          className="m-0 rounded-md border border-border px-3 py-2 text-xs"
          style={{ color: 'var(--status-warn-text)' }}
        >
          {t('proposal.partialNotice', { count: notice.missingSections.length })}
          {notice.failedRows > 0
            ? ` · ${t('proposal.failedRows', { count: notice.failedRows })}`
            : ''}
        </p>
      ) : null}

      {!isPending && !isError && summary ? (
        <>
          <dl className="m-0 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="min-w-0 border-l border-border pl-3">
              <dt className="truncate text-xs font-normal text-text-muted">{t('proposal.globalScore')}</dt>
              <dd
                className="m-0 text-xl font-semibold tabular-nums"
                style={{ color: scoreColorVar(summary.proposed_global_score) }}
              >
                {summary.proposed_global_score == null
                  ? t('proposal.noData')
                  : fmt(summary.proposed_global_score, locale)}
              </dd>
              <dd className="m-0 text-xs text-text-muted">{t('proposal.scoreScale')}</dd>
            </div>
            <div className="min-w-0 border-l border-border pl-3">
              <dt className="truncate text-xs font-normal text-text-muted">{t('proposal.coverage')}</dt>
              <dd className="m-0 text-xl font-semibold tabular-nums text-text-primary">
                {summary.coverage.n_evaluable} / {summary.coverage.n_design_benches}
              </dd>
              <dd className="m-0 text-xs text-text-muted">
                {t('proposal.coverageValue', {
                  evaluable: summary.coverage.n_evaluable,
                  design: summary.coverage.n_design_benches,
                })}
              </dd>
            </div>
            <div className="min-w-0 border-l border-border pl-3">
              <dt className="truncate text-xs font-normal text-text-muted">{t('proposal.splitBenches')}</dt>
              <dd className="m-0 text-xl font-semibold tabular-nums text-text-primary">
                {summary.n_split_benches}
              </dd>
            </div>
            <div className="min-w-0 border-l border-border pl-3">
              <dt className="truncate text-xs font-normal text-text-muted">{t('proposal.debt')}</dt>
              <dd className="m-0 text-xl font-semibold tabular-nums" style={{ color: 'var(--status-warn-text)' }}>
                {fmt(summary.excavation_debt_area_m2, locale)} m²
              </dd>
            </div>
          </dl>
          <p className="m-0 text-xs text-text-secondary">
            {t('proposal.floorTitle', { tol: fmt(floorTol, locale) })}:{' '}
            {floorCounts.length > 0
              ? floorCounts
                  .map((entry) =>
                    `${entry.status === '-' ? t('proposal.floorUnmeasured') : entry.status} ${entry.count}`)
                  .join(' · ')
              : t('proposal.noData')}
          </p>
        </>
      ) : null}

      {!isPending && !isError && data && notice.kind === 'current' && !summary ? (
        <p role="status" className="m-0 text-text-secondary">{t('proposal.noData')}</p>
      ) : null}

      <p className="m-0 text-xs text-text-muted">
        {t('proposal.officialUnchanged')} · ±{fmt(floorTol, locale)} m ·{' '}
        {data?.floor_tolerance_source === 'session'
          ? t('proposal.tolSourceSession')
          : t('proposal.tolSourceCoreDefault')}
      </p>
    </section>
  );
}
