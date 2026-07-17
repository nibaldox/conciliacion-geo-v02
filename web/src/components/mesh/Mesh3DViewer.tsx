import { useEffect, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls, GizmoHelper, GizmoViewport } from '@react-three/drei';
import * as THREE from 'three';
import { useMeshVertices, useMeshBreaklines, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { SectionResponse, VerticesResponse, ContourData } from '../../api/types';

const DESIGN_HEX = '#7693b7'; // steel blue
const TOPO_HEX = '#cccccc';   // grey
const SECTION_HEX = '#e83149'; // red
const SELECTED_SECTION_HEX = '#f43f5e'; // bright pink-red

interface Bounds3D {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
  zmin: number;
  zmax: number;
  centerX: number;
  centerY: number;
  centerZ: number;
  maxDim: number;
}

function calculateBounds(topo: VerticesResponse | undefined, design: VerticesResponse | undefined): Bounds3D {
  let xmin = Infinity, xmax = -Infinity;
  let ymin = Infinity, ymax = -Infinity;
  let zmin = Infinity, zmax = -Infinity;

  const processVerts = (verts: VerticesResponse | undefined) => {
    if (!verts) return;
    const len = verts.x.length;
    for (let i = 0; i < len; i++) {
      const x = verts.x[i]!;
      const y = verts.y[i]!;
      const z = verts.z[i]!;
      if (x < xmin) xmin = x;
      if (x > xmax) xmax = x;
      if (y < ymin) ymin = y;
      if (y > ymax) ymax = y;
      if (z < zmin) zmin = z;
      if (z > zmax) zmax = z;
    }
  };

  processVerts(topo);
  processVerts(design);

  const cx = isFinite(xmin) ? (xmin + xmax) / 2 : 0;
  const cy = isFinite(ymin) ? (ymin + ymax) / 2 : 0;
  const cz = isFinite(zmin) ? (zmin + zmax) / 2 : 0;
  const dx = isFinite(xmax) ? xmax - xmin : 100;
  const dy = isFinite(ymax) ? ymax - ymin : 100;
  const dz = isFinite(zmax) ? zmax - zmin : 100;
  const maxDim = Math.max(dx, dy, dz);

  return {
    xmin, xmax, ymin, ymax, zmin, zmax,
    centerX: cx,
    centerY: cy,
    centerZ: cz,
    maxDim: isFinite(maxDim) && maxDim > 0 ? maxDim : 100,
  };
}

// ─── Camera Controller Component ──────────────────────────────

function CameraController({ maxDim }: { maxDim: number }) {
  const { camera } = useThree();

  useEffect(() => {
    // Position camera diagonally looking at the centered origin (0, 0, 0)
    camera.position.set(maxDim * 1.0, maxDim * 0.8, maxDim * 1.0);
    camera.lookAt(0, 0, 0);
    camera.far = maxDim * 10;
    camera.updateProjectionMatrix();
  }, [camera, maxDim]);

  return null;
}

// ─── 3D Scene Component ───────────────────────────────────────

interface SceneProps {
  topoVerts: VerticesResponse | undefined;
  designContours: ContourData | undefined;
  sections: SectionResponse[] | undefined;
  selectedSection: string | null;
  bounds: Bounds3D;
  layers: {
    topo: boolean;
    designContours: boolean;
    sections: boolean;
  };
}

function Scene({
  topoVerts,
  designContours,
  sections,
  selectedSection,
  bounds,
  layers,
}: SceneProps) {
  const mapClickHandler = useSession((s) => s.mapClickHandler);
  const selectedCurveId = useSession((s) => s.selectedCurveId);
  const selectedCurvePoints = useSession((s) => s.selectedCurvePoints);
  const { raycaster } = useThree();

  useEffect(() => {
    if (raycaster?.params?.Line) {
      raycaster.params.Line.threshold = 5; // increase threshold for easier clicking
    }
  }, [raycaster]);

  // 1. Topography Solid Mesh or Point Cloud Geometry
  const topoGeometry = useMemo(() => {
    if (!topoVerts || topoVerts.x.length === 0) return null;
    const count = topoVerts.x.length;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      // Coordinate mapping: Three.js X=East, Y=Elevation, Z=-North
      positions[i * 3] = topoVerts.x[i]! - bounds.centerX;
      positions[i * 3 + 1] = topoVerts.z[i]! - bounds.centerZ;
      positions[i * 3 + 2] = -(topoVerts.y[i]! - bounds.centerY);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    if (topoVerts.faces && topoVerts.faces.length > 0) {
      const indices = new Uint32Array(topoVerts.faces.flat());
      geo.setIndex(new THREE.BufferAttribute(indices, 1));
      geo.computeVertexNormals();
    }

    return geo;
  }, [topoVerts, bounds]);

  // Clean up geometries to prevent WebGL Context Loss (Memory Leak)
  useEffect(() => {
    return () => {
      if (topoGeometry) topoGeometry.dispose();
    };
  }, [topoGeometry]);

  // 2. Design Contour Lines Geometry
  const designLinesGeometries = useMemo(() => {
    if (!designContours || !designContours.lines) return [];
    
    const geometries: {
      id: string;
      elevIdx: number;
      segIdx: number;
      geo: THREE.BufferGeometry;
      color: string;
    }[] = [];

    designContours.lines.forEach((line, elevIdx) => {
      const isCrest = line.type === 'crest';
      const isToe = line.type === 'toe';
      const color = isCrest ? '#3b82f6' : isToe ? '#10b981' : '#ef4444';

      line.segments.forEach((segment, segIdx) => {
        const id = `${elevIdx}-${segIdx}`;
        const positions = new Float32Array(segment.length * 3);
        
        for (let i = 0; i < segment.length; i++) {
          const p = segment[i]!;
          const z = p.length > 2 ? p[2] : line.elevation;
          
          positions[i * 3] = p[0] - bounds.centerX;
          positions[i * 3 + 1] = z - bounds.centerZ;
          positions[i * 3 + 2] = -(p[1] - bounds.centerY);
        }
        
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        
        geometries.push({ id, elevIdx, segIdx, geo, color });
      });
    });

    return geometries;
  }, [designContours, bounds]);

  useEffect(() => {
    return () => {
      designLinesGeometries.forEach(item => item.geo.dispose());
    };
  }, [designLinesGeometries]);

  // 3. Section Lines Geometries — sampled at topo elevation
  const sectionsData = useMemo(() => {
    if (!sections || sections.length === 0) return [];

    // Build a fast elevation lookup from topo vertices (X, Y in world → Z elev)
    const topoElevation = (wx: number, wy: number): number => {
      if (!topoVerts || topoVerts.x.length === 0) return 0;
      let bestDist = Infinity;
      let bestZ = 0;
      const n = topoVerts.x.length;
      // Sample up to 50_000 vertices for speed on large meshes
      const stride = Math.max(1, Math.floor(n / 50_000));
      for (let i = 0; i < n; i += stride) {
        const vx = topoVerts.x[i]!;
        const vy = topoVerts.y[i]!;
        const d = (vx - wx) ** 2 + (vy - wy) ** 2;
        if (d < bestDist) {
          bestDist = d;
          bestZ = topoVerts.z[i]!;
        }
      }
      return bestZ;
    };

    // Vertical offset so lines float visibly above the surface
    const LIFT = bounds.maxDim * 0.004;

    return sections.map((sec) => {
      const azimuthRad = (sec.azimuth * Math.PI) / 180;
      const dx = Math.sin(azimuthRad) * sec.length;
      const dy = Math.cos(azimuthRad) * sec.length;

      const wx0 = sec.origin[0];
      const wy0 = sec.origin[1];
      
      // Sample every 2 meters to drape the line geometrically
      const numPoints = Math.max(2, Math.ceil(sec.length / 2) + 1);
      const positions = new Float32Array(numPoints * 3);

      for (let i = 0; i < numPoints; i++) {
        const t = i / (numPoints - 1);
        const wx = wx0 + dx * t;
        const wy = wy0 + dy * t;
        
        const px = wx - bounds.centerX;
        const pz = -(wy - bounds.centerY);
        const py = topoElevation(wx, wy) - bounds.centerZ + LIFT;
        
        positions[i * 3] = px;
        positions[i * 3 + 1] = py;
        positions[i * 3 + 2] = pz;
      }

      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const line = new THREE.Line(geo);

      return { name: sec.name, line };
    });
  }, [sections, bounds, topoVerts]);

  useEffect(() => {
    return () => {
      sectionsData.forEach(item => {
        if (item.line.geometry) item.line.geometry.dispose();
      });
    };
  }, [sectionsData]);

  // 4. Selected Curve Points
  const selectedPointsGeo = useMemo(() => {
    if (!selectedCurvePoints || selectedCurvePoints.length === 0) return null;
    
    const positions = new Float32Array(selectedCurvePoints.length * 3);
    let valid = false;
    
    selectedCurvePoints.forEach((pt, i) => {
      if (!designContours || !designContours.lines) return;
      const parts = pt.curveId.split('-');
      const elevIdx = parseInt(parts[0], 10);
      const segIdx = parseInt(parts[1], 10);
      
      const line = designContours.lines[elevIdx];
      if (!line) return;
      const segment = line.segments[segIdx];
      if (!segment) return;
      const p = segment[pt.pointIndex];
      if (!p) return;
      
      const z = p.length > 2 ? p[2] : line.elevation;
      
      positions[i * 3] = p[0] - bounds.centerX;
      positions[i * 3 + 1] = z - bounds.centerZ;
      positions[i * 3 + 2] = -(p[1] - bounds.centerY);
      valid = true;
    });
    
    if (!valid) return null;
    
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return geo;
  }, [selectedCurvePoints, designContours, bounds]);

  useEffect(() => {
    return () => {
      if (selectedPointsGeo) selectedPointsGeo.dispose();
    };
  }, [selectedPointsGeo]);

  return (
    <>
      <color attach="background" args={['#111111']} />
      <ambientLight intensity={0.25} />
      <directionalLight position={[1, 0.6, 0.5]} intensity={1.2} />
      <directionalLight position={[-1, 0.4, -0.5]} intensity={0.4} />
      
      {/* Grid helper positioned at the base of our centered mesh */}
      <gridHelper args={[bounds.maxDim * 3, 50, '#334155', '#1e293b']} position={[0, -bounds.maxDim * 0.1, 0]} />

      {/* Real Topography Solid Mesh or Point Cloud */}
      {layers.topo && topoGeometry && (
        topoGeometry.index ? (
          <mesh geometry={topoGeometry}>
            <meshStandardMaterial
              color={TOPO_HEX}
              roughness={0.8}
              metalness={0.1}
              side={THREE.DoubleSide}
            />
          </mesh>
        ) : (
          <points geometry={topoGeometry}>
            <pointsMaterial color={TOPO_HEX} size={3} sizeAttenuation={false} transparent opacity={0.8} />
          </points>
        )
      )}

      {/* Design 3D Contour Lines */}
      {layers.designContours && designLinesGeometries.map(item => {
        const isSelected = selectedCurveId === item.id;
        const opacity = selectedCurveId ? (isSelected ? 1.0 : 0.2) : 0.9;
        
        return (
          <line
            key={item.id}
            {...{ geometry: item.geo } as any}
            onClick={(e: { stopPropagation: () => void; index?: number; point: { x: number; z: number } }) => {
              e.stopPropagation();
              if (mapClickHandler) {
                const vertexIndex = e.index;
                const point = e.point;
                const worldX = point.x + bounds.centerX;
                const worldY = -point.z + bounds.centerY; // Since z was inverted
                
                mapClickHandler(worldX, worldY, item.id, vertexIndex);
              }
            }}
          >
            <lineBasicMaterial color={item.color} linewidth={isSelected ? 3 : 2} transparent opacity={opacity} />
          </line>
        );
      })}

      {/* Selected Points */}
      {selectedPointsGeo && (
        <points geometry={selectedPointsGeo}>
          <pointsMaterial color="yellow" size={10} sizeAttenuation={false} depthTest={false} />
        </points>
      )}

      {/* Section Lines */}
      {layers.sections && sectionsData.map((sec) => {
        const isSelected = selectedSection === sec.name;
        return (
          <primitive key={sec.name} object={sec.line}>
            <lineBasicMaterial
              color={isSelected ? SELECTED_SECTION_HEX : SECTION_HEX}
              linewidth={isSelected ? 3 : 1}
              transparent
              opacity={isSelected ? 1.0 : 0.45}
              attach="material"
            />
          </primitive>
        );
      })}
    </>
  );
}

// ─── Main Exported Component (3D Viewport) ─────────────────────

export function Mesh3DViewer() {
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const selectedSection = useSession((s) => s.selectedSection);
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { data: designContours, isLoading: loadingContours } = useMeshBreaklines(designMeshId);
  const { data: sections } = useSections();
  const { t } = useTranslation();

  const isLoading = loadingDesign || loadingTopo || loadingContours;
  const hasNoData = !designVerts && !topoVerts;

  const [layers, setLayers] = useState({
    topo: true,
    designContours: true,
    sections: true,
  });

  const bounds = useMemo(() => {
    return calculateBounds(topoVerts, designVerts);
  }, [topoVerts, designVerts]);

  if (hasNoData) {
    return (
      <div data-slot="mesh-3d-viewer" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="text-3xl">🌐</div>
          <p className="text-sm text-center">{t('step1.view3d_no_data')}</p>
        </div>
      </div>
    );
  }

  return (
    <div data-slot="mesh-3d-viewer" className="h-full min-h-[400px] w-full relative rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
      {isLoading ? (
        <div className="flex items-center justify-center h-full min-h-[400px]" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
            <div className="animate-spin text-2xl">⏳</div>
            <p className="text-sm">{t('step1.view3d_loading_verts')}</p>
          </div>
        </div>
      ) : (
        <>
          {/* Floating Layer Selector */}
          <div
            className="absolute top-4 right-4 z-20 p-3 rounded-lg glass-card flex flex-col gap-2 border text-[10px] font-mono select-none"
            style={{
              backgroundColor: 'rgba(11, 15, 25, 0.85)',
              borderColor: 'var(--color-border-strong)',
              boxShadow: 'var(--shadow-glow-accent)',
            }}
          >
            <span className="font-semibold uppercase tracking-wider text-accent-bright mb-1 border-b border-border pb-1">
              {t('viewer.layers', { defaultValue: 'CAPAS VISIBLES' })}
            </span>
            <label className="flex items-center gap-2 cursor-pointer hover:text-white transition-colors">
              <input
                type="checkbox"
                checked={layers.topo}
                onChange={(e) => setLayers(prev => ({ ...prev, topo: e.target.checked }))}
                className="rounded border-border bg-surface-muted text-gray-500 focus:ring-0 focus:ring-offset-0 w-3 h-3 cursor-pointer animate-none"
              />
              <span style={{ color: TOPO_HEX }}>●</span>
              <span>{t('viewer.layer_topo', { defaultValue: 'Topografía Real' })}</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer hover:text-white transition-colors">
              <input
                type="checkbox"
                checked={layers.designContours}
                onChange={(e) => setLayers(prev => ({ ...prev, designContours: e.target.checked }))}
                className="rounded border-border bg-surface-muted text-mine-blue focus:ring-0 focus:ring-offset-0 w-3 h-3 cursor-pointer animate-none"
              />
              <span style={{ color: DESIGN_HEX }}>●</span>
              <span>{t('viewer.layer_design', { defaultValue: 'Curvas de Diseño' })}</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer hover:text-white transition-colors">
              <input
                type="checkbox"
                checked={layers.sections}
                onChange={(e) => setLayers(prev => ({ ...prev, sections: e.target.checked }))}
                className="rounded border-border bg-surface-muted text-red-500 focus:ring-0 focus:ring-offset-0 w-3 h-3 cursor-pointer animate-none"
              />
              <span style={{ color: SECTION_HEX }}>●</span>
              <span>{t('viewer.layer_sections', { defaultValue: 'Líneas de Sección' })}</span>
            </label>
          </div>

          {/* R3F WebGL Canvas */}
          <div className="w-full h-full" style={{ minHeight: '400px' }}>
            <Canvas
              camera={{ fov: 50, near: 1, far: 50000 }}
              gl={{ antialias: true, preserveDrawingBuffer: true }}
            >
              <CameraController maxDim={bounds.maxDim} />
              <OrbitControls makeDefault />
              <Scene
                topoVerts={topoVerts}
                designContours={designContours}
                sections={sections}
                selectedSection={selectedSection}
                bounds={bounds}
                layers={layers}
              />
              <GizmoHelper alignment="bottom-left" margin={[60, 60]}>
                <GizmoViewport
                  axisColors={['#ff3653', '#0adb21', '#2c8fdf']}
                  labelColor="white"
                  labels={['E', 'Z', 'N']}
                />
              </GizmoHelper>
            </Canvas>
          </div>
        </>
      )}
    </div>
  );
}
