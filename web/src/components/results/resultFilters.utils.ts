import type { ComparisonResult } from '../../api/types';

export interface ResultFilterState {
  sector: string[];
  section: string[];
  level: string[];
  bench: number[];
}

export const EMPTY_RESULT_FILTERS: ResultFilterState = { sector: [], section: [], level: [], bench: [] };

export function nominalLevelOf(row: ComparisonResult): string {
  return row.level_nominal ?? row.level;
}

function nominalLabelsBySector(rows: readonly ComparisonResult[]): Map<string, Set<string>> {
  const labels = new Map<string, Set<string>>();
  for (const row of rows) {
    if (row.level_nominal == null) continue;
    const sector = row.sector ?? '';
    const sectorLabels = labels.get(sector) ?? new Set<string>();
    sectorLabels.add(row.level_nominal);
    labels.set(sector, sectorLabels);
  }
  return labels;
}

function matchesLevel(
  row: ComparisonResult,
  selected: readonly string[],
  sectorLabels: ReadonlySet<string> | undefined,
): boolean {
  if (row.level_nominal != null && selected.includes(row.level_nominal)) return true;
  return selected.some((value) => !sectorLabels?.has(value) && value === row.level);
}

export function filterResults(
  rows: readonly ComparisonResult[] | null | undefined,
  filters: ResultFilterState,
): ComparisonResult[] {
  if (!rows) return [];
  const labels = filters.level.length === 0 ? null : nominalLabelsBySector(rows);
  return rows.filter((row) =>
    (filters.sector.length === 0 || filters.sector.includes(row.sector))
    && (filters.section.length === 0 || filters.section.includes(row.section))
    && (labels === null || matchesLevel(row, filters.level, labels.get(row.sector ?? '')))
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

function numericLevel(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function uniqueLevelOptions(results: readonly ComparisonResult[] | null | undefined): string[] {
  return [...new Set((results ?? []).map(nominalLevelOf))].sort((a, b) => {
    const na = numericLevel(a);
    const nb = numericLevel(b);
    if (na !== null && nb !== null) return nb - na || a.localeCompare(b);
    if (na !== null) return -1;
    if (nb !== null) return 1;
    return a.localeCompare(b);
  });
}

export function toggleDimensionValue(current: readonly string[], value: string): string[] {
  return current.includes(value)
    ? current.filter((candidate) => candidate !== value)
    : [...current, value];
}
