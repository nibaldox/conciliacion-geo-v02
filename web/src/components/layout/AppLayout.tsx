import { Header } from './Header';
import { StepNav } from './StepNav';
import { Sidebar } from './Sidebar';
import { DemoBanner } from '../demo/DemoBanner';
import { useSession } from '../../stores/session';

interface AppLayoutProps {
  children: React.ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const { currentStep } = useSession();

  const getStepTitle = () => {
    switch (currentStep) {
      case 1: return 'Cargar Superficies';
      case 2: return 'Definir Secciones';
      case 3: return 'Análisis';
      case 4: return 'Resultados';
      default: return '';
    }
  };

  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}>
      <Header />
      <StepNav />

      <main className="flex-1 overflow-hidden">
        <div className="h-full flex flex-col">
          {/* Step title */}
          <div className="px-6 py-3 border-b shrink-0" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
            <div className="max-w-7xl mx-auto">
              <h2 style={{ color: 'var(--color-text-primary)' }} className="text-xl font-semibold">
                Paso {currentStep}: {getStepTitle()}
              </h2>
            </div>
          </div>

          {/* Demo banner — only visible when demo mode is on */}
          <div className="px-6 pt-3 shrink-0 max-w-7xl w-full mx-auto">
            <DemoBanner />
          </div>

          {/* Content area */}
          <div className="flex-1 overflow-auto p-6 min-h-0" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
            <div className="max-w-7xl mx-auto h-full">
              {children}
            </div>
          </div>
        </div>
      </main>

      <Sidebar />
    </div>
  );
}
