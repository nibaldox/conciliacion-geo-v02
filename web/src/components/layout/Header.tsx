import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useQueryClient } from '@tanstack/react-query';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';
import { KeyboardShortcutsHelp } from '../ui/KeyboardShortcutsHelp';

export function Header() {
  const { reset, setView, demoMode } = useSession();
  const queryClient = useQueryClient();
  const { t, i18n } = useTranslation();

  const handleNewSession = () => {
    localStorage.removeItem('session_id');
    queryClient.clear();
    reset();
    window.location.href = window.location.pathname;
  };

  const handleGoHome = () => {
    setView('landing');
  };

  return (
    <header
      className="flex items-center justify-between px-6 py-3 border-b shrink-0"
      style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
    >
      <div className="flex items-center gap-3">
        <button
          onClick={handleGoHome}
          className="flex items-center gap-3 rounded-lg px-2 py-1 -ml-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2"
          title={i18n.language === 'es' ? 'Volver al inicio' : 'Back to home'}
        >
          <div
            className="flex items-center justify-center w-10 h-10 rounded-lg text-white font-bold text-lg"
            style={{ backgroundColor: 'var(--color-mine-blue)' }}
          >
            CG
          </div>
          <div className="text-left">
            <h1 className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>
              {t('app.title')}
            </h1>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              {t('app.tagline')}
              {demoMode && <span className="ml-1"> · 🎮</span>}
            </p>
          </div>
        </button>
      </div>
      <div className="flex items-center gap-2 md:gap-3">
        <div className="hidden md:block">
          <KeyboardShortcutsHelp />
        </div>
        <ThemeToggle />
        <LanguageToggle />
        <button
          onClick={handleNewSession}
          title="Iniciar nueva sesión"
          className="hidden sm:inline-block px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors hover:opacity-80"
          style={{ color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)', backgroundColor: 'transparent' }}
        >
          {i18n.language === 'es' ? 'Nueva Sesión' : 'New Session'}
        </button>
        <span className="text-xs hidden md:inline" style={{ color: 'var(--color-text-muted)' }}>v2.0</span>
      </div>
    </header>
  );
}
