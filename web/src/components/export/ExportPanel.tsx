import { useState } from 'react';
import {
  useExportExcel,
  useExportWord,
  useExportDxf,
  useExportImages,
} from '../../api/hooks';

interface ExportForm {
  project: string;
  author: string;
  operation: string;
  phase: string;
}

export function ExportPanel() {
  const exportExcel = useExportExcel();
  const exportWord = useExportWord();
  const exportDxf = useExportDxf();
  const exportImages = useExportImages();

  const [form, setForm] = useState<ExportForm>({
    project: '',
    author: '',
    operation: '',
    phase: '',
  });

  const handleFieldChange = (field: keyof ExportForm, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const hasProjectInfo = form.project.trim() !== '';

  const projectParams = hasProjectInfo
    ? { project: form.project, author: form.author, operation: form.operation, phase: form.phase }
    : undefined;

  const isAnyExporting =
    exportExcel.isPending ||
    exportWord.isPending ||
    exportDxf.isPending ||
    exportImages.isPending;

  return (
    <div className="space-y-5">
      {/* Project info form */}
      <div className="rounded-xl shadow-sm p-5" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <h4 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>
          Información del Proyecto
        </h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Proyecto
            </label>
            <input
              type="text"
              value={form.project}
              onChange={(e) => handleFieldChange('project', e.target.value)}
              placeholder="Nombre del proyecto"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Autor
            </label>
            <input
              type="text"
              value={form.author}
              onChange={(e) => handleFieldChange('author', e.target.value)}
              placeholder="Nombre del autor"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Operación
            </label>
            <input
              type="text"
              value={form.operation}
              onChange={(e) => handleFieldChange('operation', e.target.value)}
              placeholder="Nombre de la operación"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Fase
            </label>
            <input
              type="text"
              value={form.phase}
              onChange={(e) => handleFieldChange('phase', e.target.value)}
              placeholder="Fase del proyecto"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
        </div>
      </div>

      {/* Export buttons */}
      <div className="grid grid-cols-4 gap-3">
        <ExportButton
          label="Exportar Excel"
          icon="📊"
          loading={exportExcel.isPending}
          disabled={isAnyExporting}
          onClick={() => exportExcel.mutate(projectParams)}
        />
        <ExportButton
          label="Exportar Word"
          icon="📄"
          loading={exportWord.isPending}
          disabled={isAnyExporting}
          onClick={() => exportWord.mutate(projectParams)}
        />
        <ExportButton
          label="Exportar DXF"
          icon="📐"
          loading={exportDxf.isPending}
          disabled={isAnyExporting}
          onClick={() => exportDxf.mutate()}
        />
        <ExportButton
          label="Exportar Imágenes"
          icon="🖼️"
          loading={exportImages.isPending}
          disabled={isAnyExporting}
          onClick={() => exportImages.mutate()}
        />
      </div>

      {/* Error feedback */}
      {(exportExcel.isError || exportWord.isError || exportDxf.isError || exportImages.isError) && (
        <p className="text-xs text-center" style={{ color: 'var(--color-mine-red)' }}>
          Error al exportar. Verifica que existan resultados procesados.
        </p>
      )}
    </div>
  );
}

// ─── Internal ExportButton component ──────────────────────────

function ExportButton({
  label,
  icon,
  loading,
  disabled,
  onClick,
}: {
  label: string;
  icon: string;
  loading: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex flex-col items-center gap-2 px-4 py-4 rounded-xl shadow-sm transition-all duration-200"
      style={disabled
        ? { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)', cursor: 'not-allowed', border: '1px solid var(--color-border)' }
        : { backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }
      }
    >
      {loading ? (
        <svg className="animate-spin h-6 w-6" style={{ color: 'var(--color-mine-blue)' }} viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : (
        <span className="text-2xl">{icon}</span>
      )}
      <span className="text-xs font-medium">{label}</span>
    </button>
  );
}
