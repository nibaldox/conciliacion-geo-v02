import { Canvas } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import { useBlastHolesBySession } from '../../api/hooks';
import type { BlastHoleSummary } from '../../api/types';
import { useTranslation } from 'react-i18next';
import { useMemo } from 'react';
import { useTheme } from '../../stores/theme';
import { readThemeColor } from '../../utils/theme';

const HARDNESS_TOKENS: Record<string, [string, string]> = {
  soft: ['--color-mine-green', '#22c5aa'],
  medium: ['--color-mine-yellow', '#e68f19'],
  hard: ['--color-mine-red', '#e83149'],
  unknown: ['--color-mine-gray', '#9fa6b2'],
};

function useHardnessColors(): Record<string, string> {
  const isDark = useTheme((s) => s.isDark);
  return useMemo(
    () => Object.fromEntries(Object.entries(HARDNESS_TOKENS).map(([key, [token, fallback]]) => [key, readThemeColor(token, fallback)])),
    [isDark],
  );
}

function useGridColors(): [string, string] {
  const isDark = useTheme((s) => s.isDark);
  return useMemo(
    () => [readThemeColor('--color-viewer-grid', '#1c2430'), readThemeColor('--color-viewer-grid-minor', '#10161d')],
    [isDark],
  );
}

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
  const hardnessColors = useHardnessColors();
  const [gridColor, gridMinorColor] = useGridColors();

  if (!sessionId) {
    return <p className="text-sm text-text-muted" data-testid="viewer-no-session">{t('blast.viewer_no_session')}</p>;
  }
  if (isLoading) {
    return <p className="text-sm text-text-muted" data-testid="viewer-loading">{t('blast.viewer_loading')}</p>;
  }
  if (error) {
    return <p className="text-sm text-text-secondary" data-testid="viewer-error" role="alert">{t('blast.viewer_error', { error: String(error) })}</p>;
  }
  const holes = data?.holes ?? [];
  if (holes.length === 0) {
    return <p className="text-sm text-text-muted" data-testid="viewer-empty">{t('blast.viewer_empty')}</p>;
  }

  const { center, radius } = centerHoles(holes);
  const cameraDistance = radius * 2.5;

  return (
    <section data-testid="blast-3d-viewer" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h3 className="ui-section-title">{t('blast.viewer_title')}</h3>
        <div data-testid="viewer-legend" className="flex flex-wrap gap-3">
          {Object.entries(hardnessColors).map(([k, c]) => (
            <span key={k} className="flex items-center gap-1.5 text-xs text-text-muted">
              <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: c }} />
              {t(`blast.hardness_${k}`)}
            </span>
          ))}
        </div>
      </div>
      <div className="overflow-hidden rounded-lg border border-border" style={{ width: '100%', height: '500px', backgroundColor: 'var(--color-viewer-bg)' }} data-testid="viewer-canvas-container">
        <Canvas
          camera={{ position: [center[0] + cameraDistance, center[1] + cameraDistance, center[2] + cameraDistance], fov: 50 }}
          data-testid="viewer-canvas"
        >
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={1} />
          <gridHelper args={[radius * 3, 20, gridColor, gridMinorColor]} />
          {holes.map((h) => (
            <mesh key={h.hole_id} position={[h.x, h.y, h.z ?? 0]} data-testid={`hole-${h.hole_id}`}>
              <sphereGeometry args={[radius * 0.02, 16, 16]} />
              <meshStandardMaterial color={hardnessColors[h.hardness ?? 'unknown']} />
              <Html distanceFactor={radius * 0.1}>
                <div className="rounded-sm px-1 py-0.5 font-mono text-[10px]" style={{ color: 'var(--color-text-primary)', backgroundColor: 'color-mix(in srgb, var(--color-surface) 75%, transparent)' }}>
                  {h.hole_id}
                </div>
              </Html>
            </mesh>
          ))}
          <OrbitControls enablePan enableZoom enableRotate target={center} />
        </Canvas>
      </div>
    </section>
  );
}
