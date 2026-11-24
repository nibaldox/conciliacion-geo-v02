import { act, screen } from '@testing-library/react';
import { it, expect, vi } from 'vitest';
import { AgentWorkspaceShell } from './AgentWorkspaceShell';
import { renderWithProviders } from './__tests__/chatTestUtils';
import { useAIChat } from '../../stores/aiChat';
import { useSession } from '../../stores/session';
import { useWorkspaceMode } from '../../stores/workspaceMode';

vi.mock('./FloatingChatButton', () => ({ useAgentChatInvalidationBridge: () => {} }));

it('keeps the real composer node when changing modes', () => {
  useSession.getState().reset();
  useWorkspaceMode.setState({ mode: 'protagonist', lastReason: 'initial', initialDecided: true });
  vi.spyOn(useAIChat.getState(), 'init').mockResolvedValue();
  renderWithProviders(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
  const input = screen.getByTestId('ai-chat-input');
  act(() => useWorkspaceMode.getState().enterCopilot('manualView'));
  expect(screen.getByTestId('ai-chat-input')).toBe(input);
  act(() => useWorkspaceMode.getState().focusConversation());
  expect(screen.getByTestId('ai-chat-input')).toBe(input);
});
