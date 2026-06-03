import { useEffect, useRef, useState, useMemo } from 'react';
import { useMeshVertices, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { SectionResponse, VerticesResponse } from '../../api/types';

// Cesium is a 4 MB JS chunk + 22 MB of static assets (Workers, Widgets,
// Assets) that we copy from node_modules to public/Cesium at build
// time. The whole point of this component is to delay loading them
// until the user actually asks for the 3D view, by gating the import
// behind a "Load 3D viewer" click. Until then, only this small
// "click to load" placeholder is in memory — saves ~26 MB of network
// on the first page load.
//
// Note: cesium's bundled .d.ts has structural issues (classes are
// typed as `typeof Class` instead of `Class`), so we type the loaded
// module as a minimal `any` to avoid fighting the type defs at runtime.

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type CesiumAPI = any;

const DESIGN_HEX = '#3b82f6';
const TOPO_HEX = '#22c55e';
const POINT_PIXEL_SIZE = 3;

/** Compute section line endpoints in 3D (flat on ground at z=0). */
function sectionEndpoints(sec: SectionResponse, Cartesian3: CesiumAPI): [CesiumAPI, CesiumAPI] {
  const azimuthRad = (sec.azimuth * Math.PI) / 180;
  const dx = Math.sin(azimuthRad) * sec.length;
  const dy = Math.cos(azimuthRad) * sec.length;
  return [
    new Cartesian3(sec.origin[0], sec.origin[1], 0),
    new Cartesian3(sec.origin[0] + dx, sec.origin[1] + dy, 0),
  ];
}

function dataCenter(verts: VerticesResponse, Cartesian3: CesiumAPI): CesiumAPI {
  const len = verts.x.length;
  if (len === 0) return new Cartesian3(0, 0, 0);
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < len; i++) {
    cx += verts.x[i];
    cy += verts.y[i];
    cz += verts.z[i];
  }
  return new Cartesian3(cx / len, cy / len, cz / len);
}

function boundingRadius(verts: VerticesResponse, center: { x: number; y: number; z: number }): number {
  const len = verts.x.length;
  if (len === 0) return 100;
  let maxDist = 0;
  for (let i = 0; i < len; i++) {
    const dx = verts.x[i] - center.x;
    const dy = verts.y[i] - center.y;
    const dz = verts.z[i] - center.z;
    const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (dist > maxDist) maxDist = dist;
  }
  return maxDist;
}

// ── Lazy Cesium viewer ────────────────────────────────────────

interface CesiumViewerProps {
  designVerts: VerticesResponse | undefined;
  topoVerts: VerticesResponse | undefined;
  sections: SectionResponse[] | undefined;
  selectedSection: string | null;
}

function CesiumViewerImpl({ designVerts, topoVerts, sections, selectedSection }: CesiumViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<CesiumAPI['Viewer'] | null>(null);
  const pointsRef = useRef<CesiumAPI['PointPrimitiveCollection'] | null>(null);
  const linesRef = useRef<CesiumAPI['PolylineCollection'] | null>(null);
  const [Cesium, setCesium] = useState<CesiumAPI | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Import Cesium on mount — dynamic import so the 4 MB chunk is
  // fetched only when this component renders.
  useEffect(() => {
    let cancelled = false;
    import('cesium')
      .then((mod) => {
        if (cancelled) return;
        setCesium({
          Viewer: mod.Viewer,
          Color: mod.Color,
          Cartesian3: mod.Cartesian3,
          PointPrimitiveCollection: mod.PointPrimitiveCollection,
          PolylineCollection: mod.PolylineCollection,
          SceneMode: mod.SceneMode,
          Math: mod.Math,
          EllipsoidTerrainProvider: mod.EllipsoidTerrainProvider,
        });
      })
      .catch((err) => {
        if (!cancelled) setError(`Error al cargar CesiumJS: ${err instanceof Error ? err.message : String(err)}`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Initialise the viewer once Cesium is loaded.
  useEffect(() => {
    if (!Cesium || !containerRef.current) return;
    try {
      const viewer = new Cesium.Viewer(containerRef.current, {
        imageryProvider: false,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        sceneMode: Cesium.SceneMode.SCENE3D,
        skyBox: false as unknown as undefined,
        skyAtmosphere: false as unknown as undefined,
      } as unknown as ConstructorParameters<typeof Cesium.Viewer>[1]);
      (viewer.cesiumWidget.creditContainer as HTMLElement).style.display = 'none';
      viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0f172a');
      viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
      const points = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
      const lines = viewer.scene.primitives.add(new Cesium.PolylineCollection());
      pointsRef.current = points;
      linesRef.current = lines;
      viewerRef.current = viewer;
      return () => {
        viewer.destroy();
        viewerRef.current = null;
        pointsRef.current = null;
        linesRef.current = null;
      };
    } catch (err) {
      setError(`Error al inicializar CesiumJS: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [Cesium]);

  // Update points when data changes.
  useEffect(() => {
    if (!Cesium) return;
    const points = pointsRef.current;
    if (!points) return;
    points.removeAll();
    if (designVerts && designVerts.x.length > 0) {
      const color = Cesium.Color.fromCssColorString(DESIGN_HEX).withAlpha(0.85);
      for (let i = 0; i < designVerts.x.length; i++) {
        points.add({
          position: new Cesium.Cartesian3(designVerts.x[i], designVerts.y[i], designVerts.z[i]),
          color,
          pixelSize: POINT_PIXEL_SIZE,
        });
      }
    }
    if (topoVerts && topoVerts.x.length > 0) {
      const color = Cesium.Color.fromCssColorString(TOPO_HEX).withAlpha(0.85);
      for (let i = 0; i < topoVerts.x.length; i++) {
        points.add({
          position: new Cesium.Cartesian3(topoVerts.x[i], topoVerts.y[i], topoVerts.z[i]),
          color,
          pixelSize: POINT_PIXEL_SIZE,
        });
      }
    }
  }, [Cesium, designVerts, topoVerts]);

  // Update section lines.
  useEffect(() => {
    if (!Cesium) return;
    const lines = linesRef.current;
    if (!lines || !sections || sections.length === 0) return;
    lines.removeAll();
    for (const sec of sections) {
      const [start, end] = sectionEndpoints(sec, Cesium.Cartesian3);
      const isSelected = selectedSection === sec.name;
      lines.add({
        positions: [start, end],
        width: isSelected ? 4 : 2,
        color: isSelected
          ? Cesium.Color.fromCssColorString('#f43f5e').withAlpha(1.0)
          : Cesium.Color.fromCssColorString('#ef4444').withAlpha(0.35),
      });
    }
  }, [Cesium, sections, selectedSection]);

  // Fly to selected section.
  useEffect(() => {
    if (!Cesium) return;
    const viewer = viewerRef.current;
    if (!viewer || !sections || !selectedSection) return;
    const sec = sections.find((s) => s.name === selectedSection);
    if (!sec) return;
    const [start, end] = sectionEndpoints(sec, Cesium.Cartesian3);
    const mid = new Cesium.Cartesian3(
      (start.x + end.x) / 2,
      (start.y + end.y) / 2,
      (start.z + end.z) / 2,
    );
    viewer.camera.flyTo({
      destination: new Cesium.Cartesian3(
        mid.x + sec.length * 0.4,
        mid.y - sec.length * 0.4,
        mid.z + sec.length * 0.6,
      ),
      orientation: {
        heading: Cesium.Math.toRadians(45),
        pitch: Cesium.Math.toRadians(-45),
        roll: 0,
      },
      duration: 1.2,
    });
  }, [Cesium, selectedSection, sections]);

  // Auto-fit to data bounds on first load.
  const combinedVerts = useMemo(() => {
    if (designVerts && topoVerts) {
      return {
        x: [...designVerts.x, ...topoVerts.x],
        y: [...designVerts.y, ...topoVerts.y],
        z: [...designVerts.z, ...topoVerts.z],
      };
    }
    return designVerts ?? topoVerts ?? null;
  }, [designVerts, topoVerts]);

  useEffect(() => {
    if (!Cesium) return;
    const viewer = viewerRef.current;
    if (!viewer || !combinedVerts || combinedVerts.x.length === 0 || selectedSection) return;
    const center = dataCenter(combinedVerts, Cesium.Cartesian3);
    const radius = boundingRadius(combinedVerts, center);
    const offset = Math.max(radius * 2.5, 50);
    viewer.camera.flyTo({
      destination: new Cesium.Cartesian3(
        center.x + offset * 0.5,
        center.y - offset * 0.5,
        center.z + offset * 0.8,
      ),
      orientation: {
        heading: Cesium.Math.toRadians(30),
        pitch: Cesium.Math.toRadians(-30),
        roll: 0,
      },
      duration: 1.5,
    });
  }, [Cesium, combinedVerts, selectedSection]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-mine-red)' }}>
          <div className="text-3xl">⚠️</div>
          <p className="text-sm text-center px-4">{error}</p>
        </div>
      </div>
    );
  }

  if (!Cesium) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">Cargando CesiumJS (≈4 MB)…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-[400px] w-full rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
      <div ref={containerRef} className="w-full h-full" style={{ minHeight: '400px' }} />
    </div>
  );
}

// ── Component (public API) ───────────────────────────────────

export function Mesh3DViewer() {
  const { designMeshId, topoMeshId, selectedSection } = useSession();
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();
  const isLoading = loadingDesign || loadingTopo;
  const hasNoData = !designVerts && !topoVerts;
  const [requested, setRequested] = useState(false);

  // Gate the Cesium import behind an explicit user action so the
  // 26 MB of Cesium JS + assets aren't fetched until the user
  // actually wants the 3D view. Saves >95% of the first-load
  // bandwidth for visitors who only want the 2D plan view.

  if (hasNoData) {
    return (
      <div data-slot="mesh-3d-viewer" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="text-3xl">🌐</div>
          <p className="text-sm text-center">Cargue superficies para ver la vista 3D</p>
        </div>
      </div>
    );
  }

  if (!requested) {
    return (
      <div data-slot="mesh-3d-viewer" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="text-5xl">🌍</div>
          <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
            Vista 3D con CesiumJS
          </p>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Descarga diferida: ~4 MB de JS + ~22 MB de assets (Workers, Widgets).
            Solo se carga cuando hacés clic.
          </p>
          <button
            onClick={() => setRequested(true)}
            className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue"
            style={{ backgroundColor: 'var(--color-mine-blue)', color: '#fff' }}
          >
            Cargar vista 3D
          </button>
        </div>
      </div>
    );
  }

  return (
    <div data-slot="mesh-3d-viewer" className="h-full min-h-[400px] w-full">
      {isLoading ? (
        <div className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
            <div className="animate-spin text-2xl">⏳</div>
            <p className="text-sm">Cargando vértices…</p>
          </div>
        </div>
      ) : (
        <CesiumViewerImpl
          designVerts={designVerts}
          topoVerts={topoVerts}
          sections={sections}
          selectedSection={selectedSection}
        />
      )}
    </div>
  );
}
