import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../../../locales/es.json';
import { useSession } from '../../../../../stores/session';
import { ProfileView } from '../ProfileView';
import type { ProfileViewModel } from '../../domain/types';

vi.mock('../../../ProfilePlanThumbnail', () => ({ ProfilePlanThumbnail: () => null }));
vi.mock('../SectionHeader', () => ({ SectionHeader: () => null }));
vi.mock('../../../../charts/Plot', () => ({ default: () => null }));
vi.mock('../../../../../api/hooks', async () => ({
  ...await vi.importActual<typeof import('../../../../../api/hooks')>('../../../../../api/hooks'),
  useBlastHoles: () => ({ data: undefined }),
  useSections: () => ({ data: [] }),
  useSectionProfiles: () => [],
  useMeshVerticesRoi: () => ({ data: undefined, isLoading: false, error: null }),
}));
vi.mock('../../application', async () => ({
  ...await vi.importActual<typeof import('../../application')>('../../application'),
  useProfileViewModel: () => ({ viewModel, isLoading: false, error: null }),
}));

const baseViewModel: ProfileViewModel = {
  section: { id: 'section-1', name: 'S-01', sector: 'Norte', azimuth: 0, length: 100, origin: [0, 0] },
  lines: [{ kind: 'topo', points: [
    { distance: 0, elevation: 100 },
    { distance: 3, elevation: 92 },
    { distance: 7, elevation: 85 },
    { distance: 10, elevation: 80 },
  ] }],
  benches: [{
    benchNumber: 4, crestElevation: 100, crestDistance: 0, toeElevation: 85,
    toeDistance: 7, height: 15, faceAngle: 65, bermWidth: 8,
    designHeight: 15, designAngle: 65, designBerm: 8, isRamp: false,
    heightStatus: 'CUMPLE', angleStatus: 'CUMPLE', bermStatus: 'CUMPLE',
    status: 'CUMPLE', matched: true, deltaCrest: null, deltaToe: null,
  }],
};
let viewModel: ProfileViewModel = baseViewModel;

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

const TWO_COLUMN_CLASS = 'xl:grid-cols-[minmax(0,1fr)_minmax(260px,min(30%,420px))]';

beforeEach(() => {
  viewModel = baseViewModel;
  localStorage.clear();
  useSession.getState().reset();
  useSession.getState().setSelectedSection('section-1');
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
    unobserve() {}
  });
});

const renderView = () => render(<I18nextProvider i18n={i18n}><ProfileView /></I18nextProvider>);

describe('ProfileView layout', () => {
  it('places the location plan beside the profile chart inside a shared two-column grid', () => {
    const { container } = renderView();
    const chartFrame = container.querySelector<HTMLElement>('[data-slot="profile-chart-frame"]');
    const planPanel = container.querySelector<HTMLElement>('[data-slot="profile-plan-panel"]');

    expect(chartFrame).not.toBeNull();
    expect(planPanel).not.toBeNull();
    const grid = chartFrame?.parentElement;
    expect(grid).toBe(planPanel?.parentElement);
    expect(grid).toHaveClass('grid');
    expect(grid?.className.split(' ')).toContain(TWO_COLUMN_CLASS);
    expect(grid).not.toContainElement(container.querySelector<HTMLElement>('[data-slot="bench-table-frame"]'));
  });

  it('keeps the bench table full width below the chart and plan row', () => {
    const { container } = renderView();
    const chartFrame = container.querySelector<HTMLElement>('[data-slot="profile-chart-frame"]');
    const tableFrame = container.querySelector<HTMLElement>('[data-slot="bench-table-frame"]');

    expect(tableFrame).not.toBeNull();
    expect(chartFrame?.parentElement).not.toContainElement(tableFrame);
    expect(chartFrame?.parentElement?.parentElement).toContainElement(tableFrame);
  });

  it('drops the second column when the plan is collapsed', async () => {
    const user = userEvent.setup();
    const { container } = renderView();
    const planPanel = container.querySelector<HTMLElement>('[data-slot="profile-plan-panel"]');
    const grid = planPanel?.parentElement;

    await user.click(screen.getByRole('button', { name: 'Ubicación en planta' }));

    expect(planPanel).toHaveAttribute('hidden');
    expect(grid?.className.split(' ')).not.toContain(TWO_COLUMN_CLASS);
    expect(grid).not.toHaveClass('xl:grid-cols-[minmax(0,1fr)_400px]');
  });

  it('stretches the plan panel to the chart card height without a fixed width cap', () => {
    const { container } = renderView();
    const planPanel = container.querySelector<HTMLElement>('[data-slot="profile-plan-panel"]');

    expect(planPanel).toHaveClass('flex', 'flex-col', 'min-w-0', 'h-full');
    expect(planPanel).toHaveClass('xl:max-w-none');
    expect(planPanel?.querySelector('#profile-plan-content')).toHaveClass('flex', 'flex-1', 'min-h-0', 'flex-col');
  });

  it('renders chart, plan and table frames without card chrome', () => {
    const { container } = renderView();
    const frames = [
      container.querySelector<HTMLElement>('[data-slot="profile-chart-frame"]'),
      container.querySelector<HTMLElement>('[data-slot="profile-plan-panel"]'),
      container.querySelector<HTMLElement>('[data-slot="bench-table-frame"]'),
    ];

    frames.forEach((frame) => {
      expect(frame).not.toBeNull();
      const tokens = frame?.className.split(' ') ?? [];
      expect(tokens).not.toContain('bg-surface-raised');
      expect(tokens).not.toContain('rounded-lg');
      expect(tokens).not.toContain('border');
      expect(tokens).not.toContain('border-border');
      expect(tokens).not.toContain('shadow');
      expect(tokens).not.toContain('p-3');
      expect(tokens).toContain('min-w-0');
    });
  });

  it('keeps the plan thumbnail title variant on the page background', async () => {
    const { ProfilePlanThumbnail: ActualThumbnail } = await vi.importActual<typeof import('../../../ProfilePlanThumbnail')>('../../../ProfilePlanThumbnail');
    const { container } = render(<I18nextProvider i18n={i18n}><ActualThumbnail sectionId="section-1" showTitle /></I18nextProvider>);
    const thumbnail = container.querySelector<HTMLElement>('[data-slot="profile-plan-thumbnail"]');

    expect(thumbnail).not.toBeNull();
    const tokens = thumbnail?.className.split(' ') ?? [];
    expect(tokens).not.toContain('bg-surface-raised');
    expect(tokens).not.toContain('rounded-lg');
    expect(tokens).not.toContain('border');
    expect(tokens).not.toContain('border-border');
    expect(tokens).not.toContain('shadow');
  });

  it('keeps the toggle in the table header controlling the plan content', async () => {
    const user = userEvent.setup();
    const { container } = renderView();
    const toggle = screen.getByRole('button', { name: 'Ubicación en planta' });
    const content = container.querySelector<HTMLElement>('#profile-plan-content');

    expect(container.querySelector<HTMLElement>('[data-slot="bench-table-frame"]')).toContainElement(toggle);
    expect(toggle).toHaveAttribute('aria-controls', 'profile-plan-content');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(container.querySelector<HTMLElement>('[data-slot="profile-plan-panel"]')).toContainElement(content);
    expect(content).not.toHaveAttribute('hidden');

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(content).toHaveAttribute('hidden');
  });
});
