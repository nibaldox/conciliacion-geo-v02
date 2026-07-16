import { Canvas } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import { useBlastHolesBySession } from '../../api/hooks';
import type { BlastHoleSummary } from '../../api/types';
import { useTranslation } from 'react-i18next';

const HARDNESS_COLORS: Record<string, string> = {
  soft: '#10b981',    // green
  medium: '#f59e0b',  // amber
  hard: '#ef4444',    // red
  unknown: '#6b7280', // gray
};

export interface BlastHoles3DViewerProps {
  sessionId: string | null;
  sectionName?: string | null;
}

/** Convert a flat list of holes to a centered mesh for camera positioning. */
export function centerHoles(holes: BlastHoleSummary[]): { center: [number, number, number]; radius: number } {
  if (holes.length === 0) return { center: [0, 0, 0], radius: 10 };
  let sx = 0, sy = 0, sz = 0;
  for (const h of holes) {
    sx += h.x; sy += h.y; sz += h.z ?? 0;
  }
  const cx = sx / holes.length;
  const cy = sy / holes.length;
  const cz = sz / holes.length;
  let maxD2 = 0;
  for (const h of holes) {
    const dx = h.x - cx;
    const dy = h.y - cy;
    const dz = (h.z ?? 0) - cz;
    const d2 = dx * dx + dy * dy + dz * dz;
    if (d2 > maxD2) maxD2 = d2;
  }
  return { center: [cx, cy, cz], radius: Math.sqrt(maxD2) || 10 };
}

export function BlastHoles3DViewer({ sessionId, sectionName }: BlastHoles3DViewerProps) {
  const { t } = useTranslation();
  const { data, isLoading, error } = useBlastHolesBySession(sessionId, sectionName);

  if (!sessionId) {
    return <p data-testid="viewer-no-session">{t('blast.viewer_no_session')}</p>;
  }
  if (isLoading) {
    return <p data-testid="viewer-loading">{t('blast.viewer_loading')}</p>;
  }
  if (error) {
    return <p data-testid="viewer-error" role="alert">{t('blast.viewer_error', { error: String(error) })}</p>;
  }
  const holes = data?.holes ?? [];
  if (holes.length === 0) {
    return <p data-testid="viewer-empty">{t('blast.viewer_empty')}</p>;
  }

  const { center, radius } = centerHoles(holes);
  const cameraDistance = radius * 2.5;

  return (
    <section data-testid="blast-3d-viewer" className="glass-panel rounded-xl p-5 space-y-3">
      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
        {t('blast.viewer_title')}
      </h3>
      <div style={{ width: '100%', height: '500px' }} data-testid="viewer-canvas-container">
        <Canvas
          camera={{ position: [center[0] + cameraDistance, center[1] + cameraDistance, center[2] + cameraDistance], fov: 50 }}
          data-testid="viewer-canvas"
        >
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={1} />
          <gridHelper args={[radius * 3, 20, '#444', '#222']} />
          {holes.map((h) => (
            <mesh key={h.hole_id} position={[h.x, h.y, h.z ?? 0]} data-testid={`hole-${h.hole_id}`}>
              <sphereGeometry args={[radius * 0.02, 16, 16]} />
              <meshStandardMaterial color={HARDNESS_COLORS[h.hardness ?? 'unknown']} />
              <Html distanceFactor={radius * 0.1}>
                <div style={{ color: 'white', fontSize: '10px', background: 'rgba(0,0,0,0.6)', padding: '2px 4px', borderRadius: '2px' }}>
                  {h.hole_id}
                </div>
              </Html>
            </mesh>
          ))}
          <OrbitControls enablePan enableZoom enableRotate target={center} />
        </Canvas>
      </div>
      <div data-testid="viewer-legend" className="flex gap-4 mt-2 flex-wrap">
        {Object.entries(HARDNESS_COLORS).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            <span style={{ width: 12, height: 12, background: c, borderRadius: '50%' }} />
            {t(`blast.hardness_${k}`)}
          </span>
        ))}
      </div>
    </section>
  );
}
