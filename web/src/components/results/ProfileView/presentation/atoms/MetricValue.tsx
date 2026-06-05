/**
 * MetricValue — a single number with a small label.
 *
 * Used in the SectionHeader (Length, Azimuth, etc.) and the
 * ComplianceSummary (CUMPLE/FUERA/NO_CUMPLE counts). Numbers use
 * tabular-nums so columns of metrics align cleanly.
 */

import type { CSSProperties } from 'react';

export type MetricSize = 'sm' | 'md' | 'lg';

export interface MetricValueProps {
  readonly label: string;
  readonly value: string | number;
  /** Optional unit (e.g. "m", "°", "%"). */
  readonly unit?: string;
  readonly size?: MetricSize;
  /** Subtle label, used in the SectionHeader. */
  readonly muted?: boolean;
  /** Accent color (CSS variable name without `var(...)`). */
  readonly accent?: string;
  /** Optional tooltip. */
  readonly title?: string;
}

const VALUE_SIZE: Record<MetricSize, string> = {
  sm: 'text-sm',
  md: 'text-base',
  lg: 'text-2xl',
};

const LABEL_SIZE: Record<MetricSize, string> = {
  sm: 'text-[10px]',
  md: 'text-[11px]',
  lg: 'text-xs',
};

export function MetricValue({
  label,
  value,
  unit,
  size = 'md',
  accent,
  title,
}: MetricValueProps) {
  const style: CSSProperties = {
    color: accent ? `var(${accent})` : 'var(--color-text-primary)',
  };
  return (
    <span
      data-slot="metric-value"
      data-size={size}
      title={title}
      className="inline-flex items-baseline gap-1.5 whitespace-nowrap"
    >
      <span
        className={[
          'uppercase tracking-wider font-medium',
          LABEL_SIZE[size],
        ].join(' ')}
        style={{
          color: 'var(--color-text-muted)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        {label}
      </span>
      <span
        className={[VALUE_SIZE[size], 'font-semibold tabular-nums'].join(' ')}
        style={style}
      >
        {value}
      </span>
      {unit && (
        <span
          className={['tabular-nums', LABEL_SIZE[size]].join(' ')}
          style={{
            color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {unit}
        </span>
      )}
    </span>
  );
}
