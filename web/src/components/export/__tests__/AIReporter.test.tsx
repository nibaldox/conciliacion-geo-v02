import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { type ReactElement } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const { mockGet, mockPost, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockFetch: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => null,
}));

import { AIReporter } from '../AIReporter';
import { useSession } from '../../../stores/session';

i18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  ns: ['translation'],
  defaultNS: 'translation',
  resources: {
    es: {
      translation: {
        common: { retry: 'Reintentar' },
        ai_reporter: {
          title: 'AI Reporter',
          ready_badge: 'Listo',
          backend_status: 'Estado del backend',
          health: {
            ok: 'AI service disponible',
            unavailable: 'AI service no disponible',
            pending: 'Verificando...',
          },
          form: {
            provider_label: 'Proveedor',
            model_label: 'Modelo',
            notes_label: 'Contexto adicional',
            notes_placeholder: 'Notas...',
            generate_button: 'Generar informe',
            generating: 'Generando...',
            copy_button: 'Copiar al portapapeles',
            download_button: 'Descargar .md',
          },
          advanced: {
            toggle: 'Avanzado',
            temperature_label: 'Temperatura',
            max_tokens_label: 'Máx. tokens',
            timeout_label: 'Timeout (s)',
            cache_label: 'Usar caché',
          },
          filters: {
            toggle: 'Filtros',
            sector_label: 'Sector',
            section_label: 'Sección',
            bench_label: 'Banco',
          },
          stream: {
            label: 'Modo de respuesta',
            single: 'Respuesta única',
            stream: 'Transmitir token a token',
          },
          empty: {
            no_data_title: 'Sin datos de análisis',
            no_data_description:
              'Carga un análisis primero o prueba con datos de ejemplo.',
          },
          error: {
            unavailable_title: 'Servicio IA no disponible',
            unavailable_description: 'No se pudo conectar con el backend.',
            rate_limited: 'Servicio ocupado, reintentar en {{seconds}}s',
            server_error: 'Error generando reporte',
            network_error: 'Sin conexión al servidor',
          },
          report: {
            title: 'Informe generado',
            tokens_label:
              'Tokens: {{prompt}} prompt + {{completion}} completion = {{total}} total',
            tps_label: '{{tps}} tok/s',
            cost_label: 'Costo estimado ${{cost}}',
            cached_badge: 'served from cache',
            estimated_badge: 'estimado',
          },
        },
      },
    },
  },
  interpolation: { escapeValue: false },
});

function renderWith(ui: ReactElement, qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </QueryClientProvider>,
  );
}

function sampleComparison() {
  return [
    {
      sector: 'N',
      section: 'S-01',
      bench_num: 1,
      type: 'MATCH' as const,
      level: 'B1',
      height_design: 15,
      height_real: 14.8,
      height_dev: 0.2,
      height_status: 'CUMPLE',
      angle_design: 60,
      angle_real: 59,
      angle_dev: 1,
      angle_status: 'CUMPLE',
      berm_design: 10,
      berm_real: 9.5,
      berm_min: 8,
      berm_status: 'CUMPLE',
      delta_crest: 0.1,
      delta_toe: 0.2,
    },
  ];
}

describe('AIReporter', () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    mockGet.mockReset();
    mockPost.mockReset();
    mockFetch.mockReset();
    vi.stubGlobal('fetch', mockFetch);
    useSession.getState().reset();
  });

  afterEach(() => {
    useSession.getState().reset();
    vi.unstubAllGlobals();
  });

  function setupHealthy(options?: { results?: unknown[] }) {
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/ai/health')
        return {
          data: {
            status: 'ok',
            version: '2.0.0',
            providers: ['openai', 'ollama'],
          },
        };
      if (url === '/ai/providers')
        return { data: { providers: ['openai', 'ollama'] } };
      if (url === '/process/results')
        return { data: options?.results ?? sampleComparison() };
      if (url === '/sections') return { data: [] };
      return { data: {} };
    });
  }

  it('renders the title and pending health state immediately', () => {
    mockGet.mockImplementation(() => new Promise(() => {}));

    renderWith(<AIReporter />, qc);

    expect(screen.getByText('AI Reporter')).toBeInTheDocument();
    expect(screen.getByText('Listo')).toBeInTheDocument();
    expect(screen.getByTestId('ai-reporter-health')).toHaveTextContent(
      'Verificando...',
    );
  });

  it('marks the AI service as unavailable when /ai/health rejects', async () => {
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/ai/health') throw { response: { status: 503 } };
      return { data: {} };
    });

    renderWith(<AIReporter />, qc);

    const health = await screen.findByTestId('ai-reporter-health');
    await waitFor(() => {
      expect(health).toHaveTextContent('AI service no disponible');
    });
    expect(await screen.findByTestId('ai-reporter-unavailable')).toHaveTextContent(
      'Servicio IA no disponible',
    );
  });

  it('marks the AI service as available when /ai/health returns ok', async () => {
    setupHealthy();

    renderWith(<AIReporter />, qc);

    await waitFor(() => {
      expect(screen.getByTestId('ai-reporter-health')).toHaveTextContent(
        'AI service disponible',
      );
    });
  });

  it('renders the form when AI health is ok and results are available', async () => {
    setupHealthy();

    renderWith(<AIReporter />, qc);

    const form = await screen.findByTestId('ai-reporter-form');
    expect(form).toBeInTheDocument();
    expect(screen.getByText('Proveedor')).toBeInTheDocument();
    expect(screen.getByText('Modelo')).toBeInTheDocument();
    expect(screen.getByText('Contexto adicional')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generar informe' })).toBeInTheDocument();
  });

  it('renders the empty state instead of the form when results are missing', async () => {
    setupHealthy({ results: [] });

    renderWith(<AIReporter />, qc);

    const empty = await screen.findByTestId('ai-reporter-empty');
    expect(empty).toHaveTextContent('Sin datos de análisis');
    expect(screen.queryByTestId('ai-reporter-form')).not.toBeInTheDocument();
  });

  it('renders the report and token usage after a successful generation', async () => {
    setupHealthy();
    mockPost.mockResolvedValueOnce({
      data: {
        content: '## Informe\nCumple en 1 banco.',
        finish_reason: 'stop',
        usage: {
          prompt_tokens: 100,
          completion_tokens: 50,
          total_tokens: 150,
          is_synthetic: false,
        },
        cached: false,
        chunk_index: 0,
      },
    });

    const user = userEvent.setup();
    renderWith(<AIReporter />, qc);

    await screen.findByTestId('ai-reporter-form');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Generar informe' })).toBeEnabled();
    });

    await user.click(screen.getByRole('button', { name: 'Generar informe' }));

    await waitFor(() => {
      expect(screen.getByTestId('ai-reporter-content')).toHaveTextContent(
        '## Informe',
      );
    });
    expect(screen.getByTestId('ai-reporter-usage')).toHaveTextContent(
      'Tokens: 100 prompt + 50 completion = 150 total',
    );
    expect(mockPost).toHaveBeenCalledWith(
      '/ai/generate',
      expect.objectContaining({
        provider: 'openai',
        model: 'gpt-4o-mini',
        stream: false,
      }),
    );
  });

  it('renders the advanced section temperature slider when expanded', async () => {
    setupHealthy();

    renderWith(<AIReporter />, qc);

    await screen.findByTestId('ai-reporter-form');
    await userEvent.click(screen.getByTestId('ai-advanced').querySelector('button')!);
    const temperature = await screen.findByTestId('ai-temperature');
    expect(temperature).toBeInTheDocument();
    expect((temperature as HTMLInputElement).type).toBe('range');
  });

  it('uses the streaming endpoint when stream mode is selected', async () => {
    setupHealthy();
    function ndjsonBody(chunks: Array<Record<string, unknown>>) {
      const enc = new TextEncoder();
      const lines = chunks.map((c) => JSON.stringify(c));
      return new ReadableStream({
        start(controller) {
          lines.forEach((l) => controller.enqueue(enc.encode(l + '\n')));
          controller.close();
        },
      });
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: ndjsonBody([
        { content: 'Hola ', finish_reason: null, usage: null, cached: false, chunk_index: 0 },
        {
          content: '',
          finish_reason: 'stop',
          usage: { prompt_tokens: 1, completion_tokens: 2, total_tokens: 3, is_synthetic: false },
          cached: false,
          chunk_index: 1,
        },
      ]),
      json: async () => ({}),
    } as unknown as Response);

    const user = userEvent.setup();
    renderWith(<AIReporter />, qc);

    await screen.findByTestId('ai-reporter-form');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Generar informe' })).toBeEnabled();
    });
    await user.click(screen.getByTestId('ai-stream-toggle-stream'));
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/ai/generate/stream',
        expect.objectContaining({ method: 'POST' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId('ai-reporter-content')).toHaveTextContent('Hola');
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('downloads the report as markdown when the download button is clicked', async () => {
    setupHealthy();
    mockPost.mockResolvedValueOnce({
      data: {
        content: '## Informe\nCumple.',
        finish_reason: 'stop',
        usage: null,
        cached: false,
        chunk_index: 0,
      },
    });
    const createUrlSpy = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:fake');
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});

    const user = userEvent.setup();
    renderWith(<AIReporter />, qc);

    await screen.findByTestId('ai-reporter-form');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Generar informe' })).toBeEnabled();
    });
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));
    await screen.findByTestId('ai-reporter-result');

    await user.click(screen.getByTestId('ai-download-md'));

    expect(createUrlSpy).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    createUrlSpy.mockRestore();
    clickSpy.mockRestore();
  });

  it('shows tokens-per-second in the usage summary after generation', async () => {
    setupHealthy();
    mockPost.mockResolvedValueOnce({
      data: {
        content: '## Informe\nTexto.',
        finish_reason: 'stop',
        usage: {
          prompt_tokens: 100,
          completion_tokens: 50,
          total_tokens: 150,
          is_synthetic: false,
        },
        cached: false,
        chunk_index: 0,
      },
    });

    const user = userEvent.setup();
    renderWith(<AIReporter />, qc);

    await screen.findByTestId('ai-reporter-form');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Generar informe' })).toBeEnabled();
    });
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));

    const tps = await screen.findByTestId('ai-reporter-tps');
    expect(tps).toBeInTheDocument();
    expect(tps.textContent).toMatch(/tok\/s/);
  });
});
