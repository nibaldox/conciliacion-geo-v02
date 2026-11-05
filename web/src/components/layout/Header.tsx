import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useQueryClient } from '@tanstack/react-query';
import { LanguageToggle } from './LanguageToggle';
import { ThemeToggle } from './ThemeToggle';
import { KeyboardShortcutsHelp } from '../ui/KeyboardShortcutsHelp';
import { Button } from '../ui/Button';
import { IconExport } from '../ui/Icons';
import { useWorkflowStatus, type ProjectStatus } from '../../hooks/useWorkflowStatus';

const STATUS_TONE: Record<ProjectStatus, 'ok' | 'warn' | 'accent' | undefined> = {
  empty: undefined,
  surfaces: 'accent',
  ready: 'warn',
  processing: 'accent',
  complete: 'ok',
};

function BrandMark() {
  return (
    <svg data-slot="brand-mark" aria-hidden="true" viewBox="0 0 32 32" className="h-9 w-9 shrink-0">
      <rect x="1" y="1" width="30" height="30" rx="8" fill="var(--color-accent-bg)" stroke="var(--color-accent)" strokeWidth="1.5" />
      <path d="M6 9h4v4h4v4h4v4h4v4h4" fill="none" stroke="var(--color-accent-bright)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 15h3v4h4v4h4" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.6" />
    </svg>
  );
}

export function Header() {
  const reset = useSession((s) => s.reset);
  const collapsed = useSession((s) => s.sidebarCollapsed);
  const setCollapsed = useSession((s) => s.setSidebarCollapsed);
  const setView = useSession((s) => s.setActiveWorkspaceView);
  const { projectStatus } = useWorkflowStatus();
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
        <BrandMark />
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold md:text-lg">{t('app.title')}</h1>
          <p className="hidden text-xs text-text-muted lg:block">{t('app.tagline')}</p>
        </div>
        <span data-slot="project-status" data-status={projectStatus} data-tone={STATUS_TONE[projectStatus]} className="ui-chip hidden shrink-0 sm:inline-flex" role="status">{t('ux.status_' + projectStatus)}</span>
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
