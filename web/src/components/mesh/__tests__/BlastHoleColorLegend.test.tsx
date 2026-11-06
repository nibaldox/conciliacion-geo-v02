import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BlastHoleColorLegendView } from '../BlastHoleColorLegend';
import type { BlastHoleColorLegend } from '../blastHoleColors';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string; [name: string]: unknown }) => {
      const template = options?.defaultValue ?? key;
      return template.replace(/\{\{(\w+)\}\}/g, (match, name: string) => (
        options && name in options ? String(options[name]) : match
      ));
    },
  }),
}));

const PALETTE = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'];

function categoryLegend(categories: number, colors: number): BlastHoleColorLegend {
  return {
    kind: 'category',
    entries: Array.from({ length: categories }, (_, index) => ({
      label: `Malla ${index + 1}`,
      color: PALETTE[index % colors],
    })),
    missing: { label: 'Sin dato', color: '#808080' },
  };
}

afterEach(() => cleanup());

describe('BlastHoleColorLegendView', () => {
  it('reports total categories and distinct colors in the repeat notice', () => {
    render(<BlastHoleColorLegendView legend={categoryLegend(73, 10)} />);

    const notice = screen.getByText(/repiten/);
    expect(notice.textContent).toContain('73');
    expect(notice.textContent).toContain('10');
    expect(notice.textContent).not.toContain('{{');
    expect(notice.textContent).not.toMatch(/^63 /);
  });

  it('omits the repeat notice when every category has its own color', () => {
    render(<BlastHoleColorLegendView legend={categoryLegend(5, 10)} />);

    expect(screen.queryByText(/repiten/)).toBeNull();
  });
});
