import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastUploader } from './BlastUploader';

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

const uploadResponse = {
  session_id: 'sess-001',
  n_holes: 42,
  n_rows_loaded: 42,
  n_rows_skipped: 3,
  carga_mean: 12.3456,
  descarga_mean: 8.9,
  hardness_distribution: { Blando: 30, Duro: 12 },
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

function renderUploader(props: { onUploaded?: (r: typeof uploadResponse) => void } = {}) {
  return render(<BlastUploader onUploaded={props.onUploaded} />);
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
    expect(screen.getByText('Cargar archivo de pozos')).toBeInTheDocument();
  });

  it('shows error state when upload fails', () => {
    mockUpload({ isError: true, error: new Error('Network error') });
    mockHoles();
    renderUploader();
    expect(screen.getByRole('alert')).toHaveTextContent('Error al cargar el archivo:');
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

});
