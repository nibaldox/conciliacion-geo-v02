import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import * as THREE from 'three';
import { useSession } from '../../../stores/session';
import { useBlastView } from '../../../stores/blastView';
import es from '../../../locales/es.json';
import en from '../../../locales/en.json';
import { Mesh3DViewer } from '../Mesh3DViewer';

const view = { raycaster: { params: {} }, camera: new THREE.PerspectiveCamera(), size: { width: 800, height: 600 }, gl: { domElement: document.createElement('canvas') } };
let indexed = true;
vi.mock('@react-three/fiber', () => ({ Canvas: ({ children }: { children: ReactNode }) => <div>{children}</div>, useFrame: () => undefined, useThree: () => view }));
vi.mock('@react-three/drei', () => ({ Html: ({ children }: { children: ReactNode }) => <div>{children}</div>, OrbitControls: () => null, GizmoHelper: ({ children }: { children: ReactNode }) => <>{children}</>, GizmoViewport: () => null }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../../stores/theme', () => ({ useTheme: (selector: (state: { isDark: boolean }) => unknown) => selector({ isDark: false }) }));
vi.mock('../../../api/hooks', () => ({
  useMeshVertices: (id: string | null) => ({ data: id ? { x: [0, 10, 0], y: [0, 0, 10], z: [0, 0, 0], faces: indexed ? [[0, 1, 2]] : [] } : undefined, isLoading: false }),
  useMeshBreaklines: () => ({ data: undefined, isLoading: false }),
  useSections: () => ({ data: [] }), useResults: () => ({ data: [] }),
  useHorizontalDeviationMesh: () => ({ data: undefined, isFetching: false, isError: false }),
}));
vi.mock('../useBlastHoles3D', () => ({ useBlastHoles3D: () => ({ data: undefined, isLoading: false, isError: false }) }));

function props(element: Element): Record<string, unknown> {
  const key = Object.keys(element).find((entry) => entry.startsWith('__reactProps$'));
  if (!key) throw new Error('React props missing');
  return (element as unknown as Record<string, Record<string, unknown>>)[key]!;
}

beforeEach(() => { indexed = true; useSession.setState({ topoMeshId: 'topo', designMeshId: null }); });
afterEach(() => { cleanup(); useSession.getState().reset(); useBlastView.getState().reset(); });

describe('topography opacity', () => {
  it('defaults to opaque and updates the solid material with the accessible slider', () => {
    const { container } = render(<Mesh3DViewer />);
    const slider = screen.getByRole('slider', { name: 'viewer.layer_topo_opacity' }) as HTMLInputElement;
    expect([slider.value, slider.min, slider.max, slider.step]).toEqual(['100', '0', '100', '5']);
    const material = container.querySelector('meshstandardmaterial')!;
    expect(props(material).transparent ?? false).toBe(false);
    expect(props(material).opacity ?? 1).toBe(1);
    expect(props(material).depthWrite ?? true).toBe(true);
    fireEvent.change(slider, { target: { value: '50' } });
    expect(slider.value).toBe('50');
    expect(props(material)).toMatchObject({ transparent: true, opacity: 0.5, depthWrite: false });
    fireEvent.change(slider, { target: { value: '100' } });
    expect(props(material).transparent ?? false).toBe(false);
    expect(props(material).opacity ?? 1).toBe(1);
    expect(props(material).depthWrite ?? true).toBe(true);
  });

  it('applies opacity to the point-cloud fallback', () => {
    indexed = false;
    const { container } = render(<Mesh3DViewer />);
    fireEvent.change(screen.getByRole('slider', { name: 'viewer.layer_topo_opacity' }), { target: { value: '50' } });
    expect(props(container.querySelector('pointsmaterial')!)).toMatchObject({ transparent: true, opacity: 0.4, depthWrite: false });
  });

  it('offers the same slider in blast mode', () => {
    render(<Mesh3DViewer mode="blast" />);
    expect((screen.getByRole('slider', { name: 'viewer.layer_topo_opacity' }) as HTMLInputElement).value).toBe('100');
  });

  it('has nonempty translations in both languages', () => {
    for (const locale of [es, en]) expect((locale.viewer as Record<string, unknown>).layer_topo_opacity).toEqual(expect.stringMatching(/\S/));
  });
});
