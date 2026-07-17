/**
 * ProfileView — the orchestrator. Ties everything together.
 *
 * Compact layout (target: 1080p without scrolling):
 *  ┌────────────────────────────────────────────────────────────┐
 *  │  SectionHeader (with prev/next arrows on the right)         │  ~52px
 *  ├────────────────────────────────────────────────────────────┤
 *  │  FilterBar (4 toggles)                                       │  ~48px
 *  ├──────────────────────────────────┬─────────────────────────┤
 *  │                                  │  BenchTable             │
 *  │  ProfileChart (with floating     │  (sortable, all benches │  ~520px
 *  │  prev/next overlay arrows)       │   visible)              │
 *  │                                  │                         │
 *  ├──────────────────────────────────┴─────────────────────────┤
 *  │  ComplianceSummary card                                    │  ~96px
 *  └────────────────────────────────────────────────────────────┘
 *  ← nav: ← Anterior
 *
 * Total ~720px tall + ~60px wizard nav ≈ 780px. Fits in 1080p
 * with browser chrome.
 *
 * Owns:
 *  - useFilterState  (FilterState + URL/localStorage persistence)
 *  - useCrossLinkState (hovered/selected bench, chart↔table coord)
 *  - useProfileViewModel (API → ProfileViewModel)
 *
 * Handles 4 states: no selection, loading, error, data.
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SectionHeader } from './SectionHeader';
import { FilterBar } from './FilterBar';
import { ProfileChart } from './ProfileChart';
import { SectionNavigator } from './SectionNavigator';
import { BenchTable } from './BenchTable';
import { ComplianceSummary } from './ComplianceSummary';
import { useFilterState, useCrossLinkState, useProfileViewModel } from '../application';
import { useSession } from '../../../../stores/session';
import { Spinner } from '../../../ui/Spinner';

export interface ProfileViewProps {
  readonly blastDataAvailable?: boolean;
  readonly lastRunAt?: string | null;
}

export function ProfileView({ blastDataAvailable = false, lastRunAt }: ProfileViewProps) {
  const { t } = useTranslation();
  const selectedSectionId = useSession((s: ReturnType<typeof useSession.getState>) => s.selectedSection);
  const filter = useFilterState();
  const crossLink = useCrossLinkState();
  const { viewModel, isLoading, error, refetch } = useProfileViewModel(selectedSectionId);

  // Reset cross-link when the section changes
  useEffect(() => {
    crossLink.clear();
  }, [selectedSectionId, crossLink]);

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
      className="flex flex-col gap-2 h-full"
    >
      <SectionHeader
        section={viewModel.section}
        benchCount={viewModel.benches.length}
        lastRunAt={lastRunAt}
      />
      <FilterBar filter={filter} blastDataAvailable={blastDataAvailable} />

      {/* Main row: chart on the left, table on the right.
       *  Chart keeps a 1:1 aspect via scaleanchor; height auto-
       *  fits the available viewport. */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-2 min-h-0">
        <div
          className="relative rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--color-border)' }}
          data-slot="profile-chart-frame"
        >
          <SectionNavigator variant="overlay" showLabels />
          <ProfileChart
            viewModel={viewModel}
            filterState={filter.state}
            crossLink={crossLink}
          />
        </div>
        <div
          className="min-h-0 overflow-hidden rounded-lg"
          style={{ border: '1px solid var(--color-border)' }}
          data-slot="bench-table-frame"
        >
          <BenchTable
            benches={viewModel.benches}
            crossLink={crossLink}
            scrollToBenchNumber={crossLink.selected}
          />
        </div>
      </div>

      <ComplianceSummary benches={viewModel.benches} />
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
      <span className="text-sm">Cargando perfil…</span>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
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
      <h3 className="text-sm font-semibold">No se pudo cargar el perfil</h3>
      <p className="text-xs max-w-md opacity-80">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="text-xs underline underline-offset-2"
      >
        Reintentar
      </button>
    </div>
  );
}
