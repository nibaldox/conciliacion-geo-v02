import { describe, expect, it } from 'vitest';
import type { ComparisonResult } from '../../../api/types';
import { planColor, sectionParameterPassRate, sectionScore } from '../planColors';
const row = (values: Partial<ComparisonResult>): ComparisonResult => ({ section: 'A', height_status: 'CUMPLE', angle_status: 'CUMPLE', berm_status: 'CUMPLE', ...values } as ComparisonResult);
describe('plan colors', () => {
  it.each(['height', 'angle', 'berm'] as const)('counts evaluable %s statuses', (parameter) => {
    const key = `${parameter}_status`;
    const rows = ['CUMPLE', 'NO CUMPLE', 'FUERA DE TOLERANCIA', '-', 'NO CONSTRUIDO', 'FALTA BANCO', 'BANCO ADICIONAL', 'EXTRA', '', 'desconocido'].map((status) => row({ [key]: status }));
    expect(sectionParameterPassRate(rows, 'A', parameter)).toBe(1 / 3);
    expect(sectionParameterPassRate(rows, 'B', parameter)).toBeNull();
  });
  it('uses valid section scores without fabricating missing scores', () => {
    expect(sectionScore([row({ section_score: 80 }), row({ section_score: 60 }), row({ section_score: NaN })], 'A')).toBe(70);
    expect(sectionScore([row({})], 'A')).toBeNull();
  });
  it('recalculates section score from filtered bench scores before falling back to section_score', () => {
    expect(sectionScore([
      row({ section: 'S-70', level: '3065', type: 'MATCH', bench_score: 90, section_score: 45 }),
    ], 'S-70')).toBe(90);
    expect(sectionScore([
      row({ section: 'S-70', type: 'MATCH', bench_score: 90, section_score: 45 }),
      row({ section: 'S-70', type: 'MATCH', bench_score: 70, section_score: 45 }),
      row({ section: 'S-70', type: 'MISSING', bench_score: 0, section_score: 45 }),
    ], 'S-70')).toBe(80);
    expect(sectionScore([
      row({ section: 'S-70', type: 'MISSING', section_score: 45 }),
      row({ section: 'S-70', type: 'EXTRA', section_score: 55 }),
    ], 'S-70')).toBeNull();
    expect(sectionScore([
      row({ section: 'S-70', type: 'MATCH', bench_score: 105, section_score: 105 }),
    ], 'S-70')).toBeNull();
  });
  it('maps status tokens and scale stops', () => {
    expect(planColor('status', 'CUMPLE')).toBe('var(--status-ok-text)');
    expect(planColor('status', 'FUERA')).toBe('var(--status-warn-text)');
    expect(planColor('status', 'NO_CUMPLE')).toBe('var(--status-nok-text)');
    expect(planColor('score', null)).toBe('var(--color-text-muted)');
    expect(planColor('score', 0)).toBe('#eb485d');
    expect(planColor('height', 0.5)).toBe('#e68f19');
    expect(planColor('berm', 1)).toBe('#39ab60');
  });
});
