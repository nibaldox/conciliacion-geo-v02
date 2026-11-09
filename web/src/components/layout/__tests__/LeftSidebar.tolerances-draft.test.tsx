import { act } from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import type { Tolerances } from '../../../api/types';
import { useSession } from '../../../stores/session';
import { LeftSidebar } from '../LeftSidebar';

const updateSpy = vi.hoisted(() => vi.fn());

vi.mock('../../../api/hooks', () => {
  const mutationStub = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useSettings: () => ({ data: SETTINGS }),
    useProcessStatus: () => ({ data: undefined }),
    useSections: () => ({ data: [] }),
    useUpdateSettings: () => ({ mutate: updateSpy, isPending: false }),
    useUploadMesh: mutationStub,
    useDeleteMesh: mutationStub,
    useMeshInfo: () => ({ data: undefined }),
    useInspectDxf: mutationStub,
    useConfirmDxf: mutationStub,
    useCancelDxf: mutationStub,
  };
});

vi.mock('../../mesh/MeshUpload', () => ({ DropZone: () => <div /> }));
vi.mock('../../demo/TryDemoButton', () => ({ TryDemoButton: () => <div /> }));
vi.mock('../../sections/SectionCurveForm', () => ({ SectionCurveForm: () => <div /> }));
vi.mock('../../sections/SectionFileUpload', () => ({ SectionFileUpload: () => <div /> }));
vi.mock('../../sections/SectionList', () => ({ SectionList: () => <div /> }));
vi.mock('../../analysis/ProcessButton', () => ({ ProcessButton: () => <div /> }));
vi.mock('../../analysis/ProcessProgress', () => ({ ProcessProgress: () => <div /> }));
vi.mock('../LanguageToggle', () => ({ LanguageToggle: () => <div /> }));

const TOLERANCES: Tolerances = {
  bench_height: { neg: 1, pos: 1.5 },
  face_angle: { neg: 5, pos: 5 },
  berm_width: { min: 6 },
  inter_ramp_angle: { neg: 3, pos: 2 },
  overall_angle: { neg: 2, pos: 2 },
  crest_toe_deviation: { neg: 1, pos: 1 },
};

const SETTINGS = {
  process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
  tolerances: TOLERANCES,
};

const BENCH_NEG = 'Tolerancia negativa: Altura de banco (m)';
const BENCH_POS = 'Tolerancia positiva: Altura de banco (m)';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });
const keyPathI18n = createInstance();
void keyPathI18n.init({
  lng: 'es',
  resources: { es: { translation: {
    sidebar: { expand: 'LABEL_EXPAND', collapse: 'LABEL_COLLAPSE' },
    ux: {
      step_surfaces: 'LABEL_SURFACES', step_sections: 'LABEL_SECTIONS',
      step_parameters: 'LABEL_PARAMETERS', step_process: 'LABEL_PROCESS',
      locked_hint: 'LABEL_LOCKED',
    },
  } } },
  initAsync: false,
});

function getMutateCalls(): Array<{
  tolerances?: Tolerances;
  process?: { resolution: number };
}> {
  return updateSpy.mock.calls.map((c) => c[0] as { tolerances?: Tolerances; process?: { resolution: number } });
}

function renderSidebar() {
  return render(
    <I18nextProvider i18n={i18n}>
      <LeftSidebar />
    </I18nextProvider>,
  );
}

function renderSidebarWithKeyPathResources() {
  return render(
    <I18nextProvider i18n={keyPathI18n}>
      <LeftSidebar />
    </I18nextProvider>,
  );
}

async function openTolerances(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^[0-9]?Parámetros/ }));
  return {
    neg: screen.getByLabelText(BENCH_NEG) as HTMLInputElement,
    pos: screen.getByLabelText(BENCH_POS) as HTMLInputElement,
  };
}

describe('LeftSidebar — edición rápida de tolerancias (draft + debounce)', () => {
  beforeAll(() => {
    vi.stubGlobal(
      'matchMedia',
      (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: () => false,
      }),
    );
  });

  beforeEach(() => {
    updateSpy.mockClear();
    useSession.getState().reset();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
  });

  it('mantiene el cambio automático a 3D para mallas reales tras usar demo', () => {
    useSession.setState({ demoMode: true, demoData: null, activeWorkspaceView: 'dashboard' });
    renderSidebar();
    expect(useSession.getState().activeWorkspaceView).toBe('3d');
  });

  it('mantiene Dashboard al cargar datos demo con el panel lateral montado', async () => {
    useSession.getState().reset();
    renderSidebar();
    useSession.setState({ demoData: { sections: [] } as never });
    await act(async () => { await useSession.getState().loadDemo(); });
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
  });

  it('mantiene Dashboard al cargar demo desde un estado vacío con secciones abiertas', async () => {
    useSession.getState().reset();
    useSession.setState({ openWorkflowStep: 'sections', activeWorkspaceView: 'dashboard' });
    renderSidebar();
    useSession.setState({ demoData: { sections: [] } as never });
    await act(async () => { await useSession.getState().loadDemo(); });
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
  });

  it('mantiene ambos valores tecleados: dos ediciones antes del debounce preservan neg y pos', async () => {
    const user = userEvent.setup();
    renderSidebar();
    const { neg, pos } = await openTolerances(user);
    await user.clear(neg);
    await user.type(neg, '2.5');
    await user.clear(pos);
    await user.type(pos, '3');
    expect(neg.value).toBe('2.5');
    expect(pos.value).toBe('3');
    await waitForDebounce();
    const tolerancesCalls = getMutateCalls().filter((p) =>
      (p as { tolerances?: unknown }).tolerances !== undefined,
    );
    expect(tolerancesCalls.length).toBeGreaterThan(0);
    const last = tolerancesCalls[tolerancesCalls.length - 1] as {
      tolerances: Tolerances;
      process: { resolution: number };
    };
    expect(last.tolerances).toEqual({
      bench_height: { neg: 2.5, pos: 3 },
      face_angle: { neg: 5, pos: 5 },
      berm_width: { min: 6 },
      inter_ramp_angle: { neg: 3, pos: 2 },
      overall_angle: { neg: 2, pos: 2 },
      crest_toe_deviation: { neg: 1, pos: 1 },
    });
    expect(last.process.resolution).toBe(0.1);
  });

  it('la UI muestra el draft al instante (no revierte al valor del GET congelado)', async () => {
    const user = userEvent.setup();
    renderSidebar();
    const { neg } = await openTolerances(user);
    await user.clear(neg);
    await user.type(neg, '4');
    expect(neg.value).toBe('4');
    expect((screen.getByLabelText(BENCH_POS) as HTMLInputElement).value).toBe('1.5');
  });

  it('el botón guardar no pisa el borrador de tolerancias', async () => {
    const user = userEvent.setup();
    renderSidebar();
    await openTolerances(user);
    const neg = screen.getByLabelText(BENCH_NEG) as HTMLInputElement;
    await user.clear(neg);
    await user.type(neg, '2.5');
    await user.click(screen.getByRole('button', { name: /Guardar|guardar/i }));
    const saved = getMutateCalls().find((p) =>
      (p as { tolerances?: Tolerances }).tolerances?.bench_height?.neg === 2.5,
    );
    expect(saved).toBeDefined();
  });

  it('un re-render desde el GET viejo no deshace la edición pendiente', async () => {
    const user = userEvent.setup();
    const { rerender } = renderSidebar();
    const { neg } = await openTolerances(user);
    await user.clear(neg);
    await user.type(neg, '4');
    rerender(
      <I18nextProvider i18n={i18n}>
        <LeftSidebar />
      </I18nextProvider>,
    );
    expect((screen.getByLabelText(BENCH_NEG) as HTMLInputElement).value).toBe('4');
  });
});

describe('LeftSidebar — definición de secciones por curvas', () => {
  beforeAll(() => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: () => false,
    }));
  });

  beforeEach(() => {
    useSession.getState().reset();
  });

  it('mantiene aria-controls y el foco al alternar un paso por teclado', async () => {
    const user = userEvent.setup();
    renderSidebar();

    const stepButtons = screen.getAllByRole('button').filter((button) => button.hasAttribute('aria-controls'));
    expect(stepButtons).toHaveLength(4);
    for (const button of stepButtons) {
      expect(button).toHaveAttribute('type', 'button');
    }

    const surfacesButton = screen.getByRole('button', { name: /^[0-9]?Superficies/ });
    const panelId = surfacesButton.getAttribute('aria-controls') ?? '';
    expect(surfacesButton).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(panelId)).toBeVisible();

    await user.click(surfacesButton);
    expect(surfacesButton).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById(panelId)).toBeNull();
    expect(document.activeElement).toBe(surfacesButton);

    await user.keyboard('{Enter}');
    expect(surfacesButton).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(panelId)).toBeVisible();
    expect(document.activeElement).toBe(surfacesButton);
  });

  it('resuelve etiquetas compactas desde las claves del flujo y expande sin abrir pasos bloqueados', async () => {
    const user = userEvent.setup();
    useSession.setState({ sidebarCollapsed: true });
    renderSidebarWithKeyPathResources();

    expect(screen.getByRole('button', { name: 'LABEL_EXPAND' })).toBeInTheDocument();
    for (const label of ['LABEL_SURFACES', 'LABEL_SECTIONS', 'LABEL_PARAMETERS', 'LABEL_PROCESS']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'LABEL_SECTIONS' })).toHaveAttribute('title', 'LABEL_SECTIONS — LABEL_LOCKED');
    await user.click(screen.getByRole('button', { name: 'LABEL_SECTIONS' }));
    expect(useSession.getState().sidebarCollapsed).toBe(false);
    expect(useSession.getState().openWorkflowStep).toBe('surfaces');
    expect(screen.getByRole('button', { name: /^[0-9]?LABEL_SECTIONS/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'LABEL_COLLAPSE' })).toBeInTheDocument();
  });

  it('avisa que activa 3D y conserva la curva seleccionada al abrir el formulario', async () => {
    const user = userEvent.setup();
    const selection = { context: null, curveId: 'curva-1', start: null, end: null, rejection: null } as const;
    useSession.setState({
      designMeshId: 'design-1',
      topoMeshId: 'topo-1',
      activeWorkspaceView: 'dashboard',
      curveSelection: selection,
    });
    renderSidebar();
    useSession.getState().setActiveWorkspaceView('dashboard');

    await user.click(screen.getByRole('button', { name: /^[0-9]?Secciones/ }));

    expect(useSession.getState().activeWorkspaceView).toBe('3d');
    expect(useSession.getState().curveSelection).toBe(selection);
    expect(screen.getByRole('note')).toHaveTextContent('La vista 3D se activa automáticamente. Elige una curva en la superficie para definir la sección.');
  });

  it('conserva el manejador de clics del visor 3D con el panel colapsado', () => {
    useSession.setState({ sidebarCollapsed: true });
    const { unmount } = renderSidebar();
    expect(document.querySelector('[data-slot="left-sidebar-collapsed"]')).toBeInTheDocument();
    expect(useSession.getState().mapClickHandler).not.toBeNull();
    unmount();
    expect(useSession.getState().mapClickHandler).toBeNull();
  });
});

async function waitForDebounce() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 560));
  });
}
