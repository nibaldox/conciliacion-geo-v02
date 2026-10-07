import { useState } from 'react';
import { beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from '../../../i18n';
import { BenchFilter } from '../BenchFilter';
import type { DesignBenchOption } from '../Dashboard';

const available: readonly DesignBenchOption[] = [
  { number: 1, minElevation: 2960, maxElevation: 2960 },
  { number: 3, minElevation: 2945, maxElevation: 2945 },
  { number: 42, minElevation: 2920, maxElevation: 2920 },
];

function ControlledFilter() {
  const [selected, setSelected] = useState<number[]>([]);
  return <BenchFilter available={available} selected={selected} onChange={setSelected} />;
}

beforeAll(async () => i18n.changeLanguage('es'));

describe('BenchFilter', () => {
  it('selects multiple benches and restores the full evaluation', async () => {
    const user = userEvent.setup();
    render(<ControlledFilter />);
    await user.click(document.querySelector('summary')!);
    await user.click(screen.getByRole('checkbox', { name: 'Cota base de diseño 2960 m' }));
    await user.click(screen.getByRole('checkbox', { name: 'Cota base de diseño 2945 m' }));
    expect(document.querySelector('summary')).toHaveTextContent('Cota base de diseño 2960 m, Cota base de diseño 2945 m');
    await user.click(screen.getByRole('button', { name: 'Restablecer' }));
    expect(document.querySelector('summary')).toHaveTextContent('Todos los bancos');
    expect(screen.getByRole('button', { name: 'Restablecer' })).toBeDisabled();
  });
  it('searches options without losing selections and supports Escape', async () => {
    const user = userEvent.setup();
    render(<ControlledFilter />);
    await user.click(document.querySelector('summary')!);
    await user.click(screen.getByRole('checkbox', { name: 'Cota base de diseño 2960 m' }));
    await user.type(screen.getByRole('searchbox'), '42');
    expect(screen.queryByRole('checkbox', { name: 'Cota base de diseño 2960 m' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Cota base de diseño 2920 m' }));
    expect(document.querySelector('summary')).toHaveTextContent('Cota base de diseño 2960 m, Cota base de diseño 2920 m');
    await user.clear(screen.getByRole('searchbox'));
    expect(screen.getByRole('checkbox', { name: 'Cota base de diseño 2960 m' })).toBeChecked();
    await user.keyboard('{Escape}');
    expect(document.querySelector('details')).not.toHaveAttribute('open');
    expect(document.querySelector('summary')).toHaveFocus();
  });

  it('shows a design ID when two banks share the same base elevation', async () => {
    const user = userEvent.setup();
    render(<BenchFilter available={[
      { number: 1, minElevation: 2960, maxElevation: 2960 },
      { number: 2, minElevation: 2960, maxElevation: 2960 },
    ]} selected={[]} onChange={() => {}} />);
    await user.click(document.querySelector('summary')!);
    expect(screen.getByRole('checkbox', { name: 'Cota base de diseño 2960 m · ID de diseño 1' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Cota base de diseño 2960 m · ID de diseño 2' })).toBeInTheDocument();
  });
});
