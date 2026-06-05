/**
 * useProfileViewModel — transforms API DTOs into the domain view
 * model. The only place in the feature that calls `toProfileViewModel`.
 *
 * Pure composition: query results in, view model out. No effects,
 * no state. Memoised by the inputs.
 */

import { useMemo } from 'react';
import type { ProfileViewModel } from '../domain/types';
import { toProfileViewModel } from '../domain/mapping';
import { useProfileQuery, useSectionsQuery, useComparisonsQuery } from '../infrastructure/apiAdapter';

export interface UseProfileViewModelResult {
  readonly viewModel: ProfileViewModel | null;
  readonly isLoading: boolean;
  readonly error: Error | null;
  /** True if any of the underlying queries is still fetching. */
  readonly isStale: boolean;
}

export function useProfileViewModel(
  selectedSectionId: string | null,
): UseProfileViewModelResult {
  const profileQuery = useProfileQuery(selectedSectionId);
  const sectionsQuery = useSectionsQuery();
  const comparisonsQuery = useComparisonsQuery(profileQuery.data?.section_name ?? null);

  const viewModel = useMemo<ProfileViewModel | null>(() => {
    if (!profileQuery.data) return null;
    const section = sectionsQuery.data.find((s) => s.name === profileQuery.data!.section_name);
    if (!section) return null;
    return toProfileViewModel(profileQuery.data, section, comparisonsQuery.data);
  }, [profileQuery.data, sectionsQuery.data, comparisonsQuery.data]);

  return {
    viewModel,
    isLoading:
      profileQuery.isLoading ||
      sectionsQuery.isLoading ||
      (!!profileQuery.data && comparisonsQuery.isLoading),
    error: profileQuery.error ?? sectionsQuery.error ?? comparisonsQuery.error,
    isStale: profileQuery.isLoading || sectionsQuery.isLoading,
  };
}
