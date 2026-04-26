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
        className={`
          relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all
          ${isDragging ? 'border-mine-blue bg-blue-50' : 'border-gray-300 hover:border-mine-blue/50 hover:bg-gray-50'}
          ${file ? 'border-mine-green bg-green-50/30' : ''}
        `}
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
              <p className="text-sm font-medium text-gray-800">{file.name}</p>
              <p className="text-xs text-gray-500">
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                clearFile();
              }}
              className="ml-4 text-mine-red hover:text-red-700 text-xs font-medium"
            >
              Quitar
            </button>
          </div>
        ) : (
          <div>
            <span className="text-3xl mb-3 block">&#128228;</span>
            <p className="text-sm font-medium text-gray-700">
              Arrastra un archivo aquí o haz clic para seleccionar
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Formatos: CSV, TXT, DXF
            </p>
          </div>
        )}
      </div>

      {/* Settings */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Espaciamiento (m)
          </label>
          <input
            type="number"
            min={1}
            step="any"
            value={spacing}
            onChange={(e) => setSpacing(parseFloat(e.target.value) || 20)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-mine-blue focus:ring-1 focus:ring-mine-blue outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Longitud (m)
          </label>
          <input
            type="number"
            min={1}
            step="any"
            value={length}
            onChange={(e) => setLength(parseFloat(e.target.value) || 200)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-mine-blue focus:ring-1 focus:ring-mine-blue outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Sector
          </label>
          <input
            type="text"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-mine-blue focus:ring-1 focus:ring-mine-blue outline-none"
            placeholder="Ej: Norte"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Método de Azimuth
          </label>
          <select
            value={azMode}
            onChange={(e) => setAzMode(e.target.value as AzMode)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-mine-blue focus:ring-1 focus:ring-mine-blue outline-none bg-white"
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
          className="px-5 py-2.5 bg-mine-blue text-white rounded-lg font-medium text-sm shadow-sm hover:bg-blue-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
          <p className="text-sm text-mine-red">
            Error: {mutation.error instanceof Error ? mutation.error.message : 'No se pudieron generar las secciones'}
          </p>
        )}

        {mutation.isSuccess && (
          <p className="text-sm text-mine-green font-medium">
            Secciones generadas desde archivo correctamente
          </p>
        )}
      </div>
    </form>
  );
}
