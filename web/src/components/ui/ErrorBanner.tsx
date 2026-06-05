import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

interface ErrorBannerProps {
  message: string | null;
  onDismiss: () => void;
  onRetry?: () => void;
  autoDismissMs?: number;
  variant?: 'error' | 'warning' | 'info';
}

/**
 * Inline error/warning banner that appears at the top of a panel
 * (instead of using the browser's native `alert()` which breaks
 * the visual language and is inaccessible).
 *
 * - Renders nothing when message is null.
 * - Optional auto-dismiss (default: no auto-dismiss, user must
 *   close it explicitly).
 * - Optional retry button for recoverable errors.
 * - `variant` controls the color tokens used.
 */
export function ErrorBanner({
  message,
  onDismiss,
  onRetry,
  autoDismissMs,
  variant = 'error',
}: ErrorBannerProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (message && autoDismissMs && autoDismissMs > 0) {
      const id = setTimeout(onDismiss, autoDismissMs);
      return () => clearTimeout(id);
    }
  }, [message, autoDismissMs, onDismiss]);

  if (!message) return null;

  const palette = {
    error: { bg: 'var(--status-nok-bg)', border: 'var(--status-nok-border)', text: 'var(--status-nok-text)' },
    warning: { bg: 'var(--status-warn-bg)', border: 'var(--status-warn-border)', text: 'var(--status-warn-text)' },
    info: { bg: 'var(--status-extra-bg)', border: 'var(--status-extra-border)', text: 'var(--status-extra-text)' },
  }[variant];

  return (
    <div
      role="alert"
      data-slot="error-banner"
      className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border text-sm mb-3"
      style={{ backgroundColor: palette.bg, borderColor: palette.border, color: palette.text }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span aria-hidden="true">{variant === 'warning' ? '⚠️' : variant === 'info' ? 'ℹ️' : '❌'}</span>
        <span className="truncate">{message}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-2 py-1 rounded text-xs font-medium underline underline-offset-2 hover:opacity-80"
            style={{ color: palette.text }}
          >
            {t('common.retry')}
          </button>
        )}
        <button
          type="button"
          onClick={onDismiss}
          aria-label={t('common.close')}
          className="px-2 py-1 rounded text-xs font-medium hover:opacity-80"
          style={{ color: palette.text }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
