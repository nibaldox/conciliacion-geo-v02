import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { getCurveGeometrySnapshot } from '../../sections/curveGeometryAdapter';
import { selectGuideLine } from '../planGuideLine';
import { CompliancePlanView } from '../CompliancePlanView';
import type { ContourData } from '../../../api/types';

const data = { lines: [{ elevation: 5, segments: [[[10, 20, 5], [40, 50, 6], [80, 20, 7]]] }] } as ContourData;
const snapshot = getCurveGeometrySnapshot('design', data)!;
const selection = { context: snapshot.context, curveId: null as string | null, start: null, end: null, rejection: null };
let guideCurve: { id: string; points: [number, number, number][] } | null = { id: '0-0', points: [[10, 20, 5], [40, 50, 6], [80, 20, 7]] };
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../../stores/session', () => ({ useSession: (selector: (state: unknown) => unknown) => selector({ topoMeshId: 'topo', designMeshId: 'design', curveSelection: selection, guideCurve }) }));
vi.mock('../../../api/hooks', () => ({
  useMeshVertices: () => ({ data: { x: [0, 100], y: [0, 100], z: [0, 1] } }),
  useMeshBreaklines: () => ({ data }),
  useSections: () => ({ data: [{ id: '1', name: 'A', origin: [20, 20], azimuth: 0 }] }),
  useSectionProfiles: () => [{ data: { topo: { distances: [0, 50], elevations: [1, 2] } } }],
}));
vi.mock('../planGeometry', async (original) => ({ ...await original<typeof import('../planGeometry')>(), createSurfaceRaster: () => 'raster' }));

describe('selected 3D guide curve', () => {
  it('returns the saved original XY without requiring transient selection', () => {
    expect(selectGuideLine(guideCurve)).toEqual([[10, 20], [40, 50], [80, 20]]);
    expect(selectGuideLine(null)).toEqual([]);
  });
  it('draws selected curve over sections, independent of section selection and zoom', () => {
    const props = { variant: 'hero' as const, results: [{ section: 'A' }] as never[], statuses: new Map() };
    const { container, rerender } = render(<CompliancePlanView {...props} />);
    const guide = () => container.querySelector('[data-guide-line]');
    expect(guide()).not.toBeNull();
    expect(guide()!.getAttribute('stroke')).toBe('var(--color-accent-bright)');
    expect(guide()!.getAttribute('vector-effect')).toBe('non-scaling-stroke');
    expect(guide()!.compareDocumentPosition(container.querySelector('[data-plan-line]')!) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'plan_view.zoom_in' }));
    expect(guide()!.getAttribute('vector-effect')).toBe('non-scaling-stroke');
    guideCurve = null;
    rerender(<CompliancePlanView {...props} />);
    expect(guide()).toBeNull();
    guideCurve = { id: '0-0', points: [[10, 20, 5], [40, 50, 6], [80, 20, 7]] };
  });
});
