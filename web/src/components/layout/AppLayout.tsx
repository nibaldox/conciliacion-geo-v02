/**
 * AppLayout — the shell.
 *
 * Mission Control layout:
 *  - Dark surface (--color-surface) as base
 *  - Subtle grid background pattern (1px lines every 32px, very
 *    subtle) for that "plotter" feel
 *  - Header at top with brand + actions
 *  - WizardProgress below (the numbered step indicator with
 *    connecting lines)
 *  - Step title bar (small, uppercase tracking)
 *  - Demo banner (when in demo mode)
 *  - Main content (children)
 *  - Sidebar as a right-side drawer (hidden on mobile)
 */

import { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Header } from './Header';
import { LeftSidebar } from './LeftSidebar';
import { ViewsToolbar } from './ViewsToolbar';
import { DemoBanner } from '../demo/DemoBanner';
import { useSession } from '../../stores/session';

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const { activeWorkspaceView } = useSession();
  const { t } = useTranslation();

  const getViewTitle = () => {
    switch (activeWorkspaceView) {
      case '3d':
        return t('step1.tab_3d', { defaultValue: 'Visualizador 3D' });
      case 'profiles':
        return t('step4.tab_profiles', { defaultValue: 'Perfiles de Sección' });
      case 'dashboard':
        return t('step4.tab_dashboard', { defaultValue: 'Dashboard de Resultados' });
      case 'blast':
        return t('step4.tab_blast', { defaultValue: 'Correlación de Tronadura' });
      case 'export-ai':
        return t('step4.tab_export', { defaultValue: 'Exportación y Reportes IA' });
      default:
        return '';
    }
  };

  return (
    <div
      data-slot="app-layout"
      className="h-screen flex flex-col relative overflow-hidden font-sans"
      style={{
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text-primary)',
        backgroundImage: activeWorkspaceView === '3d'
          ? 'linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)'
          : 'none',
        backgroundSize: '32px 32px',
        backgroundPosition: '-1px -1px',
        backgroundAttachment: 'fixed',
      }}
    >
      {/* Subtle gradient overlay */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none z-0"
        style={{
          background:
            'radial-gradient(ellipse at center, transparent 0%, var(--color-surface) 90%)',
        }}
      />

      <div className="relative z-10 h-screen flex flex-col">
        {/* Skip-to-content for keyboard / screen-reader users */}
        <a href="#main-content" className="skip-to-content">
          Skip to main content
        </a>
        <Header />

        <div className="flex-1 flex overflow-hidden relative min-h-0">
          <LeftSidebar />

          <main id="main-content" tabIndex={-1} className="flex-1 flex flex-col overflow-hidden min-w-0">
            {/* View title bar */}
            <div
              data-slot="step-title-bar"
              className="px-3 md:px-6 py-2 shrink-0 flex items-center gap-3"
              style={{
                backgroundColor: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-border)',
              }}
            >
              <span
                className="text-[10px] uppercase tracking-widest font-semibold"
                style={{
                  color: 'var(--color-text-muted)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {t('app.mission', { defaultValue: 'CONCILIACIÓN GEOTÉCNICA' })}
              </span>
              <span
                className="text-[10px] uppercase tracking-widest"
                style={{
                  color: 'var(--color-text-dim)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                /
              </span>
              <h2
                className="text-xs uppercase tracking-wider font-semibold truncate"
                style={{
                  color: 'var(--color-accent-bright)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {getViewTitle()}
              </h2>
            </div>

            {/* Demo banner — only visible when demo mode is on */}
            <div className="px-3 md:px-6 pt-3 shrink-0 max-w-7xl w-full mx-auto">
              <DemoBanner />
            </div>

            {/* Content area */}
            <div
              className="flex-1 overflow-auto p-3 md:p-6 min-h-0"
              style={{ backgroundColor: 'transparent' }}
            >
              <div className="h-full w-full">
                {children}
              </div>
            </div>
          </main>

          <ViewsToolbar />
        </div>
      </div>
    </div>
  );
}
