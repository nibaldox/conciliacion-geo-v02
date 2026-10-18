import { Mesh, OrthographicCamera, PerspectiveCamera, Raycaster, Vector2, Vector3 } from 'three';
import type { Camera, Intersection, Material, Matrix4, Object3D, Quaternion } from 'three';
import type { CurveGeometryPolyline, CurveGeometrySnapshot } from '../sections/curveGeometryAdapter';
import { projectCurveAnchor } from '../sections/curveAnchorGeometry';
import type { CurveAnchor, MiningPoint3D } from '../sections/curveSelectionTypes';
import { pickCurveCandidate } from './curvePicking';
import type { CurvePickCandidate } from './curvePicking';

export interface CurveScenePickingInput {
  readonly snapshot: CurveGeometrySnapshot;
  readonly selectedCurveId: string | null;
  readonly camera: Camera;
  readonly center: MiningPoint3D;
  readonly viewport: { readonly width: number; readonly height: number };
  readonly pointer: { readonly x: number; readonly y: number };
  readonly intersections: readonly Intersection<Object3D>[];
  readonly occluders: readonly Object3D[];
  readonly radiusPx?: number;
}

const DEFAULT_RADIUS_PX = 8;
const MAX_DRAG_DISTANCE_PX = 3;
const OCCLUSION_ROUNDOFF = 1e-6;

function curveIdOf(object: Object3D): string | null {
  const raw: unknown = object.userData.curveId;
  return typeof raw === 'string' ? raw : null;
}

function isVisibleForCamera(object: Object3D, camera: Camera): boolean {
  let node: Object3D | null = object;
  while (node !== null) {
    if (!node.visible) return false;
    node = node.parent;
  }
  return object.layers.test(camera.layers);
}

function materialIsFullyOpaque(material: Material | Material[]): boolean {
  if (Array.isArray(material)) return false;
  if (!material.visible) return false;
  return !material.transparent && material.opacity >= 1;
}

function isOccluded(
  anchor: CurveAnchor,
  center: MiningPoint3D,
  camera: Camera,
  occluders: readonly Object3D[],
): boolean {
  if (occluders.length === 0) return false;
  const target = new Vector3(
    anchor.position[0] - center[0],
    anchor.position[2] - center[2],
    -(anchor.position[1] - center[1]),
  );
  if (
    !Number.isFinite(target.x) || !Number.isFinite(target.y) || !Number.isFinite(target.z)
  ) {
    return false;
  }
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
    if (!isVisibleForCamera(hit.object, camera)) continue;
    if (!(hit.object instanceof Mesh)) continue;
    if (!materialIsFullyOpaque(hit.object.material)) continue;
    if (!Number.isFinite(hit.distance)) continue;
    const hitViewDepth = -hit.point.clone().applyMatrix4(camera.matrixWorldInverse).z;
    if (!Number.isFinite(hitViewDepth)) continue;
    if (hitViewDepth < cameraNear) continue;
    if (hitViewDepth > cameraFar) continue;
    if (hit.distance < targetDistance - roundoff) return true;
  }
  return false;
}

export interface CurveScenePointerEvent {
  readonly intersections: readonly Intersection<Object3D>[];
  readonly nativeEvent: { readonly clientX: number; readonly clientY: number };
  readonly delta: number;
  readonly stopPropagation: () => void;
}

export interface CurveSceneClickInput {
  readonly snapshot: CurveGeometrySnapshot;
  readonly selectedCurveId: string | null;
  readonly camera: Camera;
  readonly center: MiningPoint3D;
  readonly canvas: {
    readonly getBoundingClientRect: () => {
      readonly left: number;
      readonly top: number;
      readonly width: number;
      readonly height: number;
    };
  };
  readonly getOccluders: () => readonly Object3D[];
  readonly onPick: ((anchor: CurveAnchor) => void) | null;
  readonly radiusPx?: number;
}

export function resolveCurveSceneCandidate(input: CurveScenePickingInput): CurveAnchor | null {
  const { snapshot, selectedCurveId, camera, center, viewport, pointer } = input;
  const radiusPx = input.radiusPx ?? DEFAULT_RADIUS_PX;
  const candidates: CurvePickCandidate[] = [];
  for (const intersection of input.intersections) {
    const curveId = curveIdOf(intersection.object);
    if (curveId === null) continue;
    if (selectedCurveId !== null && curveId !== selectedCurveId) continue;
    if (!isVisibleForCamera(intersection.object, camera)) continue;
    const segmentIndex = intersection.index;
    if (segmentIndex === undefined) continue;
    const polyline: CurveGeometryPolyline | undefined = snapshot.curves.get(curveId);
    if (polyline === undefined) continue;
    const hit = intersection.point;
    const mining: MiningPoint3D = [hit.x + center[0], -hit.z + center[1], hit.y + center[2]];
    const anchor = projectCurveAnchor({
      context: snapshot.context,
      curveId,
      points: polyline.points,
      segmentIndex,
      position: mining,
    });
    if (anchor === null) continue;
    if (isOccluded(anchor, center, camera, input.occluders)) continue;
    candidates.push({ anchor, visible: true });
  }
  return pickCurveCandidate({
    candidates,
    context: snapshot.context,
    selectedCurveId,
    camera,
    center,
    viewport,
    pointer,
    radiusPx,
  });
}

export function handleCurveSceneClick(
  input: CurveScenePickingInput,
  options: {
    readonly dragDistancePx: number;
    readonly onPick: (anchor: CurveAnchor) => void;
    readonly stopPropagation: () => void;
  },
): CurveAnchor | null {
  const { dragDistancePx, stopPropagation, onPick } = options;
  if (!Number.isFinite(dragDistancePx) || dragDistancePx < 0 || dragDistancePx > MAX_DRAG_DISTANCE_PX) {
    return null;
  }
  const anchor = resolveCurveSceneCandidate(input);
  if (anchor === null) return null;
  stopPropagation();
  onPick(anchor);
  return anchor;
}

function buildCurveScenePickingInput(
  input: CurveSceneClickInput,
  event: Pick<CurveScenePointerEvent, 'intersections' | 'nativeEvent'>,
): CurveScenePickingInput {
  const rect = input.canvas.getBoundingClientRect();
  return {
    snapshot: input.snapshot,
    selectedCurveId: input.selectedCurveId,
    camera: input.camera,
    center: input.center,
    viewport: { width: rect.width, height: rect.height },
    pointer: { x: event.nativeEvent.clientX - rect.left, y: event.nativeEvent.clientY - rect.top },
    intersections: event.intersections,
    occluders: input.getOccluders(),
    radiusPx: input.radiusPx,
  };
}

export function createCurveSceneClickHandler(
  input: CurveSceneClickInput,
): (event: CurveScenePointerEvent) => CurveAnchor | null {
  return (event) => {
    if (input.onPick === null) return null;
    const anchor = handleCurveSceneClick(
      buildCurveScenePickingInput(input, event),
      {
        dragDistancePx: event.delta,
        onPick: input.onPick,
        stopPropagation: event.stopPropagation,
      },
    );
    return anchor;
  };
}

export function createCurveScenePreviewHandler(
  input: CurveSceneClickInput,
  onPreview: (anchor: CurveAnchor | null) => void,
): (event: Pick<CurveScenePointerEvent, 'intersections' | 'nativeEvent'>) => CurveAnchor | null {
  let lastNativeEvent: CurveScenePointerEvent['nativeEvent'] | null = null;
  let lastCandidate: CurveAnchor | null = null;
  return (event) => {
    if (event.nativeEvent === lastNativeEvent) return lastCandidate;
    lastNativeEvent = event.nativeEvent;
    if (input.onPick === null) {
      lastCandidate = null;
      onPreview(null);
      return null;
    }
    const anchor = resolveCurveSceneCandidate(buildCurveScenePickingInput(input, event));
    lastCandidate = anchor;
    onPreview(anchor);
    return anchor;
  };
}

export interface CurvePreviewViewSnapshot {
  readonly position: Vector3;
  readonly quaternion: Quaternion;
  readonly projection: Matrix4;
  readonly viewport: { readonly width: number; readonly height: number };
}

export function hasCurvePreviewViewChanged(
  snapshot: CurvePreviewViewSnapshot,
  camera: Camera,
  viewport: { readonly width: number; readonly height: number },
): boolean {
  return (
    snapshot.position.distanceToSquared(camera.position) > 1e-12
    || 1 - Math.abs(snapshot.quaternion.dot(camera.quaternion)) > 1e-12
    || !snapshot.projection.equals(camera.projectionMatrix)
    || snapshot.viewport.width !== viewport.width
    || snapshot.viewport.height !== viewport.height
  );
}

export function getCurveSearchThreshold(
  camera: Camera,
  viewportHeight: number,
  radiusPx: number = DEFAULT_RADIUS_PX,
): number | null {
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) return null;
  if (!Number.isFinite(radiusPx) || radiusPx < 0) return null;
  if (!(camera instanceof PerspectiveCamera) && !(camera instanceof OrthographicCamera)) return null;
  const projectionY = camera.projectionMatrix.elements[5];
  if (!Number.isFinite(projectionY) || projectionY <= 0) return null;
  if (camera instanceof PerspectiveCamera) {
    if (!Number.isFinite(camera.far) || camera.far <= 0) return null;
    const threshold = (2 * camera.far * radiusPx) / (projectionY * viewportHeight);
    return Number.isFinite(threshold) && threshold >= 0 ? threshold : null;
  }
  const orthoThreshold = (2 * radiusPx) / (projectionY * viewportHeight);
  return Number.isFinite(orthoThreshold) && orthoThreshold >= 0 ? orthoThreshold : null;
}
