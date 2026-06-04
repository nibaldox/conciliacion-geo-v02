import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from './Tooltip';
import { useHotkeys } from '../../hooks/useHotkeys';

/**
 * Small button in the header that opens a modal listing all
 * keyboard shortcuts. The button itself is wired to `?` as a
 * hotkey so the user can press `?` from anywhere to see the list.
 *
 * Pressing Escape inside the modal closes it.
 */
export function KeyboardShortcutsHelp() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useHotkeys('?', () => setOpen((v) => !v));
  useHotkeys('Escape', () => setOpen(false), [open]);

  // Body scroll lock while modal is open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const Row = ({ keys, label }: { keys: string[]; label: string }) => (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      <span className="flex gap-1">
        {keys.map((k) => (
          <kbd
            key={k}
            className="px-1.5 py-0.5 rounded text-xs font-mono border"
            style={{
              backgroundColor: 'var(--color-surface-muted)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
          >
            {k}
          </kbd>
        ))}
      </span>
    </div>
  );

  return (
    <>
      <Tooltip content={t('shortcuts.title')} side="bottom">
        <button
          onClick={() => setOpen(true)}
          aria-label={t('shortcuts.help')}
          className="px-2 py-1 rounded-md text-xs font-mono border focus-visible:outline-none focus-visible:ring-2"
          style={{
            backgroundColor: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-primary)',
          }}
        >
          ?
        </button>
      </Tooltip>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="shortcuts-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          onClick={() => setOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border p-6 shadow-2xl"
            style={{
              backgroundColor: 'var(--color-surface)',
              borderColor: 'var(--color-border)',
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 id="shortcuts-title" className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {t('shortcuts.title')}
              </h2>
              <button
                onClick={() => setOpen(false)}
                aria-label={t('shortcuts.close')}
                className="text-xl leading-none"
                style={{ color: 'var(--color-text-muted)' }}
              >
                ×
              </button>
            </div>
            <p className="text-xs mb-3" style={{ color: 'var(--color-text-muted)' }}>
              {t('shortcuts.intro')}
            </p>
            <div className="text-xs uppercase tracking-wide mb-1" style={{ color: 'var(--color-text-muted)' }}>
              {t('shortcuts.navigation')}
            </div>
            <Row keys={['←']} label={t('shortcuts.prev_step')} />
            <Row keys={['→']} label={t('shortcuts.next_step')} />
            <Row keys={['1', '2', '3', '4']} label={t('shortcuts.go_step')} />
            <div className="text-xs uppercase tracking-wide mb-1 mt-3" style={{ color: 'var(--color-text-muted)' }}>
              {t('shortcuts.actions')}
            </div>
            <Row keys={['?']} label={t('shortcuts.help')} />
            <Row keys={['Esc']} label={t('shortcuts.close')} />
            <p className="text-xs mt-4 italic" style={{ color: 'var(--color-text-muted)' }}>
              {t('shortcuts.press_esc')}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
