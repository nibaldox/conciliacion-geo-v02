import { useQuery } from '@tanstack/react-query';
import client, { getSessionId } from '../../api/client';
import type { BlastHole3DAttributes, BlastResponseProvenance } from '../../api/types';
import type { BlastHole3DRecord } from './BlastHoleFilters';

export interface BlastHoles3DResponse extends BlastResponseProvenance {
  session_id: string;
  section_id: number | null;
  corridor_m: number | null;
  data_revision?: string | null;
  holes: (BlastHole3DRecord & { attributes: BlastHole3DAttributes })[];
  summary: {
    total_loaded: number;
    drawable: number;
    complete_geometry: number;
    collar_only: number;
    without_geometry: number;
    rejected: number;
  };
}

export function useBlastHoles3D(enabled: boolean, sectionId: number | null, sectionGeometry: string) {
  const sessionId = getSessionId();
  return useQuery({
    queryKey: ['blast-holes-3d', 'attributes-v3', sessionId, sectionId, sectionGeometry],
    queryFn: () => client.get<BlastHoles3DResponse>('/blast/holes/3d', {
      params: sectionId === null ? {} : { section_id: sectionId, corridor_m: 10 },
    }).then((response) => response.data),
    enabled: enabled && !!sessionId,
  });
}
