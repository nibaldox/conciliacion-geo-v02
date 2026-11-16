import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

export interface PanelSize {
  width: number;
  height: number;
}

export type ResizeDirection = 'n' | 'w' | 'nw';

export const PANEL_SIZE_STORAGE_KEY = 'conciliacion.aiChat.panelSize.v2';
const LEGACY_PANEL_RECT_STORAGE_KEY = 'conciliacion.aiChat.panelRect.v1';

const PANEL_ANCHOR_RIGHT_PX = 16;
const PANEL_ANCHOR_BOTTOM_PX = 16 + 56 + 12;

export const PANEL_ANCHOR_STYLE = {
  right: `${PANEL_ANCHOR_RIGHT_PX}px`,
  bottom: `calc(${PANEL_ANCHOR_BOTTOM_PX}px + env(safe-area-inset-bottom))`,
} as const;

const MIN_PANEL_SIZE = 320;
const VIEWPORT_MARGIN = 8;
const DEFAULT_PANEL_WIDTH = 380;
const DEFAULT_PANEL_HEIGHT = 480;
const KEYBOARD_STEP = 16;
const KEYBOARD_LARGE_STEP = 64;
const DESKTOP_MEDIA_QUERY = '(min-width: 640px)';

export function isDesktopViewport(): boolean {
  if (typeof window === 'undefined') return true;
  if (typeof window.matchMedia !== 'function') return true;
  return window.matchMedia(DESKTOP_MEDIA_QUERY).matches;
}

function clampWithin(value: number, min: number, max: number): number {
  return Math.min(Math.max(Math.round(value), min), Math.max(min, max));
}

function maxWidth(): number {
  return window.innerWidth - PANEL_ANCHOR_RIGHT_PX - VIEWPORT_MARGIN;
}

function maxHeight(): number {
  return window.innerHeight - PANEL_ANCHOR_BOTTOM_PX - VIEWPORT_MARGIN;
}

function clampSize(size: PanelSize): PanelSize {
  if (typeof window === 'undefined') return { ...size };
  return {
    width: clampWithin(size.width, MIN_PANEL_SIZE, maxWidth()),
    height: clampWithin(size.height, MIN_PANEL_SIZE, maxHeight()),
  };
}

function defaultSize(): PanelSize {
  return clampSize({ width: DEFAULT_PANEL_WIDTH, height: DEFAULT_PANEL_HEIGHT });
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function dropLegacyRect(): void {
  try {
    window.localStorage.removeItem(LEGACY_PANEL_RECT_STORAGE_KEY);
  } catch {
    return;
  }
}

function readStoredSize(): PanelSize {
  dropLegacyRect();
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(PANEL_SIZE_STORAGE_KEY);
  } catch {
    raw = null;
  }
  if (!raw) return defaultSize();
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return defaultSize();
  }
  if (typeof parsed !== 'object' || parsed === null) return defaultSize();
  const candidate = parsed as Record<string, unknown>;
  const width = asFiniteNumber(candidate.width);
  const height = asFiniteNumber(candidate.height);
  if (width === null || height === null) return defaultSize();
  return clampSize({ width, height });
}

function persistSize(size: PanelSize): void {
  try {
    window.localStorage.setItem(
      PANEL_SIZE_STORAGE_KEY,
      JSON.stringify({ width: size.width, height: size.height }),
    );
  } catch {
    return;
  }
}

function applyDrag(
  size: PanelSize,
  direction: ResizeDirection,
  dx: number,
  dy: number,
): PanelSize {
  const width = direction.includes('w')
    ? clampWithin(size.width - dx, MIN_PANEL_SIZE, maxWidth())
    : size.width;
  const height = direction.includes('n')
    ? clampWithin(size.height - dy, MIN_PANEL_SIZE, maxHeight())
    : size.height;
  return { width, height };
}

interface DragState {
  direction: ResizeDirection;
  pointerX: number;
  pointerY: number;
  startSize: PanelSize;
}

export interface ResizablePanel {
  size: PanelSize;
  isDesktop: boolean;
  startResize: (direction: ResizeDirection, event: PointerEvent<HTMLElement>) => void;
  onResizeMove: (event: PointerEvent<HTMLElement>) => void;
  endResize: (event: PointerEvent<HTMLElement>) => void;
  adjustFromKeyboard: (direction: ResizeDirection, event: KeyboardEvent<HTMLElement>) => void;
}

/**
 * Desktop chat panel size. The panel is anchored to the launcher with
 * right/bottom CSS (see PANEL_ANCHOR_STYLE), so only width and height are
 * state and only they persist under PANEL_SIZE_STORAGE_KEY. The handles
 * move the north and west edges, keeping the bottom-right corner fixed.
 */
export function useResizablePanel(): ResizablePanel {
  const [size, setSize] = useState<PanelSize>(readStoredSize);
  const [isDesktop, setIsDesktop] = useState(isDesktopViewport);
  const dragRef = useRef<DragState | null>(null);
  const sizeRef = useRef<PanelSize>(size);

  const updateSize = useCallback((next: PanelSize) => {
    sizeRef.current = next;
    setSize(next);
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
    const handleWindowResize = () => updateSize(clampSize(sizeRef.current));
    window.addEventListener('resize', handleWindowResize);
    return () => window.removeEventListener('resize', handleWindowResize);
  }, [updateSize]);

  const startResize = useCallback(
    (direction: ResizeDirection, event: PointerEvent<HTMLElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      dragRef.current = {
        direction,
        pointerX: event.clientX,
        pointerY: event.clientY,
        startSize: sizeRef.current,
      };
    },
    [],
  );

  const onResizeMove = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = event.clientX - drag.pointerX;
      const dy = event.clientY - drag.pointerY;
      updateSize(applyDrag(drag.startSize, drag.direction, dx, dy));
    },
    [updateSize],
  );

  const endResize = useCallback((event: PointerEvent<HTMLElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    dragRef.current = null;
    persistSize(sizeRef.current);
  }, []);

  const adjustFromKeyboard = useCallback(
    (direction: ResizeDirection, event: KeyboardEvent<HTMLElement>) => {
      const step = event.shiftKey ? KEYBOARD_LARGE_STEP : KEYBOARD_STEP;
      let dx = 0;
      let dy = 0;
      if (direction.includes('w')) {
        if (event.key === 'ArrowLeft') dx = -step;
        else if (event.key === 'ArrowRight') dx = step;
      }
      if (direction.includes('n')) {
        if (event.key === 'ArrowUp') dy = -step;
        else if (event.key === 'ArrowDown') dy = step;
      }
      if (dx === 0 && dy === 0) return;
      event.preventDefault();
      const next = applyDrag(sizeRef.current, direction, dx, dy);
      updateSize(next);
      persistSize(next);
    },
    [updateSize],
  );

  return { size, isDesktop, startResize, onResizeMove, endResize, adjustFromKeyboard };
}
