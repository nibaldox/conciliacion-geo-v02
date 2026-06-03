import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';

/**
 * CTA shown in the mesh-upload empty state. Triggers demo mode:
 * loads the precomputed payload and jumps the user straight to the
 * results tab so they can see what the app looks like with data.
 */
export function TryDemoButton() {
  const { demoMode, demoLoading, loadDemo } = useSession();
  const { t } = useTranslation();

  if (demoMode) return null;  // banner is enough — no need for the button

  return (
    <div
      data-slot="try-demo"
      className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-5 mt-1"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      <div className="text-2xl">🎮</div>
      <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
        {t('demo.try_title')}
      </p>
      <p className="text-xs text-center" style={{ color: 'var(--color-text-muted)' }}>
        {t('demo.try_subtitle')}
      </p>
      <button
        onClick={loadDemo}
        disabled={demoLoading}
        className="mt-1 px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue"
        style={{
          backgroundColor: 'var(--color-mine-blue)',
          color: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        {demoLoading ? `⏳ ${t('common.loading')}` : t('demo.try_button')}
      </button>
    </div>
  );
}
