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
    <div className="flex gap-6 h-full min-h-0">
      {/* Left column — Process controls */}
      <div className="flex-1 flex flex-col items-center justify-center gap-6 shrink-0">
        <div className="text-center">
          <h3 className="text-xl font-bold mb-1" style={{ color: 'var(--color-text-primary)' }}>
            Procesamiento de Secciones
          </h3>
          <p className="text-sm max-w-md" style={{ color: 'var(--color-text-muted)' }}>
            Ejecuta el corte de secciones, extracción de parámetros y comparación
            diseño vs as-built.
          </p>
        </div>

        <ProcessButton />
        <ProcessProgress />

        {/* Navigation */}
        <div className="flex items-center gap-4 mt-2">
          <button
            onClick={prevStep}
            disabled={isProcessing}
            className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ border: '1px solid var(--color-border-strong)', color: 'var(--color-text-secondary)' }}
          >
            ← Anterior
          </button>
          <button
            onClick={nextStep}
            disabled={!isComplete}
            className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ backgroundColor: 'var(--color-mine-blue)', color: '#fff' }}
          >
            Ver Resultados →
          </button>
        </div>
      </div>

      {/* Right column — Settings panel */}
      <div className="w-80 rounded-xl shadow-sm p-5 self-start shrink-0 overflow-auto max-h-full" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <h4 className="font-semibold mb-4 text-sm" style={{ color: 'var(--color-text-primary)' }}>
          Parámetros de Procesamiento
        </h4>

        <div className="space-y-4">
          {/* Resolution */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Resolución (m)
            </label>
            <input
              type="number"
              step={0.1}
              min={0.1}
              value={localSettings.resolution}
              onChange={(e) => handleSettingChange('resolution', parseFloat(e.target.value) || 0.5)}
              disabled={isProcessing}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>

          {/* Face threshold */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Umbral de cara (°)
            </label>
            <input
              type="number"
              step={1}
              min={1}
              value={localSettings.face_threshold}
              onChange={(e) => handleSettingChange('face_threshold', parseFloat(e.target.value) || 40)}
              disabled={isProcessing}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>

          {/* Berm threshold */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Umbral de berma (°)
            </label>
            <input
              type="number"
              step={1}
              min={1}
              value={localSettings.berm_threshold}
              onChange={(e) => handleSettingChange('berm_threshold', parseFloat(e.target.value) || 20)}
              disabled={isProcessing}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
        </div>

        <button
          onClick={handleSaveSettings}
          disabled={isProcessing || updateSettings.isPending}
          className="mt-4 w-full px-4 py-2 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ backgroundColor: 'var(--color-mine-blue)' }}
        >
          {updateSettings.isPending ? 'Guardando...' : 'Guardar Parámetros'}
        </button>
      </div>
    </div>
  );
}
