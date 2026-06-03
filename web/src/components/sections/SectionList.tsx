import { useState } from 'react';
import {
  useSections,
  useDeleteSection,
  useClearSections,
  useUpdateSection,
} from '../../api/hooks';
import type { SectionResponse, SectionCreate } from '../../api/types';

interface EditState {
  id: string;
  form: SectionCreate;
}

export function SectionList() {
  const { data: sections, isLoading } = useSections();
  const deleteMutation = useDeleteSection();
  const clearMutation = useClearSections();
  const updateMutation = useUpdateSection();

  const [editState, setEditState] = useState<EditState | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const startEdit = (section: SectionResponse) => {
    setEditState({
      id: section.id,
      form: {
        name: section.name,
        origin: [...section.origin],
        azimuth: section.azimuth,
        length: section.length,
        sector: section.sector,
      },
    });
  };

  const cancelEdit = () => {
    setEditState(null);
  };

  const saveEdit = () => {
    if (!editState) return;
    updateMutation.mutate(
      { id: editState.id, ...editState.form },
      { onSuccess: () => setEditState(null) },
    );
  };

  const updateEditField = <K extends keyof SectionCreate>(
    key: K,
    value: SectionCreate[K],
  ) => {
    if (!editState) return;
    setEditState({ ...editState, form: { ...editState.form, [key]: value } });
  };

  const updateOrigin = (index: 0 | 1, value: string) => {
    if (!editState) return;
    const origin = [...editState.form.origin] as [number, number];
    origin[index] = parseFloat(value) || 0;
    setEditState({ ...editState, form: { ...editState.form, origin } });
  };

  const handleDelete = (id: string) => {
    deleteMutation.mutate(id);
  };

  const handleClearAll = () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    clearMutation.mutate(undefined, {
      onSuccess: () => setConfirmClear(false),
    });
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12" style={{ color: 'var(--color-text-muted)' }}>
        <span className="animate-spin inline-block w-5 h-5 border-2 rounded-full mr-3" style={{ borderColor: 'var(--color-border)', borderTopColor: 'var(--color-mine-blue)' }} />
        Cargando secciones...
      </div>
    );
  }

  const items = sections ?? [];

  // Empty state
  if (items.length === 0) {
    return (
      <div className="text-center py-12 rounded-lg" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <span className="text-4xl block mb-3">&#128203;</span>
        <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No hay secciones definidas</p>
        <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
          Use las opciones de arriba para generar secciones
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
            Secciones Definidas
          </h3>
          <span className="inline-flex items-center justify-center min-w-[24px] h-6 px-2 rounded-full text-white text-xs font-bold" style={{ backgroundColor: 'var(--color-mine-blue)' }}>
            {items.length}
          </span>
        </div>

        <button
          onClick={handleClearAll}
          disabled={clearMutation.isPending}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={confirmClear
            ? { backgroundColor: 'var(--color-mine-red)', color: '#fff' }
            : { color: 'var(--color-mine-red)', border: '1px solid var(--color-mine-red)' }
          }
        >
          {clearMutation.isPending
            ? 'Eliminando...'
            : confirmClear
              ? 'Confirmar: Eliminar Todas'
              : 'Eliminar Todas'}
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg" style={{ border: '1px solid var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ backgroundColor: 'var(--color-surface-muted)', borderBottom: '1px solid var(--color-border)' }}>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Nombre
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Origen
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Azimuth
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Longitud
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Sector
              </th>
              <th className="text-right py-2.5 px-3 font-semibold w-28" style={{ color: 'var(--color-text-secondary)' }}>
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((section) => {
              const isEditing =
                editState !== null && editState.id === section.id;

              if (isEditing) {
                return (
                  <tr
                    key={section.id}
                    style={{ backgroundColor: 'var(--color-surface-muted)', borderBottom: '1px solid var(--color-border)' }}
                  >
                    <td className="py-2 px-3">
                      <input
                        type="text"
                        value={editState.form.name}
                        onChange={(e) =>
                          updateEditField('name', e.target.value)
                        }
                        className="w-full rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex gap-1">
                        <input
                          type="number"
                          step="any"
                          value={editState.form.origin[0] || ''}
                          onChange={(e) => updateOrigin(0, e.target.value)}
                          className="w-20 rounded px-2 py-1 text-sm outline-none"
                          style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                          placeholder="X"
                        />
                        <input
                          type="number"
                          step="any"
                          value={editState.form.origin[1] || ''}
                          onChange={(e) => updateOrigin(1, e.target.value)}
                          className="w-20 rounded px-2 py-1 text-sm outline-none"
                          style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                          placeholder="Y"
                        />
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <input
                        type="number"
                        step="any"
                        value={editState.form.azimuth}
                        onChange={(e) =>
                          updateEditField(
                            'azimuth',
                            parseFloat(e.target.value) || 0,
                          )
                        }
                        className="w-20 rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3">
                      <input
                        type="number"
                        min={1}
                        step="any"
                        value={editState.form.length}
                        onChange={(e) =>
                          updateEditField(
                            'length',
                            parseFloat(e.target.value) || 200,
                          )
                        }
                        className="w-20 rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3">
                      <input
                        type="text"
                        value={editState.form.sector}
                        onChange={(e) =>
                          updateEditField('sector', e.target.value)
                        }
                        className="w-full rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={saveEdit}
                          disabled={updateMutation.isPending}
                          className="px-2 py-1 text-xs font-medium rounded transition-colors disabled:opacity-50"
                          style={{ color: 'var(--color-mine-green)' }}
                        >
                          Guardar
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-2 py-1 text-xs font-medium rounded transition-colors"
                          style={{ color: 'var(--color-text-muted)' }}
                        >
                          Cancelar
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              }

              return (
                <tr
                  key={section.id}
                  className="transition-colors"
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                >
                  <td className="py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-primary)' }}>
                    {section.name}
                  </td>
                  <td className="py-2.5 px-3 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    {section.origin[0].toFixed(1)}, {section.origin[1].toFixed(1)}
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {section.azimuth.toFixed(1)}°
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {section.length.toFixed(1)}m
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {section.sector || '—'}
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={() => startEdit(section)}
                        className="px-2 py-1 text-xs font-medium rounded transition-colors"
                        style={{ color: 'var(--color-mine-blue)' }}
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(section.id)}
                        disabled={deleteMutation.isPending}
                        className="px-2 py-1 text-xs font-medium rounded transition-colors disabled:opacity-50"
                        style={{ color: 'var(--color-mine-red)' }}
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
