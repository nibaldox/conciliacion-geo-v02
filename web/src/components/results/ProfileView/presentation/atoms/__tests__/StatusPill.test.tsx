import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusPill } from '../StatusPill';
import { StatusDot } from '../StatusDot';

describe('StatusPill', () => {
  it('renders the default short label for each status', () => {
    const { rerender } = render(<StatusPill status="CUMPLE" />);
    expect(screen.getByText('Cumple')).toBeInTheDocument();
    rerender(<StatusPill status="FUERA" />);
    expect(screen.getByText('Fuera')).toBeInTheDocument();
    rerender(<StatusPill status="NO_CUMPLE" />);
    expect(screen.getByText('No cumple')).toBeInTheDocument();
    rerender(<StatusPill status="UNKNOWN" />);
    expect(screen.getByText('Sin datos')).toBeInTheDocument();
  });

  it('renders an icon by default for md size', () => {
    render(<StatusPill status="CUMPLE" size="md" />);
    // The icon is a span with aria-hidden="true" containing the symbol.
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('hides the icon in sm size unless explicitly requested', () => {
    const { rerender } = render(<StatusPill status="CUMPLE" size="sm" />);
    expect(screen.queryByText('✓')).not.toBeInTheDocument();
    rerender(<StatusPill status="CUMPLE" size="sm" showIcon />);
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('uses the override label when provided', () => {
    render(<StatusPill status="CUMPLE" label="Within tolerance" />);
    expect(screen.getByText('Within tolerance')).toBeInTheDocument();
  });

  it('uses the override children when provided', () => {
    render(<StatusPill status="CUMPLE">3 banks ok</StatusPill>);
    expect(screen.getByText('3 banks ok')).toBeInTheDocument();
  });

  it('sets data-status for CSS targeting / testing', () => {
    render(<StatusPill status="NO_CUMPLE" />);
    expect(screen.getByText('No cumple').closest('[data-slot="status-pill"]')).toHaveAttribute(
      'data-status',
      'NO_CUMPLE',
    );
  });

  it('exposes the canonical status name as the title (for hover)', () => {
    render(<StatusPill status="FUERA" />);
    expect(screen.getByText('Fuera').closest('[data-slot="status-pill"]')).toHaveAttribute(
      'title',
      'Fuera',
    );
  });
});

describe('StatusDot', () => {
  it('renders a span with data-status', () => {
    render(<StatusDot status="CUMPLE" />);
    expect(document.querySelector('[data-status="CUMPLE"]')).toBeInTheDocument();
  });

  it('hides itself from screen readers', () => {
    render(<StatusDot status="CUMPLE" />);
    const el = document.querySelector('[data-status="CUMPLE"]');
    expect(el).toHaveAttribute('aria-hidden', 'true');
  });

  it('respects the size prop', () => {
    render(<StatusDot status="FUERA" size={12} />);
    const el = document.querySelector('[data-status="FUERA"]') as HTMLElement;
    expect(el.style.width).toBe('12px');
    expect(el.style.height).toBe('12px');
  });
});
