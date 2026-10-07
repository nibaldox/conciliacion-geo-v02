import { useTranslation } from 'react-i18next';
import { useTheme } from '../../stores/theme';

export function ThemeToggle() {
  const { isDark, toggle } = useTheme();
  const { t } = useTranslation();
  const action = t(isDark ? 'theme.switch_to_light' : 'theme.switch_to_dark');

  return (
    <button type="button" data-slot="theme-toggle" data-theme={isDark ? 'dark' : 'light'} onClick={toggle} title={action} aria-label={action} className="inline-flex items-center justify-center gap-2 rounded-lg border border-border-strong bg-surface-raised px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
      <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {isDark ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></> : <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />}
      </svg>
      <span>{t(isDark ? 'theme.light_action' : 'theme.dark_action')}</span>
    </button>
  );
}
