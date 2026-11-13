import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-models'),
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

const TEXT_DONE = [
  '{"type":"text","content":"listo"}',
  '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
];

function ndjsonResponse(): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const line of TEXT_DONE) controller.enqueue(encoder.encode(`${line}\n`));
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

function sentBody(): Record<string, unknown> {
  const call = mockFetch.mock.calls[0] as unknown as [string, RequestInit];
  return JSON.parse(String(call[1].body)) as Record<string, unknown>;
}

function sentBodies(): Array<Record<string, unknown>> {
  return mockFetch.mock.calls.map((call) =>
    JSON.parse(String((call as unknown as [string, RequestInit])[1].body)),
  );
}

function single(id: string, source: 'auto' | 'override' = 'auto'): AIProvidersState {
  return providersBody({
    chat_model: id,
    chat_models: modelsState([id], { selected: id, selected_source: source }),
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

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  mockGetSessionId.mockReturnValue('sess-models');
  useAIChat.getState().reset();
});

describe('aiChat store — detected loaded models', () => {
  it('sends the single detected instance id without any manual input', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha:2',
        chat_models: modelsState(['alpha:2'], {
          selected: 'alpha:2',
          selected_source: 'auto',
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha:2',
        chat_models: modelsState(['alpha:2'], {
          selected: 'alpha:2',
          selected_source: 'auto',
        }),
      }),
    });
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    await useAIChat.getState().send('hola');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({
      message: 'hola',
      provider: 'lmstudio',
      model: 'alpha:2',
    });
  });

  it('waits for the discovery request already in flight instead of using the stale state', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const refresh = useAIChat.getState().loadProviderState();
    await tick();
    const sending = useAIChat.getState().send('hola');
    await tick();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    gate.resolve({ data: single('alpha') });
    await refresh;

    await expect(sending).resolves.toBe(true);
    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ message: 'hola', model: 'alpha' });
    expect(sentBody().model).toBe(
      useAIChat.getState().providerState?.chat_models?.selected,
    );
  });

  it('joins the initial discovery on the first send instead of demanding a placeholder model', async () => {
    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    const loading = useAIChat.getState().loadProviderState();
    await tick();

    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    const sending = useAIChat.getState().send('hola');
    await tick();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice).toBeNull();

    gate.resolve({ data: single('alpha') });
    await loading;

    await expect(sending).resolves.toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ message: 'hola', model: 'alpha' });
  });

  it('does not send when the detected auto model changed during the send', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();
    mockGet.mockResolvedValueOnce({ data: single('beta') });
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    const accepted = await useAIChat.getState().send('hola');

    expect(accepted).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(userTexts()).toEqual([]);
    expect(useAIChat.getState().notice).toMatchObject({
      severity: 'warning',
      key: 'aiChat.notice.model_changed',
      values: { previous: 'alpha', current: 'beta' },
    });
    expect(useAIChat.getState().providerState?.chat_models?.selected).toBe(
      'beta',
    );
  });

  it('sends the confirmed model on the next send and clears the change notice', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();
    mockGet.mockResolvedValueOnce({ data: single('beta') });
    await useAIChat.getState().send('hola');
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.model_changed');

    mockGet.mockResolvedValueOnce({ data: single('beta') });
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    await expect(useAIChat.getState().send('hola')).resolves.toBe(true);

    expect(sentBody()).toMatchObject({ message: 'hola', model: 'beta' });
    expect(useAIChat.getState().notice).toBeNull();
    expect(userTexts()).toEqual(['hola']);
  });

  it('keeps asking for confirmation through successive model swaps', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();
    mockFetch.mockResolvedValue(ndjsonResponse());

    mockGet.mockResolvedValueOnce({ data: single('beta') });
    expect(await useAIChat.getState().send('hola')).toBe(false);
    expect(useAIChat.getState().notice?.values).toEqual({
      previous: 'alpha',
      current: 'beta',
    });

    mockGet.mockResolvedValueOnce({ data: single('gamma') });
    expect(await useAIChat.getState().send('hola')).toBe(false);
    expect(useAIChat.getState().notice?.values).toEqual({
      previous: 'beta',
      current: 'gamma',
    });

    mockGet.mockResolvedValueOnce({ data: single('gamma') });
    expect(await useAIChat.getState().send('hola')).toBe(true);

    expect(sentBodies().map((body) => body.model)).toEqual(['gamma']);
    expect(userTexts()).toEqual(['hola']);
  });

  it('rejects a second send synchronously while the revalidation is in flight', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockImplementation(async () => ndjsonResponse());

    const first = useAIChat.getState().send('uno');
    await tick();
    expect(useAIChat.getState().sendInFlight).toBe(true);

    await expect(useAIChat.getState().send('dos')).resolves.toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(userTexts()).toEqual([]);

    gate.resolve({ data: single('alpha') });
    await expect(first).resolves.toBe(true);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBodies().map((body) => body.message)).toEqual(['uno']);
    expect(userTexts()).toEqual(['uno']);
  });

  it('rejects two sends fired back to back before the first one awaits', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    mockFetch.mockImplementation(async () => ndjsonResponse());

    const first = useAIChat.getState().send('uno');
    const second = useAIChat.getState().send('dos');

    await expect(second).resolves.toBe(false);
    await expect(first).resolves.toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBodies().map((body) => body.message)).toEqual(['uno']);
  });

  it('refuses a pick that disappears during a concurrent refresh', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta', 'detected');

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValue(ndjsonResponse());

    const refresh = useAIChat.getState().loadProviderState();
    await tick();
    const sending = useAIChat.getState().send('hola');
    await tick();
    expect(mockFetch).not.toHaveBeenCalled();

    gate.resolve({ data: single('alpha') });
    await refresh;

    await expect(sending).resolves.toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice).toMatchObject({
      key: 'aiChat.notice.model_changed',
      values: { previous: 'beta', current: 'alpha' },
    });
  });

  it('shares a single discovery request between concurrent callers', async () => {
    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);

    const first = useAIChat.getState().loadProviderState();
    const second = useAIChat.getState().loadProviderState();
    expect(mockGet).toHaveBeenCalledTimes(1);

    gate.resolve({ data: single('alpha') });
    await Promise.all([first, second]);

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(useAIChat.getState().providerState?.chat_models?.selected).toBe(
      'alpha',
    );
    expect(useAIChat.getState().providerStateLoading).toBe(false);
  });

  it('clears a stale model notice after a successful refresh', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    mockGet.mockRejectedValueOnce(new Error('offline'));
    await useAIChat.getState().send('hola');
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.models_unreachable',
    );
    expect(useAIChat.getState().providerStateError).toBe(true);

    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().providerStateError).toBe(false);
    expect(useAIChat.getState().notice).toBeNull();
  });

  it('clears the choose-a-model notice after a successful refresh', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    await useAIChat.getState().send('hola');
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.models_required',
    );

    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().notice).toBeNull();
  });

  it('blocks the send when the revalidated model set is ambiguous', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: providersBody({
          chat_model: 'alpha',
          chat_models: modelsState(['alpha'], {
            selected: 'alpha',
            selected_source: 'auto',
          }),
        }),
      })
      .mockResolvedValueOnce({
        data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
      });
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.models_required',
    );
  });

  it('blocks the send when revalidation finds no loaded model', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: providersBody({
          chat_model: 'alpha',
          chat_models: modelsState(['alpha'], {
            selected: 'alpha',
            selected_source: 'auto',
          }),
        }),
      })
      .mockResolvedValueOnce({
        data: providersBody({ chat_models: modelsState([]) }),
      });
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.models_none');
  });

  it('blocks the send when the revalidation request fails', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: providersBody({
          chat_model: 'alpha',
          chat_models: modelsState(['alpha'], {
            selected: 'alpha',
            selected_source: 'auto',
          }),
        }),
      })
      .mockRejectedValueOnce(new Error('offline'));
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.models_unreachable',
    );
  });

  it('does not revalidate a model the user explicitly picked', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta', 'detected');
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    await useAIChat.getState().send('hola');

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(sentBody()).toMatchObject({ model: 'beta' });
  });

  it('blocks until an explicit choice when several models are loaded', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState(['alpha', 'beta']),
      }),
    });
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.models_required');

    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    useAIChat.getState().setSessionModel('beta');
    await useAIChat.getState().send('hola');
    expect(sentBody()).toMatchObject({ model: 'beta' });
  });

  it('never sends a session value outside the detected list', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('ghost');

    await useAIChat.getState().send('hola');

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.models_required');
  });

  it('reports zero loaded models honestly and keeps the manual escape hatch', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.models_none');

    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    useAIChat.getState().setSessionModel('  manual-id  ');
    await useAIChat.getState().send('hola');
    expect(sentBody()).toMatchObject({ model: 'manual-id' });
  });

  it('reports a disconnected LM Studio and still allows a manual id', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState([], {
          status: 'unavailable',
          source: null,
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.models_unreachable',
    );

    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    useAIChat.getState().setSessionModel('typed-model');
    await useAIChat.getState().send('hola');
    expect(sentBody()).toMatchObject({ model: 'typed-model' });
  });

  it('honours the server override over discovery and the session value', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'server-pinned',
        chat_models: modelsState(['alpha', 'beta'], {
          selected: 'server-pinned',
          selected_source: 'override',
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta');
    mockFetch.mockResolvedValueOnce(ndjsonResponse());

    await useAIChat.getState().send('hola');

    expect(sentBody()).toMatchObject({ model: 'server-pinned' });
  });

  it('keeps a still-valid choice across a refresh and clears a stale one', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta');

    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['gamma', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    expect(useAIChat.getState().sessionModel).toBe('beta');

    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['gamma', 'delta']) }),
    });
    await useAIChat.getState().loadProviderState();
    expect(useAIChat.getState().sessionModel).toBe('');

    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.models_required');
  });

  it('clears a detected choice when a refresh reports an empty load set', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta', 'detected');

    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().sessionModel).toBe('');
    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.models_none');
  });

  it('keeps a valid manual entry when a refresh reports an empty load set', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('typed-model');

    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().sessionModel).toBe('typed-model');
    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    await useAIChat.getState().send('hola');
    expect(sentBody()).toMatchObject({ model: 'typed-model' });
  });

  it('clears a detected choice when discovery becomes unavailable', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta', 'detected');

    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState([], { status: 'unavailable', source: null }),
      }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().sessionModel).toBe('');
    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.models_unreachable',
    );
  });

  it('keeps the last known state when a refresh fails and recovers afterwards', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();

    mockGet.mockRejectedValueOnce(new Error('offline'));
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().providerStateLoaded).toBe(true);
    expect(useAIChat.getState().providerState?.chat_models?.selected).toBe(
      'alpha',
    );
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.providers_unavailable',
    );

    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'beta',
        chat_models: modelsState(['beta'], {
          selected: 'beta',
          selected_source: 'auto',
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().providerState?.chat_models?.selected).toBe(
      'beta',
    );
    expect(useAIChat.getState().providerStateError).toBe(false);
  });

  it('recovers from an initial provider failure on the next refresh', async () => {
    mockGet.mockRejectedValueOnce(new Error('offline'));
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().providerStateLoaded).toBe(true);
    expect(useAIChat.getState().providerState).toBeNull();
    expect(useAIChat.getState().providerStateError).toBe(true);

    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().providerState?.chat_models?.selected).toBe(
      'alpha',
    );
    expect(useAIChat.getState().providerStateError).toBe(false);
    expect(useAIChat.getState().notice).toBeNull();
  });

  it('switches from a multi-model pick to the new single auto model on refresh', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    await useAIChat.getState().loadProviderState();
    useAIChat.getState().setSessionModel('beta');

    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
        }),
      }),
    });
    await useAIChat.getState().loadProviderState();

    expect(useAIChat.getState().sessionModel).toBe('');
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
        }),
      }),
    });
    mockFetch.mockResolvedValueOnce(ndjsonResponse());
    await useAIChat.getState().send('hola');
    expect(sentBody()).toMatchObject({ model: 'alpha' });
  });

  it('keeps the legacy placeholder flow when the server omits chat_models', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_model: 'loaded-model' }),
    });
    await useAIChat.getState().loadProviderState();

    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.placeholder_model_required',
    );
  });
});
