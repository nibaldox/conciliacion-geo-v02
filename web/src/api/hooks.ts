import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from './client';
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
} from './types';

// ─── Meshes ────────────────────────────────────────────────

export function useMeshInfo(meshId: string | null) {
  return useQuery({
    queryKey: ['mesh', meshId],
    queryFn: () => client.get<MeshInfo>(`/meshes/${meshId}/info`).then(r => r.data),
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

export function useMeshVertices(meshId: string | null, step = 8000) {
  return useQuery({
    queryKey: ['mesh-vertices', meshId, step],
    queryFn: () => client.get<VerticesResponse>(`/meshes/${meshId}/vertices`, { params: { step } }).then(r => r.data),
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

// ─── Sections ──────────────────────────────────────────────

export function useSections() {
  return useQuery({
    queryKey: ['sections'],
    queryFn: () => client.get<SectionResponse[]>('/sections').then(r => r.data),
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
  return useQuery({
    queryKey: ['profile', sectionId],
    queryFn: () => client.get<ProfileData>(`/process/profiles/${sectionId}`).then(r => r.data),
    enabled: !!sectionId,
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
  return useQuery({
    queryKey: ['results', section],
    queryFn: () => client.get<ComparisonResult[]>('/process/results', { params: section ? { section } : {} }).then(r => r.data),
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
