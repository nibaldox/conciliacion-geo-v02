import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import i18n from '../../../i18n';
import { BlastDensityControl } from '../BlastCorrelation';

// ─── Mocks ─────────────────────────────────────────────────
//
// The control reads session settings (useSettings), writes them
// (useUpdateSettings), and invalidates the blast-correlation query
// (useQueryClient). We mock all three so the test exercises the
// control's wiring (initialisation from settings + fire-on-apply)
// without hitting the network or the query cache.

const mockInvalidate = vi.fn();
const mockMutate = vi.fn();

vi.mock('../../../api/hooks', () => ({
  useSettings: vi.fn(() => ({ data: undefined })),
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
const { useSettings } = await import('../../../api/hooks');

describe('<BlastDensityControl />', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders density and height inputs plus the apply button', () => {
    vi.mocked(useSettings).mockReturnValue({ data: undefined } as never);
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
    render(<BlastDensityControl />);
    const density = screen.getByTestId('blast-rock-density') as HTMLInputElement;
    const height = screen.getByTestId('blast-height-fallback') as HTMLInputElement;
    expect(Number(density.value)).toBeCloseTo(3.1, 5);
    expect(Number(height.value)).toBeCloseTo(14.0, 5);
  });

  it('PUTs the blast block and invalidates the correlation query on apply', async () => {
    vi.mocked(useSettings).mockReturnValue({
      data: {
        process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
        tolerances: {} as never,
        blast: { rock_density_tm3: 2.7, height_fallback_m: 15.0 },
      },
    } as never);
    render(<BlastDensityControl />);

    // Change density to 3.0.
    const density = screen.getByTestId('blast-rock-density') as HTMLInputElement;
    fireEvent.change(density, { target: { value: '3' } });

    // Click apply.
    fireEvent.click(screen.getByTestId('blast-apply-btn'));

    await waitFor(() => {
      // The mutation fires with ONLY the blast block (no process/tolerances).
      expect(mockMutate).toHaveBeenCalledTimes(1);
      const payload = mockMutate.mock.calls[0][0];
      expect(payload).toEqual({
        blast: { rock_density_tm3: 3, height_fallback_m: 15 },
      });
      expect(payload.process).toBeUndefined();
      expect(payload.tolerances).toBeUndefined();
      // The blast-correlation query is invalidated so the table refetches.
      expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: ['blast-correlation'] });
    });
  });
});
