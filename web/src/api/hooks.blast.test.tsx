import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import client from './client';
import { useSession } from '../stores/session';
import {
  extractBlastErrorDiagnostics,
  useUploadBlastCsv,
  useBlastCorrelation,
  useBlastDamageModel,
  buildBlastUploadFormData,
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

describe('blast analysis context', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the same survey date to correlation and the damage model and refetches for a changed date', async () => {
    useSession.setState({ demoMode: false });
    const get = vi.spyOn(client, 'get').mockResolvedValue({ data: { rows: [], points: [], fit: null } });
    const view = renderHook(({ date }) => ({ correlation: useBlastCorrelation(date), damage: useBlastDamageModel(date) }), { initialProps: { date: '2026-11-04' }, wrapper: wrapper() });
    await waitFor(() => expect(get).toHaveBeenCalledWith('/process/blast-correlation', { params: { survey_date: '2026-11-04' } }));
    expect(get).toHaveBeenCalledWith('/process/blast-correlation/damage-model', { params: { survey_date: '2026-11-04' } });
    view.rerender({ date: '2026-10-01' });
    await waitFor(() => expect(get).toHaveBeenCalledWith('/process/blast-correlation/damage-model', { params: { survey_date: '2026-10-01' } }));
  });

  it('carries the confirmed column map and worksheet with the geometry contract', () => {
    const form = buildBlastUploadFormData('session', new File([''], 'pozos.xlsx'), { ...geometry, column_map: { X: 'Este real', Y: 'Norte real' }, sheet_name: 'Pozos 2026' });
    expect(JSON.parse(String(form.get('column_map')))).toEqual({ X: 'Este real', Y: 'Norte real' });
    expect(form.get('sheet_name')).toBe('Pozos 2026');
  });

  it('serializes the explicit date source and format as top-level multipart fields outside column_map', () => {
    const form = buildBlastUploadFormData('session', new File([''], 'pozos.csv'), {
      ...geometry,
      column_map: { X: 'Este real' },
      date_source_column: 'Fecha tronadura ',
      date_format: 'DMY',
    });
    expect(form.get('date_source_column')).toBe('Fecha tronadura ');
    expect(form.get('date_format')).toBe('DMY');
    expect(JSON.parse(String(form.get('column_map')))).toEqual({ X: 'Este real' });
  });

  it('omits date fields from multipart when no date source is selected', () => {
    const form = buildBlastUploadFormData('session', new File([''], 'pozos.csv'), { ...geometry, date_format: 'ISO' });
    expect(form.has('date_source_column')).toBe(false);
    expect(form.has('date_format')).toBe(false);
  });
});

function wrapper(queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })) {
  return function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
  };
}

describe('useUploadBlastCsv production request', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the exact complete v2 FormData through the real hook', async () => {
    const post = vi.spyOn(client, 'post').mockResolvedValue({ data: { accepted_rows: [] } });
    const { result } = renderHook(() => useUploadBlastCsv(), { wrapper: wrapper() });
    const file = new File(['x,y'], 'pozos.csv', { type: 'text/csv' });

    await act(async () => {
      await result.current.mutateAsync({ sessionId: 'session-1', file, geometry });
    });

    const form = post.mock.calls[0][1] as FormData;
    expect(post.mock.calls[0][0]).toBe('/blast/upload');
    expect((post.mock.calls[0][2] as { params?: Record<string, unknown> }).params).toEqual({ compact: true });
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

  it('forwards Axios upload progress as a bounded percentage when total bytes are known', async () => {
    const post = vi.spyOn(client, 'post').mockResolvedValue({ data: { accepted_rows: [] } });
    const onUploadProgress = vi.fn();
    const { result } = renderHook(() => useUploadBlastCsv(), { wrapper: wrapper() });

    await act(async () => {
      await result.current.mutateAsync({
        sessionId: 'session-1',
        file: new File(['x,y'], 'pozos.csv', { type: 'text/csv' }),
        geometry,
        onUploadProgress,
      });
    });

    const config = post.mock.calls[0][2] as { onUploadProgress?: (event: { loaded: number; total?: number }) => void };
    config.onUploadProgress?.({ loaded: 50, total: 100 });
    config.onUploadProgress?.({ loaded: 120, total: 100 });
    expect(onUploadProgress.mock.calls.map(([value]) => value)).toEqual([50, 100]);
  });

  it('invalidates 3D, session, and profile blast-hole queries after a successful upload', async () => {
    useSession.getState().setSelectedBlastHoleRowId('previous-row-5');
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    vi.spyOn(client, 'post').mockResolvedValue({ data: { accepted_rows: [{ hole_id: 'P-1' }] } });
    const { result } = renderHook(() => useUploadBlastCsv(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync({
        sessionId: 'session-1', file: new File(['x'], 'holes.csv', { type: 'text/csv' }), geometry,
      });
    });

    expect(invalidate).toHaveBeenCalledTimes(4);
    const invalidatedKeys = invalidate.mock.calls.map(([filters]) => {
      if (!filters) throw new Error('invalidateQueries se llamó sin filtros');
      return filters.queryKey;
    });
    expect(invalidatedKeys).toEqual([
      ['blast-holes-3d'], ['blast-holes-by-session'], ['blast-summary'], ['blast-holes'],
    ]);
    expect(useSession.getState().selectedBlastHoleRowId).toBeNull();
  });

  it('does not invalidate blast-hole queries when the upload fails', async () => {
    useSession.getState().setSelectedBlastHoleRowId('keep-on-failure');
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    vi.spyOn(client, 'post').mockRejectedValue(new Error('upload failed'));
    const { result } = renderHook(() => useUploadBlastCsv(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await expect(result.current.mutateAsync({
        sessionId: 'session-1', file: new File(['x'], 'holes.csv', { type: 'text/csv' }), geometry,
      })).rejects.toThrow('upload failed');
    });

    expect(invalidate).not.toHaveBeenCalled();
    expect(useSession.getState().selectedBlastHoleRowId).toBe('keep-on-failure');
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
