import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import {
  Viewer,
  Color,
  Cartesian3,
  PointPrimitiveCollection,
  PolylineCollection,
  SceneMode,
  Math as CesiumMath,
  EllipsoidTerrainProvider,
} from 'cesium';
import { useMeshVertices, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { SectionResponse, VerticesResponse } from '../../api/types';

// ── Constants ────────────────────────────────────────────────

const DESIGN_COLOR = Color.fromCssColorString('#3b82f6').withAlpha(0.85); // blue
const TOPO_COLOR = Color.fromCssColorString('#22c55e').withAlpha(0.85);   // green
const SECTION_COLOR = Color.fromCssColorString('#ef4444').withAlpha(0.9); // red
const POINT_PIXEL_SIZE = 3;

// ── Helpers ──────────────────────────────────────────────────

/** Compute section line endpoints in 3D (flat on ground at z=0). */
function sectionEndpoints(sec: SectionResponse): [Cartesian3, Cartesian3] {
  const azimuthRad = (sec.azimuth * Math.PI) / 180;
  const dx = Math.sin(azimuthRad) * sec.length;
  const dy = Math.cos(azimuthRad) * sec.length;
  return [
    new Cartesian3(sec.origin[0], sec.origin[1], 0),
    new Cartesian3(sec.origin[0] + dx, sec.origin[1] + dy, 0),
  ];
}

/** Find center of vertex data for camera positioning. */
function dataCenter(verts: VerticesResponse): Cartesian3 {
  const len = verts.x.length;
  if (len === 0) return Cartesian3.ZERO;
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < len; i++) {
    cx += verts.x[i];
    cy += verts.y[i];
    cz += verts.z[i];
  }
  return new Cartesian3(cx / len, cy / len, cz / len);
}

/** Compute bounding radius for camera offset. */
function boundingRadius(verts: VerticesResponse, center: Cartesian3): number {
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

// ── Component ────────────────────────────────────────────────

export function Mesh3DViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const pointsRef = useRef<PointPrimitiveCollection | null>(null);
  const linesRef = useRef<PolylineCollection | null>(null);

  const { designMeshId, topoMeshId } = useSession();
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();

  const [error, setError] = useState<string | null>(null);
  const isLoading = loadingDesign || loadingTopo;
  const hasNoData = !designVerts && !topoVerts;

  // ── Initialize CesiumJS viewer ──
  useEffect(() => {
    if (!containerRef.current) return;

    try {
      const viewer = new Viewer(containerRef.current, {
        // No ion token needed — use basic dark globe
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
        sceneMode: SceneMode.SCENE3D,
        // Dark background
        skyBox: false as unknown as undefined,
        skyAtmosphere: false as unknown as undefined,
      });

      // Remove default credit container clutter
      (viewer.cesiumWidget.creditContainer as HTMLElement).style.display = 'none';

      // Set dark background
      viewer.scene.backgroundColor = Color.fromCssColorString('#1e293b');

      // Use flat terrain — no Cesium ion needed
      viewer.terrainProvider = new EllipsoidTerrainProvider();

      // Create collections for points and lines
      const points = viewer.scene.primitives.add(new PointPrimitiveCollection());
      const lines = viewer.scene.primitives.add(new PolylineCollection());

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
  }, []);

  // ── Add mesh vertices to scene ──
  const addVertices = useCallback(
    (verts: VerticesResponse, color: Color) => {
      const points = pointsRef.current;
      if (!points) return;
      const len = verts.x.length;
      for (let i = 0; i < len; i++) {
        points.add({
          position: new Cartesian3(verts.x[i], verts.y[i], verts.z[i]),
          color,
          pixelSize: POINT_PIXEL_SIZE,
        });
      }
    },
    [],
  );

  // ── Update points when data changes ──
  useEffect(() => {
    const points = pointsRef.current;
    if (!points) return;

    // Clear previous points
    points.removeAll();

    if (designVerts && designVerts.x.length > 0) {
      addVertices(designVerts, DESIGN_COLOR);
    }
    if (topoVerts && topoVerts.x.length > 0) {
      addVertices(topoVerts, TOPO_COLOR);
    }
  }, [designVerts, topoVerts, addVertices]);

  // ── Update section lines when data changes ──
  useEffect(() => {
    const lines = linesRef.current;
    if (!lines || !sections || sections.length === 0) return;

    lines.removeAll();

    for (const sec of sections) {
      const [start, end] = sectionEndpoints(sec);
      lines.add({
        positions: [start, end],
        width: 2,
        color: SECTION_COLOR,
      });
    }
  }, [sections]);

  // ── Camera: auto-fit to data bounds ──
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
    const viewer = viewerRef.current;
    if (!viewer || !combinedVerts || combinedVerts.x.length === 0) return;

    const center = dataCenter(combinedVerts);
    const radius = boundingRadius(combinedVerts, center);
    const offset = Math.max(radius * 2.5, 50);

    viewer.camera.flyTo({
      destination: new Cartesian3(
        center.x + offset * 0.5,
        center.y - offset * 0.5,
        center.z + offset * 0.8,
      ),
      orientation: {
        heading: CesiumMath.toRadians(30),
        pitch: CesiumMath.toRadians(-30),
        roll: 0,
      },
      duration: 1.5,
    });
  }, [combinedVerts]);

  // ── Error state ──
  if (error) {
    return (
      <div
        data-slot="mesh-3d-viewer"
        className="flex items-center justify-center h-full min-h-[400px] bg-slate-900 rounded-xl border border-slate-700"
      >
        <div className="flex flex-col items-center gap-3 text-red-400">
          <div className="text-3xl">⚠️</div>
          <p className="text-sm text-center px-4">{error}</p>
        </div>
      </div>
    );
  }

  // ── Loading state ──
  if (isLoading) {
    return (
      <div
        data-slot="mesh-3d-viewer"
        className="flex items-center justify-center h-full min-h-[400px] bg-slate-900 rounded-xl border border-slate-700"
      >
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">Cargando vista 3D…</p>
        </div>
      </div>
    );
  }

  // ── No data state ──
  if (hasNoData) {
    return (
      <div
        data-slot="mesh-3d-viewer"
        className="flex items-center justify-center h-full min-h-[400px] bg-slate-900 rounded-xl border border-slate-700"
      >
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <div className="text-3xl">🌐</div>
          <p className="text-sm text-center">
            Cargue superficies para ver la vista 3D
          </p>
        </div>
      </div>
    );
  }

  // ── 3D Viewer ──
  return (
    <div
      data-slot="mesh-3d-viewer"
      className="h-full min-h-[400px] w-full rounded-xl overflow-hidden border border-slate-700"
    >
      <div ref={containerRef} className="w-full h-full" style={{ minHeight: '400px' }} />
    </div>
  );
}
