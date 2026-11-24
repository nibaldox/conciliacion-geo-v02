import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEffect } from 'react';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import { useSession } from '../../stores/session';
import { AgentWorkspaceShell } from './AgentWorkspaceShell';

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
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe('AgentWorkspaceShell', () => {
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
    expect(screen.queryByText('workspace content')).toBeNull();
    expect(screen.getByLabelText('draft')).toBe(input);
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
