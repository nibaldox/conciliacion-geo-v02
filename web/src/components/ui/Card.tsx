/**
 * Card — the surface primitive for content blocks.
 *
 * Three variants aligned with the Mission Control aesthetic:
 *  - solid: default 1px border (the most common card)
 *  - dashed: 1.5px dashed border for "field" / drop zones,
 *    matches the [MISIÓN 01] / [PROTOCOL ALPHA] cards in the
 *    reference design
 *  - elevated: solid border + subtle glow shadow, used for
 *    important surfaces (the compliance summary, the terminal
 *    log area)
 *
 * Two sizes: md (default) and sm (tight). Padding scales.
 *
 * Header slot is optional — render a `CardHeader` child or pass
 * `title` + `subtitle` for the canonical look. We don't try to
 * be too clever about it; this is a primitive, callers compose.
 */

import { ReactNode } from 'react';

type Variant = 'solid' | 'dashed' | 'elevated';
type Size = 'sm' | 'md' | 'lg';

export interface CardProps {
  readonly variant?: Variant;
  readonly size?: Size;
  readonly title?: ReactNode;
  /** Optional small label rendered above the title in uppercase
   *  mono, e.g. "PROTOCOL ALPHA" or "MALLA DE DISEÑO". */
  readonly eyebrow?: ReactNode;
  readonly subtitle?: ReactNode;
  /** Optional icon in the header (decorative, before title). */
  readonly icon?: ReactNode;
  /** Right-aligned slot in the header (e.g. status badge). */
  readonly headerAside?: ReactNode;
  /** Padding override. Defaults to the size preset. */
  readonly padding?: string;
  readonly className?: string;
  readonly style?: React.CSSProperties;
  readonly children?: ReactNode;
  /** Click handler. Renders as a button if provided, div otherwise. */
  readonly onClick?: () => void;
  /** Any extra data-* attribute (data-slot, data-testid, etc.).
   *  Spread onto the root element for E2E test targeting. */
  readonly [key: `data-${string}`]: string | undefined;
}

const VARIANT_STYLES: Record<Variant, React.CSSProperties> = {
  solid: {
    backgroundColor: 'var(--color-surface-raised)',
    border: '1px solid var(--color-border)',
  },
  dashed: {
    backgroundColor: 'var(--color-surface)',
    border: '1.5px dashed var(--color-border-dashed)',
  },
  elevated: {
    backgroundColor: 'var(--color-surface-raised)',
    border: '1px solid var(--color-border)',
    boxShadow: 'var(--shadow-glow-accent)',
  },
};

const SIZE_PADDING: Record<Size, string> = {
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
};

const HEADER_PAD_BOTTOM: Record<Size, string> = {
  sm: 'pb-2 mb-2',
  md: 'pb-3 mb-3',
  lg: 'pb-4 mb-4',
};

export function Card({
  variant = 'solid',
  size = 'md',
  title,
  eyebrow,
  subtitle,
  icon,
  headerAside,
  padding,
  className = '',
  style,
  children,
  onClick,
}: CardProps) {
  const hasHeader = Boolean(title || eyebrow || icon || headerAside);
  const baseStyle: React.CSSProperties = {
    ...VARIANT_STYLES[variant],
    ...(onClick ? { cursor: 'pointer' } : {}),
    ...style,
  };

  const content = (
    <>
      {hasHeader && (
        <CardHeader
          eyebrow={eyebrow}
          icon={icon}
          title={title}
          subtitle={subtitle}
          aside={headerAside}
          padBottom={HEADER_PAD_BOTTOM[size]}
        />
      )}
      {children}
    </>
  );

  const cls = [
    'rounded-lg',
    padding ?? SIZE_PADDING[size],
    onClick ? 'transition-shadow hover:shadow-md' : '',
    className,
  ].filter(Boolean).join(' ');

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        data-slot="card"
        data-variant={variant}
        data-size={size}
        className={`${cls} text-left w-full`}
        style={baseStyle}
      >
        {content}
      </button>
    );
  }

  return (
    <div
      data-slot="card"
      data-variant={variant}
      data-size={size}
      className={cls}
      style={baseStyle}
    >
      {content}
    </div>
  );
}

// ─── Header (internal) ──────────────────────────────────────

interface CardHeaderProps {
  eyebrow?: ReactNode;
  icon?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
  padBottom: string;
}

function CardHeader({ eyebrow, icon, title, subtitle, aside, padBottom }: CardHeaderProps) {
  return (
    <header
      data-slot="card-header"
      className={`flex items-start justify-between gap-3 ${padBottom}`}
      style={{ borderBottom: '1px solid var(--color-border)' }}
    >
      <div className="flex items-start gap-3 min-w-0">
        {icon && (
          <div
            className="shrink-0 w-7 h-7 flex items-center justify-center rounded"
            style={{
              backgroundColor: 'var(--color-accent-bg)',
              color: 'var(--color-accent-bright)',
            }}
            aria-hidden="true"
          >
            {icon}
          </div>
        )}
        <div className="min-w-0">
          {eyebrow && (
            <div
              className="text-[10px] uppercase tracking-widest font-semibold mb-0.5"
              style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {eyebrow}
            </div>
          )}
          {title && (
            <h3
              className="text-sm font-semibold leading-tight truncate"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {title}
            </h3>
          )}
          {subtitle && (
            <p
              className="text-xs mt-0.5"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </header>
  );
}
