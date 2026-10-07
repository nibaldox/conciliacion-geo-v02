import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button';
import { PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import type { DesignBenchOption } from './Dashboard';
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
    <section data-slot="dashboard-bench-filter" className="relative z-10 rounded-xl border border-border bg-surface-raised p-4 space-y-2">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-72">
          <p id="bench-filter-label" className="mb-1 text-xs font-semibold text-text-secondary">{t('dashboard.bench_filter.label')}</p>
          <details ref={root} className="relative" onToggle={(event) => { if (!event.currentTarget.open) setSearch(''); }}>
            <summary aria-labelledby="bench-filter-label bench-filter-value" className="flex h-9 cursor-pointer list-none items-center justify-between gap-2 rounded-md border border-border bg-surface-sunken px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
              <span id="bench-filter-value" className="truncate">{summary}</span><span aria-hidden="true" className="text-xs text-text-muted">▾</span>
            </summary>
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-lg border border-border bg-surface-raised p-2 shadow-lg space-y-2">
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('dashboard.bench_filter.search')} aria-label={t('dashboard.bench_filter.search')} className={PROJECT_INPUT_CLASS} />
              <Button size="sm" variant="secondary" fullWidth onClick={() => onChange([])}>{t('dashboard.bench_filter.all_benches')}</Button>
              <div className="max-h-48 overflow-y-auto">
                {visible.map((option) => (
                  <label key={option.number} title={t('dashboard.bench_filter.design_elevation_help')} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-surface-muted">
                    <input type="checkbox" checked={selected.includes(option.number)} onChange={() => onChange(selected.includes(option.number) ? selected.filter((value) => value !== option.number) : [...selected, option.number].sort((a, b) => a - b))} className="accent-accent" />
                    {optionLabel(option)}
                  </label>
                ))}
                {!visible.length && <p className="p-2 text-xs text-text-muted">{t('dashboard.bench_filter.no_options')}</p>}
              </div>
            </div>
          </details>
        </div>
        <Button size="sm" variant="secondary" disabled={!selected.length} onClick={() => onChange([])}>{t('dashboard.bench_filter.reset')}</Button>
      </div>
      <p className="text-xs text-text-muted">{t('dashboard.bench_filter.help')}</p>
    </section>
  );
}
