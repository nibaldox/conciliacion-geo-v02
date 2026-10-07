import type { ReactNode } from 'react';

export const PROJECT_INPUT_CLASS = 'h-8 w-full min-w-0 rounded-md border border-border bg-surface-raised px-2 text-xs text-text-primary outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50';

export function ProjectField({ id, label, title, children }: { id: string; label: string; title?: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} title={title} className="mb-0.5 block text-xs font-medium text-text-muted">{label}</label>
      {children}
    </div>
  );
}
