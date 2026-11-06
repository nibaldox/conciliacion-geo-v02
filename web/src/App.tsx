import { applyTheme } from './utils/theme';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { AppLayout } from './components/layout/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useHotkeys } from './hooks/useHotkeys';
import { DEMO_MESH_IDS, useSession } from './stores/session';
import { useTheme } from './stores/theme';
import { useSections } from './api/hooks';
import { useWorkflowStatus } from './hooks/useWorkflowStatus';

// Workspace Views
import {
  LazyMesh3DViewer,
  LazyResultsTable,
  LazyDashboard,
  LazyBlastWorkspace,
  LazyAIReporter,
  LazyProfileView,
  LazyProfilesGrid,
} from './components/lazy';
import { SectionSelector } from './components/results/SectionSelector';
import { IconGrid, IconList, IconPlay, IconSections, IconUpload } from './components/ui/Icons';
import { EmptyState, type EmptyStateProps } from './components/ui/EmptyState';
import { useStartDemo } from './components/demo/TryDemoButton';

import { ExportPanel } from './components/export/ExportPanel';

function WorkspaceEmptyState(props: EmptyStateProps) {
  return (
    <div className="flex h-full w-full items-center justify-center p-6">
      <EmptyState {...props} />
    </div>
  );
}

// ─── Profiles workspace (grid ↔ detail toggle) ─────────────

function ProfilesWorkspace() {
  const { t } = useTranslation();
  const setSelectedSection = useSession((s) => s.setSelectedSection);
  const mode = useSession((s) => s.profilesMode);
  const setMode = useSession((s) => s.setProfilesMode);

  const handleGridSelect = (id: string) => {
    setSelectedSection(id);
    setMode('detail');
  };

  const modes = [
    { key: 'grid', icon: IconGrid, label: t('profiles.mode_grid', { defaultValue: 'Grilla' }) },
    { key: 'detail', icon: IconList, label: t('profiles.mode_detail', { defaultValue: 'Detalle' }) },
  ] as const;

  return (
    <div className="flex flex-col gap-4 min-h-0">
      <div className="shrink-0 flex flex-wrap items-center justify-end gap-2">
        <div className="mr-auto w-full min-w-0 md:w-auto md:min-w-80 md:flex-1 md:max-w-2xl">{mode === 'detail' && <SectionSelector />}</div>
        <div data-slot="profiles-mode-toggle" role="group" aria-label={t('ux.profiles_mode')} className="inline-flex shrink-0 items-center gap-0.5 rounded-lg border border-border bg-surface-muted p-0.5">
          {modes.map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              aria-pressed={mode === key}
              className={[
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                mode === key ? 'bg-surface-raised text-text-primary shadow-sm' : 'text-text-secondary hover:text-text-primary',
              ].join(' ')}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" /> {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {mode === 'grid' ? (
        <div className="flex-1 overflow-y-auto min-h-0">
          <Suspense fallback={<LoadingSpinner />}>
            <LazyProfilesGrid onSectionSelect={handleGridSelect} />
          </Suspense>
        </div>
      ) : (
        <div className="space-y-3 flex-1 flex flex-col min-h-0">
          <div className="flex-1 min-h-0">
            <Suspense fallback={<LoadingSpinner />}>
              <LazyProfileView />
            </Suspense>
          </div>
        </div>
      )}
    </div>
  );
}



function WorkspaceRouter() {
  const activeWorkspaceView = useSession((s) => s.activeWorkspaceView);
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const isVirtualDemoSession = designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo;
  const { data: sections } = useSections();
  const { isComplete } = useWorkflowStatus();
  const wasComplete = useRef(false);
  const setSidebarCollapsed = useSession((s) => s.setSidebarCollapsed);
  const setOpenWorkflowStep = useSession((s) => s.setOpenWorkflowStep);
  const setActiveWorkspaceView = useSession((s) => s.setActiveWorkspaceView);
  const demoMode = useSession((s) => s.demoMode);
  const startDemo = useStartDemo();
  const { t } = useTranslation();

  const openStep = (step: 'surfaces' | 'sections' | 'process') => {
    setSidebarCollapsed(false);
    setOpenWorkflowStep(step);
  };

  const bothUploaded = !!designMeshId && !!topoMeshId;
  const hasSections = sections && sections.length > 0;
  useEffect(() => {
    if (isComplete && !wasComplete.current && useSession.getState().activeWorkspaceView === '3d') {
      setActiveWorkspaceView('dashboard');
    }
    wasComplete.current = isComplete;
  }, [isComplete, setActiveWorkspaceView]);

  if (!bothUploaded && activeWorkspaceView !== '3d') {
    return (
      <WorkspaceEmptyState
        data-slot="empty-no-mesh"
        icon={<IconUpload className="h-7 w-7" />}
        title={t('ux.empty_mesh_title')}
        description={t('ux.empty_mesh_desc')}
        primaryAction={{ label: t('ux.empty_mesh_cta'), onClick: () => openStep('surfaces') }}
        secondaryAction={demoMode ? undefined : { label: t('ux.empty_demo_cta'), onClick: () => { void startDemo(); } }}
      />
    );
  }

  if (bothUploaded && !hasSections && !(isVirtualDemoSession && activeWorkspaceView === 'export-ai') && (activeWorkspaceView === 'profiles' || activeWorkspaceView === 'dashboard' || activeWorkspaceView === 'blast' || activeWorkspaceView === 'export-ai')) {
    return (
      <WorkspaceEmptyState
        data-slot="empty-no-sections"
        icon={<IconSections className="h-7 w-7" />}
        title={t('ux.empty_sections_title')}
        description={t('ux.empty_sections_desc')}
        primaryAction={{ label: t('ux.empty_sections_cta'), onClick: () => { openStep('sections'); setActiveWorkspaceView('3d'); } }}
      />
    );
  }

  if (bothUploaded && hasSections && !isComplete && !(isVirtualDemoSession && activeWorkspaceView === 'export-ai') && (activeWorkspaceView === 'profiles' || activeWorkspaceView === 'dashboard' || activeWorkspaceView === 'blast' || activeWorkspaceView === 'export-ai')) {
    return (
      <WorkspaceEmptyState
        data-slot="empty-no-process"
        icon={<IconPlay className="h-7 w-7" />}
        title={t('ux.empty_process_title')}
        description={t('ux.empty_process_desc')}
        primaryAction={{ label: t('ux.empty_process_cta'), onClick: () => openStep('process') }}
      />
    );
  }

  switch (activeWorkspaceView) {
    case '3d':
      return <LazyMesh3DViewer />;
    case 'profiles':
      return <ProfilesWorkspace />;

    case 'dashboard':
      return (
        <div className="h-full flex flex-col gap-6 overflow-y-auto pr-1">
          <div className="shrink-0">
            <LazyDashboard />
          </div>
          <section data-slot="detail-table" className="min-w-0 shrink-0 space-y-3 pb-2">
            <h3 className="ui-section-title">{t('ux.detail_table')}</h3>
            <LazyResultsTable />
          </section>
        </div>
      );
    case 'blast':
      return (
        <div className="flex min-h-0 flex-1 flex-col">
          <LazyBlastWorkspace />
        </div>
      );
    case 'export-ai':
      return (
        <div data-slot="export-workspace" className="h-full flex flex-col gap-5 overflow-y-auto pb-4">
          <ExportPanel />
          {!isVirtualDemoSession && <LazyAIReporter />}
        </div>
      );
    default:
      return null;
  }
}

function LoadingSpinner() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent" />
      <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
        {t('common.loading', { defaultValue: 'Cargando…' })}
      </span>
    </div>
  );
}

function App({ sessionRestoreFailed = false }: { sessionRestoreFailed?: boolean }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  }));

  const { isDark } = useTheme();
  const { i18n } = useTranslation();
  const setActiveWorkspaceView = useSession((s) => s.setActiveWorkspaceView);

  // Workspace view hotkeys
  useHotkeys(['1', '2', '3', '4', '5'], (e) => {
    const target = e.key;
    if (target === '1') setActiveWorkspaceView('dashboard');
    if (target === '2') setActiveWorkspaceView('profiles');
    if (target === '3') setActiveWorkspaceView('3d');
    if (target === '4') setActiveWorkspaceView('blast');
    if (target === '5') setActiveWorkspaceView('export-ai');
  });

  // Apply dark class to root element
  useEffect(() => {
    applyTheme(isDark);
  }, [isDark]);

  // Sync <html lang> with i18n language
  useEffect(() => {
    const handler = (lng: string) => {
      document.documentElement.lang = lng.startsWith('es') ? 'es' : 'en';
    };
    handler(i18n.language);
    i18n.on('languageChanged', handler);
    return () => i18n.off('languageChanged', handler);
  }, [i18n]);

  return (
    <QueryClientProvider client={queryClient}>
      <AppLayout>
        {sessionRestoreFailed && (
          <div role="alert" className="mx-4 mt-3 rounded-lg border p-3 text-sm" style={{ borderColor: 'var(--color-status-error)', color: 'var(--color-status-error)' }}>
            {i18n.t('sessionRecovery.failed')}
          </div>
        )}
        <ErrorBoundary>
          <Suspense fallback={<LoadingSpinner />}>
            <WorkspaceRouter />
          </Suspense>
        </ErrorBoundary>
      </AppLayout>
    </QueryClientProvider>
  );
}

export default App;
