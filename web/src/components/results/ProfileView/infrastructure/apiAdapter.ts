/**
 * API adapter for the ProfileView feature.
 *
 * The ONLY file in the feature that imports from `web/src/api/hooks`.
 * Wraps the existing React Query hooks so the rest of the feature
 * depends on a stable, narrow interface (the view model DTOs) and
 * doesn't reach into global state or query keys directly.
 *
 * If we ever swap React Query for SWR, or change the API transport
 * (e.g. add a websocket), only this file changes.
 */

import { useQuery } from '@tanstack/react-query';
import { useProfile, useSections, useResults } from '../../../../api/hooks';
import { useSession } from '../../../../stores/session';
import type {
  ComparisonResultDto,
  ProfileDataDto,
  SectionResponseDto,
} from '../domain/types';

/**
 * Profile data for the currently selected section. Returns:
 *  - `data`: the raw `ProfileData` DTO, or `undefined` while loading
 *  - `isLoading`, `error`: standard React Query state
 *  - `sectionId`: the section id we queried for (so callers can
 *    cross-check it against `selectedSection` to detect staleness)
 */
export function useProfileQuery(selectedSectionId: string | null) {
  const query = useProfile(selectedSectionId);
  return {
    data: query.data as ProfileDataDto | undefined,
    isLoading: query.isLoading,
    error: query.error as Error | null,
    sectionId: selectedSectionId,
  };
}

/** All sections (used to resolve section meta + names). */
export function useSectionsQuery() {
  const query = useSections();
  return {
    data: (query.data ?? []) as readonly SectionResponseDto[],
    isLoading: query.isLoading,
    error: query.error as Error | null,
  };
}

/** Comparison results, optionally filtered to one section. */
export function useComparisonsQuery(sectionName: string | null) {
  const query = useResults(sectionName ?? undefined);
  return {
    data: (query.data ?? []) as readonly ComparisonResultDto[],
    isLoading: query.isLoading,
    error: query.error as Error | null,
  };
}

/**
 * Convenience selector: the meta of the currently selected section.
 * Returns `null` if the section isn't loaded yet, or if the id is stale.
 */
export function useSelectedSectionMeta(selectedSectionId: string | null) {
  const { data: sections, isLoading } = useSectionsQuery();
  const section = sections.find((s) => s.id === selectedSectionId);
  return { section: section ?? null, isLoading };
}

/** Debug: total mesh count for the current session (used by tests). */
export function useSessionMeshCount(): number {
  const { designMeshId, topoMeshId } = useSession();
  return (designMeshId ? 1 : 0) + (topoMeshId ? 1 : 0);
}

/** Re-export useQuery for atoms that need their own queries. */
export { useQuery };
