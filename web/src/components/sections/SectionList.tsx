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
      <div className="flex items-center justify-center py-12 text-gray-400">
        <span className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-mine-blue rounded-full mr-3" />
        Cargando secciones...
      </div>
    );
  }

  const items = sections ?? [];

  // Empty state
  if (items.length === 0) {
    return (
      <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-100">
        <span className="text-4xl block mb-3">&#128203;</span>
        <p className="text-gray-500 text-sm">No hay secciones definidas</p>
        <p className="text-gray-400 text-xs mt-1">
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
          <h3 className="text-sm font-semibold text-gray-700">
            Secciones Definidas
          </h3>
          <span className="inline-flex items-center justify-center min-w-[24px] h-6 px-2 rounded-full bg-mine-blue text-white text-xs font-bold">
            {items.length}
          </span>
        </div>

        <button
          onClick={handleClearAll}
          disabled={clearMutation.isPending}
          className={`
            px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
            ${confirmClear
              ? 'bg-mine-red text-white hover:bg-red-700'
              : 'text-mine-red hover:bg-red-50 border border-red-200'
            }
            disabled:opacity-50 disabled:cursor-not-allowed
          `}
        >
          {clearMutation.isPending
            ? 'Eliminando...'
            : confirmClear
              ? 'Confirmar: Eliminar Todas'
              : 'Eliminar Todas'}
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">
                Nombre
              </th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">
                Origen
              </th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">
                Azimuth
              </th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">
                Longitud
              </th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">
                Sector
              </th>
              <th className="text-right py-2.5 px-3 font-semibold text-gray-600 w-28">
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
                    className="border-b border-gray-100 bg-blue-50/50"
                  >
                    <td className="py-2 px-3">
                      <input
                        type="text"
                        value={editState.form.name}
                        onChange={(e) =>
                          updateEditField('name', e.target.value)
                        }
                        className="w-full rounded border border-mine-blue/30 px-2 py-1 text-sm focus:border-mine-blue outline-none"
                      />
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex gap-1">
                        <input
                          type="number"
                          step="any"
                          value={editState.form.origin[0] || ''}
                          onChange={(e) => updateOrigin(0, e.target.value)}
                          className="w-20 rounded border border-mine-blue/30 px-2 py-1 text-sm focus:border-mine-blue outline-none"
                          placeholder="X"
                        />
                        <input
                          type="number"
                          step="any"
                          value={editState.form.origin[1] || ''}
                          onChange={(e) => updateOrigin(1, e.target.value)}
                          className="w-20 rounded border border-mine-blue/30 px-2 py-1 text-sm focus:border-mine-blue outline-none"
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
                        className="w-20 rounded border border-mine-blue/30 px-2 py-1 text-sm focus:border-mine-blue outline-none"
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
                        className="w-20 rounded border border-mine-blue/30 px-2 py-1 text-sm focus:border-mine-blue outline-none"
                      />
                    </td>
                    <td className="py-2 px-3">
                      <input
                        type="text"
                        value={editState.form.sector}
                        onChange={(e) =>
                          updateEditField('sector', e.target.value)
                        }
                        className="w-full rounded border border-mine-blue/30 px-2 py-1 text-sm focus:border-mine-blue outline-none"
                      />
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={saveEdit}
                          disabled={updateMutation.isPending}
                          className="px-2 py-1 text-xs font-medium text-mine-green hover:bg-green-50 rounded transition-colors disabled:opacity-50"
                        >
                          Guardar
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 rounded transition-colors"
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
                  className="border-b border-gray-100 hover:bg-gray-50/50 transition-colors"
                >
                  <td className="py-2.5 px-3 font-medium text-gray-800">
                    {section.name}
                  </td>
                  <td className="py-2.5 px-3 text-gray-600 font-mono text-xs">
                    {section.origin[0].toFixed(1)}, {section.origin[1].toFixed(1)}
                  </td>
                  <td className="py-2.5 px-3 text-gray-600">
                    {section.azimuth.toFixed(1)}°
                  </td>
                  <td className="py-2.5 px-3 text-gray-600">
                    {section.length.toFixed(1)}m
                  </td>
                  <td className="py-2.5 px-3 text-gray-600">
                    {section.sector || '—'}
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={() => startEdit(section)}
                        className="px-2 py-1 text-xs font-medium text-mine-blue hover:bg-blue-50 rounded transition-colors"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(section.id)}
                        disabled={deleteMutation.isPending}
                        className="px-2 py-1 text-xs font-medium text-mine-red hover:bg-red-50 rounded transition-colors disabled:opacity-50"
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
