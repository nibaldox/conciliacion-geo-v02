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
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h4 className="text-sm font-semibold text-gray-800 mb-3">
          Información del Proyecto
        </h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Proyecto
            </label>
            <input
              type="text"
              value={form.project}
              onChange={(e) => handleFieldChange('project', e.target.value)}
              placeholder="Nombre del proyecto"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Autor
            </label>
            <input
              type="text"
              value={form.author}
              onChange={(e) => handleFieldChange('author', e.target.value)}
              placeholder="Nombre del autor"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Operación
            </label>
            <input
              type="text"
              value={form.operation}
              onChange={(e) => handleFieldChange('operation', e.target.value)}
              placeholder="Nombre de la operación"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Fase
            </label>
            <input
              type="text"
              value={form.phase}
              onChange={(e) => handleFieldChange('phase', e.target.value)}
              placeholder="Fase del proyecto"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none"
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
        <p className="text-xs text-red-500 text-center">
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
      className={`
        flex flex-col items-center gap-2 px-4 py-4 rounded-xl border border-gray-200 shadow-sm
        transition-all duration-200
        ${disabled
          ? 'bg-gray-50 text-gray-400 cursor-not-allowed'
          : 'bg-white text-gray-700 hover:bg-gray-50 hover:border-gray-300 hover:shadow-md active:scale-[0.98]'
        }
      `}
    >
      {loading ? (
        <svg className="animate-spin h-6 w-6 text-mine-blue" viewBox="0 0 24 24" fill="none">
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
