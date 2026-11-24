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
  return <input aria-label="draft" data-layout={layout} />;
} }));

beforeEach(() => {
  counters.mounts = 0;
  localStorage.clear();
  useWorkspaceMode.getState().resetForSession('protagonist', 'initial');
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('reduced-motion'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe('AgentWorkspaceShell', () => {
  it('keeps a manually expanded rail expanded while resizing', () => {
    useWorkspaceMode.getState().enterCopilot('manualView');
    render(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
    expect(useSession.getState().sidebarCollapsed).toBe(true);
    act(() => useSession.getState().setSidebarCollapsed(false));
    fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowLeft' });
    expect(useSession.getState().sidebarCollapsed).toBe(false);
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
