import { useEffect } from 'react';

/**
 * Lightweight global hotkey hook.
 *
 * Examples:
 *   useHotkeys('ArrowLeft', () => prevStep())
 *   useHotkeys('Escape', () => setOpen(false))
 *   useHotkeys(['1', '2', '3', '4'], (e) => setStep(parseInt(e.key, 10)))
 *
 * Why not react-hotkeys-hook? One less dependency, ~30 lines.
 * Trade-off: no chord sequences (Cmd+K, etc.) and no `useHotkeys`-
 * specific options (enabled, scopes). We can add a dep if needed.
 *
 * Ignores events when the user is typing in an input, textarea or
 * contenteditable element.
 */

export type HotkeyHandler = (event: KeyboardEvent) => void;

export function useHotkeys(key: string | string[], handler: HotkeyHandler, deps: unknown[] = []) {
  useEffect(() => {
    const keys = Array.isArray(key) ? new Set(key) : new Set([key]);

    const onKeyDown = (e: KeyboardEvent) => {
      if (keys.has(e.key)) {
        // Don't fire hotkeys while the user is typing somewhere
        const target = e.target as HTMLElement | null;
        if (target) {
          const tag = target.tagName;
          if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) {
            return;
          }
        }
        handler(e);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Array.isArray(key) ? key.join('|') : key, ...deps]);
}
