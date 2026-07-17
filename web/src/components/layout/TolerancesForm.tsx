import { useTranslation } from 'react-i18next';
import type { Tolerances } from '../../api/types';

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

const INPUT_CLS =
  'w-full px-3 py-1.5 border rounded-md text-xs outline-none transition-colors focus:ring-2 focus:ring-accent/30 font-mono';

const inputStyle = {
  backgroundColor: 'var(--color-surface-sunken)',
  borderColor: 'var(--color-border)',
  color: 'var(--color-text-primary)',
} as const;

const labelStyle = { color: 'var(--color-text-muted)' } as const;

export function TolerancesForm({ tolerances, onChange }: TolerancesFormProps) {
  const { t } = useTranslation();

  return (
    <section className="space-y-3">
      <h4
        className="text-[10px] uppercase tracking-widest font-mono font-bold"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {t('sidebar.tolerances_title')}
      </h4>
      <div className="space-y-2.5">
        {TOLERANCE_FIELDS.map((field) => {
          const value = tolerances[field.key] as unknown as Record<string, number>;
          const LabelTag = field.asLabel ? 'label' : 'p';
          const labelClass = `text-[10px] uppercase font-medium mb-1 ${field.asLabel ? 'block' : ''}`;
          return (
            <div key={field.key}>
              <LabelTag className={labelClass} style={labelStyle}>
                {t(field.labelKey)}
              </LabelTag>
              {field.mode === 'paired' ? (
                <div className="flex gap-2">
                  <input
                    type="number"
                    step={field.step}
                    placeholder="−"
                    value={value.neg}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v)) onChange(field.key, { neg: v, pos: value.pos } as Partial<Tolerances[typeof field.key]>);
                    }}
                    className={INPUT_CLS}
                    style={inputStyle}
                  />
                  <input
                    type="number"
                    step={field.step}
                    placeholder="+"
                    value={value.pos}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v)) onChange(field.key, { neg: value.neg, pos: v } as Partial<Tolerances[typeof field.key]>);
                    }}
                    className={INPUT_CLS}
                    style={inputStyle}
                  />
                </div>
              ) : (
                <input
                  type="number"
                  step={field.step}
                  min={field.min}
                  value={value.min}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!isNaN(v)) onChange(field.key, { min: v } as Partial<Tolerances[typeof field.key]>);
                  }}
                  className={INPUT_CLS}
                  style={inputStyle}
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}