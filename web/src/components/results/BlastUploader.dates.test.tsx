import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastUploader } from './BlastUploader';
import { useSession } from '../../stores/session';

const mockMutateAsync = vi.fn();

vi.mock('../../api/hooks', () => ({
  useUploadBlastCsv: vi.fn(),
  useBlastSessionSummary: vi.fn(),
  extractBlastErrorDiagnostics: () => null,
}));

vi.mock('../../api/client', () => ({
  getSessionId: vi.fn(),
}));

const { mockPreview } = vi.hoisted(() => ({ mockPreview: vi.fn() }));
vi.mock('../../api/blastImport', () => ({ previewBlastImport: (...args: unknown[]) => mockPreview(...args) }));

const { useUploadBlastCsv, useBlastSessionSummary } = await import('../../api/hooks');
const { getSessionId } = await import('../../api/client');

const HEADERS = ['Inclinacion_real', 'Azimuth_real', 'X', 'Y', 'Z_collar', 'longitud_real', 'Burden', 'Fecha tronadura '];

function previewResponse(overrides: Record<string, unknown> = {}) {
  return {
    file_type: 'csv', encoding: 'utf-8', sheets: [], sheet_name: null,
    headers: HEADERS,
    preview: [{ Inclinacion_real: 45, Azimuth_real: 90, X: 1, Y: 2, Z_collar: 100, longitud_real: 10, Burden: 3, 'Fecha tronadura ': '04/05/2026' }],
    suggested_mapping: { Incl: 'Inclinacion_real', Az: 'Azimuth_real', X: 'X', Y: 'Y', Z_collar: 'Z_collar', Len: 'longitud_real' },
    confidence: { Incl: { kind: 'exact', score: 1 }, Az: { kind: 'exact', score: 1 }, Len: { kind: 'fuzzy', score: 0.9 } },
    missing_required: [],
    ...overrides,
  };
}

function mockUpload(overrides: Record<string, unknown> = {}) {
  vi.mocked(useUploadBlastCsv).mockReturnValue({
    mutateAsync: mockMutateAsync, isPending: false, isError: false, isSuccess: false, data: undefined, error: null, ...overrides,
  } as unknown as ReturnType<typeof useUploadBlastCsv>);
}

function pickCsv(name = 'pozos.csv') {
  fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['data'], name, { type: 'text/csv' })] } });
}

function pickWorkbook(name = 'pozos.xlsx') {
  fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['wb'], name)] } });
}

function setField(testId: string, value: string) {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

function completeGeometry() {
  setField('incl-convention', 'FROM_VERTICAL');
  setField('incl-sign', 'ABSOLUTE_VALUE');
  setField('incl-unit', 'DEGREES');
  setField('az-convention', 'CLOCKWISE_FROM_NORTH');
  setField('az-unit', 'DEGREES');
}

async function readyToSubmit() {
  completeGeometry();
  fireEvent.click(screen.getByTestId('mapping-confirmed'));
  fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
  fireEvent.click(screen.getByTestId('geometry-confirmed'));
}

describe('<BlastUploader /> date import controls', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockPreview.mockReset();
    mockPreview.mockResolvedValue(previewResponse());
    vi.mocked(getSessionId).mockReturnValue('sess-date');
    useSession.setState({ demoMode: false, demoData: null, designMeshId: null, topoMeshId: null });
    mockUpload();
    vi.mocked(useBlastSessionSummary).mockReturnValue({ data: undefined, isLoading: false, error: null } as unknown as ReturnType<typeof useBlastSessionSummary>);
  });

  it('renders separate optional date source and format controls empty by default', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    expect(screen.getByTestId('date-source-column')).toHaveValue('');
    expect(screen.getByTestId('date-format')).toHaveValue('');
    expect(screen.getByTestId('date-source-column').querySelectorAll('option')).toHaveLength(HEADERS.length + 1);
    expect(screen.getByTestId('date-source-help').textContent).toContain('fecha_tronadura');
  });

  it('does not send date params when no date source is selected', async () => {
    mockUpload({ mutateAsync: mockMutateAsync.mockResolvedValue({}) });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    await readyToSubmit();
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const geometry = mockMutateAsync.mock.calls[0][0].geometry;
    expect(geometry).not.toHaveProperty('date_source_column');
    expect(geometry).not.toHaveProperty('date_format');
  });

  it('blocks submit when a date source is selected without a declared format', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    await readyToSubmit();
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
    setField('date-source-column', 'Fecha tronadura ');
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    expect(screen.getByTestId('date-format-required')).toBeInTheDocument();
  });

  it('sends the exact date source header and declared format in geometry', async () => {
    mockUpload({ mutateAsync: mockMutateAsync.mockResolvedValue({}) });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    setField('date-source-column', 'Fecha tronadura ');
    setField('date-format', 'DMY');
    await readyToSubmit();
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const geometry = mockMutateAsync.mock.calls[0][0].geometry;
    expect(geometry.date_source_column).toBe('Fecha tronadura ');
    expect(geometry.date_format).toBe('DMY');
    expect(geometry.column_map).not.toHaveProperty('date_source_column');
  });

  it('blocks a date source that duplicates a canonical column_map assignment', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    await readyToSubmit();
    setField('date-source-column', 'X');
    setField('date-format', 'ISO');
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    expect(screen.getByTestId('date-column-conflict')).toBeInTheDocument();
  });

  it('invalidates mapping and geometry confirmation when the date source changes', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    await readyToSubmit();
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
    setField('date-format', 'MDY');
    expect(screen.getByTestId('mapping-confirmed')).not.toBeChecked();
    expect(screen.getByTestId('geometry-confirmed')).not.toBeChecked();
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
  });

  it('resets date controls when the file changes', async () => {
    render(<BlastUploader />);
    pickCsv('a.csv');
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    setField('date-source-column', 'Fecha tronadura ');
    setField('date-format', 'ISO');
    pickCsv('b.csv');
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    expect(screen.getByTestId('date-source-column')).toHaveValue('');
    expect(screen.getByTestId('date-format')).toHaveValue('');
  });

  it('resets date controls when the worksheet changes', async () => {
    mockPreview.mockResolvedValue(previewResponse({ file_type: 'xlsx', sheets: ['Datos', 'Revisión'], sheet_name: 'Datos' }));
    render(<BlastUploader />);
    pickWorkbook();
    await waitFor(() => expect(screen.getByTestId('blast-sheet-select')).toBeInTheDocument());
    setField('date-source-column', 'Fecha tronadura ');
    setField('date-format', 'DMY');
    mockPreview.mockResolvedValueOnce(previewResponse({ file_type: 'xlsx', sheets: ['Datos', 'Revisión'], sheet_name: 'Revisión' }));
    setField('blast-sheet-select', 'Revisión');
    await waitFor(() => expect(mockPreview).toHaveBeenLastCalledWith(expect.any(File), 'Revisión'));
    await waitFor(() => expect(screen.getByTestId('date-source-column')).toHaveValue(''));
    expect(screen.getByTestId('date-format')).toHaveValue('');
  });

  it('disables date controls while an import is pending', async () => {
    mockUpload({ isPending: true });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    expect(screen.getByTestId('date-source-column')).toBeDisabled();
    expect(screen.getByTestId('date-format')).toBeDisabled();
  });

  it('ignores date edits while an import is pending', async () => {
    mockUpload({ isPending: true });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    await act(async () => { fireEvent.change(screen.getByTestId('date-format'), { target: { value: 'DMY' } }); });
    expect(screen.getByTestId('date-format')).toHaveValue('');
  });
});
