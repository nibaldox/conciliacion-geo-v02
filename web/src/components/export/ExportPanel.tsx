import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useExportExcel,
  useExportWord,
  useExportPdf,
  useExportDxf,
  useExportImages,
  type ExportFilters,
  type ExportProjectInfo,
} from '../../api/hooks';
import { useSession } from '../../stores/session';
import { Button } from '../ui/Button';
import { IconDashboard, IconReport, IconDesign, IconImage } from '../ui/Icons';

interface ExportForm {
  project: string;
  author: string;
  operation: string;
  phase: string;
}

interface ProfileFilterSnapshot {
  showReconciledDesign?: boolean;
  showReconciledTopo?: boolean;
  showSpillAreas?: boolean;
  showBlastHoles?: boolean;
  blastTolerance?: number;
}

const PROFILE_FILTERS_STORAGE_KEY = 'profileView.filters';

function readProfileFilters(): ProfileFilterSnapshot {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(PROFILE_FILTERS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as ProfileFilterSnapshot;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function ExportPanel() {
  const { t } = useTranslation();
  const sessionFilters = useSession((s) => s.filters);
  const exportExcel = useExportExcel();
  const exportWord = useExportWord();
  const exportPdf = useExportPdf();
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

  const profileFilters = readProfileFilters();
  const selectedBenchNumbers = sessionFilters.bench;

  const exportFilters: ExportFilters = {
    showReconciledDesign: profileFilters.showReconciledDesign ?? true,
    showReconciledTopo: profileFilters.showReconciledTopo ?? true,
    showSpillAreas: profileFilters.showSpillAreas ?? true,
    showBlastHoles: profileFilters.showBlastHoles ?? true,
    blastTolerance: profileFilters.blastTolerance ?? 2,
    selectedBenchNumbers,
  };

  const hasProjectInfo = form.project.trim() !== '';

  const baseParams: ExportProjectInfo = { filters: exportFilters };
  if (hasProjectInfo) {
    baseParams.project = form.project;
    baseParams.author = form.author;
    baseParams.operation = form.operation;
    baseParams.phase = form.phase;
  }

  const benchCount = selectedBenchNumbers.length;
  const isBenchFilterActive = benchCount > 0;

  const isAnyExporting =
    exportExcel.isPending ||
    exportWord.isPending ||
    exportPdf.isPending ||
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
      <div className="grid grid-cols-5 gap-3">
        <ExportButton
          label={t('export.excel')}
          icon={<IconDashboard className="w-6 h-6" />}
          loading={exportExcel.isPending}
          disabled={isAnyExporting}
          onClick={() => exportExcel.mutate(baseParams)}
        />
        <ExportButton
          label={t('export.word')}
          icon={<IconReport className="w-6 h-6" />}
          loading={exportWord.isPending}
          disabled={isAnyExporting}
          onClick={() => exportWord.mutate(baseParams)}
        />
        <ExportButton
          label={t('export.pdf')}
          icon={<IconReport className="w-6 h-6" />}
          loading={exportPdf.isPending}
          disabled={isAnyExporting}
          onClick={() => exportPdf.mutate(baseParams)}
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

      <div
        data-testid="export-filter-summary"
        className="text-[11px] leading-relaxed px-1"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t('export.filter_summary_prefix')}{' '}
        <strong data-testid="export-filter-bench-count" style={{ color: 'var(--color-text-secondary)' }}>
          {isBenchFilterActive ? benchCount : t('export.all_benches')}
        </strong>
        {' · '}
        {t('export.blast_tolerance_label')}{' '}
        <strong data-testid="export-filter-blast-tolerance" style={{ color: 'var(--color-text-secondary)' }}>
          {exportFilters.blastTolerance}m
        </strong>
      </div>

      {/* Error feedback */}
      {(exportExcel.isError || exportWord.isError || exportPdf.isError || exportDxf.isError || exportImages.isError) && (
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
