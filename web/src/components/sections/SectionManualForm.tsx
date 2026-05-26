import { useState } from 'react';
import { useManualSections } from '../../api/hooks';
import type { SectionCreate } from '../../api/types';

interface RowData extends Omit<SectionCreate, 'origin'> {
  originX: number;
  originY: number;
}

function createEmptyRow(index: number): RowData {
  const num = String(index + 1).padStart(2, '0');
  return {
    name: `S-${num}`,
    originX: 0,
    originY: 0,
    azimuth: 0,
    length: 200,
    sector: '',
  };
}

export function SectionManualForm() {
  const [rows, setRows] = useState<RowData[]>([createEmptyRow(0)]);
  const [successCount, setSuccessCount] = useState<number | null>(null);
  const mutation = useManualSections();

  const addRow = () => {
    setRows((prev) => [...prev, createEmptyRow(prev.length)]);
    setSuccessCount(null);
  };

  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
    setSuccessCount(null);
  };

  const updateField = <K extends keyof RowData>(
    index: number,
    key: K,
    value: RowData[K],
  ) => {
    setRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    );
    setSuccessCount(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const sections: SectionCreate[] = rows.map((row) => ({
      name: row.name,
      origin: [row.originX, row.originY],
      azimuth: row.azimuth,
      length: row.length,
      sector: row.sector,
    }));

    mutation.mutate(sections, {
      onSuccess: (data) => {
        setSuccessCount(data.sections?.length ?? 0);
      },
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Table header */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
              <th className="text-left py-2 px-2 font-semibold w-24" style={{ color: 'var(--color-text-secondary)' }}>
                Nombre
              </th>
              <th className="text-left py-2 px-2 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Origen X
              </th>
              <th className="text-left py-2 px-2 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Origen Y
              </th>
              <th className="text-left py-2 px-2 font-semibold w-24" style={{ color: 'var(--color-text-secondary)' }}>
                Azimuth (°)
              </th>
              <th className="text-left py-2 px-2 font-semibold w-28" style={{ color: 'var(--color-text-secondary)' }}>
                Longitud (m)
              </th>
              <th className="text-left py-2 px-2 font-semibold w-28" style={{ color: 'var(--color-text-secondary)' }}>
                Sector
              </th>
              <th className="w-20" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} className="transition-colors" style={{ borderBottom: '1px solid var(--color-border)' }}>
                <td className="py-1.5 px-2">
                  <input
                    type="text"
                    value={row.name}
                    onChange={(e) => updateField(idx, 'name', e.target.value)}
                    className="w-full rounded px-2 py-1.5 text-sm outline-none"
                    style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                  />
                </td>
                <td className="py-1.5 px-2">
                  <input
                    type="number"
                    step="any"
                    value={row.originX || ''}
                    onChange={(e) =>
                      updateField(
                        idx,
                        'originX',
                        parseFloat(e.target.value) || 0,
                      )
                    }
                    className="w-full rounded px-2 py-1.5 text-sm outline-none"
                    style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                    placeholder="0.0"
                  />
                </td>
                <td className="py-1.5 px-2">
                  <input
                    type="number"
                    step="any"
                    value={row.originY || ''}
                    onChange={(e) =>
                      updateField(
                        idx,
                        'originY',
                        parseFloat(e.target.value) || 0,
                      )
                    }
                    className="w-full rounded px-2 py-1.5 text-sm outline-none"
                    style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                    placeholder="0.0"
                  />
                </td>
                <td className="py-1.5 px-2">
                  <input
                    type="number"
                    step="any"
                    value={row.azimuth}
                    onChange={(e) =>
                      updateField(
                        idx,
                        'azimuth',
                        parseFloat(e.target.value) || 0,
                      )
                    }
                    className="w-full rounded px-2 py-1.5 text-sm outline-none"
                    style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                  />
                </td>
                <td className="py-1.5 px-2">
                  <input
                    type="number"
                    min={1}
                    step="any"
                    value={row.length}
                    onChange={(e) =>
                      updateField(
                        idx,
                        'length',
                        parseFloat(e.target.value) || 200,
                      )
                    }
                    className="w-full rounded px-2 py-1.5 text-sm outline-none"
                    style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                  />
                </td>
                <td className="py-1.5 px-2">
                  <input
                    type="text"
                    value={row.sector}
                    onChange={(e) => updateField(idx, 'sector', e.target.value)}
                    className="w-full rounded px-2 py-1.5 text-sm outline-none"
                    style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                    placeholder="Ej: Norte"
                  />
                </td>
                <td className="py-1.5 px-2">
                  <button
                    type="button"
                    onClick={() => removeRow(idx)}
                    disabled={rows.length <= 1}
                    className="text-xs font-medium transition-colors disabled:cursor-not-allowed"
                    style={{ color: rows.length <= 1 ? 'var(--color-text-muted)' : 'var(--color-mine-red)' }}
                    title="Eliminar fila"
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={addRow}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
        >
          + Agregar Fila
        </button>

        <button
          type="submit"
          disabled={mutation.isPending || rows.length === 0}
          className="px-5 py-2.5 text-white rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ backgroundColor: 'var(--color-mine-blue)' }}
        >
          {mutation.isPending ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
              Guardando...
            </span>
          ) : (
            'Guardar Secciones'
          )}
        </button>

        {mutation.isError && (
          <p className="text-sm" style={{ color: 'var(--color-mine-red)' }}>
            Error: {mutation.error instanceof Error ? mutation.error.message : 'No se pudieron guardar las secciones'}
          </p>
        )}

        {successCount !== null && (
          <p className="text-sm font-medium" style={{ color: 'var(--color-mine-green)' }}>
            Se guardaron {successCount} secciones correctamente
          </p>
        )}
      </div>
    </form>
  );
}
