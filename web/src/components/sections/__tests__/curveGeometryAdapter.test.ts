import { describe, expect, it } from 'vitest';
import type { ContourData } from '../../../api/types';
import { getCurveGeometrySnapshot } from '../curveGeometryAdapter';

function buildContourData(): ContourData {
  return {
    bounds: { min_east: 0, max_east: 1100 },
    elevation_min: 1200,
    elevation_max: 1210,
    interval: 5,
    lines: [
      {
        elevation: 1205,
        type: 'crest',
        segments: [
          [
            [1000, 2000],
            [1010, 2010],
            [1020, 2020],
          ],
        ],
      },
    ],
  };
}

describe('getCurveGeometrySnapshot', () => {
  it('returns the same shared snapshot for the same data object and mesh, preserving original XY and the finite line elevation as Z', () => {
    const data: ContourData = {
      bounds: { min_east: 900, max_east: 1100 },
      elevation_min: 1200,
      elevation_max: 1210,
      interval: 5,
      lines: [
        {
          elevation: 1205,
          type: 'crest',
          segments: [
            [
              [1000, 2000],
              [1010, 2010],
              [1020, 2020],
            ],
          ],
        },
      ],
    };

    const first = getCurveGeometrySnapshot('mesh-A', data);
    const second = getCurveGeometrySnapshot('mesh-A', data);

    expect(first).not.toBeNull();
    expect(second).toBe(first);
    expect(second?.context).toBe(first?.context);
    expect(second?.context.designMeshId).toBe('mesh-A');
    expect(second?.context.geometryKey).not.toBe('');

    const curve = second?.curves.get('0-0');
    expect(curve).toBeDefined();
    expect(curve?.type).toBe('crest');
    expect(curve?.points).toHaveLength(3);
    expect(curve?.points[0]).toEqual([1000, 2000, 1205]);
    expect(curve?.points[2]).toEqual([1020, 2020, 1205]);
    expect(curve?.points[0]).not.toBe(data.lines[0].segments[0][0]);
  });

  it('creates a new snapshot and geometry token for a distinct data object with identical content', () => {
    const dataA = buildContourData();
    const dataB = buildContourData();
    const snapA = getCurveGeometrySnapshot('mesh-A', dataA);
    const snapB = getCurveGeometrySnapshot('mesh-A', dataB);

    expect(snapA).not.toBeNull();
    expect(snapB).not.toBeNull();
    expect(snapB).not.toBe(snapA);
    expect(snapB?.context.designMeshId).toBe('mesh-A');
    expect(snapB?.context.geometryKey).not.toBe(snapA?.context.geometryKey);
    expect(getCurveGeometrySnapshot('mesh-A', dataA)).toBe(snapA);
  });

  it('creates a separate snapshot per mesh for the same data object and keeps prior mesh snapshots stable', () => {
    const data = buildContourData();
    const snapA = getCurveGeometrySnapshot('mesh-A', data);
    const snapB = getCurveGeometrySnapshot('mesh-B', data);

    expect(snapA).not.toBeNull();
    expect(snapB).not.toBeNull();
    expect(snapB).not.toBe(snapA);
    expect(snapB?.context.designMeshId).toBe('mesh-B');
    expect(snapB?.context.geometryKey).not.toBe(snapA?.context.geometryKey);
    expect(getCurveGeometrySnapshot('mesh-A', data)).toBe(snapA);
  });

  it('prefers the explicit third coordinate when finite, and rejects the whole polyline when it is nonfinite or explicitly undefined instead of falling back', () => {
    const mixed: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 400,
      interval: 5,
      lines: [
        {
          elevation: 77,
          type: 'toe',
          segments: [
            [
              [1, 2, 300],
              [3, 4],
            ],
          ],
        },
      ],
    };
    const mixedSnap = getCurveGeometrySnapshot('mesh-A', mixed);
    expect(mixedSnap?.curves.get('0-0')?.type).toBe('toe');
    expect(mixedSnap?.curves.get('0-0')?.points[0]).toEqual([1, 2, 300]);
    expect(mixedSnap?.curves.get('0-0')?.points[1]).toEqual([3, 4, 77]);

    const nanZ: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 400,
      interval: 5,
      lines: [
        {
          elevation: 77,
          segments: [
            [
              [1, 2, Number.NaN],
              [3, 4],
            ],
          ],
        },
      ],
    };
    const nanSnap = getCurveGeometrySnapshot('mesh-A', nanZ);
    expect(nanSnap).not.toBeNull();
    expect(nanSnap?.curves.size).toBe(0);

    const undefinedZSegment: number[][] = [
      [1, 2, undefined as unknown as number],
      [3, 4],
    ];
    const undefinedZ: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 400,
      interval: 5,
      lines: [{ elevation: 77, segments: [undefinedZSegment] }],
    };
    const undefinedSnap = getCurveGeometrySnapshot('mesh-A', undefinedZ);
    expect(undefinedSnap).not.toBeNull();
    expect(undefinedSnap?.curves.size).toBe(0);
  });

  it('keeps zero coordinates and zero elevation as valid geometry', () => {
    const data: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 0,
      interval: 0,
      lines: [
        {
          elevation: 0,
          segments: [
            [
              [0, 0],
              [5, 0, 0],
            ],
          ],
        },
      ],
    };
    const snap = getCurveGeometrySnapshot('mesh-A', data);
    expect(snap).not.toBeNull();
    expect(snap?.curves.get('0-0')?.points[0]).toEqual([0, 0, 0]);
    expect(snap?.curves.get('0-0')?.points[1]).toEqual([5, 0, 0]);
  });

  it('skips invalid polylines without renumbering neighbors and keeps duplicated vertices and original ids', () => {
    const data: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 10,
      interval: 5,
      lines: [
        {
          elevation: 5,
          type: 'crest',
          segments: [
            [[100, 200]],
            [
              [100, 200],
              [110, 210],
              [110, 210],
            ],
          ],
        },
        {
          elevation: 7,
          segments: [
            [
              [300, 310],
              [320, 330],
            ],
          ],
        },
      ],
    };
    const snap = getCurveGeometrySnapshot('mesh-A', data);

    expect(snap?.curves.size).toBe(2);
    expect(snap?.curves.has('0-0')).toBe(false);
    expect(snap?.curves.has('0-1')).toBe(true);
    expect(snap?.curves.has('1-0')).toBe(true);
    expect(snap?.curves.get('0-1')?.type).toBe('crest');
    expect(snap?.curves.get('1-0')?.type).toBeUndefined();
    expect(snap?.curves.get('0-1')?.points).toEqual([
      [100, 200, 5],
      [110, 210, 5],
      [110, 210, 5],
    ]);
    expect(snap?.curves.get('1-0')?.points).toEqual([
      [300, 310, 7],
      [320, 330, 7],
    ]);
  });

  it('returns the same snapshot and curves map on repeated calls and never mutates the source data', () => {
    const data = buildContourData();
    const before = JSON.stringify(data);
    const first = getCurveGeometrySnapshot('mesh-A', data);
    const second = getCurveGeometrySnapshot('mesh-A', data);

    expect(first).not.toBeNull();
    expect(second).toBe(first);
    expect(second?.curves).toBe(first?.curves);
    expect(JSON.stringify(data)).toBe(before);
    expect(second?.curves.get('0-0')?.points[0]).not.toBe(data.lines[0].segments[0][0]);
  });

  it('returns null for absent inputs and a non-null empty snapshot for empty or fully invalid datasets', () => {
    const data = buildContourData();
    expect(getCurveGeometrySnapshot(null, data)).toBeNull();
    expect(getCurveGeometrySnapshot('mesh-A', undefined)).toBeNull();
    expect(getCurveGeometrySnapshot(null, undefined)).toBeNull();

    const empty: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 0,
      interval: 5,
      lines: [],
    };
    const emptySnap = getCurveGeometrySnapshot('mesh-A', empty);
    expect(emptySnap).not.toBeNull();
    expect(emptySnap?.curves.size).toBe(0);
    expect(emptySnap?.context.designMeshId).toBe('mesh-A');
    expect(emptySnap?.context.geometryKey).not.toBe('');
    expect(getCurveGeometrySnapshot('mesh-A', empty)).toBe(emptySnap);

    const allInvalid: ContourData = {
      bounds: {},
      elevation_min: 0,
      elevation_max: 5,
      interval: 5,
      lines: [
        { elevation: 3, segments: [[[0, 0]]] },
        { elevation: 4, segments: [[[Number.NaN, 1, 2]]] },
      ],
    };
    const invalidSnap = getCurveGeometrySnapshot('mesh-A', allInvalid);
    expect(invalidSnap).not.toBeNull();
    expect(invalidSnap?.curves.size).toBe(0);
    expect(invalidSnap?.context.designMeshId).toBe('mesh-A');
  });
});
