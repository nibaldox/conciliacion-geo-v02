import { memo, useEffect, useRef, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import type { ChatMessage, ChatNotice } from '../../stores/aiChat';
import { useAIChat } from '../../stores/aiChat';
import {
  LMSTUDIO_PLACEHOLDER_MODEL,
  type AIProvidersState,
} from '../../api/aiChat';
import {
  modelOptionLabel,
  resolveChatModelSelection,
  type ChatModelSelection,
} from '../../utils/chatModelSelection';
import { Spinner } from '../ui/Spinner';
import { MarkdownMessage } from './MarkdownMessage';
import { TopoUploadZone } from './TopoUploadZone';
import { EmbeddedWorkflowGuide } from './EmbeddedWorkflowGuide';
import { ChatPet } from './ChatPet';
import { CopilotHeader } from './CopilotHeader';
import { ContextChip } from './ContextChip';
import { ConfirmationCard, ToolCallCard, ToolActivityGroup } from './ToolCallCard';
import { type ResizeDirection, useResizablePanel } from './useResizablePanel';

const NOTICE_TONE: Record<ChatNotice['severity'], string> = {
  info: 'border-border text-text-secondary',
  warning: 'border-[var(--color-status-warning)] text-text-primary',
  error: 'border-[var(--color-status-error)] text-text-primary',
};

type PanelStatus =
  | 'loading'
  | 'configured'
  | 'unavailable'
  | 'no_model'
  | 'no_connection'
  | 'not_supported'
  | 'choose_model'
  | 'manual';

const PANEL_STATUS_KEY: Record<Exclude<PanelStatus, 'loading'>, string> = {
  configured: 'aiChat.header.configured',
  unavailable: 'aiChat.header.unavailable',
  no_model: 'aiChat.header.no_model',
  no_connection: 'aiChat.header.no_connection',
  not_supported: 'aiChat.header.not_supported',
  choose_model: 'aiChat.header.choose_model',
  manual: 'aiChat.header.manual',
};

function derivePanelStatus(options: {
  providerStateLoaded: boolean;
  chatEnabled: boolean;
  supportsTools: boolean;
  modelsState: AIProvidersState['chat_models'] | null;
  selection: ChatModelSelection;
  manual: string;
}): PanelStatus {
  if (!options.providerStateLoaded) return 'loading';
  if (!options.chatEnabled || !options.supportsTools) return 'unavailable';
  const models = options.modelsState;
  if (!models) {
    if (options.selection.kind === 'legacy' && options.selection.needsManual) {
      return options.manual ? 'manual' : 'no_model';
    }
    return 'configured';
  }
  if (options.selection.kind === 'unresolved' && options.selection.manual) {
    return 'manual';
  }
  if (models.status === 'disabled') return 'unavailable';
  if (
    options.selection.kind === 'fixed' &&
    models.selected_source === 'override' &&
    models.status === 'ok'
  ) {
    return 'configured';
  }
  if (models.status === 'not_supported') return 'not_supported';
  if (models.status !== 'ok') return 'no_connection';
  if (models.models.length === 0) return 'no_model';
  if (options.selection.kind === 'pick' && options.selection.model === null) {
    return 'choose_model';
  }
  return 'configured';
}

const MessageBubble = memo(function MessageBubble({ message, embedded = false }: { message: ChatMessage; embedded?: boolean }) {
  const { t } = useTranslation();
  if (message.kind === 'tool') return <ToolCallCard message={message} />;
  if (message.kind === 'confirmation') {
    return <ConfirmationCardLazy message={message} embedded={embedded} />;
  }
  if (message.kind === 'observation') {
    return (
      <div
        data-slot="ai-chat-observation"
        className={embedded ? "min-w-0 border-b border-border py-3 text-xs text-text-secondary" : "rounded-lg border border-border bg-surface-muted px-3 py-2 text-xs text-text-secondary"}
      >
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
      </div>
    );
  }
  const isUser = message.kind === 'user';
  if (embedded) return <div data-slot="ai-chat-message" data-kind={message.kind} className="calm-appear min-w-0 border-b border-border py-4 last:border-0">
    <div className="mb-2 text-xs font-semibold text-text-secondary">{isUser ? t('aiChat.messages.you') : t('aiChat.messages.agent')}</div>
    {message.kind === 'agent' ? <MarkdownMessage content={message.text} chips /> : <p className="whitespace-pre-wrap break-words text-sm font-medium">{message.text}</p>}
  </div>;
  return (
    <div
      data-slot="ai-chat-message"
      data-kind={message.kind}
      className={`calm-appear flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-accent text-accent-fg'
            : 'border border-border bg-surface text-text-primary'
        }`}
      >
        <span className="sr-only">
          {isUser ? t('aiChat.messages.you') : t('aiChat.messages.agent')}
        </span>
        {message.kind === 'agent' ? (
          <MarkdownMessage content={message.text} />
        ) : (
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
        )}
      </div>
    </div>
  );
}, (prev, next) => prev.message === next.message && prev.embedded === next.embedded);

function ConfirmationCardLazy({
  message,
  embedded,
}: {
  message: Extract<ChatMessage, { kind: 'confirmation' }>;
  embedded: boolean;
}) {
  const busy = useAIChat((s) => s.streaming || s.sendInFlight || s.clearing);
  const approve = useAIChat((s) => s.approve);
  const deny = useAIChat((s) => s.deny);
  return (
    <ConfirmationCard
      message={message}
      presentation={embedded ? 'embedded' : 'floating'}
      busy={busy}
      onApprove={() => void approve()}
      onDeny={() => void deny()}
    />
  );
}

function NoticeBanner({ notice }: { notice: ChatNotice }) {
  const { t } = useTranslation();
  const dismissNotice = useAIChat((s) => s.dismissNotice);
  const text = t(notice.key, {
    defaultValue: notice.fallback ?? '',
    ...notice.values,
  });
  return (
    <div
      role="status"
      data-slot="ai-chat-notice"
      data-testid="ai-chat-notice"
      data-severity={notice.severity}
      className={`flex items-start justify-between gap-2 rounded-lg border px-3 py-2 text-xs ${NOTICE_TONE[notice.severity]}`}
    >
      <p className="whitespace-pre-wrap break-words">{text}</p>
      <button
        type="button"
        aria-label={t('aiChat.notice.dismiss')}
        onClick={dismissNotice}
        className="shrink-0 text-text-muted hover:text-text-primary"
      >
        ×
      </button>
    </div>
  );
}

interface ChatPanelProps {
  onClose?: () => void;
  presentation?: 'floating' | 'embedded';
  layout?: 'protagonist' | 'copilot';
  /**
   * Desktop-only extra gap subtracted from the stored rect height so the
   * panel's bottom edge clears the floating launcher button (which stays
   * fixed above it at z-[95]). Ignored on mobile (bottom sheet).
   */
  bottomOffsetPx?: number;
}

const RESIZE_HANDLES: ReadonlyArray<{
  direction: ResizeDirection;
  labelKey: 'north' | 'south' | 'east' | 'west' | 'ne' | 'nw' | 'se' | 'sw';
  orientation?: 'horizontal' | 'vertical';
  className: string;
}> = [
  { direction: 'n', labelKey: 'north', orientation: 'horizontal', className: 'inset-x-3 top-0 h-1.5 cursor-n-resize' },
  { direction: 's', labelKey: 'south', orientation: 'horizontal', className: 'inset-x-3 bottom-0 h-1.5 cursor-s-resize' },
  { direction: 'e', labelKey: 'east', orientation: 'vertical', className: 'inset-y-3 right-0 w-1.5 cursor-e-resize' },
  { direction: 'w', labelKey: 'west', orientation: 'vertical', className: 'inset-y-3 left-0 w-1.5 cursor-w-resize' },
  { direction: 'nw', labelKey: 'nw', className: 'left-0 top-0 h-3 w-3 cursor-nw-resize' },
  { direction: 'ne', labelKey: 'ne', className: 'right-0 top-0 h-3 w-3 cursor-ne-resize' },
  { direction: 'sw', labelKey: 'sw', className: 'bottom-0 left-0 h-3 w-3 cursor-sw-resize' },
  { direction: 'se', labelKey: 'se', className: 'bottom-0 right-0 h-3 w-3 cursor-se-resize' },
];

/**
 * The chat panel: history, notices, confirmation cards, mesh upload and
 * the message input. Agent output is rendered as Markdown inside a
 * sandboxed renderer (no raw HTML ever reaches the DOM). On desktop the
 * panel is resizable from its edges/corners; on mobile it stays a
 * full-width bottom sheet. Escape closes the panel and focus is
 * restored to the previously focused element.
 */
export function ChatPanel({ onClose, bottomOffsetPx = 0, presentation = 'floating', layout = 'copilot' }: ChatPanelProps) {
  const embedded = presentation === 'embedded';
  const protagonist = embedded && layout === 'protagonist';
  const { t } = useTranslation();
  const resizable = useResizablePanel();
  const messages = useAIChat((s) => s.messages);
  const streaming = useAIChat((s) => s.streaming);
  const sendInFlight = useAIChat((s) => s.sendInFlight);
  const clearing = useAIChat((s) => s.clearing);
  const providerState = useAIChat((s) => s.providerState);
  const providerStateLoaded = useAIChat((s) => s.providerStateLoaded);
  const providerStateLoading = useAIChat((s) => s.providerStateLoading);
  const sessionModel = useAIChat((s) => s.sessionModel);
  const notice = useAIChat((s) => s.notice);
  const acceptedDraft = useAIChat((s) => s.acceptedDraft);
  const send = useAIChat((s) => s.send);
  const abort = useAIChat((s) => s.abort);
  const setSessionModel = useAIChat((s) => s.setSessionModel);
  const loadProviderState = useAIChat((s) => s.loadProviderState);
  const clearConversation = useAIChat((s) => s.clearConversation);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const legacyInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const handledAcceptanceRef = useRef<string | null>(null);
  const [draft, setDraft] = useState('');
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const isTouchDevice = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches === true;

  const resizeInput = () => {
    const textarea = inputRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const availableHeight = typeof window !== 'undefined'
      ? (window.visualViewport?.height ?? window.innerHeight)
      : 0;
    const maxHeight = Math.min(embedded && !protagonist ? 128 : 168, Math.max(48, availableHeight - 250));
    const contentHeight = textarea.scrollHeight;
    const height = Math.min(contentHeight + 2, maxHeight);
    textarea.style.height = `${height}px`;
    textarea.style.overflowY = contentHeight + 2 > maxHeight ? 'auto' : 'hidden';
  };

  useEffect(() => {
    resizeInput();
  }, [draft, embedded, layout]);

  useEffect(() => {
    const resize = () => resizeInput();
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
    };
  }, [embedded]);

  useEffect(() => {
    if (!acceptedDraft || handledAcceptanceRef.current === acceptedDraft.id) {
      return;
    }
    handledAcceptanceRef.current = acceptedDraft.id;
    setDraft((current) =>
      current.trim() === acceptedDraft.text ? '' : current,
    );
  }, [acceptedDraft]);

  useEffect(() => {
    void useAIChat.getState().init();
  }, []);

  useEffect(() => {
    if (embedded) return;
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    legacyInputRef.current?.focus();
    return () => {
      restoreFocusRef.current?.focus();
    };
  }, [embedded]);

  useEffect(() => {
    const list = listRef.current;
    if (list && (!embedded || followRef.current)) list.scrollTop = list.scrollHeight;
  }, [messages, notice, embedded]);

  const chatEnabled = providerState?.chat_enabled ?? false;
  const provider = providerState?.chat_provider ?? null;
  const localOnly = providerState?.chat_local_only ?? false;
  const modelsState = providerState?.chat_models ?? null;
  const supportsTools = provider
    ? providerState?.supports_tool_calls[provider] !== false
    : true;
  const isLmStudioLocal = localOnly && provider === 'lmstudio';
  const selection = resolveChatModelSelection(providerState, sessionModel);
  const placeholderModel =
    chatEnabled && selection.kind === 'legacy' && selection.needsManual;
  const rawHeaderModel =
    selection.kind === 'fixed' || selection.kind === 'pick'
      ? selection.model
      : selection.kind === 'unresolved'
        ? selection.manual || null
        : selection.needsManual
          ? sessionModel.trim() || null
          : selection.model;
  const headerModel =
    rawHeaderModel === LMSTUDIO_PLACEHOLDER_MODEL ? null : rawHeaderModel;
  const chosenToolUse =
    selection.kind === 'fixed' || selection.kind === 'pick'
      ? selection.toolUse
      : null;

  const status = derivePanelStatus({
    providerStateLoaded,
    chatEnabled,
    supportsTools,
    modelsState,
    selection,
    manual: sessionModel.trim(),
  });
  const turnActive = streaming || sendInFlight;
  const busy = turnActive || clearing;

  const handleSubmit = () => {
    if (busy) return;
    const text = draft.trim();
    if (!text) return;
    void send(text);
  };

  const fillDraft = (text: string) => {
    setDraft((current) => current.trim() ? current : text);
    requestAnimationFrame(() => (embedded ? inputRef.current : legacyInputRef.current)?.focus());
  };

  const handleClear = () => {
    if (busy) return;
    if (!confirmingClear) {
      setConfirmingClear(true);
      return;
    }
    setConfirmingClear(false);
    void clearConversation();
  };

  const providerLabel = providerState?.chat_backend_label?.trim() || (isLmStudioLocal ? t('aiChat.header.local_badge') : provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : '');

  const bottomGap = Math.max(0, Math.round(bottomOffsetPx));
  const panelStyle: CSSProperties = {
    paddingBottom: 'env(safe-area-inset-bottom)',
    ...(resizable.isDesktop
      ? {
          position: 'fixed',
          left: resizable.rect.left,
          top: resizable.rect.top,
          width: resizable.rect.width,
          height: resizable.rect.height - bottomGap,
          maxHeight: resizable.rect.height - bottomGap,
        }
      : {}),
  };

  return (
    <section
      data-slot="ai-chat-panel"
      data-testid="ai-chat-panel"
      role={embedded ? undefined : "dialog"}
      aria-label={t('aiChat.title')}
      aria-busy={busy}
      onKeyDown={(e) => {
        if (!embedded && e.key === 'Escape') onClose?.();
      }}
      className={embedded ? "flex h-full min-h-0 min-w-0 w-full flex-col bg-surface text-text-primary" : "fixed inset-x-0 bottom-0 z-[90] flex max-h-[72vh] flex-col rounded-t-xl border border-border bg-surface-raised text-text-primary shadow-lg sm:inset-x-auto sm:rounded-xl"}
      style={embedded ? undefined : panelStyle}
    >
      <header className="shrink-0 border-b border-border px-3 py-2">
        {embedded && !protagonist && <CopilotHeader
          hasModel={Boolean(headerModel)}
          providerLabel={providerLabel}
          model={headerModel}
          onRefresh={() => void loadProviderState()}
          onClear={handleClear}
          onClearBlur={() => setConfirmingClear(false)}
          refreshing={providerStateLoading}
          busy={busy}
          clearing={clearing}
          confirmingClear={confirmingClear}
        />}
        {!embedded && <div className="flex items-center justify-between gap-2">
          <h2 className="shrink-0 whitespace-nowrap text-sm font-semibold">
            {t('aiChat.title')}
          </h2>
          <button
            type="button"
            data-testid="ai-chat-close"
            aria-label={t('aiChat.close')}
            onClick={onClose}
            className="shrink-0 rounded px-1.5 py-0.5 text-sm text-text-muted hover:text-text-primary"
          >
            ×
          </button>
        </div>}
        {(!embedded || protagonist) && <div className={`mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] ${protagonist ? 'mx-auto w-full max-w-3xl' : ''}`}>
          {isLmStudioLocal && (
            <span
              data-testid="ai-chat-local-badge"
              className="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 font-medium text-text-secondary"
            >
              {providerState?.chat_backend_label?.trim() || t('aiChat.header.local_badge')}
            </span>
          )}
          {headerModel && (embedded ? (
            <details className="min-w-0 max-w-full text-text-secondary">
              <summary className="cursor-pointer">{t('aiChat.activity.model')}</summary>
              <span data-testid="ai-chat-model-chip" title={headerModel} className="block break-all font-mono text-text-secondary">{headerModel}</span>
            </details>
          ) : (
            <span data-testid="ai-chat-model-chip" className="min-w-0 max-w-full truncate font-mono text-text-muted" title={headerModel}>{headerModel}</span>
          ))}
          <span
            data-testid="ai-chat-status"
            data-status={status}
            className="ml-auto flex shrink-0 items-center gap-1 text-text-muted"
          >
            {providerStateLoading ? <Spinner size="sm" /> : null}
            {status === 'loading' ? null : t(PANEL_STATUS_KEY[status])}
          </span>
          <button
            type="button"
            data-testid="ai-chat-models-refresh"
            aria-label={t('aiChat.model.refresh')}
            title={t('aiChat.model.refresh')}
            onClick={() => void loadProviderState()}
            disabled={providerStateLoading || busy}
            className="shrink-0 rounded px-1.5 py-0.5 text-text-muted hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            ↻
          </button>
          <button
            type="button"
            data-testid="ai-chat-clear"
            onClick={handleClear}
            onBlur={() => setConfirmingClear(false)}
            disabled={busy}
            aria-busy={clearing}
            className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-text-muted hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {clearing ? <Spinner size="sm" /> : null}
            {confirmingClear
              ? t('aiChat.clear_confirm')
              : t('aiChat.clear')}
          </button>
        </div>}
      </header>

      <div data-testid={embedded ? "ai-chat-column" : undefined} ref={listRef} onScroll={(event) => { const el = event.currentTarget; followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48; }} className={`flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-y-auto px-3 py-2 ${embedded ? 'mx-auto w-full max-w-3xl' : ''}`}>
        {embedded && messages.length === 0 && <div data-testid="ai-chat-welcome" className="mx-auto w-full max-w-3xl py-6 text-text-secondary">
          {protagonist ? <div className="text-center"><div className="mx-auto w-20 [&_.ai-pet__svg]:h-20 [&_.ai-pet__svg]:w-20"><ChatPet /></div><h1 className="mt-4 text-2xl text-text-primary">{t('aiChat.welcome.title')}</h1><p className="mt-2 text-sm">{t('aiChat.welcome.subtitle')}</p></div> : <p className="text-xs font-semibold">{t('aiChat.welcome.compact')}</p>}
        </div>}
        {embedded && <div className="mx-auto w-full max-w-3xl"><EmbeddedWorkflowGuide fillDraft={fillDraft} canDraft={false} /></div>}
        {notice && <NoticeBanner notice={notice} />}
        {!providerStateLoaded && (
          <div
            role="status"
            className="flex items-center gap-2 text-xs text-text-muted"
          >
            <Spinner size="sm" />
            {t('aiChat.header.status_loading')}
          </div>
        )}
        {providerStateLoaded && !chatEnabled && (
          <div
            role="status"
            data-testid="ai-chat-disabled-notice"
            className="rounded-lg border border-border px-3 py-2 text-xs text-text-secondary"
          >
            {t('aiChat.notice.chat_disabled')}
          </div>
        )}
        {providerStateLoaded && chatEnabled && !supportsTools && (
          <div
            role="status"
            data-testid="ai-chat-no-tools-notice"
            className="rounded-lg border border-border px-3 py-2 text-xs text-text-secondary"
          >
            {t('aiChat.notice.provider_no_tools')}
          </div>
        )}
        {placeholderModel && (
          <div
            role="status"
            data-testid="ai-chat-placeholder-model-warning"
            className={`rounded-lg border px-3 py-2 text-xs text-text-primary ${embedded ? 'border-border' : 'border-[var(--color-status-warning)]'}`}
          >
            <p>{t('aiChat.notice.placeholder_model_warn')}</p>
            <label className="mt-2 block">
              <span className="text-[11px] text-text-muted">
                {t('aiChat.model.session_label')}
              </span>
              <input
                type="text"
                data-testid="ai-chat-session-model-input"
                value={sessionModel}
                onChange={(e) => setSessionModel(e.target.value)}
                aria-label={t('aiChat.model.session_label')}
                placeholder="qwen3-32b"
                disabled={busy}
                className="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs disabled:cursor-not-allowed disabled:opacity-50"
              />
            </label>
          </div>
        )}
        {!embedded && chatEnabled && selection.kind === 'pick' && (
          <div
            role="status"
            data-testid={
              selection.model === null
                ? 'ai-chat-models-notice'
                : 'ai-chat-model-selector'
            }
            className={`rounded-lg border px-3 py-2 text-xs text-text-primary ${
              selection.model === null
                ? 'border-[var(--color-status-warning)]'
                : 'border-border'
            }`}
          >
            {selection.model === null && (
              <div className="flex items-start justify-between gap-2">
                <p>{t('aiChat.notice.models_required')}</p>
              </div>
            )}
            <label
              className={selection.model === null ? 'mt-2 block' : 'block'}
            >
              <span className="text-[11px] text-text-muted">
                {t('aiChat.model.selector_label')}
              </span>
              <select
                data-testid="ai-chat-model-select"
                value={selection.model ?? ''}
                onChange={(e) => setSessionModel(e.target.value, 'detected')}
                aria-label={t('aiChat.model.selector_label')}
                disabled={busy}
                className="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">{t('aiChat.model.selector_placeholder')}</option>
                {selection.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {modelOptionLabel(model, selection.models)}
                    {model.tool_use === false
                      ? ` · ${t('aiChat.model.no_tools_suffix')}`
                      : ''}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        {chatEnabled &&
          selection.kind === 'unresolved' &&
          modelsState?.status !== 'disabled' && (
            <div
              role="status"
              data-testid="ai-chat-models-notice"
              className={`rounded-lg border px-3 py-2 text-xs text-text-primary ${embedded ? 'border-border' : 'border-[var(--color-status-warning)]'}`}
            >
              <div className="flex items-start justify-between gap-2">
                <p>
                  {t(
                    selection.status === 'ok'
                      ? 'aiChat.notice.models_none'
                      : selection.status === 'not_supported'
                        ? 'aiChat.notice.models_unsupported'
                        : 'aiChat.notice.models_unreachable',
                  )}
                </p>
              </div>
              <label className="mt-2 block">
                <span className="text-[11px] text-text-muted">
                  {t('aiChat.model.manual_label')}
                </span>
                <input
                  type="text"
                  data-testid="ai-chat-session-model-input"
                  value={sessionModel}
                  onChange={(e) => setSessionModel(e.target.value)}
                  aria-label={t('aiChat.model.manual_label')}
                  placeholder="qwen3-32b"
                  disabled={busy}
                  className="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs disabled:cursor-not-allowed disabled:opacity-50"
                />
              </label>
            </div>
          )}
        {chosenToolUse === false && (
          <div
            role="status"
            data-testid="ai-chat-model-no-tools"
            className={`rounded-lg border px-3 py-2 text-xs text-text-primary ${embedded ? 'border-border' : 'border-[var(--color-status-warning)]'}`}
          >
            {t('aiChat.notice.model_no_tools')}
          </div>
        )}
        {messages.length === 0 && providerStateLoaded && (
          !embedded && <p className="py-4 text-center text-xs text-text-muted">{t('aiChat.messages.empty')}</p>
        )}
        <div
          data-testid="ai-chat-messages"
          role="log"
          aria-live="polite"
          className={embedded ? "mx-auto flex w-full max-w-3xl min-w-0 flex-col" : "flex flex-col gap-2"}
        >
          {embedded ? (() => {
            const groups: Array<ChatMessage | Extract<ChatMessage, { kind: 'tool' }>[]> = [];
            for (const message of messages) {
              const last = groups[groups.length - 1];
              if (message.kind === 'tool') { if (Array.isArray(last)) last.push(message); else groups.push([message]); }
              else groups.push(message);
            }
            return groups.map((item) => Array.isArray(item) ? <ToolActivityGroup key={item[0].id} messages={item} /> : <MessageBubble key={item.id} message={item} embedded />);
          })() : messages.map((message) => <MessageBubble key={message.id} message={message} />)}
        </div>
        {streaming && (
          <div
            role="status"
            data-testid="ai-chat-streaming-indicator"
            className="flex items-center gap-2 text-xs text-text-muted"
          >
            <Spinner size="sm" />
            {t('aiChat.messages.streaming')}
          </div>
        )}
      </div>

      <div
        hidden={embedded && !attachmentsOpen}
        className={`shrink-0 ${embedded ? 'px-3' : ''}`}
      >
        <TopoUploadZone />
      </div>

      {embedded && !protagonist && <ContextChip />}
      <form
        data-testid="ai-chat-composer"
        className={embedded ? "mx-auto w-full max-w-3xl shrink-0 px-3 py-2" : "flex shrink-0 items-end gap-2 border-t border-border px-3 py-2"}
        onSubmit={(e) => {
          e.preventDefault();
          handleSubmit();
        }}
      >
        <div data-testid={embedded ? "ai-chat-composer-box" : undefined} className={embedded ? "grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2 rounded-xl border border-border bg-surface-raised p-2 focus-within:ring-1 focus-within:ring-accent" : "contents"}>
        {embedded && (
          <textarea
            ref={inputRef}
            rows={protagonist ? 3 : 1}
            data-testid="ai-chat-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || isComposing || isTouchDevice) return;
              event.preventDefault();
              handleSubmit();
            }}
            placeholder={t('aiChat.input.placeholder')}
            aria-label={t('aiChat.input.aria')}
            className={`col-span-2 row-start-1 w-full min-w-0 resize-none overflow-y-hidden border-0 bg-transparent px-1 py-1.5 text-sm leading-5 outline-none ${protagonist ? 'min-h-[4.5rem]' : 'min-h-[2.25rem]'}`}
          />
        )}
        {embedded && (
          <button
            type="button"
            data-testid="ai-chat-attachments"
            aria-label={t('aiChat.activity.surfaces')}
            title={t('aiChat.activity.surfaces')}
            aria-expanded={attachmentsOpen}
            onClick={() => setAttachmentsOpen((open) => !open)}
            className="col-start-1 row-start-2 justify-self-start shrink-0 rounded-md border border-border px-2 py-1.5 text-sm text-text-secondary hover:bg-surface-muted"
          >
            <span aria-hidden="true">+ </span>{t('aiChat.activity.surfaces')}
          </button>
        )}
        {embedded && chatEnabled && selection.kind === 'pick' && (
          <label className="col-start-1 row-start-2 ml-28 min-w-0 justify-self-start text-xs text-text-muted">
            <span className="sr-only">{t('aiChat.model.selector_label')}</span>
            <select data-testid="ai-chat-model-select" value={selection.model ?? ''} onChange={(event) => setSessionModel(event.target.value, 'detected')} aria-label={t('aiChat.model.selector_label')} disabled={busy} className="max-w-full rounded border border-border bg-surface px-2 py-1.5 text-xs">
              <option value="">{t('aiChat.model.selector_placeholder')}</option>
              {selection.models.map((model) => <option key={model.id} value={model.id}>{modelOptionLabel(model, selection.models)}{model.tool_use === false ? ` · ${t('aiChat.model.no_tools_suffix')}` : ''}</option>)}
            </select>
            {selection.model === null && <span data-testid="ai-chat-models-notice" className="block mt-1 text-text-secondary">{t('aiChat.notice.models_required')}</span>}
          </label>
        )}
        {embedded && headerModel && selection.kind !== 'pick' && <span title={headerModel} className="col-start-1 row-start-2 ml-28 min-w-0 truncate text-xs text-text-muted">{headerModel}</span>}
        {!embedded && (
          <input
            ref={legacyInputRef}
            type="text"
            data-testid="ai-chat-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t('aiChat.input.placeholder')}
            aria-label={t('aiChat.input.aria')}
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
          />
        )}
        {turnActive ? (
          <button
            type="button"
            data-testid="ai-chat-stop"
            onClick={abort}
            className={embedded ? "col-start-2 row-start-2 flex shrink-0 items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-muted" : "flex shrink-0 items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-muted"}
          >
            <Spinner size="sm" />
            {t('aiChat.input.stop')}
          </button>
        ) : (
          <button
            type="submit"
            data-testid="ai-chat-send"
            disabled={clearing || !draft.trim()}
            className={embedded ? "calm-primary col-start-2 row-start-2 shrink-0 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:cursor-not-allowed disabled:opacity-50" : "calm-primary shrink-0 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:cursor-not-allowed disabled:opacity-50"}
          >
            {t('aiChat.input.send')}
          </button>
        )}
        </div>
      </form>
      {protagonist && messages.length === 0 && <EmbeddedWorkflowGuide suggestionsOnly fillDraft={fillDraft} canDraft={providerStateLoaded && !turnActive && !clearing} />}

      {!embedded && resizable.isDesktop &&
        RESIZE_HANDLES.map(({ direction, labelKey, orientation, className }) => (
          <div
            key={direction}
            role="separator"
            data-testid={`ai-chat-resize-${direction}`}
            aria-label={t(`aiChat.resize.${labelKey}`)}
            aria-orientation={orientation}
            tabIndex={0}
            onPointerDown={(e) => resizable.startResize(direction, e)}
            onPointerMove={resizable.onResizeMove}
            onPointerUp={resizable.endResize}
            onPointerCancel={resizable.endResize}
            onKeyDown={(e) => resizable.adjustFromKeyboard(direction, e)}
            className={`absolute z-20 touch-none ${className}`}
          />
        ))}
    </section>
  );
}
