import { describe, expect, it } from 'vitest';
import type { BlastHole3DRecord } from '../BlastHoleFilters';
import { BLAST_HOLE_VARIABLE_OPTIONS, COLOR_SCALE_NAMES, getAvailableBlastHoleVariables, mapBlastHoleColors } from '../blastHoleColors';

function hole(rowId: string, attributes: Record<string, unknown> = {}): BlastHole3DRecord {
  return {
    row_id: rowId,
    hole_id: rowId,
    collar: null,
    toe: null,
    geometry_status: 'complete',
    provenance: {},
    attributes,
    section_relation: null,
    section_distance_m: null,
  };
}

describe('mapBlastHoleColors', () => {
  it('treats blank category values as missing data', () => {
    const result = mapBlastHoleColors([
      hole('populated', { Banco: '3150' }),
      hole('blank', { Banco: '' }),
      hole('spaces', { Banco: '   ' }),
    ], { kind: 'category', category: 'bench' });

    expect(result.legend).toMatchObject({
      kind: 'category',
      entries: [{ label: '3150' }],
      missing: { label: 'Sin dato', color: '#808080' },
    });
    expect(result.colorsByRowId.get('blank')).toBe('#808080');
    expect(result.colorsByRowId.get('spaces')).toBe('#808080');
  });

  it('maps categories in Python lexical order and uses the Streamlit Plotly cycle', () => {
    const result = mapBlastHoleColors([
      hole('two', { Banco: '2' }),
      hole('one-ten', { Banco: '10' }),
      hole('one', { Banco: '1' }),
      hole('missing', { Banco: null }),
    ], { kind: 'category', category: 'bench' });

    expect(result.colorsByRowId.get('one')).toBe('#636EFA');
    expect(result.colorsByRowId.get('one-ten')).toBe('#EF553B');
    expect(result.colorsByRowId.get('two')).toBe('#00CC96');
    expect(result.colorsByRowId.get('missing')).toBe('#808080');
    expect(result.legend).toEqual({
      kind: 'category',
      entries: [
        { label: '1', color: '#636EFA' },
        { label: '10', color: '#EF553B' },
        { label: '2', color: '#00CC96' },
      ],
      missing: { label: 'Sin dato', color: '#808080' },
    });
  });

  it('resolves the original mesh category alias', () => {
    const result = mapBlastHoleColors([
      hole('mesh-a', { Nombre_Malla_Original: 'Malla B' }),
      hole('mesh-b', { Nombre_Malla_Original: 'Malla A' }),
    ], { kind: 'category', category: 'grid' });

    expect(result.legend).toMatchObject({
      kind: 'category',
      entries: [
        { label: 'Malla A', color: '#636EFA' },
        { label: 'Malla B', color: '#EF553B' },
      ],
    });
  });

  it('preserves category strings exactly, including leading and trailing whitespace', () => {
    const result = mapBlastHoleColors([
      hole('spaced', { Fase: ' Fase ' }),
      hole('plain', { Fase: 'Fase' }),
      hole('missing', { Fase: null }),
    ], { kind: 'category', category: 'phase' });

    expect(result.legend).toMatchObject({
      kind: 'category',
      entries: [
        { label: ' Fase ', color: '#636EFA' },
        { label: 'Fase', color: '#EF553B' },
      ],
      missing: { color: '#808080' },
    });
  });

  it('keeps the first existing source column authoritative even when its row value is null', () => {
    const result = mapBlastHoleColors([
      hole('first-column-null', { Kilos_Cargados_real: null, Kilos_Cargados: 120 }),
      hole('fallback-column', { Kilos_Cargados: 120 }),
      hole('primary-column', { Kilos_Cargados_real: 240 }),
    ], { kind: 'variable', variable: 'charge' });

    expect(result.colorsByRowId.get('first-column-null')).toBe('#808080');
    expect(result.colorsByRowId.get('fallback-column')).toBe('#808080');
    expect(result.colorsByRowId.get('primary-column')).not.toBe('#808080');
  });

  it('selects aliases once for the whole record set, leaving rows without that column value missing', () => {
    const result = mapBlastHoleColors([
      hole('alternate-only', { Kilos_Cargados: 120, Fase: 'Fase alterna' }),
      hole('primary-column', { Kilos_Cargados_real: 240, Nombre_Fase: 'Fase principal' }),
    ], { kind: 'variable', variable: 'charge' });
    const categoryResult = mapBlastHoleColors([
      hole('alternate-only', { Fase: 'Fase alterna' }),
      hole('primary-column', { Nombre_Fase: 'Fase principal' }),
    ], { kind: 'category', category: 'phase' });

    expect(result.colorsByRowId.get('alternate-only')).toBe('#808080');
    expect(result.colorsByRowId.get('primary-column')).not.toBe('#808080');
    expect(categoryResult.colorsByRowId.get('alternate-only')).toBe('#808080');
    expect(categoryResult.legend.kind === 'category' && categoryResult.legend.entries.map(({ label }) => label)).toEqual(['Fase principal']);
  });

  it('keeps the source-wide alias when the row that provides its column is filtered out', () => {
    const sourceRecords = [
      hole('excluded-primary', { Kilos_Cargados_real: 240 }),
      hole('visible-secondary', { Kilos_Cargados: 120 }),
    ];
    const result = mapBlastHoleColors([sourceRecords[1]], {
      kind: 'variable',
      variable: 'charge',
      sourceRecords,
    });

    expect(result.colorsByRowId.get('visible-secondary')).toBe('#808080');
    expect(result.legend.kind === 'variable' && result.legend.min).toBe(0);
    expect(result.legend.kind === 'variable' && result.legend.max).toBe(1000);
  });

  it.each([
    ['collarElevation', hole('measured', {},), [10, 20, 300], 300],
    ['hardness', hole('measured', { dureza: 'Roca muy dura' }), null, 4],
    ['diameter', hole('measured', { Diam_mm: 165 }), null, 165],
    ['hardnessIndex', hole('measured', { indice_dureza: '72.5' }), null, 72.5],
    ['penetrationRate', hole('measured', { tasa_penetracion: 18 }), null, 18],
    ['depth', hole('measured', { Len: 12.4 }), null, 12.4],
    ['inclination', hole('measured', { Incl: 87 }), null, 87],
  ] as const)('reads the %s variable and preserves missing values', (variable, measured, collar, expected) => {
    const valueHole: BlastHole3DRecord = collar ? { ...measured, collar: [...collar] } : measured;
    const result = mapBlastHoleColors([valueHole, hole('missing')], { kind: 'variable', variable });

    expect(result.colorsByRowId.get('measured')).toBe('#a4fc3b');
    expect(result.colorsByRowId.get('missing')).toBe('#808080');
    expect(result.legend.kind === 'variable' && result.legend.min).toBe(expected);
    expect(result.legend.kind === 'variable' && result.legend.max).toBe(expected);
  });

  it('exports Streamlit variable labels for selector integration', () => {
    expect(BLAST_HOLE_VARIABLE_OPTIONS.map(({ value }) => value)).toEqual([
      'charge', 'powderFactor', 'powderFactorGeometry', 'collarElevation', 'hardness', 'diameter', 'hardnessIndex',
      'penetrationRate', 'depth', 'inclination', 'attribute',
    ]);
  });

  it('recognizes hardness aliases when deciding whether the variable is available', () => {
    expect(getAvailableBlastHoleVariables([hole('upper', { Dureza: 'Roca media' })])).toContain('hardness');
    expect(getAvailableBlastHoleVariables([hole('english', { hardness: 'Roca dura' })])).toContain('hardness');
  });

  it('hides variables whose key exists but has no resolvable value', () => {
    const holes = [hole('a', { pf_g_per_ton_inf: null, pf_g_per_ton: 50 }), hole('b', { pf_g_per_ton_inf: null, pf_g_per_ton: 60 })];
    expect(getAvailableBlastHoleVariables(holes)).not.toContain('powderFactor');
    expect(getAvailableBlastHoleVariables(holes)).toContain('powderFactorGeometry');
    expect(getAvailableBlastHoleVariables([hole('c', { Kilos_Cargados_real: null })])).not.toContain('charge');
    expect(getAvailableBlastHoleVariables([hole('d', { Dureza: 'Desconocida' })])).not.toContain('hardness');
    expect(getAvailableBlastHoleVariables([hole('e', { Dureza: '   ' })])).not.toContain('hardness');
  });

  it('does not offer powderFactor from pf_g_per_ton when the influence key has no values', () => {
    const holes = [hole('a', { pf_g_per_ton_inf: null, pf_g_per_ton: 50 })];
    expect(getAvailableBlastHoleVariables(holes)).not.toContain('powderFactor');
  });

  it('assigns hardness values with surrounding spaces after trimming', () => {
    const result = mapBlastHoleColors([hole('spaced', { Dureza: ' roca dura ' }), hole('plain', { Dureza: 'Roca dura' })], {
      kind: 'variable', variable: 'hardness', rangeMode: 'data',
    });
    expect(result.legend).toMatchObject({ min: 3, max: 3, missingCount: 0 });
    expect(result.colorsByRowId.get('spaced')).not.toBe('#808080');
  });

  it('shows Sin dato in the category legend based on the domain, not the filtered subset', () => {
    const domain = [hole('a', { Banco: '1' }), hole('b', { Banco: null })];
    const subset = [hole('a', { Banco: '1' })];
    const result = mapBlastHoleColors(subset, { kind: 'category', category: 'bench', domainRecords: domain, sourceRecords: domain });
    expect(result.legend).toMatchObject({ kind: 'category', missing: { label: 'Sin dato' } });
    const noMissing = mapBlastHoleColors(subset, { kind: 'category', category: 'bench', domainRecords: [hole('a', { Banco: '1' })] });
    expect(noMissing.legend).toMatchObject({ kind: 'category', missing: null });
  });

  it('keeps categories and the missing entry for the whole domain', () => {
    const domain = [hole('a', { Banco: '1' }), hole('b', { Banco: '2' })];
    const subset = [hole('a', { Banco: '1' })];
    const result = mapBlastHoleColors(subset, { kind: 'category', category: 'bench', domainRecords: domain, sourceRecords: domain });
    expect(result.legend).toMatchObject({ kind: 'category', entries: [{ label: '1' }, { label: '2' }] });
  });

  it('uses fixed 0–1000 charge and 0–200 powder factor bounds, clamping at the palette endpoints', () => {
    const holes = [
      hole('low', { Kilos_Cargados_real: -5, pf_g_per_ton_inf: 0 }),
      hole('mid', { Kilos_Cargados_real: 500, pf_g_per_ton_inf: 100 }),
      hole('high', { Kilos_Cargados_real: 1200, pf_g_per_ton_inf: 240 }),
    ];
    const charge = mapBlastHoleColors(holes, { kind: 'variable', variable: 'charge' });
    const pf = mapBlastHoleColors(holes, { kind: 'variable', variable: 'powderFactor' });

    expect(charge.legend).toMatchObject({ min: 0, max: 1000, palette: 'Turbo' });
    expect(charge.colorsByRowId.get('low')).toBe('#30123b');
    expect(charge.colorsByRowId.get('mid')).toBe('#a4fc3b');
    expect(charge.colorsByRowId.get('high')).toBe('#7a0402');
    expect(pf.legend).toMatchObject({ min: 0, max: 200 });
    expect(pf.colorsByRowId.get('mid')).toBe('#a4fc3b');
    expect(mapBlastHoleColors([hole('missing', { Kilos_Cargados_real: null })], { kind: 'variable', variable: 'charge' }).legend)
      .toMatchObject({ min: 0, max: 1000 });
    expect(mapBlastHoleColors([hole('missing', { pf_g_per_ton: null })], { kind: 'variable', variable: 'powderFactor' }).legend)
      .toMatchObject({ min: 0, max: 200 });
  });

  it('autoscale uses finite values, handles equal values at the center, and keeps missing data gray', () => {
    const result = mapBlastHoleColors([
      hole('one', { depth: 5 }),
      hole('two', { depth: '5' }),
      hole('bad', { depth: Number.NaN }),
      hole('absent'),
    ], { kind: 'variable', variable: 'attribute', attributeKey: 'depth' });

    expect(result.legend).toMatchObject({ min: 5, max: 5, palette: 'Turbo' });
    expect(result.colorsByRowId.get('one')).toBe('#a4fc3b');
    expect(result.colorsByRowId.get('two')).toBe('#a4fc3b');
    expect(result.colorsByRowId.get('bad')).toBe('#808080');
    expect(result.colorsByRowId.get('absent')).toBe('#808080');
    expect(result.legend.kind === 'variable' && result.legend.missing.color).toBe('#808080');
  });

  it('exposes all 19 palettes returned by the Streamlit selector and supports exact palette endpoints', () => {
    const result = mapBlastHoleColors([
      hole('low', { value: 0 }),
      hole('high', { value: 1 }),
    ], { kind: 'variable', variable: 'attribute', attributeKey: 'value', palette: 'Viridis' });

    expect(COLOR_SCALE_NAMES).toHaveLength(19);
    expect(result.colorsByRowId.get('low')).toBe('#440154');
    expect(result.colorsByRowId.get('high')).toBe('#fde725');
    expect(result.legend.kind === 'variable' && result.legend.palette).toBe('Viridis');
    expect(result.legend.kind === 'variable' && result.legend.stops).toHaveLength(10);
    expect(result.legend.kind === 'variable' && result.legend.stops[0]).toMatchObject({ position: 0, color: '#440154', label: '0' });
    expect(result.legend.kind === 'variable' && result.legend.stops[5]).toMatchObject({ position: 5 / 9, color: '#1f9e89', label: '0.5556' });
    expect(result.legend.kind === 'variable' && result.legend.stops.at(-1)).toMatchObject({ position: 1, color: '#fde725', label: '1' });
  });
});

describe('explicit ranges, saturation diagnostics and geometric powder factor', () => {
  it('data range uses the complete source domain while colors of visible holes stay stable', () => {
    const source = [
      hole('low', { Kilos_Cargados_real: 100 }),
      hole('visible', { Kilos_Cargados_real: 200 }),
      hole('high', { Kilos_Cargados_real: 300 }),
    ];
    const full = mapBlastHoleColors(source, { kind: 'variable', variable: 'charge', rangeMode: 'data' });
    const filtered = mapBlastHoleColors([source[1]], { kind: 'variable', variable: 'charge', rangeMode: 'data', sourceRecords: source });

    expect(filtered.legend).toMatchObject({ kind: 'variable', min: 100, max: 300, observedMin: 100, observedMax: 300, belowCount: 0, aboveCount: 0, missingCount: 0, unit: 'kg' });
    expect(filtered.colorsByRowId.get('visible')).toBe(full.colorsByRowId.get('visible'));
  });

  it('manual range clamps saturated values to the palette endpoints and counts them', () => {
    const result = mapBlastHoleColors([
      hole('below', { Kilos_Cargados_real: -1 }),
      hole('inside', { Kilos_Cargados_real: 500 }),
      hole('above', { Kilos_Cargados_real: 1200 }),
      hole('missing', { Kilos_Cargados_real: null }),
    ], { kind: 'variable', variable: 'charge', rangeMode: 'manual', rangeMin: 0, rangeMax: 1000 });

    expect(result.legend).toMatchObject({
      kind: 'variable', min: 0, max: 1000, observedMin: -1, observedMax: 1200,
      belowCount: 1, aboveCount: 1, missingCount: 1, sourceKey: 'Kilos_Cargados_real', unit: 'kg',
    });
    expect(result.colorsByRowId.get('below')).toBe('#30123b');
    expect(result.colorsByRowId.get('above')).toBe('#7a0402');
    expect(result.colorsByRowId.get('missing')).toBe('#808080');
  });

  it('range diagnostics read the complete source domain, not only visible holes', () => {
    const source = [
      hole('visible', { Kilos_Cargados_real: 500 }),
      hole('filtered-above', { Kilos_Cargados_real: 1500 }),
    ];
    const result = mapBlastHoleColors([source[0]], { kind: 'variable', variable: 'charge', rangeMode: 'manual', rangeMin: 0, rangeMax: 1000, sourceRecords: source });

    expect(result.legend).toMatchObject({ aboveCount: 1, belowCount: 0, observedMax: 1500 });
  });

  it.each([
    [undefined, 10],
    [0, undefined],
    [10, 10],
    [20, 10],
    [Number.NaN, 10],
    [0, Number.POSITIVE_INFINITY],
  ])('rejects invalid manual range %s..%s with RangeError', (rangeMin, rangeMax) => {
    expect(() => mapBlastHoleColors([hole('a', { Kilos_Cargados_real: 1 })], {
      kind: 'variable', variable: 'charge', rangeMode: 'manual', rangeMin, rangeMax,
    })).toThrow(RangeError);
  });

  it('constant data range uses the central color and a single-value legend', () => {
    const result = mapBlastHoleColors([hole('a', { depth: 7 }), hole('b', { depth: 7 })], {
      kind: 'variable', variable: 'attribute', attributeKey: 'depth', rangeMode: 'data',
    });

    expect(result.colorsByRowId.get('a')).toBe('#a4fc3b');
    expect(result.legend).toMatchObject({ min: 7, max: 7, observedMin: 7, observedMax: 7, belowCount: 0, aboveCount: 0 });
  });

  it('data range without finite values yields null bounds, gray holes and no NaN or Infinity', () => {
    const result = mapBlastHoleColors([hole('a', { depth: 'texto' }), hole('b')], {
      kind: 'variable', variable: 'attribute', attributeKey: 'depth', rangeMode: 'data',
    });
    const serialized = JSON.stringify(result.legend);

    expect(result.legend).toMatchObject({ min: null, max: null, observedMin: null, observedMax: null, missingCount: 2 });
    expect(result.colorsByRowId.get('a')).toBe('#808080');
    expect(serialized).not.toMatch(/NaN|Infinity/);
  });

  it('powderFactorGeometry reads only pf_g_per_ton and never the influence alias', () => {
    const result = mapBlastHoleColors([
      hole('influence-only', { pf_g_per_ton_inf: 100 }),
      hole('geometric', { pf_g_per_ton: 50 }),
    ], { kind: 'variable', variable: 'powderFactorGeometry', rangeMode: 'data' });

    expect(result.colorsByRowId.get('influence-only')).toBe('#808080');
    expect(result.legend).toMatchObject({ min: 50, max: 50, sourceKey: 'pf_g_per_ton', unit: 'g/t', missingCount: 1 });
  });

  it('legacy powderFactor keeps the influence alias first', () => {
    const result = mapBlastHoleColors([hole('both', { pf_g_per_ton_inf: 100, pf_g_per_ton: 50 })], {
      kind: 'variable', variable: 'powderFactor',
    });

    expect(result.legend).toMatchObject({ sourceKey: 'pf_g_per_ton_inf' });
  });

  it('offers powderFactorGeometry only when the geometric key exists', () => {
    expect(getAvailableBlastHoleVariables([hole('a', { pf_g_per_ton: 5 })])).toContain('powderFactorGeometry');
    expect(getAvailableBlastHoleVariables([hole('a', { pf_g_per_ton_inf: 5 })])).not.toContain('powderFactorGeometry');
    expect(getAvailableBlastHoleVariables([hole('a', { pf_g_per_ton_inf: 5 })])).toContain('powderFactor');
  });

  it('category colors stay identical when filtering to a subset of the source', () => {
    const source = [hole('a', { Banco: '1' }), hole('b', { Banco: '2' }), hole('c', { Banco: '3' })];
    const full = mapBlastHoleColors(source, { kind: 'category', category: 'bench' });
    const filtered = mapBlastHoleColors([source[2]], { kind: 'category', category: 'bench', sourceRecords: source });

    expect(filtered.colorsByRowId.get('c')).toBe(full.colorsByRowId.get('c'));
    expect(filtered.legend).toEqual(full.legend);
  });

  it('73 categories cycle the palette deterministically without claiming unique colors', () => {
    const source = Array.from({ length: 73 }, (_, index) => hole(`h${index}`, { Banco: String(index + 1).padStart(2, '0') }));
    const result = mapBlastHoleColors(source, { kind: 'category', category: 'bench' });

    expect(result.legend.kind === 'category' && result.legend.entries).toHaveLength(73);
    expect(new Set(result.legend.kind === 'category' ? result.legend.entries.map(({ color }) => color) : []).size).toBe(10);
    expect(result.colorsByRowId.get('h0')).toBe(result.colorsByRowId.get('h10'));
    expect(result.colorsByRowId.get('h0')).not.toBe(result.colorsByRowId.get('h1'));
  });
});

describe('finite extreme ranges without overflow', () => {
  const sampleHoles = (values: readonly number[]) => values.map((value, index) => hole(`v${index}`, { x: value }));
  const finiteColor = /^#[0-9a-f]{6}$/;

  it('maps the extreme finite manual range to endpoints and a central color without NaN or Infinity', () => {
    const result = mapBlastHoleColors(sampleHoles([-1e308, 0, 1e308]), {
      kind: 'variable', variable: 'attribute', attributeKey: 'x', rangeMode: 'manual', rangeMin: -1e308, rangeMax: 1e308,
    });

    expect(result.colorsByRowId.get('v0')).toBe('#30123b');
    expect(result.colorsByRowId.get('v1')).toBe('#a4fc3b');
    expect(result.colorsByRowId.get('v2')).toBe('#7a0402');
    expect(result.legend.kind === 'variable' && result.legend.stops[0].label).toBe('-1e+308');
    expect(result.legend.kind === 'variable' && result.legend.stops.at(-1)?.label).toBe('1e+308');
    expect(JSON.stringify(result.legend)).not.toMatch(/NaN|Infinity/);
  });

  it('keeps legend labels finite and ordered for extreme ranges', () => {
    const result = mapBlastHoleColors(sampleHoles([-1e308, 1e308]), {
      kind: 'variable', variable: 'attribute', attributeKey: 'x', rangeMode: 'data',
    });

    expect(result.legend.kind === 'variable' && result.legend.stops[0].label).toBe('-1e+308');
    expect(result.legend.kind === 'variable' && result.legend.stops.at(-1)?.label).toBe('1e+308');
    expect(result.legend.kind === 'variable' && result.legend.stops.map(({ label }) => Number(label)).every(Number.isFinite)).toBe(true);
    expect(result.colorsByRowId.get('v0')).toBe('#30123b');
    expect(result.colorsByRowId.get('v1')).toBe('#7a0402');
  });

  it('keeps midpoint and tail colors ordered when the naive span overflows', () => {
    const result = mapBlastHoleColors(sampleHoles([-1.7e308, 0, 1e307, 1.7e308]), {
      kind: 'variable', variable: 'attribute', attributeKey: 'x', rangeMode: 'manual', rangeMin: -1.7e308, rangeMax: 1.7e308,
    });

    expect(result.colorsByRowId.get('v0')).toBe('#30123b');
    expect(result.colorsByRowId.get('v3')).toBe('#7a0402');
    expect(result.colorsByRowId.get('v1')).not.toBe(result.colorsByRowId.get('v0'));
    expect(result.colorsByRowId.get('v2')).not.toBe(result.colorsByRowId.get('v1'));
    for (const color of result.colorsByRowId.values()) expect(color).toMatch(finiteColor);
  });

  it('handles subnormal spans and constants without division by zero', () => {
    const subnormal = mapBlastHoleColors(sampleHoles([0, 5e-324]), {
      kind: 'variable', variable: 'attribute', attributeKey: 'x', rangeMode: 'manual', rangeMin: 0, rangeMax: 5e-324,
    });
    const constant = mapBlastHoleColors(sampleHoles([5e-324, 5e-324]), {
      kind: 'variable', variable: 'attribute', attributeKey: 'x', rangeMode: 'data',
    });

    expect(subnormal.colorsByRowId.get('v0')).toBe('#30123b');
    expect(subnormal.colorsByRowId.get('v1')).toBe('#7a0402');
    expect(constant.colorsByRowId.get('v0')).toBe('#a4fc3b');
    for (const color of [...subnormal.colorsByRowId.values(), ...constant.colorsByRowId.values()]) expect(color).toMatch(finiteColor);
  });

  it('keeps extreme-range saturation counts exact without changing the bounds', () => {
    const result = mapBlastHoleColors(sampleHoles([-1e308, 1e308, 1.5e308]), {
      kind: 'variable', variable: 'attribute', attributeKey: 'x', rangeMode: 'manual', rangeMin: -1e308, rangeMax: 1e308,
    });

    expect(result.legend).toMatchObject({ min: -1e308, max: 1e308, belowCount: 0, aboveCount: 1, missingCount: 0 });
  });
});
