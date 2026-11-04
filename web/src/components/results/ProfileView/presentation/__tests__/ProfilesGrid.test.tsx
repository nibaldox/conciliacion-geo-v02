import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../../../locales/es.json';
import { useSession } from '../../../../../stores/session';
import { useTheme } from '../../../../../stores/theme';
import { ProfilesGrid } from '../ProfilesGrid';

const queryState = vi.hoisted(() => ({
  data: undefined as unknown,
  isPending: false,
  isError: false,
  refetch: vi.fn(),
}));

vi.mock('../../../../../api/hooks', () => ({
  useSections: () => ({
    data: [{ id: 'section-1', name: 'S-01', sector: 'Norte', origin: [0, 0], azimuth: 0, length: 100 }],
    isLoading: false,
  }),
  useProfile: () => queryState,
}));

vi.mock('../../../../charts/Plot', () => ({ default: ({ layout }: {
  layout: {
    xaxis?: { tickfont?: { size?: number; color?: string } };
    yaxis?: { tickfont?: { size?: number; color?: string } };
  };
}) => (
  <div
    data-testid="profile-plot"
    data-x-tick-size={layout.xaxis?.tickfont?.size}
    data-x-tick-color={layout.xaxis?.tickfont?.color}
    data-y-tick-size={layout.yaxis?.tickfont?.size}
    data-y-tick-color={layout.yaxis?.tickfont?.color}
  />
)}));

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

beforeEach(() => {
  queryState.data = undefined;
  queryState.isPending = false;
  queryState.isError = false;
  queryState.refetch.mockReset();
  useSession.setState({ selectedSection: null });
  useTheme.setState({ isDark: true });
});

afterEach(() => vi.clearAllMocks());

describe('ProfilesGrid profile query states', () => {
  it('highlights the selected card by section id when its name differs', () => {
    useSession.setState({ selectedSection: 'section-1' });
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByRole('button', { name: /S-01/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('uses responsive one, two, and three column layouts', () => {
    render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

    expect(screen.getByRole('button', { name: /S-01/ }).parentElement?.parentElement).toHaveClass(
      'grid-cols-1',
      'sm:grid-cols-2',
      'xl:grid-cols-3',
    );
  });

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

  it('uses readable sector text and secondary-color ticks in both themes', () => {
    queryState.data = {
      design: { distances: [0, 10], elevations: [100, 90] },
      topo: null,
    };

    for (const [isDark, expectedTickColor] of [[true, '#bfccd9'], [false, '#4b5563']] as const) {
      useTheme.setState({ isDark });
      const { unmount } = render(<I18nextProvider i18n={i18n}><ProfilesGrid /></I18nextProvider>);

      const sector = screen.getByText('Norte');
      expect(sector).toHaveClass('text-xs');
      expect(sector).toHaveStyle({ color: 'var(--color-text-secondary)' });

      const plot = screen.getByTestId('profile-plot');
      expect(plot).toHaveAttribute('data-x-tick-size', '10');
      expect(plot).toHaveAttribute('data-y-tick-size', '10');
      expect(plot).toHaveAttribute('data-x-tick-color', expectedTickColor);
      expect(plot).toHaveAttribute('data-y-tick-color', expectedTickColor);
      unmount();
    }
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
