import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SelectedSectionPanel } from './DashboardRail';

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
