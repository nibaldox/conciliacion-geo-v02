import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUploadMesh, useDeleteMesh, useMeshInfo, useInspectDxf, useConfirmDxf, useCancelDxf } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { TryDemoButton } from '../demo/TryDemoButton';
import { ErrorBanner } from '../ui/ErrorBanner';
import type { DxfImportReport, DxfInspectResponse, MeshType } from '../../api/types';
import { DxfImportDialog, DxfImportSummary } from './DxfImportDialog';
import { IconMesh } from '../ui/Icons';
import { Spinner } from '../ui/Spinner';

/** Accepted file extensions */
const ACCEPTED_EXTENSIONS = ['.stl', '.obj', '.ply', '.dxf'];
const ACCEPTED_MIME = '.stl,.obj,.ply,.dxf';

interface DropZoneProps {
  type: MeshType;
  meshId: string | null;
  onSetMeshId: (id: string | null) => void;
  compact?: boolean;
}

/* ─── Individual Drop Zone ───────────────────────────────── */

function DropZone({ type, meshId, onSetMeshId, compact = false }: DropZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dxfReport, setDxfReport] = useState<DxfInspectResponse | null>(null);
  const [dxfImportResult, setDxfImportResult] = useState<DxfImportReport | null>(null);
  const [dxfError, setDxfError] = useState<string | null>(null);
  const inspectDxf = useInspectDxf();
  const confirmDxf = useConfirmDxf();
  const cancelDxf = useCancelDxf();
  const cancelDxfMutation = cancelDxf.mutate;
  const dxfRequestRef = useRef(0);
  const stagedDxfRef = useRef<string | null>(null);
  const upload = useUploadMesh();
  const removeMesh = useDeleteMesh();
  const { data: meshInfo } = useMeshInfo(meshId);
  const { t } = useTranslation();

  const label = type === 'design' ? t('step1.design') : t('step1.topo');
  const borderColor = type === 'design' ? 'blue' : 'green';

  const getApiError = useCallback((error: unknown) => {
    if (typeof error === 'object' && error !== null && 'response' in error) {
      const response = (error as { response?: { data?: { detail?: unknown } } }).response;
      const translateCode = (code: string) => t(`step1.dxf.warning.${code}`, { defaultValue: '' });
      if (typeof response?.data?.detail === 'string') return translateCode(response.data.detail) || response.data.detail;
      if (response?.data?.detail && typeof response.data.detail === 'object' && 'message' in response.data.detail) {
        const detail = response.data.detail as { message?: unknown; error_code?: unknown };
        const code = typeof detail.error_code === 'string' ? detail.error_code : null;
        const message = detail.message;
        if (code && translateCode(code)) return translateCode(code);
        if (typeof message === 'string') return message;
      }
    }
    return t('step1.upload_failed');
  }, [t]);

  const handleFile = useCallback(
    (file: File) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      const requestId = ++dxfRequestRef.current;
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        setUploadError(t('step1.unsupported_format', { formats: ACCEPTED_EXTENSIONS.join(', ') }));
        return;
      }
      if (ext === '.dxf') {
        setUploadError(null);
        setDxfError(null);
        setDxfReport(null);
        inspectDxf.mutate({ file, type }, {
          onSuccess: (report) => {
            if (requestId !== dxfRequestRef.current) {
              cancelDxfMutation(report.upload_id);
              return;
            }
            stagedDxfRef.current = report.upload_id;
            setDxfReport(report);
          },
          onError: (error) => {
            if (requestId === dxfRequestRef.current) setDxfError(getApiError(error));
          },
        });
        return;
      }
      setDxfError(null);
      setDxfReport(null);
      setUploadError(null);
      if (stagedDxfRef.current) {
        cancelDxfMutation(stagedDxfRef.current);
        stagedDxfRef.current = null;
      }
      upload.mutate(
        { file, type },
        {
          onSuccess: (res) => {
            setUploadError(null);
            setDxfImportResult(null);
            onSetMeshId(res.mesh_id);
          },
          onError: (err) => {
            console.error('Upload failed:', err);
            setUploadError(getApiError(err));
          },
        },
      );
    },
    [upload, type, onSetMeshId, t, inspectDxf, cancelDxfMutation, getApiError],
  );

  const handleDxfCancel = useCallback(() => {
    dxfRequestRef.current += 1;
    const uploadId = stagedDxfRef.current;
    stagedDxfRef.current = null;
    setDxfReport(null);
    setDxfError(null);
    if (uploadId) cancelDxfMutation(uploadId);
  }, [cancelDxfMutation]);

  const handleDxfConfirm = useCallback((layers: string[], units: number) => {
    if (!dxfReport) return;
    setDxfError(null);
    confirmDxf.mutate({ uploadId: dxfReport.upload_id, layers, units }, {
      onSuccess: (result) => {
        stagedDxfRef.current = null;
        setDxfReport(null);
        setDxfImportResult(result.import_report);
        onSetMeshId(result.mesh_id);
      },
      onError: (error) => setDxfError(getApiError(error)),
    });
  }, [dxfReport, confirmDxf, onSetMeshId, getApiError]);

  useEffect(() => () => {
    dxfRequestRef.current += 1;
    if (stagedDxfRef.current) cancelDxfMutation(stagedDxfRef.current);
  }, [cancelDxfMutation]);

  const dxfDialog = dxfReport ? <DxfImportDialog report={dxfReport} type={type} busy={confirmDxf.isPending} error={dxfError} onConfirm={handleDxfConfirm} onCancel={handleDxfCancel} /> : null;
  const dxfStatus = <>
    {inspectDxf.isPending && <div role="status" className="mb-2 flex items-center gap-2 text-sm text-text-secondary"><Spinner size="sm" />{t('step1.dxf.inspecting')}</div>}
    {dxfError && !dxfReport && <ErrorBanner message={dxfError} onDismiss={() => setDxfError(null)} autoDismissMs={10000} />}
  </>;

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleRemove = useCallback(() => {
    if (!meshId) return;
    removeMesh.mutate(meshId, {
      onSuccess: () => onSetMeshId(null),
    });
  }, [meshId, removeMesh, onSetMeshId]);

  if (compact) {
    return (
      <><div data-slot="mesh-upload-zone" data-compact="true" className="min-w-0">
        <ErrorBanner message={uploadError} onDismiss={() => setUploadError(null)} autoDismissMs={6000} />
        {dxfStatus}
        {upload.isPending ? (
          <div role="status" className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2">
            <Spinner size="sm" />
            <div className="min-w-0"><p className="text-sm font-medium">{t('step1.uploading', { label })}</p><p className="truncate text-xs text-text-muted" title={upload.variables?.file.name}>{upload.variables?.file.name}</p></div>
          </div>
        ) : meshId && meshInfo ? (
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="flex min-w-0 items-center gap-2"><IconMesh className="h-4 w-4 shrink-0 text-mine-green" /><p className="text-sm font-medium">{label}</p></div>
            <p className="mt-1 truncate text-xs text-text-secondary" title={meshInfo.filename}>{meshInfo.filename}</p>
            {(dxfImportResult ?? meshInfo.import_report) && <DxfImportSummary report={(dxfImportResult ?? meshInfo.import_report)!} />}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span className="text-text-muted" title={t('step1.mesh_counts', { vertices: meshInfo.n_vertices, faces: meshInfo.n_faces })}>△ {meshInfo.n_vertices.toLocaleString()} · ◻ {meshInfo.n_faces.toLocaleString()}</span>
              <button type="button" className="text-accent-bright hover:underline" onClick={() => fileInputRef.current?.click()}>{t('step1.replace')}</button>
              <button type="button" className="text-mine-red hover:underline disabled:opacity-50" onClick={handleRemove} disabled={removeMesh.isPending}>{removeMesh.isPending ? t('step1.removing') : t('common.delete')}</button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title={t('step1.max_size')}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            aria-label={t('step1.select_mesh', { label })}
            className={`flex w-full items-center gap-3 rounded-lg border border-dashed px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${isDragging ? 'border-accent bg-accent-bg' : 'border-border-strong bg-surface hover:bg-surface-muted'}`}
          >
            <IconMesh className={`h-5 w-5 shrink-0 ${type === 'design' ? 'text-mine-blue' : 'text-mine-green'}`} />
            <span className="min-w-0"><span className="block text-sm font-medium text-text-primary">{label}</span><span className="block text-xs text-text-muted">{t('step1.compact_drop_hint')}</span></span>
          </button>
        )}
        <input ref={fileInputRef} type="file" accept={ACCEPTED_MIME} className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) handleFile(file); event.target.value = ''; }} />
      </div>{dxfDialog}</>
    );
  }

  // ── Upload in progress ──
  if (upload.isPending) {
    return (
      <><div
        data-slot="mesh-upload-zone"
        className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-4 transition-colors min-h-[160px]"
        style={{ borderColor: 'var(--color-border)' }}
      >
        {dxfStatus}
        <div className="animate-spin text-3xl mb-3" style={{ color: 'var(--color-mine-blue)' }}>⏳</div>
        <p className="text-sm font-medium">{t('step1.uploading', { label })}</p>
        <p className="text-xs mt-1 opacity-70">
          {upload.variables?.file.name ?? ''}
        </p>
        {/* Simple indeterminate progress bar */}
        <div className="w-full max-w-[200px] h-1.5 rounded-full mt-4 overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div className="h-full rounded-full animate-pulse w-2/3" style={{ backgroundColor: 'var(--color-mine-blue)' }} />
        </div>
      </div>{dxfDialog}</>
    );
  }

  // ── Mesh already uploaded — show info ──
  if (meshId && meshInfo) {
    return (
      <><div
        data-slot="mesh-upload-zone"
        className="flex flex-col items-center justify-center rounded-xl border-2 border-solid p-4 min-h-[160px]"
        style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-mine-green)' }}
      >
        {dxfStatus}
        {/* Green check */}
        <ErrorBanner message={uploadError} onDismiss={() => setUploadError(null)} />
        <div className="w-10 h-10 rounded-full flex items-center justify-center mb-3" style={{ backgroundColor: 'var(--status-ok-bg)' }}>
          <span className="text-lg font-bold" style={{ color: 'var(--status-ok-text)' }}>&#10003;</span>
        </div>
        <p className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{label}</p>
        <p className="text-xs mt-1 truncate max-w-[180px]" style={{ color: 'var(--color-text-muted)' }} title={meshInfo.filename}>
          {meshInfo.filename}
        </p>
        {(dxfImportResult ?? meshInfo.import_report) && <DxfImportSummary report={(dxfImportResult ?? meshInfo.import_report)!} />}

        {/* Stats */}
        <div className="flex gap-4 mt-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <span title="Vértices">
            △ {meshInfo.n_vertices.toLocaleString()}
          </span>
          <span title="Caras">
            ◻ {meshInfo.n_faces.toLocaleString()}
          </span>
          {meshInfo.bounds && (
            <span title="Extensión">
              {(meshInfo.bounds.xmax - meshInfo.bounds.xmin).toFixed(0)}×
              {(meshInfo.bounds.ymax - meshInfo.bounds.ymin).toFixed(0)}m
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 mt-4">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="text-xs underline underline-offset-2 focus-visible:outline-none rounded px-2 py-0.5"
            style={{ color: 'var(--color-mine-blue)' }}
          >
            {t('step1.replace')}
          </button>
          <button
            onClick={handleRemove}
            disabled={removeMesh.isPending}
            className="text-xs underline underline-offset-2 focus-visible:outline-none rounded px-2 py-0.5 disabled:opacity-50"
            style={{ color: 'var(--color-mine-red)' }}
          >
            {removeMesh.isPending ? t('step1.removing') : t('common.delete')}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_MIME}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = '';
          }}
        />
      </div>{dxfDialog}</>
    );
  }

  // ── Empty drop zone ──
  return (
    <><div className="flex flex-col">
      <ErrorBanner message={uploadError} onDismiss={() => setUploadError(null)} autoDismissMs={6000} />
      {dxfStatus}
      <div
        data-slot="mesh-upload-zone"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label={t('step1.drop_zone_aria')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click();
        }}
        className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-4 cursor-pointer transition-all min-h-[160px] focus-visible:outline-none"
        style={isDragging
          ? { borderColor: 'var(--color-mine-blue)', backgroundColor: 'var(--color-surface-muted)' }
          : { borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }
        }
      >
      <div className="text-4xl mb-3" style={{ color: borderColor === 'blue' ? 'var(--color-mine-blue)' : 'var(--color-mine-green)' }}>
        {type === 'design' ? t('step1.design_icon') : t('step1.topo_icon')}
      </div>
      <p className="font-medium" style={{ color: isDragging ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>
        {label}
      </p>
      <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
        {t('step1.drop_hint')}
      </p>
      <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
        {t('step1.file_types')}
      </p>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_MIME}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = '';
        }}
      />
      </div>
    </div>{dxfDialog}</>
  );
}

/* ─── Exported internals — used by Step1Content to compose the
   Mission Control "PROTOCOL ALPHA / PROTOCOL OMEGA" cards. ── */

export { DropZone };
export type { DropZoneProps };

/* ─── Main MeshUpload Component ──────────────────────────── */

export function MeshUpload() {
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const setDesignMeshId = useSession((s) => s.setDesignMeshId);
  const setTopoMeshId = useSession((s) => s.setTopoMeshId);
  const { t } = useTranslation();
  const bothUploaded = !!designMeshId && !!topoMeshId;

  return (
    <div data-slot="mesh-upload" className="flex flex-col gap-4">
      {/* Drop zones side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DropZone
          type="design"
          meshId={designMeshId}
          onSetMeshId={setDesignMeshId}
        />
        <DropZone
          type="topo"
          meshId={topoMeshId}
          onSetMeshId={setTopoMeshId}
        />
      </div>

      {/* File size hint */}
      {!bothUploaded && (
        <p className="text-xs text-center" style={{ color: 'var(--color-text-muted)' }}>
          {t('step1.max_size')}
        </p>
      )}

      {/* "Try with sample data" CTA — only visible in the empty state */}
      {!bothUploaded && <TryDemoButton />}
    </div>
  );
}
