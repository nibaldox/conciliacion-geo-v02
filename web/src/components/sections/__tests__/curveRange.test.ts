import { describe, expect, it } from 'vitest';
import { expectTypeOf } from 'expect-type';

import { createCurveAnchor } from '../curveAnchorGeometry';
import { buildCurveRange } from '../curveRange';
import type { CurveRangeInput } from '../curveRange';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../curveSelectionTypes';

const context: CurveSelectionContext = { designMeshId: 'diseno-1', geometryKey: 'geo-1' };

function anchorAt(
  curveId: string,
  points: readonly MiningPoint3D[],
  segmentIndex: number,
  t: number,
  anchorContext: CurveSelectionContext = context,
): CurveAnchor {
  const anchor = createCurveAnchor({ context: anchorContext, curveId, points, segmentIndex, t });
  if (!anchor) {
    throw new Error('ancla de prueba inválida');
  }
  return anchor;
}

function forgedAnchor(
  curveId: string,
  segmentIndex: number,
  t: number,
  position: MiningPoint3D,
  chainage: number,
): CurveAnchor {
  return { context, curveId, segmentIndex, t, position, chainage };
}

describe('buildCurveRange', () => {
  it('expone el contrato de entrada con todos los campos readonly', () => {
    expectTypeOf<CurveRangeInput>().toEqualTypeOf<{
      readonly context: CurveSelectionContext;
      readonly curveId: string;
      readonly points: readonly MiningPoint3D[];
      readonly start: CurveAnchor;
      readonly end: CurveAnchor;
    }>();
  });

  it('interpola ambos extremos dentro del mismo segmento', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0.2),
      end: anchorAt('curva-a', points, 0, 0.8),
    };
    expect(buildCurveRange(input)).toEqual([
      [20, 0, 0],
      [80, 0, 0],
    ]);
  });

  it('conserva esquinas entre varios segmentos', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 50, 0],
      [40, 50, 0],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0.5),
      end: anchorAt('curva-a', points, 2, 0.5),
    };
    expect(buildCurveRange(input)).toEqual([
      [50, 0, 0],
      [100, 0, 0],
      [100, 50, 0],
      [70, 50, 0],
    ]);
  });

  it('invierte exactamente el recorrido al intercambiar extremos', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 50, 0],
      [40, 50, 0],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 2, 0.5),
      end: anchorAt('curva-a', points, 0, 0.5),
    };
    expect(buildCurveRange(input)).toEqual([
      [70, 50, 0],
      [100, 50, 0],
      [100, 0, 0],
      [50, 0, 0],
    ]);
  });

  it('no duplica extremos apoyados en vértices', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 50, 0],
      [40, 50, 0],
    ];
    const endOnVertex: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0.5),
      end: anchorAt('curva-a', points, 1, 1),
    };
    expect(buildCurveRange(endOnVertex)).toEqual([
      [50, 0, 0],
      [100, 0, 0],
      [100, 50, 0],
    ]);
    const startOnVertex: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 1, 0),
      end: anchorAt('curva-a', points, 2, 0.5),
    };
    expect(buildCurveRange(startOnVertex)).toEqual([
      [100, 0, 0],
      [100, 50, 0],
      [70, 50, 0],
    ]);
  });

  it('rechaza por valor anclas de otro contexto', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const otherContext: CurveSelectionContext = { designMeshId: 'diseno-2', geometryKey: 'geo-1' };
    const startForeign: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0.2, otherContext),
      end: anchorAt('curva-a', points, 0, 0.8),
    };
    expect(buildCurveRange(startForeign)).toBeNull();
    const endForeign: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0.2),
      end: anchorAt('curva-a', points, 0, 0.8, otherContext),
    };
    expect(buildCurveRange(endForeign)).toBeNull();
  });

  it('rechaza por valor anclas de otra curva', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-b', points, 0, 0.2),
      end: anchorAt('curva-a', points, 0, 0.8),
    };
    expect(buildCurveRange(input)).toBeNull();
  });

  it('rechaza anclas forjadas u obsoletas', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    const valid = anchorAt('curva-a', points, 0, 0.5);
    const forgedPosition: CurveAnchor = { ...valid, position: [90, 0, 0] };
    const inputPosition: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: forgedPosition,
      end: anchorAt('curva-a', points, 1, 0.5),
    };
    expect(buildCurveRange(inputPosition)).toBeNull();
    const forgedChainage: CurveAnchor = { ...valid, chainage: 90 };
    const inputChainage: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: forgedChainage,
      end: anchorAt('curva-a', points, 1, 0.5),
    };
    expect(buildCurveRange(inputChainage)).toBeNull();
  });

  it('retorna null con estaciones coincidentes', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0.5),
      end: anchorAt('curva-a', points, 0, 0.5),
    };
    expect(buildCurveRange(input)).toBeNull();
  });

  it('retorna null cuando la curva no tiene longitud XY', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [0, 0, 10],
      [0, 0, 20],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: forgedAnchor('curva-a', 0, 0.5, [0, 0, 5], 0),
      end: forgedAnchor('curva-a', 1, 0.5, [0, 0, 15], 0),
    };
    expect(buildCurveRange(input)).toBeNull();
  });

  it('retorna null cuando el tramo recortado queda sin longitud XY', () => {
    const points: readonly MiningPoint3D[] = [
      [1e9, 0, 0],
      [1e9 + 100, 0, 0],
    ];
    const input: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points,
      start: anchorAt('curva-a', points, 0, 0),
      end: anchorAt('curva-a', points, 0, 1e-12),
    };
    expect(buildCurveRange(input)).toBeNull();
  });

  it('rechaza anclas sobre segmento degenerado o con puntos no finitos', () => {
    const degenerate: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [0, 0, 10],
      [100, 0, 0],
    ];
    const inputDegenerate: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points: degenerate,
      start: forgedAnchor('curva-a', 0, 0.5, [0, 0, 5], 0),
      end: anchorAt('curva-a', degenerate, 1, 0.5),
    };
    expect(buildCurveRange(inputDegenerate)).toBeNull();
    const nonFinite: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [Number.NaN, 50, 0],
    ];
    const inputNonFinite: CurveRangeInput = {
      context,
      curveId: 'curva-a',
      points: nonFinite,
      start: forgedAnchor('curva-a', 0, 0.2, [20, 0, 0], 20),
      end: forgedAnchor('curva-a', 0, 0.8, [80, 0, 0], 80),
    };
    expect(buildCurveRange(inputNonFinite)).toBeNull();
  });
});
