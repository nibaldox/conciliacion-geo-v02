import type { ContourData, ContourLine } from '../../api/types';
import type { CurveSelectionContext, MiningPoint3D } from './curveSelectionTypes';

export interface CurveGeometryPolyline {
  readonly id: string;
  readonly type?: 'crest' | 'toe';
  readonly points: readonly MiningPoint3D[];
}

export interface CurveGeometrySnapshot {
  readonly context: CurveSelectionContext;
  readonly curves: ReadonlyMap<string, CurveGeometryPolyline>;
}

const snapshotCache = new WeakMap<ContourData, Map<string, CurveGeometrySnapshot>>();
let geometryTokenCounter = 0;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function toMiningPoint(raw: unknown, lineElevation: number): MiningPoint3D | null {
  if (!Array.isArray(raw) || raw.length < 2) {
    return null;
  }
  const east = raw[0];
  const north = raw[1];
  if (!isFiniteNumber(east) || !isFiniteNumber(north)) {
    return null;
  }
  if (raw.length === 2) {
    if (!isFiniteNumber(lineElevation)) {
      return null;
    }
    return [east, north, lineElevation];
  }
  const explicitZ = raw[2];
  if (!isFiniteNumber(explicitZ)) {
    return null;
  }
  return [east, north, explicitZ];
}

function buildPolyline(
  line: ContourLine,
  lineIndex: number,
  segmentIndex: number,
  rawSegment: unknown,
): CurveGeometryPolyline | null {
  if (!Array.isArray(rawSegment) || rawSegment.length < 2) {
    return null;
  }
  const points: MiningPoint3D[] = [];
  for (const rawPoint of rawSegment) {
    const point = toMiningPoint(rawPoint, line.elevation);
    if (point === null) {
      return null;
    }
    points.push(point);
  }
  const id = `${lineIndex}-${segmentIndex}`;
  return line.type === undefined ? { id, points } : { id, type: line.type, points };
}

export function getCurveGeometrySnapshot(
  designMeshId: string | null,
  data: ContourData | undefined,
): CurveGeometrySnapshot | null {
  if (designMeshId === null || data === undefined) {
    return null;
  }
  let perMesh = snapshotCache.get(data);
  if (perMesh === undefined) {
    perMesh = new Map<string, CurveGeometrySnapshot>();
    snapshotCache.set(data, perMesh);
  }
  const cached = perMesh.get(designMeshId);
  if (cached !== undefined) {
    return cached;
  }

  geometryTokenCounter += 1;
  const context: CurveSelectionContext = {
    designMeshId,
    geometryKey: `curve-geometry-${geometryTokenCounter}`,
  };
  const curves = new Map<string, CurveGeometryPolyline>();
  const lines = Array.isArray(data.lines) ? data.lines : [];
  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const line = lines[lineIndex];
    if (line === undefined) {
      continue;
    }
    const segments = Array.isArray(line.segments) ? line.segments : [];
    for (let segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
      const polyline = buildPolyline(line, lineIndex, segmentIndex, segments[segmentIndex]);
      if (polyline !== null) {
        curves.set(polyline.id, polyline);
      }
    }
  }
  const snapshot: CurveGeometrySnapshot = { context, curves };
  perMesh.set(designMeshId, snapshot);
  return snapshot;
}
