import { act, cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import { AgentWorkspaceShell } from './AgentWorkspaceShell';
import { renderWithProviders } from './__tests__/chatTestUtils';
import { useAIChat } from '../../stores/aiChat';
import { useSession } from '../../stores/session';
import { useWorkspaceMode } from '../../stores/workspaceMode';

vi.mock('./FloatingChatButton', () => ({ useAgentChatInvalidationBridge: () => {} }));

afterEach(() => {
  cleanup();
  useAIChat.getState().reset();
});

it('keeps the real composer node when changing modes', () => {
  useAIChat.getState().reset();
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

it('keeps the real composer node mounted when collapsing and expanding the copilot pane', () => {
  useAIChat.getState().reset();
  useSession.getState().reset();
  useWorkspaceMode.setState({ mode: 'copilot', lastReason: 'manualView', initialDecided: true });
  vi.spyOn(useAIChat.getState(), 'init').mockResolvedValue();
  renderWithProviders(<AgentWorkspaceShell><div>workspace</div></AgentWorkspaceShell>);
  const input = screen.getByTestId('ai-chat-input');
  const toggle = screen.getByTestId('ai-chat-copilot-toggle');
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(screen.getByTestId('ai-chat-input')).toBe(input);
  expect(input.closest('.agent-shell__chat-body')).toHaveAttribute('inert');
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByTestId('ai-chat-input')).toBe(input);
  expect(input.closest('.agent-shell__chat-body')).not.toHaveAttribute('inert');
});
