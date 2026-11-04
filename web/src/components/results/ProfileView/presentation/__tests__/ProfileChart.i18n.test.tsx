import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../../../i18n';
import { useSession } from '../../../../../stores/session';
import { DEFAULT_FILTER_STATE } from '../../domain/filters';
import type { ProfileViewModel } from '../../domain/types';
import type { UseCrossLinkStateApi } from '../../application';
import { ProfileChart } from '../ProfileChart';

vi.mock('../../../../../api/hooks', async () => ({
  ...await vi.importActual<typeof import('../../../../../api/hooks')>('../../../../../api/hooks'),
  useBlastHoles: () => ({ data: undefined }),
}));

vi.mock('../../../../charts/Plot', () => ({
  default: ({ data, onClick }: {
    data: Array<{ name?: string; meta?: { profileViewRole?: string }; customdata?: unknown[][]; hovertemplate?: string[] | string }>;
    onClick?: (event: { points: Array<{ curveNumber: number; customdata?: unknown }> }) => void;
  }) => {
    const markerIndex = data.findIndex((trace) => trace.meta?.profileViewRole === 'bench-marker');
    const topo = data.find((trace) => trace.name === 'Topografía' || trace.name === 'Topography');
    return (
      <div
        data-testid="profile-plot"
        data-trace-names={JSON.stringify(data.map((trace) => trace.name))}
        data-hover-template={JSON.stringify(topo?.hovertemplate)}
      >
        <button
          type="button"
          data-testid="select-bench"
          onClick={() => {
            const trace = data[markerIndex];
            if (trace && markerIndex >= 0) {
              onClick?.({ points: [{ curveNumber: markerIndex, customdata: trace.customdata?.[0] }] });
            }
          }}
        >
          Select bench
        </button>
      </div>
    );
  },
}));

const viewModel: ProfileViewModel = {
  section: { id: 'section-i18n', name: 'S-10', sector: 'Norte', azimuth: 0, length: 100, origin: [0, 0] },
  lines: [
    { kind: 'design', points: [{ distance: 0, elevation: 100 }, { distance: 10, elevation: 90 }] },
    { kind: 'topo', points: [{ distance: 0, elevation: 99 }, { distance: 10, elevation: 89 }] },
  ],
  benches: [{
    benchNumber: 7, crestElevation: 100, crestDistance: 0, toeElevation: 89,
    toeDistance: 10, height: 11, faceAngle: 45, bermWidth: 4,
    designHeight: 11, designAngle: 45, designBerm: 4, isRamp: false,
    heightStatus: 'CUMPLE', angleStatus: 'CUMPLE', bermStatus: 'CUMPLE',
    status: 'CUMPLE', matched: true, deltaCrest: null, deltaToe: null,
  }],
};

const crossLink: UseCrossLinkStateApi = {
  hovered: null,
  selected: null,
  setHovered: vi.fn(),
  setSelected: vi.fn(),
  clear: vi.fn(),
};

beforeAll(async () => {
  await i18n.changeLanguage('es');
});

beforeEach(() => {
  void i18n.changeLanguage('es');
  vi.clearAllMocks();
  useSession.getState().reset();
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
    unobserve() {}
  });
});

afterEach(() => {
  void i18n.changeLanguage('es');
  vi.unstubAllGlobals();
});

describe('ProfileChart real i18n connection', () => {
  it('changes trace legend and hover labels from the loaded resources without changing bench selection', async () => {
    const { rerender } = render(
      <I18nextProvider i18n={i18n}>
        <ProfileChart viewModel={viewModel} filterState={DEFAULT_FILTER_STATE} crossLink={crossLink} />
      </I18nextProvider>,
    );

    const spanishPlot = screen.getByTestId('profile-plot');
    expect(JSON.parse(spanishPlot.getAttribute('data-trace-names') ?? '[]')).toContain('Diseño');
    expect(JSON.parse(spanishPlot.getAttribute('data-trace-names') ?? '[]')).toContain('Topografía');
    expect(spanishPlot.getAttribute('data-hover-template')).toContain('Ángulo real');

    await i18n.changeLanguage('en');
    rerender(
      <I18nextProvider i18n={i18n}>
        <ProfileChart viewModel={viewModel} filterState={DEFAULT_FILTER_STATE} crossLink={crossLink} />
      </I18nextProvider>,
    );

    const englishPlot = screen.getByTestId('profile-plot');
    expect(JSON.parse(englishPlot.getAttribute('data-trace-names') ?? '[]')).toContain('Design');
    expect(JSON.parse(englishPlot.getAttribute('data-trace-names') ?? '[]')).toContain('Topography');
    expect(englishPlot.getAttribute('data-hover-template')).toContain('Actual angle');

    fireEvent.click(screen.getByTestId('select-bench'));
    expect(crossLink.setSelected).toHaveBeenCalledWith(7);
  });
});
