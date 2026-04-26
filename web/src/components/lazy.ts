import { lazy } from 'react';

// Lazy load heavy components to reduce initial bundle

export const LazyPlanView = lazy(() =>
  import('./mesh/PlanView').then(m => ({ default: m.PlanView }))
);

export const LazyMesh3DViewer = lazy(() =>
  import('./mesh/Mesh3DViewer').then(m => ({ default: m.Mesh3DViewer }))
);

export const LazyProfileChart = lazy(() =>
  import('./results/ProfileChart').then(m => ({ default: m.ProfileChart }))
);

export const LazyResultsTable = lazy(() =>
  import('./results/ResultsTable').then(m => ({ default: m.ResultsTable }))
);

export const LazyDashboard = lazy(() =>
  import('./results/Dashboard').then(m => ({ default: m.Dashboard }))
);

export const LazyBenchEditor = lazy(() =>
  import('./analysis/BenchEditor').then(m => ({ default: m.BenchEditor }))
);

export const LazyAIReporter = lazy(() =>
  import('./export/AIReporter').then(m => ({ default: m.AIReporter }))
);
