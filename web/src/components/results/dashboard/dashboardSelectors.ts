import type { ComparisonResult } from '../../../api/types';
import type { BenchStatus } from '../ProfileView/domain/types';
import { resolveBenchScore } from '../ProfileView/domain/status';

export type Parameter = 'height' | 'angle' | 'berm';
export type ParameterTone = 'ok' | 'warn' | 'nok' | 'unknown';
export function parameterTone(raw: string | null | undefined): ParameterTone {
  const value = raw?.trim().toUpperCase();
  if (value === 'CUMPLE') return 'ok';
  if (value === 'FUERA' || value === 'FUERA DE TOLERANCIA') return 'warn';
  if (value === 'NO CUMPLE' || value === 'NO_CUMPLE') return 'nok';
  return 'unknown';
}
export function parameterBars(rows: readonly ComparisonResult[]) {
  return (['height', 'angle', 'berm'] as const).map((parameter) => {
    const counts = { parameter, ok: 0, warn: 0, nok: 0, unknown: 0 };
    for (const row of rows) counts[parameterTone(row[`${parameter}_status`])]++;
    return counts;
  });
}
export function sectionSummary(rows: readonly ComparisonResult[], section: string, statuses: ReadonlyMap<string, BenchStatus>) {
  const benches = rows.filter((row) => row.section === section).sort((a, b) => a.bench_num - b.bench_num);
  if (!benches.length) return null;
  const mean = (values: readonly (number | null | undefined)[]) => {
    const finite = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    return finite.length ? finite.reduce((sum, value) => sum + value, 0) / finite.length : null;
  };
  return {
    benches,
    status: statuses.get(section) ?? 'UNKNOWN',
    score: mean(benches.map(resolveBenchScore)),
    means: {
      height_dev: mean(benches.map((row) => row.height_dev)),
      angle_dev: mean(benches.map((row) => row.angle_dev)),
      delta_crest: mean(benches.map((row) => row.delta_crest)),
      delta_toe: mean(benches.map((row) => row.delta_toe)),
    },
  };
}
