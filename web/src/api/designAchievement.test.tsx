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
  buildDesignAchievementQuery,
  useDesignAchievement,
  type DesignAchievementResponse,
} from './designAchievement';

const getMock = client.get as unknown as Mock;

const EMPTY = { sector: [], section: [], level: [], bench: [] };

const SUMMARY = {
  global_score: 78.4,
  n_total: 12,
  n_evaluable: 10,
  crest_cumple: 3,
  crest_denom: 4,
  crest_pct: 75,
  toe_cumple: 2,
  toe_denom: 4,
  toe_pct: 50,
  berm_cumple: 1,
  berm_denom: 2,
  berm_pct: 50,
  delta_crest_mean: 0.25,
  delta_toe_mean: -0.1,
};

const RESPONSE: DesignAchievementResponse = {
  session_id: 's1',
  n_total_rows: 12,
  summary: { ...SUMMARY },
  sectors: [{ sector: 'Norte', ...SUMMARY }],
  tolerances: { neg: 0.3, pos: 0.3 },
  tolerances_source: 'session',
  filters: { sector: [], section: [], level: [], bench: [] },
  units: { corrections: 'm', score: '0-100' },
  status_model: 'core',
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

describe('buildDesignAchievementQuery', () => {
  it('serializa parámetros repetidos preservando sector vacío y bench 0', () => {
    const qs = buildDesignAchievementQuery({
      sector: ['', 'Norte'],
      section: ['S01'],
      level: [],
      bench: [0, 2],
    });
    expect(qs).toBe('sector=&sector=Norte&section=S01&bench=0&bench=2');
  });

  it('devuelve cadena vacía para filtros abiertos', () => {
    expect(buildDesignAchievementQuery(EMPTY)).toBe('');
  });
});

describe('useDesignAchievement', () => {
  it('consulta el endpoint con la serialización repetida', async () => {
    getMock.mockResolvedValue({ data: RESPONSE });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useDesignAchievement({ sector: ['Norte'], section: [], level: [], bench: [2] }),
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(result.current.data?.summary.global_score).toBe(78.4));
    expect(getMock).toHaveBeenCalledTimes(1);
    expect(getMock.mock.calls[0][0]).toBe('/process/design-achievement?sector=Norte&bench=2');
  });

  it('no consulta la API en modo demo y marca isDemo sin estados falsos', async () => {
    useSession.setState({ demoMode: true });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDesignAchievement(EMPTY), { wrapper: Wrapper });
    await Promise.resolve();
    expect(getMock).not.toHaveBeenCalled();
    expect(result.current.isDemo).toBe(true);
    expect(result.current.isPending).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it('al activar demo con caché previa real devuelve data nula sin consultar', async () => {
    getMock.mockResolvedValue({ data: RESPONSE });
    const { Wrapper } = makeWrapper();
    const { result, rerender } = renderHook(() => useDesignAchievement(EMPTY), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.data?.summary.global_score).toBe(78.4));
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
    const { rerender } = renderHook(() => useDesignAchievement(EMPTY), { wrapper: Wrapper });
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
});
