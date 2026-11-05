import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BlastHole3DRecord } from '../BlastHoleFilters';
import { BlastHoleColorControls } from '../BlastHoleColorControls';
import type { BlastHoleColorMapping } from '../blastHoleColors';
import type { BlastViewColorConfig } from '../../../stores/blastView';

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

    expect(controlsGrid?.getAttribute('style')).toContain('repeat(auto-fit, minmax(min(100%, 140px), 1fr))');
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
      colorsByRowId: new Map([['two', '#EF553B']]),
    }), 'category'));
    expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({
      kind: 'category',
      entries: [{ label: 'Malla A', color: '#636EFA' }, { label: 'Malla B', color: '#EF553B' }],
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
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ kind: 'variable', min: 100, max: 900 }));

    fireEvent.change(screen.getByLabelText('Variable'), { target: { value: 'charge' } });
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ kind: 'variable', min: 0, max: 1000 }));
  });

  it('defaults to the first available Streamlit variable, then falls back in Streamlit order', () => {
    const records = [hole('hole', { pf_g_per_ton: 40, Diam_mm: 165 })];
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} />);

    expect(screen.getByLabelText('Variable')).toHaveValue('powderFactor');
    expect(Array.from(screen.getByLabelText('Variable').querySelectorAll('option')).map((option) => option.value)).toEqual([
      'powderFactor', 'powderFactorGeometry', 'diameter', 'collarElevation',
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

describe('BlastHoleColorControls controlled config', () => {
  const records = [
    hole('low', { Kilos_Cargados_real: 100 }, [0, 0, 100]),
    hole('high', { Kilos_Cargados_real: 900 }, [0, 0, 900]),
  ];

  it('reports config patches through onConfigChange and renders from the controlled config', () => {
    const onConfigChange = vi.fn();
    const { rerender } = render(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={vi.fn()}
      config={{ kind: 'variable', variable: 'charge', category: 'grid', palette: 'Turbo', rangeMode: 'data' }}
      onConfigChange={onConfigChange}
    />);
    fireEvent.change(screen.getByLabelText('Escala de color'), { target: { value: 'Viridis' } });
    expect(onConfigChange).toHaveBeenLastCalledWith({ palette: 'Viridis' });
    expect(screen.getByLabelText('Escala de color')).toHaveValue('Turbo');

    rerender(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={vi.fn()}
      config={{ kind: 'variable', variable: 'charge', category: 'grid', palette: 'Viridis', rangeMode: 'data' }}
      onConfigChange={onConfigChange}
    />);
    expect(screen.getByLabelText('Escala de color')).toHaveValue('Viridis');
  });

  it('keeps manual draft local and publishes only a valid finite min<max pair', () => {
    const onConfigChange = vi.fn();
    function Parent() {
      const [config, setConfig] = useState<BlastViewColorConfig>({ kind: 'variable', variable: 'collarElevation', category: 'grid', palette: 'Turbo', rangeMode: 'data' });
      return <BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={vi.fn()} config={config}
        onConfigChange={(patch) => { onConfigChange(patch); setConfig((current) => ({ ...current, ...patch })); }} />;
    }
    render(<Parent />);
    fireEvent.change(screen.getByLabelText('Rango'), { target: { value: 'manual' } });
    expect(onConfigChange).toHaveBeenLastCalledWith({ rangeMode: 'manual', rangeMin: 100, rangeMax: 900 });
    fireEvent.change(screen.getByLabelText('Mínimo'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Máximo'), { target: { value: '200' } });
    expect(screen.getByRole('button', { name: 'Aplicar rango' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Se mantiene la última escala válida');
    expect(onConfigChange).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('Máximo'), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar rango' }));
    expect(onConfigChange).toHaveBeenLastCalledWith({ rangeMode: 'manual', rangeMin: 500, rangeMax: 1000 });
  });

  it('keeps the last valid mapping while an invalid manual range is edited', async () => {
    const onColorsChange = vi.fn();
    const { rerender } = render(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={onColorsChange}
      config={{ kind: 'variable', variable: 'collarElevation', category: 'grid', palette: 'Turbo', rangeMode: 'manual', rangeMin: 0, rangeMax: 1000 }}
      onConfigChange={vi.fn()}
    />);
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ min: 0, max: 1000 }));
    const calls = onColorsChange.mock.calls.length;
    rerender(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={onColorsChange}
      config={{ kind: 'variable', variable: 'collarElevation', category: 'grid', palette: 'Turbo', rangeMode: 'manual', rangeMin: 900, rangeMax: 100 }}
      onConfigChange={vi.fn()}
    />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(onColorsChange.mock.calls.length).toBe(calls);
  });

  it('hides the internal legend when showLegend is false without removing controls', () => {
    const onColorsChange = vi.fn();
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={onColorsChange} showLegend={false} />);
    expect(screen.queryByLabelText('Escala de valores')).toBeNull();
    expect(screen.getByLabelText('Variable')).toBeInTheDocument();
    expect(onColorsChange).toHaveBeenCalled();
  });
});

describe('BlastHoleColorControls manual range scope', () => {
  const records = [
    hole('low', { Kilos_Cargados_real: 100, Nombre_Malla_Original: 'Malla A' }, [0, 0, 1000]),
    hole('high', { Kilos_Cargados_real: 900, Nombre_Malla_Original: 'Malla B' }, [0, 0, 1200]),
  ];

  it('controlled: changing variable while manual publishes data range and clears manual limits', () => {
    const onConfigChange = vi.fn();
    render(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={vi.fn()}
      config={{ kind: 'variable', variable: 'charge', category: 'grid', palette: 'Turbo', rangeMode: 'manual', rangeMin: 100, rangeMax: 900 }}
      onConfigChange={onConfigChange}
    />);
    fireEvent.change(screen.getByLabelText('Variable'), { target: { value: 'collarElevation' } });
    expect(onConfigChange).toHaveBeenLastCalledWith({ kind: 'variable', variable: 'collarElevation', rangeMode: 'data', rangeMin: undefined, rangeMax: undefined });
  });

  it('controlled: changing kind while manual publishes data range and clears manual limits', () => {
    const onConfigChange = vi.fn();
    render(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={vi.fn()}
      config={{ kind: 'variable', variable: 'charge', category: 'grid', palette: 'Turbo', rangeMode: 'manual', rangeMin: 100, rangeMax: 900 }}
      onConfigChange={onConfigChange}
    />);
    fireEvent.change(screen.getByLabelText('Colorear por'), { target: { value: 'category' } });
    expect(onConfigChange).toHaveBeenLastCalledWith({ kind: 'category', rangeMode: 'data', rangeMin: undefined, rangeMax: undefined });
  });

  it('uncontrolled: changing variable from manual resets to data range and the legend uses the new variable extent', async () => {
    const onColorsChange = vi.fn();
    render(<BlastHoleColorControls records={records} filteredRecords={records} onColorsChange={onColorsChange} />);
    fireEvent.change(screen.getByLabelText('Rango'), { target: { value: 'manual' } });
    expect(screen.getByLabelText('Mínimo')).toHaveValue(100);
    fireEvent.change(screen.getByLabelText('Variable'), { target: { value: 'collarElevation' } });
    expect(screen.getByLabelText('Rango')).toHaveValue('data');
    expect(screen.queryByLabelText('Mínimo')).toBeNull();
    await waitFor(() => expect(onColorsChange.mock.lastCall?.[0].legend).toMatchObject({ kind: 'variable', min: 1000, max: 1200 }));
  });

  it('legend source label follows the legend that is still shown while the current manual range is invalid', () => {
    const { rerender } = render(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={vi.fn()}
      config={{ kind: 'variable', variable: 'charge', category: 'grid', palette: 'Turbo', rangeMode: 'data' }}
      onConfigChange={vi.fn()}
    />);
    expect(screen.getByText(/^Fuente: .+ · Kilos_Cargados_real$/)).toBeInTheDocument();
    rerender(<BlastHoleColorControls
      records={records}
      filteredRecords={records}
      onColorsChange={vi.fn()}
      config={{ kind: 'variable', variable: 'collarElevation', category: 'grid', palette: 'Turbo', rangeMode: 'manual', rangeMin: 900, rangeMax: 100 }}
      onConfigChange={vi.fn()}
    />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Fuente: Carga Explosiva (Kg) · Kilos_Cargados_real')).toBeInTheDocument();
    expect(screen.queryByText(/^Fuente: Cota Collar/)).toBeNull();
  });
});
