import { useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useBlastHolesBySession } from '../../api/hooks';
import type { BlastHoleSummary } from '../../api/types';
import { useTranslation } from 'react-i18next';
import { BlastHolesLayer, type BlastHole3D } from '../mesh/BlastHolesLayer';

const HARDNESS_COLORS: Record<string, string> = {
  soft: '#10b981',
  medium: '#f59e0b',
  hard: '#ef4444',
  unknown: '#6b7280',
};

export interface BlastHoles3DViewerProps {
  sessionId: string | null;
  sectionName?: string | null;
}

/** Convert a flat list of holes to a centered mesh for camera positioning. */
export function centerHoles(holes: BlastHoleSummary[]): { center: [number, number, number]; radius: number } {
  const drawable = holes.filter((hole) => Number.isFinite(hole.x) && Number.isFinite(hole.y) && hole.z !== null && Number.isFinite(hole.z));
  if (drawable.length === 0) return { center: [0, 0, 0], radius: 10 };
  let sx = 0, sy = 0, sz = 0;
  for (const h of drawable) {
    sx += h.x; sy += h.y; sz += h.z!;
  }
  const cx = sx / drawable.length;
  const cy = sy / drawable.length;
  const cz = sz / drawable.length;
  let maxD2 = 0;
  for (const h of drawable) {
    const dx = h.x - cx;
    const dy = h.y - cy;
    const dz = h.z! - cz;
    const d2 = dx * dx + dy * dy + dz * dz;
    if (d2 > maxD2) maxD2 = d2;
  }
  return { center: [cx, cy, cz], radius: Math.sqrt(maxD2) || 10 };
}

export function BlastHoles3DViewer({ sessionId, sectionName }: BlastHoles3DViewerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <section data-testid="blast-3d-viewer" className="glass-panel rounded-xl p-5 space-y-3">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        aria-expanded={open}
        aria-controls="blast-3d-viewer-content"
        aria-label={t(open ? 'blast.viewer_close' : 'blast.viewer_open')}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.viewer_title')}
        </span>
        <span aria-hidden="true" style={{ color: 'var(--color-text-muted)' }}>{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div id="blast-3d-viewer-content">
          <BlastHoles3DContent sessionId={sessionId} sectionName={sectionName} />
        </div>
      )}
    </section>
  );
}

function BlastHoles3DContent({ sessionId, sectionName }: BlastHoles3DViewerProps) {
  const { t } = useTranslation();
  const { data, isLoading, error } = useBlastHolesBySession(sessionId, sectionName);

  if (!sessionId) return <p data-testid="viewer-no-session">{t('blast.viewer_no_session')}</p>;
  if (isLoading) return <p data-testid="viewer-loading">{t('blast.viewer_loading')}</p>;
  if (error) return <p data-testid="viewer-error" role="alert">{t('blast.viewer_error', { error: String(error) })}</p>;

  const holes = data?.holes ?? [];
  if (holes.length === 0) return <p data-testid="viewer-empty">{t('blast.viewer_empty')}</p>;

  return <BlastHolesCanvas holes={holes} />;
}

function BlastHolesCanvas({ holes }: { holes: BlastHoleSummary[] }) {
  const { t } = useTranslation();
  const { center, radius } = useMemo(() => centerHoles(holes), [holes]);
  const cameraDistance = radius * 2.5;
  const meshHoles = useMemo<BlastHole3D[]>(() => holes.filter((hole) => (
    Number.isFinite(hole.x) && Number.isFinite(hole.y) && hole.z !== null && Number.isFinite(hole.z)
  )).map((hole) => ({
    key: hole.hole_id,
    collar: [hole.x, hole.y, hole.z!],
    color: HARDNESS_COLORS[hole.hardness ?? 'unknown'] ?? HARDNESS_COLORS.unknown,
  })), [holes]);

  return (
    <>
      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }} data-testid="viewer-hole-count">
        {t('blast.viewer_hole_count', { count: meshHoles.length })}
      </p>
      <div style={{ width: '100%', height: '500px' }} data-testid="viewer-canvas-container">
        <Canvas
          camera={{ position: [cameraDistance, cameraDistance, cameraDistance], fov: 50 }}
          data-testid="viewer-canvas"
        >
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={1} />
          <gridHelper args={[radius * 3, 20, '#444', '#222']} />
          <BlastHolesLayer holes={meshHoles} center={center} collarRadius={0.35} />
          <OrbitControls enablePan enableZoom enableRotate target={[0, 0, 0]} />
        </Canvas>
      </div>
      <div data-testid="viewer-legend" className="flex gap-4 mt-2 flex-wrap">
        {Object.entries(HARDNESS_COLORS).map(([key, color]) => (
          <span key={key} className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            <span style={{ width: 12, height: 12, background: color, borderRadius: '50%' }} />
            {t(`blast.hardness_${key}`)}
          </span>
        ))}
      </div>
    </>
  );
}
