import { useEffect, useRef, useState } from 'react';
import {
  useAIChat,
  type ChatMessage,
  type ChatNotice,
  type PendingConfirmation,
} from '../../stores/aiChat';

export type PetState =
  'idle' | 'thinking' | 'tool' | 'confirm' | 'done' | 'error' | 'off' | 'unread';
export const DONE_HOLD_MS = 2400;

interface PetStateInput {
  streaming: boolean;
  sendInFlight: boolean;
  messages: ChatMessage[];
  pendingConfirmation: PendingConfirmation | null;
  notice: ChatNotice | null;
  providerStateLoaded: boolean;
  chatEnabled: boolean;
  supportsTools: boolean;
  unread: boolean;
  justFinished: boolean;
}

export function derivePetState(input: PetStateInput): PetState {
  if (
    input.pendingConfirmation ||
    input.messages.some((m) => m.kind === 'confirmation' && m.resolution === 'pending')
  )
    return 'confirm';
  const active = input.streaming || input.sendInFlight;
  const lastTool = [...input.messages].reverse().find((m) => m.kind === 'tool');
  if (active && lastTool?.kind === 'tool' && lastTool.status === 'running') return 'tool';
  if (active) return 'thinking';
  if (input.notice?.severity === 'error') return 'error';
  if (input.justFinished) return 'done';
  if (input.unread) return 'unread';
  if (input.providerStateLoaded && (!input.chatEnabled || !input.supportsTools)) return 'off';
  return 'idle';
}

export function usePetState({ unread }: { unread: boolean }): PetState {
  const streaming = useAIChat((s) => s.streaming);
  const sendInFlight = useAIChat((s) => s.sendInFlight);
  const messages = useAIChat((s) => s.messages);
  const pendingConfirmation = useAIChat((s) => s.pendingConfirmation);
  const notice = useAIChat((s) => s.notice);
  const providerState = useAIChat((s) => s.providerState);
  const providerStateLoaded = useAIChat((s) => s.providerStateLoaded);
  const active = streaming || sendInFlight;
  const wasActive = useRef(active);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [justFinished, setJustFinished] = useState(false);
  useEffect(() => {
    if (active) {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      setJustFinished(false);
    } else if (wasActive.current && notice?.severity !== 'error') {
      setJustFinished(true);
      timer.current = setTimeout(() => {
        setJustFinished(false);
        timer.current = null;
      }, DONE_HOLD_MS);
    }
    wasActive.current = active;
  }, [active, notice?.severity]);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const provider = providerState?.chat_provider ?? null;
  return derivePetState({
    streaming,
    sendInFlight,
    messages,
    pendingConfirmation,
    notice,
    providerStateLoaded,
    chatEnabled: providerState?.chat_enabled ?? false,
    supportsTools: provider ? providerState?.supports_tool_calls[provider] !== false : true,
    unread,
    justFinished,
  });
}
