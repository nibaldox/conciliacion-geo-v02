import { describe, it, expect } from 'vitest';
import { computeContourAspectRatio } from '../ContourChart';

describe('computeContourAspectRatio', () => {
  it('returns the data natural aspect ratio when bounds are valid', () => {
    // 1831m wide × 2317m tall → dx/dy ≈ 0.7902
    expect(
      computeContourAspectRatio({ xmin: 0, xmax: 1831, ymin: 0, ymax: 2317 }),
    ).toBeCloseTo(0.7902, 3);
  });

  it('returns > 1 for a landscape mesh', () => {
    // 2000m wide × 1000m tall → 2.0
    const ratio = computeContourAspectRatio({
      xmin: 0,
      xmax: 2000,
      ymin: 0,
      ymax: 1000,
    });
    expect(ratio).toBe(2.0);
  });

  it('returns < 1 for a portrait mesh', () => {
    // 1000m wide × 2000m tall → 0.5
    const ratio = computeContourAspectRatio({
      xmin: 0,
      xmax: 1000,
      ymin: 0,
      ymax: 2000,
    });
    expect(ratio).toBe(0.5);
  });

  it('returns 1 (square) when bounds are undefined', () => {
    expect(computeContourAspectRatio(undefined)).toBe(1);
  });

  it('returns 1 (square) when dx is zero — no horizontal extent', () => {
    expect(
      computeContourAspectRatio({ xmin: 500, xmax: 500, ymin: 0, ymax: 1000 }),
    ).toBe(1);
  });

  it('returns 1 (square) when dy is zero — no vertical extent', () => {
    expect(
      computeContourAspectRatio({ xmin: 0, xmax: 1000, ymin: 500, ymax: 500 }),
    ).toBe(1);
  });

  it('returns 1 (square) when bounds are inverted (max < min)', () => {
    // Defensive: if the backend ever returns inverted bounds,
    // we fall back to square rather than rendering a negative
    // or 1/ratio aspect that flips the chart.
    expect(
      computeContourAspectRatio({ xmin: 1000, xmax: 0, ymin: 0, ymax: 1000 }),
    ).toBe(1);
  });

  it('matches the real UTM data from the user screenshot (~1.27)', () => {
    // The screenshot shows:
    //   X: 91,867.4 → 93,698.5 (dx = 1831.1)
    //   Y: 20,221.4 → 22,538.5 (dy = 2317.1)
    // Expected ratio: 0.7901
    const ratio = computeContourAspectRatio({
      xmin: 91867.4,
      xmax: 93698.5,
      ymin: 20221.4,
      ymax: 22538.5,
    });
    expect(ratio).toBeCloseTo(0.7901, 3);
  });
});
