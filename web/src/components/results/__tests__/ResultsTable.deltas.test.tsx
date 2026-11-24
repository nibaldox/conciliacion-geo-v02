import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from '../../../i18n';
import { ResultsTable } from '../ResultsTable';
import { useBenchFocus } from '../../../stores/benchFocus';
import { useSession } from '../../../stores/session';
import type { ComparisonResult } from '../../../api/types';

beforeAll(async () => {
  i18n.addResourceBundle('es', 'translation', {
    results: { filters: { level: 'Cota', no_sector: '(sin sector)' } },
    table: {
      col_level: 'Nivel',
      col_delta_crest: 'Δ Cresta',
      col_delta_toe: 'Δ Pata',
      col_status: 'Estado',
      col_score: 'Score',
      col_action: 'Acción',
      open_profile: 'Abrir perfil',
      order_by_severity: 'Por gravedad',
    },
    status: { cumple: 'CUMPLE', fuera: 'FUERA', no_cumple: 'NO CUMPLE' },
    dashboard: {
      rail: { status_unknown: 'Sin dato' },
      priority: { open_profile_aria: 'Abrir perfil de la sección {{section}}' },
    },
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

let fakeResults: ComparisonResult[] = [];
let fakeSections: Array<{ id: string; name: string }> = [];

const defaultResults: ComparisonResult[] = [
  makeRow({ section: 'S01', delta_crest: null, delta_toe: 1.25 }),
  makeRow({ section: 'S02', sector: 'Sur', bench_num: 2, level: '2945', type: 'MISSING', delta_crest: -0.5, delta_toe: null }),
  makeRow({ section: 'S03', bench_num: 3, level: '2930', delta_crest: 0, delta_toe: 0 }),
];

const defaultSections = [
  { id: 'sec-1', name: 'S01' },
  { id: 'sec-2', name: 'S02' },
  { id: 'sec-3', name: 'S03' },
];

vi.mock('../../../api/hooks', () => ({
  useResults: () => ({ data: fakeResults, isLoading: false, error: null }),
  useSections: () => ({ data: fakeSections, isLoading: false, error: null }),
}));

beforeEach(() => {
  fakeResults = defaultResults;
  fakeSections = defaultSections;
  useSession.setState({
    filters: { sector: [], section: [], level: [], bench: [] },
    selectedSection: null,
    profilesMode: 'grid',
    activeWorkspaceView: 'dashboard',
  });
  useBenchFocus.setState({ request: null, current: null });
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

  it('muestra columnas Estado, Score y Acción y ordena Por gravedad poniendo menor score MATCH primero y no-MATCH al final', async () => {
    const user = userEvent.setup();
    fakeResults = [
      makeRow({
        section: 'S01',
        bench_num: 1,
        type: 'MATCH',
        height_status: 'CUMPLE',
        angle_status: 'CUMPLE',
        berm_status: 'CUMPLE',
      }),
      makeRow({
        section: 'S02',
        bench_num: 2,
        type: 'MISSING',
      }),
      makeRow({
        section: 'S03',
        bench_num: 3,
        type: 'MATCH',
        height_status: 'CUMPLE',
        angle_status: 'NO CUMPLE',
        berm_status: 'NO CUMPLE',
      }),
      makeRow({
        section: 'S04',
        bench_num: 4,
        type: 'MATCH',
      }),
    ];
    fakeSections = [
      { id: 'sec-1', name: 'S01' },
      { id: 'sec-2', name: 'S02' },
      { id: 'sec-3', name: 'S03' },
      { id: 'sec-4a', name: 'S04' },
      { id: 'sec-4b', name: 'S04' },
    ];

    render(<ResultsTable />);
    expect(screen.getByRole('columnheader', { name: 'Estado' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Score' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Acción' })).toBeInTheDocument();

    expect(screen.getByText('CUMPLE')).toBeInTheDocument();
    expect(screen.getByText('NO CUMPLE')).toBeInTheDocument();
    expect(screen.getByText('Sin dato')).toBeInTheDocument();
    expect(screen.getByText('100/100')).toBeInTheDocument();
    expect(screen.getByText('30/100')).toBeInTheDocument();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Orden' }), 'Por gravedad');
    const rowTexts = [...document.querySelectorAll('tbody tr')].map((r) => r.textContent ?? '');
    expect(rowTexts[0]).toContain('S03');
    expect(rowTexts[1]).toContain('S01');
    expect(rowTexts[2]).toContain('S04');
    expect(rowTexts[3]).toContain('S02');

    expect(screen.queryByRole('button', { name: /S04/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Abrir perfil de la sección S03/i }));
    expect(useSession.getState().selectedSection).toBe('sec-3');
    expect(useSession.getState().profilesMode).toBe('detail');
    expect(useSession.getState().activeWorkspaceView).toBe('profiles');
    expect(useBenchFocus.getState().request).toMatchObject({
      sectionId: 'sec-3',
      designBench: 3,
    });
  });
});
