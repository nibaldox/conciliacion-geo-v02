import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Header } from './Header';
import { LeftSidebar } from './LeftSidebar';
import { DemoBanner } from '../demo/DemoBanner';
import { useSession } from '../../stores/session';

interface AppLayoutProps { children: ReactNode }

export function AppLayout({ children }: AppLayoutProps) {
  const view = useSession((s) => s.activeWorkspaceView);
  const isSpatialView = view === '3d';
  const { t } = useTranslation();
  const titles = { '3d': 'step1.tab_3d', profiles: 'step4.tab_profiles', dashboard: 'step4.tab_dashboard', blast: 'step4.tab_blast', 'export-ai': 'step4.tab_export' };

  return (
    <div data-slot="app-layout" className="flex h-dvh flex-col overflow-hidden bg-surface font-sans text-text-primary">
      <a href="#main-content" className="skip-to-content">{t('workspace.skip')}</a>
      <Header />
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        <LeftSidebar />
        <main id="main-content" tabIndex={-1} className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className={`min-h-0 flex-1 p-3 md:p-6 ${isSpatialView ? 'flex flex-col overflow-hidden' : 'overflow-auto'}`}>
            <div className={`mx-auto flex w-full flex-col gap-4 ${isSpatialView ? 'min-h-0 flex-1' : 'min-h-full max-w-[1800px]'}`}>
              <div data-slot="step-title-bar" className="flex shrink-0 flex-wrap items-center justify-between gap-3">
                <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">{t(titles[view])}</h2>
                <DemoBanner />
              </div>
              <div className="min-h-0 flex-1">{children}</div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
