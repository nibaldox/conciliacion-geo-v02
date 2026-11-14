import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useExportExcel,
  useExportWord,
  useExportPdf,
  useExportDxf,
  useExportImages,
  useExportLevels,
  type ExportFilters,
  type ExportSectorLevels,
  type ExportProjectInfo,
  type ExportResult,
} from '../../api/hooks';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import { Button } from '../ui/Button';
import { ExportLevelSelector } from './ExportLevelSelector';

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

interface ExportFormatRow {
  id: string;
  name: string;
  description: string;
  actionLabel: string;
  pending: boolean;
  failed: boolean;
  errorLabel: string;
  onClick: () => void;
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

type Translate = (key: string, options?: Record<string, unknown>) => string;

function normalizeLevelSectors(raw: unknown): ExportSectorLevels[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (entry): entry is ExportSectorLevels =>
      !!entry &&
      typeof entry === 'object' &&
      typeof (entry as ExportSectorLevels).sector === 'string' &&
      Array.isArray((entry as ExportSectorLevels).levels) &&
      (entry as ExportSectorLevels).levels.length > 0,
  );
}

function matchDashboardLevels(sectors: ExportSectorLevels[], dashboardLevels: string[]): Record<string, string[]> {
  const selection: Record<string, string[]> = {};
  if (dashboardLevels.length === 0) return selection;
  const names = new Set(dashboardLevels.map((value) => value.trim()));
  const numbers = dashboardLevels
    .filter((value) => value.trim() !== '')
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  for (const entry of sectors) {
    const labels = entry.levels
      .filter(
        (level) =>
          names.has(level.label) ||
          numbers.some((value) => value >= level.min_level && value <= level.max_level),
      )
      .map((level) => level.label);
    if (labels.length > 0) selection[entry.sector] = labels;
  }
  return selection;
}

function formatLevelsBySector(value: unknown, translate: Translate): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const parts: string[] = [];
  for (const [sector, levels] of Object.entries(value as Record<string, unknown>)) {
    if (!Array.isArray(levels)) continue;
    const caption = sector === ''
      ? translate('export.levels_no_sector')
      : translate('export.levels_sector', { sector });
    parts.push(`${caption}: ${levels.length > 0 ? levels.join(', ') : translate('export.levels_all')}`);
  }
  return parts.length > 0 ? parts.join('; ') : null;
}

function formatAppliedFilters(raw: string | null, translate: Translate): string | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const parts: string[] = [];
    const push = (label: string, value: unknown) => {
      if (Array.isArray(value) && value.length > 0) parts.push(`${label}: ${value.join(', ')}`);
    };
    push(translate('export.applied_sectors'), parsed.sectors);
    push(translate('export.applied_sections'), parsed.sections);
    const levelsBySector = formatLevelsBySector(parsed.levels_by_sector, translate);
    if (levelsBySector) parts.push(`${translate('export.applied_levels_by_sector')}: ${levelsBySector}`);
    else push(translate('export.applied_levels'), parsed.levels);
    push(translate('export.applied_benches'), parsed.selected_bench_numbers);
    return parts.length > 0 ? parts.join(' · ') : null;
  } catch {
    return null;
  }
}

export function ExportPanel() {
  const { t } = useTranslation();
  const sessionFilters = useSession((s) => s.filters);
  const { designMeshId, topoMeshId } = useSession();
  const hasVirtualDemoMesh = designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo;
  const exportsBlocked = hasVirtualDemoMesh;
  const exportExcel = useExportExcel();
  const exportWord = useExportWord();
  const exportPdf = useExportPdf();
  const exportDxf = useExportDxf();
  const exportImages = useExportImages();
  const exportLevels = useExportLevels();

  const [form, setForm] = useState<ExportForm>({
    project: '',
    author: '',
    operation: '',
    phase: '',
  });
  const [appliedFilters, setAppliedFilters] = useState<{ raw: string | null; selection: string } | null>(null);
  const [levelOverrides, setLevelOverrides] = useState<Record<string, string[]> | null>(null);

  const levelSectors = exportLevels.isError ? [] : normalizeLevelSectors(exportLevels.data?.sectors);
  const levelWarnings = Array.isArray(exportLevels.data?.warnings)
    ? exportLevels.data.warnings.filter((warning): warning is string => typeof warning === 'string')
    : [];
  const showLevelSelector = !exportsBlocked && levelSectors.length > 0;
  const levelSelection = levelOverrides ?? matchDashboardLevels(levelSectors, sessionFilters.level);
  const dashboardLevelActive = sessionFilters.level.length > 0;
  const levelsBySector: Record<string, string[]> = {};
  if (showLevelSelector) {
    for (const entry of levelSectors) {
      const selected = entry.levels
        .map((level) => level.label)
        .filter((label) => (levelSelection[entry.sector] ?? []).includes(label));
      if (selected.length > 0 || dashboardLevelActive) levelsBySector[entry.sector] = selected;
    }
  }
  const hasLevelSelection = Object.keys(levelsBySector).length > 0;
  const selectionKey = JSON.stringify([sessionFilters, levelsBySector]);
  const appliedNote = appliedFilters?.selection === selectionKey
    ? formatAppliedFilters(appliedFilters.raw, (key, options) => t(key, options)) : null;

  const handleLevelToggle = (sector: string, label: string) => {
    const current = levelSelection[sector] ?? [];
    const next = current.includes(label) ? current.filter((item) => item !== label) : [...current, label];
    setAppliedFilters(null);
    setLevelOverrides({ ...levelSelection, [sector]: next });
  };

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
    sector: sessionFilters.sector,
    section: sessionFilters.section,
    level: sessionFilters.level,
    ...(hasLevelSelection ? { levelsBySector } : {}),
  };

  const runExport = async (run: () => Promise<ExportResult | void>) => {
    if (exportsBlocked) return;
    setAppliedFilters(null);
    try {
      const result = await run();
      if (result && typeof result === 'object' && 'appliedFilters' in result) {
        setAppliedFilters({ raw: result.appliedFilters, selection: selectionKey });
      }
    } catch {
      return;
    }
  };

  const hasProjectInfo = form.project.trim() !== '';

  const baseParams: ExportProjectInfo = hasProjectInfo
    ? {
        filters: exportFilters,
        project: form.project,
        author: form.author,
        operation: form.operation,
        phase: form.phase,
      }
    : { filters: exportFilters };

  const benchCount = selectedBenchNumbers.length;
  const isBenchFilterActive = benchCount > 0;

  const isAnyExporting =
    exportExcel.isPending ||
    exportWord.isPending ||
    exportPdf.isPending ||
    exportDxf.isPending ||
    exportImages.isPending;

  const formats: ExportFormatRow[] = [
    {
      id: 'excel',
      name: t('export.format_excel', { defaultValue: 'Excel' }),
      description: t('export.format_excel_desc', { defaultValue: 'Léeme, Resumen, Bancos, Secciones, Sector-Nivel, Tronadura y Pozos' }),
      actionLabel: t('export.excel'),
      pending: exportExcel.isPending,
      failed: exportExcel.isError,
      errorLabel: t('export.error_excel'),
      onClick: () => void runExport(() => exportExcel.mutateAsync(baseParams)),
    },
    {
      id: 'word',
      name: t('export.format_word', { defaultValue: 'Word' }),
      description: t('export.format_word_desc', { defaultValue: 'Informe técnico editable con tablas y gráficos' }),
      actionLabel: t('export.word'),
      pending: exportWord.isPending,
      failed: exportWord.isError,
      errorLabel: t('export.error_word'),
      onClick: () => void runExport(() => exportWord.mutateAsync(baseParams)),
    },
    {
      id: 'pdf',
      name: t('export.format_pdf', { defaultValue: 'PDF ejecutivo' }),
      description: t('export.format_pdf_desc', { defaultValue: 'Informe resumido listo para compartir' }),
      actionLabel: t('export.pdf'),
      pending: exportPdf.isPending,
      failed: exportPdf.isError,
      errorLabel: t('export.error_pdf'),
      onClick: () => void runExport(() => exportPdf.mutateAsync(baseParams)),
    },
    {
      id: 'dxf',
      name: t('export.format_dxf', { defaultValue: 'DXF' }),
      description: t('export.format_dxf_desc', { defaultValue: 'Perfiles y secciones para software CAD' }),
      actionLabel: t('export.dxf'),
      pending: exportDxf.isPending,
      failed: exportDxf.isError,
      errorLabel: t('export.error_dxf'),
      onClick: () => { if (!exportsBlocked) exportDxf.mutate(); },
    },
    {
      id: 'images',
      name: t('export.format_images', { defaultValue: 'Imágenes' }),
      description: t('export.format_images_desc', { defaultValue: 'Perfil de cada sección en PNG, comprimido en ZIP' }),
      actionLabel: t('export.images'),
      pending: exportImages.isPending,
      failed: exportImages.isError,
      errorLabel: t('export.error_images'),
      onClick: () => void runExport(() => exportImages.mutateAsync({ filters: exportFilters })),
    },
  ];

  const fields: Array<{ key: keyof ExportForm; label: string; placeholder: string }> = [
    { key: 'project', label: t('export.project'), placeholder: t('export.project_placeholder') },
    { key: 'author', label: t('export.author'), placeholder: t('export.author_placeholder') },
    { key: 'operation', label: t('export.operation'), placeholder: t('export.operation_placeholder') },
    { key: 'phase', label: t('export.phase'), placeholder: t('export.phase_placeholder') },
  ];

  return (
    <div data-slot="export-panel" className="flex flex-col gap-6">
      <section className="flex flex-col gap-3" aria-labelledby="export-formats-title">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h3 id="export-formats-title" className="ui-section-title">
            {t('export.formats_title', { defaultValue: 'Exportar resultados' })}
          </h3>
          <div
            data-testid="export-filter-summary"
            className="flex flex-wrap items-center gap-2 text-xs text-text-muted"
          >
            <span className="sr-only">{t('export.filter_summary_prefix')}</span>
            <span className="ui-chip">
              {t('export.applied_benches')}:
              <span data-testid="export-filter-bench-count" className="tabular-nums text-text-primary">
                {isBenchFilterActive ? benchCount : t('export.all_benches')}
              </span>
            </span>
            <span className="ui-chip">
              {t('export.blast_tolerance_label')}:
              <span data-testid="export-filter-blast-tolerance" className="tabular-nums text-text-primary">
                {exportFilters.blastTolerance}m
              </span>
            </span>
          </div>
        </div>

        {exportsBlocked && (
          <p data-testid="export-demo-notice" role="status" className="text-xs leading-relaxed text-text-muted">
            {t('export.demo_unavailable')}
          </p>
        )}

        {!exportsBlocked && exportLevels.isLoading && (
          <p data-testid="export-level-loading" role="status" className="text-xs text-text-muted">
            {t('export.levels_loading')}
          </p>
        )}

        {!exportsBlocked && exportLevels.isError && (
          <div role="alert" className="text-xs text-text-muted">
            {t('export.levels_error')} <button type="button" onClick={() => void exportLevels.refetch()}>{t('export.levels_retry')}</button>
          </div>
        )}

        {showLevelSelector && (
          <ExportLevelSelector
            sectors={levelSectors}
            selection={levelsBySector}
            warnings={levelWarnings}
            disabled={isAnyExporting}
            onToggle={handleLevelToggle}
          />
        )}

        <ul data-testid="export-actions" className="divide-y divide-border">
          {formats.map((format) => (
            <li key={format.id} data-export-format={format.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-text-primary">{format.name}</p>
                <p className="line-clamp-2 text-xs text-text-muted" title={format.description}>{format.description}</p>
                {format.failed && (
                  <p role="alert" aria-live="polite" className="mt-0.5 text-xs text-[var(--status-nok-text)]">
                    {format.errorLabel}
                  </p>
                )}
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={format.onClick}
                disabled={isAnyExporting || exportsBlocked || (format.id !== 'dxf' && exportLevels.isLoading)}
                loading={format.pending}
                aria-label={format.actionLabel}
                className="shrink-0"
              >
                {t('export.download', { defaultValue: 'Exportar' })}
              </Button>
            </li>
          ))}
        </ul>

        {appliedNote && (
          <p data-testid="export-applied-filters" className="text-xs leading-relaxed text-text-muted">
            {t('export.applied_filters_prefix')} {appliedNote}
          </p>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h4 className="ui-section-title">{t('export.title')}</h4>
          <p className="mt-0.5 text-xs text-text-muted">
            {t('export.project_info_hint', { defaultValue: 'Opcional. Se incluye en los informes exportados.' })}
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {fields.map((field) => (
            <label key={field.key} className="flex min-w-0 flex-col gap-1">
              <span className="text-xs text-text-muted">{field.label}</span>
              <input
                type="text"
                value={form[field.key]}
                onChange={(e) => handleFieldChange(field.key, e.target.value)}
                placeholder={field.placeholder}
                className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent"
              />
            </label>
          ))}
        </div>
      </section>
    </div>
  );
}
