// @vitest-environment jsdom
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import client from './client';
import { useProcess, useProfile } from './hooks';
import { DEMO_MESH_IDS, useSession, type DemoData } from '../stores/session';

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const profileResponse = {
  data: {
    section_name: 'S-01',
    sector: '',
    origin: [0, 0],
    azimuth: 0,
    design: { distances: [0, 10], elevations: [100, 90] },
    topo: null,
  },
};

describe('profile query freshness across surface changes', () => {
  afterEach(() => {
    useSession.getState().reset();
    vi.restoreAllMocks();
  });

  it('fetches a new profile when the topo mesh changes with the same design mesh', async () => {
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
    const get = vi.spyOn(client, 'get').mockResolvedValue(profileResponse);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useProfile('0'), { wrapper: createWrapper(queryClient) });

    await waitFor(() => expect(result.current.data).toEqual(profileResponse.data));
    act(() => useSession.getState().setTopoMeshId('topo-2'));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));

    expect(get.mock.calls.map(([url]) => url)).toEqual([
      '/process/profiles/0',
      '/process/profiles/0',
    ]);
    queryClient.clear();
  });

  it('refetches an active profile after processing completes', async () => {
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
    const get = vi.spyOn(client, 'get').mockResolvedValue(profileResponse);
    vi.spyOn(client, 'post').mockResolvedValue({ data: { status: 'complete' } });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = createWrapper(queryClient);
    const { result: profile } = renderHook(() => useProfile('0'), { wrapper });
    const { result: process } = renderHook(() => useProcess(), { wrapper });

    await waitFor(() => expect(profile.current.data).toEqual(profileResponse.data));
    const profileFetchesBeforeProcessing = get.mock.calls.length;
    await act(async () => {
      await process.current.mutateAsync({ resolution: 0.1, face_threshold: 40, berm_threshold: 20 });
    });
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(profileFetchesBeforeProcessing));

    queryClient.clear();
  });
});

describe('demo profile resolution', () => {
  const demoSection = (name: string) => ({
    section_name: name,
    sector: 'Norte',
    origin: [0, 0],
    azimuth: 90,
    design_profile: { distances: [0, 10], elevations: [100, 90] },
    topo_profile: { distances: [0, 10], elevations: [100, 91] },
    reconciled_topo: { distances: [0, 10], elevations: [100, 91] },
    benches_topo: [],
  });

  afterEach(() => {
    useSession.getState().reset();
    vi.restoreAllMocks();
  });

  function setupDemo() {
    useSession.setState({
      demoMode: true,
      designMeshId: DEMO_MESH_IDS.design,
      topoMeshId: DEMO_MESH_IDS.topo,
      demoData: { sections: [demoSection('DEMO-S01'), demoSection('DEMO-S02')] } as unknown as DemoData,
    });
    return vi.spyOn(client, 'get');
  }

  it('resolves a demo profile by section name', async () => {
    const get = setupDemo();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useProfile('DEMO-S02'), { wrapper: createWrapper(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.section_name).toBe('DEMO-S02');
    expect(get).not.toHaveBeenCalled();
    queryClient.clear();
  });

  it('falls back to the numeric index used by demo section ids', async () => {
    setupDemo();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useProfile('1'), { wrapper: createWrapper(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.section_name).toBe('DEMO-S02');
    queryClient.clear();
  });

  it('reports an unknown demo section', async () => {
    setupDemo();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useProfile('DEMO-S99'), { wrapper: createWrapper(queryClient) });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Demo section DEMO-S99 not found');
    queryClient.clear();
  });
});
