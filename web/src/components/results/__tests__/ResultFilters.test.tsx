import { useState } from 'react';
import { beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from '../../../i18n';
import { ResultFilters } from '../ResultFilters';
import { EMPTY_RESULT_FILTERS, type ResultFilterState } from '../resultFilters';
import type { ComparisonResult } from '../../../api/types';

beforeAll(async () => {
  i18n.addResourceBundle('es', 'translation', {
    results: { filters: { level: 'Cota', no_sector: '(sin sector)' } },
    table: { col_level: 'Nivel', col_delta_crest: 'Δ Cresta', col_delta_toe: 'Δ Pata' },
  }, true, true);
  await i18n.changeLanguage('es');
});

function makeResult(overrides: Partial<ComparisonResult>): ComparisonResult {
  return {
    sector: 'Norte', section: 'S01', bench_num: 1, type: 'MATCH', level: '2960',
    height_design: null, height_real: null, height_dev: null, height_status: '',
    angle_design: null, angle_real: null, angle_dev: null, angle_status: '',
    berm_design: null, berm_real: null, berm_min: null, berm_status: '',
    delta_crest: null, delta_toe: null,
    ...overrides,
  } as ComparisonResult;
}

const results: readonly ComparisonResult[] = [
  makeResult({ sector: 'Norte', section: 'S01', level: '2960' }),
  makeResult({ sector: '', section: 'S01', level: '2960' }),
  makeResult({ sector: 'Sur', section: 'S02', level: '2945', bench_num: 2 }),
];

function ControlledResultFilters(props: { initial?: ResultFilterState }) {
  const [filters, setFilters] = useState<ResultFilterState>(props.initial ?? EMPTY_RESULT_FILTERS);
  return <ResultFilters results={results} filters={filters} onChange={setFilters} />;
}

function dimensionRoot(name: string): HTMLElement {
  const root = document.querySelector<HTMLElement>(`[data-dimension="${name}"]`);
  if (!root) throw new Error(`missing dimension ${name}`);
  return root;
}
function checkboxValues(root: HTMLElement): string[] {
  return [...root.querySelectorAll('input[type="checkbox"]')].map((input) => (input as HTMLInputElement).value);
}

describe('ResultFilters', () => {
  it('renderiza tres desplegables accesibles sector/sección/cota sin selección inicial', () => {
    render(<ControlledResultFilters />);
    for (const name of ['sector', 'section', 'level']) {
      const summary = dimensionRoot(name).querySelector('summary')!;
      expect(summary).toHaveAccessibleName();
    }
    expect(dimensionRoot('sector').querySelector('summary')).toHaveTextContent('Todos');
    expect(dimensionRoot('section').querySelector('summary')).toHaveTextContent('Todos');
    expect(dimensionRoot('level').querySelector('summary')).toHaveTextContent('Todos');
  });

  it('lista valores únicos y ordenados por dimensión al abrir el desplegable', async () => {
    const user = userEvent.setup();
    render(<ControlledResultFilters />);
    await user.click(dimensionRoot('sector').querySelector('summary')!);
    expect(checkboxValues(dimensionRoot('sector'))).toEqual(['', 'Norte', 'Sur']);
    expect(screen.getByRole('checkbox', { name: '(sin sector)' })).toBeInTheDocument();
    await user.click(dimensionRoot('level').querySelector('summary')!);
    expect(checkboxValues(dimensionRoot('level'))).toEqual(['2945', '2960']);
  });

  it('cambia una dimensión vía onChange preservando el resto del estado', async () => {
    const user = userEvent.setup();
    const initial: ResultFilterState = { sector: [], section: ['S01'], level: ['2960'], bench: [2] };
    render(<ControlledResultFilters initial={initial} />);
    await user.click(dimensionRoot('sector').querySelector('summary')!);
    await user.click(screen.getByRole('checkbox', { name: 'Norte' }));
    const summary = dimensionRoot('sector').querySelector('summary')!;
    expect(summary).toHaveTextContent('Norte');
    expect(dimensionRoot('section').querySelector('summary')).toHaveTextContent('S01');
    expect(dimensionRoot('level').querySelector('summary')).toHaveTextContent('2960');
  });

  it('acumula selección OR dentro de una dimensión y deselecciona al repetir', async () => {
    const user = userEvent.setup();
    render(<ControlledResultFilters />);
    await user.click(dimensionRoot('sector').querySelector('summary')!);
    await user.click(screen.getByRole('checkbox', { name: 'Norte' }));
    await user.click(screen.getByRole('checkbox', { name: 'Sur' }));
    let summary = dimensionRoot('sector').querySelector('summary')!;
    expect(summary).toHaveTextContent('Norte');
    expect(summary).toHaveTextContent('Sur');
    await user.click(screen.getByRole('checkbox', { name: 'Sur' }));
    summary = dimensionRoot('sector').querySelector('summary')!;
    expect(summary).toHaveTextContent('Norte');
  });

  it('reinicia sector/sección/cota con el botón restablecer conservando el filtro de banco', async () => {
    const user = userEvent.setup();
    let latest: ResultFilterState | null = null;
    const initial: ResultFilterState = { sector: ['Norte'], section: [], level: [], bench: [3] };
    const { rerender } = render(
      <ResultFilters
        results={results}
        filters={initial}
        onChange={(next) => {
          latest = next;
          rerender(<ResultFilters results={results} filters={next} onChange={() => {}} />);
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Restablecer' }));
    expect(latest!).toEqual({ sector: [], section: [], level: [], bench: [3] });
  });
});
