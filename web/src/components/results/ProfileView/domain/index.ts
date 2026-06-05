/**
 * Barrel export for the ProfileView domain layer.
 *
 * The presentation layer (and tests) import from `@/.../domain`
 * never from individual files. Adding a new domain module? Add it
 * to this barrel.
 */

export type {
  ProfilePoint,
  ProfileLine,
  Bench,
  BenchStatus,
  SectionMeta,
  ProfileViewModel,
  ProfileDataDto,
  SectionResponseDto,
  ComparisonResultDto,
  BenchParamsDto,
} from './types';

export { assertNever } from './types';

export {
  BACKEND_STATUS_STRINGS,
  STATUS_BG_VAR,
  STATUS_FG_VAR,
  STATUS_BORDER_VAR,
  STATUS_ICON,
  STATUS_PRESENTATION_ORDER,
  STATUS_SEVERITY,
  isBackendStatusString,
  parseBenchStatus,
  worstOfThree,
  compareStatus,
  forEachStatus,
  formatStatus,
} from './status';
export type { BackendStatusString } from './status';

export {
  DEFAULT_FILTER_STATE,
  ALL_STATUSES_FOR_FILTER,
  isFilterActive,
  applyFilters,
  toggleStatus,
  compareByStatusSeverity,
} from './filters';
export type { FilterState } from './filters';

export {
  SORT_FIELDS,
  DEFAULT_SORT,
  comparator,
  applySort,
  cycleSort,
} from './sorting';
export type { SortField, SortDirection } from './sorting';

export {
  computeCompliance,
  describeCompliance,
  iterateCounts,
} from './compliance';
export type { ComplianceStats } from './compliance';

export {
  toSectionMeta,
  toProfileLines,
  toBench,
  toBenches,
  toProfileViewModel,
} from './mapping';
