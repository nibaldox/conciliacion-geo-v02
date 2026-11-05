import { useTranslation } from 'react-i18next';
import { FilterToggle } from './atoms/FilterToggle';
import type { UseFilterStateApi } from '../application';
import { useFilterState } from '../application';
import { isFilterActive } from '../domain/filters';

export interface FilterBarProps {
  readonly filter: UseFilterStateApi;
  readonly blastDataAvailable?: boolean;
  readonly horizontalDeviationAvailable?: boolean;
  readonly activeCount?: number;
}

export function FilterBar({ filter, blastDataAvailable = false, horizontalDeviationAvailable = false, activeCount }: FilterBarProps) {
  const { t } = useTranslation();
  const { state, setField, reset } = filter;

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
      role="toolbar"
      aria-label={t('profileView.filter.label', { defaultValue: 'Mostrar' })}
      className="flex min-h-11 flex-wrap items-center gap-1.5 border-b border-border px-3 py-1.5"
    >
      <span className="mr-1 text-xs text-text-muted">
        {t('profileView.filter.label', { defaultValue: 'Mostrar' })}
      </span>

      <FilterToggle
        checked={reconciledOn}
        onChange={setReconciled}
        label={t('profileView.filter.reconciled', { defaultValue: 'Reconciliado' })}
        title={t('profileView.filter.reconciled_help', { defaultValue: 'Geometría idealizada detectada' })}
      />
      <FilterToggle
        checked={state.showAreas}
        onChange={(v) => setField('showAreas', v)}
        label={t('profileView.filter.areas', { defaultValue: 'Áreas' })}
        title={t('profileView.filter.areas_help', { defaultValue: 'Sobre-excavación y deuda de material' })}
      />
      <FilterToggle
        checked={state.showSpillAreas}
        onChange={(v) => setField('showSpillAreas', v)}
        label={t('profileView.filter.spill', { defaultValue: 'Derrame' })}
        title={t('profileView.filter.spill_help', { defaultValue: 'Material derramado en la base de los bancos' })}
      />
      <FilterToggle
        checked={state.showSemaphore}
        onChange={(v) => setField('showSemaphore', v)}
        label={t('profileView.filter.semaphore', { defaultValue: 'Semáforo' })}
        title={t('profileView.filter.semaphore_help', { defaultValue: 'Verde=Cumple, Amarillo=Alerta, Rojo=No cumple' })}
      />
      {horizontalDeviationAvailable && (
        <FilterToggle
          checked={state.showHorizontalDeviation}
          onChange={(v) => setField('showHorizontalDeviation', v)}
          label={t('profileView.filter.horizontal_deviation', { defaultValue: 'Desviación horizontal' })}
          title={t('profileView.filter.horizontal_deviation_help', {
            defaultValue: 'Colorea la topografía por dH a igual cota; + sobreexcavación, − faltante.',
          })}
        />
      )}

      {blastDataAvailable && (
        <>
          <span className="mx-1 inline-block h-4 w-px bg-border" aria-hidden="true" />
          <FilterToggle
            checked={state.showBlastHoles}
            onChange={(v) => setField('showBlastHoles', v)}
            label={t('profileView.filter.blast', { defaultValue: 'Pozos' })}
            title={t('profileView.filter.blast_help', { defaultValue: 'Proyección de pozos de tronadura' })}
          />
          {state.showBlastHoles && (
            <ToleranceInput value={state.blastTolerance} onChange={(v) => setField('blastTolerance', v)} />
          )}
        </>
      )}

      <div className="flex-1" />

      {hasActive && (
        <>
          <span
            data-slot="filter-active-count"
            className="inline-flex h-5 items-center gap-1 rounded-full border border-border px-2 text-xs tabular-nums text-text-muted"
          >
            {t('profileView.filter.active', { defaultValue: 'Activos' })}
            <span className="text-text-secondary">{displayCount}</span>
          </span>
          <button
            type="button"
            onClick={reset}
            className="rounded px-1.5 py-0.5 text-xs text-text-muted underline-offset-2 hover:text-text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {t('profileView.filter.reset', { defaultValue: 'Restablecer' })}
          </button>
        </>
      )}
    </div>
  );
}

function ToleranceInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { t } = useTranslation();
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-text-muted">
      <span>{t('profileView.filter.tolerance', { defaultValue: 'Tol' })}</span>
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
        className="h-7 w-12 rounded border border-border bg-surface px-1.5 text-right text-xs tabular-nums text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
      />
      <span>m</span>
    </label>
  );
}

export function useActiveFilterCount() {
  const { state } = useFilterState();
  return isFilterActive(state) ? 1 : 0;
}
