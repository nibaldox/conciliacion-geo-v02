import { Header } from './Header';
import { StepNav } from './StepNav';
import { Sidebar } from './Sidebar';
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
    <div className="h-screen flex flex-col bg-gray-50">
      <Header />
      <StepNav />
      
      <main className="flex-1 overflow-hidden">
        <div className="h-full flex flex-col">
          {/* Step title */}
          <div className="px-6 py-3 bg-white border-b border-gray-100">
            <h2 className="text-xl font-semibold text-gray-800">
              Paso {currentStep}: {getStepTitle()}
            </h2>
          </div>
          
          {/* Content area */}
          <div className="flex-1 overflow-auto p-6">
            {children}
          </div>
        </div>
      </main>
      
      <Sidebar />
    </div>
  );
}
