import { useState, useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useSession, type WorkflowStepKey } from '../../stores/session';
import { DropZone } from '../mesh/MeshUpload';
import { TryDemoButton } from '../demo/TryDemoButton';
import { SectionCurveForm } from '../sections/SectionCurveForm';
import { SectionFileUpload } from '../sections/SectionFileUpload';
import { SectionList } from '../sections/SectionList';
import { ProcessButton } from '../analysis/ProcessButton';
import { ProcessProgress } from '../analysis/ProcessProgress';
import { useSettings, useUpdateSettings } from '../../api/hooks';
import type { ProcessSettings, Tolerances } from '../../api/types';
import { DEFAULT_SETTINGS } from '../../utils/constants';
import { Button } from '../ui/Button';
import { ProjectField, PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import { StepperItem, type StepperItemStatus } from '../ui/StepperItem';
import { IconCheck, IconLock } from '../ui/Icons';
import { useWorkflowStatus, type WorkflowStatus } from '../../hooks/useWorkflowStatus';
import { useSidebarResize } from './useSidebarResize';
import { TolerancesForm, mergeTolerance } from './TolerancesForm';
import { LanguageToggle } from './LanguageToggle';

type SectionTab = 'curves' | 'file';

const PROCESS_FIELDS = [
  { key: 'resolution',     labelKey: 'sidebar.resolution',     step: 0.1, min: 0.1, max: undefined, fallback: 0.1 },
  { key: 'face_threshold', labelKey: 'sidebar.face_threshold', step: 1,   min: 1,   max: 90,        fallback: 40 },
  { key: 'berm_threshold', labelKey: 'sidebar.berm_threshold', step: 1,   min: 1,   max: 90,        fallback: 20 },
] as const;

const STEP_ORDER: readonly WorkflowStepKey[] = ['surfaces', 'sections', 'parameters', 'process'];

const STEP_TITLE_KEYS: Record<WorkflowStepKey, string> = {
  surfaces: 'ux.step_surfaces',
  sections: 'ux.step_sections',
  parameters: 'ux.step_parameters',
  process: 'ux.step_process',
};

const COLLAPSED_CIRCLE_CLASSES: Record<StepperItemStatus, string> = {
  done: 'bg-mine-green text-white',
  current: 'bg-accent text-accent-fg',
  pending: 'bg-surface-muted text-text-muted',
  locked: 'bg-surface-muted text-text-dim',
};

function workflowStepDomId(key: WorkflowStepKey): string {
  return `workflow-step-${key}`;
}

function stepSummary(key: WorkflowStepKey, workflow: WorkflowStatus, t: TFunction): string {
  switch (key) {
    case 'surfaces':
      if (workflow.surfacesDone) return t('ux.summary_surfaces_done');
      if (workflow.hasDesign || workflow.hasTopo) return t('ux.summary_surfaces_partial');
      return t('ux.summary_surfaces_none');
    case 'sections':
      return workflow.sectionCount > 0
        ? t('ux.summary_sections', { count: workflow.sectionCount })
        : t('ux.summary_sections_none');
    case 'parameters':
      return t('ux.summary_parameters');
    case 'process':
      if (workflow.isComplete) return t('ux.summary_process_done');
      if (workflow.isProcessing) return t('ux.summary_process_running');
      if (workflow.steps.process === 'locked') return t('ux.summary_process_blocked');
      return t('ux.summary_process_ready');
  }
}

export function LeftSidebar() {
  const { t } = useTranslation();
  const sidebarCollapsed = useSession((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useSession((s) => s.setSidebarCollapsed);
  const setActiveWorkspaceView = useSession((s) => s.setActiveWorkspaceView);
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const setDesignMeshId = useSession((s) => s.setDesignMeshId);
  const setTopoMeshId = useSession((s) => s.setTopoMeshId);
  const setMapClickHandler = useSession((s) => s.setMapClickHandler);
  const openWorkflowStep = useSession((s) => s.openWorkflowStep);
  const setOpenWorkflowStep = useSession((s) => s.setOpenWorkflowStep);

  const workflow = useWorkflowStatus();
  const { steps, nextStep, isProcessing } = workflow;
  const bothUploaded = !!designMeshId && !!topoMeshId;

  const [sectionTab, setSectionTab] = useState<SectionTab>('curves');

  useEffect(() => {
    if (window.matchMedia('(max-width: 767px)').matches) setSidebarCollapsed(true);
  }, [setSidebarCollapsed]);

  const { sidebarWidth, startResizing, isResizing } = useSidebarResize();

  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();

  const [tolerancesDraft, setTolerancesDraft] = useState<Tolerances | null>(null);
  const tolerancesDraftRef = useRef<Tolerances | null>(null);

  const [processSettings, setProcessSettings] = useState<ProcessSettings>({
    resolution: DEFAULT_SETTINGS.resolution,
    face_threshold: DEFAULT_SETTINGS.face_threshold,
    berm_threshold: DEFAULT_SETTINGS.berm_threshold,
  });

  useEffect(() => {
    if (settings?.process) {
      setProcessSettings(settings.process);
    }
  }, [settings]);

  const handleProcessChange = <K extends keyof ProcessSettings>(key: K, value: number) => {
    setProcessSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveSettings = () => {
    if (!settings) return;
    updateSettings.mutate({
      process: processSettings,
      tolerances: tolerancesDraftRef.current ?? settings.tolerances,
    });
  };

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveSettings = (payload: Parameters<typeof updateSettings.mutate>[0]) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      updateSettings.mutate(payload);
    }, 400);
  };

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (openWorkflowStep === 'sections' && sectionTab === 'curves') {
      setActiveWorkspaceView('3d');
    }
  }, [openWorkflowStep, sectionTab, setActiveWorkspaceView]);

  const didAutoSwitchTo3D = useRef(false);
  useEffect(() => {
    if (!didAutoSwitchTo3D.current && designMeshId && topoMeshId) {
      didAutoSwitchTo3D.current = true;
      setActiveWorkspaceView('3d');
    }
  }, [designMeshId, topoMeshId, setActiveWorkspaceView]);

  const previousStepsRef = useRef(steps);
  useEffect(() => {
    const previous = previousStepsRef.current;
    previousStepsRef.current = steps;
    if (previous === steps) return;
    const becameDone = STEP_ORDER.some((key) => steps[key] === 'done' && previous[key] !== 'done');
    if (becameDone) setOpenWorkflowStep(nextStep);
  }, [steps, nextStep, setOpenWorkflowStep]);

  const toggleStep = (key: WorkflowStepKey) => {
    setOpenWorkflowStep(openWorkflowStep === key ? null : key);
  };

  const handleToleranceChange = <K extends keyof Tolerances>(
    key: K,
    partial: Partial<Tolerances[K]>,
  ) => {
    if (!settings) return;
    const base = tolerancesDraftRef.current ?? settings.tolerances;
    const merged = mergeTolerance(base, key, partial);
    tolerancesDraftRef.current = merged;
    setTolerancesDraft(merged);
    saveSettings({
      process: processSettings,
      tolerances: merged,
    });
  };

  if (sidebarCollapsed) {
    return (
      <aside
        data-slot="left-sidebar-collapsed"
        className="w-14 h-full flex flex-col items-center overflow-y-auto py-3 border-r shrink-0 select-none"
        style={{
          backgroundColor: 'var(--color-surface-raised)',
          borderColor: 'var(--color-border)',
        }}
      >
        <button
          type="button"
          onClick={() => setSidebarCollapsed(false)}
          className="w-8 h-8 rounded-md flex items-center justify-center hover:bg-surface-muted transition-colors cursor-pointer text-xs mb-4 text-text-muted"
          title={t('sidebar.expand', { defaultValue: 'Expandir panel' })}
          aria-label={t('sidebar.expand', { defaultValue: 'Expandir panel' })}
        >
          ▶
        </button>

        <ol className="flex flex-col items-center gap-3" aria-label={t('ux.workflow')}>
          {STEP_ORDER.map((key, i) => {
            const status = steps[key];
            const title = t(STEP_TITLE_KEYS[key]);
            return (
              <li key={key}>
                <button
                  type="button"
                  data-state={status}
                  aria-label={title}
                  title={status === 'locked' ? `${title} — ${t('ux.locked_hint')}` : title}
                  onClick={() => {
                    setSidebarCollapsed(false);
                    if (status !== 'locked') setOpenWorkflowStep(key);
                  }}
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold transition-opacity hover:opacity-80 cursor-pointer ${COLLAPSED_CIRCLE_CLASSES[status]}`}
                >
                  {status === 'done' && <IconCheck width={14} height={14} strokeWidth={3} aria-hidden="true" />}
                  {status === 'locked' && <IconLock width={12} height={12} aria-hidden="true" />}
                  {status !== 'done' && status !== 'locked' && <span>{i + 1}</span>}
                </button>
              </li>
            );
          })}
        </ol>
        <div className="mt-auto flex flex-col items-center gap-2 py-4 md:hidden">
          <LanguageToggle />
        </div>
      </aside>
    );
  }

  const stepContent: Record<WorkflowStepKey, ReactNode> = {
    surfaces: (
      <div className="space-y-2">
        <div className="space-y-2">
          <DropZone compact type="design" meshId={designMeshId} onSetMeshId={setDesignMeshId} />
          <DropZone compact type="topo" meshId={topoMeshId} onSetMeshId={setTopoMeshId} />
        </div>
        <p className="px-1 text-xs text-text-muted">{t('step1.file_types')}</p>
        {!bothUploaded && (
          <div>
            <TryDemoButton compact />
          </div>
        )}
      </div>
    ),
    sections: (
      <div className="space-y-1.5">
        {!bothUploaded ? (
          <div className="p-2 rounded-md border border-dashed text-center" style={{ borderColor: 'var(--status-nok-border)', backgroundColor: 'var(--status-nok-bg)' }}>
            <p className="text-xs font-medium" style={{ color: 'var(--status-nok-text)' }}>
              {t('sidebar.no_surfaces_for_sections', { defaultValue: 'Cargue superficies primero para definir secciones' })}
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-1 rounded-md shrink-0" style={{ backgroundColor: 'var(--color-surface)' }}>
              {(['curves', 'file'] as SectionTab[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setSectionTab(tab)}
                  className="h-8 text-xs font-medium rounded-md transition-colors"
                  aria-pressed={sectionTab === tab}
                  style={{
                    backgroundColor: sectionTab === tab ? 'var(--color-accent-bg)' : 'transparent',
                    color: sectionTab === tab ? 'var(--color-accent-bright)' : 'var(--color-text-muted)',
                  }}
                >
                  {t(tab === 'curves' ? 'workspace.curves' : 'workspace.file')}
                </button>
              ))}
            </div>

            <div className="min-w-0">
              {sectionTab === 'curves' && (
                <>
                  <p role="note" className="rounded-md border border-border bg-surface-raised px-2 py-1.5 text-xs text-text-secondary">
                    {t('workspace.curve_view_hint', { defaultValue: 'La vista 3D se activa automáticamente. Elige una curva en la superficie para definir la sección.' })}
                  </p>
                  <SectionCurveForm onRegisterClickHandler={setMapClickHandler} />
                </>
              )}
              {sectionTab === 'file' && <SectionFileUpload />}
            </div>

            <details className="rounded-md border border-border bg-surface-raised px-2 py-1">
              <summary className="cursor-pointer text-xs font-medium text-text-secondary">{t('step2.existing_sections')}</summary>
              <div className="mt-2 max-h-48 overflow-auto"><SectionList compact /></div>
            </details>
          </>
        )}
      </div>
    ),
    parameters: (
      <div className="space-y-2">
        <section className="space-y-2 border-b pb-2" style={{ borderColor: 'var(--color-border)' }}>
          <h4 className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
            {t('sidebar.process_title')}
          </h4>
          <div className="grid grid-cols-3 gap-2">
            {PROCESS_FIELDS.map((f) => (
              <ProjectField key={f.key} id={`process-${f.key}`} label={t('project_input.' + f.key)} title={t(f.labelKey)}>
                <input id={`process-${f.key}`} type="number" step={f.step} min={f.min} max={f.max}
                  value={processSettings[f.key]}
                  onChange={(e) => handleProcessChange(f.key, parseFloat(e.target.value) || f.fallback)}
                  className={PROJECT_INPUT_CLASS} disabled={isProcessing} />
              </ProjectField>
            ))}
            <Button
              variant="secondary"
              className="col-span-3 min-h-8"
              onClick={handleSaveSettings}
              disabled={isProcessing || updateSettings.isPending}
              loading={updateSettings.isPending}
              fullWidth
              size="sm"
            >
              {updateSettings.isPending ? t('common.loading') : t('step3.save')}
            </Button>
          </div>
        </section>

        {settings && (
          <TolerancesForm
            tolerances={tolerancesDraft ?? settings.tolerances}
            onChange={handleToleranceChange}
          />
        )}
      </div>
    ),
    process: (
      <div className="flex flex-col gap-2">
        <ProcessButton />
        <ProcessProgress />
      </div>
    ),
  };

  return (
    <aside
      data-slot="left-sidebar"
      className="project-sidebar relative h-full flex flex-col border-r shrink-0 select-none overflow-hidden"
      style={{
        width: sidebarWidth,
        backgroundColor: 'var(--color-surface-raised)',
        borderColor: 'var(--color-border)',
      }}
    >
      <div
        data-slot="project-heading"
        className="flex items-center justify-between px-4 pt-4 pb-2 shrink-0"
      >
        <h3 className="ui-section-title">{t('ux.workflow')}</h3>
        <button
          type="button"
          onClick={() => setSidebarCollapsed(true)}
          className="w-6 h-6 rounded-md flex items-center justify-center text-[9px] text-text-muted hover:bg-surface-muted transition-colors cursor-pointer"
          title={t('sidebar.collapse', { defaultValue: 'Contraer Panel' })}
          aria-label={t('sidebar.collapse', { defaultValue: 'Contraer Panel' })}
        >
          ◀
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3" data-slot="project-controls">
        {STEP_ORDER.map((key, i) => {
          const status = steps[key];
          return (
            <div key={key} title={status === 'locked' ? t('ux.locked_hint') : undefined}>
              <StepperItem
                id={workflowStepDomId(key)}
                index={i + 1}
                title={t(STEP_TITLE_KEYS[key])}
                summary={stepSummary(key, workflow, t)}
                status={status}
                expanded={status !== 'locked' && openWorkflowStep === key}
                onToggle={() => toggleStep(key)}
                isLast={i === STEP_ORDER.length - 1}
              >
                {stepContent[key]}
              </StepperItem>
            </div>
          );
        })}
      </div>

      <div
        className="absolute top-0 right-0 w-1 h-full cursor-col-resize z-50 transition-colors"
        style={{ backgroundColor: isResizing ? 'var(--color-accent)' : 'transparent' }}
        onMouseDown={startResizing}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--color-accent)')}
        onMouseLeave={(e) => {
          if (!isResizing) e.currentTarget.style.backgroundColor = 'transparent';
        }}
        aria-hidden="true"
      />
    </aside>
  );
}
