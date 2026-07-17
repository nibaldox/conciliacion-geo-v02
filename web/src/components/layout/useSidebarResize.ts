import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'sidebar_width';
const DEFAULT_WIDTH = 320;
const MIN_WIDTH = 240;
const MAX_WIDTH = 800;

function loadInitialWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_WIDTH;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    const parsed = parseInt(saved, 10);
    if (!isNaN(parsed)) return parsed;
  }
  return DEFAULT_WIDTH;
}

/**
 * Manages the left sidebar width with mouse-drag resizing and localStorage
 * persistence. Listeners are attached once and read the latest width from a
 * ref so we don't re-subscribe on every pixel of drag.
 *
 * Returns `{ sidebarWidth, startResizing, isResizing }`:
 *  - `sidebarWidth`: current width in px (pass to `<aside style={{ width }} />`)
 *  - `startResizing`: mousedown handler for the resize handle
 *  - `isResizing`: reactive boolean for highlighting the handle while dragging
 */
export function useSidebarResize() {
  const [sidebarWidth, setSidebarWidth] = useState<number>(loadInitialWidth);
  const [isResizing, setIsResizing] = useState(false);
  const isResizingRef = useRef(false);
  const sidebarWidthRef = useRef(sidebarWidth);
  sidebarWidthRef.current = sidebarWidth;

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      const newWidth = Math.max(MIN_WIDTH, Math.min(e.clientX, MAX_WIDTH));
      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false;
        setIsResizing(false);
        document.body.style.cursor = 'default';
        document.body.classList.remove('select-none');
        localStorage.setItem(STORAGE_KEY, sidebarWidthRef.current.toString());
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const startResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizingRef.current = true;
    setIsResizing(true);
    document.body.style.cursor = 'col-resize';
    document.body.classList.add('select-none');
  }, []);

  return { sidebarWidth, startResizing, isResizing };
}