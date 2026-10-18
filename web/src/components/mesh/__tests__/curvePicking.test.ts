import { describe, expect, it } from 'vitest';
import { OrthographicCamera, PerspectiveCamera, Vector3 } from 'three';
import { pickCurveCandidate } from '../curvePicking';
import type { CurvePickCandidate, CurvePickingInput } from '../curvePicking';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../../sections/curveSelectionTypes';

const context: CurveSelectionContext = { designMeshId: 'mesh-1', geometryKey: 'geo-1' };
const center: MiningPoint3D = [1000, 2000, 50];
const viewport = { width: 800, height: 600 };

function mineAt(offsetX: number, offsetY: number, offsetZ: number): MiningPoint3D {
  return [center[0] + offsetX, center[1] - offsetZ, center[2] + offsetY];
}

function anchorFor(
  curveId: string,
  position: MiningPoint3D,
  overrides: Partial<Omit<CurveAnchor, 'curveId' | 'position'>> = {},
): CurveAnchor {
  return { context, curveId, segmentIndex: 0, t: 0.5, chainage: 12.5, position, ...overrides };
}

function perspectiveCamera(): PerspectiveCamera {
  const camera = new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 100);
  camera.position.set(0, 0, 0);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

function orthographicCamera(): OrthographicCamera {
  const camera = new OrthographicCamera(-4, 4, 3, -3, 0.1, 100);
  camera.position.set(0, 0, 0);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

function projectedCss(
  position: MiningPoint3D,
  camera: PerspectiveCamera | OrthographicCamera,
): { x: number; y: number } {
  const ndc = new Vector3(
    position[0] - center[0],
    position[2] - center[2],
    -(position[1] - center[1]),
  ).project(camera);
  return { x: (ndc.x * 0.5 + 0.5) * viewport.width, y: (0.5 - ndc.y * 0.5) * viewport.height };
}

function inputFor(
  candidates: readonly CurvePickCandidate[],
  camera: PerspectiveCamera | OrthographicCamera,
  overrides: Partial<CurvePickingInput> = {},
): CurvePickingInput {
  return {
    candidates,
    context,
    selectedCurveId: 'curve-a',
    camera,
    center,
    viewport,
    pointer: { x: 400, y: 300 },
    ...overrides,
  };
}

function withDevicePixelRatio(dpr: number, run: () => void): void {
  const previous = Object.getOwnPropertyDescriptor(window, 'devicePixelRatio');
  Object.defineProperty(window, 'devicePixelRatio', { value: dpr, configurable: true });
  try {
    run();
  } finally {
    if (previous) {
      Object.defineProperty(window, 'devicePixelRatio', previous);
    } else {
      Reflect.deleteProperty(window, 'devicePixelRatio');
    }
  }
}

function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== 'object') return value;
  Object.freeze(value);
  for (const key of Object.getOwnPropertyNames(value)) {
    deepFreeze((value as Record<string, unknown>)[key]);
  }
  return value;
}

function deepFreezeInput(input: CurvePickingInput): CurvePickingInput {
  const { camera, ...rest } = input;
  const frozenRest = deepFreeze(rest) as Omit<CurvePickingInput, 'camera'>;
  return { ...frozenRest, camera };
}

describe('pickCurveCandidate', () => {
  it('cannot be won by a closer candidate from another curve than the active curve', () => {
    const camera = perspectiveCamera();
    const active = anchorFor('curve-a', mineAt(0.05, 0, -4));
    const neighbor = anchorFor('curve-b', mineAt(0.04, 0, -4));
    const neighborCss = projectedCss(neighbor.position, camera);
    const result = pickCurveCandidate(inputFor(
      [
        { anchor: active, visible: true },
        { anchor: neighbor, visible: true },
      ],
      camera,
      { pointer: { x: neighborCss.x + 1, y: neighborCss.y } },
    ));
    expect(result).toBe(active);
  });

  it('returns null without falling back when the active curve has no eligible candidate', () => {
    const camera = perspectiveCamera();
    const neighbor = anchorFor('curve-b', mineAt(0.04, 0, -4));
    const neighborCss = projectedCss(neighbor.position, camera);
    const result = pickCurveCandidate(inputFor(
      [{ anchor: neighbor, visible: true }],
      camera,
      { pointer: { x: neighborCss.x + 1, y: neighborCss.y } },
    ));
    expect(result).toBeNull();
  });

  it('applies the default CSS pixel radius inclusively, honors radiusPx and stays DPR independent', () => {
    const camera = perspectiveCamera();
    const point = anchorFor('curve-a', mineAt(0, 0, -4));
    const candidates = [{ anchor: point, visible: true }];
    const atBoundary = pickCurveCandidate(inputFor(candidates, camera, { pointer: { x: 392, y: 300 } }));
    expect(atBoundary).toBe(point);
    const beyond = pickCurveCandidate(inputFor(candidates, camera, { pointer: { x: 391, y: 300 } }));
    expect(beyond).toBeNull();
    withDevicePixelRatio(2, () => {
      const dprBoundary = pickCurveCandidate(inputFor(candidates, camera, { pointer: { x: 392, y: 300 } }));
      expect(dprBoundary).toBe(point);
      const tighter = pickCurveCandidate(inputFor(candidates, camera, { pointer: { x: 392, y: 300 }, radiusPx: 4 }));
      expect(tighter).toBeNull();
    });
  });

  it('projects candidates through the current perspective camera in CSS pixels', () => {
    const camera = perspectiveCamera();
    const target = anchorFor('curve-a', mineAt(0.5, 0.3, -6));
    const decoy = anchorFor('curve-a', mineAt(-0.5, -0.3, -6));
    const targetCss = projectedCss(target.position, camera);
    const decoyCss = projectedCss(decoy.position, camera);
    expect(Math.hypot(targetCss.x - decoyCss.x, targetCss.y - decoyCss.y)).toBeGreaterThan(8);
    const result = pickCurveCandidate(inputFor(
      [
        { anchor: decoy, visible: true },
        { anchor: target, visible: true },
      ],
      camera,
      { pointer: { x: targetCss.x, y: targetCss.y } },
    ));
    expect(result).toBe(target);
  });

  it('honors camera zoom when computing pixel distances', () => {
    const camera = perspectiveCamera();
    const point = anchorFor('curve-a', mineAt(0.2, 0, -4));
    const candidates = [{ anchor: point, visible: true }];
    const pointCss = projectedCss(point.position, camera);
    const pointer = { x: pointCss.x - 16, y: pointCss.y };
    const beforeZoom = pickCurveCandidate(inputFor(candidates, camera, { pointer, radiusPx: 30 }));
    expect(beforeZoom).toBe(point);
    camera.zoom = 2;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    const afterZoom = pickCurveCandidate(inputFor(candidates, camera, { pointer, radiusPx: 30 }));
    expect(afterZoom).toBeNull();
  });

  it('rejects candidates behind the camera and outside the near and far planes', () => {
    const camera = perspectiveCamera();
    const behind = anchorFor('curve-a', mineAt(0, 0, 5));
    const tooNear = anchorFor('curve-a', mineAt(0, 0, -0.05));
    const tooFar = anchorFor('curve-a', mineAt(0, 0, -150));
    for (const anchor of [behind, tooNear, tooFar]) {
      expect(pickCurveCandidate(inputFor([{ anchor, visible: true }], camera))).toBeNull();
    }
    const inFront = anchorFor('curve-a', mineAt(0, 0, -4));
    expect(pickCurveCandidate(inputFor([{ anchor: inFront, visible: true }], camera))).toBe(inFront);
  });

  it('picks with orthographic projection and breaks equal-distance ties by camera depth', () => {
    const camera = orthographicCamera();
    const near = anchorFor('curve-a', mineAt(0.05, 0, -10));
    const far = anchorFor('curve-a', mineAt(0.05, 0, -50));
    expect(projectedCss(near.position, camera)).toEqual(projectedCss(far.position, camera));
    const css = projectedCss(near.position, camera);
    const result = pickCurveCandidate(inputFor(
      [
        { anchor: far, visible: true },
        { anchor: near, visible: true },
      ],
      camera,
      { pointer: { x: css.x + 5, y: css.y }, radiusPx: 8 },
    ));
    expect(result).toBe(near);
  });

  it('rejects candidates flagged as not visible', () => {
    const camera = perspectiveCamera();
    const hidden = anchorFor('curve-a', mineAt(0.02, 0, -4));
    const shown = anchorFor('curve-a', mineAt(0.05, 0, -4));
    const result = pickCurveCandidate(inputFor(
      [
        { anchor: hidden, visible: false },
        { anchor: shown, visible: true },
      ],
      camera,
    ));
    expect(result).toBe(shown);
    expect(pickCurveCandidate(inputFor([{ anchor: hidden, visible: false }], camera))).toBeNull();
  });

  it('rejects anchors whose context is stale by value on both identity fields', () => {
    const camera = perspectiveCamera();
    const staleMesh = anchorFor('curve-a', mineAt(0.01, 0, -4), {
      context: { designMeshId: 'mesh-2', geometryKey: 'geo-1' },
    });
    const staleGeometry = anchorFor('curve-a', mineAt(0.02, 0, -4), {
      context: { designMeshId: 'mesh-1', geometryKey: 'geo-9' },
    });
    const current = anchorFor('curve-a', mineAt(0.05, 0, -4));
    const result = pickCurveCandidate(inputFor(
      [
        { anchor: staleMesh, visible: true },
        { anchor: staleGeometry, visible: true },
        { anchor: current, visible: true },
      ],
      camera,
    ));
    expect(result).toBe(current);
    expect(pickCurveCandidate(inputFor([{ anchor: staleMesh, visible: true }], camera))).toBeNull();
  });

  it('rejects invalid anchor numerics and invalid picking inputs', () => {
    const camera = perspectiveCamera();
    const base = anchorFor('curve-a', mineAt(0, 0, -4));
    expect(pickCurveCandidate(inputFor([{ anchor: base, visible: true }], camera))).toBe(base);
    const brokenAnchors = [
      { ...base, position: [Number.NaN, base.position[1], base.position[2]] as MiningPoint3D },
      { ...base, position: [base.position[0], base.position[1], Number.POSITIVE_INFINITY] as MiningPoint3D },
      { ...base, chainage: -1 },
      { ...base, chainage: Number.NaN },
      { ...base, t: -0.1 },
      { ...base, t: 1.1 },
      { ...base, t: Number.NaN },
      { ...base, segmentIndex: -1 },
      { ...base, segmentIndex: 2.5 },
      { ...base, segmentIndex: Number.NaN },
    ];
    for (const anchor of brokenAnchors) {
      expect(pickCurveCandidate(inputFor([{ anchor, visible: true }], camera))).toBeNull();
    }
    const basePosition = base.position;
    const brokenInputs: Partial<CurvePickingInput>[] = [
      { viewport: { width: 0, height: 600 } },
      { viewport: { width: 800, height: -600 } },
      { viewport: { width: Number.POSITIVE_INFINITY, height: 600 } },
      { pointer: { x: Number.NaN, y: 300 } },
      { pointer: { x: 400, y: Number.POSITIVE_INFINITY } },
      { center: [Number.NaN, 2000, 50] },
      { center: [1000, 2000, Number.POSITIVE_INFINITY] },
      { radiusPx: -1 },
      { radiusPx: Number.NaN },
    ];
    for (const override of brokenInputs) {
      expect(pickCurveCandidate(inputFor([{ anchor: base, visible: true }], camera, override))).toBeNull();
    }
    void basePosition;
  });

  it('breaks exact ties deterministically by curve, segment and fraction', () => {
    const camera = perspectiveCamera();
    const position = mineAt(0, 0, -4);
    const otherCurve = anchorFor('curve-b', position, { segmentIndex: 0, t: 0.5 });
    const laterSegment = anchorFor('curve-a', position, { segmentIndex: 5, t: 0.1 });
    const laterFraction = anchorFor('curve-a', position, { segmentIndex: 2, t: 0.9 });
    const winner = anchorFor('curve-a', position, { segmentIndex: 2, t: 0.4 });
    const result = pickCurveCandidate(inputFor(
      [otherCurve, laterSegment, laterFraction, winner].map((anchor) => ({ anchor, visible: true })),
      camera,
      { selectedCurveId: null },
    ));
    expect(result).toBe(winner);
  });

  it('does not mutate the frozen input or the camera matrices', () => {
    const camera = perspectiveCamera();
    const winner = anchorFor('curve-a', mineAt(0.05, 0, -4));
    const other = anchorFor('curve-b', mineAt(0.02, 0, -4));
    const input = deepFreezeInput(inputFor(
      [
        { anchor: other, visible: true },
        { anchor: winner, visible: true },
      ],
      camera,
    ));
    const matrixWorld = Array.from(camera.matrixWorld.elements);
    const projectionMatrix = Array.from(camera.projectionMatrix.elements);
    const matrixWorldInverse = Array.from(camera.matrixWorldInverse.elements);
    const cameraPosition = camera.position.toArray();
    const result = pickCurveCandidate(input);
    expect(result).toBe(winner);
    expect(Array.from(camera.matrixWorld.elements)).toEqual(matrixWorld);
    expect(Array.from(camera.projectionMatrix.elements)).toEqual(projectionMatrix);
    expect(Array.from(camera.matrixWorldInverse.elements)).toEqual(matrixWorldInverse);
    expect(camera.position.toArray()).toEqual(cameraPosition);
  });
});
