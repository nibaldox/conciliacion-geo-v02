import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SectionHeader } from './SectionHeader';
import { FilterBar } from './FilterBar';
import { ProfileChart } from './ProfileChart';
import { BenchInspector } from './BenchInspector';
import { ProfilePlanThumbnail } from '../../ProfilePlanThumbnail';
import { BenchTable } from './BenchTable';
import { ComplianceSummary } from './ComplianceSummary';
import { HorizontalDeviationLegend } from '../../HorizontalDeviationLegend';
import { HorizontalDeviationOverview } from '../../HorizontalDeviationOverview';
import { useFilterState, useCrossLinkState, useProfileViewModel } from '../application';
import { useSession } from '../../../../stores/session';
import { Spinner } from '../../../ui/Spinner';
import { horizontalDeviationWarning } from '../../../../utils/horizontalDeviationMessages';

export interface ProfileViewProps {
  readonly blastDataAvailable?: boolean;
  readonly lastRunAt?: string | null;
}

export function ProfileView({ blastDataAvailable = false, lastRunAt }: ProfileViewProps) {
  const { t } = useTranslation();
  const selectedSectionId = useSession((s: ReturnType<typeof useSession.getState>) => s.selectedSection);
  const selectedDesignBenches = useSession((s) => s.filters.bench);
  const filter = useFilterState();
  const crossLink = useCrossLinkState();
  const clearCrossLink = crossLink.clear;
  const { viewModel, isLoading, error, refetch } = useProfileViewModel(selectedSectionId);

  // Reset cross-link when the section changes
  useEffect(() => {
    clearCrossLink();
  }, [selectedSectionId, clearCrossLink]);

  useEffect(() => {
    if (!viewModel || crossLink.selected == null) return;
    const selectedTopoBench = viewModel.benches.find((bench) => bench.benchNumber === crossLink.selected);
    const remainsVisible = selectedDesignBenches.length === 0
      || (selectedTopoBench?.designBenchNumber != null && selectedDesignBenches.includes(selectedTopoBench.designBenchNumber));
    if (!remainsVisible) clearCrossLink();
  }, [viewModel, crossLink.selected, selectedDesignBenches, clearCrossLink]);

  const selectedDesignStatuses = (viewModel?.comparisonBenchStatuses ?? []).filter((bench) =>
    selectedDesignBenches.length === 0 || (bench.designBenchNumber != null && selectedDesignBenches.includes(bench.designBenchNumber)));
  const profileWarnings = viewModel
    ? (['design', 'topo'] as const).flatMap((surface) => (viewModel.profileWarnings?.[surface] ?? [])
      .filter((code) => code === 'no_section_intersection'
        || code === 'insufficient_section_points'
        || code === 'disconnected_profile_components'
        || code === 'ambiguous_profile_geometry'
        || code === 'section_cut_error'
        || code === 'section_processing_error')
      .map((code) => ({ surface, code })))
    : [];
  const recoveredProfileWarnings = viewModel
    ? (['design', 'topo'] as const).flatMap((surface) => (viewModel.profileWarnings?.[surface] ?? [])
      .filter((code) => code === 'minor_profile_reversal_normalized')
      .map((code) => ({ surface, code })))
    : [];

  if (!selectedSectionId) {
    return (
      <EmptyState
        title={t('profileView.empty.title', { defaultValue: 'Selecciona una sección' })}
        body={t('profileView.empty.body', {
          defaultValue: 'Elige una sección transversal del paso anterior para ver su perfil.',
        })}
      />
    );
  }

  if (isLoading && !viewModel) {
    return <LoadingState />;
  }

  if (error) {
    return (
      <ErrorState
        message={error.message}
        onRetry={refetch}
      />
    );
  }

  if (!viewModel) {
    return <LoadingState />;
  }

  return (
    <div
      data-slot="profile-view"
      data-section-id={selectedSectionId}
      className="flex flex-col gap-4"
    >
      <SectionHeader
        section={viewModel.section}
        benchCount={viewModel.benches.length}
        floorElevation={viewModel.floorElevation ?? undefined}
        crestElevationMax={viewModel.crestElevationMax ?? undefined}
        lastRunAt={lastRunAt}
      />
      {recoveredProfileWarnings.length > 0 && (
        <div data-slot="profile-recovery-warning" role="status" className="flex flex-col gap-1 rounded-lg border border-status-warn-border bg-status-warn-bg px-4 py-3 text-sm text-status-warn-text">
          {recoveredProfileWarnings.map(({ surface, code }) => (
            <p key={`${surface}-${code}`}>
              {t(`profileView.warnings.${code}`, { surface: t(`profileView.surfaces.${surface}`) })}
            </p>
          ))}
        </div>
      )}
      {profileWarnings.length > 0 && (
        <div data-slot="profile-unavailable-warning" role="status" className="flex flex-col gap-1 rounded-lg border border-status-warn-border bg-status-warn-bg px-4 py-3 text-sm text-status-warn-text">
          {profileWarnings.map(({ surface, code }) => (
            <p key={`${surface}-${code}`}>
              {t(`profileView.warnings.${code}`, { surface: t(`profileView.surfaces.${surface}`) })}
            </p>
          ))}
        </div>
      )}

      <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px] 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <div
          className="min-w-0 overflow-hidden rounded-xl bg-surface-raised"
          style={{ border: '1px solid var(--color-border)' }}
          data-slot="profile-chart-frame"
        >
          <FilterBar
            filter={filter}
            blastDataAvailable={blastDataAvailable}
            horizontalDeviationAvailable={!!viewModel.horizontalDeviation}
          />
          {viewModel.horizontalDeviation && filter.state.showHorizontalDeviation && (
            <div
              data-slot="profile-horizontal-deviation-summary"
              className="flex flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-start"
              style={{ backgroundColor: 'var(--color-surface)' }}
            >
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <HorizontalDeviationOverview summary={viewModel.horizontalDeviation.summary} compact />
                <p className="text-[10px] leading-snug" style={{ color: 'var(--color-text-muted)' }}>
                  {t('horizontalDeviation.method_caption')} · {t('horizontalDeviation.direction_caption')}
                </p>
                <p className="text-[10px] leading-snug" style={{ color: 'var(--color-text-muted)' }}>
                  {t('horizontalDeviation.sample_hint')}
                </p>
                {viewModel.horizontalDeviation.warnings.slice(0, 3).map((warning, index) => {
                  const message = horizontalDeviationWarning(warning);
                  return (
                    <p key={`${index}-${warning}`} className="text-[10px] leading-snug" style={{ color: 'var(--color-text-muted)' }}>
                      {t(message.key, message.options)}
                    </p>
                  );
                })}
              </div>
              <HorizontalDeviationLegend compact />
            </div>
          )}
          <div className="h-[440px] md:h-[480px]">
            <ProfileChart viewModel={viewModel} filterState={filter.state} crossLink={crossLink} />
          </div>
        </div>
        <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 xl:flex xl:flex-col">
          <ProfilePlanThumbnail sectionId={selectedSectionId} />
          <BenchInspector bench={viewModel.benches.find((bench) => bench.benchNumber === crossLink.selected) ?? null} />
        </div>
      </div>
      <section data-slot="bench-table-frame" className="min-w-0 overflow-hidden rounded-xl border border-border bg-surface-raised">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-4">
          <h3 className="text-lg font-semibold">{t('profileView.table.title')}</h3>
          <p className="text-xs text-text-muted">{t('profileView.table.comparison')}</p>
        </div>
        <BenchTable
          benches={viewModel.benches}
          crossLink={crossLink}
          selectedDesignBenchNumbers={selectedDesignBenches}
          comparisonBenchStatuses={selectedDesignStatuses}
        />
      </section>
      <ComplianceSummary
        benches={viewModel.benches}
        statuses={selectedDesignStatuses.length || selectedDesignBenches.length
          ? selectedDesignStatuses.map((bench) => bench.status)
          : undefined}
        filtered={selectedDesignBenches.length > 0}
      />
    </div>
  );
}

// ─── Internal states ────────────────────────────────────────

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div
      data-slot="profile-view-empty"
      className="flex flex-col items-center justify-center text-center px-6 py-16 rounded-xl gap-2"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px dashed var(--color-border)',
        color: 'var(--color-text-muted)',
      }}
    >
      <div className="text-3xl" aria-hidden="true">📈</div>
      <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{title}</h3>
      <p className="text-xs max-w-md">{body}</p>
    </div>
  );
}

function LoadingState() {
  const { t } = useTranslation();
  return (
    <div
      data-slot="profile-view-loading"
      className="flex items-center justify-center px-6 py-16 rounded-xl gap-3"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        color: 'var(--color-text-muted)',
      }}
    >
      <Spinner />
      <span className="text-sm">{t('profileView.loading')}</span>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      data-slot="profile-view-error"
      className="flex flex-col items-center justify-center text-center px-6 py-12 rounded-xl gap-3"
      role="alert"
      style={{
        backgroundColor: 'var(--status-nok-bg)',
        border: '1px solid var(--status-nok-border)',
        color: 'var(--status-nok-text)',
      }}
    >
      <span className="text-2xl" aria-hidden="true">❌</span>
      <h3 className="text-sm font-semibold">{t('profileView.error')}</h3>
      <p className="text-xs max-w-md opacity-80">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="text-xs underline underline-offset-2"
      >
        {t('common.retry')}
      </button>
    </div>
  );
}
