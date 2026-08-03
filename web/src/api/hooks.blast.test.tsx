import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import client from './client';
import {
  extractBlastErrorDiagnostics,
  useUploadBlastCsv,
  type BlastGeometryForm,
} from './hooks';

const geometry: BlastGeometryForm = {
  geometry_configuration_version: '2.0',
  geometry_user_confirmed: true,
  inclination_source_column: 'Inclinacion_real',
  inclination_convention: 'FROM_VERTICAL',
  inclination_sign_convention: 'ABSOLUTE_VALUE',
  inclination_unit: 'DEGREES',
  inclination_source_rule: '',
  azimuth_source_column: 'Azimuth_real',
  azimuth_convention: 'CLOCKWISE_FROM_NORTH',
  azimuth_unit: 'RADIANS',
};

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  );
}

describe('useUploadBlastCsv production request', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the exact complete v2 FormData through the real hook', async () => {
    const post = vi.spyOn(client, 'post').mockResolvedValue({ data: { accepted_rows: [] } });
    const { result } = renderHook(() => useUploadBlastCsv(), { wrapper });
    const file = new File(['x,y'], 'pozos.csv', { type: 'text/csv' });

    await act(async () => {
      await result.current.mutateAsync({ sessionId: 'session-1', file, geometry });
    });

    const form = post.mock.calls[0][1] as FormData;
    const entries = Object.fromEntries(form.entries());
    expect(Object.keys(entries).sort()).toEqual([
      'azimuth_convention',
      'azimuth_source_column',
      'azimuth_unit',
      'file',
      'geometry_configuration_version',
      'geometry_user_confirmed',
      'inclination_convention',
      'inclination_sign_convention',
      'inclination_source_column',
      'inclination_source_rule',
      'inclination_unit',
      'session_id',
    ]);
    expect(entries.inclination_unit).toBe('DEGREES');
    expect(entries.azimuth_unit).toBe('RADIANS');
    expect(entries.geometry_configuration_version).toBe('2.0');
    expect(entries).not.toHaveProperty('angle_unit');
    expect(entries).not.toHaveProperty('incl_convention');
  });

  it('unwraps FastAPI HTTP 400 detail into structured blocking errors', () => {
    const result = extractBlastErrorDiagnostics({
      response: {
        status: 400,
        data: {
          detail: {
            error_code: 'LEGACY_V2_CONFLICT',
            message: 'Contrato contradictorio',
            details: { conflicts: { angle_unit: 'radians' } },
          },
        },
      },
    });
    expect(result?.blocking_errors?.[0]).toMatchObject({
      error_code: 'LEGACY_V2_CONFLICT',
      message: 'Contrato contradictorio',
    });
  });
});
