export type MiningPoint3D = readonly [east: number, north: number, elevation: number];

export interface CurveSelectionContext {
  readonly designMeshId: string;
  readonly geometryKey: string;
}

export interface CurveAnchor {
  readonly context: CurveSelectionContext;
  readonly curveId: string;
  readonly segmentIndex: number;
  readonly t: number;
  readonly position: MiningPoint3D;
  readonly chainage: number;
}
