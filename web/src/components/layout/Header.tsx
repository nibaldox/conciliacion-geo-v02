import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useQueryClient } from '@tanstack/react-query';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';

export function Header() {
  const { reset } = useSession();
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  const handleNewSession = () => {
    localStorage.removeItem('session_id');
    queryClient.clear();
    reset();
    window.location.href = window.location.pathname;
  };

  return (
    <header
      className="flex items-center justify-between px-6 py-3 border-b shrink-0"
      style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
    >
      <div className="flex items-center gap-3">
        <div
          className="flex items-center justify-center w-10 h-10 rounded-lg text-white font-bold text-lg"
          style={{ backgroundColor: 'var(--color-mine-blue)' }}
        >
          CG
        </div>
        <div>
          <h1 className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>
            {t('app.title')}
          </h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {t('app.tagline')}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        <LanguageToggle />
        <button
          onClick={handleNewSession}
          title="Iniciar nueva sesión"
          className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors hover:opacity-80"
          style={{ color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)', backgroundColor: 'transparent' }}
        >
          {t('common.loading') === 'Loading…' ? 'New Session' : 'Nueva Sesión'}
        </button>
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>v2.0</span>
      </div>
    </header>
  );
}
