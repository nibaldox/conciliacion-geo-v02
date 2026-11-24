import type { ComparisonResult } from '../../../api/types';
import { BENCH_PASSING_SCORE, resolveBenchScore } from '../ProfileView/domain/status';
import { parameterTone } from './dashboardSelectors';

export interface DirectionalStats {
  berm: {
    compared: number;
    passCount: number;
    passPct: number;
    validDesignCount: number;
    validDesignPassPct: number | null;
    meanDeficitVsDesign: number | null;
    belowMinCount: number;
    below5mCount: number;
    effectiveEvaluated: number;
    effectivePassCount: number;
    effectivePassPct: number | null;
  };
  crest: {
    count: number;
    mean: number | null;
    median: number | null;
    gt1mCount: number;
    gt3mCount: number;
  };
  angle: {
    count: number;
    median: number | null;
    flatterCount: number;
    steeperCount: number;
  };
  height: {
    count: number;
    median: number | null;
    overTolCount: number;
    underTolCount: number;
  };
  toe: {
    count: number;
    median: number | null;
  };
}

export interface LevelComplianceRow {
  level: string;
  compared: number;
  notBuilt: number;
  extra: number;
  meanScore: number | null;
  heightPassPct: number | null;
  anglePassPct: number | null;
  bermPassPct: number | null;
  smallSample: boolean;
}

export type PriorityReasonCode = 'effective_berm' | 'berm_below_min' | 'crest_loss' | 'low_score';

export interface PriorityReviewItem {
  section: string;
  sectionId: string | null;
  benchNum: number;
  level: string;
  score: number | null;
  bermReal: number | null;
  bermDesign: number | null;
  effectiveBerm: number | null;
  deltaCrest: number | null;
  bermMin: number | null;
  severity: number;
  reasons: readonly PriorityReasonCode[];
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function computeMean(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function normalizeLevel(row: ComparisonResult): string {
  const nominal = row.level_nominal?.trim();
  if (nominal) return nominal;
  return (row.level ?? '').trim();
}

function parseElevation(level: string): number | null {
  if (level.length === 0) return null;
  const parsed = Number(level);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeEffectiveBermStatus(raw: string | null | undefined): string {
  return raw?.trim().toUpperCase() ?? '';
}

function isEvaluatedEffectiveBermStatus(normalized: string): boolean {
  return normalized !== '' && normalized !== '-';
}

export function computeMedian(values: readonly number[]): number | null {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return null;
  const sorted = [...finite].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function computeDirectionalStats(
  rows: readonly ComparisonResult[],
  tolerances: { heightPos: number; heightNeg: number; bermMin: number },
): DirectionalStats {
  const matchRows = rows.filter((row) => row.type === 'MATCH');

  let bermCompared = 0;
  let bermPassCount = 0;
  let validDesignCount = 0;
  let validDesignEvaluated = 0;
  let validDesignPassCount = 0;
  const deficitsVsDesign: number[] = [];
  let belowMinCount = 0;
  let below5mCount = 0;
  let effectiveEvaluated = 0;
  let effectivePassCount = 0;

  const crestValues: number[] = [];
  let gt1mCount = 0;
  let gt3mCount = 0;

  const angleValues: number[] = [];
  let flatterCount = 0;
  let steeperCount = 0;

  const heightValues: number[] = [];
  let overTolCount = 0;
  let underTolCount = 0;
  const negHeightLimit = -Math.abs(tolerances.heightNeg);

  const toeValues: number[] = [];

  for (const row of matchRows) {
    const minThreshold = isFiniteNumber(row.berm_min) ? row.berm_min : tolerances.bermMin;
    const bermTone = parameterTone(row.berm_status);
    if (bermTone !== 'unknown') {
      bermCompared += 1;
      if (bermTone === 'ok') {
        bermPassCount += 1;
      }
    }

    if (isFiniteNumber(row.berm_design) && row.berm_design >= minThreshold) {
      validDesignCount += 1;
      if (bermTone !== 'unknown') {
        validDesignEvaluated += 1;
        if (bermTone === 'ok') {
          validDesignPassCount += 1;
        }
      }
      if (isFiniteNumber(row.berm_real)) {
        deficitsVsDesign.push(row.berm_real - row.berm_design);
        if (row.berm_real < minThreshold) {
          belowMinCount += 1;
        }
        if (row.berm_real < 5) {
          below5mCount += 1;
        }
      }
    }

    const effStatus = normalizeEffectiveBermStatus(row.effective_berm_status);
    if (isEvaluatedEffectiveBermStatus(effStatus)) {
      effectiveEvaluated += 1;
      if (effStatus === 'CUMPLE') {
        effectivePassCount += 1;
      }
    }

    if (isFiniteNumber(row.delta_crest)) {
      crestValues.push(row.delta_crest);
      if (row.delta_crest > 1) gt1mCount += 1;
      if (row.delta_crest > 3) gt3mCount += 1;
    }

    if (isFiniteNumber(row.angle_dev)) {
      angleValues.push(row.angle_dev);
      if (row.angle_dev < 0) flatterCount += 1;
      if (row.angle_dev > 0) steeperCount += 1;
    }

    if (isFiniteNumber(row.height_dev)) {
      heightValues.push(row.height_dev);
      if (row.height_dev > tolerances.heightPos) overTolCount += 1;
      if (row.height_dev < negHeightLimit) underTolCount += 1;
    }

    if (isFiniteNumber(row.delta_toe)) {
      toeValues.push(row.delta_toe);
    }
  }

  return {
    berm: {
      compared: bermCompared,
      passCount: bermPassCount,
      passPct: bermCompared > 0 ? (100 * bermPassCount) / bermCompared : 0,
      validDesignCount,
      validDesignPassPct:
        validDesignEvaluated > 0 ? (100 * validDesignPassCount) / validDesignEvaluated : null,
      meanDeficitVsDesign: computeMean(deficitsVsDesign),
      belowMinCount,
      below5mCount,
      effectiveEvaluated,
      effectivePassCount,
      effectivePassPct:
        effectiveEvaluated > 0 ? (100 * effectivePassCount) / effectiveEvaluated : null,
    },
    crest: {
      count: crestValues.length,
      mean: computeMean(crestValues),
      median: computeMedian(crestValues),
      gt1mCount,
      gt3mCount,
    },
    angle: {
      count: angleValues.length,
      median: computeMedian(angleValues),
      flatterCount,
      steeperCount,
    },
    height: {
      count: heightValues.length,
      median: computeMedian(heightValues),
      overTolCount,
      underTolCount,
    },
    toe: {
      count: toeValues.length,
      median: computeMedian(toeValues),
    },
  };
}

export function computeLevelCompliance(
  rows: readonly ComparisonResult[],
): LevelComplianceRow[] {
  interface LevelAccumulator {
    compared: number;
    notBuilt: number;
    extra: number;
    scores: number[];
    heightEval: number;
    heightPass: number;
    angleEval: number;
    anglePass: number;
    bermEval: number;
    bermPass: number;
  }

  const groups = new Map<string, LevelAccumulator>();

  for (const row of rows) {
    const level = normalizeLevel(row);
    let acc = groups.get(level);
    if (!acc) {
      acc = {
        compared: 0,
        notBuilt: 0,
        extra: 0,
        scores: [],
        heightEval: 0,
        heightPass: 0,
        angleEval: 0,
        anglePass: 0,
        bermEval: 0,
        bermPass: 0,
      };
      groups.set(level, acc);
    }

    if (row.type === 'MISSING') {
      acc.notBuilt += 1;
      continue;
    }
    if (row.type === 'EXTRA') {
      acc.extra += 1;
      continue;
    }

    acc.compared += 1;
    const score = resolveBenchScore(row);
    if (score !== null) {
      acc.scores.push(score);
    }

    const hTone = parameterTone(row.height_status);
    if (hTone !== 'unknown') {
      acc.heightEval += 1;
      if (hTone === 'ok') acc.heightPass += 1;
    }

    const aTone = parameterTone(row.angle_status);
    if (aTone !== 'unknown') {
      acc.angleEval += 1;
      if (aTone === 'ok') acc.anglePass += 1;
    }

    const bTone = parameterTone(row.berm_status);
    if (bTone !== 'unknown') {
      acc.bermEval += 1;
      if (bTone === 'ok') acc.bermPass += 1;
    }
  }

  const result: LevelComplianceRow[] = [];
  for (const [level, acc] of groups.entries()) {
    result.push({
      level,
      compared: acc.compared,
      notBuilt: acc.notBuilt,
      extra: acc.extra,
      meanScore: computeMean(acc.scores),
      heightPassPct: acc.heightEval > 0 ? (100 * acc.heightPass) / acc.heightEval : null,
      anglePassPct: acc.angleEval > 0 ? (100 * acc.anglePass) / acc.angleEval : null,
      bermPassPct: acc.bermEval > 0 ? (100 * acc.bermPass) / acc.bermEval : null,
      smallSample: acc.compared < 5,
    });
  }

  result.sort((a, b) => {
    const elevA = parseElevation(a.level);
    const elevB = parseElevation(b.level);
    if (elevA !== null && elevB !== null) {
      if (elevA !== elevB) return elevB - elevA;
      return a.level.localeCompare(b.level);
    }
    if (elevA !== null) return -1;
    if (elevB !== null) return 1;
    if (a.level === '' && b.level !== '') return 1;
    if (a.level !== '' && b.level === '') return -1;
    return a.level.localeCompare(b.level);
  });

  return result;
}

export function computePriorityReviewList(
  rows: readonly ComparisonResult[],
  sections: readonly { id: string; name: string }[] | undefined,
  defaultBermMin: number,
  limit = 8,
): PriorityReviewItem[] {
  const sectionIdByName = new Map<string, string | null>();
  if (sections) {
    for (const sec of sections) {
      if (sectionIdByName.has(sec.name)) {
        sectionIdByName.set(sec.name, null);
      } else {
        sectionIdByName.set(sec.name, sec.id);
      }
    }
  }

  const items: PriorityReviewItem[] = [];

  for (const row of rows) {
    if (row.type !== 'MATCH') continue;

    const minThreshold = isFiniteNumber(row.berm_min) ? row.berm_min : defaultBermMin;
    const bermDesign = isFiniteNumber(row.berm_design) ? row.berm_design : null;
    const bermReal = isFiniteNumber(row.berm_real) ? row.berm_real : null;
    const effectiveBerm = isFiniteNumber(row.effective_berm) ? row.effective_berm : null;
    const deltaCrest = isFiniteNumber(row.delta_crest) ? row.delta_crest : null;
    const bermMin = isFiniteNumber(row.berm_min) ? row.berm_min : null;
    const score = resolveBenchScore(row);

    const isTruncatedBerm = bermDesign !== null && bermDesign < minThreshold;

    const effStatus = normalizeEffectiveBermStatus(row.effective_berm_status);
    const hasEffStatus = isEvaluatedEffectiveBermStatus(effStatus);
    const hasEffectiveBermDefect = hasEffStatus
      ? effStatus !== 'CUMPLE'
      : effectiveBerm !== null && effectiveBerm < minThreshold;

    const bermTone = parameterTone(row.berm_status);
    const hasBermBelowMin =
      (bermReal !== null && bermReal < minThreshold) ||
      bermTone === 'nok' ||
      bermTone === 'warn';

    const hasCrestLoss = deltaCrest !== null && deltaCrest > 3;
    const hasLowScore = score !== null && score < BENCH_PASSING_SCORE;

    const reasons: PriorityReasonCode[] = [];
    if (hasEffectiveBermDefect) reasons.push('effective_berm');
    if (hasBermBelowMin) reasons.push('berm_below_min');
    if (hasCrestLoss) reasons.push('crest_loss');
    if (hasLowScore) reasons.push('low_score');

    if (reasons.length === 0) continue;

    let rawSeverity = 0;

    if (hasEffectiveBermDefect) {
      if (!isTruncatedBerm) {
        const deficit = effectiveBerm !== null ? Math.max(0, minThreshold - effectiveBerm) : 0;
        rawSeverity += 40 + Math.min(20, deficit * 2.5);
      } else {
        const deficit =
          effectiveBerm !== null && bermDesign !== null
            ? Math.max(0, bermDesign - effectiveBerm)
            : 0;
        rawSeverity += 8 + Math.min(4, deficit);
      }
    }

    if (hasBermBelowMin) {
      if (!isTruncatedBerm) {
        const deficit = bermReal !== null ? Math.max(0, minThreshold - bermReal) : 0;
        rawSeverity += 30 + Math.min(25, deficit * 3);
      } else {
        const deficit =
          bermReal !== null && bermDesign !== null ? Math.max(0, bermDesign - bermReal) : 0;
        rawSeverity += 6 + Math.min(4, deficit);
      }
    }

    if (hasCrestLoss && deltaCrest !== null) {
      rawSeverity += 22 + Math.min(18, (deltaCrest - 3) * 3);
    }

    if (hasLowScore && score !== null) {
      const scoreDeficitRatio = (BENCH_PASSING_SCORE - score) / BENCH_PASSING_SCORE;
      if (isTruncatedBerm && !hasCrestLoss) {
        rawSeverity += 3 + scoreDeficitRatio * 5;
      } else {
        rawSeverity += 10 + scoreDeficitRatio * 15;
      }
    }

    items.push({
      section: row.section,
      sectionId: sectionIdByName.get(row.section) ?? null,
      benchNum: row.bench_num,
      level: normalizeLevel(row),
      score,
      bermReal,
      bermDesign,
      effectiveBerm,
      deltaCrest,
      bermMin,
      severity: Math.round(rawSeverity * 100) / 100,
      reasons,
    });
  }

  items.sort((a, b) => {
    if (b.severity !== a.severity) return b.severity - a.severity;
    const scoreA = a.score ?? Number.POSITIVE_INFINITY;
    const scoreB = b.score ?? Number.POSITIVE_INFINITY;
    if (scoreA !== scoreB) return scoreA - scoreB;
    const sectionCmp = a.section.localeCompare(b.section);
    if (sectionCmp !== 0) return sectionCmp;
    return a.benchNum - b.benchNum;
  });

  return items.slice(0, Math.max(0, limit));
}
