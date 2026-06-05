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
  it('shows a checkmark only when checked', () => {
    const { rerender } = render(
      <FilterToggle variant="chip" checked={false} onChange={() => {}} label="CUMPLE" />,
    );
    expect(screen.queryByText('✓')).not.toBeInTheDocument();
    rerender(
      <FilterToggle variant="chip" checked={true} onChange={() => {}} label="CUMPLE" />,
    );
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('toggles via click', async () => {
    const onChange = vi.fn();
    render(<FilterToggle variant="chip" checked={false} onChange={onChange} label="X" />);
    await userEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
