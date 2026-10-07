import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../../../locales/es.json';
import { useSession } from '../../../../../stores/session';
import { ProfileView } from '../ProfileView';
import type { ProfileViewModel } from '../../domain/types';

vi.mock('../../../ProfilePlanThumbnail', () => ({ ProfilePlanThumbnail: () => null }));
vi.mock('../SectionHeader', () => ({ SectionHeader: () => null }));
vi.mock('../../../../../api/hooks', async () => ({
  ...await vi.importActual<typeof import('../../../../../api/hooks')>('../../../../../api/hooks'),
  useBlastHoles: () => ({ data: undefined }),
}));
vi.mock('../../../../charts/Plot', () => ({
  default: ({ data, onClick }: {
    data: Array<{ meta?: { profileViewRole?: string }; mode?: string; name?: string; customdata?: unknown[] }>;
    onClick?: (event: { points: Array<{ curveNumber: number; customdata?: unknown }> }) => void;
  }) => {
    const markerIndex = data.findIndex((trace) => trace.meta?.profileViewRole === 'bench-marker' && trace.mode === 'text+markers');
    const faceIndex = data.findIndex((trace) => trace.meta?.profileViewRole === 'bench-face' && trace.mode === 'lines');
    const clickTrace = (curveNumber: number) => {
      const trace = data[curveNumber];
      if (curveNumber < 0 || !trace) return;
      onClick?.({ points: [
        { curveNumber: 0 },
        { curveNumber, customdata: trace.customdata?.[0] },
      ] });
    };
    return (
      <div>
        <button type="button" data-testid="plot-bench-marker" onClick={() => clickTrace(markerIndex)}>Marker</button>
        <button type="button" data-testid="plot-bench-face" onClick={() => clickTrace(faceIndex)}>Face</button>
      </div>
    );
  },
}));
vi.mock('../../application', async () => ({
  ...await vi.importActual<typeof import('../../application')>('../../application'),
  useProfileViewModel: () => ({ viewModel, isLoading: false, error: null }),
}));

const baseViewModel: ProfileViewModel = {
  section: { id: 'section-1', name: 'S-01', sector: 'Norte', azimuth: 0, length: 100, origin: [0, 0] },
  lines: [{ kind: 'topo', points: [
    { distance: 0, elevation: 100 },
    { distance: 3, elevation: 92 },
    { distance: 7, elevation: 85 },
    { distance: 10, elevation: 80 },
  ] }],
  benches: [{
    benchNumber: 4, crestElevation: 100, crestDistance: 0, toeElevation: 85,
    toeDistance: 7, height: 15, faceAngle: 65, bermWidth: 8,
    designHeight: 15, designAngle: 65, designBerm: 8, isRamp: false,
    heightStatus: 'CUMPLE', angleStatus: 'CUMPLE', bermStatus: 'CUMPLE',
    status: 'CUMPLE', matched: true, deltaCrest: null, deltaToe: null,
  }],
};
let viewModel: ProfileViewModel = baseViewModel;

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

beforeEach(() => {
  viewModel = baseViewModel;
  localStorage.clear();
  useSession.getState().reset();
  useSession.getState().setSelectedSection('section-1');
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
    unobserve() {}
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('ProfileView selection', () => {
  it('explains a disconnected source profile by surface', () => {
    viewModel = { ...baseViewModel, profileWarnings: { design: ['disconnected_profile_components'], topo: [] } };
    render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

    expect(screen.getByRole('status')).toHaveTextContent('El corte de diseño cruza tramos desconectados; se omitió el perfil de esta sección.');
  });

  it('explains a normalized small reversal without claiming the profile was omitted', () => {
    viewModel = { ...baseViewModel, profileWarnings: { design: [], topo: ['minor_profile_reversal_normalized'] } };
    const { container } = render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

    const warning = container.querySelector('[data-slot="profile-recovery-warning"]');
    expect(warning).not.toBeNull();
    expect(warning).toHaveTextContent('El corte de topografía tenía un retroceso local pequeño. Se normalizó a un tramo vertical de hasta 0,1 m y se conservaron las cotas; revise esta zona si esa resolución es relevante.');
    expect(warning).not.toHaveTextContent('se omitió el perfil');
    expect(container.querySelector('[data-slot="profile-unavailable-warning"]')).not.toBeInTheDocument();
  });

  it('keeps a major geometry rejection distinct from a recoverable warning', () => {
    viewModel = { ...baseViewModel, profileWarnings: { design: [], topo: ['ambiguous_profile_geometry'] } };
    const { container } = render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

    expect(container.querySelector('[data-slot="profile-unavailable-warning"]')).toHaveTextContent('se omitió el perfil de esta sección');
    expect(container.querySelector('[data-slot="profile-recovery-warning"]')).not.toBeInTheDocument();
  });

  it('explains missing intersections and processing errors without displaying unknown codes', () => {
    viewModel = { ...baseViewModel, profileWarnings: {
      design: ['no_section_intersection', 'private_backend_detail'],
      topo: ['section_processing_error'],
    } };
    render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

    const warning = screen.getByRole('status');
    expect(warning).toHaveTextContent('El corte de diseño no intersecta la superficie; no se obtuvo un perfil para esta sección.');
    expect(warning).toHaveTextContent('Ocurrió un error al procesar la sección de topografía; el perfil no está disponible.');
    expect(warning).not.toHaveTextContent('private_backend_detail');
  });

  it('shows the selected bank in the inspector when clicking its profile face', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

    await user.click(screen.getByTestId('plot-bench-face'));

    expect(screen.getByText('Banco 04')).toBeInTheDocument();
    expect(screen.getByRole('row', { name: 'Banco 4' })).toHaveAttribute('data-selected', 'true');
    expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it('shows the selected bank in the inspector when clicking its marker', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

    await user.click(screen.getByTestId('plot-bench-marker'));

    expect(screen.getByText('Banco 04')).toBeInTheDocument();
    expect(screen.getByRole('row', { name: 'Banco 4' })).toHaveAttribute('data-selected', 'true');
  });

  it('keeps a selected bench through rerenders and clears it only when the section changes', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);
    const row = screen.getByRole('row', { name: 'Banco 4' });
    await user.click(row);
    expect(screen.getByText('Banco 04')).toBeInTheDocument();
    expect(row).toHaveAttribute('data-selected', 'true');
    await user.hover(row);
    await user.unhover(row);
    expect(screen.getByText('Banco 04')).toBeInTheDocument();
    act(() => useSession.getState().setSelectedSection('section-2'));
    expect(screen.getByText('Selecciona un banco')).toBeInTheDocument();
    expect(row).not.toHaveAttribute('data-selected');
  });
});
