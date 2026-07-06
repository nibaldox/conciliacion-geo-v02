import { lazy } from 'react';

// Lazy load heavy components to reduce initial bundle

export const LazyContourChart = lazy(() =>
  import('./mesh/ContourChart').then(m => ({ default: m.ContourChart }))
);

export const LazyMesh3DViewer = lazy(() =>
  import('./mesh/Mesh3DViewer').then(m => ({ default: m.Mesh3DViewer }))
);


// Note: the old LazyProfileChart is gone. ProfileView (the new
// orchestrator) is loaded eagerly because Plotly is its biggest
// dependency and is already in the Plotly vendor chunk. The
// ProfileView itself dynamically imports Plotly on first render.

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
