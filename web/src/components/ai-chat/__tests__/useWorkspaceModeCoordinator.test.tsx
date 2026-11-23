import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSession, type DemoData } from '../../../stores/session';
import { useWorkspaceMode } from '../../../stores/workspaceMode';
import { useWorkspaceModeCoordinator } from '../useWorkspaceModeCoordinator';

const query = vi.hoisted(() => ({
  value: { isSuccess: true, isError: false, data: { status: 'idle', n_results: 0 } } as {
    isSuccess: boolean; isError: boolean; data?: { status: string; n_results: number };
  },
}));
vi.mock('../../../api/hooks', () => ({ useProcessStatus: () => query.value }));

function setQuery(status: string, count = 0) {
  query.value = { isSuccess: true, isError: false, data: { status, n_results: count } };
}
function meshes() {
  useSession.setState({ designMeshId: 'design', topoMeshId: 'topo' });
}
function expectMode(mode: string, view: string) {
  expect(useWorkspaceMode.getState().mode).toBe(mode);
  expect(useSession.getState().activeWorkspaceView).toBe(view);
}

beforeEach(() => {
  useSession.getState().reset();
  useWorkspaceMode.setState({ mode: 'protagonist', lastReason: 'initial' });
  setQuery('idle');
});

describe('workspace mode coordinator', () => {
  it('initializes an empty session in protagonist mode', () => {
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('protagonist', '3d');
  });
  it('initializes two meshes in copilot and 3d', () => {
    meshes();
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('copilot', '3d');
    expect(useWorkspaceMode.getState().lastReason).toBe('meshesReady');
  });
  it('prefers restored results over simultaneous meshes', () => {
    meshes();
    setQuery('complete', 2);
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('copilot', 'dashboard');
    expect(useWorkspaceMode.getState().lastReason).toBe('resultsRestored');
  });
  it('restores results even without meshes', () => {
    setQuery('complete', 2);
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('copilot', 'dashboard');
  });
  it('waits for process status', () => {
    meshes();
    query.value = { isSuccess: false, isError: false };
    const { rerender } = renderHook(() => useWorkspaceModeCoordinator());
    expectMode('protagonist', '3d');
    setQuery('complete', 1);
    rerender();
    expectMode('copilot', 'dashboard');
  });
  it('uses meshes but never dashboard when the process query errors', () => {
    meshes();
    query.value = { isSuccess: false, isError: true };
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('copilot', '3d');
  });
  it('stays protagonist on process error without both meshes', () => {
    query.value = { isSuccess: false, isError: true };
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('protagonist', '3d');
  });
  it('reacts when the second mesh arrives', () => {
    useSession.setState({ designMeshId: 'design' });
    renderHook(() => useWorkspaceModeCoordinator());
    act(() => useSession.getState().setTopoMeshId('topo'));
    expectMode('copilot', '3d');
    expect(useWorkspaceMode.getState().lastReason).toBe('meshesReady');
  });
  it('does not reenter copilot on a refetch after focus', () => {
    meshes();
    const { rerender } = renderHook(() => useWorkspaceModeCoordinator());
    act(() => useWorkspaceMode.getState().focusConversation());
    setQuery('idle');
    rerender();
    expectMode('protagonist', '3d');
  });
  it('enters copilot when an external view change follows focus', () => {
    meshes();
    renderHook(() => useWorkspaceModeCoordinator());
    act(() => useWorkspaceMode.getState().focusConversation());
    act(() => useSession.getState().setActiveWorkspaceView('export-ai'));
    expectMode('copilot', 'export-ai');
    expect(useWorkspaceMode.getState().lastReason).toBe('manualView');
  });
  it('does not let later mesh events steal a manually chosen view', () => {
    renderHook(() => useWorkspaceModeCoordinator());
    act(() => useSession.getState().setActiveWorkspaceView('profiles'));
    act(() => meshes());
    expectMode('copilot', 'profiles');
  });
  it('moves from 3d to dashboard on processing completion without changing mode', () => {
    const { rerender } = renderHook(() => useWorkspaceModeCoordinator());
    setQuery('complete', 1);
    rerender();
    expectMode('protagonist', 'dashboard');
    expect(useWorkspaceMode.getState().lastReason).toBe('initial');
  });
  it('keeps profiles on processing completion', () => {
    const { rerender } = renderHook(() => useWorkspaceModeCoordinator());
    act(() => useSession.getState().setActiveWorkspaceView('profiles'));
    setQuery('complete', 1);
    rerender();
    expectMode('copilot', 'profiles');
  });
  it('initializes a loaded demo in dashboard', () => {
    useSession.setState({ demoMode: true, demoData: { sections: [] } as unknown as DemoData });
    renderHook(() => useWorkspaceModeCoordinator());
    expectMode('copilot', 'dashboard');
    expect(useWorkspaceMode.getState().lastReason).toBe('demo');
  });
  it('preserves a manual selection made while hydration is pending', () => {
    query.value = { isSuccess: false, isError: false };
    const { rerender } = renderHook(() => useWorkspaceModeCoordinator());
    act(() => {
      useWorkspaceMode.getState().enterCopilot('manualView');
      useSession.getState().setActiveWorkspaceView('profiles');
    });
    setQuery('complete', 1);
    rerender();
    expectMode('copilot', 'profiles');
  });
  it('does not classify coordinator navigation as manual or prevent later mesh transitions', () => {
    setQuery('complete', 1);
    const { rerender } = renderHook(() => useWorkspaceModeCoordinator());
    expect(useWorkspaceMode.getState().lastReason).toBe('resultsRestored');
    setQuery('idle');
    rerender();
    act(() => meshes());
    expectMode('copilot', '3d');
    expect(useWorkspaceMode.getState().lastReason).toBe('meshesReady');
  });
  it('recognizes loadDemo directly setting dashboard', async () => {
    useSession.setState({ demoData: { sections: [] } as unknown as DemoData });
    renderHook(() => useWorkspaceModeCoordinator());
    await act(async () => useSession.getState().loadDemo());
    expectMode('copilot', 'dashboard');
    expect(useWorkspaceMode.getState().lastReason).toBe('demo');
  });
});
