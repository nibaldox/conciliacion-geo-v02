// @vitest-environment jsdom
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import client from './client';
import { useExportDxf, useExportWord } from './hooks';

afterEach(() => vi.restoreAllMocks());
it.each([['word', useExportWord], ['dxf', useExportDxf]])('%s exports use a ten minute timeout', async (_, hook) => {
  const get = vi.spyOn(client, 'get').mockResolvedValue({ data: new Blob(), headers: {} });
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const queryClient = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => hook(), { wrapper });
  await act(async () => { await result.current.mutateAsync(); });
  expect(get).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ timeout: 600000, responseType: 'blob' }));
  vi.unstubAllGlobals();
  queryClient.clear();
});
