import { useTranslation } from 'react-i18next';

export type AIHealthState = 'pending' | 'ok' | 'unavailable';

interface AIStatusCardProps {
  healthState: AIHealthState;
}

export function AIStatusCard({ healthState }: AIStatusCardProps) {
  const { t } = useTranslation();
  const healthLabel =
    healthState === 'ok'
      ? t('ai_reporter.health.ok')
      : healthState === 'unavailable'
        ? t('ai_reporter.health.unavailable')
        : t('ai_reporter.health.pending');
  const healthIcon =
    healthState === 'ok' ? '✓' : healthState === 'unavailable' ? '⚠' : '…';

  return (
    <div
      className="rounded-xl shadow-sm p-5"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <h4
          className="text-sm font-semibold"
          style={{ color: 'var(--color-text-primary)' }}
        >
          {t('ai_reporter.title')}
        </h4>
        <span
          className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full"
          style={{
            backgroundColor: 'var(--color-accent-soft)',
            color: 'var(--color-text-muted)',
          }}
        >
          {t('ai_reporter.ready_badge')}
        </span>
      </div>
      <div className="flex items-center gap-3 mt-3">
        <span aria-hidden="true" className="text-base">
          {healthIcon}
        </span>
        <div className="flex-1 min-w-0">
          <div
            className="text-[10px] uppercase tracking-wider mb-0.5"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {t('ai_reporter.backend_status')}
          </div>
          <div
            className="text-xs font-medium"
            style={{ color: 'var(--color-text-primary)' }}
            data-testid="ai-reporter-health"
          >
            {healthLabel}
          </div>
        </div>
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
    <div
      className="rounded-xl shadow-sm p-5"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
      }}
      data-testid={testId}
    >
      <h5
        className="text-sm font-semibold mb-1"
        style={{ color: 'var(--color-text-primary)' }}
      >
        {t(titleKey)}
      </h5>
      <p
        className="text-xs leading-relaxed"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t(descriptionKey)}
      </p>
    </div>
  );
}