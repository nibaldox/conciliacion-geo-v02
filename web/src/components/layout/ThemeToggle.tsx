import { useTranslation } from 'react-i18next';
import { useTheme } from '../../stores/theme';

export function ThemeToggle() {
  const { isDark, toggle } = useTheme();
  const { t } = useTranslation();

  return (
    <button
      onClick={toggle}
      title={isDark ? t('theme.switch_to_light') : t('theme.switch_to_dark')}
      className="w-9 h-9 flex items-center justify-center rounded-lg transition-colors"
      style={{ color: 'var(--color-text-secondary)' }}
      aria-label={isDark ? t('theme.aria_light') : t('theme.aria_dark')}
    >
      {/* Sun icon (dark mode → click for light) */}
      <svg
        className="absolute w-5 h-5 transition-all duration-300"
        style={{
          opacity: isDark ? 1 : 0,
          transform: isDark ? 'rotate(0deg) scale(1)' : 'rotate(180deg) scale(0)',
        }}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>

      {/* Moon icon (light mode → click for dark) */}
      <svg
        className="absolute w-5 h-5 transition-all duration-300"
        style={{
          opacity: !isDark ? 1 : 0,
          transform: !isDark ? 'rotate(0deg) scale(1)' : 'rotate(-180deg) scale(0)',
        }}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </button>
  );
}
