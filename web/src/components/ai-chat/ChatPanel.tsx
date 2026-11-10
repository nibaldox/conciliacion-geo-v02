import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { LMSTUDIO_PLACEHOLDER_MODEL } from '../../api/aiChat';
import type { ChatMessage, ChatNotice } from '../../stores/aiChat';
import { useAIChat } from '../../stores/aiChat';
import { Spinner } from '../ui/Spinner';
import { MarkdownMessage } from './MarkdownMessage';
import { TopoUploadZone } from './TopoUploadZone';
import { ConfirmationCard, ToolCallCard } from './ToolCallCard';
import { type ResizeDirection, useResizablePanel } from './useResizablePanel';

const NOTICE_TONE: Record<ChatNotice['severity'], string> = {
  info: 'border-border text-text-secondary',
  warning: 'border-[var(--color-status-warning)] text-text-primary',
  error: 'border-[var(--color-status-error)] text-text-primary',
};

function MessageBubble({ message }: { message: ChatMessage }) {
  const { t } = useTranslation();
  if (message.kind === 'tool') return <ToolCallCard message={message} />;
  if (message.kind === 'confirmation') {
    return <ConfirmationCardLazy message={message} />;
  }
  if (message.kind === 'observation') {
    return (
      <div
        data-slot="ai-chat-observation"
        className="rounded-lg border border-border bg-surface-muted px-3 py-2 text-xs text-text-secondary"
      >
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
      </div>
    );
  }
  const isUser = message.kind === 'user';
  return (
    <div
      data-slot="ai-chat-message"
      data-kind={message.kind}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
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
}

function ConfirmationCardLazy({
  message,
}: {
  message: Extract<ChatMessage, { kind: 'confirmation' }>;
}) {
  const busy = useAIChat((s) => s.streaming);
  const approve = useAIChat((s) => s.approve);
  const deny = useAIChat((s) => s.deny);
  return (
    <ConfirmationCard
      message={message}
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
  onClose: () => void;
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
export function ChatPanel({ onClose, bottomOffsetPx = 0 }: ChatPanelProps) {
  const { t } = useTranslation();
  const resizable = useResizablePanel();
  const messages = useAIChat((s) => s.messages);
  const streaming = useAIChat((s) => s.streaming);
  const providerState = useAIChat((s) => s.providerState);
  const providerStateLoaded = useAIChat((s) => s.providerStateLoaded);
  const sessionModel = useAIChat((s) => s.sessionModel);
  const notice = useAIChat((s) => s.notice);
  const send = useAIChat((s) => s.send);
  const abort = useAIChat((s) => s.abort);
  const setSessionModel = useAIChat((s) => s.setSessionModel);
  const clearConversation = useAIChat((s) => s.clearConversation);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const [draft, setDraft] = useState('');
  const [confirmingClear, setConfirmingClear] = useState(false);

  useEffect(() => {
    void useAIChat.getState().init();
  }, []);

  useEffect(() => {
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    inputRef.current?.focus();
    return () => {
      restoreFocusRef.current?.focus();
    };
  }, []);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages, notice]);

  const chatEnabled = providerState?.chat_enabled ?? false;
  const provider = providerState?.chat_provider ?? null;
  const localOnly = providerState?.chat_local_only ?? false;
  const chatModel = providerState?.chat_model ?? null;
  const placeholderModel = chatEnabled && chatModel === LMSTUDIO_PLACEHOLDER_MODEL;
  const supportsTools = provider
    ? providerState?.supports_tool_calls[provider] !== false
    : true;
  const isLmStudioLocal = localOnly && provider === 'lmstudio';
  const headerModel = placeholderModel && sessionModel.trim()
    ? sessionModel.trim()
    : chatModel;

  const handleSubmit = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    void send(text);
  };

  const handleClear = () => {
    if (!confirmingClear) {
      setConfirmingClear(true);
      return;
    }
    setConfirmingClear(false);
    void clearConversation();
  };

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
      role="dialog"
      aria-label={t('aiChat.title')}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
      className="fixed inset-x-0 bottom-0 z-[90] flex max-h-[72vh] flex-col rounded-t-xl border border-border bg-surface-raised text-text-primary shadow-lg sm:inset-x-auto sm:rounded-xl"
      style={panelStyle}
    >
      <header className="shrink-0 border-b border-border px-3 py-2">
        <div className="flex items-center justify-between gap-2">
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
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
          {isLmStudioLocal && (
            <span
              data-testid="ai-chat-local-badge"
              className="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 font-medium text-text-secondary"
            >
              {t('aiChat.header.local_badge')}
            </span>
          )}
          {headerModel && (
            <span
              data-testid="ai-chat-model-chip"
              className="min-w-0 truncate font-mono text-text-muted"
              title={headerModel}
            >
              {headerModel}
            </span>
          )}
          <span
            data-testid="ai-chat-status"
            className="ml-auto flex shrink-0 items-center gap-1 text-text-muted"
          >
            {!providerStateLoaded ? (
              <Spinner size="sm" />
            ) : chatEnabled && supportsTools ? (
              t('aiChat.header.configured')
            ) : (
              t('aiChat.header.unavailable')
            )}
          </span>
          <button
            type="button"
            data-testid="ai-chat-clear"
            onClick={handleClear}
            onBlur={() => setConfirmingClear(false)}
            className="shrink-0 rounded px-1.5 py-0.5 text-text-muted hover:text-text-primary"
          >
            {confirmingClear
              ? t('aiChat.clear_confirm')
              : t('aiChat.clear')}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3 py-2">
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
            className="rounded-lg border border-[var(--color-status-warning)] px-3 py-2 text-xs text-text-primary"
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
                className="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs"
              />
            </label>
          </div>
        )}
        {messages.length === 0 && providerStateLoaded && (
          <p className="py-4 text-center text-xs text-text-muted">
            {t('aiChat.messages.empty')}
          </p>
        )}
        <div
          ref={listRef}
          data-testid="ai-chat-messages"
          role="log"
          aria-live="polite"
          className="flex flex-col gap-2"
        >
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
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

      <TopoUploadZone />

      <form
        className="flex shrink-0 items-end gap-2 border-t border-border px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          handleSubmit();
        }}
      >
        <input
          ref={inputRef}
          type="text"
          data-testid="ai-chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t('aiChat.input.placeholder')}
          aria-label={t('aiChat.input.aria')}
          className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
        />
        {streaming ? (
          <button
            type="button"
            data-testid="ai-chat-stop"
            onClick={abort}
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-muted"
          >
            {t('aiChat.input.stop')}
          </button>
        ) : (
          <button
            type="submit"
            data-testid="ai-chat-send"
            disabled={!draft.trim()}
            className="shrink-0 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('aiChat.input.send')}
          </button>
        )}
      </form>

      {resizable.isDesktop &&
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
