import { useState, useRef } from 'react';
import { useFileSections } from '../../api/hooks';

type AzMode = 'perpendicular' | 'local_slope';

const ACCEPTED_EXTENSIONS = ['.csv', '.txt', '.dxf'];

export function SectionFileUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [spacing, setSpacing] = useState(20);
  const [length, setLength] = useState(200);
  const [sector, setSector] = useState('');
  const [azMode, setAzMode] = useState<AzMode>('perpendicular');
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useFileSections();

  const isValidFile = (f: File): boolean => {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase();
    return ACCEPTED_EXTENSIONS.includes(ext);
  };

  const handleFileSelect = (f: File) => {
    if (isValidFile(f)) {
      setFile(f);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) handleFileSelect(selected);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    mutation.mutate({ file, spacing, length, sector, az_mode: azMode });
  };

  const clearFile = () => {
    setFile(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        className="relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all"
        style={isDragging
          ? { borderColor: 'var(--color-mine-blue)', backgroundColor: 'var(--color-surface-muted)' }
          : file
            ? { borderColor: 'var(--color-mine-green)', backgroundColor: 'var(--status-ok-bg)' }
            : { borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }
        }
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.txt,.dxf"
          onChange={handleInputChange}
          className="hidden"
        />

        {file ? (
          <div className="flex items-center justify-center gap-3">
            <span className="text-2xl">&#128196;</span>
            <div className="text-left">
              <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{file.name}</p>
              <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                clearFile();
              }}
              className="ml-4 text-xs font-medium"
              style={{ color: 'var(--color-mine-red)' }}
            >
              Quitar
            </button>
          </div>
        ) : (
          <div>
            <span className="text-3xl mb-3 block">&#128228;</span>
            <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              Arrastra un archivo aquí o haz clic para seleccionar
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
              Formatos: CSV, TXT, DXF
            </p>
          </div>
        )}
      </div>

      {/* Settings */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            Espaciamiento (m)
          </label>
          <input
            type="number"
            min={1}
            step="any"
            value={spacing}
            onChange={(e) => setSpacing(parseFloat(e.target.value) || 20)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            Longitud (m)
          </label>
          <input
            type="number"
            min={1}
            step="any"
            value={length}
            onChange={(e) => setLength(parseFloat(e.target.value) || 200)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            Sector
          </label>
          <input
            type="text"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            placeholder="Ej: Norte"
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            Método de Azimuth
          </label>
          <select
            value={azMode}
            onChange={(e) => setAzMode(e.target.value as AzMode)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          >
            <option value="perpendicular">Perpendicular a la cresta</option>
            <option value="local_slope">Pendiente local del diseño</option>
          </select>
        </div>
      </div>

      {/* Submit */}
      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={!file || mutation.isPending}
          className="px-5 py-2.5 text-white rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ backgroundColor: 'var(--color-mine-blue)' }}
        >
          {mutation.isPending ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
              Procesando...
            </span>
          ) : (
            'Generar desde Archivo'
          )}
        </button>

        {mutation.isError && (
          <p className="text-sm" style={{ color: 'var(--color-mine-red)' }}>
            Error: {mutation.error instanceof Error ? mutation.error.message : 'No se pudieron generar las secciones'}
          </p>
        )}

        {mutation.isSuccess && (
          <p className="text-sm font-medium" style={{ color: 'var(--color-mine-green)' }}>
            Secciones generadas desde archivo correctamente
          </p>
        )}
      </div>
    </form>
  );
}
