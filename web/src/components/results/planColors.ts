import type { ComparisonResult } from '../../api/types';
import { isValidBenchScore, resolveBenchScore } from './ProfileView/domain';
import type { BenchStatus } from './ProfileView/domain/types';

export type PlanColorBy = 'status' | 'score' | 'height' | 'angle' | 'berm';
export type PlanStatusKey = BenchStatus;

export function sectionParameterPassRate(rows: readonly ComparisonResult[], section: string, parameter: 'height' | 'angle' | 'berm'): number | null {
  const statuses = rows.filter((row) => row.section === section).map((row) => row[`${parameter}_status`]?.trim().toUpperCase());
  const evaluable = statuses.filter((status) => status === 'CUMPLE' || status === 'FUERA' || status === 'FUERA DE TOLERANCIA' || status === 'NO CUMPLE' || status === 'NO_CUMPLE');
  return evaluable.length ? evaluable.filter((status) => status === 'CUMPLE').length / evaluable.length : null;
}

export function sectionScore(rows: readonly ComparisonResult[], section: string): number | null {
  const sectionRows = rows.filter((row) => row.section === section);
  const benchScores = sectionRows
    .map((row) => resolveBenchScore(row))
    .filter((score): score is number => score !== null);
  if (benchScores.length > 0) {
    return benchScores.reduce((sum, score) => sum + score, 0) / benchScores.length;
  }
  const sectionScores = sectionRows
    .filter((row) => row.type !== 'MISSING' && row.type !== 'EXTRA')
    .map((row) => row.section_score)
    .filter((score): score is number => isValidBenchScore(score));
  return sectionScores.length > 0
    ? sectionScores.reduce((sum, score) => sum + score, 0) / sectionScores.length
    : null;
}

export function planStatusStrokeDash(status: PlanStatusKey): string | undefined {
  if (status === 'FUERA') return '10 6';
  if (status === 'NO_CUMPLE') return '1 5';
  if (status === 'UNKNOWN') return '10 3 1 3';
  return undefined;
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
