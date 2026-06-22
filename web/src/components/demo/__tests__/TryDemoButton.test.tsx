import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { type ReactElement } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

vi.mock('../../../api/client', () => ({
  default: {
    get: vi.fn(async () => ({
      data: {
        status: 'idle',
        current_section: null,
        total_sections: null,
        completed_sections: 0,
        n_results: 0,
      },
    })),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
  },
}));

import { TryDemoButton } from '../TryDemoButton';
import { useSession, type DemoData } from '../../../stores/session';
import { useProcessStatus } from '../../../api/hooks';

i18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  resources: {
    es: {
      translation: {
        common: { loading: 'Cargando…' },
        demo: {
          try_title: '¿Sin datos propios?',
          try_subtitle: 'sub',
          try_button: '▶ Probar con datos de ejemplo',
        },
      },
    },
  },
  interpolation: { escapeValue: false },
});

const demoData: DemoData = {
  summary: { n_sections: 4, n_comparisons: 16, n_match: 10, compliance: {} },
  vertices: {
    design: { x: [0, 1], y: [0, 1], z: [0, 1] },
    topo: { x: [0, 1], y: [0, 1], z: [0, 1] },
  },
  sections: [
    {
      section_name: 'S-01',
      sector: 'N',
      origin: [0, 0],
      azimuth: 90,
      design_profile: { distances: [0, 1], elevations: [10, 10] },
      topo_profile: { distances: [0, 1], elevations: [10, 10] },
      reconciled_topo: { distances: [0, 1], elevations: [10, 10] },
      benches_topo: [],
    },
  ],
  comparisons: [],
};

function StatusProbe() {
  const { data } = useProcessStatus();
  return <div data-testid="probe">{data?.status ?? 'none'}</div>;
}

function renderWith(ui: ReactElement, qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </QueryClientProvider>,
  );
}

describe('TryDemoButton — demo process-status cache', () => {
  let qc: QueryClient;
  let originalFetch: typeof fetch;

  beforeEach(() => {
    qc = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
      },
    });
    originalFetch = globalThis.fetch;
    useSession.getState().reset();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    useSession.getState().reset();
  });

  function mockDemoFetch() {
    globalThis.fetch = vi.fn(async (input: URL | RequestInfo) => {
      const url = String(input);
      if (url.includes('/demo/precomputed.json')) {
        return new Response(JSON.stringify(demoData), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('', { status: 404 });
    }) as typeof fetch;
  }

  it('writes { status: "complete" } to the process-status cache after click', async () => {
    mockDemoFetch();
    const user = userEvent.setup();
    renderWith(<TryDemoButton />, qc);

    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(qc.getQueryData(['process-status'])).toMatchObject({
        status: 'complete',
        total_sections: 4,
        completed_sections: 4,
        n_results: 16,
      });
    });
  });

  it('useProcessStatus().data reports complete after the demo loads', async () => {
    mockDemoFetch();
    const user = userEvent.setup();
    renderWith(
      <>
        <TryDemoButton />
        <StatusProbe />
      </>,
      qc,
    );

    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByTestId('probe')).toHaveTextContent('complete');
    });
  });
});
