import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import { useSession } from '../../../stores/session';

const apiState = vi.hoisted(() => ({
  sections: [] as { id: string }[],
  status: undefined as { status: string } | undefined,
}));

vi.mock('../../../api/hooks', () => ({
  useSections: () => ({ data: apiState.sections }),
  useProcessStatus: () => ({ data: apiState.status }),
}));

import { Header } from '../Header';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

function renderHeader() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}><Header /></QueryClientProvider>
    </I18nextProvider>,
  );
}

beforeEach(() => {
  useSession.getState().reset();
  apiState.sections = [];
  apiState.status = undefined;
});

describe('Header project status', () => {
  it('renders the brand mark instead of the text logo', () => {
    const { container } = renderHeader();
    expect(container.querySelector('[data-slot="brand-mark"]')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByText('CG')).not.toBeInTheDocument();
  });

  it('shows the empty status chip without a tone for a new session', () => {
    renderHeader();
    const chip = screen.getByRole('status');
    expect(chip).toHaveTextContent('Sin datos');
    expect(chip).not.toHaveAttribute('data-tone');
  });

  it('reports loaded surfaces with the accent tone', () => {
    useSession.setState({ designMeshId: 'design', topoMeshId: 'topo' });
    renderHeader();
    const chip = screen.getByRole('status');
    expect(chip).toHaveTextContent('Superficies cargadas');
    expect(chip).toHaveAttribute('data-tone', 'accent');
  });

  it('reports a ready project with the warn tone', () => {
    useSession.setState({ designMeshId: 'design', topoMeshId: 'topo' });
    apiState.sections = [{ id: 'section-1' }];
    renderHeader();
    const chip = screen.getByRole('status');
    expect(chip).toHaveTextContent('Listo para procesar');
    expect(chip).toHaveAttribute('data-tone', 'warn');
  });

  it('reports a completed analysis with the ok tone', () => {
    useSession.setState({ designMeshId: 'design', topoMeshId: 'topo' });
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'complete' };
    renderHeader();
    const chip = screen.getByRole('status');
    expect(chip).toHaveTextContent('Análisis completo');
    expect(chip).toHaveAttribute('data-tone', 'ok');
  });
});
