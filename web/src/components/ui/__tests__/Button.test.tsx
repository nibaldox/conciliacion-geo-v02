import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../Button';

describe('Button (Mission Control variants)', () => {
  it('renders the launch variant with uppercase + tracking', () => {
    render(<Button variant="launch">Launch Engine</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('data-variant', 'launch');
    expect(btn).toHaveClass('uppercase');
    expect(btn).toHaveClass('tracking-wider');
    expect(btn.textContent).toBe('Launch Engine');
  });

  it('renders the terminal variant with monospace font (via CSS var)', () => {
    render(<Button variant="terminal">$ run --scan</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('data-variant', 'terminal');
    // The terminal style sets fontFamily to the --font-mono CSS
    // variable; the browser resolves it at runtime. We just check
    // that the CSS var is wired up.
    expect(btn.style.fontFamily).toBe('var(--font-mono)');
  });

  it('falls back to a button when no onClick', () => {
    render(<Button>Click</Button>);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('does not call onClick when disabled', async () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>x</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('renders the spinner when loading', () => {
    render(<Button loading>x</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
  });
});
