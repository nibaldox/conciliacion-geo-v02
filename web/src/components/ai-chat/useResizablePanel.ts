import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

export interface PanelRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'nw' | 'ne' | 'sw' | 'se';

export const PANEL_RECT_STORAGE_KEY = 'conciliacion.aiChat.panelRect.v1';

const MIN_PANEL_SIZE = 320;
const VIEWPORT_MARGIN = 8;
const DEFAULT_EDGE_OFFSET = 16;
const DEFAULT_PANEL_WIDTH = 380;
const DEFAULT_PANEL_HEIGHT = 480;
const KEYBOARD_STEP = 16;
const KEYBOARD_LARGE_STEP = 64;
const DESKTOP_MEDIA_QUERY = '(min-width: 640px)';

/**
 * True when the viewport is desktop-sized (>= sm / 640px). Falls back to
 * true when matchMedia is unavailable (e.g. jsdom), so the resizable
 * desktop behaviour stays the default in every environment that cannot
 * prove it is mobile.
 */
export function isDesktopViewport(): boolean {
  if (typeof window === 'undefined') return true;
  if (typeof window.matchMedia !== 'function') return true;
  return window.matchMedia(DESKTOP_MEDIA_QUERY).matches;
}

function clampWithin(value: number, min: number, max: number): number {
  return Math.min(Math.max(Math.round(value), min), Math.max(min, max));
}

/**
 * Clamps a full rect into the current viewport (8px margin per side)
 * while keeping a 320x320 minimum. Used on mount, on persisted reads
 * and on window resize; drag steps clamp edge-aware instead (see
 * applyDrag) so the dragged edge tracks the pointer.
 */
function clampRect(rect: PanelRect): PanelRect {
  if (typeof window === 'undefined') return { ...rect };
  const width = clampWithin(
    rect.width,
    MIN_PANEL_SIZE,
    window.innerWidth - VIEWPORT_MARGIN * 2,
  );
  const height = clampWithin(
    rect.height,
    MIN_PANEL_SIZE,
    window.innerHeight - VIEWPORT_MARGIN * 2,
  );
  const left = clampWithin(
    rect.left,
    VIEWPORT_MARGIN,
    window.innerWidth - VIEWPORT_MARGIN - width,
  );
  const top = clampWithin(
    rect.top,
    VIEWPORT_MARGIN,
    window.innerHeight - VIEWPORT_MARGIN - height,
  );
  return { left, top, width, height };
}

/** Default rect anchored to the bottom-right corner (16px per edge). */
function defaultRect(): PanelRect {
  const base: PanelRect = {
    left: 0,
    top: 0,
    width: DEFAULT_PANEL_WIDTH,
    height: DEFAULT_PANEL_HEIGHT,
  };
  if (typeof window === 'undefined') return base;
  base.left = window.innerWidth - DEFAULT_PANEL_WIDTH - DEFAULT_EDGE_OFFSET;
  base.top = window.innerHeight - DEFAULT_PANEL_HEIGHT - DEFAULT_EDGE_OFFSET;
  return clampRect(base);
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Reads the stored rect tolerantly: invalid JSON, non-numeric fields or
 * rects written by another viewport fall back to the default bottom-right
 * rect. A legacy entry holding only {width, height} keeps its saved size
 * and is re-anchored bottom-right. The result is always clamped.
 */
function readStoredRect(): PanelRect {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(PANEL_RECT_STORAGE_KEY);
  } catch {
    raw = null;
  }
  if (!raw) return defaultRect();
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return defaultRect();
  }
  if (typeof parsed !== 'object' || parsed === null) {
    return defaultRect();
  }
  const candidate = parsed as Record<string, unknown>;
  const width = asFiniteNumber(candidate.width);
  const height = asFiniteNumber(candidate.height);
  if (width === null || height === null) return defaultRect();
  const left = asFiniteNumber(candidate.left);
  const top = asFiniteNumber(candidate.top);
  return clampRect({
    left: left ?? window.innerWidth - width - DEFAULT_EDGE_OFFSET,
    top: top ?? window.innerHeight - height - DEFAULT_EDGE_OFFSET,
    width,
    height,
  });
}

function persistRect(rect: PanelRect): void {
  try {
    window.localStorage.setItem(PANEL_RECT_STORAGE_KEY, JSON.stringify(rect));
  } catch {
    return;
  }
}

/**
 * Resolves one horizontal drag step. 'e' keeps the west edge fixed and
 * grows eastward; 'w' keeps the east edge fixed so the panel grows
 * westward without sliding. The moving edge follows the pointer until
 * the 320px minimum or the 8px viewport margin stops it.
 */
function resolveHorizontal(
  rect: PanelRect,
  direction: ResizeDirection,
  dx: number,
): { left: number; width: number } {
  if (!direction.includes('e') && !direction.includes('w')) {
    return { left: rect.left, width: rect.width };
  }
  if (direction.includes('e')) {
    const maxWidth = window.innerWidth - VIEWPORT_MARGIN - rect.left;
    return {
      left: rect.left,
      width: clampWithin(rect.width + dx, MIN_PANEL_SIZE, maxWidth),
    };
  }
  const rightEdge = rect.left + rect.width;
  const left = clampWithin(
    rect.left + dx,
    VIEWPORT_MARGIN,
    rightEdge - MIN_PANEL_SIZE,
  );
  return { left, width: rightEdge - left };
}

/**
 * Vertical counterpart of resolveHorizontal: 's' grows the south edge
 * with the fixed top edge, 'n' grows the north edge with the fixed
 * bottom edge.
 */
function resolveVertical(
  rect: PanelRect,
  direction: ResizeDirection,
  dy: number,
): { top: number; height: number } {
  if (!direction.includes('n') && !direction.includes('s')) {
    return { top: rect.top, height: rect.height };
  }
  if (direction.includes('s')) {
    const maxHeight = window.innerHeight - VIEWPORT_MARGIN - rect.top;
    return {
      top: rect.top,
      height: clampWithin(rect.height + dy, MIN_PANEL_SIZE, maxHeight),
    };
  }
  const bottomEdge = rect.top + rect.height;
  const top = clampWithin(
    rect.top + dy,
    VIEWPORT_MARGIN,
    bottomEdge - MIN_PANEL_SIZE,
  );
  return { top, height: bottomEdge - top };
}

function applyDrag(
  rect: PanelRect,
  direction: ResizeDirection,
  dx: number,
  dy: number,
): PanelRect {
  const horizontal = resolveHorizontal(rect, direction, dx);
  const vertical = resolveVertical(rect, direction, dy);
  return {
    left: horizontal.left,
    top: vertical.top,
    width: horizontal.width,
    height: vertical.height,
  };
}

interface DragState {
  direction: ResizeDirection;
  pointerX: number;
  pointerY: number;
  startRect: PanelRect;
}

export interface ResizablePanel {
  rect: PanelRect;
  isDesktop: boolean;
  startResize: (direction: ResizeDirection, event: PointerEvent<HTMLElement>) => void;
  onResizeMove: (event: PointerEvent<HTMLElement>) => void;
  endResize: (event: PointerEvent<HTMLElement>) => void;
  adjustFromKeyboard: (direction: ResizeDirection, event: KeyboardEvent<HTMLElement>) => void;
}

/**
 * User-resizable chat panel modelled as an explicit fixed-position rect
 * {left, top, width, height}, so EVERY handle follows the pointer:
 * 'e'/'ne'/'se' move the east edge (width += dx), 'w'/'nw'/'sw' the
 * west edge (width -= dx, left += dx), 's'/'se'/'sw' the south edge
 * (height += dy) and 'n'/'ne'/'nw' the north edge (height -= dy,
 * top += dy); corners combine both axes. Each drag step is clamped
 * edge-aware: 320x320 minimum and 8px viewport margins on all sides,
 * with the opposite edge held in place while the dragged edge tracks
 * the pointer. The full rect persists to localStorage under
 * PANEL_RECT_STORAGE_KEY on pointerUp/keyboard and is re-clamped on
 * window resize; corrupt or out-of-viewport stored values fall back to
 * the bottom-right anchored default rect. Handles use Pointer Events
 * with setPointerCapture (optional-chained: jsdom does not implement
 * it) and carry touch-action: none via Tailwind's touch-none class in
 * the component. Keyboard: arrows step 16px (Shift: 64px) along the
 * handle direction with the same clamps.
 */
export function useResizablePanel(): ResizablePanel {
  const [rect, setRect] = useState<PanelRect>(readStoredRect);
  const [isDesktop, setIsDesktop] = useState(isDesktopViewport);
  const dragRef = useRef<DragState | null>(null);
  const rectRef = useRef<PanelRect>(rect);

  const updateRect = useCallback((next: PanelRect) => {
    rectRef.current = next;
    setRect(next);
  }, []);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia(DESKTOP_MEDIA_QUERY);
    const handleChange = (event: MediaQueryListEvent) => setIsDesktop(event.matches);
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', handleChange);
      return () => query.removeEventListener('change', handleChange);
    }
    query.addListener?.(handleChange);
    return () => query.removeListener?.(handleChange);
  }, []);

  useEffect(() => {
    const handleWindowResize = () => updateRect(clampRect(rectRef.current));
    window.addEventListener('resize', handleWindowResize);
    return () => window.removeEventListener('resize', handleWindowResize);
  }, [updateRect]);

  const startResize = useCallback(
    (direction: ResizeDirection, event: PointerEvent<HTMLElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      dragRef.current = {
        direction,
        pointerX: event.clientX,
        pointerY: event.clientY,
        startRect: rectRef.current,
      };
    },
    [],
  );

  const onResizeMove = useCallback((event: PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = event.clientX - drag.pointerX;
    const dy = event.clientY - drag.pointerY;
    updateRect(applyDrag(drag.startRect, drag.direction, dx, dy));
  }, [updateRect]);

  const endResize = useCallback((event: PointerEvent<HTMLElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    dragRef.current = null;
    persistRect(rectRef.current);
  }, []);

  const adjustFromKeyboard = useCallback(
    (direction: ResizeDirection, event: KeyboardEvent<HTMLElement>) => {
      const step = event.shiftKey ? KEYBOARD_LARGE_STEP : KEYBOARD_STEP;
      let dx = 0;
      let dy = 0;
      if (direction.includes('e') || direction.includes('w')) {
        if (event.key === 'ArrowRight') dx = step;
        else if (event.key === 'ArrowLeft') dx = -step;
      }
      if (direction.includes('s') || direction.includes('n')) {
        if (event.key === 'ArrowDown') dy = step;
        else if (event.key === 'ArrowUp') dy = -step;
      }
      if (dx === 0 && dy === 0) return;
      event.preventDefault();
      const next = applyDrag(rectRef.current, direction, dx, dy);
      updateRect(next);
      persistRect(next);
    },
    [updateRect],
  );

  return { rect, isDesktop, startResize, onResizeMove, endResize, adjustFromKeyboard };
}
