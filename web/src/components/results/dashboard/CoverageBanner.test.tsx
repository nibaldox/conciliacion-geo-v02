import '../../../i18n';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import i18n from '../../../i18n';
import type { Tolerances } from '../../../api/types';
import { CoverageBanner } from './CoverageBanner';
import { DashboardContextBar } from './DashboardContextBar';
import type { DashboardCoverage } from './coverageSelectors';

const BASE_TOLERANCES: Tolerances = {
  bench_height: { neg: 2.0, pos: 2.0 },
  face_angle: { neg: 5.0, pos: 5.0 },
  berm_width: { min: 7.0 },
  inter_ramp_angle: { neg: 3.0, pos: 2.0 },
  overall_angle: { neg: 2.0, pos: 2.0 },
  crest_toe_deviation: { neg: 1.0, pos: 1.0 },
};

function makeCoverage(overrides: Partial<DashboardCoverage> = {}): DashboardCoverage {
  return {
    totalSectionsDefined: 80,
    evaluatedSections: 77,
    evaluatedFilteredSections: 77,
    missingSections: ['S-19', 'S-53', 'S-80'],
    totalRows: 120,
    designBenches: 110,
    comparedBenches: 100,
    evaluableCompleteBenches: 75,
    notBuiltBenches: 10,
    extraBenches: 10,
    truncatedStateBenches: 25,
    notExcavatedStateBenches: 10,
    unmeasuredStateBenches: 2,
    truncatedBermDesignCount: 25,
    truncatedBermDesignPct: 25,
    bermZeroRealCount: 4,
    ...overrides,
  };
}

describe('DashboardContextBar', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('es');
  });

  it('renders context metadata, visible tolerances, formula text, and filter trigger', () => {
    const { container } = render(
      <DashboardContextBar
        designName="fase4_diseno.stl"
        topoName="topo_2026_11.stl"
        sectionLengthM={250}
        tolerances={BASE_TOLERANCES}
        activeChips={[]}
        filterTrigger={<button type="button">Filtros</button>}
      />,
    );

    expect(container.querySelector('[data-slot="dashboard-context-bar"]')).toBeInTheDocument();
    expect(screen.getByText('fase4_diseno.stl')).toBeInTheDocument();
    expect(screen.getByText('topo_2026_11.stl')).toBeInTheDocument();
    expect(screen.getByText('250 m')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Filtros' })).toBeInTheDocument();

    const criteria = container.querySelector('[data-slot="dashboard-criteria-line"]')!;
    expect(criteria).toHaveTextContent('±2,0 m');
    expect(criteria).toHaveTextContent('±5,0°');
    expect(criteria).toHaveTextContent('≥ 7,0 m');
    expect(criteria).toHaveTextContent('±1,0 m');
    expect(criteria).toHaveTextContent('Fórmula (berma 60, alt 30, áng 10)');
    expect(container.querySelector('[data-slot="dashboard-active-filters"]')).not.toBeInTheDocument();
  });

  it('renders removable filter chips and invokes callbacks on click', () => {
    const onRemoveSector = vi.fn();
    const onRemoveLevel = vi.fn();
    const onClearAll = vi.fn();

    render(
      <DashboardContextBar
        designName="design.stl"
        topoName="topo.stl"
        sectionLengthM={null}
        tolerances={BASE_TOLERANCES}
        activeChips={[
          { key: 'sector:Norte', label: 'Sector: Norte', onRemove: onRemoveSector },
          { key: 'level:2400', label: 'Cota: 2400', onRemove: onRemoveLevel },
        ]}
        onClearAllFilters={onClearAll}
      />,
    );

    expect(screen.getByText('Sector: Norte')).toBeInTheDocument();
    expect(screen.getByText('Cota: 2400')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtro: Sector: Norte' }));
    expect(onRemoveSector).toHaveBeenCalledOnce();
    expect(onRemoveLevel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtro' }));
    expect(onClearAll).toHaveBeenCalledOnce();
  });
});

describe('CoverageBanner', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('es');
  });

  it('renders missing sections collapsible list, funnel, breakdown, and truncated berm warning', () => {
    const { container } = render(
      <CoverageBanner coverage={makeCoverage()} defaultBermMin={7} />,
    );

    const root = container.querySelector('[data-slot="dashboard-coverage"]')!;
    expect(root).toBeInTheDocument();
    expect(screen.getByText('77 de 80 secciones')).toBeInTheDocument();
    expect(screen.getByText('3 secciones sin perfil')).toBeInTheDocument();

    const details = container.querySelector('[data-slot="missing-sections-details"]')!;
    expect(details).toBeInTheDocument();
    expect(details).toHaveTextContent('S-19, S-53, S-80');

    expect(
      screen.getByText('110 de diseño → 100 comparados → 75 evaluables completos'),
    ).toBeInTheDocument();
    expect(container.querySelector('[data-slot="coverage-funnel-bar"]')).toBeInTheDocument();
    expect(screen.getByText('Truncados:')).toBeInTheDocument();
    expect(screen.getByText('No excavados:')).toBeInTheDocument();
    expect(screen.getByText('Sin medir:')).toBeInTheDocument();
    expect(screen.getByText('Adicionales:')).toBeInTheDocument();

    const warning = screen.getByRole('status');
    expect(warning).toHaveAttribute('data-slot', 'truncated-berm-warning');
    expect(warning).toHaveTextContent(
      '25 bancos comparados (25,0 %) tienen la berma de diseño truncada por el largo de sección (< 7,0 m).',
    );
  });

  it('renders clean zero-warning state without missing sections details or zero breakdown items', () => {
    const cleanCoverage = makeCoverage({
      totalSectionsDefined: 40,
      evaluatedSections: 40,
      evaluatedFilteredSections: 40,
      missingSections: [],
      designBenches: 80,
      comparedBenches: 80,
      evaluableCompleteBenches: 80,
      notBuiltBenches: 0,
      extraBenches: 0,
      truncatedStateBenches: 0,
      notExcavatedStateBenches: 0,
      unmeasuredStateBenches: 0,
      truncatedBermDesignCount: 0,
      truncatedBermDesignPct: 0,
    });

    const { container } = render(
      <CoverageBanner coverage={cleanCoverage} defaultBermMin={7} />,
    );

    expect(screen.getByText('40 de 40 secciones')).toBeInTheDocument();
    expect(screen.getByText('Todas las secciones cuentan con perfil válido.')).toBeInTheDocument();
    expect(container.querySelector('[data-slot="missing-sections-details"]')).not.toBeInTheDocument();
    expect(container.querySelector('[data-slot="truncated-berm-warning"]')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('Truncados:')).not.toBeInTheDocument();
    expect(screen.queryByText('No excavados:')).not.toBeInTheDocument();
    expect(screen.queryByText('Sin medir:')).not.toBeInTheDocument();
    expect(screen.queryByText('Adicionales:')).not.toBeInTheDocument();
  });
});
