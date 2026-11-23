import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { useBenchFocus } from '../../stores/benchFocus';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import type { SectionRef } from '../../utils/workspaceTargets';

export interface AgentChipActions {
  sections: readonly SectionRef[];
  contextSectionId: string | null;
  openSection: (ref: SectionRef) => void;
  selectBench: (sectionId: string, designBench: number) => void;
}

export function useAgentChipActions(): AgentChipActions {
  const { data: sections = [] } = useSections();
  const contextSectionId = useSession((state) => state.selectedSection);
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
