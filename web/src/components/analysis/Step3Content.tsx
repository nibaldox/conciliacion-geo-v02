import { useState } from 'react';
import { ProcessButton } from './ProcessButton';
import { ProcessProgress } from './ProcessProgress';
import { useSession } from '../../stores/session';
import { useProcessStatus, useSettings, useUpdateSettings } from '../../api/hooks';
import { DEFAULT_SETTINGS } from '../../utils/constants';
import type { ProcessSettings } from '../../api/types';

export function Step3Content() {
  const { prevStep, nextStep } = useSession();
  const { data: status } = useProcessStatus();
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();

  const isComplete = status?.status === 'complete';
  const isProcessing = status?.status === 'processing';

  const currentProcess = settings?.process ?? DEFAULT_SETTINGS;

  const [localSettings, setLocalSettings] = useState<ProcessSettings>({
    resolution: currentProcess.resolution,
    face_threshold: currentProcess.face_threshold,
    berm_threshold: currentProcess.berm_threshold,
  });

  const handleSettingChange = <K extends keyof ProcessSettings>(
    key: K,
    value: number,
  ) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveSettings = () => {
    if (!settings) return;
    updateSettings.mutate({
      process: localSettings,
      tolerances: settings.tolerances,
    });
  };

  return (
    <div className="flex gap-6 h-full">
      {/* Left column — Process controls */}
      <div className="flex-1 flex flex-col items-center justify-center gap-8">
        <div className="text-center">
          <h3 className="text-xl font-bold text-gray-800 mb-1">
            Procesamiento de Secciones
          </h3>
          <p className="text-sm text-gray-500 max-w-md">
            Ejecuta el corte de secciones, extracción de parámetros y comparación
            diseño vs as-built.
          </p>
        </div>

        <ProcessButton />
        <ProcessProgress />

        {/* Navigation */}
        <div className="flex items-center gap-4 mt-4">
          <button
            onClick={prevStep}
            disabled={isProcessing}
            className="px-5 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ← Anterior
          </button>
          <button
            onClick={nextStep}
            disabled={!isComplete}
            className="px-5 py-2.5 bg-mine-blue text-white rounded-lg text-sm font-medium hover:bg-blue-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Ver Resultados →
          </button>
        </div>
      </div>

      {/* Right column — Settings panel */}
      <div className="w-80 bg-white rounded-xl border border-gray-200 shadow-sm p-5 self-start">
        <h4 className="font-semibold text-gray-800 mb-4 text-sm">
          Parámetros de Procesamiento
        </h4>

        <div className="space-y-4">
          {/* Resolution */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Resolución (m)
            </label>
            <input
              type="number"
              step={0.1}
              min={0.1}
              value={localSettings.resolution}
              onChange={(e) => handleSettingChange('resolution', parseFloat(e.target.value) || 0.5)}
              disabled={isProcessing}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none disabled:bg-gray-50 disabled:text-gray-400"
            />
          </div>

          {/* Face threshold */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Umbral de cara (°)
            </label>
            <input
              type="number"
              step={1}
              min={1}
              value={localSettings.face_threshold}
              onChange={(e) => handleSettingChange('face_threshold', parseFloat(e.target.value) || 40)}
              disabled={isProcessing}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none disabled:bg-gray-50 disabled:text-gray-400"
            />
          </div>

          {/* Berm threshold */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Umbral de berma (°)
            </label>
            <input
              type="number"
              step={1}
              min={1}
              value={localSettings.berm_threshold}
              onChange={(e) => handleSettingChange('berm_threshold', parseFloat(e.target.value) || 20)}
              disabled={isProcessing}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none disabled:bg-gray-50 disabled:text-gray-400"
            />
          </div>
        </div>

        <button
          onClick={handleSaveSettings}
          disabled={isProcessing || updateSettings.isPending}
          className="mt-4 w-full px-4 py-2 bg-mine-blue text-white text-sm font-medium rounded-lg hover:bg-blue-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {updateSettings.isPending ? 'Guardando...' : 'Guardar Parámetros'}
        </button>
      </div>
    </div>
  );
}
