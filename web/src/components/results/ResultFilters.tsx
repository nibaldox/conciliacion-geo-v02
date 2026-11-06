import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ComparisonResult } from '../../api/types';
import {
  toggleDimensionValue,
  uniqueLevelOptions,
  uniqueSectionOptions,
  uniqueSectorOptions,
  type ResultFilterState,
} from './resultFilters.utils';

export function positionFilterMenu(details: HTMLDetailsElement) {
  if (!details.open) return;
  const summary = details.querySelector('summary');
  const menu = summary?.nextElementSibling as HTMLElement | null;
  if (!summary || !menu) return;
  const rect = summary.getBoundingClientRect();
  menu.style.maxWidth = `${Math.max(0, window.innerWidth - rect.left - 8)}px`;
  menu.style.maxHeight = '';
  const naturalLimit = Number.parseFloat(getComputedStyle(menu).maxHeight) || Infinity;
  menu.style.maxHeight = `${Math.min(naturalLimit, Math.max(0, Math.max(window.innerHeight - rect.bottom - 12, rect.top - 12)))}px`;
  menu.style.overflowY = 'auto';
  const menuHeight = menu.getBoundingClientRect().height;
  const above = rect.bottom + 4 + menuHeight > window.innerHeight - 8 && rect.top > window.innerHeight - rect.bottom;
  menu.style.top = above ? 'auto' : '100%';
  menu.style.bottom = above ? '100%' : 'auto';
  menu.style.marginTop = above ? '0' : '4px';
  menu.style.marginBottom = above ? '4px' : '0';
}

interface DimensionOption {
  readonly value: string;
  readonly label: string;
}

interface DimensionSelectProps {
  readonly dimension: 'sector' | 'section' | 'level';
  readonly label: string;
  readonly options: readonly DimensionOption[];
  readonly selected: readonly string[];
  readonly onToggle: (value: string) => void;
  readonly compact: boolean;
}

function DimensionSelect({ dimension, label, options, selected, onToggle, compact }: DimensionSelectProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const { t } = useTranslation();

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        const details = rootRef.current.querySelector('details');
        if (details?.open) details.open = false;
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        const details = rootRef.current?.querySelector('details');
        if (details?.open) {
          event.stopPropagation();
          details.open = false;
          details.querySelector('summary')?.focus();
        }
      }
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const valueLabels = new Map(options.map((option) => [option.value, option.label]));
  const selectedLabels = selected.map((value) => valueLabels.get(value) ?? value);
  const summary = selected.length === 0 ? t('dashboard.bench_filter.all') : selectedLabels.join(', ');
  const labelId = `result-filters-${dimension}-label`;
  const valueId = `result-filters-${dimension}-value`;

  return (
    <div ref={rootRef} data-dimension={dimension} className={`relative z-10 flex items-center gap-1.5 has-[details[open]]:z-20 ${compact ? 'w-full' : ''}`}>
      <p id={labelId} className={`shrink-0 whitespace-nowrap text-xs text-text-muted ${compact ? 'w-28' : ''}`}>{label}</p>
      <div role="group" aria-labelledby={labelId}>
        <details className="relative" onToggle={(event) => positionFilterMenu(event.currentTarget)}>
          <summary
            aria-labelledby={`${labelId} ${valueId}`}
            className="flex h-8 w-32 cursor-pointer list-none items-center justify-between gap-2 rounded-md border border-border bg-surface-sunken px-2.5 text-xs text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <span id={valueId} className="truncate">{summary}</span>
            <span aria-hidden="true" className="text-text-muted">▾</span>
          </summary>
          <ul
            className="absolute left-0 top-full z-20 mt-1 max-h-48 w-56 overflow-y-auto rounded-lg border border-border bg-surface-raised p-1 shadow-lg"
          >
            {options.map((option) => {
              const isSelected = selected.includes(option.value);
              return (
                <li key={option.value}>
                  <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-muted">
                    <input
                      type="checkbox"
                      value={option.value}
                      checked={isSelected}
                      onChange={() => onToggle(option.value)}
                      className="accent-accent"
                    />
                    {option.label}
                  </label>
                </li>
              );
            })}
            {options.length === 0 && <li className="p-2 text-xs text-text-muted">{t('dashboard.bench_filter.no_options')}</li>}
          </ul>
        </details>
      </div>
    </div>
  );
}

export function ResultFilters({ results, filters, onChange, compact = false }: {
  readonly compact?: boolean;
  readonly results: readonly ComparisonResult[] | null | undefined;
  readonly filters: ResultFilterState;
  readonly onChange: (filters: ResultFilterState) => void;
}) {
  const { t } = useTranslation();
  const sectorLabel = t('dashboard.sector', { defaultValue: 'Sector' });
  const sectionLabel = t('table.col_section', { defaultValue: 'Sección' });
  const levelLabel = t('results.filters.level', { defaultValue: 'Cota' });
  const noSectorLabel = t('results.filters.no_sector', { defaultValue: '(sin sector)' });

  const sectorOptions = uniqueSectorOptions(results)
    .map((sector) => ({ value: sector, label: sector === '' ? noSectorLabel : sector }));
  const sectionOptions = uniqueSectionOptions(results)
    .map((section) => ({ value: section, label: section }));
  const levelOptions = uniqueLevelOptions(results)
    .map((level) => ({ value: level, label: level }));

  const toggleSector = (value: string) => onChange({ ...filters, sector: toggleDimensionValue(filters.sector, value) });
  const toggleSection = (value: string) => onChange({ ...filters, section: toggleDimensionValue(filters.section, value) });
  const toggleLevel = (value: string) => onChange({ ...filters, level: toggleDimensionValue(filters.level, value) });

  const noDimensionSelected = filters.sector.length === 0 && filters.section.length === 0 && filters.level.length === 0;
  const activeFilters = [
    ...filters.sector.map((value) => `${sectorLabel}: ${value === '' ? noSectorLabel : value}`),
    ...filters.section.map((value) => `${sectionLabel}: ${value}`),
    ...filters.level.map((value) => `${levelLabel}: ${value}`),
  ];

  return (
    <section data-slot="result-filters" aria-label={t('results.filters.group_label', { defaultValue: 'Filtros de resultados' })} className={compact ? "flex w-full flex-col items-start gap-2" : "flex flex-wrap items-center gap-x-4 gap-y-2"}>
      <DimensionSelect
        dimension="sector"
        compact={compact}
        label={sectorLabel}
        options={sectorOptions}
        selected={filters.sector}
        onToggle={toggleSector}
      />
      <DimensionSelect
        dimension="section"
        compact={compact}
        label={sectionLabel}
        options={sectionOptions}
        selected={filters.section}
        onToggle={toggleSection}
      />
      <DimensionSelect
        dimension="level"
        compact={compact}
        label={levelLabel}
        options={levelOptions}
        selected={filters.level}
        onToggle={toggleLevel}
      />
      <button
        type="button"
        disabled={noDimensionSelected}
        aria-describedby="result-filters-reset-help"
        title={t('results.filters.reset_help', { defaultValue: 'Restablece sector, sección y cota; conserva el filtro de banco.' })}
        onClick={() => onChange({ ...filters, sector: [], section: [], level: [] })}
        className="text-xs text-text-muted underline-offset-2 hover:text-text-primary hover:underline disabled:invisible"
      >
        {t('dashboard.bench_filter.reset')}
      </button>
      <p id="result-filters-reset-help" className="sr-only">
        {t('results.filters.reset_help', { defaultValue: 'Restablece sector, sección y cota; conserva el filtro de banco.' })}
      </p>
      <p className="sr-only" aria-live="polite">
        {activeFilters.length > 0 && (
          <>
            <span>{t('results.filters.active_label', { defaultValue: 'Filtros activos en este panel:' })}</span>{' '}
            {activeFilters.join(' · ')}
          </>
        )}
      </p>
    </section>
  );
}
