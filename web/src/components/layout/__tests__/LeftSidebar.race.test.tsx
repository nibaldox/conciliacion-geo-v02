import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import { DEFAULT_SETTINGS, DEFAULT_TOLERANCES } from '../../../utils/constants';
import { useSession } from '../../../stores/session';
import { useWorkspaceMode } from '../../../stores/workspaceMode';
import { useWorkspaceModeCoordinator } from '../../ai-chat/useWorkspaceModeCoordinator';
import { LeftSidebar } from '../LeftSidebar';

const requests = vi.hoisted(() => ({
  sections: () => Promise.resolve([] as Array<{ id: string }>),
  status: () => Promise.resolve({ status: 'complete', n_results: 1 }),
}));

vi.mock('../../../api/hooks', () => ({
  useSections: () => useQuery({ queryKey: ['sections'], queryFn: requests.sections }),
  useProcessStatus: () => useQuery({ queryKey: ['status'], queryFn: requests.status }),
  useSettings: () => ({ data: { process: DEFAULT_SETTINGS, tolerances: DEFAULT_TOLERANCES } }),
  useUpdateSettings: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../../mesh/MeshUpload', () => ({ DropZone: () => null }));
vi.mock('../../demo/TryDemoButton', () => ({ TryDemoButton: () => null }));
vi.mock('../../sections/SectionCurveForm', () => ({ SectionCurveForm: () => null }));
vi.mock('../../sections/SectionFileUpload', () => ({ SectionFileUpload: () => null }));
vi.mock('../../sections/SectionList', () => ({ SectionList: () => null }));
vi.mock('../../analysis/ProcessButton', () => ({ ProcessButton: () => null }));
vi.mock('../../analysis/ProcessProgress', () => ({ ProcessProgress: () => null }));
vi.mock('../LanguageToggle', () => ({ LanguageToggle: () => null }));
vi.mock('../../session/RecentSessionsList', () => ({ RecentSessionsList: () => null }));

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function App() {
  useWorkspaceModeCoordinator();
  return <LeftSidebar />;
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><I18nextProvider i18n={i18n}><App /></I18nextProvider></QueryClientProvider>);
}

describe('restauración y navegación de secciones AI-first', () => {
  beforeAll(() => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: () => false }));
  });
  beforeEach(() => {
    vi.stubEnv('VITE_AI_FIRST', 'true');
    vi.stubEnv('VITE_AI_CHAT', 'true');
    useSession.getState().reset();
    useSession.setState({ designMeshId: 'design', topoMeshId: 'topo', openWorkflowStep: 'surfaces' });
    useWorkspaceMode.getState().resetForSession('protagonist', 'initial');
  });
  afterEach(() => { vi.unstubAllEnvs(); });

  it.each(['status-first', 'sections-first'])('restaura dashboard con orden %s', async (order) => {
    const sections = deferred<Array<{ id: string }>>();
    const status = deferred<{ status: string; n_results: number }>();
    requests.sections = () => sections.promise;
    requests.status = () => status.promise;
    renderApp();
    if (order === 'status-first') {
      await act(async () => { status.resolve({ status: 'complete', n_results: 226 }); });
      await waitFor(() => expect(useSession.getState().activeWorkspaceView).toBe('dashboard'));
      await act(async () => { sections.resolve([{ id: 's1' }]); });
    } else {
      await act(async () => { sections.resolve([{ id: 's1' }]); });
      await waitFor(() => expect(document.getElementById('workflow-step-sections')).toHaveAttribute('data-state', 'done'));
      await act(async () => { status.resolve({ status: 'complete', n_results: 226 }); });
    }
    await waitFor(() => expect(document.getElementById('workflow-step-sections')).toHaveAttribute('data-state', 'done'));
    await waitFor(() => expect(document.getElementById('workflow-step-process')).toHaveAttribute('data-state', 'done'));
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
    expect(useWorkspaceMode.getState().mode).toBe('copilot');
    expect(useWorkspaceMode.getState().lastReason).not.toBe('manualView');
  });

  it('abrir secciones con curvas navega a 3D', async () => {
    requests.sections = () => Promise.resolve([{ id: 's1' }]);
    requests.status = () => Promise.resolve({ status: 'complete', n_results: 226 });
    renderApp();
    await waitFor(() => expect(useSession.getState().activeWorkspaceView).toBe('dashboard'));
    fireEvent.click(document.getElementById('workflow-step-sections')!);
    expect(useSession.getState().activeWorkspaceView).toBe('3d');
    expect(useWorkspaceMode.getState().lastReason).toBe('manualView');
  });

  it('elegir curvas en el paso abierto navega a 3D', async () => {
    requests.sections = () => Promise.resolve([{ id: 's1' }]);
    requests.status = () => Promise.resolve({ status: 'complete', n_results: 226 });
    renderApp();
    await waitFor(() => expect(useSession.getState().activeWorkspaceView).toBe('dashboard'));
    fireEvent.click(document.getElementById('workflow-step-sections')!);
    fireEvent.click(screen.getByRole('button', { name: i18n.t('workspace.file') }));
    act(() => useSession.getState().setActiveWorkspaceView('dashboard'));
    fireEvent.click(screen.getByRole('button', { name: i18n.t('workspace.curves') }));
    expect(useSession.getState().activeWorkspaceView).toBe('3d');
  });
});
