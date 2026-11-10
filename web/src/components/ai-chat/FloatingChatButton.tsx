import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { useAIChat, WRITE_TOOL_QUERY_KEYS } from '../../stores/aiChat';
import { ChatPanel } from './ChatPanel';
import { ChatPet } from './ChatPet';

/**
 * Build-time feature flag for the whole chat UI. When VITE_AI_CHAT is
 * not enabled the button (and everything behind it) is not rendered at
 * all — not hidden with CSS, absent from the DOM.
 */
export function isChatUiEnabled(envValue: string | undefined): boolean {
  return envValue === 'true' || envValue === '1';
}

/**
 * Bridge between the chat store and TanStack Query: after a WRITE tool
 * completes inside the agent turn, invalidate the affected session
 * queries so the dashboard reflects what the agent did. Registered here
 * (inside the QueryClientProvider) so invalidation works even when the
 * panel itself is closed mid-stream.
 */
function useAgentChatInvalidationBridge() {
  const queryClient = useQueryClient();
  useEffect(() => {
    useAIChat.getState().setWriteResultObserver((toolName) => {
      const queryKeys = WRITE_TOOL_QUERY_KEYS[toolName];
      if (!queryKeys) return;
      for (const queryKey of queryKeys) {
        void queryClient.invalidateQueries({ queryKey });
      }
    });
    return () => {
      useAIChat.getState().setWriteResultObserver(null);
    };
  }, [queryClient]);
}

/**
 * Desktop-only extra gap between the panel's bottom edge and the stored
 * rect bottom, so the launcher button (56px + 12px clearance) stays
 * visible below the panel instead of being covered by it. The button
 * renders at z-[95] above the panel's z-[90].
 */
const PANEL_BOTTOM_GAP_PX = 68;

export function FloatingChatButton() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [choreo, setChoreo] = useState<'opening' | 'closing' | null>(null);
  const [unread, setUnread] = useState(false);
  const streaming = useAIChat((s) => s.streaming);
  const messages = useAIChat((s) => s.messages);
  const agentMessageCount = messages.reduce(
    (count, message) => (message.kind === 'agent' ? count + 1 : count),
    0,
  );
  const wasStreamingRef = useRef(streaming);
  const agentCountRef = useRef(agentMessageCount);
  useAgentChatInvalidationBridge();

  useEffect(() => {
    if (open) {
      setUnread(false);
    } else {
      if (streaming && !wasStreamingRef.current) setUnread(true);
      if (agentMessageCount > agentCountRef.current) setUnread(true);
    }
    wasStreamingRef.current = streaming;
    agentCountRef.current = agentMessageCount;
  }, [open, streaming, agentMessageCount]);

  if (!isChatUiEnabled(import.meta.env.VITE_AI_CHAT)) return null;

  return (
    <>
      <button
        type="button"
        data-slot="ai-chat-button"
        data-testid="ai-chat-button"
        aria-label={t(open ? 'aiChat.close' : 'aiChat.open')}
        onClick={() => {
          setChoreo(open ? 'closing' : 'opening');
          setOpen((v) => !v);
        }}
        className={`ai-chat-launcher group fixed right-4 z-[95] h-14 w-14 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
          open ? 'hidden sm:flex' : 'flex'
        }`}
        style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
      >
        <span
          aria-hidden="true"
          className="pointer-events-none absolute right-full mr-3 hidden whitespace-nowrap rounded-md border border-border bg-surface-raised px-2 py-1 text-xs font-medium text-text-primary opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 sm:block"
        >
          {open ? t('aiChat.close') : t('aiChat.open')}
        </span>
        <span
          aria-hidden="true"
          className={`ai-chat-halo ${choreo === 'opening' ? 'ai-chat-halo--pulse' : ''}`}
        />
        <span
          data-testid="ai-chat-pet-layer"
          aria-hidden="true"
          className={`ai-chat-fade pointer-events-none absolute inset-0 flex items-center justify-center motion-reduce:transition-none ${
            open ? 'opacity-0 ai-chat-pose--pet-hidden' : 'opacity-100'
          } ${
            choreo === 'opening'
              ? 'ai-chat-anim--pet-out'
              : choreo === 'closing'
                ? 'ai-chat-anim--pet-in'
                : ''
          }`}
        >
          <ChatPet streaming={streaming} />
          {unread && (
            <span
              data-testid="ai-chat-pet-unread"
              className="absolute right-0.5 top-0.5 h-3.5 w-3.5 rounded-full border-2 border-[var(--color-surface)] bg-[var(--status-warn-text)]"
            />
          )}
        </span>
        <span
          data-testid="ai-chat-close-icon"
          aria-hidden="true"
          className={`ai-chat-fade pointer-events-none absolute inset-0 flex items-center justify-center text-accent-fg motion-reduce:transition-none ${
            open ? 'opacity-100' : 'opacity-0 ai-chat-pose--x-hidden'
          } ${
            choreo === 'opening'
              ? 'ai-chat-anim--x-in'
              : choreo === 'closing'
                ? 'ai-chat-anim--x-out'
                : ''
          }`}
        >
          <svg
            viewBox="0 0 24 24"
            className="h-6 w-6"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
          >
            <path d="M6 6l12 12" />
            <path d="M18 6L6 18" />
          </svg>
        </span>
      </button>
      {open && (
        <ChatPanel onClose={() => setOpen(false)} bottomOffsetPx={PANEL_BOTTOM_GAP_PX} />
      )}
    </>
  );
}
