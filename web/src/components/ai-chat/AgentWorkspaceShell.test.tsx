import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEffect } from 'react';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import { useSession } from '../../stores/session';
import { AgentWorkspaceShell } from './AgentWorkspaceShell';
import { useCanvasHidden } from './canvasVisibility';

function VisibilityProbe() {
  const hidden = useCanvasHidden();
  return <span data-testid="canvas-visibility">{hidden ? 'hidden' : 'visible'}</span>;
}

const counters = vi.hoisted(() => ({ mounts: 0 }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./FloatingChatButton', () => ({ useAgentChatInvalidationBridge: () => {} }));
vi.mock('./ChatPanel', () => ({ ChatPanel: ({ layout }: { layout: string }) => {
  useEffect(() => { counters.mounts += 1; }, []);
  return <input aria-label="draft" data-testid="ai-chat-input" data-layout={layout} />;
} }));

beforeEach(() => {
  counters.mounts = 0;
  useSession.getState().reset();
  useWorkspaceMode.setState({ initialDecided: false });
  localStorage.clear();
  useWorkspaceMode.getState().resetForSession('protagonist', 'initial');
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('reduced-motion'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
describe('AgentWorkspaceShell', () => {
  it('keeps the rail open when entering copilot during data entry', () => {
    vi.stubGlobal('innerWidth', 1440);
    render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(useSession.getState().sidebarCollapsed).toBe(false);
  });
  it('collapses on entry when complete', () => {
    vi.stubGlobal('innerWidth', 1440);
    render(<AgentWorkspaceShell dataEntry={false}><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(useSession.getState().sidebarCollapsed).toBe(true);
  });
  it('collapses once on completion and respects a manual expansion across renders', () => {
    vi.stubGlobal('innerWidth', 1440);
    useWorkspaceMode.setState({ mode: 'copilot', initialDecided: true });
    const { rerender } = render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    rerender(<AgentWorkspaceShell dataEntry={false}><div>workspace</div></AgentWorkspaceShell>);
    expect(useSession.getState().sidebarCollapsed).toBe(true);
    act(() => useSession.getState().setSidebarCollapsed(false));
    rerender(<AgentWorkspaceShell dataEntry={false}><div>changed</div></AgentWorkspaceShell>);
    expect(useSession.getState().sidebarCollapsed).toBe(false);
  });
  it('expands when completion becomes data entry', () => {
    vi.stubGlobal('innerWidth', 1440);
    useWorkspaceMode.setState({ mode: 'copilot', initialDecided: true });
    const { rerender } = render(<AgentWorkspaceShell dataEntry={false}><div>workspace</div></AgentWorkspaceShell>);
    rerender(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    expect(useSession.getState().sidebarCollapsed).toBe(false);
  });
  it('respects a manual collapse during data entry across renders', () => {
    vi.stubGlobal('innerWidth', 1440);
    useWorkspaceMode.setState({ mode: 'copilot', initialDecided: true });
    const { rerender } = render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    act(() => useSession.getState().setSidebarCollapsed(true));
    rerender(<AgentWorkspaceShell dataEntry><div>changed</div></AgentWorkspaceShell>);
    expect(useSession.getState().sidebarCollapsed).toBe(true);
  });
  it('collapses on entry when available width is insufficient', () => {
    vi.stubGlobal('innerWidth', 1024);
    render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(useSession.getState().sidebarCollapsed).toBe(true);
  });
  it('measures the threshold against the stored rail width', () => {
    vi.stubGlobal('innerWidth', 1200);
    const { unmount } = render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(useSession.getState().sidebarCollapsed).toBe(false);
    unmount();
    act(() => useWorkspaceMode.getState().focusConversation());
    localStorage.setItem('sidebar_width', '520');
    render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(useSession.getState().sidebarCollapsed).toBe(true);
  });
  it('does not change the rail on mobile', () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('max-width'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    useSession.getState().setSidebarCollapsed(true);
    render(<AgentWorkspaceShell dataEntry><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(useSession.getState().sidebarCollapsed).toBe(true);
  });
  it('reports visibility outside the shell and across keep-alive mode changes', () => {
    useWorkspaceMode.setState({ mode: 'copilot', initialDecided: true });
    render(<><VisibilityProbe /><AgentWorkspaceShell><VisibilityProbe /></AgentWorkspaceShell></>);
    expect(screen.getAllByTestId('canvas-visibility').map((node) => node.textContent)).toEqual(['visible', 'visible']);
    act(() => useWorkspaceMode.getState().focusConversation());
    expect(screen.getAllByTestId('canvas-visibility').map((node) => node.textContent)).toEqual(['visible', 'hidden']);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(screen.getAllByTestId('canvas-visibility').map((node) => node.textContent)).toEqual(['visible', 'visible']);
  });
  it('shows a loading copilot shell before the initial restored decision', () => {
    useSession.setState({ designMeshId: 'design', topoMeshId: 'topo' });
    const { container } = render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    expect(container.querySelector('.agent-shell--copilot')).toHaveClass('agent-shell--no-animation');
    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.queryByText('workspace content')).toBeNull();
    expect(container.querySelector('.agent-shell--protagonist')).toBeNull();
  });
  it('does not animate the first decision from protagonist to copilot', () => {
    const { container } = render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    act(() => {
      useWorkspaceMode.getState().enterCopilot('resultsRestored');
      useWorkspaceMode.getState().markInitialDecided();
    });
    expect(container.querySelector('.agent-shell')).toHaveClass('agent-shell--no-animation');
    expect(container.querySelector<HTMLElement>('.agent-shell__grid')?.style.transition).toBe('');
  });
  it('focuses the composer when the conversation is explicitly focused', () => {
    useWorkspaceMode.setState({ mode: 'copilot', lastReason: 'manualView', initialDecided: true });
    render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().focusConversation());
    expect(screen.getByTestId('ai-chat-input')).toHaveFocus();
  });
  it('does not steal focus from a control that remains mounted', () => {
    useWorkspaceMode.setState({ mode: 'copilot', lastReason: 'manualView', initialDecided: true });
    render(<><button>Outside</button><AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell></>);
    screen.getByText('Outside').focus();
    act(() => useWorkspaceMode.getState().focusConversation());
    expect(screen.getByText('Outside')).toHaveFocus();
  });
  it('moves focus from the analysis rail to the mounted canvas heading', () => {
    useWorkspaceMode.setState({ initialDecided: true });
    render(<><aside data-slot="left-sidebar"><button>Dashboard</button></aside><AgentWorkspaceShell canvasHeader={<h2 tabIndex={-1}>Canvas</h2>}><div>workspace</div></AgentWorkspaceShell></>);
    screen.getByText('Dashboard').focus();
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(screen.getByText('Canvas')).toHaveFocus();
  });
  it('keeps a manually expanded rail expanded while resizing', () => {
    useWorkspaceMode.getState().enterCopilot('manualView');
    render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    expect(useSession.getState().sidebarCollapsed).toBe(true);
    act(() => useSession.getState().setSidebarCollapsed(false));
    fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowLeft' });
    expect(useSession.getState().sidebarCollapsed).toBe(false);
  });
  it('returns to workspace on a manual view event on mobile', () => {
    vi.stubGlobal('innerWidth', 600);
    useWorkspaceMode.setState({ mode: 'copilot', initialDecided: true });
    const { container } = render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    fireEvent.click(screen.getByText('agentWorkspace.chat'));
    expect(container.querySelector('.agent-shell')).toHaveClass('agent-shell--mobile-chat');
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(container.querySelector('.agent-shell')).toHaveClass('agent-shell--mobile-workspace');
  });
  it('keeps mobile chat mounted when switching panes', () => {
    useWorkspaceMode.getState().enterCopilot('manualView');
    render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    const input = screen.getByLabelText('draft');
    fireEvent.click(screen.getByText('agentWorkspace.chat'));
    fireEvent.click(screen.getByText('agentWorkspace.workspace'));
    expect(screen.getByLabelText('draft')).toBe(input);
    expect(counters.mounts).toBe(1);
  });
  it('keeps one chat node and switches layout while mounting the canvas only in copilot', () => {
    render(<AgentWorkspaceShell canvasHeader={<div>canvas header</div>}><div>workspace content</div></AgentWorkspaceShell>);
    const input = screen.getByLabelText('draft');
    expect(input).toHaveAttribute('data-layout', 'protagonist');
    expect(screen.queryByText('workspace content')).toBeNull();
    expect(screen.queryByText('canvas header')).toBeNull();
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(screen.getByText('workspace content')).toBeTruthy();
    expect(screen.getByText('canvas header')).toBeTruthy();
    expect(screen.getByLabelText('draft')).toBe(input);
    expect(input).toHaveAttribute('data-layout', 'copilot');
    expect(counters.mounts).toBe(1);
    act(() => useWorkspaceMode.getState().focusConversation());
    expect(screen.getByText('workspace content')).toBeTruthy();
    expect(screen.getByText('workspace content').closest('.agent-shell__workspace')).toHaveAttribute('inert');
    expect(screen.getByLabelText('draft')).toBe(input);
  });
  it('defers the first canvas mount until the animated transition ends', () => {
    vi.useFakeTimers();
    vi.stubGlobal('innerWidth', 1200);
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    useWorkspaceMode.setState({ mode: 'protagonist', initialDecided: true });
    const { container } = render(<AgentWorkspaceShell><div>workspace deferred</div></AgentWorkspaceShell>);
    act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
    expect(screen.queryByText('workspace deferred')).toBeNull();
    act(() => { vi.advanceTimersByTime(250); });
    expect(screen.getByText('workspace deferred')).toBeTruthy();
    expect(container.querySelector('.agent-shell__canvas')).toBeTruthy();
  });
  it('survives unavailable storage on read and write', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
    useWorkspaceMode.setState({ mode: 'copilot', initialDecided: true });
    expect(() => render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>)).not.toThrow();
    expect(() => fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowLeft' })).not.toThrow();
    vi.restoreAllMocks();
  });
  it('resizes with keyboard and persists a bounded width', () => {
    localStorage.setItem('conciliacion.agentWorkspace.copilotWidth.v1', 'corrupt');
    useWorkspaceMode.getState().enterCopilot('manualView');
    render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    const handle = screen.getByRole('separator');
    expect(handle).toHaveAttribute('aria-valuenow', '390');
    fireEvent.keyDown(handle, { key: 'ArrowLeft' });
    expect(handle).toHaveAttribute('aria-valuenow', '406');
    fireEvent.keyDown(handle, { key: 'End' });
    expect(handle).toHaveAttribute('aria-valuenow', '520');
    expect(localStorage.getItem('conciliacion.agentWorkspace.copilotWidth.v1')).toBe('520');
    fireEvent.keyDown(handle, { key: 'Home' });
    expect(handle).toHaveAttribute('aria-valuenow', '320');
  });
});
