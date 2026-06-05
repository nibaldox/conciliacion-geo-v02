// Presentation barrel — the React/UI layer.
// External callers should import from `@/components/results/ProfileView`
// (the feature index), not from this file directly.

export { FilterBar } from './FilterBar';
export type { FilterBarProps } from './FilterBar';

export { ProfileChart } from './ProfileChart';
export type { ProfileChartProps } from './ProfileChart';

// Atoms barrel (re-exported here so callers can `import { StatusPill }
// from '@/.../ProfileView/presentation'` if they want a single import)
export {
  StatusPill,
  FilterToggle,
  MetricValue,
  StatusDot,
} from './atoms';
export type {
  StatusPillProps,
  StatusPillSize,
  FilterToggleProps,
  MetricValueProps,
  MetricSize,
  StatusDotProps,
} from './atoms';
