import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SectionNavigator } from '../SectionNavigator';

const MOCK_SECTIONS = [
  { id: 'sec-1', name: 'S-001', sector: 'Norte', azimuth: 45, length: 200, origin: [0, 0] },
  { id: 'sec-2', name: 'S-002', sector: 'Norte', azimuth: 90, length: 200, origin: [0, 0] },
  { id: 'sec-3', name: 'S-003', sector: 'Sur', azimuth: 135, length: 200, origin: [0, 0] },
];

// vi.hoisted runs BEFORE the vi.mock factories are hoisted, so the
// state object is created in a fresh TDZ-safe scope. Both the
// mock factory and the test cases reference the same object.
const mocks = vi.hoisted(() => ({
  selectedSection: 'sec-2' as string | null,
  setSelectedSection: vi.fn(),
}));

vi.mock('../../../../../stores/session', () => ({
  useSession: (
    selector?: (s: { selectedSection: string | null; setSelectedSection: typeof mocks.setSelectedSection }) => unknown,
  ) => {
    const state = { selectedSection: mocks.selectedSection, setSelectedSection: mocks.setSelectedSection };
    return selector ? selector(state) : state;
  },
}));

vi.mock('../../infrastructure/apiAdapter', () => ({
  useSectionsQuery: () => ({ data: MOCK_SECTIONS, isLoading: false, error: null }),
}));

beforeEach(() => {
  mocks.selectedSection = 'sec-2';
  mocks.setSelectedSection.mockClear();
});

describe('SectionNavigator', () => {
  it('renders both prev and next buttons in compact variant', () => {
    render(<SectionNavigator variant="compact" />);
    expect(screen.getByTestId('nav-prev')).toBeInTheDocument();
    expect(screen.getByTestId('nav-next')).toBeInTheDocument();
  });

  it('renders overlay variant with absolute positioning', () => {
    mocks.selectedSection = 'sec-2';
    const { container } = render(<SectionNavigator variant="overlay" showLabels />);
    const prev = container.querySelector('[data-testid="overlay-nav-prev"]');
    const next = container.querySelector('[data-testid="overlay-nav-next"]');
    expect(prev).toHaveClass('left-2');
    expect(next).toHaveClass('right-2');
  });

  it('disables the prev button when on the first section', () => {
    mocks.selectedSection = 'sec-1';
    render(<SectionNavigator variant="compact" />);
    expect(screen.getByTestId('nav-prev')).toBeDisabled();
    expect(screen.getByTestId('nav-next')).not.toBeDisabled();
  });

  it('disables the next button when on the last section', () => {
    mocks.selectedSection = 'sec-3';
    render(<SectionNavigator variant="compact" />);
    expect(screen.getByTestId('nav-prev')).not.toBeDisabled();
    expect(screen.getByTestId('nav-next')).toBeDisabled();
  });

  it('disables both buttons when no section is selected', () => {
    mocks.selectedSection = null;
    render(<SectionNavigator variant="compact" />);
    expect(screen.getByTestId('nav-prev')).toBeDisabled();
    expect(screen.getByTestId('nav-next')).toBeDisabled();
  });

  it('calls setSelectedSection with the prev id on click', async () => {
    mocks.selectedSection = 'sec-2';
    render(<SectionNavigator variant="compact" />);
    const prev = screen.getByTestId('nav-prev');
    expect(prev).not.toBeDisabled();
    await userEvent.click(prev);
    expect(mocks.setSelectedSection).toHaveBeenCalledWith('sec-1');
  });

  it('calls setSelectedSection with the next id on click', async () => {
    mocks.selectedSection = 'sec-2';
    render(<SectionNavigator variant="compact" />);
    const next = screen.getByTestId('nav-next');
    expect(next).not.toBeDisabled();
    await userEvent.click(next);
    expect(mocks.setSelectedSection).toHaveBeenCalledWith('sec-3');
  });
});
