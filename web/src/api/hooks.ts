import { useQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import client, { getSessionId } from './client';
import { useSession, DEMO_MESH_IDS, type DemoData } from '../stores/session';
import type {
  MeshInfo,
  UploadResponse,
  SectionResponse,
  SectionAutoParams,
  SectionCreate,
  SectionClickParams, SectionCurveParams,
  ProfileData,
  ComparisonResult,
  ProcessStatus,
  ProcessSettings,
  Tolerances,
  BenchParams,
  SettingsResponse,
  SettingsUpdate,
  VerticesResponse,
  ContourData,
  ReferenceLineResponse,
  BlastHolesOnProfileResponse,
  BlastCorrelationResponse,
  BlastDamageModelResponse,
  BlastUploadResponse,
  BlastHolesResponse,
  AIGenerateRequest,
  AIResponseChunk,
  AIUsageMetrics,
  ColumnDetectRequest,
  ColumnDetectResponse,
  ColumnSchemaResponse,
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

// Loop-based min/max: Math.min(...xs) spread throws RangeError past
// ~100-150K elements, and real meshes routinely exceed that.
function safeMin(xs: number[]): number {
  let m = Infinity;
  for (const v of xs) if (v < m) m = v;
  return m;
}
function safeMax(xs: number[]): number {
  let m = -Infinity;
  for (const v of xs) if (v > m) m = v;
  return m;
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
            min_x: safeMin(xs), max_x: safeMax(xs),
            min_y: safeMin(ys), max_y: safeMax(ys),
            min_z: safeMin(zs), max_z: safeMax(zs),
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

export function useMeshVertices(meshId: string | null, _step = 150000) {
  const { demoMode, demoData } = useSession();
  return useQuery({
    queryKey: ['mesh-vertices', meshId, demoMode, _step],
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

export function useMeshContours(meshId: string | null, interval = 15.0, resolution = 1) {
  return useQuery({
    queryKey: ['mesh-contours', meshId, interval, resolution],
    queryFn: async () => {
      const data = await client
        .get<ContourData>(`/meshes/${meshId}/contours`, { params: { interval } })
        .then(r => r.data);
      if (resolution <= 1) return data;
      // Client-side decimation: the backend does not expose a resolution
      // parameter, so we stride the contour points by the chosen factor.
      return {
        ...data,
        lines: data.lines.map((line) => ({
          ...line,
          segments: line.segments.map((segment) => segment.filter((_, i) => i % resolution === 0)),
        })),
      };
    },
    enabled: !!meshId,
  });
}

/**
 * Fetch reference lines (drilling/blast mesh boundaries) for the current session.
 *
 * TODO: backend endpoint `GET /api/v1/reference-lines?session_id=...` is not
 * implemented yet. The hook is stubbed to an empty response so the overlay
 * component can be built and tested now; once the endpoint exists, replace this
 * stub with a real `useQuery` call.
 */
export function useReferenceLines(_drillHardnessSessionId: string | null) {
  return {
    data: { lines: [] } satisfies ReferenceLineResponse,
    isLoading: false,
    error: null,
  };
}

export function useMeshBreaklines(meshId: string | null) {
  return useQuery({
    queryKey: ['mesh-breaklines', meshId],
    queryFn: () => client.get<ContourData>(`/meshes/${meshId}/breaklines`).then(r => r.data),
    enabled: !!meshId,
  });
}

// ─── Sections ──────────────────────────────────────────────

export function useSections() {
  const { demoMode, demoData, designMeshId } = useSession();
  return useQuery({
    queryKey: ['sections', demoMode, designMeshId],
    queryFn: async () => {
      // Only serve demo data if the active design mesh is actually a demo
      // mesh. If the user uploaded their own mesh while still in demo
      // mode (the flag stays sticky after loadDemo), we must hit the
      // backend so freshly generated profiles show up.
      if (demoMode && demoData && isDemoMeshId(designMeshId)) {
        return demoData.sections.map((s, i): SectionResponse => ({
          id: String(i),
          name: s.section_name,
          origin: s.origin as [number, number],
          azimuth: s.azimuth,
          length: 400,            // matches the synthetic generator
          sector: s.sector,
        }));
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
    mutationFn: ({ file, ...params }: { file: File; spacing: number; length: number; length_up?: number; length_down?: number; sector: string; az_mode: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) fd.append(k, String(v));
      });
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

export function setDemoProcessStatus(
  qc: QueryClient,
  summary?: { n_sections: number; n_comparisons: number },
): void {
  const total = summary?.n_sections ?? 0;
  qc.setQueryData<ProcessStatus>(['process-status'], {
    status: 'complete',
    current_section: null,
    total_sections: total,
    completed_sections: total,
    n_results: summary?.n_comparisons ?? 0,
  });
}

export function setDemoSectionsCache(
  qc: QueryClient,
  demoData: DemoData,
): void {
  const { demoMode, designMeshId } = useSession.getState();
  const sections: SectionResponse[] = demoData.sections.map((s, i) => ({
    id: String(i),
    name: s.section_name,
    origin: s.origin as [number, number],
    azimuth: s.azimuth,
    length: 400,
    sector: s.sector,
  }));
  qc.setQueryData<SectionResponse[]>(
    ['sections', demoMode, designMeshId],
    sections,
  );
}

export function setDemoComparisonsCache(
  qc: QueryClient,
  demoData: DemoData,
): void {
  const { demoMode, designMeshId } = useSession.getState();
  if (!demoData.comparisons) return;
  qc.setQueryData<ComparisonResult[]>(
    ['results', undefined, demoMode, designMeshId],
    demoData.comparisons,
  );
}

export function useProfile(sectionId: string | null) {
  const { demoMode, demoData, designMeshId } = useSession();
  return useQuery({
    queryKey: ['profile', sectionId, demoMode, designMeshId],
    queryFn: async () => {
      // Same demo guard as useSections: only use demo data if the active
      // design mesh is a demo mesh, otherwise always hit the backend so
      // profiles the user just generated become visible.
      if (demoMode && demoData && isDemoMeshId(designMeshId) && sectionId !== null) {
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

// ─── Blast holes (per-profile projection) ──────────────────

/**
 * Fetch the blast-hole markers projected onto a single section profile.
 *
 * Wraps `GET /process/profiles/{sectionId}/blast-holes?mesh_id=&tolerance=`.
 * The hook is gated by `enabled` so callers can tie it to
 * `filterState.showBlastHoles`; we keep the FilterState type out of this
 * module to avoid leaking the ProfileView domain into the API layer.
 *
 * Demo mode short-circuits to an empty hole list: the precomputed demo
 * payload has no blast-hole data, so we never hit the (non-existent on
 * GitHub Pages) backend.
 *
 * `staleTime` is 5 min so toggling the filter off/on does not refetch.
 */
export function useBlastHoles(
  sectionId: string | null,
  meshId: string | null,
  tolerance: number,
  enabled: boolean,
) {
  const { demoMode, demoData, designMeshId } = useSession();
  return useQuery({
    queryKey: ['blast-holes', sectionId, meshId, tolerance, demoMode, designMeshId],
    queryFn: async () => {
      if (demoMode && demoData && isDemoMeshId(designMeshId)) {
        return {
          section_id: sectionId ?? '',
          mesh_id: meshId ?? '',
          tolerance,
          holes: [],
        } satisfies BlastHolesOnProfileResponse;
      }
      return client
        .get<BlastHolesOnProfileResponse>(
          `/process/profiles/${sectionId}/blast-holes`,
          { params: { mesh_id: meshId ?? '', tolerance } },
        )
        .then(r => r.data);
    },
    enabled: enabled && sectionId !== null,
    staleTime: 5 * 60 * 1000,
  });
}

// ─── Results ───────────────────────────────────────────────

export function useResults(section?: string) {
  const { demoMode, demoData, designMeshId } = useSession();
  return useQuery({
    queryKey: ['results', section, demoMode, designMeshId],
    queryFn: async () => {
      // Same demo guard: only serve demo comparison rows if the active
      // design mesh is a demo mesh. Otherwise hit the backend so the
      // user sees comparison results they actually generated.
      if (demoMode && demoData && isDemoMeshId(designMeshId)) {
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

// ─── Blast-hole CSV upload ─────────────────────────────────

/**
 * Upload a blast-hole CSV to `POST /blast/upload`.
 *
 * The endpoint expects a multipart body with `file` and `session_id`.
 * On success it returns the upload summary including the number of
 * parsed holes, skipped rows, and mean charge/discharge metrics.
 */
export function useUploadBlastCsv() {
  return useMutation({
    mutationFn: async ({ sessionId, file }: { sessionId: string; file: File }) => {
      const form = new FormData();
      form.append('file', file);
      form.append('session_id', sessionId);
      const { data } = await client.post<BlastUploadResponse>('/blast/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
  });
}

/**
 * Fetch persisted blast-hole summaries for the session from
 * `GET /blast/{sessionId}/holes`. Optionally filters by `section_name`
 * when the backend supports it.
 *
 * Note: this hook is named `useBlastHolesBySession` because the legacy
 * `useBlastHoles` (per-profile projection) already exists in this file.
 */
export function useBlastHolesBySession(sessionId: string | null, sectionName?: string | null) {
  return useQuery({
    queryKey: ['blast-holes-by-session', sessionId, sectionName],
    queryFn: async () => {
      const { data } = await client.get<BlastHolesResponse>(
        `/blast/${sessionId}/holes`,
        { params: sectionName ? { section_name: sectionName } : {} },
      );
      return data;
    },
    enabled: !!sessionId,
  });
}

// ─── Blast correlation (per-section powder factor) ─────────

/**
 * Fetch per-section blast/powder-factor metrics from
 * `GET /process/blast-correlation`. The endpoint returns an empty
 * `{ rows: [] }` (HTTP 200) when the session has no wells loaded, so
 * callers must handle the empty-rows case in the UI.
 *
 * Demo mode short-circuits to an empty payload: the precomputed demo
 * bundle has no blast data, so we never hit the (non-existent on
 * GitHub Pages) backend. Mirrors the `useBlastHoles` demo guard.
 */
export function useBlastCorrelation() {
  const { demoMode, demoData, designMeshId } = useSession();
  return useQuery<BlastCorrelationResponse>({
    queryKey: ['blast-correlation', demoMode, designMeshId],
    queryFn: async () => {
      if (demoMode && demoData && isDemoMeshId(designMeshId)) {
        return {
          rows: [],
          tolerance: null,
          n_sections: demoData.sections.length,
          carga: [],
          descarga: [],
        } satisfies BlastCorrelationResponse;
      }
      return client
        .get<BlastCorrelationResponse>('/process/blast-correlation')
        .then((r) => r.data);
    },
  });
}

/**
 * Fetch the fitted PF↔damage regression model from
 * `GET /process/blast-correlation/damage-model`. Returns the scatter
 * points (one per section: PF g/ton, overbreak m) and the OLS fit summary
 * (or null when the fitter reported INSUFFICIENT confidence). The endpoint
 * always returns HTTP 200 — empty case is `{ points: [], fit: null }`.
 *
 * Demo mode short-circuits to an empty payload, mirroring `useBlastCorrelation`
 * (the demo bundle has no blast data, and the backend is not reachable on
 * GitHub Pages).
 */
export function useBlastDamageModel() {
  const { demoMode, demoData, designMeshId } = useSession();
  return useQuery<BlastDamageModelResponse>({
    queryKey: ['blast-damage-model', demoMode, designMeshId],
    queryFn: async () => {
      if (demoMode && demoData && isDemoMeshId(designMeshId)) {
        return {
          points: [],
          fit: null,
          x_metric: 'pf_g_per_ton',
          y_metric: 'over_break',
        } satisfies BlastDamageModelResponse;
      }
      return client
        .get<BlastDamageModelResponse>('/process/blast-correlation/damage-model')
        .then((r) => r.data);
    },
  });
}

// ─── Export ────────────────────────────────────────────────

export interface ExportFilters {
  showReconciledDesign: boolean;
  showReconciledTopo: boolean;
  showSpillAreas: boolean;
  showBlastHoles: boolean;
  blastTolerance: number;
  selectedBenchNumbers: number[];
}

export interface ExportProjectInfo {
  project?: string;
  author?: string;
  operation?: string;
  phase?: string;
  filters?: ExportFilters;
}

function buildExportQuery(params?: ExportProjectInfo): Record<string, string> {
  const query: Record<string, string> = {};
  if (!params) return query;
  if (params.project) query.project = params.project;
  if (params.author) query.author = params.author;
  if (params.operation) query.operation = params.operation;
  if (params.phase) query.phase = params.phase;
  if (params.filters) query.filters = JSON.stringify(params.filters);
  return query;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function useExportMutation(endpoint: string, defaultFilename: string, withParams = true) {
  return useMutation({
    mutationFn: (params?: ExportProjectInfo | void) => {
      const config = withParams
        ? { params: buildExportQuery(params as ExportProjectInfo | undefined), responseType: 'blob' as const }
        : { responseType: 'blob' as const };
      return client.get(endpoint, config).then(r => {
        downloadBlob(r.data, defaultFilename);
      });
    },
  });
}

export function useExportExcel() {
  return useExportMutation('/export/excel', 'Conciliacion_Geotecnica.xlsx');
}
export function useExportWord() {
  return useExportMutation('/export/word', 'Reporte_Geotecnico.docx');
}
export function useExportPdf() {
  return useExportMutation('/export/pdf', 'Reporte_Ejecutivo.pdf');
}
export function useExportDxf() {
  return useExportMutation('/export/dxf', 'Perfiles_3D.dxf', false);
}
export function useExportImages() {
  return useExportMutation('/export/images', 'Secciones_Imagenes.zip', false);
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
    // Accepts a full SettingsResponse or a partial SettingsUpdate so callers
    // can PATCH a single block (e.g. `{ blast: {...} }`) without resending
    // the others — the router merges only the blocks actually present.
    mutationFn: (settings: SettingsUpdate) =>
      client.put('/settings', settings).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });
}

// ─── AI ────────────────────────────────────────────────────

/** Callbacks delivered by {@link useGenerateAIStream} as the NDJSON stream
 *  produced by `POST /ai/generate/stream` is parsed. */
export interface AIStreamCallbacks {
  onChunk?: (accumulated: string, chunk: AIResponseChunk) => void;
  onDone?: (fullText: string, usage: AIUsageMetrics | null, cached: boolean) => void;
  onError?: (err: unknown) => void;
}

/**
 * Stream an AI report token-by-token from `POST /ai/generate/stream`.
 *
 * Uses the native `fetch` ReadableStream API (axios does not expose a
 * streaming body reader uniformly). The session ID and base URL mirror the
 * axios client so auth/routing stay consistent. Errors are thrown in the
 * same `{ response: { status, data } }` shape `classifyError` expects so
 * callers can reuse the existing error UI.
 */
export function useGenerateAIStream() {
  const [isPending, setPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const stream = useCallback(async (body: AIGenerateRequest, cb: AIStreamCallbacks) => {
    setPending(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const base = (client.defaults.baseURL || '/api/v1').replace(/\/$/, '');
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const sid = getSessionId();
      if (sid) headers['X-Session-ID'] = sid;
      const res = await fetch(`${base}/ai/generate/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const detail = await res.json().catch(() => ({} as { detail?: string }));
        throw { response: { status: res.status, data: detail } };
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let full = '';
      let usage: AIUsageMetrics | null = null;
      let cached = false;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const chunk = JSON.parse(trimmed) as AIResponseChunk;
          if (chunk.cached) cached = true;
          if (chunk.usage) usage = chunk.usage;
          if (chunk.content) {
            full += chunk.content;
            cb.onChunk?.(full, chunk);
          }
          if (chunk.finish_reason === 'error') {
            throw { response: { status: 502, data: { detail: chunk.content } } };
          }
        }
      }
      cb.onDone?.(full, usage, cached);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      cb.onError?.(err);
    } finally {
      setPending(false);
      abortRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(false);
  }, []);

  return { stream, cancel, isPending };
}


export function useCurveSection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: SectionCurveParams) => {
      const { demoMode, demoData, designMeshId } = useSession.getState();
      // Only skip the API call if the user is actually using demo meshes
      // (the demo data is loaded client-side from demoData, so a real
      // POST would 404 on the backend). If the user uploaded their own
      // meshes while still in demo mode (the flag stays sticky), the
      // POST must proceed so we hit the real backend pipeline.
      if (demoMode && demoData && isDemoMeshId(designMeshId)) return;
      await client.post('/sections/curve', params);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
    },
  });
}

// ─── Column mapping (schema-agnostic CSV/Excel ingest) ───────

/**
 * GET /mapping/schema
 *
 * Returns the canonical blast-hole schema (20 fields, 6 required) from
 * `core.column_mapping.py`. Cached aggressively (5 min staleTime) so
 * the modal does not refetch on every remount; the schema never
 * changes during a session.
 */
export function useMappingSchema() {
  return useQuery({
    queryKey: ['mapping', 'schema'],
    queryFn: () =>
      client.get<ColumnSchemaResponse>('/mapping/schema').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * POST /mapping/detect
 *
 * Wraps the auto-detect endpoint and exposes it as a `useMutation` so
 * the ColumnMapper modal can call it imperatively once the source
 * columns are known (i.e. after `useUploadBlastCsv` succeeds — at
 * that point we POST the parsed headers and receive a suggested
 * mapping per canonical field plus per-field confidence
 * (`exact` | `fuzzy` | `unmatched`).
 *
 * Returns the `useMutation` handle so the caller can drive loading
 * states via `isPending` / `isError` / `data`.
 */
export function useDetectColumnMapping() {
  return useMutation({
    mutationFn: (body: ColumnDetectRequest) =>
      client
        .post<ColumnDetectResponse>('/mapping/detect', body)
        .then((r) => r.data),
  });
}
