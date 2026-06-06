// Presentation barrel — the React/UI layer.
// External callers should import from `@/components/results/ProfileView`
// (the feature index), not from this file directly.

export { FilterBar } from './FilterBar';
export type { FilterBarProps } from './FilterBar';

export { ProfileChart } from './ProfileChart';
export type { ProfileChartProps } from './ProfileChart';

export { SectionHeader } from './SectionHeader';
export type { SectionHeaderProps } from './SectionHeader';

export { SectionNavigator } from './SectionNavigator';
export type { SectionNavigatorProps } from './SectionNavigator';

export { BenchTable } from './BenchTable';
export type { BenchTableProps } from './BenchTable';

export { ComplianceSummary } from './ComplianceSummary';
export type { ComplianceSummaryProps } from './ComplianceSummary';

export { ProfileView } from './ProfileView';
export type { ProfileViewProps } from './ProfileView';

export { ProfilesGrid } from './ProfilesGrid';


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

// Spinner is shared with the rest of the app via ui/, not in
// our atoms. Re-export it from the feature index for callers
// that import from `@/.../ProfileView`.
export { Spinner } from '../../../ui/Spinner';
