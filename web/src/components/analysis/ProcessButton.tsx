import { useTranslation } from 'react-i18next';
import { useProcess, useProcessStatus } from '../../api/hooks';
import { useSettings } from '../../api/hooks';
import { DEFAULT_SETTINGS } from '../../utils/constants';
import { Button } from '../ui/Button';

export function ProcessButton() {
  const processMutation = useProcess();
  const { data: status } = useProcessStatus();
  const { data: settings } = useSettings();
  const { t } = useTranslation();

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
        <Button
          onClick={handleProcess}
          loading={isProcessing || isPending}
          disabled={isProcessing || isPending}
          size="lg"
          className="!px-8 !py-4 !text-lg shadow-lg"
        >
          {isProcessing || isPending ? t('step3.running') : t('step3.start_processing')}
        </Button>
      )}

      {/* Complete state */}
      {isComplete && (
        <div className="flex flex-col items-center gap-2 px-8 py-4 rounded-xl" style={{ backgroundColor: 'var(--status-ok-bg)', border: '1px solid var(--status-ok-border)' }}>
          <div className="flex items-center gap-2 font-semibold text-lg" style={{ color: 'var(--status-ok-text)' }}>
            <span className="text-2xl">✓</span>
            {t('step3.complete_title')}
          </div>
          <p className="text-sm" style={{ color: 'var(--status-ok-text)', opacity: 0.8 }}>
            {t('step3.n_results', { count: status?.n_results ?? 0 })}
          </p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="flex flex-col items-center gap-3 px-8 py-4 rounded-xl" style={{ backgroundColor: 'var(--status-nok-bg)', border: '1px solid var(--status-nok-border)' }}>
          <div className="font-semibold text-lg" style={{ color: 'var(--status-nok-text)' }}>
            {t('step3.error_title')}
          </div>
          <p className="text-sm" style={{ color: 'var(--status-nok-text)', opacity: 0.8 }}>
            {t('step3.error_detail')}
          </p>
          <Button variant="danger" onClick={handleProcess}>
            {t('step3.retry')}
          </Button>
        </div>
      )}
    </div>
  );
}
