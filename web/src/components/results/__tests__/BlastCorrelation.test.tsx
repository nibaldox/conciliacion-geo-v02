import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
// Initialise i18next so useTranslation() returns real Spanish strings
// instead of the raw keys (mirrors app entry in main.tsx).
import i18n from '../../../i18n';
import {
  formatKg,
  formatMJ,
  formatGramsPerTon,
  formatPowderFactor,
  formatBreakMeters,
  BlastCorrelation,
} from '../BlastCorrelation';
import type { BlastCorrelationRow } from '../../../api/types';

// ─── Pure helper / type-mapping tests ───────────────────────

describe('BlastCorrelation formatting helpers', () => {
  it('formatKg renders finite kilograms with 1 decimal', () => {
    expect(formatKg(1234.5)).toBe('1234.5 kg');
  });

  it('formatKg renders an em dash for null / undefined / NaN', () => {
    expect(formatKg(null)).toBe('—');
    expect(formatKg(undefined)).toBe('—');
    expect(formatKg(NaN)).toBe('—');
  });

  it('formatGramsPerTon renders the highlighted g/ton value with 2 decimals (no unit)', () => {
    expect(formatGramsPerTon(82.376)).toBe('82.38');
  });

  it('formatPowderFactor renders kg/m³ or kg/m² terms with 3 decimals', () => {
    expect(formatPowderFactor(0.926)).toBe('0.926');
  });

  it('formatMJ rounds energy to whole megajoules', () => {
    // es-CL uses '.' as the thousands separator.
    expect(formatMJ(8421.6)).toBe('8.422 MJ');
  });

  it('formatBreakMeters renders over/under-break metres with 2 decimals', () => {
    expect(formatBreakMeters(0.4567)).toBe('0.46');
  });
});

// ─── Type-shape sanity (guards against backend drift) ───────

describe('BlastCorrelationRow type mapping', () => {
  it('matches the 13-field backend BlastCorrelationRowSchema', () => {
    const row: BlastCorrelationRow = {
      section_name: 'S-001',
      num_wells: 12,
      total_kg: 5400,
      mean_abs_deviation: 0.4,
      avg_over_break: 0.8,
      avg_under_break: 0.3,
      n_over: 3,
      n_under: 2,
      pf_vol_avg_kgm3: 0.92,
      pf_area_avg_kgm2: 2.31,
      pf_g_per_ton_avg: 82.4,
      energy_total_mj: 24500,
      n_pf_valid: 10,
    };
    // Touch every field so a missing/renamed key fails compilation.
    expect(row.section_name).toBe('S-001');
    expect(row.num_wells).toBe(12);
    expect(row.total_kg).toBe(5400);
    expect(row.mean_abs_deviation).toBe(0.4);
    expect(row.avg_over_break).toBe(0.8);
    expect(row.avg_under_break).toBe(0.3);
    expect(row.n_over).toBe(3);
    expect(row.n_under).toBe(2);
    expect(row.pf_vol_avg_kgm3).toBe(0.92);
    expect(row.pf_area_avg_kgm2).toBe(2.31);
    expect(row.pf_g_per_ton_avg).toBe(82.4);
    expect(row.energy_total_mj).toBe(24500);
    expect(row.n_pf_valid).toBe(10);
    expect(Object.keys(row)).toHaveLength(13);
  });
});

// ─── Component render: empty-rows state ─────────────────────

vi.mock('../../../api/hooks', () => ({
  useBlastCorrelation: vi.fn(),
  useSettings: vi.fn(() => ({ data: undefined })),
  useUpdateSettings: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: vi.fn(() => ({
      invalidateQueries: vi.fn(),
    })),
  };
});

// Pull the mocked hook out so we can drive its return value per test.
// Top-level dynamic import keeps the module graph after vi.mock hoisting.
const { useBlastCorrelation } = await import('../../../api/hooks');

function mockHook(overrides: Partial<{
  data: { rows: BlastCorrelationRow[]; tolerance: number | null; n_sections: number };
  isLoading: boolean;
  error: unknown;
}>) {
  vi.mocked(useBlastCorrelation).mockReturnValue({
    data: { rows: [], tolerance: null, n_sections: 0 },
    isLoading: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof useBlastCorrelation>);
}

describe('<BlastCorrelation /> empty-rows state', () => {
  // Pin the locale to Spanish so the assertions below match the
  // primary UI language. jsdom's navigator.language defaults to
  // en-US, which would otherwise resolve the English strings.
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => vi.clearAllMocks());

  it('renders the friendly empty message when rows is empty', async () => {
    mockHook({ data: { rows: [], tolerance: null, n_sections: 0 } });
    render(<BlastCorrelation />);
    expect(
      screen.getByText('Sin datos de tronadura'),
    ).toBeInTheDocument();
  });

  it('renders the loading message while pending', async () => {
    mockHook({ isLoading: true });
    render(<BlastCorrelation />);
    expect(
      screen.getByText('Cargando datos de tronadura…'),
    ).toBeInTheDocument();
  });

  it('renders the highlighted g/ton column header when rows exist', async () => {
    const row: BlastCorrelationRow = {
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
      energy_total_mj: 9000,
      n_pf_valid: 4,
    };
    mockHook({
      data: { rows: [row], tolerance: 2.0, n_sections: 1 },
    });
    render(<BlastCorrelation />);
    // Primary column header
    expect(
      screen.getByText('Factor de carga (g/ton)'),
    ).toBeInTheDocument();
    // Section name cell
    expect(screen.getByText('S-001')).toBeInTheDocument();
    // Highlighted value rendered with 2 decimals
    await waitFor(() => {
      expect(screen.getByText('42.50')).toBeInTheDocument();
    });
  });
});
