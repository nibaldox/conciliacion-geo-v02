import { describe, expect, it } from 'vitest';
import type { ComparisonResult } from '../../../api/types';
import { computeDashboardCoverage, type DefinedSectionRef } from './coverageSelectors';

const makeRow = (overrides: Partial<ComparisonResult> = {}): ComparisonResult => ({
  sector: 'North',
  section: 'S-01',
  bench_num: 1,
  type: 'MATCH',
  level: '100',
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
  berm_min: 6,
  berm_status: 'CUMPLE',
  delta_crest: 0,
  delta_toe: 0,
  ...overrides,
});

const makeSectionName = (index: number): string => `S-${String(index).padStart(2, '0')}`;

describe('computeDashboardCoverage', () => {
  it('handles empty datasets with undefined, empty, or populated definedSections', () => {
    const emptyUndefined = computeDashboardCoverage([], [], undefined, 6);
    expect(emptyUndefined).toEqual({
      totalSectionsDefined: 0,
      evaluatedSections: 0,
      evaluatedFilteredSections: 0,
      missingSections: [],
      totalRows: 0,
      designBenches: 0,
      comparedBenches: 0,
      evaluableCompleteBenches: 0,
      notBuiltBenches: 0,
      extraBenches: 0,
      truncatedStateBenches: 0,
      notExcavatedStateBenches: 0,
      unmeasuredStateBenches: 0,
      truncatedBermDesignCount: 0,
      truncatedBermDesignPct: 0,
      bermZeroRealCount: 0,
    });

    const emptyArray = computeDashboardCoverage([], [], [], 6);
    expect(emptyArray.totalSectionsDefined).toBe(0);
    expect(emptyArray.missingSections).toEqual([]);

    const definedOnly = computeDashboardCoverage(
      [],
      [],
      [
        { id: '3', name: 'S-80' },
        { id: '1', name: 'S-19' },
        { id: '2', name: 'S-53' },
        { id: '4', name: 'S-19' },
      ],
      6,
    );
    expect(definedOnly.totalSectionsDefined).toBe(4);
    expect(definedOnly.evaluatedSections).toBe(0);
    expect(definedOnly.missingSections).toEqual(['S-19', 'S-53', 'S-80']);
  });

  it('falls back to evaluatedSections when definedSections is omitted or empty', () => {
    const rows = [
      makeRow({ section: 'S-01', bench_num: 1 }),
      makeRow({ section: 'S-01', bench_num: 2 }),
      makeRow({ section: 'S-02', bench_num: 1 }),
    ];

    const coverageUndefined = computeDashboardCoverage(rows, rows, undefined, 6);
    expect(coverageUndefined.totalSectionsDefined).toBe(2);
    expect(coverageUndefined.evaluatedSections).toBe(2);
    expect(coverageUndefined.evaluatedFilteredSections).toBe(2);
    expect(coverageUndefined.missingSections).toEqual([]);

    const coverageEmpty = computeDashboardCoverage(rows, rows, [], 6);
    expect(coverageEmpty.totalSectionsDefined).toBe(2);
    expect(coverageEmpty.missingSections).toEqual([]);
  });

  it('computes the INFORME.md session scenario accurately', () => {
    const definedSections: DefinedSectionRef[] = Array.from({ length: 92 }, (_, idx) => ({
      id: `sec-${idx + 1}`,
      name: makeSectionName(idx + 1),
    }));
    const missingSet = new Set(['S-19', 'S-53', 'S-80']);
    const evaluatedNames = definedSections.map((s) => s.name).filter((name) => !missingSet.has(name));

    const rows: ComparisonResult[] = [];
    const truncatedCount = 54;
    for (let i = 0; i < 156; i++) {
      rows.push(
        makeRow({
          section: evaluatedNames[i % evaluatedNames.length],
          bench_num: Math.floor(i / evaluatedNames.length) + 1,
          type: 'MATCH',
          berm_design: i < truncatedCount ? 3.2 : 8.5,
          berm_real: i < 12 ? 0 : 7.5,
          berm_min: 6,
        }),
      );
    }
    for (let i = 0; i < 67; i++) {
      rows.push(
        makeRow({
          section: evaluatedNames[i % evaluatedNames.length],
          bench_num: 10 + i,
          type: 'MISSING',
          berm_design: 2.0,
          berm_real: null,
        }),
      );
    }
    for (let i = 0; i < 3; i++) {
      rows.push(
        makeRow({
          section: evaluatedNames[i],
          bench_num: 100 + i,
          type: 'EXTRA',
          berm_design: null,
          berm_real: 0,
        }),
      );
    }

    const coverage = computeDashboardCoverage(rows, rows, definedSections, 6);

    expect(coverage.totalSectionsDefined).toBe(92);
    expect(coverage.evaluatedSections).toBe(89);
    expect(coverage.evaluatedFilteredSections).toBe(89);
    expect(coverage.missingSections).toEqual(['S-19', 'S-53', 'S-80']);
    expect(coverage.totalRows).toBe(226);
    expect(coverage.comparedBenches).toBe(156);
    expect(coverage.notBuiltBenches).toBe(67);
    expect(coverage.extraBenches).toBe(3);
    expect(coverage.designBenches).toBe(223);
    expect(coverage.truncatedBermDesignCount).toBe(truncatedCount);
    expect(coverage.truncatedBermDesignPct).toBeCloseTo((truncatedCount / 156) * 100, 10);
    expect(coverage.evaluableCompleteBenches).toBe(156 - truncatedCount);
    expect(coverage.bermZeroRealCount).toBe(12);
  });

  it('computes missingSections and evaluatedSections from allRows while scoping bench counts to filteredRows', () => {
    const definedSections: DefinedSectionRef[] = [
      { id: '1', name: 'S-01' },
      { id: '2', name: 'S-02' },
      { id: '3', name: 'S-03' },
      { id: '4', name: 'S-04' },
      { id: '5', name: 'S-05' },
    ];
    const allRows: ComparisonResult[] = [
      makeRow({ sector: 'North', section: 'S-01', bench_num: 1, type: 'MATCH', berm_design: 4, berm_min: 6 }),
      makeRow({ sector: 'North', section: 'S-01', bench_num: 2, type: 'MISSING' }),
      makeRow({ sector: 'South', section: 'S-02', bench_num: 1, type: 'MATCH', berm_design: 8, berm_min: 6 }),
      makeRow({ sector: 'South', section: 'S-03', bench_num: 1, type: 'EXTRA' }),
    ];
    const filteredRows = allRows.filter((r) => r.sector === 'North');

    const coverage = computeDashboardCoverage(filteredRows, allRows, definedSections, 6);

    expect(coverage.totalSectionsDefined).toBe(5);
    expect(coverage.evaluatedSections).toBe(3);
    expect(coverage.evaluatedFilteredSections).toBe(1);
    expect(coverage.missingSections).toEqual(['S-04', 'S-05']);
    expect(coverage.totalRows).toBe(2);
    expect(coverage.comparedBenches).toBe(1);
    expect(coverage.notBuiltBenches).toBe(1);
    expect(coverage.extraBenches).toBe(0);
    expect(coverage.designBenches).toBe(2);
    expect(coverage.truncatedBermDesignCount).toBe(1);
    expect(coverage.truncatedBermDesignPct).toBe(100);
    expect(coverage.evaluableCompleteBenches).toBe(0);
  });

  it('uses proposed_evaluable when present and excludes EXTRA rows', () => {
    const rows: ComparisonResult[] = [
      makeRow({ bench_num: 1, type: 'MATCH', proposed_evaluable: true, design_bench_state: 'section_truncated', berm_design: 2 }),
      makeRow({ bench_num: 2, type: 'MATCH', proposed_evaluable: false, design_bench_state: 'excavated', berm_design: 10 }),
      makeRow({ bench_num: 3, type: 'MISSING', proposed_evaluable: true, design_bench_state: 'not_excavated' }),
      makeRow({ bench_num: 4, type: 'EXTRA', proposed_evaluable: true, design_bench_state: 'excavated' }),
      makeRow({ bench_num: 5, type: 'MISSING', proposed_evaluable: false, design_bench_state: 'unmeasured' }),
    ];

    const coverage = computeDashboardCoverage(rows, rows, undefined, 6);

    expect(coverage.evaluableCompleteBenches).toBe(2);
    expect(coverage.truncatedStateBenches).toBe(1);
    expect(coverage.notExcavatedStateBenches).toBe(1);
    expect(coverage.unmeasuredStateBenches).toBe(1);
  });

  it('falls back to design_bench_state when proposed_evaluable is absent and excludes EXTRA rows', () => {
    const rows: ComparisonResult[] = [
      makeRow({ bench_num: 1, type: 'MATCH', design_bench_state: 'excavated', berm_design: 2 }),
      makeRow({ bench_num: 2, type: 'MATCH', design_bench_state: 'section_truncated', berm_design: 10 }),
      makeRow({ bench_num: 3, type: 'MISSING', design_bench_state: 'not_excavated' }),
      makeRow({ bench_num: 4, type: 'MISSING', design_bench_state: 'unmeasured' }),
      makeRow({ bench_num: 5, type: 'MISSING', design_bench_state: 'excavated' }),
      makeRow({ bench_num: 6, type: 'EXTRA', design_bench_state: 'excavated' }),
    ];

    const coverage = computeDashboardCoverage(rows, rows, undefined, 6);

    expect(coverage.evaluableCompleteBenches).toBe(2);
    expect(coverage.truncatedStateBenches).toBe(1);
    expect(coverage.notExcavatedStateBenches).toBe(1);
    expect(coverage.unmeasuredStateBenches).toBe(1);
  });

  it('falls back to non-truncated MATCH rows when both proposed_evaluable and design_bench_state are absent or null', () => {
    const rows: ComparisonResult[] = [
      makeRow({ bench_num: 1, type: 'MATCH', design_bench_state: null, berm_design: null, berm_min: 6 }),
      makeRow({ bench_num: 2, type: 'MATCH', design_bench_state: null, berm_design: 6, berm_min: 6 }),
      makeRow({ bench_num: 3, type: 'MATCH', design_bench_state: null, berm_design: 5.99, berm_min: 6 }),
      makeRow({ bench_num: 4, type: 'MATCH', design_bench_state: '', berm_design: Number.NaN, berm_min: 6 }),
      makeRow({ bench_num: 5, type: 'MISSING', design_bench_state: null, berm_design: 10, berm_min: 6 }),
      makeRow({ bench_num: 6, type: 'EXTRA', design_bench_state: null, berm_design: 10, berm_min: 6 }),
    ];

    const coverage = computeDashboardCoverage(rows, rows, undefined, 6);

    expect(coverage.comparedBenches).toBe(4);
    expect(coverage.truncatedBermDesignCount).toBe(1);
    expect(coverage.truncatedBermDesignPct).toBe(25);
    expect(coverage.evaluableCompleteBenches).toBe(3);
  });

  it('counts bermZeroRealCount only on MATCH rows and resolves per-row berm_min vs defaultBermMin', () => {
    const rows: ComparisonResult[] = [
      makeRow({ bench_num: 1, type: 'MATCH', berm_design: 7, berm_min: 8, berm_real: 0 }),
      makeRow({ bench_num: 2, type: 'MATCH', berm_design: 5, berm_min: 4, berm_real: 0 }),
      makeRow({ bench_num: 3, type: 'MATCH', berm_design: 5.5, berm_min: null, berm_real: 0.01 }),
      makeRow({ bench_num: 4, type: 'MATCH', berm_design: 6, berm_min: Number.NaN, berm_real: null }),
      makeRow({ bench_num: 5, type: 'MATCH', berm_design: 5.9, berm_min: Number.POSITIVE_INFINITY, berm_real: Number.NaN }),
      makeRow({ bench_num: 6, type: 'MISSING', berm_design: 1, berm_min: 10, berm_real: 0 }),
      makeRow({ bench_num: 7, type: 'EXTRA', berm_design: 1, berm_min: 10, berm_real: 0 }),
    ];

    const coverage = computeDashboardCoverage(rows, rows, undefined, 6);

    expect(coverage.comparedBenches).toBe(5);
    expect(coverage.truncatedBermDesignCount).toBe(3);
    expect(coverage.truncatedBermDesignPct).toBe(60);
    expect(coverage.evaluableCompleteBenches).toBe(2);
    expect(coverage.bermZeroRealCount).toBe(2);
  });
});
