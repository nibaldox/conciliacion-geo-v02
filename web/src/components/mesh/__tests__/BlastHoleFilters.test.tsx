import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BlastHoleFilters, filterBlastHoles, type BlastHole3DRecord, type BlastHoleFilterState } from '../BlastHoleFilters';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => {
      const messages: Record<string, string> = {
        'blast.holeFilters.id': 'Buscar ID',
        'blast.holeFilters.bench': 'Banco',
        'blast.holeFilters.dateEvent': 'Fecha o evento',
        'blast.holeFilters.datePresence': 'Presencia de fecha',
        'blast.holeFilters.withDate': 'Con fecha',
        'blast.holeFilters.geometry': 'Geometría',
        'blast.holeFilters.provenanceLabel': 'Procedencia',
        'blast.holeFilters.collarProvenanceLabel': 'Procedencia de cota',
        'blast.holeFilters.surfaceSampleStatusLabel': 'Estado de muestreo de superficie',
        'blast.holeFilters.section': 'Sección',
        'blast.holeFilters.corridor': 'Corredor',
        'blast.holeFilters.grid': 'Malla (Grid)',
        'blast.holeFilters.polygon': 'Polígono',
        'blast.holeFilters.originalBench': 'Banco de tronadura',
        'blast.holeFilters.phase': 'Fase',
        'blast.holeFilters.searchOptions': 'Buscar opciones',
        'blast.holeFilters.depthRange': 'Profundidad (m)',
        'blast.holeFilters.chargeRange': 'Explosivo (kg)',
        'blast.holeFilters.minimum': 'Mínimo',
        'blast.holeFilters.maximum': 'Máximo',
        'blast.holeFilters.clear': 'Limpiar filtros',
        'blast.holeFilters.unavailableFiltersCleared': 'Se limpiaron filtros porque sus columnas ya no están disponibles.',
        'blast.holeFilters.selectedCount': `${options?.count ?? ''} seleccionados`,
        'blast.holeFilters.chooseSection': 'Elija una sección',
        'blast.holeFilters.countTotal': `Cargados: ${options?.count ?? ''}`,
        'blast.holeFilters.countDrawable': `Dibujables: ${options?.count ?? ''}`,
        'blast.holeFilters.countVisible': `Visibles con filtros: ${options?.count ?? ''}`,
        'blast.holeFilters.countExcluded': `Sin geometría dibujable: ${options?.count ?? ''}`,
      };
      return messages[key] ?? key;
    },
  }),
}));

const base: BlastHoleFilterState = {
  query: '', bench: '', grid: [], polygon: [], originalBench: [], phase: [],
  depthMin: '', depthMax: '', chargeMin: '', chargeMax: '', date: '', geometryStatus: '', provenance: '', surfaceSampleStatus: '', sectionRelation: '', corridorM: 10,
};

function makeHole(overrides: Partial<BlastHole3DRecord> = {}): BlastHole3DRecord {
  return {
    row_id: 'row-1', hole_id: 'P-01', collar: [1, 2, 3], toe: [1, 2, 0], geometry_status: 'complete',
    provenance: { z_collar_semantic: 'collar_elevation', surface_sample_status: 'sampled' }, attributes: { bench_num: '3150', fecha_tronadura: '2026-10-31' },
    section_relation: 'near_section', section_distance_m: 8, ...overrides,
  };
}

describe('BlastHoleFilters', () => {
  it('uses panel-width-driven auto-fit columns with a 200px minimum control width', () => {
    const { container } = render(<BlastHoleFilters holes={[makeHole()]} />);
    const controlsGrid = container.querySelector('fieldset > div');

    expect(controlsGrid?.getAttribute('style')).toContain('repeat(auto-fit, minmax(min(100%, 200px), 1fr))');
    expect(controlsGrid?.className).not.toMatch(/sm:grid-cols|lg:grid-cols/);
  });

  it('combines ID, bench, date, geometry, provenance, relation and corridor criteria', () => {
    const matching = makeHole();
    const other = makeHole({ row_id: 'row-2', hole_id: 'P-02', section_distance_m: 14 });
    expect(filterBlastHoles([matching, other], {
      ...base, query: 'p-01', bench: '3150', date: '2026-10', geometryStatus: 'complete',
      surfaceSampleStatus: 'sampled', sectionRelation: 'near_section', corridorM: 10,
    })).toEqual([matching]);
  });

  it('keeps near-section distances within the editable corridor and preserves exact intersections', () => {
    const near = makeHole({ section_distance_m: 11 });
    const exact = makeHole({ row_id: 'row-2', section_relation: 'exact_intersection', section_distance_m: 0 });
    expect(filterBlastHoles([near, exact], { ...base, sectionRelation: 'near_section', corridorM: 10 })).toEqual([]);
    expect(filterBlastHoles([exact], { ...base, sectionRelation: 'exact_intersection', corridorM: 0 })).toEqual([exact]);
  });

  it('includes an outside-classified hole when the editable corridor expands beyond its backend corridor', () => {
    const outsideAtDefaultCorridor = makeHole({
      section_relation: 'outside',
      section_distance_m: 14,
    });

    expect(filterBlastHoles([outsideAtDefaultCorridor], {
      ...base, sectionRelation: 'near_section', corridorM: 20,
    })).toEqual([outsideAtDefaultCorridor]);
    expect(filterBlastHoles([outsideAtDefaultCorridor], {
      ...base, sectionRelation: 'near_section', corridorM: 10,
    })).toEqual([]);
  });

  it('reports drawable and geometry-excluded counts and emits filtered records', async () => {
    const onFilteredChange = vi.fn();
    render(<BlastHoleFilters holes={[makeHole(), makeHole({ row_id: 'row-2', hole_id: 'P-02', collar: null, geometry_status: 'none' })]} onFilteredChange={onFilteredChange} />);
    expect(screen.getByText('Cargados: 2')).toBeTruthy();
    expect(screen.getByText('Dibujables: 1')).toBeTruthy();
    expect(screen.getByText('Sin geometría dibujable: 1')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Buscar ID'), { target: { value: 'P-01' } });
    await waitFor(() => expect(onFilteredChange).toHaveBeenLastCalledWith(
      [expect.objectContaining({ hole_id: 'P-01' })], 10, expect.objectContaining({ visible: 1 }),
    ));
  });

  it('counts only drawable filtered collars and keeps the excluded geometry count independent of filters', async () => {
    const onFilteredChange = vi.fn();
    render(<BlastHoleFilters holes={[makeHole(), makeHole({ row_id: 'row-2', hole_id: 'P-02', collar: null, geometry_status: 'none' })]} onFilteredChange={onFilteredChange} />);
    fireEvent.change(screen.getByLabelText('Buscar ID'), { target: { value: 'P-02' } });
    await waitFor(() => expect(onFilteredChange).toHaveBeenLastCalledWith(
      [expect.objectContaining({ hole_id: 'P-02' })], 10,
      expect.objectContaining({ visible: 0, excludedGeometry: 1 }),
    ));
  });

  it('disables section filters without a section, resets relation when it disappears, and can clear filters', async () => {
    const { rerender } = render(<BlastHoleFilters holes={[makeHole()]} hasSection onFilteredChange={vi.fn()} />);
    const sectionControl = screen.getByLabelText('Sección');
    fireEvent.change(sectionControl, { target: { value: 'near_section' } });
    rerender(<BlastHoleFilters holes={[makeHole()]} hasSection={false} onFilteredChange={vi.fn()} />);
    expect(screen.getByLabelText('Sección')).toHaveProperty('disabled', true);
    expect(screen.getByLabelText('Corredor')).toHaveProperty('disabled', true);
    expect(screen.getByText('Elija una sección')).toBeTruthy();
    await waitFor(() => expect((screen.getByLabelText('Sección') as HTMLSelectElement).value).toBe(''));
    fireEvent.change(screen.getByLabelText('Buscar ID'), { target: { value: 'P-01' } });
    fireEvent.click(screen.getByText('Limpiar filtros'));
    expect((screen.getByLabelText('Buscar ID') as HTMLInputElement).value).toBe('');
  });

  it('filters collar provenance and surface-sampling status independently', () => {
    const hole = makeHole({ provenance: { z_collar_semantic: 'design_surface_estimate', surface_sample_status: 'sampled' } });
    expect(filterBlastHoles([hole], { ...base, provenance: 'design_surface_estimate' })).toEqual([hole]);
    expect(filterBlastHoles([hole], { ...base, surfaceSampleStatus: 'sampled' })).toEqual([hole]);
    expect(filterBlastHoles([hole], { ...base, provenance: 'design_surface_estimate', surfaceSampleStatus: 'sampled' })).toEqual([hole]);
    const noSampleStatus = makeHole({ provenance: { z_collar_semantic: 'design_surface_estimate', surface_sample_status: null } });
    expect(filterBlastHoles([noSampleStatus], { ...base, provenance: 'design_surface_estimate', surfaceSampleStatus: '__missing__' })).toEqual([noSampleStatus]);
    expect(filterBlastHoles([hole], { ...base, provenance: 'sampled' })).toEqual([]);
    expect(filterBlastHoles([hole], { ...base, provenance: 'design_surface_estimate', surfaceSampleStatus: 'outside' })).toEqual([]);
  });

  it('supports explicit missing-data filters for bench, date, and provenance', () => {
    const missing = makeHole({ row_id: 'missing', attributes: {}, provenance: {} });
    const populated = makeHole();
    const missingFilters = {
      ...base, bench: '__missing__', datePresence: '__missing__', provenance: '__missing__', surfaceSampleStatus: '__missing__',
    };
    expect(filterBlastHoles([missing, populated], missingFilters)).toEqual([missing]);
    expect(filterBlastHoles([missing, populated], { ...missingFilters, bench: '3150' })).toEqual([]);
    expect(filterBlastHoles([missing, populated], { ...missingFilters, datePresence: '__present__' })).toEqual([]);
    expect(filterBlastHoles([missing, populated], { ...missingFilters, surfaceSampleStatus: 'sampled' })).toEqual([]);
  });

  it('searches event IDs independently while date-presence filters remain about dates only', () => {
    const withBoth = makeHole({ attributes: { fecha_tronadura: '2026-10-31', event_id: 'voladura-norte' } });
    const eventWithoutDate = makeHole({ row_id: 'event-only', attributes: { event_id: 'voladura-sur' } });

    expect(filterBlastHoles([withBoth, eventWithoutDate], { ...base, date: 'voladura-norte' })).toEqual([withBoth]);
    expect(filterBlastHoles([withBoth, eventWithoutDate], {
      ...base, date: 'voladura-sur', datePresence: '__missing__',
    })).toEqual([eventWithoutDate]);
    expect(filterBlastHoles([withBoth, eventWithoutDate], {
      ...base, date: 'voladura-sur', datePresence: '__present__',
    })).toEqual([]);
    expect(filterBlastHoles([withBoth, eventWithoutDate], {
      ...base, date: 'voladura-norte', datePresence: '__present__',
    })).toEqual([withBoth]);
  });

  it('combines Streamlit category filters with OR within a category and AND across categories', () => {
    const first = makeHole({ attributes: {
      Nombre_Malla_Original: 'Malla 1', holes_polygon: 'Polígono A', Banco_Original: '3150', Nombre_Fase: 'Fase Norte',
    } });
    const second = makeHole({ row_id: 'row-2', attributes: {
      Nombre_Malla_Original: 'Malla 2', holes_polygon: 'Polígono B', Banco_Original: '3150', Nombre_Fase: 'Fase Sur',
    } });
    const third = makeHole({ row_id: 'row-3', attributes: {
      Nombre_Malla_Original: 'Malla 3', holes_polygon: 'Polígono A', Banco_Original: '3200', Nombre_Fase: 'Fase Norte',
    } });
    expect(filterBlastHoles([first, second, third], {
      ...base, grid: ['Malla 1', 'Malla 2'], polygon: ['Polígono A', 'Polígono B'],
      originalBench: ['3150'], phase: ['Fase Norte', 'Fase Sur'],
    })).toEqual([first, second]);
  });

  it('filters numeric depth and charge ranges without coercing missing values to zero', () => {
    const inRange = makeHole({ attributes: { Len: 20, Kilos_Cargados_real: 500 } });
    const tooShort = makeHole({ row_id: 'short', attributes: { Len: 8, Kilos_Cargados_real: 500 } });
    const missing = makeHole({ row_id: 'missing', attributes: { Len: null, Kilos_Cargados_real: null } });
    expect(filterBlastHoles([inRange, tooShort, missing], {
      ...base, depthMin: '10', depthMax: '30', chargeMin: '400', chargeMax: '600',
    })).toEqual([inRange]);
    expect(filterBlastHoles([inRange, missing], { ...base, depthMin: '0' })).toEqual([inRange]);
    expect(filterBlastHoles([missing], base)).toEqual([missing]);
  });

  it('uses the supported depth and charge aliases in Streamlit priority order', () => {
    const aliased = makeHole({ attributes: { longitud_real: 18, Kilos_Cargados: 250 } });
    expect(filterBlastHoles([aliased], {
      ...base, depthMin: '15', depthMax: '20', chargeMin: '200', chargeMax: '300',
    })).toEqual([aliased]);

    const preferred = makeHole({ attributes: {
      Len: 25, longitud_real: 5, Kilos_Cargados_real: 700, Kilos_Cargados: 100,
    } });
    expect(filterBlastHoles([aliased, preferred], {
      ...base, depthMin: '15', depthMax: '20', chargeMin: '200', chargeMax: '300',
    })).toEqual([]);
    expect(filterBlastHoles([aliased, preferred], {
      ...base, depthMin: '20', depthMax: '30', chargeMin: '600', chargeMax: '800',
    })).toEqual([preferred]);
  });

  it('resolves phase and bench aliases once per dataset and preserves nulls in preferred columns', () => {
    const fallback = makeHole({ attributes: { Fase: 'Fase Norte', Banco: '3150' } });
    expect(filterBlastHoles([fallback], { ...base, phase: ['Fase Norte'], originalBench: ['3150'] })).toEqual([fallback]);

    const missingPreferred = makeHole({ row_id: 'missing-preferred', attributes: {
      Nombre_Fase: null, Fase: 'Fase Norte', Nombre_Banco: null, Banco: '3150',
    } });
    const populatedPreferred = makeHole({ row_id: 'preferred', attributes: {
      Nombre_Fase: 'Fase Sur', Fase: 'Fase Norte', Nombre_Banco: '3200', Banco: '3150',
    } });
    expect(filterBlastHoles([missingPreferred, populatedPreferred], {
      ...base, phase: ['Fase Norte'], originalBench: ['3150'],
    })).toEqual([]);
    expect(filterBlastHoles([missingPreferred, populatedPreferred], {
      ...base, phase: ['Fase Sur'], originalBench: ['3200'],
    })).toEqual([populatedPreferred]);
  });

  it('renders searchable category filters and accessible range controls', () => {
    render(<BlastHoleFilters holes={[makeHole({ provenance: { z_collar_semantic: 'design_surface_estimate', surface_sample_status: 'sampled' }, attributes: {
      Nombre_Malla_Original: 'Malla 1', holes_polygon: 'Polígono A', Banco_Original: '3150', Nombre_Fase: 'Fase Norte', Len: 12, Kilos_Cargados_real: 400,
    } })]} />);
    expect(screen.getByLabelText('Buscar opciones: Malla (Grid)')).toBeTruthy();
    expect(screen.getByLabelText('Buscar opciones: Polígono')).toBeTruthy();
    expect(screen.getByLabelText('Profundidad (m): Mínimo')).toBeTruthy();
    expect(screen.getByLabelText('Explosivo (kg): Máximo')).toBeTruthy();
    expect(screen.getByLabelText('Procedencia de cota')).toBeTruthy();
    expect(screen.getByLabelText('Estado de muestreo de superficie')).toBeTruthy();
  });

  it('keeps null-valued fields available and clears only filters whose columns disappear after a dataset change', async () => {
    const onFilteredChange = vi.fn();
    const { rerender } = render(<BlastHoleFilters onFilteredChange={onFilteredChange} holes={[makeHole({ attributes: {
      Nombre_Malla_Original: 'Malla 1', holes_polygon: null, Banco_Original: null, Nombre_Fase: null,
      Len: 12, Kilos_Cargados_real: 400, bench_num_topo: '3150',
    } })]} />);
    expect(screen.getByLabelText('Buscar opciones: Malla (Grid)')).toBeTruthy();
    expect(screen.getByLabelText('Buscar opciones: Polígono')).toBeTruthy();
    expect(screen.getByLabelText('Buscar opciones: Banco de tronadura')).toBeTruthy();
    expect(screen.getByLabelText('Buscar opciones: Fase')).toBeTruthy();
    expect(screen.getByLabelText('Profundidad (m): Mínimo')).toBeTruthy();
    expect(screen.getByLabelText('Explosivo (kg): Máximo')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Buscar opciones: Malla (Grid)'), { target: { value: 'Malla 1' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Malla 1' }));
    fireEvent.change(screen.getByLabelText('Profundidad (m): Mínimo'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Explosivo (kg): Mínimo'), { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('Banco'), { target: { value: '3150' } });

    const retained = makeHole({ row_id: 'new-3150', attributes: { bench_num_topo: '3150' } });
    const excludedByAvailableBench = makeHole({ row_id: 'new-3200', attributes: { bench_num_topo: '3200' } });
    rerender(<BlastHoleFilters onFilteredChange={onFilteredChange} holes={[retained, excludedByAvailableBench]} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Se limpiaron filtros porque sus columnas ya no están disponibles.');
    await waitFor(() => expect(onFilteredChange).toHaveBeenLastCalledWith(
      [retained], 10, expect.objectContaining({ total: 2, visible: 1 }),
    ));

    expect(screen.queryByLabelText('Buscar opciones: Malla (Grid)')).toBeNull();
    expect(screen.queryByLabelText('Buscar opciones: Polígono')).toBeNull();
    expect(screen.queryByLabelText('Buscar opciones: Banco de tronadura')).toBeNull();
    expect(screen.queryByLabelText('Buscar opciones: Fase')).toBeNull();
    expect(screen.queryByLabelText('Profundidad (m): Mínimo')).toBeNull();
    expect(screen.queryByLabelText('Explosivo (kg): Máximo')).toBeNull();
  });

  it('clears category values that disappear from a same-schema dataset but retains values hidden by other filters', async () => {
    const first = makeHole({ row_id: 'first', hole_id: 'P-01', attributes: { Nombre_Malla_Original: 'Malla 1' } });
    const second = makeHole({ row_id: 'second', hole_id: 'P-02', attributes: { Nombre_Malla_Original: 'Malla 2' } });
    const onFilteredChange = vi.fn();
    const { rerender } = render(<BlastHoleFilters holes={[first, second]} onFilteredChange={onFilteredChange} />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Malla 1' }));
    fireEvent.change(screen.getByLabelText('Buscar ID'), { target: { value: 'P-02' } });
    expect(screen.getByText('1 seleccionados')).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();

    rerender(<BlastHoleFilters holes={[second]} onFilteredChange={onFilteredChange} />);
    await waitFor(() => expect(screen.queryByText('1 seleccionados')).toBeNull());
    expect(await screen.findByRole('status')).toHaveTextContent('Se limpiaron filtros porque sus columnas ya no están disponibles.');
    await waitFor(() => expect(onFilteredChange).toHaveBeenLastCalledWith(
      [second], 10, expect.objectContaining({ total: 1, visible: 1 }),
    ));
    expect((screen.getByLabelText('Buscar ID') as HTMLInputElement).value).toBe('P-02');
  });
});
