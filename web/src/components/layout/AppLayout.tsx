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
import { WizardProgress } from './WizardProgress';
import { Sidebar } from './Sidebar';
import { DemoBanner } from '../demo/DemoBanner';
import { useSession } from '../../stores/session';

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const { currentStep } = useSession();
  const { t } = useTranslation();

  const getStepTitle = () => {
    switch (currentStep) {
      case 1: return t('nav.step1');
      case 2: return t('nav.step2');
      case 3: return t('nav.step3');
      case 4: return t('nav.step4');
      default: return '';
    }
  };

  return (
    <div
      data-slot="app-layout"
      className="h-screen flex flex-col relative overflow-hidden"
      style={{
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text-primary)',
        // Subtle grid background — 1px lines every 32px, very low opacity.
        // Creates the "plotter / engineering" feel without competing
        // with the chart.
        backgroundImage:
          'linear-gradient(var(--color-border) 1px, transparent 1px),' +
          'linear-gradient(90deg, var(--color-border) 1px, transparent 1px)',
        backgroundSize: '32px 32px',
        backgroundPosition: '-1px -1px',
        backgroundAttachment: 'fixed',
      }}
    >
      {/* Subtle gradient overlay so the grid fades toward the edges
       *  and the content area reads as "less pattern, more surface". */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
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
        <WizardProgress />

        <main id="main-content" tabIndex={-1} className="flex-1 overflow-hidden">
          <div className="h-full flex flex-col">
            {/* Step title bar — small, uppercase, tracking, with the
             *  step number badge on the right. Mission Control style. */}
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
                className="text-sm uppercase tracking-wider font-semibold truncate"
                style={{
                  color: 'var(--color-accent-bright)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {t('app.mission_step', {
                  defaultValue: 'MISIÓN {{n}} — {{title}}',
                  n: String(currentStep).padStart(2, '0'),
                  title: getStepTitle(),
                })}
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
              <div className="max-w-7xl mx-auto h-full">
                {children}
              </div>
            </div>
          </div>
        </main>

        {/* Sidebar hidden on mobile — drawers are non-essential on small screens */}
        <div className="hidden md:block">
          <Sidebar />
        </div>
      </div>
    </div>
  );
}
