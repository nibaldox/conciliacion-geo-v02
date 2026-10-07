import { describe, it, expect } from 'vitest';
import {
  toSectionMeta,
  toProfileLines,
  toBench,
  toBenches,
  toDesignBenchStatuses,
  toComparisonBenchStatuses,
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
  it('rejects a non-finite northing even when the easting is valid', () => {
    expect(toSectionMeta(makeSection({ origin: [1000, Infinity] })).origin).toEqual([0, 0]);
  });

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
  it('drops points with non-finite elevations and retains valid zero coordinates', () => {
    const lines = toProfileLines(makeProfile({
      design: { distances: [0, 10, 20], elevations: [0, Infinity, NaN] },
      topo: null,
    }));
    expect(lines).toEqual([{ kind: 'design', points: [{ distance: 0, elevation: 0 }] }]);
  });

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

  it('preserves finite spill geometry and zero measurements', () => {
    const bench = toBench({
      ...rawBench,
      spill_width: 0,
      spill_start_distance: 12,
      spill_start_elevation: 0,
      floor_elevation: 85,
    }, makeComparison({ bench_score: 75 }));
    expect(bench.spillWidth).toBe(0);
    expect(bench.spillStartDistance).toBe(12);
    expect(bench.spillStartElevation).toBe(0);
    expect(bench.floorElevation).toBe(85);
    expect(bench.benchScore).toBe(75);
    expect([bench.designHeight, bench.designAngle, bench.designBerm]).toEqual([15, 65, 8]);
    expect([bench.deltaCrest, bench.deltaToe]).toEqual([0, 0]);
  });

  it.each([undefined, null, NaN, Infinity, -Infinity])(
    'discards missing or non-finite spill geometry (%s)',
    (value) => {
      const bench = toBench({
        ...rawBench,
        spill_width: value,
        spill_start_distance: value,
        spill_start_elevation: value,
        floor_elevation: value,
      }, null);
      expect(bench.spillWidth).toBeNull();
      expect(bench.spillStartDistance).toBeNull();
      expect(bench.spillStartElevation).toBeNull();
      expect(bench.floorElevation).toBeNull();
    },
  );

  it.each([0, -10])('discards a non-positive floor elevation (%s)', (value) => {
    expect(toBench({ ...rawBench, floor_elevation: value }, null).floorElevation).toBeNull();
  });

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

  it('joins benches using the explicit topographic bench identity', () => {
    const comparisons = [
      makeComparison({ section: 'S-001', bench_num: 11, bench_num_topo: 1, height_status: 'CUMPLE' }),
      makeComparison({ section: 'OTHER', bench_num: 2, bench_num_topo: 2, height_status: 'NO CUMPLE' }),
    ];
    const benches = toBenches(rawBenches, 'S-001', comparisons);
    expect(benches[0]!.status).toBe('CUMPLE');
    // Second bench has no matching comparison for S-001
    expect(benches[1]!.status).toBe('UNKNOWN');
  });

  it('keeps an EXTRA topo bench separate from a same-number MISSING design bench', () => {
    const raw = {
      bench_number: 2,
      crest_elevation: 2945.0616,
      crest_distance: 7.7877,
      toe_elevation: 2932.9114,
      toe_distance: 12.1525,
      bench_height: 12.1525,
      face_angle: 69.4825,
      berm_width: 14.9097,
      is_ramp: false,
    };
    const comparisons = [
      makeComparison({
        type: 'MISSING', bench_num: 2, bench_num_topo: null,
        height_real: null, angle_real: null, berm_real: null,
        height_design: 15, angle_design: 74.8, berm_design: 9.4,
        delta_crest: null, delta_toe: null,
      }),
      makeComparison({
        type: 'EXTRA', bench_num: 999, bench_num_topo: 2,
        height_design: null, angle_design: null, berm_design: null,
        height_real: 12.15, angle_real: 69.5, berm_real: 14.91,
        delta_crest: null, delta_toe: null,
      }),
    ];

    const [bench] = toBenches([raw], 'S-001', comparisons);
    expect(bench).toMatchObject({
      benchNumber: 2,
      height: 12.1525,
      faceAngle: 69.4825,
      bermWidth: 14.9097,
      matched: false,
      designAngle: null,
      designBerm: null,
      deltaCrest: null,
      deltaToe: null,
    });
  });

  it('joins a MATCH when design and topo bench numbers differ', () => {
    const comparison = makeComparison({
      bench_num: 1,
      bench_num_topo: 2,
      angle_design: 74.8,
      berm_design: 9.4,
      delta_crest: 0.25,
      delta_toe: -0.5,
    });
    const [bench] = toBenches([rawBenches[1]!], 'S-001', [comparison]);
    expect(bench).toMatchObject({
      benchNumber: 2,
      matched: true,
      designAngle: 74.8,
      designBerm: 9.4,
      deltaCrest: 0.25,
      deltaToe: -0.5,
    });
  });

  it('infers a unique legacy comparison from its rounded real measurements', () => {
    const raw = {
      bench_number: 2,
      crest_elevation: 2945.0616,
      crest_distance: 7.7877,
      toe_elevation: 2932.9114,
      toe_distance: 12.1525,
      bench_height: 12.1525,
      face_angle: 69.4825,
      berm_width: 14.9097,
      is_ramp: false,
    };
    const legacyExtra = makeComparison({
      type: 'EXTRA', bench_num: 999,
      height_design: null, angle_design: null, berm_design: null,
      height_real: 12.15, angle_real: 69.5, berm_real: 14.91,
      delta_crest: null, delta_toe: null,
    });

    const [bench] = toBenches([raw], 'S-001', [legacyExtra]);
    expect(bench).toMatchObject({
      benchNumber: 2,
      matched: false,
      faceAngle: 69.4825,
      bermWidth: 14.9097,
      designAngle: null,
      designBerm: null,
      deltaCrest: null,
      deltaToe: null,
    });
  });

  it('leaves legacy comparisons unassociated when multiple topo benches share the fingerprint', () => {
    const first = { ...rawBenches[0]!, bench_height: 12.15, face_angle: 69.5, berm_width: 14.91 };
    const second = { ...first, bench_number: 2 };
    const legacyExtra = makeComparison({
      type: 'EXTRA', bench_num: 999,
      height_design: null, angle_design: null, berm_design: null,
      height_real: 12.15, angle_real: 69.5, berm_real: 14.91,
    });

    const benches = toBenches([first, second], 'S-001', [legacyExtra]);
    expect(benches.every((bench) => !bench.matched && bench.designAngle === null)).toBe(true);
  });

  it('leaves a legacy topo bench unassociated when multiple rows share its fingerprint', () => {
    const raw = { ...rawBenches[1]!, bench_height: 12.15, face_angle: 69.5, berm_width: 14.91 };
    const first = makeComparison({
      type: 'EXTRA', bench_num: 999,
      height_design: null, angle_design: null, berm_design: null,
      height_real: 12.15, angle_real: 69.5, berm_real: 14.91,
    });
    const second = { ...first, bench_num: 998 };

    const [bench] = toBenches([raw], 'S-001', [first, second]);
    expect(bench).toMatchObject({ matched: false, designAngle: null, designBerm: null });
  });

  it('does not infer a legacy association when the real fingerprint is incomplete or non-finite', () => {
    const raw = { ...rawBenches[1]!, bench_height: 15, face_angle: 70, berm_width: 8 };
    const base = makeComparison({
      type: 'EXTRA', bench_num: 999,
      height_design: null, angle_design: null, berm_design: null,
      height_real: 15, angle_real: 70, berm_real: 8,
    });

    const [missingMeasurement] = toBenches([raw], 'S-001', [{ ...base, berm_real: null }]);
    const [nonFiniteMeasurement] = toBenches(
      [{ ...raw, berm_width: Number.NaN }],
      'S-001',
      [base],
    );

    expect(missingMeasurement).toMatchObject({ matched: false, designAngle: null, designBerm: null });
    expect(nonFiniteMeasurement).toMatchObject({ matched: false, bermWidth: null, designAngle: null });
  });

  it('leaves duplicate explicit topo identities unassociated', () => {
    const comparisons = [
      makeComparison({ bench_num: 1, bench_num_topo: 2 }),
      makeComparison({ bench_num: 3, bench_num_topo: 2 }),
    ];
    const [bench] = toBenches([rawBenches[1]!], 'S-001', comparisons);
    expect(bench).toMatchObject({ matched: false, designAngle: null, designBerm: null });
  });

  it('handles null comparisons gracefully', () => {
    const benches = toBenches(rawBenches, 'S-001', null);
    expect(benches).toHaveLength(2);
    expect(benches.every((b) => b.status === 'UNKNOWN')).toBe(true);
  });
});

// ─── toProfileViewModel ─────────────────────────────────────

describe('toProfileViewModel', () => {
  it('preserves design identities, backend tolerance tiers, and missing banks without including extras', () => {
    const statuses = toDesignBenchStatuses([
      makeComparison({ bench_num: 4, bench_num_topo: 2, level: '2932', height_status: 'FUERA DE TOLERANCIA' }),
      makeComparison({ bench_num: 5, type: 'MISSING', bench_num_topo: null, level: '2917', height_status: 'NO CONSTRUIDO', angle_status: '-', berm_status: 'FALTA BANCO' }),
      makeComparison({ bench_num: 999, type: 'EXTRA', bench_num_topo: 3 }),
      makeComparison({ section: 'OTHER', bench_num: 9, level: '2800' }),
      makeComparison({ bench_num: 6, bench_num_topo: 4, height_status: '-', angle_status: '-', berm_status: '-' }),
    ], 'S-001');

    expect(statuses).toEqual([
      { sectionName: 'S-001', designBenchNumber: 4, designElevation: 2932, status: 'FUERA', hasTopo: true },
      { sectionName: 'S-001', designBenchNumber: 5, designElevation: 2917, status: 'NO_CUMPLE', hasTopo: false },
      { sectionName: 'S-001', designBenchNumber: 6, designElevation: 4040, status: 'UNKNOWN', hasTopo: true },
    ]);
  });

  it('keeps EXTRA as an additional topo status without a design id or elevation', () => {
    const rows = toComparisonBenchStatuses([
      makeComparison({ bench_num: 999, type: 'EXTRA', bench_num_topo: 3, height_status: 'NO CUMPLE' }),
    ], 'S-001');
    expect(rows).toEqual([{
      sectionName: 'S-001', designBenchNumber: null, designElevation: null,
      status: 'NO_CUMPLE', hasTopo: true, isAdditional: true,
    }]);
  });

  it('preserves section elevation bounds when supplied', () => {
    const vm = toProfileViewModel(
      makeProfile({ floor_elevation: 0, crest_elevation_max: 100 }),
      makeSection(),
      [],
    );
    expect(vm.floorElevation).toBe(0);
    expect(vm.crestElevationMax).toBe(100);
    expect(vm.horizontalDeviation).toBeNull();
  });

  it('preserves the horizontal deviation payload for the chart', () => {
    const horizontalDeviation: NonNullable<ProfileDataDto['horizontal_deviation']> = {
      unit: 'm',
      method: 'horizontal_at_equal_elevation',
      direction: 'positive_overbreak_negative_underbreak',
      thresholds: { within: 1, moderate: 1.8, severe: 3 },
      points: [],
      samples: [],
      summary: { measured: 0, total: 0, within_percent: null, max_abs_deviation: null },
      warnings: [],
    };
    const vm = toProfileViewModel(
      makeProfile({ horizontal_deviation: horizontalDeviation }),
      makeSection(),
      [],
    );
    expect(vm.horizontalDeviation).toBe(horizontalDeviation);
  });

  it('preserves per-surface profile warnings without translating them into compliance status', () => {
    const vm = toProfileViewModel(
      makeProfile({ profile_warnings: { design: ['disconnected_profile_components'], topo: [] } }),
      makeSection(),
      [],
    );
    expect(vm.profileWarnings).toEqual({ design: ['disconnected_profile_components'], topo: [] });
    expect(vm.benches).toEqual([]);
  });

  it('assembles the full view model from a profile + section + comparisons', () => {
    const section = makeSection();
    const profile = makeProfile({
      benches_topo: [
        { bench_number: 1, crest_elevation: 100, crest_distance: 5, toe_elevation: 85, toe_distance: 15, bench_height: 15, face_angle: 65, berm_width: 8, is_ramp: false },
      ],
    });
    const comparisons = [makeComparison({ section: 'S-001', bench_num: 1, bench_num_topo: 1 })];

    const vm = toProfileViewModel(profile, section, comparisons);
    expect(vm.section).toEqual(toSectionMeta(section));
    expect(vm.lines.length).toBeGreaterThan(0);
    expect(vm.benches).toHaveLength(1);
    expect(vm.benches[0]!.status).toBe('CUMPLE');
    expect(vm.benches[0]!.designBenchNumber).toBe(1);
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
