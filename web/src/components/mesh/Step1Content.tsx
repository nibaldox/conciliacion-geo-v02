import { Suspense, useState } from 'react';
import { MeshUpload } from './MeshUpload';
import { LazyPlanView, LazyMesh3DViewer } from '../lazy';
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
      className="flex flex-col h-full gap-6"
    >
      {/* Top half: Mesh Upload zones */}
      <section aria-label="Carga de superficies">
        <MeshUpload />
      </section>

      {/* Bottom half: Plan View / 3D Viewer with toggle */}
      <section
        aria-label="Vista del terreno"
        className="flex-1 min-h-[400px] rounded-xl overflow-hidden flex flex-col gap-2"
      >
        {/* 2D / 3D toggle */}
        <div className="flex gap-1 self-start" role="tablist" aria-label="Tipo de vista">
          <button
            role="tab"
            aria-selected={viewMode === '2d'}
            onClick={() => setViewMode('2d')}
            className={`
              px-4 py-1.5 text-xs font-medium rounded-lg transition-all
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue
              ${
                viewMode === '2d'
                  ? 'bg-mine-blue text-white shadow-sm'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }
            `}
          >
            Vista 2D
          </button>
          <button
            role="tab"
            aria-selected={viewMode === '3d'}
            onClick={() => setViewMode('3d')}
            className={`
              px-4 py-1.5 text-xs font-medium rounded-lg transition-all
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue
              ${
                viewMode === '3d'
                  ? 'bg-mine-blue text-white shadow-sm'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }
            `}
          >
            Vista 3D
          </button>
        </div>

        {/* Viewer */}
        <Suspense fallback={<LoadingSpinner message="Cargando vista…" />}>
          {viewMode === '2d' ? (
            <LazyPlanView />
          ) : (
            <LazyMesh3DViewer />
          )}
        </Suspense>
      </section>

      {/* Navigation: Siguiente button */}
      <div className="flex justify-end pt-2 pb-1">
        <button
          onClick={nextStep}
          disabled={!bothUploaded}
          className={`
            px-6 py-2.5 rounded-lg font-medium text-sm transition-all
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue focus-visible:ring-offset-2
            ${
              bothUploaded
                ? 'bg-mine-blue text-white shadow-md hover:bg-blue-800 active:scale-[0.98]'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }
          `}
        >
          Siguiente →
        </button>
      </div>
    </div>
  );
}
