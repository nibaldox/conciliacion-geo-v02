import type { ComparisonResult } from '../../../api/types';

export interface DefinedSectionRef {
  readonly id: string;
  readonly name: string;
}

export interface DashboardCoverage {
  readonly totalSectionsDefined: number;
  readonly evaluatedSections: number;
  readonly evaluatedFilteredSections: number;
  readonly missingSections: readonly string[];
  readonly totalRows: number;
  readonly designBenches: number;
  readonly comparedBenches: number;
  readonly evaluableCompleteBenches: number;
  readonly notBuiltBenches: number;
  readonly extraBenches: number;
  readonly truncatedStateBenches: number;
  readonly notExcavatedStateBenches: number;
  readonly unmeasuredStateBenches: number;
  readonly truncatedBermDesignCount: number;
  readonly truncatedBermDesignPct: number;
  readonly bermZeroRealCount: number;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isTruncatedBermDesign(row: ComparisonResult, defaultBermMin: number): boolean {
  const minThreshold = isFiniteNumber(row.berm_min) ? row.berm_min : defaultBermMin;
  return isFiniteNumber(row.berm_design) && row.berm_design < minThreshold;
}

function collectUniqueSections(rows: readonly ComparisonResult[]): Set<string> {
  const sections = new Set<string>();
  for (const row of rows) {
    if (typeof row.section === 'string' && row.section.length > 0) {
      sections.add(row.section);
    }
  }
  return sections;
}

export function computeDashboardCoverage(
  filteredRows: readonly ComparisonResult[],
  allRows: readonly ComparisonResult[],
  definedSections: readonly DefinedSectionRef[] | undefined,
  defaultBermMin: number,
): DashboardCoverage {
  const evaluatedSectionSet = collectUniqueSections(allRows);
  const filteredSectionSet = collectUniqueSections(filteredRows);

  const evaluatedSections = evaluatedSectionSet.size;
  const evaluatedFilteredSections = filteredSectionSet.size;

  const hasDefinedSections = Array.isArray(definedSections) && definedSections.length > 0;
  const totalSectionsDefined = hasDefinedSections ? definedSections.length : evaluatedSections;

  const missingSectionSet = new Set<string>();
  if (hasDefinedSections) {
    for (const section of definedSections) {
      if (typeof section.name === 'string' && section.name.length > 0 && !evaluatedSectionSet.has(section.name)) {
        missingSectionSet.add(section.name);
      }
    }
  }
  const missingSections = Array.from(missingSectionSet).sort();

  let comparedBenches = 0;
  let notBuiltBenches = 0;
  let extraBenches = 0;
  let truncatedStateBenches = 0;
  let notExcavatedStateBenches = 0;
  let unmeasuredStateBenches = 0;
  let truncatedBermDesignCount = 0;
  let bermZeroRealCount = 0;

  let hasProposedEvaluable = false;
  let hasDesignBenchState = false;

  for (const row of filteredRows) {
    if (row.type === 'MATCH') {
      comparedBenches++;
      if (isTruncatedBermDesign(row, defaultBermMin)) {
        truncatedBermDesignCount++;
      }
      if (row.berm_real === 0) {
        bermZeroRealCount++;
      }
    } else if (row.type === 'MISSING') {
      notBuiltBenches++;
    } else if (row.type === 'EXTRA') {
      extraBenches++;
    }

    if (row.design_bench_state === 'section_truncated') {
      truncatedStateBenches++;
    } else if (row.design_bench_state === 'not_excavated') {
      notExcavatedStateBenches++;
    } else if (row.design_bench_state === 'unmeasured') {
      unmeasuredStateBenches++;
    }

    if (typeof row.proposed_evaluable === 'boolean') {
      hasProposedEvaluable = true;
    }
    if (typeof row.design_bench_state === 'string' && row.design_bench_state.length > 0) {
      hasDesignBenchState = true;
    }
  }

  let evaluableCompleteBenches = 0;
  if (hasProposedEvaluable) {
    for (const row of filteredRows) {
      if (row.type !== 'EXTRA' && row.proposed_evaluable === true) {
        evaluableCompleteBenches++;
      }
    }
  } else if (hasDesignBenchState) {
    for (const row of filteredRows) {
      if (row.type !== 'EXTRA' && row.design_bench_state === 'excavated') {
        evaluableCompleteBenches++;
      }
    }
  } else {
    evaluableCompleteBenches = comparedBenches - truncatedBermDesignCount;
  }

  const totalRows = filteredRows.length;
  const designBenches = comparedBenches + notBuiltBenches;
  const truncatedBermDesignPct = comparedBenches === 0 ? 0 : (truncatedBermDesignCount / comparedBenches) * 100;

  return {
    totalSectionsDefined,
    evaluatedSections,
    evaluatedFilteredSections,
    missingSections,
    totalRows,
    designBenches,
    comparedBenches,
    evaluableCompleteBenches,
    notBuiltBenches,
    extraBenches,
    truncatedStateBenches,
    notExcavatedStateBenches,
    unmeasuredStateBenches,
    truncatedBermDesignCount,
    truncatedBermDesignPct,
    bermZeroRealCount,
  };
}
