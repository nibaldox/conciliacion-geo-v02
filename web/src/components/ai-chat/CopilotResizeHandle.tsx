import { useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';

interface Props { width: number; onChange: (width: number) => void; onCommit?: (width: number) => void; onDragChange?: (dragging: boolean) => void }

export function CopilotResizeHandle({ width, onChange, onCommit, onDragChange }: Props) {
  const { t } = useTranslation();
  const handle = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; width: number; value: number } | null>(null);
  const frame = useRef<number | null>(null);
  useLayoutEffect(() => () => { if (frame.current !== null) cancelAnimationFrame(frame.current); }, []);
  const [measured, setMeasured] = useState<{ width: number; max: number } | null>(null);
  useLayoutEffect(() => {
    const chat = handle.current?.parentElement;
    const grid = chat?.parentElement;
    if (!chat || !grid) return;
    const measure = () => {
      const actual = chat.getBoundingClientRect().width;
      const total = grid.getBoundingClientRect().width;
      if (actual > 0 && total > 0) setMeasured({ width: actual, max: Math.min(520, Math.max(0, total - 480)) });
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(chat);
    observer.observe(grid);
    return () => observer.disconnect();
  }, []);
  const effective = measured?.width ?? width;
  const max = measured?.max ?? 520;
  const clamp = (value: number) => Math.min(max, Math.max(Math.min(320, max), value));
  const finish = () => {
    if (!drag.current) return;
    if (frame.current !== null) { cancelAnimationFrame(frame.current); frame.current = null; onChange(drag.current.value); }
    onCommit?.(drag.current.value);
    drag.current = null;
    onDragChange?.(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = event.key === 'ArrowLeft' ? effective + 16 : event.key === 'ArrowRight' ? effective - 16 : event.key === 'Home' ? 320 : event.key === 'End' ? max : null;
    if (next !== null) { event.preventDefault(); const value = clamp(next); onChange(value); onCommit?.(value); }
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const actual = event.currentTarget.parentElement?.getBoundingClientRect().width || effective;
    drag.current = { x: event.clientX, width: actual, value: actual };
    onDragChange?.(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  return <div ref={handle} className="agent-shell__resize" role="separator" tabIndex={0} aria-label={t('agentWorkspace.resize')} aria-orientation="vertical" aria-valuemin={Math.min(320, max)} aria-valuemax={max} aria-valuenow={effective} onKeyDown={onKeyDown} onPointerDown={onPointerDown} onPointerMove={(event) => {
    if (!drag.current) return;
    if (event.buttons === 0) { finish(); return; }
    const value = clamp(drag.current.width + drag.current.x - event.clientX);
    drag.current.value = value;
    if (frame.current === null) frame.current = requestAnimationFrame(() => {
      frame.current = null;
      if (drag.current) onChange(drag.current.value);
    });
  }} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish} />;
}
