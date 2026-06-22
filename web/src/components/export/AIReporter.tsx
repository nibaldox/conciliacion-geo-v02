import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

type HealthState = 'pending' | 'ok' | 'unavailable';

const HEALTH_ENDPOINT = '/api/v1/ai/health';

export function AIReporter() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<HealthState>('pending');

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(HEALTH_ENDPOINT);
        if (cancelled) return;
        if (res.ok) {
          setHealth('ok');
        } else {
          setHealth('unavailable');
        }
      } catch {
        if (!cancelled) {
          setHealth('unavailable');
        }
      }
    };
    void check();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      data-slot="ai-reporter-stub"
      className="space-y-5"
    >
      <div
        className="rounded-xl shadow-sm p-5"
        style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex items-center justify-between gap-3 mb-2">
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
            Stub
          </span>
        </div>
        <p
          className="text-xs leading-relaxed"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('ai_reporter.pending')}
        </p>
      </div>

      <div
        className="rounded-xl shadow-sm p-5"
        style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <h5
          className="text-xs font-semibold uppercase tracking-wider mb-2"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('ai_reporter.how_it_works')}
        </h5>
        <ul
          className="text-xs space-y-1.5 list-disc pl-5"
          style={{ color: 'var(--color-text-muted)' }}
        >
          <li>{t('ai_reporter.feature_sanitization')}</li>
          <li>{t('ai_reporter.feature_streaming')}</li>
          <li>{t('ai_reporter.feature_structured')}</li>
          <li>{t('ai_reporter.feature_tokens')}</li>
        </ul>
      </div>

      <div
        className="rounded-xl shadow-sm p-4 flex items-center gap-3"
        style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <span aria-hidden="true" className="text-base">
          {health === 'ok' ? '✓' : health === 'unavailable' ? '⚠' : '…'}
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
            {health === 'ok' && t('ai_reporter.health_ok')}
            {health === 'unavailable' && t('ai_reporter.health_unavailable')}
            {health === 'pending' && t('ai_reporter.health_pending')}
          </div>
        </div>
      </div>
    </div>
  );
}
