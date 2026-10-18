import { createCurveAnchor } from './curveAnchorGeometry';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from './curveSelectionTypes';

export interface CurveRangeInput {
  readonly context: CurveSelectionContext;
  readonly curveId: string;
  readonly points: readonly MiningPoint3D[];
  readonly start: CurveAnchor;
  readonly end: CurveAnchor;
}

function samePoint(a: MiningPoint3D, b: MiningPoint3D): boolean {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
}

function sameIdentity(a: CurveSelectionContext, b: CurveSelectionContext): boolean {
  return a.designMeshId === b.designMeshId && a.geometryKey === b.geometryKey;
}

function recalcAnchor(input: CurveRangeInput, anchor: CurveAnchor): CurveAnchor | null {
  if (anchor.curveId !== input.curveId || !sameIdentity(anchor.context, input.context)) {
    return null;
  }
  const recalculated = createCurveAnchor({
    context: input.context,
    curveId: input.curveId,
    points: input.points,
    segmentIndex: anchor.segmentIndex,
    t: anchor.t,
  });
  if (!recalculated) {
    return null;
  }
  if (!samePoint(recalculated.position, anchor.position) || recalculated.chainage !== anchor.chainage) {
    return null;
  }
  return recalculated;
}

export function buildCurveRange(input: CurveRangeInput): readonly MiningPoint3D[] | null {
  const start = recalcAnchor(input, input.start);
  const end = recalcAnchor(input, input.end);
  if (!start || !end || start.chainage === end.chainage) {
    return null;
  }
  const forward = start.chainage < end.chainage;
  const low = forward ? start : end;
  const high = forward ? end : start;
  const lower = low.segmentIndex + (low.t === 1 ? 2 : 1);
  const upper = high.segmentIndex + (high.t > 0 ? 0 : -1);
  const result: MiningPoint3D[] = [start.position];
  if (lower <= upper) {
    if (forward) {
      for (let k = lower; k <= upper; k += 1) {
        const vertex = input.points[k];
        if (!samePoint(vertex, result[result.length - 1])) {
          result.push(vertex);
        }
      }
    } else {
      for (let k = upper; k >= lower; k -= 1) {
        const vertex = input.points[k];
        if (!samePoint(vertex, result[result.length - 1])) {
          result.push(vertex);
        }
      }
    }
  }
  if (!samePoint(end.position, result[result.length - 1])) {
    result.push(end.position);
  }
  let resultLength = 0;
  for (let i = 0; i + 1 < result.length; i += 1) {
    resultLength += Math.hypot(
      result[i + 1][0] - result[i][0],
      result[i + 1][1] - result[i][1],
    );
  }
  if (!(resultLength > 0) || !Number.isFinite(resultLength)) {
    return null;
  }
  return result;
}
