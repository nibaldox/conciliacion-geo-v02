import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();

  const [editState, setEditState] = useState<EditState | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  // Auto-cancel the confirm-clear armed state after 5s of inactivity
  // (so a user who clicks once and walks away doesn't leave a red
  // "Confirmar: Eliminar Todas" button waiting for an accidental 2nd
  // click). Esc also cancels.
  useEffect(() => {
    if (!confirmClear) return;
    const id = setTimeout(() => setConfirmClear(false), 5000);
    return () => clearTimeout(id);
  }, [confirmClear]);

  useEffect(() => {
    if (!confirmClear) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setConfirmClear(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirmClear]);

  const startEdit = (section: SectionResponse) => {
    setEditState({
      id: section.id,
      form: {
        name: section.name,
        origin: [...section.origin],
        azimuth: section.azimuth,
        length: section.length,
        length_up: section.length_up ?? (section.length / 2),
        length_down: section.length_down ?? (section.length / 2),
        sector: section.sector,
      },
    });
  };

  const cancelEdit = () => {
    setEditState(null);
  };

  const saveEdit = () => {
    if (!editState) return;
    
    // Automatically compute length based on length_up and length_down if they are edited
    const updatedForm = { ...editState.form };
    if (updatedForm.length_up !== undefined && updatedForm.length_down !== undefined) {
      updatedForm.length = updatedForm.length_up + updatedForm.length_down;
    }

    updateMutation.mutate(
      { id: editState.id, ...updatedForm },
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
        {t('section_list.loading')}
      </div>
    );
  }

  const items = sections ?? [];

  // Empty state
  if (items.length === 0) {
    return (
      <div className="text-center py-12 rounded-lg" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <span className="text-4xl block mb-3">&#128203;</span>
        <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{t('section_list.empty_title')}</p>
        <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
          {t('section_list.empty_subtitle')}
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
            {t('section_list.header')}
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
            ? t('section_list.clearing')
            : confirmClear
              ? t('section_list.clear_confirm')
              : t('section_list.clear_button')}
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg" style={{ border: '1px solid var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ backgroundColor: 'var(--color-surface-muted)', borderBottom: '1px solid var(--color-border)' }}>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                {t('section_list.col_name')}
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                {t('section_list.col_origin')}
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                {t('section_list.col_azimuth')}
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Long Sup
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                Long Inf
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                {t('section_list.col_length')}
              </th>
              <th className="text-left py-2.5 px-3 font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                {t('section_list.col_sector')}
              </th>
              <th className="text-right py-2.5 px-3 font-semibold w-28" style={{ color: 'var(--color-text-secondary)' }}>
                {t('section_list.col_actions')}
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
                        className="w-16 rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3">
                      <input
                        type="number"
                        min={1}
                        step="any"
                        value={editState.form.length_up}
                        onChange={(e) =>
                          updateEditField(
                            'length_up',
                            parseFloat(e.target.value) || 100,
                          )
                        }
                        className="w-16 rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3">
                      <input
                        type="number"
                        min={1}
                        step="any"
                        value={editState.form.length_down}
                        onChange={(e) =>
                          updateEditField(
                            'length_down',
                            parseFloat(e.target.value) || 100,
                          )
                        }
                        className="w-16 rounded px-2 py-1 text-sm outline-none"
                        style={{ border: '1px solid var(--color-mine-blue)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
                      />
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">
                      {(editState.form.length_up || 0) + (editState.form.length_down || 0)}m
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
                          {t('section_list.save')}
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-2 py-1 text-xs font-medium rounded transition-colors"
                          style={{ color: 'var(--color-text-muted)' }}
                        >
                          {t('section_list.cancel')}
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
                    {section.length_up !== undefined && section.length_up !== null ? section.length_up.toFixed(1) : (section.length / 2).toFixed(1)}m
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {section.length_down !== undefined && section.length_down !== null ? section.length_down.toFixed(1) : (section.length / 2).toFixed(1)}m
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
                        {t('section_list.edit')}
                      </button>
                      <button
                        onClick={() => handleDelete(section.id)}
                        disabled={deleteMutation.isPending}
                        className="px-2 py-1 text-xs font-medium rounded transition-colors disabled:opacity-50"
                        style={{ color: 'var(--color-mine-red)' }}
                      >
                        {t('common.delete')}
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
