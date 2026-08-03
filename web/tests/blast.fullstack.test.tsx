import type { ReactNode } from 'react';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import client from '../src/api/client';
import { useUploadBlastCsv, type BlastGeometryForm } from '../src/api/hooks';

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

describe('browser request to persisted and exported blast result', () => {
  afterEach(() => vi.restoreAllMocks());

  it('feeds the hook FormData through API, core, persistence, and Excel export', async () => {
    const post = vi.spyOn(client, 'post').mockResolvedValue({ data: { accepted_rows: [] } });
    const { result } = renderHook(() => useUploadBlastCsv(), { wrapper });
    const csv = [
      'Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real',
      '1000.0,2000.0,4000,15.0,1.5707963267948966,12.0',
      '1010.0,2000.0,4000,15.0,1.5707963267948966,12.0',
      '1010.0,2010.0,4000,15.0,1.5707963267948966,12.0',
      '1000.0,2010.0,4000,15.0,1.5707963267948966,12.0',
    ].join('\n');
    const file = new File([csv], 'pozos.csv', { type: 'text/csv' });

    await act(async () => {
      await result.current.mutateAsync({ sessionId: 'browser-session-placeholder', file, geometry });
    });

    const form = post.mock.calls[0][1] as FormData;
    const fields = Object.fromEntries(
      Array.from(form.entries())
        .filter(([, value]) => typeof value === 'string')
        .map(([key, value]) => [key, value as string]),
    );
    const integration = spawnSync(
      'uv',
      ['run', 'python', 'tests/support/frontend_api_integration_harness.py'],
      {
        cwd: path.resolve(process.cwd(), '..'),
        env: process.env,
        input: JSON.stringify({ fields, csv }),
        encoding: 'utf8',
      },
    );
    expect(integration.status, integration.stderr).toBe(0);
    expect(JSON.parse(integration.stdout)).toMatchObject({
      status_code: 200,
      accepted_rows: 4,
      persisted_same_result: true,
      export_reopened: true,
      inclination_unit: 'DEGREES',
      azimuth_unit: 'RADIANS',
    });
  });
});
