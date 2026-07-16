import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import i18n from '../../../i18n';
import {
  buildOverlayHistogram,
  BlastCorrelation,
} from '../BlastCorrelation';
import type { BlastCorrelationRow } from '../../../api/types';

// ─── Pure helper: buildOverlayHistogram ─────────────────────

describe('buildOverlayHistogram', () => {
  it('returns correct counts for a known input', () => {
    const carga = [1, 2, 3];
    const descarga = [2, 3, 4];
    const result = buildOverlayHistogram(carga, descarga, 2);

    expect(result.carga).toEqual(carga);
    expect(result.descarga).toEqual(descarga);
    expect(result.binEdges).toHaveLength(3);
    expect(result.binMidpoints).toHaveLength(2);
    expect(result.countsCarga).toEqual([2, 1]);
    expect(result.countsDescarga).toEqual([1, 2]);
  });

  it('handles empty arrays gracefully', () => {
    const result = buildOverlayHistogram([], [], 20);

    expect(result.carga).toEqual([]);
    expect(result.descarga).toEqual([]);
    expect(result.binEdges).toHaveLength(21);
    expect(result.binMidpoints).toHaveLength(20);
    expect(result.countsCarga).toEqual(new Array(20).fill(0));
    expect(result.countsDescarga).toEqual(new Array(20).fill(0));
  });
});

// ─── Component: histogram section render ────────────────────

vi.mock('../../../api/hooks', () => ({
  useBlastCorrelation: vi.fn(),
  useBlastDamageModel: vi.fn(() => ({
    data: { points: [], fit: null, x_metric: 'pf_g_per_ton', y_metric: 'over_break' },
    isLoading: false,
    error: null,
  })),
  useSettings: vi.fn(() => ({ data: undefined })),
  useSections: vi.fn(() => ({ data: [] })),
  useUpdateSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  };
});

vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plotly-stub" />,
}));

const { useBlastCorrelation } = await import('../../../api/hooks');

function makeRow(name: string): BlastCorrelationRow {
  return {
    section_name: name,
    num_wells: 2,
    total_kg: 400,
    mean_abs_deviation: 0.3,
    avg_over_break: 0.5,
    avg_under_break: 0.2,
    n_over: 1,
    n_under: 1,
    pf_vol_avg_kgm3: 0.9,
    pf_area_avg_kgm2: 2.1,
    pf_g_per_ton_avg: 82.4,
    pf_g_per_ton_net_avg: 88.0,
    energy_total_mj: 9000,
    n_pf_valid: 2,
    sector: 'Principal',
    rock_density_used: 2.7,
  };
}

function mockCorrelation(rows: BlastCorrelationRow[], carga: number[] = [], descarga: number[] = []) {
  vi.mocked(useBlastCorrelation).mockReturnValue({
    data: { rows, tolerance: 2.0, n_sections: rows.length, carga, descarga },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useBlastCorrelation>);
}

describe('<BlastCorrelation /> histogram section', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => vi.clearAllMocks());

  it('renders the histogram section when data has carga/descarga', async () => {
    mockCorrelation(
      [makeRow('S-01')],
      [100, 120, 140, 160],
      [90, 110, 130, 150],
    );

    render(<BlastCorrelation />);
    await waitFor(() => {
      expect(screen.getByTestId('blast-histogram-chart')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Histograma Carga vs Descarga'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('plotly-stub')).toBeInTheDocument();
  });

  it('does not render the histogram section when carga/descarga are absent', () => {
    mockCorrelation([makeRow('S-01')]);
    render(<BlastCorrelation />);
    expect(screen.queryByTestId('blast-histogram-chart')).toBeNull();
  });
});
