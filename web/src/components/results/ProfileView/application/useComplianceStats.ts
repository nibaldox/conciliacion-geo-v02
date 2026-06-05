/**
 * useComplianceStats — derived from the full bench list (before
 * filters). The summary card should reflect the section's overall
 * health, not the filtered view.
 */

import { useMemo } from 'react';
import type { Bench } from '../domain/types';
import { computeCompliance } from '../domain/compliance';

export function useComplianceStats(benches: readonly Bench[]) {
  return useMemo(() => computeCompliance(benches), [benches]);
}
