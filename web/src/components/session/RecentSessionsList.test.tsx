import { cleanup, render, screen, fireEvent, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecentSessionsList } from './RecentSessionsList';
import '../../i18n';

const state = vi.hoisted(() => ({ result: {} as unknown }));
vi.mock('../../api/sessions', () => ({ useRecentSessions: () => state.result }));
vi.mock('../../api/client', () => ({ getSessionId: () => '0', setSessionId: vi.fn() }));

const sessions = Array.from({ length: 6 }, (_, index) => ({
  session_id: String(index), created_at: '2026-01-01T00:00:00Z', last_used_at: '2026-01-01T00:00:00Z',
  expires_at: '2026-12-01T00:00:00Z', design_filename: `design-${index}.stl`, topo_filename: 'topo.stl',
  n_sections: 1, n_results: 2, process_status: 'completed',
}));
function mount() {
  return render(<QueryClientProvider client={new QueryClient()}><RecentSessionsList /></QueryClientProvider>);
}
afterEach(cleanup);
beforeEach(() => {
  state.result = { isSuccess: true, data: { ttl_days: 30, sessions } };
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
});
describe('recent sessions in the rail', () => {
  it('shows five sessions, marks the current one, and opens the full list', () => {
    mount();
    expect(screen.getByText('Recent sessions')).toBeTruthy();
    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(5);
    expect(within(rows[0]).getByText('Current')).toBeTruthy();
    expect(within(rows[1]).getByRole('button', { name: 'Open' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'View all' }));
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
  it('renders nothing when the endpoint fails', () => {
    state.result = { isSuccess: false, isError: true };
    const { container } = mount();
    expect(container.firstChild).toBeNull();
  });
  it('renders nothing when sessions is not an array', () => {
    state.result = { isSuccess: true, data: { sessions: null } };
    const { container } = mount();
    expect(container.firstChild).toBeNull();
  });
  it('renders nothing for an empty list', () => {
    state.result = { isSuccess: true, data: { ttl_days: 30, sessions: [] } };
    const { container } = mount();
    expect(container.firstChild).toBeNull();
  });
});
