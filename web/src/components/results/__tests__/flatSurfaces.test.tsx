import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ComparisonResult } from '../../../api/types';

const mocks = vi.hoisted(() => ({
  rows: [] as ComparisonResult[],
}));

vi.mock('../../../api/hooks', () => ({
  useResults: () => ({ data: mocks.rows }),
  useSections: () => ({ data: [] }),
  useSettings: () => ({ data: undefined }),
  useExportExcel: () => ({ isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
  useExportWord: () => ({ isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
  useExportPdf: () => ({ isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
  useExportDxf: () => ({ isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
  useExportImages: () => ({ isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'es' } }),
}));

vi.mock('../CompliancePlanView', () => ({ CompliancePlanView: () => null }));
vi.mock('../DesignAchievementPanel', () => ({ DesignAchievementPanel: () => null }));
vi.mock('../../charts/Plot', () => ({ default: () => <div data-testid="plot" /> }));

import { BlastTemporalFilter } from '../BlastTemporalFilter';
import { Dashboard } from '../Dashboard';
import { ExportPanel } from '../../export/ExportPanel';

function expectNoCard(className: string): void {
  expect(className).not.toContain('bg-surface-raised');
  expect(className).not.toContain('rounded-lg');
  expect(className).not.toContain('ui-card');
  expect(className).not.toContain('shadow');
}

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

describe('flat content surfaces', () => {
  it('renders the temporal filter as a flat section', () => {
    render(<BlastTemporalFilter surveyDate="" onApply={vi.fn()} />);
    const section = screen.getByRole('region', { name: 'blast.temporal.title' });
    expectNoCard(section.className);
    expect(section.className).not.toContain('bg-surface-muted');
    expect(section.className).toContain('border-t');
  });

  it('renders the dashboard sections without card wrappers', () => {
    mocks.rows = [makeRow()];
    const { container } = render(<Dashboard />);

    expect(screen.getByText('dashboard.rail.parameters')).toBeTruthy();

    const blocks = container.querySelectorAll('section, [data-slot]');
    expect(blocks.length).toBeGreaterThan(0);
    for (const block of blocks) {
      expectNoCard(block.className);
    }
  });

  it('renders the export panel without card wrappers', () => {
    const { container } = render(<ExportPanel />);

    expectNoCard(screen.getByTestId('export-actions').className);

    const blocks = container.querySelectorAll('section, [data-slot]');
    expect(blocks.length).toBeGreaterThan(0);
    for (const block of blocks) {
      expectNoCard(block.className);
    }
  });
});
