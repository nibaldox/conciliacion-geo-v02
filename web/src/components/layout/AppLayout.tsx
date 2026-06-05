import { useTranslation } from 'react-i18next';
import { Header } from './Header';
import { WizardProgress } from './WizardProgress';
import { Sidebar } from './Sidebar';
import { DemoBanner } from '../demo/DemoBanner';
import { useSession } from '../../stores/session';

interface AppLayoutProps {
  children: React.ReactNode;
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
    <div className="h-screen flex flex-col" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}>
      {/* Skip-to-content for keyboard / screen-reader users */}
      <a href="#main-content" className="skip-to-content">
        Skip to main content
      </a>
      <Header />
      <WizardProgress />

      <main id="main-content" tabIndex={-1} className="flex-1 overflow-hidden">
        <div className="h-full flex flex-col">
          {/* Step title */}
          <div className="px-3 md:px-6 py-3 border-b shrink-0" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
            <div className="max-w-7xl mx-auto">
              <h2 style={{ color: 'var(--color-text-primary)' }} className="text-lg md:text-xl font-semibold truncate">
                {t('app.title')} · {currentStep}/4 · {getStepTitle()}
              </h2>
            </div>
          </div>

          {/* Demo banner — only visible when demo mode is on */}
          <div className="px-3 md:px-6 pt-3 shrink-0 max-w-7xl w-full mx-auto">
            <DemoBanner />
          </div>

          {/* Content area */}
          <div className="flex-1 overflow-auto p-3 md:p-6 min-h-0" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
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
  );
}
