import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';

/**
 * Banner shown at the top of the wizard when demo mode is active.
 *
 * In demo mode the entire UI is driven by precomputed synthetic data
 * loaded from /demo/precomputed.json — no API calls, no mesh upload.
 * The user can exit demo mode at any time to switch to the real flow.
 */
export function DemoBanner() {
  const { demoMode, demoLoading, demoError, exitDemo, demoData } = useSession();
  const { t } = useTranslation();

  if (!demoMode && !demoLoading && !demoError) return null;

  // ── Error state ──
  if (demoError) {
    return (
      <div
        data-slot="demo-banner"
        className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border-2 mb-3"
        style={{ backgroundColor: 'var(--status-nok-bg)', borderColor: 'var(--status-nok-border)', color: 'var(--status-nok-text)' }}
      >
        <div className="flex items-center gap-2 text-sm">
          <span>⚠️</span>
          <span>
            {t('demo.banner_error', { error: demoError })}
          </span>
        </div>
        <button
          onClick={exitDemo}
          className="text-xs underline underline-offset-2"
        >
          {t('common.close')}
        </button>
      </div>
    );
  }

  // ── Loading state ──
  if (demoLoading) {
    return (
      <div
        data-slot="demo-banner"
        className="flex items-center gap-3 px-4 py-2.5 rounded-lg border-2 mb-3 animate-pulse"
        style={{ backgroundColor: 'var(--color-surface-muted)', borderColor: 'var(--color-border)' }}
      >
        <div className="animate-spin text-base">⏳</div>
        <span className="text-sm">{t('demo.banner_loading')}</span>
      </div>
    );
  }

  // ── Active state ──
  const nS = demoData?.summary.n_sections ?? 0;
  const nC = demoData?.summary.n_comparisons ?? 0;
  return (
    <div
      data-slot="demo-banner"
      className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border-2 mb-3"
      style={{
        backgroundColor: 'var(--status-extra-bg)',
        borderColor: 'var(--status-extra-border)',
        color: 'var(--status-extra-text)',
      }}
    >
      <div className="flex items-center gap-3 text-sm">
        <span className="text-base">🎮</span>
        <div>
          <span className="font-semibold">{t('demo.banner_active')}</span>
          <span className="ml-2 opacity-80">
            {t('demo.banner_active_detail', {
              n_sections: t('common.n_sections', { count: nS }),
              n_comparisons: t('common.n_comparisons', { count: nC }),
            })}
          </span>
        </div>
      </div>
      <button
        onClick={exitDemo}
        className="shrink-0 px-3 py-1.5 rounded-md text-xs font-medium border"
        style={{
          backgroundColor: 'var(--color-surface)',
          borderColor: 'var(--color-border-strong)',
          color: 'var(--color-text-primary)',
        }}
      >
        {t('demo.exit')}
      </button>
    </div>
  );
}
