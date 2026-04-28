import { useState } from 'react';
import { useAutoSections } from '../../api/hooks';
import { AZ_METHODS } from '../../utils/constants';
import type { SectionAutoParams } from '../../api/types';

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

export function SectionAutoForm() {
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
            Punto de Inicio
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                Este (X)
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
                Norte (Y)
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
            Punto Final
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                Este (X)
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
                Norte (Y)
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
            Número de Secciones
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
            Longitud (m)
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
            Sector
          </label>
          <input
            type="text"
            value={form.sector}
            onChange={(e) => update('sector', e.target.value)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            placeholder="Ej: Norte"
          />
        </div>
      </div>

      {/* Azimuth method */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            Método de Azimuth
          </label>
          <select
            value={form.az_method}
            onChange={(e) =>
              update('az_method', e.target.value as SectionAutoParams['az_method'])
            }
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          >
            {AZ_METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        {form.az_method === 'fixed' && (
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
              Azimuth Fijo (°)
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
        <button
          type="submit"
          disabled={mutation.isPending}
          className="px-5 py-2.5 text-white rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ backgroundColor: 'var(--color-mine-blue)' }}
        >
          {mutation.isPending ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
              Generando...
            </span>
          ) : (
            'Generar Secciones'
          )}
        </button>

        {mutation.isError && (
          <p className="text-sm" style={{ color: 'var(--color-mine-red)' }}>
            Error: {mutation.error instanceof Error ? mutation.error.message : 'No se pudieron generar las secciones'}
          </p>
        )}

        {successCount !== null && (
          <p className="text-sm font-medium" style={{ color: 'var(--color-mine-green)' }}>
            Se generaron {successCount} secciones correctamente
          </p>
        )}
      </div>
    </form>
  );
}
