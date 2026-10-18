import type { CurveAnchor, CurveSelectionContext } from './curveSelectionTypes';

export type { CurveAnchor, CurveSelectionContext };

export type CurveSelectionRejection =
  | 'different_curve'
  | 'stale_context'
  | 'invalid_anchor'
  | 'coincident_anchor'
  | 'invalid_geometry';

export interface CurveSelectionState {
  readonly context: CurveSelectionContext | null;
  readonly curveId: string | null;
  readonly start: CurveAnchor | null;
  readonly end: CurveAnchor | null;
  readonly rejection: CurveSelectionRejection | null;
}

export type CurveSelectionAction =
  | { readonly type: 'click'; readonly anchor: CurveAnchor }
  | { readonly type: 'context'; readonly context: CurveSelectionContext | null }
  | { readonly type: 'cancel' }
  | { readonly type: 'generated' }
  | { readonly type: 'invalid_geometry' };

export function createCurveSelectionState(
  context: CurveSelectionContext | null = null,
): CurveSelectionState {
  return { context, curveId: null, start: null, end: null, rejection: null };
}

function contextsEqual(
  a: CurveSelectionContext | null,
  b: CurveSelectionContext | null,
): boolean {
  if (a === null || b === null) return a === b;
  return a.designMeshId === b.designMeshId && a.geometryKey === b.geometryKey;
}

function anchorIsValid(anchor: CurveAnchor): boolean {
  const finite = (n: number) => typeof n === 'number' && Number.isFinite(n);
  return (
    Array.isArray(anchor.position) &&
    anchor.position.length === 3 &&
    anchor.position.every(finite) &&
    Number.isInteger(anchor.segmentIndex) &&
    anchor.segmentIndex >= 0 &&
    finite(anchor.t) &&
    anchor.t >= 0 &&
    anchor.t <= 1 &&
    finite(anchor.chainage) &&
    anchor.chainage >= 0
  );
}

function isCoincident(state: CurveSelectionState, chainage: number): boolean {
  return (
    (state.start !== null && state.start.chainage === chainage) ||
    (state.end !== null && state.end.chainage === chainage)
  );
}

export function reduceCurveSelection(
  state: CurveSelectionState,
  action: CurveSelectionAction,
): CurveSelectionState {
  if (action.type === 'context') {
    if (contextsEqual(state.context, action.context)) return state;
    return {
      context: action.context,
      curveId: null,
      start: null,
      end: null,
      rejection: null,
    };
  }

  if (action.type === 'cancel' || action.type === 'generated') {
    return {
      context: state.context,
      curveId: null,
      start: null,
      end: null,
      rejection: null,
    };
  }

  if (action.type === 'invalid_geometry') {
    return {
      context: state.context,
      curveId: null,
      start: null,
      end: null,
      rejection: 'invalid_geometry',
    };
  }

  const anchor = action.anchor;

  if (!anchorIsValid(anchor)) {
    return { ...state, rejection: 'invalid_anchor' };
  }

  if (state.context === null || !contextsEqual(state.context, anchor.context)) {
    return { ...state, rejection: 'stale_context' };
  }

  if (state.curveId === null) {
    return { ...state, curveId: anchor.curveId, start: null, end: null, rejection: null };
  }

  if (anchor.curveId !== state.curveId) {
    return { ...state, rejection: 'different_curve' };
  }

  if (state.end !== null) {
    return { ...state, start: anchor, end: null, rejection: null };
  }

  if (isCoincident(state, anchor.chainage)) {
    return { ...state, rejection: 'coincident_anchor' };
  }

  if (state.start === null) {
    return { ...state, start: anchor, end: null, rejection: null };
  }

  return { ...state, end: anchor, rejection: null };
}
