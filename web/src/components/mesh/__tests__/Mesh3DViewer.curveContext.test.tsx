import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import type { ReactNode } from 'react';
import type { ContourData } from '../../../api/types';
import type { CurveAnchor } from '../../sections/curveSelectionState';
import { useSession } from '../../../stores/session';
import { useBlastView } from '../../../stores/blastView';
import { Mesh3DViewer } from '../Mesh3DViewer';
import { curveContextsEqual, resolveCurveContextAction } from '../curveContextSync';

let contourData: ContourData | undefined;
let sectionData: Array<{ id: string; name: string; origin: [number, number]; azimuth: number; length: number; sector: string }> = [];
let blastHolesData: {
  session_id: string; section_id: number | null; corridor_m: number | null; data_revision?: string | null;
  holes: Array<{ row_id: string; hole_id: string; collar: number[] | null; toe: number[] | null; geometry_status: string; provenance: Record<string, unknown>; attributes: Record<string, unknown>; section_relation: string | null; section_distance_m: number | null }>;
  summary: { total_loaded: number; drawable: number; complete_geometry: number; collar_only: number; without_geometry: number; rejected: number };
} | undefined;
const blastHoleHookCalls: Array<[boolean, number | null, string]> = [];

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
  Html: (props: { children?: ReactNode }) => <div data-testid="curve-html">{props.children}</div>,
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
  useMeshBreaklines: () => ({ data: contourData, isLoading: false }),
  useSections: () => ({ data: sectionData }),
  useResults: () => ({ data: [] }),
  useHorizontalDeviationMesh: () => ({
    data: undefined,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('../useBlastHoles3D', () => ({
  useBlastHoles3D: (enabled: boolean, sectionId: number | null, sectionGeometry: string) => {
    blastHoleHookCalls.push([enabled, sectionId, sectionGeometry]);
    return { data: blastHolesData, isLoading: false, isError: false };
  },
}));

vi.mock('../BlastHolesLayer', () => ({
  BlastHolesLayer: ({ holes, center, selectedKey, onSelect, colorTrajectories }: {
    holes: Array<{ key: string; collar: number[] | null; toe: number[] | null; color?: string }>;
    center: readonly number[];
    selectedKey?: string | null;
    onSelect?: (key: string) => void;
    colorTrajectories?: boolean;
  }) => (
    <output data-testid="blast-layer" data-holes={JSON.stringify(holes)} data-center={JSON.stringify(center)}
      data-colors={JSON.stringify(holes.map((hole) => hole.color ?? null))} data-selected={selectedKey ?? ''} data-trajectories={String(!!colorTrajectories)}>
      <button type="button" aria-label="select-blast-hole" onClick={() => holes[0] && onSelect?.(holes[0].key)} />
    </output>
  ),
}));

function contourFixture(): ContourData {
  return {
    bounds: {},
    elevation_min: 100,
    elevation_max: 100,
    interval: 1,
    lines: [
      { elevation: 100, type: 'crest', segments: [[[0, 0, 100], [10, 0, 100], [20, 0, 100]]] },
      { elevation: 100, type: 'toe', segments: [[[0, 5, 100], [10, 5, 100], [20, 5, 100]]] },
    ],
  };
}

function buildAnchor(curveId: string, segmentIndex: number, t: number, chainage: number): CurveAnchor {
  const context = useSession.getState().curveSelection.context;
  if (context === null) throw new Error('contexto de selección ausente');
  const position: [number, number, number] = [chainage, 0, 100];
  return { context, curveId, segmentIndex, t, position, chainage };
}

function selectRangeOnViewer(): void {
  act(() => {
    useSession.getState().dispatchCurveSelection({ type: 'click', anchor: buildAnchor('0-0', 0, 0, 0) });
    useSession.getState().dispatchCurveSelection({ type: 'click', anchor: buildAnchor('0-0', 0, 0.5, 10) });
    useSession.getState().dispatchCurveSelection({ type: 'click', anchor: buildAnchor('0-0', 0, 1, 20) });
  });
}

beforeEach(() => {
  contourData = undefined;
  sectionData = [];
  blastHolesData = undefined;
  blastHoleHookCalls.length = 0;
  useSession.getState().reset();
  useBlastView.getState().reset();
});

afterEach(() => {
  cleanup();
  useSession.getState().reset();
  useBlastView.getState().reset();
});

describe('Mesh3DViewer · contexto de geometría de curvas', () => {
  it('publica el contexto al montar sin que el formulario de curvas esté montado', () => {
    contourData = contourFixture();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });

    render(<Mesh3DViewer />);

    const context = useSession.getState().curveSelection.context;
    expect(context).not.toBeNull();
    expect(context?.designMeshId).toBe('design-1');
  });

  it('permite redimensionar el panel flotante arrastrando la esquina y respeta limites responsivos', () => {
    contourData = contourFixture();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });

    render(<Mesh3DViewer />);

    const panel = screen.getByTestId('mesh-layer-panel');
    expect(panel.getAttribute('style')).toContain('320px');
    expect(panel.getAttribute('style')).toContain('min-width: 280px');
    expect(screen.getByRole('button', { name: 'viewer.panel_resize_corner' })).toBeTruthy();
    expect(screen.getByText('viewer.panel_resize_hint')).toBeTruthy();
  });

  it('mantiene la capa apagada hasta activar el toggle y envía la sección activa al hook', () => {
    sectionData = [
      { id: 'section-a', name: 'S-A', origin: [0, 0], azimuth: 0, length: 20, sector: 'Norte' },
      { id: 'section-b', name: 'S-B', origin: [5, 6], azimuth: 90, length: 30, sector: 'Sur' },
    ];
    blastHolesData = {
      session_id: 'session-test', section_id: null, corridor_m: null, data_revision: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      holes: [
        { row_id: 'row-1', hole_id: 'H-1', collar: [101, 202, 303], toe: [104, 205, 293], geometry_status: 'complete', provenance: {}, attributes: {}, section_relation: 'exact_intersection', section_distance_m: 0 },
        { row_id: 'row-2', hole_id: 'H-2', collar: [111, 212, 313], toe: null, geometry_status: 'collar_only', provenance: {}, attributes: {}, section_relation: null, section_distance_m: null },
      ],
      summary: { total_loaded: 2, drawable: 2, complete_geometry: 1, collar_only: 1, without_geometry: 0, rejected: 0 },
    };
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1', selectedSection: null });

    render(<Mesh3DViewer />);
    expect(screen.queryByTestId('blast-layer')).toBeNull();
    expect(blastHoleHookCalls.at(-1)).toEqual([false, null, '']);

    fireEvent.click(screen.getByTestId('blast-holes-toggle'));
    expect(screen.queryByTestId('blast-layer')).toBeNull();
    expect((screen.getByLabelText('blast.confirmSpatial3d') as HTMLInputElement).checked).toBe(false);
    expect(blastHoleHookCalls.at(-1)).toEqual([true, null, '']);

    fireEvent.click(screen.getByLabelText('blast.confirmSpatial3d'));
    expect((screen.getByLabelText('blast.confirmSpatial3d') as HTMLInputElement).checked).toBe(true);
    expect(JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-holes')!)).toEqual([
      { key: 'row-1', collar: [101, 202, 303], toe: [104, 205, 293], color: '#30123b' },
      { key: 'row-2', collar: [111, 212, 313], toe: null, color: '#7a0402' },
    ]);

    fireEvent.change(screen.getByLabelText('blast.holeFilters.id'), { target: { value: 'H-2' } });
    expect(JSON.parse(screen.getByTestId('blast-layer').getAttribute('data-holes')!)).toEqual([
      { key: 'row-2', collar: [111, 212, 313], toe: null, color: '#7a0402' },
    ]);
    fireEvent.change(screen.getByLabelText('blast.holeFilters.id'), { target: { value: '' } });

    fireEvent.change(screen.getByLabelText('blast.sectionSelect'), { target: { value: 'section-b' } });
    expect(blastHoleHookCalls.at(-1)).toEqual([true, 1, JSON.stringify([[5, 6], 90, 30, null, null])]);
    expect(useSession.getState().selectedSection).toBe('section-b');
    expect((screen.getByLabelText('blast.confirmSpatial3d') as HTMLInputElement).checked).toBe(true);

    act(() => useSession.getState().setDesignMeshId('design-2'));
    expect((screen.getByLabelText('blast.confirmSpatial3d') as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByTestId('blast-layer')).toBeNull();
  });

  it('integra color por variable y categoría con filtros, escala, selección y tamaño del panel', () => {
    blastHolesData = {
      session_id: 'session-color-test', section_id: null, corridor_m: null, data_revision: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      holes: [
        { row_id: 'row-1', hole_id: 'H-1', collar: [1, 2, 101], toe: [1, 2, 91], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B1', Kilos_Cargados_real: 100 }, section_relation: null, section_distance_m: null },
        { row_id: 'row-2', hole_id: 'H-2', collar: [3, 4, 303], toe: [3, 4, 293], geometry_status: 'complete', provenance: {}, attributes: { Banco_Original: 'B2', Kilos_Cargados_real: 300 }, section_relation: null, section_distance_m: null },
      ],
      summary: { total_loaded: 2, drawable: 2, complete_geometry: 2, collar_only: 0, without_geometry: 0, rejected: 0 },
    };
    useSession.setState({ designMeshId: 'design-color', topoMeshId: 'topo-color' });

    render(<Mesh3DViewer />);
    expect(screen.getByRole('button', { name: 'viewer.panel_resize_corner' })).toBeTruthy();

    fireEvent.click(screen.getByTestId('blast-holes-toggle'));
    fireEvent.click(screen.getByLabelText('blast.confirmSpatial3d'));
    const layer = screen.getByTestId('blast-layer');
    expect(JSON.parse(layer.getAttribute('data-holes') ?? '[]')).toHaveLength(2);
    const turboColors = JSON.parse(layer.getAttribute('data-colors') ?? '[]');
    expect(turboColors).toHaveLength(2);
    expect(turboColors[0]).not.toBe(turboColors[1]);

    fireEvent.change(screen.getByLabelText('blast.colors.palette'), { target: { value: 'Viridis' } });
    const viridisColors = JSON.parse(layer.getAttribute('data-colors') ?? '[]');
    expect(viridisColors).toHaveLength(2);
    expect(viridisColors[0]).not.toBe(turboColors[0]);

    fireEvent.change(screen.getByLabelText('blast.holeFilters.bench'), { target: { value: 'B2' } });
    expect(JSON.parse(layer.getAttribute('data-holes') ?? '[]')).toHaveLength(1);
    expect(JSON.parse(layer.getAttribute('data-holes') ?? '[]')[0].key).toBe('row-2');
    const filteredColor = JSON.parse(layer.getAttribute('data-colors') ?? '[]');
    expect(filteredColor).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'select-blast-hole' }));
    expect(layer.getAttribute('data-selected')).toBe('row-2');
    expect(screen.getByText(/blast\.selection: H-2/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('blast.colors.mode'), { target: { value: 'category' } });
    fireEvent.change(screen.getByLabelText('blast.colors.categoryLabel'), { target: { value: 'bench' } });
    expect(screen.getByLabelText('blast.colors.palette')).toBeDisabled();
    expect(layer.getAttribute('data-trajectories')).toBe('true');
    expect(screen.getByTestId('mesh-layer-panel')).toBeTruthy();
  });

  it('invalida anclas obsoletas cuando cambia la identidad de geometría sin formulario montado', () => {
    contourData = contourFixture();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });

    const { rerender } = render(<Mesh3DViewer />);
    const firstToken = useSession.getState().curveSelection.context?.geometryKey;
    selectRangeOnViewer();
    expect(useSession.getState().curveSelection.start).not.toBeNull();
    expect(useSession.getState().curveSelection.end).not.toBeNull();

    contourData = contourFixture();
    rerender(<Mesh3DViewer />);

    const state = useSession.getState().curveSelection;
    expect(state.context?.geometryKey).not.toBe(firstToken);
    expect(state.curveId).toBeNull();
    expect(state.start).toBeNull();
    expect(state.end).toBeNull();
    expect(state.rejection).toBeNull();
  });

  it('no cancela una selección válida cuando la geometría no está disponible', () => {
    contourData = contourFixture();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });

    const { rerender } = render(<Mesh3DViewer />);
    selectRangeOnViewer();
    const selected = useSession.getState().curveSelection;
    expect(selected.start).not.toBeNull();

    contourData = undefined;
    rerender(<Mesh3DViewer />);

    expect(useSession.getState().curveSelection).toBe(selected);
  });

  it('no renotifica ni recrea el estado cuando la instantánea no cambió', () => {
    contourData = contourFixture();
    useSession.setState({ designMeshId: 'design-1', topoMeshId: 'topo-1' });

    const { rerender } = render(<Mesh3DViewer />);
    selectRangeOnViewer();
    const selected = useSession.getState().curveSelection;
    const listener = vi.fn();
    const unsubscribe = useSession.subscribe(listener);

    try {
      rerender(<Mesh3DViewer />);
      expect(useSession.getState().curveSelection).toBe(selected);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });
});

describe('resolveCurveContextAction', () => {
  const first = { designMeshId: 'design-1', geometryKey: 'token-1' };
  const sameByValue = { designMeshId: 'design-1', geometryKey: 'token-1' };
  const secondToken = { designMeshId: 'design-1', geometryKey: 'token-2' };

  it('no propone acción cuando la siguiente geometría no está disponible', () => {
    expect(resolveCurveContextAction(first, null)).toBeNull();
    expect(resolveCurveContextAction(null, null)).toBeNull();
  });

  it('no propone acción para contextos iguales por valor aunque cambie la referencia', () => {
    expect(curveContextsEqual(first, sameByValue)).toBe(true);
    expect(resolveCurveContextAction(first, sameByValue)).toBeNull();
  });

  it('compara por valor el identificador de malla y el token de geometría', () => {
    expect(curveContextsEqual(first, { ...first, designMeshId: 'design-2' })).toBe(false);
    expect(curveContextsEqual(first, null)).toBe(false);
    expect(curveContextsEqual(null, null)).toBe(true);
  });

  it('propone el despacho de contexto cuando cambia la identidad de geometría', () => {
    expect(resolveCurveContextAction(first, secondToken)).toEqual({ type: 'context', context: secondToken });
    expect(resolveCurveContextAction(null, secondToken)).toEqual({ type: 'context', context: secondToken });
  });
});
