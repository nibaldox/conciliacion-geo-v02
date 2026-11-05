import { useRef, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useWorkflowStatus } from '../../hooks/useWorkflowStatus';
import { Icon3D, IconProfiles, IconDashboard, IconLightning, IconExport, IconLock } from '../ui/Icons';

type WorkspaceView = '3d' | 'profiles' | 'dashboard' | 'blast' | 'export-ai';

interface ViewsToolbarProps {
  onNavigate?: () => void;
}

const VIEWS = [
  { key: '3d', icon: Icon3D, text: 'workspace.view3d', hotkey: '1', requiresComplete: false },
  { key: 'profiles', icon: IconProfiles, text: 'workspace.profiles', hotkey: '2', requiresComplete: true },
  { key: 'dashboard', icon: IconDashboard, text: 'workspace.summary', hotkey: '3', requiresComplete: true },
  { key: 'blast', icon: IconLightning, text: 'workspace.blast', hotkey: '4', requiresComplete: true },
  { key: 'export-ai', icon: IconExport, text: 'workspace.export', hotkey: '5', requiresComplete: true },
] as const;

export function ViewsToolbar({ onNavigate }: ViewsToolbarProps) {
  const { t } = useTranslation();
  const activeView = useSession((s) => s.activeWorkspaceView);
  const setActiveView = useSession((s) => s.setActiveWorkspaceView);
  const { isComplete } = useWorkflowStatus();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const select = (key: WorkspaceView) => {
    setActiveView(key);
    onNavigate?.();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = VIEWS.length - 1;
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = index === last ? 0 : index + 1;
    else if (event.key === 'ArrowLeft') next = index === 0 ? last : index - 1;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = last;
    if (next === null) return;
    event.preventDefault();
    tabRefs.current[next]?.focus();
    select(VIEWS[next].key);
  };

  return (
    <nav
      data-slot="views-toolbar"
      aria-label={t('ux.views_nav')}
      className="shrink-0 overflow-x-auto border-b border-border bg-surface-raised px-3 md:px-6"
    >
      <div role="tablist" aria-label={t('ux.views_nav')} className="flex min-w-max items-stretch gap-1">
        {VIEWS.map(({ key, icon: Icon, text, hotkey, requiresComplete }, index) => {
          const active = activeView === key;
          const locked = requiresComplete && !isComplete;
          const label = t(text);
          return (
            <button
              key={key}
              ref={(node) => { tabRefs.current[index] = node; }}
              type="button"
              role="tab"
              id={`views-tab-${key}`}
              aria-selected={active}
              aria-current={active ? 'page' : undefined}
              aria-controls="main-content"
              aria-label={label}
              tabIndex={active ? 0 : -1}
              data-view={key}
              data-locked={locked ? 'true' : undefined}
              data-active={active ? 'true' : undefined}
              title={locked ? t('ux.view_locked') : label}
              onClick={() => select(key)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={[
                'relative -mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent',
                active
                  ? 'border-accent-bright text-accent-bright opacity-100'
                  : `border-transparent text-text-secondary hover:border-border hover:text-text-primary${locked ? ' opacity-60' : ''}`,
              ].join(' ')}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{label}</span>
              {locked && <IconLock data-slot="view-lock" className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-accent-bright' : 'text-text-muted'}`} aria-hidden="true" />}
              <kbd
                aria-hidden="true"
                title={t('ux.shortcut', { key: hotkey })}
                className="hidden rounded border border-border bg-surface-muted px-1.5 font-mono text-[10px] leading-4 text-text-muted sm:inline-block"
              >
                {hotkey}
              </kbd>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
