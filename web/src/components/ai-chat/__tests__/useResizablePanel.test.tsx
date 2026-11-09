import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => 'sess-resize',
}));

import type { AIProvidersState } from '../../../api/aiChat';
import { useAIChat } from '../../../stores/aiChat';
import { ChatPanel } from '../ChatPanel';
import { PANEL_RECT_STORAGE_KEY, type PanelRect } from '../useResizablePanel';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

function providersBody(): AIProvidersState {
  return {
    providers: ['ollama', 'lmstudio', 'openai'],
    supports_tool_calls: { ollama: false, lmstudio: true, openai: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'qwen3-32b',
  };
}

function stubMatchMedia(matches: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches,
      media: '(min-width: 640px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  );
}

const SEED: PanelRect = { left: 100, top: 100, width: 380, height: 480 };

function seedRect(rect: PanelRect): void {
  window.localStorage.setItem(PANEL_RECT_STORAGE_KEY, JSON.stringify(rect));
}

function storedRect(): PanelRect {
  return JSON.parse(
    window.localStorage.getItem(PANEL_RECT_STORAGE_KEY) ?? 'null',
  ) as PanelRect;
}

function renderPanel(): HTMLElement {
  renderWithProviders(<ChatPanel onClose={() => undefined} />);
  return screen.getByTestId('ai-chat-panel');
}

function dragHandle(
  direction: string,
  from: { x: number; y: number },
  to: { x: number; y: number },
): void {
  const handle = screen.getByTestId(`ai-chat-resize-${direction}`);
  fireEvent.pointerDown(handle, { pointerId: 1, clientX: from.x, clientY: from.y });
  fireEvent.pointerMove(handle, { pointerId: 1, clientX: to.x, clientY: to.y });
  fireEvent.pointerUp(handle, { pointerId: 1, clientX: to.x, clientY: to.y });
}

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockGet.mockResolvedValue({ data: providersBody() });
  initChatI18n();
  useAIChat.getState().reset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatPanel — resizable panel rect (desktop)', () => {
  it('mounts with the default rect anchored bottom-right when nothing is stored', () => {
    const panel = renderPanel();
    expect(panel.style.width).toBe('380px');
    expect(panel.style.height).toBe('480px');
    expect(panel.style.position).toBe('fixed');
    expect(panel.style.left).toBe(`${window.innerWidth - 380 - 16}px`);
    expect(panel.style.top).toBe(`${window.innerHeight - 480 - 16}px`);
  });

  it("dragging 'e' moves the east edge: width +60 and left unchanged", () => {
    seedRect(SEED);
    const panel = renderPanel();
    dragHandle('e', { x: 400, y: 400 }, { x: 460, y: 400 });
    expect(panel.style.width).toBe('440px');
    expect(panel.style.left).toBe('100px');
    expect(storedRect()).toEqual({ left: 100, top: 100, width: 440, height: 480 });
  });

  it("dragging 'w' moves the west edge: width +60 and left -60", () => {
    seedRect(SEED);
    const panel = renderPanel();
    dragHandle('w', { x: 300, y: 400 }, { x: 240, y: 400 });
    expect(panel.style.width).toBe('440px');
    expect(panel.style.left).toBe('40px');
    expect(storedRect()).toEqual({ left: 40, top: 100, width: 440, height: 480 });
  });

  it("dragging 'n' moves the north edge: height +60 and top -60", () => {
    seedRect({ left: 100, top: 200, width: 380, height: 480 });
    const panel = renderPanel();
    dragHandle('n', { x: 500, y: 400 }, { x: 500, y: 340 });
    expect(panel.style.height).toBe('540px');
    expect(panel.style.top).toBe('140px');
  });

  it("dragging 's' moves the south edge: height +60 and top unchanged", () => {
    seedRect(SEED);
    const panel = renderPanel();
    dragHandle('s', { x: 500, y: 400 }, { x: 500, y: 460 });
    expect(panel.style.height).toBe('540px');
    expect(panel.style.top).toBe('100px');
    expect(storedRect()).toEqual({ left: 100, top: 100, width: 380, height: 540 });
  });

  it("corner 'se' resizes both axes keeping left/top unchanged", () => {
    seedRect(SEED);
    const panel = renderPanel();
    dragHandle('se', { x: 500, y: 500 }, { x: 540, y: 540 });
    expect(panel.style.width).toBe('420px');
    expect(panel.style.height).toBe('520px');
    expect(panel.style.left).toBe('100px');
    expect(panel.style.top).toBe('100px');
  });

  it('clamps both dimensions at the 320px minimum', () => {
    seedRect({ left: 400, top: 100, width: 380, height: 480 });
    const panel = renderPanel();

    dragHandle('w', { x: 300, y: 400 }, { x: 5000, y: 400 });
    expect(panel.style.width).toBe('320px');
    expect(panel.style.left).toBe('460px');

    dragHandle('n', { x: 500, y: 300 }, { x: 500, y: 5000 });
    expect(panel.style.height).toBe('320px');
    expect(panel.style.top).toBe('260px');
  });

  it('keeps the east/south edges inside the viewport margin (8px)', () => {
    seedRect(SEED);
    const first = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const panel = screen.getByTestId('ai-chat-panel');

    dragHandle('e', { x: 400, y: 400 }, { x: 5000, y: 400 });
    expect(panel.style.width).toBe(`${window.innerWidth - 108}px`);
    expect(100 + (window.innerWidth - 8 - 100)).toBeLessThanOrEqual(
      window.innerWidth - 8,
    );
    first.unmount();

    seedRect(SEED);
    const secondRender = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const second = screen.getByTestId('ai-chat-panel');
    dragHandle('s', { x: 500, y: 400 }, { x: 500, y: 5000 });
    expect(second.style.height).toBe(`${window.innerHeight - 108}px`);
    expect(100 + (window.innerHeight - 8 - 100)).toBeLessThanOrEqual(
      window.innerHeight - 8,
    );
    secondRender.unmount();
  });

  it('keeps the west/north edges inside the viewport margin (8px)', () => {
    seedRect(SEED);
    const first = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const panel = screen.getByTestId('ai-chat-panel');

    dragHandle('w', { x: 300, y: 400 }, { x: -5000, y: 400 });
    expect(panel.style.left).toBe('8px');
    expect(panel.style.width).toBe(`${100 + 380 - 8}px`);
    first.unmount();

    seedRect({ left: 100, top: 200, width: 380, height: 480 });
    const secondRender = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const second = screen.getByTestId('ai-chat-panel');
    dragHandle('n', { x: 500, y: 400 }, { x: 500, y: -5000 });
    expect(second.style.top).toBe('8px');
    expect(second.style.height).toBe(`${200 + 480 - 8}px`);
    secondRender.unmount();
  });

  it('persists the full rect on pointerUp and restores left/top after remount', () => {
    seedRect(SEED);
    const first = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const panel = screen.getByTestId('ai-chat-panel');
    dragHandle('w', { x: 300, y: 400 }, { x: 240, y: 400 });
    dragHandle('s', { x: 500, y: 400 }, { x: 500, y: 460 });
    expect(panel.style.left).toBe('40px');
    expect(storedRect()).toEqual({ left: 40, top: 100, width: 440, height: 540 });
    first.unmount();

    const restored = renderPanel();
    expect(restored.style.left).toBe('40px');
    expect(restored.style.top).toBe('100px');
    expect(restored.style.width).toBe('440px');
    expect(restored.style.height).toBe('540px');
  });

  it('falls back to the clamped default rect on corrupt JSON', () => {
    window.localStorage.setItem(PANEL_RECT_STORAGE_KEY, '{not json');
    const panel = renderPanel();
    expect(panel.style.width).toBe('380px');
    expect(panel.style.height).toBe('480px');
    expect(panel.style.left).toBe(`${window.innerWidth - 380 - 16}px`);
    expect(panel.style.top).toBe(`${window.innerHeight - 480 - 16}px`);
  });

  it('clamps an out-of-range stored rect into the current viewport', () => {
    seedRect({ left: -9999, top: -9999, width: 99999, height: -50 });
    const panel = renderPanel();
    expect(panel.style.width).toBe(`${window.innerWidth - 16}px`);
    expect(panel.style.height).toBe('320px');
    expect(panel.style.left).toBe('8px');
    expect(panel.style.top).toBe('8px');
  });

  it('re-anchors a legacy stored {width, height} without left/top bottom-right', () => {
    window.localStorage.setItem(
      PANEL_RECT_STORAGE_KEY,
      JSON.stringify({ width: 420, height: 500 }),
    );
    const panel = renderPanel();
    expect(panel.style.width).toBe('420px');
    expect(panel.style.height).toBe('500px');
    expect(panel.style.left).toBe(`${window.innerWidth - 420 - 16}px`);
    expect(panel.style.top).toBe(`${window.innerHeight - 500 - 16}px`);
  });

  it('keyboard on the west handle moves width and left by 16px (64 with Shift) and persists', () => {
    const panel = renderPanel();
    const handle = screen.getByTestId('ai-chat-resize-w');
    handle.focus();

    fireEvent.keyDown(handle, { key: 'ArrowLeft' });
    expect(panel.style.width).toBe('396px');
    expect(panel.style.left).toBe(`${window.innerWidth - 380 - 16 - 16}px`);
    fireEvent.keyDown(handle, { key: 'ArrowLeft', shiftKey: true });
    expect(panel.style.width).toBe('460px');
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(panel.style.width).toBe('444px');

    expect(storedRect()).toEqual({
      left: window.innerWidth - 380 - 16 - 16 - 64 + 16,
      top: window.innerHeight - 480 - 16,
      width: 444,
      height: 480,
    });
  });

  it('keyboard on the east handle grows eastward keeping left fixed', () => {
    seedRect(SEED);
    const panel = renderPanel();
    const handle = screen.getByTestId('ai-chat-resize-e');
    handle.focus();

    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(panel.style.width).toBe('396px');
    expect(panel.style.left).toBe('100px');
    expect(storedRect()).toEqual({ left: 100, top: 100, width: 396, height: 480 });
  });

  it('re-clamps the rect when the window resizes', () => {
    seedRect({
      left: window.innerWidth - 380 - 16,
      top: window.innerHeight - 480 - 16,
      width: 380,
      height: 480,
    });
    const panel = renderPanel();
    const descriptor = Object.getOwnPropertyDescriptor(window, 'innerWidth');
    Object.defineProperty(window, 'innerWidth', {
      value: 500,
      configurable: true,
      writable: true,
    });
    try {
      fireEvent(window, new Event('resize'));
      expect(panel.style.left).toBe('112px');
      expect(panel.style.width).toBe('380px');
    } finally {
      if (descriptor) Object.defineProperty(window, 'innerWidth', descriptor);
      else Reflect.deleteProperty(window, 'innerWidth');
    }
  });

  it('renders all eight handles with separator role and localized labels', () => {
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    for (const direction of ['n', 's', 'e', 'w', 'nw', 'ne', 'sw', 'se']) {
      const handle = screen.getByTestId(`ai-chat-resize-${direction}`);
      expect(handle).toHaveAttribute('role', 'separator');
      expect(handle).toHaveAttribute('tabindex', '0');
      expect(handle).toHaveAttribute(
        'aria-label',
        expect.stringContaining('Redimensionar panel'),
      );
    }
    expect(screen.getByTestId('ai-chat-resize-w')).toHaveAttribute(
      'aria-orientation',
      'vertical',
    );
    expect(screen.getByTestId('ai-chat-resize-n')).toHaveAttribute(
      'aria-orientation',
      'horizontal',
    );
  });
});

describe('ChatPanel — resizable panel (mobile bottom sheet)', () => {
  it('hides the handles and applies neither inline size nor rect', () => {
    stubMatchMedia(false);
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const panel = screen.getByTestId('ai-chat-panel');
    for (const direction of ['n', 's', 'e', 'w', 'nw', 'ne', 'sw', 'se']) {
      expect(
        screen.queryByTestId(`ai-chat-resize-${direction}`),
      ).toBeNull();
    }
    expect(panel.style.width).toBe('');
    expect(panel.style.height).toBe('');
    expect(panel.style.maxHeight).toBe('');
    expect(panel.style.left).toBe('');
    expect(panel.style.top).toBe('');
    expect(panel.style.position).toBe('');
  });
});
