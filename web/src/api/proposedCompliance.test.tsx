import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

vi.mock('./client', () => ({
  default: { get: vi.fn() },
}));

let settingsStamp = 1000;
let resultsStamp = 2000;
vi.mock('./hooks', () => ({
  useSettings: () => ({ dataUpdatedAt: settingsStamp }),
  useResults: () => ({ dataUpdatedAt: resultsStamp }),
}));

import client from './client';
import { useSession } from '../stores/session';
import {
  buildProposedComplianceQuery,
  useProposedCompliance,
  type ProposedComplianceResponse,
} from './proposedCompliance';

const getMock = client.get as unknown as Mock;

const EMPTY = { sector: [], section: [], level: [], bench: [] };

const RESPONSE: ProposedComplianceResponse = {
  session_id: 's1',
  proposal_status: 'current',
  n_total_rows: 12,
  n_proposal_rows: 12,
  n_failed_rows: 0,
  n_not_computed_rows: 0,
  summary: {
    section: null,
    proposed_global_score: 78.5,
    n_rows: 12,
    n_evaluable: 9,
    n_not_excavated: 2,
    n_section_truncated: 0,
    n_unmeasured: 1,
    n_split_fragments: 0,
    n_split_benches: 1,
    excavation_debt_area_m2: 1250.4,
    floor_status_counts: { CUMPLE: 7, 'NO CUMPLE': 2, '-': 3 },
    coverage: { n_evaluable: 9, n_design_benches: 10, ratio: 0.9 },
    by_section: {
      'S-01': {
        section: 'S-01',
        proposed_section_score: 80,
        proposed_section_status: 'CUMPLE',
        n_rows: 6,
        n_evaluable: 5,
        n_not_excavated: 1,
        n_section_truncated: 0,
        n_unmeasured: 0,
        n_split_fragments: 0,
        n_split_benches: 0,
        excavation_debt_area_m2: 625.2,
        floor_status_counts: { CUMPLE: 4, '-': 2 },
      },
    },
  },
  floor_tolerance: { max: 0.5 },
  floor_tolerance_source: 'core_default',
  filters: { sector: [], section: [], level: [], bench: [] },
  status_model: 'rows',
  assumptions: ['official values never change'],
  warnings: [],
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrapper };
}

afterEach(() => {
  getMock.mockReset();
  settingsStamp = 1000;
  resultsStamp = 2000;
  useSession.setState({ demoMode: false, demoData: null, designMeshId: null });
});

describe('buildProposedComplianceQuery', () => {
  it('serializa parámetros repetidos preservando sector vacío y bench 0', () => {
    const qs = buildProposedComplianceQuery({
      sector: ['', 'Norte'],
      section: ['S01'],
      level: [],
      bench: [0, 2],
    });
    expect(qs).toBe('sector=&sector=Norte&section=S01&bench=0&bench=2');
  });

  it('devuelve cadena vacía para filtros abiertos', () => {
    expect(buildProposedComplianceQuery(EMPTY)).toBe('');
  });
});

describe('useProposedCompliance', () => {
  it('consulta el endpoint con la serialización repetida', async () => {
    getMock.mockResolvedValue({ data: RESPONSE });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useProposedCompliance({ sector: ['Norte'], section: [], level: [], bench: [2] }),
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(result.current.data?.summary?.proposed_global_score).toBe(78.5));
    expect(getMock).toHaveBeenCalledTimes(1);
    expect(getMock.mock.calls[0][0]).toBe('/process/proposed-compliance?sector=Norte&bench=2');
  });

  it('consulta sin query string cuando no hay filtros', async () => {
    getMock.mockResolvedValue({ data: RESPONSE });
    const { Wrapper } = makeWrapper();
    renderHook(() => useProposedCompliance(EMPTY), { wrapper: Wrapper });
    await waitFor(() => expect(getMock.mock.calls[0][0]).toBe('/process/proposed-compliance'));
  });

  it('no consulta la API en modo demo y marca isDemo sin estados falsos', async () => {
    useSession.setState({ demoMode: true });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposedCompliance(EMPTY), { wrapper: Wrapper });
    await Promise.resolve();
    expect(getMock).not.toHaveBeenCalled();
    expect(result.current.isDemo).toBe(true);
    expect(result.current.isPending).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it('al activar demo con caché previa real devuelve data nula sin consultar', async () => {
    getMock.mockResolvedValue({ data: RESPONSE });
    const { Wrapper } = makeWrapper();
    const { result, rerender } = renderHook(() => useProposedCompliance(EMPTY), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.data?.proposal_status).toBe('current'));
    const callsBefore = getMock.mock.calls.length;
    useSession.setState({ demoMode: true });
    rerender();
    expect(result.current.isDemo).toBe(true);
    expect(result.current.data).toBeNull();
    await waitFor(() => {
      expect(getMock.mock.calls.length).toBe(callsBefore);
    });
  });

  it('renueva la query key (y refresca) cuando cambian settings o results', async () => {
    getMock.mockResolvedValue({ data: RESPONSE });
    const { qc, Wrapper } = makeWrapper();
    const { rerender } = renderHook(() => useProposedCompliance(EMPTY), { wrapper: Wrapper });
    await waitFor(() => expect(qc.getQueryCache().getAll()).toHaveLength(1));
    const keys = () => qc.getQueryCache().getAll().map((entry) => JSON.stringify(entry.queryKey));

    settingsStamp = 1001;
    rerender();
    await waitFor(() => expect(qc.getQueryCache().getAll()).toHaveLength(2));

    resultsStamp = 2001;
    rerender();
    await waitFor(() => expect(qc.getQueryCache().getAll()).toHaveLength(3));

    expect(new Set(keys()).size).toBe(3);
  });

  it('expone isError y refetch cuando la consulta falla', async () => {
    getMock.mockRejectedValue(new Error('boom'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposedCompliance(EMPTY), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeNull();
    getMock.mockClear();
    getMock.mockResolvedValue({ data: RESPONSE });
    result.current.refetch();
    await waitFor(() => expect(result.current.data?.proposal_status).toBe('current'));
  });
});
