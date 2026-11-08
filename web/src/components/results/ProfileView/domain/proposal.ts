import type { ComparisonResultDto, ProfileLine } from './types';
import type { ProposedComplianceResponse } from '../../../../api/types';

export type ProposalSource = 'current' | 'guided' | 'mixed';

export type ProposalMagnitudeSource = 'guided' | 'current';

export type ProposalBenchState =
  | 'excavated'
  | 'not_excavated'
  | 'section_truncated'
  | 'unmeasured'
  | 'split_bench'
  | 'split_fragment'
  | 'unknown';

export interface ProposalValuePair {
  readonly official: number | null;
  readonly proposed: number | null;
  readonly source?: ProposalMagnitudeSource | null;
}

export interface ProposalRow {
  readonly key: string;
  readonly section: string;
  readonly benchLabel: string;
  readonly isExtra: boolean;
  readonly benchNumTopo: number | null;
  readonly state: ProposalBenchState;
  readonly source: ProposalSource | null;
  readonly debtAreaM2: number | null;
  readonly height: ProposalValuePair;
  readonly angle: ProposalValuePair;
  readonly deltaCrest: ProposalValuePair;
  readonly deltaToe: ProposalValuePair;
  readonly berm: ProposalValuePair;
  readonly score: ProposalValuePair;
  readonly floorOffsetM: number | null;
  readonly floorStatus: string;
  readonly error: string | null;
}

export interface ProposalSessionNotice {
  readonly kind: 'current' | 'partial' | 'not_computed';
  readonly missingSections: readonly string[];
  readonly failedRows: number;
  readonly notComputedRows: number;
}

export interface ProposalDesignBench {
  readonly benchNumber: number;
  readonly crestDistance: number;
  readonly toeDistance: number;
  readonly toeElevation: number;
  readonly bermWidth: number | null;
}

export interface ProposalOverlayPoint {
  readonly x: number;
  readonly y: number;
}

export interface ProposalOverlaySegment {
  readonly x0: number;
  readonly x1: number;
  readonly elevation: number;
}

export interface ProposalOverlay {
  readonly toeMarkers: readonly ProposalOverlayPoint[];
  readonly floorSegments: readonly ProposalOverlaySegment[];
}

export interface ProposalProfileRange {
  readonly xMin: number;
  readonly xMax: number;
}

export const PROPOSAL_FLOOR_SPAN_M = 8;

export function toProposalProfileRange(
  lines: readonly ProfileLine[],
): ProposalProfileRange | null {
  let xMin = Number.POSITIVE_INFINITY;
  let xMax = Number.NEGATIVE_INFINITY;
  for (const line of lines) {
    for (const point of line.points) {
      if (!Number.isFinite(point.distance)) continue;
      if (point.distance < xMin) xMin = point.distance;
      if (point.distance > xMax) xMax = point.distance;
    }
  }
  return Number.isFinite(xMin) && Number.isFinite(xMax) ? { xMin, xMax } : null;
}

export function hasProposalData(
  rows: readonly ComparisonResultDto[] | null | undefined,
): boolean {
  if (!rows) return false;
  return rows.some((row) => row.proposed_source !== undefined || row.proposal_status !== undefined);
}

export function toProposalBenchState(row: ComparisonResultDto): ProposalBenchState {
  if (row.proposed_exclusion_reason === 'split_fragment') return 'split_fragment';
  if (row.split_bench === true) return 'split_bench';
  const reason = row.proposed_exclusion_reason;
  if (reason === 'not_excavated' || reason === 'section_truncated' || reason === 'unmeasured') {
    return reason;
  }
  const state = row.design_bench_state;
  if (
    state === 'excavated' || state === 'not_excavated'
    || state === 'section_truncated' || state === 'unmeasured'
  ) {
    return state;
  }
  return 'unknown';
}

function pairOf(
  official: number | null | undefined,
  proposed: number | null | undefined,
  source?: string | null,
): ProposalValuePair {
  const magnitudeSource: ProposalMagnitudeSource | null =
    source === 'guided' || source === 'current' ? source : null;
  return { official: official ?? null, proposed: proposed ?? null, source: magnitudeSource };
}

function toBenchLabel(row: ComparisonResultDto): string {
  if (row.type === 'EXTRA') return `+${row.bench_num_topo ?? '—'}`;
  return row.bench_num != null ? `B${row.bench_num}` : '—';
}

export function toProposalRow(row: ComparisonResultDto): ProposalRow {
  const source: ProposalSource | null =
    row.proposed_source === 'current' || row.proposed_source === 'guided' || row.proposed_source === 'mixed'
      ? row.proposed_source
      : null;
  return {
    key: `${row.section}|${row.type}|${row.bench_num}|${row.bench_num_topo ?? ''}`,
    section: row.section,
    benchLabel: toBenchLabel(row),
    isExtra: row.type === 'EXTRA',
    benchNumTopo: row.bench_num_topo ?? null,
    state: toProposalBenchState(row),
    source,
    debtAreaM2: row.excavation_debt_area_m2 ?? row.guided_excavation_debt_area_m2 ?? null,
    height: pairOf(row.height_real, row.proposed_height, row.proposed_height_source),
    angle: pairOf(row.angle_real, row.proposed_angle, row.proposed_angle_source),
    deltaCrest: pairOf(row.delta_crest, row.proposed_delta_crest, row.proposed_crest_source),
    deltaToe: pairOf(row.delta_toe, row.proposed_delta_toe, row.proposed_toe_source),
    berm: pairOf(row.berm_real, row.proposed_berm, row.proposed_berm_source),
    score: pairOf(row.bench_score ?? null, row.proposed_bench_score),
    floorOffsetM: row.floor_offset_m ?? row.guided_floor_offset_m ?? null,
    floorStatus: row.floor_status ?? '-',
    error: row.proposal_error ?? null,
  };
}

export function toProposalRows(
  rows: readonly ComparisonResultDto[] | null | undefined,
): readonly ProposalRow[] {
  return (rows ?? []).map(toProposalRow);
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

export type ProposalLang = 'es' | 'en';

function makeFmt(lang: ProposalLang, signed: boolean): Intl.NumberFormat {
  return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-AR', {
    maximumFractionDigits: 2,
    ...(signed ? { signDisplay: 'exceptZero' as const } : {}),
  });
}

export function formatProposalNumber(value: number | null, lang: ProposalLang = 'es'): string {
  if (!isFiniteNumber(value)) return '—';
  return makeFmt(lang, false).format(value);
}

const PROPOSAL_SOURCE_SUFFIXES: Record<ProposalMagnitudeSource, string> = {
  guided: ' (g)',
  current: ' (o)',
};

export function formatProposalPair(pair: ProposalValuePair, lang: ProposalLang = 'es'): string {
  const suffix = pair.source ? PROPOSAL_SOURCE_SUFFIXES[pair.source] : '';
  return `${formatProposalNumber(pair.official, lang)} → ${formatProposalNumber(pair.proposed, lang)}${suffix}`;
}

export function formatSignedMeters(value: number | null, lang: ProposalLang = 'es'): string {
  if (!isFiniteNumber(value)) return '—';
  if (value === 0) return '±0 m';
  return `${makeFmt(lang, true).format(value)} m`;
}

export function formatFloor(
  offset: number | null,
  status: string | null | undefined,
  lang: ProposalLang = 'es',
): string {
  if (!isFiniteNumber(offset)) return '—';
  const signed = formatSignedMeters(offset, lang);
  return status ? `${signed} · ${status}` : signed;
}

const FLOOR_STATUS_ORDER = ['CUMPLE', 'FUERA DE TOLERANCIA', 'NO CUMPLE', '-'] as const;

function pushFloorCount(
  out: { status: string; count: number }[],
  counts: Record<string, number>,
  status: string,
): void {
  const count = counts[status] ?? 0;
  if (count > 0) out.push({ status, count });
}

export function formatFloorStatusCounts(
  counts: Record<string, number>,
): { status: string; count: number }[] {
  const out: { status: string; count: number }[] = [];
  for (const status of FLOOR_STATUS_ORDER) {
    pushFloorCount(out, counts, status);
  }
  const known = new Set<string>(FLOOR_STATUS_ORDER);
  for (const status of Object.keys(counts).sort()) {
    if (!known.has(status)) pushFloorCount(out, counts, status);
  }
  return out;
}

export function toProposalSessionNotice(
  response: Pick<
    ProposedComplianceResponse,
    'proposal_status' | 'n_failed_rows' | 'n_not_computed_rows' | 'summary'
  > | null | undefined,
  allSections: readonly string[],
): ProposalSessionNotice {
  if (!response) {
    return { kind: 'not_computed', missingSections: allSections, failedRows: 0, notComputedRows: 0 };
  }
  const bySection = response.summary?.by_section ?? {};
  const missingSections = allSections.filter((section) => !(section in bySection));
  return {
    kind: response.proposal_status,
    missingSections,
    failedRows: response.n_failed_rows,
    notComputedRows: response.n_not_computed_rows,
  };
}

export function buildProposalOverlay(
  comparisons: readonly ComparisonResultDto[],
  designBenches: readonly ProposalDesignBench[],
  profileRange?: ProposalProfileRange | null,
): ProposalOverlay {
  const byNumber = new Map(designBenches.map((bench) => [bench.benchNumber, bench]));
  const rowsByNumber = new Map<number, ComparisonResultDto>();
  for (const row of comparisons) {
    if (row.type !== 'EXTRA') rowsByNumber.set(row.bench_num, row);
  }
  const toeMarkers: ProposalOverlayPoint[] = [];
  const floorSegments: ProposalOverlaySegment[] = [];

  for (const row of comparisons) {
    if (row.type === 'EXTRA') continue;
    const bench = byNumber.get(row.bench_num);
    if (!bench) continue;
    const sign = bench.crestDistance >= bench.toeDistance ? 1 : -1;

    const offset = row.floor_offset_m ?? row.guided_floor_offset_m;
    const floorElevation = isFiniteNumber(offset) ? bench.toeElevation + offset : null;

    const deltaToe = row.guided_delta_toe;
    const guidedToe = isFiniteNumber(deltaToe)
      ? bench.toeDistance + deltaToe * sign
      : bench.toeDistance;
    if (isFiniteNumber(deltaToe)) {
      toeMarkers.push({
        x: guidedToe,
        y: floorElevation ?? bench.toeElevation,
      });
    }
    if (floorElevation != null) {
      const span = isFiniteNumber(bench.bermWidth) ? bench.bermWidth : PROPOSAL_FLOOR_SPAN_M;
      let x1 = guidedToe - span * sign;
      let anchored = false;
      const lower = byNumber.get(bench.benchNumber + 1);
      if (lower) {
        const lowerSign = lower.crestDistance >= lower.toeDistance ? 1 : -1;
        let crest = lower.crestDistance;
        const deltaCrest = rowsByNumber.get(lower.benchNumber)?.guided_delta_crest;
        if (isFiniteNumber(deltaCrest)) crest += deltaCrest * lowerSign;
        if (sign > 0 ? crest < guidedToe : crest > guidedToe) {
          x1 = crest;
          anchored = true;
        }
      }
      if (!anchored && profileRange) {
        x1 = sign > 0 ? profileRange.xMin : profileRange.xMax;
      }
      if (profileRange) {
        floorSegments.push({
          x0: Math.min(Math.max(guidedToe, profileRange.xMin), profileRange.xMax),
          x1: Math.min(Math.max(x1, profileRange.xMin), profileRange.xMax),
          elevation: floorElevation,
        });
      } else {
        floorSegments.push({
          x0: guidedToe,
          x1,
          elevation: floorElevation,
        });
      }
    }
  }

  return { toeMarkers, floorSegments };
}
