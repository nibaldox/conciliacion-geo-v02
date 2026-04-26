import { useState, useCallback, useEffect } from 'react';
import { useClickSection, useSections } from '../../api/hooks';
import type { SectionClickParams } from '../../api/types';

interface SectionClickFormProps {
  /** Register callback so PlanView can invoke it on map click */
  onRegisterClickHandler?: (handler: ((x: number, y: number) => void) | null) => void;
}

export function SectionClickForm({ onRegisterClickHandler }: SectionClickFormProps) {
  const [length, setLength] = useState(200);
  const [sector, setSector] = useState('');
  const [azMode, setAzMode] = useState<'auto' | 'manual'>('auto');
  const [azimuth, setAzimuth] = useState(0);

  const mutation = useClickSection();
  const { data: sections } = useSections();

  const handleMapClick = useCallback(
    (x: number, y: number) => {
      const coords: [number, number] = [x, y];
      const params: SectionClickParams = {
        origin: coords,
        length,
        sector,
        az_mode: azMode,
        ...(azMode === 'manual' ? { azimuth } : {}),
      };

      mutation.mutate(params);
    },
    [length, sector, azMode, azimuth, mutation],
  );

  // Register the click handler so parent components (PlanView) can call it
  useEffect(() => {
    onRegisterClickHandler?.(handleMapClick);
    return () => {
      onRegisterClickHandler?.(null);
    };
  }, [onRegisterClickHandler, handleMapClick]);

  return (
    <div className="space-y-5">
      {/* Instructions */}
      <div className="flex items-center gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <span className="text-2xl">&#x1F4CD;</span>
        <div>
          <p className="text-sm font-medium text-blue-800">
            Haga clic en la vista en planta para agregar secciones
          </p>
          <p className="text-xs text-blue-600 mt-0.5">
            Configure los parámetros abajo y luego haga clic en el mapa.
          </p>
        </div>
      </div>

      {/* Settings */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
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
            Modo Azimuth
          </label>
          <select
            value={azMode}
            onChange={(e) => setAzMode(e.target.value as 'auto' | 'manual')}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-mine-blue focus:ring-1 focus:ring-mine-blue outline-none bg-white"
          >
            <option value="auto">Automático</option>
            <option value="manual">Manual</option>
          </select>
        </div>

        {azMode === 'manual' && (
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Azimuth (°)
            </label>
            <input
              type="number"
              min={0}
              max={360}
              step="any"
              value={azimuth}
              onChange={(e) => setAzimuth(parseFloat(e.target.value) || 0)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-mine-blue focus:ring-1 focus:ring-mine-blue outline-none"
            />
          </div>
        )}
      </div>

      {/* Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-mine-blue text-white text-sm font-bold">
            {sections?.length ?? 0}
          </span>
          <span className="text-sm text-gray-600">
            secciones agregadas
          </span>
        </div>

        {mutation.isPending && (
          <span className="flex items-center gap-2 text-sm text-mine-blue">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-mine-blue/30 border-t-mine-blue rounded-full" />
            Agregando...
          </span>
        )}

        {mutation.isError && (
          <p className="text-sm text-mine-red">
            Error: {mutation.error instanceof Error ? mutation.error.message : 'No se pudo agregar la sección'}
          </p>
        )}
      </div>
    </div>
  );
}
