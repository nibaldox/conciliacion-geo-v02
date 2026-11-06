import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS, DEFAULT_TOLERANCES } from './constants';

describe('shared defaults', () => {
  it('uses the agreed detection thresholds', () => {
    expect(DEFAULT_SETTINGS.face_threshold).toBe(30);
    expect(DEFAULT_SETTINGS.berm_threshold).toBe(10);
  });

  it('uses the agreed bench height and berm tolerances', () => {
    expect(DEFAULT_TOLERANCES.bench_height).toEqual({ neg: 2, pos: 2 });
    expect(DEFAULT_TOLERANCES.berm_width).toEqual({ min: 7 });
  });
});
