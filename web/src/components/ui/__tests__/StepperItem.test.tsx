import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepperItem } from '../StepperItem';

describe('StepperItem', () => {
  it('calls onToggle when the header is clicked', async () => {
    const onToggle = vi.fn();
    render(
      <StepperItem id="step-surfaces" index={1} title="Superficies" status="current" expanded={false} onToggle={onToggle} />,
    );
    const header = screen.getByRole('button', { name: /Superficies/ });
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(header).toHaveAttribute('aria-controls', 'step-surfaces-panel');
    await userEvent.click(header);
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it('disables the header when locked', async () => {
    const onToggle = vi.fn();
    render(
      <StepperItem id="step-process" index={4} title="Procesar" status="locked" expanded={false} onToggle={onToggle} />,
    );
    const header = screen.getByRole('button', { name: /Procesar/ });
    expect(header).toBeDisabled();
    await userEvent.click(header);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('renders the panel only when expanded', () => {
    const { rerender } = render(
      <StepperItem id="step-sections" index={2} title="Secciones" status="pending" expanded={false} onToggle={() => {}}>
        <p>Contenido</p>
      </StepperItem>,
    );
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(screen.queryByText('Contenido')).not.toBeInTheDocument();
    rerender(
      <StepperItem id="step-sections" index={2} title="Secciones" status="pending" expanded onToggle={() => {}}>
        <p>Contenido</p>
      </StepperItem>,
    );
    const panel = screen.getByRole('region');
    expect(panel).toHaveAttribute('id', 'step-sections-panel');
    expect(panel).toHaveTextContent('Contenido');
    expect(panel).toHaveClass('pl-3');
    expect(panel).not.toHaveClass('pl-[52px]');
    expect(document.querySelector('[data-slot="stepper-connector"]')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Secciones/ })).toHaveAttribute('aria-expanded', 'true');
  });

  it('exposes the status via data-state and shows the summary', () => {
    render(
      <StepperItem
        id="step-surfaces"
        index={1}
        title="Superficies"
        summary="Diseño y topografía cargados"
        status="done"
        expanded={false}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /Superficies/ })).toHaveAttribute('data-state', 'done');
    expect(screen.getByText('Diseño y topografía cargados')).toBeInTheDocument();
    expect(screen.queryByText('1')).not.toBeInTheDocument();
  });

  it('shows the step number when pending and omits the connector on the last item', () => {
    const { container } = render(
      <StepperItem id="step-params" index={3} title="Parámetros" status="pending" expanded={false} onToggle={() => {}} isLast />,
    );
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(container.querySelector('[data-slot="stepper-connector"]')).not.toBeInTheDocument();
  });
});
