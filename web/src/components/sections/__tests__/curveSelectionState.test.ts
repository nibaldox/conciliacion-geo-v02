import { describe, expect, expectTypeOf, it } from 'vitest';
import {
  createCurveSelectionState,
  reduceCurveSelection,
  type CurveAnchor,
  type CurveSelectionAction,
  type CurveSelectionContext,
  type CurveSelectionState,
} from '../curveSelectionState';

const ctxA: CurveSelectionContext = { designMeshId: 'mesh-1', geometryKey: 'geo-1' };
const ctxB: CurveSelectionContext = { designMeshId: 'mesh-2', geometryKey: 'geo-2' };
const ctxAEqual: CurveSelectionContext = { designMeshId: 'mesh-1', geometryKey: 'geo-1' };

function makeAnchor(
  context: CurveSelectionContext,
  curveId: string,
  segmentIndex: number,
  t: number,
  chainage: number,
  position: readonly [number, number, number] = [1, 2, 3],
): CurveAnchor {
  return { context, curveId, segmentIndex, t, position, chainage };
}

function click(action: { anchor: CurveAnchor }): CurveSelectionAction {
  return { type: 'click', anchor: action.anchor };
}

function validClick(curveId: string, chainage: number, segmentIndex = 0): CurveSelectionAction {
  return click({ anchor: makeAnchor(ctxA, curveId, segmentIndex, 0.5, chainage) });
}

function invalidNumericAnchor(): CurveAnchor {
  return makeAnchor(ctxA, 'A', -1, Number.POSITIVE_INFINITY, Number.NaN, [Number.NaN, 0, 0]);
}

describe('curveSelectionState', () => {
  it('action variants declare readonly discriminant and payload fields', () => {
    expectTypeOf<CurveSelectionAction>().toEqualTypeOf<
      | { readonly type: 'click'; readonly anchor: CurveAnchor }
      | { readonly type: 'context'; readonly context: CurveSelectionContext | null }
      | { readonly type: 'cancel' }
      | { readonly type: 'generated' }
      | { readonly type: 'invalid_geometry' }
    >();
  });

  it('first click chooses curve only; start/end remain null', () => {
    let state = createCurveSelectionState(ctxA);
    const before = state;
    state = reduceCurveSelection(state, validClick('A', 10));
    expect(state).toEqual<CurveSelectionState>({
      context: ctxA,
      curveId: 'A',
      start: null,
      end: null,
      rejection: null,
    });
    expect(before).not.toBe(state);
  });

  it('second click same curve sets start; third foreign curve cannot change start nor confirm end', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, validClick('A', 20));
    expect(state.start?.chainage).toBe(20);
    expect(state.end).toBeNull();

    const rejected = reduceCurveSelection(state, validClick('B', 80));
    expect(rejected.curveId).toBe('A');
    expect(rejected.start?.chainage).toBe(20);
    expect(rejected.end).toBeNull();
    expect(rejected.rejection).toBe('different_curve');
  });

  it('third same-curve click at different chainage confirms end', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, validClick('A', 20));
    state = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 1, 0.5, 60) }));
    expect(state.start?.chainage).toBe(20);
    expect(state.end?.chainage).toBe(60);
  });

  it('same segment distinct chainages 20 and 80 are accepted; coincident station rejected while choosing second endpoint', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 20, 0));
    state = reduceCurveSelection(state, validClick('A', 80, 0));
    expect(state.start?.chainage).toBe(80);

    const blocked = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 1, 0.5, 80) }));
    expect(blocked.start).toBe(state.start);
    expect(blocked.rejection).toBe('coincident_anchor');

    state = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 1, 0.5, 200) }));
    expect(state.start?.chainage).toBe(80);
    expect(state.end?.chainage).toBe(200);
  });

  it('after two endpoints a further valid same-curve click restarts start and clears end', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, validClick('A', 20));
    state = reduceCurveSelection(state, validClick('A', 60));
    expect(state.end?.chainage).toBe(60);
    state = reduceCurveSelection(state, validClick('A', 90));
    expect(state.curveId).toBe('A');
    expect(state.start?.chainage).toBe(90);
    expect(state.end).toBeNull();
  });

  it('after ready, clicking an existing endpoint chainage restarts instead of coincident rejection', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 0, 0.2, 20) }));
    state = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 1, 0.8, 80) }));
    expect(state.start?.chainage).toBe(20);
    expect(state.end?.chainage).toBe(80);

    const restarted = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 0, 0.2, 20) }));
    expect(restarted.rejection).toBeNull();
    expect(restarted.start?.chainage).toBe(20);
    expect(restarted.end).toBeNull();
  });

  it('cancel and generated clear selection but retain context', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, validClick('A', 20));
    const canceled = reduceCurveSelection(state, { type: 'cancel' });
    expect(canceled).toEqual<CurveSelectionState>({
      context: ctxA,
      curveId: null,
      start: null,
      end: null,
      rejection: null,
    });
    const generated = reduceCurveSelection(state, { type: 'generated' });
    expect(generated).toEqual<CurveSelectionState>({
      context: ctxA,
      curveId: null,
      start: null,
      end: null,
      rejection: null,
    });
  });

  it('equal-value context action keeps same state; changed context clears selection and installs new context', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    const same = reduceCurveSelection(state, { type: 'context', context: ctxAEqual });
    expect(same).toBe(state);

    const changed = reduceCurveSelection(state, { type: 'context', context: ctxB });
    expect(changed).toEqual<CurveSelectionState>({
      context: ctxB,
      curveId: null,
      start: null,
      end: null,
      rejection: null,
    });

    const cleared = reduceCurveSelection(state, { type: 'context', context: null });
    expect(cleared.context).toBeNull();
    expect(cleared.curveId).toBeNull();
  });

  it('context action null on already-null context returns same state reference, preserving rejection', () => {
    let state = createCurveSelectionState(null);
    state = reduceCurveSelection(state, validClick('A', 10));
    expect(state.context).toBeNull();
    expect(state.rejection).toBe('stale_context');

    const same = reduceCurveSelection(state, { type: 'context', context: null });
    expect(same).toBe(state);
    expect(same.rejection).toBe('stale_context');
  });

  it('stale anchor context (missing current or mismatched) rejects stale_context', () => {
    let state = createCurveSelectionState(null);
    const noCtx = reduceCurveSelection(state, validClick('A', 10));
    expect(noCtx.curveId).toBeNull();
    expect(noCtx.start).toBeNull();
    expect(noCtx.rejection).toBe('stale_context');

    state = reduceCurveSelection(state, validClick('A', 10));
    const stale = reduceCurveSelection(
      state,
      click({ anchor: makeAnchor(ctxB, 'A', 0, 0.5, 20) }),
    );
    expect(stale.start).toBeNull();
    expect(stale.end).toBeNull();
    expect(stale.rejection).toBe('stale_context');
  });

  it('numeric-invalid anchor rejects invalid_anchor without changing confirmed selection', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, validClick('A', 20));
    const bad = reduceCurveSelection(state, click({ anchor: invalidNumericAnchor() }));
    expect(bad.curveId).toBe('A');
    expect(bad.start?.chainage).toBe(20);
    expect(bad.end).toBeNull();
    expect(bad.rejection).toBe('invalid_anchor');
  });

  it('invalid_geometry clears curve and anchors, retains context and rejection', () => {
    let state = createCurveSelectionState(ctxA);
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, validClick('A', 20));
    const failed = reduceCurveSelection(state, { type: 'invalid_geometry' });
    expect(failed).toEqual<CurveSelectionState>({
      context: ctxA,
      curveId: null,
      start: null,
      end: null,
      rejection: 'invalid_geometry',
    });
  });

  it('zero coordinates and chainage are valid; successful valid click clears rejection', () => {
    let state = createCurveSelectionState(ctxA) as CurveSelectionState;
    state = reduceCurveSelection(state, validClick('A', 10));
    state = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'B', 0, 0, 0, [0, 0, 0]) }));
    expect(state.rejection).toBe('different_curve');

    state = reduceCurveSelection(state, click({ anchor: makeAnchor(ctxA, 'A', 0, 0, 0, [0, 0, 0]) }));
    expect(state.start?.chainage).toBe(0);
    expect(state.start?.position).toEqual([0, 0, 0]);
    expect(state.rejection).toBeNull();
  });

  it(' reducers never mutate inputs', () => {
    const originalState = createCurveSelectionState(ctxA);
    const frozen: CurveSelectionState = Object.freeze(originalState);
    reduceCurveSelection(frozen, validClick('A', 10));
    expect(frozen).toBe(originalState);
  });
});
