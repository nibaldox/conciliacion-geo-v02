import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SectionHeader } from '../SectionHeader';
import type { SectionMeta } from '../../domain/types';

const setSelectedSection = vi.fn();

vi.mock('../../infrastructure/apiAdapter', () => ({
  useSectionsQuery: () => ({
    data: [
      { id: 'sec-1', name: 'S-001' },
      { id: 'sec-2', name: 'S-002' },
    ],
    isLoading: false,
    error: null,
  }),
}));

vi.mock('../../../../../stores/session', () => ({
  useSession: (selector?: (s: { selectedSection: string | null; setSelectedSection: typeof setSelectedSection }) => unknown) => {
    const state = { selectedSection: 'sec-1', setSelectedSection };
    return selector ? selector(state) : state;
  },
}));

const META: SectionMeta = {
  id: 'sec-1',
  name: 'S-001',
  sector: 'Norte',
  azimuth: 45,
  length: 187.4,
  origin: [0, 0],
};

beforeEach(() => {
  setSelectedSection.mockReset();
});

describe('SectionHeader sticky', () => {
  it('sticks to the top of the scroll container with an opaque background and a hairline divider', () => {
    const { container } = render(<SectionHeader section={META} benchCount={5} />);
    const header = container.querySelector<HTMLElement>('[data-slot="section-header"]');

    expect(header).not.toBeNull();
    expect(header).toHaveClass('sticky', '-top-3', 'md:-top-6', 'z-20');
    expect(header).not.toHaveClass('top-0');
    expect(header).toHaveClass('bg-surface', 'border-b', 'border-border');
    expect(header).not.toHaveClass('shadow-lg');
  });

  it('keeps the section arrows inside the sticky header', () => {
    const { container } = render(<SectionHeader section={META} benchCount={5} />);
    const header = container.querySelector<HTMLElement>('[data-slot="section-header"]');

    expect(header?.querySelector('[data-slot="section-navigator"]')).not.toBeNull();
    expect(header).toContainElement(screen.getByTestId('nav-prev'));
    expect(header).toContainElement(screen.getByTestId('nav-next'));
  });

  it('changes section from the arrows while the header is stuck', async () => {
    const user = userEvent.setup();
    render(<SectionHeader section={META} benchCount={5} />);

    await user.click(screen.getByTestId('nav-next'));

    expect(setSelectedSection).toHaveBeenCalledWith('sec-2');
  });
});
