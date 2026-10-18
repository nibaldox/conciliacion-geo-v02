import { describe, expect, it, vi } from 'vitest';
import {
  BufferGeometry,
  Camera,
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
import type { Intersection, Material, Object3D } from 'three';
import {
  computeCurveSearchBounds,
  getCurveSearchThreshold,
  resolveCurveSceneCandidate,
} from '../curveScenePicking';
import type { CurveScenePickingInput } from '../curveScenePicking';
import { pickCurveCandidate } from '../curvePicking';
import type { CurvePickCandidate } from '../curvePicking';
import { projectCurveAnchor } from '../../sections/curveAnchorGeometry';
import type { CurveGeometryPolyline, CurveGeometrySnapshot } from '../../sections/curveGeometryAdapter';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../../sections/curveSelectionTypes';

const context: CurveSelectionContext = { designMeshId: 'mesh-perf', geometryKey: 'geo-perf' };
const center: MiningPoint3D = [0, 0, 0];
const viewport = { width: 800, height: 600 };
const DEFAULT_RADIUS_PX = 8;
const OCCLUSION_ROUNDOFF = 1e-6;

type Viewport = { readonly width: number; readonly height: number };

function snapshotWith(polylines: readonly CurveGeometryPolyline[]): CurveGeometrySnapshot {
  return { context, curves: new Map(polylines.map((polyline) => [polyline.id, polyline] as const)) };
}

function toRenderPoint(point: MiningPoint3D, origin: MiningPoint3D): Vector3 {
  return new Vector3(point[0] - origin[0], point[2] - origin[2], -(point[1] - origin[1]));
}

function taggedLine(curveId: string, points: readonly MiningPoint3D[], origin: MiningPoint3D): Line {
  const line = new Line(
    new BufferGeometry().setFromPoints(points.map((point) => toRenderPoint(point, origin))),
    new LineBasicMaterial(),
  );
  line.userData.curveId = curveId;
  line.updateMatrixWorld(true);
  return line;
}

function projectedCss(
  position: MiningPoint3D,
  origin: MiningPoint3D,
  camera: Camera,
  size: Viewport,
): { x: number; y: number } {
  const ndc = toRenderPoint(position, origin).project(camera);
  return { x: (ndc.x * 0.5 + 0.5) * size.width, y: (0.5 - ndc.y * 0.5) * size.height };
}

function rayDirectionFor(camera: Camera, renderPoint: Vector3): Vector3 {
  const ndc = renderPoint.clone().project(camera);
  const raycaster = new Raycaster();
  raycaster.setFromCamera(new Vector2(ndc.x, ndc.y), camera);
  return raycaster.ray.direction.clone();
}

function legacyCurveIdOf(object: Object3D): string | null {
  const raw: unknown = object.userData.curveId;
  return typeof raw === 'string' ? raw : null;
}

function legacyIsVisibleForCamera(object: Object3D, camera: Camera): boolean {
  let node: Object3D | null = object;
  while (node !== null) {
    if (!node.visible) return false;
    node = node.parent;
  }
  return object.layers.test(camera.layers);
}

function legacyMaterialIsFullyOpaque(material: Material | Material[]): boolean {
  if (Array.isArray(material)) return false;
  if (!material.visible) return false;
  return !material.transparent && material.opacity >= 1;
}

function legacyIsOccluded(
  anchor: CurveAnchor,
  origin: MiningPoint3D,
  camera: Camera,
  occluders: readonly Object3D[],
): boolean {
  if (occluders.length === 0) return false;
  const target = new Vector3(
    anchor.position[0] - origin[0],
    anchor.position[2] - origin[2],
    -(anchor.position[1] - origin[1]),
  );
  if (!Number.isFinite(target.x) || !Number.isFinite(target.y) || !Number.isFinite(target.z)) return false;
  const ndc = target.clone().project(camera);
  if (!Number.isFinite(ndc.x) || !Number.isFinite(ndc.y)) return false;
  const raycaster = new Raycaster();
  raycaster.layers.mask = camera.layers.mask;
  raycaster.setFromCamera(new Vector2(ndc.x, ndc.y), camera);
  const targetDistance = raycaster.ray.origin.distanceTo(target);
  if (!Number.isFinite(targetDistance) || targetDistance <= 0) return false;
  raycaster.near = 0;
  raycaster.far = targetDistance;
  const clipBounds = camera as unknown as { near?: number; far?: number };
  const cameraNear = typeof clipBounds.near === 'number' && Number.isFinite(clipBounds.near) ? clipBounds.near : Number.NEGATIVE_INFINITY;
  const cameraFar = typeof clipBounds.far === 'number' && Number.isFinite(clipBounds.far) ? clipBounds.far : Number.POSITIVE_INFINITY;
  const roundoff = Math.abs(targetDistance) * OCCLUSION_ROUNDOFF;
  for (const hit of raycaster.intersectObjects([...occluders], false)) {
    if (!legacyIsVisibleForCamera(hit.object, camera)) continue;
    if (!(hit.object instanceof Mesh)) continue;
    if (!legacyMaterialIsFullyOpaque(hit.object.material)) continue;
    if (!Number.isFinite(hit.distance)) continue;
    const hitViewDepth = -hit.point.clone().applyMatrix4(camera.matrixWorldInverse).z;
    if (!Number.isFinite(hitViewDepth)) continue;
    if (hitViewDepth < cameraNear) continue;
    if (hitViewDepth > cameraFar) continue;
    if (hit.distance < targetDistance - roundoff) return true;
  }
  return false;
}

function legacyResolveCurveSceneCandidate(input: CurveScenePickingInput): CurveAnchor | null {
  const { snapshot, selectedCurveId, camera, center: origin, viewport: size, pointer } = input;
  const radiusPx = input.radiusPx ?? DEFAULT_RADIUS_PX;
  const candidates: CurvePickCandidate[] = [];
  for (const intersection of input.intersections) {
    const curveId = legacyCurveIdOf(intersection.object);
    if (curveId === null) continue;
    if (selectedCurveId !== null && curveId !== selectedCurveId) continue;
    if (!legacyIsVisibleForCamera(intersection.object, camera)) continue;
    const segmentIndex = intersection.index;
    if (segmentIndex === undefined) continue;
    const polyline = snapshot.curves.get(curveId);
    if (polyline === undefined) continue;
    const hit = intersection.point;
    const mining: MiningPoint3D = [hit.x + origin[0], -hit.z + origin[1], hit.y + origin[2]];
    const anchor = projectCurveAnchor({
      context: snapshot.context,
      curveId,
      points: polyline.points,
      segmentIndex,
      position: mining,
    });
    if (anchor === null) continue;
    if (legacyIsOccluded(anchor, origin, camera, input.occluders)) continue;
    candidates.push({ anchor, visible: true });
  }
  return pickCurveCandidate({
    candidates,
    context: snapshot.context,
    selectedCurveId,
    camera,
    center: origin,
    viewport: size,
    pointer,
    radiusPx,
  });
}

interface RaycastCounter {
  count: number;
}

function pushFakeHit(raycaster: Raycaster, mesh: Mesh, intersects: Intersection<Object3D>[]): void {
  const distance = raycaster.far * 0.5;
  intersects.push({ distance, point: raycaster.ray.at(distance, new Vector3()), object: mesh });
}

function occluderFor(isBlocked: (direction: Vector3) => boolean, counter: RaycastCounter): Mesh {
  const mesh = new Mesh(new PlaneGeometry(1, 1), new MeshBasicMaterial());
  mesh.raycast = (raycaster: Raycaster, intersects: Intersection<Object3D>[]): void => {
    counter.count += 1;
    if (!isBlocked(raycaster.ray.direction)) return;
    pushFakeHit(raycaster, mesh, intersects);
  };
  mesh.updateMatrixWorld(true);
  return mesh;
}

function blockingDirections(directions: readonly Vector3[]): (direction: Vector3) => boolean {
  return (direction: Vector3): boolean =>
    directions.some((blocked) => blocked.distanceToSquared(direction) < 1e-12);
}

function hashedBlocking(seed: number, period: number): (direction: Vector3) => boolean {
  return (direction: Vector3): boolean => {
    const hash = Math.abs(
      Math.round((direction.x + 1) * 1e6) * 31
      + Math.round((direction.y + 1) * 1e6) * 17
      + Math.round((direction.z + 1) * 1e6) * 7
      + seed * 13,
    );
    return hash % period === 0;
  };
}

function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function lookFromZ20(camera: PerspectiveCamera): PerspectiveCamera {
  camera.position.set(0, 0, 20);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

function sceneInput(overrides: Partial<CurveScenePickingInput>): CurveScenePickingInput {
  return {
    snapshot: snapshotWith([{ id: 'curve-a', points: [[0, 0, 0], [30, 0, 0]] }]),
    selectedCurveId: null,
    camera: lookFromZ20(new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 500)),
    center,
    viewport,
    pointer: { x: 400, y: 300 },
    intersections: [],
    occluders: [],
    radiusPx: 1000,
    ...overrides,
  };
}

function randomScene(rand: () => number): { input: CurveScenePickingInput; counter: RaycastCounter } {
  const origin: MiningPoint3D = [rand() * 8 - 4, rand() * 8 - 4, rand() * 8 - 4];
  const curveCount = 1 + Math.floor(rand() * 3);
  const polylines: CurveGeometryPolyline[] = [];
  const lines: Line[] = [];
  for (let index = 0; index < curveCount; index += 1) {
    const base: MiningPoint3D = [rand() * 40 - 20, rand() * 40 - 20, rand() * 40 - 20];
    const points: MiningPoint3D[] = [];
    for (let step = 0; step < 3; step += 1) {
      points.push([base[0] + rand() * 6 - 3, base[1] + rand() * 6 - 3, base[2] + rand() * 6 - 3]);
    }
    const id = `curve-${index}`;
    polylines.push({ id, points });
    lines.push(taggedLine(id, points, origin));
  }
  const camera = new PerspectiveCamera(40 + rand() * 40, 1.6, 0.1, 500);
  camera.position.set(rand() * 60 - 30, rand() * 60 - 30, 60 + rand() * 40);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  const size: Viewport = { width: 400 + Math.floor(rand() * 500), height: 300 + Math.floor(rand() * 400) };
  const intersections: Intersection<Object3D>[] = [];
  const hitCount = 1 + Math.floor(rand() * 6);
  let lastRender = new Vector3();
  for (let index = 0; index < hitCount; index += 1) {
    const curveIndex = Math.floor(rand() * curveCount);
    const polyline = polylines[curveIndex];
    const line = lines[curveIndex];
    const vertex = polyline.points[Math.floor(rand() * polyline.points.length)];
    const renderPoint = toRenderPoint(vertex, origin).add(
      new Vector3(rand() * 1.5 - 0.75, rand() * 1.5 - 0.75, rand() * 1.5 - 0.75),
    );
    intersections.push({
      distance: 1 + rand() * 40,
      point: renderPoint,
      index: Math.floor(rand() * 2),
      object: line,
    });
    lastRender = renderPoint;
  }
  const anchorNdc = lastRender.clone().project(camera);
  const anchorCss = {
    x: (anchorNdc.x * 0.5 + 0.5) * size.width,
    y: (0.5 - anchorNdc.y * 0.5) * size.height,
  };
  const pointer = {
    x: anchorCss.x + (rand() * 20 - 10),
    y: anchorCss.y + (rand() * 20 - 10),
  };
  const selectedCurveId = rand() < 0.4 ? null : polylines[Math.floor(rand() * polylines.length)].id;
  const counter: RaycastCounter = { count: 0 };
  const occluders: Object3D[] = [];
  if (rand() < 0.6) {
    occluders.push(
      occluderFor(hashedBlocking(Math.floor(rand() * 1000), 2 + Math.floor(rand() * 3)), counter),
    );
  }
  return {
    input: {
      snapshot: snapshotWith(polylines),
      selectedCurveId,
      camera,
      center: origin,
      viewport: size,
      pointer,
      intersections,
      occluders,
      radiusPx: rand() < 0.35 ? DEFAULT_RADIUS_PX + rand() * 60 : DEFAULT_RADIUS_PX,
    },
    counter,
  };
}

describe('lazy occlusion selection is identical to the legacy occlude-then-rank order', () => {
  it('agrees with the reference implementation on 300 randomized scenes', () => {
    const rand = makeRandom(20261018);
    let resolved = 0;
    let occludedTopRanked = 0;
    let budgetComparisons = 0;
    for (let index = 0; index < 300; index += 1) {
      const { input, counter } = randomScene(rand);
      const legacy = legacyResolveCurveSceneCandidate(input);
      const legacyChecks = counter.count;
      counter.count = 0;
      const actual = resolveCurveSceneCandidate(input);
      const lazyChecks = counter.count;
      expect(actual).toEqual(legacy);
      expect(lazyChecks).toBeLessThanOrEqual(legacyChecks);
      budgetComparisons += 1;
      if (actual !== null) resolved += 1;
      if (lazyChecks >= 2) occludedTopRanked += 1;
    }
    expect(budgetComparisons).toBe(300);
    expect(resolved).toBeGreaterThan(0);
    expect(occludedTopRanked).toBeGreaterThan(0);
  });

  it('falls through to the second-ranked candidate when the top-ranked one is occluded', () => {
    const camera = lookFromZ20(new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 500));
    const points: readonly MiningPoint3D[] = [[0, 0, 0], [30, 0, 0]];
    const snapshot = snapshotWith([{ id: 'curve-a', points }]);
    const line = taggedLine('curve-a', points, center);
    const nearRender = toRenderPoint([6, 0, 0], center);
    const farRender = toRenderPoint([24, 0, 0], center);
    const intersections: Intersection<Object3D>[] = [
      { distance: 20, point: nearRender, index: 0, object: line },
      { distance: 20, point: farRender, index: 0, object: line },
    ];
    const pointer = projectedCss([6, 0, 0], center, camera, viewport);
    const base = sceneInput({ snapshot, camera, pointer, intersections });

    expect(resolveCurveSceneCandidate(base)?.t).toBeCloseTo(0.2, 9);

    const counter: RaycastCounter = { count: 0 };
    const blocker = occluderFor(blockingDirections([rayDirectionFor(camera, nearRender)]), counter);
    const occludedBest = { ...base, occluders: [blocker] };
    const legacy = legacyResolveCurveSceneCandidate(occludedBest);
    counter.count = 0;
    const actual = resolveCurveSceneCandidate(occludedBest);
    expect(actual).toEqual(legacy);
    expect(actual?.t).toBeCloseTo(0.8, 9);
    expect(actual?.position[0]).toBeCloseTo(24, 9);
    expect(counter.count).toBe(2);

    const both: RaycastCounter = { count: 0 };
    const wide = occluderFor(
      blockingDirections([rayDirectionFor(camera, nearRender), rayDirectionFor(camera, farRender)]),
      both,
    );
    const fullyOccluded = { ...base, occluders: [wide] };
    expect(legacyResolveCurveSceneCandidate(fullyOccluded)).toBeNull();
    both.count = 0;
    expect(resolveCurveSceneCandidate(fullyOccluded)).toBeNull();
    expect(both.count).toBe(2);
  });

  it('breaks a full ranking tie by curve id and honours active-curve priority over nearer foreign candidates', () => {
    const camera = lookFromZ20(new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 500));
    const lowPoints: readonly MiningPoint3D[] = [[-3, 0, 0], [-1, 0, 0]];
    const highPoints: readonly MiningPoint3D[] = [[1, 0, 0], [3, 0, 0]];
    const farPoints: readonly MiningPoint3D[] = [[20, 0, 0], [40, 0, 0]];
    const snapshot = snapshotWith([
      { id: 'curve-a', points: lowPoints },
      { id: 'curve-b', points: highPoints },
      { id: 'curve-z', points: farPoints },
    ]);
    const lineA = taggedLine('curve-a', lowPoints, center);
    const lineB = taggedLine('curve-b', highPoints, center);
    const lineZ = taggedLine('curve-z', farPoints, center);
    const aRender = toRenderPoint([-2, 0, 0], center);
    const bRender = toRenderPoint([2, 0, 0], center);
    const zRender = toRenderPoint([20, 0, 0], center);
    const intersections: Intersection<Object3D>[] = [
      { distance: 20, point: aRender, index: 0, object: lineA },
      { distance: 20, point: bRender, index: 0, object: lineB },
      { distance: 20, point: zRender, index: 0, object: lineZ },
    ];
    const base = sceneInput({ snapshot, camera, pointer: { x: 400, y: 300 }, intersections });

    const tie = resolveCurveSceneCandidate(base);
    expect(tie).toEqual(legacyResolveCurveSceneCandidate(base));
    expect(tie?.curveId).toBe('curve-a');

    const aCounter: RaycastCounter = { count: 0 };
    const blockA = occluderFor(blockingDirections([rayDirectionFor(camera, aRender)]), aCounter);
    const tiedWithOccludedA = { ...base, occluders: [blockA] };
    const legacyTie = legacyResolveCurveSceneCandidate(tiedWithOccludedA);
    aCounter.count = 0;
    const tieWinner = resolveCurveSceneCandidate(tiedWithOccludedA);
    expect(tieWinner).toEqual(legacyTie);
    expect(tieWinner?.curveId).toBe('curve-b');
    expect(aCounter.count).toBe(2);

    const priority = { ...base, selectedCurveId: 'curve-z' };
    const priorityResult = resolveCurveSceneCandidate(priority);
    expect(priorityResult).toEqual(legacyResolveCurveSceneCandidate(priority));
    expect(priorityResult?.curveId).toBe('curve-z');

    const zCounter: RaycastCounter = { count: 0 };
    const blockZ = occluderFor(blockingDirections([rayDirectionFor(camera, zRender)]), zCounter);
    const blockedPriority = { ...priority, occluders: [blockZ] };
    expect(legacyResolveCurveSceneCandidate(blockedPriority)).toBeNull();
    zCounter.count = 0;
    expect(resolveCurveSceneCandidate(blockedPriority)).toBeNull();
    expect(zCounter.count).toBe(1);
  });
});

describe('occlusion raycast budget', () => {
  function manyCandidates(count: number) {
    const points: readonly MiningPoint3D[] = [[0, 0, 0], [40, 0, 0]];
    const snapshot = snapshotWith([{ id: 'curve-a', points }]);
    const camera = lookFromZ20(new PerspectiveCamera(60, viewport.width / viewport.height, 0.1, 500));
    const line = taggedLine('curve-a', points, center);
    const intersections: Intersection<Object3D>[] = [];
    for (let index = 0; index < count; index += 1) {
      const fraction = 0.05 + (0.9 * index) / count;
      intersections.push({
        distance: 20,
        point: toRenderPoint([40 * fraction, 0, 0], center),
        index: 0,
        object: line,
      });
    }
    const pointer = projectedCss([40 * 0.05, 0, 0], center, camera, viewport);
    return { snapshot, camera, pointer, intersections };
  }

  it('runs exactly one occlusion raycast for 40 candidates when the top-ranked one is visible', () => {
    const scene = manyCandidates(40);
    const farAwayBlocker = new Mesh(new PlaneGeometry(1, 1), new MeshBasicMaterial());
    farAwayBlocker.position.set(0, 500, 0);
    farAwayBlocker.updateMatrixWorld(true);
    const spy = vi.spyOn(Raycaster.prototype, 'intersectObjects');
    const result = resolveCurveSceneCandidate(
      sceneInput({ ...scene, occluders: [farAwayBlocker], radiusPx: 4000 }),
    );
    expect(result).not.toBeNull();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith([farAwayBlocker], false);
    spy.mockRestore();
    const input = sceneInput({ ...scene, occluders: [farAwayBlocker], radiusPx: 4000 });
    expect(result).toEqual(legacyResolveCurveSceneCandidate(input));
  });

  it('never raycasts more than the legacy order for the same candidate set', () => {
    const scene = manyCandidates(40);
    const counter: RaycastCounter = { count: 0 };
    const directions: Vector3[] = scene.intersections.map((intersection) =>
      rayDirectionFor(scene.camera, intersection.point),
    );
    const blocker = occluderFor(blockingDirections(directions.slice(0, 12)), counter);
    const input = sceneInput({ ...scene, occluders: [blocker], radiusPx: 4000 });
    const legacy = legacyResolveCurveSceneCandidate(input);
    const legacyChecks = counter.count;
    counter.count = 0;
    const actual = resolveCurveSceneCandidate(input);
    expect(actual).toEqual(legacy);
    expect(actual).not.toBeNull();
    expect(actual?.t).toBeCloseTo(0.05 + (0.9 * 12) / 40, 9);
    expect(counter.count).toBe(13);
    expect(legacyChecks).toBe(40);
    expect(counter.count).toBeLessThan(legacyChecks);
  });
});

describe('conservative curve search threshold from the design bounding sphere', () => {
  function sphereScene() {
    const points: readonly MiningPoint3D[] = [[-1, 0, 0], [1, 0, 0]];
    const snapshot = snapshotWith([{ id: 'curve-a', points }]);
    const bounds = computeCurveSearchBounds(snapshot, center);
    return { snapshot, bounds };
  }

  it('captures a curve point on the sphere far side that sits exactly radiusPx from the pick ray', () => {
    const { bounds } = sphereScene();
    expect(bounds).not.toBeNull();
    const radius = bounds === null ? 0 : bounds.radius;
    expect(radius).toBeCloseTo(1, 12);
    expect(bounds?.center.x).toBeCloseTo(0, 12);
    expect(bounds?.center.z).toBeCloseTo(0, 12);

    const camera = new PerspectiveCamera(60, 1.5, 0.1, 100);
    camera.position.set(0, 0, 10);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    const radiusPx = 8;
    const threshold = getCurveSearchThreshold(camera, 600, radiusPx, bounds);
    expect(threshold).not.toBeNull();
    const reach = camera.position.distanceTo(bounds === null ? new Vector3() : bounds.center) + radius;
    expect(reach).toBeCloseTo(11, 12);
    expect(threshold).toBeCloseTo((2 * reach * radiusPx) / (camera.projectionMatrix.elements[5] * 600), 12);

    const pxToWorld = (threshold ?? 0) / radiusPx;
    const farSide = new Vector3(0, pxToWorld * radiusPx, 10 - reach);
    const line = new Line(
      new BufferGeometry().setFromPoints([farSide, farSide.clone().add(new Vector3(0.05, 0, 0))]),
      new LineBasicMaterial(),
    );
    line.updateMatrixWorld(true);
    const raycaster = new Raycaster();
    raycaster.params.Line.threshold = threshold ?? 0;
    raycaster.setFromCamera(new Vector2(0, 0), camera);
    expect(raycaster.ray.distanceToPoint(farSide)).toBeCloseTo(threshold ?? 0, 9);
    expect(raycaster.intersectObject(line, false).length).toBe(1);
    expect(projectedCss([0, 0, 0], center, camera, viewport).x).toBeCloseTo(400, 9);
  });

  it('is strictly below the camera.far threshold when the geometry is closer, and keeps orthographic and invalid input unchanged', () => {
    const { snapshot, bounds } = sphereScene();
    const camera = new PerspectiveCamera(60, 1.5, 0.1, 100);
    camera.position.set(0, 0, 10);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    const farThreshold = getCurveSearchThreshold(camera, 600, 8, null);
    const nearThreshold = getCurveSearchThreshold(camera, 600, 8, bounds);
    expect(farThreshold).not.toBeNull();
    expect(nearThreshold).not.toBeNull();
    expect(nearThreshold).toBeGreaterThan(0);
    expect(nearThreshold).toBeLessThan(farThreshold ?? 0);
    expect(getCurveSearchThreshold(camera, 600, 8)).toBeCloseTo(farThreshold ?? 0, 12);

    const beyondFar = getCurveSearchThreshold(camera, 600, 8, { center: new Vector3(0, 0, -500), radius: 10 });
    expect(beyondFar).toBeCloseTo(farThreshold ?? 0, 12);
    const unusable = getCurveSearchThreshold(camera, 600, 8, { center: new Vector3(Number.NaN, 0, 0), radius: 1 });
    expect(unusable).toBeCloseTo(farThreshold ?? 0, 12);

    const ortho = new OrthographicCamera(-4, 4, 3, -3, 0.1, 100);
    ortho.updateProjectionMatrix();
    ortho.updateMatrixWorld(true);
    expect(getCurveSearchThreshold(ortho, 600, 8, bounds)).toBeCloseTo(
      getCurveSearchThreshold(ortho, 600, 8, null) ?? 0,
      12,
    );

    expect(getCurveSearchThreshold(new Camera(), 600, 8, bounds)).toBeNull();
    expect(getCurveSearchThreshold(camera, 0, 8, bounds)).toBeNull();
    expect(getCurveSearchThreshold(camera, 600, -1, bounds)).toBeNull();
    expect(computeCurveSearchBounds(snapshotWith([]), center)).toBeNull();
    expect(computeCurveSearchBounds(snapshot, [Number.NaN, 0, 0])).toBeNull();
    expect(computeCurveSearchBounds(snapshot, [0, 0, Number.POSITIVE_INFINITY])).toBeNull();
  });
});
