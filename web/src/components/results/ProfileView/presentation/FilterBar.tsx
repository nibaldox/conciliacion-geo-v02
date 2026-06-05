/**
 * FilterBar — the row of overlay toggles above the profile chart.
 *
 * Reads/writes the FilterState via useFilterState. Toggles for the
 * four render overlays (Reconciled, Areas, Spill, Semaphore) plus
 * the optional Blast Holes toggle (only shown when blast data is
 * available — gated on a prop the parent supplies).
 *
 * The "Reconciled" toggle is a single UI control that flips BOTH
 * the design and topo reconciled lines (in the domain, those are
 * two fields so future enhancements can split them without
 * touching the FilterBar).
 *
 * Visual: a single horizontal row of switches, separated by a
 * subtle 1px bottom border. Active count is shown as a small badge
 * on the right; the Reset link is shown only when isFilterActive.
 */

import { useTranslation } from 'react-i18next';
import { FilterToggle } from './atoms/FilterToggle';
import { MetricValue } from './atoms/MetricValue';
import { useFilterState } from '../application';
import { isFilterActive } from '../domain/filters';

export interface FilterBarProps {
  /** True when blast-hole data is available for the current session.
   *  When false, the Blast Holes toggle is hidden. The session
   *  exposes this via a flag we read from useSession (or the parent
   *  can pass it in if it has a more direct source). */
  readonly blastDataAvailable?: boolean;
  /** Optional: live count of "active" overlays, computed by the
   *  parent if it has cheaper access than the FilterState. */
  readonly activeCount?: number;
}

export function FilterBar({ blastDataAvailable = false, activeCount }: FilterBarProps) {
  const { t } = useTranslation();
  const { state, setField, reset } = useFilterState();

  // The "Reconciled" toggle controls BOTH reconciled lines.
  const reconciledOn = state.showReconciledDesign && state.showReconciledTopo;
  const setReconciled = (next: boolean) => {
    setField('showReconciledDesign', next);
    setField('showReconciledTopo', next);
  };

  const hasActive = isFilterActive(state);
  const displayCount = activeCount ?? (hasActive ? 1 : 0);

  return (
    <div
      data-slot="filter-bar"
      className="flex flex-wrap items-center gap-2 px-3 md:px-6 py-2 border-b"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      <span
        className="text-[10px] uppercase tracking-wider font-semibold mr-1"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t('profileView.filter.label', { defaultValue: 'Mostrar' })}
      </span>

      <FilterToggle
        checked={reconciledOn}
        onChange={setReconciled}
        label={t('profileView.filter.reconciled', { defaultValue: 'Reconciliado' })}
        title={t('profileView.filter.reconciled_help', {
          defaultValue: 'Geometría idealizada detectada',
        })}
      />
      <FilterToggle
        checked={state.showAreas}
        onChange={(v) => setField('showAreas', v)}
        label={t('profileView.filter.areas', { defaultValue: 'Áreas' })}
        title={t('profileView.filter.areas_help', {
          defaultValue: 'Sobre-excavación y deuda de material',
        })}
      />
      <FilterToggle
        checked={state.showSpillAreas}
        onChange={(v) => setField('showSpillAreas', v)}
        label={t('profileView.filter.spill', { defaultValue: 'Derrame' })}
        title={t('profileView.filter.spill_help', {
          defaultValue: 'Material derramado en la base de los bancos',
        })}
      />
      <FilterToggle
        checked={state.showSemaphore}
        onChange={(v) => setField('showSemaphore', v)}
        label={t('profileView.filter.semaphore', { defaultValue: 'Semáforo' })}
        title={t('profileView.filter.semaphore_help', {
          defaultValue: 'Verde=Cumple, Amarillo=Alerta, Rojo=No cumple',
        })}
      />

      {blastDataAvailable && (
        <>
          <span
            className="inline-block w-px h-4 mx-1"
            style={{ backgroundColor: 'var(--color-border)' }}
            aria-hidden="true"
          />
          <FilterToggle
            checked={state.showBlastHoles}
            onChange={(v) => setField('showBlastHoles', v)}
            label={t('profileView.filter.blast', { defaultValue: 'Pozos' })}
            title={t('profileView.filter.blast_help', {
              defaultValue: 'Proyección de pozos de tronadura',
            })}
          />
          {state.showBlastHoles && (
            <ToleranceInput
              value={state.blastTolerance}
              onChange={(v) => setField('blastTolerance', v)}
            />
          )}
        </>
      )}

      <div className="flex-1" />

      {hasActive && (
        <button
          type="button"
          onClick={reset}
          className="text-[11px] font-medium px-2 py-1 rounded underline-offset-2 hover:underline"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('profileView.filter.reset', { defaultValue: 'Reset' })}
        </button>
      )}

      <MetricValue
        label={t('profileView.filter.active', { defaultValue: 'Activos' })}
        value={displayCount}
        size="sm"
        muted
      />
    </div>
  );
}

// ─── Internal: blast tolerance input ────────────────────────

function ToleranceInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <label
      className="inline-flex items-center gap-1.5 text-[11px]"
      style={{ color: 'var(--color-text-muted)' }}
    >
      <span className="uppercase tracking-wider">
        {t('profileView.filter.tolerance', { defaultValue: 'Tol' })}
      </span>
      <input
        type="number"
        min={1}
        max={50}
        step={1}
        value={value}
        onChange={(e) => {
          const n = parseFloat(e.target.value);
          if (Number.isFinite(n) && n >= 1 && n <= 50) onChange(n);
        }}
        className="w-12 px-1.5 py-0.5 rounded text-xs text-right tabular-nums focus:outline-none focus:ring-1"
        style={{
          border: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          color: 'var(--color-text-primary)',
        }}
      />
      <span>m</span>
    </label>
  );
}

/** Hook helper for parent components that want to show the
 *  active-filter count without subscribing to the full state. */
export function useActiveFilterCount() {
  const { state } = useFilterState();
  return isFilterActive(state) ? 1 : 0;
}
