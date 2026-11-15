import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { ChatPet } from '../ChatPet';
import type { PetState } from '../petState';

describe('ChatPet', () => {
  it.each<PetState>(['idle', 'thinking', 'tool', 'confirm', 'done', 'error', 'off', 'unread'])('renders state %s', (state) => {
    const { container, getByTestId } = render(<ChatPet state={state} trackPointer={false} />);
    expect(container.querySelector('.ai-pet')).toHaveAttribute('data-state', state);
    expect(container.querySelector(`.ai-pet--${state}`)).not.toBeNull();
    expect(getByTestId('ai-chat-pet')).toHaveAttribute('aria-hidden', 'true');
    expect(getByTestId('ai-pet-body')).toBeInTheDocument();
    expect(getByTestId('ai-pet-helmet')).toBeInTheDocument();
    expect(getByTestId('ai-pet-bubble')).toBeInTheDocument();
    expect(container.querySelector('.ai-pet__mouth, .ai-pet__nose, .ai-pet__pupil')).toBeNull();
  });
  it('renders the shovel without the old gear in tool state', () => {
    const { container, getByTestId } = render(<ChatPet state="tool" />);
    expect(getByTestId('ai-pet-shovel')).toBeInTheDocument();
    expect(container.querySelector('.ai-pet__bubble-gear')).toBeNull();
  });
  it('uses unique gradient ids', () => {
    const { container } = render(<><ChatPet /><ChatPet /></>);
    const ids = [...container.querySelectorAll('linearGradient, radialGradient')].map((el) => el.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
  it('uses two oval eyes for idle', () => {
    const { getByTestId } = render(<ChatPet />);
    expect(getByTestId('ai-pet-eyes').querySelectorAll('ellipse')).toHaveLength(2);
  });
});


describe('pointer tracking', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it('throttles pointer movement and reacts to reduced-motion changes', () => {
    let change: (() => void) | undefined;
    const media = { matches: false, addEventListener: vi.fn((_name, cb) => { change = cb; }), removeEventListener: vi.fn() };
    vi.stubGlobal('matchMedia', () => media);
    let frame: FrameRequestCallback | undefined;
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => { frame = cb; return 1; });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
    const { getByTestId, unmount } = render(<ChatPet />);
    const svg = getByTestId('ai-chat-pet');
    fireEvent.pointerMove(window, { clientX: 700, clientY: 0 });
    fireEvent.pointerMove(window, { clientX: 800, clientY: 0 });
    expect(raf).toHaveBeenCalledTimes(1);
    frame?.(0);
    expect(svg.style.getPropertyValue('--ai-pet-ex')).toBe('1.8px');
    media.matches = true;
    change?.();
    expect(svg.style.getPropertyValue('--ai-pet-ex')).toBe('');
    fireEvent.pointerMove(window, { clientX: 900, clientY: 0 });
    expect(raf).toHaveBeenCalledTimes(1);
    media.matches = false;
    change?.();
    fireEvent.pointerMove(window, { clientX: 900, clientY: 0 });
    expect(raf).toHaveBeenCalledTimes(2);
    unmount();
    expect(media.removeEventListener).toHaveBeenCalled();
  });
  it('does not subscribe to pointer movement when disabled', () => {
    const add = vi.spyOn(window, 'addEventListener');
    render(<ChatPet trackPointer={false} />);
    expect(add.mock.calls.some(([name]) => name === 'pointermove')).toBe(false);
  });
});
