import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../Button';

describe('Button variants', () => {
  it('starts the primary action when activated with the keyboard', async () => {
    const onClick = vi.fn();
    render(<Button variant="launch" onClick={onClick}>Iniciar análisis</Button>);
    const btn = screen.getByRole('button', { name: 'Iniciar análisis' });
    expect(btn).toHaveAttribute('data-variant', 'launch');
    btn.focus();
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('keeps secondary actions available in the terminal variant', async () => {
    const onClick = vi.fn();
    render(<Button variant="terminal" onClick={onClick}>Guardar</Button>);
    const btn = screen.getByRole('button', { name: 'Guardar' });
    expect(btn).toHaveAttribute('data-variant', 'terminal');
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalledOnce();
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
