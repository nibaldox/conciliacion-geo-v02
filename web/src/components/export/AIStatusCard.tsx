import { useTranslation } from 'react-i18next';

export type AIHealthState = 'pending' | 'ok' | 'unavailable';

interface AIStatusCardProps {
  healthState: AIHealthState;
}

const HEALTH_DOT: Record<AIHealthState, string> = {
  ok: 'var(--status-ok-text)',
  unavailable: 'var(--status-nok-text)',
  pending: 'var(--color-text-muted)',
};

export function AIStatusCard({ healthState }: AIStatusCardProps) {
  const { t } = useTranslation();
  const healthLabel =
    healthState === 'ok'
      ? t('ai_reporter.health.ok')
      : healthState === 'unavailable'
        ? t('ai_reporter.health.unavailable')
        : t('ai_reporter.health.pending');

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
      <h3 className="ui-section-title">{t('ai_reporter.title')}</h3>
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <span className="sr-only">{t('ai_reporter.backend_status')}</span>
        <span
          aria-hidden="true"
          data-health={healthState}
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: HEALTH_DOT[healthState] }}
        />
        <span data-testid="ai-reporter-health" className="text-text-secondary">
          {healthLabel}
        </span>
      </div>
    </div>
  );
}

interface AIUnavailableCardProps {
  testId: string;
  titleKey: string;
  descriptionKey: string;
}

export function AIInfoCard({ testId, titleKey, descriptionKey }: AIUnavailableCardProps) {
  const { t } = useTranslation();
  return (
    <div data-testid={testId} className="flex flex-col gap-1">
      <p className="text-sm font-medium text-text-primary">{t(titleKey)}</p>
      <p className="text-xs leading-relaxed text-text-muted">{t(descriptionKey)}</p>
    </div>
  );
}
