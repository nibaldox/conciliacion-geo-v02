import { useTranslation } from 'react-i18next';
import { useProcessStatus } from '../../api/hooks';

export function ProcessProgress() {
  const { data: status } = useProcessStatus();
  const { t } = useTranslation();

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
        <p className="text-sm text-center" style={{ color: 'var(--color-text-secondary)' }}>
          {t('step3.processing_section', { current: current ?? '...', total })}
        </p>
      )}

      {isComplete && (
        <p className="text-sm text-center font-medium" style={{ color: 'var(--status-ok-text)' }}>
          {t('step3.complete', { count: status.n_results })}
        </p>
      )}

      {status.status === 'error' && (
        <p className="text-sm text-center font-medium" style={{ color: 'var(--status-nok-text)' }}>
          {t('step3.error')}
        </p>
      )}

      {/* Progress bar */}
      <div className="w-full rounded-full h-3 overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${progressPct}%`,
            backgroundColor: isComplete ? 'var(--color-mine-green)' : isProcessing ? 'var(--color-mine-blue)' : 'var(--color-mine-red)'
          }}
        />
      </div>

      {/* Progress numbers */}
      <div className="flex justify-between text-xs" style={{ color: 'var(--color-text-muted)' }}>
        <span>{t('step3.n_completed', { completed, total })}</span>
        <span>{Math.round(progressPct)}%</span>
      </div>
    </div>
  );
}
