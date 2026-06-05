import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MetricValue } from '../MetricValue';

describe('MetricValue', () => {
  it('renders the label and value', () => {
    render(<MetricValue label="Azimuth" value={45} unit="°" />);
    expect(screen.getByText('Azimuth')).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText('°')).toBeInTheDocument();
  });

  it('renders string values', () => {
    render(<MetricValue label="Sector" value="Norte" />);
    expect(screen.getByText('Norte')).toBeInTheDocument();
  });

  it('skips the unit span when no unit is provided', () => {
    const { container } = render(<MetricValue label="Length" value={200} />);
    // Only the label and value spans — no third element.
    expect(container.firstChild?.childNodes.length).toBe(2);
  });

  it('uses the title attribute for hover tooltips', () => {
    render(<MetricValue label="Length" value={200} unit="m" title="Section length" />);
    expect(screen.getByText('Length').closest('[data-slot="metric-value"]')).toHaveAttribute(
      'title',
      'Section length',
    );
  });

  it('exposes data-size for CSS targeting', () => {
    render(<MetricValue label="Length" value={200} size="lg" />);
    expect(screen.getByText('Length').closest('[data-slot="metric-value"]')).toHaveAttribute(
      'data-size',
      'lg',
    );
  });
});
