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
  name: string;
  origin: number[];  // [x, y]
  azimuth: number;
  length: number;
  sector: string;
}

export interface SectionResponse {
  id: string;
  name: string;
  origin: number[];
  azimuth: number;
  length: number;
  sector: string;
}

export interface SectionAutoParams {
  start: number[];   // [x, y]
  end: number[];     // [x, y]
  n_sections: number;
  azimuth?: number | null;
  length: number;
  sector: string;
  az_method: 'perpendicular' | 'fixed' | 'local_slope';
  fixed_az: number;
}

export interface SectionFromFileParams {
  spacing: number;
  length: number;
  sector: string;
  az_mode: 'perpendicular' | 'local_slope';
}

export interface SectionClickParams {
  origin: number[];
  length: number;
  sector: string;
  az_mode: 'auto' | 'manual';
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
}

export interface MessageResponse {
  message: string;
}

export interface VerticesResponse {
  x: number[];
  y: number[];
  z: number[];
}
