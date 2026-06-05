/**
 * StatusPill — semantic compliance badge.
 *
 * Visual: small rounded chip with the status icon + short label.
 * Color comes from the design system's CSS variables, not hex values.
 *
 * Sizes:
 *  - `sm`: 20px tall, used inline in tables
 *  - `md`: 28px tall, used in cards and headers
 *  - `lg`: 36px tall, used as the focal point of the summary card
 */

import type { CSSProperties, ReactNode } from 'react';
import {
  STATUS_BG_VAR,
  STATUS_FG_VAR,
  STATUS_BORDER_VAR,
  STATUS_ICON,
} from '../../domain/status';
import type { BenchStatus } from '../../domain/types';

export type StatusPillSize = 'sm' | 'md' | 'lg';

export interface StatusPillProps {
  readonly status: BenchStatus;
  readonly size?: StatusPillSize;
  /** Show the status icon (default true for md/lg, false for sm). */
  readonly showIcon?: boolean;
  /** Override the visible text (e.g. localised label). */
  readonly label?: string;
  /** Optional title attribute for the full status name on hover. */
  readonly title?: string;
  /** Extra class for the wrapper (e.g. for spacing in tables). */
  readonly className?: string;
  /** Optional children — when present, replaces the default label. */
  readonly children?: ReactNode;
}

const SIZE_CLASSES: Record<StatusPillSize, string> = {
  sm: 'h-5 px-1.5 text-[10px] gap-0.5',
  md: 'h-7 px-2.5 text-xs gap-1',
  lg: 'h-9 px-3.5 text-sm gap-1.5',
};

const ICON_SIZE: Record<StatusPillSize, string> = {
  sm: 'text-[10px]',
  md: 'text-xs',
  lg: 'text-sm',
};

const DEFAULT_LABEL: Record<BenchStatus, string> = {
  CUMPLE: 'Cumple',
  FUERA: 'Fuera',
  NO_CUMPLE: 'No cumple',
  UNKNOWN: 'Sin datos',
};

export function StatusPill({
  status,
  size = 'md',
  showIcon,
  label,
  title,
  className = '',
  children,
}: StatusPillProps) {
  const showIconDefault = showIcon ?? size !== 'sm';
  const style: CSSProperties = {
    backgroundColor: STATUS_BG_VAR[status],
    color: STATUS_FG_VAR[status],
    border: `1px solid ${STATUS_BORDER_VAR[status]}`,
  };
  return (
    <span
      data-slot="status-pill"
      data-status={status}
      data-size={size}
      title={title ?? DEFAULT_LABEL[status]}
      className={[
        'inline-flex items-center justify-center rounded-full font-medium',
        'whitespace-nowrap tabular-nums select-none',
        SIZE_CLASSES[size],
        className,
      ].filter(Boolean).join(' ')}
      style={style}
    >
      {showIconDefault && (
        <span aria-hidden="true" className={ICON_SIZE[size]}>
          {STATUS_ICON[status]}
        </span>
      )}
      <span>{children ?? label ?? DEFAULT_LABEL[status]}</span>
    </span>
  );
}
