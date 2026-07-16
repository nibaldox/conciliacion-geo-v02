import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createElement } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from '../../../i18n';
import { computeContourAspectRatio, ContourChart } from '../ContourChart';
import type { ContourData } from '../../../api/types';

let meshContoursCalls: Array<{ meshId: string | null; interval: number; resolution: number }> = [];

vi.mock('react-chartjs-2', () => ({
  Line: (props: { data: { datasets?: unknown[] } }) =>
    createElement('div', {
      'data-testid': 'mock-line',
      'data-dataset-count': String(props.data?.datasets?.length ?? 0),
    }),
}));

vi.mock('../../../api/hooks', () => ({
  useMeshContours: (meshId: string | null, interval: number, resolution: number) => {
    meshContoursCalls.push({ meshId, interval, resolution });
    if (meshId === 'topo-id') {
      return {
        data: {
          bounds: { xmin: 0, xmax: 100, ymin: 0, ymax: 100 },
          elevation_min: 0,
          elevation_max: 10,
          interval,
          lines: [{ elevation: 5, segments: [[[0, 0], [100, 100]]] }],
        } satisfies ContourData,
        isLoading: false,
        error: null,
      };
    }
    if (meshId === 'design-id') {
      return {
        data: {
          bounds: { xmin: 0, xmax: 100, ymin: 0, ymax: 100 },
          elevation_min: 0,
          elevation_max: 10,
          interval,
          lines: [{ elevation: 7, segments: [[[0, 100], [100, 0]]] }],
        } satisfies ContourData,
        isLoading: false,
        error: null,
      };
    }
    return { data: undefined, isLoading: false, error: null };
  },
  useSections: () => ({ data: [] }),
  useReferenceLines: () => ({ data: { lines: [] }, isLoading: false, error: null }),
}));

vi.mock('../../../stores/session', () => ({
  useSession: () => ({
    designMeshId: 'design-id',
    topoMeshId: 'topo-id',
  }),
}));

vi.mock('../../../stores/theme', () => ({
  useTheme: () => ({ isDark: false }),
}));

beforeEach(async () => {
  meshContoursCalls = [];
  await i18n.changeLanguage('es');
});

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

describe('<ContourChart /> toolbar', () => {
  it('default state is Topo, 2.0m, Media resolution', () => {
    render(createElement(ContourChart));

    expect(screen.getByRole('radio', { name: /Topografía/i })).toBeChecked();
    expect(screen.getByRole('radio', { name: /Diseño/i })).not.toBeChecked();

    const slider = screen.getByRole('slider', { name: /Intervalo/i });
    expect(slider).toHaveValue('2');

    const select = screen.getByRole('combobox', { name: /Resolución/i });
    expect(select).toHaveValue('medium');

    expect(meshContoursCalls).toContainEqual({ meshId: 'topo-id', interval: 2, resolution: 2 });
    expect(meshContoursCalls).not.toContainEqual({ meshId: 'design-id', interval: 2, resolution: 2 });
  });

  it('radio switches the active mesh id', async () => {
    render(createElement(ContourChart));
    meshContoursCalls = [];

    const designRadio = screen.getByRole('radio', { name: /Diseño/i });
    await userEvent.click(designRadio);

    expect(designRadio).toBeChecked();
    expect(meshContoursCalls).toContainEqual({ meshId: 'design-id', interval: 2, resolution: 2 });
    expect(meshContoursCalls).not.toContainEqual({ meshId: 'topo-id', interval: 2, resolution: 2 });
  });

  it('interval slider re-renders with new step', async () => {
    render(createElement(ContourChart));
    meshContoursCalls = [];

    const slider = screen.getByRole('slider', { name: /Intervalo/i });
    fireEvent.change(slider, { target: { value: '4.5' } });

    expect(meshContoursCalls).toContainEqual({ meshId: 'topo-id', interval: 4.5, resolution: 2 });
  });
});
