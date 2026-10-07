import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { Icon3D, IconProfiles, IconDashboard, IconLightning, IconExport } from '../ui/Icons';

interface ViewsToolbarProps {
  compact?: boolean;
  onNavigate?: () => void;
}

export function ViewsToolbar({ compact = false, onNavigate }: ViewsToolbarProps) {
  const { t } = useTranslation();
  const activeView = useSession((s) => s.activeWorkspaceView);
  const setActiveView = useSession((s) => s.setActiveWorkspaceView);
  const views = [
    { key: 'profiles', icon: IconProfiles, label: 'step4.tab_profiles', text: 'workspace.profiles' },
    { key: '3d', icon: Icon3D, label: 'step1.tab_3d', text: 'workspace.view3d' },
    { key: 'dashboard', icon: IconDashboard, label: 'step4.tab_dashboard', text: 'workspace.summary' },
    { key: 'blast', icon: IconLightning, label: 'step4.tab_blast', text: 'workspace.blast' },
    { key: 'export-ai', icon: IconExport, label: 'step4.tab_export', text: 'workspace.export' },
  ] as const;

  return (
    <nav data-slot="views-toolbar" aria-label={t('workspace.analysis')} className="flex flex-col gap-1">
      {!compact && <h3 className="px-3 pt-4 pb-2 text-xs font-semibold text-text-muted">{t('workspace.analysis')}</h3>}
      {views.map(({ key, icon: Icon, label, text }) => (
        <button
          key={key}
          type="button"
          onClick={() => { setActiveView(key); onNavigate?.(); }}
          aria-label={t(label)}
          aria-pressed={activeView === key}
          title={t(text)}
          className={['flex items-center gap-3 rounded-lg py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent', compact ? 'justify-center px-2' : 'px-3 text-left', activeView === key ? 'bg-accent-bg text-accent-bright' : 'text-text-secondary hover:bg-surface-muted hover:text-text-primary'].join(' ')}
        >
          <Icon className="h-5 w-5 shrink-0" />
          {!compact && <span>{t(text)}</span>}
        </button>
      ))}
    </nav>
  );
}
