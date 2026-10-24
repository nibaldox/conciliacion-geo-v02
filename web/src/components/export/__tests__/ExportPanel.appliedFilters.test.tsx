import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { type ReactElement } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'es' } }),
}));

import { ExportPanel } from '../ExportPanel';
import { useSession } from '../../../stores/session';

function renderWith(ui: ReactElement, qc: QueryClient) {
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
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

    await user.click(screen.getByRole('button', { name: 'export.word' }));

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

    await user.click(screen.getByRole('button', { name: 'export.word' }));

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

    await user.click(screen.getByRole('button', { name: 'export.word' }));

    const note = await screen.findByTestId('export-applied-filters');
    expect(note).toHaveTextContent('Filtros aplicados:');
    expect(note).toHaveTextContent('Sectores: A');
    expect(note).toHaveTextContent('Niveles: L1');
    expect(note).toHaveTextContent('Bancos: 2');
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

    await user.click(screen.getByRole('button', { name: 'export.word' }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('export-applied-filters')).not.toBeInTheDocument();
  });
});
