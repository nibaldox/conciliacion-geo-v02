import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BlastHole3DRecord } from '../BlastHoleFilters';
import { BlastHoleColorControls } from '../BlastHoleColorControls';
import type { BlastHoleColorMapping } from '../blastHoleColors';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, options?: { defaultValue?: string; [key: string]: unknown }) => {
    const value = options?.defaultValue ?? key;
    return value.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ''));
  } }),
}));

function hole(rowId: string, attributes: Record<string, unknown> = {}, collar: number[] | null = [0, 0, 100]): BlastHole3DRecord {
  return {
    row_id: rowId,
    hole_id: rowId,
    collar,
    toe: null,
    geometry_status: 'complete',
    provenance: {},
    attributes,
    section_relation: null,
    section_distance_m: null,
  };
}

afterEach(() => cleanup());

describe('BlastHoleColorControls', () => {
  it('uses panel-width-driven auto-fit controls without forcing palette across columns', () => {
    const records = [hole('hole', { Kilos_Cargados_real: 100 })];
    const { container } = render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} />);
    const controlsGrid = container.querySelector('section > div');
    const paletteLabel = screen.getByLabelText('Escala de color').closest('label');

    expect(controlsGrid?.getAttribute('style')).toContain('repeat(auto-fit, minmax(min(100%, 200px), 1fr))');
    expect(controlsGrid?.className).not.toMatch(/sm:grid-cols/);
    expect(paletteLabel?.className).not.toContain('sm:col-span-2');
  });

  it('shows only available variable/category options and emits colors for filtered rows', async () => {
    const onColorsChange = vi.fn<(mapping: BlastHoleColorMapping, kind: 'category' | 'variable') => void>();
    const records = [
      hole('one', { Kilos_Cargados_real: 100, Nombre_Malla_Original: 'Malla A', Len: 25, Incl: 85 }),
      hole('two', { Kilos_Cargados_real: 200, Nombre_Malla_Original: 'Malla B', Len: 30, Incl: 80 }),
    ];
    const { rerender } = render(<BlastHoleColorControls records={records} filteredRecords={[records[1]]} onColorsChange={onColorsChange} />);

    expect(screen.getByLabelText('Variable').querySelector('option[value="charge"]')).not.toBeNull();
    expect(screen.getByLabelText('Variable')).toHaveValue('charge');
    expect(screen.queryByRole('option', { name: 'Factor de Carga (g/ton)' })).toBeNull();
    expect(screen.getByRole('option', { name: 'Cota Collar' })).not.toBeNull();
    expect(screen.getByRole('option', { name: 'Profundidad (m)' })).not.toBeNull();
    expect(screen.getByRole('option', { name: 'Inclinación (°)' })).not.toBeNull();
    expect(screen.getByLabelText('Escala de color')).toHaveValue('Turbo');

    await waitFor(() => expect(onColorsChange).toHaveBeenLastCalledWith(expect.objectContaining({
      colorsByRowId: new Map([['two', expect.any(String)]]),
    }), 'variable'));

    fireEvent.change(screen.getByLabelText('Colorear por'), { target: { value: 'category' } });
    expect(screen.getByRole('option', { name: 'Mallas de Tronadura (Grid)' })).not.toBeNull();
    expect(screen.getByLabelText('Escala de color')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'grid' } });
    await waitFor(() => expect(onColorsChange).toHaveBeenLastCalledWith(expect.objectContaining({
      colorsByRowId: new Map([['two', '#636EFA']]),
    }), 'category'));
    expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({
      kind: 'category',
      entries: [{ label: 'Malla B', color: '#636EFA' }],
    });

    rerender(<BlastHoleColorControls records={records} filteredRecords={[records[0]]} onColorsChange={onColorsChange} />);
    expect(screen.getByLabelText('Categoría')).toHaveValue('grid');
    await waitFor(() => expect(onColorsChange).toHaveBeenLastCalledWith(expect.objectContaining({
      colorsByRowId: new Map([['one', '#636EFA']]),
    }), 'category'));
  });

  it('limits large discrete legends to 100 visible entries and reports the full count', () => {
    const records = Array.from({ length: 20_000 }, (_, index) => hole(`hole-${index}`, { Nombre_Malla_Original: `Grid ${index}` }));
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Colorear por'), { target: { value: 'category' } });
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'grid' } });

    expect(screen.getByText('Se muestran 100 de 20000 categorías')).toBeInTheDocument();
    expect(screen.getByLabelText('Leyenda discreta').querySelectorAll('li')).toHaveLength(100);
  });

  it('renders a continuous legend and a missing-data entry', () => {
    const records = [hole('measured', { Kilos_Cargados_real: 400 }), hole('missing', { Kilos_Cargados_real: null })];
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} />);

    expect(screen.getByLabelText('Leyenda continua')).toBeInTheDocument();
    expect(screen.getByText('Sin dato')).toBeInTheDocument();
    expect(screen.getByLabelText('Escala de color')).toHaveValue('Turbo');
  });

  it('recalculates autoscale and discrete domains from filtered rows while keeping charge bounds fixed', async () => {
    const onColorsChange = vi.fn<(mapping: BlastHoleColorMapping, kind: 'category' | 'variable') => void>();
    const records = [
      hole('low', { Kilos_Cargados_real: 100 }, [0, 0, 100]),
      hole('high', { Kilos_Cargados_real: 900 }, [0, 0, 900]),
    ];
    const { rerender } = render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={onColorsChange} />);
    fireEvent.change(screen.getByLabelText('Variable'), { target: { value: 'collarElevation' } });
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ kind: 'variable', min: 100, max: 900 }));

    rerender(<BlastHoleColorControls records={records} filteredRecords={[records[1]]} onColorsChange={onColorsChange} />);
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ kind: 'variable', min: 900, max: 900 }));

    fireEvent.change(screen.getByLabelText('Variable'), { target: { value: 'charge' } });
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ kind: 'variable', min: 0, max: 1000 }));
  });

  it('defaults to the first available Streamlit variable, then falls back in Streamlit order', () => {
    const records = [hole('hole', { pf_g_per_ton: 40, Diam_mm: 165 })];
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} />);

    expect(screen.getByLabelText('Variable')).toHaveValue('powderFactor');
    expect(Array.from(screen.getByLabelText('Variable').querySelectorAll('option')).map((option) => option.value)).toEqual([
      'powderFactor', 'diameter', 'collarElevation',
    ]);
  });

  it('defaults to the first available category when charge and powder factor are absent, and adapts until selection', () => {
    const initial = [] as BlastHole3DRecord[];
    const categoryRecords = [hole('categorized', { Nombre_Malla_Original: 'Malla A' }, null)];
    const variableRecords = [hole('charged', { Kilos_Cargados_real: 20, Nombre_Malla_Original: 'Malla A' }, null)];
    const { rerender } = render(<BlastHoleColorControls records={initial} filteredRecords={initial} onColorsChange={vi.fn()} />);
    expect(screen.getByLabelText('Colorear por')).toHaveValue('variable');

    rerender(<BlastHoleColorControls records={categoryRecords} filteredRecords={categoryRecords} onColorsChange={vi.fn()} />);
    expect(screen.getByLabelText('Colorear por')).toHaveValue('category');
    expect(screen.getByLabelText('Categoría')).toHaveValue('grid');

    rerender(<BlastHoleColorControls records={variableRecords} filteredRecords={variableRecords} onColorsChange={vi.fn()} />);
    expect(screen.getByLabelText('Colorear por')).toHaveValue('variable');
    expect(screen.getByLabelText('Variable')).toHaveValue('charge');

    fireEvent.change(screen.getByLabelText('Colorear por'), { target: { value: 'category' } });
    rerender(<BlastHoleColorControls records={variableRecords} filteredRecords={variableRecords} onColorsChange={vi.fn()} />);
    expect(screen.getByLabelText('Colorear por')).toHaveValue('category');
  });

  it('offers only legacy source fields that actually exist, and explains an empty selection', () => {
    const legacyRecords = [hole('legacy', { Kilos_Cargados_real: 100 }, null)];
    const { rerender } = render(<BlastHoleColorControls records={legacyRecords} filteredRecords={legacyRecords} onColorsChange={vi.fn()} />);

    expect(Array.from(screen.getByLabelText('Variable').querySelectorAll('option')).map((option) => option.value)).toEqual(['charge']);
    expect(screen.queryByRole('option', { name: 'blast.colors.variable.depth' })).toBeNull();
    expect(screen.queryByRole('option', { name: 'blast.colors.variable.inclination' })).toBeNull();
    expect(screen.queryByRole('option', { name: 'blast.colors.variable.collarElevation' })).toBeNull();

    const empty = [] as BlastHole3DRecord[];
    rerender(<BlastHoleColorControls records={empty} filteredRecords={empty} onColorsChange={vi.fn()} />);
    expect(screen.getByLabelText('Variable')).toBeDisabled();
    expect(screen.getAllByText('No hay variables con datos disponibles')).toHaveLength(2);
    expect(screen.getByLabelText('Variable')).toHaveValue('');
  });

  it('shows depth and inclination only when source fields exist', () => {
    const records = [hole('partial', { Len: 18 }, null)];
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} />);

    expect(Array.from(screen.getByLabelText('Variable').querySelectorAll('option')).map((option) => option.value)).toEqual(['depth']);
  });

  it('does not loop when the parent callback updates state and changes identity on each render', async () => {
    let callbackCalls = 0;
    const records = [hole('hole', { Kilos_Cargados_real: 100 })];
    function Parent() {
      const [updates, setUpdates] = useState(0);
      return <>
        <BlastHoleColorControls
          records={records}
          filteredRecords={records}
          onColorsChange={() => {
            callbackCalls += 1;
            setUpdates((current) => current + 1);
          }}
        />
        <output data-testid="parent-updates">{updates}</output>
      </>;
    }

    render(<Parent />);
    await waitFor(() => expect(screen.getByTestId('parent-updates')).toHaveTextContent('1'));
    expect(callbackCalls).toBe(1);
  });
});
