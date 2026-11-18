import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { AgentWorkspaceShell } from './AgentWorkspaceShell';
import { useSession } from '../../stores/session';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./FloatingChatButton', () => ({ useAgentChatInvalidationBridge: () => {} }));
vi.mock('./ChatPanel', () => ({ ChatPanel: () => { const [value, setValue] = useState(''); return <input aria-label="draft" value={value} onChange={(e) => setValue(e.target.value)} />; } }));

afterEach(() => { cleanup(); useSession.getState().reset(); });

describe('AgentWorkspaceShell', () => {
  it('opens workspace without losing the chat draft and returns to wide chat', () => {
    render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    const input = screen.getByLabelText('draft');
    fireEvent.change(input, { target: { value: 'draft' } });
    expect(screen.queryByText('workspace content')).toBeNull();
    fireEvent.click(screen.getByText('agentWorkspace.open'));
    expect(screen.getByText('workspace content')).toBeTruthy();
    expect(screen.getByLabelText('draft')).toBe(input);
    expect((input as HTMLInputElement).value).toBe('draft');
    fireEvent.click(screen.getByText('agentWorkspace.expandChat'));
    expect(screen.getByLabelText('draft')).toBe(input);
  });
  it('reveals workspace for a restored or newly loaded mesh', () => {
    useSession.getState().setTopoMeshId('mesh-1');
    render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    expect(screen.getByText('workspace content')).toBeTruthy();
  });
  it('reveals workspace when a mesh arrives after opening', () => {
    const { rerender } = render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    fireEvent.change(screen.getByLabelText('draft'), { target: { value: 'draft' } });
    useSession.getState().setDesignMeshId('mesh-new');
    rerender(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    expect(screen.getByText('workspace content')).toBeTruthy();
    expect((screen.getByLabelText('draft') as HTMLInputElement).value).toBe('draft');
  });
  it('does not open for blank mesh ids', () => {
    useSession.getState().setTopoMeshId('  ');
    render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    expect(screen.queryByText('workspace content')).toBeNull();
  });
});
