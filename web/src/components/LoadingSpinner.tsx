interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
}

const SIZE_CLASSES: Record<NonNullable<LoadingSpinnerProps['size']>, string> = {
  sm: 'h-6 w-6',
  md: 'h-10 w-10',
  lg: 'h-16 w-16',
};

export function LoadingSpinner({ size = 'md', message }: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <div
        className={`animate-spin rounded-full ${SIZE_CLASSES[size]} border-b-2`}
        role="status"
        aria-label={message ?? 'Cargando'}
        style={{ borderColor: 'var(--color-mine-blue)', borderTopColor: 'transparent' }}
      />
      {message && <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{message}</p>}
    </div>
  );
}
