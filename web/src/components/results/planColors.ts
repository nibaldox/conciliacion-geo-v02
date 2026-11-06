import type { ComparisonResult } from '../../api/types';
import type { BenchStatus } from './ProfileView/domain/types';

export type PlanColorBy = 'status' | 'score' | 'height' | 'angle' | 'berm';
export type PlanStatusKey = BenchStatus;

export function sectionParameterPassRate(rows: readonly ComparisonResult[], section: string, parameter: 'height' | 'angle' | 'berm'): number | null {
  const statuses = rows.filter((row) => row.section === section).map((row) => row[`${parameter}_status`]?.trim().toUpperCase());
  const evaluable = statuses.filter((status) => status === 'CUMPLE' || status === 'FUERA' || status === 'FUERA DE TOLERANCIA' || status === 'NO CUMPLE' || status === 'NO_CUMPLE');
  return evaluable.length ? evaluable.filter((status) => status === 'CUMPLE').length / evaluable.length : null;
}

export function sectionScore(rows: readonly ComparisonResult[], section: string): number | null {
  const scores = rows.filter((row) => row.section === section).map((row) => row.section_score).filter((score): score is number => typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 100);
  return scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : null;
}

export function planColor(colorBy: PlanColorBy, value: number | PlanStatusKey | null): string {
  if (colorBy === 'status') {
    if (value === 'CUMPLE') return 'var(--status-ok-text)';
    if (value === 'FUERA') return 'var(--status-warn-text)';
    if (value === 'NO_CUMPLE') return 'var(--status-nok-text)';
    return 'var(--color-text-muted)';
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'var(--color-text-muted)';
  const v = Math.max(0, Math.min(1, value));
  const stops = [[235, 72, 93], [230, 143, 25], [57, 171, 96]];
  const index = v < 0.5 ? 0 : 1;
  const fraction = v < 0.5 ? v * 2 : (v - 0.5) * 2;
  return `#${stops[index]!.map((channel, i) => Math.round(channel + (stops[index + 1]![i]! - channel) * fraction).toString(16).padStart(2, '0')).join('')}`;
}
