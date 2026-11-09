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

describe('ToolCallCard — export_report download action', () => {
  it('renders the Download button under an ok export result', () => {
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
    await userEvent.click(screen.getByTestId('ai-chat-tool-download'));
    await waitFor(() => {
      expect(useAIChat.getState().notice?.key).toBe(
        'aiChat.notice.download_failed',
      );
    });
  });
});
