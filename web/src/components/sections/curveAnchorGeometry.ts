import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from './curveSelectionTypes';

export interface CurveAnchorInput {
  readonly context: CurveSelectionContext;
  readonly curveId: string;
  readonly points: readonly MiningPoint3D[];
  readonly segmentIndex: number;
  readonly t: number;
}

function finite(value: number): boolean {
  return Number.isFinite(value);
}

function xyLength(a: MiningPoint3D, b: MiningPoint3D): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function segmentIsValid(a: MiningPoint3D, b: MiningPoint3D): boolean {
  const length = xyLength(a, b);
  return finite(length) && length > 0;
}

export function createCurveAnchor(input: CurveAnchorInput): CurveAnchor | null {
  const { context, curveId, points, segmentIndex, t } = input;
  if (points.length < 2) {
    return null;
  }
  for (const point of points) {
    if (!finite(point[0]) || !finite(point[1]) || !finite(point[2])) {
      return null;
    }
  }
  const maxSegmentIndex = points.length - 2;
  if (!Number.isInteger(segmentIndex) || segmentIndex < 0 || segmentIndex > maxSegmentIndex) {
    return null;
  }
  if (!finite(t) || t < 0 || t > 1) {
    return null;
  }

  const requestedA = points[segmentIndex];
  const requestedB = points[segmentIndex + 1];
  if (!segmentIsValid(requestedA, requestedB)) {
    return null;
  }

  let index = segmentIndex;
  let parameter = t;
  if (parameter === 1 && index < maxSegmentIndex && segmentIsValid(points[index + 1], points[index + 2])) {
    index += 1;
    parameter = 0;
  }

  const a = points[index];
  const b = points[index + 1];
  const currentLength = xyLength(a, b);
  let priorLength = 0;
  for (let i = 0; i < index; i += 1) {
    priorLength += xyLength(points[i], points[i + 1]);
  }
  const position: MiningPoint3D = [
    a[0] + (b[0] - a[0]) * parameter,
    a[1] + (b[1] - a[1]) * parameter,
    a[2] + (b[2] - a[2]) * parameter,
  ];
  const chainage = priorLength + parameter * currentLength;
  if (!finite(currentLength) || currentLength <= 0) {
    return null;
  }
  if (!finite(position[0]) || !finite(position[1]) || !finite(position[2]) || !finite(chainage)) {
    return null;
  }
  return { context, curveId, segmentIndex: index, t: parameter, position, chainage };
}

export interface CurveAnchorProjectionInput {
  readonly context: CurveSelectionContext;
  readonly curveId: string;
  readonly points: readonly MiningPoint3D[];
  readonly segmentIndex: number;
  readonly position: MiningPoint3D;
}

export function projectCurveAnchor(input: CurveAnchorProjectionInput): CurveAnchor | null {
  const { context, curveId, points, segmentIndex, position } = input;
  if (points.length < 2) {
    return null;
  }
  for (const point of points) {
    if (!finite(point[0]) || !finite(point[1]) || !finite(point[2])) {
      return null;
    }
  }
  if (!finite(position[0]) || !finite(position[1]) || !finite(position[2])) {
    return null;
  }
  const maxSegmentIndex = points.length - 2;
  if (!Number.isInteger(segmentIndex) || segmentIndex < 0 || segmentIndex > maxSegmentIndex) {
    return null;
  }

  const a = points[segmentIndex];
  const b = points[segmentIndex + 1];
  if (!segmentIsValid(a, b)) {
    return null;
  }
  const abx = b[0] - a[0];
  const aby = b[1] - a[1];
  const abz = b[2] - a[2];
  const norm2 = abx * abx + aby * aby + abz * abz;
  if (!finite(norm2) || norm2 <= 0) {
    return null;
  }
  const rawT =
    ((position[0] - a[0]) * abx + (position[1] - a[1]) * aby + (position[2] - a[2]) * abz) / norm2;
  if (!finite(rawT)) {
    return null;
  }
  const t = Math.min(1, Math.max(0, rawT));
  return createCurveAnchor({ context, curveId, points, segmentIndex, t });
}
