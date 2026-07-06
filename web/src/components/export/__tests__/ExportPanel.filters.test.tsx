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
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  );
}

function setBenchFilter(benches: number[]): void {
  useSession.setState({ filters: { sector: [], section: [], level: [], bench: benches } });
}

function setProfileFilters(snapshot: Record<string, unknown>): void {
  window.localStorage.setItem('profileView.filters', JSON.stringify(snapshot));
}

function lastGetCallArgs(): { url: string; config: { params: Record<string, string> } } {
  const last = mockGet.mock.calls[mockGet.mock.calls.length - 1];
  if (!last) throw new Error('client.get was never called');
  return { url: last[0] as string, config: last[1] as { params: Record<string, string> } };
}

describe('ExportPanel — filter propagation (G09)', () => {
  let qc: QueryClient;
  const createUrl = vi.fn(() => 'blob:mock');
  const revokeUrl = vi.fn();

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
    mockGet.mockResolvedValue({ data: new Blob(['x']) });
    vi.stubGlobal('URL', { ...URL, createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    window.localStorage.clear();
    useSession.getState().reset();
  });

  afterEach(() => {
    useSession.getState().reset();
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('passes the active filters to the Excel export mutation', async () => {
    setBenchFilter([2, 3]);
    setProfileFilters({ showSpillAreas: false, blastTolerance: 8 });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'export.excel' }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    const { url, config } = lastGetCallArgs();
    expect(url).toBe('/export/excel');
    const filters = JSON.parse(config.params.filters);
    expect(filters.selectedBenchNumbers).toEqual([2, 3]);
    expect(filters.showSpillAreas).toBe(false);
    expect(filters.blastTolerance).toBe(8);
  });

  it('excludes benches not present in the active bench filter', async () => {
    setBenchFilter([2]);

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'export.word' }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    const { config } = lastGetCallArgs();
    const filters = JSON.parse(config.params.filters);
    expect(filters.selectedBenchNumbers).toEqual([2]);
    expect(filters.selectedBenchNumbers).not.toContain(1);
  });

  it('threads the blast tolerance from the profile filter through the request', async () => {
    setProfileFilters({ blastTolerance: 15, showBlastHoles: true });

    const user = userEvent.setup();
    renderWith(<ExportPanel />, qc);

    await user.click(screen.getByRole('button', { name: 'export.excel' }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    const { config } = lastGetCallArgs();
    const filters = JSON.parse(config.params.filters);
    expect(filters.blastTolerance).toBe(15);
    expect(filters.showBlastHoles).toBe(true);
  });

  it('renders the filter summary with the active bench count', () => {
    setBenchFilter([1, 2, 3]);

    renderWith(<ExportPanel />, qc);

    expect(screen.getByTestId('export-filter-summary')).toBeInTheDocument();
    expect(screen.getByTestId('export-filter-bench-count')).toHaveTextContent('3');
  });
});
