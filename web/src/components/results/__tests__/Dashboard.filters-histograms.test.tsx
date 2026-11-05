import { beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import i18n from '../../../i18n';
import { buildHistogram, Dashboard, filterByBench } from '../Dashboard';
import type { ComparisonResult } from '../../../api/types';

const mocks = vi.hoisted(() => ({
  rows: [] as unknown[],
  tolerances: null as Record<string, Record<string, number>> | null,
  filters: { sector: [], section: [], level: [], bench: [] } as {
    sector: string[];
    section: string[];
    level: string[];
    bench: number[];
  },
}));

vi.mock('../../../api/hooks', () => ({
  useResults: () => ({ data: mocks.rows }),
  useSettings: () => ({
    data: mocks.tolerances === null ? undefined : { tolerances: mocks.tolerances },
  }),
}));

vi.mock('../../../stores/session', () => ({
  useSession: (selector: (s: unknown) => unknown) =>
    selector({
      filters: mocks.filters,
      setFilters: (f: Record<string, unknown>) => {
        mocks.filters = { ...mocks.filters, ...f } as typeof mocks.filters;
      },
    }),
}));

vi.mock('../CompliancePlanView', () => ({
  CompliancePlanView: () => null,
}));

vi.mock('../DesignAchievementPanel', () => ({
  DesignAchievementPanel: () => <div data-testid="design-achievement-panel" />,
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
  i18n.addResource('es', 'translation', 'dashboard.filters.no_matching_results', 'Ningún resultado coincide con la combinación de filtros activa. Ajusta o restablece los filtros de sector, sección, nivel o banco.');
  await i18n.changeLanguage('es');
});

const HISTOGRAM_SEGMENTS = ['Altura', 'Ángulo', 'Cresta', 'Pata', 'Berma'];

function histogramGroup(): HTMLElement {
  return screen.getByRole('group', { name: 'Variable del histograma' });
}

function selectHistogram(label: string): void {
  const button = [...histogramGroup().querySelectorAll('button')].find((node) => node.textContent === label);
  if (!button) throw new Error(`missing segment ${label}`);
  fireEvent.click(button);
}

function collectHistogramBands(): number[][] {
  const bands: number[][] = [];
  for (const label of HISTOGRAM_SEGMENTS) {
    selectHistogram(label);
    const plots = plotData();
    const histogram = plots[plots.length - 1]!;
    for (const shape of histogram.layout.shapes ?? []) bands.push([shape.x0, shape.x1]);
  }
  return bands;
}

function plotData(): { data: unknown; layout: { shapes?: { x0: number; x1: number }[] } }[] {
  return screen
    .getAllByTestId('plot')
    .map((node) => ({
      data: JSON.parse(node.getAttribute('data-data') ?? '[]'),
      layout: JSON.parse(node.getAttribute('data-layout') ?? '{}') as { shapes?: { x0: number; x1: number }[] },
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
    mocks.tolerances = null;
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
    mocks.rows = [makeRow({ sector: 'Norte' }), makeRow({ sector: 'Sur', height_status: 'NO CUMPLE', angle_status: 'NO CUMPLE', berm_status: 'NO CUMPLE' })];
    mocks.tolerances = null;
    mocks.filters = { sector: [], section: [], level: [], bench: [] };
    render(<Dashboard />);
    const serialized = screen.getAllByTestId('plot').map((node) => `${node.getAttribute('data-data')}${node.getAttribute('data-layout')}`).join('');
    expect(serialized).not.toMatch(/#[0-9a-fA-F]{6}/);
    expect(serialized).toContain('var(--status-ok-text)');
    expect(serialized).toContain('var(--status-nok-text)');
  });

  it('explica que la combinación de filtros activa no tiene resultados', () => {
    mocks.rows = [makeRow()];
    mocks.tolerances = null;
    mocks.filters = { sector: ['Sur'], section: ['S-002'], level: ['3200'], bench: [2] };
    render(<Dashboard />);
    expect(screen.getByRole('status').textContent).toBe(
      'Ningún resultado coincide con la combinación de filtros activa. Ajusta o restablece los filtros de sector, sección, nivel o banco.',
    );
    expect(screen.queryByText('Desviación de Altura (m)')).toBeNull();
  });
});

describe('Dashboard distribución de desviaciones con selector', () => {
  it('agrupa los cinco histogramas en una sección con selector y un solo gráfico', () => {
    mocks.rows = [makeRow()];
    mocks.tolerances = {
      bench_height: { neg: 0.7, pos: 1.3 },
      face_angle: { neg: 4, pos: 2 },
      berm_width: { min: 5.5 },
      crest_toe_deviation: { neg: 0.9, pos: 1.1 },
    };
    mocks.filters = { sector: [], section: [], level: [], bench: [] };
    render(<Dashboard />);
    expect(screen.getByText('Distribución de desviaciones')).toBeTruthy();
    const segments = [...histogramGroup().querySelectorAll('button')].map((node) => node.textContent);
    expect(segments).toEqual(HISTOGRAM_SEGMENTS);
    const plotCount = screen.getAllByTestId('plot').length;
    expect(screen.getAllByText('Desviación de Altura (m)').length).toBe(1);
    selectHistogram('Pata');
    expect(screen.getAllByText('Desviación de Pata (m)').length).toBe(1);
    expect(screen.queryByText('Desviación de Altura (m)')).toBeNull();
    selectHistogram('Berma');
    expect(screen.getAllByText('Ancho de berma (m)').length).toBe(1);
    expect(screen.getAllByTestId('plot').length).toBe(plotCount);
    expect(histogramGroup().querySelector('[aria-pressed="true"]')?.textContent).toBe('Berma');
  });

  it('usa bandas asimétricas de tolerancia y mínimo de berma', () => {
    mocks.rows = [
      makeRow({ height_dev: 0.2, angle_dev: 0.5, delta_crest: 0.1, delta_toe: -0.4, berm_real: 7 }),
    ];
    mocks.tolerances = {
      bench_height: { neg: 0.7, pos: 1.3 },
      face_angle: { neg: 4, pos: 2 },
      berm_width: { min: 5.5 },
      crest_toe_deviation: { neg: 0.9, pos: 1.1 },
    };
    mocks.filters = { sector: [], section: [], level: [], bench: [] };
    render(<Dashboard />);
    const bands = collectHistogramBands();
    expect(bands.some(([x0, x1]) => x0 === -0.7 && x1 === 1.3)).toBe(true);
    expect(bands.some(([x0, x1]) => x0 === -0.9 && x1 === 1.1)).toBe(true);
    const bermBand = bands.find(([x0]) => x0 === 5.5);
    expect(bermBand).toBeDefined();
    expect(bermBand![1]).toBeGreaterThan(5.5);
  });

  it('recurre a DEFAULT_TOLERANCES sin configuración', () => {
    mocks.rows = [makeRow({ berm_real: 6.5 })];
    mocks.tolerances = null;
    mocks.filters = { sector: [], section: [], level: [], bench: [] };
    render(<Dashboard />);
    const bands = collectHistogramBands();
    expect(bands.some(([x0, x1]) => x0 === -1 && x1 === 1.5)).toBe(true);
    expect(bands.some(([x0, x1]) => x0 === 6 && x1 > 6)).toBe(true);
  });
});
