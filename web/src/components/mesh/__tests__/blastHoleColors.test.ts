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
      'charge', 'powderFactor', 'collarElevation', 'hardness', 'diameter', 'hardnessIndex',
      'penetrationRate', 'depth', 'inclination', 'attribute',
    ]);
  });

  it('recognizes hardness aliases when deciding whether the variable is available', () => {
    expect(getAvailableBlastHoleVariables([hole('upper', { Dureza: 'Roca media' })])).toContain('hardness');
    expect(getAvailableBlastHoleVariables([hole('english', { hardness: 'Roca dura' })])).toContain('hardness');
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
