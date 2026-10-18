import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from '../../../i18n';
import { ResultsTable } from '../ResultsTable';
import { useSession } from '../../../stores/session';
import type { ComparisonResult } from '../../../api/types';

beforeAll(async () => {
  i18n.addResourceBundle('es', 'translation', {
    results: { filters: { level: 'Cota', no_sector: '(sin sector)' } },
    table: {
      col_section: 'Sección',
      col_sector: 'Sector',
      col_level: 'Nivel',
      col_bench: 'Banco',
      col_spill: 'B. Derrame (m)',
      col_berm_effective: 'B. Efectiva (m)',
      order_label: 'Orden',
      order_by_section: 'Por Sección',
      order_by_level: 'Por Nivel',
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

const fakeResults: ComparisonResult[] = [
  makeRow({ section: 'S0', level: '1050', bench_num: 1, type: 'EXTRA' }),
  makeRow({ section: 'S1', level: '995', bench_num: 2, type: 'EXTRA', spill_width: 0.5, effective_berm: 8.2 }),
  makeRow({ section: 'S1', level: '1050', bench_num: 3, type: 'MATCH', effective_berm: 0 }),
  makeRow({ section: 'S2', level: '', bench_num: 4, type: 'MISSING', spill_width: 1.25 }),
  makeRow({ section: 'S3', level: '2000', bench_num: 5, type: 'EXTRA' }),
];

vi.mock('../../../api/hooks', () => ({
  useResults: () => ({ data: fakeResults, isLoading: false, error: null }),
}));

beforeEach(() => {
  useSession.setState({ filters: { sector: [], section: [], level: [], bench: [] } });
});

function bodyRows(): string[] {
  return [...document.querySelectorAll('tbody tr')].map((r) => r.textContent ?? '');
}

describe('ResultsTable orden Por Sección/Por Nivel y columnas derrame/berma efectiva', () => {
  it('muestra B. Derrame (m) y B. Efectiva (m): valores reales, cero válido y nulos/ausentes como —', () => {
    render(<ResultsTable />);
    expect(screen.getByRole('columnheader', { name: 'B. Derrame (m)' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'B. Efectiva (m)' })).toBeInTheDocument();
    expect(screen.getByText('0.50m')).toBeInTheDocument();
    expect(screen.getByText('8.20m')).toBeInTheDocument();
    expect(screen.getByText('1.25m')).toBeInTheDocument();
    expect(screen.getByText('0.00m')).toBeInTheDocument();
    const absent = bodyRows().find((r) => r.includes('S0'))!;
    expect(absent).not.toMatch(/\d\.\d+m/);
  });

  it('Por Sección por omisión: sección asc y cota numérica desc ("1050" antes de "995"), desconocidas al final', () => {
    render(<ResultsTable />);
    const rows = bodyRows();
    expect(rows).toHaveLength(5);
    expect(rows[0]).toMatch(/S0/);
    expect(rows[1]).toMatch(/S1/);
    expect(rows[1]).toMatch(/1050/);
    expect(rows[2]).toMatch(/995/);
    expect(rows[3]).toMatch(/S2/);
    expect(rows[4]).toMatch(/S3/);
  });

  it('Por Nivel: cota numérica desc entre secciones, empate por sección asc, nivel antes de sección y desconocidas al final', async () => {
    const user = userEvent.setup();
    render(<ResultsTable />);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Orden' }), 'Por Nivel');
    const rows = bodyRows();
    expect(rows).toHaveLength(5);
    expect(rows[0]).toMatch(/S3/);
    expect(rows[1]).toMatch(/S0/);
    expect(rows[2]).toMatch(/S1/);
    expect(rows[2]).toMatch(/1050/);
    expect(rows[3]).toMatch(/995/);
    expect(rows[4]).toMatch(/S2/);
    const headers = [...document.querySelectorAll('thead th')].map((th) => th.textContent ?? '');
    expect(headers.indexOf('Nivel')).toBeLessThan(headers.indexOf('Sección'));
    expect(headers.indexOf('Nivel')).toBeLessThan(headers.indexOf('Banco'));
  });

  it('el sorting por columnas sigue funcionando sobre el orden base', async () => {
    const user = userEvent.setup();
    render(<ResultsTable />);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Orden' }), 'Por Nivel');
    await user.click(screen.getByRole('columnheader', { name: 'Banco' }));
    const benches = bodyRows().map((r) => Number((r.match(/B(\d+)/) ?? [])[1]));
    const asc = benches.every((b, i) => i === 0 || benches[i - 1] <= b);
    const desc = benches.every((b, i) => i === 0 || benches[i - 1] >= b);
    expect(asc || desc).toBe(true);
  });
});
