import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-exclusion'),
  mockFetch: vi.fn(),
}));

vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import { useAIChat } from '../aiChat';
import type { AIProvidersState } from '../../api/aiChat';

function ndjsonResponse(): Response {
  const lines = [
    '{"type":"text","content":"listo"}',
    '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
  ];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'application/x-ndjson' },
  });
}

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
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const USER_MESSAGE = { kind: 'user' as const, id: 'u1', text: 'hola' };

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  mockGetSessionId.mockReturnValue('sess-exclusion');
  mockGet.mockResolvedValue({ data: single('alpha') });
  useAIChat.getState().reset();
});

describe('aiChat store — clear/send mutual exclusion', () => {
  it('marks clearing synchronously and blocks a send without touching messages or draft', async () => {
    await useAIChat.getState().loadProviderState();
    useAIChat.setState({
      conversationId: 'conv-clearing',
      messages: [USER_MESSAGE],
    });
    const deletion = deferred<{ data: { deleted: boolean } }>();
    mockDelete.mockImplementationOnce(() => deletion.promise);

    const clearing = useAIChat.getState().clearConversation();

    expect(useAIChat.getState().clearing).toBe(true);
    expect(mockDelete).toHaveBeenCalledTimes(1);

    await expect(useAIChat.getState().send('nuevo')).resolves.toBe(false);

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().messages).toEqual([USER_MESSAGE]);
    expect(useAIChat.getState().acceptedDraft).toBeNull();
    expect(useAIChat.getState().conversationId).toBe('conv-clearing');

    deletion.resolve({ data: { deleted: true } });
    await clearing;

    expect(useAIChat.getState().clearing).toBe(false);
    expect(useAIChat.getState().messages).toEqual([]);
    expect(useAIChat.getState().conversationId).toBeNull();
    expect(useAIChat.getState().notice).toMatchObject({
      key: 'aiChat.notice.cleared',
    });
  });

  it('keeps the conversation and its messages when the DELETE fails, and clears busy', async () => {
    await useAIChat.getState().loadProviderState();
    useAIChat.setState({
      conversationId: 'conv-failure',
      messages: [USER_MESSAGE],
    });
    mockDelete.mockRejectedValueOnce(new Error('delete_failed'));

    await useAIChat.getState().clearConversation();

    expect(useAIChat.getState().clearing).toBe(false);
    expect(useAIChat.getState().conversationId).toBe('conv-failure');
    expect(useAIChat.getState().messages).toEqual([USER_MESSAGE]);
    expect(useAIChat.getState().notice).toBeNull();

    mockGet.mockResolvedValue({ data: single('alpha') });
    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    await expect(useAIChat.getState().send('despues')).resolves.toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('ignores a second clear while the DELETE is still in flight', async () => {
    useAIChat.setState({
      conversationId: 'conv-double',
      messages: [USER_MESSAGE],
    });
    const deletion = deferred<{ data: { deleted: boolean } }>();
    mockDelete.mockImplementationOnce(() => deletion.promise);

    const first = useAIChat.getState().clearConversation();
    await useAIChat.getState().clearConversation();

    expect(mockDelete).toHaveBeenCalledTimes(1);

    deletion.resolve({ data: { deleted: true } });
    await first;

    expect(useAIChat.getState().conversationId).toBeNull();
    expect(useAIChat.getState().messages).toEqual([]);
  });

  it('blocks approve and deny while the clear request is in flight', async () => {
    await useAIChat.getState().loadProviderState();
    useAIChat.setState({
      conversationId: 'conv-pending',
      pendingConfirmation: {
        invocationId: 'inv_1',
        name: 'generate_sections_manual',
        argsSummary: 'Reemplaza 2 secciones',
      },
    });
    const deletion = deferred<{ data: { deleted: boolean } }>();
    mockDelete.mockImplementationOnce(() => deletion.promise);

    const clearing = useAIChat.getState().clearConversation();
    expect(useAIChat.getState().clearing).toBe(true);

    await useAIChat.getState().approve();
    await useAIChat.getState().deny();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().streaming).toBe(false);

    deletion.resolve({ data: { deleted: true } });
    await clearing;

    expect(useAIChat.getState().pendingConfirmation).toBeNull();
  });
});
