import { useTranslation } from 'react-i18next';
import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { useBenchFocus } from '../../stores/benchFocus';
import { describeViewContext, type WorkspaceViewId } from '../../utils/viewContext';
import { resolveVisibleSection } from './useAgentChipActions';

const VIEW_KEYS: Record<WorkspaceViewId, string> = {
  '3d': 'workspace.view3d',
  dashboard: 'workspace.summary',
  profiles: 'workspace.profiles',
  blast: 'workspace.blast',
  'export-ai': 'workspace.export',
};

export function ContextChip() {
  const { t } = useTranslation();
  const { data: sections = [] } = useSections();
  const view = useSession((state) => state.activeWorkspaceView);
  const profilesMode = useSession((state) => state.profilesMode);
  const selectedId = useSession((state) => state.selectedSection);
  const selectedByUser = useSession((state) => state.selectedByUser);
  const current = useBenchFocus((state) => state.current);
  const section = resolveVisibleSection({ selected: selectedId, selectedByUser, view, profilesMode }, sections);
  const bench = section && current?.sectionId === section.id && current.designBenchNumber !== null
    ? { designBench: current.designBenchNumber }
    : null;
  const context = describeViewContext({ view, profilesMode, section, bench });
  const viewName = t(VIEW_KEYS[context.view]);
  let label = viewName;
  if (context.view === 'profiles' && context.mode === 'grid') {
    label = `${viewName} · ${t('aiChat.context.grid')}`;
  } else if (context.view === 'profiles' && context.sectionName) {
    label = t('aiChat.context.profile', { name: context.sectionName });
    if (context.designBench !== undefined) label += ` · ${t('aiChat.context.bench', { n: context.designBench })}`;
  } else if (context.view === 'dashboard' && context.sectionName) {
    label = t('aiChat.context.section', { view: viewName, name: context.sectionName });
  }
  return <div data-testid="ai-chat-context-chip" title={t('aiChat.context.tooltip')} className="mx-auto w-full max-w-3xl truncate px-3 pt-2 text-xs text-text-muted">{t('aiChat.context.viewing', { context: label })}</div>;
}
