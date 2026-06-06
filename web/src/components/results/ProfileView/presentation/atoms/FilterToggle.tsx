/**
 * FilterToggle — a labelled switch used in the FilterBar.
 *
 * Renders a native <button role="switch"> for accessibility (no
 * JS needed, screen readers handle it natively). Two visual
 * variants:
 *  - `switch`: classic toggle (default for boolean filters)
 *  - `chip`: pill-shaped label, used for status multi-select
 *
 * The ON state must be visually unmistakable. The label, the
 * track, the thumb AND a leading marker all change so the user
 * can't miss it. OFF state is muted, ON state is bright accent
 * + bold + filled marker.
 *
 * The label uses the Mission Control mono uppercase tracking
 * so it sits visually with the rest of the filter bar.
 */

import type { CSSProperties, ReactNode } from 'react';

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
          'inline-flex items-center gap-1.5 h-7 px-3 rounded-full text-[11px] font-semibold',
          'border transition-all duration-150 select-none',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
          disabled
            ? 'opacity-40 cursor-not-allowed'
            : 'cursor-pointer hover:opacity-90',
        ].join(' ')}
        style={{
          backgroundColor: checked ? ACCENT_VAR[accent] : 'var(--color-surface)',
          color: checked ? '#0a0e14' : 'var(--color-text-muted)',
          borderColor: checked ? ACCENT_VAR[accent] : 'var(--color-border)',
          fontFamily: 'var(--font-mono)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {checked ? <span aria-hidden="true">●</span> : <span aria-hidden="true">○</span>}
        <span>{label}</span>
        {badge != null && <span className="opacity-80">{badge}</span>}
      </button>
    );
  }

  // switch variant — three visual cues for ON:
  //   1. The track fills with the accent color
  //   2. The thumb shifts to the right + gets the accent ring
  //   3. The label changes color + weight + gets a leading marker
  const labelStyle: CSSProperties = {
    color: checked ? ACCENT_VAR[accent] : 'var(--color-text-muted)',
    fontFamily: 'var(--font-mono)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={handleClick}
      title={title}
      data-slot="filter-toggle"
      data-checked={checked}
      data-variant={variant}
      className={[
        // All toggles share the same outer dimensions so they sit on
        // the same baseline in the FilterBar. `box-border` (the
        // Tailwind default) means the 1px border is INSIDE the
        // OFF (border: surface) and ON (border: accent).
        'group inline-flex items-center justify-center gap-2 h-7 px-2.5 rounded-md text-[11px] font-semibold',
        'transition-colors duration-150 select-none whitespace-nowrap',
        'border',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        disabled
          ? 'opacity-40 cursor-not-allowed'
          : 'cursor-pointer',
      ].join(' ')}
      style={{
        // Both states have a visible box. OFF is dark with a
        // subtle border, ON is the accent color. The visual weight
        // is now consistent, so toggles don't appear "misaligned"
        // when comparing ON and OFF in the same row.
        backgroundColor: checked
          ? `color-mix(in srgb, ${ACCENT_VAR[accent]} 14%, transparent)`
          : 'var(--color-surface-raised)',
        borderColor: checked
          ? ACCENT_VAR[accent]
          : 'var(--color-border-strong)',
      }}
    >
      {/* Leading marker — the strongest ON/OFF cue. */}
      <span
        aria-hidden="true"
        className="inline-block w-2 h-2 rounded-full shrink-0 transition-colors"
        style={{
          backgroundColor: checked ? ACCENT_VAR[accent] : 'var(--color-border-strong)',
          boxShadow: checked
            ? `0 0 6px ${ACCENT_VAR[accent]}`
            : 'none',
        }}
      />

      {/* The track — secondary cue.
       * overflow-hidden clips the thumb to the pill shape; without
       * it the thumb bleeds onto the first letter of the label.
       * min-w-6 protects the track from being collapsed to 0 by a
       * flex shrink edge case. */}
      <span
        aria-hidden="true"
        className="relative inline-block h-3.5 w-6 min-w-6 rounded-full transition-colors shrink-0 overflow-hidden"
        style={{
          backgroundColor: checked ? ACCENT_VAR[accent] : 'var(--color-border-strong)',
        }}
      >
        <span
          className="absolute top-0.5 h-2.5 w-2.5 rounded-full transition-transform"
          style={{
            transform: `translateX(${checked ? '13px' : '2px'})`,
            backgroundColor: '#0a0e14',
            boxShadow: checked
              ? `0 0 0 1.5px ${ACCENT_VAR[accent]}`
              : '0 0 0 1.5px var(--color-text-muted)',
          }}
        />
      </span>

      {/* The label — primary cue. Color + weight change. */}
      <span style={labelStyle} className="leading-none pt-[1px]">{label}</span>

      {badge != null && (
        <span
          className="opacity-70 tabular-nums"
          style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}
        >
          {badge}
        </span>
      )}
    </button>
  );
}
