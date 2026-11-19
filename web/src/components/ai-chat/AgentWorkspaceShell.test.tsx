import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { AgentWorkspaceShell } from './AgentWorkspaceShell';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./FloatingChatButton', () => ({ useAgentChatInvalidationBridge: () => {} }));
vi.mock('./ChatPanel', () => ({ ChatPanel: () => { const [value, setValue] = useState(''); return <input aria-label="draft" value={value} onChange={(e) => setValue(e.target.value)} />; } }));

afterEach(cleanup);

describe('AgentWorkspaceShell', () => {
  it('shows workspace and one chat from the start without an isolated landing page', () => {
    render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    expect(screen.getByText('workspace content')).toBeTruthy();
    expect(screen.getAllByLabelText('draft')).toHaveLength(1);
    expect(screen.queryByText('agentWorkspace.open')).toBeNull();
  });
  it('preserves the same chat draft while switching mobile views', () => {
    render(<AgentWorkspaceShell><div>workspace content</div></AgentWorkspaceShell>);
    const input = screen.getByLabelText('draft') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'draft' } });
    fireEvent.click(screen.getByText('agentWorkspace.chat'));
    fireEvent.click(screen.getByText('agentWorkspace.workspace'));
    fireEvent.click(screen.getByText('agentWorkspace.chat'));
    expect(screen.getByLabelText('draft')).toBe(input);
    expect(input.value).toBe('draft');
  });
});
