type Size = 'sm' | 'md' | 'lg';

const SIZE: Record<Size, { box: number; border: number; className: string }> = {
  sm: { box: 12, border: 2, className: 'h-3 w-3' },
  md: { box: 16, border: 2, className: 'h-4 w-4' },
  lg: { box: 24, border: 3, className: 'h-6 w-6' },
};

interface SpinnerProps {
  size?: Size;
  className?: string;
}

export function Spinner({ size = 'md', className = '' }: SpinnerProps) {
  const cfg = SIZE[size];
  return (
    <svg
      className={`animate-spin ${cfg.className} ${className}`}
      style={{ color: 'currentColor' }}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth={cfg.border}
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
