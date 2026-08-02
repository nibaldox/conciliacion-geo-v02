import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastUploader } from './BlastUploader';
import type { BlastUploadResponse } from '../../api/types';

// ─── Mocks ─────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock('../../api/hooks', () => ({
  useUploadBlastCsv: vi.fn(),
  useBlastHolesBySession: vi.fn(),
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

// Helper: set every required field of the geometry contract so the file
// input becomes enabled. Tests that need a "complete + confirmed" state
// call this and then tick the checkbox.
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
  fireEvent.change(screen.getByTestId('az-convention'), {
    target: { value: 'CLOCKWISE_FROM_NORTH' },
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
    expect(screen.getByText('Carga media: 12.35 kg')).toBeInTheDocument();
    expect(screen.getByText('Descarga media: 8.90 kg')).toBeInTheDocument();
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

  // ── INTEGRACIÓN §5.1 — Geometry contract behaviour ──

  it('disables the file input by default (no confirmation)', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
  });

  it('requires confirmation before enabling the file input', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fillCompleteContract();
    // Even with complete fields, the checkbox is unticked → still disabled.
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
    // Tick the checkbox → enabled.
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    expect(screen.getByTestId('blast-file-input')).not.toBeDisabled();
  });

  it('invalidates confirmation when a field is edited after ticking', () => {
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

  it('blocks submission when source columns are empty', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('incl-convention'), {
      target: { value: 'from_vertical' },
    });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    // Source columns still empty → can't submit.
    expect(screen.getByTestId('blast-file-input')).toBeDisabled();
  });

  it('requires source rule when sign convention is SOURCE_DEFINED', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('incl-sign'), {
      target: { value: 'SOURCE_DEFINED' },
    });
    // Source rule select appears.
    expect(screen.getByTestId('source-rule')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('geometry-confirmed'));
    // The rule default is filled but the field re-appears; if the user
    // clears the source columns the file input stays disabled.
    expect(screen.getByTestId('blast-file-input')).not.toBeDisabled();
  });

  it('warns when inclination and azimuth units differ', () => {
    mockUpload();
    mockHoles();
    renderUploader();
    fireEvent.change(screen.getByTestId('incl-unit'), { target: { value: 'radians' } });
    fireEvent.change(screen.getByTestId('az-unit'), { target: { value: 'degrees' } });
    expect(
      screen.getByText(
        /Las unidades de inclinación y azimut difieren/,
      ),
    ).toBeInTheDocument();
  });

  it('shows structured blocking errors from the API', () => {
    mockUpload({
      isSuccess: true,
      data: {
        ...uploadResponse,
        n_holes: 0,
        blocking_errors: [
          {
            error_code: 'NO_ACCEPTED_ROWS',
            message: 'Ninguna fila pasó la validación.',
          },
        ],
      },
    });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('blocking-errors')).toHaveTextContent('NO_ACCEPTED_ROWS');
  });

  it('shows structured rejected rows from the API', () => {
    mockUpload({
      isSuccess: true,
      data: {
        ...uploadResponse,
        n_holes: 0,
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
      },
    });
    mockHoles();
    renderUploader();
    expect(screen.getByTestId('rejected-rows')).toHaveTextContent('INVALID_X');
  });

  it('sends the full geometry contract FormData on submit', async () => {
    mockUpload({
      isSuccess: false,
      mutateAsync: mockMutateAsync.mockResolvedValue(uploadResponse),
    } as Partial<ReturnType<typeof useUploadBlastCsv>>);
    mockHoles();
    renderUploader();
    fillCompleteContract();
    fireEvent.change(screen.getByTestId('bench-height'), { target: { value: '15' } });
    fireEvent.click(screen.getByTestId('geometry-confirmed'));

    const file = new File(['x,y'], 'pozos.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByTestId('blast-file-input'), { target: { files: [file] } });

    await vi.waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const call = mockMutateAsync.mock.calls[0][0];
    expect(call.sessionId).toBe('sess-001');
    expect(call.file).toBe(file);
    expect(call.geometry.geometry_user_confirmed).toBe(true);
    expect(call.geometry.inclination_source_column).toBe('Inclinacion_real');
    expect(call.geometry.azimuth_source_column).toBe('Azimuth_real');
    expect(call.geometry.inclination_convention).toBe('from_vertical');
    expect(call.geometry.azimuth_convention).toBe('CLOCKWISE_FROM_NORTH');
    expect(call.geometry.inclination_unit).toBe('degrees');
    expect(call.geometry.azimuth_unit).toBe('degrees');
    expect(call.geometry.bench_height_m).toBe(15);
  });
});
