import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BlastHole3DRecord } from './BlastHoleFilters';
import { BlastHoleColorLegendView } from './BlastHoleColorLegend';
import type { BlastViewColorConfig } from '../../stores/blastView';
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
  type BlastHoleRangeMode,
  type BlastHoleVariable,
} from './blastHoleColors';

export interface BlastHoleColorControlsProps {
  records: readonly BlastHole3DRecord[];
  filteredRecords: readonly BlastHole3DRecord[];
  onColorsChange: (mapping: BlastHoleColorMapping, kind: BlastHoleColorLegend['kind']) => void;
  config?: BlastViewColorConfig;
  onConfigChange?: (patch: Partial<BlastViewColorConfig>) => void;
  showLegend?: boolean;
}

type ColorState = Partial<BlastViewColorConfig>;

const FIXED_RANGE_VARIABLES: readonly BlastHoleVariable[] = ['charge', 'powderFactor', 'powderFactorGeometry'];
const ERROR_COLOR = 'var(--status-error, #b91c1c)';

function isValidRange(min: number | null | undefined, max: number | null | undefined): min is number {
  return typeof min === 'number' && typeof max === 'number' && Number.isFinite(min) && Number.isFinite(max) && min < max;
}

function parseDraft(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function asText(value: number | undefined): string {
  return value === undefined ? '' : String(value);
}

export function BlastHoleColorControls({
  records,
  filteredRecords,
  onColorsChange,
  config,
  onConfigChange,
  showLegend = true,
}: BlastHoleColorControlsProps) {
  const { t } = useTranslation();
  const controlled = config !== undefined;
  const [local, setLocal] = useState<ColorState>({});
  const [manualNeedsValues, setManualNeedsValues] = useState(false);
  const [draft, setDraft] = useState({ min: asText(config?.rangeMin), max: asText(config?.rangeMax) });

  const availableVariables = useMemo(() => getAvailableBlastHoleVariables(records), [records]);
  const availableCategories = useMemo(() => getAvailableBlastHoleCategories(records), [records]);
  const defaultKind: 'variable' | 'category' = availableVariables.some((item) => item === 'charge' || item === 'powderFactor')
    ? 'variable'
    : availableCategories.length > 0 ? 'category' : 'variable';

  const current: ColorState = controlled ? config : local;
  const kind: 'variable' | 'category' = current.kind ?? defaultKind;
  const variable: BlastHoleVariable = current.variable ?? 'charge';
  const category: BlastHoleCategory = current.category ?? 'grid';
  const palette: BlastHoleColorScale = current.palette ?? 'Turbo';
  const rangeMode: BlastHoleRangeMode = current.rangeMode ?? 'legacy';
  const rangeMin = current.rangeMin;
  const rangeMax = current.rangeMax;

  const onColorsChangeRef = useRef(onColorsChange);
  onColorsChangeRef.current = onColorsChange;
  const onConfigChangeRef = useRef(onConfigChange);
  onConfigChangeRef.current = onConfigChange;

  const patch = (partial: ColorState) => {
    if (controlled) onConfigChangeRef.current?.(partial);
    else setLocal((previous) => ({ ...previous, ...partial }));
  };

  const activeVariable = availableVariables.includes(variable) ? variable : availableVariables[0];
  const activeCategory = availableCategories.includes(category) ? category : availableCategories[0] ?? 'grid';
  const missingLabel = t('blast.colors.missing', { defaultValue: 'Sin dato' });
  const manualInvalid = kind === 'variable' && rangeMode === 'manual' && !isValidRange(rangeMin, rangeMax);
  const resetManualRange: ColorState = rangeMode === 'manual' ? { rangeMode: 'data', rangeMin: undefined, rangeMax: undefined } : {};

  const computed = useMemo<BlastHoleColorMapping | null>(() => {
    if (manualInvalid) return null;
    return mapBlastHoleColors(filteredRecords, {
      kind,
      variable: activeVariable ?? 'attribute',
      category: activeCategory,
      palette,
      sourceRecords: records,
      missingLabel,
      rangeMode: kind === 'variable' ? rangeMode : 'legacy',
      rangeMin: rangeMode === 'manual' ? rangeMin : undefined,
      rangeMax: rangeMode === 'manual' ? rangeMax : undefined,
    });
  }, [manualInvalid, filteredRecords, kind, activeVariable, activeCategory, palette, records, missingLabel, rangeMode, rangeMin, rangeMax]);

  const lastValidRef = useRef<{ mapping: BlastHoleColorMapping; variable: BlastHoleVariable | undefined } | null>(null);
  if (computed) lastValidRef.current = { mapping: computed, variable: activeVariable };
  const shown = computed ? { mapping: computed, variable: activeVariable } : lastValidRef.current;
  const mapping = shown?.mapping ?? null;

  useEffect(() => {
    if (mapping) onColorsChangeRef.current(mapping, mapping.legend.kind);
  }, [mapping]);

  useEffect(() => {
    setDraft({ min: asText(rangeMin), max: asText(rangeMax) });
  }, [rangeMin, rangeMax]);

  const draftMin = parseDraft(draft.min);
  const draftMax = parseDraft(draft.max);
  const draftValid = isValidRange(draftMin, draftMax);
  const draftTouched = draft.min.trim() !== '' || draft.max.trim() !== '';
  const validDraft = draftMin !== null && draftMax !== null && isValidRange(draftMin, draftMax) ? { min: draftMin, max: draftMax } : null;

  const labelForVariable = (value: BlastHoleVariable) => {
    const option = BLAST_HOLE_VARIABLE_OPTIONS.find((item) => item.value === value);
    return t(`blast.colors.variable.${value}`, { defaultValue: option?.label ?? value });
  };
  const labelForCategory = (value: BlastHoleCategory) => {
    const option = BLAST_HOLE_CATEGORY_OPTIONS.find((item) => item.value === value);
    return t(`blast.colors.category.${value}`, { defaultValue: option?.label ?? value });
  };

  const applyManual = () => {
    if (!validDraft) return;
    setManualNeedsValues(false);
    patch({ rangeMode: 'manual', rangeMin: validDraft.min, rangeMax: validDraft.max });
  };

  const changeRangeMode = (value: BlastHoleRangeMode) => {
    if (value !== 'manual') {
      setManualNeedsValues(false);
      patch({ rangeMode: value });
      return;
    }
    if (validDraft) {
      setManualNeedsValues(false);
      patch({ rangeMode: 'manual', rangeMin: validDraft.min, rangeMax: validDraft.max });
      return;
    }
    const observedMin = mapping?.legend.kind === 'variable' ? mapping.legend.observedMin : null;
    const observedMax = mapping?.legend.kind === 'variable' ? mapping.legend.observedMax : null;
    if (observedMin !== null && observedMin !== undefined && observedMax !== null && observedMax !== undefined && isValidRange(observedMin, observedMax)) {
      setManualNeedsValues(false);
      setDraft({ min: String(observedMin), max: String(observedMax) });
      patch({ rangeMode: 'manual', rangeMin: observedMin, rangeMax: observedMax });
      return;
    }
    setManualNeedsValues(true);
  };

  const legend = mapping?.legend ?? null;
  const shownVariable = shown?.variable;
  const legendSourceLabel = legend?.kind === 'variable' && shownVariable
    ? legend.sourceKey
      ? `${labelForVariable(shownVariable)} · ${legend.sourceKey}`
      : labelForVariable(shownVariable)
    : undefined;

  return (
    <section className="flex min-w-0 flex-col gap-2 border-t border-border pt-2" aria-label={t('blast.colors.title', { defaultValue: 'Colores de pozos' })}>
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 140px), 1fr))' }}>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-text-muted">
          <span>{t('blast.colors.mode', { defaultValue: 'Colorear por' })}</span>
          <select
            aria-label={t('blast.colors.mode', { defaultValue: 'Colorear por' })}
            value={kind}
            onChange={(event) => {
              setManualNeedsValues(false);
              patch({ kind: event.target.value as 'variable' | 'category', ...resetManualRange });
            }}
            className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm"
          >
            <option value="variable">{t('blast.colors.modeVariable', { defaultValue: 'Variable' })}</option>
            <option value="category" disabled={availableCategories.length === 0}>{t('blast.colors.modeCategory', { defaultValue: 'Categoría' })}</option>
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-text-muted">
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
              if (kind === 'variable') patch({ kind, variable: event.target.value as BlastHoleVariable, ...resetManualRange });
              else patch({ kind, category: event.target.value as BlastHoleCategory });
            }}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-text-primary"
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
        {kind === 'variable' && availableVariables.length === 0 && <p className="text-xs text-text-muted">
          {t('blast.colors.noVariables', { defaultValue: 'No hay variables con datos disponibles' })}
        </p>}
        {kind === 'category' && availableCategories.length === 0 && <p className="text-xs text-text-muted">
          {t('blast.colors.noCategories', { defaultValue: 'No hay categorías disponibles' })}
        </p>}
        <label className="flex min-w-0 flex-col gap-1 text-xs text-text-muted">
          <span>{t('blast.colors.palette', { defaultValue: 'Escala de color' })}</span>
          <select
            aria-label={t('blast.colors.palette', { defaultValue: 'Escala de color' })}
            value={palette}
            disabled={kind === 'category'}
            onChange={(event) => patch({ palette: event.target.value as BlastHoleColorScale })}
            className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm disabled:opacity-60"
          >
            {COLOR_SCALE_NAMES.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        {kind === 'variable' && (
          <label className="flex flex-col gap-1 text-xs">
            <span>{t('blast.colors.rangeMode', { defaultValue: 'Rango' })}</span>
            <select
              aria-label={t('blast.colors.rangeMode', { defaultValue: 'Rango' })}
              value={rangeMode}
              onChange={(event) => changeRangeMode(event.target.value as BlastHoleRangeMode)}
              className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm"
            >
              <option value="data">{t('blast.colors.rangeData', { defaultValue: 'Observado (todos los datos)' })}</option>
              <option value="legacy">{t('blast.colors.rangeLegacy', { defaultValue: 'Fijo heredado' })}</option>
              <option value="manual">{t('blast.colors.rangeManual', { defaultValue: 'Manual' })}</option>
            </select>
          </label>
        )}
      </div>
      {kind === 'variable' && rangeMode === 'manual' && (
        <fieldset className="grid grid-cols-2 gap-2 text-xs">
          <legend className="mb-1">{t('blast.colors.manualRange', { defaultValue: 'Límites manuales' })}</legend>
          <label className="flex flex-col gap-1">
            <span>{t('blast.colors.manualMin', { defaultValue: 'Mínimo' })}</span>
            <input
              type="number"
              step="any"
              aria-label={t('blast.colors.manualMin', { defaultValue: 'Mínimo' })}
              value={draft.min}
              onChange={(event) => setDraft((previous) => ({ ...previous, min: event.target.value }))}
              className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.colors.manualMax', { defaultValue: 'Máximo' })}</span>
            <input
              type="number"
              step="any"
              aria-label={t('blast.colors.manualMax', { defaultValue: 'Máximo' })}
              value={draft.max}
              onChange={(event) => setDraft((previous) => ({ ...previous, max: event.target.value }))}
              className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm"
            />
          </label>
          <div className="col-span-2">
            <button
              type="button"
              onClick={applyManual}
              disabled={!draftValid}
              className="min-h-11 rounded border border-[var(--color-border)] px-3 text-sm disabled:opacity-50"
            >
              {t('blast.colors.manualApply', { defaultValue: 'Aplicar rango' })}
            </button>
          </div>
          {(draftTouched || manualInvalid) && !draftValid && (
            <p role="alert" className="col-span-2" style={{ color: ERROR_COLOR }}>
              {t('blast.colors.manualInvalid', { defaultValue: 'Define mínimo y máximo finitos con mínimo menor que máximo. Se mantiene la última escala válida.' })}
            </p>
          )}
        </fieldset>
      )}
      {kind === 'variable' && rangeMode !== 'manual' && manualNeedsValues && (
        <p role="alert" className="text-xs" style={{ color: ERROR_COLOR }}>
          {t('blast.colors.manualNeedsValues', { defaultValue: 'Para usar rango manual define mínimo y máximo distintos.' })}
        </p>
      )}
      {showLegend && legend && <BlastHoleColorLegendView legend={legend} sourceLabel={legendSourceLabel} />}
      {showLegend && kind === 'variable' && rangeMode === 'legacy' && activeVariable !== undefined && FIXED_RANGE_VARIABLES.includes(activeVariable)
        && legend?.kind === 'variable' && legend.min !== null && legend.max !== null && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.colors.fixedRange', { min: legend.min, max: legend.max, defaultValue: 'La escala es fija ({{min}}–{{max}}); los valores fuera del rango usan el color extremo.' })}
        </p>
      )}
    </section>
  );
}
