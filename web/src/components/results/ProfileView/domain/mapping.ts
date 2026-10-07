/**
 * Adapter: translate API DTOs into the domain `ProfileViewModel`.
 *
 * This is the ONLY place in the feature that knows about API types.
 * The domain (`Bench`, `ProfileLine`, `SectionMeta`) is wire-format
 * agnostic. If the backend renames a field, this is the only file
 * to update.
 *
 * The transformation is pure — no React, no I/O — so it's tested
 * directly with sample DTOs.
 */

import type { ComparisonResultDto, ProfileDataDto, SectionResponseDto } from './types';
import type { Bench, ComparisonBenchStatus, DesignBenchStatus, ProfileLine, ProfilePoint, ProfileViewModel, ProfileWarnings, SectionMeta } from './types';
import { worstOfThree, parseBenchStatus } from './status';

// ─── Section meta ───────────────────────────────────────────

/** Section DTO → domain meta. */
export function toSectionMeta(dto: SectionResponseDto): SectionMeta {
  return {
    id: dto.id,
    name: dto.name,
    sector: dto.sector,
    azimuth: dto.azimuth,
    length: dto.length,
    // Defensive: API returns `number[]` of length 2. Coerce to a
    // 2-tuple, defaulting to [0, 0] if malformed.
    origin: tuple2(dto.origin, [0, 0]),
  };
}

function tuple2(arr: readonly number[], fallback: readonly [number, number]): readonly [number, number] {
  if (arr.length >= 2 && Number.isFinite(arr[0]) && Number.isFinite(arr[1])) {
    return [arr[0]!, arr[1]!];
  }
  return fallback;
}

// ─── Profile line ───────────────────────────────────────────

function toPoints(p: { distances: readonly number[]; elevations: readonly number[] } | null | undefined): readonly ProfilePoint[] {
  if (!p) return [];
  const len = Math.min(p.distances.length, p.elevations.length);
  const out: ProfilePoint[] = [];
  for (let i = 0; i < len; i++) {
    const d = p.distances[i]!;
    const z = p.elevations[i]!;
    if (Number.isFinite(d) && Number.isFinite(z)) {
      out.push({ distance: d, elevation: z });
    }
  }
  return out;
}

export function toProfileLines(dto: ProfileDataDto): readonly ProfileLine[] {
  const lines: ProfileLine[] = [];
  const d = toPoints(dto.design ?? null);
  if (d.length > 0) lines.push({ kind: 'design', points: d });
  const t = toPoints(dto.topo ?? null);
  if (t.length > 0) lines.push({ kind: 'topo', points: t });
  const rd = toPoints(dto.reconciled_design_legacy ?? null);
  if (rd.length > 0) lines.push({ kind: 'reconciled_design', points: rd });
  const rt = toPoints(dto.reconciled_topo_legacy ?? null);
  if (rt.length > 0) lines.push({ kind: 'reconciled_topo', points: rt });
  return lines;
}

// ─── Bench (domain) ─────────────────────────────────────────

/**
 * A `Bench` augmented with the spill-material geometry carried by
 * the backend (`spill_width`, `spill_start_distance`,
 * `spill_start_elevation`). These are `null` when a bench has no
 * spill data (legacy fixtures, demo mode, flat benches). The
 * renderer (`ProfileChart`) reads them to draw the "Derrame" area.
 *
 * Extends `Bench` rather than living on the base type so the core
 * domain contract stays untouched; the mapping layer is the only
 * place that knows the spill fields exist.
 */
export interface SpillBench extends Bench {
  readonly spillWidth: number | null;
  readonly spillStartDistance: number | null;
  readonly spillStartElevation: number | null;
}

/** Raw bench shape that may carry optional spill fields from the API. */
type RawBench = {
  bench_number: number;
  crest_elevation: number;
  crest_distance: number;
  toe_elevation: number;
  toe_distance: number;
  bench_height: number;
  face_angle: number;
  berm_width: number;
  is_ramp: boolean;
  spill_width?: number | null;
  spill_start_distance?: number | null;
  spill_start_elevation?: number | null;
  floor_elevation?: number | null;
};

/**
 * Build a domain Bench from a `BenchParams` (raw topo extraction)
 * plus a `ComparisonResult | null` (if one exists for this bench).
 *
 * When no comparison exists, status is UNKNOWN and matched=false.
 */
export function toBench(
  raw: RawBench,
  comparison: ComparisonResultDto | null,
): SpillBench {
  const matched = comparison?.type === 'MATCH';
  const designComparison = matched ? comparison : null;
  const status = comparison
    ? worstOfThree(comparison.height_status, comparison.angle_status, comparison.berm_status)
    : 'UNKNOWN';

  return {
    benchNumber: raw.bench_number,
    crestElevation: raw.crest_elevation,
    crestDistance: raw.crest_distance,
    toeElevation: raw.toe_elevation,
    toeDistance: raw.toe_distance,
    designBenchNumber: designComparison?.bench_num ?? null,
    height: raw.bench_height,
    designHeight: designComparison?.height_design ?? null,
    faceAngle: raw.face_angle,
    designAngle: designComparison?.angle_design ?? null,
    // Backend may report 0 for "no berm" but that's an actual
    // measurement too. We treat 0 as a real value, and missing/
    // null/undefined as no berm.
    bermWidth: Number.isFinite(raw.berm_width) ? raw.berm_width : null,
    designBerm: designComparison?.berm_design ?? null,
    isRamp: raw.is_ramp,
    status,
    heightStatus: comparison ? parseBenchStatus(comparison.height_status) : 'UNKNOWN',
    angleStatus: comparison ? parseBenchStatus(comparison.angle_status) : 'UNKNOWN',
    bermStatus: comparison ? parseBenchStatus(comparison.berm_status) : 'UNKNOWN',
    matched,
    matchType: comparison?.type ?? null,
    deltaCrest: designComparison?.delta_crest ?? null,
    deltaToe: designComparison?.delta_toe ?? null,
    spillWidth: raw.spill_width != null && Number.isFinite(raw.spill_width) ? raw.spill_width : null,
    spillStartDistance: raw.spill_start_distance != null && Number.isFinite(raw.spill_start_distance) ? raw.spill_start_distance : null,
    spillStartElevation: raw.spill_start_elevation != null && Number.isFinite(raw.spill_start_elevation) ? raw.spill_start_elevation : null,
    floorElevation: raw.floor_elevation != null && Number.isFinite(raw.floor_elevation) && raw.floor_elevation > 0 ? raw.floor_elevation : null,
    benchScore: comparison?.bench_score ?? null,
  };
}

export function toBenches(
  rawBenches: readonly RawBench[] | null | undefined,
  sectionName: string,
  comparisons: readonly ComparisonResultDto[] | null | undefined,
): readonly SpillBench[] {
  if (!rawBenches || rawBenches.length === 0) return [];
  const sectionComparisons = (comparisons ?? []).filter((c) => c.section === sectionName);
  const explicitByTopo = new Map<number, ComparisonResultDto[]>();
  for (const comparison of sectionComparisons) {
    if (comparison.type === 'MISSING' || !Number.isInteger(comparison.bench_num_topo)) continue;
    const matches = explicitByTopo.get(comparison.bench_num_topo!) ?? [];
    matches.push(comparison);
    explicitByTopo.set(comparison.bench_num_topo!, matches);
  }
  const legacyComparisons = sectionComparisons.filter(
    (comparison) => comparison.type !== 'MISSING' && comparison.bench_num_topo == null,
  );
  const legacyByTopo = inferLegacyComparisons(rawBenches, legacyComparisons);

  return rawBenches.map((bench) => {
    const explicitMatches = explicitByTopo.get(bench.bench_number) ?? [];
    const comparison = explicitMatches.length === 1
      ? explicitMatches[0]!
      : explicitMatches.length === 0
        ? legacyByTopo.get(bench.bench_number) ?? null
        : null;
    return toBench(bench, comparison);
  });
}

/** Preserve design-bank identity and the backend's canonical tier, including unbuilt banks. */
export function toComparisonBenchStatuses(
  comparisons: readonly ComparisonResultDto[] | null | undefined,
  sectionName?: string,
): readonly ComparisonBenchStatus[] {
  return (comparisons ?? [])
    .filter((comparison) => sectionName == null || comparison.section === sectionName)
    .filter((comparison) => comparison.type === 'MATCH' || comparison.type === 'MISSING' || comparison.type === 'EXTRA')
    .map((comparison) => {
      const parsedElevation = comparison.type === 'EXTRA' || comparison.level.trim() === ''
        ? Number.NaN
        : Number(comparison.level);
      return {
        sectionName: comparison.section,
        designBenchNumber: comparison.type === 'EXTRA' ? null : comparison.bench_num,
        designElevation: Number.isFinite(parsedElevation) ? parsedElevation : null,
        status: worstOfThree(comparison.height_status, comparison.angle_status, comparison.berm_status),
        hasTopo: comparison.type !== 'MISSING',
        isAdditional: comparison.type === 'EXTRA',
      };
    });
}

export function toDesignBenchStatuses(
  comparisons: readonly ComparisonResultDto[] | null | undefined,
  sectionName?: string,
): readonly DesignBenchStatus[] {
  return toComparisonBenchStatuses(comparisons, sectionName)
    .filter((bench): bench is ComparisonBenchStatus & { designBenchNumber: number } => !bench.isAdditional && bench.designBenchNumber != null)
    .map(({ sectionName: name, designBenchNumber, designElevation, status, hasTopo }) => ({
      sectionName: name, designBenchNumber, designElevation, status, hasTopo,
    }));
}

function inferLegacyComparisons(
  rawBenches: readonly RawBench[],
  comparisons: readonly ComparisonResultDto[],
): Map<number, ComparisonResultDto> {
  const comparisonCandidates = rawBenches.map((bench) => {
    const fingerprint = rawBenchFingerprint(bench);
    return fingerprint == null
      ? []
      : comparisons.filter((comparison) => comparisonFingerprint(comparison) === fingerprint);
  });
  const candidateBenchCount = new Map<ComparisonResultDto, number>();
  for (const candidates of comparisonCandidates) {
    for (const comparison of candidates) {
      candidateBenchCount.set(comparison, (candidateBenchCount.get(comparison) ?? 0) + 1);
    }
  }

  const inferred = new Map<number, ComparisonResultDto>();
  comparisonCandidates.forEach((candidates, index) => {
    if (candidates.length !== 1) return;
    const comparison = candidates[0]!;
    if (candidateBenchCount.get(comparison) === 1) {
      inferred.set(rawBenches[index]!.bench_number, comparison);
    }
  });
  return inferred;
}

function rawBenchFingerprint(bench: RawBench): string | null {
  return roundedFingerprint(bench.bench_height, bench.face_angle, bench.berm_width);
}

function comparisonFingerprint(comparison: ComparisonResultDto): string | null {
  return roundedFingerprint(comparison.height_real, comparison.angle_real, comparison.berm_real);
}

function roundedFingerprint(height: number | null, angle: number | null, berm: number | null): string | null {
  if (height == null || !Number.isFinite(height) || angle == null || !Number.isFinite(angle)
    || berm == null || !Number.isFinite(berm)) return null;
  return `${height.toFixed(2)}|${angle.toFixed(1)}|${berm.toFixed(2)}`;
}

// ─── Top-level view model ───────────────────────────────────

export function toProfileViewModel(
  profile: ProfileDataDto,
  section: SectionResponseDto,
  comparisons: readonly ComparisonResultDto[] | null | undefined,
): ProfileViewModel {
  return {
    section: toSectionMeta(section),
    lines: toProfileLines(profile),
    horizontalDeviation: profile.horizontal_deviation ?? null,
    benches: toBenches(profile.benches_topo ?? null, profile.section_name, comparisons),
    comparisonBenchStatuses: toComparisonBenchStatuses(comparisons, profile.section_name),
    profileWarnings: {
      design: profile.profile_warnings?.design ?? [],
      topo: profile.profile_warnings?.topo ?? [],
    } satisfies ProfileWarnings,
    floorElevation: profile.floor_elevation ?? null,
    crestElevationMax: profile.crest_elevation_max ?? null,
  };
}
