import { buildCurveRange } from '../sections/curveRange';
import { createCurveAnchor } from '../sections/curveAnchorGeometry';
import type { CurveGeometrySnapshot } from '../sections/curveGeometryAdapter';
import type { CurveSelectionState } from '../sections/curveSelectionState';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../sections/curveSelectionTypes';

export type RenderPoint3D = readonly [x: number, y: number, z: number];

export interface CurveSelectionVisualInput {
  readonly snapshot: CurveGeometrySnapshot | null;
  readonly selection: CurveSelectionState;
  readonly center: MiningPoint3D;
}

export interface CurveSelectionVisualData {
  readonly range: readonly MiningPoint3D[] | null;
  readonly rangePositions: Float32Array | null;
  readonly start: RenderPoint3D | null;
  readonly end: RenderPoint3D | null;
}

const NULL_VISUAL: CurveSelectionVisualData = {
  range: null,
  rangePositions: null,
  start: null,
  end: null,
};

function isFinitePoint3(point: MiningPoint3D): boolean {
  return (
    point.length === 3
    && Number.isFinite(point[0])
    && Number.isFinite(point[1])
    && Number.isFinite(point[2])
  );
}

function sameIdentity(a: CurveSelectionContext, b: CurveSelectionContext): boolean {
  return a.designMeshId === b.designMeshId && a.geometryKey === b.geometryKey;
}

function normalizeZero(value: number): number {
  return value === 0 ? 0 : value;
}

function toRenderPoint(point: MiningPoint3D, center: MiningPoint3D): RenderPoint3D | null {
  if (!isFinitePoint3(point)) {
    return null;
  }
  const rendered: RenderPoint3D = [
    normalizeZero(point[0] - center[0]),
    normalizeZero(point[2] - center[2]),
    normalizeZero(-(point[1] - center[1])),
  ];
  return isFinitePoint3(rendered) ? rendered : null;
}

function buildRangePositions(
  range: readonly MiningPoint3D[],
  center: MiningPoint3D,
): Float32Array | null {
  const buffer = new Float32Array(range.length * 3);
  for (let i = 0; i < range.length; i += 1) {
    const point = range[i];
    if (point === undefined || !isFinitePoint3(point)) {
      return null;
    }
    buffer[i * 3] = normalizeZero(point[0] - center[0]);
    buffer[i * 3 + 1] = normalizeZero(point[2] - center[2]);
    buffer[i * 3 + 2] = normalizeZero(-(point[1] - center[1]));
  }
  for (let i = 0; i < buffer.length; i += 1) {
    if (!Number.isFinite(buffer[i] ?? Number.NaN)) {
      return null;
    }
  }
  return buffer;
}

function revalidateStartAnchor(
  snapshot: CurveGeometrySnapshot,
  selection: CurveSelectionState,
  anchor: CurveAnchor,
): CurveAnchor | null {
  const curveId = selection.curveId;
  if (curveId === null || anchor.curveId !== curveId || !sameIdentity(anchor.context, snapshot.context)) {
    return null;
  }
  const curve = snapshot.curves.get(curveId);
  if (curve === undefined) {
    return null;
  }
  const recalculated = createCurveAnchor({
    context: snapshot.context,
    curveId,
    points: curve.points,
    segmentIndex: anchor.segmentIndex,
    t: anchor.t,
  });
  if (recalculated === null) {
    return null;
  }
  const recalculatedMatches =
    recalculated.position[0] === anchor.position[0]
    && recalculated.position[1] === anchor.position[1]
    && recalculated.position[2] === anchor.position[2]
    && recalculated.chainage === anchor.chainage;
  return recalculatedMatches ? anchor : null;
}

export function buildCurveSelectionVisuals(input: CurveSelectionVisualInput): CurveSelectionVisualData {
  const { snapshot, selection, center } = input;
  if (snapshot === null || selection === null || !isFinitePoint3(center)) {
    return NULL_VISUAL;
  }
  if (selection.context === null || !sameIdentity(selection.context, snapshot.context)) {
    return NULL_VISUAL;
  }
  const curveId = selection.curveId;
  if (curveId === null || !snapshot.curves.has(curveId)) {
    return NULL_VISUAL;
  }
  if (selection.start === null) {
    return NULL_VISUAL;
  }
  if (selection.end === null) {
    const start = revalidateStartAnchor(snapshot, selection, selection.start);
    if (start === null) {
      return NULL_VISUAL;
    }
    const rendered = toRenderPoint(start.position, center);
    if (rendered === null) {
      return NULL_VISUAL;
    }
    return { range: null, rangePositions: null, start: rendered, end: null };
  }
  const curve = snapshot.curves.get(curveId);
  if (curve === undefined) {
    return NULL_VISUAL;
  }
  const range = buildCurveRange({
    context: snapshot.context,
    curveId,
    points: curve.points,
    start: selection.start,
    end: selection.end,
  });
  if (range === null || range.length === 0) {
    return NULL_VISUAL;
  }
  const rangePositions = buildRangePositions(range, center);
  if (rangePositions === null) {
    return NULL_VISUAL;
  }
  const start = toRenderPoint(range[0], center);
  const last = toRenderPoint(range[range.length - 1], center);
  if (start === null || last === null) {
    return NULL_VISUAL;
  }
  return { range, rangePositions, start, end: last };
}
