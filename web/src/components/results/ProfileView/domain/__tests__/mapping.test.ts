import { describe, it, expect } from 'vitest';
import {
  toSectionMeta,
  toProfileLines,
  toBench,
  toBenches,
  toProfileViewModel,
} from '../mapping';
import type { ComparisonResultDto, ProfileDataDto, SectionResponseDto } from '../types';

// ─── Fixtures ───────────────────────────────────────────────

function makeSection(overrides: Partial<SectionResponseDto> = {}): SectionResponseDto {
  return {
    id: 'sec-1',
    name: 'S-001',
    sector: 'Norte',
    azimuth: 45,
    length: 200,
    origin: [1000, 2000],
    ...overrides,
  };
}

function makeProfile(overrides: Partial<ProfileDataDto> = {}): ProfileDataDto {
  return {
    section_name: 'S-001',
    sector: 'Norte',
    origin: [1000, 2000],
    azimuth: 45,
    design: { distances: [0, 10, 20], elevations: [100, 95, 90] },
    topo: { distances: [0, 10, 20], elevations: [99, 94, 89] },
    reconciled_design: null,
    reconciled_topo: null,
    benches_topo: [],
    ...overrides,
  };
}

function makeComparison(overrides: Partial<ComparisonResultDto> = {}): ComparisonResultDto {
  return {
    sector: 'Norte',
    section: 'S-001',
    bench_num: 1,
    type: 'MATCH',
    level: '4040',
    height_design: 15,
    height_real: 14.8,
    height_dev: -0.2,
    height_status: 'CUMPLE',
    angle_design: 65,
    angle_real: 70,
    angle_dev: 5,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 8.4,
    berm_min: 8,
    berm_status: 'CUMPLE',
    delta_crest: 0,
    delta_toe: 0,
    ...overrides,
  };
}

// ─── toSectionMeta ──────────────────────────────────────────

describe('toSectionMeta', () => {
  it('maps every field', () => {
    const meta = toSectionMeta(makeSection());
    expect(meta).toEqual({
      id: 'sec-1',
      name: 'S-001',
      sector: 'Norte',
      azimuth: 45,
      length: 200,
      origin: [1000, 2000],
    });
  });

  it('coerces a malformed origin to [0, 0]', () => {
    const meta = toSectionMeta(makeSection({ origin: [42] as unknown as [number, number] }));
    expect(meta.origin).toEqual([0, 0]);
  });

  it('coerces NaN origin to [0, 0]', () => {
    const meta = toSectionMeta(makeSection({ origin: [NaN, NaN] }));
    expect(meta.origin).toEqual([0, 0]);
  });
});

// ─── toProfileLines ─────────────────────────────────────────

describe('toProfileLines', () => {
  it('emits a line per non-empty profile', () => {
    const lines = toProfileLines(makeProfile());
    expect(lines.map((l) => l.kind).sort()).toEqual(['design', 'topo']);
  });

  it('skips null profiles', () => {
    const lines = toProfileLines(makeProfile({ design: null, topo: null }));
    expect(lines).toEqual([]);
  });

  it('emits reconciled lines when present', () => {
    const lines = toProfileLines(
      makeProfile({
        reconciled_design_legacy: { distances: [0, 10], elevations: [100, 90] },
        reconciled_topo_legacy: { distances: [0, 10], elevations: [100, 90] },
      }),
    );
    expect(lines.map((l) => l.kind).sort()).toEqual([
      'design', 'reconciled_design', 'reconciled_topo', 'topo',
    ]);
  });

  it('drops points with non-finite coordinates', () => {
    const lines = toProfileLines(
      makeProfile({
        design: { distances: [0, NaN, 20], elevations: [100, 95, 90] },
      }),
    );
    expect(lines[0]!.points).toEqual([
      { distance: 0, elevation: 100 },
      { distance: 20, elevation: 90 },
    ]);
  });

  it('handles mismatched array lengths (uses the shorter)', () => {
    const lines = toProfileLines(
      makeProfile({
        design: { distances: [0, 10, 20, 30], elevations: [100, 95] },
      }),
    );
    expect(lines[0]!.points).toHaveLength(2);
  });
});

// ─── toBench ────────────────────────────────────────────────

describe('toBench', () => {
  const rawBench = {
    bench_number: 1,
    crest_elevation: 100,
    crest_distance: 5,
    toe_elevation: 85,
    toe_distance: 15,
    bench_height: 15,
    face_angle: 65,
    berm_width: 8,
    is_ramp: false,
  };

  it('returns UNKNOWN status when no comparison is given', () => {
    const bench = toBench(rawBench, null);
    expect(bench.status).toBe('UNKNOWN');
    expect(bench.matched).toBe(false);
  });

  it('returns the worst of three statuses when comparison is given', () => {
    const cmp = makeComparison({
      height_status: 'CUMPLE',
      angle_status: 'FUERA DE TOLERANCIA',
      berm_status: 'CUMPLE',
    });
    const bench = toBench(rawBench, cmp);
    expect(bench.status).toBe('FUERA');
    expect(bench.matched).toBe(true);
  });

  it('preserves all numeric fields unchanged', () => {
    const bench = toBench(rawBench, null);
    expect(bench.benchNumber).toBe(1);
    expect(bench.crestElevation).toBe(100);
    expect(bench.crestDistance).toBe(5);
    expect(bench.toeElevation).toBe(85);
    expect(bench.toeDistance).toBe(15);
    expect(bench.height).toBe(15);
    expect(bench.faceAngle).toBe(65);
    expect(bench.bermWidth).toBe(8);
    expect(bench.isRamp).toBe(false);
  });

  it('coerces NaN/Infinity bermWidth to null', () => {
    expect(toBench({ ...rawBench, berm_width: NaN }, null).bermWidth).toBeNull();
    expect(toBench({ ...rawBench, berm_width: Infinity }, null).bermWidth).toBeNull();
  });

  it('keeps bermWidth: 0 as a real measurement (not null)', () => {
    expect(toBench({ ...rawBench, berm_width: 0 }, null).bermWidth).toBe(0);
  });
});

// ─── toBenches ──────────────────────────────────────────────

describe('toBenches', () => {
  const rawBenches = [
    { bench_number: 1, crest_elevation: 100, crest_distance: 5, toe_elevation: 85, toe_distance: 15, bench_height: 15, face_angle: 65, berm_width: 8, is_ramp: false },
    { bench_number: 2, crest_elevation: 85, crest_distance: 15, toe_elevation: 70, toe_distance: 25, bench_height: 15, face_angle: 70, berm_width: 8, is_ramp: false },
  ];

  it('returns an empty array for null rawBenches', () => {
    expect(toBenches(null, 'S-001', [])).toEqual([]);
  });

  it('returns an empty array for empty rawBenches', () => {
    expect(toBenches([], 'S-001', [])).toEqual([]);
  });

  it('joins benches with their matching comparisons by section+number', () => {
    const comparisons = [
      makeComparison({ section: 'S-001', bench_num: 1, height_status: 'CUMPLE' }),
      makeComparison({ section: 'OTHER', bench_num: 2, height_status: 'NO CUMPLE' }),
    ];
    const benches = toBenches(rawBenches, 'S-001', comparisons);
    expect(benches[0]!.status).toBe('CUMPLE');
    // Second bench has no matching comparison for S-001
    expect(benches[1]!.status).toBe('UNKNOWN');
  });

  it('handles null comparisons gracefully', () => {
    const benches = toBenches(rawBenches, 'S-001', null);
    expect(benches).toHaveLength(2);
    expect(benches.every((b) => b.status === 'UNKNOWN')).toBe(true);
  });
});

// ─── toProfileViewModel ─────────────────────────────────────

describe('toProfileViewModel', () => {
  it('assembles the full view model from a profile + section + comparisons', () => {
    const section = makeSection();
    const profile = makeProfile({
      benches_topo: [
        { bench_number: 1, crest_elevation: 100, crest_distance: 5, toe_elevation: 85, toe_distance: 15, bench_height: 15, face_angle: 65, berm_width: 8, is_ramp: false },
      ],
    });
    const comparisons = [makeComparison({ section: 'S-001', bench_num: 1 })];

    const vm = toProfileViewModel(profile, section, comparisons);
    expect(vm.section).toEqual(toSectionMeta(section));
    expect(vm.lines.length).toBeGreaterThan(0);
    expect(vm.benches).toHaveLength(1);
    expect(vm.benches[0]!.status).toBe('CUMPLE');
  });

  it('handles undefined benches_topo (coerces to null)', () => {
    const section = makeSection();
    const profile = makeProfile({ benches_topo: undefined });
    const vm = toProfileViewModel(profile, section, []);
    expect(vm.benches).toEqual([]);
  });

  it('handles undefined comparisons (coerces to empty)', () => {
    const section = makeSection();
    const profile = makeProfile({
      benches_topo: [
        { bench_number: 1, crest_elevation: 100, crest_distance: 5, toe_elevation: 85, toe_distance: 15, bench_height: 15, face_angle: 65, berm_width: 8, is_ramp: false },
      ],
    });
    const vm = toProfileViewModel(profile, section, undefined);
    expect(vm.benches).toHaveLength(1);
    expect(vm.benches[0]!.status).toBe('UNKNOWN');
  });
});
