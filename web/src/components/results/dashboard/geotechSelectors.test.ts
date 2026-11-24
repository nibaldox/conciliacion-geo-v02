import { describe, expect, it } from 'vitest';
import type { ComparisonResult } from '../../../api/types';
import {
  computeDirectionalStats,
  computeLevelCompliance,
  computeMedian,
  computePriorityReviewList,
} from './geotechSelectors';

const makeRow = (overrides: Partial<ComparisonResult> = {}): ComparisonResult =>
  ({
    sector: 'North',
    section: 'S1',
    bench_num: 1,
    type: 'MATCH',
    level: '2840',
    level_nominal: null,
    height_design: 15,
    height_real: 15,
    height_dev: 0,
    height_status: 'CUMPLE',
    angle_design: 70,
    angle_real: 70,
    angle_dev: 0,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 8,
    berm_min: 7,
    berm_status: 'CUMPLE',
    effective_berm: 7.5,
    effective_berm_status: 'CUMPLE',
    delta_crest: 0,
    delta_toe: 0,
    bench_score: 100,
    ...overrides,
  }) as ComparisonResult;

describe('computeMedian', () => {
  it('returns null for empty or non-finite arrays', () => {
    expect(computeMedian([])).toBeNull();
    expect(computeMedian([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])).toBeNull();
  });

  it('computes odd and even medians without mutating input', () => {
    const odd = [9, 1, 5];
    expect(computeMedian(odd)).toBe(5);
    expect(odd).toEqual([9, 1, 5]);

    expect(computeMedian([10, 2, 4, 8])).toBe(6);
    expect(computeMedian([-10, -2, -6])).toBe(-6);
    expect(computeMedian([Number.NaN, 3, Number.POSITIVE_INFINITY, 7])).toBe(5);
  });
});

describe('computeDirectionalStats', () => {
  const defaultTolerances = { heightPos: 2, heightNeg: 2, bermMin: 7 };

  it('returns zeroed counts and null stats for empty input', () => {
    const stats = computeDirectionalStats([], defaultTolerances);
    expect(stats).toEqual({
      berm: {
        compared: 0,
        passCount: 0,
        passPct: 0,
        validDesignCount: 0,
        validDesignPassPct: null,
        meanDeficitVsDesign: null,
        belowMinCount: 0,
        below5mCount: 0,
        effectiveEvaluated: 0,
        effectivePassCount: 0,
        effectivePassPct: null,
      },
      crest: { count: 0, mean: null, median: null, gt1mCount: 0, gt3mCount: 0 },
      angle: { count: 0, median: null, flatterCount: 0, steeperCount: 0 },
      height: { count: 0, median: null, overTolCount: 0, underTolCount: 0 },
      toe: { count: 0, median: null },
    });
  });

  it('excludes MISSING and EXTRA rows from all directional metrics', () => {
    const rows = [
      makeRow({ delta_crest: 0.5, angle_dev: -1, height_dev: 0.5, delta_toe: 0.2 }),
      makeRow({
        type: 'MISSING',
        berm_status: 'FALTA BANCO',
        effective_berm_status: 'NO CUMPLE',
        delta_crest: 9,
        angle_dev: 20,
        height_dev: 10,
        delta_toe: 8,
      }),
      makeRow({
        type: 'EXTRA',
        berm_status: 'BANCO ADICIONAL',
        effective_berm_status: 'NO CUMPLE',
        delta_crest: 8,
        angle_dev: -20,
        height_dev: -10,
        delta_toe: -8,
      }),
    ];
    const stats = computeDirectionalStats(rows, defaultTolerances);
    expect(stats.berm.compared).toBe(1);
    expect(stats.berm.passCount).toBe(1);
    expect(stats.berm.passPct).toBe(100);
    expect(stats.berm.effectiveEvaluated).toBe(1);
    expect(stats.berm.effectivePassCount).toBe(1);
    expect(stats.crest).toEqual({ count: 1, mean: 0.5, median: 0.5, gt1mCount: 0, gt3mCount: 0 });
    expect(stats.angle).toEqual({ count: 1, median: -1, flatterCount: 1, steeperCount: 0 });
    expect(stats.height).toEqual({ count: 1, median: 0.5, overTolCount: 0, underTolCount: 0 });
    expect(stats.toe).toEqual({ count: 1, median: 0.2 });
  });

  it('distinguishes validDesign vs truncated design berms and evaluates effective berm statuses', () => {
    const rows = [
      makeRow({
        berm_design: 9,
        berm_real: 7.5,
        berm_min: 7,
        berm_status: 'CUMPLE',
        effective_berm_status: 'cumple',
      }),
      makeRow({
        berm_design: 8,
        berm_real: 4.5,
        berm_min: null,
        berm_status: 'NO CUMPLE',
        effective_berm_status: 'NO CUMPLE',
      }),
      makeRow({
        berm_design: 8,
        berm_real: 6,
        berm_min: 7,
        berm_status: 'NO CUMPLE',
        effective_berm_status: '-',
      }),
      makeRow({
        berm_design: 3,
        berm_real: 2,
        berm_min: 7,
        berm_status: 'NO CUMPLE',
        effective_berm_status: null,
      }),
      makeRow({
        berm_design: 8,
        berm_real: null,
        berm_min: 7,
        berm_status: '-',
        effective_berm_status: '',
      }),
    ];

    const stats = computeDirectionalStats(rows, defaultTolerances);
    expect(stats.berm.compared).toBe(4);
    expect(stats.berm.passCount).toBe(1);
    expect(stats.berm.passPct).toBe(25);
    expect(stats.berm.validDesignCount).toBe(4);
    expect(stats.berm.validDesignPassPct).toBeCloseTo(100 / 3, 6);
    expect(stats.berm.meanDeficitVsDesign).toBeCloseTo((-1.5 + -3.5 + -2) / 3, 6);
    expect(stats.berm.belowMinCount).toBe(2);
    expect(stats.berm.below5mCount).toBe(1);
    expect(stats.berm.effectiveEvaluated).toBe(2);
    expect(stats.berm.effectivePassCount).toBe(1);
    expect(stats.berm.effectivePassPct).toBe(50);
  });

  it('tracks directional sign conventions for crest, angle, height, and toe', () => {
    const rows = [
      makeRow({ delta_crest: -0.5, angle_dev: -4, height_dev: -2.5, delta_toe: -1.5 }),
      makeRow({ delta_crest: 1, angle_dev: 0, height_dev: -2, delta_toe: 0.5 }),
      makeRow({ delta_crest: 2.5, angle_dev: 3, height_dev: 2, delta_toe: 2.5 }),
      makeRow({ delta_crest: 4, angle_dev: 6, height_dev: 3.5, delta_toe: null }),
      makeRow({ delta_crest: null, angle_dev: null, height_dev: Number.NaN, delta_toe: Number.POSITIVE_INFINITY }),
    ];

    const stats = computeDirectionalStats(rows, { heightPos: 2, heightNeg: -2, bermMin: 7 });
    expect(stats.crest.count).toBe(4);
    expect(stats.crest.mean).toBeCloseTo(1.75, 6);
    expect(stats.crest.median).toBeCloseTo(1.75, 6);
    expect(stats.crest.gt1mCount).toBe(2);
    expect(stats.crest.gt3mCount).toBe(1);

    expect(stats.angle).toEqual({ count: 4, median: 1.5, flatterCount: 1, steeperCount: 2 });
    expect(stats.height).toEqual({ count: 4, median: 0, overTolCount: 1, underTolCount: 1 });
    expect(stats.toe).toEqual({ count: 3, median: 0.5 });
  });
});

describe('computeLevelCompliance', () => {
  it('returns empty array for empty input', () => {
    expect(computeLevelCompliance([])).toEqual([]);
  });

  it('groups by normalized nominal level, sorts descending numerically with non-numeric last, and flags small samples', () => {
    const rows: ComparisonResult[] = [
      ...Array.from({ length: 5 }, (_, idx) =>
        makeRow({
          bench_num: idx + 1,
          level: '2841',
          level_nominal: ' 2840 ',
          bench_score: idx < 3 ? 100 : 40,
          height_status: 'CUMPLE',
          angle_status: idx < 4 ? 'CUMPLE' : 'NO CUMPLE',
          berm_status: idx < 3 ? 'CUMPLE' : 'NO CUMPLE',
        }),
      ),
      makeRow({ type: 'MISSING', level: '2840', level_nominal: '2840', bench_score: 0 }),
      makeRow({ type: 'EXTRA', level: '2840', level_nominal: '2840', bench_score: 0 }),
      makeRow({
        level: '2855',
        level_nominal: null,
        bench_score: null,
        height_status: 'CUMPLE',
        angle_status: 'NO CUMPLE',
        berm_status: 'CUMPLE',
      }),
      makeRow({
        level: 'N/A',
        level_nominal: null,
        height_status: '-',
        angle_status: '-',
        berm_status: '-',
        bench_score: null,
      }),
      makeRow({
        level: '',
        level_nominal: '  ',
        type: 'MISSING',
      }),
    ];

    const levels = computeLevelCompliance(rows);
    expect(levels.map((l) => l.level)).toEqual(['2855', '2840', 'N/A', '']);

    expect(levels[0]).toEqual({
      level: '2855',
      compared: 1,
      notBuilt: 0,
      extra: 0,
      meanScore: 90,
      heightPassPct: 100,
      anglePassPct: 0,
      bermPassPct: 100,
      smallSample: true,
    });

    expect(levels[1]).toEqual({
      level: '2840',
      compared: 5,
      notBuilt: 1,
      extra: 1,
      meanScore: 76,
      heightPassPct: 100,
      anglePassPct: 80,
      bermPassPct: 60,
      smallSample: false,
    });

    expect(levels[2]).toEqual({
      level: 'N/A',
      compared: 1,
      notBuilt: 0,
      extra: 0,
      meanScore: null,
      heightPassPct: null,
      anglePassPct: null,
      bermPassPct: null,
      smallSample: true,
    });

    expect(levels[3]).toEqual({
      level: '',
      compared: 0,
      notBuilt: 1,
      extra: 0,
      meanScore: null,
      heightPassPct: null,
      anglePassPct: null,
      bermPassPct: null,
      smallSample: true,
    });
  });
});

describe('computePriorityReviewList', () => {
  it('skips compliant MATCH rows and all non-MATCH rows', () => {
    const rows = [
      makeRow({ section: 'S1', bench_num: 1, bench_score: 100, delta_crest: 2.5 }),
      makeRow({ section: 'S1', bench_num: 2, type: 'MISSING', bench_score: 0, berm_real: 0 }),
      makeRow({ section: 'S1', bench_num: 3, type: 'EXTRA', bench_score: 0, berm_real: 0 }),
    ];
    expect(computePriorityReviewList(rows, [{ id: 'id-1', name: 'S1' }], 7)).toEqual([]);
  });

  it('prioritizes real geotechnical defects above truncated-berm-only rows', () => {
    const rows = [
      makeRow({
        section: 'Truncated',
        bench_num: 1,
        berm_design: 2.5,
        berm_real: 2.2,
        berm_min: 7,
        berm_status: 'NO CUMPLE',
        effective_berm: 2.0,
        effective_berm_status: 'NO CUMPLE',
        bench_score: 40,
      }),
      makeRow({
        section: 'RealEffFail',
        bench_num: 1,
        berm_design: 9,
        berm_real: 7.5,
        berm_min: 7,
        berm_status: 'CUMPLE',
        effective_berm: 4.5,
        effective_berm_status: 'NO CUMPLE',
        bench_score: 100,
      }),
      makeRow({
        section: 'RealBermSevere',
        bench_num: 2,
        berm_design: 8.5,
        berm_real: 3.0,
        berm_min: 7,
        berm_status: 'NO CUMPLE',
        effective_berm: 2.5,
        effective_berm_status: 'NO CUMPLE',
        bench_score: 40,
      }),
      makeRow({
        section: 'CrestLoss',
        bench_num: 3,
        berm_design: 8,
        berm_real: 8,
        berm_min: 7,
        berm_status: 'CUMPLE',
        effective_berm: 7.5,
        effective_berm_status: 'CUMPLE',
        delta_crest: 4.5,
        bench_score: 100,
      }),
      makeRow({
        section: 'LowScoreOnly',
        bench_num: 4,
        berm_design: 8,
        berm_real: 8,
        berm_min: 7,
        berm_status: 'CUMPLE',
        effective_berm: 7.5,
        effective_berm_status: 'CUMPLE',
        height_status: 'NO CUMPLE',
        angle_status: 'NO CUMPLE',
        bench_score: 60,
      }),
    ];

    const list = computePriorityReviewList(rows, undefined, 7);
    expect(list.map((item) => item.section)).toEqual([
      'RealBermSevere',
      'RealEffFail',
      'CrestLoss',
      'Truncated',
      'LowScoreOnly',
    ]);
    expect(list[0].reasons).toEqual(['effective_berm', 'berm_below_min', 'low_score']);
    expect(list[1].reasons).toEqual(['effective_berm']);
    expect(list[2].reasons).toEqual(['crest_loss']);
    expect(list[3].reasons).toEqual(['effective_berm', 'berm_below_min', 'low_score']);
    expect(list[4].reasons).toEqual(['low_score']);
  });

  it('resolves sectionId only when unique and returns null for duplicates or missing sections', () => {
    const sections = [
      { id: 'sec-unique', name: 'Unique' },
      { id: 'sec-dup-1', name: 'Duplicate' },
      { id: 'sec-dup-2', name: 'Duplicate' },
    ];
    const rows = [
      makeRow({ section: 'Unique', bench_num: 1, delta_crest: 5 }),
      makeRow({ section: 'Duplicate', bench_num: 2, delta_crest: 5 }),
      makeRow({ section: 'Missing', bench_num: 3, delta_crest: 5 }),
    ];

    const list = computePriorityReviewList(rows, sections, 7);
    const bySection = new Map(list.map((item) => [item.section, item.sectionId]));
    expect(bySection.get('Unique')).toBe('sec-unique');
    expect(bySection.get('Duplicate')).toBeNull();
    expect(bySection.get('Missing')).toBeNull();
  });

  it('respects tie-breaking order and limit', () => {
    const rows = [
      makeRow({ section: 'S2', bench_num: 2, delta_crest: 4, bench_score: 80 }),
      makeRow({ section: 'S1', bench_num: 2, delta_crest: 4, bench_score: 80 }),
      makeRow({ section: 'S1', bench_num: 1, delta_crest: 4, bench_score: 80 }),
      makeRow({ section: 'S3', bench_num: 1, delta_crest: 4, bench_score: 70 }),
    ];

    const full = computePriorityReviewList(rows, undefined, 7, 10);
    expect(full.map((i) => `${i.section}#${i.benchNum}`)).toEqual([
      'S3#1',
      'S1#1',
      'S1#2',
      'S2#2',
    ]);

    const limited = computePriorityReviewList(rows, undefined, 7, 2);
    expect(limited).toHaveLength(2);
    expect(limited.map((i) => `${i.section}#${i.benchNum}`)).toEqual(['S3#1', 'S1#1']);
  });

  it('falls back to defaultBermMin when row.berm_min is null and detects effective_berm without status string', () => {
    const rows = [
      makeRow({
        section: 'S1',
        bench_num: 1,
        level: '2800',
        level_nominal: '2805',
        berm_design: null,
        berm_real: 6.5,
        berm_min: null,
        berm_status: 'CUMPLE',
        effective_berm: 5.5,
        effective_berm_status: null,
        bench_score: 100,
      }),
    ];

    const list = computePriorityReviewList(rows, [{ id: 's1', name: 'S1' }], 7);
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({
      section: 'S1',
      sectionId: 's1',
      benchNum: 1,
      level: '2805',
      bermMin: null,
      bermReal: 6.5,
      bermDesign: null,
      effectiveBerm: 5.5,
      reasons: ['effective_berm', 'berm_below_min'],
    });
  });
});
