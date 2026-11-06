import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

export type BlastHolePoint = readonly [number, number, number] | null | undefined;

export interface BlastHole3D {
  key: string;
  collar: BlastHolePoint;
  toe?: BlastHolePoint;
  color?: string;
}

export interface BlastHoleGeometryData {
  linePositions: Float32Array;
  lineColors: Float32Array;
  collarPositions: Float32Array;
  markerBatches: BlastHoleMarkerBatchData[];
  completeCount: number;
  collarOnlyCount: number;
  excludedCount: number;
}

export interface BlastHoleMarkerBatchData {
  holes: BlastHole3D[];
  positions: Float32Array;
}

export const BLAST_HOLE_PICKING_CELL_SIZE_M = 350;

export interface BlastHolesLayerProps {
  holes: readonly BlastHole3D[];
  center: readonly [number, number, number];
  visible?: boolean;
  collarRadius?: number;
  trajectoryColor?: THREE.ColorRepresentation;
  completeCollarColor?: THREE.ColorRepresentation;
  collarOnlyColor?: THREE.ColorRepresentation;
  selectedKey?: string | null;
  selectedColor?: THREE.ColorRepresentation;
  onSelect?: (key: string) => void;
  colorTrajectories?: boolean;
}

function isPoint(point: BlastHolePoint): point is readonly [number, number, number] {
  return Array.isArray(point) && point.length === 3 && point.every(Number.isFinite);
}

export function getBlastHoleKeyByInstanceId(
  holes: readonly BlastHole3D[],
  instanceId: number | undefined,
): string | null {
  if (instanceId === undefined || instanceId < 0) return null;
  let instanceIndex = 0;
  for (const hole of holes) {
    if (!isPoint(hole.collar)) continue;
    if (instanceIndex === instanceId) return hole.key;
    instanceIndex += 1;
  }
  return null;
}

export function handleBlastHoleInstanceSelection(
  holes: readonly BlastHole3D[],
  instanceId: number | undefined,
  onSelect: ((key: string) => void) | undefined,
  stopPropagation: () => void,
): void {
  stopPropagation();
  const key = getBlastHoleKeyByInstanceId(holes, instanceId);
  if (key !== null) onSelect?.(key);
}

export function getBlastHoleMarkerColor(
  hole: BlastHole3D,
  selectedKey: string | null | undefined,
  completeCollarColor: THREE.ColorRepresentation,
  collarOnlyColor: THREE.ColorRepresentation,
  selectedColor: THREE.ColorRepresentation,
): THREE.ColorRepresentation {
  if (hole.key === selectedKey) return selectedColor;
  if (hole.color) return hole.color;
  return isPoint(hole.toe) ? completeCollarColor : collarOnlyColor;
}

export function buildBlastHoleGeometry(
  holes: readonly BlastHole3D[],
  center: readonly [number, number, number] = [0, 0, 0],
): BlastHoleGeometryData {
  const linePositions: number[] = [];
  const lineColors: number[] = [];
  const collarPositions: number[] = [];
  const markerBatches = new Map<string, { holes: BlastHole3D[]; positions: number[] }>();
  let completeCount = 0;
  let collarOnlyCount = 0;
  let excludedCount = 0;

  for (const hole of holes) {
    if (!isPoint(hole.collar)) {
      excludedCount += 1;
      continue;
    }

    const [centerX, centerY, centerZ] = center;
    const toLocal = (point: readonly [number, number, number]): [number, number, number] => [
      point[0] - centerX,
      point[2] - centerZ,
      -(point[1] - centerY),
    ];
    const localCollar = toLocal(hole.collar);
    collarPositions.push(...localCollar);
    const cellKey = localCollar.map((coordinate) => Math.floor(coordinate / BLAST_HOLE_PICKING_CELL_SIZE_M)).join(':');
    const batch = markerBatches.get(cellKey) ?? { holes: [], positions: [] };
    batch.holes.push(hole);
    batch.positions.push(...localCollar);
    markerBatches.set(cellKey, batch);
    if (isPoint(hole.toe)) {
      linePositions.push(...toLocal(hole.collar), ...toLocal(hole.toe));
      const color = new THREE.Color(hole.color ?? '#969696');
      lineColors.push(color.r, color.g, color.b, color.r, color.g, color.b);
      completeCount += 1;
    } else {
      collarOnlyCount += 1;
    }
  }

  return {
    linePositions: new Float32Array(linePositions),
    lineColors: new Float32Array(lineColors),
    collarPositions: new Float32Array(collarPositions),
    markerBatches: Array.from(markerBatches.values(), (batch) => ({
      holes: batch.holes,
      positions: new Float32Array(batch.positions),
    })),
    completeCount,
    collarOnlyCount,
    excludedCount,
  };
}

export function BlastHolesLayer({
  holes,
  center,
  visible = true,
  collarRadius = 0.35,
  trajectoryColor = '#f59e0b',
  completeCollarColor = '#f97316',
  collarOnlyColor = '#38bdf8',
  selectedKey = null,
  selectedColor = '#fde047',
  onSelect,
  colorTrajectories = false,
}: BlastHolesLayerProps) {
  const data = useMemo(() => buildBlastHoleGeometry(holes, center), [holes, center]);
  const lineGeometry = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(data.linePositions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(data.lineColors, 3));
    return geometry;
  }, [data.linePositions, data.lineColors]);
  const markerGeometry = useMemo(() => {
    const geometry = new THREE.SphereGeometry(1, 6, 4);
    return geometry;
  }, []);

  useEffect(() => () => lineGeometry.dispose(), [lineGeometry]);
  useEffect(() => () => markerGeometry.dispose(), [markerGeometry]);

  if (!visible) return null;
  return (
    <group name="blast-holes-layer">
      {data.linePositions.length > 0 && (
        <lineSegments geometry={lineGeometry}>
          <lineBasicMaterial color={colorTrajectories ? '#ffffff' : trajectoryColor} vertexColors={colorTrajectories} transparent opacity={0.78} />
        </lineSegments>
      )}
      {data.markerBatches.map((batch, index) => (
        <BlastHoleMarkerBatch
          key={`${index}-${batch.holes[0]?.key ?? 'empty'}`}
          batch={batch}
          geometry={markerGeometry}
          collarRadius={collarRadius}
          completeCollarColor={completeCollarColor}
          collarOnlyColor={collarOnlyColor}
          selectedKey={selectedKey}
          selectedColor={selectedColor}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}

interface BlastHoleMarkerBatchProps {
  batch: BlastHoleMarkerBatchData;
  geometry: THREE.SphereGeometry;
  collarRadius: number;
  completeCollarColor: THREE.ColorRepresentation;
  collarOnlyColor: THREE.ColorRepresentation;
  selectedKey: string | null;
  selectedColor: THREE.ColorRepresentation;
  onSelect?: (key: string) => void;
}

function BlastHoleMarkerBatch({
  batch,
  geometry,
  collarRadius,
  completeCollarColor,
  collarOnlyColor,
  selectedKey,
  selectedColor,
  onSelect,
}: BlastHoleMarkerBatchProps) {
  const instancedRef = useRef<THREE.InstancedMesh>(null);

  useEffect(() => {
    const mesh = instancedRef.current;
    if (!mesh) return;
    const matrix = new THREE.Matrix4();
    const color = new THREE.Color();
    for (let index = 0; index < batch.holes.length; index += 1) {
      const hole = batch.holes[index]!;
      const positionOffset = index * 3;
      matrix.makeScale(collarRadius, collarRadius, collarRadius);
      matrix.setPosition(
        batch.positions[positionOffset]!,
        batch.positions[positionOffset + 1]!,
        batch.positions[positionOffset + 2]!,
      );
      mesh.setMatrixAt(index, matrix);
      color.set(getBlastHoleMarkerColor(hole, selectedKey, completeCollarColor, collarOnlyColor, selectedColor));
      mesh.setColorAt(index, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [batch, collarRadius, completeCollarColor, collarOnlyColor, selectedKey, selectedColor]);

  return (
    <instancedMesh
      ref={instancedRef}
      args={[geometry, undefined, batch.holes.length]}
      onClick={(event) => handleBlastHoleInstanceSelection(batch.holes, event.instanceId, onSelect, () => event.stopPropagation())}
    >
      <meshBasicMaterial vertexColors />
    </instancedMesh>
  );
}
