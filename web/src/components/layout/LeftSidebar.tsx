import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { DropZone } from '../mesh/MeshUpload';
import { TryDemoButton } from '../demo/TryDemoButton';
import { SectionCurveForm } from '../sections/SectionCurveForm';
import { SectionFileUpload } from '../sections/SectionFileUpload';
import { SectionList } from '../sections/SectionList';
import { ProcessButton } from '../analysis/ProcessButton';
import { ProcessProgress } from '../analysis/ProcessProgress';
import {
  useSettings,
  useUpdateSettings,
  useProcessStatus,
} from '../../api/hooks';
import type { ProcessSettings, Tolerances } from '../../api/types';
import { DEFAULT_SETTINGS } from '../../utils/constants';
import { Button } from '../ui/Button';
import { ProjectField, PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import { IconMesh, IconSections, IconSettings, IconLightning } from '../ui/Icons';
import { useSidebarResize } from './useSidebarResize';
import { TolerancesForm } from './TolerancesForm';
import { ViewsToolbar } from './ViewsToolbar';
import { LanguageToggle } from './LanguageToggle';


type SectionTab = 'curves' | 'file';

type AccordionKey = 'mallas' | 'secciones' | 'tolerancias' | 'procesamiento';

// Process-parameter input config. Drives the map-driven render in the
// "Parámetros de Proceso" section of the sidebar.
const PROCESS_FIELDS = [
  { key: 'resolution',     labelKey: 'sidebar.resolution',     step: 0.1, min: 0.1, max: undefined, fallback: 0.1 },
  { key: 'face_threshold', labelKey: 'sidebar.face_threshold', step: 1,   min: 1,   max: 90,        fallback: 40 },
  { key: 'berm_threshold', labelKey: 'sidebar.berm_threshold', step: 1,   min: 1,   max: 90,        fallback: 20 },
] as const;

interface AccordionItemProps {
  id: AccordionKey;
  title: string;
  icon: React.ReactNode;
  openSection: AccordionKey | '';
  toggle: (id: AccordionKey) => void;
  children: React.ReactNode;
}

function AccordionItem({ id, title, icon, openSection, toggle, children }: AccordionItemProps) {
  const isOpen = openSection === id;
  const index = ['mallas', 'secciones', 'tolerancias', 'procesamiento'].indexOf(id);
  return (
    <div className="contents">
      <button
        onClick={() => toggle(id)}
        aria-expanded={isOpen}
        aria-controls={`project-panel-${id}`}
        className="flex h-9 min-w-0 items-center rounded-md border border-border px-2 text-xs font-medium transition-colors hover:bg-surface-muted"
        style={{
          gridRow: Math.floor(index / 2) + 1,
          gridColumn: index % 2 + 1,
          backgroundColor: isOpen ? 'var(--color-accent-bg)' : 'transparent',
          color: isOpen ? 'var(--color-accent-bright)' : 'var(--color-text-secondary)',
        }}
      >
        <span className="flex min-w-0 items-center gap-1.5">{icon}<span className="truncate">{title}</span></span>
      </button>
      {isOpen && <div id={`project-panel-${id}`} className="col-span-2 row-start-3 overflow-hidden rounded-lg border border-border">{children}</div>}
    </div>
  );
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

  const bothUploaded = !!designMeshId && !!topoMeshId;

  // Accordion open states
  const [openSection, setOpenSection] = useState<'mallas' | 'secciones' | 'tolerancias' | 'procesamiento' | ''>('mallas');

  // Section definition tab state
  const [sectionTab, setSectionTab] = useState<SectionTab>('curves');

  useEffect(() => {
    if (window.matchMedia('(max-width: 767px)').matches) setSidebarCollapsed(true);
  }, [setSidebarCollapsed]);

  const handleNavigate = () => {
    setOpenSection('');
    if (window.matchMedia('(max-width: 767px)').matches) setSidebarCollapsed(true);
  };

  // Sidebar resize (mouse drag + localStorage persistence)
  const { sidebarWidth, startResizing, isResizing } = useSidebarResize();

  // Settings state & mutations
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();
  const { data: status } = useProcessStatus();
  const isProcessing = status?.status === 'processing';

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
      tolerances: settings.tolerances,
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

  // Auto-switch to 3D View when clicking to place sections
  useEffect(() => {
    if (openSection === 'secciones' && sectionTab === 'curves') {
      setActiveWorkspaceView('3d');
    }
  }, [openSection, sectionTab, setActiveWorkspaceView]);

  // Auto-switch to 3D View when a mesh upload completes. Previously
  // this effect fired whenever `designMeshId`/`topoMeshId` changed
  // identity, which also happens on first render and on store
  // hydration — yanking the user back to 3D even if they were reading
  // the Dashboard. Now it only runs once, when both meshes are present
  // for the first time in this session.
  const didAutoSwitchTo3D = useRef(false);
  useEffect(() => {
    if (!didAutoSwitchTo3D.current && designMeshId && topoMeshId) {
      didAutoSwitchTo3D.current = true;
      setActiveWorkspaceView('3d');
      setOpenSection((current) => current === 'mallas' ? '' : current);
    }
  }, [designMeshId, topoMeshId, setActiveWorkspaceView]);

  const toggleAccordion = (section: 'mallas' | 'secciones' | 'tolerancias' | 'procesamiento') => {
    setOpenSection(openSection === section ? '' : section);
  };

  // Persist a single tolerance field (debounced through saveSettings).
  const handleToleranceChange = <K extends keyof Tolerances>(
    key: K,
    partial: Partial<Tolerances[K]>,
  ) => {
    if (!settings) return;
    saveSettings({
      process: processSettings,
      tolerances: {
        ...settings.tolerances,
        [key]: { ...settings.tolerances[key], ...partial },
      },
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
          onClick={() => setSidebarCollapsed(false)}
          className="w-8 h-8 rounded-md flex items-center justify-center border hover:bg-surface-muted transition-colors cursor-pointer text-xs mb-6"
          style={{ borderColor: 'var(--color-border)' }}
          title={t('sidebar.expand', { defaultValue: 'Expandir Panel' })}
          aria-label={t('sidebar.expand', { defaultValue: 'Expandir Panel' })}
        >
          ▶
        </button>

        <div className="flex flex-col gap-6 items-center opacity-50 mt-4">
          <button type="button" aria-label={t('sidebar.mallas', { defaultValue: 'Mallas' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.mallas', { defaultValue: 'Mallas' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('mallas'); }}><IconMesh className="w-4 h-4" /></button>
          <button type="button" aria-label={t('sidebar.secciones', { defaultValue: 'Secciones' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.secciones', { defaultValue: 'Secciones' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('secciones'); }}><IconSections className="w-4 h-4" /></button>
          <button type="button" aria-label={t('sidebar.tolerancias', { defaultValue: 'Parámetros' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.tolerancias', { defaultValue: 'Parámetros' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('tolerancias'); }}><IconSettings className="w-5 h-5" /></button>
          <button type="button" aria-label={t('sidebar.procesamiento', { defaultValue: 'Procesar' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.procesamiento', { defaultValue: 'Procesar' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('procesamiento'); }}><IconLightning className="w-5 h-5" /></button>
        </div>
        <div className="mt-6 w-full px-1"><ViewsToolbar compact onNavigate={handleNavigate} /></div>
        <div className="mt-auto flex flex-col items-center gap-2 py-4 md:hidden">
          <LanguageToggle />
        </div>
      </aside>
    );
  }

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
      {/* Sidebar header */}
      <div
        data-slot="project-heading"
        className="flex items-center justify-between p-4 border-b shrink-0"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <h3
          className="text-sm font-semibold"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('workspace.project')}
        </h3>
        <button
          onClick={() => setSidebarCollapsed(true)}
          className="w-6 h-6 rounded flex items-center justify-center border text-[9px] hover:bg-surface-muted transition-colors cursor-pointer"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          title={t('sidebar.collapse', { defaultValue: 'Contraer Panel' })}
          aria-label={t('sidebar.collapse', { defaultValue: 'Contraer Panel' })}
        >
          ◀
        </button>
      </div>

      {/* Accordions container */}
      <div className="grid min-h-0 grid-cols-2 auto-rows-min content-start gap-2 overflow-y-auto p-2" data-slot="project-controls">
        <AccordionItem id="mallas" title={t('workspace.surfaces')} icon={<IconMesh className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-2 space-y-2 bg-surface-sunken">
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
        </AccordionItem>

        <AccordionItem id="secciones" title={t('workspace.sections')} icon={<IconSections className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-2 space-y-1.5 bg-surface-sunken">
            {!bothUploaded ? (
              <div className="p-2 rounded-md border border-dashed text-center" style={{ borderColor: 'var(--status-nok-border)', backgroundColor: 'var(--status-nok-bg)' }}>
                <p className="text-xs font-medium" style={{ color: 'var(--status-nok-text)' }}>
                  {t('plan_view_no_data', { defaultValue: 'Cargue superficies primero para definir secciones' })}
                </p>
              </div>
            ) : (
              <>
                {/* Step 2 Form tabs */}
                <div className="grid grid-cols-2 gap-1 rounded-md shrink-0" style={{ backgroundColor: 'var(--color-surface)' }}>
                  {(['curves', 'file'] as SectionTab[]).map((tab) => (
                    <button
                      key={tab}
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

                {/* Selected form */}
                <div className="min-w-0">
                  {sectionTab === 'curves' && (
                    <SectionCurveForm onRegisterClickHandler={setMapClickHandler} />
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
        </AccordionItem>

        <AccordionItem id="tolerancias" title={t('workspace.parameters')} icon={<IconSettings className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-2 space-y-2 bg-surface-sunken">
              {/* Process parameters */}
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

              {/* Tolerances */}
              {settings && (
                <TolerancesForm
                  tolerances={settings.tolerances}
                  onChange={handleToleranceChange}
                />
              )}
            </div>
        </AccordionItem>

        <AccordionItem id="procesamiento" title={t('project_input.process')} icon={<IconLightning className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-2 bg-surface-sunken flex flex-col gap-2">
            <ProcessButton />
            <ProcessProgress />
          </div>
        </AccordionItem>
      </div>
      <div className="shrink-0 border-t border-border p-2"><ViewsToolbar onNavigate={handleNavigate} /></div>

      {/* Resize Handle */}
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
