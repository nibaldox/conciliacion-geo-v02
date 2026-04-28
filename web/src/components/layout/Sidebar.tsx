import { useState, useEffect } from 'react';
import { useSettings, useUpdateSettings } from '../../api/hooks';
import type { ProcessSettings } from '../../api/types';
import { DEFAULT_SETTINGS } from '../../utils/constants';

const inputCls = "w-full px-3 py-2 border rounded-lg text-sm outline-none transition-colors focus:ring-2 focus:ring-mine-blue/30";

export function Sidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const { data: settings, isLoading, isError } = useSettings();
  const updateSettings = useUpdateSettings();

  const [processSettings, setProcessSettings] = useState<ProcessSettings>({
    resolution: DEFAULT_SETTINGS.resolution,
    face_threshold: DEFAULT_SETTINGS.face_threshold,
    berm_threshold: DEFAULT_SETTINGS.berm_threshold,
  });

  useEffect(() => {
    if (settings?.process) {
      setProcessSettings(settings.process);
    }
  }, [settings]);

  const handleSave = () => {
    if (!settings) return;
    updateSettings.mutate({
      process: processSettings,
      tolerances: settings.tolerances,
    });
  };

  const handleProcessChange = <K extends keyof ProcessSettings>(key: K, value: number) => {
    setProcessSettings((prev) => ({ ...prev, [key]: value }));
  };

  const inputStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-surface)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-text-primary)',
  };

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed right-0 top-1/2 -translate-y-1/2 z-40 text-white px-2 py-4 rounded-l-lg shadow-lg transition-colors"
        style={{ backgroundColor: 'var(--color-mine-blue)' }}
        title="Configuración"
      >
        ⚙
      </button>

      {/* Sidebar panel */}
      {isOpen && (
        <div
          className="fixed right-0 top-0 h-full w-80 z-50 overflow-y-auto border-l"
          style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
        >
          <div
            className="flex items-center justify-between p-4 border-b"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <h2 className="font-bold" style={{ color: 'var(--color-text-primary)' }}>Configuración</h2>
            <button
              onClick={() => setIsOpen(false)}
              className="text-xl transition-colors"
              style={{ color: 'var(--color-text-muted)' }}
            >
              ✕
            </button>
          </div>

          {isLoading && (
            <div className="p-4">
              <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                Conectando con la API...
              </p>
            </div>
          )}

          {isError && !isLoading && (
            <div className="p-4">
              <p className="text-sm" style={{ color: '#ef4444' }}>
                No se pudo conectar con la API.
              </p>
            </div>
          )}

          {settings && !isLoading && (
            <div className="p-4 space-y-5">
              {/* Process parameters */}
              <section>
                <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                  Parámetros de Procesamiento
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Resolución (m)
                    </label>
                    <input
                      type="number"
                      step={0.1}
                      min={0.1}
                      value={processSettings.resolution}
                      onChange={(e) => handleProcessChange('resolution', parseFloat(e.target.value) || 0.5)}
                      className={inputCls}
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Umbral de cara (°)
                    </label>
                    <input
                      type="number"
                      step={1}
                      min={1}
                      max={90}
                      value={processSettings.face_threshold}
                      onChange={(e) => handleProcessChange('face_threshold', parseFloat(e.target.value) || 40)}
                      className={inputCls}
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Umbral de berma (°)
                    </label>
                    <input
                      type="number"
                      step={1}
                      min={1}
                      max={90}
                      value={processSettings.berm_threshold}
                      onChange={(e) => handleProcessChange('berm_threshold', parseFloat(e.target.value) || 20)}
                      className={inputCls}
                      style={inputStyle}
                    />
                  </div>
                </div>
              </section>

              {/* Tolerances */}
              <section>
                <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                  Tolerancias de Aceptabilidad
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>Altura de banco (m)</p>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        step={0.1}
                        placeholder="−"
                        value={settings.tolerances.bench_height.neg}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, bench_height: { ...settings.tolerances.bench_height, neg: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                      <input
                        type="number"
                        step={0.1}
                        placeholder="+"
                        value={settings.tolerances.bench_height.pos}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, bench_height: { ...settings.tolerances.bench_height, pos: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                    </div>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>Neg (−) / Pos (+)</p>
                  </div>

                  <div>
                    <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>Ángulo de cara (°)</p>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        step={0.5}
                        placeholder="−"
                        value={settings.tolerances.face_angle.neg}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, face_angle: { ...settings.tolerances.face_angle, neg: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                      <input
                        type="number"
                        step={0.5}
                        placeholder="+"
                        value={settings.tolerances.face_angle.pos}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, face_angle: { ...settings.tolerances.face_angle, pos: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Ancho mínimo de berma (m)
                    </label>
                    <input
                      type="number"
                      step={0.5}
                      min={0}
                      value={settings.tolerances.berm_width.min}
                      onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        if (!isNaN(val)) updateSettings.mutate({
                          process: processSettings,
                          tolerances: { ...settings.tolerances, berm_width: { min: val } },
                        });
                      }}
                      className={inputCls}
                      style={inputStyle}
                    />
                  </div>

                  <div>
                    <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>Ángulo inter-rampa (°)</p>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        step={0.5}
                        placeholder="−"
                        value={settings.tolerances.inter_ramp_angle.neg}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, inter_ramp_angle: { ...settings.tolerances.inter_ramp_angle, neg: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                      <input
                        type="number"
                        step={0.5}
                        placeholder="+"
                        value={settings.tolerances.inter_ramp_angle.pos}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, inter_ramp_angle: { ...settings.tolerances.inter_ramp_angle, pos: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>Ángulo global (°)</p>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        step={0.5}
                        placeholder="−"
                        value={settings.tolerances.overall_angle.neg}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, overall_angle: { ...settings.tolerances.overall_angle, neg: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                      <input
                        type="number"
                        step={0.5}
                        placeholder="+"
                        value={settings.tolerances.overall_angle.pos}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) updateSettings.mutate({
                            process: processSettings,
                            tolerances: { ...settings.tolerances, overall_angle: { ...settings.tolerances.overall_angle, pos: val } },
                          });
                        }}
                        className={inputCls}
                        style={inputStyle}
                      />
                    </div>
                  </div>
                </div>
              </section>

              {/* Save button */}
              <button
                onClick={handleSave}
                disabled={updateSettings.isPending}
                className="w-full px-4 py-2 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                style={{ backgroundColor: 'var(--color-mine-blue)' }}
              >
                {updateSettings.isPending ? 'Guardando...' : 'Guardar Cambios'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40"
          style={{ backgroundColor: 'rgba(0,0,0,0.3)' }}
          onClick={() => setIsOpen(false)}
        />
      )}
    </>
  );
}