import { useRef, type KeyboardEvent, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';

interface Props { width: number; onChange: (width: number) => void }

export function CopilotResizeHandle({ width, onChange }: Props) {
  const { t } = useTranslation();
  const drag = useRef<{ x: number; width: number } | null>(null);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = event.key === 'ArrowLeft' ? width + 16 : event.key === 'ArrowRight' ? width - 16 : event.key === 'Home' ? 320 : event.key === 'End' ? 520 : null;
    if (next !== null) { event.preventDefault(); onChange(next); }
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    drag.current = { x: event.clientX, width };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  return <div className="agent-shell__resize" role="separator" tabIndex={0} aria-label={t('agentWorkspace.resize')} aria-orientation="vertical" aria-valuemin={320} aria-valuemax={520} aria-valuenow={width} onKeyDown={onKeyDown} onPointerDown={onPointerDown} onPointerMove={(event) => { if (drag.current) onChange(drag.current.width + drag.current.x - event.clientX); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} />;
}
