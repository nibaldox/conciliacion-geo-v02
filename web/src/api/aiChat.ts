/**
 * Thin HTTP client for the conversational AI agent chat (T5).
 *
 * The streaming endpoints (POST /ai/chat, POST /ai/chat/confirm) answer
 * NDJSON event streams and are consumed with the native fetch
 * ReadableStream API — axios does not expose a streaming body reader
 * uniformly. The base URL and the X-Session-ID header mirror
 * `api/client.ts` so routing and session handling stay consistent.
 *
 * Nothing here touches localStorage: persistence is the store's
 * concern, and only the conversation id is ever persisted.
 */
import { parseAgentEventLine, type AgentEvent } from './agentChat';
import client, { getSessionId } from './client';

export interface AIProvidersState {
  providers: string[];
  supports_tool_calls: Record<string, boolean>;
  chat_enabled: boolean;
  chat_provider: string | null;
  chat_local_only: boolean;
  chat_model: string;
}

export interface AgentChatRequestBody {
  message: string;
  provider: string;
  model: string;
  conversation_id?: string;
}

export interface StreamCallOptions {
  signal?: AbortSignal;
}

export const LMSTUDIO_PLACEHOLDER_MODEL = 'loaded-model';

function resolveBaseUrl(): string {
  return (client.defaults.baseURL || '/api/v1').replace(/\/$/, '');
}

function sessionHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const sessionId = getSessionId();
  if (sessionId) headers['X-Session-ID'] = sessionId;
  return headers;
}

/**
 * POST /ai/chat: start (or continue) one agent turn.
 *
 * Resolves with the raw fetch Response so the caller can stream the
 * NDJSON body and read the X-Conversation-Id header.
 */
export async function sendChat(
  body: AgentChatRequestBody,
  options: StreamCallOptions = {},
): Promise<Response> {
  return fetch(`${resolveBaseUrl()}/ai/chat`, {
    method: 'POST',
    headers: sessionHeaders(),
    body: JSON.stringify(body),
    signal: options.signal,
  });
}

/**
 * POST /ai/chat/confirm: approve or deny ONE pending tool call.
 *
 * The body is EXACTLY { invocation_id, approved } — the backend rejects
 * any extra field with 422 (extra="forbid"), and the frontend must
 * never send provider, model, args or messages: the server rebuilds
 * the whole resumed turn from the claimed pending run.
 */
export async function confirmChat(
  invocationId: string,
  approved: boolean,
  options: StreamCallOptions = {},
): Promise<Response> {
  return fetch(`${resolveBaseUrl()}/ai/chat/confirm`, {
    method: 'POST',
    headers: sessionHeaders(),
    body: JSON.stringify({ invocation_id: invocationId, approved }),
    signal: options.signal,
  });
}

/** GET /ai/providers: chat feature state + tool-calling capability map. */
export async function fetchProviders(
  options: StreamCallOptions = {},
): Promise<AIProvidersState> {
  const response = await client.get<AIProvidersState>('/ai/providers', {
    signal: options.signal,
  });
  return response.data;
}

/** DELETE /ai/chat/conversation/{id}: remove the server-side conversation. */
export async function deleteConversation(
  conversationId: string,
  options: StreamCallOptions = {},
): Promise<{ deleted: boolean; pendings_invalidated?: number }> {
  const response = await client.delete<{
    deleted: boolean;
    pendings_invalidated?: number;
  }>(`/ai/chat/conversation/${encodeURIComponent(conversationId)}`, {
    signal: options.signal,
  });
  return response.data;
}

export interface SanitizedHistoryMessage {
  role: 'user' | 'assistant' | 'tool';
  content?: string;
  tools?: string[];
  ok?: boolean;
  summary?: string;
  error?: string | null;
}

export interface ConversationPending {
  invocation_id: string;
  tool_name: string;
  args_summary: string;
}

export interface ConversationHistoryResponse {
  exists: boolean;
  conversation_id?: string;
  messages?: SanitizedHistoryMessage[];
  pending?: ConversationPending | null;
}

/**
 * GET /ai/chat/conversation/{id}: sanitized history + live pending.
 *
 * The server answers the sanitized message list (no system prompt, no
 * raw tool arguments) plus the conversation's pending confirmation so
 * the UI can restore the view after a reload. Unknown and foreign ids
 * answer the SAME generic 404 {exists:false}; other failures throw so
 * the caller can silently start fresh.
 */
export async function fetchConversationHistory(
  conversationId: string,
  options: StreamCallOptions = {},
): Promise<ConversationHistoryResponse> {
  const response = await fetch(
    `${resolveBaseUrl()}/ai/chat/conversation/${encodeURIComponent(conversationId)}`,
    { headers: sessionHeaders(), signal: options.signal },
  );
  if (response.status === 404) return { exists: false };
  if (!response.ok) {
    throw new Error(`conversation_history_failed_${response.status}`);
  }
  return (await response.json()) as ConversationHistoryResponse;
}

export interface ExportDownloadInfo {
  format: string;
  filename: string;
  endpoint: string;
  contentType: string;
}

interface ExportDownloadSpec {
  endpoint: string;
  filename: string;
  contentType: string;
}

/**
 * Deterministic download coordinates per export format.
 *
 * Mirrors the REAL export surface byte for byte: the routes and media
 * types of `api/routers/export.py` and the filenames/media types the
 * frozen `export_report` handler announces
 * (`api/ai_agent_write_handlers.py`). The summary is trusted ONLY to
 * detect ok===true and the format; everything that ends up in a fetch
 * comes from this table, so a truncated or tampered summary can never
 * steer the download.
 */
const EXPORT_DOWNLOADS: Record<string, ExportDownloadSpec> = {
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

function matchFormat(summary: string): string {
  const match = /"format"\s*:\s*"([^"]+)"/.exec(summary);
  return match?.[1] ?? '';
}

/**
 * Extract the download metadata of an export_report tool result.
 *
 * The NDJSON ToolResultEvent carries the observation ONLY as its
 * ``summary`` (the compact JSON form, truncated with "…" beyond 200
 * chars). The summary is used exclusively to detect ok===true and the
 * format: a strict JSON parse when valid, otherwise a single bounded
 * regex. Filename, endpoint and content type come EXCLUSIVELY from the
 * deterministic EXPORT_DOWNLOADS table. Returns null when the summary
 * is not a successful export observation or the format is unknown.
 */
export function extractExportDownload(
  summary: string | null,
): ExportDownloadInfo | null {
  if (!summary) return null;
  let format = '';
  try {
    const parsed = JSON.parse(summary) as Record<string, unknown>;
    if (parsed.ok !== true) return null;
    format = typeof parsed.format === 'string' ? parsed.format : '';
  } catch {
    if (!/"ok"\s*:\s*true/.test(summary)) return null;
    format = matchFormat(summary);
  }
  const spec = format ? EXPORT_DOWNLOADS[format] : undefined;
  if (!spec) return null;
  return { format, ...spec };
}

/**
 * Download one export file with the session headers.
 *
 * Mirrors the app's download/blob mechanism (createObjectURL + temp
 * anchor click) used by the AIReporter markdown download, saving the
 * blob under the server-provided filename and content type.
 */
export async function downloadExportFile(
  info: ExportDownloadInfo,
  options: StreamCallOptions = {},
): Promise<void> {
  if (!info.endpoint.startsWith('/')) {
    throw new Error('export_download_unsafe_endpoint');
  }
  const base = resolveBaseUrl();
  const url = info.endpoint.startsWith(base)
    ? info.endpoint
    : `${base}${info.endpoint}`;
  const headers: Record<string, string> = {};
  const sessionId = getSessionId();
  if (sessionId) headers['X-Session-ID'] = sessionId;
  const response = await fetch(url, { headers, signal: options.signal });
  if (!response.ok) {
    throw new Error(`export_download_failed_${response.status}`);
  }
  const blob = new Blob([await response.blob()], { type: info.contentType });
  const fileUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = fileUrl;
  anchor.download = info.filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(fileUrl);
}

/**
 * Read an NDJSON agent-event stream to completion.
 *
 * Each line is parsed with parseAgentEventLine (fail-closed): empty and
 * malformed lines are skipped, never surfaced. The optional signal
 * aborts the stream mid-flight: the reader cancels the underlying
 * stream and resolves without error, mirroring the abort semantics of
 * the report streaming hook.
 */
export async function readAgentEventStream(
  response: Response,
  onEvent: (event: AgentEvent) => void,
  options: StreamCallOptions = {},
): Promise<void> {
  const body = response.body;
  if (!body) return;
  const reader = body.getReader();
  const handleAbort = () => {
    void reader.cancel().catch(() => undefined);
  };
  options.signal?.addEventListener('abort', handleAbort, { once: true });
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      if (options.signal?.aborted) return;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const event = parseAgentEventLine(line);
        if (event) onEvent(event);
      }
    }
    buffer += decoder.decode();
    const trailing = parseAgentEventLine(buffer);
    if (trailing) onEvent(trailing);
  } finally {
    options.signal?.removeEventListener('abort', handleAbort);
    reader.releaseLock();
  }
}

/** Extract the conversation id from a chat/confirm response, if any. */
export function conversationIdFromResponse(response: Response): string | null {
  const value = response.headers.get('X-Conversation-Id');
  return value && value.length > 0 ? value : null;
}
