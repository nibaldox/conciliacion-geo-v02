import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Card } from '../Card';

describe('Card', () => {
  it('renders a title and children by default', () => {
    render(<Card title="My Card">Body</Card>);
    expect(screen.getByText('My Card')).toBeInTheDocument();
    expect(screen.getByText('Body')).toBeInTheDocument();
  });

  it('renders an eyebrow (small uppercase label) above the title', () => {
    render(<Card eyebrow="Protocol Alpha" title="My Card" />);
    const eyebrow = screen.getByText('Protocol Alpha');
    expect(eyebrow).toBeInTheDocument();
    expect(eyebrow).toHaveClass('uppercase');
  });

  it('renders a subtitle under the title', () => {
    render(<Card title="My Card" subtitle="Some descriptive text" />);
    expect(screen.getByText('Some descriptive text')).toBeInTheDocument();
  });

  it('renders a right-aligned headerAside when provided', () => {
    render(
      <Card
        title="My Card"
        headerAside={<span data-testid="aside">CUMPLE</span>}
      />,
    );
    expect(screen.getByTestId('aside')).toBeInTheDocument();
  });

  it('exposes data-variant on the wrapper for CSS targeting', () => {
    const { container } = render(<Card variant="dashed" title="x" />);
    expect(container.querySelector('[data-variant="dashed"]')).toBeInTheDocument();
  });

  it('renders a button element when onClick is provided', () => {
    const { container } = render(
      <Card title="Clickable" onClick={() => {}}>
        Body
      </Card>,
    );
    expect(container.querySelector('button')).toBeInTheDocument();
  });

  it('renders a div by default (no onClick)', () => {
    const { container } = render(<Card title="Static">Body</Card>);
    expect(container.querySelector('div[data-slot="card"]')).toBeInTheDocument();
    expect(container.querySelector('button')).not.toBeInTheDocument();
  });
});
