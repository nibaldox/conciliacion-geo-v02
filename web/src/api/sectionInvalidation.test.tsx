// @vitest-environment jsdom
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import client from './client';
import {
  invalidateSectionDependents,
  useClickSection,
  useCurveSection,
} from './hooks';
import { DEMO_MESH_IDS, useSession, type DemoData } from '../stores/session';

const DEPENDENT_KEYS = [
  'sections',
  'results',
  'process-status',
  'profile',
  'design-achievement',
  'proposed-compliance',
  'blast-correlation',
  'blast-damage-model',
  'horizontal-deviation-mesh',
];

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapperFor(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function invalidatedKeys(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls.map(([filters]) => {
    const { queryKey } = filters as { queryKey: string[] };
    return queryKey[0];
  });
}

afterEach(() => {
  useSession.getState().reset();
  vi.restoreAllMocks();
});

describe('invalidateSectionDependents', () => {
  it('invalidates every query derived from the previous section set', () => {
    useSession.setState({ demoMode: false, demoData: null, designMeshId: 'design-1' });
    const qc = makeClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');

    invalidateSectionDependents(qc);

    for (const key of DEPENDENT_KEYS) {
      expect(spy).toHaveBeenCalledWith({ queryKey: [key] });
    }
  });

  it('invalidates results and process-status after a section mutation', async () => {
    useSession.setState({ demoMode: false, demoData: null, designMeshId: 'design-1' });
    vi.spyOn(client, 'post').mockResolvedValue({
      data: {
        section: {
          id: '1',
          name: 'S-02',
          origin: [0, 0],
          azimuth: 0,
          length: 100,
          sector: 'Norte',
        },
        total: 2,
      },
    });
    const qc = makeClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useClickSection(), { wrapper: wrapperFor(qc) });

    await act(async () => {
      await result.current.mutateAsync({
        origin: [0, 0],
        az_mode: 'manual',
        azimuth: 0,
        length: 100,
        sector: 'Norte',
      });
    });

    await waitFor(() => expect(invalidatedKeys(spy)).toContain('results'));
    expect(invalidatedKeys(spy)).toContain('process-status');
    expect(invalidatedKeys(spy)).toContain('sections');
  });

  it('keeps demo caches and the demo process-status untouched', async () => {
    useSession.setState({
      demoMode: true,
      designMeshId: DEMO_MESH_IDS.design,
      topoMeshId: DEMO_MESH_IDS.topo,
      demoData: {
        sections: [],
        comparisons: [{ section: 'DEMO-S01', sector: 'Norte' }],
      } as unknown as DemoData,
    });
    const qc = makeClient();
    const demoResultsKey = ['results', undefined, true, DEMO_MESH_IDS.design];
    qc.setQueryData(demoResultsKey, [{ section: 'DEMO-S01', sector: 'Norte' }]);
    const spy = vi.spyOn(qc, 'invalidateQueries');

    invalidateSectionDependents(qc);

    expect(invalidatedKeys(spy)).toContain('results');
    expect(invalidatedKeys(spy)).not.toContain('process-status');
    expect(qc.getQueryData(demoResultsKey)).toEqual([
      { section: 'DEMO-S01', sector: 'Norte' },
    ]);
  });

  it('keeps useCurveSection as a no-op against the API in demo mode', async () => {
    useSession.setState({
      demoMode: true,
      designMeshId: DEMO_MESH_IDS.design,
      topoMeshId: DEMO_MESH_IDS.topo,
      demoData: { sections: [] } as unknown as DemoData,
    });
    const post = vi.spyOn(client, 'post');
    const qc = makeClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useCurveSection(), { wrapper: wrapperFor(qc) });

    await act(async () => {
      await result.current.mutateAsync({
        points: [[0, 0], [10, 0]],
        spacing: 5,
        length: 100,
        sector: 'Norte',
      });
    });

    expect(post).not.toHaveBeenCalled();
    expect(invalidatedKeys(spy)).toContain('sections');
    expect(invalidatedKeys(spy)).not.toContain('process-status');
  });
});
