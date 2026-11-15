import '../../../i18n';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComparisonResult } from '../../../api/types';
import { ParameterBars, SelectedSectionPanel } from './DashboardRail';

const profile = vi.hoisted(() => vi.fn(() => ({ data: { design: { distances: [0, 1], elevations: [1, 0] }, topo: { distances: [0, 1], elevations: [2, 1] } }, isPending: false, isError: false })));
const mode = vi.hoisted(() => vi.fn());
vi.mock('../../../api/hooks', () => ({ useProfile: profile }));
vi.mock('../../../stores/session', () => ({ useSession: (selector: (state: unknown) => unknown) => selector({ setProfilesMode: mode }) }));
vi.mock('../../charts/Plot', () => ({ default: ({ data }: { data: unknown[] }) => <div data-testid="preview-plot" data-traces={data.length} /> }));

describe('selected section preview', () => {
  it('loads the selected section ID and opens its profile on click', () => {
    const open = vi.fn();
    render(<SelectedSectionPanel name="S1" sectionId="id-7" rows={[]} statuses={new Map()} canOpen onClear={() => {}} onOpen={open} />);
    expect(profile).toHaveBeenCalledWith('id-7');
    expect(screen.getByTestId('preview-plot')).toHaveAttribute('data-traces', '2');
    fireEvent.click(screen.getByTestId('preview-plot'));
    expect(mode).toHaveBeenCalledWith('detail');
    expect(open).toHaveBeenCalledOnce();
  });
  it('reserves space when no section is selected', () => {
    const { container } = render(<SelectedSectionPanel name={null} sectionId={null} rows={[]} statuses={new Map()} canOpen={false} onClear={() => {}} onOpen={() => {}} />);
    expect(container.querySelector('[data-slot="profile-preview-placeholder"]')).toHaveTextContent('—');
  });
});

const comparison = (type: ComparisonResult['type'], height_status: string) => ({ type, height_status, angle_status: 'CUMPLE', berm_status: 'CUMPLE' } as ComparisonResult);

describe('parameter bars compared benches', () => {
  it('shows 3 of 8 and excludes 19 unmatched rows from bars and denominator', () => {
    const rows = [...Array.from({ length: 3 }, () => comparison('MATCH', 'CUMPLE')), ...Array.from({ length: 5 }, () => comparison('MATCH', 'NO CUMPLE')), ...Array.from({ length: 19 }, (_, i) => comparison(i % 2 ? 'EXTRA' : 'MISSING', 'CUMPLE'))];
    const { container } = render(<ParameterBars rows={rows} />);
    expect(screen.getByText('37.5%')).toBeInTheDocument();
    expect(container.querySelector('p')).toHaveTextContent('8');
    const bar = container.querySelector('[aria-label]')!;
    expect(bar.children[0]).toHaveStyle({ width: '37.5%' });
    expect(bar.children[2]).toHaveStyle({ width: '62.5%' });
  });
  it('shows a dash if only unmatched benches exist', () => {
    render(<ParameterBars rows={[comparison('MISSING', 'CUMPLE')]} />);
    expect(screen.getAllByText('—')).toHaveLength(3);
  });
  it('excludes unknown statuses from parameter denominator', () => {
    const { container } = render(<ParameterBars rows={[comparison('MATCH', 'CUMPLE'), comparison('MATCH', '-')]} />);
    expect(screen.getAllByText('100.0%')).toHaveLength(3);
    expect(container.querySelector('p')).toHaveTextContent('2');
  });
  it('shows a dash for a parameter with no evaluable statuses', () => {
    render(<ParameterBars rows={[comparison('MATCH', '-')]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

});
