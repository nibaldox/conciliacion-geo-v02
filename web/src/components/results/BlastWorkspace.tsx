import { Suspense, lazy, useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { useBlastSessionSummary } from '../../api/hooks';
import { getSessionId } from '../../api/client';
import { GEOMETRY_CONFIGURATION_VERSION } from '../../api/types';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import { useBlastView, type BlastWorkspaceTab } from '../../stores/blastView';
import { BlastCorrelation } from './BlastCorrelation';
import { BlastSimulationPanel } from './BlastSimulationPanel';
import { BlastUploader } from './BlastUploader';

const Mesh3DViewer = lazy(() =>
  import('../mesh/Mesh3DViewer').then((m) => ({ default: m.Mesh3DViewer })),
);

const TABS: readonly BlastWorkspaceTab[] = ['explore', 'analysis', 'simulation', 'data'];

const TAB_LABEL_KEYS: Record<BlastWorkspaceTab, string> = {
  explore: 'blast.workspace.explore',
  analysis: 'blast.workspace.analysis',
  simulation: 'blast.workspace.simulation',
  data: 'blast.workspace.data',
};

const decidedSessions = new Set<string>();

function PanelFallback() {
  const { t } = useTranslation();
  return (
    <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
      {t('common.loading', { defaultValue: 'Cargando…' })}
    </p>
  );
}

export function BlastWorkspace() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const idBase = useId();
  const { designMeshId, topoMeshId } = useSession();
  const hasVirtualMesh = designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo;
  const sessionId = getSessionId();
  const summary = useBlastSessionSummary(hasVirtualMesh ? null : sessionId ?? null);
  const activeTab = useBlastView((s) => s.workspaceTab);
  const setWorkspaceTab = useBlastView((s) => s.setWorkspaceTab);
  const tabRefs = useRef<Partial<Record<BlastWorkspaceTab, HTMLButtonElement | null>>>({});

  const holeCount = summary.data?.n_holes;
  const sessionKey = sessionId ?? '';

  useEffect(() => {
    if (holeCount === undefined || hasVirtualMesh || decidedSessions.has(sessionKey)) return;
    decidedSessions.add(sessionKey);
    if (holeCount === 0) setWorkspaceTab('data');
  }, [holeCount, hasVirtualMesh, sessionKey, setWorkspaceTab]);

  const refreshAnalysis = () => Promise.all([
    qc.invalidateQueries({ queryKey: ['blast-correlation'] }),
    qc.invalidateQueries({ queryKey: ['blast-damage-model'] }),
    qc.invalidateQueries({ queryKey: ['blast-holes-3d'] }),
  ]);

  const selectTab = (tab: BlastWorkspaceTab, focus = false) => {
    setWorkspaceTab(tab);
    if (focus) tabRefs.current[tab]?.focus();
  };

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length;
    if (event.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length;
    if (next === null) return;
    event.preventDefault();
    selectTab(TABS[next], true);
  };

  const tabId = (tab: BlastWorkspaceTab) => `${idBase}-tab-${tab}`;
  const panelId = `${idBase}-panel`;

  let panel: ReactNode;
  if (activeTab === 'explore') {
    if (summary.data === undefined && sessionId && !hasVirtualMesh) {
      panel = <PanelFallback />;
    } else if (holeCount && holeCount > 0) {
      panel = (
        <Suspense fallback={<PanelFallback />}>
          <Mesh3DViewer mode="blast" />
        </Suspense>
      );
    } else {
      panel = (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {t('blast.workspace.noHoles')}
          </p>
          <button
            type="button"
            onClick={() => selectTab('data')}
            className="min-h-10 rounded border border-border px-3 text-sm"
          >
            {t('blast.workspace.data')}
          </button>
        </div>
      );
    }
  } else if (activeTab === 'analysis') {
    panel = <BlastCorrelation presentation="analysis" />;
  } else if (activeTab === 'simulation') {
    panel = (
      <Suspense fallback={<PanelFallback />}>
        <BlastSimulationPanel
          sessionId={getSessionId()}
          geometryConfigurationVersion={GEOMETRY_CONFIGURATION_VERSION}
        />
      </Suspense>
    );
  } else {
    panel = <BlastUploader onUploaded={refreshAnalysis} />;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div
        role="tablist"
        aria-label={t('blast.workspace.tabsLabel')}
        className="flex flex-wrap gap-2 border-b pb-2"
        style={{ borderColor: 'var(--color-border)' }}
      >
        {TABS.map((tab, index) => {
          const selected = tab === activeTab;
          return (
            <button
              key={tab}
              ref={(el) => { tabRefs.current[tab] = el; }}
              id={tabId(tab)}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              onClick={() => selectTab(tab)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
              className="min-h-10 rounded-md px-3 text-sm font-semibold"
              style={{
                backgroundColor: selected ? 'var(--color-accent, #f97316)' : 'var(--color-surface-muted)',
                color: selected ? 'white' : 'var(--color-text-secondary)',
              }}
            >
              {t(TAB_LABEL_KEYS[tab])}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId(activeTab)}
        className={activeTab === 'explore' ? 'flex-1 min-h-0' : 'flex-1 min-h-0 overflow-y-auto'}
      >
        {panel}
      </div>
    </div>
  );
}
