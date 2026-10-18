import { describe, expectTypeOf, it } from 'vitest';
import type {
  CurveAnchor,
  CurveSelectionContext,
  MiningPoint3D,
} from '../curveSelectionTypes';

type IsAssignable<Source, Target> = [Source] extends [Target] ? true : false;

type MutablePoint = [number, number, number];
const context: CurveSelectionContext = {
  designMeshId: 'mesh-001',
  geometryKey: 'geometry-abc',
};
const anchor: CurveAnchor = {
  context,
  curveId: 'curve-001',
  segmentIndex: 3,
  t: 0.5,
  position: [3071230, 6254500, 1852],
  chainage: 1250.5,
};

describe('curveSelectionTypes', () => {
  it('MiningPoint3D es tupla readonly de 3 numeros en orden East/North/Elevation', () => {
    expectTypeOf<MiningPoint3D>().toEqualTypeOf<
      readonly [east: number, north: number, elevation: number]
    >();
    expectTypeOf<MiningPoint3D[0]>().toEqualTypeOf<number>();
    expectTypeOf<MiningPoint3D[1]>().toEqualTypeOf<number>();
    expectTypeOf<MiningPoint3D[2]>().toEqualTypeOf<number>();
    expectTypeOf<MiningPoint3D['length']>().toEqualTypeOf<3>();
    expectTypeOf<IsAssignable<MiningPoint3D, MutablePoint>>().toEqualTypeOf<false>();
    expectTypeOf<IsAssignable<MutablePoint, MiningPoint3D>>().toEqualTypeOf<true>();
  });

  it('CurveSelectionContext es exactamente dos strings readonly', () => {
    expectTypeOf<CurveSelectionContext>().toEqualTypeOf<{
      readonly designMeshId: string;
      readonly geometryKey: string;
    }>();
    expectTypeOf<CurveSelectionContext['designMeshId']>().toEqualTypeOf<string>();
    expectTypeOf<CurveSelectionContext['geometryKey']>().toEqualTypeOf<string>();
  });

  it('CurveAnchor es exactamente el contrato readonly sin campos legados', () => {
    expectTypeOf<CurveAnchor>().toEqualTypeOf<{
      readonly context: CurveSelectionContext;
      readonly curveId: string;
      readonly segmentIndex: number;
      readonly t: number;
      readonly position: MiningPoint3D;
      readonly chainage: number;
    }>();
    expectTypeOf<CurveAnchor['curveId']>().toEqualTypeOf<string>();
    expectTypeOf<CurveAnchor['segmentIndex']>().toEqualTypeOf<number>();
    expectTypeOf<CurveAnchor['t']>().toEqualTypeOf<number>();
    expectTypeOf<CurveAnchor['chainage']>().toEqualTypeOf<number>();
    expectTypeOf<CurveAnchor['position']>().toEqualTypeOf<MiningPoint3D>();
    expectTypeOf<CurveAnchor['context']>().toEqualTypeOf<CurveSelectionContext>();
  });

  it('Acepta un literal tipado valido', () => {
    expectTypeOf(anchor.position).toEqualTypeOf<MiningPoint3D>();
    expectTypeOf(anchor.curveId).toEqualTypeOf<string>();
    expectTypeOf(anchor.segmentIndex).toEqualTypeOf<number>();
    expectTypeOf(anchor.t).toEqualTypeOf<number>();
    expectTypeOf(anchor.chainage).toEqualTypeOf<number>();
  });
});
