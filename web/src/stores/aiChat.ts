/**
 * Zustand store for the conversational AI agent chat (T5).
 *
 * The browser holds PRESENTATION STATE ONLY: the server-side SQLite
 * conversation (see api/ai_agent_conversations.py) is the source of
 * truth. localStorage persists the conversation id (scoped per API
 * session) and nothing else — never message bodies, never
 * invocation_ids, never tool payloads.
 */
import { create } from 'zustand';
import {
  LMSTUDIO_PLACEHOLDER_MODEL,
  confirmChat,
  conversationIdFromResponse,
  deleteConversation,
  fetchConversationHistory,
  fetchProviders,
  readAgentEventStream,
  sendChat,
  type AIProvidersState,
  type ConversationHistoryResponse,
  type SanitizedHistoryMessage,
} from '../api/aiChat';
import type { AgentEvent } from '../api/agentChat';
import { getSessionId } from '../api/client';

export type ChatMessage =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'agent'; id: string; text: string }
  | { kind: 'observation'; id: string; text: string }
  | {
      kind: 'tool';
      id: string;
      invocationId: string;
      name: string;
      status: 'running' | 'ok' | 'error';
      summary: string | null;
      error: string | null;
    }
  | {
      kind: 'confirmation';
      id: string;
      invocationId: string;
      name: string;
      argsSummary: string;
      resolution: 'pending' | 'approved' | 'denied';
    };

export interface ChatNotice {
  severity: 'info' | 'warning' | 'error';
  key: string;
  values?: Record<string, unknown>;
  fallback?: string;
}

export interface PendingConfirmation {
  invocationId: string;
  name: string;
  argsSummary: string;
}

export const WRITE_TOOL_QUERY_KEYS: Record<string, readonly string[][]> = {
  generate_sections_auto: [['sections']],
  generate_sections_manual: [['sections']],
  add_section_click: [['sections']],
  run_reconciliation: [['process-status'], ['results'], ['profile']],
};

const INFORMATIONAL_OBSERVATION_CODES: ReadonlySet<string> = new Set([
  'denied_by_user',
  'skipped_turn_denied',
  'confirmation_limit_reached',
]);

const STORAGE_PREFIX = 'conciliacion.aiChat.conversationId';

function conversationStorageKey(): string {
  const sessionId = getSessionId();
  return sessionId ? `${STORAGE_PREFIX}.${sessionId}` : STORAGE_PREFIX;
}

function readStoredConversationId(): string | null {
  try {
    return window.localStorage.getItem(conversationStorageKey());
  } catch {
    return null;
  }
}

function persistConversationId(conversationId: string | null): void {
  try {
    const key = conversationStorageKey();
    if (conversationId) {
      window.localStorage.setItem(key, conversationId);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    return;
  }
}

function makeMessageId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `msg_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

/**
 * Map the sanitized server history onto presentation messages.
 *
 * Exported pure for tests. User/assistant entries become text bubbles;
 * a ``role:tool`` answer is paired with the pending function name of
 * its parent assistant ``tools`` list (positionally) and rendered as a
 * ToolCallCard — EXCEPT denial/limit guardrail observations, which are
 * informational. Restored ids are synthetic (``restored_*``): they can
 * never collide with live ``inv_*`` ids. Content is plain text only.
 */
export function historyToChatMessages(
  history: SanitizedHistoryMessage[],
): ChatMessage[] {
  const messages: ChatMessage[] = [];
  let names: string[] = [];
  history.forEach((entry, index) => {
    if (entry.role === 'user') {
      names = [];
      messages.push({
        kind: 'user',
        id: `restored_u_${index}`,
        text: entry.content ?? '',
      });
      return;
    }
    if (entry.role === 'assistant') {
      names = [...(entry.tools ?? [])];
      if (entry.content) {
        messages.push({
          kind: 'agent',
          id: `restored_a_${index}`,
          text: entry.content,
        });
      }
      return;
    }
    const name = names.shift() ?? 'tool';
    if (!entry.ok && INFORMATIONAL_OBSERVATION_CODES.has(entry.error ?? '')) {
      messages.push({
        kind: 'observation',
        id: `restored_t_${index}`,
        text: entry.summary ?? '',
      });
      return;
    }
    messages.push({
      kind: 'tool',
      id: `restored_t_${index}`,
      invocationId: `restored_${index}`,
      name,
      status: entry.ok ? 'ok' : 'error',
      summary: entry.summary ?? null,
      error: entry.error ?? null,
    });
  });
  return messages;
}

async function restoreConversation(
  conversationId: string,
  set: SetState,
  get: GetState,
): Promise<void> {
  if (get().streaming || get().messages.length > 0) return;
  let data: ConversationHistoryResponse;
  try {
    data = await fetchConversationHistory(conversationId);
  } catch {
    return;
  }
  if (!data.exists) {
    persistConversationId(null);
    if (get().conversationId === conversationId) {
      set({ conversationId: null });
    }
    return;
  }
  if (get().streaming || get().messages.length > 0) return;
  const messages = historyToChatMessages(data.messages ?? []);
  const pending = data.pending ?? null;
  if (pending) {
    messages.push({
      kind: 'confirmation',
      id: makeMessageId(),
      invocationId: pending.invocation_id,
      name: pending.tool_name,
      argsSummary: pending.args_summary,
      resolution: 'pending',
    });
  }
  set({
    messages,
    activeTextId: null,
    pendingConfirmation: pending
      ? {
          invocationId: pending.invocation_id,
          name: pending.tool_name,
          argsSummary: pending.args_summary,
        }
      : null,
  });
}

interface AIChatState {
  conversationId: string | null;
  messages: ChatMessage[];
  activeTextId: string | null;
  streaming: boolean;
  pendingConfirmation: PendingConfirmation | null;
  providerState: AIProvidersState | null;
  providerStateLoaded: boolean;
  sessionModel: string;
  notice: ChatNotice | null;
  abortController: AbortController | null;
  writeResultObserver: ((toolName: string) => void) | null;

  init: () => Promise<void>;
  send: (message: string) => Promise<void>;
  approve: () => Promise<void>;
  deny: () => Promise<void>;
  abort: () => void;
  loadProviderState: () => Promise<void>;
  setSessionModel: (model: string) => void;
  dismissNotice: () => void;
  addObservation: (text: string) => void;
  clearConversation: () => Promise<void>;
  setWriteResultObserver: (
    observer: ((toolName: string) => void) | null,
  ) => void;
  applyAgentEvent: (event: AgentEvent) => void;
  reset: () => void;
}

const initialState = {
  conversationId: null,
  messages: [] as ChatMessage[],
  activeTextId: null as string | null,
  streaming: false,
  pendingConfirmation: null as PendingConfirmation | null,
  providerState: null as AIProvidersState | null,
  providerStateLoaded: false,
  sessionModel: '',
  notice: null as ChatNotice | null,
  abortController: null as AbortController | null,
  writeResultObserver: null as ((toolName: string) => void) | null,
};

function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException &&
    (err.name === 'AbortError' || err.name === 'CancelError')
  );
}

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    return null;
  } catch {
    return null;
  }
}

export const useAIChat = create<AIChatState>((set, get) => ({
  ...initialState,

  init: async () => {
    const stored = readStoredConversationId();
    if (stored !== get().conversationId) {
      set({ conversationId: stored });
    }
    if (!get().providerStateLoaded) {
      await get().loadProviderState();
    }
    if (stored) {
      await restoreConversation(stored, set, get);
    }
  },

  loadProviderState: async () => {
    try {
      const providerState = await fetchProviders();
      set({ providerState, providerStateLoaded: true });
    } catch {
      set({
        providerState: null,
        providerStateLoaded: true,
        notice: {
          severity: 'warning',
          key: 'aiChat.notice.providers_unavailable',
        },
      });
    }
  },

  send: async (rawMessage: string) => {
    const state = get();
    const message = rawMessage.trim();
    if (!message || state.streaming) return;
    const providerState = state.providerState;
    if (providerState && !providerState.chat_enabled) {
      set({
        notice: { severity: 'warning', key: 'aiChat.notice.chat_disabled' },
      });
      return;
    }
    const provider = providerState?.chat_provider ?? 'lmstudio';
    if (
      providerState &&
      providerState.supports_tool_calls[provider] === false
    ) {
      set({
        notice: { severity: 'warning', key: 'aiChat.notice.provider_no_tools' },
      });
      return;
    }
    const configuredModel = providerState?.chat_model ?? LMSTUDIO_PLACEHOLDER_MODEL;
    const placeholderModel = configuredModel === LMSTUDIO_PLACEHOLDER_MODEL;
    const model = placeholderModel ? state.sessionModel.trim() : configuredModel;
    if (!model) {
      set({
        notice: {
          severity: 'warning',
          key: 'aiChat.notice.placeholder_model_required',
        },
      });
      return;
    }
    const controller = new AbortController();
    set({
      streaming: true,
      notice: null,
      activeTextId: null,
      abortController: controller,
      messages: [
        ...state.messages,
        { kind: 'user', id: makeMessageId(), text: message },
      ],
    });
    try {
      const response = await sendChat(
        {
          message,
          provider,
          model,
          conversation_id: get().conversationId ?? undefined,
        },
        { signal: controller.signal },
      );
      const conversationId = conversationIdFromResponse(response);
      if (conversationId && conversationId !== get().conversationId) {
        persistConversationId(conversationId);
        set({ conversationId });
      }
      if (!response.ok) {
        const detail = await readErrorDetail(response);
        set({
          streaming: false,
          abortController: null,
          notice: {
            severity: 'error',
            key: 'aiChat.notice.request_failed',
            fallback: detail ?? undefined,
            values: detail ? { detail } : undefined,
          },
        });
        return;
      }
      await readAgentEventStream(
        response,
        (event) => get().applyAgentEvent(event),
        { signal: controller.signal },
      );
    } catch (err) {
      if (!isAbortError(err)) {
        set({
          notice: { severity: 'error', key: 'aiChat.notice.network_error' },
        });
      }
    } finally {
      if (get().abortController === controller) {
        set({ abortController: null });
      }
      set({ streaming: false });
    }
  },

  approve: async () => {
    const pending = get().pendingConfirmation;
    if (!pending || get().streaming) return;
    await resumeConfirmation(pending.invocationId, true, set, get);
  },

  deny: async () => {
    const pending = get().pendingConfirmation;
    if (!pending || get().streaming) return;
    await resumeConfirmation(pending.invocationId, false, set, get);
  },

  abort: () => {
    get().abortController?.abort();
  },

  setSessionModel: (model: string) => set({ sessionModel: model }),

  dismissNotice: () => set({ notice: null }),

  addObservation: (text: string) => {
    set((state) => ({
      messages: [
        ...state.messages,
        { kind: 'observation', id: makeMessageId(), text },
      ],
    }));
  },

  clearConversation: async () => {
    const conversationId = get().conversationId;
    if (conversationId) {
      try {
        await deleteConversation(conversationId);
      } catch {
        return;
      }
    }
    persistConversationId(null);
    set({
      conversationId: null,
      messages: [],
      activeTextId: null,
      pendingConfirmation: null,
      notice: { severity: 'info', key: 'aiChat.notice.cleared' },
    });
  },

  setWriteResultObserver: (observer) => set({ writeResultObserver: observer }),

  applyAgentEvent: (event: AgentEvent) => {
    switch (event.type) {
      case 'text':
        set((state) => {
          const activeId = state.activeTextId;
          if (activeId !== null) {
            const index = state.messages.findIndex(
              (m) => m.kind === 'agent' && m.id === activeId,
            );
            if (index >= 0) {
              const target = state.messages[index] as Extract<
                ChatMessage,
                { kind: 'agent' }
              >;
              const messages = [...state.messages];
              messages[index] = { ...target, text: target.text + event.content };
              return { messages };
            }
          }
          const id = makeMessageId();
          return {
            activeTextId: id,
            messages: [
              ...state.messages,
              { kind: 'agent', id, text: event.content },
            ],
          };
        });
        break;
      case 'tool_call':
        set((state) => ({
          activeTextId: null,
          messages: [
            ...state.messages,
            {
              kind: 'tool',
              id: makeMessageId(),
              invocationId: event.invocation_id,
              name: event.name,
              status: 'running',
              summary: null,
              error: null,
            },
          ],
        }));
        break;
      case 'tool_result': {
        const state = get();
        const index = state.messages.findIndex(
          (m) => m.kind === 'tool' && m.invocationId === event.invocation_id,
        );
        const messages = [...state.messages];
        if (index >= 0) {
          const card = messages[index] as Extract<
            ChatMessage,
            { kind: 'tool' }
          >;
          messages[index] = {
            ...card,
            status: event.ok ? 'ok' : 'error',
            summary: event.summary,
            error: event.error,
          };
        } else {
          messages.push({
            kind: 'tool',
            id: makeMessageId(),
            invocationId: event.invocation_id,
            name: event.name,
            status: event.ok ? 'ok' : 'error',
            summary: event.summary,
            error: event.error,
          });
        }
        set({ messages });
        if (event.ok && event.name in WRITE_TOOL_QUERY_KEYS) {
          state.writeResultObserver?.(event.name);
        }
        break;
      }
      case 'confirmation_required':
        set((state) => ({
          activeTextId: null,
          messages: [
            ...state.messages,
            {
              kind: 'confirmation',
              id: makeMessageId(),
              invocationId: event.invocation_id,
              name: event.name,
              argsSummary: event.args_summary,
              resolution: 'pending',
            },
          ],
          pendingConfirmation: {
            invocationId: event.invocation_id,
            name: event.name,
            argsSummary: event.args_summary,
          },
        }));
        break;
      case 'error':
        set((state) => ({
          activeTextId: null,
          messages: [
            ...state.messages,
            { kind: 'agent', id: makeMessageId(), text: event.content },
          ],
          notice: {
            severity: 'error',
            key: 'aiChat.notice.provider_unreachable',
          },
        }));
        break;
      case 'done':
        set(
          event.finish_reason !== 'confirmation_required'
            ? { pendingConfirmation: null, activeTextId: null }
            : { activeTextId: null },
        );
        break;
    }
  },

  reset: () => {
    set({ ...initialState });
  },
}));

type SetState = (
  partial: Partial<AIChatState> | ((state: AIChatState) => Partial<AIChatState>),
) => void;
type GetState = () => AIChatState;

async function resumeConfirmation(
  invocationId: string,
  approved: boolean,
  set: SetState,
  get: GetState,
): Promise<void> {
  const controller = new AbortController();
  set((state) => ({
    streaming: true,
    notice: null,
    abortController: controller,
    messages: state.messages.map((message) =>
      message.kind === 'confirmation' && message.invocationId === invocationId
        ? { ...message, resolution: approved ? 'approved' : 'denied' }
        : message,
    ),
  }));
  try {
    const response = await confirmChat(invocationId, approved, {
      signal: controller.signal,
    });
    if (!response.ok) {
      const detail = await readErrorDetail(response);
      set({
        streaming: false,
        abortController: null,
        pendingConfirmation: null,
        notice: {
          severity: 'error',
          key: 'aiChat.notice.request_failed',
          fallback: detail ?? undefined,
          values: detail ? { detail } : undefined,
        },
      });
      return;
    }
    await readAgentEventStream(
      response,
      (event) => get().applyAgentEvent(event),
      { signal: controller.signal },
    );
  } catch (err) {
    if (!isAbortError(err)) {
      set({
        notice: { severity: 'error', key: 'aiChat.notice.network_error' },
      });
    }
  } finally {
    if (get().abortController === controller) {
      set({ abortController: null });
    }
    set({
      streaming: false,
      pendingConfirmation: null,
    });
  }
}
