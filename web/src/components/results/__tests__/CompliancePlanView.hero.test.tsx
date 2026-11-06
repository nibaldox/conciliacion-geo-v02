import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ComparisonResult } from '../../../api/types';
import { CompliancePlanView } from '../CompliancePlanView';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../../stores/session', () => ({ useSession: (selector: (state: { topoMeshId: string }) => unknown) => selector({ topoMeshId: 'mesh' }) }));
vi.mock('../../../api/hooks', () => ({
  useMeshVertices: () => ({ data: { x: [0, 100], y: [0, 100], z: [0, 1] } }),
  useSections: () => ({ data: [{ id: '1', name: 'A', origin: [20, 20], azimuth: 0 }, { id: '2', name: 'B', origin: [60, 20], azimuth: 0 }] }),
  useSectionProfiles: (ids: string[]) => ids.map(() => ({ data: { topo: { distances: [0, 50], elevations: [1, 2] } } })),
}));
vi.mock('../planGeometry', async (importOriginal) => ({ ...await importOriginal<typeof import('../planGeometry')>(), createSurfaceRaster: () => 'raster' }));
const results = [{ section: 'A', height_status: 'CUMPLE', section_score: 50 }] as ComparisonResult[];
const statuses = new Map([['A', 'CUMPLE' as const]]);
describe('hero plan', () => {
  it('overlays only the selected visible section and tracks selection and zoom', () => {
    const rows = [...results, { section: 'B', height_status: 'NO_CUMPLE', section_score: 30 } as ComparisonResult];
    const states = new Map([['A', 'CUMPLE' as const], ['B', 'NO_CUMPLE' as const]]);
    const props = { variant: 'hero' as const, results: rows, statuses: states };
    const { container, rerender } = render(<CompliancePlanView {...props} />);
    const overlay = () => container.querySelector('[data-selected-section-line]');
    expect(overlay()).toBeNull();
    rerender(<CompliancePlanView {...props} selectedSection="A" />);
    expect(overlay()).not.toBeNull();
    expect(overlay()!.getAttribute('points')).toBe(container.querySelector('[data-section-name="A"] [data-plan-line]')!.getAttribute('points'));
    expect(overlay()!.getAttribute('stroke')).toBe('var(--color-accent-bright)');
    expect(overlay()!.getAttribute('vector-effect')).toBe('non-scaling-stroke');
    fireEvent.click(screen.getByRole('button', { name: 'plan_view.zoom_in' }));
    expect(overlay()!.getAttribute('vector-effect')).toBe('non-scaling-stroke');
    const first = overlay()!.getAttribute('points');
    rerender(<CompliancePlanView {...props} selectedSection="B" />);
    expect(overlay()!.getAttribute('points')).not.toBe(first);
    expect(overlay()!.getAttribute('points')).toBe(container.querySelector('[data-section-name="B"] [data-plan-line]')!.getAttribute('points'));
    rerender(<CompliancePlanView {...props} selectedSection="B" visibleStatuses={new Set(['CUMPLE'])} />);
    expect(overlay()).toBeNull();
    rerender(<CompliancePlanView {...props} selectedSection={null} />);
    expect(overlay()).toBeNull();
  });
  it('selects accessibly and clears with Escape or empty space', () => {
    const onSelectSection = vi.fn();
    const { container } = render(<CompliancePlanView variant="hero" results={results} statuses={statuses} selectedSection="A" onSelectSection={onSelectSection} />);
    expect(container.querySelector('[slot="compliance-plan-view"]')).toBeNull();
    const section = screen.getByRole('button', { name: /A/ });
    expect(section.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(section); expect(onSelectSection).toHaveBeenCalledWith('A');
    fireEvent.keyDown(section, { key: 'Escape' }); expect(onSelectSection).toHaveBeenCalledWith(null);
    fireEvent.click(screen.getByRole('img')); expect(onSelectSection).toHaveBeenCalledWith(null);
  });
  it('dims filtered sections and prevents interaction', () => {
    const onSelectSection = vi.fn();
    const { container } = render(<CompliancePlanView variant="hero" results={results} statuses={statuses} visibleStatuses={new Set()} onSelectSection={onSelectSection} />);
    const line = container.querySelector('[data-section-name="A"]')!;
    expect(Number(line.getAttribute('opacity'))).toBeLessThan(0.5);
    fireEvent.click(line); expect(onSelectSection).not.toHaveBeenCalled();
  });
  it('shows a tooltip on hover and selects with the keyboard', () => {
    const onSelectSection = vi.fn();
    render(<CompliancePlanView variant="hero" results={results} statuses={statuses} onSelectSection={onSelectSection} />);
    const section = screen.getByRole('button', { name: /A/ });
    fireEvent.mouseEnter(section);
    expect(screen.getByRole('tooltip').textContent).toContain('A');
    fireEvent.keyDown(section, { key: ' ' });
    expect(onSelectSection).toHaveBeenCalledWith('A');
    fireEvent.mouseLeave(section);
    expect(screen.queryByRole('tooltip')).toBeNull();
  });
  it('zooms on wheel and prevents page scrolling', () => {
    render(<CompliancePlanView variant="hero" results={results} statuses={statuses} />);
    const svg = screen.getByRole('img');
    const initial = svg.getAttribute('viewBox');
    const event = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true });
    fireEvent(svg, event);
    expect(svg.getAttribute('viewBox')).not.toBe(initial);
    expect(event.defaultPrevented).toBe(true);
  });
  it('pans by dragging without selecting the background', () => {
    const onSelectSection = vi.fn();
    render(<CompliancePlanView variant="hero" results={results} statuses={statuses} onSelectSection={onSelectSection} />);
    const svg = screen.getByRole('img');
    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent(svg, new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 100, clientY: 100 }));
    fireEvent(svg, new MouseEvent('pointermove', { bubbles: true, clientX: 130, clientY: 120 }));
    fireEvent(svg, new MouseEvent('pointerup', { bubbles: true, clientX: 130, clientY: 120 }));
    fireEvent.click(svg);
    expect(svg.getAttribute('viewBox')).toBe('-30 -20 1000 600');
    expect(onSelectSection).not.toHaveBeenCalled();
  });
  it('keeps cursor position anchored and zoom bounded', () => {
    render(<CompliancePlanView variant="hero" results={results} statuses={statuses} />);
    const svg = screen.getByRole('img');
    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.wheel(svg, { deltaY: -1000, clientX: 250, clientY: 300 });
    const [x, y, width, height] = svg.getAttribute('viewBox')!.split(' ').map(Number);
    expect(x! + width! / 4).toBeCloseTo(250);
    expect(y! + height! / 2).toBeCloseTo(300);
    fireEvent.wheel(svg, { deltaY: -100000, clientX: 250, clientY: 300 });
    expect(Number(svg.getAttribute('viewBox')!.split(' ')[2])).toBe(125);
    fireEvent.click(screen.getByRole('button', { name: 'plan_view.zoom_reset' }));
    expect(svg.getAttribute('viewBox')).toBe('0 0 1000 600');
  });
  it('changes viewBox with zoom and stroke with coloring', () => {
    const { container, rerender } = render(<CompliancePlanView variant="hero" results={results} statuses={statuses} />);
    const svg = screen.getByRole('img'); const initial = svg.getAttribute('viewBox');
    fireEvent.click(screen.getByRole('button', { name: 'plan_view.zoom_in' }));
    expect(svg.getAttribute('viewBox')).not.toBe(initial);
    const stroke = container.querySelector('[data-plan-line]')!.getAttribute('stroke');
    rerender(<CompliancePlanView variant="hero" results={results} statuses={statuses} colorBy="score" />);
    expect(container.querySelector('[data-plan-line]')!.getAttribute('stroke')).not.toBe(stroke);
  });
});
