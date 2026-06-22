import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { AIReporter } from '../AIReporter';

i18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  ns: ['translation'],
  defaultNS: 'translation',
  resources: {
    es: {
      translation: {
        ai_reporter: {
          title: 'AI Reporter',
          pending:
            'Próximamente — la integración con el backend core/ai_v2 está pendiente.',
          how_it_works: 'Cómo funciona',
          feature_sanitization:
            'Sanitización de prompt contra inyección desde metadata del usuario',
          feature_streaming:
            'Respuestas en streaming con métricas de tokens',
          feature_structured:
            'Output estructurado (veredicto, métricas, recomendaciones)',
          feature_tokens:
            'Tracking de usage con propagación de tokens reales del provider',
          backend_status: 'Estado del backend',
          health_ok: 'AI service disponible',
          health_unavailable: 'AI service no disponible',
          health_pending: 'Verificando...',
        },
      },
    },
  },
  interpolation: { escapeValue: false },
});

function renderWithI18n() {
  return render(
    <I18nextProvider i18n={i18n}>
      <AIReporter />
    </I18nextProvider>
  );
}

describe('AIReporter stub', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('renders the title and pending message immediately', () => {
    globalThis.fetch = vi.fn(() => new Promise(() => {})) as typeof fetch;

    renderWithI18n();

    expect(screen.getByText('AI Reporter')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Próximamente — la integración con el backend core/ai_v2 está pendiente.'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('Cómo funciona')).toBeInTheDocument();
    expect(screen.getByTestId('ai-reporter-health')).toHaveTextContent(
      'Verificando...'
    );
  });

  it('marks the AI service as unavailable when /api/v1/ai/health returns 503', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response('service unavailable', { status: 503 })
    ) as typeof fetch;

    renderWithI18n();

    const health = await screen.findByTestId('ai-reporter-health');
    await waitFor(() => {
      expect(health).toHaveTextContent('AI service no disponible');
    });
  });

  it('marks the AI service as available when /api/v1/ai/health returns 200', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    ) as typeof fetch;

    renderWithI18n();

    const health = await screen.findByTestId('ai-reporter-health');
    await waitFor(() => {
      expect(health).toHaveTextContent('AI service disponible');
    });
  });
});
