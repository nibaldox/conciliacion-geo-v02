import { describe, expect, it } from 'vitest';
import {
  BufferGeometry,
  Camera,
  DoubleSide,
  Group,
  Line,
  LineBasicMaterial,
  Mesh,
  MeshBasicMaterial,
  OrthographicCamera,
  PerspectiveCamera,
  PlaneGeometry,
  Raycaster,
  Vector2,
  Vector3,
} from 'three';
import type { Intersection, Object3D } from 'three';
import {
  createCurveSceneClickHandler,
  createCurveScenePreviewHandler,
  getCurveSearchThreshold,
  handleCurveSceneClick,
  hasCurvePreviewViewChanged,
  resolveCurveSceneCandidate,
  TOUCH_RADIUS_PX,
} from '../curveScenePicking';
import type { CurvePreviewViewSnapshot, CurveScenePickingInput } from '../curveScenePicking';
import type { CurveGeometryPolyline, CurveGeometrySnapshot } from '../../sections/curveGeometryAdapter';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../../sections/curveSelectionTypes';

const context: CurveSelectionContext = { designMeshId: 'mesh-1', geometryKey: 'geo-1' };
const center: MiningPoint3D = [1000, 2000, 50];
const viewport = { width: 800, height: 600 };

function mineAt(offsetX: number, offsetY: number, offsetZ: number): MiningPoint3D {
  return [center[0] + offsetX, center[1] - offsetZ, center[2] + offsetY];
}

const curveAPoints: readonly MiningPoint3D[] = [mineAt(-0.1, 0, -4.1), mineAt(0.1, 0, -4.1)];
const curveBPoints: readonly MiningPoint3D[] = [mineAt(-0.1, 0, -4), mineAt(0.1, 0, -4)];

function toRenderPoint(point: MiningPoint3D): Vector3 {
  return new Vector3(
    point[0] - center[0],
    point[2] - center[2],
    -(point[1] - center[1]),
  );
}

function snapshotWith(...polylines: readonly CurveGeometryPolyline[]): CurveGeometrySnapshot {
  return { context, curves: new Map(polylines.map((polyline) => [polyline.id, polyline] as const)) };
}

function taggedLine(curveId: string, points: readonly MiningPoint3D[]): Line {
  const line = new Line(new BufferGeometry().setFromPoints(points.map(toRenderPoint)), new LineBasicMaterial());
  line.userData.curveId = curveId;
  line.updateMatrixWorld(true);
  return line;
}

function perspectiveCamera(): PerspectiveCamera {
  const camera = new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 100);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

function projectedCss(point: MiningPoint3D | Vector3, camera: Camera): { x: number; y: number } {
  const render = point instanceof Vector3 ? point.clone() : toRenderPoint(point);
  const ndc = render.project(camera);
  return { x: (ndc.x * 0.5 + 0.5) * viewport.width, y: (0.5 - ndc.y * 0.5) * viewport.height };
}

function planeAt(z: number, options: { transparent?: boolean; opacity?: number } = {}): Mesh {
  const material = new MeshBasicMaterial();
  if (options.transparent !== undefined) material.transparent = options.transparent;
  if (options.opacity !== undefined) material.opacity = options.opacity;
  const mesh = new Mesh(new PlaneGeometry(4, 4), material);
  mesh.position.z = z;
  mesh.updateMatrixWorld(true);
  return mesh;
}

function thresholdOf(camera: Camera, viewportHeight: number, radiusPx?: number): number {
  const value = getCurveSearchThreshold(camera, viewportHeight, radiusPx);
  if (value === null) throw new Error('expected a finite world search threshold');
  return value;
}

function raycastIntersections(camera: Camera, objects: Object3D[], cssPointer: { x: number; y: number }) {
  for (const object of objects) {
    object.updateMatrixWorld(true);
  }
  const raycaster = new Raycaster();
  raycaster.params.Line.threshold = 0.05;
  raycaster.layers.enableAll();
  raycaster.setFromCamera(
    new Vector2(
      (cssPointer.x * 2) / viewport.width - 1,
      -((cssPointer.y * 2) / viewport.height - 1),
    ),
    camera,
  );
  return raycaster.intersectObjects(objects, false);
}

function inputFor(overrides: Partial<CurveScenePickingInput> = {}): CurveScenePickingInput {
  return {
    snapshot: snapshotWith(
      { id: 'curve-a', points: curveAPoints },
      { id: 'curve-b', points: curveBPoints },
    ),
    selectedCurveId: 'curve-a',
    camera: perspectiveCamera(),
    center,
    viewport,
    pointer: { x: 400, y: 300 },
    intersections: [],
    occluders: [],
    ...overrides,
  };
}

describe('curveScenePicking', () => {
  it('resolves every intersection and consumes a neighbor-first event exactly once for the active curve', () => {
    const camera = perspectiveCamera();
    const activeLine = taggedLine('curve-a', curveAPoints);
    const neighborLine = taggedLine('curve-b', curveBPoints);
    const pointer = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
    const intersections = raycastIntersections(camera, [activeLine, neighborLine], pointer);
    expect(intersections.length).toBe(2);
    expect(intersections[0].object).toBe(neighborLine);
    expect(intersections[1].object).toBe(activeLine);

    const picks: CurveAnchor[] = [];
    let stops = 0;
    const result = handleCurveSceneClick(
      inputFor({ camera, pointer, intersections }),
      {
        dragDistancePx: 0,
        onPick: (anchor) => {
          picks.push(anchor);
        },
        stopPropagation: () => {
          stops += 1;
        },
      },
    );
    expect(result).not.toBeNull();
    expect(result?.curveId).toBe('curve-a');
    expect(result?.segmentIndex).toBe(0);
    expect(result?.t).toBeCloseTo(0.5, 10);
    expect(result?.position[0]).toBeCloseTo(1000, 9);
    expect(result?.position[1]).toBeCloseTo(2004.1, 9);
    expect(result?.position[2]).toBeCloseTo(50, 9);
    expect(result?.chainage).toBeCloseTo(0.1, 9);
    expect(stops).toBe(1);
    expect(picks.length).toBe(1);
    expect(picks[0]).toBe(result);
    expect(resolveCurveSceneCandidate(inputFor({ camera, pointer, intersections }))).toEqual(result);
  });

  it('ignores invalid drag distances and invalid radii with zero callbacks', () => {
    const camera = perspectiveCamera();
    const line = taggedLine('curve-a', curveAPoints);
    const pointer = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
    const intersections = raycastIntersections(camera, [line], pointer);
    const input = inputFor({ camera, pointer, intersections });
    const expectNoCalls = (dragDistancePx: number, radiusPx?: number): void => {
      let picks = 0;
      let stops = 0;
      const result = handleCurveSceneClick(
        radiusPx === undefined ? input : { ...input, radiusPx },
        {
          dragDistancePx,
          onPick: () => {
            picks += 1;
          },
          stopPropagation: () => {
            stops += 1;
          },
        },
      );
      expect(result).toBeNull();
      expect(picks).toBe(0);
      expect(stops).toBe(0);
    };
    expectNoCalls(Number.NaN);
    expectNoCalls(-0.5);
    expectNoCalls(3.0001);
    expectNoCalls(Number.POSITIVE_INFINITY);
    expectNoCalls(0, -1);
    expectNoCalls(0, Number.NaN);
    let picks = 0;
    let stops = 0;
    const boundary = handleCurveSceneClick(input, {
      dragDistancePx: 3,
      onPick: () => {
        picks += 1;
      },
      stopPropagation: () => {
        stops += 1;
      },
    });
    expect(boundary).not.toBeNull();
    expect(boundary?.curveId).toBe('curve-a');
    expect(picks).toBe(1);
    expect(stops).toBe(1);
  });

  it('ignores hidden objects, hidden ancestors, foreign camera layers, untagged and foreign curves', () => {
    const camera = perspectiveCamera();
    const pointer = { x: 400, y: 300 };
    const resolveFor = (objects: Object3D[], snapshot?: CurveGeometrySnapshot): CurveAnchor | null => {
      return resolveCurveSceneCandidate(
        inputFor({
          camera,
          pointer,
          intersections: raycastIntersections(camera, objects, pointer),
          ...(snapshot === undefined ? {} : { snapshot }),
        }),
      );
    };
    const controlLine = taggedLine('curve-a', curveAPoints);
    expect(resolveFor([controlLine])).not.toBeNull();

    const hiddenLine = taggedLine('curve-a', curveAPoints);
    hiddenLine.visible = false;
    expect(resolveFor([hiddenLine])).toBeNull();

    const group = new Group();
    group.visible = false;
    const child = taggedLine('curve-a', curveAPoints);
    group.add(child);
    group.updateMatrixWorld(true);
    expect(resolveFor([child])).toBeNull();

    const layered = taggedLine('curve-a', curveAPoints);
    layered.layers.set(1);
    expect(resolveFor([layered])).toBeNull();

    const untagged = new Mesh(new PlaneGeometry(1, 1), new MeshBasicMaterial());
    untagged.position.z = -4.1;
    untagged.updateMatrixWorld(true);
    expect(resolveFor([untagged])).toBeNull();

    const unknownCurve = taggedLine('curve-z', curveAPoints);
    expect(resolveFor([unknownCurve])).toBeNull();

    const foreignNeighbor = taggedLine('curve-b', curveBPoints);
    expect(resolveFor([foreignNeighbor])).toBeNull();
  });

  it('rejects out-of-range, negative, fractional and missing segment indices without clamping', () => {
    const camera = perspectiveCamera();
    const line = taggedLine('curve-a', curveAPoints);
    const pointer = { x: 400, y: 300 };
    const forged = (index: number | undefined): Intersection<Object3D> => ({
      distance: 4.1,
      point: new Vector3(0, 0, -4.1),
      index,
      object: line,
    });
    for (const badIndex of [5, -1, 0.5, Number.NaN, undefined]) {
      const result = resolveCurveSceneCandidate(
        inputFor({ camera, pointer, intersections: [forged(badIndex)] }),
      );
      expect(result).toBeNull();
    }
    const longPoints: readonly MiningPoint3D[] = [
      mineAt(-0.2, 0, -4.1),
      mineAt(0, 0, -4.1),
      mineAt(0.2, 0, -4.1),
    ];
    const longLine = taggedLine('curve-a', longPoints);
    const longPointer = projectedCss(toRenderPoint(mineAt(0.1, 0, -4.1)), camera);
    const longIntersections = raycastIntersections(camera, [longLine], longPointer);
    expect(longIntersections.length).toBe(1);
    const anchor = resolveCurveSceneCandidate(inputFor({
      snapshot: snapshotWith({ id: 'curve-a', points: longPoints }),
      camera,
      pointer: longPointer,
      intersections: longIntersections,
    }));
    expect(anchor?.segmentIndex).toBe(1);
    expect(anchor?.t).toBeCloseTo(0.5, 7);
    expect(anchor?.chainage).toBeCloseTo(0.3, 7);
  });

  it('rejects an anchor occluded by an opaque mesh strictly in front of it with zero callbacks', () => {
    const camera = perspectiveCamera();
    const line = taggedLine('curve-a', curveAPoints);
    const blocker = planeAt(-3);
    const pointer = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
    const intersections = raycastIntersections(camera, [line, blocker], pointer);
    expect(intersections[0].object).toBe(blocker);
    const input = inputFor({ camera, pointer, intersections, occluders: [blocker] });
    expect(resolveCurveSceneCandidate(input)).toBeNull();
    expect(resolveCurveSceneCandidate({ ...input, occluders: [] })).not.toBeNull();
    const justBeyondRoundoff = planeAt(-4.1 + 1e-4);
    expect(
      resolveCurveSceneCandidate(inputFor({ camera, pointer, intersections, occluders: [justBeyondRoundoff] })),
    ).toBeNull();
    let picks = 0;
    let stops = 0;
    const clicked = handleCurveSceneClick(input, {
      dragDistancePx: 0,
      onPick: () => {
        picks += 1;
      },
      stopPropagation: () => {
        stops += 1;
      },
    });
    expect(clicked).toBeNull();
    expect(picks).toBe(0);
    expect(stops).toBe(0);
  });

  it('accepts anchors when candidate occluders are hidden, transparent, translucent, behind, coplanar or within float roundoff', () => {
    const camera = perspectiveCamera();
    const line = taggedLine('curve-a', curveAPoints);
    const pointer = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
    const intersections = raycastIntersections(camera, [line], pointer);
    expect(intersections.length).toBe(1);
    const input = inputFor({ camera, pointer, intersections });

    const hidden = planeAt(-3);
    hidden.visible = false;
    expect(resolveCurveSceneCandidate({ ...input, occluders: [hidden] })).not.toBeNull();

    const transparent = planeAt(-3, { transparent: true });
    expect(resolveCurveSceneCandidate({ ...input, occluders: [transparent] })).not.toBeNull();

    const translucent = planeAt(-3, { opacity: 0.5 });
    expect(resolveCurveSceneCandidate({ ...input, occluders: [translucent] })).not.toBeNull();

    const coplanar = planeAt(-4.1);
    expect(resolveCurveSceneCandidate({ ...input, occluders: [coplanar] })).not.toBeNull();

    const behind = planeAt(-5);
    expect(resolveCurveSceneCandidate({ ...input, occluders: [behind] })).not.toBeNull();

    const withinRoundoff = planeAt(-4.1 + 1e-8);
    expect(resolveCurveSceneCandidate({ ...input, occluders: [withinRoundoff] })).not.toBeNull();
  });

  it('computes the conservative world search threshold per camera type and rejects invalid inputs', () => {
    const perspective = perspectiveCamera();
    const base = thresholdOf(perspective, 600);
    expect(base).toBeCloseTo((2 * perspective.far * 8) / (perspective.projectionMatrix.elements[5] * 600), 12);
    perspective.zoom = 2;
    perspective.updateProjectionMatrix();
    const zoomed = thresholdOf(perspective, 600);
    expect(zoomed).toBeCloseTo((2 * perspective.far * 8) / (perspective.projectionMatrix.elements[5] * 600), 12);
    expect(zoomed).toBeLessThan(base);
    const ortho = new OrthographicCamera(-4, 4, 3, -3, 0.1, 100);
    ortho.updateProjectionMatrix();
    ortho.updateMatrixWorld(true);
    expect(thresholdOf(ortho, 600)).toBeCloseTo((2 * 8) / (ortho.projectionMatrix.elements[5] * 600), 12);
    expect(thresholdOf(perspective, 600, 20)).toBeCloseTo(
      (2 * perspective.far * 20) / (perspective.projectionMatrix.elements[5] * 600),
      12,
    );
    expect(getCurveSearchThreshold(new Camera(), 600)).toBeNull();
    expect(getCurveSearchThreshold(perspective, 0)).toBeNull();
    expect(getCurveSearchThreshold(perspective, Number.NaN)).toBeNull();
    expect(getCurveSearchThreshold(perspective, 600, -1)).toBeNull();
    expect(getCurveSearchThreshold(perspective, 600, Number.NaN)).toBeNull();
    const degenerate = new OrthographicCamera(-4, 4, 3, 3, 0.1, 100);
    degenerate.updateProjectionMatrix();
    expect(getCurveSearchThreshold(degenerate, 600)).toBeNull();
  });

  it('rejects an overflowing finite-input perspective threshold', () => {
    const camera = new PerspectiveCamera(60, 1, 0.1, 1e308);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    expect(getCurveSearchThreshold(camera, 1000, 8)).toBeNull();
  });

  it('flags a projection-only zoom change as a preview view change while pose and viewport stay identical', () => {
    const camera = new OrthographicCamera(-4, 4, 3, -3, 0.1, 100);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    const snapshot: CurvePreviewViewSnapshot = {
      position: camera.position.clone(),
      quaternion: camera.quaternion.clone(),
      projection: camera.projectionMatrix.clone(),
      viewport,
    };
    expect(hasCurvePreviewViewChanged(snapshot, camera, viewport)).toBe(false);
    camera.zoom = 2;
    camera.updateProjectionMatrix();
    expect(snapshot.projection.equals(camera.projectionMatrix)).toBe(false);
    expect(hasCurvePreviewViewChanged(snapshot, camera, viewport)).toBe(true);
    camera.zoom = 1;
    camera.updateProjectionMatrix();
    camera.position.set(1, 0, 0);
    expect(hasCurvePreviewViewChanged(snapshot, camera, viewport)).toBe(true);
    camera.position.set(0, 0, 0);
    expect(hasCurvePreviewViewChanged(snapshot, camera, { width: viewport.width, height: viewport.height + 1 })).toBe(true);
    expect(hasCurvePreviewViewChanged(snapshot, camera, viewport)).toBe(false);
  });

  describe('createCurveSceneClickHandler (event adapter)', () => {
    function fakeCanvas(): { left: number; top: number; width: number; height: number; getBoundingClientRect: () => { left: number; top: number; width: number; height: number } } {
      const rect = { left: 20, top: 10, width: viewport.width, height: viewport.height };
      return { ...rect, getBoundingClientRect: () => ({ left: rect.left, top: rect.top, width: rect.width, height: rect.height }) };
    }

    function fixtureEvent(
      camera: Camera,
      canvas: ReturnType<typeof fakeCanvas>,
      clients: { clientX: number; clientY: number },
      castAt?: { x: number; y: number },
    ) {
      const cast = castAt ?? { x: clients.clientX - canvas.left, y: clients.clientY - canvas.top };
      return {
        intersections: raycastIntersections(
          camera,
          [taggedLine('curve-a', curveAPoints), taggedLine('curve-b', curveBPoints)],
          cast,
        ),
        nativeEvent: { clientX: clients.clientX, clientY: clients.clientY },
        delta: 0,
        stopPropagation: (): void => undefined,
      };
    }

    it('routes a real Three click event through the factory and picks the active curve from client coords with a nonzero canvas origin', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const css = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);

      const event = fixtureEvent(camera, canvas, { clientX: canvas.left + css.x, clientY: canvas.top + css.y });
      expect(event.intersections.length).toBe(2);
      expect(event.intersections[0]?.object.userData.curveId).toBe('curve-b');
      expect(event.intersections[1]?.object.userData.curveId).toBe('curve-a');

      const picks: CurveAnchor[] = [];
      let stops = 0;
      const handler = createCurveSceneClickHandler({
        snapshot: inputFor().snapshot,
        selectedCurveId: 'curve-a',
        camera,
        center,
        canvas,
        getOccluders: () => [],
        onPick: (anchor) => {
          picks.push(anchor);
        },
      });
      const anchor = handler({
        ...event,
        stopPropagation: () => {
          stops += 1;
        },
      });
      expect(anchor).not.toBeNull();
      expect(anchor?.curveId).toBe('curve-a');
      expect(anchor?.segmentIndex).toBe(0);
      expect(stops).toBe(1);
      expect(picks.length).toBe(1);
      expect(picks[0]).toBe(anchor);
    });

    it('does nothing for a null onPick handler: returns null with zero stops', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const css = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
      const event = fixtureEvent(camera, canvas, { clientX: canvas.left + css.x, clientY: canvas.top + css.y });
      let stops = 0;
      const handler = createCurveSceneClickHandler({
        snapshot: inputFor().snapshot,
        selectedCurveId: 'curve-a',
        camera,
        center,
        canvas,
        getOccluders: () => [],
        onPick: null,
      });
      expect(handler({ ...event, stopPropagation: () => { stops += 1; } })).toBeNull();
      expect(stops).toBe(0);
    });

    it('rejects out-of-radius pointers and drag deltas beyond the limit without consuming the event', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const css = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
      const handler = createCurveSceneClickHandler({
        snapshot: inputFor().snapshot,
        selectedCurveId: 'curve-a',
        camera,
        center,
        canvas,
        getOccluders: () => [],
        onPick: (): void => undefined,
      });
      let stops = 0;
      const consume = (event: { intersections: Intersection<Object3D>[]; nativeEvent: { clientX: number; clientY: number }; delta: number }): CurveAnchor | null =>
        handler({ ...event, stopPropagation: () => { stops += 1; } });


      const hitEvent = fixtureEvent(camera, canvas, { clientX: canvas.left + css.x, clientY: canvas.top + css.y });
      expect(hitEvent.intersections.length).toBe(2);
      const offRadius = { ...hitEvent, nativeEvent: { clientX: canvas.left + css.x + viewport.width, clientY: canvas.top + css.y + viewport.height } };
      expect(consume(offRadius)).toBeNull();
      expect(consume({ ...offRadius, delta: 1 })).toBeNull();
      expect(stops).toBe(0);


      const okEvent = { ...hitEvent, nativeEvent: { clientX: canvas.left + css.x, clientY: canvas.top + css.y } };
      expect(consume({ ...okEvent, delta: 3.0001 })).toBeNull();
      expect(stops).toBe(0);
      expect(consume({ ...okEvent, delta: 3 })).not.toBeNull();
      expect(stops).toBe(1);
    });

    function handlerFor(camera: Camera, canvas: ReturnType<typeof fakeCanvas>, picks: CurveAnchor[]): (event: Parameters<ReturnType<typeof createCurveSceneClickHandler>>[0]) => CurveAnchor | null {
      return createCurveSceneClickHandler({
        snapshot: inputFor().snapshot,
        selectedCurveId: 'curve-a',
        camera,
        center,
        canvas,
        getOccluders: () => [],
        onPick: (anchor) => {
          picks.push(anchor);
        },
      });
    }

    function touchEvent(
      camera: Camera,
      canvas: ReturnType<typeof fakeCanvas>,
      pointerType: string | undefined,
      delta: number,
    ): { intersections: Intersection<Object3D>[]; nativeEvent: { clientX: number; clientY: number; pointerType?: string }; delta: number; stopPropagation: () => void } {
      const css = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
      const base = fixtureEvent(camera, canvas, { clientX: canvas.left + css.x, clientY: canvas.top + css.y });
      return {
        ...base,
        delta,
        nativeEvent: pointerType === undefined
          ? { clientX: base.nativeEvent.clientX, clientY: base.nativeEvent.clientY }
          : { clientX: base.nativeEvent.clientX, clientY: base.nativeEvent.clientY, pointerType },
        stopPropagation: (): void => undefined,
      };
    }

    it('selects the active curve for a touch tap with a 10 px delta within the touch tolerances', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const picks: CurveAnchor[] = [];
      let stops = 0;
      const handler = handlerFor(camera, canvas, picks);
      const event = touchEvent(camera, canvas, 'touch', 10);
      const anchor = handler({
        ...event,
        stopPropagation: () => {
          stops += 1;
        },
      });
      expect(anchor).not.toBeNull();
      expect(anchor?.curveId).toBe('curve-a');
      expect(anchor?.segmentIndex).toBe(0);
      expect(stops).toBe(1);
      expect(picks.length).toBe(1);
      expect(picks[0]).toBe(anchor);
    });

    it('keeps the desktop contract: a mouse event with a 10 px delta is still rejected', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const picks: CurveAnchor[] = [];
      let stops = 0;
      const handler = handlerFor(camera, canvas, picks);
      const anchor = handler({
        ...touchEvent(camera, canvas, 'mouse', 10),
        stopPropagation: () => {
          stops += 1;
        },
      });
      expect(anchor).toBeNull();
      expect(stops).toBe(0);
      expect(picks.length).toBe(0);
      const withoutPointerType = handler({
        ...touchEvent(camera, canvas, undefined, 10),
        stopPropagation: () => {
          stops += 1;
        },
      });
      expect(withoutPointerType).toBeNull();
      expect(stops).toBe(0);
      expect(picks.length).toBe(0);
    });

    it('rejects a touch tap with a 20 px delta beyond the touch drag limit', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const picks: CurveAnchor[] = [];
      let stops = 0;
      const handler = handlerFor(camera, canvas, picks);
      const anchor = handler({
        ...touchEvent(camera, canvas, 'touch', 20),
        stopPropagation: () => {
          stops += 1;
        },
      });
      expect(anchor).toBeNull();
      expect(stops).toBe(0);
      expect(picks.length).toBe(0);
    });

    it('picks a curve 15 px away through the injected touch radius and misses for a mouse pointer', () => {
      const camera = perspectiveCamera();
      const canvas = fakeCanvas();
      const css = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
      const line = taggedLine('curve-a', curveAPoints);
      const forgedHit: Intersection<Object3D> = {
        distance: 4.1,
        point: new Vector3(0, 0, -4.1),
        index: 0,
        object: line,
      };
      const touchPicks: CurveAnchor[] = [];
      const touchAnchor = handlerFor(camera, canvas, touchPicks)({
        intersections: [forgedHit],
        nativeEvent: { clientX: canvas.left + css.x, clientY: canvas.top + css.y + 15, pointerType: 'touch' },
        delta: 0,
        stopPropagation: (): void => undefined,
      });
      expect(touchAnchor).not.toBeNull();
      expect(touchAnchor?.curveId).toBe('curve-a');
      expect(touchPicks.length).toBe(1);
      const mousePicks: CurveAnchor[] = [];
      let stops = 0;
      const mouseAnchor = handlerFor(camera, canvas, mousePicks)({
        intersections: [forgedHit],
        nativeEvent: { clientX: canvas.left + css.x, clientY: canvas.top + css.y + 15, pointerType: 'mouse' },
        delta: 0,
        stopPropagation: () => {
          stops += 1;
        },
      });
      expect(mouseAnchor).toBeNull();
      expect(stops).toBe(0);
      expect(mousePicks.length).toBe(0);
    });
  });

  describe('touch pick radius', () => {
    function midpointHit(line: Line): Intersection<Object3D> {
      return {
        distance: 4.1,
        point: new Vector3(0, 0, -4.1),
        index: 0,
        object: line,
      };
    }

    it('picks a curve 15 px away with the 22 px touch radius and misses with the default 8 px radius', () => {
      const camera = perspectiveCamera();
      const line = taggedLine('curve-a', curveAPoints);
      const anchorScreen = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
      const pointer = { x: anchorScreen.x, y: anchorScreen.y + 15 };
      const intersections = [midpointHit(line)];
      let picks = 0;
      let stops = 0;
      const click = (radiusPx?: number): CurveAnchor | null =>
        handleCurveSceneClick(
          inputFor({ camera, pointer, intersections, ...(radiusPx === undefined ? {} : { radiusPx }) }),
          {
            dragDistancePx: 0,
            onPick: () => {
              picks += 1;
            },
            stopPropagation: () => {
              stops += 1;
            },
          },
        );
      const withTouchRadius = click(TOUCH_RADIUS_PX);
      expect(withTouchRadius).not.toBeNull();
      expect(withTouchRadius?.curveId).toBe('curve-a');
      expect(picks).toBe(1);
      expect(stops).toBe(1);
      const withDefaultRadius = click();
      expect(withDefaultRadius).toBeNull();
      expect(picks).toBe(1);
      expect(stops).toBe(1);
    });
  });

  describe('actual camera occlusion', () => {
    const smallViewport = { width: 200, height: 200 };

    const axisPoints: readonly MiningPoint3D[] = [
      [center[0] + 9, center[1], center[2]],
      [center[0] + 11, center[1], center[2]],
    ];
    const axisSnapshot = snapshotWith({ id: 'curve-a', points: axisPoints });

    function axisLine(): Line {
      const line = new Line(
        new BufferGeometry().setFromPoints([new Vector3(9, 0, 0), new Vector3(11, 0, 0)]),
        new LineBasicMaterial(),
      );
      line.userData.curveId = 'curve-a';
      return line;
    }

    function lookOriginAtZ10<T extends PerspectiveCamera | OrthographicCamera>(camera: T): T {
      camera.position.set(0, 0, 10);
      camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      return camera;
    }

    function intersectionsAt(camera: Camera, objects: Object3D[], point: Vector3) {
      for (const object of objects) object.updateMatrixWorld(true);
      const ndc = point.clone().project(camera);
      const pointer = {
        x: (ndc.x * 0.5 + 0.5) * smallViewport.width,
        y: (0.5 - ndc.y * 0.5) * smallViewport.height,
      };
      const raycaster = new Raycaster();
      raycaster.params.Line.threshold = 0.05;
      raycaster.layers.enableAll();
      raycaster.setFromCamera(new Vector2(ndc.x, ndc.y), camera);
      return { pointer, hits: raycaster.intersectObjects(objects, false) };
    }

    it('occludes a perspective anchor when the true camera ray hits an off-axis blocker', () => {
      const camera = lookOriginAtZ10(new PerspectiveCamera(120, 1, 0.1, 100));
      const line = axisLine();
      const blockerMaterial = new MeshBasicMaterial();
      blockerMaterial.side = DoubleSide;
      const blocker = new Mesh(new PlaneGeometry(4, 4), blockerMaterial);
      blocker.position.set(9, 0, 1);
      const target = new Vector3(10, 0, 0);
      const { pointer, hits } = intersectionsAt(camera, [line, blocker], target);
      const blockerHit = hits.find((hit) => hit.object === blocker);
      expect(blockerHit).toBeDefined();
      expect(blockerHit!.distance).toBeCloseTo(12.727922, 5);
      expect(blockerHit!.distance).toBeGreaterThan(
        raycasterOriginDepthOf(camera),
      );
      const result = resolveCurveSceneCandidate(
        inputFor({
          snapshot: axisSnapshot,
          camera, viewport: smallViewport, pointer, intersections: hits, occluders: [blocker],
        }),
      );
      expect(result).toBeNull();
    });

    it('accepts an orthographic anchor whose parallel camera ray misses the blocker', () => {
      const camera = lookOriginAtZ10(new OrthographicCamera(-20, 20, 20, -20, 0.1, 100));
      const line = axisLine();
      const blocker = new Mesh(new PlaneGeometry(0.5, 0.5), new MeshBasicMaterial());
      blocker.position.set(2, 0, 8);
      const target = new Vector3(10, 0, 0);
      const { pointer, hits } = intersectionsAt(camera, [line, blocker], target);
      expect(hits.some((hit) => hit.object === blocker)).toBe(false);
      const result = resolveCurveSceneCandidate(
        inputFor({
          snapshot: axisSnapshot,
          camera, viewport: smallViewport, pointer, intersections: hits, occluders: [blocker],
        }),
      );
      expect(result).not.toBeNull();
      expect(result?.curveId).toBe('curve-a');
    });

    it('does not occlude through a mesh whose material is invisible', () => {
      const camera = perspectiveCamera();
      const line = taggedLine('curve-a', curveAPoints);
      const pointer = projectedCss(toRenderPoint(mineAt(0, 0, -4.1)), camera);
      const intersections = raycastIntersections(camera, [line], pointer);
      const blocker = planeAt(-3);
      (blocker.material as MeshBasicMaterial).visible = false;
      expect(
        resolveCurveSceneCandidate(inputFor({ camera, pointer, intersections, occluders: [blocker] })),
      ).not.toBeNull();
    });
  });

  describe('createCurveScenePreviewHandler (hover preview)', () => {
    const longCurvePoints: readonly MiningPoint3D[] = [mineAt(0, 0, -4.1), mineAt(100, 0, -4.1)];

    function previewCanvas(): {
      left: number;
      top: number;
      width: number;
      height: number;
      getBoundingClientRect: () => { left: number; top: number; width: number; height: number };
    } {
      const rect = { left: 20, top: 10, width: viewport.width, height: viewport.height };
      return { ...rect, getBoundingClientRect: () => ({ ...rect }) };
    }

    function previewEvent(
      camera: PerspectiveCamera,
      canvas: ReturnType<typeof previewCanvas>,
      line: Line,
      offset: number,
    ): { intersections: Intersection<Object3D>[]; nativeEvent: { clientX: number; clientY: number } } {
      const pointer = projectedCss(toRenderPoint(mineAt(offset, 0, -4.1)), camera);
      return {
        intersections: raycastIntersections(camera, [line], pointer),
        nativeEvent: { clientX: canvas.left + pointer.x, clientY: canvas.top + pointer.y },
      };
    }

    it('previews distinct interior candidates along one long segment through real pointer moves', () => {
      const camera = new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 1000);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      const line = taggedLine('curve-a', longCurvePoints);
      const canvas = previewCanvas();
      const previews: (CurveAnchor | null)[] = [];
      const picks: CurveAnchor[] = [];
      const handler = createCurveScenePreviewHandler(
        {
          snapshot: snapshotWith({ id: 'curve-a', points: longCurvePoints }),
          selectedCurveId: 'curve-a',
          camera,
          center,
          canvas,
          getOccluders: (): Object3D[] => [],
          onPick: (anchor) => {
            picks.push(anchor);
          },
        },
        (anchor) => {
          previews.push(anchor);
        },
      );
      const first = handler(previewEvent(camera, canvas, line, 20));
      const second = handler(previewEvent(camera, canvas, line, 80));
      expect(first).not.toBeNull();
      expect(second).not.toBeNull();
      expect(previews.length).toBe(2);
      expect(previews[0]).toBe(first);
      expect(previews[1]).toBe(second);
      expect(first?.segmentIndex).toBe(0);
      expect(second?.segmentIndex).toBe(0);
      expect(first?.t).toBeGreaterThan(0);
      expect(first?.t).toBeLessThan(1);
      expect(first?.t).toBeCloseTo(0.2, 7);
      expect(second?.t).toBeCloseTo(0.8, 7);
      expect(first?.position[0]).toBeCloseTo(1020, 5);
      expect(second?.position[0]).toBeCloseTo(1080, 5);
      expect(first?.position[1]).toBeCloseTo(2004.1, 5);
      expect(second?.position[1]).toBeCloseTo(2004.1, 5);
      expect(first?.position[2]).toBeCloseTo(50, 5);
      expect(second?.position[2]).toBeCloseTo(50, 5);
      expect(first?.curveId).toBe('curve-a');
      expect(second?.curveId).toBe('curve-a');
      expect(first?.chainage).toBeCloseTo(20, 5);
      expect(second?.chainage).toBeCloseTo(80, 5);
      expect(picks.length).toBe(0);
    });

    it('clears to null outside the curve, beyond the pick radius and when picking is unavailable', () => {
      const camera = new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 1000);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      const line = taggedLine('curve-a', longCurvePoints);
      const canvas = previewCanvas();
      let picks = 0;
      const previews: (CurveAnchor | null)[] = [];
      const handler = createCurveScenePreviewHandler(
        {
          snapshot: snapshotWith({ id: 'curve-a', points: longCurvePoints }),
          selectedCurveId: 'curve-a',
          camera,
          center,
          canvas,
          getOccluders: (): Object3D[] => [],
          onPick: () => {
            picks += 1;
          },
        },
        (anchor) => {
          previews.push(anchor);
        },
      );
      expect(handler({ intersections: [], nativeEvent: { clientX: 1, clientY: 2 } })).toBeNull();
      const hitEvent = previewEvent(camera, canvas, line, 20);
      expect(handler({ ...hitEvent, nativeEvent: { clientX: canvas.left + 400, clientY: canvas.top + 500 } })).toBeNull();
      expect(previews.length).toBe(2);
      expect(previews[0]).toBeNull();
      expect(previews[1]).toBeNull();
      expect(picks).toBe(0);
      const nullPreviews: (CurveAnchor | null)[] = [];
      const previewOnlyHandler = createCurveScenePreviewHandler(
        {
          snapshot: snapshotWith({ id: 'curve-a', points: longCurvePoints }),
          selectedCurveId: 'curve-a',
          camera,
          center,
          canvas,
          getOccluders: (): Object3D[] => [],
          onPick: null,
        },
        (anchor) => {
          nullPreviews.push(anchor);
        },
      );
      expect(previewOnlyHandler(hitEvent)).toBeNull();
      expect(nullPreviews).toEqual([null]);
      expect(picks).toBe(0);
    });

    it('resolves and previews once per actual pointer move when the same native event is delivered twice', () => {
      const camera = new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 1000);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      const line = taggedLine('curve-a', longCurvePoints);
      const canvas = previewCanvas();
      const previews: (CurveAnchor | null)[] = [];
      let picks = 0;
      const handler = createCurveScenePreviewHandler(
        {
          snapshot: snapshotWith({ id: 'curve-a', points: longCurvePoints }),
          selectedCurveId: 'curve-a',
          camera,
          center,
          canvas,
          getOccluders: (): Object3D[] => [],
          onPick: () => {
            picks += 1;
          },
        },
        (anchor) => {
          previews.push(anchor);
        },
      );
      const event = previewEvent(camera, canvas, line, 20);
      const first = handler(event);
      const second = handler(event);
      expect(first).not.toBeNull();
      expect(second).toBe(first);
      expect(previews.length).toBe(1);
      expect(previews[0]).toBe(first);
      expect(picks).toBe(0);
    });

    it('clears to null for a foreign selected curve and a line missing from the snapshot', () => {
      const camera = new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 1000);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      const canvas = previewCanvas();
      const previews: (CurveAnchor | null)[] = [];
      const handler = createCurveScenePreviewHandler(
        {
          snapshot: snapshotWith({ id: 'curve-a', points: longCurvePoints }),
          selectedCurveId: 'curve-b',
          camera,
          center,
          canvas,
          getOccluders: (): Object3D[] => [],
          onPick: null,
        },
        (anchor) => {
          previews.push(anchor);
        },
      );
      const event = previewEvent(camera, canvas, taggedLine('curve-a', longCurvePoints), 20);
      expect(handler(event)).toBeNull();
      expect(previews).toEqual([null]);
      const unknownLine = taggedLine('curve-z', longCurvePoints);
      const unknownEvent = previewEvent(camera, canvas, unknownLine, 20);
      expect(handler(unknownEvent)).toBeNull();
      expect(previews.length).toBe(2);
      expect(previews[1]).toBeNull();
    });
  });
});

function raycasterOriginDepthOf(camera: Camera): number {
  return new Vector3().setFromMatrixPosition(camera.matrixWorld).z;
}
