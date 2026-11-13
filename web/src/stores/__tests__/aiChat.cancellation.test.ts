import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-cancel'),
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

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function userTexts(): string[] {
  return useAIChat
    .getState()
    .messages.filter((message) => message.kind === 'user')
    .map((message) => (message as { text: string }).text);
}

function sentBody(): Record<string, unknown> {
  const call = mockFetch.mock.calls[0] as unknown as [string, RequestInit];
  return JSON.parse(String(call[1].body)) as Record<string, unknown>;
}

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  mockGetSessionId.mockReturnValue('sess-cancel');
  useAIChat.getState().reset();
});

describe('aiChat store — cancellation during the send revalidation', () => {
  it('aborting while the model is being revalidated never reaches the POST', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);
    expect(mockFetch).not.toHaveBeenCalled();

    useAIChat.getState().abort();
    gate.resolve({ data: single('alpha') });

    await expect(sending).resolves.toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(userTexts()).toEqual([]);
    expect(useAIChat.getState().acceptedDraft).toBeNull();
    expect(useAIChat.getState().streaming).toBe(false);
    expect(useAIChat.getState().sendInFlight).toBe(false);
    expect(useAIChat.getState().notice).toBeNull();
  });

  it('accepts the next send after a cancelled revalidation', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    const cancelled = useAIChat.getState().send('primero');
    await tick();
    useAIChat.getState().abort();
    gate.resolve({ data: single('alpha') });
    await expect(cancelled).resolves.toBe(false);

    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    await expect(useAIChat.getState().send('segundo')).resolves.toBe(true);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ message: 'segundo', model: 'alpha' });
    expect(userTexts()).toEqual(['segundo']);
  });

  it('invalidates a pending send when the store is reset before dispatch', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const sending = useAIChat.getState().send('hola');
    await tick();
    useAIChat.getState().reset();
    gate.resolve({ data: single('alpha') });

    await expect(sending).resolves.toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().messages).toEqual([]);
    expect(useAIChat.getState().sendInFlight).toBe(false);
  });
});

describe('aiChat store — clearing is blocked while a turn is active', () => {
  it('ignores clear while the send revalidation is in flight and keeps the turn intact', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();
    useAIChat.setState({ conversationId: 'conv-pending' });

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    await useAIChat.getState().clearConversation();

    expect(mockDelete).not.toHaveBeenCalled();
    expect(useAIChat.getState().conversationId).toBe('conv-pending');

    gate.resolve({ data: single('alpha') });
    await expect(sending).resolves.toBe(true);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ conversation_id: 'conv-pending' });
    expect(useAIChat.getState().conversationId).toBe('conv-pending');
  });

  it('ignores clear while the agent stream is open and keeps the history', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta', 'detected');
    useAIChat.setState({ conversationId: 'conv-stream' });

    const pending = openNdjsonResponse();
    mockFetch.mockResolvedValueOnce(pending.response);

    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(useAIChat.getState().streaming).toBe(true);

    await useAIChat.getState().clearConversation();

    expect(mockDelete).not.toHaveBeenCalled();
    expect(useAIChat.getState().conversationId).toBe('conv-stream');
    expect(userTexts()).toEqual(['hola']);

    pending.close();
    await expect(sending).resolves.toBe(true);
    expect(useAIChat.getState().streaming).toBe(false);
  });

  it('still clears the conversation when no turn is active', async () => {
    useAIChat.setState({
      conversationId: 'conv-idle',
      messages: [{ kind: 'user', id: 'u1', text: 'hola' }],
    });
    mockDelete.mockResolvedValueOnce({ deleted: true });

    await useAIChat.getState().clearConversation();

    expect(mockDelete).toHaveBeenCalledTimes(1);
    expect(mockDelete.mock.calls[0][0]).toMatch(/\/ai\/chat\/conversation\/conv-idle$/);
    expect(useAIChat.getState().conversationId).toBeNull();
    expect(useAIChat.getState().messages).toEqual([]);
    expect(useAIChat.getState().notice).toMatchObject({
      key: 'aiChat.notice.cleared',
    });
  });
});

describe('aiChat store — sharing the discovery refresh with a blocked send', () => {
  it('waits for the refresh already in flight instead of failing on the stale block', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    expect(useAIChat.getState().notice).toBeNull();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const refresh = useAIChat.getState().loadProviderState();
    await tick();
    const sending = useAIChat.getState().send('hola');
    await tick();

    expect(useAIChat.getState().sendInFlight).toBe(true);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice).toBeNull();

    gate.resolve({ data: single('alpha') });
    await refresh;

    await expect(sending).resolves.toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ message: 'hola', model: 'alpha' });
    expect(useAIChat.getState().notice).toBeNull();
  });

  it('keeps the block when the shared refresh also leaves no usable model', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValue(ndjsonResponse());

    const refresh = useAIChat.getState().loadProviderState();
    await tick();
    const sending = useAIChat.getState().send('hola');
    await tick();
    gate.resolve({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await refresh;

    await expect(sending).resolves.toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice).toMatchObject({
      severity: 'warning',
      key: 'aiChat.notice.models_required',
    });
  });
});

describe('aiChat store — aborting the revalidation releases the turn promptly', () => {
  function ndjsonResponseWithConversation(conversationId: string): Response {
    const lines = [
      '{"type":"text","content":"viejo"}',
      '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
    ];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        for (const line of lines) {
          controller.enqueue(encoder.encode(`${line}\n`));
        }
        controller.close();
      },
    });
    return new Response(stream, {
      status: 200,
      headers: {
        'Content-Type': 'application/x-ndjson',
        'X-Conversation-Id': conversationId,
      },
    });
  }

  async function settledWithin(
    promise: Promise<boolean>,
  ): Promise<boolean | 'pending'> {
    return Promise.race([
      promise,
      tick().then(() => 'pending' as const),
    ]);
  }

  it('frees the send slot synchronously and resolves the send without waiting for discovery', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    useAIChat.getState().abort();
    expect(useAIChat.getState().sendInFlight).toBe(false);

    await expect(settledWithin(sending)).resolves.toBe(false);
    gate.resolve({ data: single('alpha') });
    await sending;

    expect(mockFetch).not.toHaveBeenCalled();
    expect(userTexts()).toEqual([]);
    expect(useAIChat.getState().acceptedDraft).toBeNull();
    expect(useAIChat.getState().streaming).toBe(false);
  });

  it('never publishes a response that arrives after the turn was aborted', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    const posted = deferred<Response>();
    mockFetch.mockImplementationOnce(() => posted.promise);

    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(useAIChat.getState().streaming).toBe(true);

    useAIChat.getState().abort();
    posted.resolve(ndjsonResponseWithConversation('conv-stale'));

    await expect(sending).resolves.toBe(false);
    expect(useAIChat.getState().conversationId).toBeNull();
    expect(userTexts()).toEqual(['hola']);
    expect(
      useAIChat
        .getState()
        .messages.some((message) => message.kind === 'agent'),
    ).toBe(false);
    expect(useAIChat.getState().notice).toBeNull();
    expect(useAIChat.getState().streaming).toBe(false);
    expect(useAIChat.getState().abortController).toBeNull();
  });

  it('keeps the send slot of a newer turn when the cancelled one settles', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);

    const first = useAIChat.getState().send('primero');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    useAIChat.getState().abort();
    expect(useAIChat.getState().sendInFlight).toBe(false);

    const pendingStream = openNdjsonResponse();
    mockFetch.mockResolvedValueOnce(pendingStream.response);
    const second = useAIChat.getState().send('segundo');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    gate.resolve({ data: single('alpha') });
    await tick();
    await tick();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ message: 'segundo' });
    expect(useAIChat.getState().streaming).toBe(true);
    expect(useAIChat.getState().sendInFlight).toBe(true);
    expect(userTexts()).toEqual(['segundo']);

    pendingStream.close();
    await expect(second).resolves.toBe(true);
    await expect(first).resolves.toBe(false);
    expect(useAIChat.getState().sendInFlight).toBe(false);
  });

  it('leaves the discovery shared with another request running after the abort', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);

    const refresh = useAIChat.getState().loadProviderState();
    await tick();
    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    useAIChat.getState().abort();
    await expect(settledWithin(sending)).resolves.toBe(false);

    gate.resolve({ data: single('alpha') });
    await refresh;

    expect(useAIChat.getState().providerState?.chat_models?.selected).toBe(
      'alpha',
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('passes an abortable signal to the discovery and cancels it on reset', async () => {
    const gate = deferred<{ data: AIProvidersState }>();
    let captured: AbortSignal | undefined;
    mockGet.mockImplementationOnce(
      (_path: string, config?: { signal?: AbortSignal }) => {
        captured = config?.signal;
        return gate.promise;
      },
    );

    const refresh = useAIChat.getState().loadProviderState();
    await tick();
    expect(captured).toBeInstanceOf(AbortSignal);

    useAIChat.getState().reset();
    expect(captured?.aborted).toBe(true);

    gate.resolve({ data: single('alpha') });
    await refresh;

    expect(useAIChat.getState().providerState).toBeNull();
    expect(useAIChat.getState().providerStateLoaded).toBe(false);
    expect(useAIChat.getState().providerStateLoading).toBe(false);
    expect(useAIChat.getState().notice).toBeNull();
  });
});
