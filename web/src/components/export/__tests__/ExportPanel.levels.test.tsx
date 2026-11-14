import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { type ReactElement } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
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
import { useSession } from '../../../stores/session';

const testI18n = i18n.createInstance();
void testI18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  resources: { es: { translation: es }, en: { translation: en } },
});

interface LevelPayload {
  label: string;
  elevation: number;
  min_level: number;
  max_level: number;
  n_sections: number;
  n_rows: number;
}

interface LevelsPayload {
  sectors: Array<{ sector: string; levels: LevelPayload[] }>;
  warnings: string[];
}

function level(label: string, min: number, max: number, nSections = 96): LevelPayload {
  return {
    label,
    elevation: Number(label),
    min_level: min,
    max_level: max,
    n_sections: nSections,
    n_rows: nSections,
  };
}

const SINGLE_SECTOR: LevelsPayload = {
  sectors: [
    {
      sector: '',
      levels: [level('3125', 3125, 3125), level('3110', 3110, 3110), level('3104', 3095, 3104)],
    },
  ],
  warnings: [],
};

const TWO_SECTORS: LevelsPayload = {
  sectors: [
    { sector: 'A', levels: [level('3125', 3125, 3125, 40), level('3110', 3110, 3110, 40)] },
    { sector: '', levels: [level('3104', 3095, 3104, 12)] },
  ],
  warnings: [],
};

type ExportHeaders = Record<string, string>;

function routeGet(levels: LevelsPayload | Error, exportHeaders: ExportHeaders = {}): void {
  mockGet.mockImplementation(async (url: string) => {
    if (url === '/export/levels') {
      if (levels instanceof Error) throw levels;
      return { data: levels };
    }
    return { data: new Blob(['x']), headers: exportHeaders };
  });
}

function exportCalls(): Array<{ url: string; config: { params?: Record<string, string> } }> {
  return mockGet.mock.calls
    .filter((call) => call[0] !== '/export/levels')
    .map((call) => ({ url: call[0] as string, config: call[1] as { params?: Record<string, string> } }));
}

function lastExportFilters(): Record<string, unknown> {
  const calls = exportCalls();
  const last = calls[calls.length - 1];
  if (!last) throw new Error('no export request was sent');
  const raw = last.config.params?.filters;
  if (!raw) throw new Error(`export request to ${last.url} carried no filters`);
  return JSON.parse(raw) as Record<string, unknown>;
}

function renderPanel(qc: QueryClient, ui: ReactElement = <ExportPanel />) {
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </I18nextProvider>,
  );
}

describe('ExportPanel — nominal level selector per sector', () => {
  let qc: QueryClient;

  beforeEach(() => {
    void testI18n.changeLanguage('es');
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.localStorage.clear();
    useSession.getState().reset();
  });

  afterEach(() => {
    useSession.getState().reset();
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders one selector per sector from /export/levels', async () => {
    routeGet(TWO_SECTORS);
    renderPanel(qc);

    const groups = await screen.findAllByTestId('export-level-sector');
    expect(groups).toHaveLength(2);
    expect(groups[0]).toHaveTextContent('Sector A');
    expect(within(groups[0]).getAllByRole('checkbox')).toHaveLength(2);
    expect(groups[1]).toHaveTextContent('Sin sector');
    expect(within(groups[1]).getAllByRole('checkbox')).toHaveLength(1);
    expect(mockGet.mock.calls.filter((call) => call[0] === '/export/levels')).toHaveLength(1);
  });

  it('shows the section count and the range only for levels grouping several values', async () => {
    routeGet(SINGLE_SECTOR);
    renderPanel(qc);

    expect(await screen.findByRole('checkbox', { name: '3104 (3095–3104 · 96 secc.)' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '3110 (96 secc.)' })).toBeInTheDocument();
  });

  it('renders a single selector without sector caption when there is one sector', async () => {
    routeGet(SINGLE_SECTOR);
    renderPanel(qc);

    const groups = await screen.findAllByTestId('export-level-sector');
    expect(groups).toHaveLength(1);
    expect(within(groups[0]).getAllByRole('checkbox')).toHaveLength(3);
    expect(screen.queryByTestId('export-level-sector-caption')).not.toBeInTheDocument();
    expect(groups[0]).not.toHaveTextContent('Sin sector');
  });

  it('starts with no level selected and omits levelsBySector from the request', async () => {
    routeGet(SINGLE_SECTOR);
    const user = userEvent.setup();
    renderPanel(qc);

    for (const box of await screen.findAllByRole('checkbox')) expect(box).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Exportar Excel' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(lastExportFilters()).not.toHaveProperty('levelsBySector');
  });

  it('sends the selected level as levelsBySector in the export request', async () => {
    routeGet(SINGLE_SECTOR);
    const user = userEvent.setup();
    renderPanel(qc);

    await user.click(await screen.findByRole('checkbox', { name: '3110 (96 secc.)' }));
    await user.click(screen.getByRole('button', { name: 'Exportar Excel' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(exportCalls()[0].url).toBe('/export/excel');
    expect(lastExportFilters().levelsBySector).toEqual({ '': ['3110'] });
  });

  it('supports multi-select per sector and omits sectors without selection', async () => {
    routeGet(TWO_SECTORS);
    const user = userEvent.setup();
    renderPanel(qc);

    const groups = await screen.findAllByTestId('export-level-sector');
    const boxes = within(groups[0]).getAllByRole('checkbox');
    await user.click(boxes[0]);
    await user.click(boxes[1]);
    await user.click(within(groups[1]).getByRole('checkbox'));
    await user.click(within(groups[1]).getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'PDF Ejecutivo' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(lastExportFilters().levelsBySector).toEqual({ A: ['3125', '3110'] });
  });

  it('preselects the nominal label matching the dashboard level filter', async () => {
    useSession.setState({ filters: { sector: [], section: [], level: ['3110'], bench: [] } });
    routeGet(SINGLE_SECTOR);
    const user = userEvent.setup();
    renderPanel(qc);

    expect(await screen.findByRole('checkbox', { name: '3110 (96 secc.)' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '3125 (96 secc.)' })).not.toBeChecked();

    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));
    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(lastExportFilters().levelsBySector).toEqual({ '': ['3110'] });
  });

  it('maps a raw dashboard level onto the nominal level whose range contains it', async () => {
    useSession.setState({ filters: { sector: [], section: [], level: ['3098.5'], bench: [] } });
    routeGet(SINGLE_SECTOR);
    renderPanel(qc);

    expect(await screen.findByRole('checkbox', { name: '3104 (3095–3104 · 96 secc.)' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '3110 (96 secc.)' })).not.toBeChecked();
  });

  it('leaves the selection empty when the dashboard level filter matches no nominal level', async () => {
    useSession.setState({ filters: { sector: [], section: [], level: ['L1'], bench: [] } });
    routeGet(SINGLE_SECTOR);
    renderPanel(qc);

    for (const box of await screen.findAllByRole('checkbox')) expect(box).not.toBeChecked();
  });

  it('lists the levels per sector in the applied-filters note', async () => {
    routeGet(TWO_SECTORS, {
      'x-export-filters-applied': JSON.stringify({
        sectors: [],
        sections: [],
        levels: [],
        levels_by_sector: { A: ['3125', '3110'], '': ['3104'] },
        selected_bench_numbers: [],
      }),
    });
    const user = userEvent.setup();
    renderPanel(qc);

    await screen.findAllByTestId('export-level-sector');
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    const note = await screen.findByTestId('export-applied-filters');
    expect(note).toHaveTextContent('Filtros aplicados: Cotas por sector: Sector A: 3125, 3110; Sin sector: 3104');
  });

  it('shows «todas las cotas» for a sector applied with an empty selection', async () => {
    routeGet(TWO_SECTORS, {
      'x-export-filters-applied': JSON.stringify({
        sectors: [],
        sections: [],
        levels: ['3125'],
        levels_by_sector: { A: [], '': ['3104'] },
        selected_bench_numbers: [],
      }),
    });
    const user = userEvent.setup();
    renderPanel(qc);

    await screen.findAllByTestId('export-level-sector');
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    const note = await screen.findByTestId('export-applied-filters');
    expect(note).toHaveTextContent('Cotas por sector: Sector A: todas las cotas; Sin sector: 3104');
    expect(note).not.toHaveTextContent('Niveles:');
  });

  it('sends an empty list for a sector cleared while the dashboard level filter is active', async () => {
    useSession.setState({ filters: { sector: [], section: [], level: ['3110'], bench: [] } });
    routeGet(SINGLE_SECTOR);
    const user = userEvent.setup();
    renderPanel(qc);

    const box = await screen.findByRole('checkbox', { name: '3110 (96 secc.)' });
    expect(box).toBeChecked();
    await user.click(box);
    expect(box).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(lastExportFilters().levelsBySector).toEqual({ '': [] });
  });

  it('sends every sector when the dashboard filter is active', async () => {
    useSession.setState({ filters: { sector: [], section: [], level: ['3125'], bench: [] } });
    routeGet(TWO_SECTORS);
    const user = userEvent.setup();
    renderPanel(qc);

    const groups = await screen.findAllByTestId('export-level-sector');
    const boxes = within(groups[0]).getAllByRole('checkbox');
    expect(boxes[0]).toBeChecked();
    await user.click(boxes[0]);
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(lastExportFilters().levelsBySector).toEqual({ A: [], '': [] });
  });

  it('omits a cleared sector when the dashboard level filter is not active', async () => {
    routeGet(SINGLE_SECTOR);
    const user = userEvent.setup();
    renderPanel(qc);

    const box = await screen.findByRole('checkbox', { name: '3110 (96 secc.)' });
    await user.click(box);
    await user.click(box);
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(lastExportFilters()).not.toHaveProperty('levelsBySector');
  });

  it('translates the all-levels note to English', async () => {
    void testI18n.changeLanguage('en');
    routeGet(SINGLE_SECTOR, {
      'x-export-filters-applied': JSON.stringify({ levels_by_sector: { A: [] } }),
    });
    const user = userEvent.setup();
    renderPanel(qc);

    await screen.findAllByTestId('export-level-sector');
    await user.click(screen.getByRole('button', { name: 'Export Word' }));

    const note = await screen.findByTestId('export-applied-filters');
    expect(note).toHaveTextContent('Sector A: all levels');
  });

  it('shows the API warnings once below the selector', async () => {
    routeGet({ ...TWO_SECTORS, warnings: ['Secciones con cotas ambiguas: S-22, S-25'] });
    renderPanel(qc);

    const warnings = await screen.findByTestId('export-level-warnings');
    expect(warnings).toHaveTextContent('Secciones con cotas ambiguas: S-22, S-25');
    expect(screen.getAllByText('Secciones con cotas ambiguas: S-22, S-25')).toHaveLength(1);
  });

  it('hides the selector when /export/levels fails and keeps the export callable', async () => {
    routeGet(new Error('Request failed with status code 400'));
    const user = userEvent.setup();
    renderPanel(qc);

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/export/levels'));
    await waitFor(() => expect(screen.queryByTestId('export-level-loading')).not.toBeInTheDocument());
    expect(screen.queryByTestId('export-level-selector')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Exportar Excel' }));
    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(exportCalls()[0].url).toBe('/export/excel');
    expect(lastExportFilters()).not.toHaveProperty('levelsBySector');
  });

  it('sends the filters with the images export', async () => {
    useSession.setState({ filters: { sector: ['A'], section: [], level: [], bench: [2] } });
    routeGet(TWO_SECTORS);
    const user = userEvent.setup();
    renderPanel(qc);

    const groups = await screen.findAllByTestId('export-level-sector');
    await user.click(within(groups[0]).getAllByRole('checkbox')[1]);
    await user.click(screen.getByRole('button', { name: 'Exportar Imágenes' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(exportCalls()[0].url).toBe('/export/images');
    const filters = lastExportFilters();
    expect(filters.sector).toEqual(['A']);
    expect(filters.selectedBenchNumbers).toEqual([2]);
    expect(filters.levelsBySector).toEqual({ A: ['3110'] });
  });

  it('keeps the DXF export without filters', async () => {
    routeGet(SINGLE_SECTOR);
    const user = userEvent.setup();
    renderPanel(qc);

    await screen.findAllByTestId('export-level-sector');
    await user.click(screen.getByRole('button', { name: 'Exportar DXF' }));

    await waitFor(() => expect(exportCalls()).toHaveLength(1));
    expect(exportCalls()[0].url).toBe('/export/dxf');
    expect(exportCalls()[0].config.params).toBeUndefined();
  });

  it('translates the selector captions to English', async () => {
    routeGet(TWO_SECTORS);
    renderPanel(qc);

    const groups = await screen.findAllByTestId('export-level-sector');
    await testI18n.changeLanguage('en');

    await waitFor(() => expect(groups[1]).toHaveTextContent('No sector'));
    expect(within(groups[1]).getByRole('checkbox', { name: '3104 (3095–3104 · 12 sect.)' })).toBeInTheDocument();
  });
  it('blocks report exports while levels load but leaves DXF available', async () => {
    mockGet.mockImplementation((url: string) => url === '/export/levels' ? new Promise(() => {}) : Promise.resolve({ data: new Blob(['x']) }));
    renderPanel(qc);
    await screen.findByTestId('export-level-loading');
    for (const name of ['Exportar Excel', 'Exportar Word', 'PDF Ejecutivo', 'Exportar Imágenes']) expect(screen.getByRole('button', { name })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Exportar DXF' })).toBeEnabled();
  });

  it('explains a levels error and retries successfully', async () => {
    routeGet(new Error('failed'));
    renderPanel(qc);
    expect(await screen.findByText(/sin cotas por sector/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Exportar Word' })).toBeEnabled();
    routeGet(SINGLE_SECTOR);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('checkbox', { name: '3110 (96 secc.)' })).toBeInTheDocument();
  });

  it('clears the applied note on level selection and export failure', async () => {
    routeGet(SINGLE_SECTOR, { 'x-export-filters-applied': JSON.stringify({ levels: ['3110'] }) });
    const user = userEvent.setup();
    renderPanel(qc);
    const box = await screen.findByRole('checkbox', { name: '3110 (96 secc.)' });
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));
    await screen.findByTestId('export-applied-filters');
    await user.click(box);
    expect(screen.queryByTestId('export-applied-filters')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Exportar Word' }));
    await screen.findByTestId('export-applied-filters');
    mockGet.mockImplementation(async (url: string) => { if (url === '/export/levels') return { data: SINGLE_SECTOR }; throw new Error('failed'); });
    await user.click(screen.getByRole('button', { name: 'PDF Ejecutivo' }));
    await screen.findByRole('alert');
    expect(screen.queryByTestId('export-applied-filters')).not.toBeInTheDocument();
  });

});
