import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import type { ReactNode } from 'react';
import { useSession } from '../../../stores/session';
import { createBlastViewContextKey, useBlastView } from '../../../stores/blastView';
import { Mesh3DViewer } from '../Mesh3DViewer';

const REV_A = 'a'.repeat(64);
const REV_B = 'b'.repeat(64);
const SESSION_ID = 'session-view';
const DESIGN_ID = 'design-view';
const TOPO_ID = 'topo-view';

interface HoleFixture {
  row_id: string; hole_id: string; collar: number[] | null; toe: number[] | null; geometry_status: string;
  provenance: Record<string, unknown>; attributes: Record<string, unknown>; section_relation: string | null; section_distance_m: number | null;
}

let blastHolesData: {
  session_id: string; section_id: number | null; corridor_m: number | null; data_revision: string | null;
  holes: HoleFixture[];
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
  BlastHolesLayer: ({ holes }: { holes: Array<{ key: string; color?: string }> }) => (
    <output data-testid="blast-layer" data-holes={JSON.stringify(holes.map((hole) => hole.key))}
      data-colors={JSON.stringify(holes.map((hole) => hole.color ?? null))} />
  ),
}));

function blastFixture(dataRevision: string | null): NonNullable<typeof blastHolesData> {
  return {
    session_id: SESSION_ID, section_id: null, corridor_m: null, data_revision: dataRevision,
    holes: [
      { row_id: 'row-1', hole_id: 'H-1', collar: [1, 2, 101], toe: [1, 2, 91], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B1', Kilos_Cargados_real: 100 }, section_relation: null, section_distance_m: null },
      { row_id: 'row-2', hole_id: 'H-2', collar: [3, 4, 303], toe: [3, 4, 293], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B2', Kilos_Cargados_real: 300 }, section_relation: null, section_distance_m: null },
    ],
    summary: { total_loaded: 2, drawable: 2, complete_geometry: 2, collar_only: 0, without_geometry: 0, rejected: 0 },
  };
}

function contextFor(dataRevision: string): string {
  return createBlastViewContextKey(SESSION_ID, DESIGN_ID, TOPO_ID, dataRevision) as string;
}

function toggleLayer(): void {
  const toggle = screen.getByTestId('blast-holes-toggle') as HTMLInputElement;
  if (!toggle.checked) fireEvent.click(toggle);
}

function confirmCheckbox(): HTMLInputElement {
  return screen.getByLabelText('blast.confirmSpatial3d') as HTMLInputElement;
}

function openConfirmedLayer(): void {
  toggleLayer();
  if (!confirmCheckbox().checked) fireEvent.click(confirmCheckbox());
}

beforeEach(() => {
  blastHolesData = undefined;
  useSession.getState().reset();
  useBlastView.getState().reset();
  useSession.setState({ designMeshId: DESIGN_ID, topoMeshId: TOPO_ID });
});

afterEach(() => {
  cleanup();
  useSession.getState().reset();
  useBlastView.getState().reset();
});

describe('Mesh3DViewer · estado de capa de pozos en blastView', () => {
  it('conserva capa, confirmación, paleta y filtro tras desmontar y volver a montar', () => {
    blastHolesData = blastFixture(REV_A);

    render(<Mesh3DViewer mode="blast" />);
    openConfirmedLayer();
    fireEvent.change(screen.getByLabelText('blast.colors.palette'), { target: { value: 'Viridis' } });
    fireEvent.change(screen.getByLabelText('blast.holeFilters.bench'), { target: { value: 'B2' } });
    expect(JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-holes') ?? '[]')).toEqual(['row-2']);

    cleanup();
    render(<Mesh3DViewer mode="blast" />);

    expect((screen.getByTestId('blast-holes-toggle') as HTMLInputElement).checked).toBe(true);
    expect(confirmCheckbox().checked).toBe(true);
    expect((screen.getByLabelText('blast.colors.palette') as HTMLSelectElement).value).toBe('Viridis');
    expect((screen.getByLabelText('blast.holeFilters.bench') as HTMLSelectElement).value).toBe('B2');
    expect(JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-holes') ?? '[]')).toEqual(['row-2']);
  });

  it('invalida la confirmación y no dibuja la capa cuando cambia data_revision con la misma sesión y mallas', () => {
    blastHolesData = blastFixture(REV_A);

    const { rerender } = render(<Mesh3DViewer />);
    openConfirmedLayer();
    expect(screen.getByTestId('blast-layer')).toBeTruthy();
    expect(useBlastView.getState().confirmedSpatialContext).toBe(contextFor(REV_A));
    fireEvent.change(screen.getByLabelText('blast.colors.palette'), { target: { value: 'Viridis' } });
    useSession.getState().setSelectedBlastHoleRowId('row-1');

    blastHolesData = blastFixture(REV_B);
    rerender(<Mesh3DViewer />);

    expect(screen.queryByTestId('blast-layer')).toBeNull();
    expect(confirmCheckbox().checked).toBe(false);
    expect(confirmCheckbox().disabled).toBe(false);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
    expect(useBlastView.getState().contextKey).toBe(contextFor(REV_B));
    expect(useSession.getState().selectedBlastHoleRowId).toBeNull();
    expect(useBlastView.getState().colorConfig.palette).toBe('Viridis');

    fireEvent.click(confirmCheckbox());
    expect(screen.getByTestId('blast-layer')).toBeTruthy();
    expect(useBlastView.getState().confirmedSpatialContext).toBe(contextFor(REV_B));
  });

  it('con data_revision nula deshabilita la confirmación, no dibuja la capa y no reutiliza una confirmación previa', () => {
    blastHolesData = blastFixture(REV_A);

    const { rerender } = render(<Mesh3DViewer />);
    openConfirmedLayer();
    expect(screen.getByTestId('blast-layer')).toBeTruthy();

    blastHolesData = blastFixture(null);
    rerender(<Mesh3DViewer />);

    expect(screen.queryByTestId('blast-layer')).toBeNull();
    expect(confirmCheckbox().disabled).toBe(true);
    expect(confirmCheckbox().checked).toBe(false);
    expect(screen.getByText(/blast\.spatialRevisionMissing/)).toBeTruthy();
    expect(useBlastView.getState().contextKey).toBeNull();
    expect(useBlastView.getState().confirmedSpatialContext).not.toBeNull();

    blastHolesData = blastFixture(REV_A);
    rerender(<Mesh3DViewer />);

    expect(confirmCheckbox().disabled).toBe(false);
    expect(confirmCheckbox().checked).toBe(true);
    expect(screen.getByTestId('blast-layer')).toBeTruthy();
  });

  it('una revisión distinta tras un nulo exige reconfirmar y no reutiliza la confirmación previa', () => {
    blastHolesData = blastFixture(REV_A);

    const { rerender } = render(<Mesh3DViewer />);
    openConfirmedLayer();

    blastHolesData = blastFixture(null);
    rerender(<Mesh3DViewer />);
    blastHolesData = blastFixture(REV_B);
    rerender(<Mesh3DViewer />);

    expect(confirmCheckbox().checked).toBe(false);
    expect(screen.queryByTestId('blast-layer')).toBeNull();
  });

  it('desmarcar la confirmación oculta la capa pero conserva paleta y filtro', () => {
    blastHolesData = blastFixture(REV_A);

    render(<Mesh3DViewer mode="blast" />);
    openConfirmedLayer();
    fireEvent.change(screen.getByLabelText('blast.colors.palette'), { target: { value: 'Viridis' } });
    fireEvent.change(screen.getByLabelText('blast.holeFilters.bench'), { target: { value: 'B2' } });

    fireEvent.click(confirmCheckbox());

    expect(screen.queryByTestId('blast-layer')).toBeNull();
    expect(confirmCheckbox().checked).toBe(false);
    expect(useBlastView.getState().confirmedSpatialContext).toBeNull();
    expect(useBlastView.getState().showBlastHoles).toBe(true);
    expect(useBlastView.getState().colorConfig.palette).toBe('Viridis');
    expect(useBlastView.getState().filters.bench).toBe('B2');

    fireEvent.click(confirmCheckbox());
    expect(useBlastView.getState().colorConfig.palette).toBe('Viridis');
    expect((screen.getByLabelText('blast.colors.palette') as HTMLSelectElement).value).toBe('Viridis');
    expect((screen.getByLabelText('blast.holeFilters.bench') as HTMLSelectElement).value).toBe('B2');
    expect(JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-holes') ?? '[]')).toEqual(['row-2']);
  });
});
