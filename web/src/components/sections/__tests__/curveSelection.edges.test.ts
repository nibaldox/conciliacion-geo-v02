// T13: aristas de densidad, repetición, escala UTM, curva cerrada, identidad de malla y elevación ausente sobre las funciones puras T02/T03/T05 y el adaptador de geometría.
import { describe, expect, it } from 'vitest';
import { createCurveAnchor, projectCurveAnchor } from '../curveAnchorGeometry';
import { buildCurveRange } from '../curveRange';
import { createCurveSelectionState, reduceCurveSelection } from '../curveSelectionState';
import { getCurveGeometrySnapshot } from '../curveGeometryAdapter';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../curveSelectionTypes';
import type { ContourData } from '../../../api/types';

const context: CurveSelectionContext = { designMeshId: 'mesh-t13', geometryKey: 'geo-t13' };

function anchorAt(
  points: readonly MiningPoint3D[],
  segmentIndex: number,
  t: number,
  anchorContext: CurveSelectionContext = context,
  curveId = 'curva-t13',
): CurveAnchor {
  const anchor = createCurveAnchor({ context: anchorContext, curveId, points, segmentIndex, t });
  if (anchor === null) {
    throw new Error('ancla de prueba no generable');
  }
  return anchor;
}

function rangeOf(
  points: readonly MiningPoint3D[],
  start: CurveAnchor,
  end: CurveAnchor,
): readonly MiningPoint3D[] | null {
  return buildCurveRange({ context, curveId: 'curva-t13', points, start, end });
}

function contour(lines: ContourData['lines']): ContourData {
  return { bounds: {}, elevation_min: 0, elevation_max: 0, interval: 5, lines };
}

describe('densidad de vértices (T02/T03)', () => {
  it('recorta en ambas direcciones una curva de dos vértices y no normaliza t=1 al segmento abierto', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const start = anchorAt(points, 0, 0.25);
    const end = anchorAt(points, 0, 0.75);
    expect(rangeOf(points, start, end)).toEqual([
      [25, 0, 0],
      [75, 0, 0],
    ]);
    expect(rangeOf(points, end, start)).toEqual([
      [75, 0, 0],
      [25, 0, 0],
    ]);
    const open = anchorAt(points, 0, 1);
    expect(open.segmentIndex).toBe(0);
    expect(open.t).toBe(1);
    expect(open.position).toEqual([100, 0, 0]);
  });

  it('ancla en el último segmento y recorre 100k vértices preservando interiores', () => {
    const points: MiningPoint3D[] = [];
    for (let i = 0; i < 100000; i += 1) {
      points.push([i, 0, 0]);
    }
    const last = anchorAt(points, 99998, 0.5);
    expect(last.segmentIndex).toBe(99998);
    expect(last.position).toEqual([99998.5, 0, 0]);
    expect(last.chainage).toBe(99998.5);

    const full = rangeOf(points, anchorAt(points, 0, 0), anchorAt(points, 99998, 1));
    expect(full).not.toBeNull();
    expect(full?.length).toBe(100000);
    expect(full?.[0]).toEqual([0, 0, 0]);
    expect(full?.[99999]).toEqual([99999, 0, 0]);

    const window = rangeOf(points, anchorAt(points, 49999, 0.5), anchorAt(points, 50000, 0.5));
    expect(window).toEqual([
      [49999.5, 0, 0],
      [50000, 0, 0],
      [50000.5, 0, 0],
    ]);
  });

  it('deduplica puntos consecutivos repetidos y conserva repetidos no consecutivos', () => {
    const repeated: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    expect(rangeOf(repeated, anchorAt(repeated, 0, 0.5), anchorAt(repeated, 2, 0.5))).toEqual([
      [50, 0, 0],
      [100, 0, 0],
      [150, 0, 0],
    ]);

    const nonConsecutive: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [0, 0, 0],
    ];
    const range = rangeOf(nonConsecutive, anchorAt(nonConsecutive, 0, 0.5), anchorAt(nonConsecutive, 1, 0.5));
    expect(range).toEqual([
      [50, 0, 0],
      [100, 0, 0],
      [50, 0, 0],
    ]);
  });
});

describe('escala UTM y fracciones sub-milimétricas (T02/T03)', () => {
  it('conserva estación XY con fracción de 1e-9 en E~700000 N~7200000 Z~3000', () => {
    const points: readonly MiningPoint3D[] = [
      [700000, 7200000, 3000],
      [700100, 7200000, 3000],
    ];
    const subMilli = anchorAt(points, 0, 1e-9);
    expect(subMilli.chainage).toBe(100 * 1e-9);
    expect(subMilli.chainage).toBeGreaterThan(0);
    expect(subMilli.position[0] - 700000).toBeCloseTo(100 * 1e-9, 9);
    expect(subMilli.position[2]).toBe(3000);

    const tiny = rangeOf(points, anchorAt(points, 0, 0), anchorAt(points, 0, 1e-6));
    expect(tiny).toEqual([
      [700000, 7200000, 3000],
      [700000.0001, 7200000, 3000],
    ]);
  });

  it('estaciona solo por XY aunque la elevación cambie en escala UTM', () => {
    const points: readonly MiningPoint3D[] = [
      [700000, 7200000, 3000],
      [700100, 7200000, 3100],
    ];
    const anchor = anchorAt(points, 0, 0.5);
    expect(anchor.position).toEqual([700050, 7200000, 3050]);
    expect(anchor.chainage).toBe(50);
  });

  it('projectCurveAnchor recupera la fracción sub-milimétrica sobre UTM', () => {
    const points: readonly MiningPoint3D[] = [
      [700000, 7200000, 3000],
      [700100, 7200000, 3000],
    ];
    const projected = projectCurveAnchor({
      context,
      curveId: 'curva-t13',
      points,
      segmentIndex: 0,
      position: [700000.00005, 7200000, 3000],
    });
    expect(projected).not.toBeNull();
    expect(projected?.t).toBeCloseTo(5e-7, 9);
    expect(projected?.chainage).toBeCloseTo(5e-5, 9);
  });
});

describe('curva cerrada primero==último (T02/T03/T05)', () => {
  const ring: readonly MiningPoint3D[] = [
    [0, 0, 0],
    [100, 0, 0],
    [100, 100, 0],
    [0, 0, 0],
  ];

  it('preserva estaciones distintas y el recorrido directo aunque inicio y fin compartan XYZ', () => {
    const start = anchorAt(ring, 0, 0);
    const end = anchorAt(ring, 2, 1);
    expect(start.chainage).toBe(0);
    expect(end.chainage).toBeGreaterThan(0);
    expect(start.position).toEqual([0, 0, 0]);
    expect(end.position).toEqual([0, 0, 0]);

    const range = rangeOf(ring, start, end);
    expect(range).toEqual([
      [0, 0, 0],
      [100, 0, 0],
      [100, 100, 0],
      [0, 0, 0],
    ]);
  });

  it('acepta dos estaciones distintas con la misma posición al cerrar el bucle', () => {
    let state = createCurveSelectionState(context);
    state = reduceCurveSelection(state, { type: 'click', anchor: anchorAt(ring, 0, 0) });
    state = reduceCurveSelection(state, { type: 'click', anchor: anchorAt(ring, 0, 0) });
    expect(state.start?.chainage).toBe(0);
    expect(state.end).toBeNull();

    state = reduceCurveSelection(state, { type: 'click', anchor: anchorAt(ring, 2, 1) });
    expect(state.start?.chainage).toBe(0);
    expect(state.end?.chainage).toBeGreaterThan(0);
    expect(state.end?.position).toEqual(state.start?.position);
    expect(state.rejection).toBeNull();
  });
});

describe('identidad de malla/geometría (adaptador + T03)', () => {
  it('invalida un ancla del snapshot previo cuando el objeto de datos se reemplaza', () => {
    const build = (): ContourData =>
      contour([{ elevation: 5, segments: [[[0, 0], [100, 0]]] }]);
    const snapA = getCurveGeometrySnapshot('mesh-t13', build());
    const snapB = getCurveGeometrySnapshot('mesh-t13', build());
    expect(snapA).not.toBeNull();
    expect(snapB).not.toBeNull();
    expect(snapB?.context.geometryKey).not.toBe(snapA?.context.geometryKey);

    const pointsA = snapA?.curves.get('0-0')?.points;
    const pointsB = snapB?.curves.get('0-0')?.points;
    if (!pointsA || !pointsB || !snapA || !snapB) {
      throw new Error('snapshot de prueba incompleto');
    }
    const stale = createCurveAnchor({
      context: snapA.context,
      curveId: '0-0',
      points: pointsA,
      segmentIndex: 0,
      t: 0.5,
    });
    const freshEnd = createCurveAnchor({
      context: snapB.context,
      curveId: '0-0',
      points: pointsB,
      segmentIndex: 0,
      t: 0.8,
    });
    const freshStart = createCurveAnchor({
      context: snapB.context,
      curveId: '0-0',
      points: pointsB,
      segmentIndex: 0,
      t: 0.2,
    });
    if (!stale || !freshEnd || !freshStart) {
      throw new Error('anclas de prueba no generables');
    }

    expect(
      buildCurveRange({ context: snapB.context, curveId: '0-0', points: pointsB, start: stale, end: freshEnd }),
    ).toBeNull();
    expect(
      buildCurveRange({ context: snapB.context, curveId: '0-0', points: pointsB, start: freshStart, end: freshEnd }),
    ).toEqual([
      [20, 0, 5],
      [80, 0, 5],
    ]);
  });
});

describe('elevación ausente en el adaptador', () => {
  it('rechaza un punto 2D cuando la elevación de la línea no es finita y acepta el Z explícito en otra polilínea', () => {
    const data = contour([
      {
        elevation: Number.NaN,
        segments: [
          [[1, 2]],
          [
            [3, 4, 300],
            [5, 6, 300],
          ],
        ],
      },
    ]);
    const snap = getCurveGeometrySnapshot('mesh-t13', data);
    expect(snap).not.toBeNull();
    expect(snap?.curves.has('0-0')).toBe(false);
    expect(snap?.curves.get('0-1')?.points).toEqual([
      [3, 4, 300],
      [5, 6, 300],
    ]);
  });
});
