import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import type { ComponentProps, ReactNode } from 'react';
import { useSession } from '../../../stores/session';
import { useBlastView } from '../../../stores/blastView';
import { Mesh3DViewer } from '../Mesh3DViewer';

let blastHolesData: {
  session_id: string; section_id: number | null; corridor_m: number | null; data_revision?: string | null;
  holes: Array<{ row_id: string; hole_id: string; collar: number[] | null; toe: number[] | null; geometry_status: string; provenance: Record<string, unknown>; attributes: Record<string, unknown>; section_relation: string | null; section_distance_m: number | null }>;
  summary: { total_loaded: number; drawable: number; complete_geometry: number; collar_only: number; without_geometry: number; rejected: number };
} | undefined;

const fakeView = {
  raycaster: { params: {} as Record<string, unknown> },
  camera: new THREE.PerspectiveCamera(),
  size: { width: 800, height: 600 },
  gl: { domElement: document.createElement('canvas') },
};

vi.mock('@react-three/fiber', () => ({
  Canvas: (props: { children?: ReactNode }) => <div data-testid="canvas">{props.children}</div>,
  useFrame: () => undefined,
  useThree: () => fakeView,
}));

vi.mock('@react-three/drei', () => ({
  Html: (props: { children?: ReactNode }) => <div>{props.children}</div>,
  OrbitControls: () => null,
  GizmoHelper: (props: { children?: ReactNode }) => <>{props.children}</>,
  GizmoViewport: () => null,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../../stores/theme', () => ({
  useTheme: (selector: (state: { isDark: boolean }) => unknown) => selector({ isDark: false }),
}));

vi.mock('../../../api/hooks', () => ({
  useMeshVertices: (id: string | null) => ({
    data: id === null ? undefined : { x: [0, 10, 0, 10], y: [0, 0, 10, 10], z: [0, 0, 0, 0] },
    isLoading: false,
  }),
  useMeshBreaklines: () => ({ data: undefined, isLoading: false }),
  useSections: () => ({ data: [] }),
  useResults: () => ({ data: [] }),
  useHorizontalDeviationMesh: () => ({ data: undefined, isFetching: false, isError: false, refetch: vi.fn() }),
}));

vi.mock('../useBlastHoles3D', () => ({
  useBlastHoles3D: (...args: unknown[]) => {
    holesHookCalls.push(args);
    return { data: blastHolesData, isLoading: false, isError: false };
  },
}));

const holesHookCalls: unknown[][] = [];

const colorControlsMode = { freezeUpdates: false };

vi.mock('../BlastHoleColorControls', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../BlastHoleColorControls')>();
  return {
    BlastHoleColorControls: (props: ComponentProps<typeof actual.BlastHoleColorControls>) => (
      <actual.BlastHoleColorControls
        {...props}
        onColorsChange={colorControlsMode.freezeUpdates ? () => undefined : props.onColorsChange}
      />
    ),
  };
});

vi.mock('../BlastHolesLayer', () => ({
  BlastHolesLayer: ({ holes }: { holes: Array<{ key: string; color?: string }> }) => (
    <output data-testid="blast-layer" data-colors={JSON.stringify(holes.map((hole) => hole.color ?? null))} />
  ),
}));

function numericHoles() {
  return {
    session_id: 'session-layout', section_id: null, corridor_m: null, data_revision: 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
    holes: [
      { row_id: 'row-1', hole_id: 'H-1', collar: [1, 2, 101], toe: [1, 2, 91], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B1', Kilos_Cargados_real: 100 }, section_relation: null, section_distance_m: null },
      { row_id: 'row-2', hole_id: 'H-2', collar: [3, 4, 303], toe: [3, 4, 293], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B2', Kilos_Cargados_real: 300 }, section_relation: null, section_distance_m: null },
    ],
    summary: { total_loaded: 2, drawable: 2, complete_geometry: 2, collar_only: 0, without_geometry: 0, rejected: 0 },
  };
}

function setSources() {
  blastHolesData = numericHoles();
  useSession.setState({ designMeshId: 'design-layout', topoMeshId: 'topo-layout' });
}

function confirmSpatial() {
  fireEvent.click(screen.getByLabelText('blast.confirmSpatial3d'));
}

function follows(a: Element, b: Element): boolean {
  return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

beforeEach(() => {
  blastHolesData = undefined;
  useSession.getState().reset();
  useBlastView.getState().reset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useSession.getState().reset();
  useBlastView.getState().reset();
});

describe('Mesh3DViewer · modo general', () => {
  it('conserva el panel flotante de capas y no añade el layout de pozos', () => {
    setSources();
    render(<Mesh3DViewer />);

    expect(screen.getByTestId('mesh-layer-panel')).toBeTruthy();
    expect(screen.queryByTestId('blast-view-panel')).toBeNull();
    expect(screen.queryByTestId('blast-legend-strip')).toBeNull();
    expect(screen.queryByTestId('blast-view-toolbar')).toBeNull();
  });

  it('no activa la capa de pozos al montar', () => {
    setSources();
    render(<Mesh3DViewer />);

    expect(useBlastView.getState().showBlastHoles).toBe(false);
  });

  it('tras haber activado la capa en Tronadura, la vista general arranca sin capa ni consulta de pozos', () => {
    setSources();
    const blast = render(<Mesh3DViewer mode="blast" />);
    expect(useBlastView.getState().showBlastHoles).toBe(true);
    blast.unmount();

    holesHookCalls.length = 0;
    render(<Mesh3DViewer />);

    expect((screen.getByTestId('blast-holes-toggle') as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByTestId('blast-layer')).toBeNull();
    expect(holesHookCalls.length).toBeGreaterThan(0);
    for (const args of holesHookCalls) expect(args[0]).toBe(false);
  });
});

describe('Mesh3DViewer · modo blast', () => {
  it('sustituye el panel flotante por el aside acoplado y no lo superpone', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    expect(screen.getByTestId('blast-view-panel').tagName).toBe('ASIDE');
    expect(screen.queryByTestId('mesh-layer-panel')).toBeNull();
  });

  it('activa la capa de pozos al montar', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    expect(useBlastView.getState().showBlastHoles).toBe(true);
    expect((screen.getByTestId('blast-holes-toggle') as HTMLInputElement).checked).toBe(true);
  });

  it('monta un único canvas', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    expect(screen.getAllByTestId('canvas')).toHaveLength(1);
  });

  it('muestra la barra superior con los toggles de capas y el botón de panel fuera del aside', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    const toolbar = screen.getByTestId('blast-view-toolbar');
    const aside = screen.getByTestId('blast-view-panel');
    expect(aside.contains(toolbar)).toBe(false);
    expect(within(toolbar).getByTestId('blast-holes-toggle')).toBeTruthy();
    expect(within(toolbar).getByRole('checkbox', { name: /viewer.layer_topo/ })).toBeTruthy();
    expect(within(toolbar).getByRole('checkbox', { name: /viewer.layer_design/ })).toBeTruthy();
    expect(within(toolbar).getByRole('checkbox', { name: /viewer.layer_sections/ })).toBeTruthy();
    expect(within(toolbar).getByText('blast.viewPanel.visibleCount')).toBeTruthy();
    expect(within(toolbar).getByRole('button', { name: 'blast.viewPanel.hide' })).toBeTruthy();
  });

  it('el botón de panel expresa aria-expanded, controla el aside y lo oculta', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    const aside = screen.getByTestId('blast-view-panel');
    const button = screen.getByRole('button', { name: 'blast.viewPanel.hide' });
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(button.getAttribute('aria-controls')).toBe(aside.id);
    expect(aside.id).not.toBe('');
    expect(aside.hidden).toBe(false);

    fireEvent.click(button);
    const collapsed = screen.getByRole('button', { name: 'blast.viewPanel.show' });
    expect(collapsed.getAttribute('aria-expanded')).toBe('false');
    expect(aside.hidden).toBe(true);

    fireEvent.click(collapsed);
    expect(screen.getByRole('button', { name: 'blast.viewPanel.hide' }).getAttribute('aria-expanded')).toBe('true');
    expect(aside.hidden).toBe(false);
  });

  it('empieza plegado en viewport estrecho', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('max-width'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    }));
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    expect(screen.getByTestId('blast-view-panel').hidden).toBe(true);
    expect(screen.getByRole('button', { name: 'blast.viewPanel.show' }).getAttribute('aria-expanded')).toBe('false');
  });

  it('el aside tiene ancho acoplado y scroll propio', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    const aside = screen.getByTestId('blast-view-panel');
    expect(aside.className).toContain('md:w-[340px]');
    expect(aside.className).toContain('overflow-y-auto');
  });

  it('la franja de leyenda está fuera del aside y muestra la leyenda del mapping actual', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);
    confirmSpatial();

    const strip = screen.getByTestId('blast-legend-strip');
    const aside = screen.getByTestId('blast-view-panel');
    expect(aside.contains(strip)).toBe(false);
    expect(within(strip).getByLabelText('blast.colors.legendContinuous')).toBeTruthy();
    expect(within(aside).queryByLabelText('blast.colors.legendContinuous')).toBeNull();
  });

  it('la franja de leyenda conserva la última leyenda válida mientras llega el nuevo mapping', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);
    confirmSpatial();
    expect(within(screen.getByTestId('blast-legend-strip')).getByLabelText('blast.colors.legendContinuous')).toBeTruthy();

    colorControlsMode.freezeUpdates = true;
    try {
      fireEvent.change(screen.getByLabelText('blast.holeFilters.bench'), { target: { value: 'B2' } });
      const strip = screen.getByTestId('blast-legend-strip');
      expect(within(strip).getByLabelText('blast.colors.legendContinuous')).toBeTruthy();
      expect(within(strip).queryByText('blast.viewPanel.legendHelp')).toBeNull();
    } finally {
      colorControlsMode.freezeUpdates = false;
    }
  });

  it('la franja de leyenda permanece aunque el panel esté plegado', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);
    confirmSpatial();

    fireEvent.click(screen.getByRole('button', { name: 'blast.viewPanel.hide' }));
    expect(screen.getByTestId('blast-view-panel').hidden).toBe(true);
    expect(within(screen.getByTestId('blast-legend-strip')).getByLabelText('blast.colors.legendContinuous')).toBeTruthy();
  });

  it('ordena los controles del aside: confirmación, sección, filtros, color y destino', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);
    confirmSpatial();

    const aside = screen.getByTestId('blast-view-panel');
    const confirm = screen.getByLabelText('blast.confirmSpatial3d');
    const section = screen.getByLabelText('blast.sectionSelect');
    const filters = screen.getByLabelText('blast.holeFilters.bench');
    const colorMode = screen.getByLabelText('blast.colors.mode');
    const target = screen.getByLabelText('blast.colors.target');
    [confirm, section, filters, colorMode, target].forEach((element) => expect(aside.contains(element)).toBe(true));
    expect(follows(confirm, section)).toBe(true);
    expect(follows(section, filters)).toBe(true);
    expect(follows(filters, colorMode)).toBe(true);
    expect(follows(colorMode, target)).toBe(true);
  });

  it('la confirmación espacial sigue siendo obligatoria antes de mostrar controles de pozos', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);

    expect(screen.queryByLabelText('blast.sectionSelect')).toBeNull();
    expect(screen.queryByLabelText('blast.colors.mode')).toBeNull();
    const strip = screen.queryByTestId('blast-legend-strip');
    expect(strip === null || within(strip).queryByLabelText('blast.colors.legendContinuous') === null).toBe(true);
  });

  it('los controles generales quedan plegados dentro de un details del aside', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);
    confirmSpatial();

    const aside = screen.getByTestId('blast-view-panel');
    const deviation = screen.getByTestId('horizontal-deviation-toggle');
    const details = deviation.closest('details');
    expect(details).not.toBeNull();
    expect(aside.contains(details as Element)).toBe(true);
    expect(details?.open).toBe(false);
    expect(follows(screen.getByLabelText('blast.colors.target'), details as Element)).toBe(true);
  });

  it('el color de pozos llega a la capa 3D sin cambiar el destino por defecto', () => {
    setSources();
    render(<Mesh3DViewer mode="blast" />);
    confirmSpatial();

    const colors = JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-colors') ?? '[]');
    expect(colors).toHaveLength(2);
    expect(colors[0]).not.toBeNull();
    expect(useBlastView.getState().colorTarget).toBe('both');
  });
});
