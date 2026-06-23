import { describe, it, expect } from 'vitest';
import { toProfileLines } from '../mapping';
import type { ProfileDataDto } from '../types';

// ─── Fixtures ───────────────────────────────────────────────

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
    reconciled_design_legacy: null,
    reconciled_topo_legacy: null,
    benches_topo: [],
    ...overrides,
  };
}

function findLine(lines: readonly { kind: string }[], kind: string) {
  return lines.find((l) => l.kind === kind);
}

// ─── reconciled_design_legacy ───────────────────────────────

describe('toProfileLines — reconciled_*_legacy mapping', () => {
  it('reads reconciled_design_legacy when present', () => {
    const lines = toProfileLines(
      makeProfile({
        reconciled_design_legacy: { distances: [0, 10], elevations: [3140, 3140] },
      }),
    );
    const rd = findLine(lines, 'reconciled_design');
    expect(rd).toBeDefined();
    expect(rd!.points).toEqual([
      { distance: 0, elevation: 3140 },
      { distance: 10, elevation: 3140 },
    ]);
  });

  it('reads reconciled_topo_legacy when present', () => {
    const lines = toProfileLines(
      makeProfile({
        reconciled_topo_legacy: { distances: [0, 10], elevations: [3140, 3140] },
      }),
    );
    const rt = findLine(lines, 'reconciled_topo');
    expect(rt).toBeDefined();
    expect(rt!.points).toEqual([
      { distance: 0, elevation: 3140 },
      { distance: 10, elevation: 3140 },
    ]);
  });

  it('omits reconciled_design when legacy is null', () => {
    const lines = toProfileLines(
      makeProfile({ reconciled_design_legacy: null }),
    );
    expect(findLine(lines, 'reconciled_design')).toBeUndefined();
  });

  it('omits reconciled_design when legacy is undefined', () => {
    const profile = makeProfile();
    delete profile.reconciled_design_legacy;
    const lines = toProfileLines(profile);
    expect(findLine(lines, 'reconciled_design')).toBeUndefined();
  });

  it('ignores the rich reconciled_design field (guards against regression)', () => {
    // After the fix, the mapper reads ONLY reconciled_design_legacy.
    // Feeding the (soon-to-be-rich) reconciled_design field without the
    // legacy companion must produce NO reconciled_design line — otherwise
    // the old bug (silently reading the wrong shape) has returned.
    const lines = toProfileLines(
      makeProfile({
        reconciled_design: { distances: [0, 10], elevations: [100, 90] },
        reconciled_design_legacy: null,
      }),
    );
    expect(findLine(lines, 'reconciled_design')).toBeUndefined();
  });
});
