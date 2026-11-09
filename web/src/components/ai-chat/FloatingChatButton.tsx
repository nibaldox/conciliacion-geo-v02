import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { useAIChat, WRITE_TOOL_QUERY_KEYS } from '../../stores/aiChat';
import { ChatPanel } from './ChatPanel';

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

export function FloatingChatButton() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  useAgentChatInvalidationBridge();

  if (!isChatUiEnabled(import.meta.env.VITE_AI_CHAT)) return null;

  return (
    <>
      {!open && (
        <button
          type="button"
          data-slot="ai-chat-button"
          data-testid="ai-chat-button"
          aria-label={t('aiChat.open')}
          onClick={() => setOpen(true)}
          className="fixed right-4 z-[85] flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-fg shadow-lg hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            className="h-6 w-6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 8.5-8.5 8.38 8.38 0 0 1 8.5 8.5Z" />
          </svg>
        </button>
      )}
      {open && <ChatPanel onClose={() => setOpen(false)} />}
    </>
  );
}
