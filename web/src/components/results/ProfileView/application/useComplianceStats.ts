/**
 * useComplianceStats — derives tolerance-tier counts from normalized
 * design-bank comparisons or, when absent, the available profile benches.
 */

import { useMemo } from 'react';
import type { Bench, BenchStatus } from '../domain/types';
import { computeCompliance, computeComplianceStatuses } from '../domain/compliance';

export function useComplianceStats(benches: readonly Bench[], statuses?: readonly BenchStatus[]) {
  return useMemo(() => statuses ? computeComplianceStatuses(statuses) : computeCompliance(benches), [benches, statuses]);
}
