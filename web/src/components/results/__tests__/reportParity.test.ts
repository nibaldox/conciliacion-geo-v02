/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import type { ComparisonResult } from '../../../api/types';
import { filterResults, type ResultFilterState } from '../resultFilters.utils';
import {
  computeGlobalScore,
  computeParameterBreakdown,
  computeProfileComplianceCounts,
  computeProfileScores,
  computeProfileStatuses,
} from '../Dashboard';

interface Expected {
  n_rows: number;
  n_match: number;
  n_missing: number;
  n_extra: number;
  n_sections: number;
  filter_counts: Record<string, number>;
  profiles: Record<string, string>;
  profile_counts: { CUMPLE: number; FUERA: number; NO_CUMPLE: number };
  profile_scores: Record<string, number>;
  global_weighted_score: number;
  parameters: {
    parameter: string;
    cumple: number;
    no_cumple: number;
    pct_cumple: number;
    mean_real: number;
    n_evaluated: number;
    n_not_compared: number;
  }[];
}

interface FallbackExpected {
  profile_scores: Record<string, number>;
  global_weighted_score: number;
}

interface Fixture {
  rows: ComparisonResult[];
  expected: Expected;
  fallback_rows: ComparisonResult[];
  fallback_expected: FallbackExpected;
}

const fixturePath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../../tests/fixtures/report_parity.json',
);
const fixture = JSON.parse(readFileSync(fixturePath, 'utf-8')) as Fixture;
const rows: ComparisonResult[] = fixture.rows;
const expected = fixture.expected;

const filters = (o: Partial<ResultFilterState>): ResultFilterState => ({
  sector: [], section: [], level: [], bench: [], ...o,
});

describe('report_parity fixture — web dashboard functions', () => {
  it('filterResults yields the same counts per dimension as the Python port', () => {
    const cases: Record<string, ResultFilterState> = {
      empty: filters({}),
      sector_A: filters({ sector: ['A'] }),
      sector_B: filters({ sector: ['B'] }),
      section_S01: filters({ section: ['S-01'] }),
      section_S03: filters({ section: ['S-03'] }),
      level_100: filters({ level: ['100'] }),
      level_60: filters({ level: ['60'] }),
      level_empty: filters({ level: [''] }),
      bench_1: filters({ bench: [1] }),
      bench_2: filters({ bench: [2] }),
      sector_A_section_S01: filters({ sector: ['A'], section: ['S-01'] }),
      sector_A_bench_1: filters({ sector: ['A'], bench: [1] }),
      sector_Z: filters({ sector: ['Z'] }),
      section_S01_bench_2: filters({ section: ['S-01'], bench: [2] }),
    };
    for (const [name, state] of Object.entries(cases)) {
      expect(filterResults(rows, state).length, name).toBe(expected.filter_counts[name]);
    }
  });

  it('computeProfileStatuses / counts classify profiles by evaluable MATCH score while keeping EXTRA-only sections UNKNOWN', () => {
    const statuses = computeProfileStatuses(rows);
    const asObject: Record<string, string> = {};
    for (const [section, status] of statuses) asObject[section] = status;
    expect(asObject).toEqual({ ...expected.profiles, 'S-04': 'UNKNOWN' });
    const counts = computeProfileComplianceCounts(rows);
    expect({
      CUMPLE: counts.cumple,
      FUERA: counts.fuera,
      NO_CUMPLE: counts.noCumple,
    }).toEqual({
      CUMPLE: expected.profile_counts.CUMPLE,
      FUERA: 0,
      NO_CUMPLE: expected.profile_counts.NO_CUMPLE - 1,
    });
  });

  it('computeProfileScores / computeGlobalScore match the weighted scores', () => {
    const scores = computeProfileScores(rows);
    for (const [section, score] of Object.entries(expected.profile_scores)) {
      if (score == null) expect(scores.has(section), section).toBe(false);
      else expect(scores.get(section), section).toBeCloseTo(score, 9);
    }
    expect(scores.has('S-04')).toBe(false);
    expect(computeGlobalScore(rows)).toBeCloseTo(expected.global_weighted_score, 9);
  });

  it('counts the per-parameter denominator over MATCH rows only (D11)', () => {
    expect(expected.parameters.map((p) => p.n_evaluated)).toEqual([expected.n_match, expected.n_match, expected.n_match]);
    expect(expected.parameters.map((p) => p.n_not_compared)).toEqual(
      Array(3).fill(expected.n_missing + expected.n_extra),
    );
  });

  it('computeParameterBreakdown matches cumple/noCumple and computes mean_real over MATCH rows only', () => {
    const breakdown = computeParameterBreakdown(rows);
    expect(breakdown.map((p) => p.parameter)).toEqual(['height', 'angle', 'berm']);
    const matchRows = rows.filter((r) => r.type === 'MATCH');
    const matchMean = (key: 'height_real' | 'angle_real' | 'berm_real') => {
      const vals = matchRows.map((r) => r[key]).filter((v): v is number => v != null && Number.isFinite(v));
      return vals.reduce((a, b) => a + b, 0) / vals.length;
    };
    const expectedMatchMeans = {
      height: matchMean('height_real'),
      angle: matchMean('angle_real'),
      berm: matchMean('berm_real'),
    };
    for (const p of breakdown) {
      const e = expected.parameters.find((x) => x.parameter === p.parameter)!;
      expect(p.cumple, p.parameter).toBe(e.cumple);
      expect(p.noCumple, p.parameter).toBe(e.no_cumple);
      expect(p.nEvaluated, p.parameter).toBe(e.n_evaluated);
      expect(p.nNotCompared, p.parameter).toBe(e.n_not_compared);
      expect(p.cumple + p.noCumple, p.parameter).toBe(e.n_evaluated);
      expect((100 * p.cumple) / p.nEvaluated, p.parameter).toBeCloseTo(e.pct_cumple, 9);
      const mean = p.realCount === 0 ? null : p.realSum / p.realCount;
      expect(mean, p.parameter).not.toBeNull();
      expect(mean!, p.parameter).toBeCloseTo(expectedMatchMeans[p.parameter], 5);
    }
  });

  it('scores MATCH rows without bench_score using the web weighted fallback', () => {
    const fallbackRows = fixture.fallback_rows;
    const fallbackExpected = fixture.fallback_expected;
    const scores = computeProfileScores(fallbackRows);
    for (const [section, score] of Object.entries(fallbackExpected.profile_scores)) {
      if (score == null) expect(scores.has(section), section).toBe(false);
      else expect(scores.get(section), section).toBeCloseTo(score, 9);
    }
    expect(computeGlobalScore(fallbackRows)).toBeCloseTo(fallbackExpected.global_weighted_score, 9);
  });
});
