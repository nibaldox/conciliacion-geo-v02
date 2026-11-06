import { describe, expect, it } from 'vitest';
import { buildTopoHeightIndex, heightAt } from '../topoSurfaceHeight';

describe('topographic surface heights', () => {
  it('interpolates a sloping plane inside both triangles', () => {
    const index = buildTopoHeightIndex({ x: [0, 10, 0, 10], y: [0, 0, 10, 10], z: [5, 25, 35, 55], faces: [[0, 1, 2], [1, 3, 2]] });
    for (const [x, y] of [[2, 3], [8, 7], [5, 5]]) expect(heightAt(index, x!, y!)).toBeCloseTo(5 + 2 * x! + 3 * y!, 9);
  });

  it('interpolates a steep upper face rather than its nearest vertex', () => {
    const index = buildTopoHeightIndex({ x: [0, 10, 0, 10], y: [0, 0, 10, 10], z: [0, 30, 30, 60], faces: [[0, 1, 2], [1, 3, 2]] });
    expect(heightAt(index, 8, 8)).toBeCloseTo(48, 9);
  });

  it('falls back to the closest vertex outside all triangles', () => {
    const index = buildTopoHeightIndex({ x: [0, 10, 0], y: [0, 0, 10], z: [1, 2, 3], faces: [[0, 1, 2]] });
    expect(heightAt(index, 12, 0)).toBe(2);
  });

  it('uses nearest vertices when faces are absent', () => {
    const index = buildTopoHeightIndex({ x: [0, 10], y: [0, 0], z: [1, 9] });
    expect(heightAt(index, 9, 0)).toBe(9);
  });

  it('falls back to the true closest vertex without stride sampling', () => {
    const x = Array.from({ length: 150001 }, (_, i) => i);
    const index = buildTopoHeightIndex({ x, y: x.map(() => 0), z: x });
    expect(heightAt(index, 100001, 0)).toBe(100001);
  });

  it('handles shared edges, degenerate faces, and translated coordinates', () => {
    const index = buildTopoHeightIndex({ x: [1000000, 1000010, 1000000, 1000010], y: [7000000, 7000000, 7000010, 7000010], z: [0, 20, 30, 50], faces: [[0, 0, 0], [0, 1, 2], [1, 3, 2]] });
    expect(heightAt(index, 1000005, 7000005)).toBeCloseTo(25, 9);
    expect(heightAt(index, 1000010, 7000010)).toBeCloseTo(50, 9);
  });

  it('builds an index for 150000 vertices within one second', () => {
    const x: number[] = [], y: number[] = [], z: number[] = [], faces: number[][] = [];
    for (let i = 0; i < 150000; i++) { x.push(i % 500); y.push(Math.floor(i / 500)); z.push(i % 17); }
    for (let row = 0; row < 299; row++) for (let col = 0; col < 499; col++) {
      const a = row * 500 + col;
      faces.push([a, a + 1, a + 500], [a + 1, a + 501, a + 500]);
    }
    const started = performance.now();
    const index = buildTopoHeightIndex({ x, y, z, faces });
    expect(performance.now() - started).toBeLessThan(1000);
    expect(Number.isFinite(heightAt(index, 12.2, 13.3))).toBe(true);
  });
});
