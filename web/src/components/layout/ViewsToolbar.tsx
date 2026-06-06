import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { Tooltip } from '../ui/Tooltip';
import { Icon3D, IconProfiles, IconDashboard, IconExport } from '../ui/Icons';


export function ViewsToolbar() {
  const { t } = useTranslation();
  const { activeWorkspaceView, setActiveWorkspaceView } = useSession();

  const views: {
    key: typeof activeWorkspaceView;
    icon: React.ReactNode;
    labelKey: string;
    descriptionKey: string;
  }[] = [
    {
      key: '3d',
      icon: <Icon3D className="w-5 h-5" />,
      labelKey: 'step1.tab_3d',
      descriptionKey: 'step1.view3d_title',
    },

    {
      key: 'profiles',
      icon: <IconProfiles className="w-5 h-5" />,
      labelKey: 'step4.tab_profiles',
      descriptionKey: 'step4.tab_profiles',
    },
    {
      key: 'dashboard',
      icon: <IconDashboard className="w-5 h-5" />,
      labelKey: 'step4.tab_dashboard',
      descriptionKey: 'step4.tab_dashboard',
    },
    {
      key: 'export-ai',
      icon: <IconExport className="w-5 h-5" />,
      labelKey: 'step4.tab_export',
      descriptionKey: 'step4.tab_export',
    },
  ];

  return (
    <div
      data-slot="views-toolbar"
      className="flex flex-col gap-2.5 p-2 border rounded-l-xl z-20 shrink-0 shadow-lg select-none"
      style={{
        backgroundColor: 'var(--color-surface-raised)',
        borderColor: 'var(--color-border)',
        borderRight: 'none',
      }}
    >
      <div
        className="text-[9px] uppercase tracking-wider font-mono font-bold text-center border-b pb-1.5 opacity-55"
        style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
      >
        VIEWS
      </div>

      <div className="flex flex-col gap-2">
        {views.map((view) => {
          const isActive = activeWorkspaceView === view.key;
          return (
            <Tooltip
              key={view.key}
              content={t(view.descriptionKey, { defaultValue: t(view.labelKey) })}
              side="left"
            >
              <button
                onClick={() => setActiveWorkspaceView(view.key)}
                className="w-10 h-10 rounded-lg flex items-center justify-center text-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent cursor-pointer"
                style={{
                  backgroundColor: isActive ? 'var(--color-accent-bg)' : 'transparent',
                  color: isActive ? 'var(--color-accent-bright)' : 'var(--color-text-muted)',
                  border: isActive
                    ? '1px solid var(--color-accent)'
                    : '1px solid transparent',
                  boxShadow: isActive ? '0 0 10px rgba(249, 115, 22, 0.25)' : 'none',
                }}
                aria-label={t(view.labelKey)}
                aria-pressed={isActive}
              >
                {view.icon}
              </button>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}
