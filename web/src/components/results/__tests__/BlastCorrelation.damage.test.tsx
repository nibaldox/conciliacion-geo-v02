import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
// Initialise i18next so useTranslation() returns real Spanish strings.
import i18n from '../../../i18n';
import {
  buildDamageTraces,
  DAMAGE_MODEL_MIN_SAMPLES,
  BlastCorrelation,
} from '../BlastCorrelation';
import type {
  BlastCorrelationRow,
  BlastDamagePoint,
  BlastDamageModelFit,
} from '../../../api/types';

// ─── Pure helper: buildDamageTraces ─────────────────────────

describe('buildDamageTraces', () => {
  it('returns an empty array when there are no points', () => {
    expect(buildDamageTraces([], null)).toEqual([]);
  });

  it('emits only the scatter trace (no regression line) when fit is null', () => {
    const points: BlastDamagePoint[] = [
      { section_name: 'S-01', pf_g_per_ton: 80, over_break: 0.5 },
      { section_name: 'S-02', pf_g_per_ton: 90, over_break: 0.7 },
    ];
    const traces = buildDamageTraces(points, null);
    expect(traces).toHaveLength(1);
    expect((traces[0] as { type?: string }).type).toBe('scatter');
    expect((traces[0] as { mode?: string }).mode).toBe('markers');
    // Scatter carries the section names for hover.
    expect((traces[0] as { text?: string[] }).text).toEqual(['S-01', 'S-02']);
  });

  it('overlays the regression line when fit is present and points >= min_samples', () => {
    const points: BlastDamagePoint[] = Array.from(
      { length: DAMAGE_MODEL_MIN_SAMPLES },
      (_, i) => ({
        section_name: `S-${i.toString().padStart(2, '0')}`,
        pf_g_per_ton: 80 + i * 5,
        over_break: 0.4 + i * 0.1,
      }),
    );
    const fit: BlastDamageModelFit = {
      beta0: 0.1,
      beta1: 0.005,
      r_squared: 0.85,
      p_value: 0.02,
      n: points.length,
      confidence: 'MEDIUM',
      ci_beta1_low: 0.001,
      ci_beta1_high: 0.009,
    };

    const traces = buildDamageTraces(points, fit);
    expect(traces).toHaveLength(2);
    // Second trace is the OLS line.
    const line = traces[1] as {
      type?: string;
      mode?: string;
      x?: number[];
      y?: number[];
    };
    expect(line.type).toBe('scatter');
    expect(line.mode).toBe('lines');
    // Line spans the x-range of the points.
    const xMin = Math.min(...points.map((p) => p.pf_g_per_ton));
    const xMax = Math.max(...points.map((p) => p.pf_g_per_ton));
    expect(line.x).toEqual([xMin, xMax]);
    // y = beta0 + beta1 * x at the endpoints.
    expect(line.y).toEqual([fit.beta0 + fit.beta1 * xMin, fit.beta0 + fit.beta1 * xMax]);
  });

  it('does NOT overlay the regression line when points < min_samples even if fit present', () => {
    const points: BlastDamagePoint[] = [
      { section_name: 'S-01', pf_g_per_ton: 80, over_break: 0.5 },
      { section_name: 'S-02', pf_g_per_ton: 90, over_break: 0.7 },
    ];
    const fit: BlastDamageModelFit = {
      beta0: 0.1,
      beta1: 0.005,
      r_squared: 0.5,
      p_value: 0.3,
      n: 2,
      confidence: 'INSUFFICIENT',
      ci_beta1_low: 0,
      ci_beta1_high: 0,
    };
    const traces = buildDamageTraces(points, fit);
    expect(traces).toHaveLength(1);
  });
});

// ─── Component: BlastDamageChart insufficient caption ───────
//
// Mocks both useBlastCorrelation (table rows) and useBlastDamageModel
// (chart points/fit) so the table renders and the chart's insufficient
// caption shows when there are fewer than min_samples points.

vi.mock('../../../api/hooks', () => ({
  useBlastCorrelation: vi.fn(),
  useBlastDamageModel: vi.fn(),
  useSettings: vi.fn(() => ({ data: undefined })),
  useSections: vi.fn(() => ({ data: [] })),
  useUpdateSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUploadBlastCsv: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
  })),
  useBlastHolesBySession: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>(
    '@tanstack/react-query',
  );
  return {
    ...actual,
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  };
});

// react-plotly.js renders a placeholder div in jsdom; we assert on the
// caption and container, not on Plotly's internals.
vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plotly-stub" />,
}));

const { useBlastCorrelation, useBlastDamageModel } = await import('../../../api/hooks');

function mockRows(rows: BlastCorrelationRow[]) {
  vi.mocked(useBlastCorrelation).mockReturnValue({
    data: { rows, tolerance: 2.0, n_sections: rows.length },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useBlastCorrelation>);
}

function mockDamageModel(
  points: BlastDamagePoint[],
  fit: BlastDamageModelFit | null,
) {
  vi.mocked(useBlastDamageModel).mockReturnValue({
    data: { points, fit, x_metric: 'pf_g_per_ton', y_metric: 'over_break' },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useBlastDamageModel>);
}

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

describe('<BlastCorrelation /> damage chart', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => vi.clearAllMocks());

  it('renders the insufficient-samples caption when fewer than 5 points', async () => {
    mockRows([makeRow('S-01')]);
    mockDamageModel(
      [
        { section_name: 'S-01', pf_g_per_ton: 80, over_break: 0.5 },
        { section_name: 'S-02', pf_g_per_ton: 90, over_break: 0.7 },
      ],
      null,
    );

    render(<BlastCorrelation />);
    await waitFor(() => {
      expect(screen.getByTestId('blast-damage-chart')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('blast-damage-insufficient'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Insuficientes secciones para ajustar el modelo (mínimo 5).',
      ),
    ).toBeInTheDocument();
  });

  it('does not render the chart container when there are no points', () => {
    mockRows([makeRow('S-01')]);
    mockDamageModel([], null);
    render(<BlastCorrelation />);
    expect(screen.queryByTestId('blast-damage-chart')).toBeNull();
  });

  it('hides the insufficient caption when 5+ points and a fit are present', async () => {
    const rows = Array.from({ length: 5 }, (_, i) => makeRow(`S-${i.toString().padStart(2, '0')}`));
    mockRows(rows);
    mockDamageModel(
      rows.map((r) => ({
        section_name: r.section_name,
        pf_g_per_ton: 80,
        over_break: 0.5,
      })),
      {
        beta0: 0.1,
        beta1: 0.005,
        r_squared: 0.8,
        p_value: 0.03,
        n: 5,
        confidence: 'MEDIUM',
        ci_beta1_low: 0.001,
        ci_beta1_high: 0.009,
      },
    );

    render(<BlastCorrelation />);
    await waitFor(() => {
      expect(screen.getByTestId('blast-damage-chart')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('blast-damage-insufficient')).toBeNull();
  });
});
