import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { type ReactElement } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import i18n from 'i18next';
import es from '../../../locales/es.json';
import en from '../../../locales/en.json';

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
  },
}));

import { ExportPanel } from '../ExportPanel';
import { DEMO_MESH_IDS, useSession } from '../../../stores/session';

const testI18n = i18n.createInstance();
void testI18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  resources: { es: { translation: es }, en: { translation: en } },
});

function renderWith(ui: ReactElement, qc: QueryClient) {
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </I18nextProvider>,
  );
}

function lastGetCallArgs(): { url: string; config: { params: Record<string, string> } } {
  const last = mockGet.mock.calls[mockGet.mock.calls.length - 1];
  if (!last) throw new Error('client.get was never called');
  return { url: last[0] as string, config: last[1] as { params: Record<string, string> } };
}

describe('ExportPanel — session filters, filename and applied-filters note', () => {
  let qc: QueryClient;
  let downloaded: string | null;

  beforeEach(() => {
    void testI18n.changeLanguage('es');
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
    mockGet.mockResolvedValue({ data: new Blob(['x']) });
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() });
    downloaded = null;
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloaded = this.download;
    });
    window.localStorage.clear();
    useSession.getState().reset();
  });

  afterEach(() => {
    useSession.getState().reset();
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('sends the session result filters (sector/section/level/bench) with the export', async () => {
    useSession.setState({ filters: { sector: ['A'], section: ['S-01'], level: ['L1'], bench: [2, 3] } });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    const { config } = lastGetCallArgs();
    const filters = JSON.parse(config.params.filters);
    expect(filters.sector).toEqual(['A']);
    expect(filters.section).toEqual(['S-01']);
    expect(filters.level).toEqual(['L1']);
    expect(filters.selectedBenchNumbers).toEqual([2, 3]);
  });

  it('uses the filename from Content-Disposition when downloading', async () => {
    mockGet.mockResolvedValue({
      data: new Blob(['x']),
      headers: { 'content-disposition': 'attachment; filename=Informe_Conciliacion.docx' },
    });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    await waitFor(() => expect(downloaded).toBe('Informe_Conciliacion.docx'));
  });

  it('shows the applied-filters note from the response header', async () => {
    mockGet.mockResolvedValue({
      data: new Blob(['x']),
      headers: {
        'content-disposition': 'attachment; filename=Informe_Conciliacion.docx',
        'x-export-filters-applied': JSON.stringify({
          sectors: ['A'],
          sections: [],
          levels: ['L1'],
          selected_bench_numbers: [2],
        }),
      },
    });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    const note = await screen.findByTestId('export-applied-filters');
    expect(note).toHaveTextContent('Filtros aplicados:');
    expect(note).toHaveTextContent('Sectores: A');
    expect(note).toHaveTextContent('Niveles: L1');
    expect(note).toHaveTextContent('Bancos: 2');
  });

  it('updates the applied-filters note when the language changes', async () => {
    mockGet.mockResolvedValue({
      data: new Blob(['x']),
      headers: {
        'content-disposition': 'attachment; filename=Informe_Conciliacion.docx',
        'x-export-filters-applied': JSON.stringify({
          sectors: ['A'],
          sections: ['S-01'],
          levels: ['L1'],
          selected_bench_numbers: [2],
        }),
      },
    });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    const note = await screen.findByTestId('export-applied-filters');
    expect(note).toHaveTextContent('Filtros aplicados: Sectores: A · Secciones: S-01 · Niveles: L1 · Bancos: 2');

    await testI18n.changeLanguage('en');

    await waitFor(() =>
      expect(note).toHaveTextContent('Filters applied: Sectors: A · Sections: S-01 · Levels: L1 · Benches: 2'),
    );
  });

  it('does not render the note when no filter dimension is applied', async () => {
    mockGet.mockResolvedValue({
      data: new Blob(['x']),
      headers: {
        'content-disposition': 'attachment; filename=Informe_Conciliacion.docx',
        'x-export-filters-applied': JSON.stringify({
          sectors: [],
          sections: [],
          levels: [],
          selected_bench_numbers: [],
        }),
      },
    });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('export-applied-filters')).not.toBeInTheDocument();
  });

  it('explains that synthetic demo meshes cannot be exported and prevents API calls', async () => {
    useSession.setState({
      demoMode: true,
      designMeshId: DEMO_MESH_IDS.design,
      topoMeshId: DEMO_MESH_IDS.topo,
    });

    renderWith(<ExportPanel />, qc);

    expect(screen.getByTestId('export-demo-notice')).toHaveTextContent('La demo usa superficies sintéticas');
    const buttons = screen.getByTestId('export-actions').querySelectorAll('button');
    expect(buttons).toHaveLength(5);
    for (const button of buttons) expect(button).toBeDisabled();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Exportar Word' }));
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('keeps exports available when demoMode remains true but the session has real mesh IDs', () => {
    useSession.setState({ demoMode: true, designMeshId: 'real-design-id', topoMeshId: 'real-topo-id' });

    renderWith(<ExportPanel />, qc);

    expect(screen.queryByTestId('export-demo-notice')).not.toBeInTheDocument();
    for (const button of screen.getByTestId('export-actions').querySelectorAll('button')) {
      expect(button).toBeEnabled();
    }
  });
});
