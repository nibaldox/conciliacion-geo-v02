import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import { useSession } from '../../../stores/session';
import { LeftSidebar } from '../LeftSidebar';

const sectionsState = vi.hoisted(() => ({ data: [] as Array<{ id: string }> }));
const processState = vi.hoisted(() => ({ data: undefined as { status: string } | undefined }));

vi.mock('../../../api/hooks', () => {
  const mutationStub = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useSettings: () => ({ data: undefined }),
    useProcessStatus: () => ({ data: processState.data }),
    useSections: () => ({ data: sectionsState.data }),
    useUpdateSettings: mutationStub,
  };
});

vi.mock('../../mesh/MeshUpload', () => ({ DropZone: () => <div data-testid="drop-zone" /> }));
vi.mock('../../demo/TryDemoButton', () => ({ TryDemoButton: () => <div /> }));
vi.mock('../../sections/SectionCurveForm', () => ({ SectionCurveForm: () => <div /> }));
vi.mock('../../sections/SectionFileUpload', () => ({ SectionFileUpload: () => <div /> }));
vi.mock('../../sections/SectionList', () => ({ SectionList: () => <div /> }));
vi.mock('../../analysis/ProcessButton', () => ({ ProcessButton: () => <div data-testid="process-button" /> }));
vi.mock('../../analysis/ProcessProgress', () => ({ ProcessProgress: () => <div /> }));
vi.mock('../LanguageToggle', () => ({ LanguageToggle: () => <div /> }));

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

function renderSidebar() {
  return render(
    <I18nextProvider i18n={i18n}>
      <LeftSidebar />
    </I18nextProvider>,
  );
}

function stepButton(key: string): HTMLElement {
  const element = document.getElementById(`workflow-step-${key}`);
  if (!element) throw new Error(`missing step ${key}`);
  return element;
}

describe('LeftSidebar — flujo de trabajo vertical', () => {
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
    sectionsState.data = [];
    processState.data = undefined;
    useSession.getState().reset();
  });

  it('renderiza los cuatro pasos en orden con el título del flujo', () => {
    renderSidebar();
    expect(screen.getByRole('heading', { name: 'Flujo de trabajo' })).toBeInTheDocument();
    const controls = document.querySelector('[data-slot="project-controls"]');
    const buttons = Array.from(controls?.querySelectorAll('button[aria-controls]') ?? []);
    expect(buttons.map((button) => button.id)).toEqual([
      'workflow-step-surfaces',
      'workflow-step-sections',
      'workflow-step-parameters',
      'workflow-step-process',
    ]);
    expect(buttons[0]).toHaveTextContent('Superficies');
    expect(buttons[1]).toHaveTextContent('Secciones');
    expect(buttons[2]).toHaveTextContent('Parámetros');
    expect(buttons[3]).toHaveTextContent('Procesar');
  });

  it('bloquea los pasos dependientes cuando no hay mallas', () => {
    renderSidebar();
    expect(stepButton('surfaces')).toBeEnabled();
    expect(stepButton('surfaces')).toHaveAttribute('data-state', 'current');
    for (const key of ['sections', 'parameters', 'process']) {
      expect(stepButton(key)).toBeDisabled();
      expect(stepButton(key)).toHaveAttribute('data-state', 'locked');
      expect(stepButton(key).closest('[title]')).toHaveAttribute('title', 'Disponible al completar el paso anterior');
    }
    expect(stepButton('surfaces')).toHaveTextContent('Cargue diseño y topografía');
    expect(stepButton('process')).toHaveTextContent('Complete los pasos anteriores');
  });

  it('expande un paso al hacer clic y colapsa el anterior', async () => {
    const user = userEvent.setup();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
    sectionsState.data = [{ id: 's-1' }, { id: 's-2' }];
    renderSidebar();

    expect(stepButton('surfaces')).toHaveAttribute('aria-expanded', 'true');
    expect(stepButton('sections')).toHaveTextContent('2 secciones definidas');
    expect(stepButton('process')).toHaveTextContent('Listo para procesar');

    await user.click(stepButton('process'));
    expect(stepButton('process')).toHaveAttribute('aria-expanded', 'true');
    expect(stepButton('surfaces')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByTestId('process-button')).toBeInTheDocument();
    expect(useSession.getState().openWorkflowStep).toBe('process');

    await user.click(stepButton('process'));
    expect(useSession.getState().openWorkflowStep).toBeNull();
  });

  it('avanza al siguiente paso cuando uno se completa, pero no al montar', () => {
    renderSidebar();
    expect(useSession.getState().openWorkflowStep).toBe('surfaces');

    act(() => {
      useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
    });
    expect(useSession.getState().openWorkflowStep).toBe('sections');
    expect(useSession.getState().activeWorkspaceView).toBe('3d');
  });

  it('contrae el paso abierto cuando el último paso se completa', () => {
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
    sectionsState.data = [{ id: 's-1' }];
    const { rerender } = renderSidebar();
    act(() => {
      useSession.setState({ openWorkflowStep: 'process' });
    });
    expect(stepButton('process')).toHaveAttribute('aria-expanded', 'true');

    processState.data = { status: 'complete' };
    rerender(
      <I18nextProvider i18n={i18n}>
        <LeftSidebar />
      </I18nextProvider>,
    );
    expect(useSession.getState().openWorkflowStep).toBeNull();
    for (const key of ['surfaces', 'sections', 'parameters', 'process']) {
      expect(stepButton(key)).toHaveAttribute('data-state', 'done');
      expect(stepButton(key)).toHaveAttribute('aria-expanded', 'false');
    }
  });

  it('contrae todos los pasos cuando la demo los completa a la vez', () => {
    const { rerender } = renderSidebar();
    expect(useSession.getState().openWorkflowStep).toBe('surfaces');

    sectionsState.data = [{ id: 's-1' }];
    processState.data = { status: 'complete' };
    act(() => {
      useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });
    });
    rerender(
      <I18nextProvider i18n={i18n}>
        <LeftSidebar />
      </I18nextProvider>,
    );
    expect(useSession.getState().openWorkflowStep).toBeNull();
    expect(stepButton('sections')).toHaveAttribute('aria-expanded', 'false');
  });

  it('no contrae al montar un proyecto ya completo', () => {
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1', openWorkflowStep: 'parameters' });
    sectionsState.data = [{ id: 's-1' }];
    processState.data = { status: 'complete' };
    renderSidebar();
    expect(useSession.getState().openWorkflowStep).toBe('parameters');
  });

  it('no incluye la barra de vistas en el panel lateral', () => {
    const { unmount } = renderSidebar();
    expect(document.querySelector('[data-slot="views-toolbar"]')).toBeNull();
    unmount();

    useSession.setState({ sidebarCollapsed: true });
    renderSidebar();
    expect(document.querySelector('[data-slot="left-sidebar-collapsed"]')).toBeInTheDocument();
    expect(document.querySelector('[data-slot="views-toolbar"]')).toBeNull();
  });

  it('en modo contraído muestra los pasos y abre el elegido al expandir', async () => {
    const user = userEvent.setup();
    useSession.setState({ sidebarCollapsed: true, designMeshId: 'design-1', topoMeshId: 'topo-1' });
    renderSidebar();

    const surfaces = screen.getByRole('button', { name: 'Superficies' });
    expect(surfaces).toHaveAttribute('data-state', 'done');
    expect(screen.getByRole('button', { name: 'Procesar' })).toHaveAttribute('data-state', 'locked');

    await user.click(screen.getByRole('button', { name: 'Parámetros' }));
    expect(useSession.getState().sidebarCollapsed).toBe(false);
    expect(stepButton('parameters')).toHaveAttribute('aria-expanded', 'true');
  });
});
