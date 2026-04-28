import { useProcess, useProcessStatus } from '../../api/hooks';
import { useSettings } from '../../api/hooks';
import { DEFAULT_SETTINGS } from '../../utils/constants';

export function ProcessButton() {
  const processMutation = useProcess();
  const { data: status } = useProcessStatus();
  const { data: settings } = useSettings();

  const isProcessing = status?.status === 'processing';
  const isComplete = status?.status === 'complete';
  const isError = status?.status === 'error';
  const isPending = processMutation.isPending;

  const handleProcess = () => {
    const processSettings = settings?.process ?? {
      resolution: DEFAULT_SETTINGS.resolution,
      face_threshold: DEFAULT_SETTINGS.face_threshold,
      berm_threshold: DEFAULT_SETTINGS.berm_threshold,
    };

    processMutation.mutate(processSettings);
  };

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Main process button */}
      {!isComplete && !isError && (
        <button
          onClick={handleProcess}
          disabled={isProcessing || isPending}
          className="px-8 py-4 rounded-xl font-semibold text-lg shadow-lg transition-all duration-200 flex items-center gap-3"
          style={isProcessing || isPending
            ? { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)', cursor: 'not-allowed' }
            : { backgroundColor: 'var(--color-mine-blue)', color: '#fff' }
          }
        >
          {(isProcessing || isPending) && (
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {isProcessing || isPending ? 'Procesando...' : '▶ Iniciar Procesamiento'}
        </button>
      )}

      {/* Complete state */}
      {isComplete && (
        <div className="flex flex-col items-center gap-2 px-8 py-4 rounded-xl" style={{ backgroundColor: 'var(--status-ok-bg)', border: '1px solid var(--status-ok-border)' }}>
          <div className="flex items-center gap-2 font-semibold text-lg" style={{ color: 'var(--status-ok-text)' }}>
            <span className="text-2xl">✓</span>
            Procesamiento Completo
          </div>
          <p className="text-sm" style={{ color: 'var(--status-ok-text)', opacity: 0.8 }}>
            {status?.n_results ?? 0} resultados generados
          </p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="flex flex-col items-center gap-3 px-8 py-4 rounded-xl" style={{ backgroundColor: 'var(--status-nok-bg)', border: '1px solid var(--status-nok-border)' }}>
          <div className="font-semibold text-lg" style={{ color: 'var(--status-nok-text)' }}>
            Error en el procesamiento
          </div>
          <p className="text-sm" style={{ color: 'var(--status-nok-text)', opacity: 0.8 }}>
            Hubo un error al procesar las secciones. Intenta nuevamente.
          </p>
          <button
            onClick={handleProcess}
            className="px-6 py-2 text-white rounded-lg font-medium transition-colors"
            style={{ backgroundColor: 'var(--color-mine-red)' }}
          >
            Reintentar
          </button>
        </div>
      )}
    </div>
  );
}
