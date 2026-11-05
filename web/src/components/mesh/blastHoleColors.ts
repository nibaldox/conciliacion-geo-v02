import type { BlastHole3DRecord } from './BlastHoleFilters';

export const COLOR_SCALE_NAMES = [
  'Turbo', 'Inferno', 'Hot', 'Viridis', 'Plasma', 'Magma', 'Cividis',
  'Rainbow', 'Jet', 'Earth', 'YlOrRd', 'RdBu', 'Spectral', 'Balance',
  'Electric', 'Bluered', 'Greens', 'Reds', 'Blues',
] as const;

export type BlastHoleColorScale = (typeof COLOR_SCALE_NAMES)[number];
export type BlastHoleCategory = 'grid' | 'polygon' | 'phase' | 'bench';
export type BlastHoleVariable =
  | 'charge'
  | 'powderFactor'
  | 'collarElevation'
  | 'hardness'
  | 'diameter'
  | 'hardnessIndex'
  | 'penetrationRate'
  | 'depth'
  | 'inclination'
  | 'attribute';

export const BLAST_HOLE_VARIABLE_OPTIONS: readonly { value: BlastHoleVariable; label: string }[] = [
  { value: 'charge', label: 'Carga Explosiva (Kg)' },
  { value: 'powderFactor', label: 'Factor de Carga (g/ton)' },
  { value: 'collarElevation', label: 'Cota Collar' },
  { value: 'hardness', label: 'Dureza' },
  { value: 'diameter', label: 'Diámetro (mm)' },
  { value: 'hardnessIndex', label: 'Índice de Dureza' },
  { value: 'penetrationRate', label: 'Tasa de Penetración' },
  { value: 'depth', label: 'Profundidad (m)' },
  { value: 'inclination', label: 'Inclinación (°)' },
  { value: 'attribute', label: 'Atributo numérico' },
];

export interface BlastHoleColorOptions {
  kind: 'category' | 'variable';
  category?: BlastHoleCategory;
  variable?: BlastHoleVariable;
  attributeKey?: string;
  palette?: BlastHoleColorScale;
  missingLabel?: string;
  domainRecords?: readonly BlastHole3DRecord[];
  sourceRecords?: readonly BlastHole3DRecord[];
}

export interface BlastHoleColorLegendEntry {
  label: string;
  color: string;
}

export interface BlastHoleColorScaleLegendStop extends BlastHoleColorLegendEntry {
  position: number;
}

export type BlastHoleColorLegend =
  | { kind: 'category'; entries: BlastHoleColorLegendEntry[]; missing: BlastHoleColorLegendEntry | null }
  | { kind: 'variable'; min: number | null; max: number | null; palette: BlastHoleColorScale; stops: BlastHoleColorScaleLegendStop[]; missing: BlastHoleColorLegendEntry };

export interface BlastHoleColorMapping {
  colorsByRowId: Map<string, string>;
  legend: BlastHoleColorLegend;
}

const MISSING_COLOR = '#808080';
const COLOR_CYCLE = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'] as const;

const PLOTLY_SCALES = {"Turbo":[[0,"#30123b"],[0.07142857142857142,"#4145ab"],[0.14285714285714285,"#4675ed"],[0.21428571428571427,"#39a2fc"],[0.2857142857142857,"#1bcfd4"],[0.3571428571428571,"#24eca6"],[0.42857142857142855,"#61fc6c"],[0.5,"#a4fc3b"],[0.5714285714285714,"#d1e834"],[0.6428571428571428,"#f3c63a"],[0.7142857142857142,"#fe9b2d"],[0.7857142857142857,"#f36315"],[0.8571428571428571,"#d93806"],[0.9285714285714285,"#b11901"],[1,"#7a0402"]],"Inferno":[[0,"#000004"],[0.1111111111111111,"#1b0c41"],[0.2222222222222222,"#4a0c6b"],[0.3333333333333333,"#781c6d"],[0.4444444444444444,"#a52c60"],[0.5555555555555556,"#cf4446"],[0.6666666666666666,"#ed6925"],[0.7777777777777777,"#fb9b06"],[0.8888888888888888,"#f7d13d"],[1,"#fcffa4"]],"Hot":[[0,"rgb(0,0,0)"],[0.3333333333333333,"rgb(230,0,0)"],[0.6666666666666666,"rgb(255,210,0)"],[1,"rgb(255,255,255)"]],"Viridis":[[0,"#440154"],[0.1111111111111111,"#482878"],[0.2222222222222222,"#3e4989"],[0.3333333333333333,"#31688e"],[0.4444444444444444,"#26828e"],[0.5555555555555556,"#1f9e89"],[0.6666666666666666,"#35b779"],[0.7777777777777777,"#6ece58"],[0.8888888888888888,"#b5de2b"],[1,"#fde725"]],"Plasma":[[0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777777,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1,"#f0f921"]],"Magma":[[0,"#000004"],[0.1111111111111111,"#180f3d"],[0.2222222222222222,"#440f76"],[0.3333333333333333,"#721f81"],[0.4444444444444444,"#9e2f7f"],[0.5555555555555556,"#cd4071"],[0.6666666666666666,"#f1605d"],[0.7777777777777777,"#fd9668"],[0.8888888888888888,"#feca8d"],[1,"#fcfdbf"]],"Cividis":[[0,"#00224e"],[0.1111111111111111,"#123570"],[0.2222222222222222,"#3b496c"],[0.3333333333333333,"#575d6d"],[0.4444444444444444,"#707173"],[0.5555555555555556,"#8a8678"],[0.6666666666666666,"#a59c74"],[0.7777777777777777,"#c3b369"],[0.8888888888888888,"#e1cc55"],[1,"#fee838"]],"Rainbow":[[0,"rgb(150,0,90)"],[0.125,"rgb(0,0,200)"],[0.25,"rgb(0,25,255)"],[0.375,"rgb(0,152,255)"],[0.5,"rgb(44,255,150)"],[0.625,"rgb(151,255,0)"],[0.75,"rgb(255,234,0)"],[0.875,"rgb(255,111,0)"],[1,"rgb(255,0,0)"]],"Jet":[[0,"rgb(0,0,131)"],[0.2,"rgb(0,60,170)"],[0.4,"rgb(5,255,255)"],[0.6000000000000001,"rgb(255,255,0)"],[0.8,"rgb(250,0,0)"],[1,"rgb(128,0,0)"]],"Earth":[[0,"rgb(161, 105, 40)"],[0.16666666666666666,"rgb(189, 146, 90)"],[0.3333333333333333,"rgb(214, 189, 141)"],[0.5,"rgb(237, 234, 194)"],[0.6666666666666666,"rgb(181, 200, 184)"],[0.8333333333333333,"rgb(121, 167, 172)"],[1,"rgb(40, 135, 161)"]],"YlOrRd":[[0,"rgb(255,255,204)"],[0.125,"rgb(255,237,160)"],[0.25,"rgb(254,217,118)"],[0.375,"rgb(254,178,76)"],[0.5,"rgb(253,141,60)"],[0.625,"rgb(252,78,42)"],[0.75,"rgb(227,26,28)"],[0.875,"rgb(189,0,38)"],[1,"rgb(128,0,38)"]],"RdBu":[[0,"rgb(103,0,31)"],[0.1,"rgb(178,24,43)"],[0.2,"rgb(214,96,77)"],[0.30000000000000004,"rgb(244,165,130)"],[0.4,"rgb(253,219,199)"],[0.5,"rgb(247,247,247)"],[0.6000000000000001,"rgb(209,229,240)"],[0.7000000000000001,"rgb(146,197,222)"],[0.8,"rgb(67,147,195)"],[0.9,"rgb(33,102,172)"],[1,"rgb(5,48,97)"]],"Spectral":[[0,"rgb(158,1,66)"],[0.1,"rgb(213,62,79)"],[0.2,"rgb(244,109,67)"],[0.30000000000000004,"rgb(253,174,97)"],[0.4,"rgb(254,224,139)"],[0.5,"rgb(255,255,191)"],[0.6000000000000001,"rgb(230,245,152)"],[0.7000000000000001,"rgb(171,221,164)"],[0.8,"rgb(102,194,165)"],[0.9,"rgb(50,136,189)"],[1,"rgb(94,79,162)"]],"Balance":[[0,"rgb(23, 28, 66)"],[0.09090909090909091,"rgb(41, 58, 143)"],[0.18181818181818182,"rgb(11, 102, 189)"],[0.2727272727272727,"rgb(69, 144, 185)"],[0.36363636363636365,"rgb(142, 181, 194)"],[0.4545454545454546,"rgb(210, 216, 219)"],[0.5454545454545454,"rgb(230, 210, 204)"],[0.6363636363636364,"rgb(213, 157, 137)"],[0.7272727272727273,"rgb(196, 101, 72)"],[0.8181818181818182,"rgb(172, 43, 36)"],[0.9090909090909092,"rgb(120, 14, 40)"],[1,"rgb(60, 9, 17)"]],"Electric":[[0,"rgb(0,0,0)"],[0.2,"rgb(30,0,100)"],[0.4,"rgb(120,0,100)"],[0.6000000000000001,"rgb(160,90,0)"],[0.8,"rgb(230,200,0)"],[1,"rgb(255,250,220)"]],"Bluered":[[0,"rgb(0,0,255)"],[1,"rgb(255,0,0)"]],"Greens":[[0,"rgb(247,252,245)"],[0.125,"rgb(229,245,224)"],[0.25,"rgb(199,233,192)"],[0.375,"rgb(161,217,155)"],[0.5,"rgb(116,196,118)"],[0.625,"rgb(65,171,93)"],[0.75,"rgb(35,139,69)"],[0.875,"rgb(0,109,44)"],[1,"rgb(0,68,27)"]],"Reds":[[0,"rgb(255,245,240)"],[0.125,"rgb(254,224,210)"],[0.25,"rgb(252,187,161)"],[0.375,"rgb(252,146,114)"],[0.5,"rgb(251,106,74)"],[0.625,"rgb(239,59,44)"],[0.75,"rgb(203,24,29)"],[0.875,"rgb(165,15,21)"],[1,"rgb(103,0,13)"]],"Blues":[[0,"rgb(247,251,255)"],[0.125,"rgb(222,235,247)"],[0.25,"rgb(198,219,239)"],[0.375,"rgb(158,202,225)"],[0.5,"rgb(107,174,214)"],[0.625,"rgb(66,146,198)"],[0.75,"rgb(33,113,181)"],[0.875,"rgb(8,81,156)"],[1,"rgb(8,48,107)"]]} as const;

const CATEGORY_KEYS: Record<BlastHoleCategory, readonly string[]> = {
  grid: ['Nombre_Malla_Original'],
  polygon: ['holes_polygon'],
  phase: ['Nombre_Fase', 'Fase'],
  bench: ['Banco_Original', 'Nombre_Banco', 'Banco'],
};
export const BLAST_HOLE_CATEGORY_OPTIONS: readonly { value: BlastHoleCategory; label: string }[] = [
  { value: 'grid', label: 'Mallas de Tronadura (Grid)' },
  { value: 'polygon', label: 'Polígonos Tronados' },
  { value: 'phase', label: 'Fase' },
  { value: 'bench', label: 'Banco' },
];

const CHARGE_KEYS = ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'];
const POWDER_FACTOR_KEYS = ['pf_g_per_ton_inf', 'pf_g_per_ton'];
const VARIABLE_ATTRIBUTE_KEYS: Partial<Record<Exclude<BlastHoleVariable, 'charge' | 'powderFactor' | 'collarElevation' | 'hardness' | 'attribute'>, readonly string[]>> = {
  diameter: ['Diam_mm', 'Diametro', 'Diameter', 'Diametro_mm', 'diameter_mm'],
  hardnessIndex: ['indice_dureza', 'Indice_Dureza', 'hardness_index'],
  penetrationRate: ['tasa_penetracion', 'Tasa_Penetracion', 'penetration_rate'],
  depth: ['Len', 'longitud_real', 'Longitud_real', 'depth_m'],
  inclination: ['Incl', 'Inclinacion_real', 'Inclinacion', 'inclination'],
};
const HARDNESS_VALUES: Record<string, number> = {
  'roca suave': 1,
  'roca media': 2,
  'roca dura': 3,
  'roca muy dura': 4,
};

export function getAvailableBlastHoleVariables(holes: readonly BlastHole3DRecord[]): BlastHoleVariable[] {
  const conditional: readonly [BlastHoleVariable, readonly string[]][] = [
    ['charge', CHARGE_KEYS],
    ['powderFactor', POWDER_FACTOR_KEYS],
    ['diameter', VARIABLE_ATTRIBUTE_KEYS.diameter ?? []],
    ['hardness', ['dureza', 'Dureza', 'hardness']],
    ['hardnessIndex', VARIABLE_ATTRIBUTE_KEYS.hardnessIndex ?? []],
    ['penetrationRate', VARIABLE_ATTRIBUTE_KEYS.penetrationRate ?? []],
  ];
  const available: BlastHoleVariable[] = conditional
    .filter(([, keys]) => sourceKey(holes, keys) !== undefined)
    .map(([variable]) => variable);
  if (sourceKey(holes, VARIABLE_ATTRIBUTE_KEYS.depth ?? []) !== undefined) available.push('depth');
  if (sourceKey(holes, VARIABLE_ATTRIBUTE_KEYS.inclination ?? []) !== undefined) available.push('inclination');
  if (holes.some((hole) => hole.collar && hole.collar.length >= 3 && numericValue(hole.collar[2]) !== null)) {
    available.push('collarElevation');
  }
  return [
    ...available,
  ];
}

export function getAvailableBlastHoleCategories(holes: readonly BlastHole3DRecord[]): BlastHoleCategory[] {
  return (Object.keys(CATEGORY_KEYS) as BlastHoleCategory[]).filter((category) => sourceKey(holes, CATEGORY_KEYS[category]) !== undefined);
}

type ScaleStop = readonly [number, string];

function sourceKey(records: readonly BlastHole3DRecord[], keys: readonly string[]): string | undefined {
  for (const key of keys) {
    if (records.some((record) => Object.prototype.hasOwnProperty.call(record.attributes, key))) return key;
  }
  return undefined;
}

function firstValue(record: BlastHole3DRecord, key: string | undefined): unknown {
  return key === undefined ? undefined : record.attributes[key];
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function variableValue(hole: BlastHole3DRecord, variable: BlastHoleVariable, selectedKey?: string): number | null {
  if (variable === 'collarElevation') {
    return hole.collar && hole.collar.length >= 3 ? numericValue(hole.collar[2]) : null;
  }
  if (variable === 'hardness') {
    const hardness = categoryValue(firstValue(hole, selectedKey))?.toLocaleLowerCase();
    return hardness ? HARDNESS_VALUES[hardness] ?? null : null;
  }
  return numericValue(firstValue(hole, selectedKey));
}

function categoryValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value);
  return text.trim() ? text : null;
}

function parseRgb(color: string): readonly [number, number, number] {
  if (color.startsWith('#')) {
    const hex = color.slice(1);
    return [0, 2, 4].map((index) => Number.parseInt(hex.slice(index, index + 2), 16)) as [number, number, number];
  }
  const matches = color.match(/\d+(?:\.\d+)?/g);
  if (!matches || matches.length < 3) return [128, 128, 128];
  return [Number(matches[0]), Number(matches[1]), Number(matches[2])];
}

function hexColor(color: string): string {
  const [red, green, blue] = parseRgb(color);
  return `#${[red, green, blue].map((channel) => Math.round(channel).toString(16).padStart(2, '0')).join('')}`;
}

function interpolateScale(stops: readonly ScaleStop[], value: number): string {
  const position = Math.min(1, Math.max(0, value));
  const upperIndex = stops.findIndex(([stop]) => stop >= position);
  if (upperIndex < 0) return hexColor(stops[stops.length - 1][1]);
  if (upperIndex === 0) return hexColor(stops[0][1]);
  const [lowerPosition, lowerColor] = stops[upperIndex - 1];
  const [upperPosition, upperColor] = stops[upperIndex];
  if (position === upperPosition) return hexColor(upperColor);
  const fraction = (position - lowerPosition) / (upperPosition - lowerPosition);
  const lowerRgb = parseRgb(lowerColor);
  const upperRgb = parseRgb(upperColor);
  return `#${lowerRgb.map((channel, index) => Math.round(channel + (upperRgb[index] - channel) * fraction).toString(16).padStart(2, '0')).join('')}`;
}

function formatValue(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(4)));
}

export function mapBlastHoleColors(
  holes: readonly BlastHole3DRecord[],
  options: BlastHoleColorOptions,
): BlastHoleColorMapping {
  const missingLabel = options.missingLabel ?? 'Sin dato';
  const colorsByRowId = new Map<string, string>();

  if (options.kind === 'category') {
    const keys = CATEGORY_KEYS[options.category ?? 'bench'];
    const domain = options.domainRecords ?? holes;
    const key = sourceKey(options.sourceRecords ?? domain, keys);
    const values = holes.map((hole) => categoryValue(firstValue(hole, key)));
    const categories = [...new Set(domain.map((hole) => categoryValue(firstValue(hole, key))).filter((value): value is string => value !== null))].sort();
    const entries = categories.map((label, index) => ({ label, color: COLOR_CYCLE[index % COLOR_CYCLE.length] }));
    const colors = new Map(entries.map(({ label, color }) => [label, color]));
    holes.forEach((hole, index) => colorsByRowId.set(hole.row_id, values[index] === null ? MISSING_COLOR : colors.get(values[index]!)!));
    return {
      colorsByRowId,
      legend: {
        kind: 'category',
        entries,
        missing: values.some((value) => value === null) ? { label: missingLabel, color: MISSING_COLOR } : null,
      },
    };
  }

  const variable = options.variable ?? 'attribute';
  const keys = variable === 'charge'
    ? CHARGE_KEYS
    : variable === 'powderFactor'
      ? POWDER_FACTOR_KEYS
      : variable === 'hardness'
        ? ['dureza', 'Dureza', 'hardness']
        : variable === 'attribute'
          ? options.attributeKey ? [options.attributeKey] : []
          : variable === 'collarElevation' ? [] : VARIABLE_ATTRIBUTE_KEYS[variable] ?? [];
  const key = variable === 'collarElevation' ? undefined : sourceKey(options.sourceRecords ?? options.domainRecords ?? holes, keys);
  const values = holes.map((hole) => variableValue(hole, variable, key));
  const domainHoles = options.domainRecords ?? holes;
  const domainKey = variable === 'collarElevation' ? undefined : sourceKey(options.sourceRecords ?? domainHoles, keys);
  const domainValues = domainHoles.map((hole) => variableValue(hole, variable, domainKey)).filter((value): value is number => value !== null);
  const fixedBounds = variable === 'charge' ? [0, 1000] as const : variable === 'powderFactor' ? [0, 200] as const : null;
  let observedMinimum = Number.POSITIVE_INFINITY;
  let observedMaximum = Number.NEGATIVE_INFINITY;
  for (const value of domainValues) {
    if (value < observedMinimum) observedMinimum = value;
    if (value > observedMaximum) observedMaximum = value;
  }
  const minimum = fixedBounds?.[0] ?? (domainValues.length ? observedMinimum : null);
  const maximum = fixedBounds?.[1] ?? (domainValues.length ? observedMaximum : null);
  const palette = options.palette ?? 'Turbo';
  const stops = PLOTLY_SCALES[palette] as readonly ScaleStop[];
  const colorAt = (value: number): string => {
    const normalized = minimum === null || maximum === null || minimum === maximum
      ? 0.5
      : (value - minimum) / (maximum - minimum);
    return interpolateScale(stops, normalized);
  };
  holes.forEach((hole, index) => colorsByRowId.set(hole.row_id, values[index] === null ? MISSING_COLOR : colorAt(values[index]!)));
  const legendStops = stops.map(([position, color]) => ({
    label: minimum === null || maximum === null ? '—' : formatValue(minimum + (maximum - minimum) * position),
    color: hexColor(color),
    position,
  }));
  return {
    colorsByRowId,
    legend: {
      kind: 'variable',
      min: minimum,
      max: maximum,
      palette,
      stops: legendStops,
      missing: { label: missingLabel, color: MISSING_COLOR },
    },
  };
}
