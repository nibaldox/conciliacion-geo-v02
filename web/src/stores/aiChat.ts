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
import {
  resolveChatModelSelection,
  shouldClearSessionModel,
  type SessionModelSource,
} from '../utils/chatModelSelection';

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
  sendInFlight: boolean;
  inFlightTurn: number | null;
  clearing: boolean;
  acceptedDraft: { id: string; text: string } | null;
  pendingConfirmation: PendingConfirmation | null;
  providerState: AIProvidersState | null;
  providerStateLoaded: boolean;
  providerStateLoading: boolean;
  providerStateError: boolean;
  sessionModel: string;
  sessionModelSource: SessionModelSource;
  notice: ChatNotice | null;
  abortController: AbortController | null;
  writeResultObserver: ((toolName: string) => void) | null;

  init: () => Promise<void>;
  send: (message: string) => Promise<boolean>;
  approve: () => Promise<void>;
  deny: () => Promise<void>;
  abort: () => void;
  loadProviderState: () => Promise<void>;
  setSessionModel: (model: string, source?: SessionModelSource) => void;
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
  sendInFlight: false,
  inFlightTurn: null as number | null,
  clearing: false,
  acceptedDraft: null as { id: string; text: string } | null,
  pendingConfirmation: null as PendingConfirmation | null,
  providerState: null as AIProvidersState | null,
  providerStateLoaded: false,
  providerStateLoading: false,
  providerStateError: false,
  sessionModel: '',
  sessionModelSource: 'none' as SessionModelSource,
  notice: null as ChatNotice | null,
  abortController: null as AbortController | null,
  writeResultObserver: null as ((toolName: string) => void) | null,
};

/**
 * Notices that a successful discovery refresh makes obsolete: they report
 * a transient view of the model list, so keeping them after fresh data
 * arrives would describe a state that no longer exists.
 */
const DISCOVERY_NOTICE_KEYS: ReadonlySet<string> = new Set([
  'aiChat.notice.providers_unavailable',
  'aiChat.notice.models_unreachable',
  'aiChat.notice.models_none',
  'aiChat.notice.models_unsupported',
  'aiChat.notice.models_required',
  'aiChat.notice.model_changed',
  'aiChat.notice.placeholder_model_required',
  'aiChat.notice.chat_disabled',
  'aiChat.notice.provider_no_tools',
]);

interface DiscoveryTask {
  promise: Promise<void>;
  controller: AbortController;
}

let discoveryInFlight: DiscoveryTask | null = null;

/**
 * Monotonic token for one send attempt. `abort` and `reset` bump it, so
 * every await inside `send` can prove the attempt is still the current
 * one BEFORE dispatching the POST: a cancelled revalidation can never
 * post afterwards.
 */
let sendGeneration = 0;

/**
 * Ownership token of the attempt that holds `sendInFlight`. Cleanup from
 * an older attempt must never release the slot of a newer one.
 */
let turnSequence = 0;

/** Bumped on reset so a stale clear completion cannot repaint fresh state. */
let storeGeneration = 0;

const TURN_ABORTED = Symbol('turn-aborted');

/**
 * Wait for `promise` but give up as soon as `signal` aborts.
 *
 * The signal only detaches THIS waiter: the awaited task (the shared
 * provider discovery) keeps running for every other request. That is
 * what lets `abort` release `sendInFlight` immediately without
 * cancelling a discovery other callers are still waiting on.
 */
function waitForAbort<T>(
  promise: Promise<T>,
  signal: AbortSignal,
): Promise<T | typeof TURN_ABORTED> {
  if (signal.aborted) return Promise.resolve(TURN_ABORTED);
  return new Promise((resolve) => {
    let settled = false;
    let onAbort: () => void = () => undefined;
    const finish = (value: T | typeof TURN_ABORTED) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener('abort', onAbort);
      resolve(value);
    };
    onAbort = () => finish(TURN_ABORTED);
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(finish, () => finish(TURN_ABORTED));
  });
}

type SendPlan =
  | { kind: 'blocked'; notice: ChatNotice }
  | { kind: 'ready'; model: string; provider: string };

function blockedSend(key: string): SendPlan {
  return { kind: 'blocked', notice: { severity: 'warning', key } };
}

/**
 * Decide what one send would do with the CURRENT state: the exact model
 * id it would post, or the notice that blocks it. Pure so the same rule
 * is applied before and after a discovery refresh.
 */
function planSend(state: {
  providerState: AIProvidersState | null;
  sessionModel: string;
}): SendPlan {
  const providerState = state.providerState;
  const provider = providerState?.chat_provider ?? 'lmstudio';
  if (providerState && !providerState.chat_enabled) {
    return blockedSend('aiChat.notice.chat_disabled');
  }
  if (providerState && providerState.supports_tool_calls[provider] === false) {
    return blockedSend('aiChat.notice.provider_no_tools');
  }
  const selection = resolveChatModelSelection(providerState, state.sessionModel);
  if (selection.kind === 'fixed') {
    return { kind: 'ready', model: selection.model, provider };
  }
  if (selection.kind === 'pick') {
    return selection.model === null
      ? blockedSend('aiChat.notice.models_required')
      : { kind: 'ready', model: selection.model, provider };
  }
  if (selection.kind === 'unresolved') {
    if (selection.needsManual) {
      return blockedSend(
        selection.status === 'ok'
          ? 'aiChat.notice.models_none'
          : selection.status === 'not_supported'
            ? 'aiChat.notice.models_unsupported'
            : 'aiChat.notice.models_unreachable',
      );
    }
    return selection.manual
      ? { kind: 'ready', model: selection.manual, provider }
      : blockedSend('aiChat.notice.placeholder_model_required');
  }
  if (selection.needsManual) {
    const typed = state.sessionModel.trim();
    return typed
      ? { kind: 'ready', model: typed, provider }
      : blockedSend('aiChat.notice.placeholder_model_required');
  }
  return selection.model
    ? { kind: 'ready', model: selection.model, provider }
    : blockedSend('aiChat.notice.placeholder_model_required');
}

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
    const shared = discoveryInFlight;
    if (shared) return shared.promise;
    set({ providerStateLoading: true });
    const controller = new AbortController();
    const taskRef: { current: DiscoveryTask | null } = { current: null };
    const promise = (async () => {
      try {
        const providerState = await fetchProviders({ signal: controller.signal });
        if (discoveryInFlight !== taskRef.current) return;
        const sessionModel = get().sessionModel;
        const selection = resolveChatModelSelection(providerState, sessionModel);
        const clearStale =
          sessionModel.trim().length > 0 &&
          shouldClearSessionModel(selection, get().sessionModelSource);
        const notice = get().notice;
        const clearNotice =
          notice !== null && DISCOVERY_NOTICE_KEYS.has(notice.key);
        set({
          providerState,
          providerStateLoaded: true,
          providerStateError: false,
          ...(clearStale
            ? {
                sessionModel: '',
                sessionModelSource: 'none' as SessionModelSource,
              }
            : {}),
          ...(clearNotice ? { notice: null } : {}),
        });
      } catch {
        if (discoveryInFlight !== taskRef.current) return;
        set({
          providerStateLoaded: true,
          providerStateError: true,
          notice: {
            severity: 'warning',
            key: 'aiChat.notice.providers_unavailable',
          },
        });
      } finally {
        if (discoveryInFlight === taskRef.current) {
          set({ providerStateLoading: false });
          discoveryInFlight = null;
        }
      }
    })();
    taskRef.current = { promise, controller };
    discoveryInFlight = taskRef.current;
    return promise;
  },

  send: async (rawMessage: string) => {
    const message = rawMessage.trim();
    if (!message || get().streaming || get().sendInFlight || get().clearing) {
      return false;
    }

    const generation = sendGeneration;
    const turn = ++turnSequence;
    const controller = new AbortController();
    set({ sendInFlight: true, inFlightTurn: turn, abortController: controller });
    try {
      const displayed = planSend(get());
      let discovered = false;
      const shared = discoveryInFlight;
      if (shared) {
        const waited = await waitForAbort(shared.promise, controller.signal);
        if (waited === TURN_ABORTED || generation !== sendGeneration) {
          return false;
        }
        discovered = true;
      }
      if (displayed.kind === 'blocked' && !discovered) {
        set({ notice: displayed.notice });
        return false;
      }
      if (!discovered) {
        const initialSelection = resolveChatModelSelection(
          get().providerState,
          get().sessionModel,
        );
        if (
          initialSelection.kind === 'fixed' &&
          get().providerState?.chat_models?.selected_source === 'auto'
        ) {
          const waited = await waitForAbort(
            get().loadProviderState(),
            controller.signal,
          );
          if (waited === TURN_ABORTED || generation !== sendGeneration) {
            return false;
          }
          discovered = true;
        }
      }
      const state = get();
      if (discovered && state.providerStateError) {
        set({
          notice: {
            severity: 'warning',
            key: 'aiChat.notice.models_unreachable',
          },
        });
        return false;
      }
      const plan = planSend(state);
      if (plan.kind === 'blocked') {
        set({ notice: plan.notice });
        return false;
      }
      if (
        discovered &&
        displayed.kind === 'ready' &&
        plan.model !== displayed.model
      ) {
        set({
          notice: {
            severity: 'warning',
            key: 'aiChat.notice.model_changed',
            values: {
              previous: displayed.model,
              current: plan.model,
            },
          },
        });
        return false;
      }
      const userId = makeMessageId();
      set((current) => ({
        streaming: true,
        notice: null,
        activeTextId: null,
        abortController: controller,
        acceptedDraft: { id: userId, text: message },
        messages: [
          ...current.messages,
          { kind: 'user', id: userId, text: message },
        ],
      }));
      try {
        const response = await sendChat(
          {
            message,
            provider: plan.provider,
            model: plan.model,
            conversation_id: get().conversationId ?? undefined,
          },
          { signal: controller.signal },
        );
        if (generation !== sendGeneration || controller.signal.aborted) {
          return false;
        }
        const conversationId = conversationIdFromResponse(response);
        if (conversationId && conversationId !== get().conversationId) {
          persistConversationId(conversationId);
          set({ conversationId });
        }
        if (!response.ok) {
          const detail = await readErrorDetail(response);
          if (generation !== sendGeneration || controller.signal.aborted) {
            return false;
          }
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
          return true;
        }
        await readAgentEventStream(
          response,
          (event) => {
            if (generation === sendGeneration) get().applyAgentEvent(event);
          },
          { signal: controller.signal },
        );
        if (generation !== sendGeneration || controller.signal.aborted) {
          return false;
        }
      } catch (err) {
        if (!isAbortError(err) && generation === sendGeneration) {
          set({
            notice: { severity: 'error', key: 'aiChat.notice.network_error' },
          });
        }
      } finally {
        set((current) =>
          current.abortController === controller
            ? { abortController: null, streaming: false }
            : {},
        );
      }
      return generation === sendGeneration;
    } finally {
      set((current) => {
        const updates: Partial<AIChatState> = {};
        if (current.inFlightTurn === turn) {
          updates.sendInFlight = false;
          updates.inFlightTurn = null;
        }
        if (current.abortController === controller) {
          updates.abortController = null;
        }
        return updates;
      });
    }
  },

  approve: async () => {
    const pending = get().pendingConfirmation;
    if (
      !pending ||
      get().streaming ||
      get().sendInFlight ||
      get().clearing
    ) {
      return;
    }
    await resumeConfirmation(pending.invocationId, true, set, get);
  },

  deny: async () => {
    const pending = get().pendingConfirmation;
    if (
      !pending ||
      get().streaming ||
      get().sendInFlight ||
      get().clearing
    ) {
      return;
    }
    await resumeConfirmation(pending.invocationId, false, set, get);
  },

  abort: () => {
    sendGeneration += 1;
    set((state) =>
      state.sendInFlight
        ? { sendInFlight: false, inFlightTurn: null }
        : {},
    );
    get().abortController?.abort();
  },

  setSessionModel: (model: string, source?: SessionModelSource) =>
    set((state) => {
      const trimmed = model.trim();
      if (!trimmed) return { sessionModel: '', sessionModelSource: 'none' };
      const selection = resolveChatModelSelection(state.providerState, model);
      const resolvedSource =
        source ??
        (selection.kind === 'pick' && selection.model === trimmed
          ? 'detected'
          : 'manual');
      return { sessionModel: model, sessionModelSource: resolvedSource };
    }),

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
    if (get().clearing || get().streaming || get().sendInFlight) return;
    const conversationId = get().conversationId;
    const epoch = storeGeneration;
    set({ clearing: true });
    try {
      if (conversationId) {
        try {
          await deleteConversation(conversationId);
        } catch {
          return;
        }
        if (epoch !== storeGeneration) return;
      }
      persistConversationId(null);
      set({
        conversationId: null,
        messages: [],
        activeTextId: null,
        pendingConfirmation: null,
        notice: { severity: 'info', key: 'aiChat.notice.cleared' },
      });
    } finally {
      set({ clearing: false });
    }
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
    sendGeneration += 1;
    storeGeneration += 1;
    discoveryInFlight?.controller.abort();
    discoveryInFlight = null;
    get().abortController?.abort();
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
