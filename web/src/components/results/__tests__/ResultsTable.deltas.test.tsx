import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '../../../i18n';
import { ResultsTable } from '../ResultsTable';
import { useSession } from '../../../stores/session';
import type { ComparisonResult } from '../../../api/types';

beforeAll(async () => {
  i18n.addResourceBundle('es', 'translation', {
    results: { filters: { level: 'Cota', no_sector: '(sin sector)' } },
    table: { col_level: 'Nivel', col_delta_crest: 'Δ Cresta', col_delta_toe: 'Δ Pata' },
  }, true, true);
  await i18n.changeLanguage('es');
});

function makeRow(overrides: Partial<ComparisonResult>): ComparisonResult {
  return {
    sector: 'Norte', section: 'S01', bench_num: 1, type: 'MATCH', level: '2960',
    height_design: null, height_real: null, height_dev: null, height_status: '',
    angle_design: null, angle_real: null, angle_dev: null, angle_status: '',
    berm_design: null, berm_real: null, berm_min: null, berm_status: '',
    delta_crest: null, delta_toe: null,
    ...overrides,
  };
}

const fakeResults: ComparisonResult[] = [
  makeRow({ section: 'S01', delta_crest: null, delta_toe: 1.25 }),
  makeRow({ section: 'S02', sector: 'Sur', bench_num: 2, level: '2945', type: 'MISSING', delta_crest: -0.5, delta_toe: null }),
  makeRow({ section: 'S03', bench_num: 3, level: '2930', delta_crest: 0, delta_toe: 0 }),
];

vi.mock('../../../api/hooks', () => ({
  useResults: () => ({ data: fakeResults, isLoading: false, error: null }),
}));

beforeEach(() => {
  useSession.setState({ filters: { sector: [], section: [], level: [], bench: [] } });
});

describe('ResultsTable deltas y filtros del contrato', () => {
  it('muestra las columnas Sector, Nivel, Δ Cresta y Δ Pata', () => {
    render(<ResultsTable />);
    expect(screen.getByRole('columnheader', { name: 'Sector' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Nivel' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Δ Cresta' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Δ Pata' })).toBeInTheDocument();
  });

  it('conserva los nulos como "—" y los ceros como 0,00 en las columnas de deltas', () => {
    render(<ResultsTable />);
    expect(screen.getByText('+1.25')).toBeInTheDocument();
    expect(screen.getByText('-0.50')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText('+0.00').length).toBe(2);
  });

  it('aplica el estado de filtros de la sesión (sector vacío "" incluido) via filterResults', () => {
    useSession.setState({ filters: { sector: ['Sur'], section: [], level: [], bench: [] } });
    render(<ResultsTable />);
    expect(screen.getByText('S02')).toBeInTheDocument();
    expect(screen.queryByText('S01')).not.toBeInTheDocument();
    expect(screen.queryByText('S03')).not.toBeInTheDocument();
  });
});
