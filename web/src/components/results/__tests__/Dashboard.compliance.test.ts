import { describe, expect, it } from 'vitest';
import { benchScore, computeGlobalScore, computeParameterBreakdown, computeProfileComplianceCounts, computeProfileScores, computeProfileStatuses, computeSectorCompliance, designBenchOptions } from '../Dashboard';
import { createPlanProjection, projectPlanPoint } from '../CompliancePlanView';
import type { ComparisonResult } from '../../../api/types';

const row = (overrides: Partial<ComparisonResult> = {}): ComparisonResult => ({
  section: 'S-01', sector: 'Norte', bench_num: 1, type: 'MATCH', level: '100',
  height_design: 15, height_real: 15, height_dev: 0, height_status: 'CUMPLE',
  angle_design: 65, angle_real: 65, angle_dev: 0, angle_status: 'CUMPLE',
  berm_design: 8, berm_real: 8, berm_min: 6, berm_status: 'CUMPLE',
  delta_crest: 0, delta_toe: 0, ...overrides,
});

describe('Streamlit compliance parity', () => {
  it('uses the engine score rather than recalculating it from rounded values', () => {
    expect(benchScore(row({ bench_score: 70 }))).toBe(70);
  });
  it('uses engine weights 60/30/10 for older payloads without a score', () => {
    expect(benchScore(row({ height_status: 'NO CUMPLE' }))).toBe(70);
    expect(benchScore(row({ angle_status: 'NO CUMPLE' }))).toBe(90);
    expect(benchScore(row({ berm_status: 'NO CUMPLE' }))).toBe(40);
  });
  it('averages profiles equally and omits missing and extra banks from the score', () => {
    const rows = [row({ bench_score: 100 }), row({ bench_score: 80 }), row({ section: 'S-02', bench_score: 40 }), row({ type: 'MISSING', bench_score: 0 }), row({ section: 'S-03', type: 'EXTRA' })];
    expect(computeGlobalScore(rows)).toBe(65);
    expect([...computeProfileScores(rows)]).toEqual([['S-01', 90], ['S-02', 40]]);
  });
  it('uses worst backend tolerance tier for profile classification instead of the score threshold', () => {
    const rows = [
      row({ section: 'OK', bench_score: 0 }),
      row({ section: 'OUT', height_status: 'FUERA DE TOLERANCIA', bench_score: 100 }),
      row({ section: 'FAIL', berm_status: 'NO CUMPLE', bench_score: 100 }),
      row({ section: 'MISSING', type: 'MISSING', height_status: 'NO CONSTRUIDO', angle_status: '-', berm_status: 'FALTA BANCO' }),
      row({ section: 'UNKNOWN', height_status: '-', angle_status: '-', berm_status: '-' }),
      row({ section: 'EXTRA', type: 'EXTRA', bench_num: 999, height_status: 'NO CUMPLE' }),
    ];
    expect([...computeProfileStatuses(rows)]).toEqual([
      ['OK', 'CUMPLE'], ['OUT', 'FUERA'], ['FAIL', 'NO_CUMPLE'], ['MISSING', 'NO_CUMPLE'], ['UNKNOWN', 'UNKNOWN'], ['EXTRA', 'NO_CUMPLE'],
    ]);
    expect(computeProfileComplianceCounts(rows)).toEqual({ cumple: 1, fuera: 1, noCumple: 3 });
  });

  it('includes additional topography in All, but excludes it when a design bank is selected', () => {
    const rows = [
      row({ section: 'S-01', type: 'MATCH', bench_num: 4, bench_num_topo: 2 }),
      row({ section: 'S-01', type: 'EXTRA', bench_num: 999, bench_num_topo: 3, height_status: 'NO CUMPLE' }),
    ];
    expect(computeProfileStatuses(rows).get('S-01')).toBe('NO_CUMPLE');
    expect(computeProfileStatuses(rows.filter((item) => item.bench_num === 4)).get('S-01')).toBe('CUMPLE');
  });

  it('labels selector options with design toe elevations and excludes extras', () => {
    const options = designBenchOptions([
      row({ bench_num: 1, level: '2945' }),
      row({ section: 'S-02', bench_num: 1, level: '2940' }),
      row({ bench_num: 2, level: '2925', type: 'MISSING' }),
      row({ bench_num: 999, level: '2800', type: 'EXTRA' }),
    ]);
    expect(options).toEqual([
      { number: 1, minElevation: 2940, maxElevation: 2945 },
      { number: 2, minElevation: 2925, maxElevation: 2925 },
    ]);
  });
  it('counts evaluated parameters by sector rather than requiring a perfect bank', () => {
    const sector = computeSectorCompliance([row({ height_status: 'NO CUMPLE' }), row({ type: 'MISSING', height_status: 'NO CONSTRUIDO', angle_status: '-', berm_status: 'FALTA BANCO' })])[0]!;
    expect(sector.total).toBe(5);
    expect(sector.pct).toBe(40);
  });
  it('does not count an unavailable parameter as a failed measurement', () => {
    const rows = [row(), row({ type: 'MISSING', angle_status: '-' })];
    expect(computeParameterBreakdown(rows).find((parameter) => parameter.parameter === 'angle')?.noCumple).toBe(0);
  });
});

describe('plan projection', () => {
  it('keeps East right, North up and equal scales with large mining coordinates', () => {
    const projection = createPlanProjection({ x: [700000, 700100], y: [7200000, 7200100], z: [3900, 3900] })!;
    const origin = projectPlanPoint(700000, 7200000, projection);
    const east = projectPlanPoint(700010, 7200000, projection);
    const north = projectPlanPoint(700000, 7200010, projection);
    expect(east[0] - origin[0]).toBeCloseTo(origin[1] - north[1]);
    expect(east[0]).toBeGreaterThan(origin[0]);
    expect(north[1]).toBeLessThan(origin[1]);
  });
  it('rejects empty or invalid topography instead of inventing a map', () => {
    expect(createPlanProjection({ x: [], y: [], z: [] })).toBeNull();
    expect(createPlanProjection({ x: [NaN], y: [0], z: [0] })).toBeNull();
  });
  it('frames the evaluated area with a margin while preserving equal meter scales', () => {
    const vertices = { x: [700000, 701000], y: [7200000, 7201000], z: [3900, 3900] };
    const full = createPlanProjection(vertices)!;
    const focused = createPlanProjection(vertices, [[700400, 7200400], [700450, 7200480]])!;
    expect(focused.scale).toBeGreaterThan(full.scale * 5);
    expect(focused.xMin).toBeLessThan(700400);
    expect(focused.xMax).toBeGreaterThan(700450);
    expect(focused.yMin).toBeLessThan(7200400);
    expect(focused.yMax).toBeGreaterThan(7200480);
    const origin = projectPlanPoint(700400, 7200400, focused);
    const east = projectPlanPoint(700410, 7200400, focused);
    const north = projectPlanPoint(700400, 7200410, focused);
    expect(east[0] - origin[0]).toBeCloseTo(origin[1] - north[1]);
  });
  it('supports a single vertical profile without a degenerate horizontal range', () => {
    const focused = createPlanProjection({ x: [0, 1000], y: [0, 1000], z: [0, 0] }, [[400, 420], [400, 480]])!;
    expect(Number.isFinite(focused.scale)).toBe(true);
    expect(focused.xMax - focused.xMin).toBeGreaterThan(0);
  });
});
