import { useEffect, useState } from 'react';
import type { ProfileData, SectionResponse, VerticesResponse } from '../../api/types';

export interface Projection {
  width: number;
  height: number;
  xMin: number;
  yMin: number;
  xMax: number;
  yMax: number;
  scale: number;
  left: number;
  top: number;
}

export function createPlanProjection(vertices: VerticesResponse, focusPoints: readonly [number, number][] = [], labelled = false, viewport = { width: 1000, height: 600 }, paddingRatio = 0.12): Projection | null {
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (let i = 0; i < vertices.x.length; i++) {
    const x = vertices.x[i]!, y = vertices.y[i]!, z = vertices.z[i]!;
    if (![x, y, z].every(Number.isFinite)) continue;
    xMin = Math.min(xMin, x); xMax = Math.max(xMax, x);
    yMin = Math.min(yMin, y); yMax = Math.max(yMax, y);
  }
  if (!Number.isFinite(xMin) || xMax <= xMin || yMax <= yMin) return null;
  let focusXMin = Infinity, focusXMax = -Infinity, focusYMin = Infinity, focusYMax = -Infinity;
  let validFocusCount = 0;
  for (const [x, y] of focusPoints) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    validFocusCount++;
    focusXMin = Math.min(focusXMin, x); focusXMax = Math.max(focusXMax, x);
    focusYMin = Math.min(focusYMin, y); focusYMax = Math.max(focusYMax, y);
  }
  if (validFocusCount >= 2) {
    const focusWidth = focusXMax - focusXMin;
    const focusHeight = focusYMax - focusYMin;
    if (Number.isFinite(focusWidth) && Number.isFinite(focusHeight) && (focusWidth > 0 || focusHeight > 0)) {
      const padding = Math.max(10, Math.max(focusWidth, focusHeight) * paddingRatio);
      if (Number.isFinite(padding) && [focusXMin - padding, focusXMax + padding, focusYMin - padding, focusYMax + padding].every(Number.isFinite)) {
        xMin = focusXMin - padding;
        xMax = focusXMax + padding;
        yMin = focusYMin - padding;
        yMax = focusYMax + padding;
      }
    }
  }
  const width = viewport.width - (labelled ? 440 : 40);
  const height = viewport.height - (labelled ? 120 : 40);
  const xSpan = xMax - xMin, ySpan = yMax - yMin;
  if (!Number.isFinite(xSpan) || !Number.isFinite(ySpan) || xSpan <= 0 || ySpan <= 0 || width <= 0 || height <= 0) return null;
  const scale = Math.min(width / xSpan, height / ySpan);
  if (!Number.isFinite(scale) || scale <= 0) return null;
  return { ...viewport, xMin, yMin, xMax, yMax, scale, left: (viewport.width - xSpan * scale) / 2, top: (viewport.height - ySpan * scale) / 2 };

}

export function projectPlanPoint(x: number, y: number, projection: Projection): [number, number] {
  return [projection.left + (x - projection.xMin) * projection.scale, projection.top + (projection.yMax - y) * projection.scale];
}

export function surfaceFaceColor(vertices: Pick<VerticesResponse, 'x' | 'y' | 'z'>, a: number, b: number, c: number, zMin: number, zRange: number): string | null {
  const ux = vertices.x[b]! - vertices.x[a]!, uy = vertices.y[b]! - vertices.y[a]!, uz = vertices.z[b]! - vertices.z[a]!;
  const vx = vertices.x[c]! - vertices.x[a]!, vy = vertices.y[c]! - vertices.y[a]!, vz = vertices.z[c]! - vertices.z[a]!;
  const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  const length = Math.hypot(nx, ny, nz);
  if (!Number.isFinite(length) || length === 0) return null;
  const light = Math.abs((nx + 0.6 * ny + 0.8 * nz) / (length * Math.hypot(1, 0.6, 0.8)));
  const elevation = Math.min(1, Math.max(0, ((vertices.z[a]! + vertices.z[b]! + vertices.z[c]!) / 3 - zMin) / zRange));
  const relief = 0.58 + 0.62 * light;
  return `rgb(${Math.round((104 + (190 - 104) * elevation) * relief)}, ${Math.round((126 + (177 - 126) * elevation) * relief)}, ${Math.round((103 + (143 - 103) * elevation) * relief)})`;
}

interface RasterEntry { promise: Promise<string>; url?: string; evicted: boolean }
const rasterCache = new WeakMap<VerticesResponse, Map<string, RasterEntry>>();

export function createSurfaceRaster(vertices: VerticesResponse, projection: Projection): Promise<string> {
  let cache = rasterCache.get(vertices);
  if (!cache) { cache = new Map(); rasterCache.set(vertices, cache); }
  const key = [projection.width, projection.height, projection.xMin, projection.yMin, projection.xMax, projection.yMax, projection.scale, projection.left, projection.top].join('|');
  const existing = cache.get(key);
  if (existing) { cache.delete(key); cache.set(key, existing); return existing.promise; }
  const entry: RasterEntry = { promise: Promise.resolve(''), evicted: false };
  entry.promise = new Promise((resolve) => {
    // Yield to the initial render, so section lines are interactive first.
    setTimeout(() => {
      if (entry.evicted) { resolve(''); return; }
      const canvas = document.createElement('canvas');
      canvas.width = projection.width; canvas.height = projection.height;
      const context = canvas.getContext('2d');
      if (!context) { resolve(''); return; }
      const points = new Float64Array(vertices.x.length * 2);
      for (let i = 0; i < vertices.x.length; i++) {
        points[2 * i] = projection.left + (vertices.x[i]! - projection.xMin) * projection.scale;
        points[2 * i + 1] = projection.top + (projection.yMax - vertices.y[i]!) * projection.scale;
      }
      let zMin = Infinity, zMax = -Infinity;
      for (const z of vertices.z) { if (Number.isFinite(z)) { zMin = Math.min(zMin, z); zMax = Math.max(zMax, z); } }
      const zRange = Math.max(1, zMax - zMin);
      context.save(); context.beginPath();
      context.rect(projection.left, projection.top, (projection.xMax - projection.xMin) * projection.scale, (projection.yMax - projection.yMin) * projection.scale);
      context.clip();
      if (vertices.faces?.length) {
        for (const face of vertices.faces) {
          if (face.length !== 3) continue;
          const [a, b, c] = face as [number, number, number];
          if (a < 0 || b < 0 || c < 0 || a >= vertices.x.length || b >= vertices.x.length || c >= vertices.x.length) continue;
          const color = surfaceFaceColor(vertices, a, b, c, zMin, zRange);
          if (color === null) continue;
          context.fillStyle = color; context.beginPath();
          context.moveTo(points[2 * a]!, points[2 * a + 1]!); context.lineTo(points[2 * b]!, points[2 * b + 1]!); context.lineTo(points[2 * c]!, points[2 * c + 1]!);
          context.closePath(); context.fill();
        }
      } else {
        context.fillStyle = 'rgb(155, 155, 155)';
        for (let i = 0; i < vertices.x.length; i++) {
          if (!Number.isFinite(vertices.x[i]) || !Number.isFinite(vertices.y[i]) || !Number.isFinite(vertices.z[i])) continue;
          context.fillRect(points[2 * i]!, points[2 * i + 1]!, 2, 2);
        }
      }
      context.restore();
      canvas.toBlob((blob) => {
        if (!blob || entry.evicted) { resolve(''); return; }
        entry.url = URL.createObjectURL(blob); resolve(entry.url);
      }, 'image/png');
    }, 0);
  });
  cache.set(key, entry);
  if (cache.size > 4) {
    const oldestKey = cache.keys().next().value!;
    const oldest = cache.get(oldestKey)!; oldest.evicted = true;
    if (oldest.url) URL.revokeObjectURL(oldest.url);
    cache.delete(oldestKey);
  }
  return entry.promise;
}

export function useSurfaceRaster(vertices: VerticesResponse | undefined, projection: Projection | null): string {
  const [result, setResult] = useState<{ vertices: VerticesResponse; projection: Projection; url: string }>();
  useEffect(() => {
    if (!vertices || !projection) return;
    let active = true;
    void Promise.resolve(createSurfaceRaster(vertices, projection)).then((url) => { if (active) setResult({ vertices, projection, url }); });
    return () => { active = false; };
  }, [vertices, projection]);
  return result?.vertices === vertices && result?.projection === projection ? result.url : '';
}

export function sectionPlanPoints(section: SectionResponse, profile?: ProfileData): [number, number][] {
  if (!profile?.topo) return [];
  const angle = section.azimuth * Math.PI / 180;
  const points: [number, number][] = [];
  for (let i = 0; i < profile.topo.distances.length; i++) {
    const distance = profile.topo.distances[i]!;
    if (!Number.isFinite(distance) || !Number.isFinite(profile.topo.elevations[i])) continue;
    points.push([section.origin[0] + Math.sin(angle) * distance, section.origin[1] + Math.cos(angle) * distance]);
  }
  return points;
}

export function planBounds(points: readonly [number, number][]): [number, number, number, number] | null {
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (const [x, y] of points) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    xMin = Math.min(xMin, x); xMax = Math.max(xMax, x);
    yMin = Math.min(yMin, y); yMax = Math.max(yMax, y);
  }
  return Number.isFinite(xMin) ? [xMin, yMin, xMax, yMax] : null;
}

export function expandPlanBounds(bounds: readonly [number, number, number, number], paddingRatio: number): [number, number, number, number] {
  const [xMin, yMin, xMax, yMax] = bounds;
  const padding = Math.max(10, Math.max(xMax - xMin, yMax - yMin) * paddingRatio);
  return [xMin - padding, yMin - padding, xMax + padding, yMax + padding];
}
