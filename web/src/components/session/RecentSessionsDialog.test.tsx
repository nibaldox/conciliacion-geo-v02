import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecentSessionsDialog } from './RecentSessionsDialog';
import { setSessionId } from '../../api/client';
import '../../i18n';

const id = '80b2aef4-5f6f-4b43-8621-d5badeec61de';
const data = { ttl_days: 30, sessions: [
  { session_id: id, created_at: '2026-11-13T17:58:38Z', last_used_at: '2026-11-14T18:39:16Z', expires_at: '2026-12-14T18:39:16Z', design_filename: 'design.stl', topo_filename: 'topo.stl', n_sections: 1, n_results: 2, process_status: 'completed' },
  { session_id: 'other', created_at: '2026-11-13T17:58:38Z', last_used_at: '2026-11-14T18:39:16Z', expires_at: '2026-12-14T18:39:16Z', design_filename: null, topo_filename: null, n_sections: 2, n_results: 1, process_status: 'completed' },
] };
function mount(error = false, sessions = data) {
  const onClose = vi.fn();
  render(<QueryClientProvider client={new QueryClient()}><RecentSessionsDialog data={sessions} error={error} onClose={onClose} /></QueryClientProvider>);
  return onClose;
}
describe('recent sessions dialog', () => {
  beforeEach(() => { setSessionId(id); HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; });
  it('displays current session, filenames, dates, counts and open for other sessions', () => {
    mount();
    expect(screen.getByRole('dialog').classList.contains('m-auto')).toBe(true);
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByText(/design.stl/)).toBeTruthy();
    expect(within(rows[0]).getByText(/topo.stl/)).toBeTruthy();
    expect(within(rows[0]).getByText(/1 section.*2 results/)).toBeTruthy();
    expect(within(rows[0]).getByText('Current')).toBeTruthy();
    expect(within(rows[0]).queryByRole('button', { name: 'Open' })).toBeNull();
    expect(within(rows[1]).getByRole('button', { name: 'Open' })).toBeTruthy();
    expect(within(rows[0]).getByText(/Deleted on/)).toBeTruthy();
  });
  it('shows empty and error states', () => {
    const close = mount(false, { ttl_days: 30, sessions: [] });
    expect(screen.getByText('No saved sessions with loaded surfaces.')).toBeTruthy();
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
    expect(close).toHaveBeenCalled();
  });
  it('shows list errors', () => {
    mount(true);
    expect(screen.getByRole('alert').textContent).toContain('Could not load');
  });
});
