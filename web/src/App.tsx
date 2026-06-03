import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, lazy, useState, useEffect } from 'react';
import { AppLayout } from './components/layout/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useSession } from './stores/session';
import { useTheme } from './stores/theme';

// All four step components are lazy-loaded. The wizard's "current step"
// state lives in zustand, so navigating between steps just swaps which
// chunk React loads. This keeps the initial bundle (Step 1 only) as
// small as possible — the bulk of the app's JS is in steps 2-4 and
// only fetches when the user actually navigates there.
const LazyStep1 = lazy(() => import('./components/mesh/Step1Content').then(m => ({ default: m.Step1Content })));
const LazyStep2 = lazy(() => import('./components/sections/SectionWizard').then(m => ({ default: m.SectionWizard })));
const LazyStep3 = lazy(() => import('./components/analysis/Step3Content').then(m => ({ default: m.Step3Content })));
const LazyStep4 = lazy(() => import('./components/results/Step4Content').then(m => ({ default: m.Step4Content })));

const STEPS_MAP = {
  1: LazyStep1,
  2: LazyStep2,
  3: LazyStep3,
  4: LazyStep4,
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

  const { isDark } = useTheme();

  // Apply dark class to root element
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

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
