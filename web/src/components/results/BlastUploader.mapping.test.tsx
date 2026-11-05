import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastUploader } from './BlastUploader';
import { useSession } from '../../stores/session';
import type { BlastGeometryForm } from '../../api/hooks';

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

const HEADERS = ['Inclinacion_real', 'Azimuth_real', 'X', 'Y', 'Z_collar', 'longitud_real', 'Burden'];

function previewResponse(overrides: Record<string, unknown> = {}) {
  return {
    file_type: 'csv', encoding: 'utf-8', sheets: [], sheet_name: null,
    headers: HEADERS,
    preview: [{ Inclinacion_real: 45, Azimuth_real: 90, X: 1, Y: 2, Z_collar: 100, longitud_real: 10, Burden: 3 }],
    suggested_mapping: { Incl: 'Inclinacion_real', Az: 'Azimuth_real', X: 'X', Y: 'Y', Z_collar: 'Z_collar', Len: 'longitud_real' },
    confidence: { Incl: { kind: 'exact', score: 1 }, Az: { kind: 'exact', score: 1 }, Len: { kind: 'fuzzy', score: 0.9090909090909091 } },
    missing_required: [],
    ...overrides,
  };
}

function mockUpload(overrides: Record<string, unknown> = {}) {
  vi.mocked(useUploadBlastCsv).mockReturnValue({
    mutateAsync: mockMutateAsync, isPending: false, isError: false, isSuccess: false, data: undefined, error: null, ...overrides,
  } as unknown as ReturnType<typeof useUploadBlastCsv>);
}

function mockBlastSummary() {
  vi.mocked(useBlastSessionSummary).mockReturnValue({ data: undefined, isLoading: false, error: null } as unknown as ReturnType<typeof useBlastSessionSummary>);
}

function pickCsv(name = 'pozos.csv') {
  fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['data'], name, { type: 'text/csv' })] } });
}

function pickWorkbook(name = 'pozos.xlsx') {
  fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['wb'], name)] } });
}

function setContract(testId: string, value: string) {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

function completeGeometry() {
  setContract('incl-convention', 'FROM_VERTICAL');
  setContract('incl-sign', 'ABSOLUTE_VALUE');
  setContract('incl-unit', 'DEGREES');
  setContract('az-convention', 'CLOCKWISE_FROM_NORTH');
  setContract('az-unit', 'DEGREES');
}

describe('<BlastUploader /> mapping contract', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockPreview.mockReset();
    mockPreview.mockResolvedValue(previewResponse());
    vi.mocked(getSessionId).mockReturnValue('sess-map');
    useSession.setState({ demoMode: false, demoData: null, designMeshId: null, topoMeshId: null });
    mockUpload();
    mockBlastSummary();
  });

  it('shows suggested Incl and Az sources in the geometry selectors without confirming them', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    expect(screen.getByTestId('map-Incl')).toHaveValue('Inclinacion_real');
    expect(screen.getByTestId('incl-source-column')).toHaveValue('Inclinacion_real');
    expect(screen.getByTestId('az-source-column')).toHaveValue('Azimuth_real');
    expect(screen.getByTestId('mapping-confirmed')).not.toBeChecked();
    expect(screen.getByTestId('geometry-confirmed')).not.toBeChecked();
  });

  it('keeps the two Incl selectors representing the same source in both directions', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    setContract('incl-source-column', 'longitud_real');
    expect(screen.getByTestId('map-Incl')).toHaveValue('longitud_real');
    fireEvent.change(screen.getByTestId('map-Incl'), { target: { value: 'Azimuth_real' } });
    expect(screen.getByTestId('incl-source-column')).toHaveValue('Azimuth_real');
  });

  it('sends the mapped Incl and Az sources in geometry without a second selection', async () => {
    const mutate = vi.fn().mockResolvedValue({});
    mockUpload({ mutateAsync: mutate });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    const call = mutate.mock.calls[0][0];
    expect(call.geometry.inclination_source_column).toBe('Inclinacion_real');
    expect(call.geometry.azimuth_source_column).toBe('Azimuth_real');
    expect(call.geometry.column_map.Incl).toBe('Inclinacion_real');
  });

  it('invalidates the geometry confirmation when the worksheet changes', async () => {
    mockPreview.mockResolvedValue(previewResponse({ file_type: 'xlsx', sheets: ['Datos', 'Revisión'], sheet_name: 'Datos' }));
    render(<BlastUploader />);
    pickWorkbook();
    await waitFor(() => expect(screen.getByTestId('blast-sheet-select')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
    mockPreview.mockResolvedValueOnce(previewResponse({ file_type: 'xlsx', sheets: ['Datos', 'Revisión'], sheet_name: 'Revisión' }));
    setContract('blast-sheet-select', 'Revisión');
    await waitFor(() => expect(mockPreview).toHaveBeenLastCalledWith(expect.any(File), 'Revisión'));
    await waitFor(() => expect(screen.getByTestId('mapping-confirmed')).not.toBeChecked());
    expect(screen.getByTestId('geometry-confirmed')).not.toBeChecked();
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
  });

  it('does not let a stale preview error from a previous file affect the current file', async () => {
    let rejectOld!: (error: Error) => void;
    mockPreview.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }))
      .mockResolvedValueOnce(previewResponse());
    render(<BlastUploader />);
    pickCsv('viejo.csv');
    pickCsv('nuevo.csv');
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    await act(async () => { rejectOld(new Error('Error tardío')); });
    expect(screen.queryByText('Error tardío')).not.toBeInTheDocument();
    expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument();
    expect(screen.getByTestId('map-Incl')).toHaveValue('Inclinacion_real');
  });

  it('does not let a late worksheet result replace the current file mapping', async () => {
    let resolveLateSheet!: (value: unknown) => void;
    mockPreview.mockResolvedValueOnce(previewResponse({ file_type: 'xlsx', sheets: ['Datos', 'Revisión'], sheet_name: 'Datos' }));
    render(<BlastUploader />);
    pickWorkbook('a.xlsx');
    await waitFor(() => expect(screen.getByTestId('blast-sheet-select')).toBeInTheDocument());
    mockPreview.mockImplementationOnce(() => new Promise((resolve) => { resolveLateSheet = resolve; }));
    setContract('blast-sheet-select', 'Revisión');
    mockPreview.mockResolvedValueOnce(previewResponse({ file_type: 'xlsx', headers: ['NuevaX'], sheets: ['Otra'], sheet_name: 'Otra', suggested_mapping: {} }));
    pickWorkbook('b.xlsx');
    await waitFor(() => expect(screen.getByTestId('blast-sheet-select')).toHaveValue('Otra'));
    await act(async () => { resolveLateSheet(previewResponse({ file_type: 'xlsx', headers: ['ViejaX'], sheets: ['Datos', 'Revisión'], sheet_name: 'Revisión', suggested_mapping: { X: 'ViejaX' } })); });
    expect(screen.getByTestId('blast-sheet-select')).toHaveValue('Otra');
    expect(screen.getByTestId('map-X').textContent).toContain('NuevaX');
    expect(screen.getByTestId('map-X').textContent).not.toContain('ViejaX');
    expect(screen.getByTestId('map-X')).toHaveValue('');
  });

  it('blocks upload when a sheet change preview fails', async () => {
    mockPreview.mockResolvedValueOnce(previewResponse({ file_type: 'xlsx', sheets: ['Datos', 'Revisión'], sheet_name: 'Datos' }));
    render(<BlastUploader />);
    pickWorkbook();
    await waitFor(() => expect(screen.getByTestId('blast-sheet-select')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    mockPreview.mockRejectedValueOnce(new Error('Hoja ilegible'));
    setContract('blast-sheet-select', 'Revisión');
    await waitFor(() => expect(screen.getByText('No se pudo leer la vista previa del archivo.')).toBeInTheDocument());
    expect(screen.queryByTestId('mapping-confirmed')).not.toBeInTheDocument();
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('does not require optional fields and blocks an optional source that is not in the file', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
  });

  it('blocks a suggested optional source that does not exist in the header', async () => {
    mockPreview.mockResolvedValue(previewResponse({ suggested_mapping: { Incl: 'Inclinacion_real', Az: 'Azimuth_real', X: 'X', Y: 'Y', Z_collar: 'Z_collar', Len: 'longitud_real', Burden: 'Columna_fantasma' } }));
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByText(/Columna_fantasma/, { selector: '[role="alert"]' })).toBeInTheDocument();
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
  });

  it('does not carry the previous file Incl source into the next file', async () => {
    render(<BlastUploader />);
    pickCsv('uno.csv');
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    mockPreview.mockResolvedValueOnce(previewResponse({ headers: ['Otra_inclinacion', 'Azimuth_real', 'X', 'Y', 'Z_collar', 'longitud_real'], suggested_mapping: { X: 'X', Y: 'Y', Z_collar: 'Z_collar', Len: 'longitud_real', Az: 'Azimuth_real' } }));
    pickCsv('dos.csv');
    await waitFor(() => expect(screen.getByTestId('map-Az')).toHaveValue('Azimuth_real'));
    expect(screen.getByTestId('incl-source-column')).toHaveValue('');
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
  });

  it('shows the translated confidence kind and a 0..1 score as percentage', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    expect(screen.getAllByText('Sugerencia: coincidencia exacta (100%)', { exact: false, selector: 'span' })).not.toHaveLength(0);
    expect(screen.getByText('Sugerencia: coincidencia aproximada (91%)', { exact: false, selector: 'span' })).toBeInTheDocument();
    expect(screen.queryByText(/\b(exact|fuzzy|unmatched)\b/)).toBeNull();
  });

  it('renders English labels for the mapping messages in English', async () => {
    await i18n.changeLanguage('en');
    try {
      render(<BlastUploader />);
      pickCsv();
      await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
      expect(screen.getByText('Suggestion: approximate match (91%)', { exact: false })).toBeInTheDocument();
      fireEvent.change(screen.getByTestId('map-Y'), { target: { value: 'X' } });
      expect(screen.getByText('Each file column must be assigned to only one field.')).toBeInTheDocument();
      expect(screen.queryByText(/Sugerencia|Asigne|Cada columna|Seleccione/)).toBeNull();
    } finally {
      await i18n.changeLanguage('es');
    }
  });

  it('does not mark the collar elevation column as required when the collar source is the design surface', async () => {
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    setContract('collar-elevation-source', 'design_surface');
    fireEvent.change(screen.getByTestId('map-Z_collar'), { target: { value: '' } });
    expect(screen.queryByText(/Asigne todos los campos obligatorios: .*Z_collar/)).toBeNull();
    const label = screen.getByTestId('map-Z_collar').closest('label');
    expect(label?.textContent).not.toContain('*');
  });

  it('sends header source columns exactly as mapped, including trailing spaces', async () => {
    const spaced = 'Inclinacion_real ';
    mockPreview.mockResolvedValue(previewResponse({ headers: [spaced, 'Azimuth_real', 'X', 'Y', 'Z_collar', 'longitud_real'], preview: [], suggested_mapping: { Incl: spaced, Az: 'Azimuth_real', X: 'X', Y: 'Y', Z_collar: 'Z_collar', Len: 'longitud_real' } }));
    const mutate = vi.fn().mockResolvedValue({});
    mockUpload({ mutateAsync: mutate });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    const call = mutate.mock.calls[0][0] as { geometry: BlastGeometryForm & { column_map: Record<string, string> } };
    expect(call.geometry.column_map.Incl).toBe(spaced);
    expect(call.geometry.inclination_source_column).toBe(spaced);
    expect(call.geometry.inclination_source_column).toBe(call.geometry.column_map.Incl);
  });

  it('locks every configuration control while the upload is pending and keeps the submitted config', async () => {
    const mutate = vi.fn((_payload: { geometry: BlastGeometryForm }) => new Promise(() => undefined));
    mockUpload({ mutateAsync: mutate });
    const { rerender } = render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    completeGeometry();
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    mockUpload({ mutateAsync: mutate, isPending: true });
    rerender(<BlastUploader />);
    for (const id of ['map-X', 'map-Y', 'map-Burden', 'incl-source-column', 'az-source-column', 'incl-convention', 'incl-sign', 'incl-unit', 'az-unit', 'az-convention', 'collar-elevation-source', 'bench-height', 'mapping-confirmed', 'geometry-confirmed', 'blast-sheet-select']) {
      const el = screen.queryByTestId(id);
      if (el) expect(el).toBeDisabled();
    }
    const before = { x: (screen.getByTestId('map-X') as HTMLSelectElement).value, incl: (screen.getByTestId('incl-convention') as HTMLSelectElement).value };
    fireEvent.change(screen.getByTestId('map-X'), { target: { value: 'Burden' } });
    fireEvent.change(screen.getByTestId('incl-convention'), { target: { value: 'DIP_FROM_HORIZONTAL' } });
    fireEvent.click(screen.getByTestId('mapping-confirmed'));
    expect(screen.getByTestId('map-X')).toHaveValue(before.x);
    expect(screen.getByTestId('incl-convention')).toHaveValue(before.incl);
    expect(screen.getByTestId('mapping-confirmed')).toBeChecked();
    expect(mutate).toHaveBeenCalledTimes(1);
    const submitted = (mutate.mock.calls[0] as unknown as [{ geometry: BlastGeometryForm & { column_map: Record<string, string> } }])[0].geometry;
    expect(submitted.inclination_convention).toBe('FROM_VERTICAL');
    expect(submitted.column_map.X).toBe('X');
  });

  it('clears a previous successful upload result when the mapping changes', async () => {
    const reset = vi.fn();
    mockUpload({ isSuccess: true, data: { n_holes: 1, n_rows_skipped: 0 }, reset });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    reset.mockClear();
    fireEvent.change(screen.getByTestId('map-X'), { target: { value: 'Y' } });
    expect(reset).toHaveBeenCalled();
  });

  it('clears a previous failed upload result when the mapping changes', async () => {
    const reset = vi.fn();
    mockUpload({ isError: true, error: new Error('boom'), reset });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    reset.mockClear();
    fireEvent.change(screen.getByTestId('map-Y'), { target: { value: 'X' } });
    expect(reset).toHaveBeenCalled();
  });

  it('does not reset the upload mutation while it is pending', async () => {
    const reset = vi.fn();
    mockUpload({ isPending: true, reset });
    render(<BlastUploader />);
    pickCsv();
    await waitFor(() => expect(screen.getByTestId('blast-import-mapper')).toBeInTheDocument());
    reset.mockClear();
    fireEvent.change(screen.getByTestId('map-X'), { target: { value: 'Y' } });
    expect(reset).not.toHaveBeenCalled();
  });
});
