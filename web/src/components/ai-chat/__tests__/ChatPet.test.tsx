import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { ChatPet } from '../ChatPet';

interface MatchMediaStub {
  matches: boolean;
  media: string;
  onchange: null;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
  addListener: ReturnType<typeof vi.fn>;
  removeListener: ReturnType<typeof vi.fn>;
  dispatchEvent: ReturnType<typeof vi.fn>;
}

function stubMatchMedia(matches: boolean): void {
  vi.stubGlobal('matchMedia', (query: string): MatchMediaStub => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function mockSvgRect(svg: Element, left: number, top: number, width: number, height: number): void {
  vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue({
    x: left,
    y: top,
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height,
    toJSON: () => ({}),
  } as DOMRect);
}

describe('ChatPet', () => {
  it('renders the blob body with helmet, dot eyes and badge dots', () => {
    const { getByTestId } = render(<ChatPet />);
    expect(getByTestId('ai-chat-pet')).toBeInTheDocument();
    expect(getByTestId('ai-pet-body')).toBeInTheDocument();
    expect(getByTestId('ai-pet-helmet')).toBeInTheDocument();
    expect(getByTestId('ai-pet-eyes').querySelectorAll('ellipse')).toHaveLength(2);
    expect(getByTestId('ai-pet-dots').querySelectorAll('circle')).toHaveLength(3);
  });

  it('has no mouth or face extras', () => {
    const { getByTestId, queryByTestId } = render(<ChatPet />);
    expect(queryByTestId('ai-pet-mouth')).not.toBeInTheDocument();
    expect(getByTestId('ai-chat-pet').querySelector('.ai-pet__mouth')).toBeNull();
    expect(getByTestId('ai-chat-pet').querySelectorAll('.ai-pet__eye')).toHaveLength(2);
    expect(getByTestId('ai-chat-pet').querySelectorAll('.ai-pet__pupil')).toHaveLength(0);
  });

  it('keeps the mascot aria-hidden for assistive tech', () => {
    const { getByTestId } = render(<ChatPet />);
    expect(getByTestId('ai-chat-pet')).toHaveAttribute('aria-hidden', 'true');
  });

  it('toggles the working dots class from the streaming prop', () => {
    const { container, rerender } = render(<ChatPet streaming={false} />);
    expect(container.querySelector('.ai-pet')?.className).not.toContain('ai-pet--working');
    rerender(<ChatPet streaming />);
    expect(container.querySelector('.ai-pet--working')).not.toBeNull();
  });

  it('shifts the eyes toward a pointer on the right, then on the left', () => {
    stubMatchMedia(false);
    const { getByTestId } = render(<ChatPet />);
    const svg = getByTestId('ai-chat-pet');
    mockSvgRect(svg, 100, 100, 44, 44);
    const eyes = getByTestId('ai-pet-eyes');

    fireEvent.pointerMove(window, { clientX: 700, clientY: 122 });
    expect(eyes.style.transform).toMatch(/translate\(1\.80px,/);

    fireEvent.pointerMove(window, { clientX: -400, clientY: 122 });
    expect(eyes.style.transform).toMatch(/translate\(-1\.80px,/);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the eyes still under prefers-reduced-motion', () => {
    stubMatchMedia(true);
    const { getByTestId } = render(<ChatPet />);
    const svg = getByTestId('ai-chat-pet');
    mockSvgRect(svg, 100, 100, 44, 44);
    const eyes = getByTestId('ai-pet-eyes');

    fireEvent.pointerMove(window, { clientX: 700, clientY: 122 });
    expect(eyes.style.transform).toBe('translate(0.00px, 0.00px)');
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
});
