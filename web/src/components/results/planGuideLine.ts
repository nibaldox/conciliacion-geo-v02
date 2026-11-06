import type { GuideCurve } from '../../stores/session';

export function selectGuideLine(guide: GuideCurve | null | undefined): [number, number][] {
  return (guide?.points ?? []).map(([x, y]) => [x, y]);
}
