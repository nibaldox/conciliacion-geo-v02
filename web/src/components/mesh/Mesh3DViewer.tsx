import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { Html, OrbitControls, GizmoHelper, GizmoViewport } from '@react-three/drei';
import * as THREE from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { ViewerCameraControls } from './ViewerCameraControls';
import { cameraView, defaultCameraToggles, toggleCameraOption, isPivotClick, type CameraOption, type CameraView } from './viewerCameraState';
import { useMeshVertices, useMeshBreaklines, useSections, useResults, useHorizontalDeviationMesh } from '../../api/hooks';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import type { SectionResponse, VerticesResponse, ContourData, HorizontalDeviationMeshResponse } from '../../api/types';
import { useTheme } from '../../stores/theme';
import { readThemeColor } from '../../utils/theme';
import { expandHorizontalDeviationFaces, getHorizontalDeviationColor } from '../../utils/horizontalDeviation';
import { horizontalDeviationError, horizontalDeviationWarning } from '../../utils/horizontalDeviationMessages';
import { HorizontalDeviationLegend } from '../results/HorizontalDeviationLegend';
import { HorizontalDeviationOverview } from '../results/HorizontalDeviationOverview';
import { getCurveGeometrySnapshot } from '../sections/curveGeometryAdapter';
import {
  computeCurveSearchBounds,
  createCurveSceneClickHandler,
  createCurveScenePreviewHandler,
  getCurveSearchThreshold,
  hasCurvePreviewViewChanged,
} from './curveScenePicking';
import type { CurvePreviewViewSnapshot } from './curveScenePicking';
import { buildCurveSelectionVisuals, type RenderPoint3D } from './curveSelectionVisuals';
import { resolveCurveContextAction } from './curveContextSync';
import type { CurveAnchor, CurveSelectionContext } from '../sections/curveSelectionState';
import type { MiningPoint3D } from '../sections/curveSelectionTypes';
import { BlastHolesLayer } from './BlastHolesLayer';
import { BlastHoleFilters, type BlastHole3DRecord } from './BlastHoleFilters';
import { useBlastHoles3D } from './useBlastHoles3D';
import { getSectionExtent } from './sectionExtent';
import { buildTopoHeightIndex, heightAt } from './topoSurfaceHeight';
import { BlastHoleColorControls } from './BlastHoleColorControls';
import { Spinner } from '../ui/Spinner';
import { BlastHoleColorLegendView } from './BlastHoleColorLegend';
import type { BlastHoleColorLegend, BlastHoleColorMapping } from './blastHoleColors';
import { createBlastViewContextKey, useBlastView, type BlastColorTarget } from '../../stores/blastView';

const DESIGN_HEX = '#7693b7'; // steel blue
const TOPO_HEX = '#cccccc';   // grey
const SECTION_HEX = '#e83149'; // red
const SELECTED_SECTION_HEX = '#f43f5e'; // bright pink-red
const EMPTY_BLAST_HOLES: readonly BlastHole3DRecord[] = [];

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
  colors: { background: string; topo: string; grid: string; minorGrid: string };
  topoVerts: VerticesResponse | undefined;
  topoOpacity: number;
  horizontalDeviation: HorizontalDeviationMeshResponse | undefined;
  showHorizontalDeviation: boolean;
  designContours: ContourData | undefined;
  sections: SectionResponse[] | undefined;
  selectedSection: string | null;
  bounds: Bounds3D;
  showGrid: boolean;
  pickingPivot: boolean;
  onPivot: (point: THREE.Vector3) => void;
  layers: {
    topo: boolean;
    designContours: boolean;
    sections: boolean;
  };
}

function Scene({
  colors,
  topoVerts,
  topoOpacity,
  horizontalDeviation,
  showHorizontalDeviation,
  designContours,
  sections,
  selectedSection,
  bounds,
  showGrid,
  pickingPivot,
  onPivot,
  layers,
}: SceneProps) {
  const { t } = useTranslation();
  const mapClickHandler = useSession((s) => s.mapClickHandler);
  const curveSelection = useSession((s) => s.curveSelection);
  const dispatchCurveSelection = useSession((s) => s.dispatchCurveSelection);
  const designMeshId = useSession((s) => s.designMeshId);
  const isDark = useTheme((s) => s.isDark);
  const { raycaster, camera, size, gl } = useThree();

  const topoMeshRef = useRef<THREE.Mesh>(null);
  const deviationMeshRef = useRef<THREE.Mesh>(null);
  const previewRef = useRef<THREE.Points>(null);

  useEffect(() => {
    if (!pickingPivot) return;
    const canvas = gl.domElement;
    const previousCursor = canvas.style.cursor;
    canvas.style.cursor = 'crosshair';
    let start: [number, number] | null = null;
    let dragged = false;
    const down = (event: PointerEvent) => {
      if (event.button !== 0) return;
      start = [event.clientX, event.clientY];
      dragged = false;
    };
    const move = (event: PointerEvent) => {
      if (start && !isPivotClick(start, [event.clientX, event.clientY])) dragged = true;
    };
    const up = (event: PointerEvent) => {
      if (!start || event.button !== 0) return;
      const click = !dragged && isPivotClick(start, [event.clientX, event.clientY]);
      start = null;
      const mesh = topoMeshRef.current;
      if (!click || !mesh || !layers.topo) return;
      const rect = canvas.getBoundingClientRect();
      const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      const picker = new THREE.Raycaster();
      picker.setFromCamera(pointer, camera);
      const hit = picker.intersectObject(mesh, false)[0];
      if (hit) onPivot(hit.point);
    };
    const cancel = () => { start = null; };
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', cancel);
    return () => {
      canvas.style.cursor = previousCursor;
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      canvas.removeEventListener('pointercancel', cancel);
    };
  }, [camera, gl, layers.topo, onPivot, pickingPivot]);

  useFrame(() => {
    if (raycaster.params.Line) {
      raycaster.params.Line.threshold = getCurveSearchThreshold(camera, size.height, undefined, curveSearchBounds) ?? 0;
    }
    const preview = previewRef.current;
    if (preview === null || !preview.visible) return;
    if (hasCurvePreviewViewChanged(previewViewSnapshot, camera, size)) {
      preview.visible = false;
    }
  });


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

  const horizontalDeviationGeometry = useMemo(() => {
    if (!showHorizontalDeviation || !horizontalDeviation) return null;
    const triangles = expandHorizontalDeviationFaces(horizontalDeviation);
    if (triangles.length === 0) return null;
    const positions: number[] = [];
    const vertexColors: number[] = [];
    for (const triangle of triangles) {
      const color = new THREE.Color(getHorizontalDeviationColor(triangle.category));
      for (const [x, y, z] of triangle.vertices) {
        positions.push(x - bounds.centerX, z - bounds.centerZ, -(y - bounds.centerY));
        vertexColors.push(color.r, color.g, color.b);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(vertexColors, 3));
    geometry.computeVertexNormals();
    return geometry;
  }, [showHorizontalDeviation, horizontalDeviation, bounds, colors]);

  // Clean up geometries to prevent WebGL Context Loss (Memory Leak)
  useEffect(() => {
    return () => {
      if (topoGeometry) topoGeometry.dispose();
    };
  }, [topoGeometry]);

  useEffect(() => {
    return () => {
      if (horizontalDeviationGeometry) horizontalDeviationGeometry.dispose();
    };
  }, [horizontalDeviationGeometry]);

  const curveSnapshot = useMemo(
    () => getCurveGeometrySnapshot(designMeshId, designContours),
    [designMeshId, designContours],
  );

  const publishedCurveContextRef = useRef<CurveSelectionContext | null>(null);
  useEffect(() => {
    const nextContext = curveSnapshot ? curveSnapshot.context : null;
    const action = resolveCurveContextAction(publishedCurveContextRef.current, nextContext);
    publishedCurveContextRef.current = nextContext;
    if (action !== null) dispatchCurveSelection(action);
  }, [curveSnapshot, dispatchCurveSelection]);

  const curveCenter = useMemo<MiningPoint3D>(
    () => [bounds.centerX, bounds.centerY, bounds.centerZ],
    [bounds.centerX, bounds.centerY, bounds.centerZ],
  );
  const curveSearchBounds = useMemo(
    () => (curveSnapshot === null ? null : computeCurveSearchBounds(curveSnapshot, curveCenter)),
    [curveSnapshot, curveCenter],
  );
  const curveSelectionVisuals = useMemo(
    () => buildCurveSelectionVisuals({
      snapshot: curveSnapshot,
      selection: curveSelection,
      center: curveCenter,
    }),
    [curveSnapshot, curveSelection, curveCenter],
  );
  const rangeColor = useMemo(() => readThemeColor('--color-mine-yellow', 'orange'), [isDark]);
  const startColor = useMemo(() => readThemeColor('--color-mine-green', 'green'), [isDark]);
  const endColor = useMemo(() => readThemeColor('--color-mine-red', 'red'), [isDark]);
  const rangeLine = useMemo(() => {
    const positions = curveSelectionVisuals.rangePositions;
    if (!positions || positions.length === 0) return null;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const line = new THREE.Line(geometry);
    line.name = 'curve-selection-range';
    line.userData = { role: 'range' };
    line.frustumCulled = false;
    return line;
  }, [curveSelectionVisuals.rangePositions]);
  const startMarkerGeometry = useMemo(
    () => createPointGeometry(curveSelectionVisuals.start),
    [curveSelectionVisuals.start],
  );
  const endMarkerGeometry = useMemo(
    () => createPointGeometry(curveSelectionVisuals.end),
    [curveSelectionVisuals.end],
  );
  useEffect(() => {
    return () => {
      if (rangeLine) rangeLine.geometry.dispose();
    };
  }, [rangeLine]);
  useEffect(() => {
    return () => {
      if (startMarkerGeometry) startMarkerGeometry.dispose();
    };
  }, [startMarkerGeometry]);
  useEffect(() => {
    return () => {
      if (endMarkerGeometry) endMarkerGeometry.dispose();
    };
  }, [endMarkerGeometry]);
  const curveCanvas = useMemo(
    () => ({ getBoundingClientRect: () => gl.domElement.getBoundingClientRect() }),
    [gl],
  );
  const getCurveOccluders = useCallback((): THREE.Object3D[] => {
    const occluders: THREE.Object3D[] = [];
    if (topoMeshRef.current) occluders.push(topoMeshRef.current);
    if (showHorizontalDeviation && deviationMeshRef.current) occluders.push(deviationMeshRef.current);
    return occluders;
  }, [showHorizontalDeviation]);

  const curveClickHandler = useMemo(() => (
    curveSnapshot
      ? createCurveSceneClickHandler({
          snapshot: curveSnapshot,
          selectedCurveId: curveSelection.curveId,
          camera,
          center: curveCenter,
          canvas: curveCanvas,
          getOccluders: getCurveOccluders,
          onPick: mapClickHandler,
        })
      : null
  ), [curveSnapshot, curveSelection.curveId, camera, curveCenter, curveCanvas, getCurveOccluders, mapClickHandler]);

  const previewAttribute = useMemo(() => new THREE.BufferAttribute(new Float32Array(3), 3), []);
  const previewGeometry = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', previewAttribute);
    return geometry;
  }, [previewAttribute]);
  const { snapshot: previewViewSnapshot, viewport: previewViewportSnapshot } = useMemo(() => {
    const viewport = { width: 0, height: 0 };
    const snapshot: CurvePreviewViewSnapshot = {
      position: new THREE.Vector3(),
      quaternion: new THREE.Quaternion(),
      projection: new THREE.Matrix4(),
      viewport,
    };
    return { snapshot, viewport };
  }, []);

  const hideCurvePreview = useCallback(() => {
    const preview = previewRef.current;
    if (preview) preview.visible = false;
  }, []);

  const applyCurvePreview = useCallback((anchor: CurveAnchor | null) => {
    const preview = previewRef.current;
    if (!preview) return;
    const state = useSession.getState();
    if (
      anchor === null
      || state.designMeshId !== designMeshId
      || state.mapClickHandler !== mapClickHandler
      || state.curveSelection !== curveSelection
    ) {
      preview.visible = false;
      return;
    }
    previewAttribute.setXYZ(
      0,
      anchor.position[0] - bounds.centerX,
      anchor.position[2] - bounds.centerZ,
      -(anchor.position[1] - bounds.centerY),
    );
    previewAttribute.needsUpdate = true;
    preview.visible = true;
    previewViewSnapshot.position.copy(camera.position);
    previewViewSnapshot.quaternion.copy(camera.quaternion);
    previewViewSnapshot.projection.copy(camera.projectionMatrix);
    previewViewportSnapshot.width = size.width;
    previewViewportSnapshot.height = size.height;
  }, [mapClickHandler, designMeshId, curveSelection, bounds, camera, size, previewAttribute, previewViewSnapshot, previewViewportSnapshot]);

  const curvePreviewHandler = useMemo(() => (
    curveSnapshot
      ? createCurveScenePreviewHandler(
          {
            snapshot: curveSnapshot,
            selectedCurveId: curveSelection.curveId,
            camera,
            center: curveCenter,
            canvas: curveCanvas,
            getOccluders: getCurveOccluders,
            onPick: mapClickHandler,
          },
          applyCurvePreview,
        )
      : null
  ), [curveSnapshot, curveSelection.curveId, camera, curveCenter, curveCanvas, getCurveOccluders, mapClickHandler, applyCurvePreview]);

  useEffect(() => {
    return () => {
      previewGeometry.dispose();
    };
  }, [previewGeometry]);

  useEffect(() => {
    if (!layers.designContours) hideCurvePreview();
  }, [layers.designContours, hideCurvePreview]);

  useEffect(() => {
    return hideCurvePreview;
  }, [curveSelection, designMeshId, mapClickHandler, curveSnapshot, hideCurvePreview]);

  // 2. Design Contour Lines Geometry
  const designLinesGeometries = useMemo(() => {
    if (!curveSnapshot) return [];

    const geometries: {
      id: string;
      geo: THREE.BufferGeometry;
      color: string;
    }[] = [];

    curveSnapshot.curves.forEach((curve) => {
      const isCrest = curve.type === 'crest';
      const isToe = curve.type === 'toe';
      const color = isCrest ? '#3b82f6' : isToe ? '#10b981' : '#ef4444';

      const positions = new Float32Array(curve.points.length * 3);
      for (let i = 0; i < curve.points.length; i++) {
        const p = curve.points[i]!;
        positions[i * 3] = p[0] - bounds.centerX;
        positions[i * 3 + 1] = p[2] - bounds.centerZ;
        positions[i * 3 + 2] = -(p[1] - bounds.centerY);
      }

      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometries.push({ id: curve.id, geo, color });
    });

    return geometries;
  }, [curveSnapshot, bounds]);

  useEffect(() => {
    return () => {
      designLinesGeometries.forEach(item => item.geo.dispose());
    };
  }, [designLinesGeometries]);

  // 3. Section Lines Geometries — sampled at topo elevation
  const topoHeightIndex = useMemo(() => topoVerts ? buildTopoHeightIndex(topoVerts) : null, [topoVerts]);
  const sectionsData = useMemo(() => {
    if (!sections || sections.length === 0) return [];

    const topoElevation = (wx: number, wy: number): number => topoHeightIndex ? heightAt(topoHeightIndex, wx, wy) : 0;

    // Vertical offset so lines float visibly above the surface
    const LIFT = 0.2;

    return sections.map((sec) => {
      const { start, end } = getSectionExtent(sec);
      
      // Sample every 2 meters to drape the line geometrically
      const numPoints = Math.max(2, Math.ceil(sec.length / 2) + 1);
      const positions = new Float32Array(numPoints * 3);

      for (let i = 0; i < numPoints; i++) {
        const t = i / (numPoints - 1);
        const wx = start[0] + (end[0] - start[0]) * t;
        const wy = start[1] + (end[1] - start[1]) * t;
        
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

      return { id: sec.id, name: sec.name, line };
    });
  }, [sections, bounds, topoHeightIndex]);

  useEffect(() => {
    return () => {
      sectionsData.forEach(item => {
        if (item.line.geometry) item.line.geometry.dispose();
      });
    };
  }, [sectionsData]);


  return (
    <>
      <color attach="background" args={[colors.background]} />
      <ambientLight intensity={0.25} />
      <directionalLight position={[1, 0.6, 0.5]} intensity={1.2} />
      <directionalLight position={[-1, 0.4, -0.5]} intensity={0.4} />
      
      {/* Grid helper positioned at the base of our centered mesh */}
      {showGrid && <gridHelper args={[bounds.maxDim * 3, 50, colors.grid, colors.minorGrid]} position={[0, -bounds.maxDim * 0.1, 0]} />}

      {/* Real Topography Solid Mesh or Point Cloud */}
      {layers.topo && topoGeometry && (
        topoGeometry.index ? (
          <mesh ref={topoMeshRef} geometry={topoGeometry}>
            <meshStandardMaterial
              color={colors.topo}
              roughness={0.8}
              metalness={0.1}
              side={THREE.DoubleSide}
              transparent={topoOpacity < 1}
              opacity={topoOpacity}
              depthWrite={topoOpacity === 1}
            />
          </mesh>
        ) : (
          <points geometry={topoGeometry}>
            <pointsMaterial color={colors.topo} size={3} sizeAttenuation={false} transparent opacity={0.8 * topoOpacity} depthWrite={topoOpacity === 1} />
          </points>
        )
      )}

      {showHorizontalDeviation && horizontalDeviationGeometry && (
        <mesh ref={deviationMeshRef} geometry={horizontalDeviationGeometry}>
          <meshStandardMaterial
            vertexColors
            roughness={0.8}
            metalness={0}
            side={THREE.DoubleSide}
            polygonOffset
            polygonOffsetFactor={-1}
            polygonOffsetUnits={-1}
          />
        </mesh>
      )}

      {/* Design 3D Contour Lines */}
      {layers.designContours && designLinesGeometries.map(item => {
        const isSelected = curveSelection.curveId === item.id;
        const opacity = curveSelection.curveId ? (isSelected ? 1.0 : 0.2) : 0.9;
        
        return (
          <line
            key={item.id}
            {...{ geometry: item.geo } as any}
            userData={{ curveId: item.id }}
            onClick={
              curveClickHandler
                ? (e: ThreeEvent<MouseEvent>) => {
                    curveClickHandler(e);
                  }
                : undefined
            }
            onPointerMove={
              curvePreviewHandler
                ? (e: ThreeEvent<PointerEvent>) => {
                    curvePreviewHandler(e);
                  }
                : undefined
            }
            onPointerOut={curvePreviewHandler ? hideCurvePreview : undefined}
          >
            <lineBasicMaterial color={item.color} linewidth={isSelected ? 3 : 2} transparent opacity={opacity} />
          </line>
        );
      })}

      {layers.designContours && rangeLine && (
        <primitive object={rangeLine}>
          <lineBasicMaterial
            attach="material"
            color={rangeColor}
            linewidth={3}
            transparent
            opacity={0.9}
            depthTest={false}
          />
        </primitive>
      )}

      {layers.designContours && startMarkerGeometry && curveSelectionVisuals.start && (
        <points name="curve-selection-start" geometry={startMarkerGeometry} userData={{ role: 'start' }}>
          <pointsMaterial color={startColor} size={9} sizeAttenuation={false} depthTest={false} transparent opacity={1} />
        </points>
      )}

      {layers.designContours && startMarkerGeometry && curveSelectionVisuals.start && (
        <Html position={[...curveSelectionVisuals.start] as [number, number, number]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <span className="inline-block" style={{ pointerEvents: 'none', transform: 'translate(0px, -18px)', fontSize: '10px', fontWeight: 700, fontFamily: 'monospace', color: startColor, textShadow: '0 0 4px var(--color-viewer-bg), 0 0 2px var(--color-viewer-bg)' }}>
            {t('project_input.start')}
          </span>
        </Html>
      )}

      {layers.designContours && endMarkerGeometry && curveSelectionVisuals.end && (
        <points name="curve-selection-end" geometry={endMarkerGeometry} userData={{ role: 'end' }}>
          <pointsMaterial color={endColor} size={12} sizeAttenuation={false} depthTest={false} transparent opacity={1} />
        </points>
      )}

      {layers.designContours && endMarkerGeometry && curveSelectionVisuals.end && (
        <Html position={[...curveSelectionVisuals.end] as [number, number, number]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <span className="inline-block" style={{ pointerEvents: 'none', transform: 'translate(0px, 18px)', fontSize: '10px', fontWeight: 700, fontFamily: 'monospace', color: endColor, textShadow: '0 0 4px var(--color-viewer-bg), 0 0 2px var(--color-viewer-bg)' }}>
            {t('project_input.end')}
          </span>
        </Html>
      )}

      {layers.designContours && curveSnapshot && (
        <points
          ref={previewRef}
          name="curve-selection-preview"
          geometry={previewGeometry}
          visible={false}
          frustumCulled={false}
          userData={{ role: 'preview' }}
        >
          <pointsMaterial
            color={readThemeColor('--color-accent-bright', 'white')}
            size={7}
            sizeAttenuation={false}
            depthTest={false}
            transparent
            opacity={0.6}
          />
        </points>
      )}

      {/* Section Lines */}
      {layers.sections && sectionsData.map((sec) => {
        const isSelected = selectedSection === sec.id || selectedSection === sec.name;
        return (
          <primitive key={sec.id} object={sec.line}>
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

function CameraRig({ controls, command, maxDim, showPivot }: {
  controls: React.RefObject<OrbitControlsImpl | null>;
  command: React.RefObject<CameraView | null>;
  maxDim: number;
  showPivot: boolean;
}) {
  const { camera, gl } = useThree();
  const marker = useRef<THREE.Points>(null);
  useFrame(() => {
    const orbit = controls.current;
    if (!orbit) return;
    if (command.current) {
      const view = command.current;
      const state = cameraView(view, maxDim, orbit.target.toArray() as [number, number, number]);
      const damping = orbit.enableDamping;
      orbit.enableDamping = false;
      orbit.update();
      orbit.target.set(...state.target);
      camera.position.set(...state.position);
      if (view === 'plan') camera.position.z += maxDim * 0.00001;
      camera.up.set(0, 1, 0);
      orbit.update();
      orbit.enableDamping = damping;
      command.current = null;
    }
    if (marker.current) marker.current.position.copy(orbit.target);
  });
  return showPivot ? <points ref={marker} name="camera-pivot" renderOrder={1000} frustumCulled={false}>
    <bufferGeometry><bufferAttribute attach="attributes-position" args={[new Float32Array([0, 0, 0]), 3]} /></bufferGeometry>
    <shaderMaterial depthTest={false} uniforms={{ pointSize: { value: 14 * (gl.getPixelRatio?.() ?? 1) } }} vertexShader={'uniform float pointSize; void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_PointSize = pointSize; }'} fragmentShader={'void main() { vec2 p = abs(gl_PointCoord - vec2(0.5)); if (p.x > 0.12 && p.y > 0.12) discard; gl_FragColor = vec4(1.0, 0.8, 0.2, 1.0); }'} />
  </points> : null;
}

// ─── Main Exported Component (3D Viewport) ─────────────────────

export type Mesh3DViewerMode = 'general' | 'blast';

export interface Mesh3DViewerProps {
  mode?: Mesh3DViewerMode;
}

export function Mesh3DViewer({ mode = 'general' }: Mesh3DViewerProps = {}) {
  const isDark = useTheme((s) => s.isDark);
  const cameraControls = useRef<OrbitControlsImpl | null>(null);
  const cameraCommand = useRef<CameraView | null>(null);
  const [cameraToggles, setCameraToggles] = useState(defaultCameraToggles);
  const [pickingPivot, setPickingPivot] = useState(false);
  const setCameraPivot = useCallback((point: THREE.Vector3) => {
    const orbit = cameraControls.current;
    if (!orbit) return;
    const damping = orbit.enableDamping;
    orbit.enableDamping = false;
    orbit.update();
    orbit.target.copy(point);
    orbit.update();
    orbit.enableDamping = damping;
    setCameraToggles((state) => ({ ...state, pivot: true }));
    setPickingPivot(false);
  }, []);
  const toggleCamera = (option: CameraOption) => setCameraToggles((state) => toggleCameraOption(state, option));
  const cameraOverlay = <ViewerCameraControls toggles={cameraToggles} onToggle={toggleCamera} onView={(view) => { cameraCommand.current = view; }} pickingPivot={pickingPivot} onPickPivot={setPickingPivot} />;
  const sceneColors = useMemo(() => ({
    background: readThemeColor('--color-viewer-bg', '#111111'),
    topo: readThemeColor('--color-viewer-topo', TOPO_HEX),
    grid: readThemeColor('--color-viewer-grid', '#334155'),
    minorGrid: readThemeColor('--color-viewer-grid-minor', '#1e293b'),
  }), [isDark]);
  const designMeshId = useSession((s) => s.designMeshId);
  const topoMeshId = useSession((s) => s.topoMeshId);
  const selectedSection = useSession((s) => s.selectedSection);
  const setSelectedSection = useSession((s) => s.setSelectedSection);
  const selectedHoleKey = useSession((s) => s.selectedBlastHoleRowId);
  const setSelectedHoleKey = useSession((s) => s.setSelectedBlastHoleRowId);
  const hasDemoMeshes = designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo;
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { data: designContours, isLoading: loadingContours } = useMeshBreaklines(designMeshId);
  const { data: sections } = useSections();
  const { data: comparisonRows } = useResults();
  const { t } = useTranslation();

  const isLoading = loadingDesign || loadingTopo || loadingContours;
  const hasNoData = !designVerts && !topoVerts;

  const [layers, setLayers] = useState({
    topo: true,
    designContours: true,
    sections: true,
  });
  const [topoOpacity, setTopoOpacity] = useState(1);
  const [showHorizontalDeviation, setShowHorizontalDeviation] = useState(false);
  const storeShowBlastHoles = useBlastView((s) => s.showBlastHoles);
  const setStoreShowBlastHoles = useBlastView((s) => s.setShowBlastHoles);
  const [generalShowBlastHoles, setGeneralShowBlastHoles] = useState(false);
  const blastFilters = useBlastView((s) => s.filters);
  const setBlastFilters = useBlastView((s) => s.setFilters);
  const blastColorConfig = useBlastView((s) => s.colorConfig);
  const setBlastColorConfig = useBlastView((s) => s.setColorConfig);
  const blastColorTarget = useBlastView((s) => s.colorTarget);
  const setBlastColorTarget = useBlastView((s) => s.setColorTarget);
  const activateBlastContext = useBlastView((s) => s.activateContext);
  const confirmedBlastSpatialContext = useBlastView((s) => s.confirmedSpatialContext);
  const confirmBlastSpatialContext = useBlastView((s) => s.confirmSpatial);
  const clearBlastSpatialConfirmation = useBlastView((s) => s.clearSpatialConfirmation);
  const isBlastMode = mode === 'blast';
  const showBlastHoles = isBlastMode ? storeShowBlastHoles : generalShowBlastHoles;
  const setShowBlastHoles = useCallback((value: boolean) => {
    if (isBlastMode) setStoreShowBlastHoles(value);
    else setGeneralShowBlastHoles(value);
  }, [isBlastMode, setStoreShowBlastHoles]);
  useEffect(() => {
    if (isBlastMode) setStoreShowBlastHoles(true);
  }, [isBlastMode, setStoreShowBlastHoles]);
  const [holeCorridor, setHoleCorridor] = useState(10);
  const [filteredHoles, setFilteredHoles] = useState<{ source: unknown; holes: BlastHole3DRecord[] }>({ source: null, holes: [] });
  const [holeColorState, setHoleColorState] = useState<{ source: readonly BlastHole3DRecord[]; mapping: BlastHoleColorMapping; kind: BlastHoleColorLegend['kind'] } | null>(null);
  const [holeLegendState, setHoleLegendState] = useState<{ data: ReturnType<typeof useBlastHoles3D>['data']; mapping: BlastHoleColorMapping } | null>(null);
  const [sectorOverride, setSectorOverride] = useState<string | null>(null);
  const [benchNum, setBenchNum] = useState<number | null>(null);
  const [longitudinalStep, setLongitudinalStep] = useState(2);
  const [verticalStep, setVerticalStep] = useState(1);
  const [controlsSize, setControlsSize] = useState<{ width: number; height: number | null }>({ width: 320, height: null });
  const controlsResizeStart = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const blastPanelId = useId();
  const [blastPanelOpen, setBlastPanelOpen] = useState(readBlastPanelDefaultOpen);

  const beginControlsResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    const panelHeight = event.currentTarget.parentElement?.getBoundingClientRect().height ?? 280;
    controlsResizeStart.current = { x: event.clientX, y: event.clientY, width: controlsSize.width, height: controlsSize.height ?? panelHeight };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const moveControlsResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    const start = controlsResizeStart.current;
    if (!start) return;
    const panel = event.currentTarget.parentElement;
    const viewport = panel?.parentElement;
    const panelRect = panel?.getBoundingClientRect();
    const viewportRect = viewport?.getBoundingClientRect();
    const maxWidth = Math.max(280, Math.min(640, panelRect && viewportRect ? panelRect.right - viewportRect.left - 16 : window.innerWidth - 16));
    const maxHeight = Math.max(280, Math.min(900, panelRect && viewportRect ? viewportRect.bottom - panelRect.top - 16 : window.innerHeight - 16));
    setControlsSize({
      width: Math.max(280, Math.min(maxWidth, start.width + start.x - event.clientX)),
      height: Math.max(280, Math.min(maxHeight, start.height + event.clientY - start.y)),
    });
  };

  const sectorOptions = useMemo(() => Array.from(new Set(
    (sections ?? []).map((section) => section.sector.trim()),
  )).sort((a, b) => a.localeCompare(b)), [sections]);
  const activeSection = sections?.find((section) => section.id === selectedSection || section.name === selectedSection);
  const activeSectionIndex = activeSection && sections ? sections.indexOf(activeSection) : -1;
  const holesQuery = useBlastHoles3D(showBlastHoles && !hasDemoMeshes, activeSectionIndex < 0 ? null : activeSectionIndex,
    activeSection ? JSON.stringify([activeSection.origin, activeSection.azimuth, activeSection.length, activeSection.length_up, activeSection.length_down]) : '');
  const blastContextKey = createBlastViewContextKey(holesQuery.data?.session_id ?? null, designMeshId, topoMeshId, holesQuery.data?.data_revision);
  const confirmBlastSpatialReference = blastContextKey !== null && confirmedBlastSpatialContext === blastContextKey;
  useEffect(() => {
    if (useBlastView.getState().contextKey === blastContextKey) return;
    activateBlastContext(blastContextKey);
    setSelectedHoleKey(null);
  }, [blastContextKey, activateBlastContext, setSelectedHoleKey]);
  const updateVisibleHoles = useCallback((holes: BlastHole3DRecord[], corridor: number) => {
    setFilteredHoles({ source: holesQuery.data, holes });
    setHoleCorridor(corridor);
  }, [holesQuery.data]);
  const updateHoleColors = useCallback((mapping: BlastHoleColorMapping, kind: BlastHoleColorLegend['kind']) => {
    setHoleColorState({ source: filteredHoles.holes, mapping, kind });
    setHoleLegendState({ data: holesQuery.data, mapping });
  }, [filteredHoles.holes, holesQuery.data]);
  const sectionSector = activeSection?.sector.trim() ?? null;
  const selectedSector = sectorOverride !== null && sectorOptions.includes(sectorOverride)
    ? sectorOverride
    : sectionSector !== null && sectorOptions.includes(sectionSector)
      ? sectionSector
      : sectorOptions[0] ?? null;
  const designBenchNumbers = useMemo(() => Array.from(new Set(
    (comparisonRows ?? [])
      .filter((row) => row.sector === selectedSector && row.type !== 'EXTRA' && row.bench_num !== 999 && Number.isInteger(row.bench_num))
      .map((row) => row.bench_num),
  )).sort((a, b) => a - b), [comparisonRows, selectedSector]);
  const selectedBenchNum = benchNum !== null && designBenchNumbers.includes(benchNum) ? benchNum : null;
  const mapQuery = useHorizontalDeviationMesh(
    topoMeshId,
    designMeshId,
    { sector: selectedSector, bench_num: selectedBenchNum, longitudinal_step: longitudinalStep, vertical_step: verticalStep },
    showHorizontalDeviation,
  );
  const canRequestMap = !!designMeshId && !!topoMeshId && selectedSector !== null && !hasDemoMeshes;
  const mapError = horizontalDeviationError(mapQuery.error);

  const bounds = useMemo(() => {
    return calculateBounds(topoVerts, designVerts);
  }, [topoVerts, designVerts]);
  const holeCenter = useMemo(() => [bounds.centerX, bounds.centerY, bounds.centerZ] as const, [bounds.centerX, bounds.centerY, bounds.centerZ]);
  const hasHoleColorMapping = holeColorState?.source === filteredHoles.holes;
  const sceneHoles = useMemo(() => (filteredHoles.source === holesQuery.data ? filteredHoles.holes : []).map((hole) => ({
    key: hole.row_id,
    collar: hole.collar?.length === 3 ? hole.collar as [number, number, number] : null,
    toe: hole.toe?.length === 3 ? hole.toe as [number, number, number] : null,
    color: holeColorState?.source === filteredHoles.holes ? holeColorState.mapping.colorsByRowId.get(hole.row_id) : undefined,
  })), [filteredHoles, holesQuery.data, holeColorState]);
  const selectedHole = filteredHoles.source === holesQuery.data ? filteredHoles.holes.find((hole) => hole.row_id === selectedHoleKey) : undefined;
  const selectedHoleRelation = selectedHole?.section_relation === 'exact_intersection' || selectedHole?.section_relation === 'incomplete'
    ? selectedHole.section_relation
    : selectedHole?.section_distance_m != null ? (selectedHole.section_distance_m <= holeCorridor ? 'near_section' : 'outside') : null;

  if (hasNoData) {
    return (
      <div data-slot="mesh-3d-viewer" className="flex items-center justify-center h-full min-h-0">
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <p className="text-sm text-center">{t('step1.view3d_no_data')}</p>
        </div>
      </div>
    );
  }

  const mutedStyle = { color: 'var(--color-text-muted)' };
  const borderStyle = { borderColor: 'var(--color-border)' };
  const blastVisibleCount = filteredHoles.source === holesQuery.data ? filteredHoles.holes.length : 0;
  const blastTotalCount = holesQuery.data?.holes.length ?? 0;
  const legendMapping = holeLegendState && holeLegendState.data === holesQuery.data ? holeLegendState.mapping : null;

  const renderLayerToggles = () => (
    <>
      <LayerToggle checked={layers.topo} onChange={(checked) => setLayers(prev => ({ ...prev, topo: checked }))} color={sceneColors.topo} label={t('viewer.layer_topo', { defaultValue: 'Topografía real' })} />
      <label className="flex items-center gap-2">
        <span>{t('viewer.layer_topo_opacity')}</span>
        <input type="range" min={0} max={100} step={5} value={topoOpacity * 100}
          aria-label={t('viewer.layer_topo_opacity')} onChange={(event) => setTopoOpacity(Number(event.target.value) / 100)} />
        <span>{Math.round(topoOpacity * 100)}%</span>
      </label>
      <LayerToggle checked={layers.designContours} onChange={(checked) => setLayers(prev => ({ ...prev, designContours: checked }))} color={DESIGN_HEX} label={t('viewer.layer_design', { defaultValue: 'Curvas de diseño' })} />
      <LayerToggle checked={layers.sections} onChange={(checked) => setLayers(prev => ({ ...prev, sections: checked }))} color={SECTION_HEX} label={t('viewer.layer_sections', { defaultValue: 'Líneas de sección' })} />
    </>
  );

  const renderBlastHolesToggle = () => (
    <label className="flex items-center gap-2 cursor-pointer">
      <input data-testid="blast-holes-toggle" type="checkbox" checked={showBlastHoles} disabled={hasDemoMeshes}
        onChange={(event) => setShowBlastHoles(event.target.checked)} />
      <span>{t('blast.layer')}</span>
    </label>
  );

  const renderBlastSpatialBlock = () => showBlastHoles && !hasDemoMeshes && (
    <div className={isBlastMode ? 'flex flex-col gap-3' : undefined}>
      <label className="flex items-start gap-2">
        <input type="checkbox" checked={confirmBlastSpatialReference} disabled={blastContextKey === null}
          onChange={(event) => {
            if (event.target.checked && blastContextKey !== null) confirmBlastSpatialContext(blastContextKey);
            else clearBlastSpatialConfirmation();
          }} />
        <span>{t('blast.confirmSpatial3d')}</span>
      </label>
      {holesQuery.data && blastContextKey === null && (
        <p role="status">{t('blast.spatialRevisionMissing', { defaultValue: 'Esta fuente de pozos no tiene revisión verificable; no se puede confirmar la referencia espacial.' })}</p>
      )}
      {holesQuery.isLoading && <p>{t('blast.layerLoading')}</p>}
      {holesQuery.isError && <p role="alert">{t('blast.layerError')}</p>}
      {holesQuery.data && confirmBlastSpatialReference && <>
        <label className="flex flex-col gap-1">
          <span>{t('blast.sectionSelect')}</span>
          <select value={activeSection?.id ?? ''} onChange={(event) => setSelectedSection(event.target.value || null)}
            className="w-full rounded border px-1.5 py-1" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}>
            <option value="">{t('blast.sectionNone')}</option>
            {(sections ?? []).map((section) => <option key={section.id} value={section.id}>{section.sector ? `${section.sector} · ` : ''}{section.name}</option>)}
          </select>
        </label>
        <p>{t('blast.rejected', { count: holesQuery.data.summary.rejected })}</p>
        <p>{t(isBlastMode ? 'blast.viewPanel.legendHelp' : 'blast.legend')}</p>
        <BlastHoleFilters holes={holesQuery.data.holes} hasSection={activeSectionIndex >= 0} value={blastFilters} onChange={setBlastFilters} onFilteredChange={updateVisibleHoles} compact={isBlastMode} />
        <BlastHoleColorControls records={holesQuery.data.holes} filteredRecords={filteredHoles.source === holesQuery.data ? filteredHoles.holes : EMPTY_BLAST_HOLES} onColorsChange={updateHoleColors} config={blastColorConfig} onConfigChange={setBlastColorConfig} showLegend={!isBlastMode} />
        <label className="flex flex-col gap-1 text-xs">
          <span>{t('blast.colors.target')}</span>
          <select value={blastColorTarget} disabled={!hasHoleColorMapping} onChange={(event) => setBlastColorTarget(event.target.value as BlastColorTarget)}
            className="min-h-11 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm disabled:opacity-60">
            <option value="both">{t('blast.colors.targetBoth')}</option>
            <option value="collars">{t('blast.colors.targetCollars')}</option>
            <option value="trajectories">{t('blast.colors.targetTrajectories')}</option>
          </select>
        </label>
        {selectedHole && <div className="flex flex-col gap-0.5 border-t border-border pt-2">
          <strong>{t('blast.selection')}: {selectedHole.hole_id}</strong>
          <p>{t('blast.collar')}: {selectedHole.collar?.join(', ') ?? t('blast.noData')}</p>
          <p>{t('blast.toe')}: {selectedHole.toe?.join(', ') ?? t('blast.noData')}</p>
          {selectedHole.provenance.z_collar_semantic === 'design_surface_estimate' && <p>{t('blast.estimated')}</p>}
          {selectedHoleRelation && <p>{t('blast.relation')}: {t(`blast.holeFilters.relation.${selectedHoleRelation}`)}</p>}
          {selectedHole.section_distance_m != null && <p>{t('blast.distance')}: {selectedHole.section_distance_m.toFixed(2)} m</p>}
        </div>}
      </>}
    </div>
  );

  const renderHorizontalDeviationControls = () => (
    <div className="mt-1 border-t pt-2" style={{ borderColor: 'var(--color-border)' }}>
      <label className={`flex items-center gap-2 ${canRequestMap ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}>
        <input
          data-testid="horizontal-deviation-toggle"
          type="checkbox"
          checked={showHorizontalDeviation}
          disabled={!canRequestMap}
          onChange={(event) => setShowHorizontalDeviation(event.target.checked)}
          className="h-5 w-5 rounded border-border bg-surface-muted text-accent focus:ring-0 focus:ring-offset-0"
        />
        <span className="font-semibold">{t('viewer.horizontal_map')}</span>
      </label>
      {!canRequestMap && (
        <p className="mt-1 text-xs leading-snug" style={mutedStyle}>
          {hasDemoMeshes
            ? t('viewer.horizontal_demo')
            : !designMeshId || !topoMeshId
              ? t('viewer.horizontal_no_meshes')
              : t('viewer.horizontal_no_sections')}
        </p>
      )}
      {showHorizontalDeviation && canRequestMap && (
        <div className="mt-2 flex flex-col gap-2">
          <FieldLabel label={t('viewer.horizontal_sector')}>
            <select
              data-testid="horizontal-deviation-sector"
              value={selectedSector ?? ''}
              onChange={(event) => {
                setSectorOverride(event.target.value);
                setBenchNum(null);
              }}
              className="min-h-10 w-full rounded border px-2 py-1.5 text-sm"
              style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}
            >
              {sectorOptions.map((sector) => <option key={sector} value={sector}>{sector || t('viewer.horizontal_unnamed_sector')}</option>)}
            </select>
          </FieldLabel>
          <FieldLabel label={t('viewer.horizontal_bench')}>
            <select
              data-testid="horizontal-deviation-bench"
              value={selectedBenchNum == null ? '' : String(selectedBenchNum)}
              onChange={(event) => setBenchNum(event.target.value ? Number(event.target.value) : null)}
              className="min-h-10 w-full rounded border px-2 py-1.5 text-sm"
              style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}
            >
              <option value="">{t('viewer.horizontal_all_benches')}</option>
              {designBenchNumbers.map((number) => <option key={number} value={number}>{number}</option>)}
            </select>
          </FieldLabel>
          <div className="grid grid-cols-2 gap-2">
            <FieldLabel label={t('viewer.horizontal_longitudinal_step')}>
              <input
                data-testid="horizontal-deviation-longitudinal-step"
                type="number"
                min={1}
                max={20}
                step={1}
                value={longitudinalStep}
                onChange={(event) => setLongitudinalStep(clampStep(event.target.value, 1, 20, 2))}
                className="min-h-10 w-full rounded border px-2 py-1.5 text-sm"
                style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}
              />
            </FieldLabel>
            <FieldLabel label={t('viewer.horizontal_vertical_step')}>
              <input
                data-testid="horizontal-deviation-vertical-step"
                type="number"
                min={0.5}
                max={5}
                step={0.5}
                value={verticalStep}
                onChange={(event) => setVerticalStep(clampStep(event.target.value, 0.5, 5, 1))}
                className="min-h-10 w-full rounded border px-2 py-1.5 text-sm"
                style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}
              />
            </FieldLabel>
          </div>
          {mapQuery.isFetching && <p style={mutedStyle}>{t('viewer.horizontal_loading')}</p>}
          {mapQuery.isError && (
            <div role="alert" className="flex flex-col gap-1 rounded border p-2" style={{ borderColor: 'var(--status-nok-border)', color: 'var(--status-nok-text)' }}>
              <span>{t('viewer.horizontal_error')}{mapError ? `: ${t(mapError.key, mapError.options)}` : ''}</span>
              <button type="button" className="self-start underline" onClick={() => void mapQuery.refetch()}>
                {t('viewer.horizontal_retry')}
              </button>
            </div>
          )}
          {mapQuery.data && (
            <>
              <HorizontalDeviationOverview summary={mapQuery.data.summary} compact />
              <HorizontalDeviationLegend compact />
              <p className="text-xs leading-snug" style={mutedStyle}>
                {t('horizontalDeviation.method_caption')} · {t('horizontalDeviation.interpolated_caption')}
              </p>
              {mapQuery.data.effective_resolution && (
                <p className="text-xs leading-snug" style={mutedStyle}>
                  {t('horizontalDeviation.effective_resolution', {
                    longitudinal: formatEffectiveStep(mapQuery.data.effective_resolution.longitudinal_step_min, mapQuery.data.effective_resolution.longitudinal_step_max),
                    vertical: formatEffectiveStep(mapQuery.data.effective_resolution.vertical_step_min, mapQuery.data.effective_resolution.vertical_step_max),
                  })}
                </p>
              )}
              {mapQuery.data.summary.measured === 0 && (
                <p style={mutedStyle}>{t('viewer.horizontal_empty')}</p>
              )}
              {mapQuery.data.warnings.slice(0, 3).map((warning, index) => (
                <p key={`${index}-${warning}`} className="leading-snug" style={mutedStyle}>
                  {t(horizontalDeviationWarning(warning).key, horizontalDeviationWarning(warning).options)}
                </p>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );

  const canvasNode = (
    <Canvas
      camera={{ fov: 50, near: 1, far: 50000 }}
      gl={{ antialias: true, preserveDrawingBuffer: true }}
    >
      <CameraController maxDim={bounds.maxDim} />
      <OrbitControls ref={cameraControls} makeDefault />
      <CameraRig controls={cameraControls} command={cameraCommand} maxDim={bounds.maxDim} showPivot={cameraToggles.pivot} />
      <Scene
        colors={sceneColors}
        topoVerts={topoVerts}
        topoOpacity={topoOpacity}
        horizontalDeviation={mapQuery.data}
        showHorizontalDeviation={showHorizontalDeviation && canRequestMap && !!mapQuery.data}
        designContours={designContours}
        sections={sections}
        selectedSection={selectedSection}
        bounds={bounds}
        layers={layers}
        showGrid={cameraToggles.grid}
        pickingPivot={pickingPivot}
        onPivot={setCameraPivot}
      />
      {showBlastHoles && confirmBlastSpatialReference && holesQuery.data && <BlastHolesLayer holes={sceneHoles} center={holeCenter} selectedKey={selectedHoleKey} onSelect={setSelectedHoleKey} colorTrajectories={hasHoleColorMapping && blastColorTarget !== 'collars'} colorCollars={blastColorTarget !== 'trajectories'} trajectoryColor="#969696" />}
      {cameraToggles.compass && <GizmoHelper alignment="bottom-left" margin={[60, 60]}>
        <GizmoViewport
          axisColors={['#ff3653', '#0adb21', '#2c8fdf']}
          labelColor={readThemeColor('--color-text-primary', 'white')}
          labels={['E', 'Z', 'S']}
        />
        <Html position={[0, 0, -52]} center style={{ color: 'var(--color-text-primary)', fontWeight: 700, pointerEvents: 'none' }}>N</Html>
      </GizmoHelper>}
    </Canvas>
  );

  const loadingNode = (
    <div className="flex items-center justify-center h-full min-h-0" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
      <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
        <Spinner size="md" />
        <p className="text-sm">{t('step1.view3d_loading_verts')}</p>
      </div>
    </div>
  );

  const generalBody = (
    <>
      <div
        data-testid="mesh-layer-panel"
        role="group"
        aria-label={t('viewer.layers', { defaultValue: 'Capas visibles' })}
        className="absolute top-2 right-2 sm:top-4 sm:right-4 z-20 overflow-auto p-3 rounded-lg bg-surface-raised shadow-lg flex flex-col gap-3 border text-xs sm:text-sm select-none"
        style={{
          width: controlsSize.width,
          height: controlsSize.height ?? undefined,
          minWidth: 280,
          minHeight: 280,
          maxWidth: 'calc(100% - 1rem)',
          maxHeight: 'calc(100% - 1rem)',
          borderColor: 'var(--color-border-strong)',
        }}
      >
        <button type="button" aria-label={t('viewer.panel_resize_corner', { defaultValue: 'Cambiar ancho y alto del panel' })} aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown Shift+ArrowLeft Shift+ArrowRight Shift+ArrowUp Shift+ArrowDown" title={t('viewer.panel_resize_hint', { defaultValue: 'Arrastra la esquina para ajustar' })} onPointerDown={beginControlsResize} onPointerMove={moveControlsResize} onPointerUp={() => { controlsResizeStart.current = null; }} onPointerCancel={() => { controlsResizeStart.current = null; }} onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
          event.preventDefault();
          const step = event.shiftKey ? 40 : 16;
          const maxWidth = Math.max(280, Math.min(640, (event.currentTarget.parentElement?.parentElement?.clientWidth ?? window.innerWidth) - 16));
          const maxHeight = Math.max(280, Math.min(900, (event.currentTarget.parentElement?.parentElement?.clientHeight ?? window.innerHeight) - 16));
          const panelHeight = event.currentTarget.parentElement?.getBoundingClientRect().height ?? 280;
          setControlsSize((size) => ({ width: Math.max(280, Math.min(maxWidth, size.width + (event.key === 'ArrowLeft' ? step : event.key === 'ArrowRight' ? -step : 0))), height: Math.max(280, Math.min(maxHeight, (size.height ?? panelHeight) + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0))) }));
        }} className="absolute bottom-0 left-0 z-10 flex h-11 w-11 cursor-sw-resize touch-none items-end justify-start p-1 text-text-muted hover:text-accent focus-visible:outline focus-visible:outline-2" aria-describedby="mesh-panel-resize-hint"><svg aria-hidden="true" viewBox="0 0 18 18" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 15 15 3M8 15 15 8M13 15l2-2" /></svg></button>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
          <span className="font-semibold uppercase tracking-wider text-accent-bright">
            {t('viewer.layers', { defaultValue: 'CAPAS VISIBLES' })}
          </span>
          <span id="mesh-panel-resize-hint" className="text-xs" style={mutedStyle}>{t('viewer.panel_resize_hint', { defaultValue: 'Arrastra una esquina para ajustar' })}</span>
        </div>
        {renderLayerToggles()}
        {renderBlastHolesToggle()}
        {renderBlastSpatialBlock()}
        {renderHorizontalDeviationControls()}
      </div>
      <div className="absolute inset-0 bg-viewer-bg">{canvasNode}</div>
      {cameraOverlay}
    </>
  );

  const blastBody = (
    <>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div data-testid="blast-view-toolbar" role="toolbar" aria-label={t('blast.viewPanel.layers')} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b px-3 py-1 text-xs" style={borderStyle}>
          <span className="font-semibold uppercase tracking-wider text-accent-bright">{t('blast.viewPanel.title')}</span>
          {renderLayerToggles()}
          {renderBlastHolesToggle()}
          {showBlastHoles && !hasDemoMeshes && holesQuery.data && (
            <span style={mutedStyle}>{t('blast.viewPanel.visibleCount', { visible: blastVisibleCount, total: blastTotalCount })}</span>
          )}
          <button type="button" aria-expanded={blastPanelOpen} aria-controls={blastPanelId} onClick={() => setBlastPanelOpen((open) => !open)}
            className="ml-auto min-h-11 rounded border px-3 text-xs" style={borderStyle}>
            {t(blastPanelOpen ? 'blast.viewPanel.hide' : 'blast.viewPanel.show')}
          </button>
        </div>
        <div className="relative min-h-[360px] min-w-0 flex-1 md:min-h-[420px]">
          <div className="absolute inset-0 bg-viewer-bg">{canvasNode}</div>
          {cameraOverlay}
        </div>
        <div data-testid="blast-legend-strip" className="max-h-[30vh] shrink-0 overflow-y-auto border-t bg-surface-raised px-3 py-2 text-xs md:absolute md:bottom-0 md:left-0 md:right-[340px] md:z-10" style={borderStyle}>
          {legendMapping ? <BlastHoleColorLegendView legend={legendMapping.legend} /> : <p style={mutedStyle}>{t('blast.viewPanel.legendHelp')}</p>}
        </div>
      </div>
      <aside
        id={blastPanelId}
        data-testid="blast-view-panel"
        hidden={!blastPanelOpen}
        className={`${blastPanelOpen ? 'flex' : 'hidden'} max-h-[45vh] w-full shrink-0 flex-col gap-3 overflow-y-auto border-t p-3 text-xs md:max-h-none md:w-[340px] md:border-l md:border-t-0`}
        style={borderStyle}
      >
        {renderBlastSpatialBlock()}
        <details className="rounded border p-2" style={borderStyle}>
          <summary className="cursor-pointer font-semibold">{t('viewer.advanced_controls', { defaultValue: 'Más controles de vista' })}</summary>
          {renderHorizontalDeviationControls()}
        </details>
      </aside>
    </>
  );

  return (
    <div
      data-slot="mesh-3d-viewer"
      data-mode={isBlastMode ? 'blast' : undefined}
      className={isBlastMode
        ? 'flex h-full min-h-0 w-full flex-col rounded-xl md:relative md:flex-row'
        : 'h-full min-h-0 w-full relative rounded-xl overflow-hidden'}
      style={{ border: '1px solid var(--color-border)' }}
    >
      {isLoading ? loadingNode : isBlastMode ? blastBody : generalBody}
    </div>
  );
}

function readBlastPanelDefaultOpen(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return window.matchMedia('(min-width: 768px)').matches;
}


function createPointGeometry(point: RenderPoint3D | null): THREE.BufferGeometry | null {
  if (point === null || !point.every((value) => Number.isFinite(value))) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array([point[0], point[1], point[2]]), 3));
  return geometry;
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function clampStep(value: string, minimum: number, maximum: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  const increment = minimum < 1 ? 0.5 : 1;
  return Math.min(maximum, Math.max(minimum, minimum + Math.round((parsed - minimum) / increment) * increment));
}

function formatEffectiveStep(minimum: number | null, maximum: number | null): string {
  if (minimum === null || maximum === null || !Number.isFinite(minimum) || !Number.isFinite(maximum)) return '—';
  if (Math.abs(maximum - minimum) < 1e-6) return `${minimum.toFixed(1)} m`;
  return `${minimum.toFixed(1)}–${maximum.toFixed(1)} m`;
}

function LayerToggle({ checked, onChange, label, color, disabled = false, testId }: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  color?: string;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <label className={`flex min-h-7 items-center gap-2 rounded px-1 -mx-1 ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-surface-muted hover:text-text-primary'}`}>
      <input
        data-testid={testId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[var(--color-accent)]"
      />
      {color && <span aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />}
      <span className="min-w-0 truncate">{label}</span>
    </label>
  );
}
