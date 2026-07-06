import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import i18n from '../../../i18n';
import { BlastDensityControl } from '../BlastCorrelation';

// ─── Mocks ─────────────────────────────────────────────────
//
// The control reads session settings (useSettings), the session sections
// (useSections — to list distinct sectors in the per-sector editor), writes
// settings (useUpdateSettings), and invalidates the blast-correlation +
// blast-damage-model queries (useQueryClient). We mock all of them so the
// test exercises the control's wiring without hitting the network/cache.

const mockInvalidate = vi.fn();
const mockMutate = vi.fn();

vi.mock('../../../api/hooks', () => ({
  useSettings: vi.fn(() => ({ data: undefined })),
  useSections: vi.fn(() => ({ data: [] })),
  useUpdateSettings: vi.fn(() => ({
    mutate: mockMutate,
    isPending: false,
  })),
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: vi.fn(() => ({
      invalidateQueries: mockInvalidate,
    })),
  };
});

// Pull the mocked hooks so we can drive their return values per test.
const { useSettings, useSections } = await import('../../../api/hooks');

describe('<BlastDensityControl />', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders density and height inputs plus the apply button', () => {
    vi.mocked(useSettings).mockReturnValue({ data: undefined } as never);
    vi.mocked(useSections).mockReturnValue({ data: [] } as never);
    render(<BlastDensityControl />);
    // Spanish labels (locale pinned to es).
    expect(screen.getByText('Densidad de roca (ton/m³)')).toBeInTheDocument();
    expect(screen.getByText('Altura fallback (m)')).toBeInTheDocument();
    expect(screen.getByTestId('blast-apply-btn')).toBeInTheDocument();
  });

  it('initialises inputs from the session blast settings', () => {
    vi.mocked(useSettings).mockReturnValue({
      data: {
        process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
        tolerances: {} as never,
        blast: { rock_density_tm3: 3.1, height_fallback_m: 14.0 },
      },
    } as never);
    vi.mocked(useSections).mockReturnValue({ data: [] } as never);
    render(<BlastDensityControl />);
    const density = screen.getByTestId('blast-rock-density') as HTMLInputElement;
    const height = screen.getByTestId('blast-height-fallback') as HTMLInputElement;
    expect(Number(density.value)).toBeCloseTo(3.1, 5);
    expect(Number(height.value)).toBeCloseTo(14.0, 5);
  });

  it('PUTs the blast block (incl. sector_density) and invalidates blast queries on apply', async () => {
    vi.mocked(useSettings).mockReturnValue({
      data: {
        process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
        tolerances: {} as never,
        blast: { rock_density_tm3: 2.7, height_fallback_m: 15.0 },
      },
    } as never);
    vi.mocked(useSections).mockReturnValue({ data: [] } as never);
    render(<BlastDensityControl />);

    // Change density to 3.0.
    const density = screen.getByTestId('blast-rock-density') as HTMLInputElement;
    fireEvent.change(density, { target: { value: '3' } });

    // Click apply.
    fireEvent.click(screen.getByTestId('blast-apply-btn'));

    await waitFor(() => {
      // The mutation fires with ONLY the blast block (no process/tolerances),
      // and now includes sector_density (empty map when no overrides staged).
      expect(mockMutate).toHaveBeenCalledTimes(1);
      const payload = mockMutate.mock.calls[0][0];
      expect(payload).toEqual({
        blast: { rock_density_tm3: 3, height_fallback_m: 15, sector_density: {} },
      });
      expect(payload.process).toBeUndefined();
      expect(payload.tolerances).toBeUndefined();
      // Both blast queries are invalidated so the table + chart refetch.
      expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: ['blast-correlation'] });
      expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: ['blast-damage-model'] });
    });
  });

  it('renders the empty hint when no sections carry a sector', () => {
    vi.mocked(useSettings).mockReturnValue({ data: undefined } as never);
    vi.mocked(useSections).mockReturnValue({
      data: [
        // Sections whose sector is "" → no sectors to edit.
        { id: '0', name: 'S-1', origin: [0, 0], azimuth: 0, length: 200, sector: '' },
      ],
    } as never);
    render(<BlastDensityControl />);
    expect(screen.getByTestId('blast-sector-density-empty')).toBeInTheDocument();
  });

  it('lists distinct sectors and PUTs a per-sector override on apply', async () => {
    vi.mocked(useSettings).mockReturnValue({
      data: {
        process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
        tolerances: {} as never,
        blast: { rock_density_tm3: 2.7, height_fallback_m: 15.0 },
      },
    } as never);
    vi.mocked(useSections).mockReturnValue({
      data: [
        { id: '0', name: 'S-A', origin: [0, 0], azimuth: 0, length: 200, sector: 'Principal' },
        { id: '1', name: 'S-B', origin: [0, 0], azimuth: 0, length: 200, sector: 'Norte' },
        { id: '2', name: 'S-C', origin: [0, 0], azimuth: 0, length: 200, sector: 'Principal' },
      ],
    } as never);
    render(<BlastDensityControl />);

    // Both distinct sectors render an input.
    const principalInput = screen.getByTestId('blast-sector-rho-Principal') as HTMLInputElement;
    const norteInput = screen.getByTestId('blast-sector-rho-Norte') as HTMLInputElement;
    expect(principalInput).toBeInTheDocument();
    expect(norteInput).toBeInTheDocument();

    // Stage a 3.0 override for "Principal" only.
    fireEvent.change(principalInput, { target: { value: '3' } });

    // Apply.
    fireEvent.click(screen.getByTestId('blast-apply-btn'));

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledTimes(1);
      const payload = mockMutate.mock.calls[0][0];
      expect(payload.blast.sector_density).toEqual({ Principal: 3 });
    });
  });
});
