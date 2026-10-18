import type { ComparisonResult } from '../../api/types';

export interface ResultFilterState {
  sector: string[];
  section: string[];
  level: string[];
  bench: number[];
}

export const EMPTY_RESULT_FILTERS: ResultFilterState = { sector: [], section: [], level: [], bench: [] };

export function filterResults(
  rows: readonly ComparisonResult[] | null | undefined,
  filters: ResultFilterState,
): ComparisonResult[] {
  if (!rows) return [];
  return rows.filter((row) =>
    (filters.sector.length === 0 || filters.sector.includes(row.sector))
    && (filters.section.length === 0 || filters.section.includes(row.section))
    && (filters.level.length === 0 || filters.level.includes(row.level))
    && (filters.bench.length === 0 || filters.bench.includes(row.bench_num)));
}

function uniqueValues(values: readonly string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

export function uniqueSectorOptions(results: readonly ComparisonResult[] | null | undefined): string[] {
  return uniqueValues((results ?? []).map((row) => row.sector));
}

export function uniqueSectionOptions(results: readonly ComparisonResult[] | null | undefined): string[] {
  return uniqueValues((results ?? []).map((row) => row.section));
}

export function uniqueLevelOptions(results: readonly ComparisonResult[] | null | undefined): string[] {
  return uniqueValues((results ?? []).map((row) => row.level));
}

export function toggleDimensionValue(current: readonly string[], value: string): string[] {
  return current.includes(value)
    ? current.filter((candidate) => candidate !== value)
    : [...current, value];
}
