import { describe, expect, it } from 'vitest';
import { computeWorkflowStatus, type WorkflowStatusInput } from '../useWorkflowStatus';

const base: WorkflowStatusInput = {
  designMeshId: null,
  topoMeshId: null,
  sectionCount: 0,
  processStatus: undefined,
};

describe('computeWorkflowStatus', () => {
  it('starts on surfaces when nothing is loaded', () => {
    const result = computeWorkflowStatus(base);
    expect(result.hasDesign).toBe(false);
    expect(result.hasTopo).toBe(false);
    expect(result.surfacesDone).toBe(false);
    expect(result.steps).toEqual({
      surfaces: 'current',
      sections: 'locked',
      parameters: 'locked',
      process: 'locked',
    });
    expect(result.nextStep).toBe('surfaces');
    expect(result.projectStatus).toBe('empty');
  });

  it('keeps surfaces current with only one mesh', () => {
    const result = computeWorkflowStatus({ ...base, designMeshId: 'd1' });
    expect(result.hasDesign).toBe(true);
    expect(result.hasTopo).toBe(false);
    expect(result.surfacesDone).toBe(false);
    expect(result.steps.surfaces).toBe('current');
    expect(result.steps.sections).toBe('locked');
    expect(result.nextStep).toBe('surfaces');
    expect(result.projectStatus).toBe('empty');
  });

  it('moves to sections when both meshes exist without sections', () => {
    const result = computeWorkflowStatus({ ...base, designMeshId: 'd1', topoMeshId: 't1' });
    expect(result.surfacesDone).toBe(true);
    expect(result.sectionsDone).toBe(false);
    expect(result.steps).toEqual({
      surfaces: 'done',
      sections: 'current',
      parameters: 'pending',
      process: 'locked',
    });
    expect(result.nextStep).toBe('sections');
    expect(result.projectStatus).toBe('surfaces');
  });

  it('moves to process when sections exist but are not processed', () => {
    const result = computeWorkflowStatus({
      ...base,
      designMeshId: 'd1',
      topoMeshId: 't1',
      sectionCount: 3,
      processStatus: 'idle',
    });
    expect(result.sectionCount).toBe(3);
    expect(result.sectionsDone).toBe(true);
    expect(result.steps).toEqual({
      surfaces: 'done',
      sections: 'done',
      parameters: 'done',
      process: 'current',
    });
    expect(result.nextStep).toBe('process');
    expect(result.projectStatus).toBe('ready');
  });

  it('reports processing while the pipeline runs', () => {
    const result = computeWorkflowStatus({
      ...base,
      designMeshId: 'd1',
      topoMeshId: 't1',
      sectionCount: 3,
      processStatus: 'processing',
    });
    expect(result.isProcessing).toBe(true);
    expect(result.isComplete).toBe(false);
    expect(result.steps.process).toBe('current');
    expect(result.nextStep).toBe('process');
    expect(result.projectStatus).toBe('processing');
  });

  it('marks every step done when processing is complete', () => {
    const result = computeWorkflowStatus({
      ...base,
      designMeshId: 'd1',
      topoMeshId: 't1',
      sectionCount: 3,
      processStatus: 'complete',
    });
    expect(result.isComplete).toBe(true);
    expect(result.steps).toEqual({
      surfaces: 'done',
      sections: 'done',
      parameters: 'done',
      process: 'done',
    });
    expect(result.nextStep).toBeNull();
    expect(result.projectStatus).toBe('complete');
  });
});
