import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BlastSimulationPanel } from './BlastSimulationPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'es' },
  }),
}));

vi.mock('../../api/hooks', () => ({
  useCreateBlastSimulation: vi.fn(),
  extractSimulationErrorDiagnostics: (error: unknown) => {
    if (!error) return null;
    const resp = (error as { response?: { data?: unknown } }).response;
    const data = resp?.data ?? error;
    const detail = (data as { detail?: Record<string, unknown> }).detail ?? data;
    if (!detail || typeof detail !== 'object') return null;
    const d = detail as Record<string, unknown>;
    if (typeof d.error_code !== 'string') return null;
    return {
      error_code: d.error_code as string,
      message: (d.message as string) ?? '',
      details: (d.details as Record<string, unknown>) ?? {},
    };
  },
}));

import { useCreateBlastSimulation } from '../../api/hooks';

type MutationShape = {
  mutateAsync: (body: unknown) => Promise<unknown>;
  isPending: boolean;
  isError: boolean;
  error: unknown;
};

function mockMutation(overrides: Partial<MutationShape> = {}): MutationShape {
  return {
    mutateAsync: vi.fn().mockResolvedValue({ simulation_id: 'sim-1' }),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useCreateBlastSimulation).mockReturnValue(mockMutation() as never);
});

function fillForm() {
  // Fill all numeric inputs in DOM order: xMin, yMin, zMin, xMax, yMax,
  // zMax, voxelSize, then attenuation, regularization, coupling (in the
  // kernel fieldset).
  const inputs = screen.getAllByRole('spinbutton');
  const values = ['0', '0', '0', '10', '10', '10', '1.0', '2.0', '0.5', '0.85'];
  values.forEach((v, i) => {
    fireEvent.change(inputs[i], { target: { value: v } });
  });
}

describe('BlastSimulationPanel', () => {
  it('renders title and uncalibrated warning', () => {
    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    expect(screen.getByText('blast.simulation.title')).toBeTruthy();
    expect(screen.getByText(/warning_uncalibrated/)).toBeTruthy();
  });

  it('shows no_session message when sessionId is null', () => {
    render(<BlastSimulationPanel sessionId={null} geometryConfigurationVersion="2.0" />);
    expect(screen.getByText('blast.simulation.no_session')).toBeTruthy();
  });

  it('starts with all dropdowns on the placeholder option', () => {
    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBe(3);
    selects.forEach((s) => {
      expect((s as HTMLSelectElement).value).toBe('');
    });
  });

  it('disables confirm checkbox while required fields are missing', () => {
    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    const checkbox = screen.getByTestId('sim-confirm-checkbox') as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
  });

  it('enables confirm after all numeric fields + selects are filled', () => {
    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    fillForm();
    // Select energy_mode
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'ABSOLUTE' } });
    fireEvent.change(selects[1], { target: { value: 'STATIC' } });
    fireEvent.change(selects[2], { target: { value: 'ISOTROPIC' } });
    const checkbox = screen.getByTestId('sim-confirm-checkbox') as HTMLInputElement;
    expect(checkbox.disabled).toBe(false);
  });

  it('clears confirmation when any field is edited after ticking', () => {
    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    fillForm();
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'ABSOLUTE' } });
    fireEvent.change(selects[1], { target: { value: 'STATIC' } });
    fireEvent.change(selects[2], { target: { value: 'ISOTROPIC' } });
    const checkbox = screen.getByTestId('sim-confirm-checkbox') as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(true);
    // Edit attenuation → confirmation clears.
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[7], { target: { value: '3.0' } });
    expect(checkbox.checked).toBe(false);
  });

  it('disables the run button until confirmed', () => {
    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    fillForm();
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'ABSOLUTE' } });
    fireEvent.change(selects[1], { target: { value: 'STATIC' } });
    fireEvent.change(selects[2], { target: { value: 'ISOTROPIC' } });
    const runBtn = screen.getByTestId('sim-run-button') as HTMLButtonElement;
    expect(runBtn.disabled).toBe(true);
    const checkbox = screen.getByTestId('sim-confirm-checkbox') as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(runBtn.disabled).toBe(false);
  });

  it('submits the structured request after confirmation', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      simulation_id: 'sim-xyz',
      summary: {
        accepted_holes: 1, charge_segments: 4, valid_sources: 4,
        invalid_sources: 0, voxel_count: 1000, active_voxels: 1000,
        represented_energy_j: 1.0e8, outside_domain_energy_j: 0.0,
        total_coupled_energy_j: 1.0e8, fraction_represented: 1.0,
        warning_records: 0, blocking_error_records: 0,
        temporal_status: 'NOT_AVAILABLE', energy_mode: 'ABSOLUTE',
      },
      configuration: {},
      grid_metadata: {
        shape: [10, 10, 10], voxel_size_m: 1.0,
        bounds: { x_min: 0, y_min: 0, z_min: 0, x_max: 10, y_max: 10, z_max: 10 },
        axes_order: 'xyz', energy_unit: 'J', dtype: 'float32',
        voxel_count: 1000, voxel_volume_m3: 1.0, npz_sha256: 'abc',
        created_at: '',
      },
      energy_field: {
        represented_energy_j: 1e8, outside_domain_energy_j: 0,
        total_coupled_energy_j: 1e8, fraction_represented: 1.0,
        active_voxels: 1000, max_energy_j: 1e6, mean_energy_j_active: 1e5,
        npz_path: '', energy_unit: 'J',
      },
      plan_slices: [], section_slices: [],
      warnings: [], blocking_errors: [],
      provenance: {
        engine_version: 'blast-sim-1.0.0',
        simulation_configuration_version: '1.0',
        geometry_configuration_version: '2.0',
        explosive_registry_source: 'reg',
        explosive_products_used: ['ANFO'],
        rock_mass_source: 'lab',
        propagation_velocity_source: '',
        assumptions: [], warnings: [],
        accepted_rows_hash: 'hash',
      },
      npz_sha256: 'abc',
    });
    vi.mocked(useCreateBlastSimulation).mockReturnValue({
      mutateAsync, isPending: false, isError: false, error: null,
    } as never);

    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    fillForm();
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'ABSOLUTE' } });
    fireEvent.change(selects[1], { target: { value: 'STATIC' } });
    fireEvent.change(selects[2], { target: { value: 'ISOTROPIC' } });
    fireEvent.click(screen.getByTestId('sim-confirm-checkbox'));
    fireEvent.click(screen.getByTestId('sim-run-button'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const body = mutateAsync.mock.calls[0][0] as Record<string, unknown>;
    expect(body.user_confirmed).toBe(true);
    expect(body.energy_mode).toBe('ABSOLUTE');
    expect((body as { voxel_size_m: number }).voxel_size_m).toBe(1.0);
  });

  it('renders structured diagnostics on HTTP 400', () => {
    const axiosLikeError = {
      response: {
        data: {
          detail: {
            error_code: 'SIMULATION_REJECTED',
            message: 'rejected by operator',
            details: { state: 'REJECTED' },
          },
        },
      },
    };
    vi.mocked(useCreateBlastSimulation).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: true,
      error: axiosLikeError as never,
    } as never);

    render(<BlastSimulationPanel sessionId="sess-1" geometryConfigurationVersion="2.0" />);
    expect(screen.getByText(/SIMULATION_REJECTED/)).toBeTruthy();
  });
});
