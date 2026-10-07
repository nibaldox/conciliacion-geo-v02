import { describe, expect, it } from 'vitest';
import type { HorizontalDeviationMeshResponse } from '../../api/types';
import { expandHorizontalDeviationFaces, getHorizontalDeviationColor } from '../horizontalDeviation';
import { horizontalDeviationError, horizontalDeviationWarning } from '../horizontalDeviationMessages';

function makeMap(): HorizontalDeviationMeshResponse {
  return {
    vertices: { x: [0, 1, 0, 1], y: [0, 0, 1, 1], z: [10, 10, 11, 11] },
    faces: [[0, 1, 2], [0, 2, 3], [0, 1, 9], [1, 2, 3]],
    cell_index_by_face: [1, 0, 3, 2],
    cells: [
      { deviation_m: 3.5, category: 'overbreak_severe', status: 'measured', station_m: 1, elevation_m: 10 },
      { deviation_m: -1.4, category: 'underbreak_minor', status: 'measured', station_m: 2, elevation_m: 11 },
      { deviation_m: null, category: 'unmeasured', status: 'topo_missing', station_m: 3, elevation_m: 12 },
      { deviation_m: null, category: 'overbreak_severe', status: 'topo_ambiguous', station_m: 4, elevation_m: 13 },
    ],
    unit: 'm',
    method: 'horizontal_at_equal_elevation',
    direction: 'positive_overbreak_negative_underbreak',
    thresholds: { within: 1, moderate: 1.8, severe: 3 },
    resolution: { longitudinal_step: 2, vertical_step: 1 },
    summary: { measured: 2, total: 4, within_percent: 0, max_abs_deviation: 3.5 },
    warnings: [],
    sector: 'Norte',
    bench_num: null,
  };
}

describe('horizontal deviation presentation', () => {
  it('uses the face-to-cell index and renders null measurements as unmeasured', () => {
    const triangles = expandHorizontalDeviationFaces(makeMap());

    expect(triangles.map((triangle) => triangle.category)).toEqual([
      'underbreak_minor',
      'overbreak_severe',
      'unmeasured',
    ]);
    expect(triangles[0]?.vertices).toEqual([[0, 0, 10], [1, 0, 10], [0, 1, 11]]);
  });

  it('uses the gray fallback for unknown and unassessed categories', () => {
    expect(getHorizontalDeviationColor('unassessed')).toBe(getHorizontalDeviationColor('unmeasured'));
    expect(getHorizontalDeviationColor('future_category')).toBe(getHorizontalDeviationColor('unmeasured'));
  });

  it('maps API warning and limit errors to localized message keys', () => {
    expect(horizontalDeviationWarning('section_pair_gap_too_large:60m').key)
      .toBe('horizontalDeviation.warning.section_gap');
    expect(horizontalDeviationError({ response: { data: { detail: 'Requested grid exceeds the limit' } } })?.key)
      .toBe('horizontalDeviation.warning.resolution_limit');
    expect(horizontalDeviationError({ response: { data: { detail: 'insufficient_sections' } } })?.key)
      .toBe('horizontalDeviation.warning.two_sections');
  });
});
