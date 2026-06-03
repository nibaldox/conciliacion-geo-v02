import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUploadMesh, useDeleteMesh, useMeshInfo } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { TryDemoButton } from '../demo/TryDemoButton';
import type { MeshType } from '../../api/types';

/** Accepted file extensions */
const ACCEPTED_EXTENSIONS = ['.stl', '.obj', '.ply', '.dxf'];
const ACCEPTED_MIME = '.stl,.obj,.ply,.dxf';

interface DropZoneProps {
  type: MeshType;
  meshId: string | null;
  onSetMeshId: (id: string | null) => void;
}

/* ─── Individual Drop Zone ───────────────────────────────── */

function DropZone({ type, meshId, onSetMeshId }: DropZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const upload = useUploadMesh();
  const removeMesh = useDeleteMesh();
  const { data: meshInfo } = useMeshInfo(meshId);
  const { t } = useTranslation();

  const label = type === 'design' ? t('step1.design') : t('step1.topo');
  const borderColor = type === 'design' ? 'blue' : 'green';

  const handleFile = useCallback(
    (file: File) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        alert(t('step1.unsupported_format', { formats: ACCEPTED_EXTENSIONS.join(', ') }));
        return;
      }
      upload.mutate(
        { file, type },
        {
          onSuccess: (res) => onSetMeshId(res.mesh_id),
          onError: (err) => {
            console.error('Upload failed:', err);
            alert(t('step1.upload_failed'));
          },
        },
      );
    },
    [upload, type, onSetMeshId, t],
  );

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

  // ── Upload in progress ──
  if (upload.isPending) {
    return (
      <div
        data-slot="mesh-upload-zone"
        className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 transition-colors min-h-[220px]"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="animate-spin text-3xl mb-3" style={{ color: 'var(--color-mine-blue)' }}>⏳</div>
        <p className="text-sm font-medium">{t('step1.uploading', { label })}</p>
        <p className="text-xs mt-1 opacity-70">
          {upload.variables?.file.name ?? ''}
        </p>
        {/* Simple indeterminate progress bar */}
        <div className="w-full max-w-[200px] h-1.5 rounded-full mt-4 overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div className="h-full rounded-full animate-pulse w-2/3" style={{ backgroundColor: 'var(--color-mine-blue)' }} />
        </div>
      </div>
    );
  }

  // ── Mesh already uploaded — show info ──
  if (meshId && meshInfo) {
    return (
      <div
        data-slot="mesh-upload-zone"
        className="flex flex-col items-center justify-center rounded-xl border-2 border-solid p-6 min-h-[220px]"
        style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-mine-green)' }}
      >
        {/* Green check */}
        <div className="w-10 h-10 rounded-full flex items-center justify-center mb-3" style={{ backgroundColor: 'var(--status-ok-bg)' }}>
          <span className="text-lg font-bold" style={{ color: 'var(--status-ok-text)' }}>&#10003;</span>
        </div>
        <p className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{label}</p>
        <p className="text-xs mt-1 truncate max-w-[180px]" style={{ color: 'var(--color-text-muted)' }} title={meshInfo.filename}>
          {meshInfo.filename}
        </p>

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
              {(meshInfo.bounds.max_x - meshInfo.bounds.min_x).toFixed(0)}×
              {(meshInfo.bounds.max_y - meshInfo.bounds.min_y).toFixed(0)}m
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
      </div>
    );
  }

  // ── Empty drop zone ──
  return (
    <div
      data-slot="mesh-upload-zone"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => fileInputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click();
      }}
      className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 cursor-pointer transition-all min-h-[220px] focus-visible:outline-none"
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
  );
}

/* ─── Main MeshUpload Component ──────────────────────────── */

export function MeshUpload() {
  const { designMeshId, topoMeshId, setDesignMeshId, setTopoMeshId } = useSession();
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
