import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockGet, mockDelete, mockGetSessionId, mockFetch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-panel'),
  mockFetch: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(async () => ({ data: {} })),
    delete: (...args: unknown[]) => mockDelete(...args),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import type { AIProvidersState } from '../../../api/aiChat';
import { useAIChat } from '../../../stores/aiChat';
import { ChatPanel } from '../ChatPanel';
import {
  CHAT_TEXT_DONE,
  initChatI18n,
  makeNdjsonResponse,
  renderWithProviders,
} from './chatTestUtils';

function providersBody(overrides: Partial<AIProvidersState> = {}): AIProvidersState {
  return {
    providers: ['ollama', 'lmstudio', 'openai'],
    supports_tool_calls: { ollama: false, lmstudio: true, openai: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'qwen3-32b',
    ...overrides,
  };
}

const CONFIRMATION_STREAM = [
  '{"type":"text","content":"Voy a reemplazar las secciones."}',
  '{"type":"tool_call","invocation_id":"inv_1","name":"generate_sections_manual","args":{},"requires_confirmation":true}',
  '{"type":"confirmation_required","invocation_id":"inv_1","name":"generate_sections_manual","args_summary":"Reemplaza 2 secciones existentes"}',
  '{"type":"done","finish_reason":"confirmation_required","usage":null,"cached":false}',
];

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockDelete.mockReset();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  initChatI18n();
  useAIChat.getState().reset();
});

describe('ChatPanel — explicit deployment states', () => {
  it('shows the disabled-deployment notice when chat_enabled is false', async () => {
    mockGet.mockResolvedValueOnce({ data: providersBody({ chat_enabled: false }) });
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    expect(await screen.findByTestId('ai-chat-disabled-notice')).toHaveTextContent(
      'El chat no está disponible en este despliegue.',
    );
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('NO DISPONIBLE');
  });

  it('shows the LM Studio local badge and CONFIGURADO under the corporate policy', async () => {
    mockGet.mockResolvedValueOnce({ data: providersBody() });
    const { container } = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    await screen.findByText('LM Studio · Local');
    expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
    expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent('qwen3-32b');
    expect(screen.queryByText('conectado')).toBeNull();
    const panel = container.querySelector<HTMLElement>(
      '[data-slot="ai-chat-panel"]',
    );
    expect(panel?.className).toContain('inset-x-0');
    expect(panel?.className).not.toContain('sm:bottom-4');
    expect(panel?.className).not.toContain('sm:right-4');
    expect(panel?.style.position).toBe('fixed');
    expect(panel?.style.width).toBe('380px');
    expect(panel?.style.left).toBe(`${window.innerWidth - 380 - 16}px`);
  });

  it('shows the no-tool-calls notice for a provider without tool support', async () => {
    mockGet.mockResolvedValueOnce({
      data: providersBody({
        chat_provider: 'ollama',
        supports_tool_calls: { ollama: false, lmstudio: true },
      }),
    });
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    expect(await screen.findByTestId('ai-chat-no-tools-notice')).toHaveTextContent(
      'no soporta llamadas a herramientas',
    );
  });
});

describe('ChatPanel — agent Markdown rendering and focus', () => {
  it('renders agent Markdown safely and keeps raw HTML inert', async () => {
    mockGet.mockResolvedValue({ data: providersBody() });
    mockFetch.mockResolvedValueOnce(
      makeNdjsonResponse([
        '{"type":"text","content":"**negrita** y <script>alert(1)</script>\\n\\n- punto uno\\n- punto dos"}',
        '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
      ]),
    );
    const { container } = renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const input = await screen.findByTestId('ai-chat-input');
    await userEvent.type(input, 'dame markdown');
    await userEvent.click(screen.getByTestId('ai-chat-send'));

    expect(await screen.findByText('negrita')).toBeInTheDocument();
    expect(container.querySelector('strong')?.textContent).toBe('negrita');
    expect(screen.getByText('punto uno')).toBeInTheDocument();
    expect(container.querySelectorAll('ul > li')).toHaveLength(2);

    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
    expect(container.innerHTML).not.toContain('<script');
    expect(container.textContent).toContain('<script>alert(1)</script>');

    const userMessage = screen.getByText('dame markdown');
    expect(userMessage.tagName).toBe('P');
    expect(userMessage.className).toContain('whitespace-pre-wrap');
  });

  it('focuses the input on open and restores focus on close; Escape closes', async () => {
    mockGet.mockResolvedValue({ data: providersBody() });
    const anchor = document.createElement('button');
    anchor.id = 'outside-anchor';
    document.body.appendChild(anchor);
    anchor.focus();
    const onClose = vi.fn();
    const { unmount } = renderWithProviders(<ChatPanel onClose={onClose} />);
    const input = screen.getByTestId('ai-chat-input');
    await waitFor(() => expect(document.activeElement).toBe(input));
    await userEvent.type(input, '{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();
    expect(document.activeElement).toBe(anchor);
    anchor.remove();
  });
});

describe('ChatPanel — confirmation card flow', () => {
  it('shows Confirmar/Cancelar with the args summary and posts the EXACT decision body', async () => {
    mockGet.mockResolvedValue({ data: providersBody() });
    mockFetch
      .mockResolvedValueOnce(
        makeNdjsonResponse(CONFIRMATION_STREAM, { conversationId: 'conv_flow' }),
      )
      .mockResolvedValueOnce(
        makeNdjsonResponse([
          '{"type":"tool_call","invocation_id":"inv_1","name":"generate_sections_manual","args":{},"requires_confirmation":true}',
          '{"type":"tool_result","invocation_id":"inv_1","name":"generate_sections_manual","ok":true,"summary":"1 sección creada","duration_ms":10,"error":null}',
          '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
        ]),
      );
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const input = await screen.findByTestId('ai-chat-input');
    await userEvent.type(input, 'reemplaza las secciones');
    await userEvent.click(screen.getByTestId('ai-chat-send'));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('generate_sections_manual');
    expect(dialog).toHaveTextContent('Reemplaza 2 secciones existentes');

    await userEvent.click(screen.getByTestId('ai-chat-confirm-approve'));
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const [url, init] = mockFetch.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/ai/chat/confirm');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(['approved', 'invocation_id']);
    expect(body).toEqual({ invocation_id: 'inv_1', approved: true });
    expect(await screen.findByText('1 sección creada')).toBeInTheDocument();
    expect(screen.queryByTestId('ai-chat-confirm-approve')).toBeNull();
  });

  it('deny shows the denial informational text and sends approved:false', async () => {
    mockGet.mockResolvedValue({ data: providersBody() });
    mockFetch
      .mockResolvedValueOnce(makeNdjsonResponse(CONFIRMATION_STREAM))
      .mockResolvedValueOnce(
        makeNdjsonResponse([
          '{"type":"tool_result","invocation_id":"inv_1","name":"generate_sections_manual","ok":false,"summary":"","duration_ms":5,"error":"denied_by_user"}',
          '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
        ]),
      );
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const input = await screen.findByTestId('ai-chat-input');
    await userEvent.type(input, 'reemplaza');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    await userEvent.click(await screen.findByTestId('ai-chat-confirm-deny'));
    expect(await screen.findByText('Operación cancelada por el usuario; no se modificó nada.')).toBeInTheDocument();
    const body = JSON.parse(
      String((mockFetch.mock.calls[1] as unknown as [string, RequestInit])[1].body),
    ) as Record<string, unknown>;
    expect(body).toEqual({ invocation_id: 'inv_1', approved: false });
  });
});

describe('ChatPanel — placeholder model handling', () => {
  it('warns, blocks send until the session-only model input is filled, then sends it as model', async () => {
    mockGet.mockResolvedValue({
      data: providersBody({ chat_model: 'loaded-model' }),
    });
    mockFetch.mockResolvedValueOnce(makeNdjsonResponse(CHAT_TEXT_DONE));
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    expect(await screen.findByTestId('ai-chat-placeholder-model-warning')).toHaveTextContent(
      'CONCILIACION_LMSTUDIO_DEFAULT_MODEL',
    );
    const input = screen.getByTestId('ai-chat-input');
    await userEvent.type(input, 'hola');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.getByText('Indica el modelo cargado en LM Studio antes de enviar mensajes.')).toBeInTheDocument();
    expect(input).toHaveValue('hola');

    await userEvent.type(screen.getByTestId('ai-chat-session-model-input'), 'qwen3-32b');
    await userEvent.click(screen.getByTestId('ai-chat-send'));
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(
      String((mockFetch.mock.calls[0] as unknown as [string, RequestInit])[1].body),
    ) as Record<string, unknown>;
    expect(body.model).toBe('qwen3-32b');
  });
});

describe('ChatPanel — a11y and history restore (T5)', () => {
  it('the messages container is a polite live log', async () => {
    mockGet.mockResolvedValue({ data: providersBody() });
    renderWithProviders(<ChatPanel onClose={() => undefined} />);
    const log = await screen.findByTestId('ai-chat-messages');
    expect(log).toHaveAttribute('role', 'log');
    expect(log).toHaveAttribute('aria-live', 'polite');
  });

  it('restores history + pending card from the stored conversation id on mount', async () => {
    window.localStorage.setItem(
      'conciliacion.aiChat.conversationId.sess-panel',
      'conv_rest',
    );
    mockGet.mockResolvedValue({ data: providersBody() });
    mockFetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          exists: true,
          conversation_id: 'conv_rest',
          messages: [
            { role: 'user', content: 'reejecuta la conciliación' },
            {
              role: 'assistant',
              content: 'Voy a reejecutar el proceso.',
              tools: ['run_reconciliation'],
            },
            {
              role: 'tool',
              ok: false,
              summary: 'Operación cancelada por el usuario; no se modificó nada.',
              error: 'denied_by_user',
            },
          ],
          pending: {
            invocation_id: 'inv_rest',
            tool_name: 'run_reconciliation',
            args_summary: 'Reejecutar el proceso de conciliación',
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    mockFetch.mockResolvedValueOnce(
      makeNdjsonResponse([
        '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
      ]),
    );
    renderWithProviders(<ChatPanel onClose={() => undefined} />);

    expect(await screen.findByText('reejecuta la conciliación')).toBeInTheDocument();
    expect(screen.getByText('Voy a reejecutar el proceso.')).toBeInTheDocument();
    expect(
      screen.getByText('Operación cancelada por el usuario; no se modificó nada.'),
    ).toBeInTheDocument();
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('run_reconciliation');
    expect(dialog).toHaveTextContent('Reejecutar el proceso de conciliación');

    await userEvent.click(screen.getByTestId('ai-chat-confirm-approve'));
    const [url, init] = mockFetch.mock.calls[1] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe('/api/v1/ai/chat/confirm');
    expect(JSON.parse(String(init.body))).toEqual({
      invocation_id: 'inv_rest',
      approved: true,
    });
  });
});
