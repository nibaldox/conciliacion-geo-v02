import type { HorizontalDeviationMeshResponse } from '../api/types';
import { readThemeColor } from './theme';

export const HORIZONTAL_DEVIATION_CATEGORIES = [
  'within_tolerance',
  'underbreak_minor',
  'underbreak_moderate',
  'underbreak_severe',
  'overbreak_minor',
  'overbreak_moderate',
  'overbreak_severe',
  'unmeasured',
] as const;

export type HorizontalDeviationLegendCategory = typeof HORIZONTAL_DEVIATION_CATEGORIES[number];

const COLOR_TOKENS: Record<HorizontalDeviationLegendCategory, readonly [string, string]> = {
  within_tolerance: ['--color-hdev-within', '#22c55e'],
  underbreak_minor: ['--color-hdev-underbreak-minor', '#facc15'],
  underbreak_moderate: ['--color-hdev-underbreak-moderate', '#f97316'],
  underbreak_severe: ['--color-hdev-underbreak-severe', '#ef4444'],
  overbreak_minor: ['--color-hdev-overbreak-minor', '#22d3ee'],
  overbreak_moderate: ['--color-hdev-overbreak-moderate', '#3b82f6'],
  overbreak_severe: ['--color-hdev-overbreak-severe', '#1e3a8a'],
  unmeasured: ['--color-hdev-unmeasured', '#94a3b8'],
};

export function getHorizontalDeviationColor(category: string): string {
  const normalized = category === 'unassessed' ? 'unmeasured' : category;
  const token = COLOR_TOKENS[normalized as HorizontalDeviationLegendCategory] ?? COLOR_TOKENS.unmeasured;
  return readThemeColor(token[0], token[1]);
}

export interface HorizontalDeviationTriangle {
  readonly vertices: readonly [readonly [number, number, number], readonly [number, number, number], readonly [number, number, number]];
  readonly category: string;
}

export function expandHorizontalDeviationFaces(
  map: HorizontalDeviationMeshResponse,
): HorizontalDeviationTriangle[] {
  const triangles: HorizontalDeviationTriangle[] = [];
  for (let faceIndex = 0; faceIndex < map.faces.length; faceIndex += 1) {
    const face = map.faces[faceIndex];
    const cellIndex = map.cell_index_by_face[faceIndex];
    const cell = cellIndex === undefined ? undefined : map.cells[cellIndex];
    if (!face || face.length !== 3 || !cell) continue;
    const vertices = face.map((vertexIndex) => {
      const x = map.vertices.x[vertexIndex];
      const y = map.vertices.y[vertexIndex];
      const z = map.vertices.z[vertexIndex];
      if (x === undefined || y === undefined || z === undefined) return null;
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
      return [x, y, z] as const;
    });
    const [first, second, third] = vertices;
    if (!first || !second || !third) continue;
    const category = cell.deviation_m !== null && Number.isFinite(cell.deviation_m)
      ? cell.category
      : 'unmeasured';
    triangles.push({
      vertices: [first, second, third],
      category,
    });
  }
  return triangles;
}
