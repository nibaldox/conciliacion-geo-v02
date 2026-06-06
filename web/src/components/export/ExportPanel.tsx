import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useExportExcel,
  useExportWord,
  useExportDxf,
  useExportImages,
} from '../../api/hooks';
import { Button } from '../ui/Button';
import { IconDashboard, IconReport, IconDesign, IconImage } from '../ui/Icons';

interface ExportForm {
  project: string;
  author: string;
  operation: string;
  phase: string;
}

export function ExportPanel() {
  const { t } = useTranslation();
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
          {t('export.title')}
        </h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              {t('export.project')}
            </label>
            <input
              type="text"
              value={form.project}
              onChange={(e) => handleFieldChange('project', e.target.value)}
              placeholder={t('export.project_placeholder')}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              {t('export.author')}
            </label>
            <input
              type="text"
              value={form.author}
              onChange={(e) => handleFieldChange('author', e.target.value)}
              placeholder={t('export.author_placeholder')}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              {t('export.operation')}
            </label>
            <input
              type="text"
              value={form.operation}
              onChange={(e) => handleFieldChange('operation', e.target.value)}
              placeholder={t('export.operation_placeholder')}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              {t('export.phase')}
            </label>
            <input
              type="text"
              value={form.phase}
              onChange={(e) => handleFieldChange('phase', e.target.value)}
              placeholder={t('export.phase_placeholder')}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
        </div>
      </div>

      {/* Export buttons */}
      <div className="grid grid-cols-4 gap-3">
        <ExportButton
          label={t('export.excel')}
          icon={<IconDashboard className="w-6 h-6" />}
          loading={exportExcel.isPending}
          disabled={isAnyExporting}
          onClick={() => exportExcel.mutate(projectParams)}
        />
        <ExportButton
          label={t('export.word')}
          icon={<IconReport className="w-6 h-6" />}
          loading={exportWord.isPending}
          disabled={isAnyExporting}
          onClick={() => exportWord.mutate(projectParams)}
        />
        <ExportButton
          label={t('export.dxf')}
          icon={<IconDesign className="w-6 h-6" />}
          loading={exportDxf.isPending}
          disabled={isAnyExporting}
          onClick={() => exportDxf.mutate()}
        />
        <ExportButton
          label={t('export.images')}
          icon={<IconImage className="w-6 h-6" />}
          loading={exportImages.isPending}
          disabled={isAnyExporting}
          onClick={() => exportImages.mutate()}
        />
      </div>

      {/* Error feedback */}
      {(exportExcel.isError || exportWord.isError || exportDxf.isError || exportImages.isError) && (
        <p className="text-xs text-center" style={{ color: 'var(--color-mine-red)' }}>
          {t('export.error')}
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
  icon: React.ReactNode;
  loading: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant="secondary"
      onClick={onClick}
      disabled={disabled}
      loading={loading}
      fullWidth
      className="!flex-col !gap-2 !px-4 !py-4"
    >
      {!loading && <span className="mb-1 text-accent">{icon}</span>}
      <span className="text-xs font-medium">{label}</span>
    </Button>
  );
}
