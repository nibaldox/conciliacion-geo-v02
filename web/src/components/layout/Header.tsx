import { useSession } from '../../stores/session';
import { useQueryClient } from '@tanstack/react-query';
import { ThemeToggle } from './ThemeToggle';

export function Header() {
  const { reset } = useSession();
  const queryClient = useQueryClient();

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
            Conciliación Geotécnica
          </h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Diseño vs As-Built
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        <button
          onClick={handleNewSession}
          title="Iniciar nueva sesión"
          className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors hover:opacity-80"
          style={{ color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)', backgroundColor: 'transparent' }}
        >
          Nueva Sesión
        </button>
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>v2.0</span>
      </div>
    </header>
  );
}
