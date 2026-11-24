import i18n from '../../../i18n';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComparisonResult } from '../../../api/types';
import { DirectionalSummary } from './DirectionalSummary';
import { LevelComplianceTable } from './LevelComplianceTable';
import { PriorityReviewList } from './PriorityReviewList';
import {
  computeDirectionalStats,
  type LevelComplianceRow,
  type PriorityReviewItem,
} from './geotechSelectors';

beforeEach(async () => {
  await i18n.changeLanguage('es');
});

const makeRow = (overrides: Partial<ComparisonResult> = {}): ComparisonResult =>
  ({
    sector: 'North',
    section: 'S1',
    bench_num: 1,
    type: 'MATCH',
    level: '2840',
    level_nominal: '2840',
    height_design: 15,
    height_real: 15,
    height_dev: 0,
    height_status: 'CUMPLE',
    angle_design: 70,
    angle_real: 70,
    angle_dev: 0,
    angle_status: 'CUMPLE',
    berm_design: 8,
    berm_real: 8,
    berm_min: 7,
    berm_status: 'CUMPLE',
    effective_berm: 7.5,
    effective_berm_status: 'CUMPLE',
    delta_crest: 0,
    delta_toe: 0,
    bench_score: 100,
    ...overrides,
  }) as ComparisonResult;

describe('DirectionalSummary', () => {
  it('renders parameter bars with icons, directional engineering breakdown, crest row, and MATCH denominator', () => {
    const rows: ComparisonResult[] = [
      makeRow({
        height_status: 'CUMPLE',
        height_dev: 0.4,
        angle_status: 'CUMPLE',
        angle_dev: -2.0,
        berm_status: 'NO CUMPLE',
        berm_design: 9.0,
        berm_real: 4.5,
        berm_min: 7.0,
        effective_berm: 4.0,
        effective_berm_status: 'NO CUMPLE',
        delta_crest: 3.6,
      }),
      makeRow({
        bench_num: 2,
        height_status: 'FUERA DE TOLERANCIA',
        height_dev: 2.5,
        angle_status: 'NO CUMPLE',
        angle_dev: -4.4,
        berm_status: 'CUMPLE',
        berm_design: 9.0,
        berm_real: 8.5,
        berm_min: 7.0,
        effective_berm: 7.8,
        effective_berm_status: 'CUMPLE',
        delta_crest: 1.4,
      }),
      makeRow({
        bench_num: 3,
        height_status: 'NO CUMPLE',
        height_dev: -2.4,
        angle_status: 'CUMPLE',
        angle_dev: 1.6,
        berm_status: 'NO CUMPLE',
        berm_design: 9.0,
        berm_real: 6.2,
        berm_min: 7.0,
        effective_berm: 5.5,
        effective_berm_status: 'NO CUMPLE',
        delta_crest: 0.4,
      }),
      makeRow({
        bench_num: 4,
        type: 'MISSING',
        height_status: 'NO CONSTRUIDO',
        angle_status: 'NO CONSTRUIDO',
        berm_status: 'NO CONSTRUIDO',
        delta_crest: 10,
      }),
      makeRow({
        bench_num: 5,
        type: 'EXTRA',
        height_status: 'EXTRA',
        angle_status: 'EXTRA',
        berm_status: 'EXTRA',
        delta_crest: 10,
      }),
    ];

    const stats = computeDirectionalStats(rows, { heightPos: 2, heightNeg: 2, bermMin: 7 });
    const { container } = render(<DirectionalSummary stats={stats} rows={rows} />);

    const root = container.querySelector('[data-slot="directional-summary"]')!;
    expect(root).toBeInTheDocument();

    expect(root.querySelector('[data-slot="directional-denominator"]')).toHaveTextContent('n = 3');
    expect(root).toHaveTextContent('3');

    const heightBlock = root.querySelector('[data-parameter="height"]')!;
    expect(heightBlock).toHaveTextContent('✗');
    expect(heightBlock).toHaveTextContent('33,3 %');
    expect(heightBlock).toHaveTextContent('1 sobre · 1 bajo tolerancia');
    expect(heightBlock).toHaveTextContent('+0,40 m');

    const angleBlock = root.querySelector('[data-parameter="angle"]')!;
    expect(angleBlock).toHaveTextContent('⚠');
    expect(angleBlock).toHaveTextContent('66,7 %');
    expect(angleBlock).toHaveTextContent('2 de 3 más tendidos');
    expect(angleBlock).toHaveTextContent('-2,0°');
    expect(angleBlock).toHaveTextContent('1 más empinados');

    const bermBlock = root.querySelector('[data-parameter="berm"]')!;
    expect(bermBlock).toHaveTextContent('✗');
    expect(bermBlock).toHaveTextContent('33,3 %');
    expect(bermBlock).toHaveTextContent('-2,60 m');
    expect(bermBlock).toHaveTextContent('2 <');
    expect(bermBlock).toHaveTextContent('1 < 5 m');
    expect(bermBlock).toHaveTextContent('33,3 % (1/3)');

    const crestBlock = root.querySelector('[data-parameter="crest"]')!;
    expect(crestBlock).toHaveTextContent('✗');
    expect(crestBlock).toHaveTextContent('+1,8 m');
    expect(crestBlock).toHaveTextContent('2 > 1 m, 1 > 3 m');
    expect(crestBlock).toHaveTextContent('+ = retroceso / pérdida de cresta');
  });

  it('handles empty rows and zeroed stats with dashes', () => {
    const stats = computeDirectionalStats([], { heightPos: 2, heightNeg: 2, bermMin: 7 });
    const { container } = render(<DirectionalSummary stats={stats} rows={[]} />);

    const root = container.querySelector('[data-slot="directional-summary"]')!;
    expect(root.querySelector('[data-slot="directional-denominator"]')).toHaveTextContent('n = 0');
    expect(screen.getAllByText('—')).toHaveLength(4);
  });
});

describe('LevelComplianceTable', () => {
  const levels: LevelComplianceRow[] = [
    {
      level: '2860',
      compared: 2,
      notBuilt: 1,
      extra: 0,
      meanScore: 40,
      heightPassPct: 50,
      anglePassPct: 100,
      bermPassPct: 0,
      smallSample: true,
    },
    {
      level: '2845',
      compared: 156,
      notBuilt: 4,
      extra: 2,
      meanScore: 82.4,
      heightPassPct: 91.2,
      anglePassPct: 76.5,
      bermPassPct: 71.8,
      smallSample: false,
    },
  ];

  it('renders levels in order, marks smallSample rows with badge and softened style, and toggles level filter', () => {
    const onToggleLevel = vi.fn();
    const { container } = render(
      <LevelComplianceTable
        levels={levels}
        activeLevels={['2845']}
        onToggleLevel={onToggleLevel}
      />,
    );

    const root = container.querySelector('[data-slot="level-compliance-table"]')!;
    expect(root).toBeInTheDocument();

    const smallRow = root.querySelector('tr[data-level="2860"]')!;
    expect(smallRow).toHaveAttribute('data-small-sample', 'true');
    expect(smallRow).toHaveAttribute('data-active', 'false');
    const badge = smallRow.querySelector('[data-slot="small-sample-badge"]')!;
    expect(badge).toHaveTextContent('n=2');
    expect(badge).toHaveAttribute('title', 'Muestra pequeña (n=2)');

    const largeRow = root.querySelector('tr[data-level="2845"]')!;
    expect(largeRow).toHaveAttribute('data-small-sample', 'false');
    expect(largeRow).toHaveAttribute('data-active', 'true');
    expect(largeRow.querySelector('[data-slot="small-sample-badge"]')).toBeNull();

    const activeBtn = within(largeRow as HTMLElement).getByRole('button');
    expect(activeBtn).toHaveAttribute('aria-pressed', 'true');

    const inactiveBtn = within(smallRow as HTMLElement).getByRole('button');
    expect(inactiveBtn).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(inactiveBtn);
    expect(onToggleLevel).toHaveBeenCalledTimes(1);
    expect(onToggleLevel).toHaveBeenCalledWith('2860');

    fireEvent.click(largeRow);
    expect(onToggleLevel).toHaveBeenCalledTimes(2);
    expect(onToggleLevel).toHaveBeenLastCalledWith('2845');
  });

  it('renders empty message when there are no levels', () => {
    const { container } = render(
      <LevelComplianceTable levels={[]} activeLevels={[]} onToggleLevel={vi.fn()} />,
    );
    expect(container.querySelector('[data-slot="level-compliance-table"]')).toBeInTheDocument();
    expect(container.querySelector('table')).toBeNull();
  });
});

describe('PriorityReviewList', () => {
  const sampleItems: PriorityReviewItem[] = [
    {
      section: 'S-12',
      sectionId: 'sec-12',
      benchNum: 3,
      level: '2830',
      score: 30,
      bermReal: 4.2,
      bermDesign: 8.5,
      effectiveBerm: 3.1,
      deltaCrest: 3.8,
      bermMin: 7,
      severity: 95,
      reasons: ['effective_berm', 'berm_below_min', 'crest_loss', 'low_score'],
    },
    {
      section: 'S-99',
      sectionId: null,
      benchNum: 1,
      level: '2860',
      score: 40,
      bermReal: 5.5,
      bermDesign: null,
      effectiveBerm: null,
      deltaCrest: null,
      bermMin: 7,
      severity: 45,
      reasons: ['berm_below_min', 'low_score'],
    },
  ];

  it('renders priority benches with reason badges, invokes onOpenBench, and disables button when sectionId is null', () => {
    const onOpenBench = vi.fn();
    const { container } = render(
      <PriorityReviewList items={sampleItems} onOpenBench={onOpenBench} />,
    );

    const root = container.querySelector('[data-slot="priority-review-list"]')!;
    expect(root).toBeInTheDocument();

    const firstRow = root.querySelector('tr[data-section="S-12"]') as HTMLElement;
    expect(firstRow).toHaveTextContent('S-12');
    expect(firstRow).toHaveTextContent('B3');
    expect(firstRow).toHaveTextContent('2830');
    expect(firstRow.querySelector('[data-reason="effective_berm"]')).toHaveTextContent('3,1 m');
    expect(firstRow.querySelector('[data-reason="berm_below_min"]')).toHaveTextContent('4,2 / 8,5 m');
    expect(firstRow.querySelector('[data-reason="crest_loss"]')).toHaveTextContent('Δ +3,8 m');
    expect(firstRow.querySelector('[data-reason="low_score"]')).toHaveTextContent('30/100');

    const openBtn = within(firstRow).getByRole('button', { name: /S-12/ });
    expect(openBtn).toBeEnabled();
    fireEvent.click(openBtn);
    expect(onOpenBench).toHaveBeenCalledTimes(1);
    expect(onOpenBench).toHaveBeenCalledWith(sampleItems[0]);

    const secondRow = root.querySelector('tr[data-section="S-99"]') as HTMLElement;
    expect(secondRow.querySelector('[data-reason="berm_below_min"]')).toHaveTextContent('5,5 m');
    const disabledBtn = within(secondRow).getByRole('button', { name: /S-99/ });
    expect(disabledBtn).toBeDisabled();
    fireEvent.click(disabledBtn);
    expect(onOpenBench).toHaveBeenCalledTimes(1);
  });

  it('renders clean empty state when items list is empty', () => {
    const { container } = render(
      <PriorityReviewList items={[]} onOpenBench={vi.fn()} />,
    );

    const root = container.querySelector('[data-slot="priority-review-list"]')!;
    expect(root.querySelector('[data-slot="priority-review-empty"]')).toHaveTextContent(
      'Sin desviaciones críticas pendientes.',
    );
    expect(root.querySelector('table')).toBeNull();
  });
});
