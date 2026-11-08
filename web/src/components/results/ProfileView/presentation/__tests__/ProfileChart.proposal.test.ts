import { describe, expect, it } from 'vitest';
import { buildProposalTraces } from '../ProfileChart';
import type { ComparisonResultDto } from '../../domain/types';

function makeRow(overrides: Partial<ComparisonResultDto> = {}): ComparisonResultDto {
  return {
    sector: '',
    section: 'S-46',
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

const s46Benches = [
  { benchNumber: 1, crestDistance: -18.15, toeDistance: -12.69, toeElevation: 3080, bermWidth: 6.66 },
  { benchNumber: 2, crestDistance: 0, toeDistance: 4.04, toeElevation: 3065, bermWidth: 12.69 },
  { benchNumber: 3, crestDistance: 10, toeDistance: 14.7, toeElevation: 3050, bermWidth: 8 },
];

const s46Rows: ComparisonResultDto[] = [
  makeRow({
    bench_num: 1,
    guided_delta_toe: 3.49,
    floor_offset_m: 0.9,
    berm_design: 6.66,
  }),
  makeRow({
    bench_num: 2,
    guided_delta_toe: -1.63,
    floor_offset_m: -0.21,
    berm_design: 12.69,
  }),
];

describe('buildProposalTraces · S-46 (sin diagonales entre pisos)', () => {
  it('un solo trazo de piso con separador null entre segmentos', () => {
    const traces = buildProposalTraces(s46Rows, s46Benches);
    const floors = traces.filter((trace) => trace.legendgroup === 'propuesta piso');
    expect(floors).toHaveLength(1);
    const floor = floors[0]!;
    expect(floor.x).toHaveLength(5);
    expect(floor.y).toHaveLength(5);
    expect(floor.x![2]).toBeNull();
    expect(floor.y![2]).toBeNull();
    expect(floor.x![0]).toBeCloseTo(-16.18, 2);
    expect(floor.x![1]).toBeCloseTo(0, 2);
    expect(floor.x![3]).toBeCloseTo(5.67, 2);
    expect(floor.x![4]).toBeCloseTo(10, 2);
    expect(floor.y![0]).toBeCloseTo(3080.9, 2);
    expect(floor.y![1]).toBeCloseTo(3080.9, 2);
    expect(floor.y![3]).toBeCloseTo(3064.79, 2);
    expect(floor.y![4]).toBeCloseTo(3064.79, 2);
  });

  it('cada segmento es horizontal (sin diagonal dentro del segmento)', () => {
    const traces = buildProposalTraces(s46Rows, s46Benches);
    const floor = traces.find((trace) => trace.legendgroup === 'propuesta piso')!;
    const y = floor.y as (number | null)[];
    expect(y[0]).toBeCloseTo(y[1] as number, 6);
    expect(y[3]).toBeCloseTo(y[4] as number, 6);
  });

  it('el trazo de patas guiadas queda en una sola traza de marcadores', () => {
    const traces = buildProposalTraces(s46Rows, s46Benches);
    const toes = traces.filter((trace) => trace.legendgroup === 'propuesta');
    expect(toes).toHaveLength(1);
    expect(toes[0]!.mode).toBe('markers');
    expect(toes[0]!.x![0]).toBeCloseTo(-16.18, 2);
    expect(toes[0]!.x![1]).toBeCloseTo(5.67, 2);
  });
});
