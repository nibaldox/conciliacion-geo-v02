import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

vi.mock('../../../api/hooks', () => ({
  useProcess: vi.fn(),
  useProcessStatus: vi.fn(),
  useSettings: vi.fn(),
}));

import { ProcessButton } from '../ProcessButton';
import { useProcess, useProcessStatus, useSettings } from '../../../api/hooks';

const useProcessMock = vi.mocked(useProcess);
const useProcessStatusMock = vi.mocked(useProcessStatus);
const useSettingsMock = vi.mocked(useSettings);

i18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  resources: {
    es: {
      translation: {
        step3: {
          running: 'Procesando…',
          start_processing: '▶ Iniciar Procesamiento',
          complete_title: 'Procesamiento Completo',
          n_results: '{{count}} resultados generados',
          error_title: 'Error en el procesamiento',
          error_detail: 'Hubo un error al procesar las secciones. Intenta nuevamente.',
          error_reason_label: 'Motivo:',
          retry: 'Reintentar',
        },
      },
    },
  },
  interpolation: { escapeValue: false },
});

type ProcessMutation = ReturnType<typeof useProcess>;
type ProcessStatusQuery = ReturnType<typeof useProcessStatus>;
type SettingsQuery = ReturnType<typeof useSettings>;

function makeMutation(overrides: Partial<ProcessMutation> = {}): ProcessMutation {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  } as unknown as ProcessMutation;
}

function idleStatus(): ProcessStatusQuery {
  return {
    data: {
      status: 'idle',
      current_section: null,
      total_sections: null,
      completed_sections: 0,
      n_results: 0,
    },
  } as unknown as ProcessStatusQuery;
}

function noSettings(): SettingsQuery {
  return { data: undefined } as unknown as SettingsQuery;
}

function axiosLikeError(detail: unknown): Error {
  return { response: { data: { detail } } } as unknown as Error;
}

function renderProcessButton() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <ProcessButton />
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

describe('ProcessButton — mutation failure reason', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useProcessStatusMock.mockReturnValue(idleStatus());
    useSettingsMock.mockReturnValue(noSettings());
  });

  it('shows the API detail string when the process POST fails with 400', async () => {
    const mutate = vi.fn();
    useProcessMock.mockReturnValue(
      makeMutation({ mutate, isError: true, error: axiosLikeError('Load sections first') }),
    );
    const user = userEvent.setup();
    renderProcessButton();

    expect(screen.getByText('Error en el procesamiento')).toBeInTheDocument();
    expect(screen.getByText(/Load sections first/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('falls back to the generic i18n message when the error has no detail', () => {
    useProcessMock.mockReturnValue(
      makeMutation({ isError: true, error: new Error('Network Error') }),
    );
    renderProcessButton();

    expect(screen.getByText(/Hubo un error al procesar las secciones/)).toBeInTheDocument();
    expect(screen.queryByText(/Load sections first/)).not.toBeInTheDocument();
  });

  it('does not render the failure block while the mutation is idle', () => {
    useProcessMock.mockReturnValue(makeMutation());
    renderProcessButton();

    expect(screen.queryByText('Error en el procesamiento')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '▶ Iniciar Procesamiento' })).toBeInTheDocument();
  });
});
