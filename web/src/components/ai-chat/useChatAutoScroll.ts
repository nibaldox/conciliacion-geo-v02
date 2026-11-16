import { useLayoutEffect, useRef, useState, type RefObject } from 'react';
import {
  useAIChat,
  type ChatMessage,
  type PanelScrollState,
} from '../../stores/aiChat';

const BOTTOM_THRESHOLD_PX = 48;

function isNearBottom(element: HTMLElement): boolean {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    BOTTOM_THRESHOLD_PX
  );
}

function measure(element: HTMLElement): PanelScrollState {
  return { top: element.scrollTop, atBottom: isNearBottom(element) };
}

function followBottom(element: HTMLElement, position: PanelScrollState): void {
  element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
  position.top = element.scrollTop;
  position.atBottom = true;
}

function lastUserMessageId(messages: ChatMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.kind === 'user') return message.id;
  }
  return null;
}

export function useChatAutoScroll({
  scrollRef,
  contentRef,
  messages,
}: {
  scrollRef: RefObject<HTMLDivElement | null>;
  contentRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessage[];
}) {
  const positionRef = useRef<PanelScrollState>({ top: 0, atBottom: true });
  const seenMessagesRef = useRef<ChatMessage[]>(messages);
  const seenUserIdRef = useRef<string | null>(lastUserMessageId(messages));
  const [unseen, setUnseen] = useState(false);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return undefined;
    const position = positionRef.current;
    const saved = useAIChat.getState().panelScroll;
    if (saved && !saved.atBottom) {
      element.scrollTop = saved.top;
      Object.assign(position, measure(element));
    } else {
      followBottom(element, position);
    }
    return () => {
      useAIChat.getState().setPanelScroll({
        top: position.top,
        atBottom: position.atBottom,
      });
    };
  }, [scrollRef]);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const position = positionRef.current;
    const userId = lastUserMessageId(messages);
    if (messages.length === 0) {
      position.top = 0;
      position.atBottom = true;
    } else if (userId !== null && userId !== seenUserIdRef.current) {
      position.atBottom = true;
    }
    seenUserIdRef.current = userId;
    const contentChanged = seenMessagesRef.current !== messages;
    seenMessagesRef.current = messages;
    if (position.atBottom) {
      followBottom(element, position);
      setUnseen(false);
    } else if (contentChanged) {
      setUnseen(true);
    }
  });

  useLayoutEffect(() => {
    const ResizeObserverType = globalThis.ResizeObserver;
    const element = scrollRef.current;
    const content = contentRef.current;
    if (!ResizeObserverType || !element || !content) return undefined;
    const observer = new ResizeObserverType(() => {
      const scroller = scrollRef.current;
      if (scroller && positionRef.current.atBottom) {
        followBottom(scroller, positionRef.current);
      }
    });
    observer.observe(element);
    observer.observe(content);
    return () => observer.disconnect();
  }, [scrollRef, contentRef]);

  const handleScroll = () => {
    const element = scrollRef.current;
    const position = positionRef.current;
    if (!element || element.scrollTop === position.top) return;
    Object.assign(position, measure(element));
    if (position.atBottom) setUnseen(false);
  };

  const jumpToLatest = () => {
    const element = scrollRef.current;
    if (!element) return;
    followBottom(element, positionRef.current);
    setUnseen(false);
  };

  return { unseen, handleScroll, jumpToLatest };
}
