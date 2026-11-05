import { useMemo } from 'react';
import { useProcessStatus, useSections } from '../api/hooks';
import { useSession, type WorkflowStepKey } from '../stores/session';

export type WorkflowStepState = 'done' | 'current' | 'pending' | 'locked';

export type ProjectStatus = 'empty' | 'surfaces' | 'ready' | 'processing' | 'complete';

export interface WorkflowStatusInput {
  designMeshId: string | null;
  topoMeshId: string | null;
  sectionCount: number;
  processStatus: 'idle' | 'processing' | 'complete' | 'error' | null | undefined;
}

export interface WorkflowStatus {
  hasDesign: boolean;
  hasTopo: boolean;
  surfacesDone: boolean;
  sectionCount: number;
  sectionsDone: boolean;
  isProcessing: boolean;
  isComplete: boolean;
  steps: Record<WorkflowStepKey, WorkflowStepState>;
  projectStatus: ProjectStatus;
  nextStep: WorkflowStepKey | null;
}

const STEP_ORDER: readonly WorkflowStepKey[] = ['surfaces', 'sections', 'parameters', 'process'];

export function computeWorkflowStatus(input: WorkflowStatusInput): WorkflowStatus {
  const hasDesign = Boolean(input.designMeshId);
  const hasTopo = Boolean(input.topoMeshId);
  const surfacesDone = hasDesign && hasTopo;
  const sectionCount = input.sectionCount;
  const sectionsDone = surfacesDone && sectionCount > 0;
  const isProcessing = input.processStatus === 'processing';
  const isComplete = input.processStatus === 'complete';

  const done: Record<WorkflowStepKey, boolean> = {
    surfaces: surfacesDone,
    sections: sectionsDone,
    parameters: sectionsDone,
    process: isComplete,
  };
  const locked: Record<WorkflowStepKey, boolean> = {
    surfaces: false,
    sections: !surfacesDone,
    parameters: !surfacesDone,
    process: !sectionsDone,
  };

  let nextStep: WorkflowStepKey | null = null;
  const steps = {} as Record<WorkflowStepKey, WorkflowStepState>;
  for (const key of STEP_ORDER) {
    if (done[key]) {
      steps[key] = 'done';
    } else if (locked[key]) {
      steps[key] = 'locked';
    } else if (nextStep === null) {
      steps[key] = 'current';
      nextStep = key;
    } else {
      steps[key] = 'pending';
    }
  }

  let projectStatus: ProjectStatus = 'empty';
  if (isComplete) projectStatus = 'complete';
  else if (isProcessing) projectStatus = 'processing';
  else if (sectionsDone) projectStatus = 'ready';
  else if (surfacesDone) projectStatus = 'surfaces';

  return {
    hasDesign,
    hasTopo,
    surfacesDone,
    sectionCount,
    sectionsDone,
    isProcessing,
    isComplete,
    steps,
    projectStatus,
    nextStep,
  };
}

export function useWorkflowStatus(): WorkflowStatus {
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const { data: sections } = useSections();
  const { data: status } = useProcessStatus();
  const sectionCount = sections?.length ?? 0;
  const processStatus = status?.status;

  return useMemo(
    () => computeWorkflowStatus({ designMeshId, topoMeshId, sectionCount, processStatus }),
    [designMeshId, topoMeshId, sectionCount, processStatus],
  );
}
