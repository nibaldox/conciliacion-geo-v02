import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Tolerances } from '../../api/types';
import { DEFAULT_TOLERANCES } from '../../utils/constants';
import { PROJECT_INPUT_CLASS } from '../ui/ProjectControls';

export interface TolerancesFormProps {
  tolerances: Tolerances;
  /** Called with the tolerance key and the partial slice to merge into that key. */
  onChange: <K extends keyof Tolerances>(key: K, partial: Partial<Tolerances[K]>) => void;
}

type FieldMode = 'paired' | 'single';

interface ToleranceFieldDef {
  key: keyof Tolerances;
  labelKey: string;
  step: number;
  /** `paired` renders neg/pos inputs; `single` renders a single `min` input. */
  mode: FieldMode;
  /** Minimum value constraint for single-mode inputs. */
  min?: number;
  /** Whether to render the label with `<label>` (true) or `<p>` (false). */
  asLabel?: boolean;
  nonNegative?: boolean;
  defaultLabel?: string;
}

const TOLERANCE_FIELDS: readonly ToleranceFieldDef[] = [
  { key: 'bench_height',     labelKey: 'sidebar.tol_bench_height', step: 0.1, mode: 'paired' },
  { key: 'face_angle',       labelKey: 'sidebar.tol_face_angle',   step: 0.5, mode: 'paired' },
  { key: 'berm_width',       labelKey: 'sidebar.tol_berm_min',     step: 0.5, mode: 'single', min: 0, asLabel: true },
  { key: 'inter_ramp_angle', labelKey: 'sidebar.tol_inter_ramp',   step: 0.5, mode: 'paired' },
  { key: 'overall_angle',    labelKey: 'sidebar.tol_overall',      step: 0.5, mode: 'paired' },
];

const CREST_TOE_FIELD: ToleranceFieldDef = {
  key: 'crest_toe_deviation',
  labelKey: 'sidebar.tol_crest_toe',
  defaultLabel: 'Desviación cresta-pata (m)',
  step: 0.1,
  mode: 'paired',
  nonNegative: true,
};

const stringifyValue = (value: number | undefined) =>
  typeof value === 'number' && Number.isFinite(value) ? String(value) : '';

interface ToleranceInputProps {
  value: number | undefined;
  step: number;
  min?: number;
  ariaLabel: string;
  className: string;
  accept: (v: number) => boolean;
  onCommit: (v: number) => void;
}

export function ToleranceInput({ value, step, min, ariaLabel, accept, onCommit, className }: ToleranceInputProps) {
  const [text, setText] = useState(stringifyValue(value));
  const emittedRef = useRef(value);
  useEffect(() => {
    if (typeof value === 'number' && Number.isFinite(value) && value === emittedRef.current) return;
    emittedRef.current = value;
    setText(stringifyValue(value));
  }, [value]);
  const handleBlur = () => {
    const parsed = parseFloat(text);
    if (!Number.isFinite(parsed) || !accept(parsed)) setText(stringifyValue(value));
  };
  return (
    <input
      type="number"
      step={step}
      min={min}
      value={text}
      aria-label={ariaLabel}
      onChange={(e) => {
        const nextText = e.target.value;
        setText(nextText);
        const parsed = parseFloat(nextText);
        if (!Number.isFinite(parsed) || !accept(parsed)) return;
        emittedRef.current = parsed;
        onCommit(parsed);
      }}
      onBlur={handleBlur}
      className={className}
    />
  );
}

export function mergeTolerance<K extends keyof Tolerances>(
  tolerances: Tolerances,
  key: K,
  partial: Partial<Tolerances[K]>,
): Tolerances {
  const fallback = DEFAULT_TOLERANCES[key] as unknown as Record<string, number>;
  const current = (tolerances[key] ?? fallback) as unknown as Record<string, number>;
  return { ...tolerances, [key]: { ...current, ...partial } };
}

export function TolerancesForm({ tolerances, onChange }: TolerancesFormProps) {
  const { t } = useTranslation();
  const renderField = (field: ToleranceFieldDef) => {
    const value = (tolerances[field.key] ?? DEFAULT_TOLERANCES[field.key]) as unknown as Record<string, number>;
    const labelText = t(field.labelKey, { defaultValue: field.defaultLabel });
    const accept = (v: number) => (field.nonNegative ? Number.isFinite(v) && v >= 0 : !isNaN(v));
    return (
      <div key={field.key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
        <p className="text-xs text-text-muted">{labelText}</p>
        {field.mode === 'paired' ? (
          <div className="grid grid-cols-2 gap-1">
            {(['neg', 'pos'] as const).map((side) => (
              <ToleranceInput
                key={side}
                value={value[side]}
                step={field.step}
                min={field.nonNegative ? 0 : undefined}
                ariaLabel={t('project_input.tolerance_' + side, { field: labelText })}
                className={PROJECT_INPUT_CLASS}
                accept={accept}
                onCommit={(v) =>
                  onChange(field.key, { neg: value.neg, pos: value.pos, [side]: v } as Partial<Tolerances[typeof field.key]>)
                }
              />
            ))}
          </div>
        ) : (
          <ToleranceInput
            value={value.min}
            step={field.step}
            min={field.min}
            ariaLabel={labelText}
            className={PROJECT_INPUT_CLASS}
            accept={accept}
            onCommit={(v) => onChange(field.key, { min: v } as Partial<Tolerances[typeof field.key]>)}
          />
        )}
      </div>
    );
  };
  return (
    <section className="space-y-2">
      <h4 className="text-xs font-semibold text-text-secondary">{t('sidebar.tolerances_title')}</h4>
      <div className="grid grid-cols-2 gap-2 text-xs text-text-muted">
        <span />
        <div className="grid grid-cols-2 gap-1 text-center"><span>{t('project_input.negative')}</span><span>{t('project_input.positive')}</span></div>
      </div>
      {TOLERANCE_FIELDS.slice(0, 3).map(renderField)}
      {renderField(CREST_TOE_FIELD)}
      <details className="rounded-md border border-border p-2">
        <summary className="cursor-pointer text-xs font-medium text-text-secondary">{t('project_input.global_angles')}</summary>
        <div className="mt-2 space-y-2">{TOLERANCE_FIELDS.slice(3).map(renderField)}</div>
      </details>
    </section>
  );
}
