import { useTranslation } from 'react-i18next';
import { setLocale, SUPPORTED_LOCALES, type SupportedLocale } from '../../i18n';

/**
 * Language toggle button for the header. Cycles through the
 * supported locales. The current locale is reflected on the
 * <html lang> attribute and persisted in localStorage (handled
 * by the i18n config).
 */
export function LanguageToggle() {
  const { i18n, t } = useTranslation();
  const current = i18n.language as SupportedLocale;

  const cycle = () => {
    const idx = SUPPORTED_LOCALES.indexOf(current);
    const next = SUPPORTED_LOCALES[(idx + 1) % SUPPORTED_LOCALES.length];
    setLocale(next);
  };

  return (
    <button
      onClick={cycle}
      title={t('language.toggle')}
      aria-label={t('language.toggle')}
      className="px-2 py-1 rounded-md text-xs font-medium border focus-visible:outline-none focus-visible:ring-2"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
        color: 'var(--color-text-primary)',
      }}
    >
      <span className="uppercase tracking-wide">
        {current === 'es' ? '🇪🇸 ES' : '🇺🇸 EN'}
      </span>
    </button>
  );
}
