import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from '../../../i18n';
import { BlastWorkspace } from '../BlastWorkspace';
import { useBlastSessionSummary } from '../../../api/hooks';
import { DEMO_MESH_IDS, useSession } from '../../../stores/session';
import { useBlastView } from '../../../stores/blastView';

const sessionState = vi.hoisted(() => ({ id: 'session-a' as string | null }));
const uploaderProps = vi.hoisted(() => ({ onUploaded: undefined as undefined | (() => unknown) }));

vi.mock('../../../api/client', () => ({
  getSessionId: vi.fn(() => sessionState.id),
}));

vi.mock('../../../api/hooks', () => ({
  useBlastSessionSummary: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
}));

vi.mock('../../mesh/Mesh3DViewer', () => ({
  Mesh3DViewer: ({ mode }: { mode?: string }) => (
    <div data-testid="mesh-viewer" data-mode={mode} />
  ),
}));

vi.mock('../BlastCorrelation', () => ({
  BlastCorrelation: ({ presentation }: { presentation?: string }) => (
    <div data-testid="blast-correlation" data-presentation={presentation ?? 'legacy'} />
  ),
}));

vi.mock('../BlastSimulationPanel', () => ({
  BlastSimulationPanel: ({ sessionId, geometryConfigurationVersion }: { sessionId: string | null; geometryConfigurationVersion: string }) => (
    <div data-testid="simulation-panel" data-session={sessionId ?? ''} data-version={geometryConfigurationVersion} />
  ),
}));

vi.mock('../BlastUploader', () => ({
  BlastUploader: (props: { onUploaded?: () => unknown }) => {
    uploaderProps.onUploaded = props.onUploaded;
    return <div data-testid="blast-uploader" />;
  },
}));

const summaryMock = vi.mocked(useBlastSessionSummary);

function setHoles(nHoles: number | undefined, isLoading = false) {
  summaryMock.mockReturnValue({
    data: nHoles === undefined ? undefined : { n_holes: nHoles },
    isLoading,
    error: null,
  } as unknown as ReturnType<typeof useBlastSessionSummary>);
}

function renderWorkspace(queryClient = new QueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <BlastWorkspace />
    </QueryClientProvider>,
  );
}

function tab(name: 'explore' | 'analysis' | 'simulation' | 'data') {
  return screen.getByRole('tab', { name: { explore: 'Explorar', analysis: 'Análisis', simulation: 'Simulación', data: 'Datos' }[name] });
}

beforeAll(async () => {
  await i18n.changeLanguage('es');
});

beforeEach(() => {
  vi.clearAllMocks();
  sessionState.id = `session-${Math.random().toString(36).slice(2)}`;
  uploaderProps.onUploaded = undefined;
  useSession.setState({ demoMode: false, demoData: null, designMeshId: null, topoMeshId: null });
  useBlastView.setState({ workspaceTab: 'explore', surveyDate: '' });
});

it('warns about legacy data and opens Datos', () => {
  summaryMock.mockReturnValue({ data: { n_holes: 3, data_status: 'legacy_reimport_required' }, isLoading: false, error: null } as unknown as ReturnType<typeof useBlastSessionSummary>);
  renderWorkspace();
  expect(screen.getByText(/Estos pozos se importaron con una versión anterior/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /ir a datos/i }));
  expect(tab('data')).toHaveAttribute('aria-selected', 'true');
});

describe('<BlastWorkspace /> tablist', () => {
  it('exposes an accessible tablist with four tabs labelled in Spanish', () => {
    setHoles(3);
    renderWorkspace();
    const list = screen.getByRole('tablist', { name: 'Secciones de Tronadura' });
    expect(list).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((el) => el.textContent)).toEqual([
      'Explorar', 'Análisis', 'Simulación', 'Datos',
    ]);
  });
});

describe('<BlastWorkspace /> initial tab', () => {
  it('opens Explorar with the blast-mode viewer when holes exist', async () => {
    setHoles(3);
    renderWorkspace();
    const viewer = await screen.findByTestId('mesh-viewer');
    expect(viewer).toHaveAttribute('data-mode', 'blast');
    expect(tab('explore')).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByTestId('blast-uploader')).not.toBeInTheDocument();
  });

  it('opens Datos when no holes are loaded', async () => {
    setHoles(0);
    renderWorkspace();
    expect(await screen.findByTestId('blast-uploader')).toBeInTheDocument();
    expect(tab('data')).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByTestId('mesh-viewer')).not.toBeInTheDocument();
  });

  it('does not force a tab while the holes summary is loading', () => {
    useBlastView.setState({ workspaceTab: 'analysis' });
    setHoles(undefined, true);
    renderWorkspace();
    expect(tab('analysis')).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByTestId('blast-uploader')).not.toBeInTheDocument();
  });

  it('decides the initial tab only once per session', () => {
    setHoles(0);
    const { rerender } = renderWorkspace();
    expect(tab('data')).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(tab('analysis'));
    setHoles(0);
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <BlastWorkspace />
      </QueryClientProvider>,
    );
    expect(tab('analysis')).toHaveAttribute('aria-selected', 'true');
  });

  it('respects the stored tab when holes exist', () => {
    useBlastView.setState({ workspaceTab: 'simulation' });
    setHoles(4);
    renderWorkspace();
    expect(tab('simulation')).toHaveAttribute('aria-selected', 'true');
  });
});

describe('<BlastWorkspace /> panels', () => {
  it('mounts only the active panel', async () => {
    setHoles(3);
    renderWorkspace();
    await screen.findByTestId('mesh-viewer');
    fireEvent.click(tab('analysis'));
    expect(screen.getByTestId('blast-correlation')).toBeInTheDocument();
    expect(screen.queryByTestId('mesh-viewer')).not.toBeInTheDocument();
    expect(screen.queryByTestId('simulation-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('blast-uploader')).not.toBeInTheDocument();
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  });

  it('Análisis renders BlastCorrelation in analysis presentation', () => {
    setHoles(3);
    renderWorkspace();
    fireEvent.click(tab('analysis'));
    expect(screen.getByTestId('blast-correlation')).toHaveAttribute('data-presentation', 'analysis');
  });

  it('Simulación passes the session and geometry configuration version', () => {
    setHoles(3);
    renderWorkspace();
    fireEvent.click(tab('simulation'));
    const panel = screen.getByTestId('simulation-panel');
    expect(panel).toHaveAttribute('data-session', sessionState.id);
    expect(panel).toHaveAttribute('data-version', '2.0');
  });

  it('gives the Explorar panel full height without overflow and scrolls the other panels', () => {
    setHoles(3);
    renderWorkspace();
    const root = screen.getByRole('tabpanel').parentElement as HTMLElement;
    expect(root).toHaveClass('flex-1', 'min-h-0', 'flex', 'flex-col', 'gap-4');
    const panelClasses = () => screen.getByRole('tabpanel').className.split(/\s+/);

    expect(panelClasses()).toEqual(expect.arrayContaining(['flex-1', 'min-h-0']));
    expect(panelClasses()).not.toContain('overflow-y-auto');

    fireEvent.click(tab('analysis'));
    expect(panelClasses()).toEqual(expect.arrayContaining(['flex-1', 'min-h-0', 'overflow-y-auto']));

    fireEvent.click(tab('simulation'));
    expect(panelClasses()).toEqual(expect.arrayContaining(['flex-1', 'min-h-0', 'overflow-y-auto']));

    fireEvent.click(tab('data'));
    expect(panelClasses()).toEqual(expect.arrayContaining(['flex-1', 'min-h-0', 'overflow-y-auto']));
  });

  it('Datos invalidates correlation, damage and 3D hole queries after upload', async () => {
    setHoles(0);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined);
    renderWorkspace(qc);
    await screen.findByTestId('blast-uploader');
    await act(async () => {
      await uploaderProps.onUploaded?.();
    });
    const keys = spy.mock.calls.map(([arg]) => (arg as { queryKey: unknown[] }).queryKey);
    expect(keys).toEqual(expect.arrayContaining([
      ['blast-correlation'],
      ['blast-damage-model'],
      ['blast-holes-3d'],
    ]));
  });
});

describe('<BlastWorkspace /> keyboard and persistence', () => {
  it('ArrowRight and ArrowLeft move between tabs and wrap around', () => {
    setHoles(3);
    renderWorkspace();
    const explore = tab('explore');
    fireEvent.keyDown(explore, { key: 'ArrowRight' });
    expect(tab('analysis')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('analysis'), { key: 'ArrowRight' });
    expect(tab('simulation')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('simulation'), { key: 'ArrowLeft' });
    expect(tab('analysis')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('explore'), { key: 'ArrowLeft' });
    expect(tab('data')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('data'), { key: 'ArrowRight' });
    expect(tab('explore')).toHaveAttribute('aria-selected', 'true');
  });

  it('tabs point to their panels via aria-controls and aria-labelledby', () => {
    setHoles(3);
    renderWorkspace();
    const explore = tab('explore');
    const panel = screen.getByRole('tabpanel');
    expect(explore).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', explore.id);
  });

  it('keeps the selected tab across unmount and remount (store)', () => {
    setHoles(3);
    const first = renderWorkspace();
    fireEvent.click(tab('simulation'));
    first.unmount();
    expect(useBlastView.getState().workspaceTab).toBe('simulation');
    renderWorkspace();
    expect(tab('simulation')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('simulation-panel')).toBeInTheDocument();
  });

  it('Explorar without holes shows the notice and a button to Datos', () => {
    setHoles(0);
    renderWorkspace();
    fireEvent.click(tab('explore'));
    expect(screen.getByText('Cargue un archivo de pozos en Datos para explorar.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Datos' }));
    expect(tab('data')).toHaveAttribute('aria-selected', 'true');
    expect(useBlastView.getState().workspaceTab).toBe('data');
  });

  it('uses the virtual-mesh guard: no summary query for demo meshes', () => {
    useSession.setState({ designMeshId: DEMO_MESH_IDS.design });
    setHoles(0);
    renderWorkspace();
    expect(summaryMock).toHaveBeenCalledWith(null);
  });
});
