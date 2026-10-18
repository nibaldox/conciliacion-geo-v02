import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import type { ReactNode } from 'react';
import type { ContourData } from '../../../api/types';
import type { CurveAnchor } from '../../sections/curveSelectionState';
import { useSession } from '../../../stores/session';
import { Mesh3DViewer } from '../Mesh3DViewer';
import { curveContextsEqual, resolveCurveContextAction } from '../curveContextSync';

let contourData: ContourData | undefined;

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
  useSections: () => ({ data: [] }),
  useResults: () => ({ data: [] }),
  useHorizontalDeviationMesh: () => ({
    data: undefined,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  }),
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
  useSession.getState().reset();
});

afterEach(() => {
  cleanup();
  useSession.getState().reset();
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
