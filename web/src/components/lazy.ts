import { lazy } from 'react';

// Lazy load heavy components to reduce initial bundle

export const LazyContourChart = lazy(() =>
  import('./mesh/ContourChart').then(m => ({ default: m.ContourChart }))
);

export const LazyMesh3DViewer = lazy(() =>
  import('./mesh/Mesh3DViewer').then(m => ({ default: m.Mesh3DViewer }))
);


export const LazyProfileView = lazy(() =>
  import('./results/ProfileView').then(m => ({ default: m.ProfileView }))
);

export const LazyProfilesGrid = lazy(() =>
  import('./results/ProfileView').then(m => ({ default: m.ProfilesGrid }))
);

export const LazyResultsTable = lazy(() =>
  import('./results/ResultsTable').then(m => ({ default: m.ResultsTable }))
);

export const LazyDashboard = lazy(() =>
  import('./results/Dashboard').then(m => ({ default: m.Dashboard }))
);

export const LazyBlastCorrelation = lazy(() =>
  import('./results/BlastCorrelation').then(m => ({ default: m.BlastCorrelation }))
);

export const LazyBenchEditor = lazy(() =>
  import('./analysis/BenchEditor').then(m => ({ default: m.BenchEditor }))
);

export const LazyAIReporter = lazy(() =>
  import('./export/AIReporter').then(m => ({ default: m.AIReporter }))
);
