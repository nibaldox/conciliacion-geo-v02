import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { AppLayout } from './components/layout/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useHotkeys } from './hooks/useHotkeys';
import { useSession } from './stores/session';
import { useTheme } from './stores/theme';
import { useSections, useProcessStatus } from './api/hooks';

// Workspace Views
import {
  LazyMesh3DViewer,
  LazyResultsTable,
  LazyDashboard,
  LazyBlastCorrelation,
  LazyAIReporter,
  LazyProfileView,
  LazyProfilesGrid,
} from './components/lazy';
import { SectionSelector } from './components/results/SectionSelector';
import { IconGrid, IconList } from './components/ui/Icons';

import { ExportPanel } from './components/export/ExportPanel';

function WarningState({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <div className="flex items-center justify-center h-full w-full p-6">
      <div
        className="flex flex-col items-center justify-center max-w-md text-center p-8 border border-dashed rounded-2xl"
        style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-sunken)' }}
      >
        <div className="text-5xl mb-4" aria-hidden="true">{icon}</div>
        <h3 className="text-base font-semibold mb-2 font-mono uppercase tracking-wider" style={{ color: 'var(--color-text-primary)' }}>
          {title}
        </h3>
        <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
          {description}
        </p>
      </div>
    </div>
  );
}

// ─── Profiles workspace (grid ↔ detail toggle) ─────────────

function ProfilesWorkspace() {
  const { t } = useTranslation();
  const selectedSection = useSession((s) => s.selectedSection);
  const setSelectedSection = useSession((s) => s.setSelectedSection);
  const [mode, setMode] = useState<'grid' | 'detail'>('grid');

  // When user picks a section from the grid, auto-switch to detail
  const handleGridSelect = (id: string) => {
    setSelectedSection(id);
    setMode('detail');
  };


  return (
    <div className="flex flex-col h-full gap-3 min-h-0">
      {/* Mode toggle */}
      <div className="shrink-0 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setMode('grid')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-colors"
          style={
            mode === 'grid'
              ? {
                  backgroundColor: 'var(--color-accent)',
                  color: 'var(--color-accent-fg)',
                  border: '1px solid var(--color-accent-bright)',
                }
              : {
                  backgroundColor: 'var(--color-surface-raised)',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                }
          }
        >
          <IconGrid className="w-3.5 h-3.5" /> {t('profiles.mode_grid', { defaultValue: 'Grilla' })}
        </button>
        <button
          type="button"
          onClick={() => setMode('detail')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-colors"
          style={
            mode === 'detail'
              ? {
                  backgroundColor: 'var(--color-accent)',
                  color: 'var(--color-accent-fg)',
                  border: '1px solid var(--color-accent-bright)',
                }
              : {
                  backgroundColor: 'var(--color-surface-raised)',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                }
          }
        >
          <IconList className="w-3.5 h-3.5" /> {t('profiles.mode_detail', { defaultValue: 'Detalle' })}
        </button>
        {mode === 'detail' && selectedSection && (
          <span className="text-xs font-mono ml-2" style={{ color: 'var(--color-text-muted)' }}>
            — {selectedSection}
          </span>
        )}
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
          <div className="shrink-0">
            <SectionSelector />
          </div>
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
  const { data: sections } = useSections();
  const { data: status } = useProcessStatus();
  const { t } = useTranslation();

  const bothUploaded = !!designMeshId && !!topoMeshId;
  const hasSections = sections && sections.length > 0;
  const isComplete = status?.status === 'complete';

  // 1. Mesh load prerequisite check
  if (!bothUploaded && activeWorkspaceView !== '3d') {
    return (
      <WarningState
        icon="⛰️"
        title={t('warning.no_mesh_title', { defaultValue: 'Mallas no cargadas' })}
        description={t('warning.no_mesh_desc', { defaultValue: 'Cargue superficies de diseño (Protocol Alpha) y topografía (Protocol Omega) en el panel lateral para acceder a esta vista.' })}
      />
    );
  }

  // 2. Sections prerequisite check
  if (bothUploaded && !hasSections && (activeWorkspaceView === 'profiles' || activeWorkspaceView === 'dashboard' || activeWorkspaceView === 'blast' || activeWorkspaceView === 'export-ai')) {
    return (
      <WarningState
        icon="📏"
        title={t('warning.no_sections_title', { defaultValue: 'Sin Secciones' })}
        description={t('warning.no_sections_desc', { defaultValue: 'Defina al menos una sección en el panel lateral para iniciar el análisis.' })}
      />
    );
  }

  // 3. Process completion check
  if (bothUploaded && hasSections && !isComplete && (activeWorkspaceView === 'profiles' || activeWorkspaceView === 'dashboard' || activeWorkspaceView === 'blast' || activeWorkspaceView === 'export-ai')) {
    return (
      <WarningState
        icon="⚡"
        title={t('warning.no_process_title', { defaultValue: 'Conciliación Pendiente' })}
        description={t('warning.no_process_desc', { defaultValue: 'Las secciones están definidas, pero el análisis no ha corrido. Haga clic en "Iniciar Análisis" en la sección de Procesamiento del panel lateral.' })}
      />
    );
  }

  // Active View Render
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
          <div className="flex-1 border rounded-lg overflow-hidden" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}>
            <div className="p-3 border-b border-border text-xs font-mono font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-surface-raised)' }}>
              Tabla Detallada de Comparación
            </div>
            <div className="p-4 overflow-x-auto">
              <LazyResultsTable />
            </div>
          </div>
        </div>
      );
    case 'blast':
      return (
        <div className="h-full flex flex-col gap-6 overflow-y-auto pr-1">
          <div className="shrink-0">
            <LazyBlastCorrelation />
          </div>
        </div>
      );
    case 'export-ai':
      return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full overflow-y-auto pb-4">
          <div className="h-fit">
            <ExportPanel />
          </div>
          <div className="h-fit">
            <LazyAIReporter />
          </div>
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

function App() {
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
    if (target === '1') setActiveWorkspaceView('3d');
    if (target === '2') setActiveWorkspaceView('profiles');
    if (target === '3') setActiveWorkspaceView('dashboard');
    if (target === '4') setActiveWorkspaceView('blast');
    if (target === '5') setActiveWorkspaceView('export-ai');
  });

  // Apply dark class to root element
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
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
