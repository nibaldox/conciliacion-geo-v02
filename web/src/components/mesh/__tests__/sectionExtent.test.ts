import { describe, expect, it } from 'vitest';
import { getSectionExtent } from '../sectionExtent';
import type { SectionResponse } from '../../../api/types';

function section(overrides: Partial<SectionResponse> = {}): SectionResponse {
  return {
    id: 'section-1',
    name: 'S-01',
    origin: [100, 200],
    azimuth: 0,
    length: 40,
    sector: 'Norte',
    ...overrides,
  };
}

describe('getSectionExtent', () => {
  it('uses symmetric station limits and places endpoints along north azimuth', () => {
    expect(getSectionExtent(section())).toEqual({
      lowerStation: -20,
      upperStation: 20,
      start: [100, 180],
      end: [100, 220],
    });
  });

  it('uses backend-compatible asymmetric length_down and length_up limits', () => {
    expect(getSectionExtent(section({
      azimuth: 90,
      length: 99,
      length_down: 8,
      length_up: 22,
    }))).toEqual({
      lowerStation: -8,
      upperStation: 22,
      start: [92, 200],
      end: [122, 200],
    });
  });

  it('falls back to symmetric limits if either asymmetric limit is missing', () => {
    expect(getSectionExtent(section({ length_up: 12 }))).toEqual({
      lowerStation: -20,
      upperStation: 20,
      start: [100, 180],
      end: [100, 220],
    });
  });
});
