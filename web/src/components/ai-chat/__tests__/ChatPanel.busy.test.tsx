import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-panel-busy'),
  mockFetch: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: (...args: unknown[]) => mockDelete(...args),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import type { AIProvidersState } from '../../../api/aiChat';
import { useAIChat } from '../../../stores/aiChat';
import { ChatPanel } from '../ChatPanel';
import {
  CHAT_TEXT_DONE,
  initChatI18n,
  makeNdjsonResponse,
  renderWithProviders,
} from './chatTestUtils';

function providersBody(overrides: Partial<AIProvidersState> = {}): AIProvidersState {
  return {
    providers: ['lmstudio'],
    supports_tool_calls: { lmstudio: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'loaded-model',
    ...overrides,
  };
}

function modelsState(
  ids: string[],
  overrides: Partial<NonNullable<AIProvidersState['chat_models']>> = {},
): NonNullable<AIProvidersState['chat_models']> {
  return {
    status: 'ok',
    source: 'v1',
    models: ids.map((id) => ({ id, label: id, tool_use: true })),
    selected: null,
    selected_source: null,
    ...overrides,
  };
}

function single(id: string): AIProvidersState {
  return providersBody({
    chat_model: id,
    chat_models: modelsState([id], { selected: id, selected_source: 'auto' }),
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function openNdjsonResponse(): { response: Response; close: () => void } {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
      c.enqueue(encoder.encode('{"type":"text","content":"parcial"}\n'));
    },
  });
  return {
    response: new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'application/x-ndjson' },
    }),
    close() {
      controller.enqueue(
        encoder.encode(
          '{"type":"done","finish_reason":"stop","usage":null,"cached":false}\n',
        ),
      );
      controller.close();
    },
  };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

const noop = () => undefined;

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  initChatI18n();
  useAIChat.getState().reset();
});

describe('ChatPanel — busy controls during the send revalidation', () => {
  it('disables Limpiar, shows Detener and blocks the refresh while revalidating', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha'),
    );

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(makeNdjsonResponse(CHAT_TEXT_DONE));

    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    await tick();

    expect(screen.getByTestId('ai-chat-clear')).toBeDisabled();
    expect(screen.getByTestId('ai-chat-models-refresh')).toBeDisabled();
    expect(screen.getByTestId('ai-chat-stop')).toBeInTheDocument();
    expect(screen.queryByTestId('ai-chat-send')).toBeNull();
    expect(input).toHaveValue('hola');

    gate.resolve({ data: single('alpha') });

    await waitFor(() => expect(input).toHaveValue(''));
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-clear')).toBeEnabled(),
    );
    expect(screen.getByTestId('ai-chat-models-refresh')).toBeEnabled();
    expect(screen.getByTestId('ai-chat-send')).toBeInTheDocument();
  });

  it('cancels the pending revalidation from the Detener button without sending', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha'),
    );

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(makeNdjsonResponse(CHAT_TEXT_DONE));

    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    await tick();

    await userEvent.click(screen.getByTestId('ai-chat-stop'));
    gate.resolve({ data: single('alpha') });

    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-send')).toBeInTheDocument(),
    );
    expect(mockFetch).not.toHaveBeenCalled();
    expect(input).toHaveValue('hola');
    expect(useAIChat.getState().messages).toEqual([]);
  });
});

describe('ChatPanel — busy controls while the conversation is being cleared', () => {
  it('shows busy, blocks sending and keeps the draft while the DELETE is in flight', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha'),
    );

    useAIChat.setState({
      conversationId: 'conv-ui',
      messages: [{ kind: 'user', id: 'u1', text: 'hola' }],
    });

    const deletion = deferred<{ data: { deleted: boolean } }>();
    mockDelete.mockImplementationOnce(() => deletion.promise);

    await userEvent.type(input, 'borrador');
    await userEvent.click(screen.getByTestId('ai-chat-clear'));
    await userEvent.click(screen.getByTestId('ai-chat-clear'));

    expect(screen.getByTestId('ai-chat-panel')).toHaveAttribute(
      'aria-busy',
      'true',
    );
    expect(screen.getByTestId('ai-chat-clear')).toBeDisabled();
    const sendButton = screen.getByTestId('ai-chat-send');
    expect(sendButton).toBeDisabled();
    expect(input).toHaveValue('borrador');
    expect(screen.getByText('hola')).toBeInTheDocument();

    await userEvent.click(sendButton);
    expect(mockFetch).not.toHaveBeenCalled();

    deletion.resolve({ data: { deleted: true } });
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-clear')).toBeEnabled(),
    );
    expect(screen.queryByText('hola')).toBeNull();
    expect(input).toHaveValue('borrador');
  });
});

describe('ChatPanel — busy controls while the agent streams', () => {
  it('disables Limpiar and the model selector while the stream is open', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const select = await screen.findByTestId('ai-chat-model-select');
    await userEvent.selectOptions(select, 'beta');
    const input = screen.getByTestId('ai-chat-input');

    const pending = openNdjsonResponse();
    mockFetch.mockResolvedValueOnce(pending.response);

    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    await screen.findByTestId('ai-chat-streaming-indicator');

    expect(screen.getByTestId('ai-chat-clear')).toBeDisabled();
    expect(screen.getByTestId('ai-chat-model-select')).toBeDisabled();
    expect(screen.getByTestId('ai-chat-stop')).toBeInTheDocument();

    pending.close();

    await waitFor(() =>
      expect(screen.queryByTestId('ai-chat-streaming-indicator')).toBeNull(),
    );
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-clear')).toBeEnabled(),
    );
    expect(screen.getByTestId('ai-chat-model-select')).toBeEnabled();
  });
});
