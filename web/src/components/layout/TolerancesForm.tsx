import { useTranslation } from 'react-i18next';
import type { Tolerances } from '../../api/types';
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
}

const TOLERANCE_FIELDS: readonly ToleranceFieldDef[] = [
  { key: 'bench_height',     labelKey: 'sidebar.tol_bench_height', step: 0.1, mode: 'paired' },
  { key: 'face_angle',       labelKey: 'sidebar.tol_face_angle',   step: 0.5, mode: 'paired' },
  { key: 'berm_width',       labelKey: 'sidebar.tol_berm_min',     step: 0.5, mode: 'single', min: 0, asLabel: true },
  { key: 'inter_ramp_angle', labelKey: 'sidebar.tol_inter_ramp',   step: 0.5, mode: 'paired' },
  { key: 'overall_angle',    labelKey: 'sidebar.tol_overall',      step: 0.5, mode: 'paired' },
];

export function TolerancesForm({ tolerances, onChange }: TolerancesFormProps) {
  const { t } = useTranslation();
  const renderField = (field: ToleranceFieldDef) => {
    const value = tolerances[field.key] as unknown as Record<string, number>;
    return (
      <div key={field.key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
        <p className="text-xs text-text-muted">{t(field.labelKey)}</p>
        {field.mode === 'paired' ? (
          <div className="grid grid-cols-2 gap-1">
            {(['neg', 'pos'] as const).map((side) => (
              <input key={side} type="number" step={field.step} value={value[side]}
                aria-label={t('project_input.tolerance_' + side, { field: t(field.labelKey) })}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  if (!isNaN(v)) onChange(field.key, { neg: value.neg, pos: value.pos, [side]: v } as Partial<Tolerances[typeof field.key]>);
                }} className={PROJECT_INPUT_CLASS} />
            ))}
          </div>
        ) : (
          <input type="number" step={field.step} min={field.min} value={value.min} aria-label={t(field.labelKey)}
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              if (!isNaN(v)) onChange(field.key, { min: v } as Partial<Tolerances[typeof field.key]>);
            }} className={PROJECT_INPUT_CLASS} />
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
      <details className="rounded-md border border-border p-2">
        <summary className="cursor-pointer text-xs font-medium text-text-secondary">{t('project_input.global_angles')}</summary>
        <div className="mt-2 space-y-2">{TOLERANCE_FIELDS.slice(3).map(renderField)}</div>
      </details>
    </section>
  );
}
