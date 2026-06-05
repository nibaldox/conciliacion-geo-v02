/**
 * Step1Content — the "CARGAR SUPERFICIES" step (MISIÓN 01).
 *
 * Mission Control layout: two side-by-side "PROTOCOL" cards
 * (ALPHA for design, OMEGA for topo) with the MeshUpload zones
 * inside, a TERMINAL DE STATUS log at the bottom showing what
 * the system is doing, and a big "INITIALIZE ANALYSIS" launch
 * button (orange accent, uppercase, tracking) when both meshes
 * are uploaded.
 */

import { Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DropZone } from './MeshUpload';
import { LazyContourChart, LazyMesh3DViewer } from '../lazy';
import { LoadingSpinner } from '../LoadingSpinner';
import { Card, Button, StatusBar } from '../ui';
import { useSession } from '../../stores/session';

type ViewMode = '2d' | '3d';

export function Step1Content() {
  const { designMeshId, topoMeshId, setDesignMeshId, setTopoMeshId, nextStep } = useSession();
  const bothUploaded = !!designMeshId && !!topoMeshId;
  const [viewMode, setViewMode] = useState<ViewMode>('2d');
  const { t } = useTranslation();

  return (
    <div
      data-slot="step1-content"
      className="flex flex-col h-full gap-4 min-h-0"
    >
      {/* ── Two protocol cards side by side ──────────────────────── */}
      <section
        aria-label={t('step1.upload_zones_aria', { defaultValue: 'Upload zones' })}
        className="shrink-0 grid grid-cols-1 lg:grid-cols-2 gap-4"
      >
        <UploadProtocolCard
          eyebrow="PROTOCOL ALPHA"
          icon="⛰"
          title={t('step1.design')}
          subtitle={t('step1.design_subtitle', { defaultValue: 'Diseño planificado del pit' })}
          loaded={!!designMeshId}
        >
          <DropZone type="design" meshId={designMeshId} onSetMeshId={setDesignMeshId} />
        </UploadProtocolCard>

        <UploadProtocolCard
          eyebrow="PROTOCOL OMEGA"
          icon="📡"
          title={t('step1.topo')}
          subtitle={t('step1.topo_subtitle', { defaultValue: 'Topografía real escaneada' })}
          loaded={!!topoMeshId}
        >
          <DropZone type="topo" meshId={topoMeshId} onSetMeshId={setTopoMeshId} />
        </UploadProtocolCard>
      </section>

      {/* ── Viewer (plan / 3D) with tabbed toggle ──────────────────── */}
      <section
        aria-label={t('step1.viewer_aria')}
        className="flex-1 min-h-[300px] rounded-lg overflow-hidden flex flex-col gap-2 shrink-0"
        style={{
          backgroundColor: 'var(--color-surface-raised)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex gap-1 self-start p-2" role="tablist" aria-label={t('step1.viewer_type_aria')}>
          <ViewerTab active={viewMode === '2d'} onClick={() => setViewMode('2d')}>
            {t('step1.tab_2d')}
          </ViewerTab>
          <ViewerTab active={viewMode === '3d'} onClick={() => setViewMode('3d')}>
            {t('step1.tab_3d')}
          </ViewerTab>
        </div>

        <div className="flex-1 min-h-0 px-2 pb-2">
          <Suspense fallback={<LoadingSpinner message={t('step1.loading_view')} />}>
            {viewMode === '2d' ? <LazyContourChart /> : <LazyMesh3DViewer />}
          </Suspense>
        </div>
      </section>

      {/* ── Terminal de status — fake log feed ──────────────────── */}
      <StatusBar
        title="TERMINAL DE STATUS"
        entries={[
          { level: 'system', text: t('step1.terminal.ingest', { defaultValue: 'Ingest core initialised' }) },
          { level: 'scan', text: bothUploaded
            ? t('step1.terminal.both_loaded', { defaultValue: 'Both surface data packets received' })
            : t('step1.terminal.waiting', { defaultValue: 'Waiting for surface data packets' }) },
          ...(bothUploaded
            ? [{ level: 'geo' as const, text: t('step1.terminal.coord', { defaultValue: 'Local coordinate set to EPSG:4326' }) }]
            : []),
        ]}
      />

      {/* ── Launch button ──────────────────────────────────────── */}
      <div className="flex justify-end pt-1 pb-1 shrink-0">
        <Button
          variant="launch"
          size="lg"
          onClick={nextStep}
          disabled={!bothUploaded}
          leftIcon={<span aria-hidden="true">🚀</span>}
        >
          {bothUploaded
            ? t('step1.launch', { defaultValue: 'Inicializar análisis' })
            : t('step1.launch_waiting', { defaultValue: 'Awaiting data packets' })}
        </Button>
      </div>
    </div>
  );
}

// ─── Internal: protocol card (design / topo) ─────────────────

interface UploadProtocolCardProps {
  eyebrow: string;
  icon: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  loaded: boolean;
  children: React.ReactNode;
}

function UploadProtocolCard({ eyebrow, icon, title, subtitle, loaded, children }: UploadProtocolCardProps) {
  return (
    <Card
      data-testid="protocol-card"
      variant="dashed"
      eyebrow={eyebrow}
      icon={icon}
      title={title}
      subtitle={subtitle}
      headerAside={
        <span
          data-testid="protocol-status"
          data-loaded={loaded}
          className="text-[10px] uppercase tracking-widest font-mono px-2 py-0.5 rounded"
          style={{
            backgroundColor: loaded ? 'var(--status-ok-bg)' : 'var(--color-surface-muted)',
            color: loaded ? 'var(--status-ok-text)' : 'var(--color-text-muted)',
            border: loaded
              ? '1px solid var(--status-ok-border)'
              : '1px solid var(--color-border)',
          }}
        >
          {loaded ? '● ONLINE' : '○ WAITING'}
        </span>
      }
    >
      {children}
    </Card>
  );
}

// ─── Internal: viewer tab ───────────────────────────────────

function ViewerTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className="px-3 py-1 text-[11px] uppercase tracking-widest font-semibold rounded transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      style={{
        backgroundColor: active ? 'var(--color-accent-bg)' : 'transparent',
        color: active ? 'var(--color-accent-bright)' : 'var(--color-text-muted)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {children}
    </button>
  );
}
