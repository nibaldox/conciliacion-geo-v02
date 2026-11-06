import { describe, expect, it } from 'vitest';
import type { ComparisonResult } from '../../../api/types';
import { parameterBars, sectionSummary } from './dashboardSelectors';

const row = (values: Partial<ComparisonResult>): ComparisonResult => ({ section: 'S1', bench_num: 1, level: '100', type: 'MATCH', height_status: 'CUMPLE', angle_status: 'CUMPLE', berm_status: 'CUMPLE', ...values } as ComparisonResult);

describe('dashboard selectors', () => {
  it('summarizes only the selected section, sorts benches and ignores non-finite values', () => {
    const rows = [row({ bench_num: 2, height_dev: 2, angle_dev: NaN }), row({ bench_num: 1, height_dev: 0, angle_dev: 4 }), row({ section: 'S2', height_dev: 99 })];
    const summary = sectionSummary(rows, 'S1', new Map([['S1', 'CUMPLE']]));
    expect(summary?.benches.map((b) => b.bench_num)).toEqual([1, 2]);
    expect(summary?.means.height_dev).toBe(1);
    expect(summary?.means.angle_dev).toBe(4);
    expect(summary?.means.delta_toe).toBeNull();
    expect(summary?.status).toBe('CUMPLE');
    expect(sectionSummary(rows, 'absent', new Map())).toBeNull();
  });
  it('counts parameter status tiers including unknown and special values', () => {
    const bars = parameterBars([row({ height_status: 'CUMPLE' }), row({ height_status: ' FUERA DE TOLERANCIA ' }), row({ height_status: 'NO CUMPLE' }), row({ height_status: '-' }), row({ height_status: 'NO CONSTRUIDO' })]);
    expect(bars[0]).toEqual({ parameter: 'height', ok: 1, warn: 1, nok: 1, unknown: 2 });
  });
});
