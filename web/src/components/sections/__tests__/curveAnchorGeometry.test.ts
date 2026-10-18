import { describe, expect, it } from 'vitest';

import { createCurveAnchor, projectCurveAnchor } from '../curveAnchorGeometry';
import type { CurveSelectionContext, MiningPoint3D } from '../curveSelectionTypes';

const context: CurveSelectionContext = { designMeshId: 'diseno-1', geometryKey: 'geo-1' };

describe('createCurveAnchor', () => {
  it('interpola dentro de una arista recta y estaciona por XY', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const at20 = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, t: 0.2 });
    const at80 = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, t: 0.8 });

    expect(at20).not.toBeNull();
    expect(at80).not.toBeNull();
    expect(at20?.position).toEqual([20, 0, 0]);
    expect(at80?.position).toEqual([80, 0, 0]);
    expect(at20?.chainage).toBe(20);
    expect(at80?.chainage).toBe(80);
    expect(at20?.segmentIndex).toBe(at80?.segmentIndex);
    expect(at20?.t).toBe(0.2);
    expect(at80?.context).toEqual(context);
    expect(at80?.curveId).toBe('curva-a');
  });

  it('estaciona solo por XY aunque la elevación cambie', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 50],
    ];
    const anchor = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, t: 0.5 });
    expect(anchor?.position).toEqual([50, 0, 25]);
    expect(anchor?.chainage).toBe(50);
  });

  it('suma estaciones XY de segmentos previos y mantiene esquinas', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [0, 50, 0],
    ];
    const anchor = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1, t: 0.5 });
    expect(anchor?.segmentIndex).toBe(1);
    expect(anchor?.position).toEqual([50, 25, 0]);
    expect(anchor?.chainage).toBeCloseTo(100 + Math.hypot(100, 50) / 2, 12);
  });

  it('normaliza t=1 al segmento siguiente y conserva el extremo final abierto', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    const shared = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, t: 1 });
    expect(shared?.segmentIndex).toBe(1);
    expect(shared?.t).toBe(0);
    expect(shared?.position).toEqual([100, 0, 0]);
    expect(shared?.chainage).toBe(100);

    const open = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1, t: 1 });
    expect(open?.segmentIndex).toBe(1);
    expect(open?.t).toBe(1);
    expect(open?.position).toEqual([200, 0, 0]);
    expect(open?.chainage).toBe(200);
  });

  it('no sustituye un segmento degenerado ni ajusta el índice', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    const degenerate = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1, t: 0.5 });
    expect(degenerate).toBeNull();

    const afterDegenerate = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 2, t: 0.5 });
    expect(afterDegenerate?.segmentIndex).toBe(2);
    expect(afterDegenerate?.chainage).toBe(150);
  });

  it('conserva t=1 del segmento actual cuando el siguiente es degenerado', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    const kept = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, t: 1 });
    expect(kept?.segmentIndex).toBe(0);
    expect(kept?.t).toBe(1);
    expect(kept?.position).toEqual([100, 0, 0]);
    expect(kept?.chainage).toBe(100);
  });

  it('rechaza el segmento degenerado incluso en t=1', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    const degenerateAtEnd = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1, t: 1 });
    expect(degenerateAtEnd).toBeNull();
  });

  it('en anillo cerrado no envuelve la estación final con la inicial', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [0, 0, 0],
    ];
    const closing = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1, t: 1 });
    expect(closing?.segmentIndex).toBe(1);
    expect(closing?.t).toBe(1);
    expect(closing?.chainage).toBe(200);
  });

  it('rechaza entradas inválidas sin convertir en cero', () => {
    const basic: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: [], segmentIndex: 0, t: 0.5 })).toBeNull();
    expect(
      createCurveAnchor({
        context,
        curveId: 'curva-a',
        points: [
          [0, 0, 0],
          [Number.NaN, 0, 0],
        ],
        segmentIndex: 0,
        t: 0.5,
      }),
    ).toBeNull();
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: basic, segmentIndex: -1, t: 0.5 })).toBeNull();
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: basic, segmentIndex: 1, t: 0.5 })).toBeNull();
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: basic, segmentIndex: 0.5, t: 0.5 })).toBeNull();
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: basic, segmentIndex: 0, t: -0.1 })).toBeNull();
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: basic, segmentIndex: 0, t: 1.1 })).toBeNull();
    expect(createCurveAnchor({ context, curveId: 'curva-a', points: basic, segmentIndex: 0, t: Number.NaN })).toBeNull();
  });
});

describe('projectCurveAnchor', () => {
  it('proyecta la posición observada sobre la arista 0..100 y ancla en 20 y 80', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const at20 = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [20, 0, 0] });
    const at80 = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [80, 0, 0] });

    expect(at20).not.toBeNull();
    expect(at80).not.toBeNull();
    expect(at20?.position).toEqual([20, 0, 0]);
    expect(at80?.position).toEqual([80, 0, 0]);
    expect(at20?.chainage).toBe(20);
    expect(at80?.chainage).toBe(80);
    expect(at20?.segmentIndex).toBe(0);
    expect(at20?.t).toBe(0.2);
    expect(at80?.t).toBe(0.8);
  });

  it('proyecta sobre el segmento 3D y separa la estación XY de la elevación', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [10, 0, 10],
    ];
    const anchor = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [5, 0, 0] });
    expect(anchor?.segmentIndex).toBe(0);
    expect(anchor?.t).toBe(0.25);
    expect(anchor?.position).toEqual([2.5, 0, 2.5]);
    expect(anchor?.chainage).toBe(2.5);
  });

  it('ajusta al rango [0,1] y conserva la canonicalización de createCurveAnchor', () => {
    const points: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
      [200, 0, 0],
    ];
    const before = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [-50, 10, 7] });
    expect(before?.segmentIndex).toBe(0);
    expect(before?.t).toBe(0);
    expect(before?.position).toEqual([0, 0, 0]);
    expect(before?.chainage).toBe(0);

    const vertex = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [100, 0, 0] });
    expect(vertex?.segmentIndex).toBe(1);
    expect(vertex?.t).toBe(0);
    expect(vertex?.chainage).toBe(100);

    const after = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1, position: [300, 0, 0] });
    expect(after?.segmentIndex).toBe(1);
    expect(after?.t).toBe(1);
    expect(after?.chainage).toBe(200);
  });

  it('mantiene precisión en coordenadas grandes y ignora el offset perpendicular XY', () => {
    const points: readonly MiningPoint3D[] = [
      [1e9, 1e9, 0],
      [1e9 + 10, 1e9, 0],
    ];
    const anchor = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [1e9 + 5, 1e9 + 1, 0] });
    expect(anchor?.t).toBe(0.5);
    expect(anchor?.position).toEqual([1e9 + 5, 1e9, 0]);
    expect(anchor?.chainage).toBe(5);
  });

  it('rechaza consultas, puntos, índices y segmentos inválidos sin ajustarlos', () => {
    const basic: readonly MiningPoint3D[] = [
      [0, 0, 0],
      [100, 0, 0],
    ];
    const base = { context, curveId: 'curva-a', points: basic, segmentIndex: 0 };
    expect(projectCurveAnchor({ ...base, position: [Number.NaN, 0, 0] })).toBeNull();
    expect(projectCurveAnchor({ ...base, position: [Number.POSITIVE_INFINITY, 0, 0] })).toBeNull();
    expect(
      projectCurveAnchor({
        ...base,
        points: [
          [Number.NaN, 0, 0],
          [100, 0, 0],
        ],
        position: [50, 0, 0],
      }),
    ).toBeNull();
    expect(projectCurveAnchor({ ...base, segmentIndex: -1, position: [50, 0, 0] })).toBeNull();
    expect(projectCurveAnchor({ ...base, segmentIndex: 1, position: [50, 0, 0] })).toBeNull();
    expect(projectCurveAnchor({ ...base, segmentIndex: 0.5, position: [50, 0, 0] })).toBeNull();
    expect(
      projectCurveAnchor({
        ...base,
        points: [
          [0, 0, 0],
          [0, 0, 5],
        ],
        position: [0, 0, 2],
      }),
    ).toBeNull();
  });

  it('no muta las entradas congeladas', () => {
    const points = Object.freeze([
      [0, 0, 0],
      [100, 0, 0],
    ]) as readonly MiningPoint3D[];
    const position = Object.freeze([30, 4, 2]) as MiningPoint3D;
    const anchor = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position });
    expect(anchor?.t).toBe(0.3);
    expect(anchor?.chainage).toBe(30);
    expect(Object.isFrozen(points)).toBe(true);
    expect(Object.isFrozen(position)).toBe(true);
  });

  it('devuelve null cuando la proyección desborda a no finito', () => {
    const points: readonly MiningPoint3D[] = [
      [-1.7e308, 0, 0],
      [1.7e308, 0, 0],
    ];
    const anchor = projectCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, position: [0, 0, 0] });
    expect(anchor).toBeNull();
  });
});
