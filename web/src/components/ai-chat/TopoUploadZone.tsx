import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useCancelDxf,
  useConfirmDxf,
  useInspectDxf,
  useMeshInfo,
  useUploadMesh,
} from '../../api/hooks';
import type {
  DxfInspectResponse,
  MeshType,
  UploadResponse,
} from '../../api/types';
import { useAIChat } from '../../stores/aiChat';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import { DxfImportDialog } from '../mesh/DxfImportDialog';
import { IconMesh } from '../ui/Icons';
import { Spinner } from '../ui/Spinner';

const ACCEPTED_EXTENSIONS = ['.stl', '.obj', '.ply', '.dxf'];
const ACCEPTED_MIME = '.stl,.obj,.ply,.dxf';

function formatBounds(bounds: Record<string, number>): string {
  const span = (min: string, max: string) =>
    `${Number(bounds[min] ?? 0).toFixed(1)}–${Number(bounds[max] ?? 0).toFixed(1)}`;
  return `X ${span('xmin', 'xmax')} · Y ${span('ymin', 'ymax')} · Z ${span('zmin', 'zmax')} m`;
}

function extractDetail(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('response' in error)) {
    return null;
  }
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    .response?.data?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : null;
}

/**
 * Mesh upload zone for the chat panel (plan §4.5 route a).
 *
 * The upload is ALWAYS user-initiated: the model never sends files.
 * Before anything touches the network, an upload that would replace the
 * session's same-role mesh warns inline and requires an explicit
 * confirmation click. The File object lives in a ref for the duration
 * of the in-flight request only — never in React state and never in
 * localStorage — and the file content is never sent to the model.
 */
export function TopoUploadZone() {
  const { t } = useTranslation();
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const setDesignMeshId = useSession((s) => s.setDesignMeshId);
  const setTopoMeshId = useSession((s) => s.setTopoMeshId);
  const addObservation = useAIChat((s) => s.addObservation);

  const [meshType, setMeshType] = useState<MeshType>('topo');
  const [pendingFileName, setPendingFileName] = useState<string | null>(null);
  const [replaceWarn, setReplaceWarn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dxfReport, setDxfReport] = useState<DxfInspectResponse | null>(null);
  const [dxfError, setDxfError] = useState<string | null>(null);
  const fileRef = useRef<File | null>(null);
  const dxfUploadIdRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const upload = useUploadMesh();
  const inspectDxf = useInspectDxf();
  const confirmDxf = useConfirmDxf();
  const cancelDxf = useCancelDxf();

  const currentMeshId = meshType === 'design' ? designMeshId : topoMeshId;
  const hasRealMesh =
    !!currentMeshId &&
    currentMeshId !== DEMO_MESH_IDS.design &&
    currentMeshId !== DEMO_MESH_IDS.topo;
  const { data: existingMeshInfo } = useMeshInfo(
    hasRealMesh ? currentMeshId : null,
  );

  const roleLabel =
    meshType === 'design'
      ? t('aiChat.upload.type_design')
      : t('aiChat.upload.type_topo');

  const clearPendingFile = useCallback(() => {
    fileRef.current = null;
    setPendingFileName(null);
    setReplaceWarn(false);
  }, []);

  const injectObservation = useCallback(
    (result: UploadResponse) => {
      addObservation(
        t('aiChat.observation.mesh_loaded', {
          role: roleLabel,
          meshId: result.mesh_id,
          vertices: result.n_vertices.toLocaleString('es-CL'),
          faces: result.n_faces.toLocaleString('es-CL'),
          bounds: formatBounds(result.bounds),
        }),
      );
    },
    [addObservation, roleLabel, t],
  );

  const proceedUpload = useCallback(
    (file: File) => {
      if (file.name.toLowerCase().endsWith('.dxf')) {
        inspectDxf.mutate(
          { file, type: meshType },
          {
            onSuccess: (report) => {
              dxfUploadIdRef.current = report.upload_id;
              setDxfReport(report);
            },
            onError: (err) => {
              clearPendingFile();
              setError(
                extractDetail(err) ?? t('aiChat.upload.failed'),
              );
            },
          },
        );
        return;
      }
      upload.mutate(
        { file, type: meshType },
        {
          onSuccess: (result) => {
            clearPendingFile();
            if (meshType === 'design') setDesignMeshId(result.mesh_id);
            else setTopoMeshId(result.mesh_id);
            injectObservation(result);
          },
          onError: (err) => {
            clearPendingFile();
            setError(extractDetail(err) ?? t('aiChat.upload.failed'));
          },
        },
      );
    },
    [
      clearPendingFile,
      injectObservation,
      inspectDxf,
      meshType,
      setDesignMeshId,
      setTopoMeshId,
      t,
      upload,
    ],
  );

  const handleFileSelected = useCallback(
    (file: File) => {
      const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        setError(
          t('aiChat.upload.unsupported', {
            formats: ACCEPTED_EXTENSIONS.join(', '),
          }),
        );
        return;
      }
      setError(null);
      setDxfError(null);
      fileRef.current = file;
      setPendingFileName(file.name);
      if (hasRealMesh) {
        setReplaceWarn(true);
        return;
      }
      proceedUpload(file);
    },
    [hasRealMesh, proceedUpload, t],
  );

  const handleReplaceConfirmed = useCallback(() => {
    const file = fileRef.current;
    if (!file) {
      clearPendingFile();
      return;
    }
    proceedUpload(file);
  }, [clearPendingFile, proceedUpload]);

  const handleReplaceCancelled = useCallback(() => {
    clearPendingFile();
  }, [clearPendingFile]);

  const handleDxfConfirm = useCallback(
    (layers: string[], units: number) => {
      if (!dxfReport) return;
      setDxfError(null);
      confirmDxf.mutate(
        { uploadId: dxfReport.upload_id, layers, units },
        {
          onSuccess: (result) => {
            dxfUploadIdRef.current = null;
            setDxfReport(null);
            clearPendingFile();
            if (meshType === 'design') setDesignMeshId(result.mesh_id);
            else setTopoMeshId(result.mesh_id);
            injectObservation(result);
          },
          onError: (err) => {
            setDxfError(extractDetail(err) ?? t('aiChat.upload.failed'));
          },
        },
      );
    },
    [
      clearPendingFile,
      confirmDxf,
      dxfReport,
      injectObservation,
      meshType,
      setDesignMeshId,
      setTopoMeshId,
      t,
    ],
  );

  const handleDxfCancel = useCallback(() => {
    const uploadId = dxfUploadIdRef.current;
    dxfUploadIdRef.current = null;
    setDxfReport(null);
    setDxfError(null);
    if (uploadId) cancelDxf.mutate(uploadId);
    clearPendingFile();
  }, [cancelDxf, clearPendingFile]);

  const busy =
    upload.isPending || inspectDxf.isPending || confirmDxf.isPending;

  return (
    <div data-slot="ai-chat-upload-zone" className="border-t border-border pt-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          data-testid="ai-chat-upload-type-design"
          aria-pressed={meshType === 'design'}
          onClick={() => setMeshType('design')}
          className="rounded px-2 py-0.5 text-xs text-text-secondary aria-[pressed=true]:bg-surface-raised aria-[pressed=true]:text-text-primary"
        >
          {t('aiChat.upload.type_design')}
        </button>
        <button
          type="button"
          data-testid="ai-chat-upload-type-topo"
          aria-pressed={meshType === 'topo'}
          onClick={() => setMeshType('topo')}
          className="rounded px-2 py-0.5 text-xs text-text-secondary aria-[pressed=true]:bg-surface-raised aria-[pressed=true]:text-text-primary"
        >
          {t('aiChat.upload.type_topo')}
        </button>
        <span className="ml-auto text-[11px] text-text-muted">
          {t('aiChat.upload.drop_hint')}
        </span>
      </div>

      {busy ? (
        <div
          role="status"
          className="mt-2 flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm"
        >
          <Spinner size="sm" />
          <span className="truncate text-text-secondary">
            {inspectDxf.isPending
              ? t('aiChat.upload.inspecting')
              : t('aiChat.upload.uploading', { role: roleLabel })}
          </span>
        </div>
      ) : replaceWarn ? (
        <div
          role="alert"
          data-testid="ai-chat-replace-warning"
          className="mt-2 rounded-lg border border-[var(--color-status-warning)] bg-surface px-3 py-2 text-xs"
        >
          <p className="text-text-primary">
            {t('aiChat.upload.replace_warning', {
              role: roleLabel,
              filename: existingMeshInfo?.filename ?? pendingFileName ?? '',
            })}
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              data-testid="ai-chat-replace-confirm"
              onClick={handleReplaceConfirmed}
              className="rounded-md bg-accent px-3 py-1 font-medium text-accent-fg"
            >
              {t('aiChat.upload.replace_confirm')}
            </button>
            <button
              type="button"
              data-testid="ai-chat-replace-cancel"
              onClick={handleReplaceCancelled}
              className="rounded-md border border-border px-3 py-1 text-text-secondary hover:bg-surface-muted"
            >
              {t('aiChat.upload.replace_cancel')}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          data-testid="ai-chat-upload-dropzone"
          aria-label={t('aiChat.upload.select_file', { role: roleLabel })}
          onClick={() => fileInputRef.current?.click()}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFileSelected(file);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          className={`mt-2 flex w-full items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
            isDragging
              ? 'border-accent bg-accent-bg'
              : 'border-border-strong bg-surface hover:bg-surface-muted'
          }`}
        >
          <IconMesh aria-hidden="true" className="h-4 w-4 shrink-0 text-text-secondary" />
          <span className="text-text-secondary">
            {pendingFileName ?? t('aiChat.upload.select_file', { role: roleLabel })}
          </span>
        </button>
      )}

      {error && (
        <p role="alert" className="mt-2 text-xs text-[var(--status-nok-text)]">
          {error}
        </p>
      )}
      {dxfError && (
        <p role="alert" className="mt-2 text-xs text-[var(--status-nok-text)]">
          {dxfError}
        </p>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_MIME}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) handleFileSelected(file);
          event.target.value = '';
        }}
      />

      {dxfReport && (
        <DxfImportDialog
          report={dxfReport}
          type={meshType}
          busy={confirmDxf.isPending}
          error={dxfError}
          onConfirm={handleDxfConfirm}
          onCancel={handleDxfCancel}
        />
      )}
    </div>
  );
}
