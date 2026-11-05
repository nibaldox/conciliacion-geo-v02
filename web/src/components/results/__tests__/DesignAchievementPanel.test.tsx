import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DesignAchievementPanel } from '../DesignAchievementPanel';
import { EMPTY_RESULT_FILTERS } from '../resultFilters.utils';
import type {
  DesignAchievementResponse,
  DesignAchievementSummary,
} from '../../../api/designAchievement';

const useDesignAchievementMock = vi.fn();
let lastFilters: unknown;
vi.mock('../../../api/designAchievement', () => ({
  useDesignAchievement: (filters: unknown) => {
    lastFilters = filters;
    return useDesignAchievementMock();
  },
}));

function makeSummary(o: Partial<DesignAchievementSummary> = {}): DesignAchievementSummary {
  return {
    global_score: null,
    n_total: 10,
    n_evaluable: 0,
    crest_cumple: 0,
    crest_denom: 0,
    crest_pct: null,
    toe_cumple: 0,
    toe_denom: 0,
    toe_pct: null,
    berm_cumple: 0,
    berm_denom: 0,
    berm_pct: null,
    delta_crest_mean: null,
    delta_toe_mean: null,
    ...o,
  };
}

function makeResponse(
  summary: DesignAchievementSummary = makeSummary(),
  sectors: DesignAchievementResponse['sectors'] = [],
  extra: Partial<DesignAchievementResponse> = {},
): DesignAchievementResponse {
  return {
    session_id: 's1',
    n_total_rows: 10,
    summary,
    sectors,
    tolerances: { neg: 0.3, pos: 0.3 },
    tolerances_source: 'core_default',
    filters: { sector: [], section: [], level: [], bench: [] },
    units: { corrections: 'm', score: '0-100' },
    status_model: 'core',
    warnings: [],
    ...extra,
  };
}

function hookResult(o: Record<string, unknown> = {}) {
  return {
    data: null,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    isDemo: false,
    refetch: vi.fn(),
    ...o,
  };
}

beforeEach(() => {
  lastFilters = undefined;
  useDesignAchievementMock.mockReset();
  useDesignAchievementMock.mockReturnValue(hookResult());
});

describe('DesignAchievementPanel', () => {
  it('estado de carga sin inventar datos', () => {
    useDesignAchievementMock.mockReturnValue(hookResult({ isPending: true }));
    render(<DesignAchievementPanel />);
    expect(screen.getByRole('status').textContent).toMatch(/Cargando/i);
    expect(screen.queryByText(/78[.,]4/)).toBeNull();
  });

  it('nulos: muestra —/Sin datos y 0 evaluables, nunca porcentajes falsos', () => {
    useDesignAchievementMock.mockReturnValue(hookResult({ data: makeResponse() }));
    render(<DesignAchievementPanel />);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Sin datos/).length).toBeGreaterThan(0);
    expect(screen.getByText(/0\s*\/\s*10/)).toBeTruthy();
    expect(screen.queryByText(/(?<!\d)0\s*%/)).toBeNull();
    expect(lastFilters).toBe(EMPTY_RESULT_FILTERS);
  });

  it('metadata.status no_data: mensaje Sin datos + conteos, advertencias y procedencia legibles, sin métricas', () => {
    useDesignAchievementMock.mockReturnValue(
      hookResult({
        data: makeResponse(makeSummary(), [], {
          metadata: {
            source: 'persisted_comparisons',
            status: 'no_data',
            assumptions: ['Global score folds missing elements as zero.'],
          },
          warnings: ['no_evaluable_rows', 'session_tolerance_invalid_using_core_default'],
        }),
      }),
    );
    render(<DesignAchievementPanel />);
    expect(screen.getByText('Sin datos')).toBeTruthy();
    expect(screen.getByText(/10\s*filas/i)).toBeTruthy();
    expect(screen.getByText(/0\s*\/\s*10/)).toBeTruthy();
    expect(screen.getByText(/evaluables?/i)).toBeTruthy();
    expect(screen.getAllByText(/mediciones|predeterminad|tolerancia de sesión|invalid/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/no_evaluable_rows/)).toBeNull();
    expect(screen.queryByText(/session_tolerance_invalid/)).toBeNull();
    expect(screen.queryByText(/Global score folds/i)).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText(/(?<!\d)0\s*%/)).toBeNull();
    expect(screen.getByText(/comparaciones procesadas|persisted comparisons/i)).toBeTruthy();
  });

  it('valores: score global, pesos 40/30/30 con crédito parcial, por elemento y medias firmadas', () => {
    const summary = makeSummary({
      global_score: 78.4,
      n_evaluable: 9,
      crest_cumple: 3,
      crest_denom: 4,
      crest_pct: 75,
      delta_crest_mean: 0.25,
      toe_cumple: 2,
      toe_denom: 3,
      toe_pct: 66.7,
      delta_toe_mean: -0.1,
      berm_cumple: 1,
      berm_denom: 2,
      berm_pct: 50,
    });
    useDesignAchievementMock.mockReturnValue(hookResult({ data: makeResponse(summary) }));
    render(<DesignAchievementPanel filters={{ sector: ['Norte'], section: [], level: [], bench: [] }} />);
    expect(screen.getByText(/78[.,]4/)).toBeTruthy();
    expect(screen.getByText(/75\s*%/)).toBeTruthy();
    expect(screen.getByText(/\+0[.,]25\s*m/)).toBeTruthy();
    expect(screen.getByText(/-0[.,]1\s*m|−0[.,]1\s*m/)).toBeTruthy();
    expect(screen.getByText(/Puntaje de Logro Diseño|Design achievement score/i)).toBeTruthy();
    expect(screen.getByText(/Pesos de Logro Diseño|Design achievement weights/i)).toBeTruthy();
    expect(screen.getByText('Pata')).toBeTruthy();
    expect(screen.getByText(/40\s*%/)).toBeTruthy();
    expect(screen.getByText(/[Cc]rédito parcial|partial credit/)).toBeTruthy();
    expect(screen.getByText(/Tolerancia|Tolerance/i)).toBeTruthy();
    expect(lastFilters).toEqual({ sector: ['Norte'], section: [], level: [], bench: [] });
  });

  it('tabla de sectores: n evaluables y sector vacío mantiene identidad como “Sin sector”', () => {
    const filled = makeSummary({
      global_score: 50,
      n_evaluable: 4,
      crest_cumple: 1,
      crest_denom: 2,
      crest_pct: 50,
      toe_cumple: 1,
      toe_denom: 2,
      toe_pct: 50,
    });
    const sectors = [
      { sector: '', ...makeSummary({ global_score: 40, n_evaluable: 2 }) },
      { sector: 'Norte', ...filled },
    ];
    useDesignAchievementMock.mockReturnValue(hookResult({ data: makeResponse(filled, sectors) }));
    render(<DesignAchievementPanel />);
    expect(screen.getByText(/Sin sector/)).toBeTruthy();
    expect(screen.getByText('Norte')).toBeTruthy();
    expect(screen.getByText(/n evaluables?/i)).toBeTruthy();
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(3);
  });

  it('error: mensaje con rol alert y reintento, sin falsos ceros', () => {
    const refetch = vi.fn();
    useDesignAchievementMock.mockReturnValue(
      hookResult({ isError: true, error: new Error('boom'), refetch }),
    );
    render(<DesignAchievementPanel />);
    expect(screen.getByRole('alert').textContent).toMatch(/boom|error/i);
    fireEvent.click(screen.getByRole('button', { name: /Reintentar|Retry/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/78[.,]4/)).toBeNull();
  });

  it('demo: aviso explícito y ninguna métrica fabricada', () => {
    useDesignAchievementMock.mockReturnValue(hookResult({ isDemo: true }));
    render(<DesignAchievementPanel />);
    expect(screen.getByRole('status').textContent).toMatch(/no disponible/i);
    expect(screen.queryByText(/%/)).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
