import type { ReactNode } from 'react';
import { Tooltip } from '../ui/Tooltip';

export type StatusTone = 'ok' | 'warn' | 'nok' | 'muted';

export function statusToneColor(tone: StatusTone): string {
  return tone === 'muted' ? 'var(--color-text-muted)' : `var(--status-${tone}-text)`;
}

export function StatusDot({ tone }: { tone: StatusTone }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ backgroundColor: statusToneColor(tone) }}
    />
  );
}

export function InfoTip({ label, children, side = 'bottom' }: { label: string; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <Tooltip content={children} side={side}>
      <button
        type="button"
        aria-label={label}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-border text-[10px] leading-none text-text-muted hover:text-text-primary"
      >
        i
      </button>
    </Tooltip>
  );
}

export interface SegmentOption<T extends string> {
  readonly value: T;
  readonly label: string;
}

export function SegmentedControl<T extends string>({ label, options, value, onChange }: {
  label: string;
  options: readonly SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex flex-wrap rounded-md border border-border p-0.5">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${active ? 'bg-surface-muted text-text-primary' : 'text-text-muted hover:text-text-primary'}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function SummaryPanel({ title, info, actions, slot, className, children, ...rest }: {
  title: ReactNode;
  info?: ReactNode;
  actions?: ReactNode;
  slot?: string;
  className?: string;
  children: ReactNode;
  'data-extent'?: string;
}) {
  return (
    <section data-slot={slot} {...rest} className={`min-w-0 space-y-3 rounded-lg border border-border bg-surface-raised p-4 ${className ?? ''}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="ui-section-title">{title}</h3>
          {info}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
