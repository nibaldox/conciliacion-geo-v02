import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useQueryClient } from '@tanstack/react-query';
import { LanguageToggle } from './LanguageToggle';
import { ThemeToggle } from './ThemeToggle';
import { KeyboardShortcutsHelp } from '../ui/KeyboardShortcutsHelp';
import { Button } from '../ui/Button';
import { IconExport } from '../ui/Icons';

export function Header() {
  const reset = useSession((s) => s.reset);
  const collapsed = useSession((s) => s.sidebarCollapsed);
  const setCollapsed = useSession((s) => s.setSidebarCollapsed);
  const setView = useSession((s) => s.setActiveWorkspaceView);
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  const handleNewSession = () => {
    queryClient.clear();
    reset();
    window.location.href = window.location.pathname;
  };

  return (
    <header data-slot="app-header" className="flex min-h-16 items-center justify-between gap-3 border-b border-border bg-surface-raised px-3 py-3 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button type="button" className="rounded-lg p-2 text-text-secondary hover:bg-surface-muted md:hidden" aria-label={t('workspace.menu')} aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}>☰</button>
        <span className="text-3xl font-bold tracking-tight text-accent-bright" aria-hidden="true">CG</span>
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold md:text-lg">{t('app.title')}</h1>
          <p className="hidden text-xs text-text-muted lg:block">{t('app.tagline')}</p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <div className="hidden items-center gap-1 md:flex"><KeyboardShortcutsHelp /><LanguageToggle /></div>
        <ThemeToggle />
        <Button variant="secondary" size="sm" onClick={handleNewSession} aria-label={t('header.new_session')} title={t('header.new_session')}><span className="hidden sm:inline">{t('header.new_session')}</span><span className="sm:hidden" aria-hidden="true">+</span></Button>
        <span className="hidden sm:inline-flex"><Button variant="secondary" size="sm" leftIcon={<IconExport className="h-4 w-4" />} onClick={() => setView('export-ai')}>{t('workspace.export')}</Button></span>
      </div>
    </header>
  );
}
