import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAutoSections } from '../../api/hooks';
import type { SectionAutoParams } from '../../api/types';
import { Button } from '../ui/Button';

const INITIAL: Omit<SectionAutoParams, 'azimuth'> & { azimuth: number } = {
  start: [0, 0],
  end: [100, 100],
  n_sections: 5,
  length: 200,
  sector: '',
  az_method: 'perpendicular',
  fixed_az: 0,
  azimuth: 0,
};

const AZ_OPTION_KEYS: Record<string, string> = {
  perpendicular: 'section_form_auto.az_perpendicular',
  fixed: 'section_form_auto.az_fixed',
  local_slope: 'section_form_auto.az_local_slope',
};

export function SectionAutoForm() {
  const { t } = useTranslation();
  const [form, setForm] = useState(INITIAL);
  const [successCount, setSuccessCount] = useState<number | null>(null);
  const mutation = useAutoSections();

  const update = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSuccessCount(null);
  };

  const updateCoord = (
    field: 'start' | 'end',
    index: 0 | 1,
    value: string,
  ) => {
    const num = value === '' ? 0 : parseFloat(value);
    setForm((prev) => {
      const arr = [...prev[field]];
      arr[index] = isNaN(num) ? 0 : num;
      return { ...prev, [field]: arr as [number, number] };
    });
    setSuccessCount(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const payload: SectionAutoParams = {
      start: form.start,
      end: form.end,
      n_sections: form.n_sections,
      length: form.length,
      sector: form.sector,
      az_method: form.az_method,
      fixed_az: form.fixed_az,
      azimuth: form.az_method === 'fixed' ? form.fixed_az : null,
    };

    mutation.mutate(payload, {
      onSuccess: (data) => {
        setSuccessCount(data.sections?.length ?? 0);
      },
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Coordinates */}
      <div className="grid grid-cols-2 gap-4">
        <fieldset className="rounded-lg p-4" style={{ border: '1px solid var(--color-border)' }}>
          <legend className="text-sm font-semibold px-2" style={{ color: 'var(--color-text-secondary)' }}>
            {t('section_form_auto.start_legend')}
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                {t('section_form_auto.east')}
              </label>
              <input
                type="number"
                step="any"
                value={form.start[0] || ''}
                onChange={(e) => updateCoord('start', 0, e.target.value)}
                className="w-full rounded-md px-3 py-2 text-sm outline-none"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                placeholder="0.0"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                {t('section_form_auto.north')}
              </label>
              <input
                type="number"
                step="any"
                value={form.start[1] || ''}
                onChange={(e) => updateCoord('start', 1, e.target.value)}
                className="w-full rounded-md px-3 py-2 text-sm outline-none"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                placeholder="0.0"
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="rounded-lg p-4" style={{ border: '1px solid var(--color-border)' }}>
          <legend className="text-sm font-semibold px-2" style={{ color: 'var(--color-text-secondary)' }}>
            {t('section_form_auto.end_legend')}
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                {t('section_form_auto.east')}
              </label>
              <input
                type="number"
                step="any"
                value={form.end[0] || ''}
                onChange={(e) => updateCoord('end', 0, e.target.value)}
                className="w-full rounded-md px-3 py-2 text-sm outline-none"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                placeholder="0.0"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                {t('section_form_auto.north')}
              </label>
              <input
                type="number"
                step="any"
                value={form.end[1] || ''}
                onChange={(e) => updateCoord('end', 1, e.target.value)}
                className="w-full rounded-md px-3 py-2 text-sm outline-none"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                placeholder="0.0"
              />
            </div>
          </div>
        </fieldset>
      </div>

      {/* Parameters */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_auto.n_sections')}
          </label>
          <input
            type="number"
            min={1}
            max={200}
            value={form.n_sections}
            onChange={(e) => update('n_sections', parseInt(e.target.value) || 1)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_auto.length')}
          </label>
          <input
            type="number"
            min={1}
            step="any"
            value={form.length}
            onChange={(e) => update('length', parseFloat(e.target.value) || 200)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_auto.sector')}
          </label>
          <input
            type="text"
            value={form.sector}
            onChange={(e) => update('sector', e.target.value)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            placeholder={t('section_form_auto.sector_placeholder')}
          />
        </div>
      </div>

      {/* Azimuth method */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_auto.az_method')}
          </label>
          <select
            value={form.az_method}
            onChange={(e) =>
              update('az_method', e.target.value as SectionAutoParams['az_method'])
            }
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          >
            {Object.entries(AZ_OPTION_KEYS).map(([value, key]) => (
              <option key={value} value={value}>
                {t(key)}
              </option>
            ))}
          </select>
        </div>

        {form.az_method === 'fixed' && (
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
              {t('section_form_auto.fixed_az')}
            </label>
            <input
              type="number"
              min={0}
              max={360}
              step="any"
              value={form.fixed_az}
              onChange={(e) =>
                update('fixed_az', parseFloat(e.target.value) || 0)
              }
              className="w-full rounded-md px-3 py-2 text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
        )}
      </div>

      {/* Submit */}
      <div className="flex items-center gap-4 pt-2">
        <Button
          type="submit"
          disabled={mutation.isPending}
          loading={mutation.isPending}
        >
          {mutation.isPending ? t('section_form_auto.submitting') : t('section_form_auto.submit')}
        </Button>

        {mutation.isError && (
          <p className="text-sm" style={{ color: 'var(--color-mine-red)' }}>
            {t('common.error')}: {mutation.error instanceof Error ? mutation.error.message : t('section_form_auto.error_generic')}
          </p>
        )}

        {successCount !== null && (
          <p className="text-sm font-medium" style={{ color: 'var(--color-mine-green)' }}>
            {t('section_form_auto.success', { count: successCount })}
          </p>
        )}
      </div>
    </form>
  );
}
