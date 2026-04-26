import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, useState } from 'react';
import { AppLayout } from './components/layout/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Step1Content } from './components/mesh/Step1Content';
import { SectionWizard } from './components/sections/SectionWizard';
import { Step3Content } from './components/analysis/Step3Content';
import { Step4Content } from './components/results/Step4Content';
import { useSession } from './stores/session';

const STEPS_MAP = {
  1: Step1Content,
  2: SectionWizard,
  3: Step3Content,
  4: Step4Content,
} as const;

function StepsRouter() {
  const { currentStep } = useSession();
  const Component = STEPS_MAP[currentStep as keyof typeof STEPS_MAP];
  return Component ? <Component /> : null;
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-mine-blue" />
    </div>
  );
}

function App() {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  }));

  return (
    <QueryClientProvider client={queryClient}>
      <AppLayout>
        <ErrorBoundary>
          <Suspense fallback={<LoadingSpinner />}>
            <StepsRouter />
          </Suspense>
        </ErrorBoundary>
      </AppLayout>
    </QueryClientProvider>
  );
}

export default App;
