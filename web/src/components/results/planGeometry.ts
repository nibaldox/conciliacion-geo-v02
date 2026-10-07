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
  const valid = focusPoints.filter((point) => point.every(Number.isFinite));
  if (valid.length >= 2) {
    xMin = Infinity; xMax = -Infinity; yMin = Infinity; yMax = -Infinity;
    for (const [x, y] of valid) {
      xMin = Math.min(xMin, x); xMax = Math.max(xMax, x);
      yMin = Math.min(yMin, y); yMax = Math.max(yMax, y);
    }
    const padding = Math.max(10, Math.max(xMax - xMin, yMax - yMin) * paddingRatio);
    xMin -= padding; xMax += padding; yMin -= padding; yMax += padding;
  }
  const width = viewport.width - (labelled ? 440 : 120);
  const scale = Math.min(width / (xMax - xMin), (viewport.height - 120) / (yMax - yMin));
  return { ...viewport, xMin, yMin, xMax, yMax, scale, left: (viewport.width - (xMax - xMin) * scale) / 2, top: (viewport.height - (yMax - yMin) * scale) / 2 };

}

export function projectPlanPoint(x: number, y: number, projection: Projection): [number, number] {
  return [projection.left + (x - projection.xMin) * projection.scale, projection.top + (projection.yMax - y) * projection.scale];
}

export function createSurfaceRaster(vertices: VerticesResponse, projection: Projection): string {
  const canvas = document.createElement('canvas');
  canvas.width = projection.width; canvas.height = projection.height;
  const context = canvas.getContext('2d');
  if (!context) return '';
  const points = vertices.x.map((x, i) => projectPlanPoint(x, vertices.y[i]!, projection));
  let zMin = Infinity, zMax = -Infinity;
  for (const z of vertices.z) {
    if (!Number.isFinite(z)) continue;
    zMin = Math.min(zMin, z); zMax = Math.max(zMax, z);
  }
  const zRange = Math.max(1, zMax - zMin);
  context.save();
  context.beginPath();
  context.rect(projection.left, projection.top, (projection.xMax - projection.xMin) * projection.scale, (projection.yMax - projection.yMin) * projection.scale);
  context.clip();
  if (vertices.faces?.length) {
    for (const face of vertices.faces) {
      if (face.length !== 3) continue;
      const [a, b, c] = face as [number, number, number];
      if (!points[a] || !points[b] || !points[c]) continue;
      const u = [vertices.x[b]! - vertices.x[a]!, vertices.y[b]! - vertices.y[a]!, vertices.z[b]! - vertices.z[a]!];
      const v = [vertices.x[c]! - vertices.x[a]!, vertices.y[c]! - vertices.y[a]!, vertices.z[c]! - vertices.z[a]!];
      const normal = [u[1]! * v[2]! - u[2]! * v[1]!, u[2]! * v[0]! - u[0]! * v[2]!, u[0]! * v[1]! - u[1]! * v[0]!];
      const length = Math.hypot(...normal);
      if (!Number.isFinite(length) || length === 0) continue;
      const light = Math.abs((normal[0]! + 0.6 * normal[1]! + 0.8 * normal[2]!) / (length * Math.hypot(1, 0.6, 0.8)));
      const elevation = Math.min(1, Math.max(0, ((vertices.z[a]! + vertices.z[b]! + vertices.z[c]!) / 3 - zMin) / zRange));
      const relief = 0.58 + 0.62 * light;
      const low = [104, 126, 103];
      const high = [190, 177, 143];
      const channels = low.map((value, index) => Math.round((value + (high[index]! - value) * elevation) * relief));
      context.fillStyle = `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
      context.beginPath();
      context.moveTo(...points[a]!); context.lineTo(...points[b]!); context.lineTo(...points[c]!);
      context.closePath(); context.fill();
    }
  } else {
    context.fillStyle = 'rgb(155, 155, 155)';
    for (let i = 0; i < points.length; i++) {
      if (![vertices.x[i], vertices.y[i], vertices.z[i]].every(Number.isFinite)) continue;
      context.fillRect(points[i]![0], points[i]![1], 2, 2);
    }
  }
  context.restore();
  return canvas.toDataURL('image/png');
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
