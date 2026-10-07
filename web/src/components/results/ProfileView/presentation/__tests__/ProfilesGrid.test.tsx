import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../../../locales/es.json';
import { ProfilesGrid } from '../ProfilesGrid';

const queryState = vi.hoisted(() => ({
  data: undefined as unknown,
  isPending: false,
  isError: false,
  refetch: vi.fn(),
}));

vi.mock('../../../../../api/hooks', () => ({
  useSections: () => ({
    data: [{ id: 'section-1', name: 'S-01', origin: [0, 0], azimuth: 0, length: 100 }],
    isLoading: false,
  }),
  useProfile: () => queryState,
}));

vi.mock('../../../../charts/Plot', () => ({ default: () => <div data-testid="profile-plot" /> }));

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

beforeEach(() => {
  queryState.data = undefined;
  queryState.isPending = false;
  queryState.isError = false;
  queryState.refetch.mockReset();
});

afterEach(() => vi.clearAllMocks());

describe('ProfilesGrid profile query states', () => {
  it('shows a terminal API error and retries instead of leaving a permanent spinner', () => {
    queryState.isError = true;
    queryState.refetch.mockResolvedValue({});
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByText('No se pudo cargar este perfil.')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar perfil' }));
    expect(queryState.refetch).toHaveBeenCalledOnce();
  });

  it('keeps the spinner while the profile request is still pending', () => {
    queryState.isPending = true;
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('No se pudo cargar este perfil.')).not.toBeInTheDocument();
  });

  it('renders a valid profile after loading completes', () => {
    queryState.data = {
      design: { distances: [0, 10], elevations: [100, 90] },
      topo: null,
    };
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByTestId('profile-plot')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('explains a successful response with no profile points', () => {
    queryState.data = { design: null, topo: null };
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByText('Este perfil no tiene datos para mostrar.')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('keeps cached profile data visible when a background refresh fails', () => {
    queryState.data = {
      design: { distances: [0, 10], elevations: [100, 90] },
      topo: null,
    };
    queryState.isError = true;
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByTestId('profile-plot')).toBeInTheDocument();
    expect(screen.getByText('No se pudo actualizar este perfil.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reintentar perfil' })).toBeInTheDocument();
  });
});
