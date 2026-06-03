import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from './client';
import { useSession, DEMO_MESH_IDS } from '../stores/session';
import type {
  MeshInfo,
  UploadResponse,
  SectionResponse,
  SectionAutoParams,
  SectionCreate,
  SectionClickParams,
  ProfileData,
  ComparisonResult,
  ProcessStatus,
  ProcessSettings,
  Tolerances,
  BenchParams,
  SettingsResponse,
  VerticesResponse,
  ContourData,
} from './types';

// ─── Demo data helpers ──────────────────────────────────────
//
// When the session is in demo mode (set by useSession().loadDemo()),
// the data hooks below short-circuit and return precomputed synthetic
// data from the in-memory DemoData payload — no API calls are made.
// This is what makes the "Try demo" button work end-to-end on
// GitHub Pages with no backend running.


function isDemoMeshId(meshId: string | null | undefined): boolean {
  return meshId === DEMO_MESH_IDS.design || meshId === DEMO_MESH_IDS.topo;
}


// ─── Meshes ────────────────────────────────────────────────

export function useMeshInfo(meshId: string | null) {
  const { demoMode, demoData } = useSession();
  return useQuery({
    queryKey: ['mesh', meshId, demoMode],
    queryFn: async () => {
      if (demoMode && demoData && isDemoMeshId(meshId)) {
        const kind = meshId === DEMO_MESH_IDS.design ? 'design' : 'topo';
        const v = demoData.vertices[kind];
        // Compute bounds from the (x, y, z) arrays we already have.
        const xs = v.x, ys = v.y, zs = v.z;
        return {
          id: meshId!,
          type: kind,
          n_vertices: xs.length,
          n_faces: 0,
          bounds: {
            min_x: Math.min(...xs), max_x: Math.max(...xs),
            min_y: Math.min(...ys), max_y: Math.max(...ys),
            min_z: Math.min(...zs), max_z: Math.max(...zs),
          },
          filename: kind === 'design' ? 'demo-design.stl' : 'demo-topo.stl',
          uploaded_at: new Date().toISOString(),
        } satisfies MeshInfo;
      }
      return client.get<MeshInfo>(`/meshes/${meshId}/info`).then(r => r.data);
    },
    enabled: !!meshId,
  });
}

export function useUploadMesh() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, type }: { file: File; type: 'design' | 'topo' }): Promise<UploadResponse> => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('type', type);
      return client.post('/meshes/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(r => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meshes'] });
    },
  });
}

export function useMeshVertices(meshId: string | null, _step = 8000) {
  const { demoMode, demoData } = useSession();
  return useQuery({
    queryKey: ['mesh-vertices', meshId, demoMode],
    queryFn: async () => {
      if (demoMode && demoData && isDemoMeshId(meshId)) {
        const kind = meshId === DEMO_MESH_IDS.design ? 'design' : 'topo';
        return demoData.vertices[kind] satisfies VerticesResponse;
      }
      return client
        .get<VerticesResponse>(`/meshes/${meshId}/vertices`, { params: { step: _step } })
        .then(r => r.data);
    },
    enabled: !!meshId,
  });
}

export function useDeleteMesh() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (meshId: string) => client.delete(`/meshes/${meshId}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meshes'] }),
  });
}

export function useMeshContours(meshId: string | null, interval = 15.0) {
  return useQuery({
    queryKey: ['mesh-contours', meshId, interval],
    queryFn: () => client.get<ContourData>(`/meshes/${meshId}/contours`, { params: { interval } }).then(r => r.data),
    enabled: !!meshId,
  });
}

// ─── Sections ──────────────────────────────────────────────

export function useSections() {
  const { demoMode, demoData } = useSession();
  return useQuery({
    queryKey: ['sections', demoMode],
    queryFn: async () => {
      if (demoMode && demoData) {
        return demoData.sections.map((s, i) => ({
          id: String(i),
          name: s.section_name,
          origin: s.origin,
          azimuth: s.azimuth,
          length: 400,            // matches the synthetic generator
          sector: s.sector,
        })) satisfies SectionResponse[];
      }
      return client.get<SectionResponse[]>('/sections').then(r => r.data);
    },
  });
}

export function useAutoSections() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: SectionAutoParams) =>
      client.post<{ sections: SectionResponse[] }>('/sections/auto', params).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

export function useManualSections() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sections: SectionCreate[]) =>
      client.post<{ sections: SectionResponse[] }>('/sections/manual', sections).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

export function useClickSection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: SectionClickParams) =>
      client.post<{ section: SectionResponse; total: number }>('/sections/click', params).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

export function useFileSections() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, ...params }: { file: File; spacing: number; length: number; sector: string; az_mode: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      Object.entries(params).forEach(([k, v]) => fd.append(k, String(v)));
      return client.post('/sections/from-file', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(r => r.data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

export function useUpdateSection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & SectionCreate) =>
      client.put(`/sections/${id}`, data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

export function useDeleteSection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.delete(`/sections/${id}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

export function useClearSections() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => client.delete('/sections').then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sections'] }),
  });
}

// ─── Process ───────────────────────────────────────────────

export function useProcess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (settings: ProcessSettings & { tolerances?: Tolerances }) =>
      client.post('/process', settings).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['process-status'] });
      qc.invalidateQueries({ queryKey: ['results'] });
    },
  });
}

export function useProcessStatus() {
  return useQuery<ProcessStatus>({
    queryKey: ['process-status'],
    queryFn: () => client.get<ProcessStatus>('/process/status').then(r => r.data),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === 'processing' ? 1000 : false;
    },
  });
}

export function useProfile(sectionId: string | null) {
  const { demoMode, demoData } = useSession();
  return useQuery({
    queryKey: ['profile', sectionId, demoMode],
    queryFn: async () => {
      if (demoMode && demoData && sectionId !== null) {
        const idx = parseInt(sectionId, 10);
        const sec = demoData.sections[idx];
        if (!sec) throw new Error(`Demo section ${sectionId} not found`);
        return {
          section_name: sec.section_name,
          sector: sec.sector,
          origin: sec.origin,
          azimuth: sec.azimuth,
          design: sec.design_profile,
          topo: sec.topo_profile,
          reconciled_design: null,
          reconciled_topo: sec.reconciled_topo,
          benches_topo: sec.benches_topo,
        } satisfies ProfileData;
      }
      return client
        .get<ProfileData>(`/process/profiles/${sectionId}`)
        .then(r => r.data);
    },
    enabled: sectionId !== null,
  });
}

export function useUpdateReconciled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sectionId, benches }: { sectionId: string; benches: BenchParams[] }) =>
      client.put(`/process/results/${sectionId}/reconciled`, benches).then(r => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['profile', vars.sectionId] });
      qc.invalidateQueries({ queryKey: ['results'] });
    },
  });
}

// ─── Results ───────────────────────────────────────────────

export function useResults(section?: string) {
  const { demoMode, demoData } = useSession();
  return useQuery({
    queryKey: ['results', section, demoMode],
    queryFn: async () => {
      if (demoMode && demoData) {
        const rows = demoData.comparisons;
        return section ? rows.filter(r => r.section === section) : rows;
      }
      return client
        .get<ComparisonResult[]>('/process/results', {
          params: section ? { section } : {},
        })
        .then(r => r.data);
    },
  });
}

// ─── Export ────────────────────────────────────────────────

export function useExportExcel() {
  return useMutation({
    mutationFn: (params?: { project?: string; author?: string; operation?: string; phase?: string }) =>
      client.get('/export/excel', { params, responseType: 'blob' }).then(r => {
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Conciliacion_Geotecnica.xlsx';
        a.click();
        URL.revokeObjectURL(url);
      }),
  });
}

export function useExportWord() {
  return useMutation({
    mutationFn: (params?: { project?: string; author?: string; operation?: string; phase?: string }) =>
      client.get('/export/word', { params, responseType: 'blob' }).then(r => {
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Reporte_Geotecnico.docx';
        a.click();
        URL.revokeObjectURL(url);
      }),
  });
}

export function useExportDxf() {
  return useMutation({
    mutationFn: () =>
      client.get('/export/dxf', { responseType: 'blob' }).then(r => {
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Perfiles_3D.dxf';
        a.click();
        URL.revokeObjectURL(url);
      }),
  });
}

export function useExportImages() {
  return useMutation({
    mutationFn: () =>
      client.get('/export/images', { responseType: 'blob' }).then(r => {
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Secciones_Imagenes.zip';
        a.click();
        URL.revokeObjectURL(url);
      }),
  });
}

// ─── Settings ──────────────────────────────────────────────

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => client.get<SettingsResponse>('/settings').then(r => r.data),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (settings: SettingsResponse) =>
      client.put('/settings', settings).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });
}

// ─── AI ────────────────────────────────────────────────────

export interface AIProviderInfo {
  available: boolean;
  provider: string;
  models?: string[];
  base_url?: string;
  error?: string;
}

export interface AIProvidersResponse {
  providers: Record<string, AIProviderInfo>;
  default_provider: string;
}

export function useAIProviders() {
  return useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => client.get<AIProvidersResponse>('/ai/providers').then(r => r.data),
    staleTime: 60_000, // Check every minute
  });
}

export function useAIModels(provider: string | null) {
  return useQuery({
    queryKey: ['ai-models', provider],
    queryFn: () => client.get<{ provider: string; models: string[] }>(`/ai/models/${provider}`).then(r => r.data),
    enabled: !!provider,
    staleTime: 60_000,
  });
}
