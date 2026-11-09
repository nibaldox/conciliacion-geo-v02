import { useTranslation } from 'react-i18next';
import { useProcess, useProcessStatus } from '../../api/hooks';
import { useSettings } from '../../api/hooks';
import { DEFAULT_SETTINGS } from '../../utils/constants';
import { Button } from '../ui/Button';

function extractMutationErrorReason(error: unknown): string | null {
  if (!error || typeof error !== 'object') return null;
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  if (typeof detail === 'string' && detail.trim() !== '') return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim() !== '') return message;
  }
  return null;
}

export function ProcessButton() {
  const processMutation = useProcess();
  const { data: status } = useProcessStatus();
  const { data: settings } = useSettings();
  const { t } = useTranslation();

  const isProcessing = status?.status === 'processing';
  const isComplete = status?.status === 'complete';
  const isError = status?.status === 'error';
  const isPending = processMutation.isPending;
  const mutationErrorReason = processMutation.isError
    ? (extractMutationErrorReason(processMutation.error) ?? t('step3.error_detail'))
    : null;

  const handleProcess = () => {
    const processSettings = settings?.process ?? {
      resolution: DEFAULT_SETTINGS.resolution,
      face_threshold: DEFAULT_SETTINGS.face_threshold,
      berm_threshold: DEFAULT_SETTINGS.berm_threshold,
    };

    processMutation.mutate(processSettings);
  };

  return (
    <div className="flex w-full flex-col gap-2">
      {/* Main process button */}
      {!isComplete && !isError && (
        <Button
          onClick={handleProcess}
          loading={isProcessing || isPending}
          disabled={isProcessing || isPending}
          size="sm"
          fullWidth
          className="min-h-8"
        >
          {isProcessing || isPending ? t('step3.running') : t('step3.start_processing')}
        </Button>
      )}

      {/* Complete state */}
      {isComplete && (
        <div className="flex flex-col items-center gap-2 w-full">
          <div className="flex flex-col items-center gap-1 p-2 rounded-md w-full" style={{ backgroundColor: 'var(--status-ok-bg)', border: '1px solid var(--status-ok-border)' }}>
            <div className="flex items-center gap-2 font-semibold text-xs" style={{ color: 'var(--status-ok-text)' }}>
              <span className="text-xs">✓</span>
              {t('step3.complete_title')}
            </div>
            <p className="text-xs" style={{ color: 'var(--status-ok-text)', opacity: 0.8 }}>
              {t('step3.n_results', { count: status?.n_results ?? 0 })}
            </p>
          </div>

          <Button
            variant="secondary"
            onClick={handleProcess}
            loading={isPending}
            disabled={isPending}
            size="sm"
            className="w-full min-h-8"
          >
            {t('step3.recalculate', { defaultValue: 'Recalcular Perfiles' })}
          </Button>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="flex flex-col items-center gap-2 p-2 rounded-md w-full" style={{ backgroundColor: 'var(--status-nok-bg)', border: '1px solid var(--status-nok-border)' }}>
          <div className="font-semibold text-xs" style={{ color: 'var(--status-nok-text)' }}>
            {t('step3.error_title')}
          </div>
          <p className="text-xs" style={{ color: 'var(--status-nok-text)', opacity: 0.8 }}>
            {t('step3.error_detail')}
          </p>
          <Button variant="danger" size="sm" fullWidth onClick={handleProcess}>
            {t('step3.retry')}
          </Button>
        </div>
      )}

      {/* Mutation failure (e.g. HTTP 400 detail from the API) */}
      {processMutation.isError && (
        <div className="flex flex-col items-center gap-2 p-2 rounded-md w-full" style={{ backgroundColor: 'var(--status-nok-bg)', border: '1px solid var(--status-nok-border)' }}>
          <div className="font-semibold text-xs" style={{ color: 'var(--status-nok-text)' }}>
            {t('step3.error_title')}
          </div>
          <p className="text-xs" style={{ color: 'var(--status-nok-text)', opacity: 0.8 }}>
            {t('step3.error_reason_label')} {mutationErrorReason}
          </p>
          <Button variant="danger" size="sm" fullWidth onClick={handleProcess} loading={isPending} disabled={isPending}>
            {t('step3.retry')}
          </Button>
        </div>
      )}
    </div>
  );
}
