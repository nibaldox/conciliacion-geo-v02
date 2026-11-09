import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentEvent } from './agentChat';
import {
  conversationIdFromResponse,
  confirmChat,
  deleteConversation,
  downloadExportFile,
  extractExportDownload,
  fetchConversationHistory,
  fetchProviders,
  readAgentEventStream,
  sendChat,
} from './aiChat';

const { mockGet, mockDelete, mockGetSessionId } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-test'),
}));

vi.mock('./client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

const NDJSON_LINES = [
  '{"type":"text","content":"Voy a generar 78 secciones…"}',
  '{"type":"tool_call","invocation_id":"inv_abc","name":"generate_sections_auto","args":{"start":[0.0,0.0]},"requires_confirmation":false}',
  '{"type":"tool_result","invocation_id":"inv_abc","name":"generate_sections_auto","ok":true,"summary":"78 secciones creadas","duration_ms":1200.5,"error":null}',
  '{"type":"confirmation_required","invocation_id":"inv_def","name":"run_reconciliation","args_summary":"Procesar 78 secciones"}',
  '{"type":"error","content":"LM Studio no disponible"}',
  '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
];

function ndjsonResponse(lines: string[], headers: Record<string, string> = {}): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'application/x-ndjson', ...headers },
  });
}

function hangingResponse(onFirstChunk?: () => void): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(encoder.encode('{"type":"text","content":"primera"}\n'));
      onFirstChunk?.();
    },
    pull() {
      return new Promise<void>(() => undefined);
    },
  });
  return new Response(stream, { status: 200 });
}

describe('readAgentEventStream', () => {
  it('parses all six event types in order', async () => {
    const events: AgentEvent[] = [];
    await readAgentEventStream(ndjsonResponse(NDJSON_LINES), (event) => {
      events.push(event);
    });
    expect(events.map((event) => event.type)).toEqual([
      'text',
      'tool_call',
      'tool_result',
      'confirmation_required',
      'error',
      'done',
    ]);
  });

  it('skips empty and malformed lines without failing', async () => {
    const lines = [
      '',
      '   ',
      'not-json-at-all',
      NDJSON_LINES[0],
      '{"type":"unknown_type"}',
      NDJSON_LINES[5],
    ];
    const events: AgentEvent[] = [];
    await readAgentEventStream(ndjsonResponse(lines), (event) => {
      events.push(event);
    });
    expect(events.map((event) => event.type)).toEqual(['text', 'done']);
  });

  it('handles a stream without trailing newline (final flush)', async () => {
    const response = ndjsonResponse([]);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode('{"type":"text","content":"sin salto"}'));
        controller.close();
      },
    });
    const raw = new Response(stream, { status: 200 });
    void response;
    const events: AgentEvent[] = [];
    await readAgentEventStream(raw, (event) => events.push(event));
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: 'text', content: 'sin salto' });
  });

  it('stops mid-stream when the signal aborts', async () => {
    const controller = new AbortController();
    const events: AgentEvent[] = [];
    const pending = readAgentEventStream(
      hangingResponse(),
      (event) => events.push(event),
      { signal: controller.signal },
    );
    await Promise.resolve();
    controller.abort();
    await expect(pending).resolves.toBeUndefined();
    expect(events).toHaveLength(1);
  });
});

describe('sendChat / confirmChat', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ndjsonResponse([])),
    );
  });

  it('posts the strict chat body with the session header', async () => {
    await sendChat(
      { message: 'hola', provider: 'lmstudio', model: 'qwen3-32b', conversation_id: 'conv_1' },
      {},
    );
    const [url, init] = vi.mocked(fetch).mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe('/api/v1/ai/chat');
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['X-Session-ID']).toBe('sess-test');
    expect(JSON.parse(String(init.body))).toEqual({
      message: 'hola',
      provider: 'lmstudio',
      model: 'qwen3-32b',
      conversation_id: 'conv_1',
    });
  });

  it('confirm sends EXACTLY {invocation_id, approved} — nothing else', async () => {
    await confirmChat('inv_abc', true, {});
    const [url, init] = vi.mocked(fetch).mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe('/api/v1/ai/chat/confirm');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(['approved', 'invocation_id']);
    expect(body).toEqual({ invocation_id: 'inv_abc', approved: true });
  });

  it('forwards the abort signal to fetch', async () => {
    const controller = new AbortController();
    await sendChat(
      { message: 'hola', provider: 'lmstudio', model: 'm' },
      { signal: controller.signal },
    );
    const [, init] = vi.mocked(fetch).mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(init.signal).toBe(controller.signal);
  });
});

describe('non-streaming helpers', () => {
  it('fetchProviders returns the parsed providers body', async () => {
    const body = {
      providers: ['ollama', 'lmstudio'],
      supports_tool_calls: { ollama: false, lmstudio: true },
      chat_enabled: true,
      chat_provider: 'lmstudio',
      chat_local_only: true,
      chat_model: 'qwen3-32b',
    };
    mockGet.mockResolvedValueOnce({ data: body });
    await expect(fetchProviders()).resolves.toEqual(body);
    expect(mockGet).toHaveBeenCalledWith('/ai/providers', expect.anything());
  });

  it('deleteConversation hits the encoded DELETE endpoint', async () => {
    mockDelete.mockResolvedValueOnce({ data: { deleted: true } });
    await expect(deleteConversation('conv_1')).resolves.toEqual({ deleted: true });
    expect(mockDelete).toHaveBeenCalledWith(
      '/ai/chat/conversation/conv_1',
      expect.anything(),
    );
  });

  it('conversationIdFromResponse reads the response header', () => {
    const headers = new Headers({ 'X-Conversation-Id': 'conv_9' });
    expect(conversationIdFromResponse({ headers } as Response)).toBe('conv_9');
    expect(conversationIdFromResponse(new Response(null))).toBeNull();
  });
});

describe('fetchConversationHistory', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('GETs the encoded endpoint with the session header and parses the body', async () => {
    const body = {
      exists: true,
      conversation_id: 'conv_h',
      messages: [{ role: 'user', content: 'hola' }],
      pending: null,
    };
    const mockFetch = vi.fn(async () =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', mockFetch);
    await expect(fetchConversationHistory('conv_h')).resolves.toEqual(body);
    const [url, init] = mockFetch.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe('/api/v1/ai/chat/conversation/conv_h');
    expect((init.headers as Record<string, string>)['X-Session-ID']).toBe(
      'sess-test',
    );
  });

  it('maps the generic 404 to {exists:false} without throwing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ exists: false }), { status: 404 }),
      ),
    );
    await expect(fetchConversationHistory('conv_gone')).resolves.toEqual({
      exists: false,
    });
  });

  it('throws on other non-2xx responses so the caller can start fresh', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 503 })),
    );
    await expect(fetchConversationHistory('conv_x')).rejects.toThrow(
      'conversation_history_failed_503',
    );
  });
});

describe('extractExportDownload', () => {
  it('serves every format from the deterministic table (mirrors export.py)', () => {
    const expected = {
      excel: {
        endpoint: '/api/v1/export/excel',
        filename: 'Conciliacion_Geotecnica.xlsx',
        contentType:
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      },
      word: {
        endpoint: '/api/v1/export/word',
        filename: 'Informe_Conciliacion.docx',
        contentType:
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      },
      pdf: {
        endpoint: '/api/v1/export/pdf',
        filename: 'Informe_Ejecutivo.pdf',
        contentType: 'application/pdf',
      },
      dxf: {
        endpoint: '/api/v1/export/dxf',
        filename: 'Perfiles_3D.dxf',
        contentType: 'application/dxf',
      },
      images: {
        endpoint: '/api/v1/export/images',
        filename: 'Secciones_Imagenes.zip',
        contentType: 'application/zip',
      },
    };
    for (const [format, spec] of Object.entries(expected)) {
      const summary = JSON.stringify({
        ok: true,
        format,
        filename: 'POISONED.bin',
        endpoint: 'https://evil.example/download',
        content_type: 'application/x-poisoned',
      });
      expect(extractExportDownload(summary)).toEqual({
        format,
        ...spec,
      });
    }
  });

  it('ignores tampered summary coordinates and keeps the table values', () => {
    const summary = JSON.stringify({
      ok: true,
      format: 'pdf',
      filename: 'malware.exe',
      endpoint: '/attacker/endpoint',
      method: 'GET',
      content_type: 'text/html',
    });
    expect(extractExportDownload(summary)).toEqual({
      format: 'pdf',
      filename: 'Informe_Ejecutivo.pdf',
      endpoint: '/api/v1/export/pdf',
      contentType: 'application/pdf',
    });
  });

  it('recovers the button from a truncated (…-cut) summary via format only', () => {
    const truncated = `${JSON.stringify({
      ok: true,
      format: 'pdf',
      filename: 'Informe',
      endpoint: '/api/v1/exp',
    }).slice(0, 40)}…`;
    expect(extractExportDownload(truncated)).toEqual({
      format: 'pdf',
      filename: 'Informe_Ejecutivo.pdf',
      endpoint: '/api/v1/export/pdf',
      contentType: 'application/pdf',
    });
  });

  it('uses the single bounded regex fallback when the summary is not valid JSON', () => {
    const summary =
      '{"ok": true, "format": "word", "filename": "Informe_Concili';
    expect(extractExportDownload(summary)).toEqual({
      format: 'word',
      filename: 'Informe_Conciliacion.docx',
      endpoint: '/api/v1/export/word',
      contentType:
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
  });

  it('returns null for non-export, failing or unknown-format observations', () => {
    expect(extractExportDownload(null)).toBeNull();
    expect(extractExportDownload('78 secciones')).toBeNull();
    expect(
      extractExportDownload('{"ok": false, "error": "no_results"}'),
    ).toBeNull();
    expect(extractExportDownload('{"ok": true, "format": "rar"}')).toBeNull();
  });
});

describe('downloadExportFile', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('fetches the endpoint with the session header and saves the blob', async () => {
    const mockFetch = vi.fn(async () =>
      new Response('binary', {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      }),
    );
    vi.stubGlobal('fetch', mockFetch);
    const createObjectURL = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:fake');
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});
    const append = vi.spyOn(document.body, 'appendChild');
    try {
      await downloadExportFile({
        format: 'pdf',
        filename: 'Informe_Ejecutivo.pdf',
        endpoint: '/api/v1/export/pdf',
        contentType: 'application/pdf',
      });
      const [url, init] = mockFetch.mock.calls[0] as unknown as [
        string,
        RequestInit,
      ];
      expect(url).toBe('/api/v1/export/pdf');
      expect((init.headers as Record<string, string>)['X-Session-ID']).toBe(
        'sess-test',
      );
      expect(createObjectURL).toHaveBeenCalledTimes(1);
      const blob = createObjectURL.mock.calls[0][0] as Blob;
      expect(blob.type).toBe('application/pdf');
      expect(append).toHaveBeenCalledTimes(1);
      expect(click).toHaveBeenCalledTimes(1);
    } finally {
      createObjectURL.mockRestore();
      click.mockRestore();
      append.mockRestore();
    }
  });

  it('throws when the export endpoint answers non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 500 })),
    );
    await expect(
      downloadExportFile({
        format: 'pdf',
        filename: 'Informe_Ejecutivo.pdf',
        endpoint: '/api/v1/export/pdf',
        contentType: 'application/pdf',
      }),
    ).rejects.toThrow('export_download_failed_500');
  });

  it('rejects endpoints that are not same-origin paths before fetching', async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal('fetch', mockFetch);
    for (const endpoint of [
      'https://evil.example/api/v1/export/pdf',
      'http://evil.example/api/v1/export/pdf',
      'blob:https://evil.example/abc',
      'data:application/pdf;base64,AAAA',
    ]) {
      await expect(
        downloadExportFile({
          format: 'pdf',
          filename: 'Informe_Ejecutivo.pdf',
          endpoint,
          contentType: 'application/pdf',
        }),
      ).rejects.toThrow('export_download_unsafe_endpoint');
    }
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
