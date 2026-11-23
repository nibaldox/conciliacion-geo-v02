import { beforeEach, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { ChatPanel } from '../ChatPanel';
import { useAIChat } from '../../../stores/aiChat';
import { renderWithProviders } from './chatTestUtils';

vi.mock('../MarkdownMessage', () => ({
  MarkdownMessage: ({ content, chips }: { content: string; chips?: boolean }) => <div data-testid="markdown-props" data-chips={String(chips)}>{content}</div>,
}));
vi.mock('../../../api/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/hooks')>();
  return { ...actual, useSections: () => ({ data: [], isLoading: false }) };
});
vi.mock('../../../api/client', () => ({ default: { get: vi.fn(async () => ({ data: {} })), post: vi.fn(), defaults: { baseURL: '/api/v1' } }, getSessionId: () => 'test' }));

beforeEach(() => {
  useAIChat.getState().reset();
  vi.spyOn(useAIChat.getState(), 'init').mockResolvedValue();
  useAIChat.setState({ messages: [{ kind: 'agent', id: 'a', text: 'Respuesta' }, { kind: 'user', id: 'u', text: 'Pregunta' }] });
});

it('activa chips solo en mensajes del agente embebidos', () => {
  const { unmount } = renderWithProviders(<ChatPanel presentation="embedded" />);
  expect(screen.getByTestId('markdown-props')).toHaveAttribute('data-chips', 'true');
  expect(screen.getAllByTestId('markdown-props')).toHaveLength(1);
  unmount();
  renderWithProviders(<ChatPanel presentation="floating" />);
  expect(screen.getByTestId('markdown-props')).toHaveAttribute('data-chips', 'undefined');
});
