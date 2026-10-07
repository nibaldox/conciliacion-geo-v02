import { beforeAll, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BenchTable } from '../BenchTable';
import i18n from '../../../../../i18n';
import type { Bench } from '../../domain/types';
import type { UseCrossLinkStateApi } from '../../application';

beforeAll(async () => i18n.changeLanguage('es'));

function makeBench(overrides: Partial<Bench> = {}): Bench {
  return {
    benchNumber: 1,
    crestElevation: 100,
    crestDistance: 0,
    toeElevation: 95,
    toeDistance: 5,
    height: 15,
    faceAngle: 65,
    bermWidth: 8,
    isRamp: false, designHeight: 15, designAngle: 65, designBerm: 8, heightStatus: 'UNKNOWN', angleStatus: 'UNKNOWN', bermStatus: 'UNKNOWN',
    status: 'CUMPLE',
    matched: true,
    deltaCrest: null,
    deltaToe: null,
    ...overrides,
  };
}

function makeCrossLink(): UseCrossLinkStateApi {
  return {
    hovered: null,
    selected: null,
    setHovered: vi.fn(),
    setSelected: vi.fn(),
    clear: vi.fn(),
  };
}

const benches: readonly Bench[] = [
  makeBench({ benchNumber: 1, designBenchNumber: 8, height: 12, faceAngle: 70, status: 'CUMPLE' }),
  makeBench({ benchNumber: 2, designBenchNumber: 6, height: 15, faceAngle: 65, status: 'FUERA' }),
  makeBench({ benchNumber: 3, designBenchNumber: 4, height: 18, faceAngle: 80, status: 'NO_CUMPLE' }),
  makeBench({ benchNumber: 4, designBenchNumber: 2, height: 14, faceAngle: 60, status: 'CUMPLE', bermWidth: null }),
];

describe('BenchTable', () => {
  it('renders one row per bench', () => {
    render(<BenchTable benches={benches} crossLink={makeCrossLink()} />);
    // 4 data rows + 1 header row
    expect(screen.getAllByRole('row')).toHaveLength(5);
  });

  it('labels an EXTRA row as additional topography while keeping its topo identity', () => {
    const { container } = render(<BenchTable benches={[makeBench({ benchNumber: 3, designBenchNumber: null, matchType: 'EXTRA' })]} crossLink={makeCrossLink()} />);
    expect(screen.getByText('Adicional topo · 3')).toBeInTheDocument();
    expect(container.querySelector('[data-bench-number="3"]')).toHaveAttribute('data-match-type', 'EXTRA');
  });

  it('shows an empty state when no benches', () => {
    render(<BenchTable benches={[]} crossLink={makeCrossLink()} />);
    expect(screen.getByText(/no hay bancos/i)).toBeInTheDocument();
  });

  it('filters by design bench identity while preserving topo row identity', () => {
    const { container } = render(<BenchTable benches={benches} crossLink={makeCrossLink()} selectedDesignBenchNumbers={[6]} />);
    expect(container.querySelectorAll('[data-bench-number]')).toHaveLength(1);
    expect(container.querySelector('[data-bench-number="2"]')).toBeInTheDocument();
  });

  it('explains a selected missing design bench using its design elevation', () => {
    const missing = { sectionName: 'S-1', designBenchNumber: 5, designElevation: 2925, status: 'NO_CUMPLE' as const, hasTopo: false, isAdditional: false };
    render(<BenchTable benches={benches} crossLink={makeCrossLink()} selectedDesignBenchNumbers={[5]} comparisonBenchStatuses={[missing]} />);
    expect(screen.getByText('Cota base de diseño 2925 m: sin banco topográfico emparejado.')).toBeInTheDocument();
  });

  it('still reports a structurally missing design bench when its compliance status is unknown', () => {
    const missing = { sectionName: 'S-1', designBenchNumber: 5, designElevation: 2925, status: 'UNKNOWN' as const, hasTopo: false, isAdditional: false };
    render(<BenchTable benches={benches} crossLink={makeCrossLink()} comparisonBenchStatuses={[missing]} />);
    expect(screen.getByText('Sin banco topográfico emparejado para cotas base de diseño: 2925 m.')).toBeInTheDocument();
  });

  it('renders sortable headers for visible table fields', () => {
    const { container } = render(<BenchTable benches={benches} crossLink={makeCrossLink()} />);
    const headers = container.querySelectorAll('[data-testid^="sort-header-"]');
    expect(headers).toHaveLength(8);
    expect(headers[0]?.textContent).toMatch(/#/);
    expect(headers[5]?.textContent).toMatch(/Áng/i);
    expect(container.querySelector('[data-testid="sort-header-status"]')).not.toBeInTheDocument();
  });

  it('omits the redundant status column while retaining the dot, parameter colors, and score', () => {
    const bench = makeBench({
      status: 'NO_CUMPLE',
      heightStatus: 'CUMPLE',
      angleStatus: 'FUERA',
      bermStatus: 'CUMPLE',
      benchScore: 90,
    });
    const { container } = render(<BenchTable benches={[bench]} crossLink={makeCrossLink()} />);
    const row = container.querySelector('[data-bench-number="1"]');
    const cells = row?.querySelectorAll('td');

    expect(row?.querySelector('[data-status="NO_CUMPLE"]')).toBeInTheDocument();
    expect(cells).toHaveLength(10);
    expect(cells?.[3]?.querySelector('.badge-ok')).toHaveTextContent('15.0');
    expect(cells?.[5]?.querySelector('.badge-warn')).toHaveTextContent('65°');
    expect(cells?.[7]?.querySelector('.badge-ok')).toHaveTextContent('8.0');
    expect(cells?.[9]).toHaveTextContent('90');
    expect(row?.querySelector('[data-slot="status-pill"]')).not.toBeInTheDocument();
  });

  it('sorts by benchNumber asc by default', () => {
    const { container } = render(<BenchTable benches={benches} crossLink={makeCrossLink()} />);
    const rows = container.querySelectorAll('[data-bench-number]');
    const numbers = Array.from(rows).map((r) => r.getAttribute('data-bench-number'));
    expect(numbers).toEqual(['1', '2', '3', '4']);
  });

  it('cycles sort on header click (asc → desc → none → asc)', async () => {
    const user = userEvent.setup();
    const { container } = render(<BenchTable benches={benches} crossLink={makeCrossLink()} />);
    const heightHeader = container.querySelector('[data-testid="sort-header-height"]') as HTMLElement;
    // First click on a DIFFERENT field → asc: 12, 14, 15, 18
    await user.click(heightHeader);
    // Verify the "Alt (R)" column (it's the 4th column now: 1:#, 2:Elev, 3:Alt(D), 4:Alt(R))
    let heights = Array.from(container.querySelectorAll('tbody tr')).map(
      (r) => (r.querySelector('td:nth-child(4)') as HTMLElement | null)?.textContent?.trim()
    );
    expect(heights).toEqual(['12.0', '14.0', '15.0', '18.0']);
    // Second click on the same field → desc: 18, 15, 14, 12
    await user.click(heightHeader);
    heights = Array.from(container.querySelectorAll('tbody tr')).map(
      (r) => (r.querySelector('td:nth-child(4)') as HTMLElement | null)?.textContent?.trim()
    );
    expect(heights).toEqual(['18.0', '15.0', '14.0', '12.0']);
    // Third click on the same field → none (returns to benchNumber asc)
    await user.click(heightHeader);
    const numbers = Array.from(container.querySelectorAll('[data-bench-number]')).map((r) =>
      r.getAttribute('data-bench-number'),
    );
    expect(numbers).toEqual(['1', '2', '3', '4']);
  });

  it('shows a dash for benches with no berm', () => {
    const { container } = render(<BenchTable benches={benches} crossLink={makeCrossLink()} />);
    const row4 = container.querySelector('[data-bench-number="4"]');
    expect(row4?.textContent).toContain('—');
  });

  it('calls crossLink.setHovered on mouseenter and setHovered(null) on mouseleave', async () => {
    const user = userEvent.setup();
    const crossLink = makeCrossLink();
    const { container } = render(<BenchTable benches={benches} crossLink={crossLink} />);
    const row2 = container.querySelector('[data-bench-number="2"]') as HTMLElement;
    await user.hover(row2);
    expect(crossLink.setHovered).toHaveBeenCalledWith(2);
    await user.unhover(row2);
    expect(crossLink.setHovered).toHaveBeenCalledWith(null);
  });

  it('calls crossLink.setSelected on click', async () => {
    const user = userEvent.setup();
    const crossLink = makeCrossLink();
    const { container } = render(<BenchTable benches={benches} crossLink={crossLink} />);
    const row3 = container.querySelector('[data-bench-number="3"]') as HTMLElement;
    await user.click(row3);
    expect(crossLink.setSelected).toHaveBeenCalledWith(3);
  });

  it('highlights the selected row (data-selected attribute)', () => {
    const crossLink: UseCrossLinkStateApi = {
      hovered: null,
      selected: 2,
      setHovered: vi.fn(),
      setSelected: vi.fn(),
      clear: vi.fn(),
    };
    const { container } = render(<BenchTable benches={benches} crossLink={crossLink} />);
    const row2 = container.querySelector('[data-bench-number="2"]');
    expect(row2).toHaveAttribute('data-selected', 'true');
  });

  it('highlights the hovered row (data-hovered attribute)', () => {
    const crossLink: UseCrossLinkStateApi = {
      hovered: 1,
      selected: null,
      setHovered: vi.fn(),
      setSelected: vi.fn(),
      clear: vi.fn(),
    };
    const { container } = render(<BenchTable benches={benches} crossLink={crossLink} />);
    const row1 = container.querySelector('[data-bench-number="1"]');
    expect(row1).toHaveAttribute('data-hovered', 'true');
  });
});
