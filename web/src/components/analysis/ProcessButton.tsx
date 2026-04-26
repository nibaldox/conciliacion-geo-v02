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
          className={`
            px-8 py-4 rounded-xl font-semibold text-lg shadow-lg
            transition-all duration-200 flex items-center gap-3
            ${(isProcessing || isPending)
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-mine-blue text-white hover:bg-blue-800 hover:shadow-xl active:scale-[0.98]'
            }
          `}
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
        <div className="flex flex-col items-center gap-2 px-8 py-4 bg-green-50 rounded-xl border border-green-200">
          <div className="flex items-center gap-2 text-green-700 font-semibold text-lg">
            <span className="text-2xl">✓</span>
            Procesamiento Completo
          </div>
          <p className="text-sm text-green-600">
            {status?.n_results ?? 0} resultados generados
          </p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="flex flex-col items-center gap-3 px-8 py-4 bg-red-50 rounded-xl border border-red-200">
          <div className="text-red-700 font-semibold text-lg">
            Error en el procesamiento
          </div>
          <p className="text-sm text-red-600">
            Hubo un error al procesar las secciones. Intenta nuevamente.
          </p>
          <button
            onClick={handleProcess}
            className="px-6 py-2 bg-mine-red text-white rounded-lg font-medium hover:bg-red-700 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}
    </div>
  );
}
