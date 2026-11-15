import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import client from '../../api/client';
import { Header } from './Header';
import '../../i18n';
import { act, fireEvent } from '@testing-library/react';
import { getSessionId, setSessionId } from '../../api/client';

vi.mock('../../hooks/useWorkflowStatus', () => ({ useWorkflowStatus: () => ({ projectStatus: 'empty' }) }));

describe('recent sessions', () => {
  it('hides the sessions button when the endpoint returns 404', async () => {
    const adapter = vi.fn(async () => { throw { response: { status: 404 } }; });
    client.defaults.adapter = adapter;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><Header /></QueryClientProvider>);
    await vi.waitFor(() => expect(queryClient.getQueryState(['recent-sessions'])?.status).toBe('error'));
    expect(screen.queryByRole('button', { name: /^sessions$/i })).toBeNull();
    expect(adapter).toHaveBeenCalledTimes(1);
  });
  it('shows the sessions button when the endpoint is available', async () => {
    client.defaults.adapter = async config => ({ config, data: { ttl_days: 30, sessions: [] }, status: 200, statusText: 'OK', headers: {} });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><Header /></QueryClientProvider>);
    const button = await screen.findByRole('button', { name: /sesiones|sessions/i });
    expect(button.querySelector('svg[aria-hidden="true"]')).toBeTruthy();
  });
  it('does not re-adopt an old id from a late response after New Session', async () => {
    setSessionId('old');
    let respond!: () => void;
    client.defaults.adapter = config => config.url === '/late' ? new Promise(resolve => { respond = () => resolve({ config, data: {}, status: 200, statusText: 'OK', headers: { 'x-session-id': 'old' } }); }) : Promise.resolve({ config, data: { ttl_days: 30, sessions: [] }, status: 200, statusText: 'OK', headers: {} });
    const late = client.get('/late');
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><Header /></QueryClientProvider>);
    await vi.waitFor(() => expect(respond).toBeTypeOf('function'));
    fireEvent.click(screen.getByRole('button', { name: /nueva sesión|new session/i }));
    const fresh = getSessionId();
    expect(fresh).toMatch(/^[0-9a-f-]{36}$/);
    await act(async () => { respond(); await late; });
    expect(localStorage.getItem('conciliacion.sessionId')).toBe(fresh);
    expect(getSessionId()).toBe(fresh);
  });

});
