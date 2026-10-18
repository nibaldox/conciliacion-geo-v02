import type { Camera } from 'three';
import { Vector3 } from 'three';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../sections/curveSelectionTypes';

export interface CurvePickCandidate {
  readonly anchor: CurveAnchor;
  readonly visible: boolean;
}

export interface CurvePickingInput {
  readonly candidates: readonly CurvePickCandidate[];
  readonly context: CurveSelectionContext;
  readonly selectedCurveId: string | null;
  readonly camera: Camera;
  readonly center: MiningPoint3D;
  readonly viewport: { readonly width: number; readonly height: number };
  readonly pointer: { readonly x: number; readonly y: number };
  readonly radiusPx?: number;
}

const DEFAULT_RADIUS_PX = 8;

interface EligibleCandidate {
  readonly anchor: CurveAnchor;
  readonly distancePx: number;
  readonly cameraDepth: number;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function sameContextByValue(a: CurveSelectionContext, b: CurveSelectionContext): boolean {
  return a.designMeshId === b.designMeshId && a.geometryKey === b.geometryKey;
}

function anchorIsUsable(anchor: CurveAnchor, context: CurveSelectionContext): boolean {
  if (!sameContextByValue(anchor.context, context)) return false;
  const [east, north, elevation] = anchor.position;
  if (!isFiniteNumber(east) || !isFiniteNumber(north) || !isFiniteNumber(elevation)) return false;
  if (!Number.isInteger(anchor.segmentIndex) || anchor.segmentIndex < 0) return false;
  if (!isFiniteNumber(anchor.t) || anchor.t < 0 || anchor.t > 1) return false;
  if (!isFiniteNumber(anchor.chainage) || anchor.chainage < 0) return false;
  return true;
}

function comesBefore(a: EligibleCandidate, b: EligibleCandidate): boolean {
  if (a.distancePx !== b.distancePx) return a.distancePx < b.distancePx;
  if (a.cameraDepth !== b.cameraDepth) return a.cameraDepth < b.cameraDepth;
  if (a.anchor.curveId !== b.anchor.curveId) return a.anchor.curveId < b.anchor.curveId;
  if (a.anchor.segmentIndex !== b.anchor.segmentIndex) return a.anchor.segmentIndex < b.anchor.segmentIndex;
  return a.anchor.t < b.anchor.t;
}

function toEligibleCandidate(
  anchor: CurveAnchor,
  camera: Camera,
  nearPlane: number,
  farPlane: number,
  center: MiningPoint3D,
  viewport: { readonly width: number; readonly height: number },
  pointer: { readonly x: number; readonly y: number },
  radiusPx: number,
): EligibleCandidate | null {
  const renderPoint = new Vector3(
    anchor.position[0] - center[0],
    anchor.position[2] - center[2],
    -(anchor.position[1] - center[1]),
  );
  const viewPoint = renderPoint.clone().applyMatrix4(camera.matrixWorldInverse);
  const cameraDepth = -viewPoint.z;
  if (!isFiniteNumber(cameraDepth) || cameraDepth <= 0) return null;
  if (cameraDepth < nearPlane || cameraDepth > farPlane) return null;
  const ndc = renderPoint.clone().project(camera);
  if (!isFiniteNumber(ndc.x) || !isFiniteNumber(ndc.y) || !isFiniteNumber(ndc.z)) return null;
  const cssX = (ndc.x * 0.5 + 0.5) * viewport.width;
  const cssY = (0.5 - ndc.y * 0.5) * viewport.height;
  const distancePx = Math.hypot(cssX - pointer.x, cssY - pointer.y);
  if (!isFiniteNumber(distancePx) || distancePx > radiusPx) return null;
  return { anchor, distancePx, cameraDepth };
}

export function pickCurveCandidate(input: CurvePickingInput): CurveAnchor | null {
  const { candidates, context, selectedCurveId, camera, center, viewport, pointer } = input;
  const radiusPx = input.radiusPx ?? DEFAULT_RADIUS_PX;
  if (!isFiniteNumber(viewport.width) || viewport.width <= 0) return null;
  if (!isFiniteNumber(viewport.height) || viewport.height <= 0) return null;
  if (!isFiniteNumber(pointer.x) || !isFiniteNumber(pointer.y)) return null;
  if (!isFiniteNumber(center[0]) || !isFiniteNumber(center[1]) || !isFiniteNumber(center[2])) return null;
  if (!isFiniteNumber(radiusPx) || radiusPx < 0) return null;
  if (!('near' in camera) || !('far' in camera)) return null;
  const nearPlane = camera.near;
  const farPlane = camera.far;
  if (!isFiniteNumber(nearPlane) || !isFiniteNumber(farPlane)) return null;

  const eligible: EligibleCandidate[] = [];
  for (const candidate of candidates) {
    if (!candidate.visible) continue;
    if (!anchorIsUsable(candidate.anchor, context)) continue;
    const projected = toEligibleCandidate(
      candidate.anchor,
      camera,
      nearPlane,
      farPlane,
      center,
      viewport,
      pointer,
      radiusPx,
    );
    if (projected !== null) eligible.push(projected);
  }

  const ranked = selectedCurveId === null
    ? eligible
    : eligible.filter((entry) => entry.anchor.curveId === selectedCurveId);

  let best: EligibleCandidate | null = null;
  for (const entry of ranked) {
    if (best === null || comesBefore(entry, best)) best = entry;
  }
  return best === null ? null : best.anchor;
}
