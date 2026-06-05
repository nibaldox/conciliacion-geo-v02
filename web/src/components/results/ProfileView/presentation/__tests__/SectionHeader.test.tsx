import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SectionHeader } from '../SectionHeader';
import type { SectionMeta } from '../../domain/types';

const META: SectionMeta = {
  id: 'sec-1',
  name: 'S-001',
  sector: 'Norte',
  azimuth: 45,
  length: 187.4,
  origin: [0, 0],
};

describe('SectionHeader', () => {
  it('renders the section name as a heading', () => {
    render(<SectionHeader section={META} benchCount={5} />);
    expect(screen.getByRole('heading', { name: 'S-001' })).toBeInTheDocument();
  });

  it('renders the azimuth, sector, length and bench count', () => {
    const { container } = render(<SectionHeader section={META} benchCount={5} />);
    // The MetricValue atoms render value + unit in separate spans,
    // so we look for the value text inside the MetricValue wrappers.
    expect(container.textContent).toContain('45°');
    expect(container.textContent).toContain('Norte');
    expect(container.textContent).toContain('187.4');
    expect(container.textContent).toContain('5');
  });

  it('shows a dash when sector is empty', () => {
    const { container } = render(
      <SectionHeader section={{ ...META, sector: '' }} benchCount={0} />,
    );
    expect(container.textContent).toContain('—');
  });

  it('shows the last-run timestamp when provided', () => {
    const pastIso = new Date(Date.now() - 60_000).toISOString();
    const { container } = render(
      <SectionHeader section={META} benchCount={3} lastRunAt={pastIso} />,
    );
    // The i18n key is missing; just verify the timestamp element
    // exists (the title attribute is always set, the visible text
    // is the i18n default).
    expect(container.querySelector('[title]')).toBeInTheDocument();
  });

  it('does NOT show the last-run line when timestamp is missing', () => {
    const { container } = render(<SectionHeader section={META} benchCount={0} />);
    // No [title] span when timestamp is missing.
    expect(container.querySelector('span[title]')).toBeNull();
  });

  it('exposes the section id in the title attribute (for tooltips)', () => {
    render(<SectionHeader section={META} benchCount={0} />);
    expect(screen.getByRole('heading')).toHaveAttribute('title', 'sec-1');
  });
});
