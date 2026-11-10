import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentEvent } from '../../api/agentChat';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-store'),
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

import { useAIChat, historyToChatMessages, type ChatMessage } from '../aiChat';
import type { AIProvidersState } from '../../api/aiChat';

function providersBody(overrides: Partial<AIProvidersState> = {}): AIProvidersState {
  return {
    providers: ['ollama', 'lmstudio', 'openai'],
    supports_tool_calls: { ollama: false, lmstudio: true, openai: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'qwen3-32b',
    ...overrides,
  };
}

function ndjsonResponse(
  lines: string[],
  { conversationId }: { conversationId?: string } = {},
): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`));
      controller.close();
    },
  });
  const headers: Record<string, string> = {
    'Content-Type': 'application/x-ndjson',
  };
  if (conversationId) headers['X-Conversation-Id'] = conversationId;
  return new Response(stream, { status: 200, headers });
}

function hangingResponse(): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        new TextEncoder().encode('{"type":"text","content":"primera"}\n'),
      );
    },
    pull() {
      return new Promise<void>(() => undefined);
    },
  });
  return new Response(stream, { status: 200 });
}

const TEXT_DONE = [
  '{"type":"text","content":"Hola, ¿en qué te ayudo?"}',
  '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
];

const CONFIRMATION_STREAM = [
  '{"type":"text","content":"Voy a reemplazar las secciones."}',
  '{"type":"tool_call","invocation_id":"inv_1","name":"generate_sections_manual","args":{},"requires_confirmation":true}',
  '{"type":"confirmation_required","invocation_id":"inv_1","name":"generate_sections_manual","args_summary":"Reemplaza 2 secciones"}',
  '{"type":"done","finish_reason":"confirmation_required","usage":null,"cached":false}',
];

function lastMessage(): ChatMessage | undefined {
  const messages = useAIChat.getState().messages;
  return messages[messages.length - 1];
}

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  mockGetSessionId.mockReturnValue('sess-store');
  useAIChat.getState().reset();
});

describe('aiChat store — provider state and gating', () => {
  it('loadProviderState stores the /ai/providers body', async () => {
    mockGet.mockResolvedValueOnce({ data: providersBody() });
    await useAIChat.getState().loadProviderState();
    expect(useAIChat.getState().providerState).toEqual(providersBody());
    expect(useAIChat.getState().providerStateLoaded).toBe(true);
  });

  it('send is blocked with an explicit notice when chat is disabled', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_enabled: false }),
    });
    await useAIChat.getState().loadProviderState();
    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.chat_disabled');
    expect(useAIChat.getState().messages).toHaveLength(0);
  });

  it('send is blocked with a notice when the provider lacks tool calls', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_provider: 'ollama',
        supports_tool_calls: { ollama: false, lmstudio: true },
      }),
    });
    await useAIChat.getState().loadProviderState();
    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.provider_no_tools');
  });

  it('placeholder model blocks send until a session-only model is set', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_model: 'loaded-model' }),
    });
    await useAIChat.getState().loadProviderState();
    await useAIChat.getState().send('hola');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.placeholder_model_required',
    );
    mockFetch.mockResolvedValueOnce(ndjsonResponse(TEXT_DONE, { conversationId: 'conv_p' }));
    useAIChat.getState().setSessionModel('  qwen3-32b  ');
    await useAIChat.getState().send('hola');
    const [url, init] = mockFetch.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe('/api/v1/ai/chat');
    expect(JSON.parse(String(init.body))).toMatchObject({
      message: 'hola',
      provider: 'lmstudio',
      model: 'qwen3-32b',
    });
  });
});

describe('aiChat store — send and stream consumption', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ data: providersBody() });
    return useAIChat.getState().loadProviderState();
  });

  it('streams text events into presentation messages and stores the conversation id', async () => {
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse(TEXT_DONE, { conversationId: 'conv_abc' }),
    );
    await useAIChat.getState().send('hola agente');
    const kinds = useAIChat.getState().messages.map((m) => m.kind);
    expect(kinds).toEqual(['user', 'agent']);
    expect(lastMessage()).toMatchObject({
      kind: 'agent',
      text: 'Hola, ¿en qué te ayudo?',
    });
    expect(useAIChat.getState().conversationId).toBe('conv_abc');
    expect(useAIChat.getState().streaming).toBe(false);
    expect(window.localStorage.getItem('conciliacion.aiChat.conversationId.sess-store')).toBe(
      'conv_abc',
    );
  });

  it('duplicate-send guard: a second send while streaming is ignored', async () => {
    mockFetch.mockImplementationOnce(async () => hangingResponse());
    const first = useAIChat.getState().send('mensaje uno');
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(useAIChat.getState().streaming).toBe(true);
    await useAIChat.getState().send('mensaje dos');
    expect(mockFetch).toHaveBeenCalledTimes(1);
    useAIChat.getState().abort();
    await first;
    expect(useAIChat.getState().messages.filter((m) => m.kind === 'user')).toHaveLength(1);
  });

  it('malformed NDJSON lines never crash the reader', async () => {
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse([
        '<<<broken>>>',
        '{"type":"text","content":"ok"}',
        '{"type":"nope"}',
        '',
        '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
      ]),
    );
    await useAIChat.getState().send('hola');
    expect(useAIChat.getState().messages.map((m) => m.kind)).toEqual([
      'user',
      'agent',
    ]);
  });

  it('continues an existing conversation via conversation_id', async () => {
    window.localStorage.setItem(
      'conciliacion.aiChat.conversationId.sess-store',
      'conv_kept',
    );
    useAIChat.getState().reset();
    mockFetch.mockRejectedValueOnce(new TypeError('history offline'));
    await useAIChat.getState().init();
    expect(useAIChat.getState().conversationId).toBe('conv_kept');
    mockFetch.mockResolvedValueOnce(ndjsonResponse(TEXT_DONE));
    await useAIChat.getState().send('otra vez');
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const [, init] = mockFetch.mock.calls[1] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body)).conversation_id).toBe('conv_kept');
  });

  it('aborts mid-stream without an error notice', async () => {
    mockFetch.mockImplementationOnce(async () => hangingResponse());
    const pending = useAIChat.getState().send('mensaje');
    await new Promise((resolve) => setTimeout(resolve, 0));
    useAIChat.getState().abort();
    await pending;
    expect(useAIChat.getState().streaming).toBe(false);
    expect(useAIChat.getState().notice).toBeNull();
  });

  it('maps a non-2xx response to the server detail notice', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'sin proveedor' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    await useAIChat.getState().send('hola');
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.request_failed');
    expect(useAIChat.getState().notice?.values).toEqual({ detail: 'sin proveedor' });
    expect(useAIChat.getState().streaming).toBe(false);
  });

  it('localStorage never holds message bodies, invocation ids or tool payloads', async () => {
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse(CONFIRMATION_STREAM, { conversationId: 'conv_sec' }),
    );
    await useAIChat.getState().send('dato sensible coordenadas 10,20');
    const stored = Object.values({ ...window.localStorage }).join('|');
    expect(stored).not.toContain('coordenadas');
    expect(stored).not.toContain('inv_1');
    expect(stored).toBe('conv_sec');
  });
});

describe('aiChat store — confirmation lifecycle', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ data: providersBody() });
    return useAIChat.getState().loadProviderState();
  });

  async function startConfirmation(): Promise<void> {
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse(CONFIRMATION_STREAM, { conversationId: 'conv_c' }),
    );
    await useAIChat.getState().send('reemplaza las secciones');
    expect(useAIChat.getState().pendingConfirmation).toMatchObject({
      invocationId: 'inv_1',
      name: 'generate_sections_manual',
    });
  }

  it('approve sends EXACTLY {invocation_id, approved:true} and consumes the resumed stream', async () => {
    await startConfirmation();
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse([
        '{"type":"tool_call","invocation_id":"inv_1","name":"generate_sections_manual","args":{},"requires_confirmation":true}',
        '{"type":"tool_result","invocation_id":"inv_1","name":"generate_sections_manual","ok":true,"summary":"1 sección creada","duration_ms":10,"error":null}',
        '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
      ]),
    );
    await useAIChat.getState().approve();
    const [url, init] = mockFetch.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/ai/chat/confirm');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(['approved', 'invocation_id']);
    expect(body).toEqual({ invocation_id: 'inv_1', approved: true });
    expect(useAIChat.getState().pendingConfirmation).toBeNull();
    const card = useAIChat
      .getState()
      .messages.find((m) => m.kind === 'confirmation');
    expect(card).toMatchObject({ resolution: 'approved' });
  });

  it('deny sends approved:false and the card stays denied', async () => {
    await startConfirmation();
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse([
        '{"type":"tool_call","invocation_id":"inv_1","name":"generate_sections_manual","args":{},"requires_confirmation":true}',
        '{"type":"tool_result","invocation_id":"inv_1","name":"generate_sections_manual","ok":false,"summary":"","duration_ms":5,"error":"denied_by_user"}',
        '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
      ]),
    );
    await useAIChat.getState().deny();
    const body = JSON.parse(
      String((mockFetch.mock.calls[1] as unknown as [string, RequestInit])[1].body),
    ) as Record<string, unknown>;
    expect(body).toEqual({ invocation_id: 'inv_1', approved: false });
    const card = useAIChat
      .getState()
      .messages.find((m) => m.kind === 'confirmation');
    expect(card).toMatchObject({ resolution: 'denied' });
  });

  it('approve is a no-op without a pending confirmation', async () => {
    await useAIChat.getState().approve();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe('aiChat store — observations, write-tool invalidation, clearing', () => {
  it('addObservation injects a plain-text observation message', () => {
    useAIChat.getState().addObservation('Malla topo cargada: mesh_id=m1');
    expect(lastMessage()).toMatchObject({
      kind: 'observation',
      text: 'Malla topo cargada: mesh_id=m1',
    });
  });

  it('notifies the registered observer after a write-tool tool_result', () => {
    const observer = vi.fn();
    useAIChat.getState().setWriteResultObserver(observer);
    useAIChat.getState().applyAgentEvent({
      type: 'tool_result',
      invocation_id: 'inv_w',
      name: 'run_reconciliation',
      ok: true,
      summary: '78 resultados',
      duration_ms: 42000,
      error: null,
    } as AgentEvent);
    expect(observer).toHaveBeenCalledWith('run_reconciliation');
    useAIChat.getState().applyAgentEvent({
      type: 'tool_result',
      invocation_id: 'inv_r',
      name: 'get_workflow_state',
      ok: true,
      summary: 'estado',
      duration_ms: 10,
      error: null,
    } as AgentEvent);
    expect(observer).toHaveBeenCalledTimes(1);
  });

  it('clearConversation deletes the server conversation and resets to fresh', async () => {
    mockGet.mockResolvedValue({ data: providersBody() });
    await useAIChat.getState().loadProviderState();
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse(TEXT_DONE, { conversationId: 'conv_del' }),
    );
    await useAIChat.getState().send('hola');
    mockDelete.mockResolvedValueOnce({ data: { deleted: true } });
    await useAIChat.getState().clearConversation();
    expect(mockDelete).toHaveBeenCalledWith(
      '/ai/chat/conversation/conv_del',
      expect.anything(),
    );
    expect(useAIChat.getState().conversationId).toBeNull();
    expect(useAIChat.getState().messages).toHaveLength(0);
    expect(useAIChat.getState().pendingConfirmation).toBeNull();
    expect(window.localStorage.getItem('conciliacion.aiChat.conversationId.sess-store')).toBeNull();
    expect(useAIChat.getState().notice?.key).toBe('aiChat.notice.cleared');
  });

  it('clearConversation without a stored conversation still resets locally', async () => {
    await useAIChat.getState().clearConversation();
    expect(mockDelete).not.toHaveBeenCalled();
    expect(useAIChat.getState().messages).toHaveLength(0);
  });

  it('error events surface as a provider-unreachable notice plus the text', () => {
    useAIChat.getState().applyAgentEvent({
      type: 'error',
      content: 'LM Studio no disponible',
    } as AgentEvent);
    expect(useAIChat.getState().notice?.key).toBe(
      'aiChat.notice.provider_unreachable',
    );
    expect(lastMessage()).toMatchObject({ kind: 'agent', text: 'LM Studio no disponible' });
  });
});

describe('aiChat store — history restore after reload (T5)', () => {
  const HISTORY_BODY = {
    exists: true,
    conversation_id: 'conv_rest',
    messages: [
      { role: 'user', content: 'reemplaza las secciones' },
      {
        role: 'assistant',
        content: 'Voy a reemplazar las secciones.',
        tools: ['generate_sections_manual'],
      },
      {
        role: 'tool',
        ok: false,
        summary: 'Operación cancelada por el usuario; no se modificó nada.',
        error: 'denied_by_user',
      },
      { role: 'assistant', content: '¿Quieres que lo intente de nuevo?' },
    ],
    pending: {
      invocation_id: 'inv_rest',
      tool_name: 'run_reconciliation',
      args_summary: 'Reejecutar la conciliación',
    },
  };

  function historyResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  beforeEach(() => {
    mockGet.mockResolvedValue({ data: providersBody() });
    return useAIChat.getState().loadProviderState();
  });

  it('init restores history + pending card and approve posts the restored invocation id', async () => {
    window.localStorage.setItem(
      'conciliacion.aiChat.conversationId.sess-store',
      'conv_rest',
    );
    mockFetch.mockResolvedValueOnce(historyResponse(HISTORY_BODY));
    await useAIChat.getState().init();
    expect(useAIChat.getState().conversationId).toBe('conv_rest');
    expect(
      useAIChat.getState().messages.map((m) => m.kind),
    ).toEqual(['user', 'agent', 'observation', 'agent', 'confirmation']);
    expect(useAIChat.getState().pendingConfirmation).toEqual({
      invocationId: 'inv_rest',
      name: 'run_reconciliation',
      argsSummary: 'Reejecutar la conciliación',
    });
    mockFetch.mockResolvedValueOnce(
      ndjsonResponse([
        '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
      ]),
    );
    await useAIChat.getState().approve();
    const [url, init] = mockFetch.mock.calls[1] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe('/api/v1/ai/chat/confirm');
    expect(JSON.parse(String(init.body))).toEqual({
      invocation_id: 'inv_rest',
      approved: true,
    });
  });

  it('restores denied tool steps as informational observations, not error cards', () => {
    const messages = historyToChatMessages([
      { role: 'user', content: ' genera' },
      { role: 'assistant', content: '', tools: ['generate_sections_auto', 'export_report'] },
      { role: 'tool', ok: false, summary: 'denegada', error: 'denied_by_user' },
      {
        role: 'tool',
        ok: true,
        summary: '{"ok": true, "format": "excel"}',
        error: null,
      },
    ]);
    expect(messages.map((m) => m.kind)).toEqual([
      'user',
      'observation',
      'tool',
    ]);
    const card = messages[2] as Extract<ChatMessage, { kind: 'tool' }>;
    expect(card).toMatchObject({
      name: 'export_report',
      status: 'ok',
      summary: '{"ok": true, "format": "excel"}',
    });
  });

  it('silently starts fresh when the history fetch fails', async () => {
    window.localStorage.setItem(
      'conciliacion.aiChat.conversationId.sess-store',
      'conv_rest',
    );
    mockFetch.mockRejectedValueOnce(new TypeError('network down'));
    await useAIChat.getState().init();
    expect(useAIChat.getState().messages).toHaveLength(0);
    expect(useAIChat.getState().pendingConfirmation).toBeNull();
    expect(useAIChat.getState().notice).toBeNull();
    expect(useAIChat.getState().conversationId).toBe('conv_rest');
  });

  it('clears the stale stored id when the conversation no longer exists', async () => {
    window.localStorage.setItem(
      'conciliacion.aiChat.conversationId.sess-store',
      'conv_gone',
    );
    mockFetch.mockResolvedValueOnce(historyResponse({ exists: false }, 404));
    await useAIChat.getState().init();
    expect(useAIChat.getState().conversationId).toBeNull();
    expect(
      window.localStorage.getItem(
        'conciliacion.aiChat.conversationId.sess-store',
      ),
    ).toBeNull();
    expect(useAIChat.getState().messages).toHaveLength(0);
  });
});

describe('aiChat store — incremental text merging', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ data: providersBody() });
    return useAIChat.getState().loadProviderState();
  });

  function agentMessages(): Extract<ChatMessage, { kind: 'agent' }>[] {
    return useAIChat
      .getState()
      .messages.filter((m): m is Extract<ChatMessage, { kind: 'agent' }> =>
        m.kind === 'agent',
      );
  }

  it('merges two consecutive text events into ONE agent message with a stable id', () => {
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Hola ' });
    const firstId = agentMessages()[0]?.id;
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'mundo' });
    const merged = agentMessages();
    expect(merged).toHaveLength(1);
    expect(merged[0].text).toBe('Hola mundo');
    expect(merged[0].id).toBe(firstId);
    expect(useAIChat.getState().activeTextId).toBe(firstId);
  });

  it('text + tool_call + text yields two agent bubbles around the tool card', () => {
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Consulto el estado.' });
    useAIChat.getState().applyAgentEvent({
      type: 'tool_call',
      invocation_id: 'inv_m',
      name: 'get_workflow_state',
      args: {},
      requires_confirmation: false,
    });
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Listo, el estado es X.' });
    const kinds = useAIChat.getState().messages.map((m) => m.kind);
    expect(kinds).toEqual(['agent', 'tool', 'agent']);
    const agents = agentMessages();
    expect(agents).toHaveLength(2);
    expect(agents[0].text).toBe('Consulto el estado.');
    expect(agents[1].text).toBe('Listo, el estado es X.');
    expect(agents[1].id).not.toBe(agents[0].id);
    expect(useAIChat.getState().activeTextId).toBe(agents[1].id);
  });

  it('done closes the bubble: text + done + text (new turn) → 2 agent messages', () => {
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'primer turno' });
    useAIChat.getState().applyAgentEvent({
      type: 'done',
      finish_reason: 'stop',
      usage: null,
      cached: false,
    });
    expect(useAIChat.getState().activeTextId).toBeNull();
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'segundo turno' });
    const agents = agentMessages();
    expect(agents).toHaveLength(2);
    expect(agents[0].text).toBe('primer turno');
    expect(agents[1].text).toBe('segundo turno');
    expect(agents[1].id).not.toBe(agents[0].id);
  });

  it('tool_result does not resurrect the closed bubble: text after tool_call opens a new bubble', () => {
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'pre-tool' });
    const preToolId = agentMessages()[0]?.id;
    useAIChat.getState().applyAgentEvent({
      type: 'tool_call',
      invocation_id: 'inv_r2',
      name: 'get_workflow_state',
      args: {},
      requires_confirmation: false,
    });
    useAIChat.getState().applyAgentEvent({
      type: 'tool_result',
      invocation_id: 'inv_r2',
      name: 'get_workflow_state',
      ok: true,
      summary: 'estado',
      duration_ms: 10,
      error: null,
    });
    useAIChat.getState().applyAgentEvent({ type: 'text', content: 'post-tool' });
    const agents = agentMessages();
    expect(agents).toHaveLength(2);
    expect(agents[0].id).toBe(preToolId);
    expect(agents[1].text).toBe('post-tool');
  });
});
