/**
 * ProfileView — the orchestrator. Ties everything together.
 *
 * Owns:
 *  - useFilterState  (FilterState + URL/localStorage persistence)
 *  - useCrossLinkState (hovered/selected bench, chart↔table coord)
 *  - useProfileViewModel (API → ProfileViewModel)
 *
 * Renders, in order:
 *  - SectionHeader (section metadata)
 *  - FilterBar (4 toggles + optional blast)
 *  - ProfileChart (Plotly, cross-link enabled)
 *  - BenchTable (sortable, cross-link enabled, scrolls to selected row)
 *  - ComplianceSummary (counts + stacked bar)
 *
 * Loading state: subtle skeleton, no spinner (we use spinner atoms
 * elsewhere — this is full-width so we keep it calm).
 *
 * No-data state: when no section is selected, show a centered
 * placeholder pointing to the section selector.
 *
 * Error state: inline ErrorBanner-like block with the message.
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SectionHeader } from './SectionHeader';
import { FilterBar } from './FilterBar';
import { ProfileChart } from './ProfileChart';
import { BenchTable } from './BenchTable';
import { ComplianceSummary } from './ComplianceSummary';
import { useFilterState, useCrossLinkState, useProfileViewModel } from '../application';
import { useSession } from '../../../../stores/session';
import { Spinner } from '../../../ui/Spinner';

export interface ProfileViewProps {
  /** Optional: a flag the parent can pass to tell us blast data is
   *  available. When false, the FilterBar hides the blast holes
   *  toggle. Defaults to false. */
  readonly blastDataAvailable?: boolean;
  /** Optional: timestamp of the last run, for the SectionHeader. */
  readonly lastRunAt?: string | null;
}

export function ProfileView({ blastDataAvailable = false, lastRunAt }: ProfileViewProps) {
  const { t } = useTranslation();
  const selectedSectionId = useSession((s: ReturnType<typeof useSession.getState>) => s.selectedSection);
  const filter = useFilterState();
  const crossLink = useCrossLinkState();
  const { viewModel, isLoading, error } = useProfileViewModel(selectedSectionId);

  // Reset cross-link when the section changes — the previous
  // bench is from a different section now, highlighting it
  // would be misleading.
  useEffect(() => {
    crossLink.clear();
  }, [selectedSectionId, crossLink]);

  // ── No selection state ────────────────────────────────────
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

  // ── Loading state ─────────────────────────────────────────
  if (isLoading && !viewModel) {
    return <LoadingState />;
  }

  // ── Error state ───────────────────────────────────────────
  if (error) {
    return (
      <ErrorState
        message={error.message}
        onRetry={() => window.location.reload()}
      />
    );
  }

  // ── No data yet (selected but not loaded) ─────────────────
  if (!viewModel) {
    return <LoadingState />;
  }

  return (
    <div
      data-slot="profile-view"
      data-section-id={selectedSectionId}
      className="flex flex-col gap-3"
    >
      <SectionHeader
        section={viewModel.section}
        benchCount={viewModel.benches.length}
        lastRunAt={lastRunAt}
      />
      <FilterBar
        blastDataAvailable={blastDataAvailable}
      />
      <ProfileChart
        viewModel={viewModel}
        filterState={filter.state}
        crossLink={crossLink}
      />
      <BenchTable
        benches={viewModel.benches}
        crossLink={crossLink}
        scrollToBenchNumber={crossLink.selected}
      />
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
