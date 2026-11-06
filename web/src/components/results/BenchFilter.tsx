import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button';
import { PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import type { DesignBenchOption } from './Dashboard';
import { positionFilterMenu } from './ResultFilters';
import type { TFunction } from 'i18next';

function designElevationLabel(option: DesignBenchOption, t: TFunction): string {
  if (option.minElevation == null || option.maxElevation == null) {
    return t('dashboard.bench_filter.no_design_elevation', { number: option.number });
  }
  const elevation = option.minElevation === option.maxElevation
    ? option.minElevation.toFixed(0)
    : `${option.minElevation.toFixed(0)}–${option.maxElevation.toFixed(0)}`;
  return t('dashboard.bench_filter.design_elevation', { elevation });
}

export function BenchFilter({ available, selected, onChange }: { available: readonly DesignBenchOption[]; selected: readonly number[]; onChange: (numbers: number[]) => void }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const root = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) root.current.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && root.current?.open) {
        root.current.open = false;
        root.current.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, []);
  const visible = available.filter((option) => `${option.number} ${designElevationLabel(option, t)}`.toLowerCase().includes(search.trim().toLowerCase()));
  const baseLabels = new Map(available.map((option) => [option.number, designElevationLabel(option, t)]));
  const labelCounts = new Map<string, number>();
  for (const label of baseLabels.values()) labelCounts.set(label, (labelCounts.get(label) ?? 0) + 1);
  const optionLabel = (option: DesignBenchOption) => {
    const label = baseLabels.get(option.number)!;
    return labelCounts.get(label)! > 1
      ? `${label} · ${t('dashboard.bench_filter.design_id', { number: option.number })}`
      : label;
  };
  const labels = selected.map((number) => available.find((option) => option.number === number)).filter((option): option is DesignBenchOption => option != null).map(optionLabel);
  const summary = selected.length === 0 ? t('dashboard.bench_filter.all_benches') : labels.length <= 2 ? labels.join(', ') : t('dashboard.bench_filter.selected', { count: labels.length });
  return (
    <section data-slot="dashboard-bench-filter" className="relative z-10 flex flex-wrap items-center gap-1.5 has-[details[open]]:z-20">
      <p id="bench-filter-label" className="w-28 shrink-0 whitespace-nowrap text-xs text-text-muted">{t('dashboard.bench_filter.label')}</p>
      <details ref={root} className="relative min-w-0 flex-1" onToggle={(event) => { if (!event.currentTarget.open) setSearch(''); else positionFilterMenu(event.currentTarget); }}>
        <summary aria-labelledby="bench-filter-label bench-filter-value" className="flex h-8 w-full cursor-pointer list-none items-center justify-between gap-2 rounded-md border border-border bg-surface-sunken px-2.5 text-xs text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
          <span id="bench-filter-value" className="truncate">{summary}</span><span aria-hidden="true" className="text-text-muted">▾</span>
        </summary>
        <div className="absolute left-0 top-full z-20 mt-1 w-64 space-y-2 rounded-lg border border-border bg-surface-raised p-2 shadow-lg">
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('dashboard.bench_filter.search')} aria-label={t('dashboard.bench_filter.search')} className={PROJECT_INPUT_CLASS} />
          <Button size="sm" variant="secondary" fullWidth onClick={() => onChange([])}>{t('dashboard.bench_filter.all_benches')}</Button>
          <div className="max-h-48 overflow-y-auto">
            {visible.map((option) => (
              <label key={option.number} title={t('dashboard.bench_filter.design_elevation_help')} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-muted">
                <input type="checkbox" checked={selected.includes(option.number)} onChange={() => onChange(selected.includes(option.number) ? selected.filter((value) => value !== option.number) : [...selected, option.number].sort((a, b) => a - b))} className="accent-accent" />
                {optionLabel(option)}
              </label>
            ))}
            {!visible.length && <p className="p-2 text-xs text-text-muted">{t('dashboard.bench_filter.no_options')}</p>}
          </div>
          <p className="px-1 text-xs text-text-muted">{t('dashboard.bench_filter.help')}</p>
        </div>
      </details>
      <button
        type="button"
        disabled={!selected.length}
        onClick={() => onChange([])}
        className="basis-full text-left text-xs text-text-muted underline-offset-2 hover:text-text-primary hover:underline disabled:invisible"
      >
        {t('dashboard.bench_filter.reset')}
      </button>
    </section>
  );
}
