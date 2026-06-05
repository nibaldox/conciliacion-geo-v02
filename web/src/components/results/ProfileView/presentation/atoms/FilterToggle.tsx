/**
 * FilterToggle — a labelled switch used in the FilterBar.
 *
 * Renders a native <button role="switch"> for accessibility (no
 * JS needed, screen readers handle it natively). The visual is a
 * track + thumb styled with design tokens.
 *
 * Two visual variants:
 *  - `switch`: classic toggle (default for boolean filters)
 *  - `chip`: pill-shaped label, used for status multi-select
 */

import type { ReactNode } from 'react';

type Variant = 'switch' | 'chip';

export interface FilterToggleProps {
  readonly checked: boolean;
  readonly onChange: (next: boolean) => void;
  readonly label: ReactNode;
  readonly variant?: Variant;
  /** Accent color when checked. Defaults to mine-blue. */
  readonly accent?: 'blue' | 'green' | 'amber' | 'red';
  /** Optional numeric badge (e.g. count of active filters). */
  readonly badge?: ReactNode;
  /** Disabled state — visible but not interactive. */
  readonly disabled?: boolean;
  /** `title` for hover tooltip. */
  readonly title?: string;
}

const ACCENT_VAR: Record<NonNullable<FilterToggleProps['accent']>, string> = {
  blue: 'var(--color-mine-blue)',
  green: 'var(--color-mine-green)',
  amber: 'var(--color-warn, #f59e0b)',
  red: 'var(--color-mine-red)',
};

export function FilterToggle({
  checked,
  onChange,
  label,
  variant = 'switch',
  accent = 'blue',
  badge,
  disabled = false,
  title,
}: FilterToggleProps) {
  const handleClick = () => {
    if (disabled) return;
    onChange(!checked);
  };

  if (variant === 'chip') {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={handleClick}
        title={title}
        className={[
          'inline-flex items-center gap-1.5 h-7 px-3 rounded-full text-xs font-medium',
          'border transition-all duration-150 select-none',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
          disabled
            ? 'opacity-40 cursor-not-allowed'
            : 'cursor-pointer hover:opacity-90',
        ].join(' ')}
        style={{
          backgroundColor: checked ? ACCENT_VAR[accent] : 'var(--color-surface)',
          color: checked ? '#fff' : 'var(--color-text-primary)',
          borderColor: checked ? ACCENT_VAR[accent] : 'var(--color-border)',
        }}
      >
        {checked && <span aria-hidden="true">✓</span>}
        <span>{label}</span>
        {badge != null && <span className="opacity-80">{badge}</span>}
      </button>
    );
  }

  // switch variant
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={handleClick}
      title={title}
      className={[
        'inline-flex items-center gap-2 h-7 px-2.5 rounded-md text-xs font-medium',
        'transition-colors duration-150 select-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        disabled
          ? 'opacity-40 cursor-not-allowed'
          : 'cursor-pointer hover:bg-[var(--color-surface-muted)]',
      ].join(' ')}
      style={{
        color: 'var(--color-text-primary)',
        backgroundColor: 'transparent',
      }}
    >
      <span
        aria-hidden="true"
        className="relative inline-block h-3.5 w-6 rounded-full transition-colors"
        style={{
          backgroundColor: checked ? ACCENT_VAR[accent] : 'var(--color-border)',
        }}
      >
        <span
          className="absolute top-0.5 h-2.5 w-2.5 rounded-full bg-white shadow transition-transform"
          style={{ transform: `translateX(${checked ? '14px' : '2px'})` }}
        />
      </span>
      <span>{label}</span>
      {badge != null && <span className="opacity-60">{badge}</span>}
    </button>
  );
}
