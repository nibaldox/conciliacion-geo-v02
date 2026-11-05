import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmptyState } from '../EmptyState';

describe('EmptyState', () => {
  it('renders the title and description', () => {
    render(<EmptyState icon={<svg />} title="Sin superficies" description="Cargue diseño y topografía" />);
    expect(screen.getByRole('heading', { name: 'Sin superficies' })).toBeInTheDocument();
    expect(screen.getByText('Cargue diseño y topografía')).toBeInTheDocument();
  });

  it('invokes the primary and secondary actions', async () => {
    const onPrimary = vi.fn();
    const onSecondary = vi.fn();
    render(
      <EmptyState
        icon={<svg />}
        title="t"
        description="d"
        primaryAction={{ label: 'Cargar superficies', onClick: onPrimary }}
        secondaryAction={{ label: 'Probar con datos demo', onClick: onSecondary }}
      />,
    );
    const primary = screen.getByRole('button', { name: 'Cargar superficies' });
    expect(primary).toHaveAttribute('data-variant', 'primary');
    await userEvent.click(primary);
    expect(onPrimary).toHaveBeenCalledOnce();
    const secondary = screen.getByRole('button', { name: 'Probar con datos demo' });
    expect(secondary).toHaveAttribute('data-variant', 'secondary');
    await userEvent.click(secondary);
    expect(onSecondary).toHaveBeenCalledOnce();
  });

  it('renders no buttons without actions and exposes the default data-slot', () => {
    const { container } = render(<EmptyState icon={<svg />} title="t" description="d" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(container.querySelector('[data-slot="empty-state"]')).toBeInTheDocument();
  });

  it('accepts a custom data-slot', () => {
    const { container } = render(
      <EmptyState icon={<svg />} title="t" description="d" data-slot="empty-mesh" />,
    );
    expect(container.querySelector('[data-slot="empty-mesh"]')).toBeInTheDocument();
  });
});
