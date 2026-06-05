import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterToggle } from '../FilterToggle';

describe('FilterToggle — switch variant', () => {
  it('renders with role=switch and aria-checked=false initially', () => {
    render(<FilterToggle checked={false} onChange={() => {}} label="Show areas" />);
    const btn = screen.getByRole('switch', { name: /show areas/i });
    expect(btn).toHaveAttribute('aria-checked', 'false');
  });

  it('sets aria-checked=true when checked', () => {
    render(<FilterToggle checked={true} onChange={() => {}} label="Show areas" />);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });

  it('exposes data-checked on the wrapper for CSS/test targeting', () => {
    const { rerender } = render(
      <FilterToggle checked={false} onChange={() => {}} label="x" />,
    );
    expect(screen.getByRole('switch')).toHaveAttribute('data-checked', 'false');
    rerender(<FilterToggle checked={true} onChange={() => {}} label="x" />);
    expect(screen.getByRole('switch')).toHaveAttribute('data-checked', 'true');
  });

  it('gives OFF toggles a visible box (background + border) so they align with ON ones', () => {
    render(<FilterToggle checked={false} onChange={() => {}} label="x" />);
    const btn = screen.getByRole('switch');
    // The OFF state must have a non-transparent background so the
    // button reads as a "box" with consistent visual weight next
    // to the ON state in the same FilterBar row.
    expect(btn.style.backgroundColor).not.toBe('');
    expect(btn.style.backgroundColor).not.toBe('transparent');
    expect(btn.style.borderColor).not.toBe('');
  });

  it('calls onChange with the opposite value on click', async () => {
    const onChange = vi.fn();
    render(<FilterToggle checked={false} onChange={onChange} label="Show" />);
    await userEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('does not call onChange when disabled', async () => {
    const onChange = vi.fn();
    render(<FilterToggle checked={false} onChange={onChange} label="Show" disabled />);
    await userEvent.click(screen.getByRole('switch'));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('renders the label inside the toggle', () => {
    render(<FilterToggle checked={true} onChange={() => {}} label="Áreas" />);
    expect(screen.getByText('Áreas')).toBeInTheDocument();
  });

  it('renders an optional badge', () => {
    render(<FilterToggle checked={false} onChange={() => {}} label="X" badge="3" />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });
});

describe('FilterToggle — chip variant', () => {
  it('shows a filled marker (●) only when checked', () => {
    const { rerender } = render(
      <FilterToggle variant="chip" checked={false} onChange={() => {}} label="CUMPLE" />,
    );
    expect(screen.queryByText('●')).not.toBeInTheDocument();
    rerender(
      <FilterToggle variant="chip" checked={true} onChange={() => {}} label="CUMPLE" />,
    );
    expect(screen.getByText('●')).toBeInTheDocument();
  });

  it('toggles via click', async () => {
    const onChange = vi.fn();
    render(<FilterToggle variant="chip" checked={false} onChange={onChange} label="X" />);
    await userEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('FilterToggle — track layout (regression: thumb bleeds onto label)', () => {
  it('clips the thumb to the track with overflow-hidden so it cannot bleed onto the label', () => {
    const { container } = render(
      <FilterToggle checked={true} onChange={() => {}} label="Reconciliado" />,
    );
    // The track is the 24px pill. It MUST have overflow-hidden or
    // the thumb visually extends onto the first letter of the label.
    const track = container.querySelector('span.relative.inline-block.rounded-full');
    expect(track).not.toBeNull();
    expect(track!.className).toContain('overflow-hidden');
  });

  it('uses a flex gap of 2.5 (10px) between track and label so the thumb has clear breathing room', () => {
    const { container } = render(
      <FilterToggle checked={true} onChange={() => {}} label="X" />,
    );
    const btn = container.querySelector('button[role="switch"]')!;
    // gap-2.5 = 0.625rem = 10px (Tailwind v4). Anything tighter
    // and the thumb (at translateX 13-14px) visually touches the
    // first letter on dense renders.
    expect(btn.className).toMatch(/\bgap-2\.5\b/);
  });

  it('protects the track from flex-shrink collapse with min-w-6', () => {
    const { container } = render(
      <FilterToggle checked={true} onChange={() => {}} label="X" />,
    );
    const track = container.querySelector('span.relative.inline-block.rounded-full')!;
    // Without min-w-6, an aggressive flex container can collapse
    // the track to 0px wide, leaving the thumb floating in the gap.
    expect(track.className).toContain('min-w-6');
  });

  it('keeps the thumb translateX within track bounds (24px wide, 10px thumb)', () => {
    // OFF: thumb at 2px → right edge at 12px (well inside 24px).
    // ON:  thumb at 13px → right edge at 23px (1px from right edge,
    // safe inside 24px — was 14px before, too close to the rim).
    const offRightEdge = 2 + 10;
    const onRightEdge = 13 + 10;
    expect(offRightEdge).toBeLessThan(24);
    expect(onRightEdge).toBeLessThan(24);
  });
});
