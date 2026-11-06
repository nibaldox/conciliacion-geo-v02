import type { VerticesResponse } from '../../api/types';

type TopoHeightIndex = {
  vertices: VerticesResponse;
  xmin: number;
  ymin: number;
  cellX: number;
  cellY: number;
  columns: number;
  rows: number;
  buckets: Map<number, number[]>;
  largeFaces: number[];
};

export function buildTopoHeightIndex(vertices: VerticesResponse): TopoHeightIndex {
  let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
  for (let i = 0; i < vertices.x.length; i++) {
    xmin = Math.min(xmin, vertices.x[i]!);
    xmax = Math.max(xmax, vertices.x[i]!);
    ymin = Math.min(ymin, vertices.y[i]!);
    ymax = Math.max(ymax, vertices.y[i]!);
  }
  const faces = vertices.faces ?? [];
  const dimension = Math.max(1, Math.min(512, Math.ceil(Math.sqrt(faces.length / 4))));
  const width = xmax - xmin, height = ymax - ymin;
  const columns = width > 0 ? dimension : 1;
  const rows = height > 0 ? dimension : 1;
  const cellX = width > 0 ? width / columns : 1;
  const cellY = height > 0 ? height / rows : 1;
  const buckets = new Map<number, number[]>();
  const largeFaces: number[] = [];
  const index = { vertices, xmin, ymin, cellX, cellY, columns, rows, buckets, largeFaces };
  for (let i = 0; i < faces.length; i++) {
    const face = faces[i]!;
    const [a, b, c] = face;
    if (a === undefined || b === undefined || c === undefined ||
        a < 0 || b < 0 || c < 0 || a >= vertices.x.length || b >= vertices.x.length || c >= vertices.x.length) continue;
    const x0 = Math.max(0, Math.min(columns - 1, Math.floor((Math.min(vertices.x[a]!, vertices.x[b]!, vertices.x[c]!) - xmin) / cellX)));
    const x1 = Math.max(0, Math.min(columns - 1, Math.floor((Math.max(vertices.x[a]!, vertices.x[b]!, vertices.x[c]!) - xmin) / cellX)));
    const y0 = Math.max(0, Math.min(rows - 1, Math.floor((Math.min(vertices.y[a]!, vertices.y[b]!, vertices.y[c]!) - ymin) / cellY)));
    const y1 = Math.max(0, Math.min(rows - 1, Math.floor((Math.max(vertices.y[a]!, vertices.y[b]!, vertices.y[c]!) - ymin) / cellY)));
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > 256) { largeFaces.push(i); continue; }
    for (let row = y0; row <= y1; row++) for (let col = x0; col <= x1; col++) {
      const key = row * columns + col;
      const bucket = buckets.get(key);
      if (bucket) bucket.push(i); else buckets.set(key, [i]);
    }
  }
  return index;
}

export function heightAt(index: TopoHeightIndex, x: number, y: number): number {
  const { vertices, xmin, ymin, cellX, cellY, columns, rows, buckets, largeFaces } = index;
  const col = Math.floor((x - xmin) / cellX), row = Math.floor((y - ymin) / cellY);
  const candidates = col >= 0 && col <= columns && row >= 0 && row <= rows
    ? buckets.get(Math.min(row, rows - 1) * columns + Math.min(col, columns - 1)) ?? [] : [];
  let chosen = Infinity;
  let height: number | undefined;
  for (const list of [candidates, largeFaces]) for (const faceIndex of list) {
    if (faceIndex >= chosen) continue;
    const [a, b, c] = vertices.faces![faceIndex]!;
    const ax = vertices.x[a!]!, ay = vertices.y[a!]!;
    const bx = vertices.x[b!]! - ax, by = vertices.y[b!]! - ay;
    const cx = vertices.x[c!]! - ax, cy = vertices.y[c!]! - ay;
    const denominator = bx * cy - by * cx;
    if (denominator === 0) continue;
    const dx = x - ax, dy = y - ay;
    const u = (dx * cy - dy * cx) / denominator;
    const v = (bx * dy - by * dx) / denominator;
    if (u >= -1e-10 && v >= -1e-10 && u + v <= 1 + 1e-10) {
      chosen = faceIndex;
      height = vertices.z[a!]! * (1 - u - v) + vertices.z[b!]! * u + vertices.z[c!]! * v;
    }
  }
  if (height !== undefined) return height;
  let best = Infinity, nearest = 0;
  for (let i = 0; i < vertices.x.length; i++) {
    const distance = (vertices.x[i]! - x) ** 2 + (vertices.y[i]! - y) ** 2;
    if (distance < best) { best = distance; nearest = vertices.z[i]!; }
  }
  return nearest;
}
