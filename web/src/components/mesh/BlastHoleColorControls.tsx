import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BlastHole3DRecord } from './BlastHoleFilters';
import {
  BLAST_HOLE_CATEGORY_OPTIONS,
  BLAST_HOLE_VARIABLE_OPTIONS,
  COLOR_SCALE_NAMES,
  getAvailableBlastHoleCategories,
  getAvailableBlastHoleVariables,
  mapBlastHoleColors,
  type BlastHoleCategory,
  type BlastHoleColorLegend,
  type BlastHoleColorMapping,
  type BlastHoleColorScale,
  type BlastHoleVariable,
} from './blastHoleColors';

export interface BlastHoleColorControlsProps {
  records: readonly BlastHole3DRecord[];
  filteredRecords: readonly BlastHole3DRecord[];
  onColorsChange: (mapping: BlastHoleColorMapping, kind: BlastHoleColorLegend['kind']) => void;
}

const LEGEND_ENTRY_LIMIT = 100;

export function BlastHoleColorControls({ records, filteredRecords, onColorsChange }: BlastHoleColorControlsProps) {
  const { t } = useTranslation();
  const [manualKind, setManualKind] = useState<'variable' | 'category' | null>(null);
  const [variable, setVariable] = useState<BlastHoleVariable>('charge');
  const [category, setCategory] = useState<BlastHoleCategory>('grid');
  const [palette, setPalette] = useState<BlastHoleColorScale>('Turbo');
  const onColorsChangeRef = useRef(onColorsChange);
  onColorsChangeRef.current = onColorsChange;
  const availableVariables = useMemo(() => getAvailableBlastHoleVariables(records), [records]);
  const availableCategories = useMemo(() => getAvailableBlastHoleCategories(records), [records]);
  const defaultKind = availableVariables.some((item) => item === 'charge' || item === 'powderFactor')
    ? 'variable'
    : availableCategories.length > 0 ? 'category' : 'variable';
  const kind = manualKind ?? defaultKind;
  const activeVariable = availableVariables.includes(variable) ? variable : availableVariables[0];
  const activeCategory = availableCategories.includes(category) ? category : availableCategories[0] ?? 'grid';
  const missingLabel = t('blast.colors.missing', { defaultValue: 'Sin dato' });
  const mapping = useMemo(() => mapBlastHoleColors(filteredRecords, {
    kind,
    variable: activeVariable ?? 'attribute',
    category: activeCategory,
    palette,
    sourceRecords: records,
    missingLabel,
  }), [filteredRecords, kind, activeVariable, activeCategory, palette, records, missingLabel]);

  useEffect(() => {
    onColorsChangeRef.current(mapping, mapping.legend.kind);
  }, [mapping]);

  const labelForVariable = (value: BlastHoleVariable) => {
    const option = BLAST_HOLE_VARIABLE_OPTIONS.find((item) => item.value === value);
    return t(`blast.colors.variable.${value}`, { defaultValue: option?.label ?? value });
  };
  const labelForCategory = (value: BlastHoleCategory) => {
    const option = BLAST_HOLE_CATEGORY_OPTIONS.find((item) => item.value === value);
    return t(`blast.colors.category.${value}`, { defaultValue: option?.label ?? value });
  };

  return (
    <section className="space-y-3 rounded-lg border border-[var(--color-border)] p-3" aria-label={t('blast.colors.title', { defaultValue: 'Colores de pozos' })}>
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))' }}>
        <label className="flex flex-col gap-1 text-xs">
          <span>{t('blast.colors.mode', { defaultValue: 'Colorear por' })}</span>
          <select
            aria-label={t('blast.colors.mode', { defaultValue: 'Colorear por' })}
            value={kind}
            onChange={(event) => setManualKind(event.target.value as 'variable' | 'category')}
            className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm"
          >
            <option value="variable">{t('blast.colors.modeVariable', { defaultValue: 'Variable' })}</option>
            <option value="category" disabled={availableCategories.length === 0}>{t('blast.colors.modeCategory', { defaultValue: 'Categoría' })}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span>{kind === 'variable'
            ? t('blast.colors.variableLabel', { defaultValue: 'Variable' })
            : t('blast.colors.categoryLabel', { defaultValue: 'Categoría' })}</span>
          <select
            aria-label={kind === 'variable'
              ? t('blast.colors.variableLabel', { defaultValue: 'Variable' })
              : t('blast.colors.categoryLabel', { defaultValue: 'Categoría' })}
            value={kind === 'variable' ? activeVariable ?? '' : activeCategory}
            disabled={kind === 'variable' ? availableVariables.length === 0 : availableCategories.length === 0}
            onChange={(event) => {
              setManualKind(kind);
              if (kind === 'variable') setVariable(event.target.value as BlastHoleVariable);
              else setCategory(event.target.value as BlastHoleCategory);
            }}
            className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm"
          >
            {kind === 'variable'
              ? availableVariables.length > 0
                ? availableVariables.map((item) => <option key={item} value={item}>{labelForVariable(item)}</option>)
                : <option value="">{t('blast.colors.noVariables', { defaultValue: 'No hay variables con datos disponibles' })}</option>
              : availableCategories.length > 0
                ? availableCategories.map((item) => <option key={item} value={item}>{labelForCategory(item)}</option>)
                : <option value="">{t('blast.colors.noCategories', { defaultValue: 'No hay categorías disponibles' })}</option>}
          </select>
        </label>
        {kind === 'variable' && availableVariables.length === 0 && <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.colors.noVariables', { defaultValue: 'No hay variables con datos disponibles' })}
        </p>}
        {kind === 'category' && availableCategories.length === 0 && <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.colors.noCategories', { defaultValue: 'No hay categorías disponibles' })}
        </p>}
        <label className="flex flex-col gap-1 text-xs">
          <span>{t('blast.colors.palette', { defaultValue: 'Escala de color' })}</span>
          <select
            aria-label={t('blast.colors.palette', { defaultValue: 'Escala de color' })}
            value={palette}
            disabled={kind === 'category'}
            onChange={(event) => setPalette(event.target.value as BlastHoleColorScale)}
            className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm disabled:opacity-60"
          >
            {COLOR_SCALE_NAMES.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
      <BlastHoleColorLegendView legend={mapping.legend} t={t} />
      {kind === 'variable' && (activeVariable === 'charge' || activeVariable === 'powderFactor') && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.colors.fixedRange', { min: 0, max: activeVariable === 'charge' ? 1000 : 200, defaultValue: 'La escala es fija ({{min}}–{{max}}); los valores fuera del rango usan el color extremo.' })}
        </p>
      )}
    </section>
  );
}

function BlastHoleColorLegendView({ legend, t }: {
  legend: BlastHoleColorLegend;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  if (legend.kind === 'category') {
    const visibleEntries = legend.entries.slice(0, LEGEND_ENTRY_LIMIT);
    return (
      <div aria-label={t('blast.colors.legendDiscrete', { defaultValue: 'Leyenda discreta' })}>
        <p className="mb-1 text-xs font-medium">{t('blast.colors.legendDiscrete', { defaultValue: 'Leyenda discreta' })}</p>
        <ul className="grid max-h-48 grid-cols-1 gap-x-3 gap-y-1 overflow-y-auto text-xs sm:grid-cols-2">
          {visibleEntries.map((entry) => <LegendEntry key={entry.label} label={entry.label} color={entry.color} />)}
          {legend.missing && <LegendEntry label={legend.missing.label} color={legend.missing.color} />}
        </ul>
        {legend.entries.length > LEGEND_ENTRY_LIMIT && <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.colors.legendLimit', { defaultValue: 'Se muestran {{shown}} de {{total}} categorías', shown: LEGEND_ENTRY_LIMIT, total: legend.entries.length })}
        </p>}
      </div>
    );
  }

  return (
    <div aria-label={t('blast.colors.legendContinuous', { defaultValue: 'Leyenda continua' })}>
      <p className="mb-1 text-xs font-medium">{t('blast.colors.legendContinuous', { defaultValue: 'Leyenda continua' })} · {legend.palette}</p>
      <div className="h-3 rounded" style={{ background: `linear-gradient(to right, ${legend.stops.map((stop) => `${stop.color} ${stop.position * 100}%`).join(', ')})` }} />
      <div className="flex justify-between gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
        <span>{legend.min === null ? '—' : legend.min}</span>
        <span>{legend.max === null ? '—' : legend.max}</span>
      </div>
      <ul className="mt-1 text-xs"><LegendEntry label={legend.missing.label} color={legend.missing.color} /></ul>
    </div>
  );
}

function LegendEntry({ label, color }: { label: string; color: string }) {
  return <li className="flex min-w-0 items-center gap-2">
    <span aria-hidden="true" className="h-3 w-3 shrink-0 rounded-full border border-black/20" style={{ backgroundColor: color }} />
    <span className="truncate">{label}</span>
  </li>;
}
