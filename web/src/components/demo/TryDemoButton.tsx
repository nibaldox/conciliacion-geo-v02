import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { useSession } from '../../stores/session';
import { setDemoProcessStatus, setDemoSectionsCache, setDemoComparisonsCache } from '../../api/hooks';
import { Button } from '../ui/Button';

/**
 * CTA shown in the mesh-upload empty state. Triggers demo mode:
 * loads the precomputed payload and jumps the user straight to the
 * results tab so they can see what the app looks like with data.
 */
export function TryDemoButton() {
  const demoMode = useSession((s) => s.demoMode);
  const demoLoading = useSession((s) => s.demoLoading);
  const loadDemo = useSession((s) => s.loadDemo);
  const qc = useQueryClient();
  const { t } = useTranslation();

  if (demoMode) return null;  // banner is enough — no need for the button

  const handleClick = async () => {
    await loadDemo();
    const { demoData } = useSession.getState();
    if (!demoData) return;
    setDemoProcessStatus(qc, demoData.summary);
    setDemoSectionsCache(qc, demoData);
    setDemoComparisonsCache(qc, demoData);
  };

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
      <Button onClick={handleClick} loading={demoLoading} className="mt-1">
        {demoLoading ? t('common.loading') : t('demo.try_button')}
      </Button>
    </div>
  );
}
