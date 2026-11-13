import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-panel-models'),
  mockFetch: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: (...args: unknown[]) => mockDelete(...args),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import type { AIProvidersState } from '../../../api/aiChat';
import { useAIChat } from '../../../stores/aiChat';
import { ChatPanel } from '../ChatPanel';
import {
  CHAT_TEXT_DONE,
  initChatI18n,
  makeNdjsonResponse,
  renderWithProviders,
} from './chatTestUtils';

function providersBody(overrides: Partial<AIProvidersState> = {}): AIProvidersState {
  return {
    providers: ['lmstudio'],
    supports_tool_calls: { lmstudio: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'loaded-model',
    ...overrides,
  };
}

function modelsState(
  ids: string[],
  overrides: Partial<NonNullable<AIProvidersState['chat_models']>> = {},
): NonNullable<AIProvidersState['chat_models']> {
  return {
    status: 'ok',
    source: 'v1',
    models: ids.map((id) => ({ id, label: id, tool_use: true })),
    selected: null,
    selected_source: null,
    ...overrides,
  };
}

function single(id: string): AIProvidersState {
  return providersBody({
    chat_model: id,
    chat_models: modelsState([id], { selected: id, selected_source: 'auto' }),
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

const noop = () => undefined;

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  initChatI18n();
  useAIChat.getState().reset();
});

describe('ChatPanel — detected loaded models', () => {
  it('shows CONFIGURADO and the detected chip for a single loaded model', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha:2',
        chat_models: modelsState(['alpha:2'], {
          selected: 'alpha:2',
          selected_source: 'auto',
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'alpha:2',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'configured',
    );
    expect(screen.queryByTestId('ai-chat-model-select')).toBeNull();
    expect(screen.queryByTestId('ai-chat-session-model-input')).toBeNull();
    expect(screen.queryByTestId('ai-chat-models-notice')).toBeNull();
  });

  it('offers an explicit selector and refuses to claim readiness until picked', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-model-select')).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('ELIGE MODELO');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'choose_model',
    );
    const optionLabels = screen
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(optionLabels).toEqual(['Selecciona un modelo…', 'alpha', 'beta']);

    await userEvent.selectOptions(
      screen.getByTestId('ai-chat-model-select'),
      'beta',
    );
    expect(useAIChat.getState().sessionModel).toBe('beta');
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
    expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('beta');
  });

  it('reports zero loaded models honestly and offers the manual fallback', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-models-notice')).toHaveTextContent(
      'No hay ningún modelo de chat cargado',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('SIN MODELO');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'no_model',
    );
    expect(screen.getByTestId('ai-chat-session-model-input')).toBeInTheDocument();
    expect(screen.queryByTestId('ai-chat-model-chip')).toBeNull();
  });

  it('reports a disconnected LM Studio instead of a fake CONFIGURADO', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState([], { status: 'unavailable', source: null }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-models-notice')).toHaveTextContent(
      'No se pudo consultar LM Studio',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('SIN CONEXIÓN');
    expect(screen.getByTestId('ai-chat-session-model-input')).toBeInTheDocument();
  });

  it('retries discovery from the notice button when the state changes', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const refresh = await screen.findByTestId('ai-chat-models-refresh');

    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
        }),
      }),
    });
    await userEvent.click(refresh);

    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'alpha',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
    expect(screen.queryByTestId('ai-chat-models-notice')).toBeNull();
  });

  it('never overrides the server-pinned model with a selector', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'server-pinned',
        chat_models: modelsState(['alpha', 'beta'], {
          selected: 'server-pinned',
          selected_source: 'override',
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'server-pinned',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
    expect(screen.queryByTestId('ai-chat-model-select')).toBeNull();
  });

  it('does not claim CONFIGURADO for a pinned model when LM Studio is down', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'server-pinned',
        chat_models: modelsState([], {
          status: 'unavailable',
          source: null,
          selected: 'server-pinned',
          selected_source: 'override',
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'server-pinned',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('SIN CONEXIÓN');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'no_connection',
    );
  });

  it('warns when the only detected model does not support tool calls', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
          models: [{ id: 'alpha', label: 'alpha', tool_use: false }],
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-model-no-tools')).toHaveTextContent(
      'no soporta llamadas a herramientas',
    );
  });

  it('keeps the legacy placeholder warning when chat_models is absent', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_model: 'loaded-model' }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(
      await screen.findByTestId('ai-chat-placeholder-model-warning'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('SIN MODELO');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'no_model',
    );
  });

  it('never renders the legacy placeholder sentinel as a model id', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_model: 'loaded-model' }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    await screen.findByTestId('ai-chat-placeholder-model-warning');
    expect(screen.queryByTestId('ai-chat-model-chip')).toBeNull();
    expect(screen.queryByText('loaded-model')).toBeNull();
  });

  const refreshStates: Array<[string, string, () => AIProvidersState]> = [
    [
      'configured',
      'CONFIGURADO',
      () =>
        providersBody({
          chat_model: 'alpha',
          chat_models: modelsState(['alpha'], {
            selected: 'alpha',
            selected_source: 'auto',
          }),
        }),
    ],
    [
      'choose_model',
      'ELIGE MODELO',
      () => providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    ],
    [
      'no_model',
      'SIN MODELO',
      () => providersBody({ chat_models: modelsState([]) }),
    ],
    [
      'no_connection',
      'SIN CONEXIÓN',
      () =>
        providersBody({
          chat_models: modelsState([], { status: 'unavailable', source: null }),
        }),
    ],
    [
      'not_supported',
      'API NO COMPATIBLE',
      () =>
        providersBody({
          chat_models: modelsState([], {
            status: 'not_supported',
            source: null,
          }),
        }),
    ],
    [
      'disabled',
      'NO DISPONIBLE',
      () => providersBody({ chat_enabled: false }),
    ],
    [
      'override',
      'CONFIGURADO',
      () =>
        providersBody({
          chat_model: 'server-pinned',
          chat_models: modelsState(['alpha', 'beta'], {
            selected: 'server-pinned',
            selected_source: 'override',
          }),
        }),
    ],
  ];

  it.each(refreshStates)(
    'offers the discovery refresh in the %s state',
    async (_name, expectedStatus, makeBody) => {
      mockGet.mockResolvedValueOnce({ data: makeBody() });
      renderWithProviders(<ChatPanel onClose={noop} />);

      await waitFor(() =>
        expect(screen.getByTestId('ai-chat-status')).toHaveTextContent(
          expectedStatus,
        ),
      );
      expect(screen.getByTestId('ai-chat-models-refresh')).toBeEnabled();
    },
  );

  it('keeps the discovery refresh visible while the state is loading', async () => {
    mockGet.mockReturnValueOnce(new Promise(() => undefined));
    renderWithProviders(<ChatPanel onClose={noop} />);

    const refresh = await screen.findByTestId('ai-chat-models-refresh');
    await waitFor(() => expect(refresh).toBeDisabled());
    expect(screen.getByTestId('ai-chat-status').textContent).toBe('');
  });

  it('recovers from a failed refresh and keeps the last known model visible', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'alpha',
        chat_models: modelsState(['alpha'], {
          selected: 'alpha',
          selected_source: 'auto',
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);
    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'alpha',
    );

    mockGet.mockRejectedValueOnce(new Error('offline'));
    await userEvent.click(screen.getByTestId('ai-chat-models-refresh'));

    expect(
      await screen.findByText(
        'No se pudo consultar el estado del chat en el servidor.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha');
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');

    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'beta',
        chat_models: modelsState(['beta'], {
          selected: 'beta',
          selected_source: 'auto',
        }),
      }),
    });
    await userEvent.click(screen.getByTestId('ai-chat-models-refresh'));

    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'beta',
    );
    await waitFor(() =>
      expect(
        screen.queryByText(
          'No se pudo consultar el estado del chat en el servidor.',
        ),
      ).toBeNull(),
    );
  });

  it('reports a non-LM-Studio API separately from a disconnected server', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState([], {
          status: 'not_supported',
          source: null,
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-models-notice')).toHaveTextContent(
      'no expone la API de modelos de LM Studio',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent(
      'API NO COMPATIBLE',
    );
  });

  it('differentiates loaded instances that share the same display label', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState(['alpha:1', 'alpha:2'], {
          models: [
            { id: 'alpha:1', label: 'Alpha', tool_use: true },
            { id: 'alpha:2', label: 'Alpha', tool_use: true },
          ],
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    const select = await screen.findByTestId('ai-chat-model-select');
    const optionLabels = Array.from(select.querySelectorAll('option')).map(
      (option) => option.textContent,
    );
    expect(optionLabels).toEqual([
      'Selecciona un modelo…',
      'Alpha (alpha:1)',
      'Alpha (alpha:2)',
    ]);
  });

  it('warns when a model chosen in the selector lacks tool support', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState(['alpha', 'beta'], {
          models: [
            { id: 'alpha', label: 'Alpha', tool_use: false },
            { id: 'beta', label: 'Beta', tool_use: true },
          ],
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    const select = await screen.findByTestId('ai-chat-model-select');
    expect(select.querySelector('option[value="alpha"]')).toHaveTextContent(
      'sin herramientas',
    );
    expect(select.querySelector('option[value="beta"]')).not.toHaveTextContent(
      'sin herramientas',
    );
    await userEvent.selectOptions(select, 'alpha');

    expect(
      await screen.findByTestId('ai-chat-model-no-tools'),
    ).toHaveTextContent('no soporta llamadas a herramientas');

    await userEvent.selectOptions(select, 'beta');
    expect(screen.queryByTestId('ai-chat-model-no-tools')).toBeNull();
  });
});

describe('ChatPanel — draft ownership and stale notices', () => {
  it('drops the choose-a-model instruction once a model is picked', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    const select = await screen.findByTestId('ai-chat-model-select');
    expect(screen.getByTestId('ai-chat-models-notice')).toHaveTextContent(
      'elige uno antes de enviar',
    );

    await userEvent.selectOptions(select, 'beta');

    expect(screen.queryByTestId('ai-chat-models-notice')).toBeNull();
    expect(screen.getByTestId('ai-chat-model-selector')).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat-model-select')).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
  });

  it('keeps the draft when the send is rejected for a missing model choice', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState(['alpha', 'beta']) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');
    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));

    expect(mockFetch).not.toHaveBeenCalled();
    expect(input).toHaveValue('hola');
    expect(screen.getByTestId('ai-chat-models-notice')).toBeInTheDocument();

    mockFetch.mockResolvedValueOnce(
      makeNdjsonResponse(CHAT_TEXT_DONE),
    );
    await userEvent.selectOptions(
      screen.getByTestId('ai-chat-model-select'),
      'beta',
    );
    await userEvent.click(screen.getByTestId('ai-chat-send'));

    await waitFor(() => expect(input).toHaveValue(''));
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('keeps the draft while the model revalidation is in flight', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha'),
    );

    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(makeNdjsonResponse(CHAT_TEXT_DONE));

    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    await tick();

    expect(input).toHaveValue('hola');
    expect(mockFetch).not.toHaveBeenCalled();

    gate.resolve({ data: single('alpha') });
    await waitFor(() => expect(input).toHaveValue(''));
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('sends the first message while the initial discovery is still in flight', async () => {
    const gate = deferred<{ data: AIProvidersState }>();
    mockGet.mockImplementationOnce(() => gate.promise);
    mockFetch.mockResolvedValueOnce(makeNdjsonResponse(CHAT_TEXT_DONE));
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');

    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    await tick();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId('ai-chat-placeholder-model-warning')).toBeNull();
    expect(input).toHaveValue('hola');

    gate.resolve({ data: single('alpha') });
    await waitFor(() => expect(input).toHaveValue(''));
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(
      String((mockFetch.mock.calls[0] as unknown as [string, RequestInit])[1].body),
    ) as Record<string, unknown>;
    expect(body.model).toBe('alpha');
    expect(screen.queryByTestId('ai-chat-notice')).toBeNull();
  });

  it('keeps the draft when the detected model changed and clears it after the resend', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    renderWithProviders(<ChatPanel onClose={noop} />);
    const input = await screen.findByTestId('ai-chat-input');
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha'),
    );

    mockGet.mockResolvedValueOnce({ data: single('beta') });
    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    expect(await screen.findByTestId('ai-chat-notice')).toHaveTextContent(
      'cambió de «alpha» a «beta»',
    );
    expect(input).toHaveValue('hola');
    expect(
      useAIChat.getState().messages.filter((m) => m.kind === 'user'),
    ).toHaveLength(0);
    expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('beta');

    mockGet.mockResolvedValueOnce({ data: single('beta') });
    mockFetch.mockResolvedValueOnce(makeNdjsonResponse(CHAT_TEXT_DONE));
    await userEvent.click(screen.getByTestId('ai-chat-send'));

    await waitFor(() => expect(input).toHaveValue(''));
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(
      String((mockFetch.mock.calls[0] as unknown as [string, RequestInit])[1].body),
    ) as Record<string, unknown>;
    expect(body.model).toBe('beta');
    await waitFor(() =>
      expect(screen.queryByTestId('ai-chat-notice')).toBeNull(),
    );
  });

  it('clears a stale model notice after a successful refresh', async () => {
    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    renderWithProviders(<ChatPanel onClose={noop} />);
    await waitFor(() =>
      expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('alpha'),
    );

    mockGet.mockRejectedValueOnce(new Error('offline'));
    await userEvent.type(screen.getByTestId('ai-chat-input'), 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    expect(await screen.findByTestId('ai-chat-notice')).toHaveTextContent(
      'No se pudo consultar LM Studio',
    );

    mockGet.mockResolvedValueOnce({ data: single('alpha') });
    await userEvent.click(screen.getByTestId('ai-chat-models-refresh'));

    await waitFor(() => expect(screen.queryByTestId('ai-chat-notice')).toBeNull());
  });
});

describe('ChatPanel — honest manual and override status', () => {
  it('reports a typed manual model instead of claiming no connection', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_models: modelsState([], { status: 'unavailable', source: null }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    const manual = await screen.findByTestId('ai-chat-session-model-input');
    await userEvent.type(manual, 'typed-model');

    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('MODELO MANUAL');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'manual',
    );
  });

  it('reports a typed manual model when discovery finds an empty load set', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({ chat_models: modelsState([]) }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    const manual = await screen.findByTestId('ai-chat-session-model-input');
    await userEvent.type(manual, 'typed-model');

    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('MODELO MANUAL');
  });

  it('keeps CONFIGURADO for a server-pinned model even with an empty discovery list', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_model: 'server-pinned',
        chat_models: modelsState([], {
          selected: 'server-pinned',
          selected_source: 'override',
        }),
      }),
    });
    renderWithProviders(<ChatPanel onClose={noop} />);

    expect(await screen.findByTestId('ai-chat-model-chip')).toHaveTextContent(
      'server-pinned',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
    expect(screen.getByTestId('ai-chat-status')).toHaveAttribute(
      'data-status',
      'configured',
    );
  });
});
