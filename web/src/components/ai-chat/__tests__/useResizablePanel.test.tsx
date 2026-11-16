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
import { PANEL_SIZE_STORAGE_KEY, type PanelSize } from '../useResizablePanel';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

const LEGACY_RECT_STORAGE_KEY = 'conciliacion.aiChat.panelRect.v1';
const ANCHOR_RIGHT = '16px';
const ANCHOR_BOTTOM = 'calc(84px + env(safe-area-inset-bottom))';
const ORIGINAL_WIDTH = window.innerWidth;
const ORIGINAL_HEIGHT = window.innerHeight;
const DEFAULT_SIZE: PanelSize = { width: 380, height: 480 };

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

function setViewport(width: number, height: number): void {
  Object.defineProperty(window, 'innerWidth', {
    value: width,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, 'innerHeight', {
    value: height,
    configurable: true,
    writable: true,
  });
}

function seedSize(value: unknown): void {
  window.localStorage.setItem(PANEL_SIZE_STORAGE_KEY, JSON.stringify(value));
}

function storedSize(): PanelSize {
  return JSON.parse(
    window.localStorage.getItem(PANEL_SIZE_STORAGE_KEY) ?? 'null',
  ) as PanelSize;
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
  setViewport(1024, 768);
  mockGet.mockReset();
  mockGet.mockResolvedValue({ data: providersBody() });
  initChatI18n();
  useAIChat.getState().reset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  setViewport(ORIGINAL_WIDTH, ORIGINAL_HEIGHT);
});

describe('ChatPanel — desktop panel anchored above the launcher', () => {
  it('anchors right/bottom to the launcher and ignores a stale v1 rect', () => {
    setViewport(1600, 900);
    window.localStorage.setItem(
      LEGACY_RECT_STORAGE_KEY,
      JSON.stringify({ left: 100, top: 50, width: 444, height: 690 }),
    );
    const panel = renderPanel();
    expect(panel.style.position).toBe('fixed');
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
    expect(panel.style.left).toBe('');
    expect(panel.style.top).toBe('');
    expect(panel.style.width).toBe('380px');
    expect(panel.style.height).toBe('480px');
    expect(window.localStorage.getItem(LEGACY_RECT_STORAGE_KEY)).toBeNull();
  });

  it('mounts with the default size anchored when nothing is stored', () => {
    const panel = renderPanel();
    expect(panel.style.width).toBe(`${DEFAULT_SIZE.width}px`);
    expect(panel.style.height).toBe(`${DEFAULT_SIZE.height}px`);
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
  });

  it("dragging 'w' by -100px grows the width by 100 and keeps the right anchor", () => {
    seedSize(DEFAULT_SIZE);
    const panel = renderPanel();
    dragHandle('w', { x: 300, y: 400 }, { x: 200, y: 400 });
    expect(panel.style.width).toBe('480px');
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
    expect(panel.style.left).toBe('');
  });

  it("dragging 'n' upward by 60px grows the height and keeps the bottom anchor", () => {
    seedSize(DEFAULT_SIZE);
    const panel = renderPanel();
    dragHandle('n', { x: 500, y: 400 }, { x: 500, y: 340 });
    expect(panel.style.height).toBe('540px');
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
    expect(panel.style.top).toBe('');
  });

  it("corner 'nw' resizes both axes and keeps right/bottom anchored", () => {
    seedSize(DEFAULT_SIZE);
    const panel = renderPanel();
    dragHandle('nw', { x: 500, y: 500 }, { x: 440, y: 440 });
    expect(panel.style.width).toBe('440px');
    expect(panel.style.height).toBe('540px');
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
  });

  it('clamps both dimensions at the 320px minimum', () => {
    seedSize(DEFAULT_SIZE);
    const panel = renderPanel();
    dragHandle('w', { x: 300, y: 400 }, { x: 5000, y: 400 });
    expect(panel.style.width).toBe('320px');
    dragHandle('n', { x: 500, y: 300 }, { x: 500, y: 5000 });
    expect(panel.style.height).toBe('320px');
  });

  it('keeps the panel 8px inside the top and left viewport edges', () => {
    seedSize(DEFAULT_SIZE);
    const panel = renderPanel();
    dragHandle('w', { x: 300, y: 400 }, { x: -5000, y: 400 });
    expect(panel.style.width).toBe(`${window.innerWidth - 16 - 8}px`);
    dragHandle('n', { x: 500, y: 400 }, { x: 500, y: -5000 });
    expect(panel.style.height).toBe(`${window.innerHeight - 84 - 8}px`);
  });

  it('persists only width and height under the v2 key', () => {
    seedSize(DEFAULT_SIZE);
    renderPanel();
    dragHandle('w', { x: 300, y: 400 }, { x: 240, y: 400 });
    dragHandle('n', { x: 500, y: 400 }, { x: 500, y: 340 });
    expect(storedSize()).toEqual({ width: 440, height: 540 });
    expect(Object.keys(storedSize()).sort()).toEqual(['height', 'width']);
  });

  it('restores the stored size after remount, still anchored to the launcher', () => {
    seedSize(DEFAULT_SIZE);
    const first = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    dragHandle('w', { x: 300, y: 400 }, { x: 240, y: 400 });
    dragHandle('n', { x: 500, y: 400 }, { x: 500, y: 340 });
    first.unmount();

    const restored = renderPanel();
    expect(restored.style.width).toBe('440px');
    expect(restored.style.height).toBe('540px');
    expect(restored.style.right).toBe(ANCHOR_RIGHT);
    expect(restored.style.bottom).toBe(ANCHOR_BOTTOM);
  });

  it('keyboard on the west handle grows width 16px (64 with Shift) and persists', () => {
    const panel = renderPanel();
    const handle = screen.getByTestId('ai-chat-resize-w');
    handle.focus();
    fireEvent.keyDown(handle, { key: 'ArrowLeft' });
    expect(panel.style.width).toBe('396px');
    fireEvent.keyDown(handle, { key: 'ArrowLeft', shiftKey: true });
    expect(panel.style.width).toBe('460px');
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(panel.style.width).toBe('444px');
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(storedSize()).toEqual({ width: 444, height: 480 });
  });

  it('keyboard on the north handle grows height with ArrowUp and persists', () => {
    const panel = renderPanel();
    const handle = screen.getByTestId('ai-chat-resize-n');
    handle.focus();
    fireEvent.keyDown(handle, { key: 'ArrowUp' });
    expect(panel.style.height).toBe('496px');
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    expect(panel.style.height).toBe('480px');
    expect(storedSize()).toEqual({ width: 380, height: 480 });
  });

  it('stays anchored on window resize and re-clamps the size (c)', () => {
    setViewport(1600, 900);
    seedSize({ width: 900, height: 600 });
    const panel = renderPanel();
    expect(panel.style.width).toBe('900px');
    expect(panel.style.height).toBe('600px');
    setViewport(500, 500);
    fireEvent(window, new Event('resize'));
    expect(panel.style.width).toBe(`${500 - 16 - 8}px`);
    expect(panel.style.height).toBe(`${500 - 84 - 8}px`);
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
  });

  it('renders only the n, w and nw handles (d)', () => {
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    for (const direction of ['n', 'w', 'nw']) {
      const handle = screen.getByTestId(`ai-chat-resize-${direction}`);
      expect(handle).toHaveAttribute('role', 'separator');
      expect(handle).toHaveAttribute('tabindex', '0');
      expect(handle).toHaveAttribute('aria-label', expect.stringContaining('Redimensionar panel'));
    }
    for (const direction of ['s', 'e', 'ne', 'sw', 'se']) {
      expect(screen.queryByTestId(`ai-chat-resize-${direction}`)).toBeNull();
    }
    expect(screen.getByTestId('ai-chat-resize-w')).toHaveAttribute('aria-orientation', 'vertical');
    expect(screen.getByTestId('ai-chat-resize-n')).toHaveAttribute('aria-orientation', 'horizontal');
  });

  it('clamps a stored size to a small viewport (e)', () => {
    setViewport(500, 600);
    seedSize({ width: 900, height: 900 });
    const panel = renderPanel();
    expect(panel.style.width).toBe(`${500 - 16 - 8}px`);
    expect(panel.style.height).toBe(`${600 - 84 - 8}px`);
    expect(panel.style.right).toBe(ANCHOR_RIGHT);
    expect(panel.style.bottom).toBe(ANCHOR_BOTTOM);
  });

  it('enforces the 320px minimum on a stored size', () => {
    seedSize({ width: 100, height: 100 });
    const panel = renderPanel();
    expect(panel.style.width).toBe('320px');
    expect(panel.style.height).toBe('320px');
  });

  it('falls back to the default size on corrupt or non-numeric v2 values', () => {
    window.localStorage.setItem(PANEL_SIZE_STORAGE_KEY, '{not json');
    const corrupt = renderPanel();
    expect(corrupt.style.width).toBe('380px');
    expect(corrupt.style.height).toBe('480px');
    expect(corrupt.style.right).toBe(ANCHOR_RIGHT);
    expect(corrupt.style.bottom).toBe(ANCHOR_BOTTOM);
  });

  it('ignores non-numeric v2 fields and a non-object payload', () => {
    seedSize({ width: 'wide', height: null });
    const nonNumeric = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    expect(screen.getByTestId('ai-chat-panel').style.width).toBe('380px');
    expect(screen.getByTestId('ai-chat-panel').style.height).toBe('480px');
    nonNumeric.unmount();
    seedSize(42);
    const scalar = renderPanel();
    expect(scalar.style.width).toBe('380px');
    expect(scalar.style.height).toBe('480px');
  });

  it('drops a corrupt legacy v1 value without crashing', () => {
    window.localStorage.setItem(LEGACY_RECT_STORAGE_KEY, '{bad');
    const panel = renderPanel();
    expect(panel.style.width).toBe('380px');
    expect(window.localStorage.getItem(LEGACY_RECT_STORAGE_KEY)).toBeNull();
  });
});

describe('ChatPanel — resizable panel (mobile bottom sheet)', () => {
  it('hides the handles and applies neither inline size nor anchor', () => {
    stubMatchMedia(false);
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const panel = screen.getByTestId('ai-chat-panel');
    for (const direction of ['n', 'w', 'nw']) {
      expect(screen.queryByTestId(`ai-chat-resize-${direction}`)).toBeNull();
    }
    expect(panel.style.width).toBe('');
    expect(panel.style.height).toBe('');
    expect(panel.style.maxHeight).toBe('');
    expect(panel.style.right).toBe('');
    expect(panel.style.bottom).toBe('');
    expect(panel.style.left).toBe('');
    expect(panel.style.top).toBe('');
    expect(panel.style.position).toBe('');
  });
});
