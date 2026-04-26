import { useCallback, useRef, useState } from 'react';
import { useUploadMesh, useDeleteMesh, useMeshInfo } from '../../api/hooks';
import { useSession } from '../../stores/session';
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

  const label = type === 'design' ? 'Diseño' : 'Topografía';
  const borderColor = type === 'design' ? 'blue' : 'green';

  // Build dynamic class sets based on mesh type
  const idleBorder = borderColor === 'blue'
    ? 'border-blue-300 hover:border-blue-400'
    : 'border-green-300 hover:border-green-400';
  const dragBorder = borderColor === 'blue'
    ? 'border-blue-500 bg-blue-50'
    : 'border-green-500 bg-green-50';
  const accentBg = borderColor === 'blue'
    ? 'bg-blue-50 text-blue-800'
    : 'bg-green-50 text-green-800';
  const iconAccent = borderColor === 'blue' ? 'text-blue-400' : 'text-green-400';
  const ringColor = borderColor === 'blue' ? 'focus-visible:ring-blue-400' : 'focus-visible:ring-green-400';

  const handleFile = useCallback(
    (file: File) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        alert(`Formato no soportado. Use: ${ACCEPTED_EXTENSIONS.join(', ')}`);
        return;
      }
      upload.mutate(
        { file, type },
        {
          onSuccess: (res) => onSetMeshId(res.mesh_id),
          onError: (err) => {
            console.error('Upload failed:', err);
            alert('Error al subir el archivo. Intente nuevamente.');
          },
        },
      );
    },
    [upload, type, onSetMeshId],
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
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 transition-colors ${accentBg} min-h-[220px]`}
      >
        <div className="animate-spin text-3xl mb-3 {iconAccent}">⏳</div>
        <p className="text-sm font-medium">Subiendo {label}…</p>
        <p className="text-xs mt-1 opacity-70">
          {upload.variables?.file.name ?? ''}
        </p>
        {/* Simple indeterminate progress bar */}
        <div className="w-full max-w-[200px] h-1.5 bg-gray-200 rounded-full mt-4 overflow-hidden">
          <div className="h-full bg-mine-blue rounded-full animate-pulse w-2/3" />
        </div>
      </div>
    );
  }

  // ── Mesh already uploaded — show info ──
  if (meshId && meshInfo) {
    return (
      <div
        data-slot="mesh-upload-zone"
        className="flex flex-col items-center justify-center rounded-xl border-2 border-solid p-6 bg-white min-h-[220px]"
      >
        {/* Green check */}
        <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center mb-3">
          <span className="text-green-600 text-lg font-bold">&#10003;</span>
        </div>
        <p className="text-sm font-semibold text-gray-800">{label}</p>
        <p className="text-xs text-gray-500 mt-1 truncate max-w-[180px]" title={meshInfo.filename}>
          {meshInfo.filename}
        </p>

        {/* Stats */}
        <div className="flex gap-4 mt-3 text-xs text-gray-500">
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

        {/* Remove button */}
        <button
          onClick={handleRemove}
          disabled={removeMesh.isPending}
          className={`mt-4 text-xs text-red-500 hover:text-red-700 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 ${ringColor} rounded px-2 py-0.5 disabled:opacity-50`}
        >
          {removeMesh.isPending ? 'Eliminando…' : 'Eliminar'}
        </button>
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
      className={`
        flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6
        cursor-pointer transition-all min-h-[220px]
        focus-visible:outline-none ${ringColor} focus-visible:ring-2
        ${isDragging ? dragBorder : `${idleBorder} bg-white hover:shadow-md`}
      `}
    >
      <div className={`text-4xl mb-3 ${iconAccent}`}>
        {type === 'design' ? '📐' : '🏔️'}
      </div>
      <p className={`font-medium ${isDragging ? '' : 'text-gray-700'}`}>
        {label}
      </p>
      <p className="text-xs text-gray-400 mt-1">
        Arrastre o haga clic para seleccionar
      </p>
      <p className="text-xs text-gray-400 mt-0.5">
        STL / OBJ / PLY / DXF
      </p>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_MIME}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          // Reset so the same file can be re-selected
          e.target.value = '';
        }}
      />
    </div>
  );
}

/* ─── Main MeshUpload Component ──────────────────────────── */

export function MeshUpload() {
  const { designMeshId, topoMeshId, setDesignMeshId, setTopoMeshId, nextStep } = useSession();
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
        <p className="text-xs text-gray-400 text-center">
          Máximo 500 MB por archivo. Los archivos .stl y .xlsx están excluidos del repositorio.
        </p>
      )}
    </div>
  );
}
