import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockGet, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-button'),
  mockFetch: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import { useAIChat } from '../../../stores/aiChat';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { FloatingChatButton, isChatUiEnabled } from '../FloatingChatButton';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

function CaptureClient({ out }: { out: { client?: QueryClient } }) {
  out.client = useQueryClient();
  return null;
}

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  initChatI18n();
  useAIChat.getState().reset();
});

describe('isChatUiEnabled', () => {
  it('is only true for the exact enabled values', () => {
    expect(isChatUiEnabled('true')).toBe(true);
    expect(isChatUiEnabled('1')).toBe(true);
    expect(isChatUiEnabled(undefined)).toBe(false);
    expect(isChatUiEnabled('')).toBe(false);
    expect(isChatUiEnabled('false')).toBe(false);
    expect(isChatUiEnabled('off')).toBe(false);
  });
});

describe('FloatingChatButton', () => {
  it('renders nothing (not even hidden) when VITE_AI_CHAT is not enabled', () => {
    vi.stubEnv('VITE_AI_CHAT', '');
    renderWithProviders(<FloatingChatButton />);
    expect(screen.queryByTestId('ai-chat-button')).toBeNull();
    expect(screen.queryByTestId('ai-chat-panel')).toBeNull();
    vi.unstubAllEnvs();
  });

  it('shows the floating button with an aria-label and opens the panel on click', async () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    mockGet.mockResolvedValue({
      data: {
        providers: ['lmstudio'],
        supports_tool_calls: { lmstudio: true },
        chat_enabled: true,
        chat_provider: 'lmstudio',
        chat_local_only: true,
        chat_model: 'qwen3-32b',
      },
    });
    renderWithProviders(<FloatingChatButton />);
    const button = screen.getByTestId('ai-chat-button');
    expect(button).toHaveAttribute('aria-label', 'Abrir asistente de IA');
    await userEvent.click(button);
    expect(screen.getByTestId('ai-chat-panel')).toBeInTheDocument();
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-label', 'Cerrar asistente');
    await userEvent.click(screen.getByTestId('ai-chat-close'));
    expect(screen.queryByTestId('ai-chat-panel')).toBeNull();
    expect(screen.getByTestId('ai-chat-button')).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-label', 'Abrir asistente de IA');
    vi.unstubAllEnvs();
  });

  it('morphs into the close control: X visible only when open, pet only when closed', async () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    mockGet.mockResolvedValue({
      data: {
        providers: ['lmstudio'],
        supports_tool_calls: { lmstudio: true },
        chat_enabled: true,
        chat_provider: 'lmstudio',
        chat_local_only: true,
        chat_model: 'qwen3-32b',
      },
    });
    renderWithProviders(<FloatingChatButton />);
    const button = screen.getByTestId('ai-chat-button');
    expect(screen.getByTestId('ai-chat-pet-layer')).not.toHaveClass('opacity-0');
    expect(screen.getByTestId('ai-chat-close-icon')).toHaveClass('opacity-0');

    await userEvent.click(button);
    expect(screen.getByTestId('ai-chat-panel')).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat-close-icon')).not.toHaveClass('opacity-0');
    expect(screen.getByTestId('ai-chat-pet-layer')).toHaveClass('opacity-0');

    await userEvent.click(button);
    expect(screen.queryByTestId('ai-chat-panel')).toBeNull();
    expect(screen.getByTestId('ai-chat-close-icon')).toHaveClass('opacity-0');
    expect(screen.getByTestId('ai-chat-pet-layer')).not.toHaveClass('opacity-0');
    vi.unstubAllEnvs();
  });

  it('renders the pet mascot inside the launcher button with the aria-label', () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    renderWithProviders(<FloatingChatButton />);
    const button = screen.getByTestId('ai-chat-button');
    expect(button.querySelector('[data-testid="ai-chat-pet"]')).not.toBeNull();
    expect(button).toHaveAttribute('aria-label', 'Abrir asistente de IA');
    vi.unstubAllEnvs();
  });

  it('shows the unread badge when streaming starts while closed and clears it once opened', async () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    renderWithProviders(<FloatingChatButton />);
    expect(screen.queryByTestId('ai-chat-pet-unread')).toBeNull();
    act(() => {
      useAIChat.setState({ streaming: true });
    });
    expect(screen.getByTestId('ai-chat-pet-unread')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('ai-chat-button'));
    expect(screen.queryByTestId('ai-chat-pet-unread')).toBeNull();
    await userEvent.click(screen.getByTestId('ai-chat-close'));
    expect(screen.queryByTestId('ai-chat-pet-unread')).toBeNull();
    expect(screen.getByTestId('ai-chat-button')).toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it('shows the unread badge when an agent message arrives while closed', () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    renderWithProviders(<FloatingChatButton />);
    act(() => {
      useAIChat.getState().applyAgentEvent({
        type: 'text',
        content: 'La conciliación terminó.',
      });
    });
    expect(screen.getByTestId('ai-chat-pet-unread')).toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it('invalidates the EXACT literal query keys after run_reconciliation', async () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    const captured: { client?: QueryClient } = {};
    renderWithProviders(
      <>
        <CaptureClient out={captured} />
        <FloatingChatButton />
      </>,
    );
    const invalidateSpy = vi.spyOn(captured.client!, 'invalidateQueries');
    useAIChat.getState().applyAgentEvent({
      type: 'tool_result',
      invocation_id: 'inv_w',
      name: 'run_reconciliation',
      ok: true,
      summary: '78 resultados',
      duration_ms: 42000,
      error: null,
    });
    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown }).queryKey,
    );
    expect(invalidatedKeys).toEqual([
      ['process-status'],
      ['results'],
      ['profile'],
    ]);
    vi.unstubAllEnvs();
  });

  it('invalidates exactly [sections] after a section generator', async () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    const captured: { client?: QueryClient } = {};
    renderWithProviders(
      <>
        <CaptureClient out={captured} />
        <FloatingChatButton />
      </>,
    );
    const invalidateSpy = vi.spyOn(captured.client!, 'invalidateQueries');
    useAIChat.getState().applyAgentEvent({
      type: 'tool_result',
      invocation_id: 'inv_s',
      name: 'generate_sections_manual',
      ok: true,
      summary: '2 secciones',
      duration_ms: 12,
      error: null,
    });
    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown }).queryKey,
    );
    expect(invalidatedKeys).toEqual([['sections']]);
    vi.unstubAllEnvs();
  });

  it('export_report results never invalidate any query', async () => {
    vi.stubEnv('VITE_AI_CHAT', 'true');
    const captured: { client?: QueryClient } = {};
    renderWithProviders(
      <>
        <CaptureClient out={captured} />
        <FloatingChatButton />
      </>,
    );
    const invalidateSpy = vi.spyOn(captured.client!, 'invalidateQueries');
    useAIChat.getState().applyAgentEvent({
      type: 'tool_result',
      invocation_id: 'inv_e',
      name: 'export_report',
      ok: true,
      summary: '{"ok": true, "format": "excel"}',
      duration_ms: 3,
      error: null,
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
    vi.unstubAllEnvs();
  });
});
