import type { CurveSelectionAction, CurveSelectionContext } from '../sections/curveSelectionState';

export function curveContextsEqual(
  a: CurveSelectionContext | null,
  b: CurveSelectionContext | null,
): boolean {
  if (a === null || b === null) return a === b;
  return a.designMeshId === b.designMeshId && a.geometryKey === b.geometryKey;
}

export function resolveCurveContextAction(
  previous: CurveSelectionContext | null,
  next: CurveSelectionContext | null,
): CurveSelectionAction | null {
  if (next === null) return null;
  if (curveContextsEqual(previous, next)) return null;
  return { type: 'context', context: next };
}
