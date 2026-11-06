import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastUploader } from './BlastUploader';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import type { BlastUploadResponse } from '../../api/types';

// ─── Mocks ─────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock('../../api/hooks', () => ({
  useUploadBlastCsv: vi.fn(),
  useBlastHolesBySession: vi.fn(),
  extractBlastErrorDiagnostics: (error: unknown) => {
    const anyErr = error as { response?: { data?: unknown } };
    return (anyErr?.response?.data ?? null) as Partial<BlastUploadResponse> | null;
  },
}));

vi.mock('../../api/client', () => ({
  getSessionId: vi.fn(),
}));

const { useUploadBlastCsv, useBlastHolesBySession } = await import('../../api/hooks');
const { getSessionId } = await import('../../api/client');

const uploadResponse: BlastUploadResponse = {
  session_id: 'sess-001',
  n_holes: 42,
  n_rows_loaded: 42,
  n_rows_skipped: 3,
  carga_mean: 12.3456,
  descarga_mean: 8.9,
  hardness_distribution: { Blando: 30, Duro: 12 },
  data_warnings: '',
  processing_summary: {},
  accepted_rows: [],
  rejected_rows: [],
  event_warnings: [],
  blocking_errors: [],
  geometry_configuration: {
    geometry_configuration_version: '2.0',
    geometry_user_confirmed: true,
    inclination_source_column: 'Inclinacion_real',
    inclination_convention: 'FROM_VERTICAL',
    inclination_sign_convention: 'ABSOLUTE_VALUE',
    inclination_unit: 'DEGREES',
    inclination_source_rule: '',
    azimuth_source_column: 'Azimuth_real',
    azimuth_convention: 'CLOCKWISE_FROM_NORTH',
    azimuth_unit: 'DEGREES',
  },
  spatial_diagnostics: {},
};

function mockUpload(overrides: Partial<ReturnType<typeof useUploadBlastCsv>> = {}) {
  vi.mocked(useUploadBlastCsv).mockReturnValue({
    mutateAsync: mockMutateAsync,
    isPending: false,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
    ...overrides,
  } as ReturnType<typeof useUploadBlastCsv>);
}

function mockHoles(overrides: Partial<ReturnType<typeof useBlastHolesBySession>> = {}) {
  vi.mocked(useBlastHolesBySession).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof useBlastHolesBySession>);
}

function renderUploader(props: { onUploaded?: (r: BlastUploadResponse) => void } = {}) {
  return render(<BlastUploader onUploaded={props.onUploaded} />);
}

// Helper: select every required field with conscious values so the file
// input becomes enabled. Mirrors the operator's flow: pick one option in
// every dropdown, fill both source columns, then tick confirmation.
function fillCompleteContract() {
  fireEvent.change(screen.getByTestId('collar-elevation-source'), {
    target: { value: 'bench_height' },
  });
  fireEvent.change(screen.getByTestId('incl-source-column'), {
    target: { value: 'Inclinacion_real' },
  });
  fireEvent.change(screen.getByTestId('az-source-column'), {
    target: { value: 'Azimuth_real' },
  });
  fireEvent.change(screen.getByTestId('incl-convention'), {
    target: { value: 'FROM_VERTICAL' },
  });
  fireEvent.change(screen.getByTestId('incl-sign'), {
    target: { value: 'ABSOLUTE_VALUE' },
  });
  fireEvent.change(screen.getByTestId('incl-unit'), {
    target: { value: 'DEGREES' },
  });
  fireEvent.change(screen.getByTestId('az-convention'), {
    target: { value: 'CLOCKWISE_FROM_NORTH' },
  });
  fireEvent.change(screen.getByTestId('az-unit'), {
    target: { value: 'DEGREES' },
  });
}

// ─── Tests ─────────────────────────────────────────────────

describe('<BlastUploader />', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getSessionId).mockReturnValue('sess-001');
    useSession.setState({ demoMode: false, demoData: null, designMeshId: null, topoMeshId: null });
  });

  it('explains that blast data is absent and prevents upload for virtual demo meshes', () => {
    useSession.setState({
      demoMode: true,
      designMeshId: DEMO_MESH_IDS.design,
      topoMeshId: DEMO_MESH_IDS.topo,
    });
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-demo-notice')).toHaveTextContent(
      'La demo usa mallas virtuales y no incluye datos de tronadura',
    );
    expect(screen.queryByTestId('blast-file-input')).not.toBeInTheDocument();
    expect(vi.mocked(useBlastHolesBySession)).toHaveBeenCalledWith(null);
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('offers detected CSV headers in native inclination and azimuth dropdowns', async () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), {
      target: { files: [new File(['"ID","Inclinacion real","Azimuth, real"\n1,45,90'], 'pozos.csv', { type: 'text/csv' })] },
    });

    await waitFor(() => {
      expect(screen.getByTestId('incl-source-column').tagName).toBe('SELECT');
      expect(screen.getByTestId('az-source-column').tagName).toBe('SELECT');
      expect(screen.getByTestId('incl-source-column').querySelector('option[value="Inclinacion real"]')).not.toBeNull();
      expect(screen.getByTestId('az-source-column').querySelector('option[value="Azimuth, real"]')).not.toBeNull();
    });
  });

  it('reads a bounded Windows-1252 header with a BOM and preserves selected columns missing from a replacement file', async () => {
    mockUpload();
    mockHoles();
    renderUploader();
    const cp1252Header = new Uint8Array([0xef, 0xbb, 0xbf, ...Array.from('ID,Inclinación,Azimuth_real', (char) => char.charCodeAt(0) > 255 ? 0xed : char.charCodeAt(0))]);
    const firstFile = new File([cp1252Header], 'pozos.csv', { type: 'text/csv' });
    const sliceSpy = vi.spyOn(firstFile, 'slice');
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [firstFile] } });

    await waitFor(() => expect(screen.getByTestId('incl-source-column').querySelector('option[value="Inclinación"]')).not.toBeNull());
    expect(sliceSpy).toHaveBeenCalledWith(0, 64 * 1024);
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinación' } });
    fireEvent.change(screen.getByTestId('az-source-column'), { target: { value: 'Azimuth_real' } });
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinación' } });
    fireEvent.change(screen.getByTestId('az-source-column'), { target: { value: 'Azimuth_real' } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Otra_inclinacion,Otro_azimuth\n1,2'], 'otro.csv', { type: 'text/csv' })] } });

    await waitFor(() => {
      expect((screen.getByTestId('incl-source-column') as HTMLSelectElement).value).toBe('Inclinación');
      expect((screen.getByTestId('az-source-column') as HTMLSelectElement).value).toBe('Azimuth_real');
      expect(screen.getByText(/«Inclinación» no está en el encabezado/i)).toBeInTheDocument();
      expect(screen.getByText(/«Azimuth_real» no está en el encabezado/i)).toBeInTheDocument();
      expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    });
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Otra_inclinacion' } });
    fireEvent.change(screen.getByTestId('az-source-column'), { target: { value: 'Otro_azimuth' } });
    expect(screen.queryByText(/no está en el encabezado/i)).toBeNull();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
  });

  it('blocks the incompatible vertical inclination and negative-downward sign combination', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-sign'), { target: { value: 'NEGATIVE_IS_DOWNWARD_DIP' } });
    expect(screen.getByText(/no es compatible/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
  });

  it('shows event warning messages returned with a successful upload', () => {
    mockUpload({ isSuccess: true, data: { ...uploadResponse, event_warnings: [{ warning_code: 'INCLINATION_ALL_ZERO', message: 'La columna de inclinación declarada contiene cero en todas las filas. Verifique el dato y la convención confirmada; no se asumió una orientación.' }] } });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('event-warnings')).toHaveTextContent('1');
    expect(screen.getByTestId('event-warning-messages')).toHaveTextContent('La columna de inclinación declarada contiene cero en todas las filas.');
  });

  it('blocks mixed sessions and skips the session-scoped holes query when either mesh is virtual', () => {
    useSession.setState({ demoMode: false, designMeshId: 'real-design', topoMeshId: DEMO_MESH_IDS.topo });
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-demo-notice')).toBeInTheDocument();
    expect(vi.mocked(useBlastHolesBySession)).toHaveBeenCalledWith(null);
    expect(screen.queryByTestId('blast-file-input')).not.toBeInTheDocument();
  });

  it('keeps blast upload available when demoMode is sticky but active meshes are real', () => {
    useSession.setState({ demoMode: true, designMeshId: 'real-design', topoMeshId: 'real-topo' });
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.queryByTestId('blast-demo-notice')).not.toBeInTheDocument();
    expect(screen.getByTestId('blast-file-input')).toBeInTheDocument();
  });

  it('renders the file input when sessionId exists', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-file-input')).toBeInTheDocument();
  });

  it('defaults to design-surface elevation and requires spatial reference confirmation', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect((screen.getByTestId('collar-elevation-source') as HTMLSelectElement).value).toBe('design_surface');
    expect(screen.getByTestId('spatial-reference-confirmed')).not.toBeChecked();
    expect(screen.queryByTestId('bench-height')).not.toBeInTheDocument();
  });

  it('selects the CSV before geometry confirmation and opens its configuration', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    const file = new File(['Inclinacion_real,Azimuth_real'], 'antes.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [file] } });
    expect(screen.getByTestId('geometry-contract-form')).toHaveAttribute('open');
    expect(screen.getByText(/antes.csv/)).toBeInTheDocument();
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    expect(mockMutateAsync).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('keeps file selection available and requires reconfirmation when replacing the CSV', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    const file = new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [file] } });
    fillCompleteContract();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [file] } });
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    expect(screen.getByTestId('geometry-confirmed')).not.toBeChecked();
    expect(screen.getByTestId('blast-file-picker')).not.toBeDisabled();
  });

  it('shows error state when upload fails', () => {
    mockUpload({ isError: true, error: new Error('Network error') });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('upload-error')).toHaveTextContent('Error al cargar el archivo:');
  });

  it('shows transfer percentage, then an unquantified geometry-processing phase', async () => {
    let resolveUpload!: (response: BlastUploadResponse) => void;
    mockMutateAsync.mockImplementation(() => new Promise<BlastUploadResponse>((resolve) => { resolveUpload = resolve; }));
    mockUpload({ mutateAsync: mockMutateAsync, isPending: false });
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));

    const { onUploadProgress } = mockMutateAsync.mock.calls[0][0];
    expect(screen.getByTestId('blast-upload-progress')).toHaveTextContent('Enviando archivo');
    act(() => onUploadProgress(62));
    expect(screen.getByRole('progressbar', { name: 'Progreso de transferencia del archivo' })).toHaveAttribute('value', '62');
    act(() => onUploadProgress(100));
    expect(screen.getByTestId('blast-upload-progress')).toHaveTextContent('Archivo enviado. Analizando pozos y geometría');
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();

    await act(async () => { resolveUpload(uploadResponse); });
    await waitFor(() => expect(screen.queryByTestId('blast-upload-progress')).not.toBeInTheDocument());
  });

  it('shows summary with n_holes after successful upload', () => {
    mockUpload({ isSuccess: true, data: uploadResponse });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-upload-summary')).toBeInTheDocument();
    expect(screen.getByText('42 pozos cargados, 3 filas omitidas')).toBeInTheDocument();
  });

  it('shows design-surface sampling coverage and all sample outcome counts', () => {
    mockUpload({
      isSuccess: true,
      data: {
        ...uploadResponse,
        design_surface: {
          mode: 'sample_design',
          mesh_id: 'design-1',
          mesh_sha256: 'abc',
          spatial_reference_confirmed: true,
          unit: 'm',
          method: 'vertical_triangle_intersection',
          rows: 42,
          coverage: 0.75,
          counts: { sampled: 32, outside: 4, ambiguous: 3, invalid: 3 },
        },
      },
    });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('design-surface-sampling-summary')).toHaveTextContent('Cota muestreada en 75.0% de 42 pozos.');
    expect(screen.getByTestId('design-surface-sampled')).toHaveTextContent('32');
    expect(screen.getByTestId('design-surface-outside')).toHaveTextContent('4');
    expect(screen.getByTestId('design-surface-ambiguous')).toHaveTextContent('3');
    expect(screen.getByTestId('design-surface-invalid')).toHaveTextContent('3');
  });

  it('shows persisted hole count after the GET request resolves', () => {
    mockUpload();
    mockHoles({
      data: {
        session_id: 'sess-001',
        holes: [
          { hole_id: 'H1', x: 1, y: 2, z: 3, carga: 10, descarga: 5, hardness: 'Blando' },
          { hole_id: 'H2', x: 4, y: 5, z: 6, carga: 20, descarga: 10, hardness: 'Duro' },
        ],
      },
    });
    renderUploader();
    expect(screen.getByTestId('blast-hole-count')).toHaveTextContent('2 pozos persistidos en sesión');
  });

  // ── INTEGRACIÓN §5.3 — no defaults ──

  it('permits choosing a file but blocks submission until geometry is confirmed', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-file-picker')).not.toBeDisabled();
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    // Confirming with empty fields does NOT enable submission.
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
  });

  it('all dropdowns start with the placeholder option selected', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect((screen.getByTestId('incl-convention') as HTMLSelectElement).value).toBe('');
    expect((screen.getByTestId('incl-sign') as HTMLSelectElement).value).toBe('');
    expect((screen.getByTestId('incl-unit') as HTMLSelectElement).value).toBe('');
    expect((screen.getByTestId('az-convention') as HTMLSelectElement).value).toBe('');
    expect((screen.getByTestId('az-unit') as HTMLSelectElement).value).toBe('');
  });

  // ── INTEGRACIÓN §5.3/§5.4 — confirmation + invalidation ──

  it('requires confirmation after filling every field', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    // Fields complete but checkbox unticked → still disabled.
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
  });

  it('invalidates confirmation when any field is edited after ticking', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
    // Edit a field — confirmation must auto-clear.
    fireEvent.change(screen.getByTestId('incl-source-column'), {
      target: { value: 'Inclinacion_real_2' },
    });
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    expect((screen.getByTestId('geometry-confirmed') as HTMLInputElement).checked).toBe(false);
  });

  it('requires source rule when sign convention is SOURCE_DEFINED', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-sign'), {
      target: { value: 'SOURCE_DEFINED' },
    });
    expect(screen.getByTestId('source-rule')).toBeInTheDocument();
    // Without selecting a rule, the contract is still incomplete.
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    // Select a rule → contract complete again.
    fireEvent.change(screen.getByTestId('source-rule'), {
      target: { value: 'negative_is_downward_dip' },
    });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
  });

  // ── INTEGRACIÓN §5.2 — independent units ──

  it('accepts differing inclination and azimuth units (no mismatch warning)', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-unit'), { target: { value: 'RADIANS' } });
    // After editing the unit, the confirmation auto-clears but NO
    // units-mismatch warning is rendered (independent units are valid).
    expect(screen.queryByText(/Las unidades de inclinación y azimut difieren/)).toBeNull();
    // Re-confirm with the mixed configuration — submission still enabled.
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinacion_real' } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-upload-submit')).not.toBeDisabled();
  });

  // ── INTEGRACIÓN §5.4 — structured diagnostics from HTTP 422 ──

  it('renders rejected_rows extracted from a 422 AxiosError response', async () => {
    // The hook rejects with an AxiosError whose .response.data carries
    // the structured payload (rejected_rows + blocking_errors). This is
    // what the operator sees when the backend returns HTTP 422.
    const structuredBody: Partial<BlastUploadResponse> = {
      n_holes: 0,
      accepted_rows: [],
      rejected_rows: [
        {
          hole_id: 'BAD-0',
          source_row_index: 0,
          source_column: 'Latitud_Geo',
          original_value: null,
          error_code: 'INVALID_X',
          rejection_reason: 'valor no numérico o ausente',
          affected_calculations: 'toe, PF',
          recommended_action: 'Corrija el dato.',
          row_processing_status: 'rejected',
        },
      ],
      blocking_errors: [
        { error_code: 'NO_ACCEPTED_ROWS', message: 'Ninguna fila pasó la validación.' },
      ],
      event_warnings: [{ warning_code: 'INCLINATION_ALL_ZERO', message: 'La columna de inclinación declarada contiene cero en todas las filas. Verifique la convención confirmada.' }],
    };
    const axiosLikeError = {
      response: { data: structuredBody, status: 422 },
      message: 'Request failed with status code 422',
    };
    mockUpload({ isError: true, error: axiosLikeError as unknown as Error });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('rejected-rows')).toHaveTextContent('INVALID_X');
    expect(screen.getByTestId('blocking-errors')).toHaveTextContent('NO_ACCEPTED_ROWS');
    expect(screen.getByTestId('event-warning-messages')).toHaveTextContent('La columna de inclinación declarada contiene cero en todas las filas.');
  });

  // ── Hook FormData assertion ──

  it('sends inclination_unit AND azimuth_unit as independent fields', async () => {
    mockUpload({
      mutateAsync: mockMutateAsync.mockResolvedValue(uploadResponse),
    } as Partial<ReturnType<typeof useUploadBlastCsv>>);
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    // Set differing units to prove they are transmitted independently.
    fireEvent.change(screen.getByTestId('incl-unit'), { target: { value: 'DEGREES' } });
    fireEvent.change(screen.getByTestId('az-unit'), { target: { value: 'RADIANS' } });
    // Re-fill the source column edited by the previous change handler.
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinacion_real' } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));

    const file = new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));

    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const call = mockMutateAsync.mock.calls[0][0];
    expect(call.geometry.inclination_unit).toBe('DEGREES');
    expect(call.geometry.azimuth_unit).toBe('RADIANS');
    expect(call.geometry.geometry_configuration_version).toBe('2.0');
    expect(call.geometry.inclination_source_column).toBe('Inclinacion_real');
    expect(call.geometry.azimuth_source_column).toBe('Azimuth_real');
    expect(call.geometry.geometry_user_confirmed).toBe(true);
  });

  it('requires spatial reference confirmation and sends design-surface elevation source', async () => {
    mockUpload({ mutateAsync: mockMutateAsync.mockResolvedValue(uploadResponse) } as Partial<ReturnType<typeof useUploadBlastCsv>>);
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [new File(['Inclinacion_real,Azimuth_real'], 'pozos.csv', { type: 'text/csv' })] } });
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('collar-elevation-source'), { target: { value: 'design_surface' } });
    expect(screen.getByTestId('design-surface-elevation')).toHaveTextContent('no se infiere la altura real del banco');
    expect(screen.getByTestId('blast-upload-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('spatial-reference-confirmed'));
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    fireEvent.click(screen.getByTestId('blast-upload-submit'));
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const { geometry } = mockMutateAsync.mock.calls[0][0];
    expect(geometry.bench_height_m).toBeUndefined();
    expect(geometry.collar_elevation_source).toBe('design_surface');
    expect(geometry.spatial_reference_confirmed).toBe(true);
  });
});
