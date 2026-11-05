import type { ReactNode } from 'react';
import { Button } from './Button';

interface EmptyStateAction {
  readonly label: string;
  readonly onClick: () => void;
}

export interface EmptyStateProps {
  readonly icon: ReactNode;
  readonly title: string;
  readonly description: string;
  readonly primaryAction?: EmptyStateAction;
  readonly secondaryAction?: EmptyStateAction;
  readonly 'data-slot'?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  'data-slot': dataSlot = 'empty-state',
}: EmptyStateProps) {
  return (
    <div
      data-slot={dataSlot}
      className="ui-card mx-auto flex w-full max-w-md flex-col items-center gap-4 px-8 py-10 text-center"
    >
      <div
        aria-hidden="true"
        className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-accent-bg text-accent-bright"
      >
        {icon}
      </div>
      <div className="flex flex-col gap-2">
        <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
        <p className="text-sm text-text-muted">{description}</p>
      </div>
      {(primaryAction || secondaryAction) && (
        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          {primaryAction && (
            <Button variant="primary" onClick={primaryAction.onClick}>
              {primaryAction.label}
            </Button>
          )}
          {secondaryAction && (
            <Button variant="secondary" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
