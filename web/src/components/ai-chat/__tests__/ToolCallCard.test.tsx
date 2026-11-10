import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockGet, mockGetSessionId } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-toolcard'),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import { useAIChat } from '../../../stores/aiChat';
import { ToolCallCard } from '../ToolCallCard';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

const EXPORT_OK_SUMMARY = JSON.stringify({
  ok: true,
  format: 'excel',
  filename: 'Conciliacion_Geotecnica.xlsx',
  endpoint: '/api/v1/export/excel',
  method: 'GET',
  content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  note: 'El archivo se genera para su descarga en la interfaz.',
});

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  vi.stubGlobal('fetch', vi.fn());
  initChatI18n();
  useAIChat.getState().reset();
});

describe('ToolCallCard — collapsed by default', () => {
  const STATE_OK_MESSAGE = {
    kind: 'tool' as const,
    id: 't_c',
    invocationId: 'inv_state',
    name: 'get_workflow_state',
    status: 'ok' as const,
    summary: '{"n_sections": 3}',
    error: null,
  };

  it('hides the summary behind the toggle until it is expanded', async () => {
    renderWithProviders(<ToolCallCard message={STATE_OK_MESSAGE} />);
    const toggle = screen.getByTestId('ai-chat-tool-toggle');
    const details = screen.getByTestId('ai-chat-tool-details');
    expect(details).toHaveAttribute('hidden');
    expect(details).not.toBeVisible();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-controls', details.id);

    await userEvent.click(toggle);
    expect(details).not.toHaveAttribute('hidden');
    expect(details).toBeVisible();
    expect(screen.getByText('{"n_sections": 3}')).toBeVisible();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await userEvent.click(toggle);
    expect(details).toHaveAttribute('hidden');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows the running state collapsed with spinner text and keeps aria-expanded', () => {
    renderWithProviders(
      <ToolCallCard
        message={{
          kind: 'tool',
          id: 't_r',
          invocationId: 'inv_run',
          name: 'run_reconciliation',
          status: 'running',
          summary: '',
          error: null,
        }}
      />,
    );
    const toggle = screen.getByTestId('ai-chat-tool-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveTextContent('ejecutando «run_reconciliation»…');
    expect(screen.getByTestId('ai-chat-tool-details')).toHaveAttribute('hidden');
  });

  it('shows the Download button only once the card is expanded', async () => {
    renderWithProviders(
      <ToolCallCard
        message={{
          kind: 'tool',
          id: 't_d',
          invocationId: 'inv_export',
          name: 'export_report',
          status: 'ok',
          summary: EXPORT_OK_SUMMARY,
          error: null,
        }}
      />,
    );
    expect(screen.getByTestId('ai-chat-tool-download')).not.toBeVisible();
    await userEvent.click(screen.getByTestId('ai-chat-tool-toggle'));
    expect(screen.getByTestId('ai-chat-tool-download')).toBeVisible();
    expect(screen.getByTestId('ai-chat-tool-download')).toHaveTextContent(
      'Descargar archivo',
    );
  });
});

describe('ToolCallCard — export_report download action', () => {
  it('renders the Download button under an ok export result', async () => {
    renderWithProviders(
      <ToolCallCard
        message={{
          kind: 'tool',
          id: 't1',
          invocationId: 'inv_export',
          name: 'export_report',
          status: 'ok',
          summary: EXPORT_OK_SUMMARY,
          error: null,
        }}
      />,
    );
    await userEvent.click(screen.getByTestId('ai-chat-tool-toggle'));
    expect(screen.getByTestId('ai-chat-tool-download')).toHaveTextContent(
      'Descargar archivo',
    );
  });

  it('no download button for other tools or failing exports', () => {
    renderWithProviders(
      <>
        <ToolCallCard
          message={{
            kind: 'tool',
            id: 't2',
            invocationId: 'inv_state',
            name: 'get_workflow_state',
            status: 'ok',
            summary: '{"n_sections": 3}',
            error: null,
          }}
        />
        <ToolCallCard
          message={{
            kind: 'tool',
            id: 't3',
            invocationId: 'inv_export_fail',
            name: 'export_report',
            status: 'error',
            summary: '{"ok": false, "error": "no_results"}',
            error: 'no_results',
          }}
        />
      </>,
    );
    expect(screen.queryByTestId('ai-chat-tool-download')).toBeNull();
  });

  it('downloads with the session headers and saves the blob as the export filename', async () => {
    const mockFetch = vi.fn(async () =>
      new Response('binary', {
        status: 200,
        headers: {
          'Content-Type':
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        },
      }),
    );
    vi.stubGlobal('fetch', mockFetch);
    const createObjectURL = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:fake');
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});
    try {
      renderWithProviders(
        <ToolCallCard
          message={{
            kind: 'tool',
            id: 't4',
            invocationId: 'inv_export',
            name: 'export_report',
            status: 'ok',
            summary: EXPORT_OK_SUMMARY,
            error: null,
          }}
        />,
      );
      await userEvent.click(screen.getByTestId('ai-chat-tool-toggle'));
      await userEvent.click(screen.getByTestId('ai-chat-tool-download'));
      await waitFor(() => {
        expect(createObjectURL).toHaveBeenCalledTimes(1);
      });
      const [url, init] = mockFetch.mock.calls[0] as unknown as [
        string,
        RequestInit,
      ];
      expect(url).toBe('/api/v1/export/excel');
      expect((init.headers as Record<string, string>)['X-Session-ID']).toBe(
        'sess-toolcard',
      );
      const blob = createObjectURL.mock.calls[0][0] as Blob;
      expect(blob.type).toBe(
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      );
      expect(click).toHaveBeenCalledTimes(1);
    } finally {
      createObjectURL.mockRestore();
      click.mockRestore();
    }
  });

  it('surfaces the download_failed notice when the endpoint fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 500 })),
    );
    renderWithProviders(
      <ToolCallCard
        message={{
          kind: 'tool',
          id: 't5',
          invocationId: 'inv_export',
          name: 'export_report',
          status: 'ok',
          summary: EXPORT_OK_SUMMARY,
          error: null,
        }}
      />,
    );
    await userEvent.click(screen.getByTestId('ai-chat-tool-toggle'));
    await userEvent.click(screen.getByTestId('ai-chat-tool-download'));
    await waitFor(() => {
      expect(useAIChat.getState().notice?.key).toBe(
        'aiChat.notice.download_failed',
      );
    });
  });
});
