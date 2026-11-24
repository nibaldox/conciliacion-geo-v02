import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { useBenchFocus } from '../../stores/benchFocus';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import type { SectionRef } from '../../utils/workspaceTargets';
import type { WorkspaceViewId } from '../../utils/viewContext';

export interface AgentChipActions {
  sections: readonly SectionRef[];
  contextSectionId: string | null;
  openSection: (ref: SectionRef) => void;
  selectBench: (sectionId: string, designBench: number) => void;
}

export function normalizeContextSectionId(
  selected: string | null,
  sections: readonly SectionRef[],
): string | null {
  if (selected === null) return null;
  if (sections.some((section) => section.id === selected)) return selected;
  const matches = sections.filter((section) => section.name === selected);
  return matches.length === 1 ? matches[0].id : null;
}

export function resolveVisibleSection(
  { selected, selectedByUser, view, profilesMode }: {
    selected: string | null;
    selectedByUser: boolean;
    view: WorkspaceViewId;
    profilesMode: 'grid' | 'detail';
  },
  sections: readonly SectionRef[],
): SectionRef | null {
  if (!selectedByUser && !(view === 'profiles' && profilesMode === 'detail')) return null;
  const id = normalizeContextSectionId(selected, sections);
  return sections.find((section) => section.id === id) ?? null;
}

export function useAgentChipActions(): AgentChipActions {
  const { data: sections = [] } = useSections();
  const selected = useSession((state) => state.selectedSection);
  const selectedByUser = useSession((state) => state.selectedByUser);
  const view = useSession((state) => state.activeWorkspaceView);
  const profilesMode = useSession((state) => state.profilesMode);
  const contextSectionId = resolveVisibleSection({ selected, selectedByUser, view, profilesMode }, sections)?.id ?? null;
  const openSection = (ref: SectionRef) => {
    const session = useSession.getState();
    session.setSelectedSection(ref.id);
    session.setProfilesMode('detail');
    session.setActiveWorkspaceView('profiles');
    useWorkspaceMode.getState().enterCopilot('manualView');
  };
  const selectBench = (sectionId: string, designBench: number) => {
    const section = sections.find((item) => item.id === sectionId);
    if (!section) return;
    openSection(section);
    useBenchFocus.getState().requestBench(sectionId, designBench);
  };
  return { sections, contextSectionId, openSection, selectBench };
}
