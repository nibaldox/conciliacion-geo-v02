import { describe, expect, it } from 'vitest';
import { createCurveAnchor } from '../../sections/curveAnchorGeometry';
import { createCurveSelectionState, type CurveSelectionState } from '../../sections/curveSelectionState';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../../sections/curveSelectionTypes';
import type { CurveGeometrySnapshot } from '../../sections/curveGeometryAdapter';
import { buildCurveSelectionVisuals, type CurveSelectionVisualData } from '../curveSelectionVisuals';

const context: CurveSelectionContext = { designMeshId: 'mesh-1', geometryKey: 'geometry-1' };
const curveId = '0-0';

function buildSnapshot(points: readonly MiningPoint3D[], id: string = curveId): CurveGeometrySnapshot {
  return { context, curves: new Map([[id, { id, points }]]) };
}

function selectionWith(start: CurveAnchor | null, end: CurveAnchor | null): CurveSelectionState {
  return { ...createCurveSelectionState(context), curveId, start, end, rejection: null };
}

function makeAnchor(points: readonly MiningPoint3D[], segmentIndex: number, t: number): CurveAnchor {
  const anchor = createCurveAnchor({ context, curveId, points, segmentIndex, t });
  if (anchor === null) {
    throw new Error('anchor not generable');
  }
  return anchor;
}

function isAllNull(data: CurveSelectionVisualData): boolean {
  return (
    data.range === null
    && data.rangePositions === null
    && data.start === null
    && data.end === null
  );
}

describe('buildCurveSelectionVisuals', () => {
  it('builds the exact clipped traversal and transformed start/end for a confirmed selection', () => {
    const points: readonly MiningPoint3D[] = [[700000, 7200000, 100], [700100, 7200000, 100]];
    const snapshot = buildSnapshot(points);
    const start = makeAnchor(points, 0, 0.2);
    const end = makeAnchor(points, 0, 0.8);
    const data = buildCurveSelectionVisuals({
      snapshot,
      selection: selectionWith(start, end),
      center: [700050, 7200020, 80],
    });
    expect(data.range).toEqual([[700020, 7200000, 100], [700080, 7200000, 100]]);
    expect(Array.from(data.rangePositions ?? [])).toEqual([-30, 20, 20, 30, 20, 20]);
    expect(data.start).toEqual([-30, 20, 20]);
    expect(data.end).toEqual([30, 20, 20]);
  });

  it('keeps corner vertices of the clipped traversal in selection order when reversed', () => {
    const points: readonly MiningPoint3D[] = [[0, 0, 0], [100, 0, 0], [200, 0, 0], [300, 0, 0]];
    const high = makeAnchor(points, 2, 0.25);
    const low = makeAnchor(points, 0, 0.5);
    const data = buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(high, low),
      center: [0, 0, 0],
    });
    expect(data.range).toEqual([[225, 0, 0], [200, 0, 0], [100, 0, 0], [50, 0, 0]]);
    expect(Array.from(data.rangePositions ?? [])).toEqual([225, 0, 0, 200, 0, 0, 100, 0, 0, 50, 0, 0]);
    expect(data.start).toEqual([225, 0, 0]);
    expect(data.end).toEqual([50, 0, 0]);
  });

  it('highlights the full traversal including corners for end-of-curve anchors', () => {
    const points: readonly MiningPoint3D[] = [[0, 0, 0], [100, 0, 0], [200, 0, 0], [300, 0, 0]];
    const start = makeAnchor(points, 0, 0);
    const end = makeAnchor(points, 2, 1);
    const data = buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(start, end),
      center: [0, 0, 0],
    });
    expect(data.range).toEqual([[0, 0, 0], [100, 0, 0], [200, 0, 0], [300, 0, 0]]);
    expect(Array.from(data.rangePositions ?? [])).toEqual([0, 0, 0, 100, 0, 0, 200, 0, 0, 300, 0, 0]);
    expect(data.start).toEqual([0, 0, 0]);
    expect(data.end).toEqual([300, 0, 0]);
  });

  it('keeps a revalidated start marker without range or end when only start is confirmed', () => {
    const points: readonly MiningPoint3D[] = [[700000, 7200000, 100], [700100, 7200000, 100]];
    const start = makeAnchor(points, 0, 0.2);
    const data = buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(start, null),
      center: [700050, 7200020, 80],
    });
    expect(data).toEqual({ range: null, rangePositions: null, start: [-30, 20, 20], end: null });
  });

  it('returns an all-null visual for absent snapshot, incomplete or stale selection', () => {
    const points: readonly MiningPoint3D[] = [[700000, 7200000, 100], [700100, 7200000, 100]];
    const start = makeAnchor(points, 0, 0.2);
    const end = makeAnchor(points, 0, 0.8);
    expect(isAllNull(buildCurveSelectionVisuals({ snapshot: null, selection: selectionWith(start, end), center: [700050, 7200020, 80] }))).toBe(true);
    expect(isAllNull(buildCurveSelectionVisuals({ snapshot: buildSnapshot(points), selection: createCurveSelectionState(null), center: [700050, 7200020, 80] }))).toBe(true);
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: { ...createCurveSelectionState(null), curveId, start, end, rejection: null },
      center: [700050, 7200020, 80],
    }))).toBe(true);
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: { ...selectionWith(start, end), curveId: 'missing' },
      center: [700050, 7200020, 80],
    }))).toBe(true);
    const staleContext: CurveSelectionContext = { designMeshId: 'mesh-1', geometryKey: 'geometry-2' };
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: { context: staleContext, curves: new Map([[curveId, { id: curveId, points }]]) },
      selection: {
        ...createCurveSelectionState(staleContext),
        curveId,
        start,
        end,
        rejection: null,
      },
      center: [700050, 7200020, 80],
    }))).toBe(true);
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(null, end),
      center: [700050, 7200020, 80],
    }))).toBe(true);
  });

  it('returns an all-null visual when the start anchor no longer revalidates or data is non-finite', () => {
    const points: readonly MiningPoint3D[] = [[700000, 7200000, 100], [700100, 7200000, 100]];
    const start = makeAnchor(points, 0, 0.2);
    const forged: CurveAnchor = { ...start, chainage: start.chainage + 1 };
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(forged, null),
      center: [700050, 7200020, 80],
    }))).toBe(true);
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(start, start),
      center: [700050, 7200020, 80],
    }))).toBe(true);
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(start, null),
      center: [700050, Number.NaN, 80],
    }))).toBe(true);
  });

  it('renders the own curve start anchor but rejects a same-geometry foreign curve anchor', () => {
    const meshContext: CurveSelectionContext = { designMeshId: 'm', geometryKey: 'g' };
    const sharedPoints: readonly MiningPoint3D[] = [[0, 0, 0], [100, 0, 0]];
    const snapshot: CurveGeometrySnapshot = {
      context: meshContext,
      curves: new Map([
        ['A', { id: 'A', points: sharedPoints }],
        ['B', { id: 'B', points: sharedPoints }],
      ]),
    };
    const ownAnchor = createCurveAnchor({ context: meshContext, curveId: 'A', points: sharedPoints, segmentIndex: 0, t: 0.2 });
    const foreignAnchor = createCurveAnchor({ context: meshContext, curveId: 'B', points: sharedPoints, segmentIndex: 0, t: 0.2 });
    if (ownAnchor === null || foreignAnchor === null) {
      throw new Error('anchor not generable');
    }
    const own = buildCurveSelectionVisuals({
      snapshot,
      selection: { ...createCurveSelectionState(meshContext), curveId: 'A', start: ownAnchor, end: null, rejection: null },
      center: [0, 0, 0],
    });
    expect(own).toEqual({ range: null, rangePositions: null, start: [20, 0, 0], end: null });
    expect(isAllNull(buildCurveSelectionVisuals({
      snapshot,
      selection: { ...createCurveSelectionState(meshContext), curveId: 'A', start: foreignAnchor, end: null, rejection: null },
      center: [0, 0, 0],
    }))).toBe(true);
  });

  it('does not mutate the snapshot geometry and stays stable across calls', () => {
    const points: readonly MiningPoint3D[] = [[0, 0, 0], [100, 0, 0], [200, 0, 0]];
    const before = points.map((point) => [point[0], point[1], point[2]] as MiningPoint3D);
    const start = makeAnchor(points, 0, 0.4);
    const end = makeAnchor(points, 1, 0.3);
    const data = buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(start, end),
      center: [0, 0, 0],
    });
    const repeat = buildCurveSelectionVisuals({
      snapshot: buildSnapshot(points),
      selection: selectionWith(start, end),
      center: [0, 0, 0],
    });
    expect(points).toEqual(before);
    expect(Array.from(data.rangePositions ?? [])).toEqual(Array.from(repeat.rangePositions ?? []));
    expect(data.range).toEqual([[40, 0, 0], [100, 0, 0], [130, 0, 0]]);
  });
});
