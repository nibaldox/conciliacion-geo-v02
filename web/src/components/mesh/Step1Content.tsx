import { Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MeshUpload } from './MeshUpload';
import { LazyContourChart, LazyMesh3DViewer } from '../lazy';
import { LoadingSpinner } from '../LoadingSpinner';
import { useSession } from '../../stores/session';

type ViewMode = '2d' | '3d';

export function Step1Content() {
  const { designMeshId, topoMeshId, nextStep } = useSession();
  const bothUploaded = !!designMeshId && !!topoMeshId;
  const [viewMode, setViewMode] = useState<ViewMode>('2d');
  const { t } = useTranslation();

  return (
    <div
      data-slot="step1-content"
      className="flex flex-col h-full gap-4 min-h-0"
    >
      {/* Top half: Mesh Upload zones */}
      <section aria-label={t('step1.upload_zones_aria')} className="shrink-0">
        <MeshUpload />
      </section>

      {/* Bottom half: Plan View / 3D Viewer with toggle */}
      <section
        aria-label={t('step1.viewer_aria')}
        className="flex-1 min-h-[300px] rounded-xl overflow-hidden flex flex-col gap-2 shrink-0"
      >
        {/* 2D / 3D toggle */}
        <div className="flex gap-1 self-start" role="tablist" aria-label={t('step1.viewer_type_aria')}>
          <button
            role="tab"
            aria-selected={viewMode === '2d'}
            onClick={() => setViewMode('2d')}
            className="px-4 py-1.5 text-xs font-medium rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue"
            style={viewMode === '2d'
              ? { backgroundColor: 'var(--color-mine-blue)', color: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }
              : { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)' }
            }
          >
            {t('step1.tab_2d')}
          </button>
          <button
            role="tab"
            aria-selected={viewMode === '3d'}
            onClick={() => setViewMode('3d')}
            className="px-4 py-1.5 text-xs font-medium rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue"
            style={viewMode === '3d'
              ? { backgroundColor: 'var(--color-mine-blue)', color: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }
              : { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)' }
            }
          >
            {t('step1.tab_3d')}
          </button>
        </div>

        {/* Viewer */}
        <div className="flex-1 min-h-0">
          <Suspense fallback={<LoadingSpinner message={t('step1.loading_view')} />}>
            {viewMode === '2d' ? (
              <LazyContourChart />
            ) : (
              <LazyMesh3DViewer />
            )}
          </Suspense>
        </div>
      </section>

      {/* Navigation: Siguiente button */}
      <div className="flex justify-end pt-1 pb-1 shrink-0">
        <button
          onClick={nextStep}
          disabled={!bothUploaded}
          className="px-6 py-2.5 rounded-lg font-medium text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue focus-visible:ring-offset-2"
          style={bothUploaded
            ? { backgroundColor: 'var(--color-mine-blue)', color: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,0.15)' }
            : { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)', cursor: 'not-allowed' }
          }
        >
          {t('step1.next')}
        </button>
      </div>
    </div>
  );
}
