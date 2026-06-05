/**
 * Public API for the ProfileView feature.
 *
 * Other parts of the app import from this file only:
 *   import { ProfileView } from '@/components/results/ProfileView';
 *
 * Anything not re-exported here is an implementation detail and can
 * be refactored without breaking callers.
 */

// Main component is added in Parada 3. For Parada 1, the feature
// is still under construction — export the foundation pieces so
// the test suite (and any early visual review) can import them.

// Domain — public so tests in other features can use the
// types/utilities.
export {
  type ProfileViewModel,
  type Bench,
  type BenchStatus,
  type FilterState,
  type SectionMeta,
  type SortField,
  type SortDirection,
  DEFAULT_FILTER_STATE,
  DEFAULT_SORT,
  STATUS_PRESENTATION_ORDER,
  STATUS_BG_VAR,
  STATUS_FG_VAR,
  STATUS_BORDER_VAR,
  STATUS_ICON,
  STATUS_SEVERITY,
  parseBenchStatus,
  worstOfThree,
  isFilterActive,
  toggleStatus,
  computeCompliance,
  describeCompliance,
  toProfileViewModel,
  applySort,
  comparator,
  cycleSort,
} from './domain';

// Application hooks
export {
  useFilterState,
  useCrossLinkState,
  useProfileViewModel,
  useFilteredBenches,
  useSortedBenches,
  useComplianceStats,
} from './application';

// Presentation atoms
export {
  StatusPill,
  FilterToggle,
  MetricValue,
  StatusDot,
} from './presentation/atoms';
