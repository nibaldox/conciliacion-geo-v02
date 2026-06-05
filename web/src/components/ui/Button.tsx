import { ReactNode, ButtonHTMLAttributes } from 'react';
import { Spinner } from './Spinner';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
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

const VARIANT_STYLES: Record<Variant, { base: React.CSSProperties; hover?: React.CSSProperties; focus: string }> = {
  primary: {
    base: { backgroundColor: 'var(--color-mine-blue)', color: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.10)' },
    hover: { boxShadow: '0 2px 6px rgba(0,0,0,0.15)' },
    focus: 'focus-visible:ring-mine-blue',
  },
  secondary: {
    base: { backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border)' },
    focus: 'focus-visible:ring-mine-blue',
  },
  ghost: {
    base: { backgroundColor: 'transparent', color: 'var(--color-text-secondary)' },
    focus: 'focus-visible:ring-mine-blue',
  },
  danger: {
    base: { backgroundColor: 'var(--color-mine-red)', color: '#fff' },
    focus: 'focus-visible:ring-mine-red',
  },
};

const SIZE_STYLES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-6 py-2.5 text-sm font-semibold gap-2',
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
  const sizeCls = SIZE_STYLES[size];

  return (
    <button
      type={type}
      disabled={isDisabled}
      onClick={isDisabled ? undefined : onClick}
      className={[
        'inline-flex items-center justify-center rounded-lg font-medium',
        'transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        v.focus,
        sizeCls,
        fullWidth ? 'w-full' : '',
        className,
      ].filter(Boolean).join(' ')}
      style={{ ...v.base, ...(v.hover ?? {}), ...style }}
      aria-busy={loading || undefined}
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
