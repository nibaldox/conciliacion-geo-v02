import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';

const { mockGet, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockFetch: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => 'sess-scroll',
}));

import type { AIProvidersState } from '../../../api/aiChat';
import { useAIChat, type ChatMessage } from '../../../stores/aiChat';
import { ChatPanel } from '../ChatPanel';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

const CLIENT_HEIGHT = 400;
const CONTENT_HEIGHT_BASE = 1000;

let contentHeight = CONTENT_HEIGHT_BASE;
const scrollPositions = new WeakMap<Element, number>();

const SCROLL_PROPERTIES = ['scrollHeight', 'clientHeight', 'scrollTop'] as const;
const originalDescriptors = SCROLL_PROPERTIES.map(
  (name) => [name, Object.getOwnPropertyDescriptor(Element.prototype, name)] as const,
);

function stubScrollGeometry(): void {
  Object.defineProperty(Element.prototype, 'scrollHeight', {
    configurable: true,
    get: () => contentHeight,
  });
  Object.defineProperty(Element.prototype, 'clientHeight', {
    configurable: true,
    get: () => CLIENT_HEIGHT,
  });
  Object.defineProperty(Element.prototype, 'scrollTop', {
    configurable: true,
    get(this: Element) {
      return scrollPositions.get(this) ?? 0;
    },
    set(this: Element, value: number) {
      scrollPositions.set(this, value);
    },
  });
}

function restoreScrollGeometry(): void {
  for (const [name, descriptor] of originalDescriptors) {
    if (descriptor) {
      Object.defineProperty(Element.prototype, name, descriptor);
    } else {
      delete (Element.prototype as unknown as Record<string, unknown>)[name];
    }
  }
}

function providersBody(overrides: Partial<AIProvidersState> = {}): AIProvidersState {
  return {
    providers: ['lmstudio'],
    supports_tool_calls: { lmstudio: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'qwen3-32b',
    ...overrides,
  };
}

const CONVERSATION: ChatMessage[] = [
  { kind: 'user', id: 'u1', text: 'hola' },
  { kind: 'agent', id: 'a1', text: 'Hola' },
];

function scroller(): HTMLElement {
  return screen.getByTestId('ai-chat-scroll');
}

function scrollTo(top: number): void {
  const element = scroller();
  element.scrollTop = top;
  fireEvent.scroll(element);
}

async function mountPanel() {
  mockGet.mockResolvedValue({ data: providersBody() });
  const rendered = renderWithProviders(<ChatPanel onClose={() => undefined} />);
  await waitFor(() =>
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'configured',
    ),
  );
  return rendered;
}

function boxClasses(root: HTMLElement): string[] {
  const offending = /^(rounded-lg|bg-accent|bg-surface|border|max-w-.*)$/;
  return [root, ...Array.from(root.querySelectorAll<HTMLElement>('*'))]
    .flatMap((element) => Array.from(element.classList))
    .filter((name) => offending.test(name));
}

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  initChatI18n();
  useAIChat.getState().reset();
  contentHeight = CONTENT_HEIGHT_BASE;
  stubScrollGeometry();
});

afterEach(() => {
  restoreScrollGeometry();
  vi.unstubAllGlobals();
});

describe('ChatPanel — stick-to-bottom auto-scroll', () => {
  it('follows a streamed delta while pinned to the bottom', async () => {
    await mountPanel();
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Hola' }));
    expect(scroller().scrollTop).toBe(CONTENT_HEIGHT_BASE - CLIENT_HEIGHT);

    contentHeight = 1200;
    act(() =>
      useAIChat.getState().applyAgentEvent({ type: 'text', content: ', ¿en qué te ayudo?' }),
    );
    expect(scroller().scrollTop).toBe(1200 - CLIENT_HEIGHT);
  });

  it('does not yank the user back down while they read above the bottom', async () => {
    await mountPanel();
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Hola' }));
    scrollTo(100);

    contentHeight = 1200;
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: ' mundo' }));
    expect(scroller().scrollTop).toBe(100);
  });

  it('resumes following once the user scrolls back near the bottom', async () => {
    await mountPanel();
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Hola' }));
    scrollTo(100);

    scrollTo(CONTENT_HEIGHT_BASE - CLIENT_HEIGHT - 10);
    contentHeight = 1200;
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: ' mundo' }));
    expect(scroller().scrollTop).toBe(1200 - CLIENT_HEIGHT);
  });

  it('a sent user message jumps to the bottom even after scrolling up', async () => {
    await mountPanel();
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    scrollTo(100);

    act(() =>
      useAIChat.setState({
        messages: [...CONVERSATION, { kind: 'user', id: 'u2', text: 'otra pregunta' }],
      }),
    );
    expect(scroller().scrollTop).toBe(CONTENT_HEIGHT_BASE - CLIENT_HEIGHT);
  });

  it('keeps the view pinned when the streaming indicator appears', async () => {
    await mountPanel();
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    contentHeight = 1100;
    act(() => useAIChat.setState({ streaming: true }));
    expect(scroller().scrollTop).toBe(1100 - CLIENT_HEIGHT);
  });

  it('re-pins to the bottom when the scroll box resizes while following', async () => {
    let notifyResize: (() => void) | null = null;
    class StubResizeObserver {
      constructor(callback: () => void) {
        notifyResize = callback;
      }
      observe() {
        return undefined;
      }
      unobserve() {
        return undefined;
      }
      disconnect() {
        return undefined;
      }
    }
    vi.stubGlobal('ResizeObserver', StubResizeObserver);
    await mountPanel();
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    contentHeight = 1300;
    act(() => notifyResize?.());
    expect(scroller().scrollTop).toBe(1300 - CLIENT_HEIGHT);
  });

  it('shows a jump-to-latest button when content arrives while scrolled up', async () => {
    await mountPanel();
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: 'Hola' }));
    scrollTo(100);
    expect(screen.queryByTestId('ai-chat-scroll-latest')).toBeNull();

    contentHeight = 1200;
    act(() => useAIChat.getState().applyAgentEvent({ type: 'text', content: ' mundo' }));
    const jump = screen.getByTestId('ai-chat-scroll-latest');
    expect(jump).toHaveTextContent('Ir a lo último');

    await act(async () => {
      jump.click();
    });
    expect(scroller().scrollTop).toBe(1200 - CLIENT_HEIGHT);
    expect(screen.queryByTestId('ai-chat-scroll-latest')).toBeNull();
  });
});

describe('ChatPanel — keeps the position across close and reopen', () => {
  it('restores the last-read scrollTop when closed while scrolled up', async () => {
    const first = await mountPanel();
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    scrollTo(100);
    first.unmount();
    expect(useAIChat.getState().panelScroll).toEqual({ top: 100, atBottom: false });

    await mountPanel();
    expect(scroller().scrollTop).toBe(100);
  });

  it('reopens at the bottom when it was pinned, including content added while closed', async () => {
    const first = await mountPanel();
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    first.unmount();
    expect(useAIChat.getState().panelScroll).toEqual({
      top: CONTENT_HEIGHT_BASE - CLIENT_HEIGHT,
      atBottom: true,
    });

    contentHeight = 1500;
    await mountPanel();
    expect(scroller().scrollTop).toBe(1500 - CLIENT_HEIGHT);
  });

  it('first open with restored history starts at the latest message, not the top', async () => {
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    await mountPanel();
    expect(scroller().scrollTop).toBe(CONTENT_HEIGHT_BASE - CLIENT_HEIGHT);
  });
});

describe('ChatPanel — minimal message rendering', () => {
  it('renders user, agent and observation turns without bubble boxes', async () => {
    await mountPanel();
    act(() =>
      useAIChat.setState({
        messages: [
          { kind: 'user', id: 'u1', text: 'pregunta' },
          { kind: 'agent', id: 'a1', text: 'respuesta' },
          { kind: 'observation', id: 'o1', text: 'Operación cancelada' },
        ],
      }),
    );
    const user = document.querySelector<HTMLElement>('[data-kind="user"]');
    const agent = document.querySelector<HTMLElement>('[data-kind="agent"]');
    const observation = document.querySelector<HTMLElement>(
      '[data-slot="ai-chat-observation"]',
    );
    expect(user).not.toBeNull();
    expect(agent).not.toBeNull();
    expect(observation).not.toBeNull();
    expect(boxClasses(user!)).toEqual([]);
    expect(boxClasses(agent!)).toEqual([]);
    expect(boxClasses(observation!)).toEqual([]);
    expect(user!.textContent).toContain('pregunta');
    expect(agent!.textContent).toContain('respuesta');
  });

  it('keeps the you and agent labels screen-reader only', async () => {
    await mountPanel();
    act(() => useAIChat.setState({ messages: CONVERSATION }));
    const user = document.querySelector<HTMLElement>('[data-kind="user"]')!;
    const agent = document.querySelector<HTMLElement>('[data-kind="agent"]')!;
    expect(user.querySelector('.sr-only')).toHaveTextContent('Tú');
    expect(agent.querySelector('.sr-only')).toHaveTextContent('Asistente');
  });
});
