import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastUploader } from './BlastUploader';
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
  fireEvent.change(screen.getByTestId('incl-source-column'), {
    target: { value: 'Inclinacion_real' },
  });
  fireEvent.change(screen.getByTestId('az-source-column'), {
    target: { value: 'Azimuth_real' },
  });
  fireEvent.change(screen.getByTestId('incl-convention'), {
    target: { value: 'from_vertical' },
  });
  fireEvent.change(screen.getByTestId('incl-sign'), {
    target: { value: 'ABSOLUTE_VALUE' },
  });
  fireEvent.change(screen.getByTestId('incl-unit'), {
    target: { value: 'degrees' },
  });
  fireEvent.change(screen.getByTestId('az-convention'), {
    target: { value: 'CLOCKWISE_FROM_NORTH' },
  });
  fireEvent.change(screen.getByTestId('az-unit'), {
    target: { value: 'degrees' },
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
  });

  it('renders the file input when sessionId exists', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-file-input')).toBeInTheDocument();
  });

  it('shows error state when upload fails', () => {
    mockUpload({ isError: true, error: new Error('Network error') });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('upload-error')).toHaveTextContent('Error al cargar el archivo:');
  });

  it('shows summary with n_holes after successful upload', () => {
    mockUpload({ isSuccess: true, data: uploadResponse });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-upload-summary')).toBeInTheDocument();
    expect(screen.getByText('42 pozos cargados, 3 filas omitidas')).toBeInTheDocument();
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

  it('disables the file input by default (every field empty)', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
    // Confirming with empty fields does NOT enable submission.
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
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
    fillCompleteContract();
    // Fields complete but checkbox unticked → still disabled.
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).not.toBeDisabled();
  });

  it('invalidates confirmation when any field is edited after ticking', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fillCompleteContract();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).not.toBeDisabled();
    // Edit a field — confirmation must auto-clear.
    fireEvent.change(screen.getByTestId('incl-source-column'), {
      target: { value: 'Inclinacion_real_2' },
    });
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
    expect((screen.getByTestId('geometry-confirmed') as HTMLInputElement).checked).toBe(false);
  });

  it('requires source rule when sign convention is SOURCE_DEFINED', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-sign'), {
      target: { value: 'SOURCE_DEFINED' },
    });
    expect(screen.getByTestId('source-rule')).toBeInTheDocument();
    // Without selecting a rule, the contract is still incomplete.
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
    // Select a rule → contract complete again.
    fireEvent.change(screen.getByTestId('source-rule'), {
      target: { value: 'negative_is_downward_dip' },
    });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).not.toBeDisabled();
  });

  // ── INTEGRACIÓN §5.2 — independent units ──

  it('accepts differing inclination and azimuth units (no mismatch warning)', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-unit'), { target: { value: 'radians' } });
    // After editing the unit, the confirmation auto-clears but NO
    // units-mismatch warning is rendered (independent units are valid).
    expect(screen.queryByText(/Las unidades de inclinación y azimut difieren/)).toBeNull();
    // Re-confirm with the mixed configuration — submission still enabled.
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinacion_real' } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).not.toBeDisabled();
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
  });

  // ── Hook FormData assertion ──

  it('sends inclination_unit AND azimuth_unit as independent fields', async () => {
    mockUpload({
      mutateAsync: mockMutateAsync.mockResolvedValue(uploadResponse),
    } as Partial<ReturnType<typeof useUploadBlastCsv>>);
    mockHoles();
    renderUploader();
    fillCompleteContract();
    // Set differing units to prove they are transmitted independently.
    fireEvent.change(screen.getByTestId('incl-unit'), { target: { value: 'degrees' } });
    fireEvent.change(screen.getByTestId('az-unit'), { target: { value: 'radians' } });
    // Re-fill the source column edited by the previous change handler.
    fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinacion_real' } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));

    const file = new File(['x,y'], 'pozos.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [file] } });

    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const call = mockMutateAsync.mock.calls[0][0];
    expect(call.geometry.inclination_unit).toBe('degrees');
    expect(call.geometry.azimuth_unit).toBe('radians');
    expect(call.geometry.inclination_source_column).toBe('Inclinacion_real');
    expect(call.geometry.azimuth_source_column).toBe('Azimuth_real');
    expect(call.geometry.geometry_user_confirmed).toBe(true);
  });
});
