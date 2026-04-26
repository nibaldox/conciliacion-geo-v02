import { useProcessStatus } from '../../api/hooks';

export function ProcessProgress() {
  const { data: status } = useProcessStatus();

  if (!status || status.status === 'idle') return null;

  const isProcessing = status.status === 'processing';
  const isComplete = status.status === 'complete';
  const total = status.total_sections ?? 0;
  const completed = status.completed_sections ?? 0;
  const current = status.current_section;
  const progressPct = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="w-full max-w-xl space-y-3">
      {/* Progress text */}
      {isProcessing && (
        <p className="text-sm text-gray-600 text-center">
          Procesando sección <span className="font-semibold">{current ?? '...'}</span> de{' '}
          <span className="font-semibold">{total}</span>...
        </p>
      )}

      {isComplete && (
        <p className="text-sm text-green-600 text-center font-medium">
          ✓ Procesamiento completado — {status.n_results} resultados generados
        </p>
      )}

      {status.status === 'error' && (
        <p className="text-sm text-red-600 text-center font-medium">
          Error durante el procesamiento
        </p>
      )}

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
        <div
          className={`
            h-full rounded-full transition-all duration-500 ease-out
            ${isComplete ? 'bg-mine-green' : isProcessing ? 'bg-mine-blue' : 'bg-mine-red'}
          `}
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Progress numbers */}
      <div className="flex justify-between text-xs text-gray-400">
        <span>{completed} / {total} secciones</span>
        <span>{Math.round(progressPct)}%</span>
      </div>
    </div>
  );
}
