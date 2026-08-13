import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import i18n from '../../../i18n';
import { BlastCorrelation } from '../BlastCorrelation';
import type { BlastCorrelationRow } from '../../../api/types';

beforeAll(async () => {
  await i18n.changeLanguage('es');
});

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
  useUploadBlastCsv: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
  })),
  useBlastHolesBySession: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
  useCreateBlastSimulation: vi.fn(() => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
    reset: vi.fn(),
  })),
  extractSimulationErrorDiagnostics: vi.fn(() => ({})),
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

vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plotly-stub" />,
}));

vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>(
    '../../../api/client',
  );
  return {
    ...actual,
    getSessionId: vi.fn(() => 'phase2-regression-session'),
  };
});

const { useBlastCorrelation } = await import('../../../api/hooks');

function makeRow(): BlastCorrelationRow {
  return {
    section_name: 'S-001',
    num_wells: 5,
    total_kg: 1000,
    mean_abs_deviation: 0.2,
    avg_over_break: 0.5,
    avg_under_break: 0.2,
    n_over: 1,
    n_under: 1,
    pf_vol_avg_kgm3: 0.8,
    pf_area_avg_kgm2: 1.5,
    pf_g_per_ton_avg: 42.5,
    pf_g_per_ton_net_avg: 45.0,
    energy_total_mj: 9000,
    n_pf_valid: 4,
    sector: 'Principal',
    rock_density_used: 2.7,
  };
}

describe('<BlastCorrelation /> Phase 2 panel mount', () => {
  it('renders the energy simulation panel (sim-confirm-checkbox) when rows exist', async () => {
    vi.mocked(useBlastCorrelation).mockReturnValue({
      data: { rows: [makeRow()], carga: [], descarga: [] },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBlastCorrelation>);

    render(<BlastCorrelation />);

    await waitFor(() => {
      expect(screen.getByTestId('sim-confirm-checkbox')).toBeInTheDocument();
    });
  });
});