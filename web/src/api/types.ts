// Enums
export type MeshType = 'design' | 'topo';

// Mesh schemas
export interface MeshInfo {
  id: string;
  type: MeshType;
  n_vertices: number;
  n_faces: number;
  bounds: Record<string, number>;
  filename: string;
  uploaded_at: string;
}

export interface UploadResponse {
  mesh_id: string;
  n_vertices: number;
  n_faces: number;
  bounds: Record<string, number>;
}

// Section schemas
export interface SectionCreate {
  name?: string;
  origin: [number, number];
  azimuth: number;
  length: number;
  length_up?: number;
  length_down?: number;
  sector?: string;
}

export interface SectionResponse {
  id: string;
  name: string;
  origin: [number, number];
  azimuth: number;
  length: number;
  length_up?: number | null;
  length_down?: number | null;
  sector: string;
}

export interface SectionAutoParams {
  start: [number, number];
  end: [number, number];
  n_sections?: number;
  length?: number;
  length_up?: number;
  length_down?: number;
  sector?: string;
  az_method?: 'perpendicular' | 'fixed' | 'local_slope';
  fixed_az?: number;
}

export interface SectionFromFileParams {
  spacing: number;
  length: number;
  length_up?: number;
  length_down?: number;
  sector: string;
  az_mode: 'perpendicular' | 'local_slope';
}

export interface SectionCurveParams {
  points: [number, number][] | number[][];
  spacing?: number;
  length?: number;
  length_up?: number;
  length_down?: number;
  sector?: string;
}

export interface SectionClickParams {
  origin: [number, number];
  length?: number;
  length_up?: number;
  length_down?: number;
  sector?: string;
  az_mode?: 'auto' | 'manual';
  azimuth?: number;
}

// Process schemas


export interface ProcessSettings {
  resolution: number;
  face_threshold: number;
  berm_threshold: number;
}

export interface Tolerances {
  bench_height: Record<string, number>;
  face_angle: Record<string, number>;
  berm_width: Record<string, number>;
  inter_ramp_angle: Record<string, number>;
  overall_angle: Record<string, number>;
}

/**
 * Per-session drill & blast tunables. Mirrors the backend
 * `BlastSettingsSchema` (`api/schemas.py`) and the `core.config.BlastDefaults`
 * singleton. `rock_density_tm3` (ρ, ton/m³) drives the per-mass powder factor
 * (`pf_g_per_ton`); `height_fallback_m` is the vertical height used when the
 * real hole geometry is missing. `sector_density` is an optional `{sector: rho}`
 * map keyed by the section's `sector` (geotechnical domain); a section whose
 * sector is present uses that ρ instead of the global `rock_density_tm3`.
 */
export interface BlastSettings {
  rock_density_tm3: number;
  height_fallback_m: number;
  sector_density?: Record<string, number>;
}

export interface BenchParams {
  bench_number: number;
  crest_elevation: number;
  crest_distance: number;
  toe_elevation: number;
  toe_distance: number;
  bench_height: number;
  face_angle: number;
  berm_width: number;
  is_ramp: boolean;
}

export interface ExtractionResult {
  section_name: string;
  sector: string;
  benches: BenchParams[];
  inter_ramp_angle: number;
  overall_angle: number;
}

export interface ProfileData {
  section_name: string;
  sector: string;
  origin: number[];
  azimuth: number;
  design?: { distances: number[]; elevations: number[] } | null;
  topo?: { distances: number[]; elevations: number[] } | null;
  reconciled_design?: { distances: number[]; elevations: number[] } | null;
  reconciled_topo?: { distances: number[]; elevations: number[] } | null;
  reconciled_design_legacy?: { distances: number[]; elevations: number[] } | null;
  reconciled_topo_legacy?: { distances: number[]; elevations: number[] } | null;
  benches_topo?: BenchParams[] | null;
}

export type MatchType = 'MATCH' | 'MISSING' | 'EXTRA';

export interface ComparisonResult {
  sector: string;
  section: string;
  bench_num: number;
  type: MatchType;
  level: string;
  height_design: number | null;
  height_real: number | null;
  height_dev: number | null;
  height_status: string;
  angle_design: number | null;
  angle_real: number | null;
  angle_dev: number | null;
  angle_status: string;
  berm_design: number | null;
  berm_real: number | null;
  berm_min: number | null;
  berm_status: string;
  delta_crest: number | null;
  delta_toe: number | null;
}

export interface ProcessStatus {
  status: 'idle' | 'processing' | 'complete' | 'error';
  current_section: number | null;
  total_sections: number | null;
  completed_sections: number;
  n_results: number;
}

export interface ExportRequest {
  project: string;
  author: string;
  operation: string;
  phase: string;
}

export interface SettingsResponse {
  process: ProcessSettings;
  tolerances: Tolerances;
  /** Per-session drill & blast tunables (rock density ρ, height fallback). */
  blast?: BlastSettings;
}

/**
 * Partial-update body for `PUT /settings`. All blocks optional so a caller
 * can PATCH a single block (e.g. `{ blast: {...} }`) without resending others.
 */
export interface SettingsUpdate {
  process?: ProcessSettings;
  tolerances?: Tolerances;
  blast?: BlastSettings;
}

export interface MessageResponse {
  message: string;
}

export interface VerticesResponse {
  x: number[];
  y: number[];
  z: number[];
  faces?: number[][];
}

export interface ContourLine {
  elevation: number;
  type?: 'crest' | 'toe';
  segments: number[][][];  // [polyline][point][x or y]
}

export interface ContourData {
  bounds: Record<string, number>;
  elevation_min: number;
  elevation_max: number;
  interval: number;
  lines: ContourLine[];
}

export interface ReferenceLinePoint {
  x: number;
  y: number;
}

export interface ReferenceLine {
  id: string;
  name: string;
  color?: string;
  points: ReferenceLinePoint[];
}

export interface ReferenceLineResponse {
  lines: ReferenceLine[];
}

export interface BlastHoleOnProfile {
  hole_id: string;
  distance: number;
  elevation: number;
  burden: number;
  spacing: number;
  is_within_tolerance: boolean;
}

export interface BlastHolesOnProfileResponse {
  section_id: string;
  mesh_id: string;
  tolerance: number;
  holes: BlastHoleOnProfile[];
}

// Blast correlation (per-section powder-factor metrics)
//
// Mirrors the backend `BlastCorrelationRowSchema` returned by
// `GET /api/v1/process/blast-correlation`. Field names are kept in
// snake_case to match the JSON wire format, consistent with the rest
// of the types in this file (e.g. BlastHolesOnProfileResponse).

export interface BlastCorrelationRow {
  section_name: string;
  num_wells: number;
  total_kg: number;
  mean_abs_deviation: number;
  avg_over_break: number;
  avg_under_break: number;
  n_over: number;
  n_under: number;
  pf_vol_avg_kgm3: number;
  pf_area_avg_kgm2: number;
  /** Highlighted primary metric (g/ton). */
  pf_g_per_ton_avg: number;
  /** Additive metric: powder factor using bench height excluding sub-drill ("sin pasadura"). */
  pf_g_per_ton_net_avg: number;
  energy_total_mj: number;
  n_pf_valid: number;
  /** Geotechnical-domain label echoed from the section's `sector`. */
  sector: string;
  /** Effective ρ (ton/m³) applied for this row (per-sector override or global). */
  rock_density_used: number;
}

export interface BlastCorrelationResponse {
  rows: BlastCorrelationRow[];
  tolerance: number | null;
  n_sections: number;
  carga?: number[];
  descarga?: number[];
}

// Blast PF↔damage regression model
//
// Mirrors the backend `BlastDamageModelResponse` returned by
// `GET /api/v1/process/blast-correlation/damage-model`. `fit` is null
// when the fitter reports INSUFFICIENT confidence (fewer than min_samples
// valid points, or the fit failed).

export interface BlastDamagePoint {
  section_name: string;
  /** Per-mass powder factor (g/ton) — the x-axis metric. */
  pf_g_per_ton: number;
  /** Mean overbreak (m) for the section — the y-axis metric. */
  over_break: number;
}

export type BlastDamageConfidence = 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT';

export interface BlastDamageModelFit {
  beta0: number;
  beta1: number;
  r_squared: number;
  p_value: number;
  n: number;
  confidence: BlastDamageConfidence;
  ci_beta1_low: number;
  ci_beta1_high: number;
}

export interface BlastDamageModelResponse {
  points: BlastDamagePoint[];
  fit: BlastDamageModelFit | null;
  x_metric: string;
  y_metric: string;
}

// AI reporter (core/ai_v2)
export interface AIUsageMetrics {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  is_synthetic: boolean;
  duration_ms?: number;
  cost_usd?: number | null;
}

export type AIFinishReason = 'stop' | 'length' | 'error';

export interface AIResponseChunk {
  content: string;
  finish_reason: AIFinishReason | null;
  usage: AIUsageMetrics | null;
  cached: boolean;
  chunk_index: number;
}

export interface AIFilters {
  sector?: string[];
  section?: string[];
  level?: string[];
  bench?: number[];
}

export interface AIAdvancedSettings {
  temperature: number;
  max_tokens: number;
  timeout_s: number;
  use_cache: boolean;
}

export interface AIGenerateRequest {
  results: Record<string, unknown>;
  sections: SectionResponse[] | null;
  provider: string;
  model: string;
  stream: boolean;
  metadata: Record<string, unknown>;
  notes?: string;
  context?: Record<string, unknown>;
  max_tokens?: number;
  temperature?: number;
  timeout_s?: number;
  use_cache?: boolean;
  filters?: AIFilters;
  blast_trend?: Record<string, unknown>;
}
