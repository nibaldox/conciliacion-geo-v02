import i18n from '../../../i18n';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { Config, Data, Layout } from 'plotly.js';
import type { ComparisonResult, Tolerances } from '../../../api/types';
import { DEFAULT_TOLERANCES } from '../../../utils/constants';
import {
  buildMiniHistogramSpec,
  DeviationHistogramsGrid,
} from './DeviationHistogramsGrid';

interface MockPlotProps {
  data: Data[];
  layout?: Partial<Layout>;
  config?: Partial<Config>;
}

const plotSpy = vi.hoisted(() => vi.fn());

vi.mock('../../charts/Plot', () => ({
  default: (props: MockPlotProps) => {
    plotSpy(props);
    return (
      <div
        data-testid="mock-histogram-plot"
        data-traces={props.data.length}
        data-height={props.layout?.height}
      />
    );
  },
}));

function makeRow(overrides: Partial<ComparisonResult> = {}): ComparisonResult {
  return {
    sector: 'S1',
    section: 'SEC-01',
    bench_num: 1,
    type: 'MATCH',
    level: '2800',
    height_design: 15,
    height_real: 15.5,
    height_dev: 0.5,
    height_status: 'CUMPLE',
    angle_design: 70,
    angle_real: 68,
    angle_dev: -2,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 7.5,
    berm_min: 7,
    berm_status: 'CUMPLE',
    delta_crest: 0.4,
    delta_toe: -0.3,
    ...overrides,
  };
}

const BASE_TOLERANCES: Tolerances = {
  ...DEFAULT_TOLERANCES,
};

beforeEach(async () => {
  plotSpy.mockClear();
  await i18n.changeLanguage('es');
});

describe('buildMiniHistogramSpec', () => {
  it('computes n, median, out-of-tolerance stats, band fill, dashed boundary lines, and annotation for delta band', () => {
    const spec = buildMiniHistogramSpec({
      values: [-3, -1, 0, 1, 4],
      title: 'Δ Altura (m)',
      xLabel: 'Δ Altura (m)',
      frequencyLabel: 'Frecuencia',
      band: { neg: 2, pos: 2 },
      bandLabel: 'CUMPLE',
      isDark: true,
    });

    expect(spec.n).toBe(5);
    expect(spec.median).toBe(0);
    expect(spec.outOfTolCount).toBe(2);
    expect(spec.outOfTolPct).toBeCloseTo(40, 5);
    expect(spec.data).toHaveLength(2);

    const withinTrace = spec.data[0] as { x?: number[]; marker?: { color?: string } };
    const outsideTrace = spec.data[1] as { x?: number[]; marker?: { color?: string } };
    expect(withinTrace.x).toEqual([-1, 0, 1]);
    expect(outsideTrace.x).toEqual([-3, 4]);
    expect(withinTrace.marker?.color).toBe('var(--color-accent)');
    expect(outsideTrace.marker?.color).toBe('var(--status-nok-text)');

    const shapes = spec.layout.shapes ?? [];
    expect(shapes).toHaveLength(3);
    expect(shapes[0]).toMatchObject({
      type: 'rect',
      x0: -2,
      x1: 2,
      fillcolor: 'rgba(57, 171, 96, 0.20)',
    });
    expect(shapes[1]).toMatchObject({
      type: 'line',
      x0: -2,
      x1: -2,
      line: { color: 'var(--status-ok-border)', width: 1, dash: 'dash' },
    });
    expect(shapes[2]).toMatchObject({
      type: 'line',
      x0: 2,
      x1: 2,
      line: { color: 'var(--status-ok-border)', width: 1, dash: 'dash' },
    });

    const annotations = spec.layout.annotations ?? [];
    expect(annotations).toHaveLength(1);
    expect(annotations[0]).toMatchObject({
      text: 'CUMPLE',
      x: 0,
      showarrow: false,
    });
    expect(spec.layout.height).toBe(190);
  });

  it('uses light band fill and supports min-only and min-max berm bands', () => {
    const minOnly = buildMiniHistogramSpec({
      values: [0, 5, 7, 10],
      title: 'Ancho de berma real (m)',
      xLabel: 'Ancho de berma real (m)',
      frequencyLabel: 'Frecuencia',
      band: { min: 7 },
      bandLabel: 'Mín. 7 m',
      isDark: false,
    });

    expect(minOnly.n).toBe(4);
    expect(minOnly.median).toBe(6);
    expect(minOnly.outOfTolCount).toBe(2);
    expect(minOnly.outOfTolPct).toBeCloseTo(50, 5);
    expect(minOnly.layout.shapes).toHaveLength(2);
    expect(minOnly.layout.shapes?.[0]).toMatchObject({
      type: 'rect',
      x0: 7,
      x1: 10,
      fillcolor: 'rgba(29, 107, 63, 0.16)',
    });
    expect(minOnly.layout.shapes?.[1]).toMatchObject({
      type: 'line',
      x0: 7,
      x1: 7,
      line: { color: 'var(--status-ok-border)', width: 1, dash: 'dash' },
    });
    expect(minOnly.layout.annotations?.[0]).toMatchObject({
      text: 'Mín. 7 m',
      x: 7,
    });

    const bounded = buildMiniHistogramSpec({
      values: [6, 8, 12, 16],
      title: 'Ancho de berma real (m)',
      xLabel: 'Ancho de berma real (m)',
      frequencyLabel: 'Frecuencia',
      band: { min: 7, max: 14 },
      bandLabel: 'Mín. 7 m',
      isDark: true,
    });

    expect(bounded.outOfTolCount).toBe(2);
    expect(bounded.layout.shapes).toHaveLength(3);
    expect(bounded.layout.shapes?.[0]).toMatchObject({ x0: 7, x1: 14 });
    expect(bounded.layout.shapes?.[2]).toMatchObject({ type: 'line', x0: 14, x1: 14 });
  });

  it('handles empty or non-finite values safely', () => {
    const spec = buildMiniHistogramSpec({
      values: [Number.NaN, Number.POSITIVE_INFINITY],
      title: 'Δ Cresta (m)',
      xLabel: 'Δ Cresta (m)',
      frequencyLabel: 'Frecuencia',
      band: { neg: 1, pos: 1 },
      bandLabel: 'CUMPLE',
      isDark: true,
    });

    expect(spec.n).toBe(0);
    expect(spec.median).toBeNull();
    expect(spec.outOfTolCount).toBe(0);
    expect(spec.outOfTolPct).toBeNull();
    expect(spec.data).toEqual([]);
  });
});

describe('DeviationHistogramsGrid', () => {
  it('renders all 5 cards simultaneously with captions, stats, and compact plot config', () => {
    const rows = [
      makeRow({
        height_dev: 1.0,
        angle_dev: -3.0,
        delta_crest: 0.5,
        delta_toe: -0.5,
        berm_real: 8.0,
      }),
      makeRow({
        bench_num: 2,
        height_dev: 3.0,
        angle_dev: 6.0,
        delta_crest: 2.5,
        delta_toe: 1.5,
        berm_real: 5.0,
      }),
    ];

    const { container } = render(
      <DeviationHistogramsGrid rows={rows} tolerances={BASE_TOLERANCES} isDark />,
    );

    const grid = container.querySelector('[data-slot="deviation-histograms-grid"]');
    expect(grid).toBeInTheDocument();
    expect(grid).toHaveClass('grid-cols-1', 'md:grid-cols-2', 'xl:grid-cols-3');

    const keys = ['height', 'angle', 'crest', 'toe', 'berm'] as const;
    for (const key of keys) {
      expect(container.querySelector(`[data-slot="histogram-card-${key}"]`)).toBeInTheDocument();
    }

    expect(screen.getByText('Δ Altura (m)')).toBeInTheDocument();
    expect(screen.getByText('Δ Ángulo (°)')).toBeInTheDocument();
    expect(screen.getByText('Δ Cresta (m)')).toBeInTheDocument();
    expect(screen.getByText('Δ Pata (m)')).toBeInTheDocument();
    expect(screen.getByText('Ancho de berma real (m)')).toBeInTheDocument();

    expect(screen.getByText('+ = más alto · − = más bajo')).toBeInTheDocument();
    expect(screen.getByText('− = más tendido · + = más empinado')).toBeInTheDocument();
    expect(screen.getByText('+ = pérdida de cresta')).toBeInTheDocument();
    expect(screen.getByText('+ = sobre-excavación / − = pata remanente')).toBeInTheDocument();

    expect(plotSpy).toHaveBeenCalledTimes(5);
    for (const call of plotSpy.mock.calls) {
      const props = call[0] as MockPlotProps;
      expect(props.layout?.height).toBe(190);
      expect(props.config).toEqual({ displayModeBar: false, responsive: true });
    }

    const heightCard = container.querySelector('[data-slot="histogram-card-height"]')!;
    expect(within(heightCard as HTMLElement).getByText('n = 2')).toBeInTheDocument();
    expect(within(heightCard as HTMLElement).getByText(/Mediana: \+2[.,]0 m/)).toBeInTheDocument();
    expect(within(heightCard as HTMLElement).getByText(/Fuera de tol\.: 50[.,]0%/)).toBeInTheDocument();

    const bermPlotProps = plotSpy.mock.calls[4]![0] as MockPlotProps;
    expect(bermPlotProps.layout?.annotations?.[0]?.text).toBe('Mín. 7 m');

    const heightPlotProps = plotSpy.mock.calls[0]![0] as MockPlotProps;
    expect(heightPlotProps.layout?.annotations?.[0]?.text).toBe('CUMPLE');
  });

  it('excludes EXTRA and MISSING rows from all histograms including berm', () => {
    const rows = [
      makeRow({
        type: 'MATCH',
        height_dev: 0.5,
        angle_dev: -1.0,
        delta_crest: 0.2,
        delta_toe: -0.1,
        berm_real: 9.0,
      }),
      makeRow({
        type: 'EXTRA',
        height_dev: 99,
        angle_dev: 99,
        delta_crest: 99,
        delta_toe: 99,
        berm_real: 0,
      }),
      makeRow({
        type: 'MISSING',
        height_dev: -50,
        angle_dev: -50,
        delta_crest: -50,
        delta_toe: -50,
        berm_real: 0,
      }),
    ];

    const { container } = render(
      <DeviationHistogramsGrid rows={rows} tolerances={BASE_TOLERANCES} isDark={false} />,
    );

    const bermCard = container.querySelector('[data-slot="histogram-card-berm"]') as HTMLElement;
    expect(within(bermCard).getByText('n = 1')).toBeInTheDocument();
    expect(within(bermCard).getByText(/Mediana: 9[.,]0 m/)).toBeInTheDocument();
    expect(within(bermCard).getByText(/Fuera de tol\.: 0[.,]0%/)).toBeInTheDocument();
    expect(bermCard.querySelector('[data-slot="histogram-berm-zeros"]')).toBeNull();
  });

  it('shows truncated 0 m note when MATCH rows contain berm_real === 0', () => {
    const rows = [
      makeRow({ berm_real: 0 }),
      makeRow({ bench_num: 2, berm_real: 0 }),
      makeRow({ bench_num: 3, berm_real: 8.5 }),
    ];

    const { container } = render(
      <DeviationHistogramsGrid rows={rows} tolerances={BASE_TOLERANCES} isDark />,
    );

    const bermCard = container.querySelector('[data-slot="histogram-card-berm"]') as HTMLElement;
    const note = bermCard.querySelector('[data-slot="histogram-berm-zeros"]');
    expect(note).toBeInTheDocument();
    expect(note).toHaveTextContent('2 bancos con berma real 0 m (truncados)');
  });

  it('renders an empty message inside individual cards that have no numeric values', () => {
    const rows = [
      makeRow({
        height_dev: 1.2,
        angle_dev: null,
        delta_crest: null,
        delta_toe: 0.4,
        berm_real: null,
      }),
    ];

    const { container } = render(
      <DeviationHistogramsGrid rows={rows} tolerances={BASE_TOLERANCES} isDark />,
    );

    expect(plotSpy).toHaveBeenCalledTimes(2);

    const angleCard = container.querySelector('[data-slot="histogram-card-angle"]') as HTMLElement;
    expect(within(angleCard).getByText('n = 0')).toBeInTheDocument();
    expect(angleCard.querySelector('[data-slot="histogram-empty"]')).toHaveTextContent(
      'Sin datos de desviación',
    );

    const bermCard = container.querySelector('[data-slot="histogram-card-berm"]') as HTMLElement;
    expect(bermCard.querySelector('[data-slot="histogram-empty"]')).toHaveTextContent(
      'Sin datos de desviación',
    );
  });

  it('localizes band annotations and captions in English', async () => {
    await i18n.changeLanguage('en');
    render(
      <DeviationHistogramsGrid rows={[makeRow()]} tolerances={BASE_TOLERANCES} isDark />,
    );

    expect(screen.getByText('Δ Height (m)')).toBeInTheDocument();
    expect(screen.getByText('Actual berm width (m)')).toBeInTheDocument();
    expect(screen.getByText('+ = crest loss')).toBeInTheDocument();

    const heightPlotProps = plotSpy.mock.calls[0]![0] as MockPlotProps;
    const bermPlotProps = plotSpy.mock.calls[4]![0] as MockPlotProps;
    expect(heightPlotProps.layout?.annotations?.[0]?.text).toBe('PASS');
    expect(bermPlotProps.layout?.annotations?.[0]?.text).toBe('Min 7 m');
  });
});
