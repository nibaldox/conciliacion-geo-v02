import { useEffect, useState, type ReactNode } from 'react';
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

const UNAVAILABLE_PROFILE_CODES = new Set([
  'no_section_intersection',
  'insufficient_section_points',
  'disconnected_profile_components',
  'ambiguous_profile_geometry',
  'section_cut_error',
  'section_processing_error',
]);

const CARD_CLASS = 'min-w-0 overflow-hidden rounded-lg border border-border bg-surface-raised';

export function ProfileView({ blastDataAvailable = false, lastRunAt }: ProfileViewProps) {
  const { t } = useTranslation();
  const [isPlanOpen, setIsPlanOpen] = useState(true);
  const selectedSectionId = useSession((s: ReturnType<typeof useSession.getState>) => s.selectedSection);
  const selectedDesignBenches = useSession((s) => s.filters.bench);
  const setSessionFilters = useSession((s) => s.setFilters);
  const filter = useFilterState();
  const crossLink = useCrossLinkState();
  const clearCrossLink = crossLink.clear;
  const { viewModel, isLoading, error, refetch } = useProfileViewModel(selectedSectionId);

  useEffect(() => {
    clearCrossLink();
  }, [selectedSectionId, clearCrossLink]);

  const selectedDesignStatuses = (viewModel?.comparisonBenchStatuses ?? []).filter((bench) =>
    selectedDesignBenches.length === 0 || (bench.designBenchNumber != null && selectedDesignBenches.includes(bench.designBenchNumber)));
  const profileWarnings = viewModel
    ? (['design', 'topo'] as const).flatMap((surface) => (viewModel.profileWarnings?.[surface] ?? [])
      .filter((code) => UNAVAILABLE_PROFILE_CODES.has(code))
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
    return <ErrorState message={error.message} onRetry={refetch} />;
  }

  if (!viewModel) {
    return <LoadingState />;
  }

  const selectedBench = viewModel.benches.find((bench) => bench.benchNumber === crossLink.selected) ?? null;
  const planToggleLabel = t('profile_plan.title');

  return (
    <div data-slot="profile-view" data-section-id={selectedSectionId} className="flex flex-col gap-4">
      <SectionHeader
        section={viewModel.section}
        benchCount={viewModel.benches.length}
        floorElevation={viewModel.floorElevation ?? undefined}
        crestElevationMax={viewModel.crestElevationMax ?? undefined}
        lastRunAt={lastRunAt}
      />

      {selectedDesignBenches.length > 0 && (
        <Notice slot="profile-bank-filter-note" role="note" tone="info">
          <span className="min-w-0 flex-1">
            {t('profileView.filter.design_bank_scope_active', {
              banks: selectedDesignBenches.map((number) => `D${number}`).join(', '),
              defaultValue: 'Filtro de bancos de diseño activo: {{banks}}. La tabla y el resumen de cumplimiento usan esos bancos; el gráfico y la inspección conservan todos los bancos topográficos.',
            })}
          </span>
          <button
            type="button"
            onClick={() => setSessionFilters({ bench: [] })}
            className="shrink-0 rounded text-accent-bright underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {t('profileView.filter.clear_design_bench', { defaultValue: 'Quitar filtro de bancos' })}
          </button>
        </Notice>
      )}
      {recoveredProfileWarnings.length > 0 && (
        <Notice slot="profile-recovery-warning" role="status" tone="warn">
          <div className="flex min-w-0 flex-col gap-0.5">
            {recoveredProfileWarnings.map(({ surface, code }) => (
              <p key={`${surface}-${code}`}>
                {t(`profileView.warnings.${code}`, { surface: t(`profileView.surfaces.${surface}`) })}
              </p>
            ))}
          </div>
        </Notice>
      )}
      {profileWarnings.length > 0 && (
        <Notice slot="profile-unavailable-warning" role="status" tone="warn">
          <div className="flex min-w-0 flex-col gap-0.5">
            {profileWarnings.map(({ surface, code }) => (
              <p key={`${surface}-${code}`}>
                {t(`profileView.warnings.${code}`, { surface: t(`profileView.surfaces.${surface}`) })}
              </p>
            ))}
          </div>
        </Notice>
      )}

      <div data-slot="profile-chart-frame" className={`flex flex-col ${CARD_CLASS}`}>
        <FilterBar
          filter={filter}
          blastDataAvailable={blastDataAvailable}
          horizontalDeviationAvailable={!!viewModel.horizontalDeviation}
        />
        {viewModel.horizontalDeviation && filter.state.showHorizontalDeviation && (
          <div
            data-slot="profile-horizontal-deviation-summary"
            className="flex flex-col gap-2 border-b border-border px-4 py-2.5 sm:flex-row sm:items-start"
          >
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <HorizontalDeviationOverview summary={viewModel.horizontalDeviation.summary} compact />
              <p className="text-xs leading-relaxed text-text-secondary">
                {t('horizontalDeviation.method_caption')} · {t('horizontalDeviation.direction_caption')}
              </p>
              <p className="text-xs leading-relaxed text-text-secondary">
                {t('horizontalDeviation.sample_hint')}
              </p>
              {viewModel.horizontalDeviation.warnings.slice(0, 3).map((warning, index) => {
                const message = horizontalDeviationWarning(warning);
                return (
                  <p key={`${index}-${warning}`} className="text-xs leading-relaxed text-text-secondary">
                    {t(message.key, message.options)}
                  </p>
                );
              })}
            </div>
            <HorizontalDeviationLegend compact />
          </div>
        )}
        <div data-slot="profile-chart-canvas" className="h-[440px] shrink-0 md:h-[480px]">
          <ProfileChart viewModel={viewModel} filterState={filter.state} crossLink={crossLink} />
        </div>
        <BenchInspector bench={selectedBench} />
      </div>

      <div className={`grid min-w-0 grid-cols-1 items-start gap-4 ${isPlanOpen ? 'xl:grid-cols-[minmax(0,1fr)_400px]' : ''}`}>
        <section data-slot="bench-table-frame" className={CARD_CLASS}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-4 py-2.5">
            <h3 className="text-sm font-medium text-text-primary">{t('profileView.table.title')}</h3>
            <p className="min-w-0 flex-1 truncate text-xs text-text-muted">{t('profileView.table.comparison')}</p>
            <button
              type="button"
              aria-expanded={isPlanOpen}
              aria-controls="profile-plan-content"
              onClick={() => setIsPlanOpen((open) => !open)}
              data-slot="profile-plan-toggle"
              className={[
                'inline-flex h-7 shrink-0 items-center rounded-md border px-2.5 text-xs transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                isPlanOpen
                  ? 'border-accent bg-accent-bg text-text-primary'
                  : 'border-border text-text-secondary hover:bg-surface-muted hover:text-text-primary',
              ].join(' ')}
            >
              {planToggleLabel}
            </button>
          </div>
          <BenchTable
            benches={viewModel.benches}
            crossLink={crossLink}
            selectedDesignBenchNumbers={selectedDesignBenches}
            comparisonBenchStatuses={selectedDesignStatuses}
          />
          <ComplianceSummary
            benches={viewModel.benches}
            statuses={selectedDesignStatuses.length || selectedDesignBenches.length
              ? selectedDesignStatuses.map((bench) => bench.status)
              : undefined}
            filtered={selectedDesignBenches.length > 0}
          />
        </section>
        <aside
          data-slot="profile-plan-panel"
          aria-label={planToggleLabel}
          hidden={!isPlanOpen}
          className={`w-full max-w-[400px] p-3 ${CARD_CLASS}`}
        >
          <div id="profile-plan-content" hidden={!isPlanOpen}>
            {isPlanOpen && <ProfilePlanThumbnail sectionId={selectedSectionId} showTitle={false} />}
          </div>
        </aside>
      </div>
    </div>
  );
}

function Notice({ slot, role, tone, children }: { slot: string; role: 'note' | 'status'; tone: 'info' | 'warn'; children: ReactNode }) {
  return (
    <div
      data-slot={slot}
      role={role}
      className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-md border border-border px-3 py-2 text-xs leading-relaxed text-text-secondary"
    >
      <span
        aria-hidden="true"
        className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: tone === 'warn' ? 'var(--status-warn-text)' : 'var(--color-accent-bright)' }}
      />
      {children}
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div
      data-slot="profile-view-empty"
      className="flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border px-6 py-16 text-center"
    >
      <h3 className="text-sm font-medium text-text-primary">{title}</h3>
      <p className="max-w-md text-xs text-text-muted">{body}</p>
    </div>
  );
}

function LoadingState() {
  const { t } = useTranslation();
  return (
    <div
      data-slot="profile-view-loading"
      className="flex items-center justify-center gap-3 rounded-lg border border-border px-6 py-16 text-text-muted"
    >
      <Spinner size="sm" />
      <span className="text-sm">{t('profileView.loading')}</span>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      data-slot="profile-view-error"
      role="alert"
      className="flex flex-col items-center justify-center gap-1.5 rounded-lg border border-border px-6 py-12 text-center"
    >
      <h3 className="inline-flex items-center gap-2 text-sm font-medium text-text-primary">
        <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--status-nok-text)' }} />
        {t('profileView.error')}
      </h3>
      <p className="max-w-md text-xs text-text-muted">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-1 rounded text-xs text-accent-bright underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {t('common.retry')}
      </button>
    </div>
  );
}
