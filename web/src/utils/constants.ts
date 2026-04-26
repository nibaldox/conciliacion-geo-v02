/** Default tolerances matching core/config.py */
export const DEFAULT_TOLERANCES = {
  bench_height: { neg: 1.0, pos: 1.5 },
  face_angle: { neg: 5.0, pos: 5.0 },
  berm_width: { min: 6.0 },
  inter_ramp_angle: { neg: 3.0, pos: 2.0 },
  overall_angle: { neg: 2.0, pos: 2.0 },
};

/** Default process settings matching core/config.py */
export const DEFAULT_SETTINGS = {
  resolution: 0.5,
  face_threshold: 40.0,
  berm_threshold: 20.0,
};

/** Wizard steps */
export const STEPS = [
  { number: 1, label: 'Cargar Superficies', icon: '📐' },
  { number: 2, label: 'Definir Secciones', icon: '📏' },
  { number: 3, label: 'Análisis', icon: '⚙️' },
  { number: 4, label: 'Resultados', icon: '📊' },
] as const;

/** Azimuth methods */
export const AZ_METHODS = [
  { value: 'perpendicular', label: 'Perpendicular a la cresta' },
  { value: 'fixed', label: 'Azimuth fijo' },
  { value: 'local_slope', label: 'Pendiente local del diseño' },
] as const;

/** Coordinate labels */
export const COORD_LABELS = {
  x: 'Este (X)',
  y: 'Norte (Y)',
  z: 'Elevación (Z)',
} as const;
