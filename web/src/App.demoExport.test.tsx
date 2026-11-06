import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import i18n from 'i18next';

vi.mock('./components/layout/AppLayout', () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('./hooks/useHotkeys', () => ({ useHotkeys: () => undefined }));
vi.mock('./api/hooks', () => ({
  useSections: () => ({ data: [{ id: 'section-1' }] }),
  useProcessStatus: () => ({ data: { status: 'complete' } }),
}));
vi.mock('./components/lazy', () => ({
  LazyMesh3DViewer: () => <div data-testid="mesh-viewer" />,
  LazyResultsTable: () => <div data-testid="results-table" />,
  LazyDashboard: () => <div data-testid="dashboard" />,
  LazyBlastCorrelation: () => <div data-testid="blast" />,
  LazyAIReporter: () => <div data-testid="ai-reporter" />,
  LazyProfileView: () => <div data-testid="profile" />,
  LazyProfilesGrid: () => <div data-testid="profiles-grid" />,
}));
vi.mock('./components/results/SectionSelector', () => ({ SectionSelector: () => <div /> }));
vi.mock('./components/export/ExportPanel', () => ({ ExportPanel: () => <div data-testid="export-panel" /> }));

import App from './App';
import { DEMO_MESH_IDS, useSession } from './stores/session';

const testI18n = i18n.createInstance();
void testI18n.use(initReactI18next).init({ lng: 'es', resources: { es: { translation: {} } } });

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={queryClient}><App /></QueryClientProvider>
    </I18nextProvider>,
  );
}

describe('App export workspace demo routing', () => {
  afterEach(() => {
    cleanup();
    useSession.getState().reset();
  });

  it('shows the export panel but does not mount AIReporter for virtual demo meshes', async () => {
    useSession.setState({
      activeWorkspaceView: 'export-ai',
      demoMode: true,
      designMeshId: DEMO_MESH_IDS.design,
      topoMeshId: DEMO_MESH_IDS.topo,
    });

    renderApp();

    expect(await screen.findByTestId('export-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('ai-reporter')).not.toBeInTheDocument();
  });

  it('keeps AIReporter mounted when demoMode is sticky but both mesh IDs are real', async () => {
    useSession.setState({
      activeWorkspaceView: 'export-ai',
      demoMode: true,
      designMeshId: 'real-design-id',
      topoMeshId: 'real-topo-id',
    });

    renderApp();

    expect(await screen.findByTestId('export-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('ai-reporter')).toBeInTheDocument();
  });

  it('does not mount AIReporter for a mixed session containing a virtual mesh', async () => {
    useSession.setState({
      activeWorkspaceView: 'export-ai',
      demoMode: true,
      designMeshId: 'real-design-id',
      topoMeshId: DEMO_MESH_IDS.topo,
    });

    renderApp();

    expect(await screen.findByTestId('export-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('ai-reporter')).not.toBeInTheDocument();
  });
});
