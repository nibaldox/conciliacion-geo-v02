import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import type { ComponentProps, ReactNode } from 'react';
import { useSession } from '../../../stores/session';
import { useBlastView, type BlastColorTarget } from '../../../stores/blastView';
import { Mesh3DViewer } from '../Mesh3DViewer';

const colorControlsMode = { withholdMapping: false };

vi.mock('../BlastHoleColorControls', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../BlastHoleColorControls')>();
  return {
    BlastHoleColorControls: (props: ComponentProps<typeof actual.BlastHoleColorControls>) =>
      colorControlsMode.withholdMapping ? null : <actual.BlastHoleColorControls {...props} />,
  };
});

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
  useBlastHoles3D: () => ({ data: blastHolesData, isLoading: false, isError: false }),
}));

vi.mock('../BlastHolesLayer', () => ({
  BlastHolesLayer: ({ holes, colorTrajectories, colorCollars, trajectoryColor }: {
    holes: Array<{ key: string; color?: string }>;
    colorTrajectories?: boolean;
    colorCollars?: boolean;
    trajectoryColor?: string;
  }) => (
    <output data-testid="blast-layer" data-colors={JSON.stringify(holes.map((hole) => hole.color ?? null))}
      data-trajectories={String(!!colorTrajectories)} data-collars={String(colorCollars !== false)} data-trajectory-color={trajectoryColor ?? ''} />
  ),
}));

function numericHoles() {
  return {
    session_id: 'session-numeric', section_id: null, corridor_m: null, data_revision: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    holes: [
      { row_id: 'row-1', hole_id: 'H-1', collar: [1, 2, 101], toe: [1, 2, 91], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B1', Kilos_Cargados_real: 100 }, section_relation: null, section_distance_m: null },
      { row_id: 'row-2', hole_id: 'H-2', collar: [3, 4, 303], toe: [3, 4, 293], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B2', Kilos_Cargados_real: 300 }, section_relation: null, section_distance_m: null },
    ],
    summary: { total_loaded: 2, drawable: 2, complete_geometry: 2, collar_only: 0, without_geometry: 0, rejected: 0 },
  };
}

function openConfirmedLayer() {
  fireEvent.click(screen.getByTestId('blast-holes-toggle'));
  fireEvent.click(screen.getByLabelText('blast.confirmSpatial3d'));
  return screen.getByTestId('blast-layer');
}

beforeEach(() => {
  blastHolesData = undefined;
  useSession.getState().reset();
  useBlastView.getState().reset();
});

afterEach(() => {
  cleanup();
  useSession.getState().reset();
  useBlastView.getState().reset();
});

describe('Mesh3DViewer · colores de trayectorias por variable numérica', () => {
  it('colorea las trayectorias cuando la variable numérica tiene mapping válido', () => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });

    render(<Mesh3DViewer />);
    const layer = openConfirmedLayer();

    const colors = JSON.parse(layer.getAttribute('data-colors') ?? '[]');
    expect(colors).toHaveLength(2);
    expect(colors[0]).not.toBeNull();
    expect(colors[0]).not.toBe(colors[1]);
    expect(layer.getAttribute('data-trajectories')).toBe('true');
  });

  it('sin mapping disponible deja las trayectorias sin color y no bloquea la capa', () => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });
    colorControlsMode.withholdMapping = true;

    try {
      render(<Mesh3DViewer />);
      const layer = openConfirmedLayer();
      expect(screen.queryByLabelText('blast.colors.mode')).toBeNull();
      expect(JSON.parse(layer.getAttribute('data-colors') ?? '[]')).toEqual([null, null]);
      expect(layer.getAttribute('data-trajectories')).toBe('false');
      expect(layer.getAttribute('data-trajectory-color')).toBe('#969696');
    } finally {
      colorControlsMode.withholdMapping = false;
    }
  });

  it('un mapping obsoleto no se propaga tras cambiar el filtro con los controles desmontados', () => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });

    render(<Mesh3DViewer />);
    const layer = openConfirmedLayer();
    expect(JSON.parse(layer.getAttribute('data-colors') ?? '[]')[1]).not.toBeNull();

    colorControlsMode.withholdMapping = true;
    try {
      fireEvent.change(screen.getByLabelText('blast.holeFilters.bench'), { target: { value: 'B2' } });
      expect(JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-colors') ?? '[]')).toEqual([null]);
    } finally {
      colorControlsMode.withholdMapping = false;
    }
  });

  it.each<[BlastColorTarget, string, string]>([
    ['both', 'true', 'true'],
    ['collars', 'false', 'true'],
    ['trajectories', 'true', 'false'],
  ])('destino %s: trayectorias=%s, collares=%s', (target, trajectories, collars) => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });
    useBlastView.getState().setColorTarget(target);

    render(<Mesh3DViewer />);
    const layer = openConfirmedLayer();

    expect(layer.getAttribute('data-trajectories')).toBe(trajectories);
    expect(layer.getAttribute('data-collars')).toBe(collars);
    expect(JSON.parse(layer.getAttribute('data-colors') ?? '[]')).toHaveLength(2);
  });

  it('expone un selector de destino accesible que actualiza el store', () => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });

    render(<Mesh3DViewer />);
    openConfirmedLayer();
    const select = screen.getByLabelText('blast.colors.target') as HTMLSelectElement;
    expect(select.disabled).toBe(false);
    expect(Array.from(select.options).map((option) => option.value)).toEqual(['both', 'collars', 'trajectories']);
    fireEvent.change(select, { target: { value: 'collars' } });
    expect(useBlastView.getState().colorTarget).toBe('collars');
    expect(screen.getByTestId('blast-layer').getAttribute('data-trajectories')).toBe('false');
  });

  it('deshabilita el selector de destino sin mapping válido y no colorea', () => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });
    colorControlsMode.withholdMapping = true;

    try {
      render(<Mesh3DViewer />);
      const layer = openConfirmedLayer();
      expect((screen.getByLabelText('blast.colors.target') as HTMLSelectElement).disabled).toBe(true);
      expect(layer.getAttribute('data-trajectories')).toBe('false');
    } finally {
      colorControlsMode.withholdMapping = false;
    }
  });

  it('mantiene el color de trayectorias por categoría', () => {
    blastHolesData = numericHoles();
    useSession.setState({ designMeshId: 'design-numeric', topoMeshId: 'topo-numeric' });

    render(<Mesh3DViewer />);
    const layer = openConfirmedLayer();
    fireEvent.change(screen.getByLabelText('blast.colors.mode'), { target: { value: 'category' } });
    expect(layer.getAttribute('data-trajectories')).toBe('true');
  });
});
