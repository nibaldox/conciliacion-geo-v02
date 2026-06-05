import { ReactNode, ButtonHTMLAttributes } from 'react';
import { Spinner } from './Spinner';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'launch' | 'terminal';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  children?: ReactNode;
}

interface VariantStyle {
  base: React.CSSProperties;
  hover?: React.CSSProperties;
  focus: string;
  textClass?: string;
}

const VARIANT_STYLES: Record<Variant, VariantStyle> = {
  primary: {
    base: { backgroundColor: 'var(--color-mine-blue)', color: '#fff' },
    hover: { filter: 'brightness(1.1)' },
    focus: 'focus-visible:ring-mine-blue',
  },
  secondary: {
    base: {
      backgroundColor: 'var(--color-surface-raised)',
      color: 'var(--color-text-primary)',
      border: '1px solid var(--color-border)',
    },
    hover: { borderColor: 'var(--color-border-strong)' },
    focus: 'focus-visible:ring-mine-blue',
  },
  ghost: {
    base: { backgroundColor: 'transparent', color: 'var(--color-text-secondary)' },
    focus: 'focus-visible:ring-mine-blue',
  },
  danger: {
    base: { backgroundColor: 'var(--color-mine-red)', color: '#fff' },
    hover: { filter: 'brightness(1.1)' },
    focus: 'focus-visible:ring-mine-red',
  },
  // The Mission Control hero CTA — orange accent, uppercase,
  // tracking, neon glow on hover. The "LAUNCH ENGINE" style.
  launch: {
    base: {
      backgroundColor: 'var(--color-accent)',
      color: '#0a0e14',
      boxShadow: '0 0 0 1px var(--color-accent-bright) inset, var(--shadow-glow-accent)',
    },
    hover: {
      backgroundColor: 'var(--color-accent-bright)',
      boxShadow: '0 0 24px rgba(249, 115, 22, 0.35)',
    },
    focus: 'focus-visible:ring-accent',
    textClass: 'uppercase tracking-wider font-semibold',
  },
  // Terminal / "console" button — monospace, subtle border, like
  // a command in a terminal. Used for secondary actions that
  // feel like "I issued a command".
  terminal: {
    base: {
      backgroundColor: 'var(--color-surface-sunken)',
      color: 'var(--color-accent-bright)',
      border: '1px solid var(--color-border)',
      fontFamily: 'var(--font-mono)',
    },
    hover: {
      borderColor: 'var(--color-accent)',
      color: 'var(--color-accent-bright)',
    },
    focus: 'focus-visible:ring-accent',
  },
};

const SIZE_STYLES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-6 py-2.5 text-sm gap-2.5',
};

const SIZE_FOR_LAUNCH: Record<Size, string> = {
  sm: 'px-4 py-2 text-xs gap-2',
  md: 'px-5 py-2.5 text-sm gap-2.5',
  lg: 'px-8 py-4 text-base gap-3',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  fullWidth = false,
  leftIcon,
  rightIcon,
  children,
  className = '',
  style,
  onClick,
  type = 'button',
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const v = VARIANT_STYLES[variant];
  const sizeCls = (variant === 'launch' ? SIZE_FOR_LAUNCH : SIZE_STYLES)[size];

  return (
    <button
      type={type}
      disabled={isDisabled}
      onClick={isDisabled ? undefined : onClick}
      className={[
        'inline-flex items-center justify-center rounded-md font-medium',
        'transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        v.focus,
        v.textClass ?? '',
        sizeCls,
        fullWidth ? 'w-full' : '',
        className,
      ].filter(Boolean).join(' ')}
      style={{ ...v.base, ...(v.hover ?? {}), ...style }}
      aria-busy={loading || undefined}
      data-variant={variant}
      {...rest}
    >
      {loading ? (
        <Spinner size={size === 'lg' ? 'md' : 'sm'} />
      ) : (
        leftIcon && <span className="inline-flex shrink-0">{leftIcon}</span>
      )}
      {children && <span className={loading ? 'opacity-70' : ''}>{children}</span>}
      {!loading && rightIcon && <span className="inline-flex shrink-0">{rightIcon}</span>}
    </button>
  );
}
