import type { ReactNode } from 'react';
import { IconCheck, IconChevronDown, IconLock } from './Icons';

export type StepperItemStatus = 'done' | 'current' | 'pending' | 'locked';

export interface StepperItemProps {
  readonly id: string;
  readonly index: number;
  readonly title: string;
  readonly summary?: string;
  readonly status: StepperItemStatus;
  readonly expanded: boolean;
  readonly onToggle: () => void;
  readonly isLast?: boolean;
  readonly children?: ReactNode;
}

const CIRCLE_CLASSES: Record<StepperItemStatus, string> = {
  done: 'bg-mine-green text-white',
  current: 'bg-accent text-accent-fg',
  pending: 'bg-surface-muted text-text-muted',
  locked: 'bg-surface-muted text-text-dim',
};

function StepMarker({ status, index }: { readonly status: StepperItemStatus; readonly index: number }) {
  if (status === 'done') return <IconCheck width={14} height={14} strokeWidth={3} aria-hidden="true" />;
  if (status === 'locked') return <IconLock width={12} height={12} aria-hidden="true" />;
  return <span>{index}</span>;
}

export function StepperItem({
  id,
  index,
  title,
  summary,
  status,
  expanded,
  onToggle,
  isLast = false,
  children,
}: StepperItemProps) {
  const locked = status === 'locked';
  const panelId = `${id}-panel`;

  return (
    <div className="relative" data-slot="stepper-item" data-state={status}>
      {!isLast && !expanded && (
        <span
          aria-hidden="true"
          data-slot="stepper-connector"
          className={`absolute bottom-0 left-[25px] top-[38px] w-px ${status === 'done' ? 'bg-mine-green' : 'bg-border'}`}
        />
      )}
      <button
        type="button"
        id={id}
        aria-expanded={expanded}
        aria-controls={panelId}
        data-state={status}
        disabled={locked}
        onClick={onToggle}
        className="relative flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
      >
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${CIRCLE_CLASSES[status]}`}
        >
          <StepMarker status={status} index={index} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-sm font-semibold text-text-primary">{title}</span>
          {summary && <span className="truncate text-xs text-text-muted">{summary}</span>}
        </span>
        <IconChevronDown
          width={16}
          height={16}
          aria-hidden="true"
          className={`shrink-0 text-text-muted transition-transform duration-150 ${expanded ? 'rotate-180' : ''}`}
        />
      </button>
      {expanded && (
        <div id={panelId} role="region" aria-labelledby={id} className="relative pb-3 pl-3 pr-3 pt-1">
          {children}
        </div>
      )}
    </div>
  );
}
