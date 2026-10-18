import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ComparisonResult } from '../../api/types';
import { Button } from '../ui/Button';
import {
  toggleDimensionValue,
  uniqueLevelOptions,
  uniqueSectionOptions,
  uniqueSectorOptions,
  type ResultFilterState,
} from './resultFilters';

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
}

function DimensionSelect({ dimension, label, options, selected, onToggle }: DimensionSelectProps) {
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
    <div ref={rootRef} data-dimension={dimension} className="relative z-10 w-40">
      <p id={labelId} className="mb-1 text-xs font-semibold text-text-secondary">{label}</p>
      <div role="group" aria-labelledby={labelId}>
        <details className="relative">
          <summary
            aria-labelledby={`${labelId} ${valueId}`}
            aria-haspopup="listbox"
            className="flex h-9 cursor-pointer list-none items-center justify-between gap-2 rounded-md bg-surface-sunken px-3 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            style={{ border: '1px solid var(--color-border)' }}
          >
            <span id={valueId} className="truncate">{summary}</span>
            <span aria-hidden="true" className="text-xs text-text-muted">▾</span>
          </summary>
          <ul
            role="listbox"
            aria-multiselectable="true"
            aria-label={`${label}: ${summary}`}
            className="absolute left-0 top-full z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-lg bg-surface-raised p-1 shadow-lg"
          >
            {options.map((option) => {
              const isSelected = selected.includes(option.value);
              return (
                <li key={option.value} role="option" aria-selected={isSelected}>
                  <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-surface-muted">
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

export function ResultFilters({ results, filters, onChange }: {
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

  return (
    <section data-slot="result-filters" className="flex flex-wrap items-end gap-3 rounded-xl bg-surface-raised p-4">
      <DimensionSelect
        dimension="sector"
        label={sectorLabel}
        options={sectorOptions}
        selected={filters.sector}
        onToggle={toggleSector}
      />
      <DimensionSelect
        dimension="section"
        label={sectionLabel}
        options={sectionOptions}
        selected={filters.section}
        onToggle={toggleSection}
      />
      <DimensionSelect
        dimension="level"
        label={levelLabel}
        options={levelOptions}
        selected={filters.level}
        onToggle={toggleLevel}
      />
      <Button
        size="sm"
        variant="secondary"
        disabled={noDimensionSelected}
        onClick={() => onChange({ ...filters, sector: [], section: [], level: [] })}
      >
        {t('dashboard.bench_filter.reset')}
      </Button>
    </section>
  );
}
