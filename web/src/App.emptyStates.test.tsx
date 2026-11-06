import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import i18n from 'i18next';
import es from './locales/es.json';

const apiState = vi.hoisted(() => ({
  sections: [] as { id: string }[],
  status: undefined as { status: string } | undefined,
  startDemo: vi.fn(),
}));

vi.mock('./components/layout/AppLayout', () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('./api/hooks', () => ({
  useSections: () => ({ data: apiState.sections }),
  useProcessStatus: () => ({ data: apiState.status }),
}));
vi.mock('./components/demo/TryDemoButton', () => ({ useStartDemo: () => apiState.startDemo }));
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
import { DEMO_MESH_IDS, useSession, type DemoData } from './stores/session';

const testI18n = i18n.createInstance();
void testI18n.use(initReactI18next).init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={queryClient}><App /></QueryClientProvider>
    </I18nextProvider>,
  );
}

describe('App workspace empty states', () => {
  beforeEach(() => {
    apiState.sections = [];
    apiState.status = undefined;
    apiState.startDemo.mockReset();
  });

  afterEach(() => {
    cleanup();
    useSession.getState().reset();
  });

  it('asks for surfaces and opens the surfaces step from the primary action', async () => {
    const user = userEvent.setup();
    useSession.setState({ activeWorkspaceView: 'profiles', sidebarCollapsed: true, openWorkflowStep: null });
    renderApp();
    expect(await screen.findByText('Comience cargando sus superficies')).toBeInTheDocument();
    expect(document.querySelector('[data-slot="empty-no-mesh"]')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cargar superficies' }));
    expect(useSession.getState().openWorkflowStep).toBe('surfaces');
    expect(useSession.getState().sidebarCollapsed).toBe(false);
  });

  it('starts the demo from the secondary action', async () => {
    const user = userEvent.setup();
    useSession.setState({ activeWorkspaceView: 'dashboard' });
    renderApp();
    await user.click(await screen.findByRole('button', { name: 'Probar con datos demo' }));
    expect(apiState.startDemo).toHaveBeenCalledOnce();
  });

  it('hides the demo action while demo mode is already active', async () => {
    useSession.setState({ activeWorkspaceView: 'dashboard', demoMode: true });
    renderApp();
    expect(await screen.findByRole('button', { name: 'Cargar superficies' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Probar con datos demo' })).not.toBeInTheDocument();
  });

  it('opens the sections step and switches to the 3D view when sections are missing', async () => {
    const user = userEvent.setup();
    useSession.setState({ activeWorkspaceView: 'blast', designMeshId: 'design', topoMeshId: 'topo', openWorkflowStep: null });
    renderApp();
    await user.click(await screen.findByRole('button', { name: 'Definir secciones' }));
    expect(useSession.getState().openWorkflowStep).toBe('sections');
    expect(useSession.getState().activeWorkspaceView).toBe('3d');
  });

  it('opens the process step when the analysis has not run', async () => {
    const user = userEvent.setup();
    apiState.sections = [{ id: 'section-1' }];
    useSession.setState({ activeWorkspaceView: 'dashboard', designMeshId: 'design', topoMeshId: 'topo', openWorkflowStep: null });
    renderApp();
    expect(document.querySelector('[data-slot="empty-no-process"]')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ir a procesar' }));
    expect(useSession.getState().openWorkflowStep).toBe('process');
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
  });

  it('opens dashboard once processing completes without reclaiming 3D afterward', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'processing' };
    useSession.setState({ activeWorkspaceView: '3d', designMeshId: 'design', topoMeshId: 'topo' });
    const view = renderApp();
    expect(screen.getByTestId('mesh-viewer')).toBeInTheDocument();
    apiState.status = { status: 'complete' };
    view.rerender(<I18nextProvider i18n={testI18n}><App /></I18nextProvider>);
    expect(await screen.findByTestId('dashboard')).toBeInTheDocument();
    act(() => useSession.getState().setActiveWorkspaceView('3d'));
    expect(screen.getByTestId('mesh-viewer')).toBeInTheDocument();
  });

  it('opens dashboard for a recovered complete session', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'complete' };
    useSession.setState({ activeWorkspaceView: '3d', designMeshId: 'design', topoMeshId: 'topo' });
    renderApp();
    expect(await screen.findByTestId('dashboard')).toBeInTheDocument();
  });

  it('opens an explicitly selected profile in detail mode', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'complete' };
    useSession.setState({ activeWorkspaceView: 'dashboard', designMeshId: 'design', topoMeshId: 'topo' });
    renderApp();
    act(() => {
      useSession.getState().setSelectedSection('section-1');
      useSession.getState().setProfilesMode('detail');
      useSession.getState().setActiveWorkspaceView('profiles');
    });
    expect(await screen.findByTestId('profile')).toBeInTheDocument();
    expect(useSession.getState().selectedSection).toBe('section-1');
    expect(useSession.getState().activeWorkspaceView).toBe('profiles');
  });

  it('preserves another selected view when processing finishes', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'processing' };
    useSession.setState({ activeWorkspaceView: 'profiles', designMeshId: 'design', topoMeshId: 'topo' });
    const view = renderApp();
    apiState.status = { status: 'complete' };
    view.rerender(<I18nextProvider i18n={testI18n}><App /></I18nextProvider>);
    expect(await screen.findByTestId('profiles-grid')).toBeInTheDocument();
  });

  it('shows the dashboard for a loaded virtual demo even if the API status is idle', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'idle' };
    useSession.setState({ activeWorkspaceView: 'dashboard', demoMode: true, demoData: { sections: [] } as unknown as DemoData, designMeshId: DEMO_MESH_IDS.design, topoMeshId: DEMO_MESH_IDS.topo });
    renderApp();
    expect(await screen.findByTestId('dashboard')).toBeInTheDocument();
    expect(document.querySelector('[data-slot="empty-no-process"]')).not.toBeInTheDocument();
  });

  it('shows blast workspace for a loaded virtual demo', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'idle' };
    useSession.setState({ activeWorkspaceView: 'blast', demoMode: true, demoData: { sections: [] } as unknown as DemoData, designMeshId: DEMO_MESH_IDS.design, topoMeshId: DEMO_MESH_IDS.topo });
    renderApp();
    expect(await screen.findByTestId('blast')).toBeInTheDocument();
  });

  it('does not treat a mixed demo and real session as complete', () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'idle' };
    useSession.setState({ activeWorkspaceView: 'dashboard', demoMode: true, demoData: { sections: [] } as unknown as DemoData, designMeshId: DEMO_MESH_IDS.design, topoMeshId: 'real' });
    renderApp();
    expect(document.querySelector('[data-slot="empty-no-process"]')).toBeInTheDocument();
  });

  it('maps numeric shortcuts to the visible tab order', async () => {
    const user = userEvent.setup();
    renderApp();
    for (const [key, view] of [['1', 'dashboard'], ['2', 'profiles'], ['3', '3d'], ['4', 'blast'], ['5', 'export-ai']]) {
      await user.keyboard(key);
      expect(useSession.getState().activeWorkspaceView).toBe(view);
    }
  });

  it('titles the dashboard detail table with the translated heading', async () => {
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'complete' };
    useSession.setState({ activeWorkspaceView: 'dashboard', designMeshId: 'design', topoMeshId: 'topo' });
    renderApp();
    expect(await screen.findByRole('heading', { name: 'Tabla detallada de comparación' })).toHaveClass('ui-section-title');
  });
});
