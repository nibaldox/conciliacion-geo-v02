import { Suspense, useState } from 'react';
import { MeshUpload } from './MeshUpload';
import { LazyContourChart, LazyMesh3DViewer } from '../lazy';
import { LoadingSpinner } from '../LoadingSpinner';
import { useSession } from '../../stores/session';

type ViewMode = '2d' | '3d';

export function Step1Content() {
  const { designMeshId, topoMeshId, nextStep } = useSession();
  const bothUploaded = !!designMeshId && !!topoMeshId;
  const [viewMode, setViewMode] = useState<ViewMode>('2d');

  return (
    <div
      data-slot="step1-content"
      className="flex flex-col h-full gap-4 min-h-0"
    >
      {/* Top half: Mesh Upload zones */}
      <section aria-label="Carga de superficies" className="shrink-0">
        <MeshUpload />
      </section>

      {/* Bottom half: Plan View / 3D Viewer with toggle */}
      <section
        aria-label="Vista del terreno"
        className="flex-1 min-h-[300px] rounded-xl overflow-hidden flex flex-col gap-2 shrink-0"
      >
        {/* 2D / 3D toggle */}
        <div className="flex gap-1 self-start" role="tablist" aria-label="Tipo de vista">
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
            Curvas de Nivel
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
            Vista 3D
          </button>
        </div>

        {/* Viewer */}
        <div className="flex-1 min-h-0">
          <Suspense fallback={<LoadingSpinner message="Cargando vista…" />}>
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
          Siguiente →
        </button>
      </div>
    </div>
  );
}
