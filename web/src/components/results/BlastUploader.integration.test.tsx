import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '../../i18n';

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>();
  return { ...actual, getSessionId: () => 'session-integration' };
});

const { default: client } = await import('../../api/client');
const { BlastUploader } = await import('./BlastUploader');

function select(testId: string, value: string) {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

function completeContract() {
  fireEvent.change(screen.getByTestId('incl-source-column'), { target: { value: 'Inclinacion_real' } });
  fireEvent.change(screen.getByTestId('az-source-column'), { target: { value: 'Azimuth_real' } });
  select('incl-convention', 'FROM_VERTICAL');
  select('incl-sign', 'ABSOLUTE_VALUE');
  select('incl-unit', 'DEGREES');
  select('az-convention', 'CLOCKWISE_FROM_NORTH');
  select('az-unit', 'RADIANS');
  fireEvent.click(screen.getByTestId('geometry-confirmed'));
}

function renderUploader() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <BlastUploader />
    </QueryClientProvider>,
  );
}

describe('BlastUploader with production hook', () => {
  beforeAll(async () => i18n.changeLanguage('es'));

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'get').mockResolvedValue({
      data: { session_id: 'session-integration', holes: [] },
    });
  });

  it('renders structured diagnostics from a real hook HTTP 422 path', async () => {
    const post = vi.spyOn(client, 'post').mockRejectedValue({
      message: 'Request failed with status code 422',
      response: {
        status: 422,
        data: {
          accepted_rows: [],
          rejected_rows: [{
            hole_id: 'BAD-1',
            source_row_index: 0,
            source_column: 'Latitud_Geo',
            original_value: null,
            error_code: 'INVALID_X',
            rejection_reason: 'Coordenada inválida',
            affected_calculations: 'toe, PF',
            recommended_action: 'Corrija la coordenada.',
            row_processing_status: 'rejected',
          }],
          event_warnings: [{ warning_code: 'W_TEST', message: 'Advertencia estructurada' }],
          blocking_errors: [{ error_code: 'NO_ACCEPTED_ROWS', message: 'Sin filas aceptadas' }],
          processing_summary: { rows_received: 1, rows_accepted: 0 },
          geometry_configuration: { geometry_configuration_version: '2.0' },
          spatial_diagnostics: { domain_status: 'blocked' },
        },
      },
    });
    renderUploader();
    completeContract();
    fireEvent.change(screen.getByTestId('blast-file-input'), {
      target: { files: [new File(['bad'], 'bad.csv', { type: 'text/csv' })] },
    });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('rejected-rows')).toHaveTextContent('INVALID_X'));
    expect(screen.getByTestId('blocking-errors')).toHaveTextContent('NO_ACCEPTED_ROWS');
    expect(screen.getByTestId('event-warnings')).toHaveTextContent('Advertencias: 1');
    expect(screen.getByTestId('processing-summary')).toHaveTextContent('rows_received');
    expect(screen.getByTestId('geometry-configuration')).toHaveTextContent('2.0');
    expect(screen.getByTestId('spatial-diagnostics')).toHaveTextContent('blocked');
  });

  it('unwraps and renders structured FastAPI HTTP 400 detail', async () => {
    const post = vi.spyOn(client, 'post').mockRejectedValue({
      message: 'Request failed with status code 400',
      response: {
        status: 400,
        data: {
          detail: {
            error_code: 'GEOMETRY_INCOMPLETE',
            message: 'La versión del contrato no es válida.',
            details: { missing_or_invalid: { geometry_configuration_version: '9.9' } },
          },
        },
      },
    });
    renderUploader();
    completeContract();
    fireEvent.change(screen.getByTestId('blast-file-input'), {
      target: { files: [new File(['bad'], 'bad.csv', { type: 'text/csv' })] },
    });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('blocking-errors')).toHaveTextContent('GEOMETRY_INCOMPLETE'));
    expect(screen.getByTestId('processing-diagnostics')).toBeInTheDocument();
  });
});
