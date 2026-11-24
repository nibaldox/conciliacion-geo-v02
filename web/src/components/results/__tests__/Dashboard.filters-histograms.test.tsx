import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import i18n from '../../../i18n';
import { buildHistogram, Dashboard, filterByBench } from '../Dashboard';
import { useBenchFocus } from '../../../stores/benchFocus';
import type { ComparisonResult } from '../../../api/types';

const mocks = vi.hoisted(() => ({
  rows: [] as unknown[],
  sections: [{ id: '0', name: 'S-001', length: 200 }] as Array<{ id: string; name: string; length?: number }>,
  tolerances: null as Record<string, Record<string, number>> | null,
  designFilename: 'diseno_f10.stl' as string | null,
  topoFilename: 'topo_ene.stl' as string | null,
  setSelectedSection: vi.fn(),
  setProfilesMode: vi.fn(),
  setActiveWorkspaceView: vi.fn(),
  filters: { sector: [], section: [], level: [], bench: [] } as {
    sector: string[];
    section: string[];
    level: string[];
    bench: number[];
  },
}));

vi.mock('../../../api/hooks', () => ({
  useResults: () => ({ data: mocks.rows }),
  useSections: () => ({ data: mocks.sections }),
  useProfile: () => ({ data: null, isPending: false, isError: false }),
  useMeshInfo: (meshId: string | null) => ({
    data:
      meshId === 'design-1' && mocks.designFilename
        ? { filename: mocks.designFilename }
        : meshId === 'topo-1' && mocks.topoFilename
          ? { filename: mocks.topoFilename }
          : undefined,
  }),
  useSettings: () => ({
    data: mocks.tolerances === null ? undefined : { tolerances: mocks.tolerances },
  }),
}));

vi.mock('../../../stores/session', () => ({
  useSession: (selector: (s: unknown) => unknown) =>
    selector({
      designMeshId: 'design-1',
      topoMeshId: 'topo-1',
      filters: mocks.filters,
      setSelectedSection: mocks.setSelectedSection,
      setProfilesMode: mocks.setProfilesMode,
      setActiveWorkspaceView: mocks.setActiveWorkspaceView,
      setFilters: (f: Record<string, unknown>) => {
        mocks.filters = { ...mocks.filters, ...f } as typeof mocks.filters;
      },
    }),
}));

vi.mock('../CompliancePlanView', () => ({
  CompliancePlanView: (props: {
    results: ComparisonResult[];
    variant?: string;
    colorBy?: string;
    visibleStatuses?: Set<string>;
    onSelectSection?: (name: string) => void;
  }) => (
    <button
      data-testid="plan"
      data-rows={props.results.length}
      data-variant={props.variant}
      data-color={props.colorBy}
      data-has-visible-statuses={props.visibleStatuses ? 'yes' : 'no'}
      onClick={() => props.onSelectSection?.('S-001')}
    >
      Select plan
    </button>
  ),
}));

vi.mock('../DesignAchievementPanel', () => ({
  DesignAchievementPanel: () => <div data-testid="design-achievement-panel" />,
}));

vi.mock('../ProposalSummaryCard', () => ({
  ProposalSummaryCard: () => <div data-testid="proposal-summary-card" />,
}));

vi.mock('../../charts/Plot', () => ({
  default: (props: { data?: unknown; layout?: unknown }) => (
    <div
      data-testid="plot"
      data-data={JSON.stringify(props.data ?? [])}
      data-layout={JSON.stringify(props.layout ?? {})}
    />
  ),
}));

function makeRow(overrides: Partial<ComparisonResult> = {}): ComparisonResult {
  return {
    sector: 'Norte',
    section: 'S-001',
    bench_num: 1,
    type: 'MATCH',
    level: '3150',
    height_design: 15,
    height_real: 15,
    height_dev: 0,
    height_status: 'CUMPLE',
    angle_design: 65,
    angle_real: 65,
    angle_dev: 0,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 8,
    berm_min: 5,
    berm_status: 'CUMPLE',
    delta_crest: 0,
    delta_toe: 0,
    ...overrides,
  };
}

beforeAll(async () => {
  await i18n.changeLanguage('es');
});

beforeEach(() => {
  mocks.sections = [{ id: '0', name: 'S-001', length: 200 }];
  mocks.tolerances = null;
  mocks.designFilename = 'diseno_f10.stl';
  mocks.topoFilename = 'topo_ene.stl';
  mocks.filters = { sector: [], section: [], level: [], bench: [] };
  mocks.setSelectedSection.mockClear();
  mocks.setProfilesMode.mockClear();
  mocks.setActiveWorkspaceView.mockClear();
  useBenchFocus.setState({ request: null, current: null });
});

function plotData(): { data: unknown; layout: { shapes?: { type?: string; x0: number; x1: number }[] } }[] {
  return screen
    .getAllByTestId('plot')
    .map((node) => ({
      data: JSON.parse(node.getAttribute('data-data') ?? '[]'),
      layout: JSON.parse(node.getAttribute('data-layout') ?? '{}') as {
        shapes?: { type?: string; x0: number; x1: number }[];
      },
    }));
}

describe('buildHistogram (bandas de tolerancia)', () => {
  it('dibuja banda asimétrica -neg/+pos', () => {
    const chart = buildHistogram([0], 't', 'x', { neg: 1, pos: 1.5 }, 'frecuencia');
    const shape = chart.layout.shapes?.[0];
    expect(shape?.x0).toBe(-1);
    expect(shape?.x1).toBe(1.5);
  });

  it('dibuja banda unilateral mínima para berma (nunca simétrica)', () => {
    const chart = buildHistogram([7, 10], 't', 'x', { min: 6 }, 'frecuencia');
    const shape = chart.layout.shapes?.[0];
    expect(shape?.x0).toBe(6);
    expect(shape?.x1).toBe(10);
  });

  it('sin valores la banda es degenerada en el mínimo y el trazo no trae datos falsos', () => {
    const chart = buildHistogram([], 't', 'x', { min: 6 }, 'frecuencia');
    const shape = chart.layout.shapes?.[0];
    expect(shape?.x0).toBe(6);
    expect(shape?.x1).toBe(6);
    const trace = chart.data[0] as { x: number[] };
    expect(trace.x).toEqual([]);
  });

  it('conserva los ceros cuando hay valores', () => {
    const chart = buildHistogram([0, 2, 0], 't', 'x', { neg: 1, pos: 1 }, 'frecuencia');
    const trace = chart.data[0] as { x: number[] };
    expect(trace.x).toEqual([0, 2, 0]);
  });
});

describe('Dashboard filtros compactos y barra de contexto', () => {
  it('muestra barra de contexto con nombres de mallas, largo y popover de filtros anclado', () => {
    mocks.rows = [makeRow()];
    const { container } = render(<Dashboard />);
    const contextBar = container.querySelector('[data-slot="dashboard-context-bar"]')!;
    expect(contextBar.textContent).toContain('diseno_f10.stl');
    expect(contextBar.textContent).toContain('topo_ene.stl');
    expect(contextBar.textContent).toContain('200 m');

    fireEvent.click(screen.getByRole('button', { name: 'Filtros' }));
    const panel = container.querySelector('#dashboard-filter-panel')!;
    expect(panel.className).toContain('right-0');
    for (const details of panel.querySelectorAll('details')) {
      expect(details.className).toContain('relative');
      expect(details.querySelector('summary')!.nextElementSibling!.className).toContain('left-0');
      expect(details.closest('[data-dimension], [data-slot="dashboard-bench-filter"]')!.querySelector('p')!.className).toContain('whitespace-nowrap');
    }
    expect(panel.querySelector('[data-slot="dashboard-bench-filter"]')!.className).toContain('flex-wrap');
  });

  it('mantiene controles principales visibles, elimina chips de estado y despliega filtros con Escape', () => {
    mocks.rows = [makeRow(), makeRow({ bench_num: 2 })];
    const { container, rerender } = render(<Dashboard />);
    expect(screen.getByRole('group', { name: 'Colorear por' })).toBeVisible();
    expect(screen.queryByRole('group', { name: 'Filtrar por estado' })).toBeNull();
    expect(container.querySelector('[data-slot="dashboard-bench-filter"]')).toBeNull();
    expect(container.querySelector('[data-slot="result-filters"]')).toBeNull();

    const toggle = screen.getByRole('button', { name: 'Filtros' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(container.querySelector('[data-slot="dashboard-bench-filter"]')).toBeVisible();
    expect(container.querySelector('[data-slot="result-filters"]')).toBeVisible();

    mocks.filters = { sector: ['Norte'], section: [], level: [], bench: [1] };
    rerender(<Dashboard />);
    expect(screen.getByRole('button', { name: 'Filtros · 2' })).toBeVisible();
    expect(container.querySelector('[data-slot="dashboard-active-filters"]')).toBeTruthy();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'Filtros · 2' })).toHaveAttribute('aria-expanded', 'false');
    expect(container.querySelector('[data-slot="result-filters"]')).toBeNull();
  });

  it('aplica banco desde el panel a la planta y cierra al pulsar fuera', () => {
    mocks.rows = [makeRow(), makeRow({ bench_num: 2, level: '3200' })];
    const { container, rerender } = render(<Dashboard />);
    expect(screen.getByTestId('plan')).toHaveAttribute('data-rows', '2');
    fireEvent.click(screen.getByRole('button', { name: 'Filtros' }));
    fireEvent.click(container.querySelector('[data-slot="dashboard-bench-filter"] summary')!);
    fireEvent.click(screen.getByRole('checkbox', { name: /Cota base de diseño 3150/ }));
    expect(mocks.filters.bench).toEqual([1]);
    rerender(<Dashboard />);
    expect(screen.getByTestId('plan')).toHaveAttribute('data-rows', '1');
    expect(screen.getByRole('button', { name: 'Filtros · 1' })).toBeVisible();
    fireEvent.pointerDown(document.body);
    expect(screen.getByRole('button', { name: 'Filtros · 1' })).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('Dashboard jerarquía geotécnica (Ola 3)', () => {
  it('conecta hero (default berm), cobertura, KPIs sin Fuera, tabla por cota, lista prioritaria y selección', () => {
    mocks.sections = [
      { id: '0', name: 'S-001', length: 200 },
      { id: '1', name: 'S-002', length: 200 },
    ];
    mocks.rows = [
      makeRow({ section: 'S-001', bench_num: 1, level: '3150', berm_real: 8, bench_score: 100 }),
      makeRow({
        section: 'S-001',
        bench_num: 2,
        level: '3135',
        berm_design: 8,
        berm_real: 3.5,
        berm_min: 7,
        berm_status: 'NO CUMPLE',
        delta_crest: 4.2,
        bench_score: 40,
      }),
    ];
    const { container } = render(<Dashboard />);

    const plan = screen.getByTestId('plan');
    expect(plan).toHaveAttribute('data-variant', 'hero');
    expect(plan).toHaveAttribute('data-color', 'berm');
    expect(plan).toHaveAttribute('data-has-visible-statuses', 'no');

    expect(container.querySelector('[data-slot="dashboard-coverage"]')).toBeTruthy();
    expect(container.querySelector('[data-slot="dashboard-coverage-count"]')?.textContent).toContain('1 de 2 secciones');
    expect(container.querySelector('[data-slot="dashboard-coverage-count"]')?.textContent).toContain('2 comparados');

    const kpis = container.querySelector('[data-slot="dashboard-kpis"]')!;
    expect(kpis.textContent).not.toContain('Fuera de tolerancia');
    expect(kpis.textContent).toContain('70,0');

    fireEvent.click(screen.getByRole('button', { name: 'Puntaje' }));
    expect(plan).toHaveAttribute('data-color', 'score');

    fireEvent.click(plan);
    const selectedPanel = container.querySelector('[data-slot="selected-section"]')!;
    expect(selectedPanel.textContent).toContain('S-001');
    fireEvent.click(within(selectedPanel as HTMLElement).getByRole('button', { name: /Abrir perfil/ }));
    expect(mocks.setSelectedSection).toHaveBeenCalledWith('0');
    expect(mocks.setProfilesMode).toHaveBeenCalledWith('detail');
    expect(mocks.setActiveWorkspaceView).toHaveBeenCalledWith('profiles');

    const levelTable = container.querySelector('[data-slot="level-compliance-table"]')!;
    fireEvent.click(levelTable.querySelector('tr[data-level="3135"]')!);
    expect(mocks.filters.level).toEqual(['3135']);

    mocks.setSelectedSection.mockClear();
    mocks.setProfilesMode.mockClear();
    mocks.setActiveWorkspaceView.mockClear();
    const priorityList = container.querySelector('[data-slot="priority-review-list"]')!;
    const priorityBtn = within(priorityList as HTMLElement).getByRole('button', { name: /Abrir perfil de la sección S-001/ });
    fireEvent.click(priorityBtn);
    expect(mocks.setSelectedSection).toHaveBeenCalledWith('0');
    expect(mocks.setProfilesMode).toHaveBeenCalledWith('detail');
    expect(mocks.setActiveWorkspaceView).toHaveBeenCalledWith('profiles');
    expect(useBenchFocus.getState().request).toMatchObject({ sectionId: '0', designBench: 2 });
  });

  it('oculta Cumplimiento por sector cuando no hay sectores asignados y colapsa métricas complementarias', () => {
    mocks.rows = [makeRow({ sector: '' })];
    const { container } = render(<Dashboard />);
    expect(container.querySelector('[data-slot="sector-compliance"]')).toBeNull();
    const complementary = container.querySelector('details[data-slot="complementary-metrics"]') as HTMLDetailsElement;
    expect(complementary).toBeTruthy();
    expect(complementary.open).toBe(false);
    expect(screen.getByTestId('design-achievement-panel')).toBeTruthy();
    expect(screen.getByTestId('proposal-summary-card')).toBeTruthy();
  });

  it('muestra Sin dato en KPIs solo cuando existen perfiles UNKNOWN', () => {
    mocks.rows = [makeRow({ section: 'S-001', type: 'MISSING', height_status: 'NO CONSTRUIDO', angle_status: '-', berm_status: 'FALTA BANCO' })];
    const { container } = render(<Dashboard />);
    const kpis = container.querySelector('[data-slot="dashboard-kpis"]')!;
    expect(kpis.textContent).toContain('Sin dato');
  });
});

describe('Dashboard filtros compartidos', () => {
  it('mantiene el helper legacy filterByBench', () => {
    expect(typeof filterByBench).toBe('function');
  });

  it('aplica filterResults a todos los agregados con filtros de sesión', () => {
    mocks.rows = [
      makeRow({ sector: 'Norte', bench_num: 1 }),
      makeRow({ sector: 'Sur', bench_num: 2 }),
      makeRow({ sector: 'Sur', bench_num: 3 }),
    ];
    mocks.filters = { sector: ['Sur'], section: [], level: [], bench: [] };
    render(<Dashboard />);
    const serialized = screen
      .getAllByTestId('plot')
      .map((node) => node.getAttribute('data-data') ?? '');
    expect(serialized.every((json) => !json.includes('"Norte"'))).toBe(true);
    expect(serialized.some((json) => json.includes('"Sur"'))).toBe(true);
    expect(screen.getByTestId('design-achievement-panel')).toBeTruthy();
  });

  it('usa tokens de tema en lugar de colores hex fijos en los gráficos', () => {
    mocks.rows = [
      makeRow({ sector: 'Norte' }),
      makeRow({ sector: 'Sur', height_status: 'NO CUMPLE', angle_status: 'NO CUMPLE', berm_status: 'NO CUMPLE' }),
    ];
    render(<Dashboard />);
    const serialized = screen
      .getAllByTestId('plot')
      .map((node) => `${node.getAttribute('data-data')}${node.getAttribute('data-layout')}`)
      .join('');
    expect(serialized).not.toMatch(/#[0-9a-fA-F]{6}/);
    expect(serialized).toContain('var(--status-ok-text)');
    expect(serialized).toContain('var(--status-nok-text)');
  });

  it('explica que la combinación de filtros activa no tiene resultados', () => {
    mocks.rows = [makeRow()];
    mocks.filters = { sector: ['Sur'], section: ['S-002'], level: ['3200'], bench: [2] };
    render(<Dashboard />);
    expect(screen.getByText(/Ningún resultado coincide con la combinación de filtros activa/)).toBeTruthy();
    expect(screen.queryByText('Desviación de Altura (m)')).toBeNull();
  });
});

describe('Dashboard distribución de desviaciones en grilla de 5 mini-histogramas', () => {
  it('renderiza los cinco mini-histogramas simultáneamente con bandas asimétricas y mínimo de berma', () => {
    mocks.rows = [
      makeRow({ height_dev: 0.2, angle_dev: 0.5, delta_crest: 0.1, delta_toe: -0.4, berm_real: 7 }),
    ];
    mocks.tolerances = {
      bench_height: { neg: 0.7, pos: 1.3 },
      face_angle: { neg: 4, pos: 2 },
      berm_width: { min: 5.5 },
      crest_toe_deviation: { neg: 0.9, pos: 1.1 },
    };
    const { container } = render(<Dashboard />);
    const grid = container.querySelector('[data-slot="deviation-histograms-grid"]')!;
    expect(grid).toBeTruthy();
    for (const key of ['height', 'angle', 'crest', 'toe', 'berm']) {
      expect(grid.querySelector(`[data-slot="histogram-card-${key}"]`)).toBeTruthy();
    }
    const rectBands = plotData()
      .flatMap((plot) => (plot.layout.shapes ?? []).filter((shape) => shape.type === 'rect'))
      .map((shape) => [shape.x0, shape.x1]);
    expect(rectBands.some(([x0, x1]) => x0 === -0.7 && x1 === 1.3)).toBe(true);
    expect(rectBands.some(([x0, x1]) => x0 === -0.9 && x1 === 1.1)).toBe(true);
    const bermBand = rectBands.find(([x0]) => x0 === 5.5);
    expect(bermBand).toBeDefined();
    expect(bermBand![1]).toBeGreaterThan(5.5);
  });

  it('recurre a DEFAULT_TOLERANCES sin configuración', () => {
    mocks.rows = [makeRow({ berm_real: 8 })];
    render(<Dashboard />);
    const rectBands = plotData()
      .flatMap((plot) => (plot.layout.shapes ?? []).filter((shape) => shape.type === 'rect'))
      .map((shape) => [shape.x0, shape.x1]);
    expect(rectBands.some(([x0, x1]) => x0 === -2 && x1 === 2)).toBe(true);
    expect(rectBands.some(([x0, x1]) => x0 === 7 && x1 > 7)).toBe(true);
  });
});

describe('Dashboard rail parameter detail', () => {
  it('places DirectionalSummary, compact 5-column parameter detail (sin No comparados) and SelectedSectionPanel in order', () => {
    mocks.rows = [makeRow()];
    const { container } = render(<Dashboard />);
    const rail = container.querySelector('[data-slot="dashboard-rail"]')!;
    const directional = rail.querySelector('[data-slot="directional-summary"]')!;
    const details = rail.querySelector('details[data-slot="parameter-detail"]')!;
    expect(directional.nextElementSibling).toBe(details);
    expect(details.nextElementSibling).toHaveAttribute('data-slot', 'selected-section');
    expect(details.querySelectorAll('[data-parameter]')).toHaveLength(3);
    expect(details.querySelectorAll('thead th')).toHaveLength(5);
    expect(details.querySelector('[data-col="no-comparados"]')).toBeNull();
  });
});
