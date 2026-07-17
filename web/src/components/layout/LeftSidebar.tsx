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
import { IconMesh, IconSections, IconSettings, IconLightning } from '../ui/Icons';
import { useSidebarResize } from './useSidebarResize';
import { TolerancesForm } from './TolerancesForm';


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
  return (
    <div className="border rounded-lg overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
      <button
        onClick={() => toggle(id)}
        className="w-full flex items-center justify-between p-3 text-xs font-mono font-semibold uppercase tracking-wider transition-colors hover:bg-surface-muted"
        style={{
          backgroundColor: isOpen ? 'var(--color-surface-sunken)' : 'transparent',
          color: isOpen ? 'var(--color-accent-bright)' : 'var(--color-text-secondary)',
        }}
      >
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
        <span>{isOpen ? '▼' : '▶'}</span>
      </button>
      {isOpen && children}
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

  // Input styles
  const inputStyle = {
    backgroundColor: 'var(--color-surface-sunken)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-text-primary)',
  };

  const inputCls =
    "w-full px-3 py-1.5 border rounded-md text-xs outline-none transition-colors focus:ring-2 focus:ring-accent/30 font-mono";

  if (sidebarCollapsed) {
    return (
      <aside
        data-slot="left-sidebar-collapsed"
        className="w-12 h-full flex flex-col items-center py-4 border-r shrink-0 select-none"
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
          <button type="button" aria-label={t('sidebar.mallas', { defaultValue: 'Mallas' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.mallas', { defaultValue: 'Mallas' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('mallas'); }}><IconMesh className="w-5 h-5" /></button>
          <button type="button" aria-label={t('sidebar.secciones', { defaultValue: 'Secciones' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.secciones', { defaultValue: 'Secciones' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('secciones'); }}><IconSections className="w-5 h-5" /></button>
          <button type="button" aria-label={t('sidebar.tolerancias', { defaultValue: 'Parámetros' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.tolerancias', { defaultValue: 'Parámetros' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('tolerancias'); }}><IconSettings className="w-5 h-5" /></button>
          <button type="button" aria-label={t('sidebar.procesamiento', { defaultValue: 'Procesar' })} className="cursor-pointer transition-colors hover:text-accent" title={t('sidebar.procesamiento', { defaultValue: 'Procesar' })} onClick={() => { setSidebarCollapsed(false); setOpenSection('procesamiento'); }}><IconLightning className="w-5 h-5" /></button>
        </div>
      </aside>
    );
  }

  return (
    <aside
      data-slot="left-sidebar"
      className="relative h-full flex flex-col border-r shrink-0 select-none overflow-hidden"
      style={{
        width: sidebarWidth,
        backgroundColor: 'var(--color-surface-raised)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* Sidebar header */}
      <div
        className="flex items-center justify-between p-4 border-b shrink-0"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <h3
          className="text-xs uppercase tracking-widest font-mono font-bold"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          CONTROL PANEL
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
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        <AccordionItem id="mallas" title={t('step1.title')} icon={<IconMesh className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-3 space-y-3 bg-surface-sunken border-t border-border">
            <div className="space-y-3">
              <DropZone type="design" meshId={designMeshId} onSetMeshId={setDesignMeshId} />
              <DropZone type="topo" meshId={topoMeshId} onSetMeshId={setTopoMeshId} />
            </div>
            {!bothUploaded && (
              <div className="pt-2 text-center">
                <TryDemoButton />
              </div>
            )}
          </div>
        </AccordionItem>

        <AccordionItem id="secciones" title={t('step2.title', { defaultValue: 'Líneas de Sección' })} icon={<IconSections className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-3 space-y-4 bg-surface-sunken border-t border-border">
            {!bothUploaded ? (
              <div className="p-4 rounded border border-dashed text-center" style={{ borderColor: 'var(--status-nok-border)', backgroundColor: 'var(--status-nok-bg)' }}>
                <p className="text-xs font-medium" style={{ color: 'var(--status-nok-text)' }}>
                  {t('plan_view_no_data', { defaultValue: 'Cargue superficies primero para definir secciones' })}
                </p>
              </div>
            ) : (
              <>
                {/* Step 2 Form tabs */}
                <div className="grid grid-cols-2 gap-1 p-1 rounded-lg shrink-0" style={{ backgroundColor: 'var(--color-surface)' }}>
                  {(['curves', 'file'] as SectionTab[]).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setSectionTab(tab)}
                      className="py-1 text-[9px] uppercase tracking-wider font-semibold rounded transition-all"
                      style={{
                        backgroundColor: sectionTab === tab ? 'var(--color-accent-bg)' : 'transparent',
                        color: sectionTab === tab ? 'var(--color-accent-bright)' : 'var(--color-text-muted)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {tab === 'curves' ? 'Por Curvas' : 'Archivo'}
                    </button>
                  ))}
                </div>

                {/* Selected form */}
                <div className="p-2 border rounded" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-raised)' }}>
                  {sectionTab === 'curves' && (
                    <SectionCurveForm onRegisterClickHandler={setMapClickHandler} />
                  )}
                  {sectionTab === 'file' && <SectionFileUpload />}
                </div>

                {/* List of sections */}
                <div>
                  <h4 className="text-[10px] uppercase tracking-widest font-mono font-bold mb-1" style={{ color: 'var(--color-text-muted)' }}>
                    {t('step2.existing_sections', { defaultValue: 'Secciones Existentes' })}
                  </h4>
                  <div className="max-h-48 overflow-y-auto border rounded" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}>
                    <SectionList />
                  </div>
                </div>
              </>
            )}
          </div>
        </AccordionItem>

        <AccordionItem id="tolerancias" title={t('step3.settings_title', { defaultValue: 'Tolerancias y Parámetros' })} icon={<IconSettings className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-3 space-y-4 bg-surface-sunken border-t border-border">
              {/* Process parameters */}
              <section className="space-y-3 border-b pb-3" style={{ borderColor: 'var(--color-border)' }}>
                <h4 className="text-[10px] uppercase tracking-widest font-mono font-bold" style={{ color: 'var(--color-text-secondary)' }}>
                  {t('sidebar.process_title')}
                </h4>
                <div className="grid grid-cols-1 gap-2.5">
                  {PROCESS_FIELDS.map((f) => (
                    <div key={f.key}>
                      <label className="block text-[10px] uppercase font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        {t(f.labelKey)}
                      </label>
                      <input
                        type="number"
                        step={f.step}
                        min={f.min}
                        max={f.max}
                        value={processSettings[f.key]}
                        onChange={(e) => handleProcessChange(f.key, parseFloat(e.target.value) || f.fallback)}
                        className={inputCls}
                        style={inputStyle}
                        disabled={isProcessing}
                      />
                    </div>
                  ))}
                  <Button
                    variant="terminal"
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

        <AccordionItem id="procesamiento" title={t('step3.title')} icon={<IconLightning className="w-4 h-4" />} openSection={openSection} toggle={toggleAccordion}>
          <div className="p-3 bg-surface-sunken border-t border-border flex flex-col items-center gap-3">
            <ProcessButton />
            <ProcessProgress />
          </div>
        </AccordionItem>
      </div>

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