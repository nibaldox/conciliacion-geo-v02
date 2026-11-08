import { describe, expect, it } from 'vitest';
import {
  PROPOSAL_FLOOR_SPAN_M,
  buildProposalOverlay,
  formatFloor,
  formatFloorStatusCounts,
  formatProposalNumber,
  formatProposalPair,
  formatSignedMeters,
  hasProposalData,
  toProposalBenchState,
  toProposalRow,
  toProposalRows,
  toProposalSessionNotice,
  toProposalProfileRange,
} from '../proposal';
import type { ComparisonResultDto } from '../types';

function makeRow(overrides: Partial<ComparisonResultDto> = {}): ComparisonResultDto {
  return {
    sector: '',
    section: 'S-01',
    bench_num: 2,
    bench_num_topo: 3,
    type: 'MATCH',
    level: '3095',
    height_design: 15,
    height_real: 14.2,
    height_dev: -0.8,
    height_status: 'CUMPLE',
    angle_design: 75,
    angle_real: 73.5,
    angle_dev: -1.5,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 6.4,
    berm_min: 7,
    berm_status: 'FUERA DE TOLERANCIA',
    delta_crest: -0.3,
    delta_toe: 1.1,
    bench_score: 66,
    ...overrides,
  };
}

describe('hasProposalData', () => {
  it('false para filas legacy sin claves de propuesta', () => {
    expect(hasProposalData([makeRow()])).toBe(false);
  });

  it('true cuando hay proposal_status aunque venga failed', () => {
    expect(hasProposalData([makeRow({ proposal_status: 'failed', proposal_error: 'x' })])).toBe(true);
  });

  it('true cuando proposed_source existe aunque sea null', () => {
    expect(hasProposalData([makeRow({ proposed_source: null })])).toBe(true);
  });

  it('false para entrada nula o vacía', () => {
    expect(hasProposalData(null)).toBe(false);
    expect(hasProposalData(undefined)).toBe(false);
    expect(hasProposalData([])).toBe(false);
  });
});

describe('toProposalBenchState', () => {
  it('split_fragment tiene prioridad', () => {
    expect(toProposalBenchState(makeRow({ proposed_exclusion_reason: 'split_fragment', split_bench: true }))).toBe('split_fragment');
  });

  it('MATCH con split_bench es banco partido', () => {
    expect(toProposalBenchState(makeRow({ split_bench: true }))).toBe('split_bench');
  });

  it('razones de exclusión conocidas', () => {
    expect(toProposalBenchState(makeRow({ proposed_exclusion_reason: 'not_excavated' }))).toBe('not_excavated');
    expect(toProposalBenchState(makeRow({ proposed_exclusion_reason: 'section_truncated' }))).toBe('section_truncated');
    expect(toProposalBenchState(makeRow({ proposed_exclusion_reason: 'unmeasured' }))).toBe('unmeasured');
  });

  it('caer a design_bench_state cuando no hay razón', () => {
    expect(toProposalBenchState(makeRow({ design_bench_state: 'excavated' }))).toBe('excavated');
    expect(toProposalBenchState(makeRow({ design_bench_state: 'not_excavated' }))).toBe('not_excavated');
    expect(toProposalBenchState(makeRow({ design_bench_state: 'section_truncated' }))).toBe('section_truncated');
    expect(toProposalBenchState(makeRow({ design_bench_state: 'unmeasured' }))).toBe('unmeasured');
  });

  it('unknown sin razón ni estado conocido', () => {
    expect(toProposalBenchState(makeRow())).toBe('unknown');
    expect(toProposalBenchState(makeRow({ design_bench_state: 'raro' }))).toBe('unknown');
  });
});

describe('toProposalRow / toProposalRows', () => {
  it('mapea pares oficial→propuesta, origen, deuda y piso', () => {
    const row = toProposalRow(makeRow({
      proposed_source: 'guided',
      proposed_height: 15.1,
      proposed_angle: 74.2,
      proposed_delta_crest: -0.1,
      proposed_delta_toe: 0.4,
      proposed_berm: 7.9,
      proposed_bench_score: 92.5,
      proposed_exclusion_reason: 'not_excavated',
      excavation_debt_area_m2: 125.4,
      guided_excavation_debt_area_m2: 130,
      floor_offset_m: 0.3,
      floor_status: 'CUMPLE',
      proposal_status: 'current',
    }));
    expect(row.section).toBe('S-01');
    expect(row.benchLabel).toBe('B2');
    expect(row.state).toBe('not_excavated');
    expect(row.source).toBe('guided');
    expect(row.debtAreaM2).toBe(125.4);
    expect(row.height).toEqual({ official: 14.2, proposed: 15.1, source: null });
    expect(row.angle).toEqual({ official: 73.5, proposed: 74.2, source: null });
    expect(row.deltaCrest).toEqual({ official: -0.3, proposed: -0.1, source: null });
    expect(row.deltaToe).toEqual({ official: 1.1, proposed: 0.4, source: null });
    expect(row.berm).toEqual({ official: 6.4, proposed: 7.9, source: null });
    expect(row.score).toEqual({ official: 66, proposed: 92.5, source: null });
    expect(row.floorOffsetM).toBe(0.3);
    expect(row.floorStatus).toBe('CUMPLE');
    expect(row.error).toBeNull();
  });

  it('deuda cae a guided cuando la oficial falta', () => {
    const row = toProposalRow(makeRow({ guided_excavation_debt_area_m2: 130 }));
    expect(row.debtAreaM2).toBe(130);
  });

  it('piso cae a guided_floor_offset_m y estado por defecto', () => {
    const row = toProposalRow(makeRow({ guided_floor_offset_m: -0.2 }));
    expect(row.floorOffsetM).toBe(-0.2);
    expect(row.floorStatus).toBe('-');
  });

  it('EXTRA etiqueta banco topo adicional', () => {
    const row = toProposalRow(makeRow({ type: 'EXTRA', bench_num: 0, bench_num_topo: 7, proposed_source: null }));
    expect(row.benchLabel).toBe('+7');
    expect(row.isExtra).toBe(true);
    expect(row.benchNumTopo).toBe(7);
    expect(row.source).toBeNull();
  });

  it('MATCH no es EXTRA y expone benchNumTopo', () => {
    const row = toProposalRow(makeRow({ bench_num: 2, bench_num_topo: 3 }));
    expect(row.isExtra).toBe(false);
    expect(row.benchNumTopo).toBe(3);
  });

  it('EXTRA sin bench_num_topo y MISSING sin bench_num muestran —', () => {
    expect(toProposalRow(makeRow({ type: 'EXTRA', bench_num: 0, bench_num_topo: null })).benchLabel).toBe('+—');
    expect(toProposalRow(makeRow({ type: 'MISSING', bench_num: null as unknown as number, bench_num_topo: null })).benchLabel).toBe('—');
  });

  it('origen desconocido y error failed se propagan', () => {
    const row = toProposalRow(makeRow({ proposed_source: 'otro', proposal_status: 'failed', proposal_error: 'asbuilt profile unavailable' }));
    expect(row.source).toBeNull();
    expect(row.error).toBe('asbuilt profile unavailable');
  });

  it('origen mixed se propaga', () => {
    expect(toProposalRow(makeRow({ proposed_source: 'mixed' })).source).toBe('mixed');
  });

  it('origen por magnitud mapea guided/current y normaliza el resto', () => {
    const row = toProposalRow(makeRow({
      proposed_source: 'mixed',
      proposed_height_source: 'guided',
      proposed_angle_source: 'current',
      proposed_crest_source: null,
      proposed_toe_source: 'raro',
      proposed_berm_source: undefined,
    }));
    expect(row.height.source).toBe('guided');
    expect(row.angle.source).toBe('current');
    expect(row.deltaCrest.source).toBeNull();
    expect(row.deltaToe.source).toBeNull();
    expect(row.berm.source).toBeNull();
    expect(row.score.source).toBeNull();
  });

  it('toProposalRows conserva el orden y genera claves únicas', () => {
    const rows = toProposalRows([
      makeRow(),
      makeRow({ type: 'EXTRA', bench_num: 0, bench_num_topo: 9 }),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0]!.key).not.toBe(rows[1]!.key);
  });

  it('toProposalRows tolera entrada nula', () => {
    expect(toProposalRows(null)).toEqual([]);
    expect(toProposalRows(undefined)).toEqual([]);
  });

  it('valores ausentes (undefined) se normalizan a null', () => {
    const row = toProposalRow(makeRow({
      delta_crest: undefined,
      height_real: null,
      proposed_delta_crest: undefined,
      proposed_height: undefined,
      floor_status: null,
      bench_score: undefined,
    }));
    expect(row.deltaCrest).toEqual({ official: null, proposed: null, source: null });
    expect(row.height).toEqual({ official: null, proposed: null, source: null });
    expect(row.floorStatus).toBe('-');
    expect(row.score).toEqual({ official: null, proposed: null, source: null });
  });
});

describe('formateadores', () => {
  it('formatProposalNumber usa coma decimal en es y recorta a 2 decimales', () => {
    expect(formatProposalNumber(null)).toBe('—');
    expect(formatProposalNumber(Number.NaN)).toBe('—');
    expect(formatProposalNumber(78.5)).toBe('78,5');
    expect(formatProposalNumber(10)).toBe('10');
    expect(formatProposalNumber(12.345)).toBe('12,35');
    expect(formatProposalNumber(13.29)).toBe('13,29');
    expect(formatProposalNumber(1234.5)).toBe('1.234,5');
  });

  it('formatProposalNumber usa punto decimal en en', () => {
    expect(formatProposalNumber(78.5, 'en')).toBe('78.5');
    expect(formatProposalNumber(1234.5, 'en')).toBe('1,234.5');
  });

  it('formatProposalPair une oficial y propuesta con formato local', () => {
    expect(formatProposalPair({ official: 14.2, proposed: 15.1 })).toBe('14,2 → 15,1');
    expect(formatProposalPair({ official: null, proposed: 3 })).toBe('— → 3');
    expect(formatProposalPair({ official: 3, proposed: null }, 'en')).toBe('3 → —');
  });

  it('formatProposalPair sufija el origen por magnitud cuando existe', () => {
    expect(formatProposalPair({ official: 14.2, proposed: 15.1, source: 'guided' })).toBe('14,2 → 15,1 (g)');
    expect(formatProposalPair({ official: 6.4, proposed: 7.9, source: 'current' })).toBe('6,4 → 7,9 (o)');
    expect(formatProposalPair({ official: 14.2, proposed: 15.1, source: null })).toBe('14,2 → 15,1');
    expect(formatProposalPair({ official: 14.2, proposed: 15.1, source: 'guided' }, 'en')).toBe('14.2 → 15.1 (g)');
  });

  it('formatSignedMeters firma el offset salvo el cero exacto, con formato local', () => {
    expect(formatSignedMeters(null)).toBe('—');
    expect(formatSignedMeters(0.3)).toBe('+0,3 m');
    expect(formatSignedMeters(-0.42)).toBe('-0,42 m');
    expect(formatSignedMeters(0)).toBe('±0 m');
    expect(formatSignedMeters(0.5, 'en')).toBe('+0.5 m');
    expect(formatSignedMeters(-1.234, 'en')).toBe('-1.23 m');
  });

  it('formatFloor combina offset firmado y estado con formato local', () => {
    expect(formatFloor(null, 'CUMPLE')).toBe('—');
    expect(formatFloor(0.3, 'CUMPLE')).toBe('+0,3 m · CUMPLE');
    expect(formatFloor(-0.6, null)).toBe('-0,6 m');
    expect(formatFloor(0.1, '')).toBe('+0,1 m');
    expect(formatFloor(0.25, 'CUMPLE', 'en')).toBe('+0.25 m · CUMPLE');
  });

  it('formatFloorStatusCounts ordena los estados oficiales y filtra ceros', () => {
    expect(formatFloorStatusCounts({ 'NO CUMPLE': 2, CUMPLE: 7, '-': 3 })).toEqual([
      { status: 'CUMPLE', count: 7 },
      { status: 'NO CUMPLE', count: 2 },
      { status: '-', count: 3 },
    ]);
    expect(formatFloorStatusCounts({ CUMPLE: 0, '-': 0 })).toEqual([]);
    expect(formatFloorStatusCounts({ raro: 4, CUMPLE: 1 })).toEqual([
      { status: 'CUMPLE', count: 1 },
      { status: 'raro', count: 4 },
    ]);
  });
});

describe('toProposalSessionNotice', () => {
  const sections = ['S-01', 'S-02', 'S-03'];

  it('respuesta nula → not_computed con todas las secciones pendientes', () => {
    const notice = toProposalSessionNotice(null, sections);
    expect(notice.kind).toBe('not_computed');
    expect(notice.missingSections).toEqual(sections);
    expect(notice.failedRows).toBe(0);
    expect(notice.notComputedRows).toBe(0);
  });

  it('summary nulo → not_computed y todas las secciones faltan', () => {
    const notice = toProposalSessionNotice({
      proposal_status: 'not_computed',
      n_failed_rows: 0,
      n_not_computed_rows: 12,
      summary: null,
    }, sections);
    expect(notice.kind).toBe('not_computed');
    expect(notice.missingSections).toEqual(sections);
    expect(notice.notComputedRows).toBe(12);
  });

  it('partial reporta las secciones sin propuesta', () => {
    const notice = toProposalSessionNotice({
      proposal_status: 'partial',
      n_failed_rows: 2,
      n_not_computed_rows: 3,
      summary: {
        by_section: { 'S-01': {} as never },
      } as never,
    }, sections);
    expect(notice.kind).toBe('partial');
    expect(notice.missingSections).toEqual(['S-02', 'S-03']);
    expect(notice.failedRows).toBe(2);
    expect(notice.notComputedRows).toBe(3);
  });

  it('current sin secciones faltantes', () => {
    const notice = toProposalSessionNotice({
      proposal_status: 'current',
      n_failed_rows: 0,
      n_not_computed_rows: 0,
      summary: {
        by_section: { 'S-01': {}, 'S-02': {}, 'S-03': {} } as never,
      } as never,
    }, sections);
    expect(notice.kind).toBe('current');
    expect(notice.missingSections).toEqual([]);
  });
});

describe('buildProposalOverlay', () => {
  const designBenches = [
    { benchNumber: 1, crestDistance: 20, toeDistance: 10, toeElevation: 3080, bermWidth: 8 },
    { benchNumber: 2, crestDistance: 40, toeDistance: 30, toeElevation: 3065, bermWidth: null },
    { benchNumber: 3, crestDistance: 50, toeDistance: 60, toeElevation: 3050, bermWidth: 6 },
  ];

  it('marca la pata guiada y el piso local con span de berma', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 1, guided_delta_toe: 1.4, floor_offset_m: 0.3 }),
    ], designBenches);
    expect(overlay.toeMarkers).toEqual([{ x: 11.4, y: 3080.3 }]);
    expect(overlay.floorSegments).toHaveLength(1);
    expect(overlay.floorSegments[0]!.x0).toBeCloseTo(11.4, 2);
    expect(overlay.floorSegments[0]!.x1).toBeCloseTo(3.4, 2);
    expect(overlay.floorSegments[0]!.elevation).toBe(3080.3);
  });

  it('sin offset de piso la marca usa la cota de pata y no hay segmento', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 1, guided_delta_toe: 1.4 }),
    ], designBenches);
    expect(overlay.toeMarkers).toEqual([{ x: 11.4, y: 3080 }]);
    expect(overlay.floorSegments).toEqual([]);
  });

  it('offset no finito se trata como ausente', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 1, guided_delta_toe: 1, floor_offset_m: Number.NaN }),
    ], designBenches);
    expect(overlay.toeMarkers).toEqual([{ x: 11, y: 3080 }]);
    expect(overlay.floorSegments).toEqual([]);
  });

  it('floor_offset ausente cae a guided_floor_offset_m', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 1, floor_offset_m: null, guided_floor_offset_m: 0.5 }),
    ], designBenches);
    expect(overlay.floorSegments).toEqual([{ x0: 10, x1: 2, elevation: 3080.5 }]);
    expect(overlay.toeMarkers).toEqual([]);
  });

  it('berma nula usa el span por defecto', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 2, floor_offset_m: 0.2 }),
    ], designBenches);
    expect(overlay.floorSegments).toEqual([
      { x0: 30, x1: 30 - PROPOSAL_FLOOR_SPAN_M, elevation: 3065.2 },
    ]);
  });

  it('banco invertido (cresta antes de la pata) usa signo negativo', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 3, guided_delta_toe: 2, floor_offset_m: -0.4, berm_design: 6 }),
    ], designBenches);
    expect(overlay.toeMarkers).toEqual([{ x: 58, y: 3049.6 }]);
    expect(overlay.floorSegments).toEqual([{ x0: 58, x1: 64, elevation: 3049.6 }]);
  });

  it('EXTRA y bancos sin diseño se ignoran', () => {
    const overlay = buildProposalOverlay([
      makeRow({ type: 'EXTRA', bench_num: 0, bench_num_topo: 9, guided_delta_toe: 1 }),
      makeRow({ bench_num: 99, guided_delta_toe: 1 }),
    ], designBenches);
    expect(overlay.toeMarkers).toEqual([]);
    expect(overlay.floorSegments).toEqual([]);
  });

  it('delta_toe no finito no genera marca', () => {
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 1, guided_delta_toe: Number.NaN }),
    ], designBenches);
    expect(overlay.toeMarkers).toEqual([]);
  });
});

describe('buildProposalOverlay · S-46 (piso hasta la cresta inferior o el fin del perfil)', () => {
  const s46Benches = [
    { benchNumber: 1, crestDistance: -18.15, toeDistance: -12.69, toeElevation: 3080, bermWidth: 6.66 },
    { benchNumber: 2, crestDistance: 0, toeDistance: 4.04, toeElevation: 3065, bermWidth: 12.69 },
  ];
  const s46Range = { xMin: -18.15, xMax: 10 };

  function s46Row(
    bench: number,
    deltaToe: number,
    floorOffset: number,
    berm: number,
    extra: Partial<ComparisonResultDto> = {},
  ): ComparisonResultDto {
    return makeRow({
      section: 'S-46',
      bench_num: bench,
      guided_delta_toe: deltaToe,
      floor_offset_m: floorOffset,
      berm_design: berm,
      ...extra,
    });
  }

  it('B1: desde la pata guiada (≈-16,2) hasta la cresta del banco inferior (0) a cota 3080,9', () => {
    const overlay = buildProposalOverlay([
      s46Row(1, 3.49, 0.9, 6.66),
    ], s46Benches, s46Range);
    expect(overlay.floorSegments).toHaveLength(1);
    const b1 = overlay.floorSegments[0]!;
    expect(b1.x0).toBeCloseTo(-16.18, 2);
    expect(b1.x1).toBeCloseTo(0, 2);
    expect(b1.x1).toBeGreaterThan(b1.x0);
    expect(b1.elevation).toBeCloseTo(3080.9, 2);
  });

  it('B2 (último banco): desde la pata guiada (≈5,7) hasta el extremo del perfil (10) a cota 3064,79', () => {
    const overlay = buildProposalOverlay([
      s46Row(2, -1.63, -0.21, 12.69),
    ], s46Benches, s46Range);
    const b2 = overlay.floorSegments[0]!;
    expect(b2.x0).toBeCloseTo(5.67, 2);
    expect(b2.x1).toBeCloseTo(10, 2);
    expect(b2.elevation).toBeCloseTo(3064.79, 2);
  });

  it('prioriza la cresta guiada del banco inferior cuando existe', () => {
    const overlay = buildProposalOverlay([
      s46Row(1, 3.49, 0.9, 6.66),
      s46Row(2, -1.63, -0.21, 12.69, { guided_delta_crest: -1 }),
    ], s46Benches, s46Range);
    const b1 = overlay.floorSegments[0]!;
    expect(b1.x1).toBeCloseTo(1, 2);
  });

  it('ningún segmento cruza la cara de otro banco ni sale del rango del perfil', () => {
    const overlay = buildProposalOverlay([
      s46Row(1, 3.49, 0.9, 6.66),
      s46Row(2, -1.63, -0.21, 12.69),
    ], s46Benches, s46Range);
    const [b1, b2] = overlay.floorSegments;
    expect(Math.max(b1!.x0, b1!.x1)).toBeLessThanOrEqual(0);
    expect(Math.min(b1!.x0, b1!.x1)).toBeGreaterThan(-18.15);
    expect(Math.max(b2!.x0, b2!.x1)).toBeLessThanOrEqual(10);
    expect(overlay.toeMarkers[0]!.x).toBeCloseTo(-16.18, 2);
    expect(overlay.toeMarkers[0]!.y).toBeCloseTo(3080.9, 2);
    expect(overlay.toeMarkers[1]!.x).toBeCloseTo(5.67, 2);
    expect(overlay.toeMarkers[1]!.y).toBeCloseTo(3064.79, 2);
  });

  it('la cresta inferior fuera del rango del perfil se recorta al rango', () => {
    const benches = [
      ...s46Benches,
      { benchNumber: 3, crestDistance: 15, toeDistance: 19.7, toeElevation: 3050, bermWidth: 8 },
    ];
    const overlay = buildProposalOverlay([
      s46Row(2, -1.63, -0.21, 12.69),
    ], benches, s46Range);
    const b2 = overlay.floorSegments[0]!;
    expect(b2.x1).toBeCloseTo(10, 2);
  });

  it('sin rango conocido ni banco inferior conserva el ancho de berma como respaldo', () => {
    const overlay = buildProposalOverlay([
      s46Row(2, -1.63, -0.21, 12.69),
    ], s46Benches);
    const b2 = overlay.floorSegments[0]!;
    expect(b2.x1).toBeCloseTo(18.36, 2);
  });

  it('sin delta guiada el piso parte de la pata de diseño hasta la cresta inferior', () => {
    const overlay = buildProposalOverlay([
      makeRow({ section: 'S-46', bench_num: 1, floor_offset_m: 0.9, berm_design: 6.66 }),
    ], s46Benches, s46Range);
    const b1 = overlay.floorSegments[0]!;
    expect(b1.x0).toBeCloseTo(-12.69, 2);
    expect(b1.x1).toBeCloseTo(0, 2);
  });

  it('banco con signo positivo ancla en la cresta inferior', () => {
    const benches = [
      { benchNumber: 1, crestDistance: 20, toeDistance: 10, toeElevation: 3080, bermWidth: 8 },
      { benchNumber: 2, crestDistance: 6, toeDistance: 0, toeElevation: 3065, bermWidth: 8 },
    ];
    const overlay = buildProposalOverlay([
      makeRow({ bench_num: 1, guided_delta_toe: 1.4, floor_offset_m: 0.3, berm_design: 8 }),
    ], benches);
    const seg = overlay.floorSegments[0]!;
    expect(seg.x0).toBeCloseTo(11.4, 2);
    expect(seg.x1).toBeCloseTo(6, 6);
  });

  it('banco con signo positivo sin inferior llega al extremo mínimo del perfil', () => {
    const overlay = buildProposalOverlay([
      makeRow({ section: 'S-46', bench_num: 1, floor_offset_m: 0.5 }),
    ], [{ benchNumber: 1, crestDistance: 20, toeDistance: 10, toeElevation: 3080, bermWidth: 8 }],
      { xMin: 4, xMax: 22 });
    expect(overlay.floorSegments[0]!.x1).toBeCloseTo(4, 2);
  });
});

describe('toProposalProfileRange', () => {
  it('une las distancias finitas de todas las líneas', () => {
    const range = toProposalProfileRange([
      { kind: 'design', points: [{ distance: -18.15, elevation: 3095 }, { distance: 0, elevation: 3080 }] },
      { kind: 'topo', points: [{ distance: -16.4, elevation: 3081 }, { distance: Number.NaN, elevation: 3080 }] },
    ]);
    expect(range).toEqual({ xMin: -18.15, xMax: 0 });
  });

  it('sin distancias finitas devuelve null', () => {
    expect(toProposalProfileRange([])).toBeNull();
    expect(toProposalProfileRange([{ kind: 'topo', points: [] }])).toBeNull();
  });
});
